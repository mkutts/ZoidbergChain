"""Milestone 6 Task 6.9: immutable Model A byte integrity and reconstruction."""

from __future__ import annotations

import hashlib
import io
import json
from copy import deepcopy
from pathlib import Path

import pytest

from block import Block
from media_integrity import (
    MEDIA_INTEGRITY_CONTRACT_VERSION,
    MediaIntegrityError,
    reconstruct_media_bytes,
    validate_current_media_chain_records,
    verify_media_block,
)
from protocol_v1 import decode_canonical_bytes, encode_canonical_bytes
from storage import JSONStorageBackend, SQLiteStorageBackend
from storage_migration import migrate_json_to_sqlite
from storage_tools import build_export_snapshot, import_storage
from tests.test_milestone_6_task_6_8_post_mint_dispute import _minted_node


def _mutated_record(block, mutate, *, rehash=False):
    record = deepcopy(block.to_dict())
    mutate(record)
    if rehash:
        record["hash"] = Block.calculate_hash_v1_from_dict(record)
    return record


@pytest.mark.parametrize("backend_name", ["json", "sqlite"])
def test_finalized_block_verifies_and_reconstructs_by_every_identity(
    isolated_data_dir, monkeypatch, backend_name
):
    node, block, kwargs = _minted_node(isolated_data_dir, backend_name, monkeypatch)
    accepted = bytes(block.media_bytes)
    report = node.verify_block_media_integrity(block, require_finalized=True)

    assert report["verified"] is True
    assert report["integrity_contract_version"] == MEDIA_INTEGRITY_CONTRACT_VERSION
    assert report["media_length"] == len(accepted)
    assert report["media_hash"] == hashlib.sha256(accepted).hexdigest()
    assert report["media_hash_equals_content_hash"] is True
    assert report["admission_certificate_binding"] == "verified"
    assert report["technical_evidence_binding"] == "verified"
    assert node.reconstruct_immutable_media(block_hash=block.hash, require_finalized=True) == accepted
    assert node.reconstruct_immutable_media(block_height=block.index, require_finalized=True) == accepted
    assert node.reconstruct_immutable_media(
        submission_id=block.submission_id, require_finalized=True
    ) == accepted

    content_object = node.get_content_object_by_hash(block.content_hash)
    cache_path = Path(content_object.local_path)
    if not cache_path.is_absolute():
        cache_path = Path(node.storage.data_dir) / cache_path
    cache_path.unlink(missing_ok=True)
    assert node.reconstruct_immutable_media(block_hash=block.hash) == accepted

    restarted = type(node)(**kwargs)
    restored = restarted.get_block_by_hash(block.hash)
    assert restored.hash == block.hash
    assert restarted.reconstruct_immutable_media(block_hash=block.hash) == accepted
    assert restarted.verify_block_media_integrity(restored)["media_hash"] == block.media_hash


def test_canonical_binary_encoding_is_lossless_and_malformed_encoding_fails():
    payload = bytes(range(256)) * 8192 + b"metadata\x00\xff\x80"
    encoded = encode_canonical_bytes(payload)
    serialized = json.dumps(encoded, sort_keys=True)
    assert decode_canonical_bytes(json.loads(serialized)) == payload

    malformed = deepcopy(encoded)
    malformed["$value"] = malformed["$value"][:-1]
    with pytest.raises(ValueError, match="lowercase hexadecimal"):
        decode_canonical_bytes(malformed)
    malformed = deepcopy(encoded)
    malformed["$value"] = "GG"
    with pytest.raises(ValueError, match="lowercase hexadecimal"):
        decode_canonical_bytes(malformed)


