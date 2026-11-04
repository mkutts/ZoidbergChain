"""Retained paired evidence must describe the final sources and exact inputs."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_paired_worker_evidence_matches_sources_and_protocol_results():
    reports = [json.loads((ROOT / f"benchmarks/milestone_7_task_7_6d_{name}_results.json").read_bytes())
               for name in ("linux", "windows")]
    linux, windows = reports
    for report in reports:
        assert report["baseline_head"] == "8607636cc13d1c78c73de3da09fa8d149f8af0f0"
        for path, digest in report["source_sha256"].items():
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
        assert report["golden"]["counts"] == {"VALID": 42, "INVALID": 110}
        assert report["corpus"]["samples"] == 36 and report["corpus"]["streams"] == 72
        assert all(row["exact_bytes"] and row["metrics"]["reaped"] for row in report["corpus"]["rows"])
        assert all(row["status"] == "INDETERMINATE_LOCAL_FAILURE" and row["metrics"]["reaped"]
                   for row in report["faults"])
        assert report["global_concurrency"] == 2 and report["queued_requests"] == 0
        assert not report["independent_decoder"] and not report["production_security_approved"]
    assert linux["input_bundle_sha256"] == windows["input_bundle_sha256"]
    assert linux["source_sha256"] == windows["source_sha256"]
    assert [(row["id"], row["status"], row["stage"], row["code"])
            for row in linux["golden"]["rows"]] == [
                (row["id"], row["status"], row["stage"], row["code"]) for row in windows["golden"]["rows"]]
    for key in ("per_case",):
        assert [(row["id"], row["request_sha256"]) for row in linux[key]] == [
            (row["id"], row["request_sha256"]) for row in windows[key]]
    assert [(row["id"], row["encoding"], row["request_sha256"]) for row in linux["corpus"]["rows"]] == [
        (row["id"], row["encoding"], row["request_sha256"]) for row in windows["corpus"]["rows"]]
