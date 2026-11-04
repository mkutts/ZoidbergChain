"""Bounded decoder measurements and fixture replay; never loads chain state."""
from __future__ import annotations

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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cffi
import zstandard as z
from zstandard import backend_cffi as alternative
from codec_prototype import strict_decoder as codec
from scripts import milestone_7_task_7_3_corpus as corpus
from scripts.milestone_7_task_7_6_vectors import DEST, compress, descriptor, frame

OUTPUT = ROOT / "benchmarks/milestone_7_task_7_6_results.json"


def timed(operation, repetitions=9, warmups=2):
    for _ in range(warmups):
        operation()
    wall, cpu = [], []
    for _ in range(repetitions):
        start_cpu, start = time.process_time_ns(), time.perf_counter_ns()
        result = operation()
        wall.append(time.perf_counter_ns() - start)
        cpu.append(time.process_time_ns() - start_cpu)
    return result, dict(wall_ns=wall, process_cpu_ns=cpu,
                        wall_ns_median=statistics.median(wall), wall_ns_p95=sorted(wall)[(95 * len(wall) + 99) // 100 - 1],
                        cpu_ns_median=statistics.median(cpu))


def status(desc):
    try:
        result = codec.decode(desc)
        return "accept", None, None, result
    except codec.CodecReject as exc:
        return "reject", exc.code, exc.stage, None
    except codec.DecoderUnavailable as exc:
        return "unvalidated", str(exc), "local", None


def raw_alternate(encoded, module):
    # This function only receives frozen fixtures with known bounded content sizes.
    # Raw-library acceptance is deliberately distinct from profile acceptance.
    try:
        out = module.ZstdDecompressor().decompress(encoded, allow_extra_data=False)
        return dict(status="decoded", produced=len(out), sha256=hashlib.sha256(out).hexdigest())
    except module.ZstdError:
        return dict(status="error")


def replay():
    manifest_raw = (DEST / "manifest.json").read_bytes()
    digest = hashlib.sha256(manifest_raw).hexdigest()
    if digest != (DEST / "manifest.sha256").read_text().strip():
        raise ValueError("fixture manifest digest mismatch")
    manifest = json.loads(manifest_raw)
    rows = []
    for vector in manifest["vectors"]:
        raw = (DEST / vector["descriptor_path"]).read_bytes()
        original = (DEST / vector["original_path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != vector["descriptor_sha256"]:
            raise ValueError("descriptor digest mismatch")
        if hashlib.sha256(original).hexdigest() != vector["original_sha256"]:
            raise ValueError("original digest mismatch")
        desc = codec.parse_descriptor(raw)
        first = status(desc)
        second = status(desc)
        if first[:3] != second[:3] or first[0] != vector["expected"]:
            raise ValueError(f"nondeterministic/unexpected fixture {vector['id']}")
        if first[0] == "reject" and first[1:3] != (vector["code"], vector["stage"]):
            raise ValueError("error classification mismatch")
        if first[3] is not None and first[3].original != original:
            raise ValueError("golden bytes mismatch")
        row = dict(id=vector["id"], profile_expected=vector["profile_expected"],
                   prototype_status=first[0], code=first[1], stage=first[2], repeated_identical=True)
        if desc["codec_id"] == "zstd":
            encoded = base64.b64decode(desc["payload"])
            row["cext_raw"] = raw_alternate(encoded, z)
            row["cffi_raw"] = raw_alternate(encoded, alternative)
            row["raw_backends_agree"] = row["cext_raw"] == row["cffi_raw"]
        rows.append(row)
    return dict(manifest_sha256=digest, counts=dict(Counter(r["prototype_status"] for r in rows)),
                raw_backends_compared=sum("raw_backends_agree" in r for r in rows),
                raw_backend_disagreements=[r["id"] for r in rows if r.get("raw_backends_agree") is False],
                independent_algorithm=False, vectors=rows)


def blocks_in_producer_frame(encoded):
    # Inputs here are emitted by our pinned producer, not adversarial peer data.
    offset, blocks = z.frame_header_size(encoded), 0
    while True:
        header = int.from_bytes(encoded[offset:offset + 3], "little")
        offset += 3 + (1 if (header >> 1) & 3 == 1 else header >> 3)
        blocks += 1
        if header & 1:
            assert offset + 4 == len(encoded)
            return blocks


def corpus_measurements():
    manifest_raw = corpus.MANIFEST_PATH.read_bytes()
    manifest = json.loads(manifest_raw)
    if corpus.make_manifest() != manifest:
        raise ValueError("corpus/environment mismatch")
    rows = []
    for sample in corpus.build_samples():
        original = sample["bytes"]
        identity = codec.decode(descriptor(original, original, "identity", sample["mime_type"]))
        if identity.original != original:
            raise ValueError("identity reconstruction mismatch")
        for restricted in (True, False):
            encoded, encode_times = timed(lambda: compress(original, restricted=restricted))
            desc = descriptor(original, encoded, mime=sample["mime_type"])
            public = status(desc)
            header = z.get_frame_parameters(encoded)
            row = dict(sample_id=sample["id"], mime_type=sample["mime_type"],
                       capacity_analysis=sample["capacity_analysis"], restricted_window=restricted,
                       benchmark_scoring=sample["benchmark_scoring"],
                       original_bytes=len(original), encoded_bytes=len(encoded),
                       original_sha256=hashlib.sha256(original).hexdigest(),
                       encoded_sha256=hashlib.sha256(encoded).hexdigest(), window_bytes=header.window_size,
                       data_blocks=blocks_in_producer_frame(encoded),
                       prototype_status=public[0], prototype_detail=public[1],
                       encode=encode_times, identity_exact=True)
            # The audit probe measures native feasibility; it is NOT an acceptance API.
            if restricted:
                info = codec.inspect_frame(encoded, len(original))
                native, decode_times = timed(lambda: codec._decode_native(encoded, info))
                if native[0] != original or native[1] != desc["original_sha256"]:
                    raise ValueError("native reconstruction mismatch")
                row.update(native_decode=decode_times, diagnostic_exact=True,
                           offset_history_unproven=native[5], output_capacity=len(original),
                           native_arena_bytes=native[2], native_reported_bytes=native[3], native_calls=native[4])
                if public[0] == "accept":
                    _, boundary_times = timed(lambda: codec.decode(desc))
                    row["complete_codec_boundary"] = boundary_times
            rows.append(row)
    return dict(manifest_sha256=hashlib.sha256(manifest_raw).hexdigest(), samples=len(rows) // 2,
                identity_exact=sum(r["restricted_window"] and r["identity_exact"] for r in rows),
                rows=rows)


def resources():
    rows = []
    for name, original, encoded in (
        ("one-raw-block", b"a" * 64, frame(b"a" * 64)),
        ("64-one-byte-blocks", b"a" * 64, frame(b"a" * 64, [(0, 1, b"a")] * 64)),
        ("64-empty-blocks", b"a", frame(b"a", [(0, 0, b"")] * 63 + [(0, 1, b"a")])),
        ("high-ratio-2MiB", b"x" * codec.MAX_SIZE, compress(b"x" * codec.MAX_SIZE)),
    ):
        desc = descriptor(original, encoded)
        result, timings = timed(lambda: codec.decode(desc), repetitions=101)
        tracemalloc.start()
        measured = codec.decode(desc)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert measured.original == original
        # Fixed batches overcome the coarse process-CPU clock on this host.
        batch_count = 128 if len(original) > 1048576 else 2048
        def batch():
            for _ in range(batch_count):
                codec.decode(desc)
        _, batch_timings = timed(batch, repetitions=3, warmups=1)
        rows.append(dict(id=name, original_bytes=len(original), encoded_bytes=len(encoded),
                         expansion_ratio=len(original) / len(encoded), timings=timings,
                         output_capacity=result.output_capacity,
                         peak_simultaneous_output_storage_bytes=2 * result.output_capacity,
                         native_arena_bytes=result.native_arena_bytes,
                         native_reported_bytes=result.native_reported_bytes, native_calls=result.native_calls,
                         python_tracemalloc_peak_bytes=peak,
                         cpu_batch_iterations=batch_count, cpu_batches=batch_timings))
    malformed = []
    manifest = json.loads((DEST / "manifest.json").read_bytes())
    for vector_id in ("checksum-corrupt", "bad-sequence-tables", "truncated-18", "blocks-65", "bomb-lying-size"):
        vector = next(v for v in manifest["vectors"] if v["id"] == vector_id)
        desc = json.loads((DEST / vector["descriptor_path"]).read_bytes())
        result, timings = timed(lambda: status(desc), repetitions=101)
        malformed.append(dict(id=vector_id, status=result[0], code=result[1], stage=result[2], timings=timings))
    return dict(valid=rows, malformed=malformed,
                memory_note="Static native context arena + caller output capacities are measured/explicit. "
                "tracemalloc is Python-observed allocation only, not portable native/RSS accounting. "
                "The output is copied once into returned bytes; input/base64/host overhead is additional.",
                process_cpu_note="process_time_ns often resolves to zero at these durations on Windows; "
                "perf_counter_ns records elapsed time, not a portable CPU/work bound.")


def run():
    return dict(report_version="1.0.0", scope="Task 7.6 only; no production integration",
                source_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                               for name in ("codec_prototype/strict_decoder.py",
                                            "scripts/milestone_7_task_7_6_conformance.py",
                                            "scripts/milestone_7_task_7_6_vectors.py",
                                            "requirements-codec-prototype.txt")},
                environment=dict(python=sys.version, platform=platform.platform(), machine=platform.machine(),
                                 zstandard=z.__version__, cext_libzstd=list(z.ZSTD_VERSION),
                                 cffi_libzstd=list(alternative.ZSTD_VERSION), cffi=cffi.__version__),
                methodology=dict(warmups=2, corpus_repetitions=9, resource_repetitions=101,
                                 clock="perf_counter_ns wall; process_time_ns process CPU",
                                 p95="nearest rank; nine samples => maximum",
                                 excluded="imports, corpus generation, JSON/report writes",
                                 producer="Zstd level3 checksum/content-size on, dictionary off, threads0; "
                                 "window_log18 versus from_level(3) default on identical M"),
                golden=replay(), corpus=corpus_measurements(), resources=resources(),
                blockers=["No independent decoder algorithm or second OS/architecture executed",
                          "Strict per-sequence offset <= declared W cannot be established by release libzstd; "
                          "cross-window compressed blocks remain unvalidated",
                          "No reviewed deterministic entropy/sequence work bound",
                          "No production restricted worker, queue/concurrency/process limits or native fault isolation",
                          "No portable working-state proof, finalized A/B/C, or block/lifecycle integration"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = run()
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.output}; golden {result['golden']['counts']}; corpus {result['corpus']['samples']}")
