from __future__ import annotations

import hashlib
import hmac
import math
import re
import secrets
import threading
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Pattern

from protocol_v1 import (
    OBJECT_TYPE_PEER_MESSAGE,
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    canonical_json_bytes,
    canonical_json_data,
    decode_canonical_bytes,
    encode_canonical_bytes,
    is_canonical_bytes_object,
    normalize_network_id,
    protocol_domain,
    resolve_network_id,
)
from storage import (
    StorageCorruptionError,
    _atomic_write_json_document,
    _backup_path_for,
    _load_json_document_with_backup,
)
from validators import is_valid_content_hash, is_valid_node_id


PROTOCOL_V1_PEER_MESSAGE_VERSION = PROTOCOL_VERSION
PROTOCOL_V1_PEER_MESSAGE_DOMAIN = protocol_domain(OBJECT_TYPE_PEER_MESSAGE)
PROTOCOL_V1_PEER_AUTH_ALGORITHM = "hmac-sha256"
PROTOCOL_V1_PEER_REPLAY_STATE_VERSION = 1
PROTOCOL_V1_PEER_REPLAY_STATE_FILE = "peer_message_replay_state.json"
PROTOCOL_V1_PEER_MESSAGE_ID_PATTERN = re.compile(r"^[0-9a-f]{64}$")
PROTOCOL_V1_PEER_NONCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

PEER_MESSAGE_TYPE_PEER_REGISTRATION = "peer-registration"
PEER_MESSAGE_TYPE_SUBMISSION = "submission"
PEER_MESSAGE_TYPE_VOTE = "vote"
PEER_MESSAGE_TYPE_CERTIFICATE = "certificate"
PEER_MESSAGE_TYPE_BLOCK = "block"
PEER_MESSAGE_TYPE_NATIVE_TRANSACTION = "native-transaction"
PEER_MESSAGE_TYPE_TRANSACTION_FETCH = "transaction-fetch"
PEER_MESSAGE_TYPE_MEMPOOL_SUMMARY = "mempool-summary"
PEER_MESSAGE_TYPE_CONTENT_METADATA = "content-metadata"
PEER_MESSAGE_TYPE_CONTENT_DOWNLOAD = "content-download"
PEER_MESSAGE_TYPE_CHAIN_SUMMARY = "chain-summary"
PEER_MESSAGE_TYPE_CHAIN_BLOCKS = "chain-blocks"

PROTOCOL_V1_PEER_MESSAGE_TYPES = {
    PEER_MESSAGE_TYPE_PEER_REGISTRATION,
    PEER_MESSAGE_TYPE_SUBMISSION,
    PEER_MESSAGE_TYPE_VOTE,
    PEER_MESSAGE_TYPE_CERTIFICATE,
    PEER_MESSAGE_TYPE_BLOCK,
    PEER_MESSAGE_TYPE_NATIVE_TRANSACTION,
    PEER_MESSAGE_TYPE_TRANSACTION_FETCH,
    PEER_MESSAGE_TYPE_MEMPOOL_SUMMARY,
    PEER_MESSAGE_TYPE_CONTENT_METADATA,
    PEER_MESSAGE_TYPE_CONTENT_DOWNLOAD,
    PEER_MESSAGE_TYPE_CHAIN_SUMMARY,
    PEER_MESSAGE_TYPE_CHAIN_BLOCKS,
}

HEADER_PEER_MESSAGE_VERSION = "X-ZOID-Peer-Message-Version"
HEADER_PROTOCOL_VERSION = "X-ZOID-Protocol-Version"
HEADER_NETWORK_ID = "X-ZOID-Network-Id"
HEADER_MESSAGE_TYPE = "X-ZOID-Message-Type"
HEADER_NODE_ID = "X-ZOID-Node-Id"
HEADER_TIMESTAMP = "X-ZOID-Timestamp"
HEADER_NONCE = "X-ZOID-Nonce"
HEADER_MESSAGE_ID = "X-ZOID-Message-Id"
HEADER_SIGNATURE = "X-ZOID-Signature"

PROTOCOL_V1_REQUIRED_PEER_HEADERS = (
    HEADER_PEER_MESSAGE_VERSION,
    HEADER_PROTOCOL_VERSION,
    HEADER_NETWORK_ID,
    HEADER_MESSAGE_TYPE,
    HEADER_NODE_ID,
    HEADER_TIMESTAMP,
    HEADER_NONCE,
    HEADER_MESSAGE_ID,
    HEADER_SIGNATURE,
)


