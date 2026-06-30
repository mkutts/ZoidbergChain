import pytest

from submission import APPROVED, HARD_REJECTED, QUEUED, VOTE_ORIGINAL


@pytest.fixture
def submission(blockchain, submission_image, wallets):
    return blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Hard rejection test",
        submitter=wallets["owner"].public_key,
    )


def test_hard_rejected_submissions_cannot_receive_votes(blockchain, submission, wallets):
    blockchain.hard_reject_submission(submission.submission_id, "Contains disallowed content.")

    with pytest.raises(ValueError, match="cannot receive votes"):
        blockchain.cast_submission_vote(
            submission.submission_id,
            wallets["contributor_one"].public_key,
            VOTE_ORIGINAL,
        )

    assert blockchain.votes == []


def test_hard_rejected_submissions_cannot_enter_mint_queue(blockchain, submission):
    submission.transition_to(APPROVED)
    blockchain.hard_reject_submission(submission.submission_id, "Automated policy failure.")

    with pytest.raises(ValueError, match="cannot enter the mint queue"):
        blockchain.add_to_mint_queue(submission.submission_id)

    assert blockchain.mint_queue == []


def test_hard_rejected_submissions_cannot_become_blocks(blockchain, submission, wallets, monkeypatch):
    submission.transition_to(APPROVED)
    submission.transition_to(QUEUED)
    blockchain.hard_reject_submission(submission.submission_id, "Late moderation failure.")
    blockchain.mint_queue.append(submission.submission_id)
    monkeypatch.setattr(blockchain, "add_block", lambda **kwargs: True)

    with pytest.raises(ValueError, match="cannot become blocks"):
        blockchain.mint_next_queued_submission(miner=wallets["contributor_one"].public_key)

    assert submission.status == HARD_REJECTED


def test_hard_reject_reason_storage(blockchain, submission):
    reason = "Known duplicate from moderation review."

    blockchain.hard_reject_submission(submission.submission_id, reason)

    assert submission.status == HARD_REJECTED
    assert submission.hard_reject_reason == reason
    assert submission.to_dict()["hard_reject_reason"] == reason


def test_normal_submissions_unaffected(blockchain, submission, wallets):
    blockchain.cast_submission_vote(
        submission.submission_id,
        wallets["contributor_one"].public_key,
        VOTE_ORIGINAL,
    )
    submission.transition_to(APPROVED)

    queued_submission = blockchain.add_to_mint_queue(submission.submission_id)

    assert len(blockchain.votes) == 1
    assert queued_submission.status == QUEUED
    assert blockchain.mint_queue == [submission.submission_id]
