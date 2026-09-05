"""Authoritative deterministic validation for Protocol v1 native ZOID transactions.

The service deliberately separates identity checks (which need no chain state)
from admission and block-sequence checks.  Callers receive a stable error code
instead of deriving protocol semantics from Python or storage exception text.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from native_transfer import (
    NATIVE_TRANSACTION_INITIAL_NONCE,
    hash_transfer_signing_message,
    validate_transaction_shape,
    verify_transfer_signature,
)
from protocol_v1 import PROTOCOL_VERSION
from protocol_v1_native_transfer import (
    PROTOCOL_V1_NATIVE_TRANSFER_VERSION,
    build_protocol_v1_native_transfer_message,
    looks_like_protocol_v1_native_transfer_message,
    resolve_protocol_v1_network_id,
)


class NativeTransactionValidationError(ValueError):
    """A deterministic native-transaction rejection.

    ``code`` is the protocol/application taxonomy.  The message is kept
    user-readable for existing API adapters and logs.
    """

    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


@dataclass(frozen=True)
class NativeTransactionValidationService:
    """Pure validation policy plus small stateful composition helpers."""

    @staticmethod
    def code_for_error(error: Exception | str) -> str:
        if isinstance(error, NativeTransactionValidationError):
            return error.code
        message = str(error).lower()
        if "tx_id" in message and ("does not match" in message or "hex" in message):
            return "invalid_tx_id"
        if "signed_message_hash" in message:
            return "invalid_signed_message_hash"
        if "recovered signer" in message or "does not match from_address" in message:
            return "sender_signature_mismatch"
        if "signature" in message:
            return "invalid_signature"
        if "network" in message:
            return "wrong_network"
        if "version" in message:
            return "unsupported_version"
        if "fee" in message:
            return "invalid_fee"
        if "nonce" in message:
            return "invalid_nonce"
        if "balance" in message or "overdraw" in message:
            return "insufficient_balance"
        return "malformed_transaction"

    def validate_identity(self, transaction: dict[str, Any], *, network_name: str) -> dict[str, Any]:
        """Validate canonical content, identity, Protocol v1 domain, and signer."""
        try:
            payload = dict(transaction or {})
            if payload.get("timestamp") not in (None, ""):
                payload.setdefault("created_at", payload["timestamp"])
                payload.setdefault("updated_at", payload["timestamp"])
            validated = validate_transaction_shape(payload, network_name=network_name)
            if validated.transaction_version != PROTOCOL_V1_NATIVE_TRANSFER_VERSION:
                raise NativeTransactionValidationError(
                    "unsupported_version",
                    "Protocol v1 native transaction version is required for mempool admission.",
                )
            if validated.protocol_version != PROTOCOL_VERSION:
                raise NativeTransactionValidationError(
                    "unsupported_version",
                    "protocol_version is required for Protocol v1 native transfers.",
                )
            expected_network_id = resolve_protocol_v1_network_id(network_name=network_name)
            if validated.network_id != expected_network_id:
                raise NativeTransactionValidationError(
                    "wrong_network", "Transaction belongs to a different network."
                )
            if validated.signed_message_hash != hash_transfer_signing_message(validated.signed_message):
                raise NativeTransactionValidationError(
                    "invalid_signed_message_hash", "signed_message_hash does not match signed_message."
                )
            if not looks_like_protocol_v1_native_transfer_message(validated.signed_message):
                raise NativeTransactionValidationError(
                    "malformed_transaction", "signed_message must be a Protocol v1 native transfer payload."
                )
            expected_message = build_protocol_v1_native_transfer_message(
                from_address=validated.from_address, to_address=validated.to_address,
                amount=validated.amount, fee=validated.fee, nonce=validated.nonce,
                timestamp=validated.timestamp, memo=validated.memo,
                network_id=validated.network_id,
            )
            if validated.signed_message != expected_message:
                raise NativeTransactionValidationError(
                    "malformed_transaction",
                    "signed_message does not match the Protocol v1 native transfer payload.",
                )
            try:
                verify_transfer_signature(
                    validated.signed_message, validated.signature, validated.from_address
                )
            except ValueError as exc:
                code = "sender_signature_mismatch" if "does not match" in str(exc).lower() else "invalid_signature"
                raise NativeTransactionValidationError(code, str(exc)) from exc
            return validated.to_dict()
        except NativeTransactionValidationError:
            raise
        except ValueError as exc:
            raise NativeTransactionValidationError(self.code_for_error(exc), str(exc)) from exc

    def validate_admission_state(self, ledger, state, transaction: dict[str, Any], *, exclude_tx_id: str | None = None) -> dict[str, Any]:
        """Apply the strict pending nonce and spendable-balance policy."""
        validated = self.validate_identity(transaction, network_name=ledger.network_name)
        tx_id = validated["tx_id"]
        if tx_id in set(ledger.get_chain_native_transaction_ids(state)):
            raise NativeTransactionValidationError(
                "already_settled", "Transaction is already present in canonical settlement."
            )
        try:
            ledger.validate_transaction_nonce(state, validated)
        except ValueError as exc:
            message = str(exc)
            if "lower" in message.lower():
                code = "stale_nonce"
            elif "ahead" in message.lower():
                code = "future_nonce"
            elif "already used or reserved" in message.lower():
                code = "active_nonce_conflict"
            else:
                code = "invalid_nonce"
            raise NativeTransactionValidationError(code, message) from exc
        try:
            ledger.validate_transaction_balance_sufficiency(
                state, validated, exclude_tx_id=exclude_tx_id
            )
        except ValueError as exc:
            raise NativeTransactionValidationError(self.code_for_error(exc), str(exc)) from exc
        return validated

    def validate_block_step(self, transaction: dict[str, Any], *, network_name: str, balances, next_nonces, canonical_tx_ids, seen_block_tx_ids, seen_nonces, normalize_wallet, coerce_nonce, normalize_decimal):
        """Validate and apply one transaction to deterministic block-local state."""
        checked = self.validate_identity(transaction, network_name=network_name)
        tx_id = checked["tx_id"]
        if tx_id in canonical_tx_ids:
            raise NativeTransactionValidationError("already_settled", "Transaction is already present in canonical settlement.")
        if tx_id in seen_block_tx_ids:
            raise NativeTransactionValidationError("duplicate_transaction_id", "Block contains the same native transaction more than once.")
        sender, recipient = normalize_wallet(checked["from_address"]), normalize_wallet(checked["to_address"])
        nonce = coerce_nonce(checked["nonce"])
        key = (sender, nonce)
        if key in seen_nonces:
            raise NativeTransactionValidationError("active_nonce_conflict", "Block contains multiple native transactions with the same sender nonce.")
        expected = next_nonces.get(sender, NATIVE_TRANSACTION_INITIAL_NONCE)
        if nonce < expected:
            raise NativeTransactionValidationError("stale_nonce", "Block native transaction nonce is lower than the next expected chain nonce.")
        if nonce > expected:
            raise NativeTransactionValidationError("future_nonce", "Block native transaction nonce creates a gap against the prior chain state.")
        amount, fee = Decimal(str(checked["amount"])), Decimal(str(checked["fee"]))
        if fee != Decimal("0"):
            raise NativeTransactionValidationError("invalid_fee", "Block native transaction fee must be zero under the current fee policy.")
        balance = balances.get(sender, Decimal("0"))
        if balance < amount + fee:
            raise NativeTransactionValidationError("insufficient_balance", "Block native transaction would overdraw the sender when applied in block order.")
        balances[sender] = balance - amount - fee
        balances[recipient] = balances.get(recipient, Decimal("0")) + amount
        next_nonces[sender] = expected + 1
        seen_block_tx_ids.add(tx_id)
        seen_nonces.add(key)
        return checked
