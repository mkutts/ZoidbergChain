"""Versioned Public Testnet media-admission policy definitions.

Task 6.2 defines policy data and the deterministic checks that can be made from
already-known metadata.  It deliberately does not inspect magic bytes, decode
images, run OCR, attest submissions, or change consensus activation.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from protocol_v1 import (
    PROTOCOL_VERSION,
    PUBLIC_TESTNET_V1_NETWORK_ID,
    canonical_hash,
    canonical_json_text,
)


MEDIA_ADMISSION_POLICY_VERSION = 1
MEDIA_ADMISSION_POLICY_SEMANTIC_VERSION = "1.0.0"
MEDIA_ADMISSION_POLICY_ID = "zoidberg-public-testnet-v1/media-admission/1"

POLICY_SCOPE_CONSENSUS = "consensus_protocol"
POLICY_SCOPE_LOCAL_DEFENSE = "local_defense_only"

OUTCOME_ACCEPT = "ACCEPT"
OUTCOME_REJECT = "REJECT"
OUTCOME_OWNER_DECISION_REQUIRED = "OWNER_DECISION_REQUIRED"

REASON_ACCEPTED_POLICY_METADATA = "ACCEPTED_POLICY_METADATA"
REASON_UNKNOWN_POLICY_VERSION = "UNKNOWN_POLICY_VERSION"
REASON_INVALID_POLICY_INPUT = "INVALID_POLICY_INPUT"
REASON_UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
REASON_DECLARED_MIME_MISMATCH = "DECLARED_MIME_MISMATCH"
REASON_EXCEEDS_REQUEST_BYTE_LIMIT = "EXCEEDS_REQUEST_BYTE_LIMIT"
REASON_EXCEEDS_STAGED_UPLOAD_BYTE_LIMIT = "EXCEEDS_STAGED_UPLOAD_BYTE_LIMIT"
REASON_EXCEEDS_ACCEPTED_MEDIA_BYTE_LIMIT = "EXCEEDS_ACCEPTED_MEDIA_BYTE_LIMIT"
REASON_EXCEEDS_TEXT_BYTE_LIMIT = "EXCEEDS_TEXT_BYTE_LIMIT"
REASON_EXCEEDS_BLOCK_BYTE_LIMIT = "EXCEEDS_BLOCK_BYTE_LIMIT"
REASON_EXCEEDS_DIMENSION_LIMIT = "EXCEEDS_DIMENSION_LIMIT"
REASON_EXCEEDS_PIXEL_LIMIT = "EXCEEDS_PIXEL_LIMIT"
REASON_EXCEEDS_FRAME_LIMIT = "EXCEEDS_FRAME_LIMIT"
REASON_DISALLOWED_ANIMATION = "DISALLOWED_ANIMATION"
REASON_DISALLOWED_ARCHIVE = "DISALLOWED_ARCHIVE"
REASON_EXECUTABLE_OR_SCRIPT = "EXECUTABLE_OR_SCRIPT"
REASON_MALFORMED_MEDIA = "MALFORMED_MEDIA"
REASON_UNSUPPORTED_METADATA = "UNSUPPORTED_METADATA"
REASON_RESOURCE_LIMIT_TERMINATED = "RESOURCE_LIMIT_TERMINATED"
REASON_PROHIBITED_CONTENT_POLICY_UNRESOLVED = "PROHIBITED_CONTENT_POLICY_UNRESOLVED"

POLICY_REASON_CODES = (
    REASON_ACCEPTED_POLICY_METADATA,
    REASON_DECLARED_MIME_MISMATCH,
    REASON_DISALLOWED_ANIMATION,
    REASON_DISALLOWED_ARCHIVE,
    REASON_EXCEEDS_ACCEPTED_MEDIA_BYTE_LIMIT,
    REASON_EXCEEDS_BLOCK_BYTE_LIMIT,
    REASON_EXCEEDS_DIMENSION_LIMIT,
    REASON_EXCEEDS_FRAME_LIMIT,
    REASON_EXCEEDS_PIXEL_LIMIT,
    REASON_EXCEEDS_REQUEST_BYTE_LIMIT,
    REASON_EXCEEDS_STAGED_UPLOAD_BYTE_LIMIT,
    REASON_EXCEEDS_TEXT_BYTE_LIMIT,
    REASON_EXECUTABLE_OR_SCRIPT,
    REASON_INVALID_POLICY_INPUT,
    REASON_MALFORMED_MEDIA,
    REASON_PROHIBITED_CONTENT_POLICY_UNRESOLVED,
    REASON_RESOURCE_LIMIT_TERMINATED,
    REASON_UNKNOWN_POLICY_VERSION,
    REASON_UNSUPPORTED_MEDIA_TYPE,
    REASON_UNSUPPORTED_METADATA,
)

_ALLOWED_MEDIA_TYPES = (
    {
        "media_type": "gif",
        "mime_type": "image/gif",
        "category": "image",
        "animation_capable": True,
    },
    {
        "media_type": "jpeg",
        "mime_type": "image/jpeg",
        "category": "image",
        "animation_capable": False,
    },
    {
        "media_type": "plain_utf8_text",
        "mime_type": "text/plain",
        "category": "text",
        "animation_capable": False,
    },
    {
        "media_type": "png",
        "mime_type": "image/png",
        "category": "image",
        "animation_capable": False,
    },
    {
        "media_type": "webp",
        "mime_type": "image/webp",
        "category": "image",
        "animation_capable": True,
    },
)

_OWNER_DECISIONS = (
    "activation_height_and_in_flight_submission_treatment",
    "animated_gif_webp_support_at_activation",
    "denylist_ownership_distribution_and_activation",
    "isolated_worker_operations_and_incident_response",
    "permanent_publication_and_rights_attestation_text",
    "prohibited_content_policy_jurisdiction_and_appeals",
    "raw_media_access_after_presentation_suppression",
    "rejected_temporary_byte_retention",
    "safety_review_authority_quorum_and_welfare",
    "safe_preview_encoding_and_animation_review",
)

_MEDIA_ADMISSION_POLICIES: dict[int, dict[str, Any]] = {
    MEDIA_ADMISSION_POLICY_VERSION: {
        "network_id": PUBLIC_TESTNET_V1_NETWORK_ID,
        "protocol_version": PROTOCOL_VERSION,
        "policy_kind": "media_admission",
        "policy_id": MEDIA_ADMISSION_POLICY_ID,
        "policy_version": MEDIA_ADMISSION_POLICY_VERSION,
        "semantic_version": MEDIA_ADMISSION_POLICY_SEMANTIC_VERSION,
        "activation": {
            "status": "inactive_owner_decision_required",
            "activation_height": None,
        },
        "rule_scopes": {
            "consensus_protocol": POLICY_SCOPE_CONSENSUS,
            "local_defense": POLICY_SCOPE_LOCAL_DEFENSE,
        },
        "consensus_protocol": {
            "type_authority": {
                "authoritative_source": "complete_detected_and_validated_media_bytes",
                "declared_mime_authoritative": False,
                "filename_extension_authoritative": False,
                "declared_mime_mismatch": "reject",
            },
            "allowed_media_types": [dict(item) for item in _ALLOWED_MEDIA_TYPES],
            "byte_limits": {
                "accepted_image_bytes": 262_144,
                "accepted_plain_text_bytes_after_canonicalization": 262_144,
                "canonical_serialized_non_genesis_block_bytes": 524_288,
            },
            "image_structure": {
                "minimum_width_pixels": 1,
                "minimum_height_pixels": 1,
                "maximum_width_pixels": 4_096,
                "maximum_height_pixels": 4_096,
                "maximum_frame_count": 60,
                "maximum_aggregate_decoded_pixels": 16_777_216,
                "every_frame_must_validate": True,
                "animation_within_limits": "provisionally_allowed_pending_activation_owner_decision",
                "decoded_color_model": "convertible_to_rgb_or_rgba_by_pinned_decoder",
            },
            "container_and_active_content": {
                "archives": "reject",
                "polyglots": "reject",
                "embedded_active_content": "reject",
                "executables": "reject",
                "scripts": "reject",
                "complete_container_parse_required": True,
                "unexpected_trailing_payload": "reject",
                "parser_warnings": "reject",
                "invalid_frame_tables": "reject",
                "unsupported_metadata": "reject",
            },
            "text_canonicalization": "normalize_crlf_and_cr_to_lf_then_trim_outer_whitespace_utf8",
            "metadata_limits": {
                "caption_unicode_scalars": 1_000,
                "caption_utf8_bytes": 4_096,
                "submission_text_unicode_scalars": 4_096,
                "submission_text_utf8_bytes": 16_384,
                "sanitized_display_filename_ascii_bytes": 255,
            },
            "peer_limits": {
                "chain_page_blocks": 64,
                "chain_page_encoded_response_bytes": 16_777_216,
                "encoded_media_length_check_before_base64_decode": True,
                "decoded_media_uses_applicable_accepted_media_limit": True,
            },
            "failure_policy": "fail_closed",
        },
        "local_defense_only": {
            "defaults": {
                "staged_uploaded_payload_bytes": 5_242_880,
                "multipart_request_body_bytes": 5_308_416,
                "text_upload_json_body_bytes": 327_680,
                "structural_decode_wall_time_seconds": 2,
                "ocr_wall_time_seconds": 5,
                "worker_memory_bytes": 268_435_456,
            },
            "worker_isolation": {
                "outside_node_api_process": True,
                "cpu_quota_required": True,
                "hard_wall_clock_timeout_required": True,
                "memory_quota_required": True,
                "network_access": False,
                "empty_working_directory": True,
                "inherit_secrets": False,
            },
            "override_rule": "local_values_may_only_tighten_admission_or_resource_defenses",
            "timeout_or_resource_termination": "reject_local_admission_never_consensus_pass",
        },
        "content_category_policy": {
            "status": "owner_decision_required_fail_closed_before_public_minting",
            "required_categories_not_yet_normatively_defined": [
                "asserted_rights_absent",
                "child_sexual_abuse_material",
                "credible_threats",
                "exposed_authentication_secrets",
                "malware_or_exploit_payloads",
                "material_illegal_in_deployment_jurisdiction",
                "non_consensual_intimate_imagery",
                "targeted_private_identifying_information",
            ],
        },
        "owner_decisions": list(_OWNER_DECISIONS),
        "deferred_enforcement": [
            "task_6_3_complete_type_detection_and_decode_hardening",
            "task_6_4_signed_submitter_attestation",
            "task_6_5_separate_safety_voting_and_certificate_binding",
            "task_6_6_plus_quarantine_reporting_disputes_serving_and_activation",
        ],
        "reason_codes": list(POLICY_REASON_CODES),
    }
}


class MediaAdmissionPolicyError(ValueError):
    """A stable-code policy lookup or validation failure."""

    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class PolicyEvaluationInput:
    """Metadata already established by callers; no byte inspection occurs here."""

    detected_mime_type: str | None = None
    declared_mime_type: str | None = None
    accepted_media_bytes: int | None = None
    staged_upload_bytes: int | None = None
    request_body_bytes: int | None = None
    request_kind: str | None = None
    canonical_block_bytes: int | None = None
    width_pixels: int | None = None
    height_pixels: int | None = None
    frame_count: int | None = None
    aggregate_decoded_pixels: int | None = None
    is_archive: bool = False
    is_polyglot: bool = False
    has_embedded_active_content: bool = False
    is_executable: bool = False
    is_script: bool = False
    is_malformed: bool = False
    has_unsupported_metadata: bool = False
    resource_limit_terminated: bool = False


def media_admission_policy(version: int = MEDIA_ADMISSION_POLICY_VERSION) -> dict[str, Any]:
    if isinstance(version, bool) or not isinstance(version, int):
        raise MediaAdmissionPolicyError(
            REASON_INVALID_POLICY_INPUT,
            "Media-admission policy version must be an integer.",
        )
    try:
        return validate_media_admission_policy(_MEDIA_ADMISSION_POLICIES[version])
    except KeyError as exc:
        raise MediaAdmissionPolicyError(
            REASON_UNKNOWN_POLICY_VERSION,
            f"Unsupported media-admission policy version: {version}",
        ) from exc


def validate_media_admission_policy(policy: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a policy object without accepting machine-local reinterpretation."""
    if not isinstance(policy, Mapping):
        raise MediaAdmissionPolicyError(
            REASON_INVALID_POLICY_INPUT, "Media-admission policy must be an object."
        )
    candidate = deepcopy(dict(policy))
    required_identity = {
        "network_id": PUBLIC_TESTNET_V1_NETWORK_ID,
        "protocol_version": PROTOCOL_VERSION,
        "policy_kind": "media_admission",
        "policy_id": MEDIA_ADMISSION_POLICY_ID,
        "policy_version": MEDIA_ADMISSION_POLICY_VERSION,
        "semantic_version": MEDIA_ADMISSION_POLICY_SEMANTIC_VERSION,
    }
    for field_name, expected in required_identity.items():
        if candidate.get(field_name) != expected:
            raise MediaAdmissionPolicyError(
                REASON_INVALID_POLICY_INPUT,
                f"Media-admission policy has invalid {field_name}.",
            )
    if candidate.get("reason_codes") != list(POLICY_REASON_CODES):
        raise MediaAdmissionPolicyError(
            REASON_INVALID_POLICY_INPUT,
            "Media-admission policy reason codes are not canonical.",
        )
    consensus = candidate.get("consensus_protocol")
    local = candidate.get("local_defense_only")
    if not isinstance(consensus, dict) or not isinstance(local, dict):
        raise MediaAdmissionPolicyError(
            REASON_INVALID_POLICY_INPUT,
            "Media-admission policy rule scopes are incomplete.",
        )
    allowed = consensus.get("allowed_media_types")
    if not isinstance(allowed, list) or allowed != [dict(item) for item in _ALLOWED_MEDIA_TYPES]:
        raise MediaAdmissionPolicyError(
            REASON_INVALID_POLICY_INPUT,
            "Media-admission policy allowed media types are not canonical.",
        )
    for group in (
        consensus.get("byte_limits"),
        consensus.get("metadata_limits"),
        consensus.get("peer_limits"),
        local.get("defaults"),
    ):
        if not isinstance(group, dict):
            raise MediaAdmissionPolicyError(
                REASON_INVALID_POLICY_INPUT,
                "Media-admission policy limit groups are incomplete.",
            )
        for value in group.values():
            if isinstance(value, bool):
                continue
            if not isinstance(value, int) or value <= 0:
                raise MediaAdmissionPolicyError(
                    REASON_INVALID_POLICY_INPUT,
                    "Media-admission policy limits must be positive integers.",
                )
    canonical_json_text(candidate)
    return candidate