def test_bit_truncation_append_reorder_and_cross_block_swap_fail(
    isolated_data_dir, monkeypatch
):
    node, block, _ = _minted_node(isolated_data_dir, "json", monkeypatch)
    original = bytes(block.media_bytes)
    altered = []
    flipped = bytearray(original)
    flipped[0] ^= 1
    altered.append(bytes(flipped))
    altered.extend((original[:-1], original + b"x", original[::-1]))

    for payload in altered:
        record = _mutated_record(block, lambda item, value=payload: item.update(
            media_bytes=encode_canonical_bytes(value)
        ))
        with pytest.raises(MediaIntegrityError):
            verify_media_block(record)

    other = _mutated_record(block, lambda item: item.update(
        submission_id="other-submission",
        media_bytes=encode_canonical_bytes(b"different valid-looking text"),
    ), rehash=True)
    with pytest.raises(MediaIntegrityError):
        verify_media_block(other)


@pytest.mark.parametrize("field", ["media_hash", "content_hash"])
def test_hash_and_block_commitment_tampering_fails(isolated_data_dir, monkeypatch, field):
    _node, block, _ = _minted_node(isolated_data_dir, "json", monkeypatch)
    record = _mutated_record(block, lambda item: item.update({field: "0" * 64}), rehash=True)
    with pytest.raises(MediaIntegrityError):
        verify_media_block(record)

    block_hash_only = _mutated_record(block, lambda item: item.update(hash="0" * 64))
    with pytest.raises(MediaIntegrityError, match="Block hash"):
        verify_media_block(block_hash_only)


@pytest.mark.parametrize(
    "tamper",
    [
        lambda cert: cert.update(content_hash="0" * 64),
        lambda cert: cert["technical_evidence"].update(raw_media_sha256="0" * 64),
        lambda cert: cert["technical_evidence"].update(raw_media_byte_length=999),
    ],
)
def test_admission_and_technical_evidence_tampering_fails(
    isolated_data_dir, monkeypatch, tamper
):
    _node, block, _ = _minted_node(isolated_data_dir, "json", monkeypatch)
    record = deepcopy(block.to_dict())
    tamper(record["admission_certificate"])
    record["hash"] = Block.calculate_hash_v1_from_dict(record)
    with pytest.raises(MediaIntegrityError, match="Admission certificate"):
        verify_media_block(record)


def test_noncanonical_text_bytes_fail_even_when_canonical_digest_is_retained(
    isolated_data_dir, monkeypatch
):
    node, block, _ = _minted_node(isolated_data_dir, "json", monkeypatch)
    noncanonical = b"  " + bytes(block.media_bytes).replace(b" ", b"\r\n", 1) + b"  "
    record = _mutated_record(
        block,
        lambda item: item.update(media_bytes=encode_canonical_bytes(noncanonical)),
        rehash=True,
    )
    with pytest.raises(MediaIntegrityError):
        verify_media_block(record)
    with pytest.raises(ValueError):
        node.validate_protocol_v1_block_payload(record)


def test_same_looking_metadata_recompression_and_format_conversion_are_different_media(
    blockchain, submission_image, wallets
):
    from PIL import Image
    from tests.blockchain.test_protocol_v1_block_format import _mint_protocol_v1_block

    _submission, _certificate, block = _mint_protocol_v1_block(
        blockchain, submission_image, wallets
    )
    original = bytes(block.media_bytes)
    # A JPEG COM segment changes only container metadata, not rendered pixels.
    metadata_changed = original[:2] + b"\xff\xfe\x00\x07task!" + original[2:]
    variants = [metadata_changed]
    with Image.open(io.BytesIO(original)) as source:
        image = source.convert("RGB")
        for format_name, kwargs in (
            ("JPEG", {"quality": 72}),
            ("PNG", {}),
            ("GIF", {}),
            ("WEBP", {"quality": 80}),
        ):
            output = io.BytesIO()
            image.save(output, format=format_name, **kwargs)
            variants.append(output.getvalue())

    assert metadata_changed != original
    for changed in variants:
        assert hashlib.sha256(changed).hexdigest() != block.media_hash
        record = _mutated_record(
            block,
            lambda item, value=changed: item.update(media_bytes=encode_canonical_bytes(value)),
            rehash=True,
        )
        with pytest.raises(MediaIntegrityError):
            verify_media_block(record)


