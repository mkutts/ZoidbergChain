"""Deterministic native ZOID mempool admission, selection, and revalidation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from config import MAX_TRANSACTIONS_PER_BLOCK
from protocol_v1_native_transfer import PROTOCOL_V1_NATIVE_TRANSFER_VERSION


@dataclass
class NativeMempoolState:
    native_transactions: list


class NativeMempoolService:
    """Mempool transitions over an injected ledger collaborator and state view."""

    def __init__(self, ledger):
        self.ledger = ledger

    def list_transactions(self, state):
        records = [dict(tx) for tx in state.native_transactions if str(tx.get("status") or "").strip().lower() == "mempool"]
        records.sort(key=self.ledger.native_mempool_sort_key)
        return records

    def get_transaction(self, state, storage, tx_id):
        transaction = self.ledger.get_native_transaction(state, storage, tx_id)
        return transaction if transaction is not None and str(transaction.get("status") or "").strip().lower() == "mempool" else None

    def validate_transaction(self, state, storage, transaction_or_tx_id):
        return self.ledger.validate_transaction_for_admission(
            state, storage, transaction_or_tx_id,
            allowed_statuses=self.ledger.native_mempool_eligible_statuses(),
            exclude_tx_id=(transaction_or_tx_id.get("tx_id") if isinstance(transaction_or_tx_id, dict) else transaction_or_tx_id),
        )

    def select_for_block(self, state, storage, chain_to_dicts, *, max_transactions_per_block=MAX_TRANSACTIONS_PER_BLOCK, error_type=ValueError):
        candidates = [dict(tx) for tx in state.native_transactions if str(tx.get("status") or "").strip().lower() in self.ledger.native_block_candidate_statuses()]
        candidates.sort(key=self.ledger.native_block_sort_key)
        selected, skipped = [], []
        chain_state = self.ledger.calculate_balances_from_chain(state, chain_to_dicts, error_type=error_type)
        seen = set(chain_state["seen_tx_ids"]); selected_ids = set(); nonces = dict(chain_state["next_nonces"]); balances = dict(chain_state["balances"]); seen_nonces = set()
        for transaction in candidates:
            tx_id = str(transaction.get("tx_id") or "").strip().lower()
            if not tx_id or tx_id in seen:
                skipped.append({"tx_id": tx_id, "reason": "already_settled"}); continue
            try:
                if str(transaction.get("status") or "").strip().lower() not in self.ledger.native_block_candidate_statuses():
                    raise ValueError(f"Transaction status {transaction.get('status')} is not eligible for this operation.")
                validated = self.ledger.validation_service.validate_block_step(
                    transaction, network_name=self.ledger.network_name, balances=balances,
                    next_nonces=nonces, canonical_tx_ids=seen, seen_block_tx_ids=selected_ids, seen_nonces=seen_nonces,
                    normalize_wallet=self.ledger.normalize_wallet_identity,
                    coerce_nonce=self.ledger.coerce_native_nonce,
                    normalize_decimal=self.ledger.normalize_decimal_value,
                )
            except ValueError as exc:
                skipped.append({"tx_id": tx_id, "reason": self.ledger.validation_service.code_for_error(exc), "message": str(exc)}); continue
            selected.append(self.ledger.serialize_native_transaction_for_block(validated))
            if len(selected) >= max_transactions_per_block: break
        return {"transactions": selected, "transaction_ids": [tx["tx_id"] for tx in selected], "transaction_count": len(selected), "transactions_hash": self.ledger.compute_block_native_transactions_hash(selected), "skipped": skipped}

    def admit(self, state, storage, tx_id, *, now_iso):
        validated = self.validate_transaction(state, storage, tx_id)
        existing = self.ledger.get_native_transaction(state, storage, validated["tx_id"])
        admitted_at = str(existing.get("admitted_at") or now_iso())
        updated = self.ledger.update_native_transaction_status(state, storage, validated["tx_id"], status="mempool", admitted_at=admitted_at, now_iso=now_iso())
        return {"tx_id": updated["tx_id"], "status": updated["status"], "admitted": True, "admitted_at": updated.get("admitted_at"), "message": "Transaction admitted to local mempool. It is not settled until included in a block."}

    def revalidate(self, state, storage, *, now_iso):
        report = {"checked": 0, "kept": 0, "removed": 0, "items": []}
        for transaction in list(self.list_transactions(state)):
            report["checked"] += 1; tx_id = transaction.get("tx_id")
            try:
                self.validate_transaction(state, storage, transaction)
                report["kept"] += 1; report["items"].append({"tx_id": tx_id, "valid": True, "status": "mempool"})
            except ValueError as exc:
                reason = str(exc); normalized = self.ledger.validation_service.code_for_error(exc)
                self.ledger.update_native_transaction_status(state, storage, tx_id, status="rejected", rejection_reason=normalized, now_iso=now_iso())
                report["removed"] += 1; report["items"].append({"tx_id": tx_id, "valid": False, "status": "rejected", "reason": normalized, "message": reason})
        return report
