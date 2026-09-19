"""Protocol v1 signed submitter rights/permanence attestations.

The signature is an EIP-191 ``personal_sign`` identity proof over the existing
Protocol v1 canonical JSON envelope.  It is not an Ethereum transaction and it
does not prove ownership of, license to, or legal entitlement in the media.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Mapping

from media_admission_policy import (
    MEDIA_ADMISSION_POLICY_ID,
    MEDIA_ADMISSION_POLICY_VERSION,
    media_admission_policy_digest,
)
from media_technical_validation import (
    TECHNICAL_VALIDATION_EVIDENCE_VERSION,
    validate_technical_evidence,
)
from protocol_v1 import (
    OBJECT_TYPE_SUBMITTER_ATTESTATION,
    PROTOCOL_VERSION,
    PUBLIC_TESTNET_V1_NETWORK_ID,
    build_domain_envelope,
    canonical_domain_hash,
    canonical_json_text,
    normalize_network_id,
    protocol_domain,
)
from wallet_signatures import normalize_wallet_address, recover_signed_wallet_address


SUBMITTER_ATTESTATION_VERSION = 1
SUBMITTER_ATTESTATION_STATEMENT_VERSION = 1
SUBMITTER_ATTESTATION_STATEMENT_ID = (
    "zoidberg-public-testnet-v1/submitter-rights-permanence/1"
)
SUBMITTER_ATTESTATION_DOMAIN = protocol_domain(OBJECT_TYPE_SUBMITTER_ATTESTATION)
SUBMITTER_ATTESTATION_SIGNATURE_SCHEME = "personal_sign"

# POLICY TODO — OWNER DECISION REQUIRED: production/legal wording is not frozen.
# This is a versioned engineering/testnet assertion only.
SUBMITTER_ATTESTATION_STATEMENT = (
    "I assert that I have the right or authorization to submit this exact content "
    "under the identified ZoidbergChain Public Testnet media-admission policy. "
    "I understand that, if accepted and finalized, the accepted media bytes become "
    "permanently replicated in immutable ZoidbergChain history and cannot be removed "
    "through ordinary moderation. This testnet attestation is my signed assertion; "
    "it is not proof of ownership, a legal determination, a waiver, or a license "
    "beyond this explicit assertion."
)

ATTESTATION_REQUIRED = "public_testnet_v1_required"
ATTESTATION_LEGACY = "legacy_pre_activation"
ATTESTATION_DEVELOPMENT = "development_only_unsigned"

REASON_MISSING_ATTESTATION = "missing_attestation"
REASON_UNSUPPORTED_ATTESTATION_VERSION = "unsupported_attestation_version"
REASON_MALFORMED_ATTESTATION = "malformed_attestation"
REASON_WRONG_NETWORK = "wrong_network"
REASON_POLICY_MISMATCH = "policy_mismatch"
REASON_MEDIA_HASH_MISMATCH = "media_hash_mismatch"
REASON_EVIDENCE_DIGEST_MISMATCH = "evidence_digest_mismatch"
REASON_NONCE_INVALID = "nonce_invalid"
REASON_NONCE_REPLAYED = "nonce_replayed"
REASON_SIGNER_MISMATCH = "signer_mismatch"
REASON_INVALID_SIGNATURE = "invalid_signature"
REASON_SUBMISSION_MISMATCH = "submission_mismatch"
REASON_MESSAGE_MISMATCH = "canonical_message_mismatch"

_HEX_32 = re.compile(r"^[0-9a-f]{32}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class SubmitterAttestationError(ValueError):
    """A fail-closed attestation error with a stable protocol reason code."""

    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code


def _isoformat(value: datetime | str) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise SubmitterAttestationError(
                REASON_MALFORMED_ATTESTATION, "Attestation timestamps must include a timezone."
            )
        return value.astimezone(timezone.utc).isoformat()
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SubmitterAttestationError(
            REASON_MALFORMED_ATTESTATION, "Attestation timestamp is invalid."
        ) from exc
    if parsed.tzinfo is None:
        raise SubmitterAttestationError(
            REASON_MALFORMED_ATTESTATION, "Attestation timestamps must include a timezone."
        )
    return parsed.astimezone(timezone.utc).isoformat()


def build_submitter_attestation_payload(
    *,
    attestation_version: int = SUBMITTER_ATTESTATION_VERSION,
    statement_id: str = SUBMITTER_ATTESTATION_STATEMENT_ID,
    statement_version: int = SUBMITTER_ATTESTATION_STATEMENT_VERSION,
    statement: str = SUBMITTER_ATTESTATION_STATEMENT,
    wallet_address: str,
    network_id: str,
    submission_id: str,
    raw_media_sha256: str,
    policy_id: str,
    policy_version: int,
    policy_digest: str,
    technical_evidence_version: int,
    technical_evidence_digest: str,
    nonce: str,
    issued_at: datetime | str,
    expires_at: datetime | str,
) -> dict[str, Any]:
    """Build the complete immutable v1 statement payload."""
    wallet = normalize_wallet_address(wallet_address)
    if wallet is None:
        raise SubmitterAttestationError(REASON_MALFORMED_ATTESTATION, "Attestation wallet is invalid.")
    normalized_network = normalize_network_id(network_id)
    submission = str(submission_id or "").strip().lower()
    media_hash = str(raw_media_sha256 or "").strip().lower()
    evidence_digest = str(technical_evidence_digest or "").strip().lower()
    policy_hash = str(policy_digest or "").strip().lower()
    normalized_nonce = str(nonce or "").strip()
    if attestation_version != SUBMITTER_ATTESTATION_VERSION:
        raise SubmitterAttestationError(
            REASON_UNSUPPORTED_ATTESTATION_VERSION, "Unsupported submitter attestation version."
        )
    if (
        statement_id != SUBMITTER_ATTESTATION_STATEMENT_ID
        or statement_version != SUBMITTER_ATTESTATION_STATEMENT_VERSION
        or statement != SUBMITTER_ATTESTATION_STATEMENT
    ):
        raise SubmitterAttestationError(
            REASON_MALFORMED_ATTESTATION, "Submitter attestation statement is not canonical."
        )
    if not _HEX_32.fullmatch(submission):
        raise SubmitterAttestationError(REASON_SUBMISSION_MISMATCH, "Attestation submission_id is invalid.")
    if not _HEX_64.fullmatch(media_hash):
        raise SubmitterAttestationError(REASON_MEDIA_HASH_MISMATCH, "Attestation media hash is invalid.")
    if not _HEX_64.fullmatch(evidence_digest):
        raise SubmitterAttestationError(
            REASON_EVIDENCE_DIGEST_MISMATCH, "Attestation evidence digest is invalid."
        )
    if not _HEX_64.fullmatch(policy_hash):
        raise SubmitterAttestationError(REASON_POLICY_MISMATCH, "Attestation policy digest is invalid.")
    if not normalized_nonce or len(normalized_nonce) > 256:
        raise SubmitterAttestationError(REASON_NONCE_INVALID, "Attestation nonce is invalid.")
    normalized_issued_at = _isoformat(issued_at)
    normalized_expires_at = _isoformat(expires_at)
    if datetime.fromisoformat(normalized_expires_at) <= datetime.fromisoformat(normalized_issued_at):
        raise SubmitterAttestationError(
            REASON_MALFORMED_ATTESTATION,
            "Attestation expiry must be later than its issue time.",
        )
    return {
        "attestation_version": attestation_version,
        "statement_id": statement_id,
        "statement_version": statement_version,
        "statement": statement,
        "wallet_address": wallet,
        "submission_id": submission,
        "raw_media_sha256": media_hash,
        "policy_id": str(policy_id or "").strip(),
        "policy_version": policy_version,
        "policy_digest": policy_hash,
        "technical_evidence_version": technical_evidence_version,
        "technical_evidence_digest": evidence_digest,
        "nonce": normalized_nonce,
        "issued_at": normalized_issued_at,
        "expires_at": normalized_expires_at,
        "network_id": normalized_network,
    }


def build_submitter_attestation_envelope(**values: Any) -> dict[str, Any]:
    payload = build_submitter_attestation_payload(**values)
    return build_domain_envelope(
        payload,
        object_type=OBJECT_TYPE_SUBMITTER_ATTESTATION,
        network_id=payload["network_id"],
    )


def build_submitter_attestation_message(**values: Any) -> str:
    return canonical_json_text(build_submitter_attestation_envelope(**values))


def submitter_attestation_payload_digest(payload: Mapping[str, Any]) -> str:
    return canonical_domain_hash(
        dict(payload),
        object_type=OBJECT_TYPE_SUBMITTER_ATTESTATION,
        network_id=str(payload.get("network_id") or ""),
    )


def build_submitter_attestation_record(
    *, payload: Mapping[str, Any], signature: str, verified_at: datetime | str
) -> dict[str, Any]:
    normalized_payload = build_submitter_attestation_payload(**dict(payload))
    message = canonical_json_text(
        build_domain_envelope(
            normalized_payload,
            object_type=OBJECT_TYPE_SUBMITTER_ATTESTATION,
            network_id=normalized_payload["network_id"],
        )
    )
    return {
        "attestation_version": SUBMITTER_ATTESTATION_VERSION,
        "statement_id": SUBMITTER_ATTESTATION_STATEMENT_ID,
        "statement_version": SUBMITTER_ATTESTATION_STATEMENT_VERSION,
        "domain": SUBMITTER_ATTESTATION_DOMAIN,
        "protocol_version": PROTOCOL_VERSION,
        "network_id": normalized_payload["network_id"],
        "signature_scheme": SUBMITTER_ATTESTATION_SIGNATURE_SCHEME,
        "signer_wallet": normalized_payload["wallet_address"],
        "signature": str(signature or "").strip(),
        "nonce": normalized_payload["nonce"],
        "canonical_payload": normalized_payload,
        "canonical_payload_digest": submitter_attestation_payload_digest(normalized_payload),
        "canonical_message": message,
        "canonical_message_hash": hashlib.sha256(message.encode("utf-8")).hexdigest(),
        "verified_at": _isoformat(verified_at),
    }


def validate_submitter_attestation(
    record: Mapping[str, Any] | None,
    *,
    expected_wallet_address: str,
    expected_submission_id: str,
    expected_raw_media_sha256: str,
    expected_technical_evidence: Mapping[str, Any],
    raw_media_bytes: bytes,
    expected_network_id: str = PUBLIC_TESTNET_V1_NETWORK_ID,
) -> dict[str, Any]:
    """Independently verify a durable attestation and all immutable bindings."""
    if not isinstance(record, Mapping):
        raise SubmitterAttestationError(REASON_MISSING_ATTESTATION, "Submitter attestation is required.")
    candidate = dict(record)
    if candidate.get("attestation_version") != SUBMITTER_ATTESTATION_VERSION:
        raise SubmitterAttestationError(
            REASON_UNSUPPORTED_ATTESTATION_VERSION, "Unsupported submitter attestation version."
        )
    if (
        candidate.get("statement_id") != SUBMITTER_ATTESTATION_STATEMENT_ID
        or candidate.get("statement_version") != SUBMITTER_ATTESTATION_STATEMENT_VERSION
        or candidate.get("domain") != SUBMITTER_ATTESTATION_DOMAIN
        or candidate.get("protocol_version") != PROTOCOL_VERSION
        or candidate.get("signature_scheme") != SUBMITTER_ATTESTATION_SIGNATURE_SCHEME
    ):
        raise SubmitterAttestationError(REASON_MALFORMED_ATTESTATION, "Submitter attestation identity is invalid.")
    if not isinstance(candidate.get("verified_at"), str):
        raise SubmitterAttestationError(
            REASON_MALFORMED_ATTESTATION, "Submitter attestation verification timestamp is required."
        )
    _isoformat(candidate["verified_at"])

    payload = candidate.get("canonical_payload")
    if not isinstance(payload, Mapping):
        raise SubmitterAttestationError(REASON_MALFORMED_ATTESTATION, "Canonical attestation payload is required.")
    try:
        normalized_payload = build_submitter_attestation_payload(**dict(payload))
    except SubmitterAttestationError:
        raise
    except (TypeError, ValueError) as exc:
        raise SubmitterAttestationError(REASON_MALFORMED_ATTESTATION, "Canonical attestation payload is malformed.") from exc
    if dict(payload) != normalized_payload:
        raise SubmitterAttestationError(REASON_MALFORMED_ATTESTATION, "Canonical attestation payload is not normalized.")

    expected_network = normalize_network_id(expected_network_id)
    if normalized_payload["network_id"] != expected_network or candidate.get("network_id") != expected_network:
        raise SubmitterAttestationError(REASON_WRONG_NETWORK, "Submitter attestation is for another network.")
    expected_wallet = normalize_wallet_address(expected_wallet_address)
    if expected_wallet is None or normalized_payload["wallet_address"] != expected_wallet:
        raise SubmitterAttestationError(REASON_SIGNER_MISMATCH, "Submitter attestation wallet does not match submitter.")
    if normalize_wallet_address(candidate.get("signer_wallet")) != expected_wallet:
        raise SubmitterAttestationError(REASON_SIGNER_MISMATCH, "Persisted attestation signer does not match submitter.")
    if normalized_payload["submission_id"] != str(expected_submission_id or "").strip().lower():
        raise SubmitterAttestationError(REASON_SUBMISSION_MISMATCH, "Submitter attestation is for another submission.")
    if normalized_payload["raw_media_sha256"] != str(expected_raw_media_sha256 or "").strip().lower():
        raise SubmitterAttestationError(REASON_MEDIA_HASH_MISMATCH, "Submitter attestation is for different media.")

    try:
        evidence = validate_technical_evidence(expected_technical_evidence, raw_media_bytes)
    except ValueError as exc:
        raise SubmitterAttestationError(
            REASON_EVIDENCE_DIGEST_MISMATCH, "Technical-validation evidence is invalid or stale."
        ) from exc
    if (
        normalized_payload["technical_evidence_version"] != evidence["evidence_version"]
        or normalized_payload["technical_evidence_digest"] != evidence["evidence_digest"]
    ):
        raise SubmitterAttestationError(
            REASON_EVIDENCE_DIGEST_MISMATCH, "Submitter attestation technical evidence does not match."
        )
    if (
        normalized_payload["policy_id"] != MEDIA_ADMISSION_POLICY_ID
        or normalized_payload["policy_version"] != MEDIA_ADMISSION_POLICY_VERSION
        or normalized_payload["policy_digest"] != media_admission_policy_digest()
        or evidence["policy_id"] != MEDIA_ADMISSION_POLICY_ID
        or evidence["policy_version"] != MEDIA_ADMISSION_POLICY_VERSION
        or evidence["policy_digest"] != media_admission_policy_digest()
    ):
        raise SubmitterAttestationError(REASON_POLICY_MISMATCH, "Submitter attestation policy does not match.")
    if not str(normalized_payload.get("nonce") or "").strip():
        raise SubmitterAttestationError(REASON_NONCE_INVALID, "Submitter attestation nonce is invalid.")
    if candidate.get("nonce") != normalized_payload["nonce"]:
        raise SubmitterAttestationError(
            REASON_NONCE_INVALID, "Persisted attestation nonce does not match its signed payload."
        )

    envelope = build_domain_envelope(
        normalized_payload,
        object_type=OBJECT_TYPE_SUBMITTER_ATTESTATION,
        network_id=expected_network,
    )
    message = canonical_json_text(envelope)
    message_hash = hashlib.sha256(message.encode("utf-8")).hexdigest()
    if (
        candidate.get("canonical_message") != message
        or candidate.get("canonical_message_hash") != message_hash
        or candidate.get("canonical_payload_digest") != submitter_attestation_payload_digest(normalized_payload)
    ):
        raise SubmitterAttestationError(REASON_MESSAGE_MISMATCH, "Canonical attestation message does not match its payload.")
    signature = candidate.get("signature")
    if not isinstance(signature, str) or not signature.strip():
        raise SubmitterAttestationError(REASON_INVALID_SIGNATURE, "Submitter attestation signature is missing.")
    try:
        recovered = recover_signed_wallet_address(message, signature)
    except ValueError as exc:
        raise SubmitterAttestationError(REASON_INVALID_SIGNATURE, "Submitter attestation signature is invalid.") from exc
    if recovered != expected_wallet:
        raise SubmitterAttestationError(REASON_SIGNER_MISMATCH, "Submitter attestation signature does not match submitter.")
    return candidate
