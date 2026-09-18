"""Hardened pre-review technical validation for Public Testnet v1 media.

The validator preserves accepted image bytes exactly.  Plain text is converted
to the canonical byte sequence frozen by media-admission policy v1.  Decoder
work runs in a child process; wall-clock termination is a local admission
defense and is never suitable for validating an already-certified block.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import io
import json
import multiprocessing
import os
import re
import struct
import tempfile
import unicodedata
import warnings
import zlib
from concurrent.futures import ProcessPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from PIL import Image

from media_admission_policy import (
    MEDIA_ADMISSION_POLICY_VERSION,
    OUTCOME_ACCEPT,
    OUTCOME_REJECT,
    REASON_ACCEPTED_POLICY_METADATA,
    REASON_DECLARED_MIME_MISMATCH,
    REASON_DISALLOWED_ARCHIVE,
    REASON_EXCEEDS_ACCEPTED_MEDIA_BYTE_LIMIT,
    REASON_EXCEEDS_DIMENSION_LIMIT,
    REASON_EXCEEDS_FRAME_LIMIT,
    REASON_EXCEEDS_PIXEL_LIMIT,
    REASON_EXCEEDS_REQUEST_BYTE_LIMIT,
    REASON_EXCEEDS_TEXT_BYTE_LIMIT,
    REASON_EXECUTABLE_OR_SCRIPT,
    REASON_MALFORMED_MEDIA,
    REASON_RESOURCE_LIMIT_TERMINATED,
    REASON_UNKNOWN_POLICY_VERSION,
    REASON_UNSUPPORTED_MEDIA_TYPE,
    REASON_UNSUPPORTED_METADATA,
    PolicyEvaluationInput,
    effective_local_defense_limits,
    evaluate_media_admission_policy,
    media_admission_policy,
    media_admission_policy_digest,
)
from protocol_v1 import canonical_hash


TECHNICAL_VALIDATION_EVIDENCE_VERSION = 1
TECHNICAL_VALIDATOR_ID = "zoidberg-media-technical-validator/1"
_HEX_64 = re.compile(r"^[a-f0-9]{64}$")
_IMAGE_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
_EXTENSIONS = {
    "image/jpeg": {".jpg", ".jpeg", ".jfif"},
    "image/png": {".png"},
    "image/gif": {".gif"},
    "image/webp": {".webp"},
    "text/plain": {".txt", ".text"},
}
_ARCHIVE_PREFIXES = (
    b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08", b"Rar!\x1a\x07",
    b"7z\xbc\xaf'\x1c", b"\x1f\x8b\x08", b"BZh", b"\xfd7zXZ\x00",
)
_EXECUTABLE_PREFIXES = (
    b"MZ", b"\x7fELF", b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe",
)
_UNSUPPORTED_BINARY_PREFIXES = (
    b"%PDF-", b"SQLite format 3\x00", b"OggS", b"fLaC", b"ID3",
    b"BM", b"II*\x00", b"MM\x00*", b"\x00\x00\x01\x00",
)
_SCRIPT_PREFIX = re.compile(
    rb"^\s*(?:#!|<\?(?:php|=)|<!doctype\s+html|<html\b|<script\b|<svg\b|javascript:)",
    re.IGNORECASE,
)
_ACTIVE_MARKERS = (b"<script", b"javascript:", b"<svg", b"<?php", b"#!/")
_RESERVED_WINDOWS_NAMES = {
    "CON", "PRN", "AUX", "NUL", "CLOCK$",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}

# Transport and local-admission observations remain useful evidence, but they
# are deliberately excluded from the canonical digest.  A filename is display
# metadata (never protocol identity), and a peer validating the same immutable
# media bytes must reproduce the same digest even when transport headers differ.
_NON_IDENTITY_EVIDENCE_FIELDS = {
    "declared_mime_type",
    "declared_mime_matches",
    "extension_matches_detected_type",
    "safe_display_filename",
    "staged_byte_length",
    "local_resource_defense_failure",
}


def _evidence_digest(result: Mapping[str, Any]) -> str:
    return canonical_hash({
        key: value
        for key, value in result.items()
        if key != "evidence_digest" and key not in _NON_IDENTITY_EVIDENCE_FIELDS
    })


class TechnicalMediaValidationError(ValueError):
    """A rejected local admission carrying stable machine-readable evidence."""

    def __init__(self, result: Mapping[str, Any]):
        self.result = dict(result)
        reasons = ",".join(self.result.get("reason_codes") or [REASON_MALFORMED_MEDIA])
        super().__init__(f"Technical media validation rejected the payload: {reasons}")


class MediaRequestTooLarge(Exception):
    pass


class _UnsupportedMetadataError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedMedia:
    raw_media_bytes: bytes
    text_content: str | None
    result: dict[str, Any]


def sanitize_display_filename(filename: str | None) -> str | None:
    """Return bounded ASCII display metadata; never a storage path."""
    if filename is None:
        return None
    if not isinstance(filename, str):
        raise ValueError("filename must be a string when provided.")
    candidate = unicodedata.normalize("NFKC", filename)
    candidate = candidate.replace("\x00", "_")
    candidate = re.sub(r"[\\/\u2044\u2215\u29f8\uff0f\uff3c]+", "_", candidate)
    candidate = "".join("_" if unicodedata.category(ch) == "Cc" else ch for ch in candidate)
    candidate = candidate.strip().strip(". ")
    candidate = re.sub(r"[^A-Za-z0-9._-]+", "_", candidate).strip("._ ")
    if not candidate:
        candidate = "upload"
    stem = candidate.split(".", 1)[0].upper()
    if stem in _RESERVED_WINDOWS_NAMES or re.match(r"^[A-Za-z]:", candidate):
        candidate = f"upload_{candidate}"
    maximum = media_admission_policy()["consensus_protocol"]["metadata_limits"][
        "sanitized_display_filename_ascii_bytes"
    ]
    candidate = candidate.encode("ascii", "ignore")[:maximum].decode("ascii").rstrip(". ")
    return candidate or "upload"


def _canonical_text(raw: bytes) -> tuple[bytes, str]:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise TechnicalMediaValidationError(_basic_rejection(raw, REASON_MALFORMED_MEDIA)) from exc
    # Only horizontal tab and line feeds are admitted from the ASCII/C1 control
    # ranges.  This keeps arbitrary terminal/binary control streams from being
    # classified as plain text without constraining ordinary Unicode scripts.
    if any((ord(ch) < 32 and ch not in {"\t", "\n", "\r"}) or 127 <= ord(ch) <= 159 for ch in text):
        raise TechnicalMediaValidationError(_basic_rejection(raw, REASON_UNSUPPORTED_MEDIA_TYPE))
    canonical = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not canonical:
        raise TechnicalMediaValidationError(_basic_rejection(raw, REASON_MALFORMED_MEDIA))
    return canonical.encode("utf-8"), canonical


def identify_media_type(raw: bytes) -> tuple[str | None, str | None, set[str]]:
    payload = bytes(raw)
    reasons: set[str] = set()
    if payload.startswith(_EXECUTABLE_PREFIXES):
        return None, None, {REASON_EXECUTABLE_OR_SCRIPT}
    if payload.startswith(_ARCHIVE_PREFIXES) or (len(payload) > 262 and payload[257:262] == b"ustar"):
        return None, None, {REASON_DISALLOWED_ARCHIVE}
    if payload.startswith(_UNSUPPORTED_BINARY_PREFIXES) or (
        len(payload) >= 12 and payload[4:8] == b"ftyp"
    ):
        return None, None, {REASON_UNSUPPORTED_MEDIA_TYPE}
    leading = payload[:4096].lower()
    if _SCRIPT_PREFIX.search(leading):
        return "plain_utf8_text", "text/plain", {REASON_EXECUTABLE_OR_SCRIPT}
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png", reasons
    if payload.startswith(b"\xff\xd8\xff"):
        return "jpeg", "image/jpeg", reasons
    if payload.startswith((b"GIF87a", b"GIF89a")):
        return "gif", "image/gif", reasons
    if len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return "webp", "image/webp", reasons
    try:
        payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None, None, {REASON_UNSUPPORTED_MEDIA_TYPE}
    if b"\x00" in payload:
        return None, None, {REASON_UNSUPPORTED_MEDIA_TYPE}
    return "plain_utf8_text", "text/plain", reasons


def _png_metadata(payload: bytes) -> tuple[int, int]:
    offset, width, height, saw_iend = 8, None, None, False
    supported_chunks = {
        b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"cHRM",
        b"sRGB", b"iCCP", b"tEXt", b"zTXt", b"iTXt", b"pHYs", b"sBIT",
        b"bKGD", b"hIST", b"tIME", b"eXIf",
    }
    while offset < len(payload):
        if offset + 12 > len(payload):
            raise ValueError("truncated PNG chunk")
        length = struct.unpack(">I", payload[offset:offset + 4])[0]
        chunk_type = payload[offset + 4:offset + 8]
        if chunk_type not in supported_chunks:
            raise _UnsupportedMetadataError("unsupported PNG chunk")
        end = offset + 12 + length
        if end > len(payload):
            raise ValueError("truncated PNG chunk data")
        data = payload[offset + 8:offset + 8 + length]
        if chunk_type in {b"tEXt", b"iTXt", b"eXIf"} and any(
            marker in data.lower() for marker in _ACTIVE_MARKERS
        ):
            raise PermissionError("embedded active-content marker")
        expected_crc = struct.unpack(">I", payload[offset + 8 + length:end])[0]
        if zlib.crc32(chunk_type + data) & 0xFFFFFFFF != expected_crc:
            raise ValueError("invalid PNG CRC")
        if offset == 8:
            if chunk_type != b"IHDR" or length != 13:
                raise ValueError("invalid PNG IHDR")
            width, height = struct.unpack(">II", data[:8])
        if chunk_type == b"IEND":
            if length != 0 or end != len(payload):
                raise ValueError("PNG has trailing payload")
            saw_iend = True
            break
        offset = end
    if not saw_iend or width is None or height is None:
        raise ValueError("incomplete PNG container")
    return width, height


def _jpeg_metadata(payload: bytes) -> tuple[int, int]:
    if not payload.endswith(b"\xff\xd9"):
        raise ValueError("JPEG has no terminal EOI")
    offset = 2
    sof = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while offset + 1 < len(payload):
        if payload[offset] != 0xFF:
            offset += 1
            continue
        while offset < len(payload) and payload[offset] == 0xFF:
            offset += 1
        if offset >= len(payload):
            break
        marker = payload[offset]
        offset += 1
        if marker in {0x00, 0x01, *range(0xD0, 0xDA)}:
            continue
        if marker == 0xD9:
            break
        if offset + 2 > len(payload):
            raise ValueError("truncated JPEG segment")
        length = struct.unpack(">H", payload[offset:offset + 2])[0]
        if length < 2 or offset + length > len(payload):
            raise ValueError("invalid JPEG segment length")
        if marker in sof:
            if length < 7:
                raise ValueError("invalid JPEG SOF")
            height, width = struct.unpack(">HH", payload[offset + 3:offset + 7])
            return width, height
        segment_data = payload[offset + 2:offset + length]
        if (marker == 0xFE or marker == 0xE1) and any(
            active in segment_data.lower() for active in _ACTIVE_MARKERS
        ):
            raise PermissionError("embedded active-content marker")
        offset += length
    raise ValueError("JPEG dimensions are missing")


def _gif_metadata(payload: bytes) -> tuple[int, int]:
    if len(payload) < 14 or not payload.endswith(b";"):
        raise ValueError("incomplete GIF container")
    return struct.unpack("<HH", payload[6:10])


def _webp_metadata(payload: bytes) -> tuple[int | None, int | None]:
    if len(payload) < 20 or struct.unpack("<I", payload[4:8])[0] + 8 != len(payload):
        raise ValueError("invalid WebP RIFF length")
    offset = 12
    allowed = {b"VP8 ", b"VP8L", b"VP8X", b"ALPH", b"ANIM", b"ANMF", b"ICCP", b"EXIF", b"XMP "}
    while offset < len(payload):
        if offset + 8 > len(payload):
            raise ValueError("truncated WebP chunk")
        kind = payload[offset:offset + 4]
        size = struct.unpack("<I", payload[offset + 4:offset + 8])[0]
        end = offset + 8 + size + (size & 1)
        if kind not in allowed:
            raise _UnsupportedMetadataError("unsupported WebP chunk")
        if end > len(payload):
            raise ValueError("invalid WebP chunk")
        if kind in {b"EXIF", b"XMP "} and any(
            marker in payload[offset + 8:offset + 8 + size].lower()
            for marker in _ACTIVE_MARKERS
        ):
            raise PermissionError("embedded active-content marker")
        offset = end
    if offset != len(payload):
        raise ValueError("invalid WebP padding")
    return None, None


def _container_metadata(payload: bytes, mime_type: str) -> tuple[int | None, int | None]:
    if mime_type == "image/png":
        return _png_metadata(payload)
    if mime_type == "image/jpeg":
        return _jpeg_metadata(payload)
    if mime_type == "image/gif":
        return _gif_metadata(payload)
    if mime_type == "image/webp":
        return _webp_metadata(payload)
    raise ValueError("unsupported image type")


def _decode_image_worker(payload: bytes, expected_mime: str, memory_limit: int) -> dict[str, int]:
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))
    except (ImportError, OSError, ValueError):
        pass
    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory(prefix="zoidberg-media-worker-") as empty_dir:
        os.chdir(empty_dir)
        old_max_pixels = Image.MAX_IMAGE_PIXELS
        try:
            Image.MAX_IMAGE_PIXELS = None
            with warnings.catch_warnings():
                warnings.simplefilter("error")
                with Image.open(io.BytesIO(payload)) as verifier:
                    actual_mime = Image.MIME.get(verifier.format)
                    if actual_mime != expected_mime:
                        raise ValueError("decoder format differs from signature")
                    verifier.verify()
                with Image.open(io.BytesIO(payload)) as source:
                    actual_mime = Image.MIME.get(source.format)
                    if actual_mime != expected_mime:
                        raise ValueError("decoder format differs from signature")
                    width, height = source.size
                    frames = int(getattr(source, "n_frames", 1))
                    aggregate = 0
                    for frame_number in range(frames):
                        source.seek(frame_number)
                        if source.size != (width, height):
                            raise ValueError("frame dimensions differ")
                        aggregate += source.width * source.height
                        source.convert("RGBA").load()
            return {"width": width, "height": height, "frame_count": frames, "aggregate_decoded_pixels": aggregate}
        finally:
            Image.MAX_IMAGE_PIXELS = old_max_pixels
            os.chdir(old_cwd)


def _run_isolated_decoder(payload: bytes, mime_type: str, *, timeout_seconds: int, memory_limit: int) -> dict[str, int]:
    context = multiprocessing.get_context("spawn" if os.name == "nt" else "fork")
    executor = ProcessPoolExecutor(max_workers=1, mp_context=context)
    future = executor.submit(_decode_image_worker, payload, mime_type, memory_limit)
    timed_out = False
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeoutError as exc:
        timed_out = True
        future.cancel()
        for process in getattr(executor, "_processes", {}).values():
            process.terminate()
        raise TimeoutError("structural decode budget exceeded") from exc
    finally:
        executor.shutdown(wait=not timed_out, cancel_futures=True)


def _basic_rejection(raw: bytes, reason: str, *, declared_mime_type: str | None = None) -> dict[str, Any]:
    policy = media_admission_policy()
    result = {
        "evidence_version": TECHNICAL_VALIDATION_EVIDENCE_VERSION,
        "validator_id": TECHNICAL_VALIDATOR_ID,
        "policy_id": policy["policy_id"],
        "policy_version": policy["policy_version"],
        "policy_digest": media_admission_policy_digest(),
        "outcome": OUTCOME_REJECT,
        "reason_codes": [reason],
        "detected_media_type": None,
        "detected_mime_type": None,
        "declared_mime_type": declared_mime_type,
        "declared_mime_matches": None,
        "extension_matches_detected_type": None,
        "safe_display_filename": None,
        "staged_byte_length": len(raw),
        "raw_media_byte_length": len(raw),
        "raw_media_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_media_semantics": "exact_input_bytes",
        "width_pixels": None,
        "height_pixels": None,
        "frame_count": None,
        "aggregate_decoded_pixels": None,
        "local_resource_defense_failure": reason == REASON_RESOURCE_LIMIT_TERMINATED,
    }
    result["evidence_digest"] = _evidence_digest(result)
    return result


def validate_media_bytes(
    raw_upload_bytes: bytes,
    *,
    declared_mime_type: str | None = None,
    original_filename: str | None = None,
    policy_version: int = MEDIA_ADMISSION_POLICY_VERSION,
    local_defense_overrides: Mapping[str, int] | None = None,
) -> ValidatedMedia:
    raw = bytes(raw_upload_bytes)
    if policy_version != MEDIA_ADMISSION_POLICY_VERSION:
        raise TechnicalMediaValidationError(_basic_rejection(raw, REASON_UNKNOWN_POLICY_VERSION))
    safe_name = sanitize_display_filename(original_filename)
    declared = str(declared_mime_type).split(";", 1)[0].strip().lower() if declared_mime_type else None
    if declared == "application/octet-stream":
        declared = None
    media_type, detected, early_reasons = identify_media_type(raw)
    text_content = None
    accepted = raw
    raw_semantics = "exact_input_bytes"
    if detected == "text/plain" and REASON_EXECUTABLE_OR_SCRIPT not in early_reasons:
        accepted, text_content = _canonical_text(raw)
        raw_semantics = "policy_canonical_utf8_text"

    policy = media_admission_policy(policy_version)
    byte_limit = policy["consensus_protocol"]["byte_limits"][
        "accepted_plain_text_bytes_after_canonicalization" if detected == "text/plain" else "accepted_image_bytes"
    ]
    metadata = PolicyEvaluationInput(
        detected_mime_type=detected,
        declared_mime_type=declared,
        accepted_media_bytes=len(accepted),
    )
    policy_result = evaluate_media_admission_policy(metadata, version=policy_version)
    reasons = set(early_reasons)
    reasons.update(code for code in policy_result["reason_codes"] if code != REASON_ACCEPTED_POLICY_METADATA)
    if not raw:
        reasons.add(REASON_MALFORMED_MEDIA)
    if len(accepted) > byte_limit:
        reasons.add(REASON_EXCEEDS_TEXT_BYTE_LIMIT if detected == "text/plain" else REASON_EXCEEDS_ACCEPTED_MEDIA_BYTE_LIMIT)

    width = height = frame_count = aggregate = None
    if detected in _IMAGE_MIMES and not reasons:
        try:
            header_width, header_height = _container_metadata(raw, detected)
        except PermissionError:
            reasons.add(REASON_EXECUTABLE_OR_SCRIPT)
        except _UnsupportedMetadataError:
            reasons.add(REASON_UNSUPPORTED_METADATA)
        except (ValueError, struct.error):
            reasons.add(REASON_MALFORMED_MEDIA)
        else:
            if header_width is not None and header_height is not None:
                preliminary = evaluate_media_admission_policy(PolicyEvaluationInput(
                    detected_mime_type=detected, accepted_media_bytes=len(raw),
                    width_pixels=header_width, height_pixels=header_height,
                    aggregate_decoded_pixels=header_width * header_height,
                ))
                reasons.update(code for code in preliminary["reason_codes"] if code != REASON_ACCEPTED_POLICY_METADATA)
    if detected in _IMAGE_MIMES and not reasons:
        limits = effective_local_defense_limits(local_defense_overrides)
        try:
            decoded = _run_isolated_decoder(
                raw, detected,
                timeout_seconds=limits["structural_decode_wall_time_seconds"],
                memory_limit=limits["worker_memory_bytes"],
            )
            width, height = decoded["width"], decoded["height"]
            frame_count = decoded["frame_count"]
            aggregate = decoded["aggregate_decoded_pixels"]
            structural = evaluate_media_admission_policy(PolicyEvaluationInput(
                detected_mime_type=detected,
                accepted_media_bytes=len(raw),
                width_pixels=width,
                height_pixels=height,
                frame_count=frame_count,
                aggregate_decoded_pixels=aggregate,
            ))
            reasons.update(code for code in structural["reason_codes"] if code != REASON_ACCEPTED_POLICY_METADATA)
        except TimeoutError:
            reasons.add(REASON_RESOURCE_LIMIT_TERMINATED)
        except Exception:
            reasons.add(REASON_MALFORMED_MEDIA)

    extension_match = None
    if safe_name and detected:
        suffix = Path(safe_name).suffix.lower()
        extension_match = suffix in _EXTENSIONS[detected] if suffix else None
    result = {
        "evidence_version": TECHNICAL_VALIDATION_EVIDENCE_VERSION,
        "validator_id": TECHNICAL_VALIDATOR_ID,
        "policy_id": policy["policy_id"],
        "policy_version": policy["policy_version"],
        "policy_digest": media_admission_policy_digest(policy_version),
        "outcome": OUTCOME_REJECT if reasons else OUTCOME_ACCEPT,
        "reason_codes": sorted(reasons) if reasons else [REASON_ACCEPTED_POLICY_METADATA],
        "detected_media_type": media_type,
        "detected_mime_type": detected,
        "declared_mime_type": declared,
        "declared_mime_matches": None if declared is None or detected is None else declared == detected,
        "extension_matches_detected_type": extension_match,
        "safe_display_filename": safe_name,
        "staged_byte_length": len(raw),
        "raw_media_byte_length": len(accepted),
        "raw_media_sha256": hashlib.sha256(accepted).hexdigest(),
        "raw_media_semantics": raw_semantics,
        "width_pixels": width,
        "height_pixels": height,
        "frame_count": frame_count,
        "aggregate_decoded_pixels": aggregate,
        "local_resource_defense_failure": REASON_RESOURCE_LIMIT_TERMINATED in reasons,
    }
    result["evidence_digest"] = _evidence_digest(result)
    if reasons:
        raise TechnicalMediaValidationError(result)
    return ValidatedMedia(accepted, text_content, result)


def validate_technical_evidence(evidence: Mapping[str, Any], raw_media_bytes: bytes) -> dict[str, Any]:
    if not isinstance(evidence, Mapping):
        raise ValueError("Technical validation evidence is required.")
    result = dict(evidence)
    digest = result.pop("evidence_digest", None)
    if result.get("evidence_version") != TECHNICAL_VALIDATION_EVIDENCE_VERSION:
        raise ValueError("Unsupported technical validation evidence version.")
    if result.get("validator_id") != TECHNICAL_VALIDATOR_ID:
        raise ValueError("Unsupported technical validator identity.")
    if result.get("policy_version") != MEDIA_ADMISSION_POLICY_VERSION:
        raise ValueError("Unsupported media-admission policy version.")
    if result.get("policy_digest") != media_admission_policy_digest():
        raise ValueError("Technical validation policy digest is invalid.")
    if result.get("outcome") != OUTCOME_ACCEPT:
        raise ValueError("Technical validation evidence is not an acceptance.")
    raw = bytes(raw_media_bytes)
    if result.get("raw_media_byte_length") != len(raw) or result.get("raw_media_sha256") != hashlib.sha256(raw).hexdigest():
        raise ValueError("Technical validation evidence does not bind these media bytes.")
    if digest != _evidence_digest(result):
        raise ValueError("Technical validation evidence digest is invalid.")
    result["evidence_digest"] = digest
    return result


def decode_canonical_media_bounded(payload: Mapping[str, Any]) -> bytes:
    limit = media_admission_policy()["consensus_protocol"]["byte_limits"]["accepted_image_bytes"]
    if not isinstance(payload, Mapping):
        raise ValueError("Canonical media payload is invalid.")
    if set(payload) == {"$type", "$encoding", "$value"}:
        if payload.get("$type") != "bytes" or payload.get("$encoding") != "hex" or not isinstance(payload.get("$value"), str):
            raise ValueError("Canonical media payload is invalid.")
        encoded = payload["$value"]
        if len(encoded) > limit * 2:
            raise ValueError("Canonical media payload exceeds the accepted-media byte limit.")
        if len(encoded) % 2 or any(character not in "0123456789abcdef" for character in encoded):
            raise ValueError("Canonical media payload is invalid.")
        raw = bytes.fromhex(encoded)
    elif set(payload) == {"encoding", "data"}:
        if payload.get("encoding") != "base64" or not isinstance(payload.get("data"), str):
            raise ValueError("Canonical media payload is invalid.")
        encoded = payload["data"]
        if len(encoded) > ((limit + 2) // 3) * 4:
            raise ValueError("Canonical media payload exceeds the accepted-media byte limit.")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Canonical media payload is invalid.") from exc
    else:
        raise ValueError("Canonical media payload is invalid.")
    if len(raw) > limit:
        raise ValueError("Canonical media payload exceeds the accepted-media byte limit.")
    return raw


async def read_upload_file_bounded(upload, *, chunk_size: int = 64 * 1024) -> bytes:
    policy = media_admission_policy()
    limit = max(policy["consensus_protocol"]["byte_limits"]["accepted_image_bytes"], policy["consensus_protocol"]["byte_limits"]["accepted_plain_text_bytes_after_canonicalization"])
    chunks, total = [], 0
    while True:
        chunk = await upload.read(min(chunk_size, limit + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise TechnicalMediaValidationError(_basic_rejection(b"", REASON_EXCEEDS_ACCEPTED_MEDIA_BYTE_LIMIT))
        chunks.append(chunk)
    return b"".join(chunks)


class TechnicalMediaRequestLimitMiddleware:
    """ASGI receive wrapper that bounds candidate-media request bodies."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        content_type = dict(scope.get("headers") or []).get(b"content-type", b"").decode("latin1").lower()
        limits = effective_local_defense_limits()
        if path == "/content/text":
            limit = limits["text_upload_json_body_bytes"]
        elif path in {"/content/upload", "/submit_content", "/add_block"} and "multipart/form-data" in content_type:
            limit = limits["multipart_request_body_bytes"]
        elif path in {"/peers/submissions/receive", "/peers/originality-evidence/receive"}:
            limit = limits["staged_uploaded_payload_bytes"]
        else:
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = 0
        if declared > limit:
            return await self._reject(send)
        total = 0

        async def bounded_receive():
            nonlocal total
            message = await receive()
            if message.get("type") == "http.request":
                total += len(message.get("body", b""))
                if total > limit:
                    raise MediaRequestTooLarge
            return message

        try:
            await self.app(scope, bounded_receive, send)
        except MediaRequestTooLarge:
            await self._reject(send)

    @staticmethod
    async def _reject(send):
        body = json.dumps({"error": "Media request exceeds the bounded staging limit.", "code": REASON_EXCEEDS_REQUEST_BYTE_LIMIT}, separators=(",", ":")).encode()
        await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
