from __future__ import annotations

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from native_transfer import (
    NATIVE_TRANSFER_SIGNATURE_SCHEME,
    NATIVE_TRANSACTION_TYPE,
    NativeTransferMessage,
    build_native_transaction,
    build_transfer_signing_message,
    compute_transaction_id,
    hash_transfer_signing_message,
    recover_signed_wallet_address,
    validate_transaction_shape,
    verify_transfer_signature,
)
from protocol_v1 import (
    OBJECT_TYPE_NATIVE_TRANSFER,
    OBJECT_TYPE_VOTE,
    PUBLIC_TESTNET_V1_NETWORK_ID,
    canonical_domain_hash,
)
from protocol_v1_native_transfer import (
    PROTOCOL_V1_NATIVE_TRANSFER_VERSION,
    build_protocol_v1_native_transfer_message,
    build_protocol_v1_native_transfer_message_hash,
    build_protocol_v1_native_transfer_payload,
    build_protocol_v1_native_transfer_signing_payload,
    calculate_protocol_v1_transaction_id,
    parse_protocol_v1_native_transfer_message,
)
from protocol_v1_originality import build_protocol_v1_vote_message


PRIVATE_KEY = "0x1111111111111111111111111111111111111111111111111111111111111111"
SENDER_WALLET = "0x19e7e376e7c213b7e7e7e46cc70a5dd086daff2a"
RECIPIENT_WALLET = "0x2222222222222222222222222222222222222222"
NETWORK_NAME = "zoidberg-testnet"
NETWORK_ID = PUBLIC_TESTNET_V1_NETWORK_ID
ALT_NETWORK_ID = "zoidberg-devnet-v1"
NONCE = "7"
TIMESTAMP = "2026-08-27T12:34:56+00:00"
AMOUNT = "1.5"
FEE = "0"
MEMO = "native transfer vector"

TRANSFER_PAYLOAD_VECTOR = {
    "amount": "1.5",
    "fee": "0",
    "from_address": SENDER_WALLET,
    "memo": "native transfer vector",
    "nonce": "7",
    "timestamp": "2026-08-27T12:34:56+00:00",
    "to_address": RECIPIENT_WALLET,
    "transaction_version": 1,
}

TRANSFER_SIGNING_PAYLOAD_VECTOR = {
    "domain": "zoidbergchain/native-transfer/v1",
    "network_id": NETWORK_ID,
    "object_type": "native-transfer",
    "payload": TRANSFER_PAYLOAD_VECTOR,
    "protocol": "zoidbergchain",
    "protocol_version": 1,
}

TRANSFER_MESSAGE_VECTOR = (
    '{"domain":"zoidbergchain/native-transfer/v1","network_id":"zoidberg-public-testnet-v1",'
    '"object_type":"native-transfer","payload":{"amount":"1.5","fee":"0",'
    '"from_address":"0x19e7e376e7c213b7e7e7e46cc70a5dd086daff2a","memo":"native transfer vector",'
    '"nonce":"7","timestamp":"2026-08-27T12:34:56+00:00",'
    '"to_address":"0x2222222222222222222222222222222222222222","transaction_version":1},'
    '"protocol":"zoidbergchain","protocol_version":1}'
)
TRANSFER_MESSAGE_HASH_VECTOR = "1285632c6ab851f61f37aae160c04e00b7c663a80e66c7961610e83424ec4bc5"
TRANSFER_TX_ID_VECTOR = "1285632c6ab851f61f37aae160c04e00b7c663a80e66c7961610e83424ec4bc5"
TRANSFER_SIGNATURE_VECTOR = (
    "1100c308111861872d0e239a8bc7a1b8c253997e688bc66a58a7b12f4168289119c940c2c785a5d37ddf9a0fed1b6935"
    "36cc7b414419bd901f0e1a756c0c9a6f1c"
)
ALT_NETWORK_HASH_VECTOR = "d70228dd02ff5641e6f7709b4f5f442460bc17a48314d0021a24abfb698b0c43"
ALT_NETWORK_TX_ID_VECTOR = "d70228dd02ff5641e6f7709b4f5f442460bc17a48314d0021a24abfb698b0c43"
NONCE_MUTATION_TX_ID_VECTOR = "a1779807b5c5e7b7fe8f3c6c14b52ee6f89e5dd8aaab4f6e8ebe9e0a40240ac7"
AMOUNT_MUTATION_TX_ID_VECTOR = "e6dfbb58b54ccdadad8ea869422e003f2cb90f7f5361e83f5e536f0d4467dc2e"
FEE_MUTATION_TX_ID_VECTOR = "4a5b12f9706682c6025370794cd9317387646036b7d78ab043202f4085876726"
MEMO_MUTATION_TX_ID_VECTOR = "edf4715c0a55d7fdf45b51bc95e7da0f4da7d7f7b96c265456ab7a48afd4b93a"
ALT_DOMAIN_HASH_VECTOR = "6317f2fb65b988fbdaa9c6d974802b887c8453a85b04a1a4b31038e155851978"
ALT_PROTOCOL_HASH_VECTOR = "cc62c60d762f1bdfa10e9eb4c521c1e4fc5516cf7c699143b2668607110041dd"

