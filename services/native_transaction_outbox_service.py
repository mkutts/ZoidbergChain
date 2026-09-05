"""Stable native-transaction peer delivery messages and outbox records."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from protocol_v1 import PROTOCOL_VERSION, canonical_json_bytes, resolve_network_id


NATIVE_TRANSACTION_MESSAGE_TYPE = "native-transaction"
NATIVE_TRANSACTION_MESSAGE_VERSION = 1
NATIVE_TRANSACTION_MESSAGE_ID_DOMAIN = "zoidbergchain:peer-native-transaction-delivery:v1"
NATIVE_TRANSACTION_OUTBOX_ID_DOMAIN = "zoidbergchain:peer-native-transaction-outbox:v1"

_SIGNED_TRANSACTION_FIELDS = (
    "tx_id",
    "transaction_type",
    "network",
    "transaction_version",
    "protocol_version",
    "network_id",
    "from_address",
    "to_address",
    "amount",
    "fee",
    "nonce",
    "timestamp",
    "memo",
    "signature",
    "signature_scheme",
    "signed_message",
    "signed_message_hash",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_canonical(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def native_transaction_delivery_message_id(
    *, tx_id: str, network_id: str, sender_node_id: str
) -> str:
    """Return the logical ID, stable across destinations, restarts, and retries."""
    return _sha256_canonical(
        {
            "domain": NATIVE_TRANSACTION_MESSAGE_ID_DOMAIN,
            "message_type": NATIVE_TRANSACTION_MESSAGE_TYPE,
            "network_id": str(network_id).strip(),
            "sender_node_id": str(sender_node_id).strip(),
            "tx_id": str(tx_id).strip().lower(),
        }
    )


def native_transaction_delivery_payload_hash(transaction: dict[str, Any]) -> str:
    """Hash only user-signed identity fields, excluding peer-local lifecycle data."""
    return _sha256_canonical(
        {field: transaction.get(field) for field in _SIGNED_TRANSACTION_FIELDS}
    )


def serialize_signed_native_transaction(transaction: dict[str, Any]) -> dict[str, Any]:
    """Exclude every sender-local lifecycle field from the peer payload."""
    return {
        field: transaction.get(field)
        for field in _SIGNED_TRANSACTION_FIELDS
        if field in transaction
    }


def native_transaction_outbox_record_id(message_id: str, destination_peer_id: str) -> str:
    return _sha256_canonical(
        {
            "domain": NATIVE_TRANSACTION_OUTBOX_ID_DOMAIN,
            "destination_peer_id": str(destination_peer_id).strip(),
            "message_id": str(message_id).strip().lower(),
        }
    )


def build_native_transaction_peer_message(
    transaction: dict[str, Any],
    *,
    sender_node_id: str,
    network_name: str,
) -> dict[str, Any]:
    tx_id = str(transaction.get("tx_id") or "").strip().lower()
    if not tx_id:
        raise ValueError("Native transaction tx_id is required for peer delivery.")
    network_id = resolve_network_id(network_name=network_name)
    message_id = native_transaction_delivery_message_id(
        tx_id=tx_id,
        network_id=network_id,
        sender_node_id=sender_node_id,
    )
    return {
        "message_type": NATIVE_TRANSACTION_MESSAGE_TYPE,
        "peer_message_version": NATIVE_TRANSACTION_MESSAGE_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "message_id": message_id,
        "origin_node_id": str(sender_node_id).strip(),
        "network_name": str(network_name).strip(),
        "network_id": network_id,
        "transaction": serialize_signed_native_transaction(transaction),
    }


def validate_native_transaction_peer_message(
    message: dict[str, Any],
    *,
    expected_sender_node_id: str,
    expected_network_name: str,
) -> dict[str, Any]:
    if not isinstance(message, dict):
        raise ValueError("Peer native transaction message must be an object.")
    if message.get("message_type") != NATIVE_TRANSACTION_MESSAGE_TYPE:
        raise ValueError("Unsupported peer native transaction message type.")
    if message.get("peer_message_version") != NATIVE_TRANSACTION_MESSAGE_VERSION:
        raise ValueError("Unsupported peer native transaction message version.")
    if message.get("protocol_version") != PROTOCOL_VERSION:
        raise ValueError("Unsupported peer native transaction protocol version.")
    if str(message.get("origin_node_id") or "").strip() != str(expected_sender_node_id).strip():
        raise ValueError("Peer native transaction sender does not match authenticated sender.")
    if str(message.get("network_name") or "").strip() != str(expected_network_name).strip():
        raise ValueError("Peer native transaction network does not match the local network.")
    expected_network_id = resolve_network_id(network_name=expected_network_name)
    if str(message.get("network_id") or "").strip() != expected_network_id:
        raise ValueError("Peer native transaction network_id does not match the local network.")
    transaction = message.get("transaction")
    if not isinstance(transaction, dict):
        raise ValueError("Peer native transaction payload must be an object.")
    expected_message_id = native_transaction_delivery_message_id(
        tx_id=str(transaction.get("tx_id") or "").strip().lower(),
        network_id=expected_network_id,
        sender_node_id=expected_sender_node_id,
    )
    if str(message.get("message_id") or "").strip().lower() != expected_message_id:
        raise ValueError("Peer native transaction message_id does not match its immutable identity.")
    return {
        "message_id": expected_message_id,
        "message_type": NATIVE_TRANSACTION_MESSAGE_TYPE,
        "sender_node_id": str(expected_sender_node_id).strip(),
        "tx_id": str(transaction.get("tx_id") or "").strip().lower(),
        "payload_hash": native_transaction_delivery_payload_hash(transaction),
        "transaction": transaction,
    }


def build_native_transaction_outbox_records(
    transaction: dict[str, Any],
    peers: list[dict[str, Any]],
    *,
    sender_node_id: str,
    network_name: str,
    created_at: str | None = None,
) -> list[dict[str, Any]]:
    message = build_native_transaction_peer_message(
        transaction,
        sender_node_id=sender_node_id,
        network_name=network_name,
    )
    serialized_message = json.dumps(
        message, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    now = created_at or utc_now_iso()
    records = []
    for peer in peers or []:
        if not isinstance(peer, dict):
            continue
        if peer.get("status") != "active" or peer.get("network_name") != network_name:
            continue
        destination_peer_id = str(peer.get("node_id") or "").strip()
        destination_peer_url = str(peer.get("url") or "").strip().rstrip("/")
        if not destination_peer_id or not destination_peer_url or destination_peer_id == sender_node_id:
            continue
        records.append(
            {
                "outbox_id": native_transaction_outbox_record_id(
                    message["message_id"], destination_peer_id
                ),
                "message_id": message["message_id"],
                "message_type": NATIVE_TRANSACTION_MESSAGE_TYPE,
                "tx_id": message["transaction"]["tx_id"],
                "destination_peer_id": destination_peer_id,
                "destination_peer_url": destination_peer_url,
                "serialized_message": serialized_message,
                "delivery_state": "queued",
                "attempt_count": 0,
                "created_at": now,
                "last_attempt_at": None,
                "next_attempt_at": None,
                "acknowledged_at": None,
                "claim_token": None,
                "claim_expires_at": None,
                "last_error_code": None,
                "last_error_detail": None,
            }
        )
    return records
