from __future__ import annotations

import json
from pathlib import Path

from eth_account import Account
from eth_account.messages import encode_defunct

from block import Block
from native_transfer import recover_signed_wallet_address as recover_transfer_wallet
from peer_sync import build_peer_signature_payload
from protocol_v1 import (
    OBJECT_TYPE_GENESIS,
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    PUBLIC_TESTNET_V1_NETWORK_ID,
    canonical_domain_hash,
    canonical_hash,
    canonical_json_text,
    decode_canonical_bytes,
    encode_canonical_bytes,
)
from protocol_v1_genesis import (
    PUBLIC_TESTNET_V1_CANONICAL_GENESIS_HASH,
    PUBLIC_TESTNET_V1_GENESIS_VERSION,
    canonical_public_testnet_v1_genesis_hash,
    canonical_public_testnet_v1_genesis_payload,
    canonical_public_testnet_v1_genesis_record,
)
from protocol_v1_native_transfer import (
    build_protocol_v1_native_transfer_message,
    build_protocol_v1_native_transfer_message_hash,
    build_protocol_v1_native_transfer_payload,
    build_protocol_v1_native_transfer_signing_payload,
    calculate_protocol_v1_transaction_id,
)
from protocol_v1_originality import (
    build_protocol_v1_certificate_identity_payload,
    build_protocol_v1_vote_message,
    build_protocol_v1_vote_message_hash,
    build_protocol_v1_vote_payload,
    build_protocol_v1_vote_set_payload,
    build_protocol_v1_vote_signing_payload,
    calculate_protocol_v1_certificate_id,
    calculate_protocol_v1_vote_hash,
)
from protocol_v1_peer_message import (
    calculate_protocol_v1_peer_message_id,
    protocol_v1_peer_envelope_text,
    sign_protocol_v1_peer_message,
)
from wallet_auth import hash_wallet_message, recover_signed_wallet_address


FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "protocol_v1_golden_vectors.json"
PRIVATE_KEY = "0x1111111111111111111111111111111111111111111111111111111111111111"
PEER_SECRET = "test-only-peer-secret"


def _load_vectors() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _build_vector_block(constructor: dict, **overrides) -> Block:
    fields = dict(constructor)
    media_bytes_hex = fields.pop("media_bytes_hex")
    fields["media_bytes"] = bytes.fromhex(media_bytes_hex)
    fields.update(overrides)
    return Block(**fields)


def test_protocol_v1_golden_fixture_matches_protocol_identity():
    vectors = _load_vectors()

    assert vectors["protocol"]["name"] == PROTOCOL_NAME
    assert vectors["protocol"]["version"] == PROTOCOL_VERSION
    assert vectors["protocol"]["network_id"] == PUBLIC_TESTNET_V1_NETWORK_ID
    assert vectors["protocol"]["genesis_hash"] == PUBLIC_TESTNET_V1_CANONICAL_GENESIS_HASH


def test_canonical_serialization_vectors_match_runtime():
    vectors = _load_vectors()["canonical_serialization"]

    for vector in vectors["simple_vectors"]:
        logical_input = vector["logical_input"]
        assert canonical_json_text(logical_input) == vector["canonical_json"]
        assert canonical_hash(logical_input) == vector["hash"]

    bytes_vector = vectors["bytes_vector"]
    logical_bytes = bytes.fromhex(bytes_vector["logical_hex"])
    assert encode_canonical_bytes(logical_bytes) == bytes_vector["canonical_object"]
    assert decode_canonical_bytes(bytes_vector["canonical_object"]) == logical_bytes
    assert canonical_json_text(logical_bytes) == bytes_vector["canonical_json"]