def active_public_testnet_media_admission_policy() -> dict[str, Any]:
    """Return v1 policy data; activation remains an explicit owner decision."""
    return media_admission_policy(MEDIA_ADMISSION_POLICY_VERSION)


def media_admission_policy_canonical_text(
    version: int = MEDIA_ADMISSION_POLICY_VERSION,
) -> str:
    return canonical_json_text(media_admission_policy(version))


def media_admission_policy_digest(version: int = MEDIA_ADMISSION_POLICY_VERSION) -> str:
    return canonical_hash(media_admission_policy(version))


def effective_local_defense_limits(
    overrides: Mapping[str, int] | None = None,
    *,
    version: int = MEDIA_ADMISSION_POLICY_VERSION,
) -> dict[str, int]:
    """Apply machine-local limits only when they tighten the versioned defaults."""
    defaults = media_admission_policy(version)["local_defense_only"]["defaults"]
    effective = dict(defaults)
    for key, value in (overrides or {}).items():
        if key not in defaults:
            raise MediaAdmissionPolicyError(
                REASON_INVALID_POLICY_INPUT, f"Unknown local-defense limit: {key}"
            )
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise MediaAdmissionPolicyError(
                REASON_INVALID_POLICY_INPUT,
                f"Local-defense limit {key} must be a positive integer.",
            )
        if value > defaults[key]:
            raise MediaAdmissionPolicyError(
                REASON_INVALID_POLICY_INPUT,
                f"Local-defense limit {key} may not relax the versioned default.",
            )
        effective[key] = value
    return effective


