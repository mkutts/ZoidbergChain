import json

import pytest

from submission import APPROVED, MINTED, PENDING, QUEUED, REJECTED, Submission


def test_new_submissions_begin_pending(blockchain, submission_image, wallets):
    starting_chain_length = len(blockchain.chain)

    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Why not pending?",
        submitter=wallets["owner"].public_key,
    )

    assert submission.status == PENDING
    assert blockchain.submissions == [submission]
    assert len(blockchain.chain) == starting_chain_length


def test_valid_state_transitions(blockchain, submission_image, wallets):
    approved_submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Approved content",
        submitter=wallets["owner"].public_key,
    )
    rejected_submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Rejected content",
        submitter=wallets["owner"].public_key,
    )

    blockchain.update_submission_status(approved_submission.submission_id, APPROVED)
    blockchain.update_submission_status(approved_submission.submission_id, QUEUED)
    blockchain.update_submission_status(approved_submission.submission_id, MINTED)
    blockchain.update_submission_status(rejected_submission.submission_id, REJECTED)

    assert approved_submission.status == MINTED
    assert rejected_submission.status == REJECTED


@pytest.mark.parametrize(
    ("current_status", "next_status"),
    [
        (PENDING, MINTED),
        (APPROVED, REJECTED),
        (APPROVED, MINTED),
        (QUEUED, APPROVED),
        (QUEUED, REJECTED),
        (REJECTED, APPROVED),
        (MINTED, APPROVED),
    ],
)
def test_invalid_state_transitions_fail(current_status, next_status):
    submission = Submission(
        image_path="meme.jpg",
        text_content="Invalid transition",
        submitter="submitter",
        status=current_status,
    )

    with pytest.raises(ValueError):
        submission.transition_to(next_status)

    assert submission.status == current_status


def test_existing_submission_dicts_without_status_remain_compatible():
    submission = Submission.from_dict(
        {
            "submission_id": "legacy-submission",
            "image_path": "legacy.jpg",
            "text_content": "Legacy content",
            "submitter": "legacy-submitter",
        }
    )

    assert submission.submission_id == "legacy-submission"
    assert submission.status == PENDING
    assert submission.content_id is not None


def test_existing_blockchain_files_without_submissions_remain_compatible(isolated_data_dir):
    from blockchain import Blockchain

    (isolated_data_dir / "blockchain.json").write_text(
        json.dumps({"chain": [], "wallets": {}}),
        encoding="utf-8",
    )

    blockchain = Blockchain()

    assert blockchain.submissions == []
    assert len(blockchain.chain) == 1