@dataclass(frozen=True)
class ProtocolV1PeerAuthContext:
    peer_message_version: int
    protocol_version: int
    network_id: str
    message_type: str
    sender_node_id: str
    timestamp: int
    nonce: str
    message_id: str
    signature: str
    envelope: dict[str, Any]
    payload: Any


@dataclass(frozen=True)
class _PeerRouteBinding:
    method: str
    path_pattern: Pattern[str]
    message_type: str


_PEER_ROUTE_BINDINGS = (
    _PeerRouteBinding("POST", re.compile(r"^/peers/register$"), PEER_MESSAGE_TYPE_PEER_REGISTRATION),
    _PeerRouteBinding("POST", re.compile(r"^/peers/submissions/receive$"), PEER_MESSAGE_TYPE_SUBMISSION),
    _PeerRouteBinding("POST", re.compile(r"^/peers/votes/receive$"), PEER_MESSAGE_TYPE_VOTE),
    _PeerRouteBinding("POST", re.compile(r"^/peers/certificates/receive$"), PEER_MESSAGE_TYPE_CERTIFICATE),
    _PeerRouteBinding("POST", re.compile(r"^/peers/blocks/receive$"), PEER_MESSAGE_TYPE_BLOCK),
    _PeerRouteBinding("POST", re.compile(r"^/peers/transactions/receive$"), PEER_MESSAGE_TYPE_NATIVE_TRANSACTION),
    _PeerRouteBinding("GET", re.compile(r"^/peers/transactions/(?P<tx_id>[0-9a-f]{64})$"), PEER_MESSAGE_TYPE_TRANSACTION_FETCH),
    _PeerRouteBinding("GET", re.compile(r"^/peers/mempool/summary$"), PEER_MESSAGE_TYPE_MEMPOOL_SUMMARY),
    _PeerRouteBinding("GET", re.compile(r"^/peers/content/(?P<content_hash>[0-9a-f]{64})/metadata$"), PEER_MESSAGE_TYPE_CONTENT_METADATA),
    _PeerRouteBinding("GET", re.compile(r"^/peers/content/(?P<content_hash>[0-9a-f]{64})$"), PEER_MESSAGE_TYPE_CONTENT_DOWNLOAD),
    _PeerRouteBinding("GET", re.compile(r"^/peers/chain/summary$"), PEER_MESSAGE_TYPE_CHAIN_SUMMARY),
    _PeerRouteBinding("GET", re.compile(r"^/peers/chain/blocks$"), PEER_MESSAGE_TYPE_CHAIN_BLOCKS),
)

_REPLAY_STORE_CACHE_LOCK = threading.Lock()
_REPLAY_STORE_CACHE: dict[str, "ProtocolV1PeerReplayStore"] = {}


class ProtocolV1PeerMessageError(ValueError):
    pass


class MissingProtocolV1PeerHeadersError(ProtocolV1PeerMessageError):
    pass


class UnsupportedPeerMessageVersionError(ProtocolV1PeerMessageError):
    pass


class UnsupportedPeerProtocolVersionError(ProtocolV1PeerMessageError):
    pass


class InvalidPeerMessageTypeError(ProtocolV1PeerMessageError):
    pass


class InvalidPeerSenderError(ProtocolV1PeerMessageError):
    pass


class InvalidPeerTimestampError(ProtocolV1PeerMessageError):
    pass


class ExpiredPeerMessageError(ProtocolV1PeerMessageError):
    pass


class InvalidPeerNonceError(ProtocolV1PeerMessageError):
    pass


class InvalidPeerMessageIdError(ProtocolV1PeerMessageError):
    pass


class InvalidPeerSignatureError(ProtocolV1PeerMessageError):
    pass


class WrongPeerNetworkError(ProtocolV1PeerMessageError):
    pass


class ReplayStateUnavailableError(ProtocolV1PeerMessageError):
    pass


class ReplayedPeerMessageError(ProtocolV1PeerMessageError):
    pass


