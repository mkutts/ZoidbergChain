"""Focused verification for the Task 7.3 representative media corpus."""

from __future__ import annotations

import hashlib
import io
import json

import pytest
from PIL import Image

from protocol_v1_genesis import canonical_public_testnet_v1_genesis_media_bytes
from scripts import milestone_7_task_7_3_corpus as corpus


def _manifest():
    return json.loads(corpus.MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_regenerates_byte_for_byte_and_has_expected_supported_inventory():
    manifest = _manifest()
    # Frozen observations describe the pre-7.12 image worker. Source identity,
    # field inventory, encoder environment and ordering must still match exactly.
    corpus.verify_manifest(manifest)
    counts = {}
    for sample in manifest["samples"]:
        counts[sample["mime_type"]] = counts.get(sample["mime_type"], 0) + 1
    assert counts == {"text/plain": 9, "image/jpeg": 7, "image/png": 7, "image/webp": 7, "image/gif": 6}


def test_every_manifest_hash_size_and_image_dimension_matches_generated_bytes():
    generated = {sample["id"]: sample for sample in corpus.build_samples()}
    for record in _manifest()["samples"]:
        payload = generated[record["id"]]["bytes"]
        assert len(payload) == record["original_byte_size"]
        assert hashlib.sha256(payload).hexdigest() == record["sha256"]
        if record["dimensions"]:
            with Image.open(io.BytesIO(payload)) as image:
                assert list(image.size) == record["dimensions"]
                image.verify()


def test_scoring_corpus_excludes_capacity_only_and_has_no_corrupt_samples():
    records = _manifest()["samples"]
    scoring = [record for record in records if record["benchmark_scoring"]]
    assert scoring
    assert all(record["category"] != "corrupt_or_adversarial" for record in records)
    assert all(record["container_decode_status"] != "invalid" for record in records)
    assert all(record["complexity"] for record in scoring)
    assert any(not record["benchmark_scoring"] and record["capacity_analysis"] for record in records)
    assert all(not record["benchmark_scoring"] for record in records if record["original_byte_size"] > corpus.PROVISIONAL_MEDIA_LIMIT)


def test_percentiles_and_provisional_limit_exclusions_use_original_image_bytes_only():
    manifest = _manifest()
    stats = corpus.image_statistics(manifest)
    assert corpus.percentile([1, 2, 3, 4], 50) == 2
    assert corpus.percentile([1, 2, 3, 4], 95) == 4
    assert stats["image_count"] == 27
    assert stats["excluded_by_original_media_limit_count"] == 5
    assert stats["excluded_by_encoded_media_limit_count"] == 5
    assert stats["requires_block_overhead_measurement"] is True
    assert "compression" not in " ".join(stats.keys()).lower()


def test_text_json_and_code_are_independent_text_plain_benchmark_categories_with_size_range():
    records = _manifest()["samples"]
    for category in ("plain_text", "structured_metadata_json", "source_code"):
        members = [record for record in records if record["category"] == category]
        assert len(members) == 3
        assert {record["mime_type"] for record in members} == {"text/plain"}
        assert max(record["original_byte_size"] for record in members) > min(record["original_byte_size"] for record in members)
        assert all(record["current_validator_status"] == "accepted" for record in members)


def test_each_image_mime_has_small_medium_and_large_representative_dimensions():
    records = _manifest()["samples"]
    for mime_type in ("image/jpeg", "image/png", "image/webp", "image/gif"):
        widths = [record["dimensions"][0] for record in records if record["mime_type"] == mime_type]
        assert min(widths) <= 480
        assert any(600 <= width <= 960 for width in widths)
        assert max(widths) >= 1024


def test_validator_environment_outcome_is_recorded_without_calling_invalid_images_valid():
    records = _manifest()["samples"]
    image_records = [record for record in records if record["mime_type"].startswith("image/")]
    assert all(record["container_decode_status"] == "valid_pillow_decode" for record in image_records)
    assert any(record["current_validator_status"] == "rejected_environment_isolation" for record in image_records)
    assert all(record["current_validator_status"] in {"accepted", "rejected_policy", "rejected_environment_isolation"} for record in records)


def test_frozen_genesis_jpeg_is_valid_and_current_validator_preserves_exact_bytes():
    payload = canonical_public_testnet_v1_genesis_media_bytes()
    with Image.open(io.BytesIO(payload)) as image:
        assert image.format == "JPEG"
        image.verify()
    from media_technical_validation import validate_media_bytes
    validated = validate_media_bytes(payload, declared_mime_type="image/jpeg")
    assert validated.raw_media_bytes == payload
    assert validated.result["raw_media_sha256"] == hashlib.sha256(payload).hexdigest()
    assert validated.result["detected_mime_type"] == "image/jpeg"
    assert validated.result["outcome"] == "ACCEPT"
