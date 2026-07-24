from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any

from eth_account import Account
from eth_account.messages import encode_defunct
from validators import is_valid_network_name


NATIVE_TRANSFER_ACTION = "transfer_zoid"
NATIVE_TRANSACTION_TYPE = "native_transfer"
NATIVE_TRANSFER_SIGNATURE_SCHEME = "personal_sign"
NATIVE_TRANSACTION_INITIAL_NONCE = 1
NATIVE_TRANSACTION_NONCE_POLICY = "strict_sequential"
NATIVE_TRANSFER_STATUSES = (
    "draft",
    "signed",
    "signed_pending",
    "pending",
    "rejected",
    "included",
    "failed",
)
NATIVE_TRANSACTION_STATUSES = (
    "signed_pending",
    "validated_pending",
    "mempool",
    "included",
    "settled",
    "rejected",
    "failed",
    "expired",
)
NATIVE_ZOID_MAX_DECIMAL_PLACES = 6
MAX_TRANSFER_MEMO_LENGTH = 280
TX_ID_HEX_LENGTH = 64


def normalize_wallet_address(wallet_address: str) -> str | None:
    candidate = str(wallet_address or "").strip()
    if len(candidate) != 42 or not candidate.startswith("0x"):
        return None
    hex_part = candidate[2:]
    if not hex_part or any(ch not in "0123456789abcdefABCDEF" for ch in hex_part):
        return None
    return f"0x{hex_part.lower()}"


def hash_wallet_message(message: str) -> str:
    return hashlib.sha256(str(message or "").encode("utf-8")).hexdigest()


def recover_signed_wallet_address(message: str, signature: str) -> str:
    try:
        recovered = Account.recover_message(
            encode_defunct(text=message),
            signature=signature,
        )
    except Exception as exc:
        raise ValueError("Malformed signature or unsupported signature payload.") from exc

    recovered_normalized = normalize_wallet_address(recovered)
    if not recovered_normalized:
        raise ValueError("Recovered signature address is invalid.")
    return recovered_normalized


@dataclass(frozen=True)
class NativeTransferMessage:
    action: str
    network: str
    from_address: str
    to_address: str
    amount: str
    nonce: str
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


@dataclass(frozen=True)
class NativeTransaction:
    tx_id: str
    transaction_type: str
    network: str
    from_address: str
    to_address: str
    amount: str
    fee: str
    nonce: str
    timestamp: str
    signature: str
    signature_scheme: str
    signed_message: str
    signed_message_hash: str
    status: str
    created_at: str
    updated_at: str
    memo: str | None = None
    included_block_hash: str | None = None
    included_block_height: int | None = None
    settled_at: str | None = None
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "tx_id": self.tx_id,
            "transaction_type": self.transaction_type,
            "network": self.network,
            "from_address": self.from_address,
            "to_address": self.to_address,
            "amount": self.amount,
            "fee": self.fee,
            "nonce": self.nonce,
            "timestamp": self.timestamp,
            "signature": self.signature,
            "signature_scheme": self.signature_scheme,
            "signed_message": self.signed_message,
            "signed_message_hash": self.signed_message_hash,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "memo": self.memo,
            "included_block_hash": self.included_block_hash,
            "included_block_height": self.included_block_height,
            "settled_at": self.settled_at,
            "rejection_reason": self.rejection_reason,
        }
        return payload


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


def normalize_tx_id(value: Any) -> str | None:
    candidate = str(value or "").strip().lower()
    if len(candidate) != TX_ID_HEX_LENGTH:
        return None
    if any(ch not in "0123456789abcdef" for ch in candidate):
        return None
    return candidate


def parse_transfer_nonce(value: Any) -> str:
    if isinstance(value, bool):
        raise ValueError("nonce is required and must be a string or integer.")
    if isinstance(value, int):
        if value < NATIVE_TRANSACTION_INITIAL_NONCE:
            raise ValueError(f"nonce must be at least {NATIVE_TRANSACTION_INITIAL_NONCE}.")
        return str(value)

    candidate = str(value or "").strip()
    if not candidate:
        raise ValueError("nonce is required.")
    if not candidate.isdigit():
        raise ValueError("nonce must be a positive integer string.")
    if int(candidate) < NATIVE_TRANSACTION_INITIAL_NONCE:
        raise ValueError(f"nonce must be at least {NATIVE_TRANSACTION_INITIAL_NONCE}.")
    return candidate


def _normalize_transfer_status(status: str | None) -> str:
    candidate = str(status or "draft").strip().lower()
    if candidate not in NATIVE_TRANSFER_STATUSES:
        raise ValueError(
            f"Transfer status must be one of: {', '.join(NATIVE_TRANSFER_STATUSES)}."
        )
    return candidate


