import pytest

from submission import APPROVED, MINTED, PENDING, QUEUED, Submission


def _certify_submission(blockchain, submission):
    for vote_index in range(5):
        blockchain.cast_submission_vote(
            submission_id=submission.submission_id,
            voter=f"mint-voter-{submission.submission_id}-{vote_index}",
            vote_type="original",
            created_at=1_000_000 + vote_index,
        )
    submission.transition_to(APPROVED)
    blockchain.create_originality_certificate(submission.submission_id, approved_at=1_000_100)


@pytest.fixture
def approved_submissions(blockchain, submission_image, wallets):
    submissions = []
    for index in range(3):
        submission = blockchain.submit_content(
            image_path=str(submission_image),
            text_content=f"Mint queue content {index}",
            submitter=wallets["owner"].public_key,
        )
        _certify_submission(blockchain, submission)
        submissions.append(submission)
    return submissions


def test_mint_queue_insertion(blockchain, approved_submissions):
    submission = approved_submissions[0]

    queued_submission = blockchain.add_to_mint_queue(submission.submission_id)

    assert queued_submission.status == QUEUED
    assert blockchain.mint_queue == [submission.submission_id]


def test_mint_queue_ordering(blockchain, approved_submissions):
    for submission in approved_submissions:
        blockchain.add_to_mint_queue(submission.submission_id)

    assert blockchain.mint_queue == [submission.submission_id for submission in approved_submissions]
    assert [submission["submission_id"] for submission in blockchain.get_mint_queue()] == blockchain.mint_queue


def test_mint_removal_and_status_update(blockchain, approved_submissions, wallets, monkeypatch):
    first, second, _ = approved_submissions
    blockchain.add_to_mint_queue(first.submission_id)
    blockchain.add_to_mint_queue(second.submission_id)
    monkeypatch.setattr(blockchain, "add_block", lambda **kwargs: True)

    result = blockchain.mint_next_queued_submission(miner=wallets["contributor_one"].public_key)

    assert result is True
    assert first.status == MINTED
    assert blockchain.mint_queue == [second.submission_id]
    assert second.status == QUEUED


def test_mint_submission_requires_front_of_queue(blockchain, approved_submissions, wallets, monkeypatch):
    first, second, _ = approved_submissions
    blockchain.add_to_mint_queue(first.submission_id)
    blockchain.add_to_mint_queue(second.submission_id)
    monkeypatch.setattr(blockchain, "add_block", lambda **kwargs: True)

    with pytest.raises(ValueError, match="front of the mint queue"):
        blockchain.mint_submission(second.submission_id, miner=wallets["contributor_one"].public_key)

    assert blockchain.mint_queue == [first.submission_id, second.submission_id]
    assert first.status == QUEUED
    assert second.status == QUEUED


def test_invalid_mint_queue_entries(blockchain, approved_submissions):
    approved, minted, _ = approved_submissions
    minted.transition_to(QUEUED)
    minted.transition_to(MINTED)
    blockchain.add_to_mint_queue(approved.submission_id)
    blockchain.mint_queue.append(minted.submission_id)
    blockchain.mint_queue.append("missing-submission")

    removed = blockchain.remove_invalid_mint_queue_entries()

    assert removed == [minted.submission_id, "missing-submission"]
    assert blockchain.mint_queue == [approved.submission_id]


def test_legacy_submission_without_content_id_can_still_be_minted(blockchain, submission_image, wallets, monkeypatch):
    submission = Submission.from_dict(
        {
            "submission_id": "legacy-mint-submission",
            "image_path": str(submission_image),
            "text_content": "Legacy mint meme",
            "submitter": wallets["owner"].public_key,
            "status": PENDING,
            "created_at": 1_000_000,
        }
    )
    blockchain.submissions.append(submission)
    _certify_submission(blockchain, submission)
    blockchain.add_to_mint_queue(submission.submission_id)
    monkeypatch.setattr(blockchain, "add_block", lambda **kwargs: True)

    result = blockchain.mint_next_queued_submission(miner=wallets["contributor_one"].public_key)

    assert result is True
    assert submission.content_id is not None
    assert submission.status == MINTED
