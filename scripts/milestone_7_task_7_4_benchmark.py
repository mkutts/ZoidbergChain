"""Run the bounded, reproducible Milestone 7.4 lossless codec benchmark.

This is measurement tooling, not a production codec implementation.  It emits
per-sample JSON and an aggregate JSON summary suitable for baseline comparison.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import platform
import statistics
import sys
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import brotli
import zstandard
from scripts import milestone_7_task_7_3_corpus as corpus

CONFIG_PATH = PROJECT_ROOT / "tests" / "fixtures" / "milestone_7_benchmark_v1_config.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "benchmarks" / "milestone_7_task_7_4_results.json"


def _percentile(values: list[float | int], percent: int) -> float | int:
    ordered = sorted(values)
    return ordered[(len(ordered) * percent + 99) // 100 - 1]


def _descriptor_size(payload: bytes, sample: dict[str, Any], codec_id: str) -> int:
    """Exact UTF-8 descriptor size under the proposed v3 media-object schema only."""
    descriptor = {
        "codec_id": codec_id, "codec_version": 1, "encoding_version": 1,
        "mime_type": sample["mime_type"], "original_sha256": hashlib.sha256(sample["bytes"]).hexdigest(),
        "original_size": len(sample["bytes"]), "payload": base64.b64encode(payload).decode("ascii"),
        "stored_size": len(payload),
    }
    return len(json.dumps(descriptor, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))


def _operations(candidate: dict[str, Any]) -> tuple[Callable[[bytes], bytes], Callable[[bytes], bytes], dict[str, Any]]:
    codec = candidate["codec"]
    if codec == "identity":
        return bytes, bytes, {"framing": "none; E equals M", "window": 0, "compatibility": "Python bytes copy; no external decoder"}
    if codec == "zstd":
        level = candidate["level"]
        parameters = zstandard.ZstdCompressionParameters.from_level(
            level, window_log=18, write_checksum=1, write_content_size=1, write_dict_id=0, threads=0)
        compressor = zstandard.ZstdCompressor(compression_params=parameters)
        decompressor = zstandard.ZstdDecompressor()
        return compressor.compress, decompressor.decompress, {"framing": "one Zstandard frame; checksum and content size required by benchmark encoder", "window": "window_log=18 (256 KiB); decoder limit is not enforced by this harness", "compatibility": "Zstandard frame format; Python zstandard 0.25.0"}
    if codec == "brotli":
        level = candidate["level"]
        return (lambda data: brotli.compress(data, mode=brotli.MODE_GENERIC, quality=level, lgwin=18), brotli.decompress,
                {"framing": "one Brotli stream", "window": "lgwin=18 (256 KiB)", "compatibility": "RFC 7932 Brotli stream; Python Brotli 1.2.0"})
    if codec == "zlib":
        return (lambda data: zlib.compress(data, level=candidate["level"], wbits=15), lambda data: zlib.decompress(data, wbits=15),
                {"framing": "one zlib-wrapped DEFLATE stream", "window": "wbits=15 (32 KiB)", "compatibility": "zlib wrapper; Python stdlib linked zlib"})
    raise ValueError(f"unknown candidate {codec}")


def _timed(operation: Callable[[bytes], bytes], value: bytes, repetitions: int, warmups: int) -> tuple[bytes, list[int]]:
    for _ in range(warmups):
        operation(value)
    timings: list[int] = []
    output = b""
    for _ in range(repetitions):
        started = time.perf_counter_ns()
        output = operation(value)
        timings.append(time.perf_counter_ns() - started)
    return output, timings


def _rate(byte_count: int, nanoseconds: float) -> float:
    return 0.0 if not nanoseconds else byte_count / (nanoseconds / 1_000_000_000) / 1_000_000


def _aggregate(rows: list[dict[str, Any]], members: list[dict[str, Any]]) -> dict[str, Any]:
    selected = [row for row in rows if row["sample_id"] in {item["id"] for item in members}]
    originals = sum(row["original_bytes"] for row in selected)
    encoded = sum(row["encoded_bytes"] for row in selected)
    adaptive = sum(min(row["encoded_bytes"], row["original_bytes"]) for row in selected)
    raw_effective = sum(row["identity_effective_descriptor_bytes_estimate"] for row in selected)
    effective = sum(row["effective_descriptor_bytes_estimate"] for row in selected)
    adaptive_effective = sum(min(row["effective_descriptor_bytes_estimate"], row["identity_effective_descriptor_bytes_estimate"]) for row in selected)
    savings = [row["savings_percent"] for row in selected]
    original_sizes = [row["original_bytes"] for row in selected]
    encoded_sizes = [row["encoded_bytes"] for row in selected]
    compression_ns = sum(row["compression_ns_median"] for row in selected)
    decompression_ns = sum(row["decompression_ns_median"] for row in selected)
    return ({"samples": len(selected), "original_bytes": originals, "encoded_bytes": encoded,
            "byte_weighted_savings_percent": (1 - encoded / originals) * 100 if originals else 0,
            "p50_savings_percent": _percentile(savings, 50), "p95_savings_percent": _percentile(savings, 95),
            "original_size_distribution_bytes": {"p50": _percentile(original_sizes, 50), "p95": _percentile(original_sizes, 95), "p99": _percentile(original_sizes, 99), "max": max(original_sizes)},
            "encoded_size_distribution_bytes": {"p50": _percentile(encoded_sizes, 50), "p95": _percentile(encoded_sizes, 95), "p99": _percentile(encoded_sizes, 99), "max": max(encoded_sizes)},
            "aggregate_compression_mb_s_from_medians": _rate(originals, compression_ns), "aggregate_decompression_mb_s_from_medians": _rate(originals, decompression_ns),
            "worst_savings_percent": min(savings), "expanding_files": sum(row["expands"] for row in selected),
            "benefiting_files": sum(row["encoded_bytes"] < row["original_bytes"] for row in selected),
            "adaptive_encoded_bytes": adaptive, "adaptive_savings_percent": (1 - adaptive / originals) * 100 if originals else 0}
            | {"identity_effective_descriptor_bytes_estimate": raw_effective, "effective_descriptor_bytes_estimate": effective,
               "effective_descriptor_savings_percent": (1 - effective / raw_effective) * 100 if raw_effective else 0,
               "adaptive_effective_descriptor_bytes_estimate": adaptive_effective,
               "adaptive_effective_descriptor_savings_percent": (1 - adaptive_effective / raw_effective) * 100 if raw_effective else 0,
               "effective_expanding_files": sum(row["effective_descriptor_bytes_estimate"] > row["identity_effective_descriptor_bytes_estimate"] for row in selected)})


def run(config: dict[str, Any]) -> dict[str, Any]:
    manifest = json.loads((PROJECT_ROOT / config["corpus_manifest"]).read_text(encoding="utf-8"))
    if corpus.make_manifest() != manifest:
        raise ValueError("corpus manifest does not regenerate; refusing benchmark")
    generated = {sample["id"]: sample for sample in corpus.build_samples()}
    rows: list[dict[str, Any]] = []
    profiles: list[dict[str, Any]] = []
    for candidate in config["candidates"]:
        encode, decode, details = _operations(candidate)
        profiles.append(candidate | details)
        for record in manifest["samples"]:
            sample = generated[record["id"]]
            original = sample["bytes"]
            encoded, enc_times = _timed(encode, original, config["timed_repetitions"], config["warmup_iterations"])
            decoded, dec_times = _timed(decode, encoded, config["timed_repetitions"], config["warmup_iterations"])
            success = decoded == original
            if not success or hashlib.sha256(decoded).hexdigest() != record["sha256"]:
                raise ValueError(f"lossless verification failed: {candidate['id']} / {record['id']}")
            enc_median, dec_median = statistics.median(enc_times), statistics.median(dec_times)
            rows.append({"candidate_id": candidate["id"], "codec": candidate["codec"], "level": candidate.get("level"),
                         "sample_id": record["id"], "mime_type": record["mime_type"], "category": record["category"],
                         "benchmark_scoring": record["benchmark_scoring"], "capacity_analysis": record["capacity_analysis"],
                         "original_bytes": len(original), "original_sha256": record["sha256"], "encoded_bytes": len(encoded),
                         "effective_descriptor_bytes_estimate": _descriptor_size(encoded, sample, candidate["codec"]),
                         "identity_effective_descriptor_bytes_estimate": _descriptor_size(original, sample, "identity"),
                         "savings_percent": (1 - len(encoded) / len(original)) * 100,
                         "expands": len(encoded) > len(original), "reconstruction_success": success, "sha256_match": True,
                         "compression_ns_median": enc_median, "compression_ns_p95": _percentile(enc_times, 95),
                         "decompression_ns_median": dec_median, "decompression_ns_p95": _percentile(dec_times, 95),
                         "compression_mb_s_median": _rate(len(original), enc_median), "decompression_mb_s_median": _rate(len(original), dec_median),
                         "peak_memory_bytes": None, "peak_memory_note": "not reported: Python tracemalloc cannot reliably measure native codec allocations"})
    aggregates: dict[str, Any] = {}
    for candidate in config["candidates"]:
        candidate_rows = [row for row in rows if row["candidate_id"] == candidate["id"]]
        groups = {"all": manifest["samples"], "primary_scoring": [s for s in manifest["samples"] if s["benchmark_scoring"]],
                  "in_limit_images": [s for s in manifest["samples"] if s["mime_type"].startswith("image/") and s["benchmark_scoring"]],
                  "oversized_images": [s for s in manifest["samples"] if s["mime_type"].startswith("image/") and not s["benchmark_scoring"]],
                  "all_images": [s for s in manifest["samples"] if s["mime_type"].startswith("image/")]}
        for mime in sorted({s["mime_type"] for s in manifest["samples"]}): groups[f"mime:{mime}"] = [s for s in manifest["samples"] if s["mime_type"] == mime]
        for category in sorted({s["category"] for s in manifest["samples"]}): groups[f"category:{category}"] = [s for s in manifest["samples"] if s["category"] == category]
        aggregates[candidate["id"]] = {name: _aggregate(candidate_rows, members) for name, members in groups.items()}
    return {"benchmark_id": config["benchmark_id"], "benchmark_version": config["benchmark_version"], "executed_at_utc": datetime.now(timezone.utc).isoformat(),
            "environment": {"python": sys.version, "platform": platform.platform(), "zstandard": zstandard.__version__, "brotli": brotli.__version__, "zlib": zlib.ZLIB_VERSION},
            "methodology": {"warmup_iterations": config["warmup_iterations"], "timed_repetitions": config["timed_repetitions"], "clock": "time.perf_counter_ns; per-operation samples; median and nearest-rank p95", "excluded_from_timing": "imports, corpus generation/verification, result serialization, and environment setup", "memory": "not reported where native allocations cannot be measured reliably"},
            "corpus": {"id": manifest["corpus_id"], "version": manifest["corpus_version"], "manifest_sha256": hashlib.sha256((PROJECT_ROOT / config["corpus_manifest"]).read_bytes()).hexdigest(), "verified": True},
            "canonical_storage_estimate": config["canonical_storage_estimate"], "profiles": profiles, "per_sample": rows, "aggregates": aggregates}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    result = run(config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({len(result['per_sample'])} per-sample rows)")

if __name__ == "__main__":
    main()
