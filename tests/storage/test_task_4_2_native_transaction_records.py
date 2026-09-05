import json
import sqlite3

import pytest

from services.native_ledger_service import NativeLedgerService
from storage import SQLiteStorageBackend, StorageUniquenessError


def _backend(base_dir, name="task-4-2"):
    return SQLiteStorageBackend(sqlite_db_path=str(base_dir / name / "zoidbergchain.db"))


def _transaction(tx_id="a" * 64, *, nonce="1", status="signed_pending", amount="1"):
    return {
        "tx_id": tx_id,
        "transaction_type": "native_transfer",
        "network": "zoidberg-testnet",
        "transaction_version": 1,
        "protocol_version": 1,
        "network_id": "zoidbergchain:testnet:v1",
        "from_address": "0x" + ("1" * 40),
        "to_address": "0x" + ("2" * 40),
        "amount": amount,
        "fee": "0",
        "nonce": nonce,
        "memo": "durable record",
        "timestamp": "2026-09-05T12:00:00+00:00",
        "signature": "0x" + ("a" * 130),
        "signature_scheme": "personal_sign",
        "signed_message": "canonical signed message",
        "signed_message_hash": "b" * 64,
        "status": status,
        "created_at": "2026-09-05T12:00:00+00:00",
        "updated_at": "2026-09-05T12:00:00+00:00",
        "admitted_at": None,
        "included_block_hash": None,
        "included_block_height": None,
        "settled_at": None,
        "rejection_reason": None,
    }


def _native_row_count(backend):
    with sqlite3.connect(backend.sqlite_db_path) as connection:
        return connection.execute("SELECT COUNT(*) FROM native_transaction_records").fetchone()[0]


def test_task_4_2_sqlite_record_round_trip_restart_and_rejection_reason(isolated_data_dir):
    backend = _backend(isolated_data_dir, "round-trip")
    transaction = _transaction(status="rejected")
    transaction["rejection_reason"] = "insufficient_available_balance"
    backend.save_native_transactions([transaction])

    reopened = SQLiteStorageBackend(sqlite_db_path=backend.sqlite_db_path)
    assert reopened.list_durable_native_transaction_records() == [transaction]
    assert reopened.get_durable_native_transaction_record(transaction["tx_id"]) == transaction
    assert reopened.load_native_transactions() == [transaction]
    assert _native_row_count(reopened) == 1


def test_task_4_2_tx_id_identity_is_database_enforced_and_conflicts_fail(isolated_data_dir):
    backend = _backend(isolated_data_dir, "identity")
    transaction = _transaction()
    backend.save_native_transactions([transaction, dict(transaction)])
    assert _native_row_count(backend) == 1

    with pytest.raises(StorageUniquenessError, match="conflicting signed payloads"):
        backend.save_native_transactions([transaction, dict(transaction, amount="2")])

    with sqlite3.connect(backend.sqlite_db_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO native_transaction_records (tx_id, immutable_payload, transaction_json, sender, nonce, lifecycle_state, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (transaction["tx_id"], "different", "{}", transaction["from_address"], transaction["nonce"], "rejected", transaction["created_at"], transaction["updated_at"]),
            )


def test_task_4_2_active_sender_nonce_constraint_and_release(isolated_data_dir):
    backend = _backend(isolated_data_dir, "nonce")
    first = _transaction()
    conflicting = _transaction("c" * 64)
    with pytest.raises(sqlite3.IntegrityError):
        backend.save_native_transactions([first, conflicting])

    sequential = _transaction("d" * 64, nonce="2")
    backend.save_native_transactions([first, sequential])
    assert _native_row_count(backend) == 2

    rejected = dict(first, status="rejected", rejection_reason="validation_failed", updated_at="2026-09-05T12:01:00+00:00")
    replacement = _transaction("e" * 64)
    backend.save_native_transactions([rejected, sequential, replacement])
    assert {item["tx_id"] for item in backend.load_native_transactions()} == {rejected["tx_id"], sequential["tx_id"], replacement["tx_id"]}


def test_task_4_2_lifecycle_transitions_are_explicit_and_durable(isolated_data_dir):
    backend = _backend(isolated_data_dir, "lifecycle")
    transaction = _transaction()
    backend.save_native_transactions([transaction])
    mempool = dict(transaction, status="mempool", updated_at="2026-09-05T12:01:00+00:00", admitted_at="2026-09-05T12:01:00+00:00")
    backend.save_native_transactions([mempool])
    assert backend.list_native_transaction_lifecycle_transitions(transaction["tx_id"])[-1]["to_state"] == "mempool"

    with sqlite3.connect(backend.sqlite_db_path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="illegal native transaction lifecycle transition"):
            connection.execute("UPDATE native_transaction_records SET lifecycle_state = 'finalized' WHERE tx_id = ?", (transaction["tx_id"],))

    transitions = NativeLedgerService.native_transaction_lifecycle_transitions()
    for current, permitted in transitions.items():
        NativeLedgerService.validate_native_transaction_lifecycle_transition(current, current)
        for target in permitted:
            NativeLedgerService.validate_native_transaction_lifecycle_transition(current, target)
    with pytest.raises(ValueError, match="Illegal native transaction lifecycle transition"):
        NativeLedgerService.validate_native_transaction_lifecycle_transition("mempool", "finalized")


def _create_legacy_sqlite(path, native_transactions, *, chain=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE storage_sections (section_name TEXT PRIMARY KEY, json_data TEXT NOT NULL, updated_at TEXT NOT NULL)")
        connection.execute(
            "INSERT INTO storage_sections (section_name, json_data, updated_at) VALUES (?, ?, ?)",
            ("native_transactions", json.dumps(native_transactions), "2026-09-05T12:00:00+00:00"),
        )
        if chain is not None:
            connection.execute(
                "INSERT INTO storage_sections (section_name, json_data, updated_at) VALUES (?, ?, ?)",
                ("chain", json.dumps(chain), "2026-09-05T12:00:00+00:00"),
            )


def test_task_4_2_migrates_legacy_sqlite_section_idempotently_without_chain_loss(isolated_data_dir):
    path = isolated_data_dir / "legacy" / "zoidbergchain.db"
    transaction = _transaction()
    block_hash = "f" * 64
    _create_legacy_sqlite(path, [transaction], chain=[{"index": 1, "hash": block_hash, "native_transactions": [transaction]}])

    migrated = SQLiteStorageBackend(sqlite_db_path=str(path))
    assert migrated.load_native_transactions() == [transaction]
    assert _native_row_count(migrated) == 1
    assert SQLiteStorageBackend(sqlite_db_path=str(path)).load_native_transactions() == [transaction]
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT tx_id, block_hash FROM canonical_native_transaction_claims"
        ).fetchall() == [(transaction["tx_id"], block_hash)]


def test_task_4_2_rejects_conflicting_legacy_transaction_records(isolated_data_dir):
    path = isolated_data_dir / "legacy-conflict" / "zoidbergchain.db"
    transaction = _transaction()
    _create_legacy_sqlite(path, [transaction, dict(transaction, amount="2")])

    with pytest.raises(StorageUniquenessError, match="conflicting signed payloads"):
        SQLiteStorageBackend(sqlite_db_path=str(path))