def _normalize_transaction_status(status: str | None) -> str:
    candidate = str(status or "signed_pending").strip().lower()
    if candidate not in NATIVE_TRANSACTION_STATUSES:
        raise ValueError(
            f"Transaction status must be one of: {', '.join(NATIVE_TRANSACTION_STATUSES)}."
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


def _canonical_transaction_fields(payload: dict[str, Any]) -> dict[str, Any]:
    network = str(payload.get("network") or "").strip()
    if not network:
        raise ValueError("network is required.")
    if not is_valid_network_name(network):
        raise ValueError("network is invalid.")

    from_address = normalize_wallet_address(payload.get("from_address"))
    if not from_address:
        raise ValueError("from_address must be a valid Ethereum-style 0x address.")

    to_address = normalize_wallet_address(payload.get("to_address"))
    if not to_address:
        raise ValueError("to_address must be a valid Ethereum-style 0x address.")
    if from_address == to_address:
        raise ValueError("from_address and to_address must be different.")

    transaction_type = str(payload.get("transaction_type") or "").strip().lower()
    if transaction_type != NATIVE_TRANSACTION_TYPE:
        raise ValueError(f"transaction_type must be exactly {NATIVE_TRANSACTION_TYPE}.")

    signature = str(payload.get("signature") or "").strip()
    if not signature:
        raise ValueError("signature is required.")

    signature_scheme = str(payload.get("signature_scheme") or "").strip()
    if signature_scheme != NATIVE_TRANSFER_SIGNATURE_SCHEME:
        raise ValueError(f"signature_scheme must be {NATIVE_TRANSFER_SIGNATURE_SCHEME}.")

    signed_message = str(payload.get("signed_message") or "").strip()
    if not signed_message:
        raise ValueError("signed_message is required.")

    signed_message_hash = str(payload.get("signed_message_hash") or "").strip().lower()
    if not signed_message_hash:
        raise ValueError("signed_message_hash is required.")
    if normalize_tx_id(signed_message_hash) is None:
        raise ValueError("signed_message_hash must be lowercase SHA-256 hex.")

    return {
        "transaction_type": transaction_type,
        "network": network,
        "from_address": from_address,
        "to_address": to_address,
        "amount": parse_native_zoid_amount(payload.get("amount"), allow_zero=False),
        "fee": parse_native_zoid_amount(payload.get("fee", "0"), allow_zero=True),
        "nonce": parse_transfer_nonce(payload.get("nonce")),
        "memo": _normalize_transfer_memo(payload.get("memo")),
        "timestamp": parse_transfer_timestamp(payload.get("timestamp")),
        "signature": signature,
        "signature_scheme": signature_scheme,
        "signed_message": signed_message,
        "signed_message_hash": signed_message_hash,
    }


def canonicalize_transaction_payload(transaction: dict[str, Any] | NativeTransaction) -> str:
    payload = transaction.to_dict() if isinstance(transaction, NativeTransaction) else dict(transaction or {})
    canonical_fields = _canonical_transaction_fields(payload)
    return json.dumps(
        canonical_fields,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def compute_transaction_id(transaction_payload: dict[str, Any] | NativeTransaction) -> str:
    canonical = canonicalize_transaction_payload(transaction_payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_transaction_shape(
    transaction: dict[str, Any] | NativeTransaction,
    *,
    network_name: str,
) -> NativeTransaction:
    payload = transaction.to_dict() if isinstance(transaction, NativeTransaction) else dict(transaction or {})
    canonical_fields = _canonical_transaction_fields(payload)

    if canonical_fields["network"] != network_name:
        raise ValueError("network does not match the active ZoidbergChain network.")

    status = _normalize_transaction_status(payload.get("status"))
    tx_id = str(payload.get("tx_id") or "").strip().lower()
    if tx_id:
        normalized_tx_id = normalize_tx_id(tx_id)
        if normalized_tx_id is None:
            raise ValueError("tx_id must be lowercase SHA-256 hex.")
        expected_tx_id = compute_transaction_id(canonical_fields)
        if normalized_tx_id != expected_tx_id:
            raise ValueError("tx_id does not match the canonical transaction payload.")
    else:
        normalized_tx_id = compute_transaction_id(canonical_fields)

    created_at = parse_transfer_timestamp(payload.get("created_at"))
    updated_at = parse_transfer_timestamp(payload.get("updated_at"))

    included_block_hash = str(payload.get("included_block_hash") or "").strip() or None
    included_block_height_value = payload.get("included_block_height")
    included_block_height = None
    if included_block_height_value not in (None, ""):
        try:
            included_block_height = int(included_block_height_value)
        except (TypeError, ValueError) as exc:
            raise ValueError("included_block_height must be an integer when provided.") from exc
        if included_block_height < 0:
            raise ValueError("included_block_height cannot be negative.")

    settled_at_value = payload.get("settled_at")
    settled_at = parse_transfer_timestamp(settled_at_value) if settled_at_value not in (None, "") else None
    rejection_reason = str(payload.get("rejection_reason") or "").strip() or None

    return NativeTransaction(
        tx_id=normalized_tx_id,
        transaction_type=canonical_fields["transaction_type"],
        network=canonical_fields["network"],
        from_address=canonical_fields["from_address"],
        to_address=canonical_fields["to_address"],
        amount=canonical_fields["amount"],
        fee=canonical_fields["fee"],
        nonce=canonical_fields["nonce"],
        memo=canonical_fields["memo"],
        timestamp=canonical_fields["timestamp"],
        signature=canonical_fields["signature"],
        signature_scheme=canonical_fields["signature_scheme"],
        signed_message=canonical_fields["signed_message"],
        signed_message_hash=canonical_fields["signed_message_hash"],
        status=status,
        created_at=created_at,
        updated_at=updated_at,
        included_block_hash=included_block_hash,
        included_block_height=included_block_height,
        settled_at=settled_at,
        rejection_reason=rejection_reason,
    )


def build_native_transaction(
    *,
    network: str,
    from_address: str,
    to_address: str,
    amount: str,
    fee: str,
    nonce: str,
    memo: str | None,
    timestamp: str,
    signature: str,
    signature_scheme: str,
    signed_message: str,
    signed_message_hash: str,
    status: str = "signed_pending",
    created_at: str | None = None,
    updated_at: str | None = None,
    included_block_hash: str | None = None,
    included_block_height: int | None = None,
    settled_at: str | None = None,
    rejection_reason: str | None = None,
) -> NativeTransaction:
    created_timestamp = parse_transfer_timestamp(created_at or datetime.now(timezone.utc).isoformat())
    updated_timestamp = parse_transfer_timestamp(updated_at or created_timestamp)
    transaction_payload = {
        "transaction_type": NATIVE_TRANSACTION_TYPE,
        "network": network,
        "from_address": from_address,
        "to_address": to_address,
        "amount": amount,
        "fee": fee,
        "nonce": nonce,
        "memo": memo,
        "timestamp": timestamp,
        "signature": signature,
        "signature_scheme": signature_scheme,
        "signed_message": signed_message,
        "signed_message_hash": signed_message_hash,
        "status": status,
        "created_at": created_timestamp,
        "updated_at": updated_timestamp,
        "included_block_hash": included_block_hash,
        "included_block_height": included_block_height,
        "settled_at": settled_at,
        "rejection_reason": rejection_reason,
    }
    transaction_payload["tx_id"] = compute_transaction_id(transaction_payload)
    return validate_transaction_shape(transaction_payload, network_name=str(network))


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

    nonce_value = parse_transfer_nonce(payload.get("nonce"))

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


def parse_transfer_signing_message(
    message: str,
    *,
    network_name: str,
) -> NativeTransferMessage:
    if not isinstance(message, str) or not message.strip():
        raise ValueError("message is required.")

    lines = message.splitlines()
    if len(lines) < 12 or lines[0].strip() != "ZoidbergChain Native Transfer":
        raise ValueError("message is not a valid ZoidbergChain native transfer signing message.")

    field_values: dict[str, str] = {}
    memo_value: str | None = None
    for line in lines:
        if line.startswith("Action: "):
            field_values["action"] = line[len("Action: "):]
        elif line.startswith("Network: "):
            field_values["network"] = line[len("Network: "):]
        elif line.startswith("From: "):
            field_values["from_address"] = line[len("From: "):]
        elif line.startswith("To: "):
            field_values["to_address"] = line[len("To: "):]
        elif line.startswith("Amount: "):
            field_values["amount"] = line[len("Amount: "):]
        elif line.startswith("Fee: "):
            field_values["fee"] = line[len("Fee: "):]
        elif line.startswith("Nonce: "):
            field_values["nonce"] = line[len("Nonce: "):]
        elif line.startswith("Timestamp: "):
            field_values["timestamp"] = line[len("Timestamp: "):]
        elif line.startswith("Memo: "):
            memo_value = line[len("Memo: "):]

    payload = {
        "action": field_values.get("action"),
        "network": field_values.get("network"),
        "from_address": field_values.get("from_address"),
        "to_address": field_values.get("to_address"),
        "amount": field_values.get("amount"),
        "nonce": field_values.get("nonce"),
        "fee": field_values.get("fee"),
        "timestamp": field_values.get("timestamp"),
        "memo": memo_value,
        "status": "draft",
    }
    return validate_native_transfer_message(payload, network_name=network_name)


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
