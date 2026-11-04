import json

from scripts import milestone_7_task_7_4a_image_evaluation as evaluation


def test_jpeg_parser_reports_container_sections_without_transforming_bytes():
    payload = next(sample["bytes"] for sample in evaluation.corpus.build_samples() if sample["id"] == "jpeg-flat-small")
    report = evaluation.jpeg_segments(payload)
    assert report["markers_before_scan"]
    assert report["scan_and_trailer_bytes"] > 0


def test_image_evaluation_reuses_verified_baseline_and_preserves_identity_requirements():
    result = evaluation.run(json.loads(evaluation.CONFIG.read_text(encoding="utf-8")))
    assert result["zstd3_all_images"]["exact_reconstruction_successes"] == 27
    assert set(result["zstd3_by_mime"]) == {"image/gif", "image/jpeg", "image/png", "image/webp"}
    assert all(item["status"] != "tested" for item in result["candidates_not_executed"])
