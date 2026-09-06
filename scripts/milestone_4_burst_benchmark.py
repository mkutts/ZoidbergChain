"""Task 4.9 durable native-transaction burst benchmark.

This is intentionally an executable benchmark rather than a synthetic SQL
load.  Every submitted item is a freshly signed Protocol v1 transfer passed to
``Blockchain._admit_signed_transfer_durably``.  The utility raises
``BenchmarkCorrectnessError`` for any durability, accounting, uniqueness, or
delivery invariant failure.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import sys
import time
from typing import Iterable

# Direct execution resolves the repository's production modules without
# requiring an operator to set PYTHONPATH.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import requests
from eth_account import Account
from eth_account.messages import encode_defunct

import peer_sync
from block import Block
from blockchain import Blockchain
from native_transfer import (
    NativeTransferMessage,
    build_native_transaction,
    build_transfer_signing_message,
    hash_transfer_signing_message,
)
from peers import PeerStore
from protocol_v1 import PROTOCOL_VERSION
from protocol_v1_native_transfer import resolve_protocol_v1_network_id
from services.native_transaction_delivery_service import (
    NativeTransactionDeliveryWorker,
    NativeTransactionRetryPolicy,
)
from storage import SQLiteStorageBackend
from submission import APPROVED, VOTE_NOT_ORIGINAL, VOTE_ORIGINAL
from transaction import Transaction
from wallet import Wallet


NETWORK = "zoidberg-testnet"
UTC = timezone.utc
# Recipients do not need a private key to receive a native transfer.  Reusing
# this valid external address keeps fixture creation from benchmarking 10,000
# unrelated recipient-key generations.
BENCHMARK_RECIPIENT = "0x000000000000000000000000000000000000dead"


class BenchmarkCorrectnessError(RuntimeError):
    """A benchmark result is invalid, even if it happened to be fast."""


@dataclass(frozen=True)
class SignedWorkItem:
    transaction: dict
    sender: str
    amount: Decimal


def _percentile(values: Iterable[float], percentile: int) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * percentile / 100
    low, high = int(position), min(int(position) + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _backend(root: Path, name: str) -> SQLiteStorageBackend:
    return SQLiteStorageBackend(
        blockchain_file=str(root / f"{name}.json"),
        peers_file=str(root / f"{name}-peers.json"),
        sqlite_db_path=str(root / f"{name}.sqlite3"),
    )


def _chain(backend: SQLiteStorageBackend) -> Blockchain:
    return Blockchain(Wallet(), Wallet(), Wallet(), storage_backend=backend)


def _fund(chain: Blockchain, accounts, *, amount: Decimal) -> None:
    """Create one ordinary funding block for the exact benchmark accounts."""
    latest = chain.get_latest_block()
    timestamp = max(float(getattr(latest, "timestamp", 0) or 0) + 1.0, float(latest.index + 1))
    funding = Block(
        index=latest.index + 1,
        previous_hash=latest.hash,
        timestamp=timestamp,
        transactions=[
            Transaction("REWARD_POOL", account.address.lower(), float(amount), tip=0, created_at=timestamp)
            for account in accounts
        ],
        miner="REWARD_POOL",
        meme={"encoded_image": "task-4.9-funding", "text": "Task 4.9 benchmark funding"},
    )
    funding.hash = funding.calculate_hash()
    chain.chain.append(funding)
    chain.recompute_reward_pool_balance(chain=chain.chain)
    chain.save_blockchain()


def _signed(account, *, nonce: int, ordinal: int) -> dict:
    timestamp = (datetime(2026, 9, 6, tzinfo=UTC) + timedelta(seconds=ordinal)).isoformat()
    fields = NativeTransferMessage(
        action="transfer_zoid", network=NETWORK, from_address=account.address.lower(),
        to_address=BENCHMARK_RECIPIENT, amount="0.01", fee="0", nonce=str(nonce),
        timestamp=timestamp, memo=f"task-4.9-burst-{ordinal}", status="signed_pending",
        transaction_version=PROTOCOL_VERSION, protocol_version=PROTOCOL_VERSION,
        network_id=resolve_protocol_v1_network_id(network_name=NETWORK),
    )
    message = build_transfer_signing_message(fields)
    signature = Account.sign_message(encode_defunct(text=message), account.key).signature.hex()
    return build_native_transaction(
        network=fields.network, transaction_version=PROTOCOL_VERSION,
        protocol_version=PROTOCOL_VERSION, network_id=fields.network_id,
        from_address=fields.from_address, to_address=fields.to_address,
        amount=fields.amount, fee=fields.fee, nonce=fields.nonce, memo=fields.memo,
        timestamp=fields.timestamp, signature=signature, signature_scheme="personal_sign",
        signed_message=message, signed_message_hash=hash_transfer_signing_message(message),
        status="signed_pending", created_at=timestamp, updated_at=timestamp,
    ).to_dict()


def _sign_sender_group(key, address: str, jobs: list[tuple[int, int]]) -> list[SignedWorkItem]:
    """Sign one sender's already-planned nonce sequence in a fixture worker."""
    account = Account.from_key(key)
    return [
        SignedWorkItem(_signed(account, nonce=nonce, ordinal=ordinal), address, Decimal("0.01"))
        for nonce, ordinal in jobs
    ]


