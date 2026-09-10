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
from protocol_v1 import PROTOCOL_VERSION, canonical_hash
from milestone5_policy import (
    APPROVAL_THRESHOLD_BPS,
    MIN_ESTABLISHED_VOTES,
    MIN_VALID_VOTES,
    REVIEWER_POLICY_VERSION,
    REPUTATION_RULE_VERSION,
)
from protocol_v1_originality import (
    MILESTONE5_CERTIFICATE_VERSION,
    MILESTONE5_CERTIFICATE_V3_VERSION,
    PROTOCOL_V1_CERTIFICATE_VERSION,
    build_milestone5_certificate_identity_payload,
    build_milestone5_certificate_identity_payload_v3,
    build_protocol_v1_certificate_identity_payload,
    build_protocol_v1_vote_set_payload,
    calculate_milestone5_certificate_id,
    calculate_milestone5_certificate_id_v3,
    calculate_milestone5_vote_hash_v3,
    calculate_protocol_v1_certificate_id,
    calculate_protocol_v1_vote_hash,
    calculate_signed_vote_identity,
    build_protocol_v1_vote_message,
    resolve_protocol_v1_network_id,
)
from originality import HARD_REJECT, revalidate_certificate_originality_evidence
from submission import APPROVED, MINTED, QUEUED, VOTE_NOT_ORIGINAL, VOTE_ORIGINAL, VOTE_UNSURE
from wallet_auth import hash_wallet_message, normalize_wallet_address, recover_signed_wallet_address


def validate_certificate_v3_vote_record(
    vote,
    *,
    submission_id,
    content_hash,
    creator_address,
    network_id,
    reviewer_status_resolver,
):
    """Independently validate one signed, policy-bound counted v3 vote."""
    if not isinstance(vote, dict):
        raise ValueError("Certificate-v3 counted votes must be objects.")
    voter = normalize_wallet_address(vote.get("voter_wallet_address") or vote.get("voter"))
    creator = normalize_wallet_address(creator_address)
    if voter is None or creator is None:
        raise ValueError("Certificate-v3 votes require canonical Ethereum wallet identities.")
    if voter == creator:
        raise ValueError("Submission creator cannot contribute a certificate-v3 vote.")
    if str(vote.get("submission_id") or "").strip() != submission_id:
        raise ValueError("Certificate-v3 vote submission_id does not match the certificate.")
    if str(vote.get("content_hash") or "").strip().lower() != content_hash:
        raise ValueError("Certificate-v3 vote content_hash does not match the certificate.")
    if vote.get("reviewer_policy_version") != REVIEWER_POLICY_VERSION:
        raise ValueError("Certificate-v3 vote reviewer_policy_version is unsupported.")
    if vote.get("reputation_rule_version") != REPUTATION_RULE_VERSION:
        raise ValueError("Certificate-v3 vote reputation_rule_version is unsupported.")
    if vote.get("reviewer_eligible") is not True:
        raise ValueError("Certificate-v3 vote is not marked canonically eligible.")
    height = vote.get("reviewer_status_effective_height")
    reference_hash = str(vote.get("reviewer_status_reference_block_hash") or "").strip().lower()
    if isinstance(height, bool) or not isinstance(height, int) or height < 0:
        raise ValueError("Certificate-v3 vote reviewer reference height is invalid.")
    if len(reference_hash) != 64 or any(ch not in "0123456789abcdef" for ch in reference_hash):
        raise ValueError("Certificate-v3 vote reviewer reference hash is invalid.")
    derived_status = reviewer_status_resolver(voter, height, reference_hash)
    if derived_status not in {"PROBATIONARY_REVIEWER", "ESTABLISHED_REVIEWER"}:
        raise ValueError("Certificate-v3 vote reviewer was not eligible at its finalized reference.")
    if vote.get("reviewer_status") != derived_status:
        raise ValueError("Certificate-v3 vote reviewer status does not match canonical state.")
    expected_message = build_protocol_v1_vote_message(
        wallet_address=voter,
        submission_id=submission_id,
        content_hash=content_hash,
        vote_type=vote.get("vote_type", vote.get("vote_value")),
        nonce=vote.get("vote_nonce"),
        issued_at=vote.get("vote_issued_at"),
        expires_at=vote.get("vote_expires_at"),
        network_id=network_id,
    )
    if vote.get("vote_version") != 1 or vote.get("protocol_version") != PROTOCOL_VERSION:
        raise ValueError("Certificate-v3 votes require signed Protocol v1 vote fields.")
    if vote.get("network_id") != network_id or vote.get("signature_scheme") != "personal_sign":
        raise ValueError("Certificate-v3 vote network or signature scheme is invalid.")
    if vote.get("vote_message") != expected_message:
        raise ValueError("Certificate-v3 vote signed message is inconsistent.")
    if recover_signed_wallet_address(expected_message, vote.get("vote_signature")) != voter:
        raise ValueError("Certificate-v3 vote signature does not match voter.")
    if vote.get("signed_message_hash") not in {None, hash_wallet_message(expected_message)}:
        raise ValueError("Certificate-v3 vote signed_message_hash is inconsistent.")
    identity = calculate_signed_vote_identity(
        wallet_address=voter,
        submission_id=submission_id,
        content_hash=content_hash,
        vote_type=vote.get("vote_type", vote.get("vote_value")),
        nonce=vote.get("vote_nonce"),
        issued_at=vote.get("vote_issued_at"),
        expires_at=vote.get("vote_expires_at"),
        network_id=network_id,
        signature=vote.get("vote_signature"),
        signature_scheme=vote.get("signature_scheme"),
    )
    if vote.get("vote_identity") != identity:
        raise ValueError("Certificate-v3 vote identity is inconsistent.")
    return vote