@pytest.mark.parametrize("backend_name", ["json", "sqlite"])
def test_portable_export_import_preserves_exact_block_bytes(
    isolated_data_dir, monkeypatch, backend_name
):
    source, block, _ = _minted_node(isolated_data_dir, backend_name, monkeypatch)
    accepted = bytes(block.media_bytes)
    snapshot = build_export_snapshot(source.storage)
    snapshot_path = isolated_data_dir / f"task69-{backend_name}-export.json"
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

    if backend_name == "json":
        target = SQLiteStorageBackend(sqlite_db_path=str(isolated_data_dir / "portable-target.db"))
    else:
        target = JSONStorageBackend(
            blockchain_file=str(isolated_data_dir / "portable-target.json"),
            peers_file=str(isolated_data_dir / "portable-target-peers.json"),
        )
    result = import_storage(target, input_path=snapshot_path)
    imported = target.load_blockchain_state()["chain"][block.index]
    assert result["written"] is True
    assert reconstruct_media_bytes(imported) == accepted
    assert imported["hash"] == block.hash
    assert imported["media_hash"] == block.media_hash
    assert imported["admission_certificate"]["certificate_digest"] == block.certificate_id
    assert verify_media_block(imported)["verified"] is True


def test_export_import_and_migration_reject_altered_media(isolated_data_dir, monkeypatch):
    source, block, _ = _minted_node(isolated_data_dir, "json", monkeypatch)
    snapshot = build_export_snapshot(source.storage)
    corrupted = deepcopy(snapshot)
    encoded = corrupted["state"]["chain"][block.index]["media_bytes"]["$value"]
    corrupted["state"]["chain"][block.index]["media_bytes"]["$value"] = (
        ("0" if encoded[0] != "0" else "1") + encoded[1:]
    )
    corrupted_path = isolated_data_dir / "corrupted-export.json"
    corrupted_path.write_text(json.dumps(corrupted), encoding="utf-8")
    target = SQLiteStorageBackend(sqlite_db_path=str(isolated_data_dir / "corrupt-target.db"))
    with pytest.raises(ValueError):
        import_storage(target, input_path=corrupted_path)

    source_path = Path(source.storage.blockchain_file)
    source_document = json.loads(source_path.read_text(encoding="utf-8"))
    source_document["chain"][block.index]["media_hash"] = "0" * 64
    bad_source = isolated_data_dir / "bad-migration.json"
    bad_source.write_text(json.dumps(source_document), encoding="utf-8")
    with pytest.raises(Exception):
        migrate_json_to_sqlite(bad_source, isolated_data_dir / "bad-migration.db")


def test_json_to_sqlite_migration_preserves_exact_media(isolated_data_dir, monkeypatch):
    source, block, _ = _minted_node(isolated_data_dir, "json", monkeypatch)
    accepted = bytes(block.media_bytes)
    target_path = isolated_data_dir / "migrated-task69.db"
    migrate_json_to_sqlite(
        source.storage.blockchain_file,
        target_path,
        peers_json_path=source.storage.peers_file,
    )
    migrated = SQLiteStorageBackend(sqlite_db_path=str(target_path)).load_blockchain_state()
    restored = migrated["chain"][block.index]
    assert reconstruct_media_bytes(restored) == accepted
    assert verify_media_block(restored)["block_hash"] == block.hash


