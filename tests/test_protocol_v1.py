from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from block import Block, PROTOCOL_V1_BLOCK_VERSION
from content import calculate_content_id
from native_transfer import (
    NativeTransferMessage,
    NATIVE_TRANSFER_SIGNATURE_SCHEME,
    build_transfer_signing_message,
    build_native_transaction,
    compute_transaction_id,
    hash_transfer_signing_message,
)
from originality_certificate import calculate_certificate_id
from peer_sync import build_peer_signature_payload
from protocol_v1 import (
    LEGACY_PUBLIC_TESTNET_NETWORK_NAME,
    OBJECT_TYPE_BLOCK,
    OBJECT_TYPE_NATIVE_TRANSFER,
    OBJECT_TYPE_VOTE,
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    PUBLIC_TESTNET_V1_NETWORK_ID,
    build_domain_envelope,
    canonical_domain_bytes,
    canonical_domain_hash,
    canonical_hash,
    canonical_json_bytes,
    canonical_json_text,
    current_runtime_network_id,
    decode_canonical_bytes,
    encode_canonical_bytes,
    normalize_network_id,
    protocol_domain,
    resolve_network_id,
)
from transaction import Transaction
from wallet_auth import build_wallet_vote_message


def test_protocol_identity_constants_are_explicit():
    assert PROTOCOL_NAME == "zoidbergchain"
    assert PROTOCOL_VERSION == 1
    assert PUBLIC_TESTNET_V1_NETWORK_ID == "zoidberg-public-testnet-v1"
    assert LEGACY_PUBLIC_TESTNET_NETWORK_NAME == "zoidberg-testnet"
    assert protocol_domain(OBJECT_TYPE_VOTE) == "zoidbergchain/vote/v1"
    assert protocol_domain(OBJECT_TYPE_NATIVE_TRANSFER) == "zoidbergchain/native-transfer/v1"


def test_network_id_normalization_and_resolution_are_explicit(monkeypatch):
    assert normalize_network_id(" ZOIDBERG-PUBLIC-TESTNET-V1 ") == PUBLIC_TESTNET_V1_NETWORK_ID
    assert resolve_network_id(network_name="zoidberg-testnet") == PUBLIC_TESTNET_V1_NETWORK_ID

    import config

    monkeypatch.setattr(config, "NETWORK_NAME", "zoidberg-testnet")
    assert current_runtime_network_id() == PUBLIC_TESTNET_V1_NETWORK_ID


def test_network_id_rejects_invalid_values():
    with pytest.raises(ValueError, match="Invalid network_id"):
        normalize_network_id("not valid!")

    with pytest.raises(ValueError, match="Unknown network_name"):
        resolve_network_id(network_name="future-network")


@pytest.mark.parametrize(
    ("value", "expected_text"),
    [
        ("hello", '"hello"'),
        ("", '""'),
        ("hello\nworld", '"hello\\nworld"'),
        ("cafe", '"cafe"'),
        ("caf\u00e9", '"caf\u00e9"'),
        (0, "0"),
        (1, "1"),
        (-1, "-1"),
        (2**80, str(2**80)),
        (True, "true"),
        (False, "false"),
        (None, "null"),
    ],
)
def test_primitive_determinism(value, expected_text):
    assert canonical_json_text(value) == expected_text
    assert canonical_json_text(value) == canonical_json_text(value)
    assert canonical_json_bytes(value) == expected_text.encode("utf-8")


def test_dictionary_insertion_order_does_not_change_bytes():
    first = {"b": 2, "a": 1}
    second = {"a": 1, "b": 2}

    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert canonical_hash(first) == canonical_hash(second)


def test_nested_dictionary_insertion_order_does_not_change_bytes():
    first = {
        "payload": {
            "z": 3,
            "a": 1,
            "nested": {
                "beta": 2,
                "alpha": 1,
            },
        }
    }
    second = {
        "payload": {
            "nested": {
                "alpha": 1,
                "beta": 2,
            },
            "a": 1,
            "z": 3,
        }
    }

    assert canonical_json_bytes(first) == canonical_json_bytes(second)