TRANSACTION_VECTOR = {
    "tx_id": TRANSFER_TX_ID_VECTOR,
    "transaction_type": NATIVE_TRANSACTION_TYPE,
    "network": NETWORK_NAME,
    "transaction_version": PROTOCOL_V1_NATIVE_TRANSFER_VERSION,
    "protocol_version": 1,
    "network_id": NETWORK_ID,
    "from_address": SENDER_WALLET,
    "to_address": RECIPIENT_WALLET,
    "amount": AMOUNT,
    "fee": FEE,
    "nonce": NONCE,
    "timestamp": TIMESTAMP,
    "memo": MEMO,
    "signature": TRANSFER_SIGNATURE_VECTOR,
    "signature_scheme": NATIVE_TRANSFER_SIGNATURE_SCHEME,
    "signed_message": TRANSFER_MESSAGE_VECTOR,
    "signed_message_hash": TRANSFER_MESSAGE_HASH_VECTOR,
    "status": "signed_pending",
    "created_at": TIMESTAMP,
    "updated_at": TIMESTAMP,
}


def test_protocol_v1_native_transfer_payload_vector_is_literal():
    assert build_protocol_v1_native_transfer_payload(
        from_address=SENDER_WALLET,
        to_address=RECIPIENT_WALLET,
        amount=AMOUNT,
        fee=FEE,
        nonce=NONCE,
        timestamp=TIMESTAMP,
        memo=MEMO,
    ) == TRANSFER_PAYLOAD_VECTOR


def test_protocol_v1_native_transfer_signing_payload_message_hash_and_tx_id_vectors_are_literal():
    payload = build_protocol_v1_native_transfer_payload(
        from_address=SENDER_WALLET,
        to_address=RECIPIENT_WALLET,
        amount=AMOUNT,
        fee=FEE,
        nonce=NONCE,
        timestamp=TIMESTAMP,
        memo=MEMO,
    )

    assert build_protocol_v1_native_transfer_signing_payload(
        from_address=SENDER_WALLET,
        to_address=RECIPIENT_WALLET,
        amount=AMOUNT,
        fee=FEE,
        nonce=NONCE,
        timestamp=TIMESTAMP,
        memo=MEMO,
        network_id=NETWORK_ID,
    ) == TRANSFER_SIGNING_PAYLOAD_VECTOR
    assert build_protocol_v1_native_transfer_message(
        from_address=SENDER_WALLET,
        to_address=RECIPIENT_WALLET,
        amount=AMOUNT,
        fee=FEE,
        nonce=NONCE,
        timestamp=TIMESTAMP,
        memo=MEMO,
        network_id=NETWORK_ID,
    ) == TRANSFER_MESSAGE_VECTOR
    assert build_protocol_v1_native_transfer_message_hash(
        from_address=SENDER_WALLET,
        to_address=RECIPIENT_WALLET,
        amount=AMOUNT,
        fee=FEE,
        nonce=NONCE,
        timestamp=TIMESTAMP,
        memo=MEMO,
        network_id=NETWORK_ID,
    ) == TRANSFER_MESSAGE_HASH_VECTOR
    assert calculate_protocol_v1_transaction_id(payload, network_id=NETWORK_ID) == TRANSFER_TX_ID_VECTOR
    assert compute_transaction_id(TRANSACTION_VECTOR) == TRANSFER_TX_ID_VECTOR
    assert TRANSFER_MESSAGE_HASH_VECTOR == TRANSFER_TX_ID_VECTOR


