import os
import sqlite3
from pathlib import Path

import pytest

from blockchain import Blockchain
from peers import PeerStore
import storage
from storage import SQLiteStorageBackend
from submission import VOTE_NOT_ORIGINAL, VOTE_ORIGINAL
from wallet import Wallet


def _backend(base_dir, name="node"):
    node_dir = base_dir / name
    return SQLiteStorageBackend(sqlite_db_path=str(node_dir / "zoidbergchain.db"))


def _table_rows(db_path):
    with sqlite3.connect(db_path) as connection:
        return connection.execute(
            "SELECT section_name, json_data FROM storage_sections ORDER BY section_name"
        ).fetchall()


def test_sqlite_storage_backend_initializes_database(isolated_data_dir):
    backend = _backend(isolated_data_dir, "init")

    assert Path(backend.sqlite_db_path).exists()
    rows = _table_rows(backend.sqlite_db_path)
    assert {row[0] for row in rows} == {
        "chain",
        "wallets",
        "submissions",
        "mint_queue",
        "votes",
        "originality_certificates",
        "peers",
    }


def test_sqlite_storage_backend_loads_existing_chain_data(isolated_data_dir):
    backend = _backend(isolated_data_dir, "load-existing")
    state = {
        "chain": [
            {
                "index": 0,
                "previous_hash": "0",
                "timestamp": 123.0,
                "transactions": [],
                "miner": "GENESIS",
                "meme": {"text": "sqlite load"},
                "hash": "a" * 64,
                "submission_id": None,
                "certificate_id": None,
                "content_hash": None,
                "creator_wallet": None,
                "vote_hash": None,
                "approval_percentage": None,
                "decisive_vote_total": None,
                "minimum_votes_required": None,
                "approved_at": None,
                "originality_score": None,
            }
        ],
        "wallets": {},
        "submissions": [],
        "mint_queue": [],
        "votes": [],
        "originality_certificates": [],
    }

    backend.save_blockchain_state(state)

    assert backend.load_blockchain_state()["chain"] == state["chain"]
    assert backend.load_chain() == state["chain"]


def test_sqlite_storage_backend_saves_and_reloads_chain_data(isolated_data_dir):
    backend = _backend(isolated_data_dir, "save-chain")
    chain = [{"index": 1, "hash": "b" * 64}]

    backend.save_chain(chain)

    assert backend.load_chain() == chain


def test_sqlite_storage_backend_wallets_save_reload(isolated_data_dir):
    backend = _backend(isolated_data_dir, "wallets")
    wallets = {
        "wallet-a": {"public_key": "wallet-a", "private_key": "private-a"},
        "wallet-b": {"public_key": "wallet-b", "private_key": "private-b"},
    }

    backend.save_wallets(wallets)

    assert backend.load_wallets() == wallets


def test_sqlite_storage_backend_submissions_save_reload(isolated_data_dir):
    backend = _backend(isolated_data_dir, "submissions")
    submissions = [
        {
            "submission_id": "submission-a",
            "image_path": "meme-a.jpg",
            "text_content": "meme a",
            "submitter": "wallet-a",
            "status": "pending",
            "created_at": 1.0,
            "hard_reject_reason": None,
            "content_hash": "c" * 64,
            "certificate_id": None,
        }
    ]

    backend.save_submissions(submissions)

    assert backend.load_submissions() == submissions


def test_sqlite_storage_backend_votes_save_reload(isolated_data_dir):
    backend = _backend(isolated_data_dir, "votes")
    votes = [
        {
            "submission_id": "submission-a",
            "voter": "wallet-b",
            "vote_type": VOTE_ORIGINAL,
            "created_at": 1.0,
        },
        {
            "submission_id": "submission-a",
            "voter": "wallet-c",
            "vote_type": VOTE_NOT_ORIGINAL,
            "created_at": 2.0,
        },
    ]

    backend.save_votes(votes)

    assert backend.load_votes() == votes


