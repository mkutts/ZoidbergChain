import json

import pytest

import media_admission_policy as policy_module
from media_admission_policy import (
    MEDIA_ADMISSION_POLICY_ID,
    MEDIA_ADMISSION_POLICY_SEMANTIC_VERSION,
    MEDIA_ADMISSION_POLICY_VERSION,
    OUTCOME_ACCEPT,
    OUTCOME_REJECT,
    POLICY_REASON_CODES,
    PolicyEvaluationInput,
    REASON_DECLARED_MIME_MISMATCH,
    REASON_DISALLOWED_ARCHIVE,
    REASON_EXCEEDS_ACCEPTED_MEDIA_BYTE_LIMIT,
    REASON_EXCEEDS_DIMENSION_LIMIT,
    REASON_EXCEEDS_FRAME_LIMIT,
    REASON_EXCEEDS_PIXEL_LIMIT,
    REASON_EXCEEDS_REQUEST_BYTE_LIMIT,
    REASON_EXCEEDS_TEXT_BYTE_LIMIT,
    REASON_EXECUTABLE_OR_SCRIPT,
    REASON_UNKNOWN_POLICY_VERSION,
    REASON_UNSUPPORTED_MEDIA_TYPE,
    active_public_testnet_media_admission_policy,
    effective_local_defense_limits,
    evaluate_media_admission_policy,
    media_admission_policy,
    media_admission_policy_canonical_text,
    media_admission_policy_digest,
    validate_media_admission_policy,
)
from submission import Submission


def test_public_testnet_v1_policy_loads_deterministically_and_is_a_copy():
    first = active_public_testnet_media_admission_policy()
    second = media_admission_policy(1)
    assert first == second
    first["policy_id"] = "mutated"
    assert media_admission_policy(1)["policy_id"] == MEDIA_ADMISSION_POLICY_ID


def test_policy_identity_version_and_golden_digest_are_stable():
    policy = media_admission_policy()
    assert policy["policy_id"] == "zoidberg-public-testnet-v1/media-admission/1"
    assert policy["policy_version"] == MEDIA_ADMISSION_POLICY_VERSION == 1
    assert policy["semantic_version"] == MEDIA_ADMISSION_POLICY_SEMANTIC_VERSION == "1.0.0"
    assert media_admission_policy_digest() == "96ca86e260de39645ac835e3be8413cdcde91a0d385bf3d951c8f3efe25b5915"


def test_policy_schema_validation_rejects_identity_or_limit_mutation():
    mutated_identity = media_admission_policy()
    mutated_identity["policy_id"] = "different"
    with pytest.raises(policy_module.MediaAdmissionPolicyError, match="policy_id"):
        validate_media_admission_policy(mutated_identity)

    mutated_limit = media_admission_policy()
    mutated_limit["consensus_protocol"]["byte_limits"]["accepted_image_bytes"] = 0
    with pytest.raises(policy_module.MediaAdmissionPolicyError, match="positive integers"):
        validate_media_admission_policy(mutated_limit)


def test_policy_serialization_is_canonical_and_independent_of_mapping_order():
    policy = media_admission_policy()
    reversed_policy = dict(reversed(list(policy.items())))
    assert media_admission_policy_canonical_text() == policy_module.canonical_json_text(reversed_policy)
    assert json.loads(media_admission_policy_canonical_text()) == policy


def test_unknown_policy_version_fails_closed_with_stable_reason():
    with pytest.raises(policy_module.MediaAdmissionPolicyError) as exc_info:
        media_admission_policy(999)
    assert exc_info.value.reason_code == REASON_UNKNOWN_POLICY_VERSION
    result = evaluate_media_admission_policy(PolicyEvaluationInput(), version=999)
    assert result == {
        "outcome": OUTCOME_REJECT,
        "reason_codes": [REASON_UNKNOWN_POLICY_VERSION],
        "policy_id": None,
        "policy_version": 999,
        "policy_digest": None,
    }


