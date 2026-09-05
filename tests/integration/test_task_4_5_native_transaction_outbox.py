import sqlite3

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
from services.native_transaction_outbox_service import (
    build_native_transaction_outbox_records,
    build_native_transaction_peer_message,
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


def _blockchain(backend):
    return Blockchain(Wallet(), Wallet(), Wallet(), storage_backend=backend)


def _signed_transaction(account, *, nonce="1", amount="4", memo="task 4.5"):
    message = NativeTransferMessage(
        action="transfer_zoid",
        network=NETWORK,
        from_address=account.address.lower(),
        to_address=Account.create().address.lower(),
        amount=amount,
        nonce=nonce,
        fee="0",
        timestamp="2026-09-05T16:00:00+00:00",
        memo=memo,
        status="signed_pending",
        transaction_version=PROTOCOL_VERSION,
        protocol_version=PROTOCOL_VERSION,
        network_id=resolve_protocol_v1_network_id(network_name=NETWORK),
    )
    signed_message = build_transfer_signing_message(message)
    signature = Account.sign_message(
        encode_defunct(text=signed_message), account.key
    ).signature.hex()
    return build_native_transaction(
        network=message.network,
        transaction_version=PROTOCOL_VERSION,
        protocol_version=PROTOCOL_VERSION,
        network_id=message.network_id,
        from_address=message.from_address,
        to_address=message.to_address,
        amount=message.amount,
        fee=message.fee,
        nonce=message.nonce,
        memo=message.memo,
        timestamp=message.timestamp,
        signature=signature,
        signature_scheme="personal_sign",
        signed_message=signed_message,
        signed_message_hash=hash_transfer_signing_message(signed_message),
        status="signed_pending",
        created_at=message.timestamp,
        updated_at=message.timestamp,
    ).to_dict()


def _stage_local_transaction(blockchain, transaction):
    blockchain.record_native_transaction(transaction, status="signed_pending")
    blockchain.save_blockchain()


def _register(store, node_id, url):
    return store.register_peer(node_id=node_id, url=url, network_name=NETWORK)


def _admit_local(blockchain, transaction, *, node_id="node-a"):
    _stage_local_transaction(blockchain, transaction)
    return blockchain.admit_native_transaction_operation(
        transaction["tx_id"], origin_node_id=node_id, network_name=NETWORK
    )


def test_local_admission_atomically_creates_one_outbox_row_per_active_peer_and_survives_restart(
    isolated_data_dir,
):
    backend = _backend(isolated_data_dir, "sender")
    blockchain = _blockchain(backend)
    store = PeerStore(storage_backend=backend)
    _register(store, "peer-b", "http://peer-b.test")
    _register(store, "peer-c", "http://peer-c.test")
    peers = store.list_peers()
    peers[1]["status"] = "inactive"
    backend.save_peers(peers)
    account = Account.create()
    fund_native_wallet_with_block(blockchain, account.address, persist=True)
    transaction = _signed_transaction(account)

    _admit_local(blockchain, transaction)
    first_rows = backend.list_native_transaction_outbox(tx_id=transaction["tx_id"])
    reopened = _backend(isolated_data_dir, "sender")
    reopened_rows = reopened.list_native_transaction_outbox(tx_id=transaction["tx_id"])

    assert blockchain.get_mempool_transaction(transaction["tx_id"]) is not None
    assert len(first_rows) == len(reopened_rows) == 1
    assert reopened_rows[0]["destination_peer_id"] == "peer-b"
    assert reopened_rows[0]["delivery_state"] == "queued"
    assert reopened_rows[0]["message"]["transaction"]["tx_id"] == transaction["tx_id"]
    assert "admitted_at" not in reopened_rows[0]["message"]["transaction"]


def test_repeated_enqueue_is_idempotent_and_database_unique_constraint_rejects_duplicate(
    isolated_data_dir,
):
    backend = _backend(isolated_data_dir, "unique")
    blockchain = _blockchain(backend)
    account = Account.create()
    fund_native_wallet_with_block(blockchain, account.address, persist=True)
    transaction = _signed_transaction(account)
    _stage_local_transaction(blockchain, transaction)
    records = build_native_transaction_outbox_records(
        transaction,
        [{"node_id": "peer-b", "url": "http://peer-b.test", "network_name": NETWORK, "status": "active"}],
        sender_node_id="node-a",
        network_name=NETWORK,
    )

    backend.enqueue_native_transaction_outbox(records)
    backend.enqueue_native_transaction_outbox(records)
    assert len(backend.list_native_transaction_outbox()) == 1

    row = records[0]
    with pytest.raises(sqlite3.IntegrityError):
        with backend._connect() as connection:
            connection.execute(
                """INSERT INTO native_transaction_peer_outbox
                   (outbox_id, message_id, message_type, tx_id, destination_peer_id,
                    destination_peer_url, serialized_message, delivery_state,
                    attempt_count, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', 0, ?)""",
                (
                    "f" * 64, row["message_id"], row["message_type"], row["tx_id"],
                    row["destination_peer_id"], row["destination_peer_url"],
                    row["serialized_message"], row["created_at"],
                ),
            )


def test_outbox_failure_rolls_back_local_admission_and_enqueue_together(
    isolated_data_dir, monkeypatch
):
    backend = _backend(isolated_data_dir, "atomic")
    blockchain = _blockchain(backend)
    store = PeerStore(storage_backend=backend)
    _register(store, "peer-b", "http://peer-b.test")
    account = Account.create()
    fund_native_wallet_with_block(blockchain, account.address, persist=True)
    transaction = _signed_transaction(account)
    _stage_local_transaction(blockchain, transaction)

    def fail_enqueue(_connection, _records):
        raise RuntimeError("injected outbox failure")

    monkeypatch.setattr(backend, "_insert_native_transaction_outbox_records", fail_enqueue)
    with pytest.raises(RuntimeError, match="injected outbox failure"):
        blockchain.admit_native_transaction_operation(
            transaction["tx_id"], origin_node_id="node-a", network_name=NETWORK
        )

    durable = backend.get_durable_native_transaction_record(transaction["tx_id"])
    assert durable["status"] == "signed_pending"
    assert backend.list_native_transaction_outbox() == []


def test_offline_active_peer_does_not_block_local_admission(isolated_data_dir):
    backend = _backend(isolated_data_dir, "offline")
    blockchain = _blockchain(backend)
    store = PeerStore(storage_backend=backend)
    _register(store, "offline-peer", "http://127.0.0.1:1")
    account = Account.create()
    fund_native_wallet_with_block(blockchain, account.address, persist=True)
    transaction = _signed_transaction(account)

    result = _admit_local(blockchain, transaction)

    assert result["status"] == "mempool"
    assert backend.list_native_transaction_outbox()[0]["delivery_state"] == "queued"


def test_claim_is_exclusive_expired_claim_is_recoverable_and_acknowledged_is_not_claimable(
    isolated_data_dir,
):
    backend = _backend(isolated_data_dir, "claim")
    blockchain = _blockchain(backend)
    store = PeerStore(storage_backend=backend)
    _register(store, "peer-b", "http://peer-b.test")
    account = Account.create()
    fund_native_wallet_with_block(blockchain, account.address, persist=True)
    transaction = _signed_transaction(account)
    _admit_local(blockchain, transaction)

    first = backend.claim_native_transaction_outbox(
        now="2026-09-05T17:00:00+00:00", lease_seconds=1
    )
    competing_backend = _backend(isolated_data_dir, "claim")
    assert competing_backend.claim_native_transaction_outbox(
        now="2026-09-05T17:00:00+00:00"
    ) is None
    recovered = competing_backend.claim_native_transaction_outbox(
        now="2026-09-05T17:00:02+00:00"
    )
    assert recovered["outbox_id"] == first["outbox_id"]
    assert recovered["claim_token"] != first["claim_token"]
    assert recovered["attempt_count"] == 2

    assert competing_backend.acknowledge_native_transaction_outbox(
        message_id=recovered["message_id"],
        destination_peer_id="peer-b",
        tx_id=transaction["tx_id"],
        claim_token=recovered["claim_token"],
    ) is True
    assert competing_backend.acknowledge_native_transaction_outbox(
        message_id=recovered["message_id"],
        destination_peer_id="peer-b",
        tx_id=transaction["tx_id"],
    ) is True
    assert competing_backend.claim_native_transaction_outbox() is None
    assert _backend(isolated_data_dir, "claim").list_native_transaction_outbox()[0]["delivery_state"] == "acknowledged"


def test_unknown_or_nonmatching_ack_cannot_acknowledge_delivery(isolated_data_dir):
    backend = _backend(isolated_data_dir, "ack-match")
    blockchain = _blockchain(backend)
    store = PeerStore(storage_backend=backend)
    _register(store, "peer-b", "http://peer-b.test")
    account = Account.create()
    fund_native_wallet_with_block(blockchain, account.address, persist=True)
    transaction = _signed_transaction(account)
    _admit_local(blockchain, transaction)
    claimed = backend.claim_native_transaction_outbox()

    assert backend.acknowledge_native_transaction_outbox(
        message_id="0" * 64, destination_peer_id="peer-b",
        tx_id=transaction["tx_id"], claim_token=claimed["claim_token"],
    ) is False
    assert backend.acknowledge_native_transaction_outbox(
        message_id=claimed["message_id"], destination_peer_id="peer-b",
        tx_id="f" * 64, claim_token=claimed["claim_token"],
    ) is False
    assert backend.get_native_transaction_outbox(outbox_id=claimed["outbox_id"])["delivery_state"] == "in_flight"


def test_receiver_durably_records_message_and_duplicate_survives_restart(isolated_data_dir):
    backend = _backend(isolated_data_dir, "receiver")
    blockchain = _blockchain(backend)
    store = PeerStore(storage_backend=backend)
    _register(store, "node-a", "http://node-a.test")
    account = Account.create()
    fund_native_wallet_with_block(blockchain, account.address, persist=True)
    transaction = _signed_transaction(account)
    message = build_native_transaction_peer_message(
        transaction, sender_node_id="node-a", network_name=NETWORK
    )

    first = peer_sync.receive_peer_transaction(
        blockchain, store, "node-a", NETWORK, transaction, NETWORK,
        peer_message=message,
    )
    reopened_backend = _backend(isolated_data_dir, "receiver")
    reopened_blockchain = _blockchain(reopened_backend)
    reopened_store = PeerStore(storage_backend=reopened_backend)
    duplicate = peer_sync.receive_peer_transaction(
        reopened_blockchain, reopened_store, "node-a", NETWORK, transaction, NETWORK,
        peer_message=message,
    )

    assert first["ack"]["status"] == "acknowledged"
    assert first["duplicate"] is False
    assert duplicate["duplicate"] is True
    assert duplicate["ack"]["message_id"] == message["message_id"]
    assert reopened_backend.get_received_native_transaction_message(message["message_id"])["tx_id"] == transaction["tx_id"]
    assert reopened_backend.get_durable_native_transaction_record(transaction["tx_id"])["status"] == "mempool"


def test_receiver_cannot_ack_when_durable_dedup_commit_fails(
    isolated_data_dir, monkeypatch
):
    backend = _backend(isolated_data_dir, "receiver-failure")
    blockchain = _blockchain(backend)
    store = PeerStore(storage_backend=backend)
    _register(store, "node-a", "http://node-a.test")
    account = Account.create()
    fund_native_wallet_with_block(blockchain, account.address, persist=True)
    transaction = _signed_transaction(account)
    message = build_native_transaction_peer_message(
        transaction, sender_node_id="node-a", network_name=NETWORK
    )

    def fail_dedup(_connection, _record):
        raise RuntimeError("injected receiver persistence failure")

    monkeypatch.setattr(backend, "_insert_received_native_transaction_message", fail_dedup)
    with pytest.raises(RuntimeError, match="injected receiver persistence failure"):
        peer_sync.receive_peer_transaction(
            blockchain, store, "node-a", NETWORK, transaction, NETWORK,
            peer_message=message,
        )

    assert backend.get_durable_native_transaction_record(transaction["tx_id"]) is None
    assert backend.get_received_native_transaction_message(message["message_id"]) is None


def test_conflicting_message_id_and_conflicting_tx_payload_fail_deterministically(isolated_data_dir):
    backend = _backend(isolated_data_dir, "conflicts")
    blockchain = _blockchain(backend)
    store = PeerStore(storage_backend=backend)
    _register(store, "node-a", "http://node-a.test")
    account = Account.create()
    fund_native_wallet_with_block(blockchain, account.address, persist=True)
    first_tx = _signed_transaction(account, nonce="1", memo="first")
    first_message = build_native_transaction_peer_message(
        first_tx, sender_node_id="node-a", network_name=NETWORK
    )
    peer_sync.receive_peer_transaction(
        blockchain, store, "node-a", NETWORK, first_tx, NETWORK,
        peer_message=first_message,
    )

    second_tx = _signed_transaction(account, nonce="2", memo="second")
    conflicting_message = build_native_transaction_peer_message(
        second_tx, sender_node_id="node-a", network_name=NETWORK
    )
    conflicting_message["message_id"] = first_message["message_id"]
    with pytest.raises(peer_sync.ConflictingPeerMessageError, match="message_id does not match"):
        peer_sync.receive_peer_transaction(
            blockchain, store, "node-a", NETWORK, second_tx, NETWORK,
            peer_message=conflicting_message,
        )

    conflicting_tx = dict(first_tx, memo="changed but tx_id reused")
    with pytest.raises(peer_sync.MalformedTransactionError, match="tx_id does not match"):
        peer_sync.receive_peer_transaction(
            blockchain, store, "node-a", NETWORK, conflicting_tx, NETWORK,
            peer_message=first_message,
        )


def test_wrong_network_message_fails_before_admission(isolated_data_dir):
    backend = _backend(isolated_data_dir, "wrong-network")
    blockchain = _blockchain(backend)
    store = PeerStore(storage_backend=backend)
    _register(store, "node-a", "http://node-a.test")
    account = Account.create()
    fund_native_wallet_with_block(blockchain, account.address, persist=True)
    transaction = _signed_transaction(account)
    message = build_native_transaction_peer_message(
        transaction, sender_node_id="node-a", network_name=NETWORK
    )
    message["network_id"] = "wrong-network-id"

    with pytest.raises(peer_sync.WrongNetworkError, match="network_id"):
        peer_sync.receive_peer_transaction(
            blockchain, store, "node-a", NETWORK, transaction, NETWORK,
            peer_message=message,
        )
    assert backend.get_durable_native_transaction_record(transaction["tx_id"]) is None


def test_two_nodes_deliver_admit_restart_ack_and_do_not_duplicate(isolated_data_dir, monkeypatch):
    sender_backend = _backend(isolated_data_dir, "node-a")
    receiver_backend = _backend(isolated_data_dir, "node-b")
    sender = _blockchain(sender_backend)
    receiver = _blockchain(receiver_backend)
    sender_peers = PeerStore(storage_backend=sender_backend)
    receiver_peers = PeerStore(storage_backend=receiver_backend)
    _register(sender_peers, "node-b", "http://node-b.test")
    _register(receiver_peers, "node-a", "http://node-a.test")
    account = Account.create()
    fund_native_wallet_with_block(sender, account.address, persist=True)
    fund_native_wallet_with_block(receiver, account.address, persist=True)
    transaction = _signed_transaction(account)
    _admit_local(sender, transaction, node_id="node-a")

    class Response:
        status_code = 200
        text = "ok"

        def __init__(self, body):
            self._body = body

        def json(self):
            return self._body

    class LoopbackTransport:
        request_error = requests.RequestException

        def post(self, _url, *, json, headers=None, timeout=None):
            assert headers is not None
            assert timeout == 3
            body = peer_sync.receive_peer_transaction(
                receiver, receiver_peers, "node-a", NETWORK,
                json["transaction"], NETWORK, peer_message=json,
            )
            return Response(body)

    monkeypatch.setattr(peer_sync, "_peer_http_transport", lambda: LoopbackTransport())
    report = peer_sync.broadcast_transaction_to_peers(
        sender, transaction["tx_id"], sender_peers, "node-a", NETWORK
    )

    assert report["accepted"] == 1
    outbox = sender_backend.list_native_transaction_outbox()[0]
    assert outbox["delivery_state"] == "acknowledged"
    assert receiver_backend.get_durable_native_transaction_record(transaction["tx_id"])["status"] == "mempool"
    restarted_receiver = _blockchain(_backend(isolated_data_dir, "node-b"))
    assert restarted_receiver.get_mempool_transaction(transaction["tx_id"]) is not None
    duplicate = peer_sync.receive_peer_transaction(
        restarted_receiver,
        PeerStore(storage_backend=restarted_receiver.storage),
        "node-a", NETWORK, transaction, NETWORK,
        peer_message=outbox["message"],
    )
    assert duplicate["duplicate"] is True
    assert len(restarted_receiver.storage.list_durable_native_transaction_records()) == 1
    assert sender_backend.claim_native_transaction_outbox(tx_id=transaction["tx_id"]) is None


def test_permanent_rejection_is_not_recorded_as_ack(isolated_data_dir, monkeypatch):
    backend = _backend(isolated_data_dir, "reject")
    blockchain = _blockchain(backend)
    store = PeerStore(storage_backend=backend)
    _register(store, "peer-b", "http://peer-b.test")
    account = Account.create()
    fund_native_wallet_with_block(blockchain, account.address, persist=True)
    transaction = _signed_transaction(account)
    _admit_local(blockchain, transaction)

    class Rejection:
        status_code = 400
        text = "invalid signature"

        @staticmethod
        def json():
            return {"accepted": False, "reason": "invalid_signature", "message": "invalid signature"}

    class RejectingTransport:
        request_error = requests.RequestException

        @staticmethod
        def post(*_args, **_kwargs):
            return Rejection()

    monkeypatch.setattr(peer_sync, "_peer_http_transport", lambda: RejectingTransport())
    report = peer_sync.broadcast_transaction_to_peers(
        blockchain, transaction["tx_id"], store, "node-a", NETWORK
    )

    row = backend.list_native_transaction_outbox()[0]
    assert report["accepted"] == 0
    assert row["delivery_state"] == "permanent_failure"
    assert row["acknowledged_at"] is None
    assert row["last_error_code"] == "invalid_signature"
