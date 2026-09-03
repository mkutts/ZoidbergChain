"""Deterministic native ZOID ledger and transfer-intent transitions."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from config import NETWORK_NAME
from native_transfer import (
    NATIVE_TRANSACTION_INITIAL_NONCE,
    NATIVE_TRANSACTION_NONCE_POLICY,
    build_native_transaction,
    parse_native_zoid_amount,
    parse_transfer_nonce,
    parse_transfer_signing_message,
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
from validators import is_valid_user_wallet_identity
from wallet_auth import hash_wallet_message, normalize_wallet_address


@dataclass
class NativeLedgerState:
    chain: list
    transfer_intents: list
    native_transactions: list


class NativeLedgerService:
    """Stateless operations over facade-owned native ledger collections."""

    @staticmethod
    def utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def normalize_wallet_identity(wallet_address):
        candidate = str(wallet_address or "").strip()
        normalized_wallet = normalize_wallet_address(candidate)
        if normalized_wallet:
            return normalized_wallet
        if candidate and is_valid_user_wallet_identity(candidate):
            return candidate
        return None

    @staticmethod
    def coerce_native_event_timestamp(value, *, now_iso=None) -> str:
        if isinstance(value, bool):
            return now_iso or NativeLedgerService.utc_now_iso()
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        return str(value or "").strip()

    @staticmethod
    def build_transfer_intent_record_from_transaction(transaction, *, transfer_id=None, signed_at=None, created_at=None, updated_at=None, id_factory=None, now_iso=None):
        payload = transaction.to_dict() if hasattr(transaction, "to_dict") else dict(transaction or {})
        current_time = now_iso or NativeLedgerService.utc_now_iso()
        record = {
            "transfer_id": str(transfer_id or (id_factory() if id_factory else os.urandom(16).hex())),
            "tx_id": payload.get("tx_id"), "from_address": payload.get("from_address"),
            "to_address": payload.get("to_address"), "amount": payload.get("amount"),
            "fee": payload.get("fee"), "memo": payload.get("memo"), "network": payload.get("network"),
            "transaction_version": payload.get("transaction_version"),
            "protocol_version": payload.get("protocol_version"), "network_id": payload.get("network_id"),
            "signature_scheme": payload.get("signature_scheme"), "signature": payload.get("signature"),
            "signed_message": payload.get("signed_message"), "signed_message_hash": payload.get("signed_message_hash"),
            "transfer_nonce": payload.get("nonce"),
            "signed_at": str(signed_at or payload.get("timestamp") or payload.get("created_at") or current_time),
            "status": payload.get("status"),
            "created_at": str(created_at or payload.get("created_at") or current_time),
        }
        if updated_at not in (None, ""):
            record["updated_at"] = str(updated_at)
        return record

    @staticmethod
    def native_mempool_eligible_statuses(): return {"signed_pending", "validated_pending", "mempool"}
    @staticmethod
    def native_ineligible_mempool_statuses(): return {"included", "settled", "rejected", "expired", "failed"}
    @staticmethod
    def native_finalized_statuses(): return {"included", "settled"}
    @staticmethod
    def native_block_candidate_statuses(): return {"validated_pending", "mempool"}
    @staticmethod
    def native_nonce_used_statuses(): return {"included", "settled"}
    @staticmethod
    def native_nonce_reserved_statuses(): return {"signed_pending", "validated_pending", "mempool"}
    @classmethod
    def native_nonce_unavailable_statuses(cls): return cls.native_nonce_used_statuses() | cls.native_nonce_reserved_statuses()
    @staticmethod
    def native_funds_reserved_statuses(): return {"signed_pending", "validated_pending", "mempool"}

    @staticmethod
    def native_mempool_sort_key(transaction):
        return (str(transaction.get("admitted_at") or transaction.get("updated_at") or transaction.get("created_at") or ""), str(transaction.get("from_address") or ""), int(parse_transfer_nonce(transaction.get("nonce"))), str(transaction.get("tx_id") or ""))

    @staticmethod
    def native_block_sort_key(transaction):
        return (str(transaction.get("from_address") or ""), int(parse_transfer_nonce(transaction.get("nonce"))), str(transaction.get("tx_id") or ""))

    @staticmethod
    def normalize_rejection_reason(reason: str) -> str:
        import re
        candidate = re.sub(r"[^a-z0-9]+", "_", str(reason or "").strip().lower()).strip("_")
        return candidate or "validation_failed"

    @staticmethod
    def normalize_decimal_value(value: Decimal) -> str:
        result = format(value.normalize(), "f")
        if "." in result:
            result = result.rstrip("0").rstrip(".")
        return result if result and result != "-0" else "0"

    @staticmethod
    def block_native_transactions(block):
        return list(block.get("native_transactions", []) or []) if isinstance(block, dict) else list(getattr(block, "native_transactions", []) or [])

    @staticmethod
    def serialize_native_transaction_for_block(transaction):
        payload = {field: transaction.get(field) for field in ("tx_id", "transaction_type", "network", "from_address", "to_address", "amount", "fee", "nonce", "memo", "timestamp", "signature", "signature_scheme", "signed_message", "signed_message_hash")}
        for field in ("transaction_version", "protocol_version", "network_id"):
            if transaction.get(field) is not None:
                payload[field] = transaction.get(field)
        return payload

    @staticmethod
    def compute_block_native_transactions_hash(transactions) -> str:
        canonical = json.dumps([dict(transaction) for transaction in transactions or []], sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def get_transfer_intent(self, state, storage, transfer_id):
        return storage.get_transfer_intent(transfer_id, state.transfer_intents)

    def get_native_transaction(self, state, storage, tx_id):
        return storage.get_native_transaction(tx_id, state.native_transactions)

    @staticmethod
    def get_transfer_intent_by_tx_id(state, tx_id):
        normalized = str(tx_id or "").strip()
        return next((record for record in state.transfer_intents if str(record.get("tx_id") or "").strip() == normalized), None)

    def get_transfer_intents_for_wallet(self, state, wallet_address):
        wallet = self.normalize_wallet_identity(wallet_address)
        if wallet is None: return []
        return [record for record in state.transfer_intents if self.normalize_wallet_identity(record.get("from_address")) == wallet or self.normalize_wallet_identity(record.get("to_address")) == wallet]

    def get_native_transactions_for_wallet(self, state, wallet_address):
        wallet = self.normalize_wallet_identity(wallet_address)
        if wallet is None: return []
        return [record for record in state.native_transactions if self.normalize_wallet_identity(record.get("from_address")) == wallet or self.normalize_wallet_identity(record.get("to_address")) == wallet]

    def find_native_transaction_index(self, state, tx_id):
        normalized = str(tx_id or "").strip().lower()
        return next((index for index, item in enumerate(state.native_transactions) if str(item.get("tx_id") or "").strip().lower() == normalized), None)

    def find_transfer_intent_index_by_tx_id(self, state, tx_id):
        normalized = str(tx_id or "").strip().lower()
        return next((index for index, item in enumerate(state.transfer_intents) if str(item.get("tx_id") or "").strip().lower() == normalized), None)

    def update_transfer_intent_status(self, state, tx_id, *, status, updated_at=None):
        index = self.find_transfer_intent_index_by_tx_id(state, tx_id)
        if index is None: return None
        record = dict(state.transfer_intents[index]); record["status"] = str(status).strip().lower()
        if updated_at: record["updated_at"] = updated_at
        state.transfer_intents[index] = record
        return record

    def replace_native_transaction(self, state, transaction):
        index = self.find_native_transaction_index(state, transaction.get("tx_id"))
        if index is None: raise ValueError("Transaction not found.")
        state.native_transactions[index] = dict(transaction)
        return state.native_transactions[index]

    def discard_native_transaction(self, state, tx_id):
        index = self.find_native_transaction_index(state, tx_id)
        if index is None: return False
        del state.native_transactions[index]
        intent_index = self.find_transfer_intent_index_by_tx_id(state, tx_id)
        if intent_index is not None: del state.transfer_intents[intent_index]
        return True

    def record_native_transaction(self, state, storage, transaction_payload, *, status="signed_pending", created_at=None, updated_at=None, now_iso=None):
        now_value = str(created_at or now_iso or self.utc_now_iso())
        candidate = dict(transaction_payload or {}); candidate.setdefault("created_at", now_value); candidate.setdefault("updated_at", str(updated_at or now_value))
        validated = validate_transaction_shape(candidate, network_name=NETWORK_NAME)
        existing = self.get_native_transaction(state, storage, validated.tx_id)
        if existing is not None: return dict(existing), True
        stored = validated.to_dict()
        stored.update({"status": str(status).strip().lower(), "created_at": now_value, "updated_at": str(updated_at or now_value), "admitted_at": None, "included_block_hash": None, "included_block_height": None, "settled_at": None, "rejection_reason": None})
        validate_transaction_shape(stored, network_name=NETWORK_NAME)
        state.native_transactions.append(stored)
        return dict(stored), False

    def update_native_transaction_status(self, state, storage, tx_id, *, status, rejection_reason=None, admitted_at=None, included_block_hash=None, included_block_height=None, settled_at=None, updated_at=None, now_iso=None):
        transaction = self.get_native_transaction(state, storage, tx_id)
        if transaction is None: raise ValueError(f"Transaction not found: {tx_id}")
        now_value = str(updated_at or now_iso or self.utc_now_iso()); updated = dict(transaction); updated["status"] = str(status).strip().lower(); updated["updated_at"] = now_value
        for field, value in (("admitted_at", admitted_at), ("included_block_hash", included_block_hash), ("included_block_height", included_block_height), ("settled_at", settled_at)):
            if value is not None: updated[field] = value
        if rejection_reason is not None: updated["rejection_reason"] = rejection_reason
        elif updated["status"] not in {"rejected", "expired"}: updated["rejection_reason"] = None
        try: stored = validate_transaction_shape(updated, network_name=NETWORK_NAME).to_dict()
        except ValueError:
            if updated["status"] not in {"rejected", "failed", "expired"}: raise
            stored = dict(updated)
        self.replace_native_transaction(state, stored)
        self.update_transfer_intent_status(state, stored["tx_id"], status=stored["status"], updated_at=now_value)
        return dict(stored)

    def validate_signed_native_transaction(self, state, storage, transaction_or_tx_id, *, allowed_statuses=None):
        if isinstance(transaction_or_tx_id, str):
            transaction = self.get_native_transaction(state, storage, transaction_or_tx_id)
            if transaction is None: raise ValueError(f"Transaction not found: {transaction_or_tx_id}")
        elif isinstance(transaction_or_tx_id, dict): transaction = dict(transaction_or_tx_id)
        else: raise ValueError("transaction must be a tx_id string or transaction object.")
        payload = dict(transaction)
        if payload.get("timestamp") not in (None, ""):
            payload.setdefault("created_at", payload["timestamp"]); payload.setdefault("updated_at", payload["timestamp"])
        validated = validate_transaction_shape(payload, network_name=NETWORK_NAME)
        if allowed_statuses is not None and validated.status not in allowed_statuses: raise ValueError(f"Transaction status {validated.status} is not eligible for this operation.")
        if validated.signed_message_hash != hash_wallet_message(validated.signed_message): raise ValueError("signed_message_hash does not match signed_message.")
        if validated.transaction_version == PROTOCOL_V1_NATIVE_TRANSFER_VERSION:
            if validated.protocol_version != PROTOCOL_VERSION: raise ValueError("protocol_version is required for Protocol v1 native transfers.")
            if validated.network_id is None: raise ValueError("network_id is required for Protocol v1 native transfers.")
            if validated.network_id != resolve_protocol_v1_network_id(network_name=NETWORK_NAME): raise ValueError("Transaction belongs to a different network.")
            expected = build_protocol_v1_native_transfer_message(from_address=validated.from_address, to_address=validated.to_address, amount=validated.amount, fee=validated.fee, nonce=validated.nonce, timestamp=validated.timestamp, memo=validated.memo, network_id=validated.network_id)
            if validated.signed_message != expected: raise ValueError("signed_message does not match the Protocol v1 native transfer payload.")
        else:
            if looks_like_protocol_v1_native_transfer_message(validated.signed_message): raise ValueError("transaction_version is required for Protocol v1 native transfer messages.")
            signed = parse_transfer_signing_message(validated.signed_message, network_name=NETWORK_NAME)
            expected = {key: getattr(validated, key) for key in ("from_address", "to_address", "amount", "fee", "nonce", "timestamp", "memo")}
            actual = {key: getattr(signed, key) for key in expected}
            if actual != expected: raise ValueError("signed_message does not match the canonical transaction payload.")
        verify_transfer_signature(validated.signed_message, validated.signature, validated.from_address)
        return validated.to_dict()

    def create_signed_transfer_intent(self, state, storage, *, from_address, to_address, amount, fee, memo, network, transaction_version=None, protocol_version=None, network_id=None, signature_scheme, signature, signed_message_hash, signed_message, transfer_nonce, transaction_timestamp=None, signed_at, status="signed_pending", created_at=None):
        transaction = build_native_transaction(network=str(network), transaction_version=transaction_version, protocol_version=protocol_version, network_id=network_id, from_address=from_address, to_address=to_address, amount=str(amount), fee=str(fee), nonce=str(transfer_nonce), memo=str(memo or "").strip() or None, timestamp=str(transaction_timestamp or signed_at), signature=str(signature), signature_scheme=str(signature_scheme), signed_message=str(signed_message), signed_message_hash=str(signed_message_hash), status=str(status), created_at=str(created_at) if created_at is not None else None)
        existing = self.reserve_transaction_nonce(state, transaction.to_dict())
        if existing is not None:
            intent = self.get_transfer_intent_by_tx_id(state, existing.get("tx_id"))
            if intent is None: raise ValueError("Transaction already recorded, but the local transfer intent record is missing.")
            duplicate = dict(intent); duplicate["duplicate"] = True; return duplicate
        record = self.build_transfer_intent_record_from_transaction(transaction, signed_at=signed_at, created_at=transaction.created_at)
        if not record["from_address"] or not record["to_address"]: raise ValueError("Transfer intent wallet addresses are invalid.")
        state.transfer_intents.append(record); state.native_transactions.append(transaction.to_dict())
        return record

    def native_transaction_sender_matches(self, transaction, wallet): return self.normalize_wallet_identity(transaction.get("from_address")) == wallet
    @staticmethod
    def coerce_native_nonce(nonce): return int(parse_transfer_nonce(nonce))

    def find_sender_nonce_transaction(self, state, wallet_address, nonce):
        wallet = self.normalize_wallet_identity(wallet_address)
        if wallet is None: return None
        nonce_value = self.coerce_native_nonce(nonce)
        return next((tx for tx in state.native_transactions if self.native_transaction_sender_matches(tx, wallet) and self.coerce_native_nonce(tx.get("nonce")) == nonce_value and str(tx.get("status") or "").strip().lower() in self.native_nonce_unavailable_statuses()), None)

    def get_used_nonces(self, state, wallet_address):
        wallet = self.normalize_wallet_identity(wallet_address)
        if wallet is None: return []
        return sorted({self.coerce_native_nonce(tx.get("nonce")) for tx in state.native_transactions if self.native_transaction_sender_matches(tx, wallet) and str(tx.get("status") or "").strip().lower() in self.native_nonce_used_statuses()})

    def get_reserved_nonces(self, state, wallet_address):
        wallet = self.normalize_wallet_identity(wallet_address)
        if wallet is None: return []
        return sorted({self.coerce_native_nonce(tx.get("nonce")) for tx in state.native_transactions if self.native_transaction_sender_matches(tx, wallet) and str(tx.get("status") or "").strip().lower() in self.native_nonce_reserved_statuses()})

    def get_next_nonce(self, state, wallet_address):
        wallet = self.normalize_wallet_identity(wallet_address)
        if wallet is None: return NATIVE_TRANSACTION_INITIAL_NONCE
        unavailable = set(self.get_used_nonces(state, wallet)) | set(self.get_reserved_nonces(state, wallet)); value = NATIVE_TRANSACTION_INITIAL_NONCE
        while value in unavailable: value += 1
        return value

    def is_nonce_available(self, state, wallet_address, nonce):
        wallet = self.normalize_wallet_identity(wallet_address)
        return wallet is not None and self.coerce_native_nonce(nonce) == self.get_next_nonce(state, wallet)

    def validate_transaction_nonce(self, state, transaction):
        wallet = self.normalize_wallet_identity(transaction.get("from_address"))
        if wallet is None: raise ValueError("Transaction from_address is invalid.")
        nonce = self.coerce_native_nonce(transaction.get("nonce")); tx_id = str(transaction.get("tx_id") or "").strip().lower(); existing = self.find_sender_nonce_transaction(state, wallet, nonce)
        if existing:
            if str(existing.get("tx_id") or "").strip().lower() == tx_id: return existing
            raise ValueError("Nonce already used or reserved. Refresh and try again.")
        expected = self.get_next_nonce(state, wallet)
        if nonce < expected: raise ValueError("Transaction nonce is lower than the next expected nonce. Refresh and try again.")
        if nonce > expected: raise ValueError("Transaction nonce is ahead of the next expected nonce. Strict sequential nonces are required.")
        return None

    def reserve_transaction_nonce(self, state, transaction): return self.validate_transaction_nonce(state, transaction)

    def get_nonce_state(self, state, wallet_address):
        wallet = self.normalize_wallet_identity(wallet_address)
        if wallet is None: raise ValueError("wallet_address must be a valid Ethereum-style 0x address.")
        return {"wallet_address": wallet, "next_nonce": self.get_next_nonce(state, wallet), "used_nonces": self.get_used_nonces(state, wallet), "reserved_nonces": self.get_reserved_nonces(state, wallet), "policy": NATIVE_TRANSACTION_NONCE_POLICY, "initial_nonce": NATIVE_TRANSACTION_INITIAL_NONCE}

    def get_reserved_native_transactions_for_wallet(self, state, wallet_address, *, exclude_tx_ids=None):
        wallet = self.normalize_wallet_identity(wallet_address)
        if wallet is None: return []
        excluded = {str(tx_id or "").strip().lower() for tx_id in (exclude_tx_ids or set()) if str(tx_id or "").strip()}
        return [tx for tx in state.native_transactions if str(tx.get("status") or "").strip().lower() in self.native_funds_reserved_statuses() and str(tx.get("tx_id") or "").strip().lower() not in excluded and (self.normalize_wallet_identity(tx.get("from_address")) == wallet or self.normalize_wallet_identity(tx.get("to_address")) == wallet)]

    def get_settled_native_transaction_records_for_wallet(self, state, wallet_address, *, chain=None):
        wallet = self.normalize_wallet_identity(wallet_address)
        if wallet is None: return []
        return [tx for block in (chain if chain is not None else state.chain) for tx in self.block_native_transactions(block) if self.normalize_wallet_identity(tx.get("from_address")) == wallet or self.normalize_wallet_identity(tx.get("to_address")) == wallet]

    def get_chain_native_transaction_ids(self, state, *, chain=None):
        return [tx_id for block in (chain if chain is not None else state.chain) for tx in self.block_native_transactions(block) if (tx_id := str(tx.get("tx_id") or "").strip().lower())]

    def get_settled_used_nonces(self, state, wallet_address, *, chain=None):
        wallet = self.normalize_wallet_identity(wallet_address)
        if wallet is None: return []
        return sorted({self.coerce_native_nonce(tx.get("nonce")) for tx in self.get_settled_native_transaction_records_for_wallet(state, wallet, chain=chain) if self.normalize_wallet_identity(tx.get("from_address")) == wallet})

    def get_next_settled_nonce(self, state, wallet_address, *, chain=None):
        wallet = self.normalize_wallet_identity(wallet_address)
        if wallet is None: return NATIVE_TRANSACTION_INITIAL_NONCE
        used = set(self.get_settled_used_nonces(state, wallet, chain=chain)); value = NATIVE_TRANSACTION_INITIAL_NONCE
        while value in used: value += 1
        return value

    def get_next_chain_nonce(self, state, wallet_address, chain_before_block=None): return self.get_next_settled_nonce(state, wallet_address, chain=chain_before_block)

    def get_final_native_balance_amount(self, state, wallet_address, *, chain=None):
        wallet = self.normalize_wallet_identity(wallet_address)
        if wallet is None: return Decimal("0")
        balance = Decimal("0")
        for block in (chain if chain is not None else state.chain):
            transactions = block.get("transactions", []) if isinstance(block, dict) else block.transactions
            for tx in transactions:
                sender_value = tx.get("sender") if isinstance(tx, dict) else tx.sender; recipient_value = tx.get("recipient") if isinstance(tx, dict) else tx.recipient
                sender = self.normalize_wallet_identity(sender_value) or sender_value; recipient = self.normalize_wallet_identity(recipient_value) or recipient_value
                amount = Decimal(str(tx.get("amount") if isinstance(tx, dict) else tx.amount)); tip = Decimal(str(tx.get("tip", 0) if isinstance(tx, dict) else tx.tip))
                if sender == wallet: balance -= amount + tip
                if recipient == wallet: balance += amount + tip
            for tx in self.block_native_transactions(block):
                sender = self.normalize_wallet_identity(tx.get("from_address")); recipient = self.normalize_wallet_identity(tx.get("to_address")); amount = Decimal(str(tx.get("amount") or "0")); fee = Decimal(str(tx.get("fee") or "0"))
                if sender == wallet: balance -= amount + fee
                if recipient == wallet: balance += amount
        return balance

    def get_pending_outgoing_balance_amount(self, state, wallet_address, *, exclude_tx_ids=None):
        wallet = self.normalize_wallet_identity(wallet_address); total = Decimal("0")
        if wallet is None: return total
        for tx in self.get_reserved_native_transactions_for_wallet(state, wallet, exclude_tx_ids=exclude_tx_ids):
            if self.normalize_wallet_identity(tx.get("from_address")) == wallet: total += Decimal(str(tx.get("amount") or "0")) + Decimal(str(tx.get("fee") or "0"))
        return total

    def get_pending_incoming_balance_amount(self, state, wallet_address, *, exclude_tx_ids=None):
        wallet = self.normalize_wallet_identity(wallet_address); total = Decimal("0")
        if wallet is None: return total
        for tx in self.get_reserved_native_transactions_for_wallet(state, wallet, exclude_tx_ids=exclude_tx_ids):
            if self.normalize_wallet_identity(tx.get("to_address")) == wallet: total += Decimal(str(tx.get("amount") or "0"))
        return total

    def get_available_native_balance_amount(self, state, wallet_address, *, exclude_tx_ids=None): return self.get_final_native_balance_amount(state, wallet_address) - self.get_pending_outgoing_balance_amount(state, wallet_address, exclude_tx_ids=exclude_tx_ids)

    def get_native_balance_snapshot(self, state, wallet_address, *, exclude_tx_ids=None):
        final = self.get_final_native_balance_amount(state, wallet_address); outgoing = self.get_pending_outgoing_balance_amount(state, wallet_address, exclude_tx_ids=exclude_tx_ids); incoming = self.get_pending_incoming_balance_amount(state, wallet_address, exclude_tx_ids=exclude_tx_ids)
        return {"final_balance": self.normalize_decimal_value(final), "pending_outgoing": self.normalize_decimal_value(outgoing), "pending_incoming": self.normalize_decimal_value(incoming), "available_balance": self.normalize_decimal_value(final - outgoing), "native_balance": self.normalize_decimal_value(final)}

    def validate_transaction_balance_sufficiency(self, state, transaction, *, exclude_tx_id=None):
        wallet = self.normalize_wallet_identity(transaction.get("from_address"))
        if wallet is None: raise ValueError("Transaction from_address is invalid.")
        fee = Decimal(parse_native_zoid_amount(transaction.get("fee") or "0", allow_zero=True))
        if fee != Decimal("0"): raise ValueError("Nonzero fees are not enabled yet.")
        amount = Decimal(parse_native_zoid_amount(transaction.get("amount") or "0", allow_zero=False)); excluded = {exclude_tx_id} if exclude_tx_id else None; available = self.get_available_native_balance_amount(state, wallet, exclude_tx_ids=excluded)
        if amount + fee > available:
            snapshot = self.get_native_balance_snapshot(state, wallet, exclude_tx_ids=excluded)
            raise ValueError(f"Insufficient available balance. Final balance: {snapshot['final_balance']} ZOID, pending outgoing: {snapshot['pending_outgoing']} ZOID, available: {snapshot['available_balance']} ZOID.")

    def calculate_balances_from_chain(self, state, chain_to_dicts, *, chain=None, error_type=ValueError):
        blocks = chain_to_dicts(chain if chain is not None else state.chain); balances, seen, next_nonces, rewarded = {}, set(), {}, set()
        def balance_for(wallet): return balances.get(wallet, Decimal("0")) if wallet is not None else Decimal("0")
        for block in blocks:
            submission_id = block.get("submission_id")
            if block.get("reward_type") == "meme_mining_reward" and submission_id:
                if submission_id in rewarded: raise error_type("duplicate_reward", "Chain contains duplicate meme reward settlement for the same submission.", details={"submission_id": submission_id})
                rewarded.add(submission_id)
            for tx in list(block.get("transactions", []) or []):
                sender_value = tx.get("sender") if isinstance(tx, dict) else tx.sender; recipient_value = tx.get("recipient") if isinstance(tx, dict) else tx.recipient
                sender = self.normalize_wallet_identity(sender_value) or sender_value; recipient = self.normalize_wallet_identity(recipient_value) or recipient_value; total = Decimal(str(tx.get("amount") if isinstance(tx, dict) else tx.amount)) + Decimal(str(tx.get("tip", 0) if isinstance(tx, dict) else tx.tip))
                if sender not in {None, "", "GENESIS", "REWARD_POOL"}: balances[sender] = balance_for(sender) - total
                if recipient: balances[recipient] = balance_for(recipient) + total
            for tx in self.block_native_transactions(block):
                validated = self.validate_signed_native_transaction(state, None, tx); tx_id = str(validated.get("tx_id") or "").strip().lower()
                if tx_id in seen: raise error_type("duplicate_transaction_id", "Chain contains the same native transaction more than once.", details={"tx_id": tx_id})
                sender = self.normalize_wallet_identity(validated.get("from_address")); recipient = self.normalize_wallet_identity(validated.get("to_address"))
                if sender is None or recipient is None: raise error_type("malformed_transaction", "Chain contains a native transaction with an invalid sender or recipient.", details={"tx_id": tx_id})
                nonce = self.coerce_native_nonce(validated.get("nonce")); expected = next_nonces.get(sender, NATIVE_TRANSACTION_INITIAL_NONCE)
                if nonce < expected: raise error_type("duplicate_nonce" if nonce == expected - 1 else "nonce_too_low", "Chain contains a native transaction with a nonce lower than the next expected chain nonce.", details={"tx_id": tx_id, "from_address": sender, "expected_nonce": expected, "received_nonce": nonce})
                if nonce > expected: raise error_type("nonce_gap", "Chain contains a native transaction with a nonce gap.", details={"tx_id": tx_id, "from_address": sender, "expected_nonce": expected, "received_nonce": nonce})
                fee = Decimal(str(validated.get("fee") or "0"))
                if fee != Decimal("0"): raise error_type("invalid_fee", "Chain contains a native transaction with a nonzero fee.", details={"tx_id": tx_id, "fee": str(validated.get("fee") or "0")})
                amount = Decimal(str(validated.get("amount") or "0")); total = amount + fee
                if balance_for(sender) < total: raise error_type("insufficient_balance", "Chain contains a native transaction that would overdraw the sender.", details={"tx_id": tx_id, "from_address": sender, "available_balance": self.normalize_decimal_value(balance_for(sender)), "required_total": self.normalize_decimal_value(total)})
                balances[sender] = balance_for(sender) - total; balances[recipient] = balance_for(recipient) + amount; next_nonces[sender] = expected + 1; seen.add(tx_id)
        return {"balances": balances, "seen_tx_ids": seen, "next_nonces": next_nonces, "rewarded_submissions": rewarded}

    def settle_block_native_transactions(self, state, storage, block, *, now_iso=None):
        transactions = self.block_native_transactions(block)
        if not transactions: return []
        hash_value = block.get("hash") if isinstance(block, dict) else getattr(block, "hash", None); height = block.get("index") if isinstance(block, dict) else getattr(block, "index", None)
        minted = block.get("minted_at") if isinstance(block, dict) else getattr(block, "minted_at", None); timestamp = block.get("timestamp") if isinstance(block, dict) else getattr(block, "timestamp", None)
        settled_at = self.coerce_native_event_timestamp(minted, now_iso=now_iso) or self.coerce_native_event_timestamp(timestamp, now_iso=now_iso) or now_iso or self.utc_now_iso(); ids = []
        for tx in transactions:
            stored, _ = self.record_native_transaction(state, storage, tx, status="validated_pending", now_iso=now_iso)
            settled = self.update_native_transaction_status(state, storage, stored["tx_id"], status="settled", included_block_hash=hash_value, included_block_height=height, settled_at=settled_at, updated_at=settled_at, now_iso=now_iso); ids.append(settled["tx_id"])
        return ids

    def reconcile_native_transactions_with_chain(self, state, storage, chain_to_dicts, *, chain=None, now_iso=None):
        accepted = chain_to_dicts(chain if chain is not None else state.chain); hashes = {str(block.get("hash") or "").strip() for block in accepted if str(block.get("hash") or "").strip()}
        for index, tx in enumerate(list(state.native_transactions)):
            if str(tx.get("status") or "").strip().lower() != "settled" or (str(tx.get("included_block_hash") or "").strip() in hashes): continue
            downgraded = dict(tx); downgraded.update({"status": "validated_pending", "included_block_hash": None, "included_block_height": None, "settled_at": None, "updated_at": now_iso or self.utc_now_iso()})
            validated = validate_transaction_shape(downgraded, network_name=NETWORK_NAME); state.native_transactions[index] = validated.to_dict(); self.update_transfer_intent_status(state, validated.tx_id, status=validated.status, updated_at=validated.updated_at)
        ids = []
        for block in accepted: ids.extend(self.settle_block_native_transactions(state, storage, block, now_iso=now_iso))
        return ids

    def restore_native_transaction_state(self, raw_transactions, raw_transfer_intents):
        state = NativeLedgerState([], [], [])
        transactions, intents, seen_ids, seen_nonces, transfer_ids, transfer_tx_ids = [], [], set(), {}, set(), set(); changed = False; removed = 0
        for transaction in list(raw_transactions or []):
            if not isinstance(transaction, dict): changed = True; removed += 1; continue
            try: validated = self.validate_signed_native_transaction(state, None, transaction)
            except ValueError: changed = True; removed += 1; continue
            tx_id = str(validated.get("tx_id") or "").strip().lower()
            if tx_id in seen_ids: changed = True; removed += 1; continue
            status = str(validated.get("status") or "").strip().lower()
            if status in self.native_nonce_unavailable_statuses():
                key = (self.normalize_wallet_identity(validated.get("from_address")), self.coerce_native_nonce(validated.get("nonce")))
                if key in seen_nonces and seen_nonces[key] != tx_id: changed = True; removed += 1; continue
                seen_nonces[key] = tx_id
            if dict(transaction) != validated: changed = True
            transactions.append(validated); seen_ids.add(tx_id)
        by_id = {str(tx.get("tx_id") or "").strip().lower(): dict(tx) for tx in transactions}
        for intent in list(raw_transfer_intents or []):
            if not isinstance(intent, dict): changed = True; removed += 1; continue
            transfer_id = str(intent.get("transfer_id") or "").strip(); tx_id = str(intent.get("tx_id") or "").strip().lower()
            if not transfer_id or transfer_id in transfer_ids or not tx_id or tx_id in transfer_tx_ids or tx_id not in by_id: changed = True; removed += 1; continue
            rebuilt = self.build_transfer_intent_record_from_transaction(by_id[tx_id], transfer_id=transfer_id, signed_at=intent.get("signed_at"), created_at=intent.get("created_at"), updated_at=intent.get("updated_at"))
            if dict(intent) != rebuilt: changed = True
            intents.append(rebuilt); transfer_ids.add(transfer_id); transfer_tx_ids.add(tx_id)
        for tx in transactions:
            tx_id = str(tx.get("tx_id") or "").strip().lower()
            if tx_id not in transfer_tx_ids: intents.append(self.build_transfer_intent_record_from_transaction(tx)); changed = True
        return {"native_transactions": transactions, "transfer_intents": intents, "changed": changed, "removed": removed}
