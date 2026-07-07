from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

import config
import storage_tools
from blockchain import Blockchain
from peers import PeerStore
from storage import JSONStorageBackend, SQLiteStorageBackend
from wallet import Wallet
from submission import VOTE_ORIGINAL


def _reload_config():
    importlib.reload(config)
    importlib.reload(storage_tools)


def _seed_backend(backend, submission_image, *, owner=None, contributor_one=None, contributor_two=None):
    owner = owner or Wallet()
    contributor_one = contributor_one or Wallet()
    contributor_two = contributor_two or Wallet()
    blockchain = Blockchain(
        project_owner_wallet=owner,
        Contributor_one=contributor_one,
        Contributor_two=contributor_two,
        storage_backend=backend,
    )
    peer_store = PeerStore(storage_backend=backend)

    extra_wallets = [Wallet() for _ in range(3)]
    for wallet in extra_wallets:
        blockchain.wallets[wallet.public_key] = wallet

    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="storage tools meme",
        submitter=owner.public_key,
    )

    for index, wallet in enumerate([contributor_one, contributor_two, *extra_wallets], start=1):
        blockchain.cast_submission_vote(
            submission_id=submission.submission_id,
            voter=wallet.public_key,
            vote_type=VOTE_ORIGINAL,
            created_at=float(index),
        )

    blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=10.0,
    )
    certificate = blockchain.get_originality_certificate_for_submission(submission.submission_id)
    blockchain.add_to_mint_queue(submission.submission_id)
    blockchain.mint_next_queued_submission(miner=owner.public_key, validate_meme=False)
    peer_store.register_peer(
        node_id="peer-a",
        url="http://peer-a.test:8000",
        network_name="zoidberg-testnet",
        now=11.0,
    )
    blockchain.save_blockchain()

    return {
        "backend": backend,
        "blockchain": blockchain,
        "peer_store": peer_store,
        "owner": owner,
        "contributor_one": contributor_one,
        "contributor_two": contributor_two,
        "submission": submission,
        "certificate": certificate,
        "extra_wallets": extra_wallets,
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


@pytest.mark.parametrize(
    "backend_factory",
    [_json_backend, _sqlite_backend],
)
def test_backup_file_is_created_and_sanitized(backend_factory, isolated_data_dir, submission_image):
    backend = backend_factory(isolated_data_dir, "backup")
    seeded = _seed_backend(backend, submission_image)
    backup_result = storage_tools.backup_storage(seeded["backend"], data_dir=isolated_data_dir)
    backup_path = Path(backup_result["backup_path"])
    original_private_key = seeded["owner"].private_key

    assert backup_path.exists()
    assert backup_result["backend"] in {"json", "sqlite"}
    assert config.NODE_ID in backup_path.name
    assert backup_result["backend"] in backup_path.name
    assert "T" in backup_path.stem
    assert original_private_key not in backup_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "backend_factory",
    [_json_backend, _sqlite_backend],
)
def test_export_includes_core_state_and_excludes_private_keys_by_default(backend_factory, isolated_data_dir, submission_image):
    backend = backend_factory(isolated_data_dir, "export")
    seeded = _seed_backend(backend, submission_image)
    output_path = isolated_data_dir / "export.json"

    result = storage_tools.export_storage(seeded["backend"], output_path=output_path)
    exported = json.loads(output_path.read_text(encoding="utf-8"))

    assert result["written"] is True
    assert exported["export_version"] == storage_tools.EXPORT_VERSION
    assert exported["metadata"]["node_id"] == config.NODE_ID
    assert exported["metadata"]["network_name"] == config.NETWORK_NAME
    assert exported["metadata"]["storage_backend"] in {"json", "sqlite"}
    assert exported["metadata"]["latest_block_hash"] == seeded["backend"].load_chain()[-1]["hash"]
    assert exported["state"]["chain"]
    assert exported["state"]["submissions"]
    assert exported["state"]["votes"]
    assert exported["state"]["originality_certificates"]
    assert exported["state"]["peers"]
    assert seeded["owner"].private_key not in output_path.read_text(encoding="utf-8")
    assert '"private_key":' not in output_path.read_text(encoding="utf-8")