def test_protocol_v1_native_transfer_signature_recovery_vector_is_literal():
    signature = Account.sign_message(encode_defunct(text=TRANSFER_MESSAGE_VECTOR), PRIVATE_KEY).signature.hex()

    assert signature == TRANSFER_SIGNATURE_VECTOR
    assert recover_signed_wallet_address(TRANSFER_MESSAGE_VECTOR, signature) == SENDER_WALLET

    verification = verify_transfer_signature(
        TRANSFER_MESSAGE_VECTOR,
        signature,
        SENDER_WALLET,
    )
    assert verification.recovered_from_address == SENDER_WALLET
    assert verification.signed_message_hash == TRANSFER_MESSAGE_HASH_VECTOR


def test_protocol_v1_native_transfer_network_domain_and_protocol_hash_vectors_are_literal():
    assert build_protocol_v1_native_transfer_message_hash(
        from_address=SENDER_WALLET,
        to_address=RECIPIENT_WALLET,
        amount=AMOUNT,
        fee=FEE,
        nonce=NONCE,
        timestamp=TIMESTAMP,
        memo=MEMO,
        network_id=ALT_NETWORK_ID,
    ) == ALT_NETWORK_HASH_VECTOR
    assert calculate_protocol_v1_transaction_id(TRANSFER_PAYLOAD_VECTOR, network_id=ALT_NETWORK_ID) == ALT_NETWORK_TX_ID_VECTOR
    assert canonical_domain_hash(
        TRANSFER_PAYLOAD_VECTOR,
        object_type=OBJECT_TYPE_VOTE,
        network_id=NETWORK_ID,
    ) == ALT_DOMAIN_HASH_VECTOR
    assert canonical_domain_hash(
        TRANSFER_PAYLOAD_VECTOR,
        object_type=OBJECT_TYPE_NATIVE_TRANSFER,
        network_id=NETWORK_ID,
        protocol_version=2,
    ) == ALT_PROTOCOL_HASH_VECTOR
    assert ALT_NETWORK_HASH_VECTOR != TRANSFER_MESSAGE_HASH_VECTOR
    assert ALT_DOMAIN_HASH_VECTOR != TRANSFER_MESSAGE_HASH_VECTOR
    assert ALT_PROTOCOL_HASH_VECTOR != TRANSFER_MESSAGE_HASH_VECTOR


