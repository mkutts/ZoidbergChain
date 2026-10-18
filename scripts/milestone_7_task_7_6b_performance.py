"""Task 7.6B offline paired measurements; no production-path imports or writes.

Reference code is read from the fixed, locally committed Task 7.6A SHA. Only
benchmark copies receive timing probes; public validation never disables checks.
"""
from __future__ import annotations

import argparse
import ast
import base64
import cProfile
import hashlib
import json
import platform
import pstats
import statistics
import subprocess
import sys
import time
import tracemalloc
import types
from collections import Counter
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cffi
import zstandard as z
from codec_prototype import strict_decoder as current
from codec_prototype import sequence_verifier as current_sequences
from scripts import milestone_7_task_7_3_corpus as corpus
from scripts.milestone_7_task_7_6_vectors import compress, descriptor, frame

BASELINE = "723a37a6627650213c9ee78ca787086b3f2659f9"
OUTPUT = ROOT / "benchmarks/milestone_7_task_7_6b_results.json"


def baseline_source(name):
    return subprocess.check_output(["git", "show", f"{BASELINE}:codec_prototype/{name}.py"], cwd=ROOT).decode("utf-8")


def module_from_source(name, source, package=None):
    module = types.ModuleType(name)
    module.__file__ = f"<task76b:{name}>"
    module.__package__ = package
    sys.modules[name] = module
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


def load_reference():
    name = "_task76a_committed_reference"
    if name + ".strict_decoder" in sys.modules:
        return sys.modules[name + ".strict_decoder"], sys.modules[name + ".sequence_verifier"]
    package = types.ModuleType(name)
    package.__path__ = []
    sys.modules[name] = package
    sequence = module_from_source(name + ".sequence_verifier", baseline_source("sequence_verifier"), name)
    decoder = module_from_source(name + ".strict_decoder", baseline_source("strict_decoder"), name)
    return decoder, sequence


def summaries(wall, cpu=None):
    result = dict(wall_ns=wall, samples=len(wall), median_ns=statistics.median(wall),
                  p95_ns=sorted(wall)[(95 * len(wall) + 99) // 100 - 1], worst_ns=max(wall))
    if cpu is not None:
        result.update(cpu_ns=cpu, median_cpu_ns=statistics.median(cpu))
    return result


def timed(operation, repeats=5):
    operation()
    wall, cpu = [], []
    for _ in range(repeats):
        c, t = time.process_time_ns(), time.perf_counter_ns()
        result = operation()
        wall.append(time.perf_counter_ns() - t)
        cpu.append(time.process_time_ns() - c)
    return result, summaries(wall, cpu)


def paired(before, after, repeats=5):
    before()
    after()
    wall, cpu = [[], []], [[], []]
    outputs = [None, None]
    for i in range(repeats):
        # Alternate order to reduce systematic warm-cache/scheduling bias.
        for j in ((0, 1) if i % 2 == 0 else (1, 0)):
            c, t = time.process_time_ns(), time.perf_counter_ns()
            outputs[j] = (before if j == 0 else after)()
            wall[j].append(time.perf_counter_ns() - t)
            cpu[j].append(time.process_time_ns() - c)
    return outputs, dict(before=summaries(wall[0], cpu[0]), after=summaries(wall[1], cpu[1]))


def check_probe(source, name):
    """Instrument actual safety predicates; never remove/replace a predicate.

    Diagnostic clocks perturb execution. The remainder is NOT an exact phase
    decomposition of uninstrumented latency, and stages must not be summed.
    """
    tree = ast.parse(source)
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "verify_sequences")
    loop = next(n for n in ast.walk(function) if isinstance(n, ast.For) and isinstance(n.target, ast.Name) and n.target.id == "index")
    def targets(n, target):
        return isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name) and n.target.id == target
    start = next(i for i, n in enumerate(loop.body) if targets(n, "used_literals"))
    stop = next(i for i, n in enumerate(loop.body) if i > start and targets(n, "block_output"))
    loop.body[start:stop] = (ast.parse("_probe_start = _probe_clock()").body + loop.body[start:stop]
                             + ast.parse("_probe_checks_ns += _probe_clock() - _probe_start").body)
    function.body[1:1] = ast.parse("global _probe_checks_ns\n_probe_checks_ns = 0").body
    ast.fix_missing_locations(tree)
    module = module_from_source(name, ast.unparse(tree))
    module._probe_clock = time.perf_counter_ns
    return module