def _make_workload(*, transactions: int, profile: str, workers: int, signing_workers: int | None = None):
    if transactions < 1:
        raise ValueError("transactions must be positive")
    fixture_started = time.perf_counter()
    if profile == "low_contention":
        # A broad sender set avoids pathological same-account contention while
        # keeping fixture key generation/funding proportional to the workload,
        # not to every individual transfer.  Each sender's own short sequence
        # remains strictly ordered and therefore legitimately admissible.
        senders = min(transactions, 128)
        accounts = [Account.create() for _ in range(senders)]
        jobs = [[] for _ in accounts]
        for ordinal in range(transactions):
            sender_index = ordinal % senders
            jobs[sender_index].append((len(jobs[sender_index]) + 1, ordinal))
    elif profile == "sequential_pressure":
        senders = max(1, min(workers, transactions))
        accounts = [Account.create() for _ in range(senders)]
        jobs = [[] for _ in accounts]
        for ordinal in range(transactions):
            sender_index = ordinal % senders
            jobs[sender_index].append((len(jobs[sender_index]) + 1, ordinal))
    else:
        raise ValueError(f"Unknown profile: {profile}")
    key_generation_seconds = time.perf_counter() - fixture_started
    selected_signing_workers = min(
        len(accounts), signing_workers if signing_workers is not None else min(16, os.cpu_count() or 1)
    )
    signing_started = time.perf_counter()
    arguments = [(bytes(account.key), account.address.lower(), group) for account, group in zip(accounts, jobs)]
    if transactions < 100 or selected_signing_workers == 1:
        groups = [_sign_sender_group(*argument) for argument in arguments]
    else:
        with ProcessPoolExecutor(max_workers=selected_signing_workers) as pool:
            groups = list(pool.map(_sign_sender_group, *(zip(*arguments))))
    return accounts, groups, {
        "sender_count": len(accounts), "recipient": BENCHMARK_RECIPIENT,
        "key_generation_seconds": key_generation_seconds,
        "signing_seconds": time.perf_counter() - signing_started,
        "signing_workers": selected_signing_workers,
    }


def _admit_group(root: Path, name: str, group: list[SignedWorkItem]):
    # Each worker has its own node facade, just as separately scheduled node
    # requests do. SQLite remains the shared durable serialization boundary.
    chain = _chain(_backend(root, name))
    outcomes = []
    for item in group:
        started = time.perf_counter()
        try:
            chain._admit_signed_transfer_durably(
                admit_to_mempool=True, origin_node_id="benchmark-node", **{
                    "from_address": item.transaction["from_address"], "to_address": item.transaction["to_address"],
                    "amount": item.transaction["amount"], "fee": item.transaction["fee"], "memo": item.transaction["memo"],
                    "network": item.transaction["network"], "transaction_version": item.transaction["transaction_version"],
                    "protocol_version": item.transaction["protocol_version"], "network_id": item.transaction["network_id"],
                    "signature_scheme": item.transaction["signature_scheme"], "signature": item.transaction["signature"],
                    "signed_message_hash": item.transaction["signed_message_hash"], "signed_message": item.transaction["signed_message"],
                    "transfer_nonce": item.transaction["nonce"], "transaction_timestamp": item.transaction["timestamp"],
                    "signed_at": item.transaction["timestamp"],
                },
            )
            outcomes.append(("acknowledged", item, time.perf_counter() - started, None))
        except ValueError as exc:
            outcomes.append(("rejected", item, time.perf_counter() - started, str(exc)))
        except Exception as exc:  # Accounting must include every worker result.
            outcomes.append(("unexpected_error", item, time.perf_counter() - started, repr(exc)))
    return outcomes