def test_peer_receive_and_retransmission_preserve_exact_bytes(
    isolated_data_dir, monkeypatch
):
    from blockchain import Blockchain
    from peer_sync import receive_peer_block
    from peers import PeerStore

    source, block, _ = _minted_node(isolated_data_dir, "json", monkeypatch)
    accepted = bytes(block.media_bytes)
    peer_dir = isolated_data_dir / "task69-peer"
    peer_dir.mkdir()
    backend = JSONStorageBackend(
        blockchain_file=str(peer_dir / "chain.json"),
        peers_file=str(peer_dir / "peers.json"),
    )
    peer = Blockchain(
        project_owner_wallet=source.project_owner_wallet,
        Contributor_one=source.Contributor_one,
        Contributor_two=source.Contributor_two,
        storage_backend=backend,
    )
    store = PeerStore(storage_backend=backend)
    store.register_peer(
        node_id="source", url="http://source.test:8000", network_name="zoidberg-testnet"
    )
    malformed = deepcopy(block.to_dict())
    malformed["media_bytes"]["$value"] = malformed["media_bytes"]["$value"][:-1]
    from peer_sync import MalformedBlockError
    with pytest.raises(MalformedBlockError):
        receive_peer_block(
            peer, store, "source", "zoidberg-testnet", malformed,
            block.submission_id, "zoidberg-testnet",
        )
    result = receive_peer_block(
        peer, store, "source", "zoidberg-testnet", deepcopy(block.to_dict()),
        block.submission_id, "zoidberg-testnet",
    )
    assert result["accepted"] is True
    received = peer.chain[-1]
    assert bytes(received.media_bytes) == accepted
    assert received.media_hash == block.media_hash
    assert received.hash == block.hash
    assert peer.reconstruct_immutable_media(block_hash=block.hash) == accepted

    duplicate = receive_peer_block(
        peer, store, "source", "zoidberg-testnet", deepcopy(received.to_dict()),
        block.submission_id, "zoidberg-testnet",
    )
    assert duplicate["reason"] == "block_already_exists"
    assert bytes(peer.get_block_by_hash(block.hash).media_bytes) == accepted


def test_report_and_dispute_overlays_do_not_change_block_or_integrity(
    isolated_data_dir, monkeypatch
):
    node, block, _ = _minted_node(isolated_data_dir, "json", monkeypatch)
    before = deepcopy(block.to_dict())
    before_report = node.verify_block_media_integrity(block)
    submission = node.get_submission(block.submission_id)
    submission.community_reports.append({"identity": "task69-observation"})
    node.post_mint_disputes.setdefault(block.submission_id, []).append(
        {"identity": "task69-dispute-observation"}
    )
    after_report = node.verify_block_media_integrity(block)
    assert block.to_dict() == before
    assert before_report == after_report


def test_media_api_is_derived_and_returns_exact_binary_bytes(isolated_data_dir, monkeypatch):
    from tests.api.test_wallet_auth_api import _client

    node, block, _ = _minted_node(isolated_data_dir, "json", monkeypatch)
    accepted = bytes(block.media_bytes)
    client, _ = _client(node)
    listing = client.get("/chain/blocks")
    assert listing.status_code == 200
    metadata = next(item for item in listing.json()["blocks"] if item["hash"] == block.hash)
    assert metadata["media_integrity_status"] == "computed_on_exact_download"
    assert metadata["media_length"] == len(accepted)
    assert metadata["finalized"] is True

    media = client.get(f"/blocks/{block.hash}/media")
    assert media.status_code == 200
    assert media.content == accepted
    assert media.headers["x-zoidberg-media-sha256"] == block.media_hash
    assert media.headers["x-zoidberg-block-hash"] == block.hash
    assert media.headers["x-zoidberg-media-integrity"] == "verified"


def test_chain_record_validator_ignores_legacy_and_fails_current_corruption(
    isolated_data_dir, monkeypatch
):
    _node, block, _ = _minted_node(isolated_data_dir, "json", monkeypatch)
    assert validate_current_media_chain_records([{"index": 7}, block.to_dict()]) == 1
    corrupt = block.to_dict()
    corrupt["media_bytes"] = {"$type": "bytes", "$encoding": "hex", "$value": "0"}
    with pytest.raises(MediaIntegrityError, match="malformed media_bytes"):
        validate_current_media_chain_records([corrupt])
