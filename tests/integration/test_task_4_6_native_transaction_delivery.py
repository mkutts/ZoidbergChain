"""Focused Task 4.6 SQLite durable native-transaction delivery coverage."""

from datetime import datetime, timedelta, timezone

import requests
from eth_account import Account
from eth_account.messages import encode_defunct

import peer_sync
from blockchain import Blockchain
from native_transfer import NativeTransferMessage, build_native_transaction, build_transfer_signing_message, hash_transfer_signing_message
from peers import PeerStore
from protocol_v1 import PROTOCOL_VERSION
from protocol_v1_native_transfer import resolve_protocol_v1_network_id
from services.native_transaction_delivery_service import (
    NativeTransactionDeliveryWorker,
    NativeTransactionRetryPolicy,
    classify_delivery_response,
)
from storage import SQLiteStorageBackend
from test_support import fund_native_wallet_with_block
from wallet import Wallet


NETWORK = "zoidberg-testnet"


def _backend(data_dir, name):
    return SQLiteStorageBackend(
        blockchain_file=str(data_dir / f"{name}.json"), peers_file=str(data_dir / f"{name}-peers.json"),
        sqlite_db_path=str(data_dir / f"{name}.sqlite3"),
    )


def _chain(backend):
    return Blockchain(Wallet(), Wallet(), Wallet(), storage_backend=backend)


def _signed(account, *, nonce="1"):
    message = NativeTransferMessage(
        action="transfer_zoid", network=NETWORK, from_address=account.address.lower(),
        to_address=Account.create().address.lower(), amount="4", fee="0", nonce=nonce,
        timestamp="2026-09-05T16:00:00+00:00", memo="task 4.6", status="signed_pending",
        transaction_version=PROTOCOL_VERSION, protocol_version=PROTOCOL_VERSION,
        network_id=resolve_protocol_v1_network_id(network_name=NETWORK),
    )
    signed_message = build_transfer_signing_message(message)
    signature = Account.sign_message(encode_defunct(text=signed_message), account.key).signature.hex()
    return build_native_transaction(
        network=message.network, transaction_version=PROTOCOL_VERSION, protocol_version=PROTOCOL_VERSION,
        network_id=message.network_id, from_address=message.from_address, to_address=message.to_address,
        amount=message.amount, fee=message.fee, nonce=message.nonce, memo=message.memo,
        timestamp=message.timestamp, signature=signature, signature_scheme="personal_sign",
        signed_message=signed_message, signed_message_hash=hash_transfer_signing_message(signed_message),
        status="signed_pending", created_at=message.timestamp, updated_at=message.timestamp,
    ).to_dict()


def _admit(chain, transaction):
    chain.record_native_transaction(transaction, status="signed_pending")
    chain.save_blockchain()
    return chain.admit_native_transaction_operation(transaction["tx_id"], origin_node_id="node-a", network_name=NETWORK)


def _worker(chain, store, transport, clock, *, batch_size=1):
    return NativeTransactionDeliveryWorker(
        chain, store, origin_node_id="node-a", network_name=NETWORK,
        transport_factory=lambda: transport, request_headers=peer_sync.build_peer_request_headers,
        retry_policy=NativeTransactionRetryPolicy(initial_delay_seconds=2, maximum_delay_seconds=5),
        timeout_seconds=1, lease_seconds=2, batch_size=batch_size, reconciliation_batch_size=10,
        reconciliation_interval_seconds=60, now=lambda: clock[0],
    )


