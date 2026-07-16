from eth_account import Account
from eth_account.messages import encode_defunct
import pytest

from native_transfer import (
    MAX_TRANSFER_MEMO_LENGTH,
    NATIVE_TRANSFER_ACTION,
    NATIVE_TRANSFER_SIGNATURE_SCHEME,
    NATIVE_TRANSFER_STATUSES,
    build_transfer_signing_message,
    hash_transfer_signing_message,
    parse_native_zoid_amount,
    validate_native_transfer_message,
    verify_transfer_signature,
)


NETWORK_NAME = "zoidberg-testnet"


def _wallet_address() -> str:
    return Account.create().address


def _payload(**overrides):
    payload = {
        "action": NATIVE_TRANSFER_ACTION,
        "network": NETWORK_NAME,
        "from_address": _wallet_address(),
        "to_address": _wallet_address(),
        "amount": "1.5",
        "nonce": "nonce-1",
        "fee": "0",
        "timestamp": "2026-07-15T15:30:00Z",
        "memo": "native transfer preview",
    }
    payload.update(overrides)
    return payload


def _sign_message(message: str, account) -> str:
    signed = Account.sign_message(encode_defunct(text=message), account.key)
    return signed.signature.hex()


def test_valid_transfer_model_accepted():
    transfer = validate_native_transfer_message(_payload(), network_name=NETWORK_NAME)

    assert transfer.action == NATIVE_TRANSFER_ACTION
    assert transfer.network == NETWORK_NAME
    assert transfer.amount == "1.5"
    assert transfer.fee == "0"
    assert transfer.status == "draft"


def test_invalid_action_rejected():
    with pytest.raises(ValueError, match="action must be exactly"):
        validate_native_transfer_message(
            _payload(action="send_zoid"),
            network_name=NETWORK_NAME,
        )


def test_wrong_network_rejected():
    with pytest.raises(ValueError, match="network does not match"):
        validate_native_transfer_message(
            _payload(network="wrong-network"),
            network_name=NETWORK_NAME,
        )


def test_invalid_from_address_rejected():
    with pytest.raises(ValueError, match="from_address"):
        validate_native_transfer_message(
            _payload(from_address="not-a-wallet"),
            network_name=NETWORK_NAME,
        )


def test_invalid_to_address_rejected():
    with pytest.raises(ValueError, match="to_address"):
        validate_native_transfer_message(
            _payload(to_address="not-a-wallet"),
            network_name=NETWORK_NAME,
        )


def test_same_from_and_to_rejected():
    address = _wallet_address()

    with pytest.raises(ValueError, match="must be different"):
        validate_native_transfer_message(
            _payload(from_address=address, to_address=address),
            network_name=NETWORK_NAME,
        )


def test_positive_amount_examples_accepted():
    assert parse_native_zoid_amount("1") == "1"
    assert parse_native_zoid_amount("1.5") == "1.5"
    assert parse_native_zoid_amount("0.000001") == "0.000001"


def test_zero_amount_rejected():
    with pytest.raises(ValueError, match="greater than zero"):
        parse_native_zoid_amount("0")


def test_negative_amount_rejected():
    with pytest.raises(ValueError, match="cannot be negative"):
        parse_native_zoid_amount("-1")


def test_invalid_decimal_amount_rejected():
    for candidate in ["abc", "NaN", "Infinity"]:
        with pytest.raises(ValueError):
            parse_native_zoid_amount(candidate)


def test_excessive_decimal_precision_rejected():
    with pytest.raises(ValueError, match="precision limit"):
        parse_native_zoid_amount("0.0000001")


def test_fee_zero_accepted():
    transfer = validate_native_transfer_message(
        _payload(fee="0"),
        network_name=NETWORK_NAME,
    )

    assert transfer.fee == "0"


def test_negative_fee_rejected():
    with pytest.raises(ValueError, match="cannot be negative"):
        validate_native_transfer_message(
            _payload(fee="-0.1"),
            network_name=NETWORK_NAME,
        )


def test_nonce_required():
    with pytest.raises(ValueError, match="nonce is required"):
        validate_native_transfer_message(
            _payload(nonce=None),
            network_name=NETWORK_NAME,
        )


def test_timestamp_required_and_validated():
    with pytest.raises(ValueError, match="timestamp is required"):
        validate_native_transfer_message(
            _payload(timestamp=""),
            network_name=NETWORK_NAME,
        )

    with pytest.raises(ValueError, match="ISO 8601"):
        validate_native_transfer_message(
            _payload(timestamp="not-a-timestamp"),
            network_name=NETWORK_NAME,
        )


