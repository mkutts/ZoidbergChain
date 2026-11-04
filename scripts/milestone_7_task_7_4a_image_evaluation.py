"""Analyze image-only Task 7.4 baseline evidence without changing codecs or corpus."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import milestone_7_task_7_3_corpus as corpus

CONFIG = ROOT / "tests" / "fixtures" / "milestone_7_image_evaluation_v1_config.json"
OUTPUT = ROOT / "benchmarks" / "milestone_7_task_7_4a_image_results.json"


def percentile(values: list[float], percent: int) -> float:
    return sorted(values)[math.ceil(len(values) * percent / 100) - 1]


def jpeg_segments(payload: bytes) -> dict[str, Any]:
    """Report container structure only; never decodes or rewrites a JPEG."""
    if not payload.startswith(b"\xff\xd8"):
        raise ValueError("not a JPEG")
    position, segments, app_bytes, comment_bytes = 2, [], 0, 0
    while position + 1 < len(payload):
        if payload[position] != 0xFF:
            raise ValueError("marker alignment error")
        while position < len(payload) and payload[position] == 0xFF:
            position += 1
        marker = payload[position]
        position += 1
        if marker == 0xD9:
            break
        if marker == 0xDA:  # scan entropy data runs through EOI; its size is residual.
            break
        if marker in {0x01} or 0xD0 <= marker <= 0xD7:
            segments.append(f"FF{marker:02X}")
            continue
        if position + 2 > len(payload):
            raise ValueError("truncated segment")
        size = int.from_bytes(payload[position:position + 2], "big")
        if size < 2 or position + size > len(payload):
            raise ValueError("invalid segment length")
        data_bytes = size - 2
        name = f"FF{marker:02X}"
        segments.append(name)
        if 0xE0 <= marker <= 0xEF:
            app_bytes += data_bytes
        if marker == 0xFE:
            comment_bytes += data_bytes
        position += size
    return {"markers_before_scan": segments, "app_payload_bytes": app_bytes, "comment_payload_bytes": comment_bytes,
            "scan_and_trailer_bytes": len(payload) - position}


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    originals = sum(row["original_bytes"] for row in rows)
    effective_originals = sum(row["identity_effective_descriptor_bytes_estimate"] for row in rows)
    effective_adaptive = sum(min(row["effective_descriptor_bytes_estimate"], row["identity_effective_descriptor_bytes_estimate"]) for row in rows)
    savings = [row["savings_percent"] for row in rows]
    return {"samples": len(rows), "p50_raw_savings_percent": percentile(savings, 50), "p95_raw_savings_percent": percentile(savings, 95),
            "raw_byte_weighted_savings_percent": (1 - sum(row["encoded_bytes"] for row in rows) / originals) * 100,
            "raw_expansion_files": sum(row["expands"] for row in rows),
            "adaptive_effective_savings_percent": (1 - effective_adaptive / effective_originals) * 100,
            "effective_expansion_files": sum(row["effective_descriptor_bytes_estimate"] > row["identity_effective_descriptor_bytes_estimate"] for row in rows),
            "exact_reconstruction_successes": sum(row["reconstruction_success"] and row["sha256_match"] for row in rows),
            "aggregate_compression_mb_s": sum(row["original_bytes"] for row in rows) / sum(row["compression_ns_median"] for row in rows) * 1000,
            "aggregate_decompression_mb_s": sum(row["original_bytes"] for row in rows) / sum(row["decompression_ns_median"] for row in rows) * 1000}


def run(config: dict[str, Any]) -> dict[str, Any]:
    manifest_path = ROOT / config["corpus_manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    corpus.verify_manifest(manifest)
    baseline_path = ROOT / config["baseline_results"]
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    rows = [row for row in baseline["per_sample"] if row["candidate_id"] == config["baseline_candidate"] and row["mime_type"].startswith("image/")]
    if len(rows) != 27:
        raise ValueError("baseline image rows are incomplete")
    samples = {sample["id"]: sample for sample in corpus.build_samples()}
    jpeg_diagnostics = []
    for row in rows:
        if row["mime_type"] == "image/jpeg":
            payload = samples[row["sample_id"]]["bytes"]
            jpeg_diagnostics.append({"sample_id": row["sample_id"], "sha256": hashlib.sha256(payload).hexdigest(),
                                     "original_bytes": len(payload), "zstd_encoded_bytes": row["encoded_bytes"],
                                     "zstd_savings_percent": row["savings_percent"]} | jpeg_segments(payload))
    by_mime = {mime: aggregate([row for row in rows if row["mime_type"] == mime]) for mime in sorted({row["mime_type"] for row in rows})}
    return {"evaluation_id": config["evaluation_id"], "evaluation_version": config["evaluation_version"],
            "baseline": {"results_path": config["baseline_results"], "results_sha256": hashlib.sha256(baseline_path.read_bytes()).hexdigest(), "candidate": config["baseline_candidate"], "baseline_environment": baseline["environment"]},
            "corpus": {"id": manifest["corpus_id"], "version": manifest["corpus_version"], "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(), "composition": "27 repository-authored synthetic image containers; no independently sourced real-world additions"},
            "image_workload_assumption": config["image_workload_assumption"], "zstd3_by_mime": by_mime, "zstd3_all_images": aggregate(rows),
            "jpeg_container_diagnostics": jpeg_diagnostics, "candidates_not_executed": config["unavailable_candidates"],
            "tool_availability": {tool: shutil.which(tool) is not None for tool in ("cjxl", "djxl", "jpegtran")}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = run(json.loads(args.config.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