def test_backoff_is_persisted_grows_and_caps_without_attempt_limit(isolated_data_dir):
    backend = _backend(isolated_data_dir, "backoff")
    chain = _chain(backend)
    peers = PeerStore(storage_backend=backend)
    peers.register_peer("node-b", "http://node-b.test", NETWORK)
    account = Account.create(); fund_native_wallet_with_block(chain, account.address, persist=True)
    transaction = _signed(account); _admit(chain, transaction)
    clock = [datetime(2026, 9, 5, 17, 0, tzinfo=timezone.utc)]

    class Offline:
        request_error = requests.RequestException
        @staticmethod
        def post(*_args, **_kwargs):
            raise requests.RequestException("offline")

    worker = _worker(chain, peers, Offline(), clock)
    worker.process_once(force_reconciliation=True)
    first = backend.list_native_transaction_outbox()[0]
    assert first["attempt_count"] == 1
    assert first["next_attempt_at"] == "2026-09-05T17:00:02+00:00"
    clock[0] += timedelta(seconds=2)
    worker.process_once()
    second = backend.list_native_transaction_outbox()[0]
    assert second["attempt_count"] == 2
    assert second["next_attempt_at"] == "2026-09-05T17:00:06+00:00"
    clock[0] += timedelta(seconds=4)
    worker.process_once()
    assert backend.list_native_transaction_outbox()[0]["next_attempt_at"] == "2026-09-05T17:00:11+00:00"
    reopened = _backend(isolated_data_dir, "backoff").list_native_transaction_outbox()[0]
    assert reopened["delivery_state"] == "retry_wait" and reopened["attempt_count"] == 3


def test_lost_ack_retries_to_durable_idempotent_receiver_admission(isolated_data_dir):
    sender_backend, receiver_backend = _backend(isolated_data_dir, "sender"), _backend(isolated_data_dir, "receiver")
    sender, receiver = _chain(sender_backend), _chain(receiver_backend)
    sender_peers, receiver_peers = PeerStore(storage_backend=sender_backend), PeerStore(storage_backend=receiver_backend)
    sender_peers.register_peer("node-b", "http://node-b.test", NETWORK)
    receiver_peers.register_peer("node-a", "http://node-a.test", NETWORK)
    account = Account.create()
    fund_native_wallet_with_block(sender, account.address, persist=True)
    fund_native_wallet_with_block(receiver, account.address, persist=True)
    transaction = _signed(account); _admit(sender, transaction)
    clock = [datetime(2026, 9, 5, 17, 0, tzinfo=timezone.utc)]

    class Response:
        status_code = 200
        text = "ok"
        def __init__(self, body): self.body = body
        def json(self): return self.body

    class LostAckThenLoopback:
        request_error = requests.RequestException
        calls = 0
        def post(self, _url, *, json, **_kwargs):
            self.calls += 1
            body = peer_sync.receive_peer_transaction(receiver, receiver_peers, "node-a", NETWORK, json["transaction"], NETWORK, peer_message=json)
            if self.calls == 1:
                raise requests.RequestException("ACK lost after durable admission")
            return Response(body)

    transport = LostAckThenLoopback(); worker = _worker(sender, sender_peers, transport, clock)
    worker.process_once(force_reconciliation=True)
    assert receiver_backend.get_durable_native_transaction_record(transaction["tx_id"])["status"] == "mempool"
    assert sender_backend.list_native_transaction_outbox()[0]["delivery_state"] == "retry_wait"
    clock[0] += timedelta(seconds=2)
    worker.process_once()
    row = sender_backend.list_native_transaction_outbox()[0]
    assert row["delivery_state"] == "acknowledged" and transport.calls == 2
    assert len(receiver_backend.list_durable_native_transaction_records()) == 1


