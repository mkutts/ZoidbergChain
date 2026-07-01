import pytest

from originality_certificate import (
    OriginalityCertificate,
    calculate_vote_hash,
)
from submission import (
    APPROVED,
    HARD_REJECTED,
    MINTED,
    PENDING,
    QUEUED,
    REJECTED,
    VOTE_NOT_ORIGINAL,
    VOTE_ORIGINAL,
    VOTE_UNSURE,
)


APPROVED_AT = 1_000_500
NETWORK_NAME = "testnet-certificates"
ISSUING_NODE_ID = "node-certifier"


def _submission(blockchain, submission_image, submitter, text="Certificate meme"):
    return blockchain.submit_content(
        image_path=str(submission_image),
        text_content=text,
        submitter=submitter,
    )


def _cast_votes(blockchain, submission_id, vote_types):
    for index, vote_type in enumerate(vote_types):
        blockchain.cast_submission_vote(
            submission_id=submission_id,
            voter=f"certificate-voter-{index}",
            vote_type=vote_type,
            created_at=1_000_000 + index,
        )


def _approved_submission(blockchain, submission_image, wallets):
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    _cast_votes(
        blockchain,
        submission.submission_id,
        [
            VOTE_ORIGINAL,
            VOTE_ORIGINAL,
            VOTE_ORIGINAL,
            VOTE_ORIGINAL,
            VOTE_NOT_ORIGINAL,
            VOTE_UNSURE,
        ],
    )
    submission.transition_to(APPROVED)
    return submission


def _pending_submission_with_votes(blockchain, submission_image, wallets, vote_types):
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    _cast_votes(blockchain, submission.submission_id, vote_types)
    return submission


def test_approved_submission_automatically_creates_certificate(blockchain, submission_image, wallets):
    submission = _pending_submission_with_votes(
        blockchain,
        submission_image,
        wallets,
        [VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_NOT_ORIGINAL],
    )

    result = blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=APPROVED_AT,
    )

    certificate = blockchain.get_originality_certificate_for_submission(submission.submission_id)
    assert submission.status == APPROVED
    assert certificate is not None
    assert result["certificate_id"] == certificate.certificate_id
    assert certificate.vote_hash == calculate_vote_hash(
        blockchain.get_submission_votes(submission.submission_id)["votes"]
    )


def test_repeated_evaluation_does_not_create_duplicate_certificate(
    blockchain,
    submission_image,
    wallets,
):
    submission = _pending_submission_with_votes(
        blockchain,
        submission_image,
        wallets,
        [VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_NOT_ORIGINAL],
    )

    first_result = blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=APPROVED_AT,
    )
    second_result = blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=APPROVED_AT + 10,
    )

    assert first_result["status"] == APPROVED
    assert second_result["reason"] == "already_finalized"
    assert len(blockchain.originality_certificates) == 1


def test_rejected_submission_does_not_automatically_create_certificate(
    blockchain,
    submission_image,
    wallets,
):
    submission = _pending_submission_with_votes(
        blockchain,
        submission_image,
        wallets,
        [VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_NOT_ORIGINAL, VOTE_NOT_ORIGINAL, VOTE_NOT_ORIGINAL],
    )

    result = blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=APPROVED_AT,
    )

    assert result["status"] == REJECTED
    assert blockchain.get_originality_certificate_for_submission(submission.submission_id) is None
    assert blockchain.originality_certificates == []


def test_pending_submission_has_no_certificate(blockchain, submission_image, wallets):
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)

    assert submission.status == PENDING
    assert blockchain.get_originality_certificate_for_submission(submission.submission_id) is None


def test_hard_rejected_submission_does_not_automatically_create_certificate(
    blockchain,
    submission_image,
    wallets,
):
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    blockchain.hard_reject_submission(submission.submission_id, "Known duplicate.")

    result = blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=APPROVED_AT,
    )

    assert result["reason"] == "already_finalized"
    assert blockchain.get_originality_certificate_for_submission(submission.submission_id) is None
    assert blockchain.originality_certificates == []


def test_certificate_can_be_created_from_approved_submission(blockchain, submission_image, wallets):
    submission = _approved_submission(blockchain, submission_image, wallets)

    certificate = blockchain.create_originality_certificate(
        submission.submission_id,
        approved_at=APPROVED_AT,
        network_name=NETWORK_NAME,
        issuing_node_id=ISSUING_NODE_ID,
    )

    assert certificate in blockchain.originality_certificates
    assert certificate.submission_id == submission.submission_id
    assert certificate.content_hash == submission.content_hash
    assert certificate.creator_wallet == wallets["owner"].public_key
    assert certificate.vote_total == 6
    assert certificate.decisive_vote_total == 5
    assert certificate.original_votes == 4
    assert certificate.not_original_votes == 1
    assert certificate.unsure_votes == 1
    assert certificate.approval_percentage == 0.8
    assert certificate.minimum_votes_required == 5
    assert certificate.approved_at == APPROVED_AT
    assert certificate.network_name == NETWORK_NAME
    assert certificate.issuing_node_id == ISSUING_NODE_ID
    assert len(certificate.certificate_id) == 64
    assert len(certificate.vote_hash) == 64


