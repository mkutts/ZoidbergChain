"""Task 4.4 deterministic native-validation equivalence coverage."""

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from native_transfer import (
    NativeTransferMessage,
    build_native_transaction,
    build_transfer_signing_message,
    hash_transfer_signing_message,
)
from protocol_v1 import PROTOCOL_VERSION
from protocol_v1_native_transfer import resolve_protocol_v1_network_id
from services.native_transaction_validation_service import NativeTransactionValidationError
from test_support import fund_native_wallet_with_block


def _signed_transaction(account, *, recipient=None, amount="1", nonce="1", memo="task-4.4", network="zoidberg-testnet"):
    recipient = (recipient or Account.create().address).lower()
    network_id = resolve_protocol_v1_network_id(network_name=network)
    message_fields = NativeTransferMessage(
        action="transfer_zoid", network=network, from_address=account.address.lower(),
        to_address=recipient, amount=amount, nonce=nonce, fee="0",
        timestamp="2026-07-26T00:00:00+00:00", memo=memo,
        transaction_version=PROTOCOL_VERSION, protocol_version=PROTOCOL_VERSION,
        network_id=network_id,
    )
    message = build_transfer_signing_message(message_fields)
    signature = Account.sign_message(encode_defunct(text=message), account.key).signature.hex()
    return build_native_transaction(
        network=network, transaction_version=PROTOCOL_VERSION, protocol_version=PROTOCOL_VERSION,
        network_id=network_id, from_address=message_fields.from_address,
        to_address=message_fields.to_address, amount=amount, fee="0", nonce=nonce,
        memo=memo, timestamp=message_fields.timestamp, signature=signature,
        signature_scheme="personal_sign", signed_message=message,
        signed_message_hash=hash_transfer_signing_message(message), status="signed_pending",
        created_at=message_fields.timestamp, updated_at=message_fields.timestamp,
    ).to_dict()


def test_identity_and_peer_ready_admission_use_the_same_valid_transaction(blockchain):
    account = Account.create()
    fund_native_wallet_with_block(blockchain, account.address, amount="5")
    transaction = _signed_transaction(account, amount="2")

    identity = blockchain._native_ledger_service.validation_service.validate_identity(
        transaction, network_name="zoidberg-testnet"
    )
    admitted = blockchain.admit_received_native_transaction_operation(transaction)

    assert identity["tx_id"] == transaction["tx_id"]
    assert admitted["transaction"]["tx_id"] == transaction["tx_id"]
    assert admitted["transaction"]["status"] == "mempool"
    assert blockchain.admit_received_native_transaction_operation(transaction)["duplicate"] is True


@pytest.mark.parametrize(
    "mutate, expected_code",
    [
        (lambda tx: tx.__setitem__("tx_id", "0" * 64), "invalid_tx_id"),
        (lambda tx: tx.__setitem__("network", "zoidberg-mainnet"), "wrong_network"),
        (lambda tx: tx.__setitem__("transaction_version", 999), "unsupported_version"),
        (lambda tx: tx.__setitem__("signature", Account.sign_message(encode_defunct(text=tx["signed_message"]), Account.create().key).signature.hex()), "sender_signature_mismatch"),
    ],
)
def test_identity_rejection_taxonomy_is_stable(blockchain, mutate, expected_code):
    transaction = _signed_transaction(Account.create())
    mutate(transaction)

    with pytest.raises(NativeTransactionValidationError) as exc_info:
        blockchain._native_ledger_service.validation_service.validate_identity(
            transaction, network_name="zoidberg-testnet"
        )

    assert exc_info.value.code == expected_code


def test_block_selection_order_is_independent_of_arrival_order(blockchain):
    first, second = Account.create(), Account.create()
    fund_native_wallet_with_block(blockchain, first.address, amount="5")
    fund_native_wallet_with_block(blockchain, second.address, amount="5")
    first_tx = _signed_transaction(first, memo="z")
    second_tx = _signed_transaction(second, memo="a")

    blockchain.record_native_transaction(second_tx, status="mempool")
    blockchain.record_native_transaction(first_tx, status="mempool")
    selected = blockchain.select_native_transactions_for_block()["transactions"]

    assert [item["tx_id"] for item in selected] == [
        item["tx_id"]
        for item in sorted((first_tx, second_tx), key=blockchain._native_block_sort_key)
    ]