def test_block_vectors_match_runtime():
    vectors = _load_vectors()["block"]
    constructor = vectors["base"]["constructor"]
    base_block = _build_vector_block(constructor)
    media_mutated = _build_vector_block(
        constructor,
        media_bytes=b"protocol-v1-medib",
    )
    metadata_mutated = _build_vector_block(
        constructor,
        certificate_id="certificate-124",
    )
    other_network = _build_vector_block(
        constructor,
        network_id="zoidberg-devnet-v1",
    )
    native_tx_a = {
        "tx_id": "a" * 64,
        "transaction_type": "native_transfer",
        "network": "zoidberg-testnet",
        "from_address": "0x2222222222222222222222222222222222222222",
        "to_address": "0x3333333333333333333333333333333333333333",
        "amount": "1.5",
        "fee": "0",
        "nonce": 1,
        "memo": "first",
        "timestamp": "2026-08-27T12:00:00Z",
        "signature": "0xaaa",
        "signature_scheme": "personal_sign",
        "signed_message": "first-msg",
        "signed_message_hash": "1" * 64,
    }
    native_tx_b = {
        "tx_id": "b" * 64,
        "transaction_type": "native_transfer",
        "network": "zoidberg-testnet",
        "from_address": "0x4444444444444444444444444444444444444444",
        "to_address": "0x5555555555555555555555555555555555555555",
        "amount": "2.5",
        "fee": "0",
        "nonce": 1,
        "memo": "second",
        "timestamp": "2026-08-27T12:05:00Z",
        "signature": "0xbbb",
        "signature_scheme": "personal_sign",
        "signed_message": "second-msg",
        "signed_message_hash": "2" * 64,
    }
    order_ab = _build_vector_block(
        constructor,
        native_transactions=[native_tx_a, native_tx_b],
        transaction_ids=[native_tx_a["tx_id"], native_tx_b["tx_id"]],
        transaction_count=2,
        transactions_hash="order-ab",
    )
    order_ba = _build_vector_block(
        constructor,
        native_transactions=[native_tx_b, native_tx_a],
        transaction_ids=[native_tx_b["tx_id"], native_tx_a["tx_id"]],
        transaction_count=2,
        transactions_hash="order-ba",
    )

    assert base_block.consensus_payload_v1_bytes().decode("utf-8") == vectors["base"]["consensus_payload_json"]
    assert base_block.hash == vectors["base"]["hash"]
    assert media_mutated.hash == vectors["mutations"]["media_bytes_hash"]
    assert metadata_mutated.hash == vectors["mutations"]["metadata_hash"]
    assert other_network.hash == vectors["mutations"]["other_network_hash"]
    assert order_ab.hash == vectors["mutations"]["order_ab_hash"]
    assert order_ba.hash == vectors["mutations"]["order_ba_hash"]


def test_vote_and_certificate_vectors_match_runtime():
    vectors = _load_vectors()
    vote = vectors["vote"]
    certificate = vectors["certificate"]

    assert build_protocol_v1_vote_payload(
        wallet_address=vote["payload"]["voter_wallet_address"],
        submission_id=vote["payload"]["submission_id"],
        content_hash=vote["payload"]["content_hash"],
        vote_type=vote["payload"]["vote_type"],
        nonce=vote["payload"]["nonce"],
        issued_at=vote["payload"]["issued_at"],
        expires_at=vote["payload"]["expires_at"],
    ) == vote["payload"]
    assert build_protocol_v1_vote_signing_payload(
        wallet_address=vote["payload"]["voter_wallet_address"],
        submission_id=vote["payload"]["submission_id"],
        content_hash=vote["payload"]["content_hash"],
        vote_type=vote["payload"]["vote_type"],
        nonce=vote["payload"]["nonce"],
        issued_at=vote["payload"]["issued_at"],
        expires_at=vote["payload"]["expires_at"],
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
    ) == vote["signing_payload"]
    assert build_protocol_v1_vote_message(
        wallet_address=vote["payload"]["voter_wallet_address"],
        submission_id=vote["payload"]["submission_id"],
        content_hash=vote["payload"]["content_hash"],
        vote_type=vote["payload"]["vote_type"],
        nonce=vote["payload"]["nonce"],
        issued_at=vote["payload"]["issued_at"],
        expires_at=vote["payload"]["expires_at"],
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
    ) == vote["message"]
    assert build_protocol_v1_vote_message_hash(
        wallet_address=vote["payload"]["voter_wallet_address"],
        submission_id=vote["payload"]["submission_id"],
        content_hash=vote["payload"]["content_hash"],
        vote_type=vote["payload"]["vote_type"],
        nonce=vote["payload"]["nonce"],
        issued_at=vote["payload"]["issued_at"],
        expires_at=vote["payload"]["expires_at"],
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
    ) == vote["message_hash"]
    assert hash_wallet_message(vote["message"]) == vote["message_hash"]
    signature = Account.sign_message(encode_defunct(text=vote["message"]), PRIVATE_KEY).signature.hex()
    assert signature == vote["signature"]
    assert recover_signed_wallet_address(vote["message"], signature) == vote["recovered_wallet"]

    vote_set_votes = [
        {
            "voter": entry["voter"],
            "vote_type": entry["vote_type"],
        }
        for entry in vote["vote_set_payload"]["votes"]
    ]
    assert build_protocol_v1_vote_set_payload(
        vote_set_votes,
        submission_id=vote["vote_set_payload"]["submission_id"],
        content_hash=vote["vote_set_payload"]["content_hash"],
    ) == vote["vote_set_payload"]
    assert calculate_protocol_v1_vote_hash(
        vote_set_votes,
        submission_id=vote["vote_set_payload"]["submission_id"],
        content_hash=vote["vote_set_payload"]["content_hash"],
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
    ) == vote["vote_hash"]
    assert build_protocol_v1_certificate_identity_payload(certificate["identity_payload"]) == certificate["identity_payload"]

    certificate_fields = {
        **certificate["identity_payload"],
        "protocol_version": PROTOCOL_VERSION,
        "network_id": PUBLIC_TESTNET_V1_NETWORK_ID,
        "approved_at": 1724760001.25,
        "issuing_node_id": "node-1",
        "content_id": "ignored-content-id",
        "network_name": "zoidberg-testnet",
    }
    insensitive_mutation = {
        **certificate_fields,
        **certificate["metadata_insensitive_mutation"],
    }
    assert calculate_protocol_v1_certificate_id(
        certificate_fields,
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
    ) == certificate["certificate_id"]
    assert calculate_protocol_v1_certificate_id(
        insensitive_mutation,
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
    ) == certificate["certificate_id"]


