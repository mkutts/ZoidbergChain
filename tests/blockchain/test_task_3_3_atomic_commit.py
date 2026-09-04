"""Milestone 3.3 atomic certified-block commitment regression tests."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from blockchain import Blockchain
from storage import StaleCanonicalHeadError, create_storage_backend


class InjectedCommitFailure(RuntimeError):
    pass


def _ready_submission(blockchain, submission_image, wallets, label="atomic"):
    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content=f"Atomic commit {label}",
        submitter=wallets["owner"].public_key,
    )
    for index in range(5):
        blockchain.cast_submission_vote(
            submission_id=submission.submission_id,
            voter=f"atomic-voter-{label}-{index}",
            vote_type="original",
            created_at=1_000_000 + index,
        )
    blockchain.evaluate_submission(submission.submission_id, automated_originality_passed=True, now=1_000_100)
    blockchain.add_to_mint_queue(submission.submission_id)
    return submission


@pytest.mark.parametrize(
    "stage",
    [
        "before_block_persistence",
        "after_block_persistence",
        "during_transaction_settlement",
        "after_transaction_settlement",
        "during_reward_settlement",
        "after_rewards_before_submission_minted",
        "after_submission_mutation_before_canonical_head_update",
        "before_transaction_commit",
    ],
)
def test_atomic_certified_commit_rolls_back_every_fault_stage(blockchain, submission_image, wallets, stage):
    submission = _ready_submission(blockchain, submission_image, wallets, stage)
    before = blockchain.storage.load_blockchain_state()

    def fail_at(observed_stage):
        if observed_stage == stage:
            raise InjectedCommitFailure(stage)

    blockchain._atomic_commit_fault_injector = fail_at
    with pytest.raises(InjectedCommitFailure, match=stage):
        blockchain.commit_certified_submission(
            submission.submission_id,
            miner=wallets["contributor_one"].public_key,
            validate_meme=False,
        )
    del blockchain._atomic_commit_fault_injector

    # Compare the complete persisted document: chain/head, native transaction
    # state and nonces, reward records, queue/submission status, certificates,
    # and every other durable domain must be identical to the pre-commit view.
    assert blockchain.storage.load_blockchain_state() == before
    assert blockchain.get_latest_block().hash == before["chain"][-1]["hash"]
    assert blockchain.get_submission(submission.submission_id).status == "queued"


def test_competing_expected_head_commits_allow_exactly_one_winner(isolated_data_dir, submission_image, wallets):
    node_dir = isolated_data_dir / "competing-head"
    node_dir.mkdir()
    storage = create_storage_backend(
        blockchain_file=str(node_dir / "blockchain.json"),
        peers_file=str(node_dir / "peers.json"),
        sqlite_db_path=str(node_dir / "zoidbergchain.db"),
    )
    first = Blockchain(wallets["owner"], wallets["contributor_one"], wallets["contributor_two"], storage_backend=storage)
    submission = _ready_submission(first, submission_image, wallets, "competing")
    second = Blockchain(wallets["owner"], wallets["contributor_one"], wallets["contributor_two"], storage_backend=storage)
    expected_head = first._current_canonical_head()
    assert second._current_canonical_head() == expected_head
    gate = Barrier(2)

    def attempt(node):
        gate.wait()
        try:
            return node.commit_certified_submission(
                submission.submission_id,
                expected_head=expected_head,
                miner=wallets["contributor_one"].public_key,
                validate_meme=False,
            )
        except StaleCanonicalHeadError:
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(attempt, (first, second)))

    assert sorted(outcomes, key=str) == [True, "stale"]
    persisted = storage.load_blockchain_state()
    assert len(persisted["chain"]) == 2
    assert persisted["chain"][-1]["previous_hash"] == expected_head["hash"]
    assert persisted["submissions"][0]["status"] == "minted"
    assert persisted["mint_queue"] == []


def test_sqlite_atomic_commit_rolls_back_after_reward_settlement(isolated_data_dir, submission_image, wallets):
    node_dir = isolated_data_dir / "sqlite-atomic"
    node_dir.mkdir()
    storage = create_storage_backend(
        "sqlite",
        blockchain_file=str(node_dir / "blockchain.json"),
        peers_file=str(node_dir / "peers.json"),
        sqlite_db_path=str(node_dir / "zoidbergchain.db"),
    )
    node = Blockchain(wallets["owner"], wallets["contributor_one"], wallets["contributor_two"], storage_backend=storage)
    submission = _ready_submission(node, submission_image, wallets, "sqlite")
    before = storage.load_blockchain_state()
    node._atomic_commit_fault_injector = lambda stage: (_ for _ in ()).throw(InjectedCommitFailure(stage)) if stage == "after_rewards_before_submission_minted" else None
    with pytest.raises(InjectedCommitFailure):
        node.commit_certified_submission(submission.submission_id, miner=wallets["contributor_one"].public_key, validate_meme=False)
    del node._atomic_commit_fault_injector
    assert storage.load_blockchain_state() == before