def test_certificate_can_be_created_from_queued_submission(blockchain, submission_image, wallets):
    submission = _approved_submission(blockchain, submission_image, wallets)
    submission.transition_to(QUEUED)

    certificate = blockchain.create_originality_certificate(
        submission.submission_id,
        approved_at=APPROVED_AT,
        network_name=NETWORK_NAME,
        issuing_node_id=ISSUING_NODE_ID,
    )

    assert certificate.submission_id == submission.submission_id
    assert blockchain.originality_certificates == [certificate]


def test_certificate_cannot_be_created_from_pending_submission(blockchain, submission_image, wallets):
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)

    with pytest.raises(ValueError, match="Only approved unminted"):
        blockchain.create_originality_certificate(submission.submission_id)

    assert blockchain.originality_certificates == []


def test_certificate_cannot_be_created_from_rejected_submission(blockchain, submission_image, wallets):
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    submission.transition_to(REJECTED)

    with pytest.raises(ValueError, match="Only approved unminted"):
        blockchain.create_originality_certificate(submission.submission_id)

    assert blockchain.originality_certificates == []


def test_certificate_cannot_be_created_from_hard_rejected_submission(
    blockchain,
    submission_image,
    wallets,
):
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    blockchain.hard_reject_submission(submission.submission_id, "Known duplicate.")

    with pytest.raises(ValueError, match="Only approved unminted"):
        blockchain.create_originality_certificate(submission.submission_id)

    assert submission.status == HARD_REJECTED
    assert blockchain.originality_certificates == []


def test_certificate_cannot_be_created_from_minted_submission(blockchain, submission_image, wallets):
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    submission.transition_to(APPROVED)
    submission.transition_to(QUEUED)
    submission.transition_to(MINTED)

    with pytest.raises(ValueError, match="Only approved unminted"):
        blockchain.create_originality_certificate(submission.submission_id)

    assert blockchain.originality_certificates == []


def test_certificate_id_is_stable_and_deterministic(blockchain, submission_image, wallets):
    submission = _approved_submission(blockchain, submission_image, wallets)
    votes = blockchain.get_submission_votes(submission.submission_id)["votes"]

    first_certificate = OriginalityCertificate.from_approved_submission(
        submission=submission,
        votes=votes,
        minimum_votes_required=5,
        approved_at=APPROVED_AT,
        network_name=NETWORK_NAME,
        issuing_node_id=ISSUING_NODE_ID,
    )
    second_certificate = OriginalityCertificate.from_approved_submission(
        submission=submission,
        votes=list(reversed(votes)),
        minimum_votes_required=5,
        approved_at=APPROVED_AT + 100,
        network_name=NETWORK_NAME,
        issuing_node_id=ISSUING_NODE_ID,
    )

    assert first_certificate.certificate_id == second_certificate.certificate_id
    assert first_certificate.vote_hash == second_certificate.vote_hash


def test_vote_hash_changes_if_vote_set_changes(blockchain, submission_image, wallets):
    submission = _approved_submission(blockchain, submission_image, wallets)
    votes = blockchain.get_submission_votes(submission.submission_id)["votes"]

    changed_votes = votes + [
        {
            "voter": "late-voter",
            "submission_id": submission.submission_id,
            "vote_type": VOTE_NOT_ORIGINAL,
            "created_at": 1_000_999,
        }
    ]

    assert calculate_vote_hash(votes) != calculate_vote_hash(changed_votes)


def test_certificate_persists_and_reloads(blockchain, submission_image, wallets):
    from blockchain import Blockchain

    submission = _approved_submission(blockchain, submission_image, wallets)
    certificate = blockchain.create_originality_certificate(
        submission.submission_id,
        approved_at=APPROVED_AT,
        network_name=NETWORK_NAME,
        issuing_node_id=ISSUING_NODE_ID,
    )

    reloaded_blockchain = Blockchain()
    reloaded_certificate = reloaded_blockchain.get_originality_certificate(certificate.certificate_id)

    assert len(reloaded_blockchain.originality_certificates) == 1
    assert reloaded_certificate is not None
    assert reloaded_certificate.to_dict() == certificate.to_dict()


def test_certificate_vote_hash_remains_stable_after_rejected_late_vote_attempt(
    blockchain,
    submission_image,
    wallets,
):
    submission = _pending_submission_with_votes(
        blockchain,
        submission_image,
        wallets,
        [VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_NOT_ORIGINAL],
    )
    blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=APPROVED_AT,
    )
    certificate = blockchain.get_originality_certificate_for_submission(submission.submission_id)
    original_certificate = certificate.to_dict()

    with pytest.raises(ValueError, match="cannot receive votes"):
        blockchain.cast_submission_vote(
            submission.submission_id,
            voter="late-voter",
            vote_type=VOTE_NOT_ORIGINAL,
            created_at=APPROVED_AT + 1,
        )

    assert blockchain.get_originality_certificate(certificate.certificate_id).to_dict() == original_certificate
    assert len(blockchain.get_submission_votes(submission.submission_id)["votes"]) == 5