def nohash_native(decoder, name):
    """Benchmark-only copy omits digest computation, retaining native safeguards."""
    tree = ast.parse(baseline_source("strict_decoder"))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_decode_native")
    replacements = 0
    for node in ast.walk(function):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "digest":
            node.value = ast.Constant(None)
            replacements += 1
    assert replacements == 1
    ast.fix_missing_locations(function)
    scope = dict(decoder.__dict__)
    exec(compile(ast.Module(body=[function], type_ignores=[]), name, "exec"), scope)
    return scope["_decode_native"]


def profile(sequence, encoded, info):
    profiler = cProfile.Profile()
    profiler.runcall(sequence.verify_sequences, encoded, info)
    stats = pstats.Stats(profiler)
    rows = [dict(function=f"{key[0]}:{key[1]}:{key[2]}", primitive_calls=value[0], calls=value[1],
                 self_seconds=value[2], cumulative_seconds=value[3]) for key, value in stats.stats.items()]
    return sorted(rows, key=lambda r: r["self_seconds"], reverse=True)[:20]


def rebuilt_table_case():
    directory = ROOT / "tests/fixtures/milestone_7_codec_v2"
    desc = json.loads((directory / "sequence-fse-max-logs.json").read_bytes())
    encoded = base64.b64decode(desc["payload"])
    info = current.inspect_frame(encoded, desc["original_size"])
    # Frozen fixture has a 4-byte raw prefix followed by one compressed block.
    offset = info.header_size + 3 + 4
    header = int.from_bytes(encoded[offset:offset + 3], "little")
    body = encoded[offset + 3:offset + 3 + (header >> 3)]
    original = bytearray(b"abcd")
    blocks = [(0, 4, b"abcd")]
    for index in range(63):
        # Each known sequence is LL0/ML3/repeat2, alternating distances 4/1.
        distance = 4 if index % 2 == 0 else 1
        for _ in range(3):
            original.append(original[-distance])
        blocks.append((2, len(body), body))
    original = bytes(original)
    return dict(id="64-rebuilt-max-fse", group="adversarial", original=original,
                descriptor=descriptor(original, frame(original, blocks)))


def cases():
    samples = corpus.build_samples()
    manifest_raw = corpus.MANIFEST_PATH.read_bytes()
    records = {r["id"]: r for r in json.loads(manifest_raw)["samples"]}
    rows = []
    for sample in samples:
        original = sample["bytes"]
        assert hashlib.sha256(original).hexdigest() == records[sample["id"]]["sha256"]
        rows.append(dict(id=sample["id"], group="corpus", original=original,
                         descriptor=descriptor(original, compress(original), mime=sample["mime_type"])))
    directory = ROOT / "tests/fixtures/milestone_7_codec_v2"
    manifest = json.loads((directory / "manifest.json").read_bytes())
    for wanted in ("short-matches-128", "short-matches-43690", "short-matches-at-frame-A", "sequence-fse-max-logs"):
        item = next(v for v in manifest["vectors"] if v["id"] == wanted)
        rows.append(dict(id=wanted, group="adversarial", original=(directory / item["original_path"]).read_bytes(),
                         descriptor=json.loads((directory / item["descriptor_path"]).read_bytes())))
    from scripts.milestone_7_task_7_6a_vectors import rle_sequences
    original = b"a" * (1 + 3 * 65536)
    blocks = [(0, 1, b"a")]
    for count in (43690, 21846):
        body = rle_sequences(count)
        blocks.append((2, len(body), body))
    rows.append(dict(id="short-matches-candidate-65536", group="adversarial", original=original,
                     descriptor=descriptor(original, frame(original, blocks))))
    for name, original, blocks in (("one-raw-block", b"a" * 64, [(0, 64, b"a" * 64)]),
                                   ("64-tiny-blocks", b"a" * 64, [(0, 1, b"a")] * 64),
                                   ("64-mostly-empty", b"a", [(0, 0, b"")] * 63 + [(0, 1, b"a")])):
        rows.append(dict(id=name, group="adversarial", original=original,
                         descriptor=descriptor(original, frame(original, blocks))))
    original = b"x" * current.MAX_SIZE
    rows.append(dict(id="high-ratio-at-A", group="adversarial", original=original,
                     descriptor=descriptor(original, compress(original))))
    rows.append(rebuilt_table_case())
    return rows


