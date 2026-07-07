from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any


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

_HEX_32_PATTERN = re.compile(r"^[a-f0-9]{32}$")
_HEX_64_PATTERN = re.compile(r"^[a-f0-9]{64}$")


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
            self.file_name = _validate_non_empty_string(self.file_name, "file_name")
        self.file_size_bytes = _validate_optional_file_size(self.file_size_bytes)

        if self.local_path is not None:
            self.local_path = _validate_non_empty_string(self.local_path, "local_path")
        if self.text_content is not None:
            self.text_content = self.text_content.strip()
        if self.caption is not None:
            self.caption = self.caption.strip()
        self.metadata = dict(self.metadata or {})

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
        mime_type: str = "text/plain",
        caption: str | None = None,
        metadata: dict[str, Any] | None = None,
        created_at: float | None = None,
        storage_status: str = STORAGE_STATUS_MISSING,
    ) -> "ContentObject":
        content_hash = calculate_content_hash(
            content_type=CONTENT_TYPE_TEXT,
            mime_type=mime_type,
            text_content=text_content,
            caption=caption,
            metadata=metadata,
        )
        return cls(
            content_hash=content_hash,
            content_type=CONTENT_TYPE_TEXT,
            mime_type=mime_type,
            submitted_by=submitted_by,
            network_name=network_name,
            created_at=time.time() if created_at is None else created_at,
            text_content=text_content,
            caption=caption,
            metadata=metadata,
            storage_status=storage_status,
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
        }
