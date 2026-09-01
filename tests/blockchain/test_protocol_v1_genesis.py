import base64
import hashlib
import json
from pathlib import Path

import blockchain as blockchain_module
import config
import pytest

from blockchain import Blockchain
from protocol_v1 import PUBLIC_TESTNET_V1_NETWORK_ID, canonical_domain_hash, decode_canonical_bytes, encode_canonical_bytes
from protocol_v1_genesis import (
    GenesisValidationError,
    PUBLIC_TESTNET_V1_CANONICAL_GENESIS_HASH,
    PUBLIC_TESTNET_V1_GENESIS_MEDIA_BYTE_LENGTH,
    PUBLIC_TESTNET_V1_GENESIS_MEDIA_CONTENT_TYPE,
    PUBLIC_TESTNET_V1_GENESIS_MEDIA_ENCODED_LENGTH,
    PUBLIC_TESTNET_V1_GENESIS_MEDIA_HASH,
    PUBLIC_TESTNET_V1_GENESIS_MEDIA_MIME_TYPE,
    PUBLIC_TESTNET_V1_GENESIS_TEXT,
    PUBLIC_TESTNET_V1_GENESIS_TIMESTAMP,
    PUBLIC_TESTNET_V1_OBSOLETE_MEDIALESS_GENESIS_HASH,
    canonical_public_testnet_v1_genesis_bytes,
    canonical_public_testnet_v1_genesis_hash,
    canonical_public_testnet_v1_genesis_media_base64,
    canonical_public_testnet_v1_genesis_media_bytes,
    canonical_public_testnet_v1_genesis_payload,
    canonical_public_testnet_v1_genesis_record,
    validate_public_testnet_v1_genesis_record,
)
from storage import JSONStorageBackend, SQLiteStorageBackend
from storage_migration import migrate_json_to_sqlite
from wallet import Wallet


EXPECTED_ZERO_HASH = "0000000000000000000000000000000000000000000000000000000000000000"
EXPECTED_PUBLIC_TESTNET_V1_GENESIS_HASH = "2b99e87f80e0e855ab98b3269b635be5415273f41d7d4bf1a2aeb8b277b13061"
EXPECTED_PUBLIC_TESTNET_V1_RESET_NETWORK_HASH = "097d76e704deba4a476fa682f8ff9e10b78e5a6c569435bd99edcdf8e8566fbc"
EXPECTED_MUTATED_TIMESTAMP_GENESIS_HASH = "bc9a7f7344bb96cc1c6f7a29a0a3faceb69b73c8fe47acc22542beae38e400ac"
EXPECTED_MUTATED_MEDIA_BYTES_GENESIS_HASH = "0278be27ada816685debc6f5356d458d9a2f562fa8be25ef45dcdbc839603d3a"
REPO_ROOT = Path(__file__).resolve().parents[2]
GENESIS_MEDIA_FIXTURE = REPO_ROOT / "public_testnet_v1_genesis_meme_base64.txt"
GOLDEN_VECTOR_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "protocol_v1_golden_vectors.json"


def _fixture_genesis_media_base64() -> str:
    return "".join(GENESIS_MEDIA_FIXTURE.read_text(encoding="ascii").split())


def _fixture_genesis_media_bytes() -> bytes:
    return base64.b64decode(_fixture_genesis_media_base64(), validate=True)


