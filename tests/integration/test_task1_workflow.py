import pytest

from submission import (
    APPROVED,
    HARD_REJECTED,
    MINTED,
    QUEUED,
    VOTE_NOT_ORIGINAL,
    VOTE_ORIGINAL,
)
from wallet import Wallet


def test_successful_task1_workflow(blockchain, submission_image, wallets):
    new_wallet = Wallet()
    assert new_wallet.public_key
    assert blockchain.add_wallet(new_wallet) is True
    assert new_wallet.public_key in blockchain.wallets

    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Task 1 integration meme",
        submitter=new_wallet.public_key,
    )
    submission.created_at = 1_000_000

    vote_types = [
        VOTE_ORIGINAL,
        VOTE_ORIGINAL,
        VOTE_ORIGINAL,
        VOTE_ORIGINAL,
        VOTE_NOT_ORIGINAL,
    ]
    voters = [
        wallets["owner"].public_key,
        wallets["contributor_one"].public_key,
        wallets["contributor_two"].public_key,
        wallets["recipient"].public_key,
        Wallet().public_key,
    ]
    for voter, vote_type in zip(voters, vote_types):
        blockchain.cast_submission_vote(
            submission_id=submission.submission_id,
            voter=voter,
            vote_type=vote_type,
            created_at=1_000_000,
        )

    approval_result = blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=1_000_000,
    )
    assert approval_result["status"] == APPROVED
    assert submission.status == APPROVED

    queued_submission = blockchain.add_to_mint_queue(submission.submission_id)
    assert queued_submission.status == QUEUED
    assert blockchain.get_mint_queue()[0]["submission_id"] == submission.submission_id

    starting_chain_length = len(blockchain.chain)

    assert blockchain.mint_next_queued_submission(miner=wallets["owner"].public_key) is True
    assert submission.status == MINTED
    assert blockchain.mint_queue == []
    assert len(blockchain.chain) == starting_chain_length + 1
    assert blockchain.get_latest_block().meme["text"] == submission.text_content


def test_failed_task1_workflow_hard_rejection(blockchain, submission_image):
    creator_wallet = Wallet()
    voter_wallet = Wallet()

    blockchain.add_wallet(creator_wallet)
    blockchain.add_wallet(voter_wallet)

    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Task 1 hard rejection meme",
        submitter=creator_wallet.public_key,
    )

    blockchain.hard_reject_submission(
        submission.submission_id,
        "Moderator confirmed prohibited duplicate.",
    )

    assert submission.status == HARD_REJECTED
    assert submission.hard_reject_reason == "Moderator confirmed prohibited duplicate."

    with pytest.raises(ValueError, match="cannot receive votes"):
        blockchain.cast_submission_vote(
            submission_id=submission.submission_id,
            voter=voter_wallet.public_key,
            vote_type=VOTE_ORIGINAL,
        )

    with pytest.raises(ValueError, match="cannot enter the mint queue"):
        blockchain.add_to_mint_queue(submission.submission_id)

    blockchain.mint_queue.append(submission.submission_id)
    with pytest.raises(ValueError, match="cannot become blocks"):
        blockchain.mint_next_queued_submission(miner=voter_wallet.public_key)
