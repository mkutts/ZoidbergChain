"""Characterization guardrails for the legacy ecdsa compatibility boundary."""

import base64
import hashlib
import json
from pathlib import Path

import ecdsa
import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils

from block import Block
from peer_sync import MalformedBlockError, receive_peer_block
from transaction import Transaction
from wallet import Wallet


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "legacy_secp256k1_compatibility_vectors.json"
SECP256K1_ORDER = ecdsa.SECP256k1.order


def _vectors():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _transaction(vectors, signature=None):
    serialized = dict(vectors["legacy_transaction"]["serialization"])
    if signature is not None:
        serialized["signature"] = signature
    return Transaction.from_dict(serialized)


class _ActivePeerStore:
    def get_active_peer(self, node_id):
        if node_id != "legacy-vector-peer":
            return None
        return {"node_id": node_id, "network_name": "zoidberg-testnet"}


def _peer_block(blockchain, vectors, transaction):
    legacy = vectors["legacy_block"]["serialization"]
    return Block(
        index=blockchain.get_latest_block().index + 1,
        previous_hash=blockchain.get_latest_block().hash,
        timestamp=legacy["timestamp"],
        transactions=[transaction],
        miner=legacy["miner"],
        meme=legacy["meme"],
    )


def test_fixed_scalar_key_formats_and_loaders_match_fixture():
    vectors = _vectors()
    legacy = vectors["legacy_ecdsa"]
    assert len(bytes.fromhex(legacy["private_scalar_hex"])) == 32
    wallet = Wallet(legacy["private_scalar_hex"])
    assert wallet.public_key == legacy["compressed_public_key_hex"]
    assert Wallet.validate_private_key(wallet.private_key, wallet.public_key) is True
    verifying_key = ecdsa.VerifyingKey.from_string(bytes.fromhex(wallet.public_key), curve=ecdsa.SECP256k1)
    assert verifying_key.to_string("compressed").hex() == wallet.public_key
    assert Wallet.validate_private_key(legacy["private_scalar_hex"], "02") is False


def test_generated_legacy_wallet_uses_serializable_secp256k1_key_formats():
    wallet = Wallet()
    assert len(bytes.fromhex(wallet.private_key)) == 32
    assert len(bytes.fromhex(wallet.public_key)) == 33
    assert wallet.public_key[:2] in {"02", "03"}
    assert Wallet.validate_private_key(wallet.private_key, wallet.public_key) is True


def test_legacy_signature_fixture_uses_sha1_raw_base64_and_verifies():
    vectors = _vectors()
    legacy = vectors["legacy_ecdsa"]
    signature = base64.b64decode(legacy["signature_base64"], validate=True)
    assert bytes.fromhex(legacy["message_hex"]) == legacy["message_utf8"].encode("utf-8")
    assert hashlib.sha1(legacy["message_utf8"].encode("utf-8")).digest()
    assert len(signature) == 64
    assert int.from_bytes(signature[:32], "big") == int(legacy["signature_r_decimal"])
    assert int.from_bytes(signature[32:], "big") == int(legacy["signature_s_decimal"])
    assert _transaction(vectors).is_valid() is True


def test_current_signers_are_randomized_and_preserve_legacy_signature_structure():
    vectors = _vectors()
    legacy = vectors["legacy_ecdsa"]
    wallet = Wallet(legacy["private_scalar_hex"])
    first, second = wallet.sign_data(legacy["message_utf8"]), wallet.sign_data(legacy["message_utf8"])
    for signature_text in (first, second):
        signature = base64.b64decode(signature_text, validate=True)
        assert len(signature) == 64
        verifier = ecdsa.VerifyingKey.from_string(bytes.fromhex(wallet.public_key), curve=ecdsa.SECP256k1)
        assert verifier.verify(signature, legacy["message_utf8"].encode("utf-8")) is True
    assert first != vectors["legacy_ecdsa"]["signature_base64"] or second != first

    transaction = _transaction(vectors, signature=None)
    transaction.sign_transaction(legacy["private_scalar_hex"])
    assert len(base64.b64decode(transaction.signature, validate=True)) == 64
    assert transaction.is_valid() is True


def test_transaction_verification_rejects_message_signature_and_encoding_tampering():
    vectors = _vectors()
    valid = _transaction(vectors)
    altered_message = Transaction(valid.sender, valid.recipient + "00", valid.amount, valid.tip, valid.payload_size_kb, valid.signature, valid.created_at)
    raw = bytearray(base64.b64decode(valid.signature, validate=True))
    raw[-1] ^= 1
    assert altered_message.is_valid() is False
    assert _transaction(vectors, base64.b64encode(raw).decode("ascii")).is_valid() is False
    assert _transaction(vectors, vectors["malformed_cases"]["invalid_base64_signature"]).is_valid() is False
    assert _transaction(vectors, vectors["malformed_cases"]["short_raw_signature_base64"]).is_valid() is False