EXPECTED_PUBLIC_TESTNET_V1_GENESIS_MEDIA_BYTES = _fixture_genesis_media_bytes()
EXPECTED_PUBLIC_TESTNET_V1_GENESIS_ENVELOPE_JSON = json.loads(
    GOLDEN_VECTOR_FIXTURE.read_text(encoding="utf-8")
)["genesis"]["envelope_json"]
EXPECTED_PUBLIC_TESTNET_V1_GENESIS_PAYLOAD = {
    "content_type": "image",
    "genesis_version": 1,
    "index": 0,
    "previous_hash": EXPECTED_ZERO_HASH,
    "timestamp": 1785542400,
    "transactions": [
        {
            "sender": "GENESIS",
            "recipient": "034f355bdcb7cc0af728ef3cceb9615d90684bb5b2ca5f859ab0f0b704075871aa",
            "amount": 790_000_000,
            "tip": 0,
            "signature": None,
            "payload_size_kb": 0,
            "created_at": 1785542400,
        },
        {
            "sender": "GENESIS",
            "recipient": "02466d7fcae563e5cb09a0d1870bb580344804617879a14949cf22285f1bae3f27",
            "amount": 100_000_000,
            "tip": 0,
            "signature": None,
            "payload_size_kb": 0,
            "created_at": 1785542400,
        },
        {
            "sender": "GENESIS",
            "recipient": "023c72addb4fdf09af94f0c94d7fe92a386a7e70cf8a1d85916386bb2535c7b1b1",
            "amount": 10_000_000,
            "tip": 0,
            "signature": None,
            "payload_size_kb": 0,
            "created_at": 1785542400,
        },
    ],
    "miner": "GENESIS",
    "meme_text": "ZoidbergChain Public Testnet v1 Genesis",
    "media_hash": "dfba5a7e5e8e5f5da047a2ed58660c9d52665c39f2793da90cba51419f8525c7",
    "media_bytes": EXPECTED_PUBLIC_TESTNET_V1_GENESIS_MEDIA_BYTES,
    "mime_type": "image/jpeg",
    "total_supply": 1_000_000_000,
    "initial_reward_pool": 100_000_000,
}
EXPECTED_PUBLIC_TESTNET_V1_GENESIS_RECORD = {
    "genesis_version": 1,
    "protocol_version": 1,
    "network_id": "zoidberg-public-testnet-v1",
    "index": 0,
    "previous_hash": EXPECTED_ZERO_HASH,
    "timestamp": 1785542400,
    "transactions": EXPECTED_PUBLIC_TESTNET_V1_GENESIS_PAYLOAD["transactions"],
    "miner": "GENESIS",
    "meme": {"text": "ZoidbergChain Public Testnet v1 Genesis"},
    "media_hash": "dfba5a7e5e8e5f5da047a2ed58660c9d52665c39f2793da90cba51419f8525c7",
    "media_bytes": encode_canonical_bytes(EXPECTED_PUBLIC_TESTNET_V1_GENESIS_MEDIA_BYTES),
    "mime_type": "image/jpeg",
    "content_type": "image",
    "hash": EXPECTED_PUBLIC_TESTNET_V1_GENESIS_HASH,
    "total_supply": 1_000_000_000,
    "initial_reward_pool": 100_000_000,
}


def _json_backend(base_dir, name="node"):
    node_dir = base_dir / name
    return JSONStorageBackend(
        blockchain_file=str(node_dir / "blockchain.json"),
        peers_file=str(node_dir / "peers.json"),
    )


def _sqlite_backend(base_dir, name="node"):
    node_dir = base_dir / name
    return SQLiteStorageBackend(sqlite_db_path=str(node_dir / "zoidbergchain.db"))


def _build_blockchain(backend, *, owner=None, contributor_one=None, contributor_two=None):
    return Blockchain(
        project_owner_wallet=owner,
        Contributor_one=contributor_one,
        Contributor_two=contributor_two,
        storage_backend=backend,
    )


def test_public_testnet_v1_genesis_media_fixture_preserves_recovered_legacy_bytes():
    encoded = _fixture_genesis_media_base64()
    decoded = _fixture_genesis_media_bytes()

    assert encoded == canonical_public_testnet_v1_genesis_media_base64()
    assert len(encoded) == PUBLIC_TESTNET_V1_GENESIS_MEDIA_ENCODED_LENGTH
    assert len(decoded) == PUBLIC_TESTNET_V1_GENESIS_MEDIA_BYTE_LENGTH
    assert decoded.startswith(b"\xff\xd8\xff")
    assert hashlib.sha256(decoded).hexdigest() == PUBLIC_TESTNET_V1_GENESIS_MEDIA_HASH
    assert base64.b64decode(base64.b64encode(decoded), validate=True) == decoded
    assert canonical_public_testnet_v1_genesis_media_bytes() == decoded