def normalize_protocol_v1_peer_message_type(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidPeerMessageTypeError("Peer message type is required.")
    normalized = value.strip().lower()
    if normalized not in PROTOCOL_V1_PEER_MESSAGE_TYPES:
        raise InvalidPeerMessageTypeError(f"Unsupported peer message type: {value!r}.")
    return normalized


def normalize_protocol_v1_peer_sender_node_id(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or not is_valid_node_id(value.strip()):
        raise InvalidPeerSenderError("Peer sender node_id is invalid.")
    return value.strip()


def normalize_protocol_v1_peer_timestamp(value: Any) -> int:
    if isinstance(value, bool):
        raise InvalidPeerTimestampError("Peer timestamp must be an integer Unix second.")
    try:
        normalized = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise InvalidPeerTimestampError("Invalid peer timestamp.") from exc
    if normalized < 0:
        raise InvalidPeerTimestampError("Peer timestamp must be non-negative.")
    return normalized


def normalize_protocol_v1_peer_nonce(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidPeerNonceError("Peer nonce is required.")
    normalized = value.strip()
    if not PROTOCOL_V1_PEER_NONCE_PATTERN.fullmatch(normalized):
        raise InvalidPeerNonceError("Peer nonce must use only letters, digits, '.', '_', ':', or '-'.")
    return normalized


def normalize_protocol_v1_peer_message_id(value: Any) -> str:
    if not isinstance(value, str) or not PROTOCOL_V1_PEER_MESSAGE_ID_PATTERN.fullmatch(value.strip()):
        raise InvalidPeerMessageIdError("Peer message_id must be a 64-character lowercase hexadecimal string.")
    return value.strip()


def normalize_protocol_v1_peer_message_version(value: Any) -> int:
    if isinstance(value, bool):
        raise UnsupportedPeerMessageVersionError("Protocol v1 peer message version is invalid.")
    try:
        normalized = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise UnsupportedPeerMessageVersionError("Protocol v1 peer message version is invalid.") from exc
    if normalized != PROTOCOL_V1_PEER_MESSAGE_VERSION:
        raise UnsupportedPeerMessageVersionError(
            f"Unsupported peer message version: {normalized}."
        )
    return normalized


def normalize_protocol_v1_protocol_version(value: Any) -> int:
    if isinstance(value, bool):
        raise UnsupportedPeerProtocolVersionError("Unsupported peer protocol version.")
    try:
        normalized = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise UnsupportedPeerProtocolVersionError("Unsupported peer protocol version.") from exc
    if normalized != PROTOCOL_VERSION:
        raise UnsupportedPeerProtocolVersionError(f"Unsupported peer protocol version: {normalized}.")
    return normalized


def resolve_protocol_v1_peer_network_id(*, network_id: str | None = None, network_name: str | None = None) -> str:
    if network_id is not None:
        return normalize_network_id(network_id)
    return resolve_network_id(network_name=network_name)


def _normalize_bool_query_value(value: Any, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if normalized in {"", "0", "false", "no", "off"}:
        return False
    if normalized in {"1", "true", "yes", "on"}:
        return True
    raise ProtocolV1PeerMessageError(f"{field_name} must be a boolean value.")


def _normalize_non_negative_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise ProtocolV1PeerMessageError(f"{field_name} must be a non-negative integer.")
    try:
        normalized = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ProtocolV1PeerMessageError(f"{field_name} must be a non-negative integer.") from exc
    if normalized < 0:
        raise ProtocolV1PeerMessageError(f"{field_name} must be a non-negative integer.")
    return normalized


def _normalize_decimal_string(value: float) -> str:
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ProtocolV1PeerMessageError("Peer payload contains an invalid float value.") from exc
    if not decimal_value.is_finite():
        raise ProtocolV1PeerMessageError("Peer payload does not support NaN or Infinity.")
    normalized = format(decimal_value, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    if normalized in {"", "-0"}:
        normalized = "0"
    return normalized


def normalize_protocol_v1_peer_payload(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (bool, int, str, bytes, bytearray, memoryview)):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ProtocolV1PeerMessageError("Peer payload does not support NaN or Infinity.")
        return _normalize_decimal_string(value)
    if isinstance(value, list):
        return [normalize_protocol_v1_peer_payload(item) for item in value]
    if isinstance(value, dict):
        if is_canonical_bytes_object(value):
            return encode_canonical_bytes(decode_canonical_bytes(value))
        normalized_items: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise ProtocolV1PeerMessageError("Protocol v1 peer payload requires string dictionary keys.")
            normalized_items[key] = normalize_protocol_v1_peer_payload(child)
        return normalized_items
    raise ProtocolV1PeerMessageError(
        f"Protocol v1 peer payload does not support values of type {type(value).__name__}."
    )


def _route_binding_for_request(method: Any, path: Any) -> tuple[_PeerRouteBinding, re.Match[str]]:
    normalized_method = str(method or "").strip().upper()
    normalized_path = str(path or "").strip()
    for binding in _PEER_ROUTE_BINDINGS:
        if binding.method != normalized_method:
            continue
        match = binding.path_pattern.fullmatch(normalized_path)
        if match:
            return binding, match
    raise InvalidPeerMessageTypeError(
        f"Unsupported Protocol v1 peer route: {normalized_method} {normalized_path}"
    )


def infer_protocol_v1_peer_message_type(method: Any, path: Any) -> str:
    binding, _match = _route_binding_for_request(method, path)
    return binding.message_type


def build_protocol_v1_peer_request_payload(
    method: Any,
    path: Any,
    *,
    body_payload: dict[str, Any] | None = None,
    query_params: Mapping[str, Any] | None = None,
) -> Any:
    binding, match = _route_binding_for_request(method, path)
    message_type = binding.message_type

    if binding.method == "POST":
        if not isinstance(body_payload, dict):
            raise ProtocolV1PeerMessageError("Protocol v1 peer request payload must be a JSON object.")
        return canonical_json_data(normalize_protocol_v1_peer_payload(body_payload))

    if message_type in {PEER_MESSAGE_TYPE_CONTENT_METADATA, PEER_MESSAGE_TYPE_CONTENT_DOWNLOAD}:
        content_hash = match.group("content_hash")
        if not is_valid_content_hash(content_hash):
            raise ProtocolV1PeerMessageError("content_hash must be a 64-character lowercase hexadecimal string.")
        return {"content_hash": content_hash}

    if message_type == PEER_MESSAGE_TYPE_TRANSACTION_FETCH:
        tx_id = match.group("tx_id")
        if not PROTOCOL_V1_PEER_MESSAGE_ID_PATTERN.fullmatch(tx_id):
            raise ProtocolV1PeerMessageError("tx_id must be a 64-character lowercase hexadecimal string.")
        return {"tx_id": tx_id}

    if message_type in {PEER_MESSAGE_TYPE_MEMPOOL_SUMMARY, PEER_MESSAGE_TYPE_CHAIN_SUMMARY}:
        return {}

    if message_type == PEER_MESSAGE_TYPE_CHAIN_BLOCKS:
        params = query_params or {}
        return {
            "from_height": _normalize_non_negative_int(params.get("from_height", 0), field_name="from_height"),
            "include_media_bytes": _normalize_bool_query_value(
                params.get("include_media_bytes", False),
                field_name="include_media_bytes",
            ),
        }

    raise InvalidPeerMessageTypeError(f"Unsupported Protocol v1 peer message type: {message_type}")


def build_protocol_v1_peer_envelope(
    payload: Any,
    *,
    network_id: str,
    message_type: str,
    sender_node_id: str,
    timestamp: int,
    nonce: str,
    peer_message_version: int = PROTOCOL_V1_PEER_MESSAGE_VERSION,
    protocol_version: int = PROTOCOL_VERSION,
    domain: str = PROTOCOL_V1_PEER_MESSAGE_DOMAIN,
) -> dict[str, Any]:
    if domain != PROTOCOL_V1_PEER_MESSAGE_DOMAIN:
        raise ProtocolV1PeerMessageError("Unsupported peer message domain.")

    return canonical_json_data(
        {
            "domain": PROTOCOL_V1_PEER_MESSAGE_DOMAIN,
            "message_type": normalize_protocol_v1_peer_message_type(message_type),
            "network_id": normalize_network_id(network_id),
            "nonce": normalize_protocol_v1_peer_nonce(nonce),
            "object_type": OBJECT_TYPE_PEER_MESSAGE,
            "payload": canonical_json_data(normalize_protocol_v1_peer_payload(payload)),
            "peer_message_version": normalize_protocol_v1_peer_message_version(peer_message_version),
            "protocol": PROTOCOL_NAME,
            "protocol_version": normalize_protocol_v1_protocol_version(protocol_version),
            "sender_node_id": normalize_protocol_v1_peer_sender_node_id(sender_node_id),
            "timestamp": normalize_protocol_v1_peer_timestamp(timestamp),
        }
    )


def protocol_v1_peer_envelope_bytes(
    payload: Any,
    *,
    network_id: str,
    message_type: str,
    sender_node_id: str,
    timestamp: int,
    nonce: str,
    peer_message_version: int = PROTOCOL_V1_PEER_MESSAGE_VERSION,
    protocol_version: int = PROTOCOL_VERSION,
) -> bytes:
    return canonical_json_bytes(
        build_protocol_v1_peer_envelope(
            payload,
            network_id=network_id,
            message_type=message_type,
            sender_node_id=sender_node_id,
            timestamp=timestamp,
            nonce=nonce,
            peer_message_version=peer_message_version,
            protocol_version=protocol_version,
        )
    )


def protocol_v1_peer_envelope_text(
    payload: Any,
    *,
    network_id: str,
    message_type: str,
    sender_node_id: str,
    timestamp: int,
    nonce: str,
    peer_message_version: int = PROTOCOL_V1_PEER_MESSAGE_VERSION,
    protocol_version: int = PROTOCOL_VERSION,
) -> str:
    return protocol_v1_peer_envelope_bytes(
        payload,
        network_id=network_id,
        message_type=message_type,
        sender_node_id=sender_node_id,
        timestamp=timestamp,
        nonce=nonce,
        peer_message_version=peer_message_version,
        protocol_version=protocol_version,
    ).decode("utf-8")


def calculate_protocol_v1_peer_message_id(
    payload: Any,
    *,
    network_id: str,
    message_type: str,
    sender_node_id: str,
    timestamp: int,
    nonce: str,
    peer_message_version: int = PROTOCOL_V1_PEER_MESSAGE_VERSION,
    protocol_version: int = PROTOCOL_VERSION,
) -> str:
    return hashlib.sha256(
        protocol_v1_peer_envelope_bytes(
            payload,
            network_id=network_id,
            message_type=message_type,
            sender_node_id=sender_node_id,
            timestamp=timestamp,
            nonce=nonce,
            peer_message_version=peer_message_version,
            protocol_version=protocol_version,
        )
    ).hexdigest()


def sign_protocol_v1_peer_message(
    payload: Any,
    *,
    network_id: str,
    message_type: str,
    sender_node_id: str,
    timestamp: int,
    nonce: str,
    secret: str,
    peer_message_version: int = PROTOCOL_V1_PEER_MESSAGE_VERSION,
    protocol_version: int = PROTOCOL_VERSION,
) -> str:
    if not isinstance(secret, str) or not secret:
        raise InvalidPeerSignatureError("Peer shared secret is required for Protocol v1 peer signing.")
    return hmac.new(
        secret.encode("utf-8"),
        protocol_v1_peer_envelope_bytes(
            payload,
            network_id=network_id,
            message_type=message_type,
            sender_node_id=sender_node_id,
            timestamp=timestamp,
            nonce=nonce,
            peer_message_version=peer_message_version,
            protocol_version=protocol_version,
        ),
        hashlib.sha256,
    ).hexdigest()


def looks_like_protocol_v1_peer_headers(headers: Mapping[str, Any] | None) -> bool:
    if headers is None:
        return False
    return any(headers.get(header_name) is not None for header_name in PROTOCOL_V1_REQUIRED_PEER_HEADERS)


def build_protocol_v1_peer_request_headers(
    method: Any,
    path: Any,
    payload: dict[str, Any] | None,
    sender_node_id: str,
    *,
    network_id: str | None = None,
    network_name: str | None = None,
    secret: str,
    timestamp: int | None = None,
    nonce: str | None = None,
    query_params: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    resolved_network_id = resolve_protocol_v1_peer_network_id(
        network_id=network_id,
        network_name=network_name,
    )
    payload_for_auth = build_protocol_v1_peer_request_payload(
        method,
        path,
        body_payload=payload,
        query_params=query_params,
    )
    timestamp_value = int(time.time()) if timestamp is None else normalize_protocol_v1_peer_timestamp(timestamp)
    nonce_value = secrets.token_hex(16) if nonce is None else normalize_protocol_v1_peer_nonce(nonce)
    message_type = infer_protocol_v1_peer_message_type(method, path)
    message_id = calculate_protocol_v1_peer_message_id(
        payload_for_auth,
        network_id=resolved_network_id,
        message_type=message_type,
        sender_node_id=sender_node_id,
        timestamp=timestamp_value,
        nonce=nonce_value,
    )
    signature = sign_protocol_v1_peer_message(
        payload_for_auth,
        network_id=resolved_network_id,
        message_type=message_type,
        sender_node_id=sender_node_id,
        timestamp=timestamp_value,
        nonce=nonce_value,
        secret=secret,
    )
    return {
        HEADER_PEER_MESSAGE_VERSION: str(PROTOCOL_V1_PEER_MESSAGE_VERSION),
        HEADER_PROTOCOL_VERSION: str(PROTOCOL_VERSION),
        HEADER_NETWORK_ID: resolved_network_id,
        HEADER_MESSAGE_TYPE: message_type,
        HEADER_NODE_ID: normalize_protocol_v1_peer_sender_node_id(sender_node_id),
        HEADER_TIMESTAMP: str(timestamp_value),
        HEADER_NONCE: nonce_value,
        HEADER_MESSAGE_ID: message_id,
        HEADER_SIGNATURE: signature,
    }


class ProtocolV1PeerReplayStore:
    def __init__(self, file_path: str | Path, *, retention_window_seconds: int):
        self.file_path = Path(file_path)
        self.retention_window_seconds = _normalize_non_negative_int(
            retention_window_seconds,
            field_name="retention_window_seconds",
        )
        self._lock = threading.Lock()

    def _default_document(self) -> dict[str, Any]:
        return {
            "replay_state_version": PROTOCOL_V1_PEER_REPLAY_STATE_VERSION,
            "retention_window_seconds": self.retention_window_seconds,
            "entries": [],
        }

    def _normalize_entry(self, entry: Any) -> dict[str, Any]:
        if not isinstance(entry, dict):
            raise ReplayStateUnavailableError("Peer replay state entry must be an object.")
        return {
            "sender_node_id": normalize_protocol_v1_peer_sender_node_id(entry.get("sender_node_id")),
            "nonce": normalize_protocol_v1_peer_nonce(entry.get("nonce")),
            "message_id": normalize_protocol_v1_peer_message_id(entry.get("message_id")),
            "timestamp": normalize_protocol_v1_peer_timestamp(entry.get("timestamp")),
            "expires_at": _normalize_non_negative_int(entry.get("expires_at"), field_name="expires_at"),
        }

    def _load_document(self) -> tuple[dict[str, Any], bool]:
        try:
            document, recovered_from_backup = _load_json_document_with_backup(
                self.file_path,
                backup_path=_backup_path_for(self.file_path),
                label="peer replay state JSON",
                expected_type=dict,
            )
        except StorageCorruptionError as exc:
            raise ReplayStateUnavailableError(
                "Peer replay state is unavailable because the persisted state is corrupt."
            ) from exc

        if document is None:
            return self._default_document(), False
        if not isinstance(document.get("entries", []), list):
            raise ReplayStateUnavailableError("Peer replay state entries must be a list.")

        normalized_entries = [self._normalize_entry(entry) for entry in document.get("entries", [])]
        normalized_entries.sort(
            key=lambda entry: (
                entry["expires_at"],
                entry["sender_node_id"],
                entry["nonce"],
                entry["message_id"],
            )
        )
        return (
            {
                "replay_state_version": PROTOCOL_V1_PEER_REPLAY_STATE_VERSION,
                "retention_window_seconds": self.retention_window_seconds,
                "entries": normalized_entries,
            },
            recovered_from_backup,
        )

    def _save_document(self, document: dict[str, Any]) -> None:
        _atomic_write_json_document(
            self.file_path,
            document,
            backup_path=_backup_path_for(self.file_path),
            create_backup_from_existing=True,
        )

    def list_entries(self, *, now: int | None = None) -> list[dict[str, Any]]:
        now_value = int(time.time()) if now is None else normalize_protocol_v1_peer_timestamp(now)
        with self._lock:
            document, changed = self._load_document()
            entries = self._prune_entries(document.get("entries", []), now=now_value)
            if changed or len(entries) != len(document.get("entries", [])):
                document["entries"] = entries
                self._save_document(document)
            return [dict(entry) for entry in entries]

    def _prune_entries(self, entries: list[dict[str, Any]], *, now: int) -> list[dict[str, Any]]:
        return [
            dict(entry)
            for entry in entries
            if isinstance(entry, dict) and int(entry.get("expires_at", -1)) >= now
        ]

    def reject_replay_or_record(
        self,
        *,
        sender_node_id: str,
        nonce: str,
        message_id: str,
        timestamp: int,
        now: int | None = None,
    ) -> None:
        normalized_sender = normalize_protocol_v1_peer_sender_node_id(sender_node_id)
        normalized_nonce = normalize_protocol_v1_peer_nonce(nonce)
        normalized_message_id = normalize_protocol_v1_peer_message_id(message_id)
        normalized_timestamp = normalize_protocol_v1_peer_timestamp(timestamp)
        now_value = int(time.time()) if now is None else normalize_protocol_v1_peer_timestamp(now)

        with self._lock:
            document, _changed = self._load_document()
            entries = self._prune_entries(document.get("entries", []), now=now_value)

            for entry in entries:
                if entry["message_id"] == normalized_message_id:
                    raise ReplayedPeerMessageError("Replayed peer message.")
                if entry["sender_node_id"] == normalized_sender and entry["nonce"] == normalized_nonce:
                    raise ReplayedPeerMessageError("Replayed peer nonce.")

            entries.append(
                {
                    "sender_node_id": normalized_sender,
                    "nonce": normalized_nonce,
                    "message_id": normalized_message_id,
                    "timestamp": normalized_timestamp,
                    "expires_at": normalized_timestamp + self.retention_window_seconds,
                }
            )
            entries.sort(
                key=lambda entry: (
                    entry["expires_at"],
                    entry["sender_node_id"],
                    entry["nonce"],
                    entry["message_id"],
                )
            )
            document["entries"] = entries
            document["retention_window_seconds"] = self.retention_window_seconds
            self._save_document(document)

    def clear(self) -> None:
        with self._lock:
            for candidate in (self.file_path, Path(_backup_path_for(self.file_path))):
                try:
                    candidate.unlink()
                except FileNotFoundError:
                    continue


def get_protocol_v1_peer_replay_store(
    *,
    data_dir: str | Path,
    retention_window_seconds: int,
) -> ProtocolV1PeerReplayStore:
    file_path = Path(data_dir) / PROTOCOL_V1_PEER_REPLAY_STATE_FILE
    cache_key = str(file_path)
    retention_window = _normalize_non_negative_int(
        retention_window_seconds,
        field_name="retention_window_seconds",
    )
    with _REPLAY_STORE_CACHE_LOCK:
        store = _REPLAY_STORE_CACHE.get(cache_key)
        if store is None or store.retention_window_seconds != retention_window:
            store = ProtocolV1PeerReplayStore(
                file_path,
                retention_window_seconds=retention_window,
            )
            _REPLAY_STORE_CACHE[cache_key] = store
        return store


def clear_protocol_v1_peer_replay_store_cache(*, data_dir: str | Path | None = None) -> None:
    with _REPLAY_STORE_CACHE_LOCK:
        if data_dir is None:
            stores = list(_REPLAY_STORE_CACHE.values())
            _REPLAY_STORE_CACHE.clear()
        else:
            file_path = str(Path(data_dir) / PROTOCOL_V1_PEER_REPLAY_STATE_FILE)
            store = _REPLAY_STORE_CACHE.pop(file_path, None)
            stores = [store] if store is not None else []
    for store in stores:
        store.clear()


def verify_protocol_v1_peer_request(
    *,
    method: Any,
    path: Any,
    headers: Mapping[str, Any],
    payload: Any,
    expected_network_id: str,
    secret: str,
    timestamp_window_seconds: int,
    replay_store: ProtocolV1PeerReplayStore | None = None,
    now: int | None = None,
) -> ProtocolV1PeerAuthContext:
    if not looks_like_protocol_v1_peer_headers(headers):
        raise MissingProtocolV1PeerHeadersError("Missing Protocol v1 peer headers.")

    missing_headers = [
        header_name
        for header_name in PROTOCOL_V1_REQUIRED_PEER_HEADERS
        if headers.get(header_name) in (None, "")
    ]
    if missing_headers:
        raise MissingProtocolV1PeerHeadersError(
            f"Missing Protocol v1 peer headers: {', '.join(missing_headers)}."
        )

    peer_message_version = normalize_protocol_v1_peer_message_version(headers.get(HEADER_PEER_MESSAGE_VERSION))
    protocol_version = normalize_protocol_v1_protocol_version(headers.get(HEADER_PROTOCOL_VERSION))
    network_id = normalize_network_id(headers.get(HEADER_NETWORK_ID))
    message_type = normalize_protocol_v1_peer_message_type(headers.get(HEADER_MESSAGE_TYPE))
    sender_node_id = normalize_protocol_v1_peer_sender_node_id(headers.get(HEADER_NODE_ID))
    timestamp = normalize_protocol_v1_peer_timestamp(headers.get(HEADER_TIMESTAMP))
    nonce = normalize_protocol_v1_peer_nonce(headers.get(HEADER_NONCE))
    message_id = normalize_protocol_v1_peer_message_id(headers.get(HEADER_MESSAGE_ID))
    signature = str(headers.get(HEADER_SIGNATURE)).strip().lower()
    if not PROTOCOL_V1_PEER_MESSAGE_ID_PATTERN.fullmatch(signature):
        raise InvalidPeerSignatureError("Peer signature must be a 64-character lowercase hexadecimal string.")

    expected_message_type = infer_protocol_v1_peer_message_type(method, path)
    if message_type != expected_message_type:
        raise InvalidPeerMessageTypeError("Peer message type does not match the requested peer route.")

    normalized_expected_network_id = normalize_network_id(expected_network_id)
    if network_id != normalized_expected_network_id:
        raise WrongPeerNetworkError("Peer message belongs to a different network.")

    if isinstance(timestamp_window_seconds, bool):
        raise InvalidPeerTimestampError("Peer timestamp window is invalid.")
    try:
        window_seconds = int(timestamp_window_seconds)
    except (TypeError, ValueError) as exc:
        raise InvalidPeerTimestampError("Peer timestamp window is invalid.") from exc
    if window_seconds < 0:
        raise InvalidPeerTimestampError("Peer timestamp window is invalid.")

    now_value = int(time.time()) if now is None else normalize_protocol_v1_peer_timestamp(now)
    if timestamp < now_value - window_seconds or timestamp > now_value + window_seconds:
        raise ExpiredPeerMessageError("Peer message timestamp outside the allowed window.")

    envelope = build_protocol_v1_peer_envelope(
        payload,
        network_id=network_id,
        message_type=message_type,
        sender_node_id=sender_node_id,
        timestamp=timestamp,
        nonce=nonce,
        peer_message_version=peer_message_version,
        protocol_version=protocol_version,
    )
    expected_message_id = calculate_protocol_v1_peer_message_id(
        payload,
        network_id=network_id,
        message_type=message_type,
        sender_node_id=sender_node_id,
        timestamp=timestamp,
        nonce=nonce,
        peer_message_version=peer_message_version,
        protocol_version=protocol_version,
    )
    if not hmac.compare_digest(message_id, expected_message_id):
        raise InvalidPeerMessageIdError("Invalid peer message ID.")

    expected_signature = sign_protocol_v1_peer_message(
        payload,
        network_id=network_id,
        message_type=message_type,
        sender_node_id=sender_node_id,
        timestamp=timestamp,
        nonce=nonce,
        secret=secret,
        peer_message_version=peer_message_version,
        protocol_version=protocol_version,
    )
    if not hmac.compare_digest(signature, expected_signature):
        raise InvalidPeerSignatureError("Invalid peer signature.")

    if replay_store is not None:
        replay_store.reject_replay_or_record(
            sender_node_id=sender_node_id,
            nonce=nonce,
            message_id=message_id,
            timestamp=timestamp,
            now=now_value,
        )

    return ProtocolV1PeerAuthContext(
        peer_message_version=peer_message_version,
        protocol_version=protocol_version,
        network_id=network_id,
        message_type=message_type,
        sender_node_id=sender_node_id,
        timestamp=timestamp,
        nonce=nonce,
        message_id=message_id,
        signature=signature,
        envelope=envelope,
        payload=canonical_json_data(normalize_protocol_v1_peer_payload(payload)),
    )