def test_all_allowed_media_types_and_authority_rules_are_explicit():
    consensus = media_admission_policy()["consensus_protocol"]
    assert {item["mime_type"] for item in consensus["allowed_media_types"]} == {
        "image/jpeg", "image/png", "image/gif", "image/webp", "text/plain"
    }
    assert {item["media_type"] for item in consensus["allowed_media_types"]} == {
        "jpeg", "png", "gif", "webp", "plain_utf8_text"
    }
    assert consensus["type_authority"] == {
        "authoritative_source": "complete_detected_and_validated_media_bytes",
        "declared_mime_authoritative": False,
        "filename_extension_authoritative": False,
        "declared_mime_mismatch": "reject",
    }


def test_unsupported_and_mismatched_types_have_deterministic_outcomes():
    unsupported = evaluate_media_admission_policy(
        PolicyEvaluationInput(detected_mime_type="application/pdf")
    )
    mismatch = evaluate_media_admission_policy(PolicyEvaluationInput(
        detected_mime_type="image/png", declared_mime_type="image/jpeg"
    ))
    assert unsupported["reason_codes"] == [REASON_UNSUPPORTED_MEDIA_TYPE]
    assert mismatch["reason_codes"] == [REASON_DECLARED_MIME_MISMATCH]


def test_byte_request_and_block_limits_are_explicit_and_resolve_old_mismatch():
    policy = media_admission_policy()
    assert policy["local_defense_only"]["defaults"] == {
        "staged_uploaded_payload_bytes": 5_242_880,
        "multipart_request_body_bytes": 5_308_416,
        "text_upload_json_body_bytes": 327_680,
        "structural_decode_wall_time_seconds": 2,
        "ocr_wall_time_seconds": 5,
        "worker_memory_bytes": 268_435_456,
    }
    assert policy["consensus_protocol"]["byte_limits"] == {
        "accepted_image_bytes": 262_144,
        "accepted_plain_text_bytes_after_canonicalization": 262_144,
        "canonical_serialized_non_genesis_block_bytes": 524_288,
    }
    image = evaluate_media_admission_policy(PolicyEvaluationInput(
        detected_mime_type="image/png", accepted_media_bytes=262_145
    ))
    text = evaluate_media_admission_policy(PolicyEvaluationInput(
        detected_mime_type="text/plain", accepted_media_bytes=262_145
    ))
    assert image["reason_codes"] == [REASON_EXCEEDS_ACCEPTED_MEDIA_BYTE_LIMIT]
    assert text["reason_codes"] == [REASON_EXCEEDS_TEXT_BYTE_LIMIT]


def test_image_dimension_pixel_and_frame_limits_are_explicit_and_evaluated():
    structure = media_admission_policy()["consensus_protocol"]["image_structure"]
    assert structure["maximum_width_pixels"] == 4_096
    assert structure["maximum_height_pixels"] == 4_096
    assert structure["maximum_frame_count"] == 60
    assert structure["maximum_aggregate_decoded_pixels"] == 16_777_216
    result = evaluate_media_admission_policy(PolicyEvaluationInput(
        detected_mime_type="image/gif", width_pixels=4_097, height_pixels=0,
        frame_count=61, aggregate_decoded_pixels=16_777_217,
    ))
    assert result["reason_codes"] == sorted({
        REASON_EXCEEDS_DIMENSION_LIMIT,
        REASON_EXCEEDS_FRAME_LIMIT,
        REASON_EXCEEDS_PIXEL_LIMIT,
    })


def test_archive_container_and_executable_script_rules_are_explicit():
    rules = media_admission_policy()["consensus_protocol"]["container_and_active_content"]
    assert rules["archives"] == rules["polyglots"] == "reject"
    assert rules["executables"] == rules["scripts"] == "reject"
    result = evaluate_media_admission_policy(PolicyEvaluationInput(
        is_archive=True, is_executable=True, is_script=True
    ))
    assert result["reason_codes"] == sorted({
        REASON_DISALLOWED_ARCHIVE, REASON_EXECUTABLE_OR_SCRIPT
    })


