"""Milestone 3.4 certified-commit replay and durable claim regression tests."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import sqlite3
from threading import Barrier

import pytest

from blockchain import Blockchain
from storage import StaleCanonicalHeadError, StorageUniquenessError, canonical_document_claims, create_storage_backend


def _ready_submission(node, submission_image, wallets, label):
    submission = node.submit_content(
        image_path=str(submission_image), text_content=f"Idempotency {label}",
        submitter=wallets["owner"].public_key,
    )
    for index in range(5):
        node.cast_submission_vote(
            submission_id=submission.submission_id, voter=f"idempotency-{label}-{index}",
            vote_type="original", created_at=2_000_000 + index,
        )
    node.evaluate_submission(submission.submission_id, automated_originality_passed=True, now=2_000_100)
    node.add_to_mint_queue(submission.submission_id)
    return submission


def _commit(node, submission, wallets, **kwargs):
    return node.commit_certified_submission(
        submission.submission_id, miner=wallets["contributor_one"].public_key,
        validate_meme=False, **kwargs,
    )


def _assert_one_committed_result(document, submission):
    blocks = [block for block in document["chain"] if block.get("submission_id") == submission.submission_id]
    assert len(blocks) == 1
    assert document["submissions"][0]["status"] == "minted"
    assert submission.submission_id not in document["mint_queue"]
    assert len({block.get("certificate_id") for block in blocks}) == 1
    reward_ids = [item["reward_id"] for block in document["chain"] for item in (block.get("voter_rewards") or [])]
    assert len(reward_ids) == len(set(reward_ids))


def test_same_certified_commit_replays_without_mutation(blockchain, submission_image, wallets):
    submission = _ready_submission(blockchain, submission_image, wallets, "sequential")
    assert _commit(blockchain, submission, wallets) is True
    after_first = deepcopy(blockchain.storage.load_blockchain_state())

    assert _commit(blockchain, submission, wallets) is True
    after_replay = blockchain.storage.load_blockchain_state()

    assert after_replay == after_first
    _assert_one_committed_result(after_replay, submission)


def test_lost_response_after_durable_commit_retries_to_existing_result(blockchain, submission_image, wallets):
    submission = _ready_submission(blockchain, submission_image, wallets, "lost-response")

    def lose_response(stage):
        if stage == "after_durable_commit_before_response":
            raise ConnectionError("simulated lost response")

    blockchain._atomic_commit_fault_injector = lose_response
    with pytest.raises(ConnectionError, match="lost response"):
        _commit(blockchain, submission, wallets)
    del blockchain._atomic_commit_fault_injector
    committed_before_retry = deepcopy(blockchain.storage.load_blockchain_state())

    assert _commit(blockchain, submission, wallets) is True
    assert blockchain.storage.load_blockchain_state() == committed_before_retry
    _assert_one_committed_result(committed_before_retry, submission)


@pytest.mark.parametrize("backend_name", ["json", "sqlite"])
def test_concurrent_identical_commit_resolves_one_durable_result(isolated_data_dir, submission_image, wallets, backend_name):
    node_dir = isolated_data_dir / backend_name
    node_dir.mkdir()
    storage = create_storage_backend(
        backend_name, blockchain_file=str(node_dir / "blockchain.json"),
        peers_file=str(node_dir / "peers.json"), sqlite_db_path=str(node_dir / "chain.db"),
    )
    first = Blockchain(wallets["owner"], wallets["contributor_one"], wallets["contributor_two"], storage_backend=storage)
    submission = _ready_submission(first, submission_image, wallets, backend_name)
    second = Blockchain(wallets["owner"], wallets["contributor_one"], wallets["contributor_two"], storage_backend=storage)
    expected_head = first._current_canonical_head()
    gate = Barrier(2)

    def attempt(node):
        gate.wait()
        return _commit(node, submission, wallets, expected_head=expected_head)

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(attempt, (first, second))) == [True, True]
    _assert_one_committed_result(storage.load_blockchain_state(), submission)


def test_different_submissions_on_same_head_still_return_stale(isolated_data_dir, submission_image, wallets):
    node_dir = isolated_data_dir / "different-stale"
    node_dir.mkdir()
    storage = create_storage_backend(
        blockchain_file=str(node_dir / "blockchain.json"), peers_file=str(node_dir / "peers.json"),
        sqlite_db_path=str(node_dir / "chain.db"),
    )
    first = Blockchain(wallets["owner"], wallets["contributor_one"], wallets["contributor_two"], storage_backend=storage)
    first_submission = _ready_submission(first, submission_image, wallets, "different-one")
    second_submission = _ready_submission(first, submission_image, wallets, "different-two")
    second = Blockchain(wallets["owner"], wallets["contributor_one"], wallets["contributor_two"], storage_backend=storage)
    expected_head = first._current_canonical_head()
    gate = Barrier(2)

    def attempt(node, submission):
        gate.wait()
        try:
            return _commit(node, submission, wallets, expected_head=expected_head)
        except StaleCanonicalHeadError:
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda pair: attempt(*pair), ((first, first_submission), (second, second_submission))))
    assert sorted(outcomes, key=str) == [True, "stale"]
    assert len(storage.load_blockchain_state()["chain"]) == 2


def test_conflicting_replay_is_rejected(blockchain, submission_image, wallets):
    submission = _ready_submission(blockchain, submission_image, wallets, "conflict")
    assert _commit(blockchain, submission, wallets) is True
    submission.content_hash = "0" * 64

    with pytest.raises(ValueError, match="content_hash|Conflicting"):
        _commit(blockchain, submission, wallets)


def test_storage_claims_reject_duplicate_native_nonce_and_conflicting_rewards():
    base_block = {
        "index": 1, "hash": "a" * 64, "submission_id": "submission-a", "certificate_id": "certificate-a",
        "content_hash": "content-a", "creator_wallet": "creator-a", "reward_type": "meme_mining_reward",
        "reward_recipient": "creator-a", "reward_amount": "1", "native_transactions": [
            {"tx_id": "tx-a", "from_address": "sender-a", "nonce": "1"},
        ], "voter_rewards": [{"reward_id": "reward-a", "reward_recipient": "voter-a", "reward_amount": "1"}],
    }
    duplicate_nonce = deepcopy(base_block)
    duplicate_nonce.update({"index": 2, "hash": "b" * 64, "submission_id": "submission-b", "certificate_id": "certificate-b"})
    duplicate_nonce["native_transactions"] = [{"tx_id": "tx-b", "from_address": "sender-a", "nonce": "1"}]
    with pytest.raises(StorageUniquenessError, match="nonce"):
        canonical_document_claims({"chain": [base_block, duplicate_nonce]})

    conflicting_reward = deepcopy(base_block)
    conflicting_reward.update({"index": 2, "hash": "c" * 64, "submission_id": "submission-b", "certificate_id": "certificate-b"})
    conflicting_reward["native_transactions"] = []
    conflicting_reward["voter_rewards"] = [{"reward_id": "reward-a", "reward_recipient": "other-voter", "reward_amount": "9"}]
    with pytest.raises(StorageUniquenessError, match="Reward"):
        canonical_document_claims({"chain": [base_block, conflicting_reward]})


def test_sqlite_claim_schema_upgrades_existing_section_database(isolated_data_dir):
    database = isolated_data_dir / "legacy-sections.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE storage_sections (section_name TEXT PRIMARY KEY, json_data TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
    backend = create_storage_backend("sqlite", sqlite_db_path=str(database))
    with sqlite3.connect(backend.sqlite_db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"certified_commit_claims", "canonical_native_transaction_claims", "canonical_reward_claims"} <= tables
