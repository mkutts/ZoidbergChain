"""Offline Windows worker measurements/replay; parent never decodes media.

All outputs are bounded, source-pinned evidence, not production security signoff.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cffi
import zstandard
from codec_prototype.isolated_decoder import IsolatedDecoder, Limits, Status
from codec_prototype import worker_ipc as ipc
from codec_prototype.worker_windows import parent_memory
from scripts import milestone_7_task_7_3_corpus as corpus
from scripts.milestone_7_task_7_6_vectors import compress, descriptor
from scripts.milestone_7_task_7_6b_performance import rebuilt_table_case

BASELINE = "86838da59d41964d8a0714720bdbf6d44a98a239"
OUTPUT = ROOT / "benchmarks/milestone_7_task_7_6c_results.json"
SOURCES = ("codec_prototype/isolated_decoder.py", "codec_prototype/worker_windows.py",
           "codec_prototype/worker_entry.py", "codec_prototype/worker_ipc.py",
           "codec_prototype/strict_decoder.py", "codec_prototype/sequence_verifier.py",
           "scripts/milestone_7_task_7_6c_isolation.py", "tests/helpers/decoder_worker_fixture.py")


def summary(values):
    return dict(samples=values, median=statistics.median(values),
                p95=sorted(values)[(95 * len(values) + 99) // 100 - 1], worst=max(values))


def successful(pool, raw, original):
    result = pool.validate(raw)
    if result.status != Status.VALID or result.original != original or not result.metrics.get("reaped"):
        raise ValueError(f"worker validation failed: {result.status}, {result.reason}, {result.metrics}")
    return result


def cases():
    samples = corpus.build_samples()
    manifest_raw = corpus.MANIFEST_PATH.read_bytes()
    records = {r["id"]: r for r in json.loads(manifest_raw)["samples"]}
    corpus_cases = []
    for sample in samples:
        original = sample["bytes"]
        assert hashlib.sha256(original).hexdigest() == records[sample["id"]]["sha256"]
        corpus_cases.append(dict(id=sample["id"], original=original,
                                 raw=ipc.canonical(descriptor(original, compress(original), mime=sample["mime_type"]))))
    wanted = {"jpeg-flat-small", "jpeg-mixed-medium", "png-noise-capacity"}
    measured = [c for c in corpus_cases if c["id"] in wanted]
    for name, codec_id in (("high-ratio-at-A", "zstd"), ("identity-at-A", "identity")):
        original = b"x" * ipc.MAX_OUTPUT
        encoded = original if codec_id == "identity" else compress(original)
        measured.append(dict(id=name, original=original, raw=ipc.canonical(descriptor(original, encoded, codec_id))))
    directory = ROOT / "tests/fixtures/milestone_7_codec_v2"
    meta = json.loads((directory / "manifest.json").read_bytes())
    item = next(v for v in meta["vectors"] if v["id"] == "short-matches-at-frame-A")
    measured.append(dict(id=item["id"], original=(directory / item["original_path"]).read_bytes(),
                         raw=(directory / item["descriptor_path"]).read_bytes()))
    rebuilt = rebuilt_table_case()
    measured.append(dict(id=rebuilt["id"], original=rebuilt["original"], raw=ipc.canonical(rebuilt["descriptor"])))
    return corpus_cases, measured, hashlib.sha256(manifest_raw).hexdigest()


def replay(pool):
    rows, manifests = [], {}
    for folder in ("milestone_7_codec_v1", "milestone_7_codec_v2"):
        directory = ROOT / "tests/fixtures" / folder
        manifest_raw = (directory / "manifest.json").read_bytes()
        digest = hashlib.sha256(manifest_raw).hexdigest()
        assert digest == (directory / "manifest.sha256").read_text().strip()
        manifests[folder] = digest
        for item in json.loads(manifest_raw)["vectors"]:
            raw = (directory / item["descriptor_path"]).read_bytes()
            original = (directory / item["original_path"]).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == item["descriptor_sha256"]
            assert hashlib.sha256(original).hexdigest() == item["original_sha256"]
            result = pool.validate(raw)
            expected = item.get("profile_expected", item["expected"])
            code, stage = item["code"], item["stage"]
            if item["id"] == "offset-exceeds-declared-window":
                code, stage = "window_offset", "decode"
            if expected == "accept":
                assert result.status == Status.VALID and result.original == original
            else:
                assert (result.status, result.code, result.stage) == (Status.INVALID, code, stage), (item["id"], result)
            assert result.metrics.get("reaped")
            rows.append(dict(id=item["id"], suite=folder, status=result.status.value, code=result.code, stage=result.stage,
                             exact_bytes=result.original == original if expected == "accept" else None,
                             metrics=result.metrics))
    return dict(total=len(rows), counts=dict(Counter(r["status"] for r in rows)), rows=rows,
                manifest_sha256=manifests, independent_implementation=False)


class ControlledWorker(IsolatedDecoder):
    """Fixed trusted fault fixture, available only in this offline runner."""
    def __init__(self, mode, **kwargs):
        super().__init__(**kwargs)
        self.mode = mode

    def _command(self):
        return [sys._base_executable, "-I", "-u", str(ROOT / "tests/helpers/decoder_worker_fixture.py"),
                str(Path(sys.prefix) / "Lib/site-packages"), self.mode]


def run(repetitions):
    if os.name != "nt":
        raise RuntimeError("Actual Windows Job Object execution is required; Linux is not implemented/tested")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    assert head == BASELINE, "unexpected baseline commit"
    corpus_cases, measured, corpus_hash = cases()
    historical_raw = (ROOT / "benchmarks/milestone_7_task_7_6b_results.json").read_bytes()
    historical = {r["id"]: r for r in json.loads(historical_raw)["per_case"]}
    rows = []
    with IsolatedDecoder(max_workers=2) as pool:
        for case in measured:
            successful(pool, case["raw"], case["original"])
            parent_before = parent_memory()
            results = [successful(pool, case["raw"], case["original"]) for _ in range(repetitions)]
            metrics = [r.metrics for r in results]
            keys = ("total_ns", "startup_ns", "exchange_ns", "worker_parse_ns", "worker_decode_ns", "cleanup_ns",
                    "process_user_ns", "process_kernel_ns", "peak_job_commit_bytes", "peak_process_commit_bytes")
            row = dict(id=case["id"], original_bytes=len(case["original"]), request_bytes=len(case["raw"]),
                       original_sha256=hashlib.sha256(case["original"]).hexdigest(),
                       request_sha256=hashlib.sha256(case["raw"]).hexdigest(), exact_reconstruction=True,
                       metrics=metrics, summaries={k: summary([m[k] for m in metrics]) for k in keys},
                       exchange_minus_worker_work_ns=summary([max(0, m["exchange_ns"] - m["worker_parse_ns"] - m["worker_decode_ns"]) for m in metrics]),
                       parent_memory_before=parent_before, parent_memory_after=parent_memory())
            if case["id"] in historical:
                row["historical_76b_inprocess_after"] = historical[case["id"]]["total"]["after"]
            rows.append(row)
            print(f"measured {case['id']}", flush=True)
        # Finite, trusted harness batch; only two calls are submitted at a time
        # by executor threads. The worker interface itself has no job queue.
        small = next(c for c in measured if c["id"] == "jpeg-flat-small")
        throughputs = []
        for concurrency in (1, 2):
            timings, batches = [], []
            for _ in range(repetitions):
                started = time.perf_counter_ns()
                with ThreadPoolExecutor(max_workers=concurrency) as threads:
                    results = list(threads.map(lambda _: successful(pool, small["raw"], small["original"]), range(8)))
                elapsed = time.perf_counter_ns() - started
                timings.append(elapsed)
                batches.append(dict(elapsed_ns=elapsed, jobs_per_second=8e9 / elapsed,
                                    pids=[r.metrics["pid"] for r in results]))
            throughputs.append(dict(concurrency=concurrency, jobs_per_batch=8, batches=batches, elapsed_ns=summary(timings)))
        golden = replay(pool)
        corpus_rows = []
        for case in corpus_cases:
            result = successful(pool, case["raw"], case["original"])
            corpus_rows.append(dict(id=case["id"], exact_bytes=True, metrics=result.metrics))
        # Parent-only tracing after latency runs; no tracing inside the child.
        memory = []
        for name in ("identity-at-A", "short-matches-at-frame-A"):
            case = next(c for c in measured if c["id"] == name)
            tracemalloc.start()
            try:
                result = successful(pool, case["raw"], case["original"])
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            memory.append(dict(id=name, parent_traced_peak_bytes=peak, metrics=result.metrics))
    fault_rows = []
    raw = ipc.canonical(descriptor(b"abc", b"abc", "identity"))
    for mode in ("crash", "hang", "spin", "allocate", "spawn_child"):
        limits = Limits(memory_bytes=32 * 1024**2, cpu_seconds=0.2, wall_seconds=3 if mode == "spin" else 0.2)
        with ControlledWorker(mode, limits=limits) as pool:
            outcome = pool.validate(raw)
            assert outcome.status == Status.INDETERMINATE_LOCAL_FAILURE and outcome.metrics.get("reaped")
            fault_rows.append(dict(mode=mode, status=outcome.status.value, reason=outcome.reason, metrics=outcome.metrics))
    return dict(task="7.6C", baseline_head=BASELINE, limits=asdict(Limits()),
                global_concurrency=2, queued_requests=0, platform_tested="Windows only",
                source_sha256={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES},
                historical_76b_sha256=hashlib.sha256(historical_raw).hexdigest(),
                environment=dict(python=sys.version, platform=platform.platform(), zstandard=zstandard.__version__,
                                 libzstd=list(zstandard.ZSTD_VERSION), cffi=cffi.__version__),
                methodology=dict(repetitions=repetitions, warmup_jobs=1, p95="nearest rank; equals maximum with three samples",
                                 scope="Parent never decodes; worker_decode_ns measures current strict decode inside the bounded child",
                                 comparison="Task 7.6B historical host timings are not a paired stationary baseline",
                                 ipc="exchange minus worker JSON/decoder time includes IPC, EOF/exit, allocation and scheduling",
                                 memory="Job counters measure Windows commit, not physical RSS; parent working-set peak is cumulative; Python trace excludes input already held by caller and native allocations"),
                per_case=rows, throughput=throughputs, golden=golden,
                corpus=dict(samples=len(corpus_rows), manifest_sha256=corpus_hash, rows=corpus_rows),
                memory_probes=memory, faults=fault_rows, independent_decoder=False, linux_enforcement=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--repetitions", type=int, default=3, choices=(3, 5))
    args = parser.parse_args()
    result = run(args.repetitions)
    args.output.write_bytes(json.dumps(result, sort_keys=True, indent=2).encode() + b"\n")
    print(f"wrote {args.output}; golden={result['golden']['counts']}, corpus={result['corpus']['samples']}")
