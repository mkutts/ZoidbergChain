"""Deterministic, explicitly constructed sequence fixtures; no custom decoder."""
import base64
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.milestone_7_task_7_6_vectors import canonical, descriptor, frame

DEST = ROOT / "tests/fixtures/milestone_7_codec_v2"


def sequence_count(count):
    if count < 128:
        return bytes([count])
    if count < 0x7F00:
        return bytes([128 + (count >> 8), count & 255])
    return b"\xff" + (count - 0x7F00).to_bytes(2, "little")


def reverse_fields(fields):
    """Encode known scalar fields in read order, followed by the stop bit."""
    value, shift = 0, 0
    for number, width in reversed(fields):
        if not 0 <= number < 1 << width:
            raise ValueError("fixture field does not fit")
        value |= number << shift
        shift += width
    value |= 1 << shift
    return value.to_bytes((shift + 8) // 8, "little")


def rle_sequences(count, *, of_code=2, extra=0, repeat=False):
    # LL=0, ML=3, explicit offset=2**of_code+extra-3, or repeat code.
    tables = b"" if repeat else bytes([0, of_code, 0])
    return (b"\0" + sequence_count(count) + bytes([0xFC if repeat else 0x54]) + tables
            + reverse_fields([(extra, of_code)] * count))


def make_vectors():
    vectors = []

    def add(name, original, blocks, code=None, window_byte=64, expected_work=None):
        encoded = frame(original, blocks, window_byte=window_byte)
        vectors.append(dict(id=name, original=original, descriptor=descriptor(original, encoded),
                            expected="reject" if code else "accept", code=code,
                            stage="decode" if code else None, work=expected_work))

    for n in (1, 127, 128, 32511, 32512, 43690):
        data = b"a" * (1 + 3 * n)
        body = rle_sequences(n)
        add(f"short-matches-{n}", data, [(0, 1, b"a"), (2, len(body), body)],
            expected_work=dict(sequences=n, max_offset=1))
    # Exactly floor(A/3) matches, with two raw bytes filling A's remainder.
    blocks = [(0, 2, b"aa")]
    for n in [43690] * 16 + [10]:
        body = rle_sequences(n)
        blocks.append((2, len(body), body))
    add("short-matches-at-frame-A", b"a" * 2097152, blocks,
        expected_work=dict(sequences=699050, max_offset=1))
    body = rle_sequences(1)
    body = b"\0\x80\x01" + body[2:]  # Permitted nonminimal 2-byte count=1.
    add("nonminimal-sequence-count", b"aaaa", [(0, 1, b"a"), (2, len(body), body)],
        expected_work=dict(sequences=1, max_offset=1))
    def two_symbol_distribution(log):
        # Norm=[2**(log-1),2**(log-1)]; known forward FSE count fields.
        bits = (log - 5) | (((1 << (log - 1)) + 1) << 4) | (((1 << log) - 1) << (4 + log))
        return bits.to_bytes((4 + 2 * log + 7) // 8, "little")
    body = (b"\0\x01\xa8" + two_symbol_distribution(9) + two_symbol_distribution(8)
            + two_symbol_distribution(9) + reverse_fields([(0, 9), (0, 8), (0, 9)]))
    add("sequence-fse-max-logs", b"abcdabc", [(0, 4, b"abcd"), (2, len(body), body)],
        expected_work=dict(sequences=1, max_offset=4, fse_tables=3, fse_cells=1280))
    for index, log in ((6, 9), (9, 10)):
        bad_body = bytearray(body)
        bad_body[index] = (bad_body[index] & 0xF0) | (log - 5)
        add(f"sequence-fse-log-over-{index}", b"abcdabc", [(0, 4, b"abcd"), (2, len(body), bytes(bad_body))], "invalid_stream")
    n = 43691
    body = rle_sequences(n)
    add("short-matches-over-block", b"a" * (1 + 3 * n), [(0, 1, b"a"), (2, len(body), body)], "invalid_stream")
    first, second = rle_sequences(1), rle_sequences(3, repeat=True)
    add("repeat-tables-across-raw", b"a" * 14,
        [(0, 1, b"a"), (2, len(first), first), (0, 1, b"a"), (2, len(second), second)],
        expected_work=dict(sequences=4, max_offset=1, fse_tables=3))
    first = rle_sequences(1, of_code=0)  # LL0 / repeat2=4; then LL0 / repeat2=1.
    second = rle_sequences(1, of_code=0, repeat=True)
    add("repeat-offset-reordering", b"abcdefgh" + b"efg" + b"ggg",
        [(0, 8, b"abcdefgh"), (2, len(first), first), (2, len(second), second)],
        expected_work=dict(sequences=2, max_offset=4))
    first, second = rle_sequences(1, of_code=3, extra=3), rle_sequences(1, of_code=1, extra=1)
    add("repeat-offset-minus-one", b"abcdefgh" + b"abc" + b"efg",
        [(0, 8, b"abcdefgh"), (2, len(first), first), (2, len(second), second)],
        expected_work=dict(sequences=2, max_offset=8))
    second = rle_sequences(1, of_code=1, extra=1)
    add("repeat-offset-minus-one-zero", b"abc", [(2, len(second), second)], "invalid_stream")
    for distance in (1024, 1025, 262144, 262145):
        original = b"a" * (distance + 3)
        raw = [(0, len(original[i:min(i + 131072, distance)]), original[i:min(i + 131072, distance)])
               for i in range(0, distance, 131072)]
        code = (distance + 3).bit_length() - 1
        body = rle_sequences(1, of_code=code, extra=distance + 3 - (1 << code))
        # Small windows require small raw blocks too.
        if distance <= 1025:
            raw = [(0, min(1024, distance - i), b"a" * min(1024, distance - i)) for i in range(0, distance, 1024)]
        add(f"offset-{distance}", original, raw + [(2, len(body), body)],
            "window_offset" if distance in (1025, 262145) else None,
            window_byte=0 if distance <= 1025 else 64,
            expected_work=None if distance in (1025, 262145) else dict(sequences=1, max_offset=distance))
    invalid_bodies = {
        "repeat-table-missing": rle_sequences(1, repeat=True),
        "sequence-reserved-bits": b"\0\x01\x55\0\x02\0\x04",
        "sequence-rle-symbol-overflow": b"\0\x01\x54\x24\x02\0\x04",
        "fse-log-overflow": b"\0\x01\x80\x05\0\0\0",
        "fse-zero-run-overflow": b"\0\x01\x80\xf0\xff\xff\xff\xff\xff\xff",
        "sequence-stop-bit-missing": rle_sequences(1)[:-1] + b"\0",
        "sequence-unused-bits": rle_sequences(1) + b"\x01",
        "sequence-count-3byte-truncated": b"\0\xff\0",
        "sequence-count-over-output": b"\0\xff\xff\xff\x54\0\x02\0\x04",
    }
    for name, body in invalid_bodies.items():
        add(name, b"aaaa", [(0, 1, b"a"), (2, len(body), body)], "invalid_stream")
    # Raw/RLE literal-size headers, all nonminimal permitted widths; no sequences.
    for fmt, width in ((0, 1), (1, 2), (3, 3)):
        header = ((3 << (3 if width == 1 else 4)) | (fmt << 2)).to_bytes(width, "little")
        body = header + b"abc\0"
        add(f"raw-literals-width-{width}", b"abc", [(2, len(body), body)], expected_work=dict(sequences=0, literal_bytes=3))
        header = ((3 << (3 if width == 1 else 4)) | (fmt << 2) | 1).to_bytes(width, "little")
        body = header + b"a\0"
        add(f"rle-literals-width-{width}", b"aaa", [(2, len(body), body)], expected_work=dict(sequences=0, literal_bytes=3))
    return vectors


def write_vectors():
    DEST.mkdir(parents=True, exist_ok=True)
    records = []
    for item in make_vectors():
        original, desc = item.pop("original"), item.pop("descriptor")
        original_path = "m-" + hashlib.sha256(original).hexdigest() + ".bin"
        desc_path = item["id"] + ".json"
        raw = canonical(desc)
        (DEST / original_path).write_bytes(original)
        (DEST / desc_path).write_bytes(raw)
        records.append(item | dict(descriptor_path=desc_path, original_path=original_path,
                                   descriptor_sha256=hashlib.sha256(raw).hexdigest(),
                                   original_sha256=hashlib.sha256(original).hexdigest(),
                                   original_bytes=len(original), encoded_bytes=desc["stored_size"],
                                   encoded_sha256=hashlib.sha256(base64.b64decode(desc["payload"])).hexdigest()))
    manifest = dict(suite_id="zoidbergchain-codec-sequence-conformance", suite_version="2.0.0",
                    baseline="../milestone_7_codec_v1/manifest.json; immutable 117 vectors",
                    baseline_sha256=hashlib.sha256((DEST.parent / "milestone_7_codec_v1/manifest.json").read_bytes()).hexdigest(),
                    contract="Task 7.5 zstd/1 / format 0.4.3 / Task 7.6A clarification",
                    provenance="scripts/milestone_7_task_7_6a_vectors.py; CPython 3.13.5; zstandard 0.25.0 / libzstd 1.5.7 checksum generation",
                    limits=dict(A=2097152, B=2097152, W=262144, blocks=64), vectors=records)
    raw = json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n"
    (DEST / "manifest.json").write_bytes(raw)
    (DEST / "manifest.sha256").write_bytes(hashlib.sha256(raw).hexdigest().encode() + b"\n")
    print(f"wrote {len(records)} Task 7.6A vectors; SHA-256 {hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    write_vectors()