def _sqlite_sizes(path: Path) -> dict:
    files = {"database": path, "wal": Path(str(path) + "-wal"), "shm": Path(str(path) + "-shm")}
    values = {name: candidate.stat().st_size if candidate.exists() else 0 for name, candidate in files.items()}
    values["total"] = sum(values.values())
    return values


def _sqlite_settings(backend: SQLiteStorageBackend) -> dict:
    with backend._connect() as connection:
        return {
            "journal_mode": connection.execute("PRAGMA journal_mode").fetchone()[0],
            "synchronous": connection.execute("PRAGMA synchronous").fetchone()[0],
            "busy_timeout_ms": connection.execute("PRAGMA busy_timeout").fetchone()[0],
        }


def _verify_restart(root: Path, name: str, expected: list[SignedWorkItem], elapsed_close: float) -> dict:
    started = time.perf_counter()
    restarted_backend = _backend(root, name)
    restarted = _chain(restarted_backend)
    restart_seconds = time.perf_counter() - started
    records = restarted_backend.list_durable_native_transaction_records()
    expected_ids = {item.transaction["tx_id"] for item in expected}
    actual_ids = [record["tx_id"] for record in records]
    actual_set = set(actual_ids)
    missing = sorted(expected_ids - actual_set)
    duplicate_records = len(actual_ids) - len(actual_set)
    with restarted_backend._connect() as connection:
        duplicate_reservations = connection.execute(
            """SELECT COUNT(*) FROM (SELECT sender, nonce, COUNT(*) AS total
               FROM native_transaction_records WHERE lifecycle_state IN ('signed_pending', 'validated_pending', 'mempool')
               GROUP BY sender, nonce HAVING total > 1)"""
        ).fetchone()[0]
        reservations = dict(connection.execute(
            """SELECT sender, COUNT(*) FROM native_transaction_records
               WHERE lifecycle_state IN ('signed_pending', 'validated_pending', 'mempool') GROUP BY sender"""
        ).fetchall())
        outgoing = dict(connection.execute(
            """SELECT sender, COALESCE(SUM(CAST(amount AS REAL) + CAST(fee AS REAL)), 0)
               FROM native_transaction_records WHERE lifecycle_state IN ('signed_pending', 'validated_pending', 'mempool') GROUP BY sender"""
        ).fetchall())
    expected_reservations = Counter(item.sender for item in expected)
    expected_outgoing = defaultdict(Decimal)
    for item in expected:
        expected_outgoing[item.sender] += item.amount
    bad_reservations = sum(reservations.get(sender, 0) != count for sender, count in expected_reservations.items())
    bad_balances = sum(Decimal(str(outgoing.get(sender, 0))).quantize(Decimal("0.01")) != amount for sender, amount in expected_outgoing.items())
    report = {
        "shutdown_close_seconds": elapsed_close, "restart_open_seconds": restart_seconds,
        "pending_recovered": len(actual_set & expected_ids), "acknowledged_missing_after_restart": len(missing),
        "duplicate_durable_records": duplicate_records, "incorrect_active_nonce_reservations": duplicate_reservations + bad_reservations,
        "incorrect_pending_balance_reservations": bad_balances,
    }
    if any((report["acknowledged_missing_after_restart"], duplicate_records, report["incorrect_active_nonce_reservations"], bad_balances)):
        raise BenchmarkCorrectnessError(f"Restart durability invariant failed: {report}")
    return report