def test_memo_length_limit_enforced():
    with pytest.raises(ValueError, match="character limit"):
        validate_native_transfer_message(
            _payload(memo="x" * (MAX_TRANSFER_MEMO_LENGTH + 1)),
            network_name=NETWORK_NAME,
        )


def test_transfer_statuses_are_defined_for_future_flow():
    assert NATIVE_TRANSFER_STATUSES == (
        "draft",
        "signed",
        "signed_pending",
        "pending",
        "rejected",
        "included",
        "failed",
    )


def test_signing_message_is_deterministic():
    transfer = validate_native_transfer_message(_payload(), network_name=NETWORK_NAME)

    first = build_transfer_signing_message(transfer)
    second = build_transfer_signing_message(transfer)

    assert first == second


def test_signing_message_includes_required_fields_and_warning():
    transfer = validate_native_transfer_message(_payload(), network_name=NETWORK_NAME)
    message = build_transfer_signing_message(transfer)

    assert "ZoidbergChain Native Transfer" in message
    assert f"Network: {transfer.network}" in message
    assert f"From: {transfer.from_address}" in message
    assert f"To: {transfer.to_address}" in message
    assert f"Amount: {transfer.amount}" in message
    assert f"Fee: {transfer.fee}" in message
    assert f"Nonce: {transfer.nonce}" in message
    assert f"Timestamp: {transfer.timestamp}" in message
    assert "This authorizes a native ZOID transfer on ZoidbergChain." in message
    assert "This is not an Ethereum/ERC-20 transfer." in message


def test_message_hash_changes_when_amount_to_or_nonce_changes():
    transfer = validate_native_transfer_message(_payload(), network_name=NETWORK_NAME)
    original_hash = hash_transfer_signing_message(build_transfer_signing_message(transfer))

    changed_amount = validate_native_transfer_message(
        _payload(amount="2"),
        network_name=NETWORK_NAME,
    )
    changed_to = validate_native_transfer_message(
        _payload(to_address=_wallet_address()),
        network_name=NETWORK_NAME,
    )
    changed_nonce = validate_native_transfer_message(
        _payload(nonce=2),
        network_name=NETWORK_NAME,
    )

    assert hash_transfer_signing_message(build_transfer_signing_message(changed_amount)) != original_hash
    assert hash_transfer_signing_message(build_transfer_signing_message(changed_to)) != original_hash
    assert hash_transfer_signing_message(build_transfer_signing_message(changed_nonce)) != original_hash


def test_valid_signature_verifies():
    account = Account.create()
    transfer = validate_native_transfer_message(
        _payload(from_address=account.address),
        network_name=NETWORK_NAME,
    )
    message = build_transfer_signing_message(transfer)
    signature = _sign_message(message, account)

    result = verify_transfer_signature(message, signature, transfer.from_address)

    assert result.verified is True
    assert result.expected_from_address == transfer.from_address
    assert result.recovered_from_address == transfer.from_address
    assert result.signature_scheme == NATIVE_TRANSFER_SIGNATURE_SCHEME
    assert result.signed_message_hash == hash_transfer_signing_message(message)


def test_wrong_signer_rejected():
    account = Account.create()
    wrong_account = Account.create()
    transfer = validate_native_transfer_message(
        _payload(from_address=account.address),
        network_name=NETWORK_NAME,
    )
    message = build_transfer_signing_message(transfer)
    signature = _sign_message(message, wrong_account)

    with pytest.raises(ValueError, match="does not match"):
        verify_transfer_signature(message, signature, transfer.from_address)


def test_modified_message_rejected():
    account = Account.create()
    transfer = validate_native_transfer_message(
        _payload(from_address=account.address),
        network_name=NETWORK_NAME,
    )
    message = build_transfer_signing_message(transfer)
    signature = _sign_message(message, account)

    with pytest.raises(ValueError, match="does not match"):
        verify_transfer_signature(message + "\nModified", signature, transfer.from_address)


def test_malformed_signature_rejected():
    transfer = validate_native_transfer_message(_payload(), network_name=NETWORK_NAME)

    with pytest.raises(ValueError, match="Malformed signature"):
        verify_transfer_signature(
            build_transfer_signing_message(transfer),
            "bad-signature",
            transfer.from_address,
        )
