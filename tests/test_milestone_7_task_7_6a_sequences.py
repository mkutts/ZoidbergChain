"""Sequence proof tests and bounded differential probes, Task 7.6A only."""
import base64
import hashlib
import json
from dataclasses import replace

import pytest
import zstandard as z

from codec_prototype import strict_decoder as codec
from codec_prototype import sequence_verifier as verifier
from scripts.milestone_7_task_7_6a_vectors import DEST
from scripts.milestone_7_task_7_6_vectors import compress, descriptor, noise

MANIFEST_RAW = (DEST / "manifest.json").read_bytes()
MANIFEST = json.loads(MANIFEST_RAW)


def test_v2_fixture_inventory_and_hashes():
    assert hashlib.sha256(MANIFEST_RAW).hexdigest() == (DEST / "manifest.sha256").read_text().strip()
    paths = {"manifest.json", "manifest.sha256"}
    assert hashlib.sha256((DEST.parent / "milestone_7_codec_v1/manifest.json").read_bytes()).hexdigest() == MANIFEST["baseline_sha256"]
    for vector in MANIFEST["vectors"]:
        for field, digest in (("descriptor_path", "descriptor_sha256"), ("original_path", "original_sha256")):
            paths.add(vector[field])
            assert hashlib.sha256((DEST / vector[field]).read_bytes()).hexdigest() == vector[digest]
        desc = json.loads((DEST / vector["descriptor_path"]).read_bytes())
        assert len((DEST / vector["original_path"]).read_bytes()) == vector["original_bytes"]
        encoded = base64.b64decode(desc["payload"])
        assert len(encoded) == vector["encoded_bytes"]
        assert hashlib.sha256(encoded).hexdigest() == vector["encoded_sha256"]
    assert {p.name for p in DEST.iterdir()} == paths


@pytest.mark.parametrize("vector", MANIFEST["vectors"], ids=lambda v: v["id"])
def test_sequence_golden_vector(vector):
    desc = json.loads((DEST / vector["descriptor_path"]).read_bytes())
    for _ in range(2):
        if vector["expected"] == "reject":
            with pytest.raises(codec.CodecReject) as caught:
                codec.decode(desc)
            assert (caught.value.code, caught.value.stage) == (vector["code"], vector["stage"])
        else:
            result = codec.decode(desc)
            assert result.original == (DEST / vector["original_path"]).read_bytes()
            assert hashlib.sha256(result.original).hexdigest() == desc["original_sha256"]
            assert result.work.decoded_bytes == result.produced == desc["original_size"]
            assert result.work.sequences <= result.produced // 3
            assert result.work.fse_tables <= 3 * result.frame.block_count
            assert result.work.fse_cells <= 1280 * result.frame.block_count
            assert result.work.max_offset <= result.frame.window
            for key, expected in vector["work"].items():
                assert getattr(result.work, key) == expected
            # A reconstruction check by the unmodified native implementation;
            # this is differential agreement, not independent-decoder approval.
            native = z.ZstdDecompressor().decompress(base64.b64decode(desc["payload"]), allow_extra_data=False)
            assert native == result.original


def test_window_forgery_rejected_before_native_allocation(monkeypatch):
    def forbidden(*args):
        pytest.fail("invalid sequence reached native decode")
    monkeypatch.setattr(codec, "_decode_native", forbidden)
    for vector in MANIFEST["vectors"]:
        if vector["expected"] == "reject":
            with pytest.raises(codec.CodecReject):
                codec.decode(json.loads((DEST / vector["descriptor_path"]).read_bytes()))


def test_native_sequence_disagreement_is_local_unavailability(monkeypatch):
    original = b"abc" * 100
    encoded = compress(original)
    real_verify = codec.verify_sequences
    def changed(*args):
        work = real_verify(*args)
        return replace(work, block_output_sizes=(work.decoded_bytes - 1,))
    monkeypatch.setattr(codec, "verify_sequences", changed)
    with pytest.raises(codec.DecoderUnavailable, match="disagreement"):
        codec.decode(descriptor(original, encoded))


