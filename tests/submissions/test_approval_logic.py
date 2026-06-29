from config import VOTING_WINDOW_HOURS
from submission import APPROVED, PENDING, REJECTED, VOTE_NOT_ORIGINAL, VOTE_ORIGINAL, VOTE_UNSURE


SECONDS_PER_HOUR = 60 * 60


def create_submission(blockchain, submission_image, submitter, created_at=1_000_000):
    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Approval logic test",
        submitter=submitter,
    )
    submission.created_at = created_at
    return submission


def cast_votes(blockchain, submission_id, vote_types, created_at=1_000_000):
    for index, vote_type in enumerate(vote_types):
        blockchain.cast_submission_vote(
            submission_id=submission_id,
            voter=f"voter-{index}",
            vote_type=vote_type,
            created_at=created_at,
        )


def test_submission_approval(blockchain, submission_image, wallets):
    now = 1_000_000
    submission = create_submission(blockchain, submission_image, wallets["owner"].public_key, now)
    cast_votes(
        blockchain,
        submission.submission_id,
        [VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_NOT_ORIGINAL],
        now,
    )

    result = blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=now,
    )

    assert submission.status == APPROVED
    assert result["status"] == APPROVED
    assert result["reason"] == "approved_by_vote"


def test_submission_rejection_when_final_vote_below_threshold(blockchain, submission_image, wallets):
    now = 1_000_000
    submission = create_submission(blockchain, submission_image, wallets["owner"].public_key, now)
    cast_votes(
        blockchain,
        submission.submission_id,
        [VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_NOT_ORIGINAL, VOTE_NOT_ORIGINAL],
        now,
    )

    result = blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=now,
    )

    assert submission.status == REJECTED
    assert result["status"] == REJECTED
    assert result["reason"] == "rejected_by_vote"


def test_unsure_votes_do_not_hurt_approval(blockchain, submission_image, wallets):
    now = 1_000_000
    submission = create_submission(blockchain, submission_image, wallets["owner"].public_key, now)
    cast_votes(
        blockchain,
        submission.submission_id,
        [VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_UNSURE],
        now,
    )

    result = blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=now,
    )

    assert submission.status == APPROVED
    assert result["approval_percentage"] == 1


def test_submission_remains_pending_before_threshold_or_window(blockchain, submission_image, wallets):
    now = 1_000_000
    submission = create_submission(blockchain, submission_image, wallets["owner"].public_key, now)
    cast_votes(
        blockchain,
        submission.submission_id,
        [VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL],
        now,
    )

    result = blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=now,
    )

    assert submission.status == PENDING
    assert result["status"] == PENDING
    assert result["reason"] == "awaiting_votes_or_window"


def test_automated_originality_rejection_is_hard_rejection(blockchain, submission_image, wallets):
    now = 1_000_000
    submission = create_submission(blockchain, submission_image, wallets["owner"].public_key, now)

    result = blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=False,
        now=now,
    )

    assert submission.status == REJECTED
    assert result["status"] == REJECTED
    assert result["reason"] == "automated_originality_rejected"


def test_voting_window_finalizes_submission(blockchain, submission_image, wallets):
    created_at = 1_000_000
    now = created_at + (VOTING_WINDOW_HOURS * SECONDS_PER_HOUR) + 1
    submission = create_submission(blockchain, submission_image, wallets["owner"].public_key, created_at)
    cast_votes(blockchain, submission.submission_id, [VOTE_ORIGINAL], now)

    result = blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=now,
    )

    assert submission.status == APPROVED
    assert result["status"] == APPROVED
    assert result["voting_window_expired"] is True
    assert result["minimum_votes_reached"] is False