@pytest.mark.parametrize(
    ("field_name", "value", "expected_tx_id"),
    [
        ("nonce", "8", NONCE_MUTATION_TX_ID_VECTOR),
        ("amount", "2", AMOUNT_MUTATION_TX_ID_VECTOR),
        ("fee", "0.25", FEE_MUTATION_TX_ID_VECTOR),
        ("memo", "native transfer vector updated", MEMO_MUTATION_TX_ID_VECTOR),
    ],
)
def test_protocol_v1_native_transfer_mutation_vectors_change_tx_id_and_invalidate_signature(field_name, value, expected_tx_id):
    mutated_payload = dict(TRANSFER_PAYLOAD_VECTOR, **{field_name: value})
    mutated_message = build_protocol_v1_native_transfer_message(
        from_address=mutated_payload["from_address"],
        to_address=mutated_payload["to_address"],
        amount=mutated_payload["amount"],
        fee=mutated_payload["fee"],
        nonce=mutated_payload["nonce"],
        timestamp=mutated_payload["timestamp"],
        memo=mutated_payload["memo"],
        network_id=NETWORK_ID,
    )

    assert calculate_protocol_v1_transaction_id(mutated_payload, network_id=NETWORK_ID) == expected_tx_id
    assert build_protocol_v1_native_transfer_message_hash(
        from_address=mutated_payload["from_address"],
        to_address=mutated_payload["to_address"],
        amount=mutated_payload["amount"],
        fee=mutated_payload["fee"],
        nonce=mutated_payload["nonce"],
        timestamp=mutated_payload["timestamp"],
        memo=mutated_payload["memo"],
        network_id=NETWORK_ID,
    ) == expected_tx_id
    with pytest.raises(ValueError, match="does not match"):
        verify_transfer_signature(mutated_message, TRANSFER_SIGNATURE_VECTOR, SENDER_WALLET)


def test_protocol_v1_native_transfer_message_requires_expected_network():
    parsed = parse_protocol_v1_native_transfer_message(
        TRANSFER_MESSAGE_VECTOR,
        expected_network_id=NETWORK_ID,
    )

    assert parsed["transaction_version"] == 1
    assert parsed["protocol_version"] == 1
    assert parsed["network_id"] == NETWORK_ID

    with pytest.raises(ValueError, match="different network"):
        parse_protocol_v1_native_transfer_message(
            TRANSFER_MESSAGE_VECTOR,
            expected_network_id=ALT_NETWORK_ID,
        )


def test_protocol_v1_native_transaction_shape_accepts_literal_vector():
    transaction = validate_transaction_shape(TRANSACTION_VECTOR, network_name=NETWORK_NAME)

    assert transaction.tx_id == TRANSFER_TX_ID_VECTOR
    assert transaction.transaction_type == NATIVE_TRANSACTION_TYPE
    assert transaction.transaction_version == 1
    assert transaction.protocol_version == 1
    assert transaction.network_id == NETWORK_ID
    assert transaction.signed_message == TRANSFER_MESSAGE_VECTOR

    rebuilt = build_native_transaction(
        network=NETWORK_NAME,
        transaction_version=1,
        protocol_version=1,
        network_id=NETWORK_ID,
        from_address=SENDER_WALLET,
        to_address=RECIPIENT_WALLET,
        amount=AMOUNT,
        fee=FEE,
        nonce=NONCE,
        memo=MEMO,
        timestamp=TIMESTAMP,
        signature=TRANSFER_SIGNATURE_VECTOR,
        signature_scheme=NATIVE_TRANSFER_SIGNATURE_SCHEME,
        signed_message=TRANSFER_MESSAGE_VECTOR,
        signed_message_hash=TRANSFER_MESSAGE_HASH_VECTOR,
        status="signed_pending",
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )
    assert rebuilt.tx_id == TRANSFER_TX_ID_VECTOR


def test_protocol_v1_transaction_id_is_signature_independent_but_field_sensitive():
    signature_variant = dict(TRANSACTION_VECTOR, signature="0x" + ("ab" * 65), signed_message_hash="b" * 64)
    local_field_variant = dict(TRANSACTION_VECTOR, status="mempool", created_at="2026-08-27T12:35:00+00:00")

    assert compute_transaction_id(signature_variant) == TRANSFER_TX_ID_VECTOR
    assert compute_transaction_id(local_field_variant) == TRANSFER_TX_ID_VECTOR