def test_list_order_remains_significant():
    first = {"items": [1, 2, 3]}
    second = {"items": [3, 2, 1]}

    assert canonical_json_bytes(first) != canonical_json_bytes(second)
    assert canonical_hash(first) != canonical_hash(second)


@pytest.mark.parametrize(
    "value",
    [
        1.5,
        float("nan"),
        float("inf"),
        float("-inf"),
        Decimal("1.5"),
        {"bad": {1, 2}},
        object(),
        {1: "bad-key"},
        ("tuple",),
    ],
)
def test_unsupported_or_unsafe_values_fail_loudly(value):
    with pytest.raises(ValueError):
        canonical_json_text(value)


def test_bytes_are_deterministic_and_round_trip():
    payload = b"\x00\xffabc\x80"
    encoded = encode_canonical_bytes(payload)

    assert encoded == {
        "$type": "bytes",
        "$encoding": "hex",
        "$value": "00ff61626380",
    }
    assert decode_canonical_bytes(encoded) == payload
    assert canonical_json_text(payload) == '{"$encoding":"hex","$type":"bytes","$value":"00ff61626380"}'


def test_empty_bytes_are_supported():
    encoded = encode_canonical_bytes(b"")

    assert encoded["$value"] == ""
    assert decode_canonical_bytes(encoded) == b""


def test_non_utf8_bytes_are_supported():
    payload = bytes([0x00, 0x81, 0xfe, 0xff])

    assert decode_canonical_bytes(encode_canonical_bytes(payload)) == payload


def test_reserved_bytes_shape_is_rejected_for_raw_dictionaries():
    with pytest.raises(ValueError, match="reserves the exact"):
        canonical_json_text(
            {
                "$type": "bytes",
                "$encoding": "hex",
                "$value": "00ff",
            }
        )


def test_reserved_bytes_shape_does_not_collide_with_actual_bytes():
    payload = b"\x00\xff"

    assert canonical_json_text(payload) == '{"$encoding":"hex","$type":"bytes","$value":"00ff"}'
    with pytest.raises(ValueError):
        canonical_json_text(
            {
                "$type": "bytes",
                "$encoding": "hex",
                "$value": "00ff",
            }
        )


def test_domain_envelope_binds_protocol_version_network_object_type_and_payload():
    envelope = build_domain_envelope(
        {"submission_id": "abc123", "vote": "original"},
        object_type=OBJECT_TYPE_VOTE,
    )

    assert envelope == {
        "domain": "zoidbergchain/vote/v1",
        "network_id": "zoidberg-public-testnet-v1",
        "object_type": "vote",
        "payload": {"submission_id": "abc123", "vote": "original"},
        "protocol": "zoidbergchain",
        "protocol_version": 1,
    }


def test_domain_separation_changes_bytes_and_hashes():
    payload = {"id": "same-payload"}

    vote_bytes = canonical_domain_bytes(payload, object_type=OBJECT_TYPE_VOTE)
    transfer_bytes = canonical_domain_bytes(payload, object_type=OBJECT_TYPE_NATIVE_TRANSFER)
    other_network_bytes = canonical_domain_bytes(
        payload,
        object_type=OBJECT_TYPE_VOTE,
        network_id="zoidberg-devnet-v1",
    )
    other_version_bytes = canonical_domain_bytes(
        payload,
        object_type=OBJECT_TYPE_VOTE,
        protocol_version=2,
    )

    assert vote_bytes != transfer_bytes
    assert vote_bytes != other_network_bytes
    assert vote_bytes != other_version_bytes
    assert canonical_domain_hash(payload, object_type=OBJECT_TYPE_VOTE) != canonical_domain_hash(
        payload,
        object_type=OBJECT_TYPE_NATIVE_TRANSFER,
    )


def test_payload_mutation_changes_domain_hash():
    first = {"id": "vote-1", "choice": "original"}
    second = {"id": "vote-1", "choice": "not_original"}

    assert canonical_domain_hash(first, object_type=OBJECT_TYPE_VOTE) != canonical_domain_hash(
        second,
        object_type=OBJECT_TYPE_VOTE,
    )


