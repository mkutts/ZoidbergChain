from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any


PROTOCOL_NAME = "zoidbergchain"
PROTOCOL_VERSION = 1
PROTOCOL_VERSION_TAG = f"v{PROTOCOL_VERSION}"

PUBLIC_TESTNET_V1_NETWORK_ID = "zoidberg-public-testnet-v1"
LEGACY_PUBLIC_TESTNET_NETWORK_NAME = "zoidberg-testnet"

OBJECT_TYPE_BLOCK = "block"
OBJECT_TYPE_ORIGINALITY_CERTIFICATE = "originality-certificate"
OBJECT_TYPE_SUBMISSION = "submission"
OBJECT_TYPE_VOTE = "vote"
OBJECT_TYPE_NATIVE_TRANSFER = "native-transfer"
OBJECT_TYPE_FINALITY_ATTESTATION = "finality-attestation"
OBJECT_TYPE_PEER_MESSAGE = "peer-message"
OBJECT_TYPE_GENESIS = "genesis"

OBJECT_TYPES = (
    OBJECT_TYPE_BLOCK,
    OBJECT_TYPE_ORIGINALITY_CERTIFICATE,
    OBJECT_TYPE_SUBMISSION,
    OBJECT_TYPE_VOTE,
    OBJECT_TYPE_NATIVE_TRANSFER,
    OBJECT_TYPE_FINALITY_ATTESTATION,
    OBJECT_TYPE_PEER_MESSAGE,
    OBJECT_TYPE_GENESIS,
)

OBJECT_DOMAINS = {
    object_type: f"{PROTOCOL_NAME}/{object_type}/{PROTOCOL_VERSION_TAG}"
    for object_type in OBJECT_TYPES
}

_PROTOCOL_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
_NETWORK_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
_OBJECT_TYPE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
_CANONICAL_BYTES_TYPE = "bytes"
_CANONICAL_BYTES_ENCODING = "hex"
_CANONICAL_BYTES_TAG_KEYS = frozenset({"$type", "$encoding", "$value"})

_NETWORK_NAME_TO_ID = {
    LEGACY_PUBLIC_TESTNET_NETWORK_NAME: PUBLIC_TESTNET_V1_NETWORK_ID,
    PUBLIC_TESTNET_V1_NETWORK_ID: PUBLIC_TESTNET_V1_NETWORK_ID,
}


class _CanonicalBytesObject(dict):
    pass


def is_valid_protocol_name(value: str) -> bool:
    return bool(isinstance(value, str) and _PROTOCOL_NAME_PATTERN.fullmatch(value.strip()))