def test_public_testnet_v1_genesis_block_zero_reconstructs_original_meme(isolated_data_dir):
    blockchain = _build_blockchain(_json_backend(isolated_data_dir, "reconstruct"), owner=Wallet())
    genesis_block = blockchain.chain[0]
    genesis_record = genesis_block.to_dict()

    reconstructed_from_record = decode_canonical_bytes(genesis_record["media_bytes"])
    reconstructed_from_chain = blockchain.recover_block_media_bytes(genesis_block.hash)

    assert genesis_record["media_hash"] == PUBLIC_TESTNET_V1_GENESIS_MEDIA_HASH
    assert genesis_record["mime_type"] == PUBLIC_TESTNET_V1_GENESIS_MEDIA_MIME_TYPE
    assert genesis_record["content_type"] == PUBLIC_TESTNET_V1_GENESIS_MEDIA_CONTENT_TYPE
    assert reconstructed_from_record == EXPECTED_PUBLIC_TESTNET_V1_GENESIS_MEDIA_BYTES
    assert reconstructed_from_chain == EXPECTED_PUBLIC_TESTNET_V1_GENESIS_MEDIA_BYTES
    assert hashlib.sha256(reconstructed_from_chain).hexdigest() == PUBLIC_TESTNET_V1_GENESIS_MEDIA_HASH


def test_public_testnet_v1_genesis_golden_vectors_match_literals():
    assert canonical_public_testnet_v1_genesis_payload() == EXPECTED_PUBLIC_TESTNET_V1_GENESIS_PAYLOAD
    assert canonical_public_testnet_v1_genesis_bytes().decode("utf-8") == EXPECTED_PUBLIC_TESTNET_V1_GENESIS_ENVELOPE_JSON
    assert canonical_public_testnet_v1_genesis_hash() == EXPECTED_PUBLIC_TESTNET_V1_GENESIS_HASH
    assert PUBLIC_TESTNET_V1_CANONICAL_GENESIS_HASH == EXPECTED_PUBLIC_TESTNET_V1_GENESIS_HASH
    assert canonical_public_testnet_v1_genesis_record() == EXPECTED_PUBLIC_TESTNET_V1_GENESIS_RECORD
    assert Blockchain.canonical_public_testnet_v1_genesis_block().to_dict() == EXPECTED_PUBLIC_TESTNET_V1_GENESIS_RECORD


def test_public_testnet_v1_genesis_network_binding_and_mutation_hashes_are_literal_and_distinct():
    alternate_network_hash = canonical_domain_hash(
        EXPECTED_PUBLIC_TESTNET_V1_GENESIS_PAYLOAD,
        object_type="genesis",
        network_id="zoidberg-public-testnet-v1-reset-1",
    )
    mutated_payload = dict(EXPECTED_PUBLIC_TESTNET_V1_GENESIS_PAYLOAD)
    mutated_payload["timestamp"] = PUBLIC_TESTNET_V1_GENESIS_TIMESTAMP + 1
    mutated_hash = canonical_domain_hash(
        mutated_payload,
        object_type="genesis",
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
    )
    mutated_media_bytes = bytearray(EXPECTED_PUBLIC_TESTNET_V1_GENESIS_PAYLOAD["media_bytes"])
    mutated_media_bytes[0] ^= 1
    mutated_media_hash = canonical_domain_hash(
        dict(EXPECTED_PUBLIC_TESTNET_V1_GENESIS_PAYLOAD, media_bytes=bytes(mutated_media_bytes)),
        object_type="genesis",
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
    )

    assert alternate_network_hash == EXPECTED_PUBLIC_TESTNET_V1_RESET_NETWORK_HASH
    assert mutated_hash == EXPECTED_MUTATED_TIMESTAMP_GENESIS_HASH
    assert mutated_media_hash == EXPECTED_MUTATED_MEDIA_BYTES_GENESIS_HASH
    assert alternate_network_hash != EXPECTED_PUBLIC_TESTNET_V1_GENESIS_HASH
    assert mutated_hash != EXPECTED_PUBLIC_TESTNET_V1_GENESIS_HASH
    assert mutated_media_hash != EXPECTED_PUBLIC_TESTNET_V1_GENESIS_HASH


