"""Offline cross-platform replay and per-request measurements for Task 7.6D."""
from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import sysconfig
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cffi
import PIL
import zstandard
from codec_prototype.isolated_decoder import IsolatedDecoder, Limits, Status
from codec_prototype import worker_ipc as ipc
from scripts.milestone_7_task_7_6_vectors import descriptor
from scripts.milestone_7_task_7_6c_isolation import cases, replay, successful, summary, ControlledWorker

BASELINE = "8607636cc13d1c78c73de3da09fa8d149f8af0f0"
SOURCES = ("codec_prototype/isolated_decoder.py", "codec_prototype/worker_entry.py",
           "codec_prototype/worker_linux.py", "codec_prototype/worker_linux_entry.py",
           "codec_prototype/worker_windows.py", "codec_prototype/worker_ipc.py",
           "codec_prototype/strict_decoder.py", "codec_prototype/sequence_verifier.py",
           "scripts/milestone_7_task_7_6d_isolation.py", "scripts/milestone_7_task_7_6c_isolation.py",
           "tests/helpers/linux_decoder_worker_fixture.py", "tests/helpers/decoder_worker_fixture.py",
           "tests/test_milestone_7_task_7_6d_linux_isolation.py", "tests/test_milestone_7_task_7_6d_evidence.py",
           "tests/test_milestone_7_task_7_6c_isolation.py")


class LinuxProbe(IsolatedDecoder):
    def __init__(self, mode, **kwargs):
        super().__init__(**kwargs)
        self.mode = mode

    def _command(self):
        return [sys.executable, "-I", "-u", str(ROOT / "tests/helpers/linux_decoder_worker_fixture.py"),
                str(os.getpid()), str(self.limits.memory_bytes), str(self.limits.cpu_seconds),
                sysconfig.get_path("purelib"), self.mode, str(threading.get_native_id())]


def get_cases(bundle=None):
    """Portable trusted replay inputs: never regenerate/re-freeze the manifest.

    Pillow/native image encoders differ across OS builds. Export the existing
    manifest-matching bytes on the reference environment, then replay exactly
    the same originals AND canonical descriptors on the other platform.
    """
    if bundle is None:
        return cases()
    data = json.loads(Path(bundle).read_bytes())
    manifest_raw = (ROOT / "tests/fixtures/milestone_7_corpus_v1_manifest.json").read_bytes()
    digest = hashlib.sha256(manifest_raw).hexdigest()
    assert data["manifest_sha256"] == digest and data["version"] == 1
    def unpack(rows):
        return [dict(id=row["id"], original=base64.b64decode(row["original"], validate=True),
                     raw=row["raw"].encode("ascii")) for row in rows]
    corpus_cases, measured = unpack(data["corpus"]), unpack(data["measured"])
    expected = {row["id"]: row["sha256"] for row in json.loads(manifest_raw)["samples"]}
    assert len(corpus_cases) == len(expected) == 36 and len(measured) == 7
    assert {row["id"] for row in corpus_cases} == set(expected)
    for row in corpus_cases + measured:
        original_hash = hashlib.sha256(row["original"]).hexdigest()
        desc = json.loads(row["raw"])
        assert desc["original_sha256"] == original_hash and desc["original_size"] == len(row["original"])
        assert row["raw"] == ipc.canonical(desc)
        if row in corpus_cases:
            assert original_hash == expected[row["id"]]
    return corpus_cases, measured, digest


def export_inputs(destination):
    corpus_cases, measured, digest = get_cases()
    def pack(rows):
        return [dict(id=row["id"], original=base64.b64encode(row["original"]).decode("ascii"),
                     raw=row["raw"].decode("ascii")) for row in rows]
    Path(destination).write_bytes(ipc.canonical(dict(version=1, manifest_sha256=digest,
        corpus=pack(corpus_cases), measured=pack(measured))) + b"\n")