def test_sqlite_storage_backend_certificates_save_reload(isolated_data_dir):
    backend = _backend(isolated_data_dir, "certificates")
    certificates = [
        {
            "certificate_id": "d" * 64,
            "submission_id": "submission-a",
            "content_hash": "e" * 64,
            "creator_wallet": "wallet-a",
            "vote_total": 6,
            "decisive_vote_total": 5,
            "original_votes": 4,
            "not_original_votes": 1,
            "unsure_votes": 1,
            "approval_percentage": 0.8,
            "minimum_votes_required": 5,
            "approved_at": 1.0,
            "network_name": "zoidberg-testnet",
            "issuing_node_id": "node-a",
            "vote_hash": "f" * 64,
            "originality_score": 2.0,
        }
    ]

    backend.save_certificates(certificates)

    assert backend.load_certificates() == certificates


def test_sqlite_storage_backend_peers_save_reload(isolated_data_dir):
    backend = _backend(isolated_data_dir, "peers")
    peers = [
        {
            "node_id": "peer-a",
            "url": "http://peer-a.test:8000",
            "network_name": "zoidberg-testnet",
            "last_seen": 100.0,
            "status": "active",
        }
    ]

    backend.save_peers(peers)

    assert backend.load_peers() == peers


def test_sqlite_storage_backend_failed_save_rolls_back_cleanly(monkeypatch, isolated_data_dir):
    backend = _backend(isolated_data_dir, "rollback")
    original_chain = [{"index": 1, "hash": "1" * 64}]
    updated_chain = [{"index": 2, "hash": "2" * 64}]

    backend.save_chain(original_chain)

    real_dumps = storage.json.dumps
    call_count = {"count": 0}

    def flaky_dumps(obj, *args, **kwargs):
        call_count["count"] += 1
        if call_count["count"] == 3:
            raise RuntimeError("forced sqlite save failure")
        return real_dumps(obj, *args, **kwargs)

    monkeypatch.setattr(storage.json, "dumps", flaky_dumps)

    with pytest.raises(RuntimeError, match="forced sqlite save failure"):
        backend.save_blockchain_state(
            {
                "chain": updated_chain,
                "wallets": {},
                "submissions": [],
                "mint_queue": [],
                "votes": [],
                "originality_certificates": [],
                "peers": [],
            }
        )

    assert backend.load_chain() == original_chain


def test_sqlite_storage_backend_backup_helper_creates_usable_backup(isolated_data_dir):
    backend = _backend(isolated_data_dir, "backup")
    chain = [{"index": 1, "hash": "1" * 64}]

    backend.save_chain(chain)
    backup_path = Path(backend.backup_sqlite_database())

    assert backup_path.exists()
    assert SQLiteStorageBackend(sqlite_db_path=str(backup_path)).load_chain() == chain


def test_sqlite_storage_integrity_passes_on_valid_database(isolated_data_dir):
    backend = _backend(isolated_data_dir, "integrity")
    backend.save_chain([{ "index": 1, "hash": "1" * 64 }])

    report = storage.check_storage_integrity(backend)

    assert report["backend"] == "sqlite"
    assert report["healthy"] is True
    assert report["main_path"] == backend.sqlite_db_path


def test_sqlite_storage_integrity_fails_on_malformed_section_json(isolated_data_dir):
    backend = _backend(isolated_data_dir, "integrity-bad")
    backend.save_chain([{ "index": 1, "hash": "1" * 64 }])

    with sqlite3.connect(backend.sqlite_db_path) as connection:
        connection.execute(
            "UPDATE storage_sections SET json_data = ? WHERE section_name = ?",
            ("{not valid json", "chain"),
        )
        connection.commit()

    with pytest.raises(storage.StorageCorruptionError, match="Malformed JSON stored in SQLite section chain"):
        storage.check_storage_integrity(backend)


def test_sqlite_storage_backend_preserves_logical_data_shape(isolated_data_dir):
    backend = _backend(isolated_data_dir, "shape")
    state = backend.load_blockchain_state()

    assert state == {
        "chain": [],
        "wallets": {},
        "submissions": [],
        "mint_queue": [],
        "votes": [],
        "originality_certificates": [],
        "peers": [],
    }