def test_predefined_tables_match_pinned_format_appendix():
    ll, of, ml = verifier.DEFAULTS
    assert len(ll.rows) == len(ml.rows) == 64 and len(of.rows) == 32
    # Unrelated state rows from the format's appendix, not encoder output.
    assert ll.rows[0] == (0, 4, 0)
    assert ll.rows[1] == (0, 4, 16)
    assert ll.rows[2] == (1, 5, 32)
    assert ll.rows[17] == (25, 5, 32)


def test_fse_builder_has_bounded_rows_and_rejects_invalid_distributions():
    for norm, log in (([32], 5), ([31, 0], 5), ([33, -1], 5), ([-2, 30], 5)):
        with pytest.raises(verifier.VerificationReject):
            verifier.build_table(norm, log)
    table = verifier.build_table([256, 256], 9)
    assert len(table.rows) == 512
    assert all(0 <= row[2] < 512 and 0 <= row[1] <= 9 for row in table.rows)


def test_repeat_tables_and_offsets_are_reset_between_frames():
    valid = next(v for v in MANIFEST["vectors"] if v["id"] == "repeat-tables-across-raw")
    invalid = next(v for v in MANIFEST["vectors"] if v["id"] == "repeat-table-missing")
    assert codec.decode(json.loads((DEST / valid["descriptor_path"]).read_bytes())).produced == 14
    with pytest.raises(codec.CodecReject):
        codec.decode(json.loads((DEST / invalid["descriptor_path"]).read_bytes()))


def test_bounded_encoder_matrix_preserves_every_byte():
    # Diverse histories and entropy tables across levels/windows/block splits.
    sources = [noise(4096), b"a" * 8192, bytes(range(256)) * 128,
               noise(50000) + noise(50000) + b"abc" * 1000,
               b"{caption: bounded parser, sequence verifier}\n" * 5000]
    for source in sources:
        for level in (1, 3, 9, 19):
            params = z.ZstdCompressionParameters.from_level(level, window_log=18,
                         write_checksum=1, write_content_size=1, write_dict_id=0, threads=0)
            encoded = z.ZstdCompressor(compression_params=params).compress(source)
            result = codec.decode(descriptor(source, encoded))
            assert result.original == source
            assert sum(result.work.block_output_sizes) == len(source)


def test_bounded_mutations_cannot_escape_verifier_failure_boundary():
    # All single-bit flips in small RLE/repeat streams; inputs remain under 300 B.
    for vector in MANIFEST["vectors"]:
        if vector["id"] not in ("repeat-tables-across-raw", "repeat-offset-minus-one", "short-matches-127"):
            continue
        desc = json.loads((DEST / vector["descriptor_path"]).read_bytes())
        encoded = base64.b64decode(desc["payload"])
        original = (DEST / vector["original_path"]).read_bytes()
        for offset in range(len(encoded)):
            for bit in range(8):
                changed = bytearray(encoded)
                changed[offset] ^= 1 << bit
                try:
                    result = codec.decode(descriptor(original, bytes(changed)))
                    assert result.original == original
                except (codec.CodecReject, codec.DecoderUnavailable):
                    pass


def test_report_distinguishes_sequence_proof_from_full_production_approval():
    report = json.loads((DEST.parents[2] / "benchmarks/milestone_7_task_7_6a_results.json").read_bytes())
    assert report["golden"]["counts"] == {"accept": 42, "reject": 110}
    assert report["golden"]["total"] == 152
    assert report["corpus"]["strict_accepts"] == report["corpus"]["identity_accepts"] == 36
    for row in report["corpus"]["rows"]:
        assert row["exact_zstd"] and row["exact_identity"]
        assert row["work"]["sequences"] <= row["original_bytes"] // 3
        assert row["work"]["max_offset"] <= 262144
    assert report["independent_decoder_executed"] is False
    assert report["remaining_gates"]