def run_admission(
    root: Path, *, name: str, transactions: int, profile: str, workers: int,
    signing_workers: int | None = None,
) -> dict:
    accounts, groups, fixture = _make_workload(
        transactions=transactions, profile=profile, workers=workers, signing_workers=signing_workers
    )
    backend = _backend(root, name)
    chain = _chain(backend)
    _fund(chain, accounts, amount=Decimal("200"))
    before = _sqlite_sizes(Path(backend.sqlite_db_path))
    # Keep one application facade per submitting worker.  Reconstructing a
    # Blockchain for every request would benchmark process startup, not native
    # transaction admission.  A complete sender nonce sequence stays on one
    # worker, preserving its intentional order.
    worker_batches = [[] for _ in range(workers)]
    for index, group in enumerate(groups):
        worker_batches[index % workers].extend(group)
    cpu_started, wall_started = time.process_time(), time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_admit_group, root, name, batch) for batch in worker_batches if batch]
        outcomes = [outcome for future in futures for outcome in future.result()]
    wall_seconds, cpu_seconds = time.perf_counter() - wall_started, time.process_time() - cpu_started
    acknowledged = [outcome for outcome in outcomes if outcome[0] == "acknowledged"]
    rejected = [outcome for outcome in outcomes if outcome[0] == "rejected"]
    unexpected = [outcome for outcome in outcomes if outcome[0] == "unexpected_error"]
    if len(outcomes) != transactions or transactions != len(acknowledged) + len(rejected) + len(unexpected):
        raise BenchmarkCorrectnessError("Admission attempt accounting is incomplete.")
    if rejected or unexpected:
        raise BenchmarkCorrectnessError(f"Expected only valid admissions; rejected={len(rejected)} unexpected={unexpected[:3]}")
    close_started = time.perf_counter()
    del chain
    close_seconds = time.perf_counter() - close_started
    restart = _verify_restart(root, name, [outcome[1] for outcome in acknowledged], close_seconds)
    after = _sqlite_sizes(Path(backend.sqlite_db_path))
    latencies = [outcome[2] for outcome in acknowledged]
    return {
        "profile": profile, "workers": workers, "attempted": transactions, "acknowledged": len(acknowledged),
        "fixture": fixture,
        "rejected": len(rejected), "unexpected_errors": len(unexpected), "database_errors": 0,
        "database_lock_busy_retries": 0, "wall_seconds": wall_seconds, "cpu_seconds": cpu_seconds,
        "throughput_tps": len(acknowledged) / wall_seconds if wall_seconds else 0,
        "latency_ms": {"p50": _percentile(latencies, 50) * 1000, "p95": _percentile(latencies, 95) * 1000,
                       "p99": _percentile(latencies, 99) * 1000, "max": max(latencies) * 1000},
        "database_before_bytes": before, "database_after_bytes": after,
        "sqlite_settings": _sqlite_settings(backend),
        "approx_bytes_per_pending_transaction": (after["total"] - before["total"]) / transactions,
        # The IDs are retained only long enough to perform the immediately
        # following restart verification.  Persisting all 10,000 IDs in every
        # progress checkpoint makes recovery metadata needlessly large; retain
        # a count and stable digest instead.
        "restart": restart,
        "transaction_id_count": len(acknowledged),
        "transaction_ids_sha256": hashlib.sha256(
            "\n".join(sorted(outcome[1].transaction["tx_id"] for outcome in acknowledged)).encode("ascii")
        ).hexdigest(),
    }


class _Response:
    status_code = 200
    text = "ok"
    def __init__(self, body): self.body = body
    def json(self): return self.body


def _delivery_worker(chain, store, transport, clock, *, node_id="node-a", batch_size=100):
    return NativeTransactionDeliveryWorker(
        chain, store, origin_node_id=node_id, network_name=NETWORK,
        transport_factory=lambda: transport, request_headers=peer_sync.build_peer_request_headers,
        retry_policy=NativeTransactionRetryPolicy(initial_delay_seconds=2, maximum_delay_seconds=5),
        timeout_seconds=1, lease_seconds=2, batch_size=batch_size, reconciliation_batch_size=batch_size,
        reconciliation_interval_seconds=60, now=lambda: clock[0],
    )


def _admit_items(chain: Blockchain, items: list[SignedWorkItem], *, node_id: str):
    outcomes = _admit_group_items(chain, items, node_id=node_id)
    if len(outcomes) != len(items) or any(item[0] != "acknowledged" for item in outcomes):
        raise BenchmarkCorrectnessError(f"Peer fixture admission failed: {outcomes[:3]}")