def test_sqlite_data_dir_isolation_for_two_nodes(isolated_data_dir):
    backend_a = _backend(isolated_data_dir, "node-a")
    backend_b = _backend(isolated_data_dir, "node-b")

    backend_a.save_chain([{ "index": 1, "hash": "1" * 64 }])
    backend_b.save_chain([{ "index": 2, "hash": "2" * 64 }])

    assert backend_a.load_chain()[0]["index"] == 1
    assert backend_b.load_chain()[0]["index"] == 2
    assert backend_a.sqlite_db_path != backend_b.sqlite_db_path
    assert os.path.exists(backend_a.sqlite_db_path)
    assert os.path.exists(backend_b.sqlite_db_path)


def test_blockchain_round_trip_persists_core_entities_sqlite(submission_image, isolated_data_dir):
    backend = _backend(isolated_data_dir, "round-trip")
    owner = Wallet()
    contributor_one = Wallet()
    contributor_two = Wallet()
    blockchain = Blockchain(
        project_owner_wallet=owner,
        Contributor_one=contributor_one,
        Contributor_two=contributor_two,
        storage_backend=backend,
    )
    peer_store = PeerStore(storage_backend=backend)

    extra_wallet = Wallet()
    extra_wallet_two = Wallet()
    extra_wallet_three = Wallet()
    blockchain.wallets[extra_wallet.public_key] = extra_wallet
    blockchain.wallets[extra_wallet_two.public_key] = extra_wallet_two
    blockchain.wallets[extra_wallet_three.public_key] = extra_wallet_three

    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="sqlite smoke test meme",
        submitter=owner.public_key,
    )

    blockchain.cast_submission_vote(
        submission_id=submission.submission_id,
        voter=contributor_one.public_key,
        vote_type=VOTE_ORIGINAL,
        created_at=1.0,
    )
    blockchain.cast_submission_vote(
        submission_id=submission.submission_id,
        voter=contributor_two.public_key,
        vote_type=VOTE_ORIGINAL,
        created_at=2.0,
    )
    blockchain.cast_submission_vote(
        submission_id=submission.submission_id,
        voter=extra_wallet.public_key,
        vote_type=VOTE_ORIGINAL,
        created_at=3.0,
    )
    blockchain.cast_submission_vote(
        submission_id=submission.submission_id,
        voter=extra_wallet_two.public_key,
        vote_type=VOTE_ORIGINAL,
        created_at=4.0,
    )
    blockchain.cast_submission_vote(
        submission_id=submission.submission_id,
        voter=extra_wallet_three.public_key,
        vote_type=VOTE_ORIGINAL,
        created_at=5.0,
    )
    blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=6.0,
    )
    certificate = blockchain.get_originality_certificate_for_submission(submission.submission_id)
    assert certificate is not None
    blockchain.add_to_mint_queue(submission.submission_id)
    blockchain.mint_next_queued_submission(
        miner=owner.public_key,
        validate_meme=False,
    )
    peer_store.register_peer(
        node_id="peer-a",
        url="http://peer-a.test:8000",
        network_name="zoidberg-testnet",
        now=7.0,
    )
    blockchain.save_blockchain()

    reloaded_blockchain = Blockchain(storage_backend=backend)
    reloaded_peer_store = PeerStore(storage_backend=backend)

    assert extra_wallet.public_key in reloaded_blockchain.wallets
    assert reloaded_blockchain.get_submission(submission.submission_id) is not None
    assert reloaded_blockchain.get_submission_votes(submission.submission_id)["votes"]
    assert reloaded_blockchain.get_originality_certificate(certificate.certificate_id) is not None
    assert reloaded_blockchain.get_latest_block().certificate_id == certificate.certificate_id
    assert reloaded_peer_store.list_peers()[0]["node_id"] == "peer-a"