def test_export_private_keys_requires_development_and_explicit_flag(monkeypatch, isolated_data_dir, submission_image):
    backend = _json_backend(isolated_data_dir, "private-keys")
    seeded = _seed_backend(backend, submission_image)
    output_path = isolated_data_dir / "private.json"

    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("PUBLIC_API_MODE", "false")
    monkeypatch.setenv("ALLOW_DEV_WALLET_PRIVATE_KEY_EXPORT", "true")
    monkeypatch.setenv("PEER_SHARED_SECRET", "development-only-secret")
    _reload_config()

    exported = storage_tools.export_storage(
        seeded["backend"],
        output_path=output_path,
        include_private_keys=True,
    )
    snapshot = json.loads(output_path.read_text(encoding="utf-8"))

    assert exported["contains_private_keys"] is True
    assert snapshot["metadata"]["contains_private_keys"] is True
    assert snapshot["state"]["wallets"][seeded["owner"].public_key]["private_key"] == seeded["owner"].private_key
    assert "warning" in snapshot["metadata"]

    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("PUBLIC_API_MODE", raising=False)
    monkeypatch.delenv("ALLOW_DEV_WALLET_PRIVATE_KEY_EXPORT", raising=False)
    monkeypatch.delenv("PEER_SHARED_SECRET", raising=False)
    _reload_config()


def test_export_private_keys_rejected_outside_development(monkeypatch, isolated_data_dir, submission_image):
    backend = _json_backend(isolated_data_dir, "private-keys-blocked")
    seeded = _seed_backend(backend, submission_image)
    output_path = isolated_data_dir / "blocked.json"

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("PUBLIC_API_MODE", "true")
    monkeypatch.setenv("ALLOW_DEV_WALLET_PRIVATE_KEY_EXPORT", "false")
    monkeypatch.setenv("PEER_SHARED_SECRET", "production-secret")
    _reload_config()

    with pytest.raises(ValueError, match="Private key export is only allowed"):
        storage_tools.export_storage(
            seeded["backend"],
            output_path=output_path,
            include_private_keys=True,
        )

    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("PUBLIC_API_MODE", raising=False)
    monkeypatch.delenv("ALLOW_DEV_WALLET_PRIVATE_KEY_EXPORT", raising=False)
    monkeypatch.delenv("PEER_SHARED_SECRET", raising=False)
    _reload_config()


@pytest.mark.parametrize(
    "backend_factory",
    [_json_backend, _sqlite_backend],
)
def test_import_round_trip_into_empty_backend(backend_factory, isolated_data_dir, submission_image):
    source_backend = backend_factory(isolated_data_dir, "source")
    seeded = _seed_backend(source_backend, submission_image)
    export_path = isolated_data_dir / "snapshot.json"
    storage_tools.export_storage(seeded["backend"], output_path=export_path)

    target_dir = isolated_data_dir / "target"
    target_backend = backend_factory(target_dir, "target")
    import_result = storage_tools.import_storage(target_backend, input_path=export_path)
    reloaded = Blockchain(storage_backend=target_backend)

    assert import_result["written"] is True
    assert reloaded.get_submission(seeded["submission"].submission_id) is not None
    assert reloaded.get_originality_certificate(seeded["certificate"].certificate_id) is not None
    assert reloaded.get_submission_votes(seeded["submission"].submission_id)["votes"]
    assert reloaded.get_latest_block().hash == seeded["backend"].load_chain()[-1]["hash"]


def test_import_refuses_overwrite_by_default(isolated_data_dir, submission_image):
    source_backend = _json_backend(isolated_data_dir, "source-overwrite")
    seeded = _seed_backend(source_backend, submission_image)
    export_path = isolated_data_dir / "overwrite.json"
    storage_tools.export_storage(seeded["backend"], output_path=export_path)

    target_backend = _json_backend(isolated_data_dir, "target-overwrite")
    _seed_backend(target_backend, submission_image)

    with pytest.raises(ValueError, match="already contains data"):
        storage_tools.import_storage(target_backend, input_path=export_path)


