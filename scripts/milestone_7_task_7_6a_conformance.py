"""Task 7.6A bounded evidence runner; no production state or codec registration."""
import argparse
import base64
import hashlib
import json
import platform
import statistics
import sys
import time
import tracemalloc
from collections import Counter
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cffi
import zstandard as z
from codec_prototype import strict_decoder as codec
from scripts import milestone_7_task_7_3_corpus as corpus
from scripts.milestone_7_task_7_6_vectors import DEST as V1, compress, descriptor, frame
from scripts.milestone_7_task_7_6a_vectors import DEST as V2

OUTPUT = ROOT / "benchmarks/milestone_7_task_7_6a_results.json"


def measure(operation, repetitions=5, warmups=1):
    for _ in range(warmups):
        operation()
    wall, cpu = [], []
    for _ in range(repetitions):
        start_cpu, start = time.process_time_ns(), time.perf_counter_ns()
        value = operation()
        wall.append(time.perf_counter_ns() - start)
        cpu.append(time.process_time_ns() - start_cpu)
    return value, dict(wall_ns=wall, cpu_ns=cpu, median_ns=statistics.median(wall),
                       p95_ns=sorted(wall)[(95 * len(wall) + 99) // 100 - 1],
                       median_cpu_ns=statistics.median(cpu))


def load_suite(directory):
    raw = (directory / "manifest.json").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != (directory / "manifest.sha256").read_text().strip():
        raise ValueError("fixture manifest mismatch")
    vectors = []
    for item in json.loads(raw)["vectors"]:
        desc_raw = (directory / item["descriptor_path"]).read_bytes()
        original = (directory / item["original_path"]).read_bytes()
        if hashlib.sha256(desc_raw).hexdigest() != item["descriptor_sha256"]:
            raise ValueError("descriptor digest mismatch")
        if hashlib.sha256(original).hexdigest() != item["original_sha256"]:
            raise ValueError("original digest mismatch")
        vectors.append((item, codec.parse_descriptor(desc_raw), original))
    return digest, vectors


def outcome(desc):
    try:
        return "accept", None, None, codec.decode(desc)
    except codec.CodecReject as exc:
        return "reject", exc.code, exc.stage, None
    except codec.DecoderUnavailable as exc:
        return "unvalidated", str(exc), "local", None


def replay():
    rows, manifests = [], {}
    for directory in (V1, V2):
        digest, vectors = load_suite(directory)
        manifests[directory.name] = digest
        for item, desc, original in vectors:
            expected = item.get("profile_expected", item["expected"])
            code, stage = item["code"], item["stage"]
            if item["id"] == "offset-exceeds-declared-window":
                code, stage = "window_offset", "decode"
            a, b = outcome(desc), outcome(desc)
            if a[:3] != b[:3] or a[:3] != (expected, code, stage):
                raise ValueError(f"vector outcome mismatch: {item['id']}: {a[:3]}")
            row = dict(suite=directory.name, id=item["id"], status=a[0], code=a[1], stage=a[2],
                       deterministic_repeat=True)
            if a[3] is not None:
                result = a[3]
                if result.original != original or result.consumed != desc["stored_size"]:
                    raise ValueError("fixture reconstruction/consumption mismatch")
                row["exact_bytes_sha256"] = True
                row["work"] = asdict(result.work) if result.work else None
            # No new package: this shows why native success is not strict validity.
            if desc["codec_id"] == "zstd":
                try:
                    raw = z.ZstdDecompressor().decompress(base64.b64decode(desc["payload"]), allow_extra_data=False)
                    row["unmodified_libzstd"] = dict(status="decoded", bytes=len(raw),
                                                   sha256=hashlib.sha256(raw).hexdigest())
                except z.ZstdError:
                    row["unmodified_libzstd"] = dict(status="error")
            rows.append(row)
    return dict(manifest_sha256=manifests, total=len(rows), counts=dict(Counter(r["status"] for r in rows)), rows=rows)


def measure_corpus():
    manifest_raw = corpus.MANIFEST_PATH.read_bytes()
    if corpus.make_manifest() != json.loads(manifest_raw):
        raise ValueError("corpus/environment mismatch")
    rows = []
    for sample in corpus.build_samples():
        original = sample["bytes"]
        encoded = compress(original)
        desc = descriptor(original, encoded, mime=sample["mime_type"])
        result, timings = measure(lambda: codec.decode(desc))
        identity = codec.decode(descriptor(original, original, "identity", sample["mime_type"]))
        if result.original != original or identity.original != original:
            raise ValueError("corpus reconstruction mismatch")
        rows.append(dict(id=sample["id"], mime_type=sample["mime_type"], original_bytes=len(original),
                         encoded_bytes=len(encoded), original_sha256=hashlib.sha256(original).hexdigest(),
                         encoded_sha256=hashlib.sha256(encoded).hexdigest(),
                         oversized=not sample["benchmark_scoring"], exact_identity=True,
                         exact_zstd=True, consumed=result.consumed, work=asdict(result.work), timings=timings,
                         native_arena_bytes=result.native_arena_bytes))
    return dict(manifest_sha256=hashlib.sha256(manifest_raw).hexdigest(), rows=rows,
                samples=len(rows), strict_accepts=len(rows), identity_accepts=len(rows))


def resources():
    _, suite = load_suite(V2)
    originals = [("one-raw-block", b"a" * 64, frame(b"a" * 64)),
                 ("64-tiny-blocks", b"a" * 64, frame(b"a" * 64, [(0, 1, b"a")] * 64)),
                 ("64-mostly-empty", b"a", frame(b"a", [(0, 0, b"")] * 63 + [(0, 1, b"a")])),
                 ("high-ratio-at-A", b"x" * 2097152, compress(b"x" * 2097152))]
    for wanted in ("short-matches-128", "short-matches-43690", "short-matches-at-frame-A", "sequence-fse-max-logs"):
        item, desc, original = next(v for v in suite if v[0]["id"] == wanted)
        originals.append((wanted, original, base64.b64decode(desc["payload"])))
    rows = []
    for name, original, encoded in originals:
        desc = descriptor(original, encoded)
        result, timings = measure(lambda: codec.decode(desc), repetitions=3)
        info = codec.inspect_frame(encoded, len(original))
        _, native_times = measure(lambda: codec._decode_native(encoded, info), repetitions=3)
        # No tracing on the largest sequence loops: tracing is not a CPU benchmark.
        peak = None
        if name not in ("short-matches-43690", "short-matches-at-frame-A"):
            tracemalloc.start()
            codec.decode(desc)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        rows.append(dict(id=name, original_bytes=len(original), encoded_bytes=len(encoded),
                         expansion_ratio=len(original) / len(encoded), timings=timings,
                         native_only_timings=native_times, native_arena_bytes=result.native_arena_bytes,
                         output_capacity=result.output_capacity, peak_output_storage=2 * result.output_capacity,
                         python_tracemalloc_peak=peak, work=asdict(result.work)))
    malformed = []
    for wanted in ("fse-log-overflow", "fse-zero-run-overflow", "sequence-count-over-output", "offset-1025"):
        item, desc, original = next(v for v in suite if v[0]["id"] == wanted)
        value, timings = measure(lambda: outcome(desc), repetitions=31)
        malformed.append(dict(id=wanted, status=value[0], code=value[1], timings=timings))
    return dict(rows=rows, malformed=malformed,
                memory_note="Explicit native arena/output capacities; Python trace is not native/RSS/stack accounting",
                cpu_note="Windows process CPU clock is coarse; raw CPU/elapsed samples retained; no validity deadline")


def run():
    return dict(task="7.6A", report_version="1.0.0", baseline_head="545b395283e0421e04894dadfd2bc2981b643de2",
                environment=dict(python=sys.version, platform=platform.platform(), architecture=platform.machine(),
                                 zstandard=z.__version__, libzstd=list(z.ZSTD_VERSION), cffi=cffi.__version__),
                source_sha256={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in (
                    "codec_prototype/strict_decoder.py", "codec_prototype/sequence_verifier.py",
                    "scripts/milestone_7_task_7_6a_vectors.py", "scripts/milestone_7_task_7_6a_conformance.py")},
                methodology=dict(corpus_warmups=1, corpus_repetitions=5, resource_warmups=1,
                                 resource_repetitions=3, malformed_repetitions=31,
                                 clocks="perf_counter_ns and process_time_ns", p95="nearest rank",
                                 excluded="imports, fixture/corpus generation, result writing"),
                golden=replay(), corpus=measure_corpus(), resources=resources(),
                enforced_derived_bounds=dict(encoded_bytes=2097152, output_bytes=2097152, window=262144,
                                            blocks=64, sequences=699050, sequence_fse_tables=192,
                                            sequence_fse_cells=81920, max_live_sequence_fse_cells=1280),
                independent_decoder_executed=False,
                remaining_gates=["Independent review/fuzzing of new verifier, including FSE/repeat handling",
                                 "Independent full decoder and supported OS/architecture agreement",
                                 "Reviewed full native Huffman/table/malformed-path work and state proof",
                                 "Restricted native workers with process memory/concurrency/queue controls",
                                 "Final launch A/B/C, integration and lifecycle tests are outside this task"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = run()
    args.output.write_bytes(json.dumps(result, indent=2, sort_keys=True).encode() + b"\n")
    print(f"wrote {args.output}; golden {result['golden']['counts']}; corpus {result['corpus']['strict_accepts']}/36")
