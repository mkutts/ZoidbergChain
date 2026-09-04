import pytest

from blockchain import Blockchain
from config import PROTOCOL_V1_CONFIRMATION_DEPTH, PROTOCOL_V1_FINALITY_DEPTH
from storage import JSONStorageBackend, SQLiteStorageBackend
from submission import APPROVED, MINTED, QUEUED, VOTE_NOT_ORIGINAL, VOTE_ORIGINAL
from wallet import Wallet


def _json_backend(base_dir, name="node"):
    node_dir = base_dir / name
    return JSONStorageBackend(
        blockchain_file=str(node_dir / "blockchain.json"),
        peers_file=str(node_dir / "peers.json"),
    )


def _sqlite_backend(base_dir, name="node"):
    node_dir = base_dir / name
    return SQLiteStorageBackend(sqlite_db_path=str(node_dir / "zoidbergchain.db"))


def _wallets():
    return {
        "owner": Wallet(),
        "contributor_one": Wallet(),
        "contributor_two": Wallet(),
    }


def _cast_majority_original_votes(blockchain, submission_id):
    for index, vote_type in enumerate(
        [
            VOTE_ORIGINAL,
            VOTE_ORIGINAL,
            VOTE_ORIGINAL,
            VOTE_ORIGINAL,
            VOTE_NOT_ORIGINAL,
        ]
    ):
        blockchain.cast_submission_vote(
            submission_id=submission_id,
            voter=f"lifecycle-voter-{index}",
            vote_type=vote_type,
            created_at=1_000_000 + index,
        )


def _certified_submission(blockchain, submission_image, wallets, *, text_content="Protocol v1 lifecycle block"):
    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content=text_content,
        submitter=wallets["owner"].public_key,
    )
    _cast_majority_original_votes(blockchain, submission.submission_id)
    evaluation = blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=1_000_100,
    )
    assert evaluation["status"] == APPROVED
    certificate = blockchain.get_originality_certificate_for_submission(submission.submission_id)
    assert certificate is not None
    return submission, certificate


def _queued_certified_submission(blockchain, submission_image, wallets, *, text_content="Protocol v1 queued lifecycle block"):
    submission, certificate = _certified_submission(
        blockchain,
        submission_image,
        wallets,
        text_content=text_content,
    )
    blockchain.add_to_mint_queue(submission.submission_id)
    assert submission.status == QUEUED
    return submission, certificate


def _append_legacy_block(blockchain, submission_image, miner, *, text_content):
    assert blockchain.add_block(
        image_path=str(submission_image),
        text_content=text_content,
        miner=miner,
        validate_meme=False,
    ) is True
    return blockchain.get_latest_block()


def test_protocol_v1_lifecycle_happy_path_depth_confirms_without_quorum_finality(
    blockchain,
    submission_image,
    wallets,
):
    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Lifecycle happy path",
        submitter=wallets["owner"].public_key,
    )
    initial_lifecycle = blockchain.get_submission_protocol_v1_lifecycle(submission.submission_id)

    assert initial_lifecycle["submitted"] is True
    assert initial_lifecycle["voting"] is True
    assert initial_lifecycle["certified"] is False
    assert initial_lifecycle["mint_eligible"] is False
    assert initial_lifecycle["phase"] == "voting"

    _cast_majority_original_votes(blockchain, submission.submission_id)
    evaluation = blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=1_000_100,
    )
    assert evaluation["status"] == APPROVED

    certified_lifecycle = blockchain.get_submission_protocol_v1_lifecycle(submission.submission_id)
    assert certified_lifecycle["certified"] is True
    assert certified_lifecycle["mint_eligible"] is True
    assert certified_lifecycle["block_created"] is False
    assert certified_lifecycle["confirmations"] is None

    blockchain.add_to_mint_queue(submission.submission_id)
    certificate = blockchain.get_originality_certificate_for_submission(submission.submission_id)
    candidate = blockchain.build_block_candidate(
        image_path=submission.image_path,
        text_content=submission.text_content,
        miner=wallets["contributor_one"].public_key,
        validate_meme=False,
        certificate=certificate,
        reward_recipient=wallets["owner"].public_key,
    )

    assert candidate is not None
    assert len(blockchain.chain) == 1
    candidate_state = blockchain.get_block_chain_state(candidate["block"])
    assert candidate_state["accepted"] is False
    assert candidate_state["canonical"] is False
    assert candidate_state["confirmed"] is False
    assert candidate_state["finalized"] is False

    assert blockchain.accept_block_candidate(candidate) is True
    blockchain.reconcile_submission_canonical_state()
    assert submission.status == MINTED

    minted_lifecycle = blockchain.get_submission_protocol_v1_lifecycle(submission.submission_id)
    assert minted_lifecycle["block_created"] is True
    assert minted_lifecycle["block_accepted"] is True
    assert minted_lifecycle["canonical"] is True
    assert minted_lifecycle["confirmations"] == 0
    assert minted_lifecycle["confirmed"] is False
    assert minted_lifecycle["finalized"] is False
    assert minted_lifecycle["phase"] == "canonical"

    for index in range(PROTOCOL_V1_FINALITY_DEPTH):
        _append_legacy_block(
            blockchain,
            submission_image,
            wallets["contributor_two"].public_key,
            text_content=f"Lifecycle finality filler {index}",
        )

    depth_confirmed_lifecycle = blockchain.get_submission_protocol_v1_lifecycle(submission.submission_id)
    assert depth_confirmed_lifecycle["confirmations"] == PROTOCOL_V1_FINALITY_DEPTH
    assert depth_confirmed_lifecycle["confirmed"] is True
    assert depth_confirmed_lifecycle["finalized"] is False
    assert depth_confirmed_lifecycle["phase"] == "confirmed"
    assert depth_confirmed_lifecycle["confirmation_depth"] == PROTOCOL_V1_CONFIRMATION_DEPTH
    assert depth_confirmed_lifecycle["finality_depth"] == PROTOCOL_V1_FINALITY_DEPTH
    assert depth_confirmed_lifecycle["finality_model"] == "validator_quorum"
    assert depth_confirmed_lifecycle["finality_scope"] == "known_validator_set"