def test_native_transfer_vectors_match_runtime():
    vectors = _load_vectors()["native_transfer"]

    assert build_protocol_v1_native_transfer_payload(
        from_address=vectors["payload"]["from_address"],
        to_address=vectors["payload"]["to_address"],
        amount=vectors["payload"]["amount"],
        fee=vectors["payload"]["fee"],
        nonce=vectors["payload"]["nonce"],
        timestamp=vectors["payload"]["timestamp"],
        memo=vectors["payload"]["memo"],
    ) == vectors["payload"]
    assert build_protocol_v1_native_transfer_signing_payload(
        from_address=vectors["payload"]["from_address"],
        to_address=vectors["payload"]["to_address"],
        amount=vectors["payload"]["amount"],
        fee=vectors["payload"]["fee"],
        nonce=vectors["payload"]["nonce"],
        timestamp=vectors["payload"]["timestamp"],
        memo=vectors["payload"]["memo"],
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
    ) == vectors["signing_payload"]
    assert build_protocol_v1_native_transfer_message(
        from_address=vectors["payload"]["from_address"],
        to_address=vectors["payload"]["to_address"],
        amount=vectors["payload"]["amount"],
        fee=vectors["payload"]["fee"],
        nonce=vectors["payload"]["nonce"],
        timestamp=vectors["payload"]["timestamp"],
        memo=vectors["payload"]["memo"],
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
    ) == vectors["message"]
    assert build_protocol_v1_native_transfer_message_hash(
        from_address=vectors["payload"]["from_address"],
        to_address=vectors["payload"]["to_address"],
        amount=vectors["payload"]["amount"],
        fee=vectors["payload"]["fee"],
        nonce=vectors["payload"]["nonce"],
        timestamp=vectors["payload"]["timestamp"],
        memo=vectors["payload"]["memo"],
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
    ) == vectors["message_hash"]
    assert calculate_protocol_v1_transaction_id(
        vectors["payload"],
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
    ) == vectors["tx_id"]
    signature = Account.sign_message(encode_defunct(text=vectors["message"]), PRIVATE_KEY).signature.hex()
    assert signature == vectors["signature"]
    assert recover_transfer_wallet(vectors["message"], signature) == vectors["recovered_wallet"]


def test_peer_message_vectors_match_runtime():
    vectors = _load_vectors()["peer_message"]
    envelope = vectors["envelope"]

    assert protocol_v1_peer_envelope_text(
        vectors["payload"],
        network_id=envelope["network_id"],
        message_type=envelope["message_type"],
        sender_node_id=envelope["sender_node_id"],
        timestamp=envelope["timestamp"],
        nonce=envelope["nonce"],
    ) == vectors["message"]
    assert calculate_protocol_v1_peer_message_id(
        vectors["payload"],
        network_id=envelope["network_id"],
        message_type=envelope["message_type"],
        sender_node_id=envelope["sender_node_id"],
        timestamp=envelope["timestamp"],
        nonce=envelope["nonce"],
    ) == vectors["message_id"]
    assert sign_protocol_v1_peer_message(
        vectors["payload"],
        network_id=envelope["network_id"],
        message_type=envelope["message_type"],
        sender_node_id=envelope["sender_node_id"],
        timestamp=envelope["timestamp"],
        nonce=envelope["nonce"],
        secret=PEER_SECRET,
    ) == vectors["hmac"]


def test_genesis_vectors_match_runtime():
    vectors = _load_vectors()["genesis"]

    assert PUBLIC_TESTNET_V1_GENESIS_VERSION == vectors["version"]
    assert canonical_public_testnet_v1_genesis_payload() == vectors["payload"]
    assert canonical_public_testnet_v1_genesis_hash() == vectors["hash"]
    assert canonical_public_testnet_v1_genesis_record() == vectors["record"]
    assert Block.from_dict(vectors["record"]).hash == vectors["hash"]
    assert canonical_domain_hash(
        vectors["payload"],
        object_type=OBJECT_TYPE_GENESIS,
        network_id="zoidberg-public-testnet-v1-reset-1",
    ) == vectors["alternate_hashes"]["network"]
    mutated_payload = dict(vectors["payload"], timestamp=1785542401)
    assert canonical_domain_hash(
        mutated_payload,
        object_type=OBJECT_TYPE_GENESIS,
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
    ) == vectors["alternate_hashes"]["timestamp"]


def test_legacy_control_vectors_remain_distinct_from_protocol_v1_vectors():
    assert build_peer_signature_payload(
        "POST",
        "/peers/block",
        1724760000,
        "nonce-1",
        "f" * 64,
    ) != _load_vectors()["peer_message"]["message"]