def test_both_node_restarts_resume_offline_delivery_in_two_simulated_seconds(isolated_data_dir):
    sender_backend, receiver_backend = _backend(isolated_data_dir, "restart-sender"), _backend(isolated_data_dir, "restart-receiver")
    sender, receiver = _chain(sender_backend), _chain(receiver_backend)
    sender_peers, receiver_peers = PeerStore(storage_backend=sender_backend), PeerStore(storage_backend=receiver_backend)
    sender_peers.register_peer("node-b", "http://node-b.test", NETWORK)
    receiver_peers.register_peer("node-a", "http://node-a.test", NETWORK)
    account = Account.create()
    fund_native_wallet_with_block(sender, account.address, persist=True)
    fund_native_wallet_with_block(receiver, account.address, persist=True)
    transaction = _signed(account); _admit(sender, transaction)
    clock = [datetime(2026, 9, 5, 17, 0, tzinfo=timezone.utc)]

    class Offline:
        request_error = requests.RequestException
        @staticmethod
        def post(*_args, **_kwargs): raise requests.RequestException("offline")

    _worker(sender, sender_peers, Offline(), clock).process_once(force_reconciliation=True)
    assert sender_backend.list_native_transaction_outbox()[0]["delivery_state"] == "retry_wait"

    # Both persisted state machines are reconstructed before peer B returns.
    sender = _chain(_backend(isolated_data_dir, "restart-sender"))
    receiver = _chain(_backend(isolated_data_dir, "restart-receiver"))
    sender_peers, receiver_peers = PeerStore(storage_backend=sender.storage), PeerStore(storage_backend=receiver.storage)
    # A process restart alone does not erase or prematurely wake backoff.
    assert _worker(sender, sender_peers, Offline(), clock).process_once(force_reconciliation=True)["attempted"] == 0
    clock[0] += timedelta(seconds=2)

    class Response:
        status_code = 200
        text = "ok"
        def __init__(self, body): self.body = body
        def json(self): return self.body

    class Reconnected:
        request_error = requests.RequestException
        @staticmethod
        def post(_url, *, json, **_kwargs):
            return Response(peer_sync.receive_peer_transaction(receiver, receiver_peers, "node-a", NETWORK, json["transaction"], NETWORK, peer_message=json))

    _worker(sender, sender_peers, Reconnected(), clock).process_once(force_reconciliation=True)
    row = sender.storage.list_native_transaction_outbox(tx_id=transaction["tx_id"])[0]
    assert row["delivery_state"] == "acknowledged"
    assert receiver.get_mempool_transaction(transaction["tx_id"]) is not None


def test_new_peer_gets_only_current_pending_backfill_and_url_change_reuses_row(isolated_data_dir):
    sender_backend, receiver_backend = _backend(isolated_data_dir, "future-sender"), _backend(isolated_data_dir, "future-receiver")
    sender, receiver = _chain(sender_backend), _chain(receiver_backend)
    sender_peers, receiver_peers = PeerStore(storage_backend=sender_backend), PeerStore(storage_backend=receiver_backend)
    account = Account.create()
    fund_native_wallet_with_block(sender, account.address, persist=True)
    fund_native_wallet_with_block(receiver, account.address, persist=True)
    transaction = _signed(account); _admit(sender, transaction)
    assert sender_backend.list_native_transaction_outbox() == []
    sender_peers.register_peer("node-b", "http://node-b.test", NETWORK)
    receiver_peers.register_peer("node-a", "http://node-a.test", NETWORK)
    clock = [datetime(2026, 9, 5, 17, 0, tzinfo=timezone.utc)]

    class Response:
        status_code = 200
        text = "ok"
        def __init__(self, body): self.body = body
        def json(self): return self.body

    class Loopback:
        request_error = requests.RequestException
        @staticmethod
        def post(_url, *, json, **_kwargs):
            return Response(peer_sync.receive_peer_transaction(receiver, receiver_peers, "node-a", NETWORK, json["transaction"], NETWORK, peer_message=json))

    worker = _worker(sender, sender_peers, Loopback(), clock)
    worker.process_once(force_reconciliation=True)
    assert receiver.get_mempool_transaction(transaction["tx_id"]) is not None
    assert sender_backend.list_native_transaction_outbox()[0]["delivery_state"] == "acknowledged"
    sender_peers.register_peer("node-b", "http://node-b-new.test", NETWORK)
    worker.reconcile_pending_transactions(force=True)
    rows = sender_backend.list_native_transaction_outbox(tx_id=transaction["tx_id"])
    # The settled delivery remains terminal; re-registration must not create a
    # second logical row for the same message/node identity.
    assert len(rows) == 1 and rows[0]["delivery_state"] == "acknowledged"


def test_permanent_failure_is_never_claimed_by_worker(isolated_data_dir):
    backend = _backend(isolated_data_dir, "permanent")
    chain = _chain(backend); peers = PeerStore(storage_backend=backend)
    peers.register_peer("node-b", "http://node-b.test", NETWORK)
    account = Account.create(); fund_native_wallet_with_block(chain, account.address, persist=True)
    transaction = _signed(account); _admit(chain, transaction)
    claimed = backend.claim_native_transaction_outbox(now="2026-09-05T17:00:00+00:00")
    backend.fail_native_transaction_outbox(outbox_id=claimed["outbox_id"], claim_token=claimed["claim_token"], error_code="wrong_network", permanent=True)
    clock = [datetime(2026, 9, 5, 18, 0, tzinfo=timezone.utc)]
    class NoNetwork: request_error = requests.RequestException
    assert _worker(chain, peers, NoNetwork(), clock).process_once()["attempted"] == 0