def test_foundation_golden_hash_vectors():
    assert canonical_hash({"a": 1}) == "015abd7f5cc57a2dd94b7590f04ad8084273905ee33ec5cebeae62276a97f862"
    assert canonical_hash({"a": [1, True, None, "zoid"]}) == "edd510ce70d225d512ee05cf6f1bcf1b56919c9c4129649500fd965c52c4070d"
    assert canonical_domain_hash({"a": 1}, object_type=OBJECT_TYPE_VOTE) == "145c78076a9c3bbf094dc53c39ee5628d879b7f477b19e7272e28df42e1105c2"
    assert canonical_domain_hash(
        {"a": b"\x00\xff"},
        object_type=OBJECT_TYPE_NATIVE_TRANSFER,
    ) == "dbfd59c1af5bfa2af86e04db1e5ad8a0b0f3a254cfcd52fc41c26be0c4e9aa82"


def test_stability_repeated_serialization_and_hashing():
    payload = {
        "network_id": PUBLIC_TESTNET_V1_NETWORK_ID,
        "payload": {"bytes": b"\x00\x01", "value": 7},
    }

    first_bytes = canonical_json_bytes(payload)
    second_bytes = canonical_json_bytes(payload)
    first_hash = canonical_hash(payload)
    second_hash = canonical_hash(payload)

    assert first_bytes == second_bytes
    assert first_hash == second_hash


def test_legacy_vote_message_remains_unchanged():
    message = build_wallet_vote_message(
        wallet_address="0x1234567890abcdef1234567890abcdef12345678",
        submission_id="submission-123",
        content_hash="a" * 64,
        vote_type="original",
        network_name="zoidberg-testnet",
        nonce="vote-nonce",
        issued_at=datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc),
        expires_at=datetime(2026, 8, 27, 12, 5, 0, tzinfo=timezone.utc),
    )

    assert message == (
        "ZoidbergChain Vote Authorization\n\n"
        "Action: vote_originality\n"
        "Network: zoidberg-testnet\n"
        "Wallet: 0x1234567890abcdef1234567890abcdef12345678\n"
        "Submission ID: submission-123\n"
        f"Content Hash: {'a' * 64}\n"
        "Vote: original\n"
        "Nonce: vote-nonce\n"
        "Issued At: 2026-08-27T12:00:00+00:00\n"
        "Expires At: 2026-08-27T12:05:00+00:00\n\n"
        "This signature proves the wallet is casting this originality vote on ZoidbergChain.\n"
        "It does not authorize a token transfer."
    )


def test_legacy_transfer_message_and_tx_id_remain_unchanged():
    message = NativeTransferMessage(
        action="transfer_zoid",
        network="zoidberg-testnet",
        from_address="0x1234567890abcdef1234567890abcdef12345678",
        to_address="0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
        amount="1.5",
        nonce="7",
        fee="0",
        timestamp="2026-08-27T12:00:00Z",
        memo="foundation regression",
    )
    signed_message = build_transfer_signing_message(message)
    transaction = build_native_transaction(
        network="zoidberg-testnet",
        from_address="0x1234567890abcdef1234567890abcdef12345678",
        to_address="0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
        amount="1.5",
        nonce="7",
        fee="0",
        timestamp="2026-08-27T12:00:00Z",
        memo="foundation regression",
        signature="0xdeadbeef",
        signature_scheme=NATIVE_TRANSFER_SIGNATURE_SCHEME,
        signed_message=signed_message,
        signed_message_hash=hash_transfer_signing_message(signed_message),
        status="signed_pending",
        created_at="2026-08-27T12:00:00Z",
        updated_at="2026-08-27T12:00:00Z",
    )

    assert signed_message == (
        "ZoidbergChain Native Transfer\n\n"
        "Action: transfer_zoid\n"
        "Network: zoidberg-testnet\n"
        "From: 0x1234567890abcdef1234567890abcdef12345678\n"
        "To: 0xabcdefabcdefabcdefabcdefabcdefabcdefabcd\n"
        "Amount: 1.5\n"
        "Fee: 0\n"
        "Nonce: 7\n"
        "Timestamp: 2026-08-27T12:00:00Z\n"
        "Memo: foundation regression\n\n"
        "This authorizes a native ZOID transfer on ZoidbergChain.\n"
        "This is not an Ethereum/ERC-20 transfer."
    )
    assert compute_transaction_id(transaction) == "c742b5776921e7cf76b28815f55d9e300351fc09dd3bf10fc8212a839afd9c38"


