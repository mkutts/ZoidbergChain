from __future__ import annotations

import json
from typing import Any

from native_transfer import (
    MAX_TRANSFER_MEMO_LENGTH,
    normalize_wallet_address,
    parse_native_zoid_amount,
    parse_transfer_nonce,
    parse_transfer_timestamp,
)
from protocol_v1 import (
    OBJECT_TYPE_NATIVE_TRANSFER,
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    canonical_domain_bytes,
    canonical_domain_hash,
    canonical_json_data,
    normalize_network_id,
    resolve_network_id,
)


PROTOCOL_V1_NATIVE_TRANSFER_VERSION = PROTOCOL_VERSION


def resolve_protocol_v1_network_id(*, network_id: str | None = None, network_name: str | None = None) -> str:
    if network_id is not None:
        return normalize_network_id(network_id)
    try:
        return resolve_network_id(network_name=network_name)
    except ValueError:
        if isinstance(network_name, str) and network_name.strip():
            return normalize_network_id(network_name.strip())
        raise


def normalize_protocol_v1_transfer_memo(memo: Any) -> str | None:
    if memo is None:
        return None
    candidate = str(memo).strip()
    if not candidate:
        return None
    if len(candidate) > MAX_TRANSFER_MEMO_LENGTH:
        raise ValueError(f"memo exceeds the {MAX_TRANSFER_MEMO_LENGTH}-character limit.")
    return candidate


def build_protocol_v1_native_transfer_payload(
    *,
    from_address: str,
    to_address: str,
    amount: str,
    fee: str,
    nonce: str | int,
    timestamp: str,
    memo: str | None = None,
) -> dict[str, Any]:
    normalized_from = normalize_wallet_address(from_address)
    if normalized_from is None:
        raise ValueError("from_address must be a valid Ethereum-style 0x address.")

    normalized_to = normalize_wallet_address(to_address)
    if normalized_to is None:
        raise ValueError("to_address must be a valid Ethereum-style 0x address.")
    if normalized_from == normalized_to:
        raise ValueError("from_address and to_address must be different.")

    return canonical_json_data(
        {
            "transaction_version": PROTOCOL_V1_NATIVE_TRANSFER_VERSION,
            "from_address": normalized_from,
            "to_address": normalized_to,
            "amount": parse_native_zoid_amount(amount, allow_zero=False),
            "fee": parse_native_zoid_amount(fee, allow_zero=True),
            "nonce": parse_transfer_nonce(nonce),
            "timestamp": parse_transfer_timestamp(timestamp),
            "memo": normalize_protocol_v1_transfer_memo(memo),
        }
    )


def build_protocol_v1_native_transfer_signing_payload(
    *,
    from_address: str,
    to_address: str,
    amount: str,
    fee: str,
    nonce: str | int,
    timestamp: str,
    memo: str | None = None,
    network_id: str,
) -> dict[str, Any]:
    return canonical_json_data(
        {
            "domain": f"{PROTOCOL_NAME}/{OBJECT_TYPE_NATIVE_TRANSFER}/v{PROTOCOL_V1_NATIVE_TRANSFER_VERSION}",
            "network_id": normalize_network_id(network_id),
            "object_type": OBJECT_TYPE_NATIVE_TRANSFER,
            "payload": build_protocol_v1_native_transfer_payload(
                from_address=from_address,
                to_address=to_address,
                amount=amount,
                fee=fee,
                nonce=nonce,
                timestamp=timestamp,
                memo=memo,
            ),
            "protocol": PROTOCOL_NAME,
            "protocol_version": PROTOCOL_VERSION,
        }
    )


def build_protocol_v1_native_transfer_message(
    *,
    from_address: str,
    to_address: str,
    amount: str,
    fee: str,
    nonce: str | int,
    timestamp: str,
    memo: str | None = None,
    network_id: str,
) -> str:
    return canonical_domain_bytes(
        build_protocol_v1_native_transfer_payload(
            from_address=from_address,
            to_address=to_address,
            amount=amount,
            fee=fee,
            nonce=nonce,
            timestamp=timestamp,
            memo=memo,
        ),
        object_type=OBJECT_TYPE_NATIVE_TRANSFER,
        network_id=normalize_network_id(network_id),
    ).decode("utf-8")


