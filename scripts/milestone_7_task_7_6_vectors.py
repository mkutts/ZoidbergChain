"""Generate versioned codec-only fixtures. Replay never recompresses fixtures.

Run only to intentionally regenerate; libzstd 1.5.7 / zstandard 0.25.0 pinned.
These are NOT block, signature, MIME-container, or live-network vectors.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import zstandard as z
from codec_prototype import strict_decoder as codec

DEST = ROOT / "tests/fixtures/milestone_7_codec_v1"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def compress(original, *, restricted=True, level=3):
    options = dict(write_checksum=1, write_content_size=1, write_dict_id=0, threads=0)
    if restricted:
        options["window_log"] = 18
    params = z.ZstdCompressionParameters.from_level(level, **options)
    return z.ZstdCompressor(compression_params=params).compress(original)


def descriptor(original, encoded, codec_id="zstd", mime="text/plain"):
    return dict(encoding_version=1, codec_id=codec_id, codec_version=1,
                original_size=len(original), stored_size=len(encoded), mime_type=mime,
                original_sha256=hashlib.sha256(original).hexdigest(),
                payload=base64.b64encode(encoded).decode())


def noise(size):
    return b"".join(hashlib.sha256(b"task7.6/" + i.to_bytes(4, "little")).digest()
                    for i in range((size + 31) // 32))[:size]


def frame(original, blocks=None, *, width=4, single=False, window_byte=64, claimed=None):
    """Construct frame grammar, never implement compression/checksum algorithms."""
    size = len(original) if claimed is None else claimed
    flag = {1: 0, 2: 1, 4: 2, 8: 3}[width]
    header = bytes([(flag << 6) | (32 if single else 0) | 4])
    if not single:
        header += bytes([window_byte])
    header += (size - (256 if width == 2 else 0)).to_bytes(width, "little")
    if blocks is None:
        blocks = [(0, len(original), original)]
    body = b"".join(((size << 3) | (kind << 1) | (i == len(blocks) - 1)).to_bytes(3, "little") + data
                    for i, (kind, size, data) in enumerate(blocks))
    return b"\x28\xb5\x2f\xfd" + header + body + compress(original)[-4:]


def offset_probe():
    blocks = [noise(8192)[i:i + 1024] for i in range(0, 8192, 1024)]
    blocks.append(blocks[0])
    original = b"".join(blocks)
    params = z.ZstdCompressionParameters.from_level(3, window_log=18, write_checksum=1,
                                                  write_content_size=1, write_dict_id=0)
    obj = z.ZstdCompressor(compression_params=params).compressobj(size=len(original))
    encoded = b"".join(obj.compress(block) + obj.flush(z.COMPRESSOBJ_FLUSH_BLOCK)
                       for block in blocks) + obj.flush()
    # Offset=8192, declared W=1024, each regenerated block <=1024.
    forged = (encoded[:4] + b"\x84\x00" + len(original).to_bytes(4, "little")
              + encoded[z.frame_header_size(encoded):])
    return original, forged


def build_vectors():
    vectors = []

    def add(name, original, encoded, expected="accept", *, code=None, stage=None,
            codec_id="zstd", mutate=None, profile=None):
        desc = descriptor(original, encoded, codec_id)
        if mutate:
            desc.update(mutate)
        vectors.append(dict(id=name, original=original, descriptor=desc,
                            expected=expected, code=code, stage=stage,
                            profile_expected=profile or expected))

    def bad(name, original, encoded, code, stage="frame", **kwargs):
        add(name, original, encoded, "reject", code=code, stage=stage, **kwargs)

    for original in (b"a", b"ab", b"abc", b"\x28\xb5\x2f\xfd"):
        add("identity-" + str(len(original)), original, original, codec_id="identity")
    original = b"x" * codec.MAX_SIZE
    add("identity-at-A-B", original, original, codec_id="identity")
    add("zstd-high-ratio-at-A", original, compress(original))
    original = b"strict codec hello\n" * 24
    encoded = compress(original)
    add("zstd-default", original, encoded)
    add("zstd-level9", original, compress(original, level=9))
    add("zstd-raw", original, frame(original))
    add("zstd-rle", b"x" * 512, frame(b"x" * 512, [(1, 512, b"x")]))
    for width, data in ((1, b"a"), (2, b"b" * 256), (4, b"abc"), (8, b"abc")):
        add(f"zstd-single-fcs{width}", data, frame(data, single=True, width=width))
    for width, data in ((2, b"b" * 256), (4, b"abc"), (8, b"abc")):
        add(f"zstd-multi-fcs{width}", data, frame(data, width=width))
    add("window-below", b"abc", frame(b"abc", window_byte=0))
    add("window-at", b"abc", frame(b"abc", window_byte=64))
    add("blocks-64-empty", b"a", frame(b"a", [(0, 0, b"")] * 63 + [(0, 1, b"a")]))
    data = b"a" * 64
    add("blocks-64-one-byte", data, frame(data, [(0, 1, b"a")] * 64))
    bad("blocks-65", b"a", frame(b"a", [(0, 0, b"")] * 64 + [(0, 1, b"a")]), "block_count")
    bad("invalid-magic", original, b"BAD!" + encoded[4:], "magic")
    bad("magicless", original, encoded[4:], "magic")
    bad("checksum-corrupt", original, encoded[:-1] + bytes([encoded[-1] ^ 1]), "checksum", "decode")
    for flag, code in ((0x10, "reserved_flags"), (8, "reserved_flags"), (1, "dictionary"),
                       (2, "dictionary"), (3, "dictionary")):
        bad(f"flag-{flag}", original, encoded[:4] + bytes([encoded[4] | flag]) + encoded[5:], code)
    # Explicit dictionary field zero/nonzero, not just a flag mutation.
    for flag, width in ((1, 1), (2, 2), (3, 4)):
        for value in (0, 13):
            single_header = frame(b"abc", single=True, width=4)
            e = (single_header[:4] + bytes([single_header[4] | flag])
                 + value.to_bytes(width, "little") + single_header[5:])
            bad(f"dictionary-{width}-{value}", b"abc", e, "dictionary")
    no_checksum = z.ZstdCompressor(level=3, write_checksum=False).compress(original)
    bad("checksum-missing", original, no_checksum, "checksum_required")
    no_size = z.ZstdCompressor(level=3, write_checksum=True, write_content_size=False).compress(original)
    bad("content-size-missing", original, no_size, "content_size_required")
    bad("content-size-false", original, encoded, "content_size_mismatch",
        mutate={"original_size": len(original) + 1})
    bad("hash-wrong", original, encoded, "original_hash", "integrity",
        mutate={"original_sha256": "0" * 64})
    bad("window-over", b"abc", frame(b"abc", window_byte=65), "window_limit")
    huge = z.ZstdCompressor(level=3, write_checksum=True).compress(b"x" * 300000)
    bad("single-window-over", b"x" * 300000, huge, "window_limit")
    for magic in range(0x184D2A50, 0x184D2A60):
        bad(f"skippable-{magic:x}", b"a", magic.to_bytes(4, "little") + b"\0" * 4, "skippable")
    for name, tail in (("concatenated", encoded), ("concatenated-empty", compress(b"")),
                       ("trailing-zero", b"\0"), ("trailing-garbage", b"XYZ"),
                       ("skippable-suffix", bytes.fromhex("502a4d1800000000"))):
        bad(name, original, encoded + tail, "trailing_data")
    # Every truncation boundary of a complete raw frame, including full output/no checksum.
    small = frame(b"abc")
    for n in range(1, len(small)):
        bad(f"truncated-{n}", b"abc", small[:n], "truncated")
    header = small[:10]
    bad("reserved-block", b"abc", header + (31).to_bytes(3, "little") + b"abc" + small[-4:], "block_type")
    bad("raw-block-over", b"abc", header + ((131073 << 3) | 1).to_bytes(3, "little") + b"abc" + small[-4:], "block_size")
    unfinished = bytearray(small)
    unfinished[10] &= 0xFE
    bad("last-block-missing", b"abc", bytes(unfinished), "block_size")
    for name, data in (("bad-treeless-literals", b"\x03\x00\x00"),
                       ("bad-literals-length", b"\xff\xff\xff"),
                       ("bad-sequence-tables", b"\x00\x01\xff")):
        bad(name, b"abc", frame(b"abc", [(2, len(data), data)]), "invalid_stream", "decode")
    bad("output-overrun", b"abc", frame(b"abcd", claimed=3), "invalid_stream", "decode")
    bad("output-overrun-rle", b"abc", frame(b"x" * 4, [(1, 4, b"x")], claimed=3), "invalid_stream", "decode")
    bad("output-underrun", b"abcd", frame(b"abc", claimed=4), "invalid_stream", "decode")
    large_block = compress(b"x" * 2048)
    oversized_regen = b"\x28\xb5\x2f\xfd\x84\x00" + (2048).to_bytes(4, "little") + large_block[z.frame_header_size(large_block):]
    bad("regenerated-block-over-window", b"x" * 2048, oversized_regen, "invalid_stream", "decode")
    bomb = compress(b"x" * (codec.MAX_SIZE + 1))
    bad("bomb-over-A", b"x", bomb, "original_size_limit", "descriptor",
        mutate={"original_size": codec.MAX_SIZE + 1})
    bad("bomb-lying-size", b"x", bomb, "content_size_mismatch")
    dictionary = z.ZstdCompressionDict(noise(4096), dict_type=z.DICT_TYPE_RAWCONTENT)
    dict_original = noise(4096)[-1024:]
    dict_frame = z.ZstdCompressor(level=3, dict_data=dictionary, write_checksum=True,
                                 write_content_size=True, write_dict_id=False).compress(dict_original)
    bad("unadvertised-raw-dictionary", dict_original, dict_frame, "invalid_stream", "decode")
    for name, fields, code in (
        ("unknown-codec", {"codec_id": "gzip"}, "codec_profile"),
        ("unknown-profile", {"codec_version": 2}, "codec_profile"),
        ("unknown-encoding", {"encoding_version": 2}, "encoding_version"),
        ("encoded-over-B", {"stored_size": codec.MAX_SIZE + 1}, "stored_size_limit"),
        ("empty-original", {"original_size": 0}, "original_size_limit"),
        ("empty-payload", {"stored_size": 0, "payload": ""}, "stored_size_limit"),
        ("boolean-int", {"original_size": True}, "integer_type"),
        ("float-int", {"stored_size": 3.0}, "integer_type"),
        ("string-int", {"codec_version": "1"}, "integer_type"),
        ("null-int", {"encoding_version": None}, "integer_type"),
        ("mime-alias", {"mime_type": "text/plain;charset=utf-8"}, "mime_type"),
        ("hash-uppercase", {"original_sha256": "A" * 64}, "hash_format"),
        ("extra-field", {"parameters": "forbidden"}, "keys"),
        ("base64-short", {"payload": "YQ="}, "base64_length"),
        ("base64-newline", {"payload": "YQ=\n"}, "base64_syntax"),
        ("base64-url", {"payload": "_w=="}, "base64_syntax"),
        ("base64-pad-bits", {"payload": "YR=="}, "base64_noncanonical"),
        ("stored-size-false", {"stored_size": 2}, "stored_size_mismatch"),
        ("identity-size-false", {"original_size": 2}, "identity_size"),
    ):
        bad(name, b"a", b"a", code, "frame" if name == "identity-size-false" else "descriptor",
            codec_id="identity", mutate=fields)
    item = descriptor(b"a", b"a", "identity")
    item.pop("mime_type")
    vectors.append(dict(id="missing-field", original=b"a", descriptor=item, expected="reject",
                        code="keys", stage="descriptor", profile_expected="reject"))
    original, encoded = offset_probe()
    add("offset-exceeds-declared-window", original, encoded, "unvalidated", profile="reject")
    original = noise(512 * 1024)
    original += original[-1024:]
    add("valid-cross-window-compressed", original, compress(original), "unvalidated", profile="accept")
    return vectors


def write_vectors():
    if z.__version__ != "0.25.0" or z.ZSTD_VERSION != (1, 5, 7):
        raise RuntimeError("unverified fixture encoder")
    DEST.mkdir(parents=True, exist_ok=True)
    records = []
    for item in build_vectors():
        original = item.pop("original")
        desc = item.pop("descriptor")
        original_path = "m-" + hashlib.sha256(original).hexdigest() + ".bin"
        (DEST / original_path).write_bytes(original)
        descriptor_path = item["id"] + ".json"
        raw = canonical(desc)
        (DEST / descriptor_path).write_bytes(raw)
        payload = base64.b64decode(desc["payload"], validate=False) if item["id"] not in (
            "base64-short", "base64-newline", "base64-url") else None
        records.append(item | dict(original_path=original_path, descriptor_path=descriptor_path,
                                   original_sha256=hashlib.sha256(original).hexdigest(),
                                   descriptor_sha256=hashlib.sha256(raw).hexdigest(),
                                   encoded_sha256=hashlib.sha256(payload).hexdigest() if payload is not None else None,
                                   original_bytes=len(original)))
    manifest = dict(suite_id="zoidbergchain-codec-conformance", suite_version="1.0.0",
                    layer="codec-only; no block/network/signature/media validity implied",
                    contract="Task 7.5 / zstd format 0.4.3 / libzstd 1.5.7",
                    limits=dict(A=codec.MAX_SIZE, B=codec.MAX_SIZE, window=codec.MAX_WINDOW, blocks=64),
                    provenance=dict(command=".venv/Scripts/python.exe scripts/milestone_7_task_7_6_vectors.py",
                                    encoder="zstandard 0.25.0 cext / libzstd 1.5.7",
                                    runtime="CPython 3.13.5 Windows AMD64"), vectors=records)
    raw = json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n"
    (DEST / "manifest.json").write_bytes(raw)
    (DEST / "manifest.sha256").write_text(hashlib.sha256(raw).hexdigest() + "\n", encoding="ascii")
    print(f"wrote {len(records)} vectors; manifest SHA-256 {hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    write_vectors()
