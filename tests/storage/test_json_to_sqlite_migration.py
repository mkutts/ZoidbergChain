from pathlib import Path

import pytest

from blockchain import Blockchain
from peers import PeerStore
from storage import JSONStorageBackend, SQLiteStorageBackend
from storage_migration import MigrationError, migrate_json_to_sqlite
from submission import VOTE_ORIGINAL
from wallet import Wallet


def _seed_json_state(base_dir, submission_image):
    backend = JSONStorageBackend(
        blockchain_file=str(base_dir / "blockchain.json"),
        peers_file=str(base_dir / "peers.json"),
    )
    owner = Wallet()
    contributor_one = Wallet()
    contributor_two = Wallet()
    blockchain = Blockchain(
        project_owner_wallet=owner,
        Contributor_one=contributor_one,
        Contributor_two=contributor_two,
        storage_backend=backend,
    )
    peer_store = PeerStore(
        storage_backend=backend,
    )

    extra_wallets = [Wallet(), Wallet(), Wallet()]
    for wallet in extra_wallets:
        blockchain.wallets[wallet.public_key] = wallet

    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="json to sqlite migration meme",
        submitter=owner.public_key,
    )

    voters = [contributor_one, contributor_two, *extra_wallets]
    for index, voter in enumerate(voters, start=1):
        blockchain.cast_submission_vote(
            submission_id=submission.submission_id,
            voter=voter.public_key,
            vote_type=VOTE_ORIGINAL,
            created_at=1_000 + index,
        )

    blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=2_000,
    )
    blockchain.add_to_mint_queue(submission.submission_id)
    blockchain.mint_next_queued_submission(
        miner=owner.public_key,
        validate_meme=False,
    )
    peer_store.register_peer(
        node_id="peer-a",
        url="http://peer-a.test:8000",
        network_name="zoidberg-testnet",
        now=3_000,
    )
    blockchain.save_blockchain()

    return {
        "backend": backend,
        "blockchain": blockchain,
        "peer_store": peer_store,
        "submission_id": submission.submission_id,
    }


def test_json_to_sqlite_migration_succeeds_from_valid_json_to_empty_sqlite(isolated_data_dir, submission_image):
    seeded = _seed_json_state(isolated_data_dir, submission_image)
    target_db = isolated_data_dir / "zoidbergchain.db"

    summary = migrate_json_to_sqlite(
        source_json_path=isolated_data_dir / "blockchain.json",
        sqlite_db_path=target_db,
    )

    sqlite_backend = SQLiteStorageBackend(sqlite_db_path=str(target_db))
    migrated_state = sqlite_backend.load_blockchain_state()

    assert summary.source_json_path == str(isolated_data_dir / "blockchain.json")
    assert summary.target_sqlite_path == str(target_db)
    assert summary.chain_length == len(seeded["blockchain"].chain)
    assert summary.wallet_count == len(seeded["blockchain"].wallets)
    assert summary.submission_count == len(seeded["blockchain"].submissions)
    assert summary.vote_count == len(seeded["blockchain"].votes)
    assert summary.certificate_count == len(seeded["blockchain"].originality_certificates)
    assert summary.peer_count == len(seeded["peer_store"].list_peers())
    assert summary.latest_block_hash == seeded["blockchain"].get_latest_block().hash
    assert migrated_state["chain"] == seeded["blockchain"]._serialize_blockchain_state()["chain"]
    assert len(sqlite_backend.load_chain()) == len(seeded["blockchain"].chain)
    assert len(sqlite_backend.load_wallets()) == len(seeded["blockchain"].wallets)
    assert len(sqlite_backend.load_submissions()) == len(seeded["blockchain"].submissions)
    assert len(sqlite_backend.load_votes()) == len(seeded["blockchain"].votes)
    assert len(sqlite_backend.load_certificates()) == len(seeded["blockchain"].originality_certificates)
    assert len(sqlite_backend.load_peers()) == len(seeded["peer_store"].list_peers())


def test_migrated_chain_loads_from_sqlite(isolated_data_dir, submission_image):
    _seed_json_state(isolated_data_dir, submission_image)
    target_db = isolated_data_dir / "zoidbergchain.db"

    migrate_json_to_sqlite(
        source_json_path=isolated_data_dir / "blockchain.json",
        sqlite_db_path=target_db,
    )

    reloaded = Blockchain(storage_backend=SQLiteStorageBackend(sqlite_db_path=str(target_db)))
    assert reloaded.get_latest_block().hash is not None
    assert len(reloaded.chain) >= 2