def test_public_testnet_v1_genesis_construction_is_repeatable():
    hashes = [
        Blockchain.canonical_public_testnet_v1_genesis_block().hash
        for _ in range(3)
    ]
    records = [
        Blockchain.canonical_public_testnet_v1_genesis_block().to_dict()
        for _ in range(3)
    ]
    envelope_json = [
        canonical_public_testnet_v1_genesis_bytes().decode("utf-8")
        for _ in range(3)
    ]

    assert hashes == [EXPECTED_PUBLIC_TESTNET_V1_GENESIS_HASH] * 3
    assert records == [EXPECTED_PUBLIC_TESTNET_V1_GENESIS_RECORD] * 3
    assert envelope_json == [EXPECTED_PUBLIC_TESTNET_V1_GENESIS_ENVELOPE_JSON] * 3


def test_public_testnet_v1_genesis_is_independent_of_clock_and_wallet_inputs(monkeypatch, isolated_data_dir):
    first_backend = _json_backend(isolated_data_dir, "clock-a")
    second_backend = _json_backend(isolated_data_dir, "clock-b")

    monkeypatch.setattr(blockchain_module.time, "time", lambda: 1.0)
    first = _build_blockchain(
        first_backend,
        owner=Wallet(),
        contributor_one=Wallet(),
        contributor_two=Wallet(),
    )

    monkeypatch.setattr(blockchain_module.time, "time", lambda: 9_999_999_999.0)
    second = _build_blockchain(
        second_backend,
        owner=Wallet(),
        contributor_one=Wallet(),
        contributor_two=Wallet(),
    )

    assert first.chain[0].to_dict() == EXPECTED_PUBLIC_TESTNET_V1_GENESIS_RECORD
    assert second.chain[0].to_dict() == EXPECTED_PUBLIC_TESTNET_V1_GENESIS_RECORD


def test_public_testnet_v1_genesis_is_independent_of_local_filesystem_and_node_identity(
    monkeypatch,
    isolated_data_dir,
):
    image_path = Path("zoidberg.jpg")
    image_path.unlink()

    monkeypatch.setattr(config, "NODE_ID", "node-a")
    first = _build_blockchain(_json_backend(isolated_data_dir, "node-a"))
    monkeypatch.setattr(config, "NODE_ID", "node-b")
    second = _build_blockchain(_json_backend(isolated_data_dir, "node-b"))

    assert first.chain[0].to_dict() == EXPECTED_PUBLIC_TESTNET_V1_GENESIS_RECORD
    assert second.chain[0].to_dict() == EXPECTED_PUBLIC_TESTNET_V1_GENESIS_RECORD


@pytest.mark.parametrize("backend_factory", [_json_backend, _sqlite_backend])
def test_fresh_node_restart_preserves_canonical_genesis_across_backends(
    backend_factory,
    isolated_data_dir,
):
    backend = backend_factory(isolated_data_dir, "restart")
    blockchain = _build_blockchain(backend, owner=Wallet(), contributor_one=Wallet(), contributor_two=Wallet())
    reloaded = _build_blockchain(backend)

    assert blockchain.chain[0].to_dict() == EXPECTED_PUBLIC_TESTNET_V1_GENESIS_RECORD
    assert reloaded.chain[0].to_dict() == EXPECTED_PUBLIC_TESTNET_V1_GENESIS_RECORD
    assert reloaded.chain[0].hash == EXPECTED_PUBLIC_TESTNET_V1_GENESIS_HASH


def test_fresh_json_and_sqlite_nodes_share_the_same_literal_genesis(isolated_data_dir):
    json_blockchain = _build_blockchain(_json_backend(isolated_data_dir, "json"), owner=Wallet())
    sqlite_blockchain = _build_blockchain(_sqlite_backend(isolated_data_dir, "sqlite"), owner=Wallet())

    assert json_blockchain.chain[0].hash == EXPECTED_PUBLIC_TESTNET_V1_GENESIS_HASH
    assert sqlite_blockchain.chain[0].hash == EXPECTED_PUBLIC_TESTNET_V1_GENESIS_HASH
    assert json_blockchain.chain[0].to_dict() == sqlite_blockchain.chain[0].to_dict()


