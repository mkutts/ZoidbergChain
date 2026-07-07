from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import config


CONTENT_TYPE_IMAGE = "image"
CONTENT_TYPE_TEXT = "text"
CONTENT_TYPE_MIXED = "mixed"
CONTENT_TYPES = {CONTENT_TYPE_IMAGE, CONTENT_TYPE_TEXT, CONTENT_TYPE_MIXED}

STORAGE_STATUS_MISSING = "missing"
STORAGE_STATUS_LOCAL = "local"
STORAGE_STATUS_REMOTE = "remote"
STORAGE_STATUS_VERIFIED = "verified"
STORAGE_STATUSES = {
    STORAGE_STATUS_MISSING,
    STORAGE_STATUS_LOCAL,
    STORAGE_STATUS_REMOTE,
    STORAGE_STATUS_VERIFIED,
}

TEXT_MIME_TYPE = "text/plain"
SUPPORTED_CONTENT_MIME_TYPES = set(config.SUPPORTED_CONTENT_MIME_TYPES)
SUPPORTED_IMAGE_MIME_TYPES = set(config.SUPPORTED_IMAGE_MIME_TYPES)
SUPPORTED_TEXT_MIME_TYPES = set(config.SUPPORTED_TEXT_MIME_TYPES)
CONTENT_MIME_EXTENSIONS = {
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    TEXT_MIME_TYPE: ".txt",
}

_HEX_32_PATTERN = re.compile(r"^[a-f0-9]{32}$")
_HEX_64_PATTERN = re.compile(r"^[a-f0-9]{64}$")

HASH_SCHEME_SHA256_BYTES = "sha256_bytes"
HASH_SCHEME_SHA256_TEXT = "sha256_text"
HASH_SCHEME_LEGACY = "legacy"
HASH_SCHEME_UNKNOWN = "unknown"
HASH_SCHEMES = {
    HASH_SCHEME_SHA256_BYTES,
    HASH_SCHEME_SHA256_TEXT,
    HASH_SCHEME_LEGACY,
    HASH_SCHEME_UNKNOWN,
}


def _normalize_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _normalize_json_value(child)
            for key, child in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_json_value(item) for item in value]
    return value


def _canonical_json(data: Any) -> str:
    try:
        return json.dumps(_normalize_json_value(data), sort_keys=True, separators=(",", ":"))
    except TypeError as exc:
        raise ValueError("Content metadata must be JSON serializable.") from exc


def _content_root_for(data_dir: str | None = None, content_storage_dir: str | None = None) -> Path:
    if content_storage_dir:
        return Path(content_storage_dir)
    if data_dir:
        return Path(data_dir) / "content"
    return Path(config.CONTENT_STORAGE_DIR)


def ensure_content_storage_dir(*, data_dir: str | None = None, content_storage_dir: str | None = None) -> str:
    content_root = _content_root_for(data_dir=data_dir, content_storage_dir=content_storage_dir)
    content_root.mkdir(parents=True, exist_ok=True)
    return str(content_root)


def compute_content_hash_bytes(data: bytes) -> str:
    if not isinstance(data, (bytes, bytearray)):
        raise ValueError("Content bytes are required.")
    return hashlib.sha256(bytes(data)).hexdigest()


def canonicalize_text_content(text_content: str) -> str:
    if not isinstance(text_content, str):
        raise ValueError("text_content is required.")
    normalized = text_content.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise ValueError("text_content is required.")
    return normalized


def compute_text_content_hash(text_content: str) -> str:
    return compute_content_hash_bytes(canonicalize_text_content(text_content).encode("utf-8"))


def _validate_hash_scheme(hash_scheme: str | None) -> str:
    if hash_scheme in (None, ""):
        return HASH_SCHEME_UNKNOWN
    if not isinstance(hash_scheme, str) or hash_scheme.strip() not in HASH_SCHEMES:
        raise ValueError(f"Invalid hash_scheme: {hash_scheme!r}")
    return hash_scheme.strip()


def _coerce_optional_float(value: float | int | None, field_name: str) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid timestamp when provided.") from exc
    return numeric