def run(repetitions, bundle=None):
    if sys.platform != "linux" and os.name != "nt":
        raise RuntimeError("Actual Windows or Linux execution required")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    if head != BASELINE:
        raise RuntimeError("Unexpected baseline commit")
    corpus_cases, measured, corpus_hash = get_cases(bundle)
    keys = ("total_ns", "startup_ns", "exchange_ns", "worker_parse_ns", "worker_decode_ns", "cleanup_ns",
            "process_user_ns", "process_kernel_ns")
    keys += ("peak_rss_bytes",) if sys.platform == "linux" else ("peak_job_commit_bytes",)
    rows, batches, corpus_rows = [], [], []
    with IsolatedDecoder(max_workers=2) as pool:
        for case in measured:
            successful(pool, case["raw"], case["original"])
            results = [successful(pool, case["raw"], case["original"]) for _ in range(repetitions)]
            rows.append(dict(id=case["id"], original_bytes=len(case["original"]),
                request_sha256=hashlib.sha256(case["raw"]).hexdigest(),
                original_sha256=hashlib.sha256(case["original"]).hexdigest(),
                exact_bytes=True, metrics=[r.metrics for r in results],
                summaries={key: summary([r.metrics[key] for r in results]) for key in keys}))
            print("measured", case["id"], flush=True)
        small = next(case for case in measured if case["id"] == "jpeg-flat-small")
        for concurrency in (1, 2):
            samples = []
            for _ in range(repetitions):
                started = time.perf_counter_ns()
                with ThreadPoolExecutor(max_workers=concurrency) as threads:
                    results = list(threads.map(lambda _: successful(pool, small["raw"], small["original"]), range(8)))
                elapsed = time.perf_counter_ns() - started
                samples.append(dict(elapsed_ns=elapsed, jobs_per_second=8e9 / elapsed,
                                    reaped=all(r.metrics["reaped"] for r in results)))
            batches.append(dict(concurrency=concurrency, jobs=8, samples=samples))
        golden = replay(pool)
        for case in corpus_cases:
            originals = case["original"]
            representations = {"zstd": case["raw"],
                               "identity": ipc.canonical(descriptor(originals, originals, "identity"))}
            for encoding, raw in representations.items():
                result = successful(pool, raw, originals)
                corpus_rows.append(dict(id=case["id"], encoding=encoding, exact_bytes=True,
                    request_sha256=hashlib.sha256(raw).hexdigest(), metrics=result.metrics))
    faults = []
    modes = ["crash", "hang", "spin", "allocate", "spawn_child"]
    probe = LinuxProbe if sys.platform == "linux" else ControlledWorker
    if sys.platform == "linux":
        modes += ["filesystem", "network", "privilege", "descriptors", "limits", "allocate_native", "missing_seccomp"]
    raw = ipc.canonical(descriptor(b"abc", b"abc", "identity"))
    for mode in modes:
        limits = Limits(memory_bytes=48 * 1024**2, cpu_seconds=0.2 if mode == "spin" else 5,
                        wall_seconds=3 if mode == "spin" else 0.3)
        with probe(mode, limits=limits) as pool:
            result = pool.validate(raw)
        assert result.status == Status.INDETERMINATE_LOCAL_FAILURE and result.metrics.get("reaped"), (mode, result)
        faults.append(dict(mode=mode, status=result.status.value, reason=result.reason, metrics=result.metrics))
    historical = (ROOT / "benchmarks/milestone_7_task_7_6c_results.json").read_bytes()
    return dict(task="7.6D", baseline_head=head,
        environment=dict(python=sys.version, platform=platform.platform(), machine=platform.machine(),
            zstandard=zstandard.__version__, libzstd=list(zstandard.ZSTD_VERSION),
            cffi=cffi.__version__, pillow=PIL.__version__),
        limits=asdict(Limits()), source_sha256={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES},
        historical_windows_76c_sha256=hashlib.sha256(historical).hexdigest(),
        input_bundle_sha256=hashlib.sha256(Path(bundle).read_bytes()).hexdigest() if bundle else None,
        methodology=dict(repetitions=repetitions, warmup_jobs=1, p95="nearest rank; equals maximum at n=3",
            linux_memory="wait4 whole-child lifetime peak RSS, includes native/interpreter and pre-exec fork accounting; not an isolated decoder allocator peak, address-space limit, or Windows commit",
            cpu="Linux user+system; Windows user budget, both times recorded",
            comparison="WSL2 Linux CPython 3.12 and Windows CPython 3.13 on shared hardware; no native Ubuntu performance claim"),
        global_concurrency=2, queued_requests=0, independent_decoder=False,
        per_case=rows, throughput=batches, golden=golden,
        corpus=dict(samples=len(corpus_cases), streams=len(corpus_rows), manifest_sha256=corpus_hash, rows=corpus_rows),
        faults=faults, production_security_approved=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--inputs", type=Path, help="trusted reference-environment replay bundle")
    parser.add_argument("--export-inputs", type=Path, help="export manifest-matching reference inputs, then exit")
    parser.add_argument("--repetitions", type=int, default=3, choices=(3, 5))
    args = parser.parse_args()
    if args.export_inputs:
        export_inputs(args.export_inputs)
        print("exported reference inputs", args.export_inputs)
        raise SystemExit(0)
    if args.output is None:
        parser.error("--output is required for measurements")
    report = run(args.repetitions, args.inputs)
    args.output.write_bytes(json.dumps(report, sort_keys=True, indent=2).encode() + b"\n")
    print("wrote", args.output, report["golden"]["counts"], "corpus streams", report["corpus"]["streams"])