def test_protocol_v1_amount_normalization_is_canonical_and_rejects_scientific_notation():
    amount_one = build_protocol_v1_native_transfer_payload(
        from_address=SENDER_WALLET,
        to_address=RECIPIENT_WALLET,
        amount="1",
        fee=FEE,
        nonce=NONCE,
        timestamp=TIMESTAMP,
        memo=MEMO,
    )
    amount_one_zero = build_protocol_v1_native_transfer_payload(
        from_address=SENDER_WALLET,
        to_address=RECIPIENT_WALLET,
        amount="1.0",
        fee=FEE,
        nonce=NONCE,
        timestamp=TIMESTAMP,
        memo=MEMO,
    )
    amount_one_two_zeroes = build_protocol_v1_native_transfer_payload(
        from_address=SENDER_WALLET,
        to_address=RECIPIENT_WALLET,
        amount="1.00",
        fee=FEE,
        nonce=NONCE,
        timestamp=TIMESTAMP,
        memo=MEMO,
    )

    assert amount_one["amount"] == "1"
    assert amount_one_zero["amount"] == "1"
    assert amount_one_two_zeroes["amount"] == "1"
    assert calculate_protocol_v1_transaction_id(amount_one, network_id=NETWORK_ID) == calculate_protocol_v1_transaction_id(
        amount_one_zero,
        network_id=NETWORK_ID,
    )
    assert calculate_protocol_v1_transaction_id(amount_one, network_id=NETWORK_ID) == calculate_protocol_v1_transaction_id(
        amount_one_two_zeroes,
        network_id=NETWORK_ID,
    )

    with pytest.raises(ValueError, match="Scientific notation"):
        build_protocol_v1_native_transfer_payload(
            from_address=SENDER_WALLET,
            to_address=RECIPIENT_WALLET,
            amount="1e0",
            fee=FEE,
            nonce=NONCE,
            timestamp=TIMESTAMP,
            memo=MEMO,
        )


def test_protocol_v1_transaction_rejects_legacy_signing_message():
    legacy_message = build_transfer_signing_message(
        NativeTransferMessage(
            action="transfer_zoid",
            network=NETWORK_NAME,
            from_address=SENDER_WALLET,
            to_address=RECIPIENT_WALLET,
            amount=AMOUNT,
            nonce=NONCE,
            fee=FEE,
            timestamp=TIMESTAMP,
            memo=MEMO,
            status="signed_pending",
        )
    )

    with pytest.raises(ValueError, match="Protocol v1 native transfer payload"):
        validate_transaction_shape(
            dict(
                TRANSACTION_VECTOR,
                signed_message=legacy_message,
                signed_message_hash=hash_transfer_signing_message(legacy_message),
            ),
            network_name=NETWORK_NAME,
        )


def test_protocol_v1_message_without_explicit_version_never_falls_back_to_legacy():
    legacy_shaped_payload = dict(TRANSACTION_VECTOR)
    legacy_shaped_payload.pop("tx_id")
    legacy_shaped_payload.pop("transaction_version")
    legacy_shaped_payload.pop("protocol_version")
    legacy_shaped_payload.pop("network_id")

    with pytest.raises(ValueError, match="transaction_version is required"):
        validate_transaction_shape(legacy_shaped_payload, network_name=NETWORK_NAME)


def test_protocol_v1_transfer_message_cannot_validate_as_vote_domain():
    vote_message = build_protocol_v1_vote_message(
        wallet_address=SENDER_WALLET,
        submission_id="submission-vector-001",
        content_hash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        vote_type="original",
        nonce="vote-nonce-001",
        issued_at="2026-08-27T12:00:00+00:00",
        expires_at="2026-08-27T12:05:00+00:00",
        network_id=NETWORK_ID,
    )
    vote_signature = Account.sign_message(encode_defunct(text=vote_message), PRIVATE_KEY).signature.hex()

    with pytest.raises(ValueError, match="Protocol v1 native transfer payload"):
        validate_transaction_shape(
            dict(
                TRANSACTION_VECTOR,
                signed_message=vote_message,
                signed_message_hash=hash_transfer_signing_message(vote_message),
                signature=vote_signature,
            ),
            network_name=NETWORK_NAME,
        )