def _canonical_json(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _canonical_vote_legacy(vote):
    return {
        "created_at": vote.get("created_at"),
        "submission_id": vote.get("submission_id"),
        "vote_type": vote.get("vote_type"),
        "voter": vote.get("voter"),
    }


def calculate_vote_hash_legacy(votes):
    canonical_votes = sorted(
        (_canonical_vote_legacy(vote) for vote in votes),
        key=lambda vote: (
            str(vote.get("submission_id")),
            str(vote.get("voter")),
            str(vote.get("vote_type")),
            str(vote.get("created_at")),
        ),
    )
    return hashlib.sha256(_canonical_json(canonical_votes).encode("utf-8")).hexdigest()


def calculate_vote_hash(
    votes,
    *,
    vote_set_version=None,
    submission_id=None,
    content_hash=None,
    network_id=None,
    network_name=None,
):
    if vote_set_version is None:
        return calculate_vote_hash_legacy(votes)
    if vote_set_version not in {
        PROTOCOL_V1_CERTIFICATE_VERSION,
        MILESTONE5_CERTIFICATE_VERSION,
        MILESTONE5_CERTIFICATE_V3_VERSION,
    }:
        raise ValueError(f"Unsupported vote_set_version: {vote_set_version}")
    if submission_id is None:
        raise ValueError("submission_id is required for Protocol v1 vote hashing.")
    if content_hash is None:
        raise ValueError("content_hash is required for Protocol v1 vote hashing.")
    resolved_network_id = resolve_protocol_v1_network_id(
        network_id=network_id,
        network_name=network_name or NETWORK_NAME,
    )
    if vote_set_version == MILESTONE5_CERTIFICATE_V3_VERSION:
        return calculate_milestone5_vote_hash_v3(
            votes,
            submission_id=submission_id,
            content_hash=content_hash,
            network_id=resolved_network_id,
        )
    return calculate_protocol_v1_vote_hash(
        votes,
        submission_id=submission_id,
        content_hash=content_hash,
        network_id=resolved_network_id,
    )


def build_vote_hash_payload_v1(
    votes,
    *,
    submission_id,
    content_hash,
):
    return build_protocol_v1_vote_set_payload(
        votes,
        submission_id=submission_id,
        content_hash=content_hash,
    )


def calculate_certificate_id_legacy(certificate_fields):
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


def calculate_certificate_id(
    certificate_fields,
    *,
    certificate_version=None,
    network_id=None,
    network_name=None,
):
    version = certificate_version
    if version is None and isinstance(certificate_fields, dict):
        version = certificate_fields.get("certificate_version")
    if version is None:
        return calculate_certificate_id_legacy(certificate_fields)
    if version == MILESTONE5_CERTIFICATE_VERSION:
        resolved_network_id = resolve_protocol_v1_network_id(
            network_id=network_id or certificate_fields.get("network_id"),
            network_name=network_name or certificate_fields.get("network_name") or NETWORK_NAME,
        )
        return calculate_milestone5_certificate_id(
            certificate_fields, network_id=resolved_network_id
        )
    if version == MILESTONE5_CERTIFICATE_V3_VERSION:
        resolved_network_id = resolve_protocol_v1_network_id(
            network_id=network_id or certificate_fields.get("network_id"),
            network_name=network_name or certificate_fields.get("network_name") or NETWORK_NAME,
        )
        return calculate_milestone5_certificate_id_v3(
            certificate_fields, network_id=resolved_network_id
        )
    if version != PROTOCOL_V1_CERTIFICATE_VERSION:
        raise ValueError(f"Unsupported certificate_version: {version}")
    resolved_network_id = resolve_protocol_v1_network_id(
        network_id=network_id or certificate_fields.get("network_id"),
        network_name=network_name or certificate_fields.get("network_name") or NETWORK_NAME,
    )
    return calculate_protocol_v1_certificate_id(
        certificate_fields,
        network_id=resolved_network_id,
    )


def build_certificate_identity_payload_v1(certificate_fields):
    return build_protocol_v1_certificate_identity_payload(certificate_fields)


def build_certificate_identity_payload_v2(certificate_fields):
    return build_milestone5_certificate_identity_payload(certificate_fields)


def build_certificate_identity_payload_v3(certificate_fields):
    return build_milestone5_certificate_identity_payload_v3(certificate_fields)


def calculate_originality_score(certificate):
    score = (
        BASE_ORIGINALITY_SCORE
        + (certificate.decisive_vote_total * DECISIVE_VOTE_WEIGHT)
        + (certificate.approval_percentage * APPROVAL_PERCENTAGE_WEIGHT)
        + (certificate.unsure_votes * UNSURE_VOTE_WEIGHT)
    )
    return round(score, 8)


def is_protocol_v1_certificate_record(value) -> bool:
    if isinstance(value, OriginalityCertificate):
        return value.is_versioned_certificate()
    return isinstance(value, dict) and value.get("certificate_version") in {
        PROTOCOL_V1_CERTIFICATE_VERSION,
        MILESTONE5_CERTIFICATE_VERSION,
        MILESTONE5_CERTIFICATE_V3_VERSION,
    }


def validate_certificate_for_submission(
    certificate,
    submission,
    network_name=NETWORK_NAME,
    approval_threshold=ORIGINALITY_APPROVAL_THRESHOLD,
    allowed_submission_statuses=None,
    network_id=None,
    originality_evidence=None,
    chain=None,
    media_bytes=None,
    mime_type=None,
    votes=None,
    reviewer_snapshot=None,
    reviewer_status_resolver=None,
    finalized_reference_validator=None,
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

    if certificate.is_versioned_certificate():
        expected_network_id = resolve_protocol_v1_network_id(
            network_id=network_id,
            network_name=network_name or certificate.network_name,
        )
        if certificate.certificate_version not in {
            PROTOCOL_V1_CERTIFICATE_VERSION,
            MILESTONE5_CERTIFICATE_VERSION,
            MILESTONE5_CERTIFICATE_V3_VERSION,
        }:
            raise ValueError("Originality certificate version is unsupported.")
        if certificate.protocol_version != PROTOCOL_VERSION:
            raise ValueError("Originality certificate protocol_version is unsupported.")
        if certificate.network_id != expected_network_id:
            raise ValueError("Originality certificate belongs to a different network.")
        if not certificate.is_certificate_v3() and not math.isclose(float(certificate.approval_threshold), float(approval_threshold)):
            raise ValueError("Originality certificate approval threshold is inconsistent.")
    elif certificate.network_name != network_name:
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
    if not certificate.is_certificate_v3() and certificate.approval_percentage < approval_threshold:
        raise ValueError("Originality certificate approval percentage is below the required threshold.")
    if not certificate.is_certificate_v3():
        if certificate.originality_score is None:
            raise ValueError("Originality certificate originality_score is required.")
        if certificate.originality_score != calculate_originality_score(certificate):
            raise ValueError("Originality certificate originality_score is inconsistent.")

    if certificate.is_milestone5_certificate():
        if certificate.evidence_binding_status != "active":
            raise ValueError("Originality certificate evidence binding is not active.")
        if certificate.creator_address != certificate.creator_wallet:
            raise ValueError("Originality certificate creator_address is inconsistent.")
        if certificate.vote_set_hash != certificate.vote_hash:
            raise ValueError("Originality certificate vote_set_hash is inconsistent.")
        if certificate.total_valid_votes != certificate.vote_total:
            raise ValueError("Originality certificate total_valid_votes is inconsistent.")
        if certificate.minimum_valid_votes != certificate.minimum_votes_required:
            raise ValueError("Originality certificate minimum_valid_votes is inconsistent.")
        expected_bps = (
            APPROVAL_THRESHOLD_BPS
            if certificate.is_certificate_v3()
            else int(round(float(approval_threshold) * 10_000))
        )
        if certificate.approval_threshold_bps != expected_bps:
            raise ValueError("Originality certificate approval_threshold_bps is inconsistent.")
        if certificate.is_certificate_v2():
            reviewer_reserved = (
                certificate.reviewer_policy_version,
                certificate.reputation_rule_version,
                certificate.reviewer_snapshot_reference_height,
                certificate.reviewer_snapshot_reference_block_hash,
                certificate.reviewer_snapshot_digest,
                certificate.minimum_established_votes,
                certificate.established_vote_count,
            )
            if any(value is not None for value in reviewer_reserved):
                raise ValueError("Reserved reviewer-policy certificate fields must be null in version 2.")
        if originality_evidence is None:
            raise ValueError("Originality evidence is required to validate certificate version 2.")
        if chain is None:
            raise ValueError("Canonical chain state is required to validate certificate version 2.")
        evidence = revalidate_certificate_originality_evidence(
            originality_evidence,
            submission_id=submission.submission_id,
            content_hash=submission.content_hash,
            chain=chain,
            media_bytes=media_bytes,
            mime_type=mime_type or "application/octet-stream",
        )
        if evidence["final_prevote_decision"] == HARD_REJECT:
            raise ValueError("Hard-rejected originality evidence cannot be certified.")
        bindings = {
            "originality_rule_version": evidence["originality_rule_version"],
            "originality_decision": evidence["final_prevote_decision"],
            "originality_reference_height": evidence["originality_reference_height"],
            "originality_reference_block_hash": evidence["originality_reference_block_hash"],
            "originality_evidence_digest": evidence["canonical_evidence_digest"],
        }
        for field_name, expected in bindings.items():
            if getattr(certificate, field_name) != expected:
                raise ValueError(f"Originality certificate {field_name} does not match evidence.")
        height = certificate.certificate_reference_height
        if isinstance(height, bool) or not isinstance(height, int) or height < 0 or height >= len(chain):
            raise ValueError("Originality certificate reference height is not canonical.")
        reference_block = chain[height]
        block_hash = reference_block.get("hash") if isinstance(reference_block, dict) else reference_block.hash
        if str(block_hash).lower() != certificate.certificate_reference_block_hash:
            raise ValueError("Originality certificate reference block is not canonical.")

        if certificate.is_certificate_v3():
            if certificate.reviewer_policy_version != REVIEWER_POLICY_VERSION:
                raise ValueError("Certificate-v3 reviewer_policy_version is unsupported.")
            if certificate.reputation_rule_version != REPUTATION_RULE_VERSION:
                raise ValueError("Certificate-v3 reputation_rule_version is unsupported.")
            if certificate.minimum_valid_votes != MIN_VALID_VOTES or certificate.minimum_votes_required != MIN_VALID_VOTES:
                raise ValueError("Certificate-v3 minimum valid-vote quorum is inconsistent.")
            if certificate.minimum_established_votes != MIN_ESTABLISHED_VOTES:
                raise ValueError("Certificate-v3 minimum established-reviewer quorum is inconsistent.")
            if certificate.approval_threshold_bps != APPROVAL_THRESHOLD_BPS:
                raise ValueError("Certificate-v3 approval threshold is inconsistent.")
            if certificate.total_valid_votes != certificate.vote_total:
                raise ValueError("Certificate-v3 total_valid_votes is inconsistent.")
            if certificate.total_valid_votes < MIN_VALID_VOTES:
                raise ValueError("Certificate-v3 has insufficient total valid votes.")
            decisive = certificate.original_votes + certificate.not_original_votes
            if decisive <= 0 or certificate.original_votes * 10_000 < decisive * APPROVAL_THRESHOLD_BPS:
                raise ValueError("Certificate-v3 does not satisfy the integer approval threshold.")
            if (
                reviewer_snapshot is None
                or reviewer_status_resolver is None
                or finalized_reference_validator is None
            ):
                raise ValueError("Certificate-v3 reviewer snapshot validation context is required.")
            snapshot_payload = {
                "reviewer_policy_version": reviewer_snapshot.get("reviewer_policy_version"),
                "reputation_rule_version": reviewer_snapshot.get("reputation_rule_version"),
                "reference_finalized_height": reviewer_snapshot.get("reference_finalized_height"),
                "reference_finalized_block_hash": reviewer_snapshot.get("reference_finalized_block_hash"),
                "review_epoch": reviewer_snapshot.get("review_epoch"),
                "reviewers": reviewer_snapshot.get("reviewers"),
            }
            if canonical_hash(snapshot_payload) != certificate.reviewer_snapshot_digest:
                raise ValueError("Certificate-v3 reviewer snapshot digest is inconsistent.")
            if reviewer_snapshot.get("reviewer_snapshot_digest") != certificate.reviewer_snapshot_digest:
                raise ValueError("Certificate-v3 reviewer snapshot assertion is inconsistent.")
            if snapshot_payload["reviewer_policy_version"] != REVIEWER_POLICY_VERSION or snapshot_payload["reputation_rule_version"] != REPUTATION_RULE_VERSION:
                raise ValueError("Certificate-v3 reviewer snapshot policy versions are inconsistent.")
            if snapshot_payload["reference_finalized_height"] != certificate.reviewer_snapshot_reference_height or snapshot_payload["reference_finalized_block_hash"] != certificate.reviewer_snapshot_reference_block_hash:
                raise ValueError("Certificate-v3 reviewer snapshot reference is inconsistent.")
            if not finalized_reference_validator(
                certificate.reviewer_snapshot_reference_height,
                certificate.reviewer_snapshot_reference_block_hash,
            ):
                raise ValueError("Certificate-v3 reviewer snapshot reference is not finalized and canonical.")
            if not finalized_reference_validator(
                certificate.certificate_reference_height,
                certificate.certificate_reference_block_hash,
            ):
                raise ValueError("Certificate-v3 certificate reference is not finalized and canonical.")
            counted_votes = list(votes or [])
            if len(counted_votes) != certificate.total_valid_votes:
                raise ValueError("Certificate-v3 counted vote set is incomplete.")
            snapshot_entries = snapshot_payload["reviewers"]
            if not isinstance(snapshot_entries, list):
                raise ValueError("Certificate-v3 reviewer snapshot reviewers must be a list.")
            snapshot_statuses = {}
            canonical_addresses = []
            for item in snapshot_entries:
                if not isinstance(item, dict):
                    raise ValueError("Certificate-v3 reviewer snapshot entries must be objects.")
                address = normalize_wallet_address(item.get("address"))
                if address is None or address != item.get("address"):
                    raise ValueError("Certificate-v3 reviewer snapshot address is not canonical.")
                if address in snapshot_statuses:
                    raise ValueError("Certificate-v3 reviewer snapshot contains a duplicate reviewer.")
                asserted_status = item.get("status")
                derived_status = reviewer_status_resolver(
                    address,
                    certificate.reviewer_snapshot_reference_height,
                    certificate.reviewer_snapshot_reference_block_hash,
                )
                if asserted_status != derived_status:
                    raise ValueError("Certificate-v3 reviewer snapshot status is not locally reproducible.")
                snapshot_statuses[address] = asserted_status
                canonical_addresses.append(address)
            if canonical_addresses != sorted(canonical_addresses):
                raise ValueError("Certificate-v3 reviewer snapshot order is not canonical.")
            seen = set()
            for vote in counted_votes:
                validate_certificate_v3_vote_record(
                    vote,
                    submission_id=certificate.submission_id,
                    content_hash=certificate.content_hash,
                    creator_address=certificate.creator_address,
                    network_id=certificate.network_id,
                    reviewer_status_resolver=reviewer_status_resolver,
                )
                voter = normalize_wallet_address(vote.get("voter_wallet_address") or vote.get("voter"))
                if voter in seen:
                    raise ValueError("Certificate-v3 counted vote set contains duplicate voters.")
                seen.add(voter)
                if snapshot_statuses.get(voter) not in {"PROBATIONARY_REVIEWER", "ESTABLISHED_REVIEWER"}:
                    raise ValueError("Certificate-v3 counted voter is ineligible in the bound reviewer snapshot.")
            if set(snapshot_statuses) != seen:
                raise ValueError("Certificate-v3 reviewer snapshot does not match the counted voter set.")
            established = sum(status == "ESTABLISHED_REVIEWER" for status in snapshot_statuses.values())
            if certificate.established_vote_count != established:
                raise ValueError("Certificate-v3 established vote count is inconsistent.")
            if established < MIN_ESTABLISHED_VOTES:
                raise ValueError("Certificate-v3 has insufficient established-reviewer votes.")
            expected_vote_hash = calculate_vote_hash(
                counted_votes,
                vote_set_version=MILESTONE5_CERTIFICATE_V3_VERSION,
                submission_id=certificate.submission_id,
                content_hash=certificate.content_hash,
                network_id=certificate.network_id,
            )
            if certificate.vote_hash != expected_vote_hash or certificate.vote_set_hash != expected_vote_hash:
                raise ValueError("Certificate-v3 vote-set hash is inconsistent.")

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
    if not certificate.is_certificate_v3():
        expected_approval = certificate.original_votes / certificate.decisive_vote_total
        if not math.isclose(certificate.approval_percentage, expected_approval):
            raise ValueError("Originality certificate approval percentage is inconsistent.")
    expected_certificate_id = calculate_certificate_id(
        certificate.to_core_dict(),
        certificate_version=certificate.certificate_version,
        network_id=certificate.network_id,
        network_name=certificate.network_name,
    )
    if certificate.certificate_id != expected_certificate_id:
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
    certificate_version: int | None = None
    network_id: str | None = None
    protocol_version: int | None = None
    approval_threshold: float | None = None
    creator_address: str | None = None
    originality_rule_version: int | None = None
    originality_decision: str | None = None
    originality_reference_height: int | None = None
    originality_reference_block_hash: str | None = None
    originality_evidence_digest: str | None = None
    reviewer_policy_version: int | None = None
    reputation_rule_version: int | None = None
    reviewer_snapshot_reference_height: int | None = None
    reviewer_snapshot_reference_block_hash: str | None = None
    reviewer_snapshot_digest: str | None = None
    minimum_valid_votes: int | None = None
    minimum_established_votes: int | None = None
    approval_threshold_bps: int | None = None
    total_valid_votes: int | None = None
    established_vote_count: int | None = None
    vote_set_hash: str | None = None
    certificate_reference_height: int | None = None
    certificate_reference_block_hash: str | None = None
    issued_timestamp: str | None = None
    evidence_binding_status: str = "active"

    def __post_init__(self):
        if self.approval_threshold is None:
            self.approval_threshold = ORIGINALITY_APPROVAL_THRESHOLD
        if self.is_versioned_certificate():
            self.protocol_version = PROTOCOL_VERSION if self.protocol_version is None else self.protocol_version
            if self.protocol_version != PROTOCOL_VERSION:
                raise ValueError("Protocol v1 originality certificates must use protocol_version=1.")
            self.network_id = resolve_protocol_v1_network_id(
                network_id=self.network_id,
                network_name=self.network_name,
            )
        if self.is_milestone5_certificate():
            self.creator_address = self.creator_wallet if self.creator_address is None else self.creator_address
            self.vote_set_hash = self.vote_hash if self.vote_set_hash is None else self.vote_set_hash
            self.total_valid_votes = self.vote_total if self.total_valid_votes is None else self.total_valid_votes
            self.minimum_valid_votes = (
                self.minimum_votes_required
                if self.minimum_valid_votes is None
                else self.minimum_valid_votes
            )
            self.approval_threshold_bps = (
                int(round(float(self.approval_threshold) * 10_000))
                if self.approval_threshold_bps is None
                else self.approval_threshold_bps
            )
        if self.originality_score is None:
            self.originality_score = calculate_originality_score(self)
        if not self.certificate_id:
            self.certificate_id = calculate_certificate_id(
                self.to_core_dict(),
                certificate_version=self.certificate_version,
                network_id=self.network_id,
                network_name=self.network_name,
            )

    def is_protocol_v1_certificate(self) -> bool:
        return self.certificate_version == PROTOCOL_V1_CERTIFICATE_VERSION

    def is_milestone5_certificate(self) -> bool:
        return self.certificate_version in {
            MILESTONE5_CERTIFICATE_VERSION,
            MILESTONE5_CERTIFICATE_V3_VERSION,
        }

    def is_certificate_v2(self) -> bool:
        return self.certificate_version == MILESTONE5_CERTIFICATE_VERSION

    def is_certificate_v3(self) -> bool:
        return self.certificate_version == MILESTONE5_CERTIFICATE_V3_VERSION

    def is_versioned_certificate(self) -> bool:
        return self.certificate_version in {
            PROTOCOL_V1_CERTIFICATE_VERSION,
            MILESTONE5_CERTIFICATE_VERSION,
            MILESTONE5_CERTIFICATE_V3_VERSION,
        }

    @classmethod
    def from_approved_submission(
        cls,
        submission,
        votes,
        minimum_votes_required,
        network_name,
        issuing_node_id,
        approved_at=None,
        certificate_version=PROTOCOL_V1_CERTIFICATE_VERSION,
        originality_evidence=None,
        reviewer_snapshot=None,
        established_vote_count=None,
        certificate_reference_height=None,
        certificate_reference_block_hash=None,
        issued_timestamp=None,
    ):
        original_votes = sum(1 for vote in votes if vote.get("vote_type") == VOTE_ORIGINAL)
        not_original_votes = sum(1 for vote in votes if vote.get("vote_type") == VOTE_NOT_ORIGINAL)
        unsure_votes = sum(1 for vote in votes if vote.get("vote_type") == VOTE_UNSURE)
        decisive_vote_total = original_votes + not_original_votes
        approval_percentage = original_votes / decisive_vote_total if decisive_vote_total else 0
        resolved_approved_at = approved_at if approved_at is not None else time.time()
        resolved_network_id = (
            resolve_protocol_v1_network_id(network_name=network_name)
            if certificate_version in {PROTOCOL_V1_CERTIFICATE_VERSION, MILESTONE5_CERTIFICATE_VERSION, MILESTONE5_CERTIFICATE_V3_VERSION}
            else None
        )
        vote_hash = calculate_vote_hash(
            votes,
            vote_set_version=certificate_version,
            submission_id=submission.submission_id,
            content_hash=submission.content_hash,
            network_id=resolved_network_id,
            network_name=network_name,
        )

        return cls(
            certificate_version=certificate_version,
            protocol_version=(
                PROTOCOL_VERSION
                if certificate_version in {PROTOCOL_V1_CERTIFICATE_VERSION, MILESTONE5_CERTIFICATE_VERSION, MILESTONE5_CERTIFICATE_V3_VERSION}
                else None
            ),
            network_id=resolved_network_id,
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
            approved_at=resolved_approved_at,
            network_name=network_name,
            issuing_node_id=issuing_node_id,
            vote_hash=vote_hash,
            approval_threshold=ORIGINALITY_APPROVAL_THRESHOLD,
            creator_address=(submission.submitter if certificate_version in {MILESTONE5_CERTIFICATE_VERSION, MILESTONE5_CERTIFICATE_V3_VERSION} else None),
            originality_rule_version=(originality_evidence or {}).get("originality_rule_version"),
            originality_decision=(originality_evidence or {}).get("final_prevote_decision"),
            originality_reference_height=(originality_evidence or {}).get("originality_reference_height"),
            originality_reference_block_hash=(originality_evidence or {}).get("originality_reference_block_hash"),
            originality_evidence_digest=(originality_evidence or {}).get("canonical_evidence_digest"),
            reviewer_policy_version=(REVIEWER_POLICY_VERSION if certificate_version == MILESTONE5_CERTIFICATE_V3_VERSION else None),
            reputation_rule_version=(REPUTATION_RULE_VERSION if certificate_version == MILESTONE5_CERTIFICATE_V3_VERSION else None),
            reviewer_snapshot_reference_height=((reviewer_snapshot or {}).get("reference_finalized_height") if certificate_version == MILESTONE5_CERTIFICATE_V3_VERSION else None),
            reviewer_snapshot_reference_block_hash=((reviewer_snapshot or {}).get("reference_finalized_block_hash") if certificate_version == MILESTONE5_CERTIFICATE_V3_VERSION else None),
            reviewer_snapshot_digest=((reviewer_snapshot or {}).get("reviewer_snapshot_digest") if certificate_version == MILESTONE5_CERTIFICATE_V3_VERSION else None),
            minimum_valid_votes=(MIN_VALID_VOTES if certificate_version == MILESTONE5_CERTIFICATE_V3_VERSION else minimum_votes_required if certificate_version == MILESTONE5_CERTIFICATE_VERSION else None),
            minimum_established_votes=(MIN_ESTABLISHED_VOTES if certificate_version == MILESTONE5_CERTIFICATE_V3_VERSION else None),
            approval_threshold_bps=(APPROVAL_THRESHOLD_BPS if certificate_version == MILESTONE5_CERTIFICATE_V3_VERSION else int(round(ORIGINALITY_APPROVAL_THRESHOLD * 10_000)) if certificate_version == MILESTONE5_CERTIFICATE_VERSION else None),
            total_valid_votes=(len(votes) if certificate_version in {MILESTONE5_CERTIFICATE_VERSION, MILESTONE5_CERTIFICATE_V3_VERSION} else None),
            established_vote_count=(established_vote_count if certificate_version == MILESTONE5_CERTIFICATE_V3_VERSION else None),
            vote_set_hash=(vote_hash if certificate_version in {MILESTONE5_CERTIFICATE_VERSION, MILESTONE5_CERTIFICATE_V3_VERSION} else None),
            certificate_reference_height=certificate_reference_height,
            certificate_reference_block_hash=certificate_reference_block_hash,
            issued_timestamp=issued_timestamp,
        )

    def to_core_dict(self):
        if self.is_certificate_v3():
            return build_certificate_identity_payload_v3({
                "certificate_version": self.certificate_version,
                "protocol_version": self.protocol_version,
                "network_id": self.network_id,
                "submission_id": self.submission_id,
                "content_hash": self.content_hash,
                "creator_address": self.creator_address,
                "originality_rule_version": self.originality_rule_version,
                "originality_decision": self.originality_decision,
                "originality_reference_height": self.originality_reference_height,
                "originality_reference_block_hash": self.originality_reference_block_hash,
                "originality_evidence_digest": self.originality_evidence_digest,
                "reviewer_policy_version": self.reviewer_policy_version,
                "reputation_rule_version": self.reputation_rule_version,
                "reviewer_snapshot_reference_height": self.reviewer_snapshot_reference_height,
                "reviewer_snapshot_reference_block_hash": self.reviewer_snapshot_reference_block_hash,
                "reviewer_snapshot_digest": self.reviewer_snapshot_digest,
                "minimum_valid_votes": self.minimum_valid_votes,
                "minimum_established_votes": self.minimum_established_votes,
                "approval_threshold_bps": self.approval_threshold_bps,
                "total_valid_votes": self.total_valid_votes,
                "established_vote_count": self.established_vote_count,
                "original_votes": self.original_votes,
                "not_original_votes": self.not_original_votes,
                "unsure_votes": self.unsure_votes,
                "vote_set_hash": self.vote_set_hash,
                "certificate_reference_height": self.certificate_reference_height,
                "certificate_reference_block_hash": self.certificate_reference_block_hash,
                "issued_timestamp": self.issued_timestamp,
            })
        if self.is_milestone5_certificate():
            return build_certificate_identity_payload_v2({
                "certificate_version": self.certificate_version,
                "protocol_version": self.protocol_version,
                "network_id": self.network_id,
                "submission_id": self.submission_id,
                "content_hash": self.content_hash,
                "creator_address": self.creator_address,
                "originality_rule_version": self.originality_rule_version,
                "originality_decision": self.originality_decision,
                "originality_reference_height": self.originality_reference_height,
                "originality_reference_block_hash": self.originality_reference_block_hash,
                "originality_evidence_digest": self.originality_evidence_digest,
                "reviewer_policy_version": self.reviewer_policy_version,
                "reputation_rule_version": self.reputation_rule_version,
                "reviewer_snapshot_reference_height": self.reviewer_snapshot_reference_height,
                "reviewer_snapshot_reference_block_hash": self.reviewer_snapshot_reference_block_hash,
                "reviewer_snapshot_digest": self.reviewer_snapshot_digest,
                "minimum_valid_votes": self.minimum_valid_votes,
                "minimum_established_votes": self.minimum_established_votes,
                "approval_threshold_bps": self.approval_threshold_bps,
                "total_valid_votes": self.total_valid_votes,
                "established_vote_count": self.established_vote_count,
                "original_votes": self.original_votes,
                "not_original_votes": self.not_original_votes,
                "unsure_votes": self.unsure_votes,
                "vote_set_hash": self.vote_set_hash,
                "certificate_reference_height": self.certificate_reference_height,
                "certificate_reference_block_hash": self.certificate_reference_block_hash,
                "issued_timestamp": self.issued_timestamp,
                "originality_score": self.originality_score,
            })
        if self.is_protocol_v1_certificate():
            return {
                "certificate_version": self.certificate_version,
                "protocol_version": self.protocol_version,
                "network_id": self.network_id,
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
                "vote_hash": self.vote_hash,
                "originality_score": self.originality_score,
                "approval_threshold": self.approval_threshold,
            }
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

    def identity_payload_v1(self):
        if not self.is_protocol_v1_certificate():
            raise ValueError("Legacy certificates do not define a Protocol v1 identity payload.")
        return build_certificate_identity_payload_v1(self.to_core_dict())

    def to_dict(self):
        payload = {
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
        if self.is_versioned_certificate():
            payload.update({
                "certificate_version": self.certificate_version,
                "protocol_version": self.protocol_version,
                "network_id": self.network_id,
                "approval_threshold": self.approval_threshold,
            })
        if self.is_milestone5_certificate():
            payload.update({
                "creator_address": self.creator_address,
                "originality_rule_version": self.originality_rule_version,
                "originality_decision": self.originality_decision,
                "originality_reference_height": self.originality_reference_height,
                "originality_reference_block_hash": self.originality_reference_block_hash,
                "originality_evidence_digest": self.originality_evidence_digest,
                "reviewer_policy_version": self.reviewer_policy_version,
                "reputation_rule_version": self.reputation_rule_version,
                "reviewer_snapshot_reference_height": self.reviewer_snapshot_reference_height,
                "reviewer_snapshot_reference_block_hash": self.reviewer_snapshot_reference_block_hash,
                "reviewer_snapshot_digest": self.reviewer_snapshot_digest,
                "minimum_valid_votes": self.minimum_valid_votes,
                "minimum_established_votes": self.minimum_established_votes,
                "approval_threshold_bps": self.approval_threshold_bps,
                "total_valid_votes": self.total_valid_votes,
                "established_vote_count": self.established_vote_count,
                "vote_set_hash": self.vote_set_hash,
                "certificate_reference_height": self.certificate_reference_height,
                "certificate_reference_block_hash": self.certificate_reference_block_hash,
                "issued_timestamp": self.issued_timestamp,
                "evidence_binding_status": self.evidence_binding_status,
            })
        return payload

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
            certificate_version=data.get("certificate_version"),
            network_id=data.get("network_id"),
            protocol_version=data.get("protocol_version"),
            approval_threshold=data.get("approval_threshold"),
            creator_address=data.get("creator_address"),
            originality_rule_version=data.get("originality_rule_version"),
            originality_decision=data.get("originality_decision"),
            originality_reference_height=data.get("originality_reference_height"),
            originality_reference_block_hash=data.get("originality_reference_block_hash"),
            originality_evidence_digest=data.get("originality_evidence_digest"),
            reviewer_policy_version=data.get("reviewer_policy_version"),
            reputation_rule_version=data.get("reputation_rule_version"),
            reviewer_snapshot_reference_height=data.get("reviewer_snapshot_reference_height"),
            reviewer_snapshot_reference_block_hash=data.get("reviewer_snapshot_reference_block_hash"),
            reviewer_snapshot_digest=data.get("reviewer_snapshot_digest"),
            minimum_valid_votes=data.get("minimum_valid_votes"),
            minimum_established_votes=data.get("minimum_established_votes"),
            approval_threshold_bps=data.get("approval_threshold_bps"),
            total_valid_votes=data.get("total_valid_votes"),
            established_vote_count=data.get("established_vote_count"),
            vote_set_hash=data.get("vote_set_hash"),
            certificate_reference_height=data.get("certificate_reference_height"),
            certificate_reference_block_hash=data.get("certificate_reference_block_hash"),
            issued_timestamp=data.get("issued_timestamp"),
            evidence_binding_status=data.get("evidence_binding_status", "active"),
        )
