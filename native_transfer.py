from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from validators import is_valid_network_name
from wallet_auth import (
    hash_wallet_message,
    normalize_wallet_address,
    recover_signed_wallet_address,
)


NATIVE_TRANSFER_ACTION = "transfer_zoid"
NATIVE_TRANSFER_SIGNATURE_SCHEME = "personal_sign"
NATIVE_TRANSFER_STATUSES = (
    "draft",
    "signed",
    "pending",
    "rejected",
    "included",
    "failed",
)
NATIVE_ZOID_MAX_DECIMAL_PLACES = 6
MAX_TRANSFER_MEMO_LENGTH = 280


@dataclass(frozen=True)
class NativeTransferMessage:
    action: str
    network: str
    from_address: str
    to_address: str
    amount: str
    nonce: int
    fee: str
    timestamp: str
    memo: str | None = None
    signature: str | None = None
    signature_scheme: str | None = None
    message_hash: str | None = None
    status: str = "draft"

    def as_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "action": self.action,
            "network": self.network,
            "from_address": self.from_address,
            "to_address": self.to_address,
            "amount": self.amount,
            "nonce": self.nonce,
            "fee": self.fee,
            "timestamp": self.timestamp,
        }
        if self.memo:
            payload["memo"] = self.memo
        if self.signature:
            payload["signature"] = self.signature
        if self.signature_scheme:
            payload["signature_scheme"] = self.signature_scheme
        if self.message_hash:
            payload["message_hash"] = self.message_hash
        if self.status:
            payload["status"] = self.status
        return payload


@dataclass(frozen=True)
class NativeTransferVerificationResult:
    verified: bool
    expected_from_address: str
    recovered_from_address: str
    signature_scheme: str
    signed_message_hash: str
    message: str