def test_json_to_sqlite_migration_preserves_canonical_genesis(isolated_data_dir):
    source_backend = _json_backend(isolated_data_dir, "migration-source")
    source_blockchain = _build_blockchain(source_backend, owner=Wallet(), contributor_one=Wallet(), contributor_two=Wallet())
    target_db = isolated_data_dir / "migration-target" / "zoidbergchain.db"

    summary = migrate_json_to_sqlite(
        source_json_path=Path(source_backend.blockchain_file),
        sqlite_db_path=target_db,
        peers_json_path=Path(source_backend.peers_file),
    )
    reloaded = _build_blockchain(SQLiteStorageBackend(sqlite_db_path=str(target_db)))

    assert summary.canonical_genesis_hash == EXPECTED_PUBLIC_TESTNET_V1_GENESIS_HASH
    assert reloaded.chain[0].to_dict() == source_blockchain.chain[0].to_dict()
    assert reloaded.chain[0].hash == EXPECTED_PUBLIC_TESTNET_V1_GENESIS_HASH


def test_loading_legacy_genesis_requires_explicit_reset_and_does_not_delete_data(isolated_data_dir):
    backend = _json_backend(isolated_data_dir, "legacy-reset")
    _build_blockchain(backend, owner=Wallet(), contributor_one=Wallet(), contributor_two=Wallet())
    blockchain_path = Path(backend.blockchain_file)
    document = json.loads(blockchain_path.read_text(encoding="utf-8"))
    legacy_genesis = document["chain"][0]
    for field_name in ["genesis_version", "protocol_version", "network_id", "total_supply", "initial_reward_pool"]:
        legacy_genesis.pop(field_name, None)
    legacy_genesis["previous_hash"] = "0"
    legacy_genesis["meme"] = {"text": "Legacy runtime genesis"}
    legacy_genesis["hash"] = "legacy-runtime-genesis"
    blockchain_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(GenesisValidationError) as exc_info:
        _build_blockchain(backend)

    assert exc_info.value.code == "legacy_chain_reset_required"
    assert blockchain_path.exists() is True


def test_loading_mutated_public_testnet_v1_genesis_fails_closed_without_deleting_data(isolated_data_dir):
    backend = _json_backend(isolated_data_dir, "mutated-reset")
    _build_blockchain(backend, owner=Wallet(), contributor_one=Wallet(), contributor_two=Wallet())
    blockchain_path = Path(backend.blockchain_file)
    document = json.loads(blockchain_path.read_text(encoding="utf-8"))
    mutated_genesis = document["chain"][0]
    mutated_genesis["timestamp"] = PUBLIC_TESTNET_V1_GENESIS_TIMESTAMP + 1
    mutated_genesis["hash"] = EXPECTED_MUTATED_TIMESTAMP_GENESIS_HASH
    blockchain_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(GenesisValidationError) as exc_info:
        _build_blockchain(backend)

    assert exc_info.value.code == "genesis_mismatch"
    assert blockchain_path.exists() is True


def test_old_media_less_public_testnet_v1_genesis_requires_explicit_prelaunch_reset():
    old_record = dict(EXPECTED_PUBLIC_TESTNET_V1_GENESIS_RECORD)
    for field_name in ["media_hash", "media_bytes", "mime_type", "content_type"]:
        old_record.pop(field_name, None)
    old_record["hash"] = PUBLIC_TESTNET_V1_OBSOLETE_MEDIALESS_GENESIS_HASH

    with pytest.raises(GenesisValidationError) as exc_info:
        validate_public_testnet_v1_genesis_record(old_record)

    assert exc_info.value.code == "prelaunch_genesis_reset_required"
    assert "superseded media-less Public Testnet v1 genesis" in str(exc_info.value)