def test_import_creates_backup_before_overwrite(isolated_data_dir, submission_image):
    source_backend = _json_backend(isolated_data_dir, "source-backup")
    seeded = _seed_backend(source_backend, submission_image)
    export_path = isolated_data_dir / "source-backup.json"
    storage_tools.export_storage(seeded["backend"], output_path=export_path)

    target_backend = _json_backend(isolated_data_dir, "target-backup")
    storage_tools.import_storage(target_backend, input_path=export_path)
    PeerStore(storage_backend=target_backend).register_peer(
        node_id="peer-b",
        url="http://peer-b.test:8000",
        network_name="zoidberg-testnet",
        now=12.0,
    )
    result = storage_tools.import_storage(target_backend, input_path=export_path, overwrite=True)

    assert result["backup"] is not None
    assert Path(result["backup"]["backup_path"]).exists()
    assert Blockchain(storage_backend=target_backend).get_submission(seeded["submission"].submission_id) is not None


def test_import_rejects_malformed_snapshot(isolated_data_dir):
    backend = _json_backend(isolated_data_dir, "malformed")
    bad_path = isolated_data_dir / "bad.json"
    bad_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="missing required keys"):
        storage_tools.import_storage(backend, input_path=bad_path)


def test_import_rejects_wrong_network_without_override(isolated_data_dir, submission_image):
    source_backend = _json_backend(isolated_data_dir, "source-network")
    seeded = _seed_backend(source_backend, submission_image)
    export_path = isolated_data_dir / "network.json"
    storage_tools.export_storage(seeded["backend"], output_path=export_path)

    snapshot = json.loads(export_path.read_text(encoding="utf-8"))
    snapshot["metadata"]["network_name"] = "different-network"
    export_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

    target_backend = _json_backend(isolated_data_dir, "target-network")

    with pytest.raises(ValueError, match="does not match this node's network"):
        storage_tools.import_storage(target_backend, input_path=export_path)


def test_import_runs_integrity_check(monkeypatch, isolated_data_dir, submission_image):
    backend = _json_backend(isolated_data_dir, "integrity")
    seeded = _seed_backend(backend, submission_image)
    export_path = isolated_data_dir / "integrity.json"
    storage_tools.export_storage(seeded["backend"], output_path=export_path)

    target_backend = _json_backend(isolated_data_dir, "integrity-target")
    called = {"count": 0}

    def tracking_integrity(check_backend=None):
        called["count"] += 1
        return {"healthy": True}

    monkeypatch.setattr(storage_tools, "check_storage_integrity", tracking_integrity)

    storage_tools.import_storage(target_backend, input_path=export_path)
    assert called["count"] == 1


def test_dry_run_does_not_write_files(isolated_data_dir, submission_image):
    backend = _json_backend(isolated_data_dir, "dry-run")
    seeded = _seed_backend(backend, submission_image)
    snapshot_path = isolated_data_dir / "dry-run-snapshot.json"
    storage_tools.export_storage(seeded["backend"], output_path=snapshot_path)
    export_path = isolated_data_dir / "dry-run-export.json"

    backup_result = storage_tools.backup_storage(seeded["backend"], data_dir=isolated_data_dir, dry_run=True)
    export_result = storage_tools.export_storage(seeded["backend"], output_path=export_path, dry_run=True)
    import_result = storage_tools.import_storage(
        _json_backend(isolated_data_dir, "dry-run-target"),
        input_path=snapshot_path,
        dry_run=True,
    )

    assert backup_result["dry_run"] is True
    assert export_result["dry_run"] is True
    assert import_result["dry_run"] is True
    assert not Path(backup_result["backup_path"]).exists()
    assert not export_path.exists()