def _clean_optional_string(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _recover_legacy_original_filename(
    *,
    content_hash: str,
    file_name: str,
    file_size_bytes: int,
    byte_hash: str | None,
    data_dir: str | None,
    managed_file_path: str | None,
) -> str | None:
    """Best-effort recovery for snapshots that predate persisted content object metadata."""
    if not data_dir or not byte_hash:
        return None

    managed_name = Path(file_name).stem.lower()
    if managed_name != content_hash.lower():
        return None

    data_root = Path(data_dir)
    content_root = _content_root_for(data_dir=data_dir)
    managed_resolved = Path(managed_file_path).resolve() if managed_file_path else None

    for candidate in data_root.rglob("*"):
        if not candidate.is_file():
            continue
        try:
            candidate.relative_to(content_root)
            continue
        except ValueError:
            pass
        if managed_resolved is not None and candidate.resolve() == managed_resolved:
            continue
        if candidate.stat().st_size != file_size_bytes:
            continue
        try:
            candidate_bytes = candidate.read_bytes()
        except OSError:
            continue
        if compute_content_hash_bytes(candidate_bytes) == byte_hash:
            return candidate.name

    return None


def calculate_content_hash(
    *,
    content_type: str,
    mime_type: str,
    text_content: str | None = None,
    caption: str | None = None,
    file_name: str | None = None,
    file_size_bytes: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    payload = {
        "content_type": content_type,
        "mime_type": mime_type,
        "text_content": (text_content or "").strip(),
        "caption": (caption or "").strip(),
        "file_name": file_name,
        "file_size_bytes": file_size_bytes,
        "metadata": metadata or {},
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def calculate_content_id(content_hash: str) -> str:
    if not isinstance(content_hash, str) or not _HEX_64_PATTERN.fullmatch(content_hash.strip()):
        raise ValueError("content_hash must be a 64-character lowercase hexadecimal string.")
    return hashlib.sha256(content_hash.strip().encode("utf-8")).hexdigest()[:32]


def guess_mime_type(file_name: str | None, default: str = "application/octet-stream") -> str:
    if not file_name:
        return default
    mime_type, _encoding = mimetypes.guess_type(file_name)
    return mime_type or default


def infer_content_type(image_path: str | None, text_content: str | None) -> str:
    has_image = bool(image_path)
    has_text = bool((text_content or "").strip())
    if has_image and has_text:
        return CONTENT_TYPE_MIXED
    if has_image:
        return CONTENT_TYPE_IMAGE
    return CONTENT_TYPE_TEXT


def _validate_content_type(content_type: str) -> str:
    if not isinstance(content_type, str) or content_type.strip() not in CONTENT_TYPES:
        raise ValueError(f"Invalid content_type: {content_type!r}")
    return content_type.strip()


def _validate_storage_status(storage_status: str) -> str:
    if not isinstance(storage_status, str) or storage_status.strip() not in STORAGE_STATUSES:
        raise ValueError(f"Invalid storage_status: {storage_status!r}")
    return storage_status.strip()


def _validate_non_empty_string(value: str | None, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required.")
    return value.strip()


def _validate_optional_file_size(file_size_bytes: int | None) -> int | None:
    if file_size_bytes is None:
        return None
    if not isinstance(file_size_bytes, int) or file_size_bytes < 0:
        raise ValueError("file_size_bytes must be a non-negative integer when provided.")
    return file_size_bytes


def _validate_content_hash_value(content_hash: str) -> str:
    if not isinstance(content_hash, str) or not _HEX_64_PATTERN.fullmatch(content_hash.strip()):
        raise ValueError("content_hash must be a 64-character lowercase hexadecimal string.")
    return content_hash.strip()


def _validate_supported_mime_type(mime_type: str) -> str:
    normalized = _validate_non_empty_string(mime_type, "mime_type").lower()
    if normalized not in SUPPORTED_CONTENT_MIME_TYPES:
        supported = ", ".join(sorted(SUPPORTED_CONTENT_MIME_TYPES))
        raise ValueError(f"Unsupported mime_type: {normalized!r}. Supported types: {supported}.")
    return normalized


def validate_mime_type(mime_type: str) -> str:
    return _validate_supported_mime_type(mime_type)


def validate_content_size(size_bytes: int, *, mime_type: str | None = None) -> int:
    if not isinstance(size_bytes, int) or size_bytes < 0:
        raise ValueError("size_bytes must be a non-negative integer.")
    if size_bytes == 0:
        raise ValueError("Uploaded file is empty.")
    if mime_type == TEXT_MIME_TYPE and size_bytes > config.MAX_TEXT_CONTENT_BYTES:
        raise ValueError(f"Text content exceeds max size of {config.MAX_TEXT_CONTENT_BYTES} bytes.")
    if size_bytes > config.MAX_CONTENT_FILE_SIZE_BYTES:
        raise ValueError(f"Content file exceeds max size of {config.MAX_CONTENT_FILE_SIZE_BYTES} bytes.")
    return size_bytes


def validate_caption(caption: str | None) -> str | None:
    if caption is None:
        return None
    if not isinstance(caption, str):
        raise ValueError("caption must be a string when provided.")
    normalized = caption.strip()
    if not normalized:
        return None
    if len(normalized) > config.MAX_CAPTION_LENGTH:
        raise ValueError(f"Caption exceeds max length of {config.MAX_CAPTION_LENGTH} characters.")
    return normalized


def validate_text_content(text_content: str) -> str:
    normalized = canonicalize_text_content(text_content)
    encoded = normalized.encode("utf-8")
    validate_content_size(len(encoded), mime_type=TEXT_MIME_TYPE)
    return normalized


def sanitize_original_filename(filename: str | None) -> str | None:
    if filename is None:
        return None
    if not isinstance(filename, str):
        raise ValueError("filename must be a string when provided.")
    candidate = os.path.basename(filename.strip())
    if not candidate or candidate in {".", ".."}:
        return None
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", candidate).strip("._")
    if not safe:
        safe = "upload"
    if len(safe) > config.MAX_FILENAME_LENGTH:
        safe = safe[: config.MAX_FILENAME_LENGTH].rstrip("._")
    if not safe:
        raise ValueError("Invalid filename metadata.")
    return safe


def detect_mime_type_from_bytes(data: bytes) -> str | None:
    payload = bytes(data)
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if payload.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if payload.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return "image/webp"
    if b"\x00" in payload:
        return None
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return TEXT_MIME_TYPE


def validate_detected_mime_matches_declared(data: bytes, declared_mime_type: str | None) -> str:
    declared = None
    if declared_mime_type is not None:
        declared = _validate_supported_mime_type(declared_mime_type)

    sniffed = detect_mime_type_from_bytes(data)
    if sniffed is not None and sniffed not in SUPPORTED_CONTENT_MIME_TYPES:
        raise ValueError(f"Unsupported detected mime_type: {sniffed!r}.")
    if declared and sniffed and declared != sniffed and config.ENABLE_STRICT_MIME_VALIDATION:
        raise ValueError(
            f"Declared mime_type {declared!r} does not match detected mime_type {sniffed!r}."
        )
    if sniffed:
        return sniffed
    if declared:
        return declared
    raise ValueError("Could not determine a supported mime_type for content bytes.")


def _resolve_mime_type(data: bytes, declared_mime_type: str | None) -> str:
    sniffed = validate_detected_mime_matches_declared(data, declared_mime_type)
    if sniffed:
        return sniffed
    raise ValueError("Could not determine a supported mime_type for content bytes.")


def resolve_payload_hash(
    data: bytes,
    mime_type: str | None,
) -> dict[str, Any]:
    payload = bytes(data)
    validate_content_size(len(payload), mime_type=mime_type if mime_type in SUPPORTED_TEXT_MIME_TYPES else None)
    resolved_mime_type = _resolve_mime_type(payload, mime_type)
    if resolved_mime_type == TEXT_MIME_TYPE:
        normalized_text = validate_text_content(payload.decode("utf-8"))
        normalized_bytes = normalized_text.encode("utf-8")
        return {
            "mime_type": resolved_mime_type,
            "content_hash": compute_content_hash_bytes(normalized_bytes),
            "hash_scheme": HASH_SCHEME_SHA256_TEXT,
            "text_content": normalized_text,
            "stored_bytes": normalized_bytes,
            "byte_hash": compute_content_hash_bytes(normalized_bytes),
        }
    return {
        "mime_type": resolved_mime_type,
        "content_hash": compute_content_hash_bytes(payload),
        "hash_scheme": HASH_SCHEME_SHA256_BYTES,
        "text_content": None,
        "stored_bytes": payload,
        "byte_hash": compute_content_hash_bytes(payload),
    }


def verify_content_hash_bytes(content_hash: str, data_bytes: bytes) -> dict[str, Any]:
    if not isinstance(content_hash, str) or not _HEX_64_PATTERN.fullmatch(content_hash.strip()):
        return {
            "verified": False,
            "hash_scheme": HASH_SCHEME_SHA256_BYTES,
            "error": "malformed_hash",
            "content_hash": content_hash,
            "actual_hash": None,
        }

    actual_hash = compute_content_hash_bytes(bytes(data_bytes))
    normalized_hash = content_hash.strip()
    return {
        "verified": actual_hash == normalized_hash,
        "hash_scheme": HASH_SCHEME_SHA256_BYTES,
        "error": None if actual_hash == normalized_hash else "hash_mismatch",
        "content_hash": normalized_hash,
        "actual_hash": actual_hash,
    }


def verify_content_hash_text(content_hash: str, text_content: str | None) -> dict[str, Any]:
    if not isinstance(content_hash, str) or not _HEX_64_PATTERN.fullmatch(content_hash.strip()):
        return {
            "verified": False,
            "hash_scheme": HASH_SCHEME_SHA256_TEXT,
            "error": "malformed_hash",
            "content_hash": content_hash,
            "actual_hash": None,
            "text_content": None,
        }
    if not isinstance(text_content, str) or not text_content.strip():
        return {
            "verified": False,
            "hash_scheme": HASH_SCHEME_SHA256_TEXT,
            "error": "missing_text",
            "content_hash": content_hash.strip(),
            "actual_hash": None,
            "text_content": None,
        }

    normalized_text = canonicalize_text_content(text_content)
    actual_hash = compute_content_hash_bytes(normalized_text.encode("utf-8"))
    normalized_hash = content_hash.strip()
    return {
        "verified": actual_hash == normalized_hash,
        "hash_scheme": HASH_SCHEME_SHA256_TEXT,
        "error": None if actual_hash == normalized_hash else "hash_mismatch",
        "content_hash": normalized_hash,
        "actual_hash": actual_hash,
        "text_content": normalized_text,
    }


def _content_relative_storage_path(content_hash: str, mime_type: str) -> Path:
    normalized_hash = _validate_content_hash_value(content_hash)
    normalized_mime_type = _validate_supported_mime_type(mime_type)
    suffix = CONTENT_MIME_EXTENSIONS[normalized_mime_type]
    return Path(normalized_hash[:2]) / normalized_hash[2:4] / f"{normalized_hash}{suffix}"


def _content_sidecar_path_for(file_path: Path) -> Path:
    return file_path.with_suffix(file_path.suffix + ".sha256")


def get_content_file_path(
    content_hash: str,
    mime_type: str | None = None,
    *,
    data_dir: str | None = None,
    content_storage_dir: str | None = None,
) -> str:
    if mime_type is None:
        located = _locate_content_file(
            content_hash,
            data_dir=data_dir,
            content_storage_dir=content_storage_dir,
        )
        if located is None:
            content_root = Path(ensure_content_storage_dir(data_dir=data_dir, content_storage_dir=content_storage_dir))
            return str(content_root / _content_relative_storage_path(content_hash, TEXT_MIME_TYPE))
        return str(located)

    content_root = Path(ensure_content_storage_dir(data_dir=data_dir, content_storage_dir=content_storage_dir))
    return str(content_root / _content_relative_storage_path(content_hash, mime_type))


def _locate_content_file(
    content_hash: str,
    *,
    data_dir: str | None = None,
    content_storage_dir: str | None = None,
) -> Path | None:
    normalized_hash = _validate_content_hash_value(content_hash)
    content_root = Path(ensure_content_storage_dir(data_dir=data_dir, content_storage_dir=content_storage_dir))
    relative_parent = Path(normalized_hash[:2]) / normalized_hash[2:4]
    for mime_type in SUPPORTED_CONTENT_MIME_TYPES:
        candidate = content_root / relative_parent / f"{normalized_hash}{CONTENT_MIME_EXTENSIONS[mime_type]}"
        if candidate.is_file():
            return candidate
    return None


def _path_relative_to(root: Path, path: Path) -> str | None:
    try:
        relative_path = path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    return str(relative_path)


def make_safe_local_path(
    path: str | os.PathLike[str] | None,
    *,
    data_dir: str | None = None,
    content_storage_dir: str | None = None,
) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        return str(candidate)

    content_root = _content_root_for(data_dir=data_dir, content_storage_dir=content_storage_dir)
    relative_to_content = _path_relative_to(content_root, candidate)
    if relative_to_content is not None:
        return str(Path("content") / relative_to_content)

    data_root = Path(data_dir) if data_dir else Path(config.DATA_DIR)
    relative_to_data = _path_relative_to(data_root, candidate)
    if relative_to_data is not None:
        return relative_to_data
    return None


def resolve_local_path(
    local_path: str | None,
    *,
    data_dir: str | None = None,
    content_storage_dir: str | None = None,
) -> str | None:
    if not isinstance(local_path, str) or not local_path.strip():
        return None
    candidate = Path(local_path.strip())
    if candidate.is_absolute():
        return str(candidate)

    content_root = _content_root_for(data_dir=data_dir, content_storage_dir=content_storage_dir)
    if candidate.parts and candidate.parts[0] == "content":
        return str((Path(data_dir) if data_dir else Path(config.DATA_DIR)) / candidate)
    return str((Path(data_dir) if data_dir else Path(config.DATA_DIR)) / candidate)


def content_file_exists(
    content_hash: str,
    mime_type: str | None = None,
    *,
    data_dir: str | None = None,
    content_storage_dir: str | None = None,
) -> bool:
    if mime_type is not None:
        return Path(
            get_content_file_path(
                content_hash,
                mime_type,
                data_dir=data_dir,
                content_storage_dir=content_storage_dir,
            )
        ).is_file()
    return _locate_content_file(
        content_hash,
        data_dir=data_dir,
        content_storage_dir=content_storage_dir,
    ) is not None


def load_content_bytes(
    content_hash: str,
    mime_type: str | None = None,
    *,
    data_dir: str | None = None,
    content_storage_dir: str | None = None,
) -> bytes:
    file_path = (
        Path(get_content_file_path(content_hash, mime_type, data_dir=data_dir, content_storage_dir=content_storage_dir))
        if mime_type is not None
        else _locate_content_file(content_hash, data_dir=data_dir, content_storage_dir=content_storage_dir)
    )
    if file_path is None or not file_path.is_file():
        raise FileNotFoundError(f"Content file not found for hash {content_hash}.")
    return file_path.read_bytes()


def verify_content_file(
    content_hash: str,
    mime_type: str | None = None,
    *,
    data_dir: str | None = None,
    content_storage_dir: str | None = None,
) -> dict[str, Any]:
    file_path = (
        Path(get_content_file_path(content_hash, mime_type, data_dir=data_dir, content_storage_dir=content_storage_dir))
        if mime_type is not None
        else _locate_content_file(content_hash, data_dir=data_dir, content_storage_dir=content_storage_dir)
    )
    if file_path is None or not file_path.is_file():
        return {
            "verified": False,
            "exists": False,
            "path": None,
            "local_path": None,
            "byte_hash": None,
            "file_size_bytes": None,
            "mime_type": mime_type,
            "error": "missing",
        }

    sidecar_path = _content_sidecar_path_for(file_path)
    if not sidecar_path.is_file():
        return {
            "verified": False,
            "exists": True,
            "path": str(file_path),
            "local_path": make_safe_local_path(file_path.resolve(), data_dir=data_dir, content_storage_dir=content_storage_dir),
            "byte_hash": None,
            "file_size_bytes": file_path.stat().st_size,
            "mime_type": mime_type or guess_mime_type(file_path.name, TEXT_MIME_TYPE),
            "error": "sidecar_missing",
        }

    expected_byte_hash = sidecar_path.read_text(encoding="utf-8").strip()
    actual_bytes = file_path.read_bytes()
    actual_byte_hash = compute_content_hash_bytes(actual_bytes)
    verified = bool(
        _HEX_64_PATTERN.fullmatch(expected_byte_hash)
        and actual_byte_hash == expected_byte_hash
    )
    return {
        "verified": verified,
        "exists": True,
        "path": str(file_path),
        "local_path": make_safe_local_path(file_path.resolve(), data_dir=data_dir, content_storage_dir=content_storage_dir),
        "byte_hash": actual_byte_hash,
        "file_size_bytes": len(actual_bytes),
        "mime_type": mime_type or guess_mime_type(file_path.name, TEXT_MIME_TYPE),
        "error": None if verified else "hash_mismatch",
    }


def verify_content_object_payload(
    content_object,
    *,
    data_dir: str | None = None,
    content_storage_dir: str | None = None,
) -> dict[str, Any]:
    content_hash = getattr(content_object, "content_hash", None)
    mime_type = getattr(content_object, "mime_type", None)
    content_type = getattr(content_object, "content_type", None)
    local_path = getattr(content_object, "local_path", None)
    text_content = getattr(content_object, "text_content", None)
    file_size_bytes = getattr(content_object, "file_size_bytes", None)
    declared_hash_scheme = _validate_hash_scheme(getattr(content_object, "hash_scheme", None))
    now = time.time()

    if not isinstance(content_hash, str) or not _HEX_64_PATTERN.fullmatch(content_hash.strip()):
        return {
            "verified": False,
            "hash_scheme": declared_hash_scheme,
            "error": "malformed_hash",
            "exists": False,
            "local_path": None,
            "byte_hash": None,
            "actual_hash": None,
            "file_size_bytes": None,
            "verified_at": None,
        }

    resolved_local_path = resolve_local_path(
        local_path,
        data_dir=data_dir,
        content_storage_dir=content_storage_dir,
    )
    file_exists = bool(resolved_local_path and os.path.isfile(resolved_local_path))
    is_text_payload = mime_type == TEXT_MIME_TYPE or content_type == CONTENT_TYPE_TEXT

    if is_text_payload and isinstance(text_content, str) and text_content.strip():
        text_result = verify_content_hash_text(content_hash, text_content)
        if text_result["verified"]:
            canonical_bytes = text_result["text_content"].encode("utf-8")
            mismatch = (
                file_size_bytes is not None
                and int(file_size_bytes) != len(canonical_bytes)
            )
            return {
                "verified": not mismatch,
                "hash_scheme": HASH_SCHEME_SHA256_TEXT,
                "error": None if not mismatch else "file_size_mismatch",
                "exists": True,
                "local_path": make_safe_local_path(
                    resolved_local_path,
                    data_dir=data_dir,
                    content_storage_dir=content_storage_dir,
                ) if file_exists else local_path,
                "byte_hash": compute_content_hash_bytes(canonical_bytes),
                "actual_hash": text_result["actual_hash"],
                "file_size_bytes": len(canonical_bytes),
                "verified_at": now if not mismatch else None,
            }
        if declared_hash_scheme in {HASH_SCHEME_UNKNOWN, HASH_SCHEME_LEGACY} and not file_exists:
            return {
                "verified": False,
                "hash_scheme": HASH_SCHEME_LEGACY,
                "error": "legacy_unverifiable",
                "exists": False,
                "local_path": None,
                "byte_hash": None,
                "actual_hash": text_result["actual_hash"],
                "file_size_bytes": None,
                "verified_at": None,
            }
        if declared_hash_scheme == HASH_SCHEME_SHA256_TEXT:
            return {
                "verified": False,
                "hash_scheme": HASH_SCHEME_SHA256_TEXT,
                "error": text_result["error"],
                "exists": True,
                "local_path": make_safe_local_path(
                    resolved_local_path,
                    data_dir=data_dir,
                    content_storage_dir=content_storage_dir,
                ) if file_exists else local_path,
                "byte_hash": None,
                "actual_hash": text_result["actual_hash"],
                "file_size_bytes": len(text_result["text_content"].encode("utf-8")) if text_result["text_content"] else None,
                "verified_at": None,
            }

    if is_text_payload and file_exists:
        payload_bytes = Path(resolved_local_path).read_bytes()
        try:
            decoded_text = payload_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return {
                "verified": False,
                "hash_scheme": declared_hash_scheme,
                "error": "unsupported_type",
                "exists": True,
                "local_path": make_safe_local_path(
                    resolved_local_path,
                    data_dir=data_dir,
                    content_storage_dir=content_storage_dir,
                ),
                "byte_hash": compute_content_hash_bytes(payload_bytes),
                "actual_hash": None,
                "file_size_bytes": len(payload_bytes),
                "verified_at": None,
            }
        text_result = verify_content_hash_text(content_hash, decoded_text)
        if text_result["verified"]:
            mismatch = file_size_bytes is not None and int(file_size_bytes) != len(payload_bytes)
            return {
                "verified": not mismatch,
                "hash_scheme": HASH_SCHEME_SHA256_TEXT,
                "error": None if not mismatch else "file_size_mismatch",
                "exists": True,
                "local_path": make_safe_local_path(
                    resolved_local_path,
                    data_dir=data_dir,
                    content_storage_dir=content_storage_dir,
                ),
                "byte_hash": compute_content_hash_bytes(payload_bytes),
                "actual_hash": text_result["actual_hash"],
                "file_size_bytes": len(payload_bytes),
                "verified_at": now if not mismatch else None,
            }
        return {
            "verified": False,
            "hash_scheme": HASH_SCHEME_LEGACY if declared_hash_scheme in {HASH_SCHEME_UNKNOWN, HASH_SCHEME_LEGACY} else HASH_SCHEME_SHA256_TEXT,
            "error": "legacy_unverifiable" if declared_hash_scheme in {HASH_SCHEME_UNKNOWN, HASH_SCHEME_LEGACY} else text_result["error"],
            "exists": True,
            "local_path": make_safe_local_path(
                resolved_local_path,
                data_dir=data_dir,
                content_storage_dir=content_storage_dir,
            ),
            "byte_hash": compute_content_hash_bytes(payload_bytes),
            "actual_hash": text_result["actual_hash"],
            "file_size_bytes": len(payload_bytes),
            "verified_at": None,
        }

    if is_text_payload:
        return {
            "verified": False,
            "hash_scheme": declared_hash_scheme,
            "error": "missing_text" if not file_exists else "hash_mismatch",
            "exists": file_exists,
            "local_path": make_safe_local_path(
                resolved_local_path,
                data_dir=data_dir,
                content_storage_dir=content_storage_dir,
            ) if file_exists else None,
            "byte_hash": None,
            "actual_hash": None,
            "file_size_bytes": None,
            "verified_at": None,
        }

    if not file_exists:
        return {
            "verified": False,
            "hash_scheme": declared_hash_scheme,
            "error": "missing_file",
            "exists": False,
            "local_path": None,
            "byte_hash": None,
            "actual_hash": None,
            "file_size_bytes": None,
            "verified_at": None,
        }

    payload_bytes = Path(resolved_local_path).read_bytes()
    bytes_result = verify_content_hash_bytes(content_hash, payload_bytes)
    if bytes_result["verified"]:
        mismatch = file_size_bytes is not None and int(file_size_bytes) != len(payload_bytes)
        return {
            "verified": not mismatch,
            "hash_scheme": HASH_SCHEME_SHA256_BYTES,
            "error": None if not mismatch else "file_size_mismatch",
            "exists": True,
            "local_path": make_safe_local_path(
                resolved_local_path,
                data_dir=data_dir,
                content_storage_dir=content_storage_dir,
            ),
            "byte_hash": bytes_result["actual_hash"],
            "actual_hash": bytes_result["actual_hash"],
            "file_size_bytes": len(payload_bytes),
            "verified_at": now if not mismatch else None,
        }

    return {
        "verified": False,
        "hash_scheme": HASH_SCHEME_LEGACY if declared_hash_scheme in {HASH_SCHEME_UNKNOWN, HASH_SCHEME_LEGACY} else HASH_SCHEME_SHA256_BYTES,
        "error": "legacy_unverifiable" if declared_hash_scheme in {HASH_SCHEME_UNKNOWN, HASH_SCHEME_LEGACY} else bytes_result["error"],
        "exists": True,
        "local_path": make_safe_local_path(
            resolved_local_path,
            data_dir=data_dir,
            content_storage_dir=content_storage_dir,
        ),
        "byte_hash": compute_content_hash_bytes(payload_bytes),
        "actual_hash": bytes_result["actual_hash"],
        "file_size_bytes": len(payload_bytes),
        "verified_at": None,
    }


def store_content_bytes(
    content_hash: str,
    data: bytes,
    mime_type: str,
    original_filename: str | None = None,
    *,
    data_dir: str | None = None,
    content_storage_dir: str | None = None,
    max_size_bytes: int | None = None,
    hash_scheme: str | None = None,
) -> dict[str, Any]:
    normalized_hash = _validate_content_hash_value(content_hash)
    payload = bytes(data)
    if max_size_bytes is None:
        max_size_bytes = config.MAX_CONTENT_FILE_SIZE_BYTES
    validate_content_size(len(payload), mime_type=mime_type if mime_type in SUPPORTED_TEXT_MIME_TYPES else None)
    if len(payload) > max_size_bytes:
        raise ValueError(
            f"Content file exceeds MAX_CONTENT_FILE_SIZE_BYTES ({max_size_bytes} bytes)."
        )

    resolved_payload = resolve_payload_hash(payload, mime_type)
    resolved_mime_type = resolved_payload["mime_type"]
    normalized_scheme = _validate_hash_scheme(hash_scheme) if hash_scheme not in (None, "") else resolved_payload["hash_scheme"]
    if normalized_scheme not in {
        HASH_SCHEME_SHA256_BYTES,
        HASH_SCHEME_SHA256_TEXT,
        HASH_SCHEME_LEGACY,
        HASH_SCHEME_UNKNOWN,
    }:
        raise ValueError("hash_scheme for stored local content is invalid.")
    strict_hash_match = normalized_scheme in {HASH_SCHEME_SHA256_BYTES, HASH_SCHEME_SHA256_TEXT}
    if strict_hash_match and resolved_payload["content_hash"] != normalized_hash:
        raise ValueError(f"Provided content_hash does not match the {normalized_scheme} payload hash.")
    payload = resolved_payload["stored_bytes"]
    byte_hash = resolved_payload["byte_hash"]
    target_path = Path(
        get_content_file_path(
            normalized_hash,
            resolved_mime_type,
            data_dir=data_dir,
            content_storage_dir=content_storage_dir,
        )
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_path = _content_sidecar_path_for(target_path)
    existing_path = _locate_content_file(
        normalized_hash,
        data_dir=data_dir,
        content_storage_dir=content_storage_dir,
    )

    if existing_path is not None:
        verification = verify_content_file(
            normalized_hash,
            guess_mime_type(existing_path.name, resolved_mime_type),
            data_dir=data_dir,
            content_storage_dir=content_storage_dir,
        )
        if verification["verified"] and verification["byte_hash"] == byte_hash:
            return {
                "content_hash": normalized_hash,
                "mime_type": guess_mime_type(existing_path.name, resolved_mime_type),
                "path": str(existing_path),
                "local_path": verification["local_path"],
                "file_size_bytes": verification["file_size_bytes"],
                "storage_status": STORAGE_STATUS_VERIFIED if strict_hash_match else STORAGE_STATUS_LOCAL,
                "byte_hash": byte_hash,
                "file_name": existing_path.name,
                "original_filename": sanitize_original_filename(original_filename),
                "hash_scheme": normalized_scheme,
            }
        raise ValueError(
            f"Existing content file for {normalized_hash} does not match the bytes being stored."
        )

    fd, temp_path = tempfile.mkstemp(prefix=f"{normalized_hash}.", suffix=".tmp", dir=str(target_path.parent))
    sidecar_fd = None
    sidecar_temp_path = None
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        stored_bytes = Path(temp_path).read_bytes()
        if compute_content_hash_bytes(stored_bytes) != byte_hash:
            raise ValueError("Temporary content file hash verification failed before commit.")

        sidecar_fd, sidecar_temp_path = tempfile.mkstemp(
            prefix=f"{normalized_hash}.",
            suffix=".sha256.tmp",
            dir=str(target_path.parent),
        )
        with os.fdopen(sidecar_fd, "w", encoding="utf-8") as handle:
            handle.write(byte_hash)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        sidecar_fd = None

        os.replace(temp_path, target_path)
        os.replace(sidecar_temp_path, sidecar_path)
        verification = verify_content_file(
            normalized_hash,
            resolved_mime_type,
            data_dir=data_dir,
            content_storage_dir=content_storage_dir,
        )
        if not verification["verified"]:
            raise ValueError(
                f"Stored content verification failed for {normalized_hash}: {verification['error']}."
            )
        return {
            "content_hash": normalized_hash,
            "mime_type": resolved_mime_type,
            "path": str(target_path),
            "local_path": verification["local_path"],
            "file_size_bytes": verification["file_size_bytes"],
            "storage_status": STORAGE_STATUS_VERIFIED if strict_hash_match else STORAGE_STATUS_LOCAL,
            "byte_hash": byte_hash,
            "file_name": target_path.name,
            "original_filename": sanitize_original_filename(original_filename),
            "hash_scheme": normalized_scheme,
        }
    finally:
        for leftover in (temp_path, sidecar_temp_path):
            if leftover and os.path.exists(leftover):
                try:
                    os.remove(leftover)
                except OSError:
                    pass


@dataclass
class ContentObject:
    content_hash: str
    content_type: str
    mime_type: str
    submitted_by: str
    network_name: str
    created_at: float = field(default_factory=time.time)
    file_name: str | None = None
    file_size_bytes: int | None = None
    storage_status: str = STORAGE_STATUS_MISSING
    local_path: str | None = None
    text_content: str | None = None
    caption: str | None = None
    metadata: dict[str, Any] | None = None
    hash_scheme: str = HASH_SCHEME_UNKNOWN
    verified_at: float | None = None
    verification_error: str | None = None
    content_id: str = ""

    def __post_init__(self):
        self.content_type = _validate_content_type(self.content_type)
        self.storage_status = _validate_storage_status(self.storage_status)
        self.content_hash = _validate_non_empty_string(self.content_hash, "content_hash")
        if not _HEX_64_PATTERN.fullmatch(self.content_hash):
            raise ValueError("content_hash must be a 64-character lowercase hexadecimal string.")

        self.mime_type = _validate_non_empty_string(self.mime_type, "mime_type")
        self.submitted_by = _validate_non_empty_string(self.submitted_by, "submitted_by")
        self.network_name = _validate_non_empty_string(self.network_name, "network_name")
        self.created_at = float(self.created_at)

        if self.file_name is not None:
            self.file_name = sanitize_original_filename(self.file_name)
            if self.file_name is None:
                raise ValueError("Invalid filename metadata.")
        self.file_size_bytes = _validate_optional_file_size(self.file_size_bytes)

        if self.local_path is not None:
            self.local_path = _validate_non_empty_string(self.local_path, "local_path")
        if self.text_content is not None:
            self.text_content = validate_text_content(self.text_content)
        if self.caption is not None:
            self.caption = validate_caption(self.caption)
        self.metadata = dict(self.metadata or {})
        self.hash_scheme = _validate_hash_scheme(self.hash_scheme)
        self.verified_at = _coerce_optional_float(self.verified_at, "verified_at")
        self.verification_error = _clean_optional_string(self.verification_error)

        expected_content_id = calculate_content_id(self.content_hash)
        if not self.content_id:
            self.content_id = expected_content_id
        elif self.content_id != expected_content_id:
            raise ValueError("content_id does not match content_hash.")

        if self.content_type == CONTENT_TYPE_TEXT and not (self.text_content or self.caption):
            raise ValueError("Text content objects must include text_content or caption.")

    @classmethod
    def from_text(
        cls,
        *,
        text_content: str,
        submitted_by: str,
        network_name: str,
        mime_type: str = TEXT_MIME_TYPE,
        caption: str | None = None,
        metadata: dict[str, Any] | None = None,
        created_at: float | None = None,
        storage_status: str = STORAGE_STATUS_MISSING,
    ) -> "ContentObject":
        normalized_text = canonicalize_text_content(text_content)
        return cls(
            content_hash=compute_text_content_hash(normalized_text),
            content_type=CONTENT_TYPE_TEXT,
            mime_type=TEXT_MIME_TYPE,
            submitted_by=submitted_by,
            network_name=network_name,
            created_at=time.time() if created_at is None else created_at,
            text_content=normalized_text,
            caption=caption,
            metadata=metadata,
            storage_status=storage_status,
            hash_scheme=HASH_SCHEME_SHA256_TEXT,
        )

    @classmethod
    def from_image_metadata(
        cls,
        *,
        submitted_by: str,
        network_name: str,
        mime_type: str,
        file_name: str | None = None,
        file_size_bytes: int | None = None,
        text_content: str | None = None,
        caption: str | None = None,
        metadata: dict[str, Any] | None = None,
        created_at: float | None = None,
        storage_status: str = STORAGE_STATUS_MISSING,
        local_path: str | None = None,
    ) -> "ContentObject":
        content_hash = calculate_content_hash(
            content_type=CONTENT_TYPE_IMAGE,
            mime_type=mime_type,
            text_content=text_content,
            caption=caption,
            file_name=file_name,
            file_size_bytes=file_size_bytes,
            metadata=metadata,
        )
        return cls(
            content_hash=content_hash,
            content_type=CONTENT_TYPE_IMAGE,
            mime_type=mime_type,
            submitted_by=submitted_by,
            network_name=network_name,
            created_at=time.time() if created_at is None else created_at,
            file_name=file_name,
            file_size_bytes=file_size_bytes,
            storage_status=storage_status,
            local_path=local_path,
            text_content=text_content,
            caption=caption,
            metadata=metadata,
            hash_scheme=HASH_SCHEME_LEGACY,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContentObject":
        if not isinstance(data, dict):
            raise ValueError("ContentObject data must be a dictionary.")
        return cls(
            content_id=data.get("content_id", ""),
            content_hash=data["content_hash"],
            content_type=data["content_type"],
            mime_type=data["mime_type"],
            file_name=data.get("file_name"),
            file_size_bytes=data.get("file_size_bytes"),
            storage_status=data.get("storage_status", STORAGE_STATUS_MISSING),
            local_path=data.get("local_path"),
            text_content=data.get("text_content"),
            caption=data.get("caption"),
            submitted_by=data.get("submitted_by", ""),
            created_at=data.get("created_at", time.time()),
            network_name=data.get("network_name", ""),
            metadata=data.get("metadata"),
            hash_scheme=data.get("hash_scheme"),
            verified_at=data.get("verified_at"),
            verification_error=data.get("verification_error"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_id": self.content_id,
            "content_hash": self.content_hash,
            "content_type": self.content_type,
            "mime_type": self.mime_type,
            "file_name": self.file_name,
            "file_size_bytes": self.file_size_bytes,
            "storage_status": self.storage_status,
            "local_path": self.local_path,
            "text_content": self.text_content,
            "caption": self.caption,
            "submitted_by": self.submitted_by,
            "created_at": self.created_at,
            "network_name": self.network_name,
            "metadata": self.metadata,
            "hash_scheme": self.hash_scheme,
            "verified_at": self.verified_at,
            "verification_error": self.verification_error,
        }


def content_object_from_submission_data(
    submission_data: dict[str, Any],
    *,
    network_name: str,
    storage_status: str | None = None,
    data_dir: str | None = None,
) -> ContentObject:
    if not isinstance(submission_data, dict):
        raise ValueError("Submission data must be a dictionary.")

    image_path = submission_data.get("image_path") or submission_data.get("image") or ""
    text_content = submission_data.get("text_content") or submission_data.get("text") or ""
    submitter = submission_data.get("submitter") or submission_data.get("miner") or ""
    content_hash = submission_data.get("content_hash")
    if not isinstance(content_hash, str) or not content_hash.strip():
        from submission import calculate_submission_content_hash

        content_hash = calculate_submission_content_hash(image_path, text_content, submitter)

    normalized_image_path = image_path
    resolved_image_path = None
    if image_path:
        resolved_image_path = resolve_local_path(image_path, data_dir=data_dir)
        if resolved_image_path and os.path.isfile(resolved_image_path):
            normalized_image_path = resolved_image_path

    file_name = os.path.basename(normalized_image_path) if normalized_image_path else None
    content_type = infer_content_type(image_path, text_content)

    raw_bytes = None
    if normalized_image_path and os.path.isfile(normalized_image_path):
        raw_bytes = Path(normalized_image_path).read_bytes()
        detected_mime_type = detect_mime_type_from_bytes(raw_bytes)
    else:
        detected_mime_type = None

    mime_type = (
        detected_mime_type
        or guess_mime_type(file_name)
        or (TEXT_MIME_TYPE if content_type == CONTENT_TYPE_TEXT else "application/octet-stream")
    )

    local_path = make_safe_local_path(normalized_image_path or image_path or None, data_dir=data_dir)
    created_at = submission_data.get("created_at")
    try:
        created_at_value = float(created_at)
    except (TypeError, ValueError):
        created_at_value = time.time()

    file_size_bytes = len(raw_bytes) if raw_bytes is not None else None

    metadata = {
        "submission_id": submission_data.get("submission_id"),
    }
    if raw_bytes is not None:
        metadata["byte_hash"] = compute_content_hash_bytes(raw_bytes)
    original_filename = submission_data.get("original_filename") or submission_data.get("file_name")
    if not original_filename and file_name and raw_bytes is not None:
        original_filename = _recover_legacy_original_filename(
            content_hash=content_hash.strip(),
            file_name=file_name,
            file_size_bytes=len(raw_bytes),
            byte_hash=metadata.get("byte_hash"),
            data_dir=data_dir,
            managed_file_path=normalized_image_path,
        )
    if not original_filename and file_name:
        original_filename = file_name
    if original_filename:
        metadata["original_filename"] = sanitize_original_filename(original_filename)
    hash_scheme = submission_data.get("hash_scheme")
    if raw_bytes is not None:
        payload_hash = resolve_payload_hash(raw_bytes, mime_type)
        if payload_hash["content_hash"] == content_hash.strip():
            hash_scheme = payload_hash["hash_scheme"]
    elif text_content:
        text_hash = verify_content_hash_text(content_hash.strip(), text_content)
        if text_hash["verified"]:
            hash_scheme = HASH_SCHEME_SHA256_TEXT

    content_object = ContentObject(
        content_hash=content_hash.strip(),
        content_type=content_type,
        mime_type=mime_type,
        file_name=sanitize_original_filename(file_name),
        file_size_bytes=file_size_bytes,
        storage_status=storage_status or (STORAGE_STATUS_LOCAL if raw_bytes is not None else STORAGE_STATUS_MISSING),
        local_path=local_path,
        text_content=(text_content or None),
        caption=(text_content or None),
        submitted_by=submitter,
        network_name=network_name,
        created_at=created_at_value,
        metadata=metadata,
        hash_scheme=hash_scheme,
        verified_at=submission_data.get("verified_at"),
        verification_error=submission_data.get("verification_error"),
    )
    payload_verification = verify_content_object_payload(content_object, data_dir=data_dir)
    content_object.hash_scheme = payload_verification["hash_scheme"]
    content_object.verification_error = payload_verification["error"]
    content_object.verified_at = payload_verification["verified_at"]
    if payload_verification["file_size_bytes"] is not None:
        content_object.file_size_bytes = payload_verification["file_size_bytes"]
    if payload_verification["local_path"] is not None:
        content_object.local_path = payload_verification["local_path"]
    if storage_status is None:
        if payload_verification["verified"]:
            content_object.storage_status = STORAGE_STATUS_VERIFIED
        elif payload_verification["error"] == "missing_file":
            content_object.storage_status = STORAGE_STATUS_MISSING
        elif raw_bytes is not None or local_path:
            content_object.storage_status = STORAGE_STATUS_LOCAL
        else:
            content_object.storage_status = STORAGE_STATUS_MISSING
    return content_object