def test_unresolved_product_and_legal_decisions_are_explicit_and_fail_closed():
    policy = media_admission_policy()
    assert policy["activation"]["status"] == "inactive_owner_decision_required"
    assert policy["activation"]["activation_height"] is None
    assert policy["content_category_policy"]["status"] == (
        "owner_decision_required_fail_closed_before_public_minting"
    )
    assert "prohibited_content_policy_jurisdiction_and_appeals" in policy["owner_decisions"]
    assert "safety_review_authority_quorum_and_welfare" in policy["owner_decisions"]
    assert "denylist_ownership_distribution_and_activation" in policy["owner_decisions"]


def test_environment_cannot_change_consensus_policy(monkeypatch):
    digest = media_admission_policy_digest()
    monkeypatch.setenv("MAX_CONTENT_FILE_SIZE_BYTES", "999999999")
    monkeypatch.setenv("MAX_TEXT_CONTENT_BYTES", "999999999")
    monkeypatch.setenv("ENABLE_STRICT_MIME_VALIDATION", "false")
    assert media_admission_policy_digest() == digest
    assert media_admission_policy()["consensus_protocol"]["byte_limits"]["accepted_image_bytes"] == 262_144


def test_local_overrides_can_tighten_but_never_relax_defaults():
    tightened = effective_local_defense_limits({"multipart_request_body_bytes": 1000})
    assert tightened["multipart_request_body_bytes"] == 1000
    with pytest.raises(policy_module.MediaAdmissionPolicyError, match="may not relax"):
        effective_local_defense_limits({"multipart_request_body_bytes": 5_308_417})
    result = evaluate_media_admission_policy(
        PolicyEvaluationInput(request_body_bytes=1001, request_kind="multipart"),
        local_defense_overrides={"multipart_request_body_bytes": 1000},
    )
    assert result["reason_codes"] == [REASON_EXCEEDS_REQUEST_BYTE_LIMIT]


def test_historical_submission_records_remain_readable_without_policy_fields():
    historical = {
        "submission_id": "legacy-submission",
        "image_path": "legacy.jpg",
        "text_content": "",
        "submitter": "0xabc",
        "status": "pending",
        "created_at": 1.0,
        "content_hash": "a" * 64,
    }
    restored = Submission.from_dict(historical)
    assert restored.submission_id == "legacy-submission"
    assert restored.content_hash == "a" * 64
    assert "admission_policy_version" not in restored.to_dict()


def test_reason_codes_are_sorted_unique_and_stable():
    assert POLICY_REASON_CODES == tuple(sorted(POLICY_REASON_CODES))
    assert len(POLICY_REASON_CODES) == len(set(POLICY_REASON_CODES))
    assert set(POLICY_REASON_CODES) >= {
        REASON_UNKNOWN_POLICY_VERSION,
        REASON_UNSUPPORTED_MEDIA_TYPE,
        REASON_DISALLOWED_ARCHIVE,
        REASON_EXECUTABLE_OR_SCRIPT,
    }


def test_policy_level_metadata_at_limits_is_accepted_without_decoding():
    result = evaluate_media_admission_policy(PolicyEvaluationInput(
        detected_mime_type="image/webp",
        declared_mime_type="image/webp",
        accepted_media_bytes=262_144,
        staged_upload_bytes=5_242_880,
        request_body_bytes=5_308_416,
        request_kind="multipart",
        canonical_block_bytes=524_288,
        width_pixels=4_096,
        height_pixels=4_096,
        frame_count=1,
        aggregate_decoded_pixels=16_777_216,
    ))
    assert result["outcome"] == OUTCOME_ACCEPT