def build_protocol_v1_native_transfer_message_hash(
    *,
    from_address: str,
    to_address: str,
    amount: str,
    fee: str,
    nonce: str | int,
    timestamp: str,
    memo: str | None = None,
    network_id: str,
) -> str:
    return canonical_domain_hash(
        build_protocol_v1_native_transfer_payload(
            from_address=from_address,
            to_address=to_address,
            amount=amount,
            fee=fee,
            nonce=nonce,
            timestamp=timestamp,
            memo=memo,
        ),
        object_type=OBJECT_TYPE_NATIVE_TRANSFER,
        network_id=normalize_network_id(network_id),
    )


def build_protocol_v1_transaction_identity_payload(transaction_fields: dict[str, Any]) -> dict[str, Any]:
    return build_protocol_v1_native_transfer_payload(
        from_address=transaction_fields.get("from_address"),
        to_address=transaction_fields.get("to_address"),
        amount=transaction_fields.get("amount"),
        fee=transaction_fields.get("fee", "0"),
        nonce=transaction_fields.get("nonce"),
        timestamp=transaction_fields.get("timestamp"),
        memo=transaction_fields.get("memo"),
    )


def calculate_protocol_v1_transaction_id(transaction_fields: dict[str, Any], *, network_id: str) -> str:
    return canonical_domain_hash(
        build_protocol_v1_transaction_identity_payload(transaction_fields),
        object_type=OBJECT_TYPE_NATIVE_TRANSFER,
        network_id=normalize_network_id(network_id),
    )


def looks_like_protocol_v1_native_transfer_message(message: Any) -> bool:
    if not isinstance(message, str) or not message.strip():
        return False
    try:
        payload = json.loads(message)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    if payload.get("protocol") != PROTOCOL_NAME:
        return False
    if payload.get("protocol_version") != PROTOCOL_VERSION:
        return False
    if payload.get("object_type") != OBJECT_TYPE_NATIVE_TRANSFER:
        return False
    if payload.get("domain") != f"{PROTOCOL_NAME}/{OBJECT_TYPE_NATIVE_TRANSFER}/v{PROTOCOL_V1_NATIVE_TRANSFER_VERSION}":
        return False
    return isinstance(payload.get("network_id"), str) and isinstance(payload.get("payload"), dict)


def parse_protocol_v1_native_transfer_message(
    message: str,
    *,
    expected_network_id: str | None = None,
) -> dict[str, Any]:
    if not looks_like_protocol_v1_native_transfer_message(message):
        raise ValueError("message is not a valid Protocol v1 native transfer signing payload.")

    envelope = json.loads(message)
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("Protocol v1 native transfer payload must be an object.")

    network_id = resolve_protocol_v1_network_id(network_id=envelope.get("network_id"))
    if expected_network_id is not None:
        resolved_expected_network_id = resolve_protocol_v1_network_id(network_id=expected_network_id)
        if network_id != resolved_expected_network_id:
            raise ValueError("Transfer belongs to a different network.")

    normalized_payload = build_protocol_v1_native_transfer_payload(
        from_address=payload.get("from_address"),
        to_address=payload.get("to_address"),
        amount=payload.get("amount"),
        fee=payload.get("fee", "0"),
        nonce=payload.get("nonce"),
        timestamp=payload.get("timestamp"),
        memo=payload.get("memo"),
    )
    if payload.get("transaction_version") != PROTOCOL_V1_NATIVE_TRANSFER_VERSION:
        raise ValueError("Protocol v1 native transfer transaction_version is unsupported.")

    expected_message = build_protocol_v1_native_transfer_message(
        from_address=normalized_payload["from_address"],
        to_address=normalized_payload["to_address"],
        amount=normalized_payload["amount"],
        fee=normalized_payload["fee"],
        nonce=normalized_payload["nonce"],
        timestamp=normalized_payload["timestamp"],
        memo=normalized_payload["memo"],
        network_id=network_id,
    )
    if message != expected_message:
        raise ValueError("Transfer message does not match the Protocol v1 native transfer payload.")

    return {
        "transaction_version": PROTOCOL_V1_NATIVE_TRANSFER_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "network_id": network_id,
        "from_address": normalized_payload["from_address"],
        "to_address": normalized_payload["to_address"],
        "amount": normalized_payload["amount"],
        "fee": normalized_payload["fee"],
        "nonce": normalized_payload["nonce"],
        "timestamp": normalized_payload["timestamp"],
        "memo": normalized_payload["memo"],
    }