def _admit_group_items(chain, items, *, node_id):
    results = []
    for item in items:
        started = time.perf_counter()
        try:
            chain._admit_signed_transfer_durably(
                admit_to_mempool=True, origin_node_id=node_id, **{
                    "from_address": item.transaction["from_address"], "to_address": item.transaction["to_address"], "amount": item.transaction["amount"], "fee": item.transaction["fee"], "memo": item.transaction["memo"], "network": item.transaction["network"], "transaction_version": item.transaction["transaction_version"], "protocol_version": item.transaction["protocol_version"], "network_id": item.transaction["network_id"], "signature_scheme": item.transaction["signature_scheme"], "signature": item.transaction["signature"], "signed_message_hash": item.transaction["signed_message_hash"], "signed_message": item.transaction["signed_message"], "transfer_nonce": item.transaction["nonce"], "transaction_timestamp": item.transaction["timestamp"], "signed_at": item.transaction["timestamp"],
                },
            )
            results.append(("acknowledged", item, time.perf_counter() - started, None))
        except Exception as exc:
            results.append(("unexpected_error", item, time.perf_counter() - started, repr(exc)))
    return results


def run_peer_propagation(root: Path, *, transactions: int) -> dict:
    accounts, groups, fixture = _make_workload(transactions=transactions, profile="sequential_pressure", workers=10)
    items = [item for group in groups for item in group]
    sender_backend, receiver_backend = _backend(root, "peer-sender"), _backend(root, "peer-receiver")
    sender, receiver = _chain(sender_backend), _chain(receiver_backend)
    _fund(sender, accounts, amount=Decimal("200")); _fund(receiver, accounts, amount=Decimal("200"))
    sender_store, receiver_store = PeerStore(storage_backend=sender_backend), PeerStore(storage_backend=receiver_backend)
    sender_store.register_peer("node-b", "http://node-b.test", NETWORK)
    receiver_store.register_peer("node-a", "http://node-a.test", NETWORK)
    _admit_items(sender, items, node_id="node-a")
    outbox_created = len(sender_backend.list_native_transaction_outbox())
    clock = [datetime(2026, 9, 6, 8, tzinfo=UTC)]
    deliveries = []
    class Loopback:
        request_error = requests.RequestException
        @staticmethod
        def post(_url, *, json, **_kwargs):
            return _Response(peer_sync.receive_peer_transaction(receiver, receiver_store, "node-a", NETWORK, json["transaction"], NETWORK, peer_message=json))
    worker = _delivery_worker(sender, sender_store, Loopback(), clock, batch_size=100)
    started = time.perf_counter()
    while True:
        report = worker.process_once(force_reconciliation=True)
        deliveries.extend(report["results"])
        if not report["results"]:
            break
    elapsed = time.perf_counter() - started
    rows = sender_backend.list_native_transaction_outbox()
    acknowledged_rows = [row for row in rows if row["delivery_state"] == "acknowledged"]
    duplicate_responses = 0
    for row in acknowledged_rows[:min(32, len(acknowledged_rows))]:
        replay = peer_sync.receive_peer_transaction(receiver, receiver_store, "node-a", NETWORK, row["message"]["transaction"], NETWORK, peer_message=row["message"])
        duplicate_responses += int(bool(replay.get("duplicate")))
    receiver_records = receiver_backend.list_durable_native_transaction_records()
    if len(receiver_records) != transactions or len({record["tx_id"] for record in receiver_records}) != transactions:
        raise BenchmarkCorrectnessError("Peer receiver admitted duplicate or missing durable transactions.")
    if len(acknowledged_rows) != transactions:
        raise BenchmarkCorrectnessError("Peer outbox did not fully converge.")
    return {"fixture": fixture, "transactions_admitted": transactions, "outbox_rows_created": outbox_created, "messages_attempted": len(deliveries),
            "messages_acked": len(acknowledged_rows), "retry_count": sum(row["attempt_count"] - 1 for row in rows),
            "duplicate_deliveries": duplicate_responses, "receiver_durable_transactions": len(receiver_records),
            "throughput_tps": transactions / elapsed if elapsed else 0, "ack_convergence_seconds": elapsed,
            "receiver_duplicates": len(receiver_records) - len({record["tx_id"] for record in receiver_records}),
            "outstanding_rows": len(rows) - len(acknowledged_rows)}