def differential_golden(reference):
    rows = []
    def outcome(module, desc):
        try:
            result = module.decode(desc)
            return ("accept", result.consumed, result.produced, hashlib.sha256(result.original).hexdigest(),
                    asdict(result.work) if result.work else None)
        except module.CodecReject as exc:
            return ("reject", exc.code, exc.stage)
    for folder in ("milestone_7_codec_v1", "milestone_7_codec_v2"):
        directory = ROOT / "tests/fixtures" / folder
        for item in json.loads((directory / "manifest.json").read_bytes())["vectors"]:
            desc = json.loads((directory / item["descriptor_path"]).read_bytes())
            before, after = outcome(reference, desc), outcome(current, desc)
            if before != after:
                raise ValueError(f"acceptance/output/work mismatch: {item['id']}")
            rows.append(dict(id=item["id"], status=after[0], agreement=True))
    return dict(total=len(rows), counts=dict(Counter(r["status"] for r in rows)), rows=rows,
                comparison="Committed Task 7.6A versus optimized prototype; NOT independent decoder verification")


def memory_evidence(sequence, encoded, info, verified_work):
    # Tracing millions of transient reference-parser allocations is extremely
    # intrusive on this Windows runtime. Retain every full timing/CPU/golden
    # case, but bound this diagnostic's instrumentation work independently.
    if verified_work.sequences > 4096:
        return dict(python_verifier_peak=None, sequences=verified_work.sequences,
                    selected_table_cells=verified_work.fse_cells, traced=False,
                    note="Not traced at large sequence counts; full latency/CPU, native arena/output and semantic checks still run")
    tracemalloc.start()
    work = sequence.verify_sequences(encoded, info)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return dict(python_verifier_peak=peak, sequences=work.sequences, selected_table_cells=work.fse_cells, traced=True)


def malformed_measurements(reference, repeats):
    rows = []
    for suite, name in (("v1", "offset-exceeds-declared-window"), ("v1", "checksum-corrupt"),
                        ("v2", "fse-zero-run-overflow"), ("v2", "sequence-count-over-output"),
                        ("v2", "sequence-stop-bit-missing")):
        desc = json.loads((ROOT / f"tests/fixtures/milestone_7_codec_{suite}" / (name + ".json")).read_bytes())
        def rejection(module):
            try:
                module.decode(desc)
            except module.CodecReject as exc:
                return (exc.stage, exc.code)
            raise AssertionError("malformed probe did not reject")
        results, times = paired(lambda: rejection(reference), lambda: rejection(current), repeats)
        assert results[0] == results[1]
        rows.append(dict(id=name, stage=results[0][0], code=results[0][1], timings=times))
    return rows


def native_allocations(module, encoded, info, work):
    """Observe caller-owned CFFI allocations, not arbitrary native malloc/stack."""
    original_backend = module._backend
    ffi, lib = original_backend()
    observed = []
    class ObservedFFI:
        def __getattr__(self, key):
            return getattr(ffi, key)
        def new(self, declaration, length):
            result = ffi.new(declaration, length)
            observed.append(dict(declaration=declaration, requested_length=length, bytes=ffi.sizeof(result)))
            return result
    module._backend = lambda: (ObservedFFI(), lib)
    try:
        result = module._decode_native(encoded, info, work)
        return dict(observed_caller_allocations=observed, reported_native_context=result[3],
                    note="Does not intercept libzstd internals; static-context contract and native/host stack audit remain separate")
    finally:
        module._backend = original_backend


