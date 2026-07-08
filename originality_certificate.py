import hashlib
import json
import math
import time
from dataclasses import dataclass, field

from config import (
    APPROVAL_PERCENTAGE_WEIGHT,
    BASE_ORIGINALITY_SCORE,
    DECISIVE_VOTE_WEIGHT,
    NETWORK_NAME,
    ORIGINALITY_APPROVAL_THRESHOLD,
    UNSURE_VOTE_WEIGHT,
)
from submission import APPROVED, MINTED, QUEUED, VOTE_NOT_ORIGINAL, VOTE_ORIGINAL, VOTE_UNSURE


def _canonical_json(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _canonical_vote(vote):
    return {
        "created_at": vote.get("created_at"),
        "submission_id": vote.get("submission_id"),
        "vote_type": vote.get("vote_type"),
        "voter": vote.get("voter"),
    }


def calculate_vote_hash(votes):
    canonical_votes = sorted(
        (_canonical_vote(vote) for vote in votes),
        key=lambda vote: (
            str(vote.get("submission_id")),
            str(vote.get("voter")),
            str(vote.get("vote_type")),
            str(vote.get("created_at")),
        ),
    )
    return hashlib.sha256(_canonical_json(canonical_votes).encode("utf-8")).hexdigest()


def calculate_certificate_id(certificate_fields):
    core_fields = {
        "approval_percentage": certificate_fields["approval_percentage"],
        "content_hash": certificate_fields["content_hash"],
        "creator_wallet": certificate_fields["creator_wallet"],
        "decisive_vote_total": certificate_fields["decisive_vote_total"],
        "issuing_node_id": certificate_fields["issuing_node_id"],
        "minimum_votes_required": certificate_fields["minimum_votes_required"],
        "network_name": certificate_fields["network_name"],
        "not_original_votes": certificate_fields["not_original_votes"],
        "original_votes": certificate_fields["original_votes"],
        "submission_id": certificate_fields["submission_id"],
        "unsure_votes": certificate_fields["unsure_votes"],
        "vote_hash": certificate_fields["vote_hash"],
        "vote_total": certificate_fields["vote_total"],
    }
    return hashlib.sha256(_canonical_json(core_fields).encode("utf-8")).hexdigest()


def calculate_originality_score(certificate):
    score = (
        BASE_ORIGINALITY_SCORE
        + (certificate.decisive_vote_total * DECISIVE_VOTE_WEIGHT)
        + (certificate.approval_percentage * APPROVAL_PERCENTAGE_WEIGHT)
        + (certificate.unsure_votes * UNSURE_VOTE_WEIGHT)
    )
    return round(score, 8)


def validate_certificate_for_submission(
    certificate,
    submission,
    network_name=NETWORK_NAME,
    approval_threshold=ORIGINALITY_APPROVAL_THRESHOLD,
    allowed_submission_statuses=None,
):
    if certificate is None:
        raise ValueError("Originality certificate is required before minting.")
    if submission is None:
        raise ValueError("Submission is required to validate an originality certificate.")
    if certificate.submission_id != submission.submission_id:
        raise ValueError("Originality certificate submission_id does not match submission.")
    if certificate.content_hash != submission.content_hash:
        raise ValueError("Originality certificate content_hash does not match submission.")
    if certificate.content_id is not None and certificate.content_id != submission.content_id:
        raise ValueError("Originality certificate content_id does not match submission.")
    if certificate.creator_wallet != submission.submitter:
        raise ValueError("Originality certificate creator_wallet does not match submission.")
    if certificate.network_name != network_name:
        raise ValueError("Originality certificate belongs to a different network.")
    if not certificate.vote_hash:
        raise ValueError("Originality certificate vote_hash is required.")
    valid_statuses = (
        {APPROVED, QUEUED, MINTED}
        if allowed_submission_statuses is None
        else set(allowed_submission_statuses)
    )
    if submission.status not in valid_statuses:
        raise ValueError("Originality certificate must reference an approved submission.")
    if certificate.approval_percentage < approval_threshold:
        raise ValueError("Originality certificate approval percentage is below the required threshold.")
    if certificate.originality_score is None:
        raise ValueError("Originality certificate originality_score is required.")
    if certificate.originality_score != calculate_originality_score(certificate):
        raise ValueError("Originality certificate originality_score is inconsistent.")

    vote_counts = [
        certificate.original_votes,
        certificate.not_original_votes,
        certificate.unsure_votes,
        certificate.vote_total,
        certificate.decisive_vote_total,
        certificate.minimum_votes_required,
    ]
    if any(not isinstance(count, int) or count < 0 for count in vote_counts):
        raise ValueError("Originality certificate vote totals must be non-negative integers.")
    if certificate.vote_total != (
        certificate.original_votes
        + certificate.not_original_votes
        + certificate.unsure_votes
    ):
        raise ValueError("Originality certificate vote_total is inconsistent.")
    if certificate.decisive_vote_total != certificate.original_votes + certificate.not_original_votes:
        raise ValueError("Originality certificate decisive_vote_total is inconsistent.")
    if certificate.decisive_vote_total <= 0:
        raise ValueError("Originality certificate must include decisive votes.")
    expected_approval = certificate.original_votes / certificate.decisive_vote_total
    if not math.isclose(certificate.approval_percentage, expected_approval):
        raise ValueError("Originality certificate approval percentage is inconsistent.")
    if certificate.certificate_id != calculate_certificate_id(certificate.to_core_dict()):
        raise ValueError("Originality certificate_id does not match certificate contents.")

    return True


@dataclass
class OriginalityCertificate:
    submission_id: str
    content_hash: str
    creator_wallet: str
    vote_total: int
    decisive_vote_total: int
    original_votes: int
    not_original_votes: int
    unsure_votes: int
    approval_percentage: float
    minimum_votes_required: int
    approved_at: float
    network_name: str
    issuing_node_id: str
    vote_hash: str
    content_id: str | None = None
    originality_score: float | None = None
    certificate_id: str = field(default="")

    def __post_init__(self):
        if self.originality_score is None:
            self.originality_score = calculate_originality_score(self)
        if not self.certificate_id:
            self.certificate_id = calculate_certificate_id(self.to_core_dict())

    @classmethod
    def from_approved_submission(
        cls,
        submission,
        votes,
        minimum_votes_required,
        network_name,
        issuing_node_id,
        approved_at=None,
    ):
        original_votes = sum(1 for vote in votes if vote.get("vote_type") == VOTE_ORIGINAL)
        not_original_votes = sum(1 for vote in votes if vote.get("vote_type") == VOTE_NOT_ORIGINAL)
        unsure_votes = sum(1 for vote in votes if vote.get("vote_type") == VOTE_UNSURE)
        decisive_vote_total = original_votes + not_original_votes
        approval_percentage = original_votes / decisive_vote_total if decisive_vote_total else 0

        return cls(
            submission_id=submission.submission_id,
            content_hash=submission.content_hash,
            content_id=submission.content_id,
            creator_wallet=submission.submitter,
            vote_total=len(votes),
            decisive_vote_total=decisive_vote_total,
            original_votes=original_votes,
            not_original_votes=not_original_votes,
            unsure_votes=unsure_votes,
            approval_percentage=approval_percentage,
            minimum_votes_required=minimum_votes_required,
            approved_at=approved_at if approved_at is not None else time.time(),
            network_name=network_name,
            issuing_node_id=issuing_node_id,
            vote_hash=calculate_vote_hash(votes),
        )

    def to_core_dict(self):
        return {
            "submission_id": self.submission_id,
            "content_hash": self.content_hash,
            "creator_wallet": self.creator_wallet,
            "vote_total": self.vote_total,
            "decisive_vote_total": self.decisive_vote_total,
            "original_votes": self.original_votes,
            "not_original_votes": self.not_original_votes,
            "unsure_votes": self.unsure_votes,
            "approval_percentage": self.approval_percentage,
            "minimum_votes_required": self.minimum_votes_required,
            "network_name": self.network_name,
            "issuing_node_id": self.issuing_node_id,
            "vote_hash": self.vote_hash,
        }

    def to_dict(self):
        return {
            "certificate_id": self.certificate_id,
            "submission_id": self.submission_id,
            "content_hash": self.content_hash,
            "content_id": self.content_id,
            "creator_wallet": self.creator_wallet,
            "vote_total": self.vote_total,
            "decisive_vote_total": self.decisive_vote_total,
            "original_votes": self.original_votes,
            "not_original_votes": self.not_original_votes,
            "unsure_votes": self.unsure_votes,
            "approval_percentage": self.approval_percentage,
            "minimum_votes_required": self.minimum_votes_required,
            "approved_at": self.approved_at,
            "network_name": self.network_name,
            "issuing_node_id": self.issuing_node_id,
            "vote_hash": self.vote_hash,
            "originality_score": self.originality_score,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            certificate_id=data.get("certificate_id", ""),
            submission_id=data["submission_id"],
            content_hash=data["content_hash"],
            content_id=data.get("content_id"),
            creator_wallet=data["creator_wallet"],
            vote_total=data["vote_total"],
            decisive_vote_total=data["decisive_vote_total"],
            original_votes=data["original_votes"],
            not_original_votes=data["not_original_votes"],
            unsure_votes=data["unsure_votes"],
            approval_percentage=data["approval_percentage"],
            minimum_votes_required=data["minimum_votes_required"],
            approved_at=data["approved_at"],
            network_name=data["network_name"],
            issuing_node_id=data["issuing_node_id"],
            vote_hash=data["vote_hash"],
            originality_score=data.get("originality_score"),
        )