def test_invalid_protocol_v1_candidate_block_does_not_mutate_chain_or_rewards(
    blockchain,
    submission_image,
    wallets,
):
    submission, certificate = _queued_certified_submission(blockchain, submission_image, wallets)
    starting_chain_length = len(blockchain.chain)
    starting_reward_pool = blockchain.reward_pool

    candidate = blockchain.build_block_candidate(
        image_path=submission.image_path,
        text_content=submission.text_content,
        miner=wallets["contributor_one"].public_key,
        validate_meme=False,
        certificate=certificate,
        reward_recipient=wallets["owner"].public_key,
    )

    candidate["block"].content_hash = "0" * 64
    candidate["block"].hash = candidate["block"].calculate_hash()

    with pytest.raises(ValueError):
        blockchain.accept_block_candidate(candidate)

    assert len(blockchain.chain) == starting_chain_length
    assert blockchain.reward_pool == starting_reward_pool
    assert blockchain.get_reward_records_for_wallet(wallets["owner"].public_key) == []
    assert submission.status == QUEUED


@pytest.mark.parametrize("backend_factory", [_json_backend, _sqlite_backend])
def test_protocol_v1_duplicate_mint_after_restart_keeps_single_creator_reward(
    backend_factory,
    isolated_data_dir,
    submission_image,
):
    wallets = _wallets()
    backend = backend_factory(isolated_data_dir, "lifecycle-restart")
    blockchain = Blockchain(
        project_owner_wallet=wallets["owner"],
        Contributor_one=wallets["contributor_one"],
        Contributor_two=wallets["contributor_two"],
        storage_backend=backend,
    )
    submission, _certificate = _queued_certified_submission(blockchain, submission_image, wallets)

    assert blockchain.mint_submission(
        submission.submission_id,
        miner=wallets["contributor_one"].public_key,
        validate_meme=False,
    ) is True

    reloaded = Blockchain(storage_backend=backend)
    with pytest.raises(ValueError, match="already been minted"):
        reloaded.mint_submission(
            submission.submission_id,
            miner=wallets["contributor_one"].public_key,
            validate_meme=False,
        )

    reloaded_submission = reloaded.get_submission(submission.submission_id)
    creator_rewards = [
        reward
        for reward in reloaded.get_reward_records_for_wallet(wallets["owner"].public_key)
        if reward.get("reward_type") == "meme_mining_reward"
        and reward.get("submission_id") == submission.submission_id
    ]
    assert reloaded_submission.status == MINTED
    assert reloaded.get_protocol_v1_block_for_submission(submission.submission_id) is not None
    assert len(creator_rewards) == 1


def test_reconcile_submission_canonical_state_restores_mint_eligible_status_after_block_disappears(
    blockchain,
    submission_image,
    wallets,
):
    submission, _certificate = _queued_certified_submission(blockchain, submission_image, wallets)
    assert blockchain.mint_submission(
        submission.submission_id,
        miner=wallets["contributor_one"].public_key,
        validate_meme=False,
    ) is True
    assert submission.status == MINTED

    blockchain.chain = blockchain.chain[:1]
    blockchain.recompute_reward_pool_balance(chain=blockchain.chain)
    assert blockchain.reconcile_submission_canonical_state() is True

    restored_lifecycle = blockchain.get_submission_protocol_v1_lifecycle(submission.submission_id)
    assert submission.status == APPROVED
    assert restored_lifecycle["block_created"] is False
    assert restored_lifecycle["block_accepted"] is False
    assert restored_lifecycle["canonical"] is False
    assert restored_lifecycle["mint_eligible"] is True
    assert restored_lifecycle["phase"] == "mint-eligible"
