import pytest

from submission import VOTE_NOT_ORIGINAL, VOTE_ORIGINAL, VOTE_UNSURE


@pytest.fixture
def submission(blockchain, submission_image, wallets):
    return blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Community vote test",
        submitter=wallets["owner"].public_key,
    )


def test_duplicate_votes_fail(blockchain, submission, wallets):
    voter = wallets["contributor_one"].public_key

    blockchain.cast_submission_vote(submission.submission_id, voter, VOTE_ORIGINAL)

    with pytest.raises(ValueError, match="already voted"):
        blockchain.cast_submission_vote(submission.submission_id, voter, VOTE_NOT_ORIGINAL)


def test_matching_duplicate_vote_cannot_be_recast(blockchain, submission, wallets):
    voter = wallets["contributor_one"].public_key

    blockchain.cast_submission_vote(submission.submission_id, voter, VOTE_ORIGINAL)

    with pytest.raises(ValueError, match="already voted"):
        blockchain.cast_submission_vote(submission.submission_id, voter, VOTE_ORIGINAL)


def test_creator_cannot_vote(blockchain, submission, wallets):
    with pytest.raises(ValueError, match="creator cannot vote"):
        blockchain.cast_submission_vote(
            submission.submission_id,
            wallets["owner"].public_key,
            VOTE_ORIGINAL,
        )


def test_invalid_vote_types_fail(blockchain, submission, wallets):
    with pytest.raises(ValueError, match="Invalid vote type"):
        blockchain.cast_submission_vote(
            submission.submission_id,
            wallets["contributor_one"].public_key,
            "maybe",
        )


def test_unsure_votes_do_not_count_toward_approval_percentage(blockchain, submission, wallets):
    blockchain.cast_submission_vote(
        submission.submission_id,
        wallets["contributor_one"].public_key,
        VOTE_UNSURE,
    )
    blockchain.cast_submission_vote(
        submission.submission_id,
        wallets["contributor_two"].public_key,
        VOTE_ORIGINAL,
    )

    vote_summary = blockchain.get_submission_votes(submission.submission_id)

    assert vote_summary["counts"] == {
        VOTE_ORIGINAL: 1,
        VOTE_NOT_ORIGINAL: 0,
        VOTE_UNSURE: 1,
    }
    assert vote_summary["approval_percentage"] == 1


def test_vote_storage(blockchain, submission, wallets):
    vote = blockchain.cast_submission_vote(
        submission.submission_id,
        wallets["contributor_one"].public_key,
        VOTE_NOT_ORIGINAL,
        created_at=1_000_000,
    )

    assert vote in blockchain.votes
    assert vote == {
        "voter": wallets["contributor_one"].public_key,
        "submission_id": submission.submission_id,
        "vote_type": VOTE_NOT_ORIGINAL,
        "created_at": 1_000_000,
    }

    vote_summary = blockchain.get_submission_votes(submission.submission_id)
    assert vote_summary["votes"] == [vote]


def test_no_votes_allowed_after_approval(blockchain, submission, wallets):
    submission.transition_to("approved")

    with pytest.raises(ValueError, match="cannot receive votes"):
        blockchain.cast_submission_vote(
            submission.submission_id,
            wallets["contributor_one"].public_key,
            VOTE_ORIGINAL,
        )


def test_no_votes_allowed_after_certificate_exists(blockchain, submission, wallets):
    blockchain.cast_submission_vote(
        submission.submission_id,
        wallets["contributor_one"].public_key,
        VOTE_ORIGINAL,
    )
    submission.transition_to("approved")
    blockchain.create_originality_certificate(submission.submission_id, approved_at=1_000_000)
    submission.status = "pending"

    with pytest.raises(ValueError, match="cannot receive votes"):
        blockchain.cast_submission_vote(
            submission.submission_id,
            wallets["contributor_two"].public_key,
            VOTE_NOT_ORIGINAL,
        )