@pytest.mark.parametrize(
    "backend_factory",
    [_json_backend, _sqlite_backend],
)
def test_backup_snapshot_can_be_imported_as_restore(backend_factory, isolated_data_dir, submission_image):
    source_backend = backend_factory(isolated_data_dir, "restore-source")
    seeded = _seed_backend(source_backend, submission_image)
    backup_result = storage_tools.backup_storage(seeded["backend"])

    restored_backend = backend_factory(isolated_data_dir, "restore-target")
    import_result = storage_tools.import_storage(
        restored_backend,
        input_path=backup_result["backup_path"],
    )
    reloaded = Blockchain(storage_backend=restored_backend)

    assert import_result["written"] is True
    assert reloaded.get_submission(seeded["submission"].submission_id) is not None
    assert reloaded.get_originality_certificate(seeded["certificate"].certificate_id) is not None


@pytest.mark.parametrize(
    "backend_factory",
    [_json_backend, _sqlite_backend],
)
def test_imported_state_supports_follow_on_app_workflow(backend_factory, isolated_data_dir, submission_image):
    source_backend = backend_factory(isolated_data_dir, "workflow-source")
    seeded = _seed_backend(source_backend, submission_image)
    export_path = isolated_data_dir / "workflow-source.json"
    storage_tools.export_storage(seeded["backend"], output_path=export_path)

    target_backend = backend_factory(isolated_data_dir, "workflow-target")
    storage_tools.import_storage(target_backend, input_path=export_path)
    reloaded = Blockchain(storage_backend=target_backend)

    owner_key = seeded["owner"].public_key
    voter_keys = [
        seeded["contributor_one"].public_key,
        seeded["contributor_two"].public_key,
        *(wallet.public_key for wallet in seeded["extra_wallets"]),
    ]
    new_submission = reloaded.submit_content(
        image_path=str(submission_image),
        text_content="post import workflow meme",
        submitter=owner_key,
    )
    for index, voter_key in enumerate(voter_keys, start=1):
        reloaded.cast_submission_vote(
            submission_id=new_submission.submission_id,
            voter=voter_key,
            vote_type=VOTE_ORIGINAL,
            created_at=20.0 + index,
        )

    result = reloaded.evaluate_submission(
        new_submission.submission_id,
        automated_originality_passed=True,
        now=30.0,
    )
    certificate = reloaded.get_originality_certificate_for_submission(new_submission.submission_id)
    reloaded.add_to_mint_queue(new_submission.submission_id)
    reloaded.mint_next_queued_submission(miner=owner_key, validate_meme=False)
    reloaded.save_blockchain()

    persisted = Blockchain(storage_backend=target_backend)
    assert result["status"] == "approved"
    assert certificate is not None
    assert persisted.get_originality_certificate(certificate.certificate_id) is not None
    assert persisted.get_latest_block().certificate_id == certificate.certificate_id


@pytest.mark.parametrize(
    "backend_factory",
    [_json_backend, _sqlite_backend],
)
def test_node_a_backup_export_import_do_not_affect_node_b(backend_factory, isolated_data_dir, submission_image):
    node_a_backend = backend_factory(isolated_data_dir, "node-a")
    node_b_backend = backend_factory(isolated_data_dir, "node-b")
    seed_a = _seed_backend(node_a_backend, submission_image)
    seed_b = _seed_backend(node_b_backend, submission_image)
    node_b_before = node_b_backend.load_blockchain_state()

    export_path = isolated_data_dir / "node-a-export.json"
    storage_tools.backup_storage(seed_a["backend"])
    storage_tools.export_storage(seed_a["backend"], output_path=export_path)
    storage_tools.import_storage(node_a_backend, input_path=export_path, overwrite=True)

    node_b_after = node_b_backend.load_blockchain_state()
    assert node_b_after == node_b_before
    assert Blockchain(storage_backend=node_b_backend).get_latest_block().hash == seed_b["blockchain"].get_latest_block().hash


def test_cli_errors_are_reported_without_traceback(capsys):
    exit_code = storage_tools.run_cli(["import", "--input", "missing-snapshot.json"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Traceback" not in captured.err
    assert "missing-snapshot.json" in captured.err