def test_removed_peer_is_not_retried_as_a_temporary_transport_failure(isolated_data_dir):
    backend = _backend(isolated_data_dir, "removed")
    chain = _chain(backend); peers = PeerStore(storage_backend=backend)
    peers.register_peer("node-b", "http://node-b.test", NETWORK)
    account = Account.create(); fund_native_wallet_with_block(chain, account.address, persist=True)
    transaction = _signed(account); _admit(chain, transaction)
    stored_peers = peers.list_peers(); stored_peers[0]["status"] = "inactive"; backend.save_peers(stored_peers)
    clock = [datetime(2026, 9, 5, 18, 0, tzinfo=timezone.utc)]
    class NoNetwork: request_error = requests.RequestException
    report = _worker(chain, peers, NoNetwork(), clock).process_once(force_reconciliation=True)
    row = backend.list_native_transaction_outbox()[0]
    assert report["results"][0]["error"] == "peer_inactive_or_removed"
    assert row["delivery_state"] == "permanent_failure"


def test_exact_already_settled_peer_transaction_returns_durable_idempotent_ack(isolated_data_dir):
    backend = _backend(isolated_data_dir, "already-settled")
    receiver = _chain(backend); peers = PeerStore(storage_backend=backend)
    peers.register_peer("node-a", "http://node-a.test", NETWORK)
    account = Account.create(); transaction = _signed(account)
    receiver.record_native_transaction(transaction, status="signed_pending")
    receiver.update_native_transaction_status(
        transaction["tx_id"], status="settled", included_block_hash="a" * 64,
        included_block_height=1, settled_at="2026-09-05T17:00:00+00:00",
    )
    receiver.save_blockchain()
    message = peer_sync.build_native_transaction_peer_message(transaction, sender_node_id="node-a", network_name=NETWORK)

    result = peer_sync.receive_peer_transaction(
        receiver, peers, "node-a", NETWORK, transaction, NETWORK, peer_message=message,
    )

    assert result["ack"]["status"] == "acknowledged"
    assert result["ack"]["duplicate"] is True
    assert backend.get_received_native_transaction_message(message["message_id"])["tx_id"] == transaction["tx_id"]


def test_nonce_state_rejections_remain_retryable_across_restart_without_duplicate_rows(isolated_data_dir):
    backend = _backend(isolated_data_dir, "state-dependent-nonce")
    sender = _chain(backend); peers = PeerStore(storage_backend=backend)
    peers.register_peer("node-b", "http://node-b.test", NETWORK)
    account = Account.create(); fund_native_wallet_with_block(sender, account.address, persist=True)
    transaction = _signed(account); _admit(sender, transaction)
    clock = [datetime(2026, 9, 5, 18, 0, tzinfo=timezone.utc)]

    class Response:
        status_code = 409
        text = "current peer nonce reservation"
        @staticmethod
        def json(): return {"accepted": False, "reason": "conflicting_nonce", "message": "pending conflict"}

    class StateDependentConflict:
        request_error = requests.RequestException
        @staticmethod
        def post(*_args, **_kwargs): return Response()

    _worker(sender, peers, StateDependentConflict(), clock).process_once(force_reconciliation=True)
    row = backend.list_native_transaction_outbox()[0]
    assert row["delivery_state"] == "retry_wait"
    assert row["last_error_code"] == "conflicting_nonce"
    assert len(_backend(isolated_data_dir, "state-dependent-nonce").list_native_transaction_outbox()) == 1
    assert classify_delivery_response(400, {"reason": "stale_nonce"})[0] == "retry"
    assert classify_delivery_response(409, {"reason": "conflicting_nonce"})[0] == "retry"
    # A peer-local assertion of finality is not authenticated finality evidence.
    assert classify_delivery_response(409, {"reason": "conflicting_nonce", "finalized": True})[0] == "retry"
    assert classify_delivery_response(400, {"reason": "future_nonce"})[0] == "retry"
    assert classify_delivery_response(400, {"reason": "insufficient_available_balance"})[0] == "retry"
    assert classify_delivery_response(400, {"reason": "invalid_signature"})[0] == "permanent"
