"""Task 4.8 cross-component reliability coverage for durable native transfers."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import sqlite3
import time

import pytest
import requests
from eth_account import Account
from eth_account.messages import encode_defunct

import peer_sync
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
from test_support import fund_native_wallet_with_block
from wallet import Wallet


NETWORK = "zoidberg-testnet"


def _backend(data_dir, name):
    return SQLiteStorageBackend(
        blockchain_file=str(data_dir / f"{name}.json"),
        peers_file=str(data_dir / f"{name}-peers.json"),
        sqlite_db_path=str(data_dir / f"{name}.sqlite3"),
    )


def _chain(backend):
    return Blockchain(Wallet(), Wallet(), Wallet(), storage_backend=backend)


def _signed(account, *, nonce="1", amount="4", memo="task 4.8"):
    fields = NativeTransferMessage(
        action="transfer_zoid", network=NETWORK, from_address=account.address.lower(),
        to_address=Account.create().address.lower(), amount=amount, fee="0", nonce=nonce,
        timestamp=f"2026-09-06T03:00:{int(nonce):02d}+00:00", memo=memo,
        status="signed_pending", transaction_version=PROTOCOL_VERSION,
        protocol_version=PROTOCOL_VERSION,
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
        status="signed_pending", created_at=fields.timestamp, updated_at=fields.timestamp,
    ).to_dict()


def _admit(chain, transaction, *, node_id="node-a"):
    chain.record_native_transaction(transaction, status="signed_pending")
    chain.save_blockchain()
    return chain.admit_native_transaction_operation(
        transaction["tx_id"], origin_node_id=node_id, network_name=NETWORK
    )


def _durably_submit(chain, transaction, *, node_id="node-a"):
    return chain._admit_signed_transfer_durably(
        admit_to_mempool=True, origin_node_id=node_id,
        from_address=transaction["from_address"], to_address=transaction["to_address"],
        amount=transaction["amount"], fee=transaction["fee"], memo=transaction["memo"],
        network=transaction["network"], transaction_version=transaction["transaction_version"],
        protocol_version=transaction["protocol_version"], network_id=transaction["network_id"],
        signature_scheme=transaction["signature_scheme"], signature=transaction["signature"],
        signed_message_hash=transaction["signed_message_hash"], signed_message=transaction["signed_message"],
        transfer_nonce=transaction["nonce"], transaction_timestamp=transaction["timestamp"],
        signed_at=transaction["timestamp"],
    )


def _worker(chain, store, transport, clock, *, batch_size=4, reconciliation_batch_size=10):
    return NativeTransactionDeliveryWorker(
        chain, store, origin_node_id="node-a", network_name=NETWORK,
        transport_factory=lambda: transport, request_headers=peer_sync.build_peer_request_headers,
        retry_policy=NativeTransactionRetryPolicy(initial_delay_seconds=2, maximum_delay_seconds=5),
        timeout_seconds=1, lease_seconds=2, batch_size=batch_size,
        reconciliation_batch_size=reconciliation_batch_size,
        reconciliation_interval_seconds=60, now=lambda: clock[0],
    )


class _Response:
    status_code = 200
    text = "ok"

    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


def test_pending_sequence_restart_preserves_reservations_and_deterministic_block_order(isolated_data_dir):
    backend = _backend(isolated_data_dir, "pending-restart")
    chain = _chain(backend)
    account = Account.create()
    fund_native_wallet_with_block(chain, account.address, persist=True)
    first, second = _signed(account, nonce="1", amount="4"), _signed(account, nonce="2", amount="4")

    _admit(chain, first)
    _admit(chain, second)
    before = chain.get_native_balance_snapshot(account.address)
    assert before["final_balance"] == "25"
    assert before["pending_outgoing"] == "8"
    assert before["available_balance"] == "17"

    restarted = _chain(_backend(isolated_data_dir, "pending-restart"))
    records = restarted.list_mempool_transactions()
    assert [record["tx_id"] for record in records] == [first["tx_id"], second["tx_id"]]
    assert restarted.get_nonce_state(account.address)["reserved_nonces"] == [1, 2]
    assert restarted.get_native_balance_snapshot(account.address) == before
    selected = restarted.select_native_transactions_for_block()
    assert selected["transaction_ids"] == [first["tx_id"], second["tx_id"]]
    assert len(restarted.storage.list_durable_native_transaction_records()) == 2


def test_future_nonce_is_rejected_then_succeeds_only_after_predecessor_is_admitted(isolated_data_dir):
    chain = _chain(_backend(isolated_data_dir, "future-nonce"))
    account = Account.create()
    fund_native_wallet_with_block(chain, account.address, persist=True)
    future, first = _signed(account, nonce="2"), _signed(account, nonce="1")

    chain.record_native_transaction(future, status="signed_pending")
    chain.save_blockchain()
    with pytest.raises(ValueError, match="ahead of the next expected nonce"):
        chain.admit_native_transaction_operation(future["tx_id"], origin_node_id="node-a", network_name=NETWORK)
    assert chain.get_native_transaction(future["tx_id"])["status"] == "signed_pending"

    _admit(chain, first)
    admitted = chain.admit_native_transaction_operation(future["tx_id"], origin_node_id="node-a", network_name=NETWORK)
    assert admitted["status"] == "mempool"
    assert [record["nonce"] for record in chain.list_mempool_transactions()] == ["1", "2"]


def test_concurrent_same_nonce_and_overspend_submissions_leave_one_durable_reservation(isolated_data_dir):
    backend = _backend(isolated_data_dir, "concurrent-admission")
    initial = _chain(backend)
    account = Account.create()
    fund_native_wallet_with_block(initial, account.address, persist=True)
    same_nonce_a = _signed(account, nonce="1", amount="7", memo="same nonce a")
    same_nonce_b = _signed(account, nonce="1", amount="7", memo="same nonce b")

    def submit(transaction):
        try:
            return "accepted", _durably_submit(_chain(_backend(isolated_data_dir, "concurrent-admission")), transaction)
        except ValueError as exc:
            return "rejected", str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(submit, (same_nonce_a, same_nonce_b)))
    assert [outcome[0] for outcome in outcomes].count("accepted") == 1
    assert [outcome[0] for outcome in outcomes].count("rejected") == 1

    restarted = _chain(_backend(isolated_data_dir, "concurrent-admission"))
    accepted = restarted.list_mempool_transactions()
    assert len(accepted) == 1
    assert accepted[0]["nonce"] == "1"
    assert restarted.get_native_balance_snapshot(account.address)["pending_outgoing"] == "7"
    assert restarted.get_nonce_state(account.address)["reserved_nonces"] == [1]


def test_receiver_restart_after_lost_ack_returns_idempotent_ack_without_duplicate_reservation(isolated_data_dir):
    sender_backend, receiver_backend = _backend(isolated_data_dir, "lost-ack-sender"), _backend(isolated_data_dir, "lost-ack-receiver")
    sender, receiver = _chain(sender_backend), _chain(receiver_backend)
    sender_peers, receiver_peers = PeerStore(storage_backend=sender_backend), PeerStore(storage_backend=receiver_backend)
    sender_peers.register_peer("node-b", "http://node-b.test", NETWORK)
    receiver_peers.register_peer("node-a", "http://node-a.test", NETWORK)
    account = Account.create()
    fund_native_wallet_with_block(sender, account.address, persist=True)
    fund_native_wallet_with_block(receiver, account.address, persist=True)
    transaction = _signed(account)
    _admit(sender, transaction)
    clock = [datetime(2026, 9, 6, 4, 0, tzinfo=timezone.utc)]

    class LostAck:
        request_error = requests.RequestException
        @staticmethod
        def post(_url, *, json, **_kwargs):
            peer_sync.receive_peer_transaction(receiver, receiver_peers, "node-a", NETWORK, json["transaction"], NETWORK, peer_message=json)
            raise requests.RequestException("lost after receiver commit")

    _worker(sender, sender_peers, LostAck(), clock).process_once(force_reconciliation=True)
    receiver = _chain(_backend(isolated_data_dir, "lost-ack-receiver"))
    receiver_peers = PeerStore(storage_backend=receiver.storage)
    clock[0] += timedelta(seconds=2)

    class Retried:
        request_error = requests.RequestException
        @staticmethod
        def post(_url, *, json, **_kwargs):
            return _Response(peer_sync.receive_peer_transaction(receiver, receiver_peers, "node-a", NETWORK, json["transaction"], NETWORK, peer_message=json))

    started = time.monotonic()
    _worker(sender, sender_peers, Retried(), clock).process_once(force_reconciliation=True)
    assert time.monotonic() - started < 2
    assert sender_backend.list_native_transaction_outbox()[0]["delivery_state"] == "acknowledged"
    assert len(receiver.storage.list_durable_native_transaction_records()) == 1
    assert receiver.get_native_balance_snapshot(account.address)["pending_outgoing"] == "4"
    assert receiver.get_nonce_state(account.address)["reserved_nonces"] == [1]


def test_reconciliation_is_bounded_idempotent_and_does_not_replay_settled_history(isolated_data_dir):
    backend = _backend(isolated_data_dir, "bounded-reconciliation")
    chain = _chain(backend)
    peers = PeerStore(storage_backend=backend)
    account = Account.create()
    fund_native_wallet_with_block(chain, account.address, persist=True)
    first, second = _signed(account, nonce="1"), _signed(account, nonce="2")
    _admit(chain, first)
    _admit(chain, second)
    chain.update_native_transaction_status(first["tx_id"], status="settled", included_block_hash="a" * 64, included_block_height=1, settled_at="2026-09-06T04:01:00+00:00")
    chain.save_blockchain()
    peers.register_peer("node-b", "http://node-b.test", NETWORK)
    clock = [datetime(2026, 9, 6, 4, 2, tzinfo=timezone.utc)]

    class Offline:
        request_error = requests.RequestException
        @staticmethod
        def post(*_args, **_kwargs):
            raise requests.RequestException("offline")

    worker = _worker(chain, peers, Offline(), clock, reconciliation_batch_size=1)
    report = worker.reconcile_pending_transactions(force=True)
    assert report["transactions"] == 1
    rows = backend.list_native_transaction_outbox()
    assert [row["tx_id"] for row in rows] == [second["tx_id"]]
    worker.reconcile_pending_transactions(force=True)
    assert len(backend.list_native_transaction_outbox()) == 1


def test_sqlite_database_guards_reject_invalid_lifecycle_outbox_claim_and_receiver_dedup(isolated_data_dir):
    backend = _backend(isolated_data_dir, "database-guards")
    chain = _chain(backend)
    account = Account.create()
    fund_native_wallet_with_block(chain, account.address, persist=True)
    transaction = _signed(account)
    _admit(chain, transaction)
    PeerStore(storage_backend=backend).register_peer("node-b", "http://node-b.test", NETWORK)
    # Admission after peer registration creates the one permitted logical delivery row.
    another = _signed(account, nonce="2")
    _admit(chain, another)
    row = backend.list_native_transaction_outbox(tx_id=another["tx_id"])[0]

    with backend._connect() as connection:
        with pytest.raises(sqlite3.IntegrityError, match="illegal native transaction lifecycle transition"):
            connection.execute("UPDATE native_transaction_records SET lifecycle_state = 'finalized' WHERE tx_id = ?", (transaction["tx_id"],))
        with pytest.raises(sqlite3.IntegrityError, match="illegal native transaction outbox transition"):
            connection.execute("UPDATE native_transaction_peer_outbox SET delivery_state = 'acknowledged' WHERE outbox_id = ?", (row["outbox_id"],))
        connection.execute(
            "INSERT INTO received_native_transaction_messages (message_id, message_type, sender_node_id, tx_id, payload_hash, received_at, acknowledged_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("d" * 64, "native_transaction", "node-a", transaction["tx_id"], "e" * 64, "2026-09-06T04:00:00+00:00", "2026-09-06T04:00:00+00:00"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO received_native_transaction_messages (message_id, message_type, sender_node_id, tx_id, payload_hash, received_at, acknowledged_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("d" * 64, "native_transaction", "node-c", another["tx_id"], "f" * 64, "2026-09-06T04:00:00+00:00", "2026-09-06T04:00:00+00:00"),
            )
        connection.execute(
            "INSERT INTO canonical_native_transaction_claims (tx_id, sender, nonce, block_hash, block_height) VALUES (?, ?, ?, ?, ?)",
            (transaction["tx_id"], transaction["from_address"], "99", "b" * 64, 2),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO canonical_native_transaction_claims (tx_id, sender, nonce, block_hash, block_height) VALUES (?, ?, ?, ?, ?)",
                (another["tx_id"], transaction["from_address"], "99", "c" * 64, 3),
            )