def test_migration_refuses_to_overwrite_existing_sqlite_data_by_default(isolated_data_dir, submission_image):
    _seed_json_state(isolated_data_dir, submission_image)
    target_db = isolated_data_dir / "zoidbergchain.db"
    target_backend = SQLiteStorageBackend(sqlite_db_path=str(target_db))
    target_backend.save_chain([{ "index": 99, "hash": "9" * 64 }])

    with pytest.raises(MigrationError, match="already contains data"):
        migrate_json_to_sqlite(
            source_json_path=isolated_data_dir / "blockchain.json",
            sqlite_db_path=target_db,
        )


def test_migration_allows_overwrite_only_when_explicitly_requested(isolated_data_dir, submission_image):
    seeded = _seed_json_state(isolated_data_dir, submission_image)
    target_db = isolated_data_dir / "zoidbergchain.db"
    target_backend = SQLiteStorageBackend(sqlite_db_path=str(target_db))
    target_backend.save_chain([{ "index": 99, "hash": "9" * 64 }])

    summary = migrate_json_to_sqlite(
        source_json_path=isolated_data_dir / "blockchain.json",
        sqlite_db_path=target_db,
        overwrite=True,
    )

    assert summary.backup_path is not None
    assert Path(summary.backup_path).exists()
    reloaded = SQLiteStorageBackend(sqlite_db_path=str(target_db))
    assert len(reloaded.load_chain()) == len(seeded["blockchain"].chain)
    assert reloaded.load_chain()[-1]["hash"] == seeded["blockchain"].get_latest_block().hash


def test_migration_fails_clearly_for_missing_json_file(isolated_data_dir):
    target_db = isolated_data_dir / "missing-target.db"

    with pytest.raises(MigrationError, match="source JSON not found"):
        migrate_json_to_sqlite(
            source_json_path=isolated_data_dir / "missing-blockchain.json",
            sqlite_db_path=target_db,
        )


def test_migration_fails_clearly_for_malformed_json(isolated_data_dir):
    bad_source = isolated_data_dir / "blockchain.json"
    bad_source.write_text("{not valid json", encoding="utf-8")
    target_db = isolated_data_dir / "bad-target.db"

    with pytest.raises(MigrationError, match="Failed to parse source JSON"):
        migrate_json_to_sqlite(
            source_json_path=bad_source,
            sqlite_db_path=target_db,
        )


def test_migration_respects_data_dir_isolation_and_does_not_touch_node_b(isolated_data_dir, submission_image):
    node_a_dir = isolated_data_dir / "node-a"
    node_b_dir = isolated_data_dir / "node-b"
    node_a_dir.mkdir()
    node_b_dir.mkdir()
    (node_a_dir / "zoidberg.jpg").write_bytes(submission_image.read_bytes())
    (node_b_dir / "zoidberg.jpg").write_bytes(submission_image.read_bytes())

    seed_a = _seed_json_state(node_a_dir, node_a_dir / "zoidberg.jpg")
    seed_b = _seed_json_state(node_b_dir, node_b_dir / "zoidberg.jpg")

    node_b_db = node_b_dir / "zoidbergchain.db"
    migrate_json_to_sqlite(
        source_json_path=node_b_dir / "blockchain.json",
        sqlite_db_path=node_b_db,
    )
    node_b_before = SQLiteStorageBackend(sqlite_db_path=str(node_b_db)).load_blockchain_state()

    migrate_json_to_sqlite(
        source_json_path=node_a_dir / "blockchain.json",
        sqlite_db_path=node_a_dir / "zoidbergchain.db",
    )

    node_b_backend = SQLiteStorageBackend(sqlite_db_path=str(node_b_db))
    node_b_after = node_b_backend.load_blockchain_state()
    assert node_b_before == node_b_after
    assert len(node_b_backend.load_chain()) == len(seed_b["blockchain"].chain)
    assert node_b_backend.load_chain()[-1]["hash"] == seed_b["blockchain"].get_latest_block().hash
    assert len(node_b_backend.load_wallets()) == len(seed_b["blockchain"].wallets)
    assert Path(node_b_db).exists()
    assert len(seed_a["blockchain"].chain) == len(SQLiteStorageBackend(sqlite_db_path=str(node_a_dir / "zoidbergchain.db")).load_chain())
