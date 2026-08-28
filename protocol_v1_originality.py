from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from config import ORIGINALITY_APPROVAL_THRESHOLD
from native_transfer import normalize_wallet_address
from protocol_v1 import (
    OBJECT_TYPE_ORIGINALITY_CERTIFICATE,
    OBJECT_TYPE_VOTE,
    PROTOCOL_VERSION,
    canonical_domain_bytes,
    canonical_domain_hash,
    canonical_json_data,
    normalize_network_id,
    resolve_network_id,
)
from submission import VOTE_TYPES
from validators import is_valid_content_hash


PROTOCOL_V1_VOTE_VERSION = PROTOCOL_VERSION
PROTOCOL_V1_CERTIFICATE_VERSION = PROTOCOL_VERSION


def normalize_decimal_string(value: Any, *, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} is required.")
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be numeric.")

    candidate = value.strip() if isinstance(value, str) else value
    if candidate == "":
        raise ValueError(f"{field_name} is required.")
    try:
        decimal_value = Decimal(str(candidate))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric.") from exc
    if not decimal_value.is_finite():
        raise ValueError(f"{field_name} must be finite.")

    normalized = format(decimal_value, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    if normalized in {"", "-0"}:
        normalized = "0"
    return normalized


def resolve_protocol_v1_network_id(*, network_id: str | None = None, network_name: str | None = None) -> str:
    if network_id is not None:
        return normalize_network_id(network_id)
    try:
        return resolve_network_id(network_name=network_name)
    except ValueError:
        if isinstance(network_name, str) and network_name.strip():
            return normalize_network_id(network_name.strip())
        raise


def normalize_protocol_v1_vote_type(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("vote_type is required.")
    normalized = value.strip()
    if normalized not in VOTE_TYPES:
        raise ValueError(f"Invalid vote type: {normalized}")
    return normalized


def normalize_protocol_identity(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required.")
    normalized = value.strip()
    normalized_wallet = normalize_wallet_address(normalized)
    return normalized_wallet or normalized


def normalize_protocol_v1_wallet_address(value: Any, *, field_name: str) -> str:
    normalized = normalize_wallet_address(str(value or "").strip())
    if normalized is None:
        raise ValueError(f"{field_name} must be a valid Ethereum-style 0x address.")
    return normalized


def normalize_protocol_v1_submission_id(value: Any, *, field_name: str = "submission_id") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required.")
    return value.strip()


def normalize_protocol_v1_content_hash(value: Any, *, field_name: str = "content_hash") -> str:
    if not isinstance(value, str) or not is_valid_content_hash(value.strip()):
        raise ValueError(f"{field_name} must be a 64-character lowercase hexadecimal string.")
    return value.strip()


def build_protocol_v1_vote_payload(
    *,
    wallet_address: str,
    submission_id: str,
    content_hash: str,
    vote_type: str,
    nonce: str,
    issued_at: str,
    expires_at: str,
) -> dict[str, Any]:
    normalized_wallet = normalize_protocol_v1_wallet_address(
        wallet_address,
        field_name="wallet_address",
    )
    normalized_submission_id = normalize_protocol_v1_submission_id(submission_id)
    normalized_content_hash = normalize_protocol_v1_content_hash(content_hash)
    normalized_vote_type = normalize_protocol_v1_vote_type(vote_type)
    if not isinstance(nonce, str) or not nonce.strip():
        raise ValueError("nonce is required.")
    if not isinstance(issued_at, str) or not issued_at.strip():
        raise ValueError("issued_at is required.")
    if not isinstance(expires_at, str) or not expires_at.strip():
        raise ValueError("expires_at is required.")

    return {
        "vote_version": PROTOCOL_V1_VOTE_VERSION,
        "submission_id": normalized_submission_id,
        "content_hash": normalized_content_hash,
        "voter_wallet_address": normalized_wallet,
        "vote_type": normalized_vote_type,
        "nonce": nonce.strip(),
        "issued_at": issued_at.strip(),
        "expires_at": expires_at.strip(),
    }


def build_protocol_v1_vote_signing_payload(
    *,
    wallet_address: str,
    submission_id: str,
    content_hash: str,
    vote_type: str,
    nonce: str,
    issued_at: str,
    expires_at: str,
    network_id: str,
) -> dict[str, Any]:
    payload = build_protocol_v1_vote_payload(
        wallet_address=wallet_address,
        submission_id=submission_id,
        content_hash=content_hash,
        vote_type=vote_type,
        nonce=nonce,
        issued_at=issued_at,
        expires_at=expires_at,
    )
    normalized_network_id = normalize_network_id(network_id)
    return canonical_json_data({
        "domain": f"zoidbergchain/vote/v{PROTOCOL_V1_VOTE_VERSION}",
        "network_id": normalized_network_id,
        "object_type": OBJECT_TYPE_VOTE,
        "payload": payload,
        "protocol": "zoidbergchain",
        "protocol_version": PROTOCOL_VERSION,
    })


def build_protocol_v1_vote_message(
    *,
    wallet_address: str,
    submission_id: str,
    content_hash: str,
    vote_type: str,
    nonce: str,
    issued_at: str,
    expires_at: str,
    network_id: str,
) -> str:
    return canonical_domain_bytes(
        build_protocol_v1_vote_payload(
            wallet_address=wallet_address,
            submission_id=submission_id,
            content_hash=content_hash,
            vote_type=vote_type,
            nonce=nonce,
            issued_at=issued_at,
            expires_at=expires_at,
        ),
        object_type=OBJECT_TYPE_VOTE,
        network_id=normalize_network_id(network_id),
    ).decode("utf-8")


def build_protocol_v1_vote_message_hash(
    *,
    wallet_address: str,
    submission_id: str,
    content_hash: str,
    vote_type: str,
    nonce: str,
    issued_at: str,
    expires_at: str,
    network_id: str,
) -> str:
    return canonical_domain_hash(
        build_protocol_v1_vote_payload(
            wallet_address=wallet_address,
            submission_id=submission_id,
            content_hash=content_hash,
            vote_type=vote_type,
            nonce=nonce,
            issued_at=issued_at,
            expires_at=expires_at,
        ),
        object_type=OBJECT_TYPE_VOTE,
        network_id=normalize_network_id(network_id),
    )


def build_protocol_v1_vote_set_payload(
    votes,
    *,
    submission_id: str,
    content_hash: str,
) -> dict[str, Any]:
    normalized_submission_id = normalize_protocol_v1_submission_id(submission_id)
    normalized_content_hash = normalize_protocol_v1_content_hash(content_hash)
    normalized_votes: list[dict[str, str]] = []
    seen_voters: set[str] = set()

    for vote in votes or []:
        if not isinstance(vote, dict):
            raise ValueError("Protocol v1 vote-set entries must be objects.")
        normalized_voter = normalize_protocol_identity(
            vote.get("voter_wallet_address") or vote.get("voter"),
            field_name="vote.voter",
        )
        if normalized_voter in seen_voters:
            raise ValueError("Protocol v1 vote-set hash does not allow duplicate voters.")
        seen_voters.add(normalized_voter)
        normalized_votes.append({
            "voter": normalized_voter,
            "vote_type": normalize_protocol_v1_vote_type(vote.get("vote_type", vote.get("vote_value"))),
        })

    normalized_votes.sort(key=lambda item: (item["voter"], item["vote_type"]))
    return {
        "vote_set_version": PROTOCOL_V1_VOTE_VERSION,
        "submission_id": normalized_submission_id,
        "content_hash": normalized_content_hash,
        "votes": normalized_votes,
    }


def calculate_protocol_v1_vote_hash(
    votes,
    *,
    submission_id: str,
    content_hash: str,
    network_id: str,
) -> str:
    return canonical_domain_hash(
        build_protocol_v1_vote_set_payload(
            votes,
            submission_id=submission_id,
            content_hash=content_hash,
        ),
        object_type=OBJECT_TYPE_VOTE,
        network_id=normalize_network_id(network_id),
    )


def build_protocol_v1_certificate_identity_payload(certificate_fields: dict[str, Any]) -> dict[str, Any]:
    approval_threshold = certificate_fields.get("approval_threshold", ORIGINALITY_APPROVAL_THRESHOLD)
    return {
        "certificate_version": PROTOCOL_V1_CERTIFICATE_VERSION,
        "submission_id": normalize_protocol_v1_submission_id(certificate_fields.get("submission_id")),
        "content_hash": normalize_protocol_v1_content_hash(certificate_fields.get("content_hash")),
        "creator_wallet": normalize_protocol_identity(
            certificate_fields.get("creator_wallet"),
            field_name="creator_wallet",
        ),
        "vote_hash": normalize_protocol_v1_content_hash(certificate_fields.get("vote_hash"), field_name="vote_hash"),
        "vote_total": _normalize_non_negative_int(certificate_fields.get("vote_total"), field_name="vote_total"),
        "decisive_vote_total": _normalize_non_negative_int(
            certificate_fields.get("decisive_vote_total"),
            field_name="decisive_vote_total",
        ),
        "original_votes": _normalize_non_negative_int(
            certificate_fields.get("original_votes"),
            field_name="original_votes",
        ),
        "not_original_votes": _normalize_non_negative_int(
            certificate_fields.get("not_original_votes"),
            field_name="not_original_votes",
        ),
        "unsure_votes": _normalize_non_negative_int(
            certificate_fields.get("unsure_votes"),
            field_name="unsure_votes",
        ),
        "minimum_votes_required": _normalize_non_negative_int(
            certificate_fields.get("minimum_votes_required"),
            field_name="minimum_votes_required",
        ),
        "approval_threshold": normalize_decimal_string(
            approval_threshold,
            field_name="approval_threshold",
        ),
        "approval_percentage": normalize_decimal_string(
            certificate_fields.get("approval_percentage"),
            field_name="approval_percentage",
        ),
        "originality_score": normalize_decimal_string(
            certificate_fields.get("originality_score"),
            field_name="originality_score",
        ),
    }


def calculate_protocol_v1_certificate_id(certificate_fields: dict[str, Any], *, network_id: str) -> str:
    return canonical_domain_hash(
        build_protocol_v1_certificate_identity_payload(certificate_fields),
        object_type=OBJECT_TYPE_ORIGINALITY_CERTIFICATE,
        network_id=normalize_network_id(network_id),
    )


def _normalize_non_negative_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a non-negative integer.")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a non-negative integer.") from exc
    if normalized < 0:
        raise ValueError(f"{field_name} must be a non-negative integer.")
    return normalized