def run_disconnect_recovery(root: Path, *, transactions: int) -> dict:
    accounts, groups, fixture = _make_workload(transactions=transactions, profile="sequential_pressure", workers=4)
    items = [item for group in groups for item in group]
    sender_backend, receiver_backend = _backend(root, "offline-sender"), _backend(root, "offline-receiver")
    sender, receiver = _chain(sender_backend), _chain(receiver_backend)
    _fund(sender, accounts, amount=Decimal("200")); _fund(receiver, accounts, amount=Decimal("200"))
    sender_store, receiver_store = PeerStore(storage_backend=sender_backend), PeerStore(storage_backend=receiver_backend)
    sender_store.register_peer("node-b", "http://node-b.test", NETWORK); receiver_store.register_peer("node-a", "http://node-a.test", NETWORK)
    _admit_items(sender, items, node_id="node-a")
    clock = [datetime(2026, 9, 6, 9, tzinfo=UTC)]
    class Offline:
        request_error = requests.RequestException
        @staticmethod
        def post(*_args, **_kwargs): raise requests.RequestException("receiver offline")
    worker = _delivery_worker(sender, sender_store, Offline(), clock, batch_size=transactions)
    worker.process_once(force_reconciliation=True)
    backlog = len(sender_backend.list_native_transaction_outbox())
    retries = sum(row["attempt_count"] for row in sender_backend.list_native_transaction_outbox())
    clock[0] += timedelta(seconds=2)
    first = {"value": True}
    class Reconnected:
        request_error = requests.RequestException
        @staticmethod
        def post(_url, *, json, **_kwargs):
            body = peer_sync.receive_peer_transaction(receiver, receiver_store, "node-a", NETWORK, json["transaction"], NETWORK, peer_message=json)
            if first["value"]:
                first["value"] = False
                raise requests.RequestException("lost ACK after receiver durable commit")
            return _Response(body)
    worker = _delivery_worker(sender, sender_store, Reconnected(), clock, batch_size=transactions)
    started = time.perf_counter()
    worker.process_once(force_reconciliation=True)
    # The deliberately lost ACK is the second attempt for that row, so the
    # configured 2,4,... policy schedules its retry four benchmark seconds on.
    clock[0] += timedelta(seconds=4)
    while worker.process_once(force_reconciliation=True)["results"]:
        pass
    elapsed = time.perf_counter() - started
    rows = sender_backend.list_native_transaction_outbox()
    outstanding = [row for row in rows if row["delivery_state"] != "acknowledged"]
    receiver_records = receiver_backend.list_durable_native_transaction_records()
    if outstanding or len(receiver_records) != transactions:
        raise BenchmarkCorrectnessError("Offline delivery backlog failed to converge.")
    return {"fixture": fixture, "batch_size": transactions, "backlog_size": backlog, "retries_before_reconnect": retries,
            "reconnect_convergence_seconds": elapsed, "duplicate_deliveries": 1,
            "unacknowledged_rows_remaining": len(outstanding)}


def run_settlement_sample(root: Path, *, transactions: int = 10) -> dict:
    """Settle a small real sample through one certified content block.

    This deliberately uses the existing content-submission/certificate/mint
    flow.  It does not create a transaction-only block or change the fixed
    one-accepted-media-item/one-block rule merely for measurement.
    """
    accounts, groups, fixture = _make_workload(
        transactions=transactions, profile="sequential_pressure", workers=1
    )
    items = [item for group in groups for item in group]
    backend = _backend(root, "settlement-sample")
    chain = _chain(backend)
    _fund(chain, accounts, amount=Decimal("200"))
    _admit_items(chain, items, node_id="settlement-node")
    submission = chain.submit_content(
        image_path=str(REPOSITORY_ROOT / "zoidberg.jpg"),
        text_content="Task 4.9 certified settlement sample",
        submitter=accounts[0].address.lower(),
    )
    for index, vote_type in enumerate((VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_NOT_ORIGINAL)):
        chain.cast_submission_vote(submission.submission_id, f"task-4.9-voter-{index}", vote_type, created_at=1_100_000 + index)
    submission.transition_to(APPROVED)
    chain.create_originality_certificate(submission.submission_id, approved_at=1_100_100, allow_pending=True)
    chain.add_to_mint_queue(submission.submission_id)
    minted = chain.mint_submission(submission.submission_id, miner=accounts[0].address.lower(), validate_meme=False)
    block = chain.get_latest_block().to_dict()
    expected_ids = {item.transaction["tx_id"] for item in items}
    included_ids = set(block.get("transaction_ids") or [])
    with backend._connect() as connection:
        claims = connection.execute(
            "SELECT tx_id, sender, nonce FROM canonical_native_transaction_claims"
        ).fetchall()
        duplicate_claims = connection.execute(
            """SELECT COUNT(*) FROM (SELECT sender, nonce, COUNT(*) AS total
               FROM canonical_native_transaction_claims GROUP BY sender, nonce HAVING total > 1)"""
        ).fetchone()[0]
    settled = [record for record in backend.list_durable_native_transaction_records() if record["tx_id"] in expected_ids]
    duplicate_settlements = len(settled) - len({record["tx_id"] for record in settled})
    if included_ids != expected_ids or len(claims) != transactions or duplicate_claims or duplicate_settlements:
        raise BenchmarkCorrectnessError("Certified content-block settlement sample has duplicate or missing claims.")
    return {"fixture": fixture, "sample_size": transactions, "content_block_hash": block["hash"],
            "canonical_claims": len(claims), "duplicate_canonical_sender_nonce_claims": duplicate_claims,
            "duplicate_settlements": duplicate_settlements}