@pytest.mark.parametrize("field_name", ["media_hash", "media_bytes", "mime_type", "content_type"])
def test_public_testnet_v1_genesis_rejects_missing_media_fields(field_name):
    mutated_record = dict(EXPECTED_PUBLIC_TESTNET_V1_GENESIS_RECORD)
    mutated_record.pop(field_name)

    with pytest.raises(GenesisValidationError) as exc_info:
        validate_public_testnet_v1_genesis_record(mutated_record)

    assert exc_info.value.code == "prelaunch_genesis_reset_required"


def test_public_testnet_v1_genesis_rejects_media_byte_mutation():
    mutated_record = dict(EXPECTED_PUBLIC_TESTNET_V1_GENESIS_RECORD)
    mutated_media = bytearray(EXPECTED_PUBLIC_TESTNET_V1_GENESIS_MEDIA_BYTES)
    mutated_media[-1] ^= 1
    mutated_record["media_bytes"] = encode_canonical_bytes(bytes(mutated_media))

    with pytest.raises(GenesisValidationError) as exc_info:
        validate_public_testnet_v1_genesis_record(mutated_record)

    assert exc_info.value.code == "genesis_media_hash_mismatch"


def test_public_testnet_v1_genesis_rejects_rehashed_foreign_media():
    mutated_record = dict(EXPECTED_PUBLIC_TESTNET_V1_GENESIS_RECORD)
    mutated_media = bytearray(EXPECTED_PUBLIC_TESTNET_V1_GENESIS_MEDIA_BYTES)
    mutated_media[0] ^= 1
    mutated_record["media_bytes"] = encode_canonical_bytes(bytes(mutated_media))
    mutated_record["media_hash"] = hashlib.sha256(bytes(mutated_media)).hexdigest()

    with pytest.raises(GenesisValidationError) as exc_info:
        validate_public_testnet_v1_genesis_record(mutated_record)

    assert exc_info.value.code == "genesis_media_mismatch"


def test_public_testnet_v1_genesis_rejects_declared_media_hash_mutation():
    mutated_record = dict(EXPECTED_PUBLIC_TESTNET_V1_GENESIS_RECORD)
    mutated_record["media_hash"] = "0" * 64

    with pytest.raises(GenesisValidationError) as exc_info:
        validate_public_testnet_v1_genesis_record(mutated_record)

    assert exc_info.value.code == "genesis_media_hash_mismatch"


def test_public_testnet_v1_genesis_rejects_mime_type_mutation():
    mutated_record = dict(EXPECTED_PUBLIC_TESTNET_V1_GENESIS_RECORD)
    mutated_record["mime_type"] = "image/png"

    with pytest.raises(GenesisValidationError) as exc_info:
        validate_public_testnet_v1_genesis_record(mutated_record)

    assert exc_info.value.code == "genesis_mismatch"


def test_public_testnet_v1_genesis_rejects_same_record_under_alternate_network():
    mutated_record = dict(EXPECTED_PUBLIC_TESTNET_V1_GENESIS_RECORD)
    mutated_record["network_id"] = "zoidberg-public-testnet-v1-reset-1"

    with pytest.raises(GenesisValidationError) as exc_info:
        validate_public_testnet_v1_genesis_record(mutated_record)

    assert exc_info.value.code == "genesis_mismatch"


def test_mutated_public_testnet_v1_genesis_record_fails_against_frozen_hash():
    mutated_record = dict(EXPECTED_PUBLIC_TESTNET_V1_GENESIS_RECORD)
    mutated_record["hash"] = EXPECTED_MUTATED_TIMESTAMP_GENESIS_HASH
    mutated_record["timestamp"] = PUBLIC_TESTNET_V1_GENESIS_TIMESTAMP + 1

    with pytest.raises(GenesisValidationError, match="frozen Public Testnet v1 genesis definition"):
        validate_public_testnet_v1_genesis_record(mutated_record)

    assert PUBLIC_TESTNET_V1_GENESIS_TEXT in EXPECTED_PUBLIC_TESTNET_V1_GENESIS_ENVELOPE_JSON
    assert canonical_public_testnet_v1_genesis_hash() == EXPECTED_PUBLIC_TESTNET_V1_GENESIS_HASH