def test_legacy_verification_accepts_both_low_s_and_high_s_encodings():
    vectors = _vectors()
    legacy = vectors["legacy_ecdsa"]
    raw = base64.b64decode(legacy["signature_base64"], validate=True)
    high_raw = base64.b64decode(legacy["high_s_counterpart_base64"], validate=True)
    assert int.from_bytes(raw[32:], "big") <= SECP256K1_ORDER // 2
    assert int.from_bytes(high_raw[32:], "big") == SECP256K1_ORDER - int.from_bytes(raw[32:], "big")
    assert _transaction(vectors).is_valid() is True
    assert _transaction(vectors, legacy["high_s_counterpart_base64"]).is_valid() is True


def test_legacy_transaction_and_block_serialization_hash_are_exact():
    vectors = _vectors()
    transaction = _transaction(vectors)
    expected_transaction = vectors["legacy_transaction"]["serialization"]
    expected_block = vectors["legacy_block"]["serialization"]
    assert transaction.to_dict() == expected_transaction
    assert "tx_id" not in transaction.to_dict()
    assert vectors["legacy_transaction"]["transaction_identifier"] is None
    block = Block.from_dict(expected_block)
    assert block.to_dict() == expected_block
    assert block.calculate_hash_legacy() == expected_block["hash"]
    assert block.hash == expected_block["hash"]


def test_signature_text_changes_the_legacy_block_hash():
    vectors = _vectors()
    low_block = Block.from_dict(vectors["legacy_block"]["serialization"])
    high_payload = low_block.to_dict()
    high_payload["transactions"][0]["signature"] = vectors["legacy_ecdsa"]["high_s_counterpart_base64"]
    assert Block.from_dict(high_payload).calculate_hash_legacy() != low_block.calculate_hash_legacy()


def test_peer_legacy_block_validation_accepts_fixture_and_rejects_rehashed_tampering(blockchain, monkeypatch):
    vectors = _vectors()
    monkeypatch.setattr(blockchain, "validate_transaction", lambda transaction: True)
    peer_store = _ActivePeerStore()
    block = _peer_block(blockchain, vectors, _transaction(vectors))
    result = receive_peer_block(blockchain, peer_store, "legacy-vector-peer", "zoidberg-testnet", block.to_dict(), None, "zoidberg-testnet")
    assert result["accepted"] is True
    assert result["status"] == "accepted"
    tampered = _peer_block(blockchain, vectors, _transaction(vectors, vectors["malformed_cases"]["short_raw_signature_base64"]))
    tampered.hash = tampered.calculate_hash()
    with pytest.raises(MalformedBlockError, match="invalid transaction"):
        receive_peer_block(blockchain, peer_store, "legacy-vector-peer", "zoidberg-testnet", tampered.to_dict(), None, "zoidberg-testnet")


def test_wallet_round_trip_uses_temporary_storage_only(tmp_path):
    vectors = _vectors()
    repository_wallets = Path.cwd() / "wallets.json"
    before = repository_wallets.read_bytes() if repository_wallets.exists() else None
    source = Wallet(vectors["legacy_ecdsa"]["private_scalar_hex"])
    persisted = tmp_path / "wallet.json"
    persisted.write_text(json.dumps(source.to_dict()), encoding="utf-8")
    assert Wallet.from_dict(json.loads(persisted.read_text(encoding="utf-8"))).to_dict() == source.to_dict()
    assert persisted.parent == tmp_path
    after = repository_wallets.read_bytes() if repository_wallets.exists() else None
    assert after == before


def test_cryptography_can_verify_legacy_raw_signature_without_double_hashing():
    vectors = _vectors()
    legacy = vectors["legacy_ecdsa"]
    private_key = ec.derive_private_key(int(legacy["private_scalar_hex"], 16), ec.SECP256K1())
    public_key, message = private_key.public_key(), legacy["message_utf8"].encode("utf-8")
    raw = base64.b64decode(legacy["signature_base64"], validate=True)
    der = utils.encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    assert public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint).hex() == legacy["compressed_public_key_hex"]
    public_key.verify(der, message, ec.ECDSA(hashes.SHA1()))
    public_key.verify(der, hashlib.sha1(message).digest(), ec.ECDSA(utils.Prehashed(hashes.SHA1())))


def test_cryptography_signature_converts_to_legacy_raw_and_current_verifier_accepts_it():
    vectors = _vectors()
    legacy = vectors["legacy_ecdsa"]
    private_key = ec.derive_private_key(int(legacy["private_scalar_hex"], 16), ec.SECP256K1())
    der = private_key.sign(legacy["message_utf8"].encode("utf-8"), ec.ECDSA(hashes.SHA1()))
    r, s = utils.decode_dss_signature(der)
    raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    assert len(raw) == 64
    assert _transaction(vectors, base64.b64encode(raw).decode("ascii")).is_valid() is True
    with pytest.raises(InvalidSignature):
        private_key.public_key().verify(der, b"changed", ec.ECDSA(hashes.SHA1()))


def test_broken_wallet_verify_signature_is_not_the_transaction_compatibility_path():
    vectors = _vectors()
    legacy = vectors["legacy_ecdsa"]
    assert Wallet.verify_signature(legacy["compressed_public_key_hex"], legacy["signature_base64"], legacy["message_utf8"]) is False