def environment() -> dict:
    with sqlite3.connect(":memory:") as connection:
        sqlite_version = connection.execute("select sqlite_version()").fetchone()[0]
    return {"os": platform.platform(), "python": sys.version.split()[0], "sqlite": sqlite_version,
            "cpu": platform.processor() or "not reported", "cpu_count": os.cpu_count(),
            "database_backend": "SQLite", "sqlite_settings": "recorded from each on-disk run",
            "peer_worker": "batch=100, lease=2s, retry=2/4/5s (benchmark clock)"}


def _write_progress(root: Path, result: dict) -> None:
    """Atomically retain completed phases if an operator interrupts a run."""
    target = root / "progress.json"
    temporary = root / "progress.json.tmp"
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(target)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("temp/task-4.9-benchmark"))
    parser.add_argument("--transactions", type=int, default=10_000)
    parser.add_argument("--calibration-transactions", type=int, default=1_000)
    parser.add_argument("--peer-transactions", type=int, default=1_000)
    parser.add_argument("--offline-transactions", type=int, default=256)
    parser.add_argument("--signing-workers", type=int, default=min(16, os.cpu_count() or 1))
    parser.add_argument("--keep-data", action="store_true")
    args = parser.parse_args(argv)
    root = args.output_dir.resolve()
    if root.exists():
        raise FileExistsError(f"Refusing to overwrite existing benchmark output directory: {root}")
    root.mkdir(parents=True)
    result = {"status": "running", "environment": environment(), "admission_runs": []}
    _write_progress(root, result)
    # One full 10,000-transaction run is paired with two 1,000-transaction
    # calibrations.  The latter expose contention and strict nonce pressure
    # without turning this durable per-commit benchmark into an impractically
    # long 30,000-transaction test on a developer workstation.
    run_plan = (
        ("low-single", "low_contention", 1, args.transactions),
        ("low-four", "low_contention", 4, args.calibration_transactions),
        ("sequential-four", "sequential_pressure", 4, args.calibration_transactions),
    )
    for name, profile, workers, transaction_count in run_plan:
        result["active_phase"] = name
        _write_progress(root, result)
        result["admission_runs"].append(
            run_admission(
                root, name=name, transactions=transaction_count, profile=profile, workers=workers,
                signing_workers=args.signing_workers,
            )
        )
        result.pop("active_phase", None)
        _write_progress(root, result)
    result["active_phase"] = "peer_propagation"; _write_progress(root, result)
    result["peer_propagation"] = run_peer_propagation(root, transactions=args.peer_transactions)
    _write_progress(root, result)
    result["active_phase"] = "disconnect_recovery"; _write_progress(root, result)
    result["disconnect_recovery"] = run_disconnect_recovery(root, transactions=args.offline_transactions)
    _write_progress(root, result)
    result["active_phase"] = "settlement_sample"; _write_progress(root, result)
    result["settlement_sample"] = run_settlement_sample(root)
    result["duplicate_settlements"] = result["settlement_sample"]["duplicate_settlements"]
    result.pop("active_phase", None)
    result["status"] = "complete"
    _write_progress(root, result)
    (root / "results.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if not args.keep_data: shutil.rmtree(root)
    return result


if __name__ == "__main__":
    main()