def is_valid_protocol_version(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def is_valid_network_id(value: str) -> bool:
    return bool(isinstance(value, str) and _NETWORK_ID_PATTERN.fullmatch(value.strip()))


def normalize_network_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("network_id must be a string.")
    normalized = value.strip().lower()
    if not is_valid_network_id(normalized):
        raise ValueError(f"Invalid network_id: {value!r}.")
    return normalized


def resolve_network_id(*, network_id: str | None = None, network_name: str | None = None) -> str:
    if network_id is not None:
        return normalize_network_id(network_id)
    if not isinstance(network_name, str) or not network_name.strip():
        raise ValueError("network_name is required when network_id is not provided.")
    normalized_name = network_name.strip()
    try:
        return _NETWORK_NAME_TO_ID[normalized_name]
    except KeyError as exc:
        raise ValueError(f"Unknown network_name for Protocol v1 network identity: {network_name!r}.") from exc


def current_runtime_network_id() -> str:
    import config

    return resolve_network_id(network_name=config.NETWORK_NAME)


def is_valid_object_type(value: str) -> bool:
    return bool(
        isinstance(value, str)
        and value in OBJECT_DOMAINS
        and _OBJECT_TYPE_PATTERN.fullmatch(value.strip())
    )


def protocol_domain(object_type: str, *, protocol_name: str = PROTOCOL_NAME, protocol_version: int = PROTOCOL_VERSION) -> str:
    normalized_object_type = normalize_object_type(object_type)
    normalized_protocol_name = normalize_protocol_name(protocol_name)
    normalized_protocol_version = normalize_protocol_version(protocol_version)
    return f"{normalized_protocol_name}/{normalized_object_type}/v{normalized_protocol_version}"


def normalize_protocol_name(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("protocol_name must be a string.")
    normalized = value.strip().lower()
    if not is_valid_protocol_name(normalized):
        raise ValueError(f"Invalid protocol_name: {value!r}.")
    return normalized


def normalize_protocol_version(value: int) -> int:
    if not is_valid_protocol_version(value):
        raise ValueError("protocol_version must be a positive integer.")
    return value


def normalize_object_type(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("object_type must be a string.")
    normalized = value.strip().lower()
    if not is_valid_object_type(normalized):
        raise ValueError(f"Unsupported object_type: {value!r}.")
    return normalized


def encode_canonical_bytes(value: bytes | bytearray | memoryview) -> dict[str, str]:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError("bytes-like value is required.")
    raw = bytes(value)
    return _CanonicalBytesObject({
        "$type": _CANONICAL_BYTES_TYPE,
        "$encoding": _CANONICAL_BYTES_ENCODING,
        "$value": raw.hex(),
    })


def is_canonical_bytes_object(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value.keys()) == _CANONICAL_BYTES_TAG_KEYS
        and value.get("$type") == _CANONICAL_BYTES_TYPE
        and value.get("$encoding") == _CANONICAL_BYTES_ENCODING
        and isinstance(value.get("$value"), str)
    )


def decode_canonical_bytes(value: Any) -> bytes:
    if not isinstance(value, dict):
        raise ValueError("Canonical bytes value must be an object.")
    if set(value.keys()) != _CANONICAL_BYTES_TAG_KEYS:
        raise ValueError("Canonical bytes object must contain exactly $type, $encoding, and $value.")
    if value.get("$type") != _CANONICAL_BYTES_TYPE:
        raise ValueError("Canonical bytes object must declare $type='bytes'.")
    if value.get("$encoding") != _CANONICAL_BYTES_ENCODING:
        raise ValueError("Canonical bytes object must declare $encoding='hex'.")
    data = value.get("$value")
    if not isinstance(data, str):
        raise ValueError("Canonical bytes object must include a string $value.")
    if len(data) % 2 != 0 or any(ch not in "0123456789abcdef" for ch in data):
        raise ValueError("Canonical bytes $value must be lowercase hexadecimal.")
    return bytes.fromhex(data)


def _normalize_canonical_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return encode_canonical_bytes(value)
    if isinstance(value, float):
        if math.isnan(value):
            raise ValueError("Canonical serialization does not support NaN.")
        if math.isinf(value):
            raise ValueError("Canonical serialization does not support Infinity.")
        raise ValueError("Canonical serialization does not support float values.")
    if isinstance(value, Decimal):
        raise ValueError("Canonical serialization does not support Decimal values without explicit conversion.")
    if isinstance(value, (datetime, date, time)):
        raise ValueError("Canonical serialization does not support datetime values; use an explicit scalar timestamp.")
    if isinstance(value, tuple):
        raise ValueError("Canonical serialization does not support tuple values.")
    if isinstance(value, set):
        raise ValueError("Canonical serialization does not support set values.")
    if isinstance(value, list):
        return [_normalize_canonical_value(item) for item in value]
    if isinstance(value, dict):
        if set(value.keys()) == _CANONICAL_BYTES_TAG_KEYS and not isinstance(value, _CanonicalBytesObject):
            raise ValueError(
                "Canonical serialization reserves the exact {'$type', '$encoding', '$value'} object shape for bytes."
            )
        normalized_items: list[tuple[str, Any]] = []
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("Canonical serialization requires string dictionary keys.")
            normalized_items.append((key, _normalize_canonical_value(child)))
        normalized_items.sort(key=lambda item: item[0])
        normalized_dict = {key: child for key, child in normalized_items}
        if isinstance(value, _CanonicalBytesObject):
            return _CanonicalBytesObject(normalized_dict)
        return normalized_dict
    raise ValueError(f"Canonical serialization does not support values of type {type(value).__name__}.")


def canonical_json_data(value: Any) -> Any:
    return _normalize_canonical_value(value)


def canonical_json_text(value: Any) -> str:
    normalized = canonical_json_data(value)
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_json_bytes(value: Any) -> bytes:
    return canonical_json_text(value).encode("utf-8")


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def build_domain_envelope(
    payload: Any,
    *,
    object_type: str,
    network_id: str = PUBLIC_TESTNET_V1_NETWORK_ID,
    protocol_name: str = PROTOCOL_NAME,
    protocol_version: int = PROTOCOL_VERSION,
) -> dict[str, Any]:
    normalized_protocol_name = normalize_protocol_name(protocol_name)
    normalized_protocol_version = normalize_protocol_version(protocol_version)
    normalized_network_id = normalize_network_id(network_id)
    normalized_object_type = normalize_object_type(object_type)
    return {
        "domain": protocol_domain(
            normalized_object_type,
            protocol_name=normalized_protocol_name,
            protocol_version=normalized_protocol_version,
        ),
        "network_id": normalized_network_id,
        "object_type": normalized_object_type,
        "payload": canonical_json_data(payload),
        "protocol": normalized_protocol_name,
        "protocol_version": normalized_protocol_version,
    }


def canonical_domain_bytes(
    payload: Any,
    *,
    object_type: str,
    network_id: str = PUBLIC_TESTNET_V1_NETWORK_ID,
    protocol_name: str = PROTOCOL_NAME,
    protocol_version: int = PROTOCOL_VERSION,
) -> bytes:
    envelope = build_domain_envelope(
        payload,
        object_type=object_type,
        network_id=network_id,
        protocol_name=protocol_name,
        protocol_version=protocol_version,
    )
    return canonical_json_bytes(envelope)


def canonical_domain_hash(
    payload: Any,
    *,
    object_type: str,
    network_id: str = PUBLIC_TESTNET_V1_NETWORK_ID,
    protocol_name: str = PROTOCOL_NAME,
    protocol_version: int = PROTOCOL_VERSION,
) -> str:
    return hashlib.sha256(
        canonical_domain_bytes(
            payload,
            object_type=object_type,
            network_id=network_id,
            protocol_name=protocol_name,
            protocol_version=protocol_version,
        )
    ).hexdigest()
