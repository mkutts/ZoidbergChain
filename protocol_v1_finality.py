"""Canonical, domain-separated Public Testnet v1 finality attestations."""

from __future__ import annotations

from typing import Any

from native_transfer import NATIVE_TRANSFER_SIGNATURE_SCHEME, normalize_wallet_address
from protocol_v1 import (
    OBJECT_TYPE_FINALITY_ATTESTATION, PROTOCOL_VERSION, canonical_domain_bytes,
    canonical_domain_hash, canonical_json_data, normalize_network_id, protocol_domain,
)
from validators import is_valid_content_hash

PROTOCOL_V1_FINALITY_ATTESTATION_VERSION = PROTOCOL_VERSION
PROTOCOL_V1_FINALITY_ATTESTATION_DOMAIN = protocol_domain(OBJECT_TYPE_FINALITY_ATTESTATION)


def _normalize_height(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("block_height must be a non-negative integer.")
    try:
        height = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("block_height must be a non-negative integer.") from exc
    if height < 0 or str(value).strip() != str(height):
        raise ValueError("block_height must be a non-negative integer.")
    return height


def build_protocol_v1_finality_attestation_payload(*, validator_address: str, block_height: int, block_hash: str) -> dict[str, Any]:
    validator = normalize_wallet_address(validator_address)
    if validator is None:
        raise ValueError("validator_address must be a valid Ethereum-style 0x address.")
    block_hash = str(block_hash or "").strip().lower()
    if not is_valid_content_hash(block_hash):
        raise ValueError("block_hash must be a 64-character lowercase hexadecimal hash.")
    return canonical_json_data({"attestation_version": PROTOCOL_V1_FINALITY_ATTESTATION_VERSION,
                                "validator_address": validator, "block_height": _normalize_height(block_height),
                                "block_hash": block_hash})


def build_protocol_v1_finality_attestation_message(*, validator_address: str, block_height: int, block_hash: str, network_id: str) -> str:
    return canonical_domain_bytes(
        build_protocol_v1_finality_attestation_payload(validator_address=validator_address, block_height=block_height, block_hash=block_hash),
        object_type=OBJECT_TYPE_FINALITY_ATTESTATION, network_id=normalize_network_id(network_id),
    ).decode("utf-8")


def build_protocol_v1_finality_attestation_message_hash(**values) -> str:
    return canonical_domain_hash(
        build_protocol_v1_finality_attestation_payload(validator_address=values["validator_address"], block_height=values["block_height"], block_hash=values["block_hash"]),
        object_type=OBJECT_TYPE_FINALITY_ATTESTATION, network_id=normalize_network_id(values["network_id"]),
    )


def build_protocol_v1_finality_attestation(*, validator_address: str, block_height: int, block_hash: str, network_id: str, signature: str) -> dict[str, Any]:
    payload = build_protocol_v1_finality_attestation_payload(validator_address=validator_address, block_height=block_height, block_hash=block_hash)
    network_id = normalize_network_id(network_id)
    if not isinstance(signature, str) or not signature.strip():
        raise ValueError("signature is required.")
    return {"attestation_version": payload["attestation_version"], "validator_address": payload["validator_address"],
            "block_height": payload["block_height"], "block_hash": payload["block_hash"], "network_id": network_id,
            "domain": PROTOCOL_V1_FINALITY_ATTESTATION_DOMAIN, "signature_scheme": NATIVE_TRANSFER_SIGNATURE_SCHEME,
            "signature": signature.strip(), "message": build_protocol_v1_finality_attestation_message(
                validator_address=payload["validator_address"], block_height=payload["block_height"], block_hash=payload["block_hash"], network_id=network_id)}
