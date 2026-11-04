"""Behavioral differential tests; no timing-dependent acceptance assertions."""
import base64
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import pytest

from codec_prototype import sequence_verifier as optimized
from codec_prototype import strict_decoder as decoder
from scripts.milestone_7_task_7_6b_performance import BASELINE, check_probe, differential_golden, load_reference, rebuilt_table_case
from scripts.milestone_7_task_7_6_vectors import compress, descriptor, noise

REFERENCE, SEQUENCES = load_reference()
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("stop_bits", range(8))
@pytest.mark.parametrize("length", (1, 2, 5, 16, 40))
@pytest.mark.parametrize("view", (False, True))
def test_all_bit_widths_and_alignment_paths_match_reference(stop_bits, length, view):
    raw = noise(length - 1) + bytes([(1 << stop_bits) | ((1 << stop_bits) - 1)])
    raw = memoryview(raw) if view else raw
    # Test every valid bit width at every reachable starting alignment, and the
    # same terminal/overrun errors. No frame-sized integers or random fuzz input.
    for prefix in range(8):
        for width in range(32):
            before, after = SEQUENCES.ReverseBits(raw), optimized.ReverseBits(raw)
            if prefix > before.bit:
                continue
            assert before.read(prefix) == after.read(prefix)
            if width > before.bit:
                with pytest.raises(SEQUENCES.VerificationReject):
                    before.read(width)
                with pytest.raises(optimized.VerificationReject):
                    after.read(width)
            else:
                assert before.read(width) == after.read(width)
                assert before.bit == after.bit


@pytest.mark.parametrize("width", (-1, 32, 1000))
def test_optimized_bit_reader_retains_width_rejections(width):
    for module in (SEQUENCES, optimized):
        bits = module.ReverseBits(b"\xff\x01")
        with pytest.raises(module.VerificationReject):
            bits.read(width)
        assert bits.bit == 8


def test_every_existing_golden_agrees_with_committed_reference():
    result = differential_golden(REFERENCE)
    assert result["total"] == 152
    assert result["counts"] == {"accept": 42, "reject": 110}


def outcome(module, desc):
    try:
        value = module.decode(desc)
        return ("accept", value.original, value.consumed, value.produced,
                asdict(value.work) if value.work else None)
    except module.CodecReject as exc:
        return ("reject", exc.code, exc.stage)


def test_bounded_mutation_classification_and_work_match_reference():
    directory = ROOT / "tests/fixtures/milestone_7_codec_v2"
    for name in ("repeat-offset-reordering", "repeat-offset-minus-one", "repeat-tables-across-raw",
                 "short-matches-127", "sequence-fse-max-logs"):
        desc = json.loads((directory / (name + ".json")).read_bytes())
        original = (directory / ("m-" + desc["original_sha256"] + ".bin")).read_bytes()
        raw = base64.b64decode(desc["payload"])
        for offset in range(len(raw)):
            for mask in (1, 4, 16, 128):
                changed = bytearray(raw)
                changed[offset] ^= mask
                mutated = descriptor(original, bytes(changed))
                assert outcome(REFERENCE, mutated) == outcome(decoder, mutated)


def test_varied_compressed_histories_preserve_work_and_original_hash():
    for original in (noise(4096), bytes(range(256)) * 128,
                     noise(100000) + noise(100000), b"abc def repeated history\n" * 12000):
        encoded = compress(original)
        desc = descriptor(original, encoded)
        before, after = REFERENCE.decode(desc), decoder.decode(desc)
        assert before.original == after.original == original
        assert asdict(before.work) == asdict(after.work)
        assert hashlib.sha256(after.original).hexdigest() == desc["original_sha256"]


def test_repeated_maximum_tables_preserve_state_and_reconstruction():
    case = rebuilt_table_case()
    before = REFERENCE.decode(case["descriptor"])
    after = decoder.decode(case["descriptor"])
    assert before.original == after.original == case["original"]
    assert asdict(before.work) == asdict(after.work)
    assert after.work.blocks == 64 and after.work.fse_tables == 189
    assert after.work.fse_cells == 63 * 1280


def test_diagnostic_timing_probe_preserves_output_and_invalid_offset():
    source = (ROOT / "codec_prototype/sequence_verifier.py").read_text(encoding="utf-8")
    probe = check_probe(source, "_task76b_test_probe")
    original = b"a" * 4096
    encoded = compress(original)
    info = decoder.inspect_frame(encoded, len(original))
    assert asdict(probe.verify_sequences(encoded, info)) == asdict(optimized.verify_sequences(encoded, info))
    assert probe._probe_checks_ns >= 0
    directory = ROOT / "tests/fixtures/milestone_7_codec_v1"
    desc = json.loads((directory / "offset-exceeds-declared-window.json").read_bytes())
    encoded = decoder._payload(desc)
    info = decoder.inspect_frame(encoded, desc["original_size"])
    with pytest.raises(probe.VerificationReject, match="window_offset"):
        probe.verify_sequences(encoded, info)


def test_measurement_artifact_records_unchanged_semantics_and_limited_claims():
    report = json.loads((ROOT / "benchmarks/milestone_7_task_7_6b_results.json").read_bytes())
    assert report["baseline_head"] == BASELINE
    assert report["golden"]["counts"] == {"accept": 42, "reject": 110}
    corpus = [r for r in report["per_case"] if r["group"] == "corpus"]
    assert len(corpus) == 36 and all(r["exact_reconstruction"] for r in corpus)
    assert report["independent_implementation"] is False
    for path, digest in report["source_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    assert len(report["per_case"]) == 46
    assert {"short-matches-at-frame-A", "64-rebuilt-max-fse", "64-mostly-empty"} <= {
        row["id"] for row in report["per_case"]}
    for row in report["memory"]:
        assert row["native_arena_bytes"] == row["native_reported_bytes"] == 95968
        allocations = row["native_allocations"]["observed_caller_allocations"]
        assert [item["bytes"] for item in allocations] == [95968, row["output_capacity"]]