def parse_native_zoid_amount(
    value: str | int | Decimal,
    *,
    allow_zero: bool = False,
    max_decimal_places: int = NATIVE_ZOID_MAX_DECIMAL_PLACES,
) -> str:
    if isinstance(value, bool):
        raise ValueError("Amount must be a decimal string or integer.")

    candidate = str(value or "").strip()
    if not candidate:
        raise ValueError("Amount is required.")
    if candidate.lower() in {"nan", "+nan", "-nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}:
        raise ValueError("Amount must be a finite decimal value.")
    if "e" in candidate.lower():
        raise ValueError("Scientific notation is not supported for ZOID amounts.")

    try:
        decimal_value = Decimal(candidate)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Amount must be a valid decimal value.") from exc

    if decimal_value.is_nan() or decimal_value.is_infinite():
        raise ValueError("Amount must be a finite decimal value.")

    if decimal_value < 0:
        raise ValueError("Amount cannot be negative.")
    if not allow_zero and decimal_value == 0:
        raise ValueError("Amount must be greater than zero.")

    exponent = decimal_value.as_tuple().exponent
    decimal_places = -exponent if exponent < 0 else 0
    if decimal_places > max_decimal_places:
        raise ValueError(f"Amount exceeds the current {max_decimal_places}-decimal precision limit.")

    normalized = format(decimal_value.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    if normalized in {"", "-0"}:
        normalized = "0"
    return normalized


def parse_transfer_timestamp(value: str) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        raise ValueError("timestamp is required.")

    normalized_candidate = candidate.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized_candidate)
    except ValueError as exc:
        raise ValueError("timestamp must be a valid ISO 8601 value.") from exc

    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone offset.")

    return parsed.astimezone(timezone.utc).isoformat()


def _normalize_transfer_status(status: str | None) -> str:
    candidate = str(status or "draft").strip().lower()
    if candidate not in NATIVE_TRANSFER_STATUSES:
        raise ValueError(
            f"Transfer status must be one of: {', '.join(NATIVE_TRANSFER_STATUSES)}."
        )
    return candidate


def _normalize_transfer_memo(memo: str | None) -> str | None:
    if memo is None:
        return None
    candidate = str(memo).strip()
    if not candidate:
        return None
    if len(candidate) > MAX_TRANSFER_MEMO_LENGTH:
        raise ValueError(f"memo exceeds the {MAX_TRANSFER_MEMO_LENGTH}-character limit.")
    return candidate


def validate_native_transfer_message(
    payload: dict[str, Any],
    *,
    network_name: str,
) -> NativeTransferMessage:
    if not isinstance(payload, dict):
        raise ValueError("Transfer payload must be an object.")

    action = str(payload.get("action") or "").strip()
    if action != NATIVE_TRANSFER_ACTION:
        raise ValueError(f"action must be exactly {NATIVE_TRANSFER_ACTION}.")

    network = str(payload.get("network") or "").strip()
    if not network:
        raise ValueError("network is required.")
    if not is_valid_network_name(network):
        raise ValueError("network is invalid.")
    if network != network_name:
        raise ValueError("network does not match the active ZoidbergChain network.")

    from_address = normalize_wallet_address(payload.get("from_address"))
    if not from_address:
        raise ValueError("from_address must be a valid Ethereum-style 0x address.")

    to_address = normalize_wallet_address(payload.get("to_address"))
    if not to_address:
        raise ValueError("to_address must be a valid Ethereum-style 0x address.")
    if from_address == to_address:
        raise ValueError("from_address and to_address must be different.")

    amount = parse_native_zoid_amount(payload.get("amount"), allow_zero=False)
    fee = parse_native_zoid_amount(payload.get("fee", "0"), allow_zero=True)

    nonce_value = payload.get("nonce")
    if isinstance(nonce_value, bool) or not isinstance(nonce_value, int):
        raise ValueError("nonce is required and must be an integer.")
    if nonce_value < 0:
        raise ValueError("nonce cannot be negative.")

    timestamp = parse_transfer_timestamp(payload.get("timestamp"))
    memo = _normalize_transfer_memo(payload.get("memo"))
    signature = str(payload.get("signature") or "").strip() or None
    signature_scheme = str(payload.get("signature_scheme") or "").strip() or None
    message_hash = str(payload.get("message_hash") or "").strip() or None
    status = _normalize_transfer_status(payload.get("status"))

    if signature_scheme and signature_scheme != NATIVE_TRANSFER_SIGNATURE_SCHEME:
        raise ValueError(
            f"signature_scheme must be {NATIVE_TRANSFER_SIGNATURE_SCHEME} when provided."
        )

    return NativeTransferMessage(
        action=action,
        network=network,
        from_address=from_address,
        to_address=to_address,
        amount=amount,
        nonce=nonce_value,
        fee=fee,
        timestamp=timestamp,
        memo=memo,
        signature=signature,
        signature_scheme=signature_scheme,
        message_hash=message_hash,
        status=status,
    )


def build_transfer_signing_message(transfer_message: NativeTransferMessage) -> str:
    lines = [
        "ZoidbergChain Native Transfer",
        "",
        f"Action: {transfer_message.action}",
        f"Network: {transfer_message.network}",
        f"From: {transfer_message.from_address}",
        f"To: {transfer_message.to_address}",
        f"Amount: {transfer_message.amount}",
        f"Fee: {transfer_message.fee}",
        f"Nonce: {transfer_message.nonce}",
        f"Timestamp: {transfer_message.timestamp}",
    ]
    if transfer_message.memo:
        lines.append(f"Memo: {transfer_message.memo}")
    lines.extend(
        [
            "",
            "This authorizes a native ZOID transfer on ZoidbergChain.",
            "This is not an Ethereum/ERC-20 transfer.",
        ]
    )
    return "\n".join(lines)


def hash_transfer_signing_message(message: str) -> str:
    return hash_wallet_message(message)


def verify_transfer_signature(
    message: str,
    signature: str,
    expected_from_address: str,
) -> NativeTransferVerificationResult:
    normalized_expected = normalize_wallet_address(expected_from_address)
    if not normalized_expected:
        raise ValueError("expected_from_address must be a valid Ethereum-style 0x address.")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("message is required.")
    if not isinstance(signature, str) or not signature.strip():
        raise ValueError("signature is required.")

    recovered_normalized = recover_signed_wallet_address(message, signature)
    if recovered_normalized != normalized_expected:
        raise ValueError("Transfer signature does not match the expected from_address.")

    return NativeTransferVerificationResult(
        verified=True,
        expected_from_address=normalized_expected,
        recovered_from_address=recovered_normalized,
        signature_scheme=NATIVE_TRANSFER_SIGNATURE_SCHEME,
        signed_message_hash=hash_transfer_signing_message(message),
        message="Transfer signature verified",
    )
