"""Task 7.6 codec boundary, NOT a block/media/admission validator.

Frozen profile: Task 7.5, zstd format 0.4.3 / libzstd 1.5.7.
Reconstruction uses the statically linked CFFI bridge in zstandard 0.25.0;
Task 7.6A verifies sequences independently before native reconstruction.
No encoder, dictionary, dynamic plugin, fallback, or production imports.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass

from .sequence_verifier import VerificationReject, WorkStats, verify_sequences

MAX_SIZE = 2 * 1024 * 1024  # Candidate A/B, NOT an activated policy.
MAX_WINDOW = 262144
MAX_BLOCKS = 64
MAX_NATIVE_ARENA = 1048576  # Local fail-closed allocation guard, not validity.
KEYS = frozenset(("encoding_version", "codec_id", "codec_version", "original_size",
                  "stored_size", "mime_type", "original_sha256", "payload"))
MIMES = frozenset(("text/plain", "image/jpeg", "image/png", "image/gif", "image/webp"))


class CodecReject(ValueError):
    """Deterministic invalid input. Stable code/stage; never native error text."""

    def __init__(self, code: str, stage: str):
        self.code, self.stage = code, stage
        super().__init__(f"{stage}:{code}")


class DecoderUnavailable(RuntimeError):
    """Local backend/resource failure: unvalidated, NEVER consensus-invalid."""


def reject(code: str, stage: str = "descriptor") -> None:
    raise CodecReject(code, stage)


@dataclass(frozen=True)
class FrameInfo:
    content_size: int
    window: int
    header_size: int
    block_count: int
    block_types: tuple[int, ...]


@dataclass(frozen=True)
class DecodeResult:
    original: bytes
    consumed: int
    produced: int
    frame: FrameInfo | None
    output_capacity: int
    native_arena_bytes: int
    native_reported_bytes: int
    native_calls: int
    work: WorkStats | None = None


def parse_descriptor(raw: bytes) -> dict:
    """Bounded canonical standalone descriptor JSON; no block/version parsing."""
    if type(raw) is not bytes or len(raw) > 4 * ((MAX_SIZE + 2) // 3) + 2048:
        reject("json_size")
    # This schema is flat. Reject nesting before building a JSON object tree.
    quoted = escaped = False
    depth = 0
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (123, 91):
            depth += 1
            if depth > 1 or byte == 91:
                reject("json_shape")
        elif byte in (125, 93):
            depth -= 1

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                reject("duplicate_key")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, CodecReject):
            raise
        reject("json_syntax")
    if canonical != raw:
        reject("noncanonical_json")
    return value


def _payload(descriptor: dict) -> bytes:
    if type(descriptor) is not dict or descriptor.keys() != KEYS:
        reject("keys")
    for name in ("encoding_version", "codec_version", "original_size", "stored_size"):
        if type(descriptor[name]) is not int:
            reject("integer_type")
    if descriptor["encoding_version"] != 1:
        reject("encoding_version")
    if (type(descriptor["codec_id"]) is not str or len(descriptor["codec_id"]) > 8
            or descriptor["codec_id"] not in ("identity", "zstd")
            or descriptor["codec_version"] != 1):
        reject("codec_profile")
    for name in ("original_size", "stored_size"):
        if not 1 <= descriptor[name] <= MAX_SIZE:
            reject(name + "_limit")
    if (type(descriptor["mime_type"]) is not str or len(descriptor["mime_type"]) > 10
            or descriptor["mime_type"] not in MIMES):
        reject("mime_type")
    digest = descriptor["original_sha256"]
    if type(digest) is not str or re.fullmatch("[0-9a-f]{64}", digest) is None:
        reject("hash_format")
    payload = descriptor["payload"]
    if type(payload) is not str or len(payload) != 4 * ((descriptor["stored_size"] + 2) // 3):
        reject("base64_length")
    try:
        encoded = base64.b64decode(payload, validate=True)
    except (ValueError, binascii.Error):
        reject("base64_syntax")
    if len(encoded) != descriptor["stored_size"]:
        reject("stored_size_mismatch")
    if base64.b64encode(encoded).decode("ascii") != payload:
        reject("base64_noncanonical")
    return encoded


def inspect_frame(encoded: bytes, original_size: int) -> FrameInfo:
    """Structural preflight only; compressed internals/checksum need native decode."""
    if type(encoded) is not bytes or not 1 <= len(encoded) <= MAX_SIZE:
        reject("stored_size_limit", "frame")
    if type(original_size) is not int or not 1 <= original_size <= MAX_SIZE:
        reject("original_size_limit", "frame")
    offset = 0

    def take(count: int) -> bytes:
        nonlocal offset
        if count > len(encoded) - offset:
            reject("truncated", "frame")
        data = encoded[offset:offset + count]
        offset += count
        return data

    magic = int.from_bytes(take(4), "little")
    if 0x184D2A50 <= magic <= 0x184D2A5F:
        reject("skippable", "frame")
    if magic != 0xFD2FB528:
        reject("magic", "frame")
    descriptor = take(1)[0]
    if descriptor & 0x18:
        reject("reserved_flags", "frame")
    if descriptor & 3:
        reject("dictionary", "frame")
    if not descriptor & 4:
        reject("checksum_required", "frame")
    single = bool(descriptor & 32)
    window = None
    if not single:
        value = take(1)[0]
        base = 1 << (10 + (value >> 3))
        window = base + (base // 8) * (value & 7)
    width = (1 if single else 0, 2, 4, 8)[descriptor >> 6]
    if not width:
        reject("content_size_required", "frame")
    size = int.from_bytes(take(width), "little") + (256 if width == 2 else 0)
    if size != original_size:
        reject("content_size_mismatch", "frame")
    window = size if single else window
    if window > MAX_WINDOW:
        reject("window_limit", "frame")
    header_size = offset
    types = []
    while True:
        if len(types) == MAX_BLOCKS:
            reject("block_count", "frame")
        block = int.from_bytes(take(3), "little")
        kind, count = (block >> 1) & 3, block >> 3
        if kind == 3:
            reject("block_type", "frame")
        if count > min(window, 131072):
            reject("block_size", "frame")
        types.append(kind)
        # No allocation proportional to block length during the walk.
        body_size = 1 if kind == 1 else count
        if body_size > len(encoded) - offset:
            reject("truncated", "frame")
        offset += body_size
        if block & 1:
            break
    take(4)
    if offset != len(encoded):
        reject("trailing_data", "frame")
    return FrameInfo(size, window, header_size, len(types), tuple(types))


def _backend():
    try:
        import zstandard
        from zstandard._cffi import ffi, lib
    except ImportError as exc:
        raise DecoderUnavailable("pinned CFFI bridge unavailable") from exc
    if zstandard.__version__ != "0.25.0" or lib.ZSTD_versionNumber() != 10507:
        raise DecoderUnavailable("unverified backend version")
    return ffi, lib


def _decode_native(encoded: bytes, info: FrameInfo, expected_work: WorkStats | None = None):
    """Bufferless streaming: exact next input, per-block destination capacity.

    Full contiguous output retains history. Static context cannot malloc/realloc.
    Each call consumes exactly its requested input slice or returns an error.
    nextSrcSize == 0 is the terminal/checksum-verified signal, not output length.
    """
    ffi, lib = _backend()
    required = int(lib.ZSTD_estimateDCtxSize())
    if not 0 < required <= MAX_NATIVE_ARENA:
        raise DecoderUnavailable("native context exceeds local arena budget")
    arena = ffi.new("unsigned long long[]", (required + 7) // 8)
    arena_size = ffi.sizeof(arena)
    context = lib.ZSTD_initStaticDCtx(arena, arena_size)
    if context == ffi.NULL:
        raise DecoderUnavailable("static context initialization failed")

    def checked(result, setup=False):
        if lib.ZSTD_isError(result):
            code = lib.ZSTD_getErrorCode(result)
            if setup or code in (lib.ZSTD_error_memory_allocation, lib.ZSTD_error_workSpace_tooSmall):
                raise DecoderUnavailable("native setup/resource failure")
            # Do not expose native English messages as protocol categories.
            if code == lib.ZSTD_error_checksum_wrong:
                reject("checksum", "decode")
            reject("invalid_stream", "decode")
        return int(result)

    checked(lib.ZSTD_decompressBegin(context), setup=True)
    checked(lib.ZSTD_DCtx_setMaxWindowSize(context, MAX_WINDOW), setup=True)
    checked(lib.ZSTD_DCtx_setParameter(context, lib.ZSTD_d_forceIgnoreChecksum,
                                    lib.ZSTD_d_validateChecksum), setup=True)
    output = ffi.new("char[]", info.content_size)  # Exactly M bytes; no terminator.
    source = ffi.from_buffer("const char[]", encoded)
    consumed = produced = calls = 0
    compressed_history_unproven = False
    current_kind = None
    current_block = -1
    # Every successful nonterminal call consumes >= 1 byte; progress is explicit.
    while True:
        needed = int(lib.ZSTD_nextSrcSizeToDecompress(context))
        if needed == 0:
            break
        if needed > len(encoded) - consumed:
            reject("incomplete", "decode")
        capacity = min(info.content_size - produced, info.window, 131072)
        # Native input types: 2=block body, 3=last block body (pinned zstd.h).
        input_type = int(lib.ZSTD_nextInputType(context))
        if input_type == int(lib.ZSTDnit_blockHeader):
            current_kind = (encoded[consumed] >> 1) & 3
            current_block += 1
        count = checked(lib.ZSTD_decompressContinue(
            context, output + produced, capacity, source + consumed, needed))
        if count > capacity:
            raise DecoderUnavailable("backend violated output capacity")
        consumed += needed
        produced += count
        if input_type in (int(lib.ZSTDnit_block), int(lib.ZSTDnit_lastBlock)):
            if expected_work is not None and count != expected_work.block_output_sizes[current_block]:
                raise DecoderUnavailable("sequence/native block-size disagreement")
            if current_kind == 2 and produced > info.window:
                compressed_history_unproven = True
        calls += 1
    if consumed != len(encoded):
        reject("unconsumed_input", "decode")
    if produced != info.content_size:
        reject("output_size", "decode")
    # Hash before copying into the returned immutable Python bytes.
    view = ffi.buffer(output, produced)
    digest = hashlib.sha256(view).hexdigest()
    return (bytes(view), digest, arena_size, int(lib.ZSTD_sizeof_DCtx(context)), calls,
            compressed_history_unproven)


def decode(descriptor: dict) -> DecodeResult:
    """Validate codec representation, reconstruct exact bytes and verify SHA-256.

    MIME membership only: container validity, text canonicalization, evidence,
    protocol/network/block versions and signatures are OUTSIDE this boundary.
    MemoryError/backend failures mean local unavailability, never invalid input.
    """
    try:
        encoded = _payload(descriptor)
        size = descriptor["original_size"]
        if descriptor["codec_id"] == "identity":
            if len(encoded) != size:
                reject("identity_size", "frame")
            original, digest = encoded, hashlib.sha256(encoded).hexdigest()
            info = None
            work = None
            arena = reported = calls = 0
        else:
            info = inspect_frame(encoded, size)
            try:
                work = verify_sequences(encoded, info)
            except VerificationReject as exc:
                reject(str(exc), "decode")
            original, digest, arena, reported, calls, _history_beyond_window = _decode_native(encoded, info, work)
        if digest != descriptor["original_sha256"]:
            reject("original_hash", "integrity")
        return DecodeResult(original, len(encoded), len(original), info, size, arena, reported, calls, work)
    except MemoryError as exc:
        raise DecoderUnavailable("local allocation failure; input remains unvalidated") from exc