def run(repeats):
    reference, sequence = load_reference()
    before_probe = check_probe(baseline_source("sequence_verifier"), "_task76b_before_probe")
    after_probe = check_probe((ROOT / "codec_prototype/sequence_verifier.py").read_text(encoding="utf-8"), "_task76b_after_probe")
    native = nohash_native(reference, "<task76b:native_without_digest>")
    rows, memory, profiles = [], [], {}
    inputs = cases()
    for case in inputs:
        if tracemalloc.is_tracing():
            raise RuntimeError("allocation tracing leaked into latency measurements")
        desc, original = case["descriptor"], case["original"]
        encoded = current._payload(desc)
        info = current.inspect_frame(encoded, len(original))
        outputs, totals = paired(lambda: reference.decode(desc), lambda: current.decode(desc), repeats)
        assert outputs[0].original == outputs[1].original == original
        work, sequences = paired(lambda: sequence.verify_sequences(encoded, info),
                                 lambda: current_sequences.verify_sequences(encoded, info), repeats)
        assert asdict(work[0]) == asdict(work[1])
        _, descriptor_times = timed(lambda: current._payload(desc), repeats)
        _, frame_times = timed(lambda: current.inspect_frame(encoded, len(original)), repeats)
        out, native_times = timed(lambda: native(encoded, info, outputs[1].work), repeats)
        assert out[0] == original and out[1] is None
        def verify_hash():
            assert hashlib.sha256(original).hexdigest() == desc["original_sha256"]
        _, hash_times = timed(verify_hash, repeats)
        check_phases = {}
        for label, probe in (("before", before_probe), ("after", after_probe)):
            guard_samples = []
            def probe_call():
                result = probe.verify_sequences(encoded, info)
                guard_samples.append(probe._probe_checks_ns)
                return result
            probe_work, whole = timed(probe_call, repeats)
            assert asdict(probe_work) == asdict(work[0])
            guards = guard_samples[1:]  # Exclude warmup, as with other timings.
            check_phases[label] = dict(instrumented_total=whole,
                                      inline_output_window_history=summaries(guards),
                                      parsing_remainder_with_probe_overhead=summaries(
                                          [total - guard for total, guard in zip(whole["wall_ns"], guards)]))
        rows.append(dict(id=case["id"], group=case["group"], original_bytes=len(original), encoded_bytes=len(encoded),
                         original_sha256=hashlib.sha256(original).hexdigest(), encoded_sha256=hashlib.sha256(encoded).hexdigest(),
                         descriptor=descriptor_times, frame=frame_times, sequence=sequences,
                         instrumented_separation=check_phases, native_without_hash=native_times,
                         output_hash=hash_times, total=totals, work=asdict(outputs[1].work), exact_reconstruction=True))
        print(f"measured {case['id']}", flush=True)
    # Run intrusive diagnostics only AFTER all timing samples, so allocation
    # tracing/profiling cannot affect subsequent latency measurements.
    for case in inputs:
        encoded = current._payload(case["descriptor"])
        info = current.inspect_frame(encoded, len(case["original"]))
        if case["id"] in ("short-matches-128", "short-matches-43690", "short-matches-at-frame-A", "sequence-fse-max-logs", "high-ratio-at-A", "64-rebuilt-max-fse"):
            result = current.decode(case["descriptor"])
            memory.append(dict(id=case["id"], before=memory_evidence(sequence, encoded, info, result.work),
                               after=memory_evidence(current_sequences, encoded, info, result.work),
                               native_arena_bytes=result.native_arena_bytes,
                               native_reported_bytes=result.native_reported_bytes,
                               output_capacity=result.output_capacity, simultaneous_output_copies=2 * len(case["original"]),
                               native_allocations=native_allocations(reference, encoded, info, result.work)))
        if case["id"] in ("short-matches-at-frame-A", "jpeg-photo-like"):
            profiles[case["id"]] = dict(before=profile(sequence, encoded, info),
                                        after=profile(current_sequences, encoded, info))
        print(f"diagnostics {case['id']}", flush=True)
    corpus_rows = [r for r in rows if r["group"] == "corpus"]
    scenarios = dict(sequence_caps={str(cap): [r["id"] for r in corpus_rows if r["work"]["sequences"] > cap]
                                   for cap in (32768, 65536, 699050)},
                     block_caps={str(cap): [r["id"] for r in corpus_rows if r["work"]["blocks"] > cap]
                                 for cap in (32, 48, 64)},
                     size_caps={str(cap): [r["id"] for r in corpus_rows if max(r["original_bytes"], r["encoded_bytes"]) > cap]
                                for cap in (1048576, 2097152)},
                     note="Corpus-only scenarios; no profile/policy limit is changed")
    return dict(task="7.6B", baseline_head=BASELINE,
                environment=dict(python=sys.version, platform=platform.platform(), architecture=platform.machine(),
                                 zstandard=z.__version__, libzstd=list(z.ZSTD_VERSION), cffi=cffi.__version__),
                source_sha256={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in (
                    "codec_prototype/strict_decoder.py", "codec_prototype/sequence_verifier.py",
                    "scripts/milestone_7_task_7_6b_performance.py")},
                baseline_source_sha256={p: hashlib.sha256(baseline_source(p).encode()).hexdigest()
                                        for p in ("strict_decoder", "sequence_verifier")},
                methodology=dict(repetitions=repeats, warmups=1, pair_order="alternating before/after",
                                 p95="nearest rank; finite small-sample tail, not a population guarantee",
                                 phase_note="Uninstrumented stage medians do not sum exactly. Repeated predicate clocks perturb execution; parsing remainder includes probe overhead.",
                                 memory_note="tracemalloc observes Python allocations only, excluding native output/arena, RSS/stack and some reused allocations; sequence-heavy cases >4096 are not traced due to intrusive instrumentation overhead"),
                golden=differential_golden(reference), per_case=rows, memory=memory, profiles=profiles,
                malformed=malformed_measurements(reference, repeats), limit_scenarios=scenarios,
                independent_implementation=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--repetitions", type=int, default=5, choices=range(3, 10))
    args = parser.parse_args()
    result = run(args.repetitions)
    args.output.write_bytes(json.dumps(result, indent=2, sort_keys=True).encode() + b"\n")
    print(f"wrote {args.output}; {result['golden']['counts']}")