def test_legacy_certificate_id_remains_unchanged():
    certificate_id = calculate_certificate_id(
        {
            "approval_percentage": 0.8,
            "content_hash": "b" * 64,
            "creator_wallet": "0x1234567890abcdef1234567890abcdef12345678",
            "decisive_vote_total": 5,
            "issuing_node_id": "node-certifier",
            "minimum_votes_required": 5,
            "network_name": "zoidberg-testnet",
            "not_original_votes": 1,
            "original_votes": 4,
            "submission_id": "submission-123",
            "unsure_votes": 2,
            "vote_hash": "c" * 64,
            "vote_total": 7,
        }
    )

    assert certificate_id == "1df42f535e45bda2f0ad664a31ba3e8b8c39126b9d70343a868555dd24cf4c0d"


def test_legacy_peer_signature_payload_remains_unchanged():
    payload = build_peer_signature_payload(
        "POST",
        "/peers/block",
        1724760000,
        "nonce-1",
        "f" * 64,
    )

    assert payload == (
        "POST\n"
        "/peers/block\n"
        "1724760000\n"
        "nonce-1\n"
        "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    )


def test_legacy_block_hash_remains_unchanged():
    block = Block(
        index=3,
        previous_hash="0" * 64,
        timestamp=1724760000.5,
        transactions=[
            Transaction(
                sender="alice",
                recipient="bob",
                amount=1.25,
                tip=0.1,
                payload_size_kb=2.5,
                signature="sig-1",
                created_at=1724760000.5,
            )
        ],
        miner="miner-1",
        meme={"encoded_image": "img", "text": "hello"},
    )

    assert block.hash == "6388dc58dd68eeddba87987db34cd03dd60a157eae9e1459293d4b433ad87f32"


def _protocol_v1_vector_block(**overrides):
    media_bytes = overrides.pop("media_bytes", b"protocol-v1-media")
    media_hash = hashlib.sha256(media_bytes).hexdigest()
    content_hash = overrides.pop("content_hash", media_hash)
    base = {
        "index": 7,
        "previous_hash": "0" * 64,
        "timestamp": 1724760000.5,
        "transactions": [
            Transaction(
                sender="REWARD_POOL",
                recipient="0x1111111111111111111111111111111111111111",
                amount=5.0,
                created_at=1724760000.5,
            )
        ],
        "miner": "0x1111111111111111111111111111111111111111",
        "meme": {
            "encoded_image": "cHJvdG9jb2wtdjEtbWVkaWE=",
            "text": "Protocol v1 vector",
        },
        "block_version": PROTOCOL_V1_BLOCK_VERSION,
        "network_id": PUBLIC_TESTNET_V1_NETWORK_ID,
        "media_hash": overrides.pop("media_hash", media_hash),
        "media_bytes": media_bytes,
        "submission_id": "submission-123",
        "certificate_id": "certificate-123",
        "content_hash": content_hash,
        "content_id": calculate_content_id(content_hash),
        "content_type": "text",
        "mime_type": "text/plain",
        "creator_wallet": "0x1111111111111111111111111111111111111111",
        "vote_hash": "f" * 64,
        "approval_percentage": 0.8,
        "decisive_vote_total": 5,
        "minimum_votes_required": 5,
        "approved_at": 1724760001.25,
        "originality_score": 9.75,
        "reward_type": "meme_mining_reward",
        "reward_recipient": "0x1111111111111111111111111111111111111111",
        "reward_amount": 5.0,
        "reward_source": "reward_pool",
        "minted_at": 1724760002.75,
        "voter_rewards": [],
        "native_transactions": [],
    }
    base.update(overrides)
    return Block(**base)


def test_protocol_v1_block_golden_vectors_are_literal_and_stable():
    base_block = _protocol_v1_vector_block()
    media_mutated = _protocol_v1_vector_block(
        media_bytes=b"protocol-v1-medib",
        media_hash=base_block.media_hash,
        content_hash=base_block.content_hash,
        content_id=base_block.content_id,
    )
    metadata_mutated = _protocol_v1_vector_block(certificate_id="certificate-124")
    other_network = _protocol_v1_vector_block(network_id="zoidberg-devnet-v1")
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
    order_ab = _protocol_v1_vector_block(
        native_transactions=[native_tx_a, native_tx_b],
        transaction_ids=[native_tx_a["tx_id"], native_tx_b["tx_id"]],
        transaction_count=2,
        transactions_hash="order-ab",
    )
    order_ba = _protocol_v1_vector_block(
        native_transactions=[native_tx_b, native_tx_a],
        transaction_ids=[native_tx_b["tx_id"], native_tx_a["tx_id"]],
        transaction_count=2,
        transactions_hash="order-ba",
    )

    assert protocol_domain(OBJECT_TYPE_BLOCK) == "zoidbergchain/block/v1"
    assert base_block.consensus_payload_v1_bytes().decode("utf-8") == (
        '{"domain":"zoidbergchain/block/v1","network_id":"zoidberg-public-testnet-v1",'
        '"object_type":"block","payload":{"approval_percentage":"0.8","approved_at":"1724760001.25",'
        '"block_version":1,"certificate_id":"certificate-123","content_hash":"ff2d30a5c313b57e8eb7ef39d709814dda8685b2b29952197b5a9023c71c892d",'
        '"content_id":"3c74bab17335f4ebf6ad33429730b300","content_type":"text",'
        '"creator_wallet":"0x1111111111111111111111111111111111111111","decisive_vote_total":5,'
        '"index":7,"media_bytes":{"$encoding":"hex","$type":"bytes","$value":"70726f746f636f6c2d76312d6d65646961"},'
        '"media_hash":"ff2d30a5c313b57e8eb7ef39d709814dda8685b2b29952197b5a9023c71c892d",'
        '"meme_text":"Protocol v1 vector","mime_type":"text/plain","miner":"0x1111111111111111111111111111111111111111",'
        '"minimum_votes_required":5,"minted_at":"1724760002.75","native_transactions":[],'
        '"originality_score":"9.75","previous_hash":"0000000000000000000000000000000000000000000000000000000000000000",'
        '"reward_amount":"5","reward_recipient":"0x1111111111111111111111111111111111111111",'
        '"reward_source":"reward_pool","reward_type":"meme_mining_reward","submission_id":"submission-123",'
        '"timestamp":"1724760000.5","transactions":[{"amount":"5","payload_size_kb":0,'
        '"recipient":"0x1111111111111111111111111111111111111111","sender":"REWARD_POOL","tip":0}],'
        '"vote_hash":"ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff","voter_rewards":[]},'
        '"protocol":"zoidbergchain","protocol_version":1}'
    )
    assert base_block.hash == "e23fb96c29f5d51c3dfabc59ad7a35da623293dc49efff87b78241ac2b1dbd4b"
    assert media_mutated.hash == "3b519000b9dee6a8dc61d5736d8123024c3012313d68ca586b96a03adb8f17d6"
    assert metadata_mutated.hash == "fec2c441577bb2d02bf4077ecde163adeb55934054679815f872e573d6d5e476"
    assert other_network.hash == "1fa965ef7fbe498b1ddc681b3a9a2105b1cbb6d0d3043e946aa20be24fd14ecb"
    assert order_ab.hash == "7b942825640a7196b6afdf42013dcff54a4ed2033c9746aaf90d693f33a1630e"
    assert order_ba.hash == "ca9a1575a576a27990c8d59f5437663cd9a80535312ffc03d01cd70bf7923e72"
    assert base_block.hash != media_mutated.hash
    assert base_block.hash != metadata_mutated.hash
    assert base_block.hash != other_network.hash
    assert order_ab.hash != order_ba.hash