def _non_negative_optional_integer(value: int | None, field_name: str) -> None:
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, int) or value < 0
    ):
        raise MediaAdmissionPolicyError(
            REASON_INVALID_POLICY_INPUT,
            f"{field_name} must be a non-negative integer when provided.",
        )


def evaluate_media_admission_policy(
    metadata: PolicyEvaluationInput,
    *,
    version: int = MEDIA_ADMISSION_POLICY_VERSION,
    local_defense_overrides: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Evaluate policy rules that do not require Task 6.3 byte decoding."""
    try:
        policy = media_admission_policy(version)
    except MediaAdmissionPolicyError as exc:
        return {
            "outcome": OUTCOME_REJECT,
            "reason_codes": [exc.reason_code],
            "policy_id": None,
            "policy_version": version,
            "policy_digest": None,
        }
    if not isinstance(metadata, PolicyEvaluationInput):
        raise MediaAdmissionPolicyError(
            REASON_INVALID_POLICY_INPUT, "metadata must be PolicyEvaluationInput."
        )

    integer_fields = (
        "accepted_media_bytes",
        "staged_upload_bytes",
        "request_body_bytes",
        "canonical_block_bytes",
        "width_pixels",
        "height_pixels",
        "frame_count",
        "aggregate_decoded_pixels",
    )
    for field_name in integer_fields:
        _non_negative_optional_integer(getattr(metadata, field_name), field_name)

    consensus = policy["consensus_protocol"]
    local_limits = effective_local_defense_limits(local_defense_overrides, version=version)
    allowed = {item["mime_type"]: item for item in consensus["allowed_media_types"]}
    detected = (
        metadata.detected_mime_type.strip().lower()
        if isinstance(metadata.detected_mime_type, str)
        else None
    )
    declared = (
        metadata.declared_mime_type.strip().lower()
        if isinstance(metadata.declared_mime_type, str)
        else None
    )
    reasons: set[str] = set()

    media = allowed.get(detected)
    if detected is not None and media is None:
        reasons.add(REASON_UNSUPPORTED_MEDIA_TYPE)
    if detected is not None and declared is not None and detected != declared:
        reasons.add(REASON_DECLARED_MIME_MISMATCH)

    if (
        metadata.staged_upload_bytes is not None
        and metadata.staged_upload_bytes
        > local_limits["staged_uploaded_payload_bytes"]
    ):
        reasons.add(REASON_EXCEEDS_STAGED_UPLOAD_BYTE_LIMIT)
    if metadata.request_body_bytes is not None:
        request_limit_key = {
            "multipart": "multipart_request_body_bytes",
            "text_json": "text_upload_json_body_bytes",
        }.get(metadata.request_kind)
        if request_limit_key is None:
            raise MediaAdmissionPolicyError(
                REASON_INVALID_POLICY_INPUT,
                "request_kind must be multipart or text_json when request_body_bytes is provided.",
            )
        if metadata.request_body_bytes > local_limits[request_limit_key]:
            reasons.add(REASON_EXCEEDS_REQUEST_BYTE_LIMIT)

    if metadata.accepted_media_bytes is not None and media is not None:
        byte_limits = consensus["byte_limits"]
        if media["category"] == "text":
            if (
                metadata.accepted_media_bytes
                > byte_limits["accepted_plain_text_bytes_after_canonicalization"]
            ):
                reasons.add(REASON_EXCEEDS_TEXT_BYTE_LIMIT)
        elif metadata.accepted_media_bytes > byte_limits["accepted_image_bytes"]:
            reasons.add(REASON_EXCEEDS_ACCEPTED_MEDIA_BYTE_LIMIT)
    if (
        metadata.canonical_block_bytes is not None
        and metadata.canonical_block_bytes
        > consensus["byte_limits"]["canonical_serialized_non_genesis_block_bytes"]
    ):
        reasons.add(REASON_EXCEEDS_BLOCK_BYTE_LIMIT)

    structure = consensus["image_structure"]
    if metadata.width_pixels is not None and not (
        structure["minimum_width_pixels"]
        <= metadata.width_pixels
        <= structure["maximum_width_pixels"]
    ):
        reasons.add(REASON_EXCEEDS_DIMENSION_LIMIT)
    if metadata.height_pixels is not None and not (
        structure["minimum_height_pixels"]
        <= metadata.height_pixels
        <= structure["maximum_height_pixels"]
    ):
        reasons.add(REASON_EXCEEDS_DIMENSION_LIMIT)
    if metadata.frame_count is not None and not (
        1 <= metadata.frame_count <= structure["maximum_frame_count"]
    ):
        reasons.add(REASON_EXCEEDS_FRAME_LIMIT)
    if (
        metadata.aggregate_decoded_pixels is not None
        and metadata.aggregate_decoded_pixels
        > structure["maximum_aggregate_decoded_pixels"]
    ):
        reasons.add(REASON_EXCEEDS_PIXEL_LIMIT)

    if metadata.is_archive or metadata.is_polyglot:
        reasons.add(REASON_DISALLOWED_ARCHIVE)
    if metadata.has_embedded_active_content or metadata.is_executable or metadata.is_script:
        reasons.add(REASON_EXECUTABLE_OR_SCRIPT)
    if metadata.is_malformed:
        reasons.add(REASON_MALFORMED_MEDIA)
    if metadata.has_unsupported_metadata:
        reasons.add(REASON_UNSUPPORTED_METADATA)
    if metadata.resource_limit_terminated:
        reasons.add(REASON_RESOURCE_LIMIT_TERMINATED)

    ordered_reasons = sorted(reasons)
    return {
        "outcome": OUTCOME_REJECT if ordered_reasons else OUTCOME_ACCEPT,
        "reason_codes": ordered_reasons or [REASON_ACCEPTED_POLICY_METADATA],
        "policy_id": policy["policy_id"],
        "policy_version": policy["policy_version"],
        "policy_digest": media_admission_policy_digest(version),
    }
