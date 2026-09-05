"""Durable, restart-safe delivery of pending native transaction gossip.

This module deliberately owns transport scheduling only.  It never changes a
transaction's consensus status: the receiver still performs ordinary durable
native-transaction admission and canonical chain sync remains the authority
for settled history.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from services.native_transaction_outbox_service import build_native_transaction_outbox_records


RETRYABLE_HTTP_STATUSES = {408, 425, 429}
# A receiver can be temporarily behind the canonical state or waiting for an
# earlier nonce.  These are deliberately not irreversible delivery failures.
RETRYABLE_REASONS = {
    # Nonce conflicts describe the receiver's current chain/mempool view.  A
    # fork-choice replacement can remove an accepted block and a pending
    # reservation can be rejected/expired, so neither is an immutable message
    # failure.  The receive response carries no independently verifiable
    # finalized-conflict proof; retain delivery intent for reconciliation.
    "future_nonce", "stale_nonce", "invalid_nonce", "active_nonce_conflict",
    "conflicting_nonce", "insufficient_balance",
    "insufficient_available_balance", "peer_temporarily_unavailable",
    "temporary_transport_failure", "transport_failure",
}
SUCCESS_REASONS = {"already_settled", "already_have"}
PERMANENT_REASONS = {
    "authentication_rejected", "wrong_network", "unsupported_transaction_version",
    "unsupported_protocol_version", "invalid_signature", "invalid_tx_id",
    "invalid_signed_message", "invalid_fee_policy", "message_conflict",
    "validation_failed", "protocol_rejected", "invalid_ack",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_at(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class NativeTransactionRetryPolicy:
    """Bounded deterministic retry policy; no attempt limit drops work."""

    initial_delay_seconds: int = 2
    maximum_delay_seconds: int = 300
    multiplier: int = 2

    def delay_seconds(self, attempt_count: int) -> int:
        exponent = max(0, int(attempt_count) - 1)
        return min(
            self.maximum_delay_seconds,
            self.initial_delay_seconds * (self.multiplier ** exponent),
        )

    def next_attempt_at(self, attempt_count: int, *, now: datetime) -> str:
        return iso_at(now + timedelta(seconds=self.delay_seconds(attempt_count)))


def classify_delivery_response(status_code, body) -> tuple[str, str, bool]:
    """Return ``(outcome, code, permanent)`` for a peer receive response."""
    body = body if isinstance(body, dict) else {}
    reason = str(body.get("reason") or "").strip().lower()
    if status_code is None or status_code >= 500 or status_code in RETRYABLE_HTTP_STATUSES:
        return "retry", reason or "peer_temporarily_unavailable", False
    if status_code >= 400:
        if reason in SUCCESS_REASONS:
            return "acknowledge", reason, False
        if reason in RETRYABLE_REASONS:
            return "retry", reason, False
        # A bare 4xx is a protocol/validation failure, not a connectivity retry.
        return "permanent", reason or ("authentication_rejected" if status_code in {401, 403} else "protocol_rejected"), True
    return "ack", reason, False


class NativeTransactionDeliveryWorker:
    """Claims one durable row at a time and performs network I/O outside locks."""

    def __init__(
        self,
        blockchain,
        peer_store,
        *,
        origin_node_id: str,
        network_name: str,
        transport_factory: Callable,
        request_headers: Callable,
        retry_policy: NativeTransactionRetryPolicy,
        timeout_seconds: int = 3,
        lease_seconds: int = 30,
        batch_size: int = 25,
        reconciliation_batch_size: int = 100,
        reconciliation_interval_seconds: int = 30,
        now: Callable[[], datetime] = utc_now,
        pull_reconcile: Callable | None = None,
    ):
        self.blockchain = blockchain
        self.peer_store = peer_store
        self.origin_node_id = origin_node_id
        self.network_name = network_name
        self.transport_factory = transport_factory
        self.request_headers = request_headers
        self.retry_policy = retry_policy
        self.timeout_seconds = timeout_seconds
        self.lease_seconds = lease_seconds
        self.batch_size = batch_size
        self.reconciliation_batch_size = reconciliation_batch_size
        self.reconciliation_interval_seconds = reconciliation_interval_seconds
        self.now = now
        self.pull_reconcile = pull_reconcile
        self._peer_versions: dict[str, tuple[str, object]] = {}
        self._has_observed_peers = False
        self._next_reconciliation_at: datetime | None = None

    @property
    def durable(self) -> bool:
        return bool(getattr(self.blockchain.storage, "supports_durable_peer_outbox", False))

    def _active_peers(self):
        return self.peer_store.list_active_peers(network_name=self.network_name)

    def reconcile_pending_transactions(self, *, force: bool = False) -> dict:
        """Backfill only present mempool work, never arbitrary history."""
        if not self.durable:
            return {"enabled": False, "peers": 0, "transactions": 0, "newly_healthy": []}
        current = self.now()
        if not force and self._next_reconciliation_at and current < self._next_reconciliation_at:
            return {"enabled": True, "skipped": True, "peers": 0, "transactions": 0, "newly_healthy": []}
        peers = self._active_peers()
        newly_healthy = []
        for peer in peers:
            peer_id = str(peer.get("node_id") or "").strip()
            version = (str(peer.get("url") or "").strip().rstrip("/"), peer.get("last_seen"))
            if peer_id and self._peer_versions.get(peer_id) != version:
                # First process startup must preserve an already persisted
                # retry schedule. Later registration/health updates are a
                # positive reconnection signal and may wake it promptly.
                if self._has_observed_peers:
                    newly_healthy.append(peer)
                self._peer_versions[peer_id] = version
        active_ids = {str(peer.get("node_id") or "").strip() for peer in peers}
        self._peer_versions = {key: value for key, value in self._peer_versions.items() if key in active_ids}
        self._has_observed_peers = True

        transactions = list(self.blockchain.list_mempool_transactions())[:self.reconciliation_batch_size]
        for peer in peers:
            records = []
            for transaction in transactions:
                records.extend(build_native_transaction_outbox_records(
                    transaction, [peer], sender_node_id=self.origin_node_id,
                    network_name=self.network_name,
                    created_at=transaction.get("admitted_at") or iso_at(current),
                ))
            if records:
                self.blockchain.storage.enqueue_native_transaction_outbox(records)
            # Node identity is the delivery identity.  A re-registration with a
            # new URL updates the one logical row rather than making a duplicate.
            self.blockchain.storage.refresh_native_transaction_outbox_destination(
                destination_peer_id=peer.get("node_id"), destination_peer_url=peer.get("url"),
                now=iso_at(current), expedite=peer in newly_healthy,
            )
        self._next_reconciliation_at = current + timedelta(seconds=self.reconciliation_interval_seconds)
        return {"enabled": True, "peers": len(peers), "transactions": len(transactions), "newly_healthy": [peer.get("node_id") for peer in newly_healthy]}

    def _retry(self, claimed, code: str, detail: str | None, *, now: datetime):
        return self.blockchain.storage.fail_native_transaction_outbox(
            outbox_id=claimed["outbox_id"], claim_token=claimed["claim_token"],
            error_code=code, error_detail=detail,
            next_attempt_at=self.retry_policy.next_attempt_at(claimed["attempt_count"], now=now),
        )

    def _deliver_claimed(self, claimed, *, now: datetime) -> dict:
        # Delivery intent is keyed to a configured node identity, not merely a
        # remembered URL.  An operator-disabled, removed, or wrong-network peer
        # must not be treated as an endless temporary network outage.
        peer = self.peer_store.get_active_peer(claimed["destination_peer_id"])
        if peer is None or peer.get("network_name") != self.network_name:
            self.blockchain.storage.fail_native_transaction_outbox(
                outbox_id=claimed["outbox_id"], claim_token=claimed["claim_token"],
                error_code="peer_inactive_or_removed",
                error_detail="Destination peer is no longer active on this network.", permanent=True,
            )
            return {"status": "permanent_failure", "outbox_id": claimed["outbox_id"], "error": "peer_inactive_or_removed"}
        path = "/peers/transactions/receive"
        payload = claimed["message"]
        headers = self.request_headers("POST", path, payload, payload["origin_node_id"], network_name=self.network_name)
        try:
            response = self.transport_factory().post(
                f"{claimed['destination_peer_url'].rstrip('/')}{path}", json=payload,
                headers=headers, timeout=self.timeout_seconds,
            )
            status_code = getattr(response, "status_code", None)
            try:
                body = response.json() if hasattr(response, "json") else {}
            except (TypeError, ValueError):
                body = {}
            outcome, code, permanent = classify_delivery_response(status_code, body)
            if outcome == "ack":
                ack = body.get("ack") if isinstance(body, dict) else None
                if not (isinstance(ack, dict) and ack.get("status") == "acknowledged" and ack.get("message_id") == claimed["message_id"] and ack.get("tx_id") == claimed["tx_id"]):
                    outcome, code, permanent = "permanent", "invalid_ack", True
                elif self.blockchain.storage.acknowledge_native_transaction_outbox(
                    message_id=ack["message_id"], destination_peer_id=claimed["destination_peer_id"],
                    tx_id=ack["tx_id"], claim_token=claimed["claim_token"],
                ):
                    return {"status": "acknowledged", "outbox_id": claimed["outbox_id"], "duplicate": bool(ack.get("duplicate"))}
                else:
                    outcome, code, permanent = "permanent", "ack_state_conflict", True
            if outcome == "acknowledge":
                self.blockchain.storage.acknowledge_native_transaction_outbox(
                    message_id=claimed["message_id"], destination_peer_id=claimed["destination_peer_id"],
                    tx_id=claimed["tx_id"], claim_token=claimed["claim_token"],
                )
                return {"status": "acknowledged", "outbox_id": claimed["outbox_id"], "already_settled": True}
            if permanent:
                self.blockchain.storage.fail_native_transaction_outbox(
                    outbox_id=claimed["outbox_id"], claim_token=claimed["claim_token"],
                    error_code=code, error_detail=(body or {}).get("message") if isinstance(body, dict) else getattr(response, "text", ""), permanent=True,
                )
                return {"status": "permanent_failure", "outbox_id": claimed["outbox_id"], "error": code}
            self._retry(claimed, code, (body or {}).get("message") if isinstance(body, dict) else getattr(response, "text", ""), now=now)
            return {"status": "retry_wait", "outbox_id": claimed["outbox_id"], "error": code}
        except self.transport_factory().request_error as exc:
            self._retry(claimed, "transport_failure", str(exc), now=now)
            return {"status": "retry_wait", "outbox_id": claimed["outbox_id"], "error": "transport_failure"}

    def process_once(self, *, force_reconciliation: bool = False) -> dict:
        if not self.durable:
            return {"enabled": False, "attempted": 0, "results": []}
        reconciliation = self.reconcile_pending_transactions(force=force_reconciliation)
        results = []
        for _ in range(self.batch_size):
            now = self.now()
            claimed = self.blockchain.storage.claim_native_transaction_outbox(
                now=iso_at(now), lease_seconds=self.lease_seconds,
            )
            if claimed is None:
                break
            results.append(self._deliver_claimed(claimed, now=now))
        # Pull anti-entropy is intentionally bounded and runs only on the same
        # cadence as peer reconciliation.  It adds no consensus trust path.
        if self.pull_reconcile and not reconciliation.get("skipped"):
            for peer in self._active_peers()[:self.reconciliation_batch_size]:
                try:
                    self.pull_reconcile(peer, self.reconciliation_batch_size)
                except Exception:
                    # The next bounded round retries; delivery rows remain durable.
                    pass
        return {"enabled": True, "attempted": len(results), "results": results, "reconciliation": reconciliation}


def native_transaction_outbox_diagnostics(storage, *, now: datetime | None = None) -> dict:
    rows = storage.list_native_transaction_outbox() if getattr(storage, "supports_durable_peer_outbox", False) else []
    counts = {state: 0 for state in ("queued", "retry_wait", "in_flight", "acknowledged", "permanent_failure")}
    outstanding = []
    for row in rows:
        counts[row["delivery_state"]] = counts.get(row["delivery_state"], 0) + 1
        if row["delivery_state"] not in {"acknowledged", "permanent_failure"}:
            outstanding.append(row.get("created_at"))
    current = now or utc_now()
    oldest_age_seconds = None
    if outstanding:
        try:
            oldest = min(datetime.fromisoformat(str(value).replace("Z", "+00:00")) for value in outstanding if value)
            oldest_age_seconds = max(0, int((current - oldest.astimezone(timezone.utc)).total_seconds()))
        except (TypeError, ValueError):
            pass
    return {"enabled": bool(getattr(storage, "supports_durable_peer_outbox", False)), "counts": counts, "oldest_outstanding_age_seconds": oldest_age_seconds}
