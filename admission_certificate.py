"""Frozen Public Testnet v1 media admission evidence.

The certificate contains the evidence needed by a peer; its identity excludes
local observation times, paths, database ordering, and later review votes.
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from dataclasses import dataclass

from dual_review import (ADMISSIBILITY, ORIGINALITY, REVIEW_POLICY_VERSION, REVIEW_VOTE_VERSION,
                         combined_review, review_policy_digest, verify_vote_record)
from milestone5_policy import MIN_VALID_VOTES
from media_admission_policy import MEDIA_ADMISSION_POLICY_ID, MEDIA_ADMISSION_POLICY_VERSION, media_admission_policy_digest
from media_technical_validation import TECHNICAL_VALIDATION_EVIDENCE_VERSION, technical_evidence_identity, validate_technical_evidence
from protocol_v1 import PUBLIC_TESTNET_V1_NETWORK_ID, canonical_hash
from protocol_v1_submitter_attestation import SUBMITTER_ATTESTATION_VERSION, validate_submitter_attestation


ADMISSION_CERTIFICATE_VERSION = 1


@dataclass(frozen=True)
class AdmissionMintCertificateView:
    """Read-only adapter for the existing atomic mint coordinator."""

    admission_certificate: dict

    def to_dict(self):
        return deepcopy(self.admission_certificate)

    def is_milestone5_certificate(self):
        return False

    @property
    def certificate_id(self):
        return self.admission_certificate["certificate_digest"]

    @property
    def submission_id(self):
        return self.admission_certificate["submission_id"]

    @property
    def content_hash(self):
        return self.admission_certificate["content_hash"]

    @property
    def content_id(self):
        from content import calculate_content_id
        return calculate_content_id(self.content_hash)

    @property
    def creator_wallet(self):
        return self.admission_certificate["creator_wallet"]

    @property
    def vote_hash(self):
        return self.admission_certificate["originality"]["vote_set_digest"]

    @property
    def approval_percentage(self):
        tally = self.admission_certificate["originality"]
        return tally["positive_votes"] / tally["approval_denominator"]

    @property
    def decisive_vote_total(self):
        return self.admission_certificate["originality"]["approval_denominator"]

    @property
    def minimum_votes_required(self):
        return MIN_VALID_VOTES

    @property
    def approved_at(self):
        return 0  # No local clock enters the immutable admission decision.

    @property
    def originality_score(self):
        return self.approval_percentage
_VOTE_FIELDS = (
    "submission_id", "content_hash", "voter", "voter_wallet_address",
    "vote_type", "dimension", "vote_version", "protocol_version", "network_id",
    "signature_scheme", "vote_signature", "vote_message", "vote_nonce",
    "signed_message_hash", "vote_issued_at", "vote_expires_at", "vote_identity",
    "reviewer_policy_version", "reputation_rule_version", "reviewer_status",
    "reviewer_eligible", "reviewer_status_effective_height",
    "reviewer_status_reference_block_hash",
)
_ATTESTATION_FIELDS = (
    "attestation_version", "statement_id", "statement_version", "domain",
    "protocol_version", "network_id", "signature_scheme", "signer_wallet",
    "signature", "nonce", "canonical_payload", "canonical_payload_digest",
    "canonical_message", "canonical_message_hash",
)


def _frozen_votes(votes):
    frozen = [{key: deepcopy(vote[key]) for key in _VOTE_FIELDS if key in vote}
              for vote in votes if vote.get("vote_version") == REVIEW_VOTE_VERSION
              and vote.get("dimension") in {ORIGINALITY, ADMISSIBILITY}]
    for vote in frozen:
        wallet = str(vote.get("voter_wallet_address") or vote.get("voter") or "").lower()
        vote["voter"] = wallet
        vote["voter_wallet_address"] = wallet
        signature = vote.get("vote_signature")
        if isinstance(signature, str):
            vote["vote_signature"] = "0x" + signature.lower().removeprefix("0x")
        reference_hash = vote.get("reviewer_status_reference_block_hash")
        if isinstance(reference_hash, str):
            vote["reviewer_status_reference_block_hash"] = reference_hash.lower()
    frozen.sort(key=lambda vote: (str(vote.get("dimension")), str(vote.get("voter_wallet_address") or vote.get("voter")).lower(),
                                  str(vote.get("vote_identity"))))
    unique = {}
    for vote in frozen:
        key = (vote.get("dimension"), vote.get("voter_wallet_address"))
        existing = unique.get(key)
        if existing is not None and existing != vote:
            raise ValueError("Conflicting review votes cannot be frozen.")
        unique[key] = vote
    return list(unique.values())


def attestation_identity(record):
    if not isinstance(record, dict) or any(field not in record for field in _ATTESTATION_FIELDS):
        raise ValueError("Admission submitter attestation is incomplete.")
    result = {field: deepcopy(record[field]) for field in _ATTESTATION_FIELDS}
    result["signer_wallet"] = str(result["signer_wallet"]).lower()
    if isinstance(result["signature"], str):
        result["signature"] = "0x" + result["signature"].lower().removeprefix("0x")
    return result


def build_admission_certificate(*, submission_id, content_hash, creator_wallet,
                                media_bytes, technical_evidence, attestation, votes,
                                reviewer_status_resolver):
    frozen_votes = _frozen_votes(votes)
    review = combined_review(frozen_votes)
    body = {
        "certificate_version": ADMISSION_CERTIFICATE_VERSION,
        "network_id": PUBLIC_TESTNET_V1_NETWORK_ID,
        "submission_id": submission_id,
        "content_hash": content_hash,
        "creator_wallet": creator_wallet.lower(),
        "policy_id": MEDIA_ADMISSION_POLICY_ID,
        "policy_version": MEDIA_ADMISSION_POLICY_VERSION,
        "policy_digest": media_admission_policy_digest(),
        "technical_evidence_version": TECHNICAL_VALIDATION_EVIDENCE_VERSION,
        "technical_evidence": technical_evidence_identity(technical_evidence),
        "attestation_version": SUBMITTER_ATTESTATION_VERSION,
        "attestation": attestation_identity(attestation),
        "review_policy_version": REVIEW_POLICY_VERSION,
        "review_policy_digest": review_policy_digest(),
        "votes": frozen_votes,
    }
    body["originality"] = review["originality"]
    body["admissibility"] = review["admissibility"]
    certificate = dict(body, certificate_digest=canonical_hash(body))
    validate_admission_certificate(certificate, media_bytes=media_bytes,
                                   reviewer_status_resolver=reviewer_status_resolver)
    return certificate


def validate_admission_certificate(certificate, *, media_bytes, reviewer_status_resolver):
    if not isinstance(certificate, dict):
        raise ValueError("Admission certificate is missing.")
    expected_keys = {"certificate_version", "network_id", "submission_id", "content_hash",
                     "creator_wallet", "policy_id", "policy_version", "policy_digest",
                     "technical_evidence_version", "technical_evidence", "attestation_version",
                     "attestation", "review_policy_version", "review_policy_digest", "votes",
                     "originality", "admissibility", "certificate_digest"}
    if set(certificate) != expected_keys:
        raise ValueError("Admission certificate schema is invalid.")
    if certificate["certificate_version"] != ADMISSION_CERTIFICATE_VERSION:
        raise ValueError("Unknown admission certificate version.")
    if certificate["network_id"] != PUBLIC_TESTNET_V1_NETWORK_ID:
        raise ValueError("Admission certificate network is invalid.")
    if (certificate["policy_id"] != MEDIA_ADMISSION_POLICY_ID
        or certificate["policy_version"] != MEDIA_ADMISSION_POLICY_VERSION
        or certificate["policy_digest"] != media_admission_policy_digest()
        or certificate["review_policy_version"] != REVIEW_POLICY_VERSION
        or certificate["review_policy_digest"] != review_policy_digest()
        or certificate["technical_evidence_version"] != TECHNICAL_VALIDATION_EVIDENCE_VERSION
        or certificate["attestation_version"] != SUBMITTER_ATTESTATION_VERSION):
        raise ValueError("Admission certificate policy or evidence version is invalid.")
    body = {key: value for key, value in certificate.items() if key != "certificate_digest"}
    if certificate["certificate_digest"] != canonical_hash(body):
        raise ValueError("Admission certificate digest is invalid.")
    raw = bytes(media_bytes)
    if hashlib.sha256(raw).hexdigest() != certificate["content_hash"]:
        raise ValueError("Admission certificate media hash is invalid.")
    evidence = validate_technical_evidence(certificate["technical_evidence"], raw)
    if certificate["technical_evidence"] != technical_evidence_identity(certificate["technical_evidence"]):
        raise ValueError("Admission technical evidence contains local observations.")
    if evidence["evidence_digest"] != certificate["technical_evidence"]["evidence_digest"]:
        raise ValueError("Admission technical evidence is invalid.")
    attestation = dict(certificate["attestation"], verified_at="1970-01-01T00:00:00Z")
    if certificate["attestation"] != attestation_identity(certificate["attestation"]):
        raise ValueError("Admission attestation identity is not canonical.")
    validate_submitter_attestation(
        attestation, expected_wallet_address=certificate["creator_wallet"],
        expected_submission_id=certificate["submission_id"],
        expected_raw_media_sha256=certificate["content_hash"],
        expected_technical_evidence=evidence, raw_media_bytes=raw,
        expected_network_id=certificate["network_id"],
    )
    votes = certificate["votes"]
    if not isinstance(votes, list) or votes != _frozen_votes(votes):
        raise ValueError("Admission vote set is not canonical.")
    if any(set(vote) != set(_VOTE_FIELDS) for vote in votes):
        raise ValueError("Admission vote evidence is incomplete.")
    if not all(verify_vote_record(
        vote, submission_id=certificate["submission_id"],
        content_hash=certificate["content_hash"], network_id=certificate["network_id"],
        creator_address=certificate["creator_wallet"], reviewer_status_resolver=reviewer_status_resolver,
    ) for vote in votes):
        raise ValueError("Admission vote signature or reviewer snapshot is invalid.")
    review = combined_review(votes)
    if (review["originality"] != certificate["originality"]
        or review["admissibility"] != certificate["admissibility"]
        or not review["review_qualified"]):
        raise ValueError("Admission review evidence does not qualify.")
    return certificate
