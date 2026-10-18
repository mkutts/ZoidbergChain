"""Codec-only security tests; no production state is opened or changed."""
import base64
import hashlib
import json
from collections import Counter

import pytest
import zstandard as z

from codec_prototype import strict_decoder as codec
from scripts.milestone_7_task_7_6_vectors import DEST, compress, descriptor, frame, noise

MANIFEST_BYTES = (DEST / "manifest.json").read_bytes()
MANIFEST = json.loads(MANIFEST_BYTES)


def test_manifest_and_all_fixture_bytes_are_frozen():
    assert hashlib.sha256(MANIFEST_BYTES).hexdigest() == (DEST / "manifest.sha256").read_text().strip()
    assert MANIFEST["limits"] == {"A": 2097152, "B": 2097152, "window": 262144, "blocks": 64}
    expected_paths = {"manifest.json", "manifest.sha256"}
    expected_paths.update(v["descriptor_path"] for v in MANIFEST["vectors"])
    expected_paths.update(v["original_path"] for v in MANIFEST["vectors"])
    assert {p.name for p in DEST.iterdir()} == expected_paths
    for vector in MANIFEST["vectors"]:
        raw = (DEST / vector["descriptor_path"]).read_bytes()
        original = (DEST / vector["original_path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == vector["descriptor_sha256"]
        assert hashlib.sha256(original).hexdigest() == vector["original_sha256"]
        assert len(original) == vector["original_bytes"]
        if vector["encoded_sha256"] is not None:
            payload = base64.b64decode(json.loads(raw)["payload"])
            assert hashlib.sha256(payload).hexdigest() == vector["encoded_sha256"]


@pytest.mark.parametrize("vector", MANIFEST["vectors"], ids=lambda v: v["id"])
def test_versioned_golden_vectors(vector):
    desc = codec.parse_descriptor((DEST / vector["descriptor_path"]).read_bytes())
    for _ in range(2):  # Repeat after previous decodes, with fresh dictionary-free state.
        if vector["expected"] == "reject":
            with pytest.raises(codec.CodecReject) as caught:
                codec.decode(desc)
            assert (caught.value.code, caught.value.stage) == (vector["code"], vector["stage"])
        elif vector["expected"] == "unvalidated":
            # Preserve v1 fixture bytes/outcomes as historical evidence. Task 7.6A
            # now resolves both cases according to their frozen profile expectation.
            if vector["profile_expected"] == "reject":
                with pytest.raises(codec.CodecReject, match="window_offset"):
                    codec.decode(desc)
            else:
                assert codec.decode(desc).original == (DEST / vector["original_path"]).read_bytes()
        else:
            result = codec.decode(desc)
            assert result.original == (DEST / vector["original_path"]).read_bytes()
            assert result.produced == result.output_capacity == desc["original_size"]
            assert result.consumed == desc["stored_size"]
            assert hashlib.sha256(result.original).hexdigest() == desc["original_sha256"]
            if desc["codec_id"] == "zstd":
                assert result.native_arena_bytes == result.native_reported_bytes <= codec.MAX_NATIVE_ARENA
                assert result.native_calls <= desc["stored_size"]


@pytest.mark.parametrize("raw,code", [
    (b'{"codec_id":"identity","codec_id":"zstd"}', "duplicate_key"),
    (b'{"x":{}}', "json_shape"),
    (b'[]', "json_shape"),
    (b'{"x":"\\ud800"}', "json_syntax"),
    (b'{"x":NaN}', "json_syntax"),
    (b'{"x":1} ', "noncanonical_json"),
    (b'\xff', "json_syntax"),
    (b' ' * (4 * ((codec.MAX_SIZE + 2) // 3) + 2049), "json_size"),
], ids=["duplicate", "nested", "array", "surrogate", "nan", "whitespace", "utf8", "oversized"])
def test_json_boundary(raw, code):
    with pytest.raises(codec.CodecReject) as caught:
        codec.parse_descriptor(raw)
    assert caught.value.code == code


def test_preflight_rejects_before_native_creation(monkeypatch):
    def forbidden():
        pytest.fail("native decoder invoked before structural rejection")
    monkeypatch.setattr(codec, "_backend", forbidden)
    for vector in MANIFEST["vectors"]:
        if vector["expected"] == "reject" and vector["stage"] in ("descriptor", "frame"):
            with pytest.raises(codec.CodecReject):
                codec.decode(json.loads((DEST / vector["descriptor_path"]).read_bytes()))


def test_codec_has_no_encoder_requirement(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("decoder requested encoder")
    monkeypatch.setattr(z, "ZstdCompressor", forbidden)
    vector = next(v for v in MANIFEST["vectors"] if v["id"] == "zstd-default")
    assert codec.decode(json.loads((DEST / vector["descriptor_path"]).read_bytes())).produced > 0


def test_allocation_failure_is_unvalidated(monkeypatch):
    def unavailable(*args):
        raise MemoryError("simulated")
    monkeypatch.setattr(codec, "_decode_native", unavailable)
    with pytest.raises(codec.DecoderUnavailable, match="allocation"):
        codec.decode(descriptor(b"abc", frame(b"abc")))


def test_pinned_backend_failure_is_unvalidated(monkeypatch):
    monkeypatch.setattr(z, "__version__", "unverified")
    with pytest.raises(codec.DecoderUnavailable, match="version"):
        codec.decode(descriptor(b"abc", frame(b"abc")))


def test_dictionary_failure_cannot_leak_state_to_following_decode():
    vector = next(v for v in MANIFEST["vectors"] if v["id"] == "unadvertised-raw-dictionary")
    with pytest.raises(codec.CodecReject):
        codec.decode(json.loads((DEST / vector["descriptor_path"]).read_bytes()))
    assert codec.decode(descriptor(b"abc", frame(b"abc"))).original == b"abc"


def test_native_stream_at_full_output_still_requires_checksum():
    data = b"checksum must finish" * 100
    encoded = compress(data)
    info = codec.inspect_frame(encoded, len(data))
    # Direct low-level probe bypasses preflight to prove terminal status matters.
    with pytest.raises(codec.CodecReject, match="incomplete"):
        codec._decode_native(encoded[:-1], info)


def test_64_block_limit_is_a_structural_limit_not_a_work_proof():
    totals = Counter(v["expected"] for v in MANIFEST["vectors"])
    assert totals == {"accept": 21, "reject": 94, "unvalidated": 2}
    assert codec.decode(descriptor(b"a", frame(b"a", [(0, 0, b"")] * 63 + [(0, 1, b"a")]))).frame.block_count == 64


def test_bounded_systematic_mutations_never_escape_error_boundary():
    original = b"bounded mutation stream " * 100
    encoded = compress(original)
    # 3 bit flips at each byte, bounded to this small frame. No random fuzz/large allocations.
    for position in range(len(encoded)):
        for mask in (1, 8, 128):
            changed = bytearray(encoded)
            changed[position] ^= mask
            try:
                result = codec.decode(descriptor(original, bytes(changed)))
                assert result.original == original
            except (codec.CodecReject, codec.DecoderUnavailable):
                pass


def test_declared_size_does_not_authorize_extra_native_output():
    original = b"x" * 10000
    encoded = compress(original)
    # Native probe deliberately bypasses metadata preflight, allocates only 9 bytes.
    false_info = codec.FrameInfo(9, 10000, 0, 1, (2,))
    with pytest.raises(codec.CodecReject):
        codec._decode_native(encoded, false_info)


def test_unhashable_and_non_scalar_fields_are_deterministic_rejections():
    for field in codec.KEYS:
        for value in ([], {}, None, True, 1.0):
            desc = descriptor(b"abc", b"abc", "identity")
            desc[field] = value
            with pytest.raises(codec.CodecReject):
                codec.decode(desc)


def test_no_production_imports_of_prototype():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    paths = list(root.glob("*.py"))
    for folder in ("services", "api_routers"):
        paths.extend((root / folder).rglob("*.py"))
    assert not [p for p in paths if "codec_prototype" in p.read_text(encoding="utf-8")]


def test_checked_in_measurements_preserve_corpus_and_distinguish_unvalidated():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    report = json.loads((root / "benchmarks/milestone_7_task_7_6_results.json").read_bytes())
    baseline = json.loads((root / "benchmarks/milestone_7_task_7_4_results.json").read_bytes())
    expected = {r["sample_id"]: r for r in baseline["per_sample"] if r["candidate_id"] == "zstd-3"}
    rows = [r for r in report["corpus"]["rows"] if r["restricted_window"]]
    assert len(rows) == report["corpus"]["identity_exact"] == 36
    assert {r["sample_id"] for r in rows if r["prototype_status"] == "unvalidated"} == {
        "jpeg-photo-like", "gif-noise-capacity"}
    assert max(r["data_blocks"] for r in rows) == 52
    for row in rows:
        assert row["diagnostic_exact"] and row["identity_exact"]
        assert row["window_bytes"] <= codec.MAX_WINDOW
        assert row["encoded_bytes"] == expected[row["sample_id"]]["encoded_bytes"]
        assert row["original_sha256"] == expected[row["sample_id"]]["original_sha256"]
    assert report["golden"]["raw_backend_disagreements"] == []
    assert report["golden"]["independent_algorithm"] is False
