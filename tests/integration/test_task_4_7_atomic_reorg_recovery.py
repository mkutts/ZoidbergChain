"""Task 4.7 durable atomicity, lifecycle, claims, restart, and outbox tests."""

import sqlite3
from copy import deepcopy

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from block import Block
from blockchain import Blockchain
from native_transfer import (
    NativeTransferMessage,
    build_native_transaction,
    build_transfer_signing_message,
    hash_transfer_signing_message,
)
from protocol_v1 import PROTOCOL_VERSION
from protocol_v1_native_transfer import resolve_protocol_v1_network_id
from services import CanonicalReorgError, CanonicalReorgService, NativeLedgerService, NativeLedgerState
from services.native_transaction_outbox_service import build_native_transaction_outbox_records
from storage import SQLiteStorageBackend
from transaction import Transaction


GENESIS_HASH = "1" * 64


def _signed_transaction(account, *, amount="2", nonce="1", memo="task-4.7", recipient=None):
    network = "zoidberg-testnet"
    network_id = resolve_protocol_v1_network_id(network_name=network)
    recipient = (recipient or Account.create().address).lower()
    timestamp = f"2026-09-06T01:00:{int(nonce):02d}+00:00"
    fields = NativeTransferMessage(
        action="transfer_zoid", network=network,
        from_address=account.address.lower(), to_address=recipient,
        amount=amount, nonce=nonce, fee="0", timestamp=timestamp, memo=memo,
        transaction_version=PROTOCOL_VERSION, protocol_version=PROTOCOL_VERSION,
        network_id=network_id,
    )
    message = build_transfer_signing_message(fields)
    signature = Account.sign_message(encode_defunct(text=message), account.key).signature.hex()
    return build_native_transaction(
        network=network, transaction_version=PROTOCOL_VERSION,
        protocol_version=PROTOCOL_VERSION, network_id=network_id,
        from_address=fields.from_address, to_address=fields.to_address,
        amount=amount, fee="0", nonce=nonce, memo=memo, timestamp=timestamp,
        signature=signature, signature_scheme="personal_sign", signed_message=message,
        signed_message_hash=hash_transfer_signing_message(message),
        status="signed_pending", created_at=timestamp, updated_at=timestamp,
    ).to_dict()


def _block(height, block_hash, previous_hash, *, native=(), legacy=(), **extra):
    return {
        "index": height, "hash": block_hash, "previous_hash": previous_hash,
        "timestamp": float(height), "minted_at": f"2026-09-06T01:01:{height:02d}+00:00",
        "transactions": list(legacy), "native_transactions": list(native), **extra,
    }


def _settled(transaction, block):
    return {
        **deepcopy(transaction), "status": "settled",
        "included_block_hash": block["hash"], "included_block_height": block["index"],
        "settled_at": block["minted_at"], "updated_at": block["minted_at"],
    }


def _document(chain, records, *, peers=()):
    return {
        "chain": chain, "native_transactions": records, "transfer_intents": [],
        "submissions": [], "mint_queue": [], "originality_certificates": [],
        "finality_attestations": [], "finalized_blocks": [], "peers": list(peers),
    }


def _claim_rows(backend, table, columns):
    with sqlite3.connect(backend.sqlite_db_path) as connection:
        return connection.execute(
            f"SELECT {columns} FROM {table} ORDER BY 1"
        ).fetchall()


def test_sqlite_reorg_atomically_rebuilds_claims_lifecycle_mempool_and_outbox(isolated_data_dir):
    backend = SQLiteStorageBackend(
        sqlite_db_path=str(isolated_data_dir / "atomic-reorg" / "zoidbergchain.db")
    )
    ledger = NativeLedgerService()
    sender = Account.create()
    transaction = _signed_transaction(sender)
    genesis = _block(
        0, GENESIS_HASH, "0",
        legacy=[{"sender": "REWARD_POOL", "recipient": sender.address.lower(), "amount": 10, "tip": 0}],
    )
    losing = _block(1, "a" * 64, GENESIS_HASH, native=[transaction])
    winner = _block(1, "b" * 64, GENESIS_HASH)
    peer = {
        "node_id": "peer-1", "url": "http://peer.test:8000",
        "network_name": "zoidberg-testnet", "status": "active",
    }
    backend.save_blockchain_document(
        _document([genesis, losing], [_settled(transaction, losing)], peers=[peer])
    )
    outcome = {}

    def mutate(document):
        replacement, report = CanonicalReorgService.rebuild_document(
            document, [genesis, winner], ledger
        )
        outcome["report"] = report
        return replacement

    def outbox(document):
        requeued = set(outcome["report"]["requeued_transaction_ids"])
        return [
            record
            for item in document["native_transactions"] if item["tx_id"] in requeued
            for record in build_native_transaction_outbox_records(
                item, document["peers"], sender_node_id="local-node",
                network_name="zoidberg-testnet", created_at=item["admitted_at"],
            )
        ]

    replacement = backend.atomic_update_blockchain_document(mutate, outbox_records=outbox)

    assert replacement["chain"][-1]["hash"] == winner["hash"]
    assert replacement["native_transactions"][0]["status"] == "mempool"
    assert _claim_rows(backend, "canonical_native_transaction_claims", "tx_id") == []
    transitions = backend.list_native_transaction_lifecycle_transitions(transaction["tx_id"])
    assert [(item["from_state"], item["to_state"]) for item in transitions] == [
        (None, "settled"), ("settled", "mempool")
    ]
    assert len(backend.list_native_transaction_outbox(tx_id=transaction["tx_id"])) == 1

    reopened = SQLiteStorageBackend(sqlite_db_path=backend.sqlite_db_path)
    reopened_document = reopened.load_blockchain_document()
    assert reopened_document["chain"][-1]["hash"] == winner["hash"]
    assert reopened_document["native_transactions"][0]["status"] == "mempool"
    assert len(reopened.list_native_transaction_outbox(tx_id=transaction["tx_id"])) == 1
    assert _claim_rows(reopened, "canonical_native_transaction_claims", "tx_id") == []

    before = backend.load_blockchain_document()
    transition_count = len(transitions)
    repeated = backend.atomic_update_blockchain_document(
        lambda document: CanonicalReorgService.rebuild_document(
            document, [genesis, winner], ledger
        )[0],
        outbox_records=outbox,
    )
    assert repeated == before
    assert len(backend.list_native_transaction_lifecycle_transitions(transaction["tx_id"])) == transition_count
    assert len(backend.list_native_transaction_outbox(tx_id=transaction["tx_id"])) == 1


def test_sqlite_winning_nonce_swap_releases_loser_before_activating_winner(isolated_data_dir):
    backend = SQLiteStorageBackend(
        sqlite_db_path=str(isolated_data_dir / "nonce-swap" / "zoidbergchain.db")
    )
    ledger = NativeLedgerService()
    sender = Account.create()
    losing_tx = _signed_transaction(sender, memo="loser")
    winning_tx = _signed_transaction(sender, memo="winner")
    genesis = _block(
        0, GENESIS_HASH, "0",
        legacy=[{"sender": "REWARD_POOL", "recipient": sender.address.lower(), "amount": 10, "tip": 0}],
    )
    losing = _block(1, "a" * 64, GENESIS_HASH, native=[losing_tx])
    winner = _block(1, "b" * 64, GENESIS_HASH, native=[winning_tx])
    rejected_winner = {
        **winning_tx, "status": "rejected", "rejection_reason": "old_local_view"
    }
    backend.save_blockchain_document(
        _document([genesis, losing], [_settled(losing_tx, losing), rejected_winner])
    )

    replacement = backend.atomic_update_blockchain_document(
        lambda document: CanonicalReorgService.rebuild_document(
            document, [genesis, winner], ledger
        )[0]
    )
    by_id = {item["tx_id"]: item for item in replacement["native_transactions"]}

    assert by_id[losing_tx["tx_id"]]["status"] == "rejected"
    assert by_id[winning_tx["tx_id"]]["status"] == "settled"
    assert _claim_rows(
        backend, "canonical_native_transaction_claims", "tx_id, sender, nonce"
    ) == [(winning_tx["tx_id"], sender.address.lower(), "1")]


def test_sqlite_reward_claims_are_replaced_not_accumulated(isolated_data_dir):
    backend = SQLiteStorageBackend(
        sqlite_db_path=str(isolated_data_dir / "reward-reorg" / "zoidbergchain.db")
    )
    ledger = NativeLedgerService()
    genesis = _block(0, GENESIS_HASH, "0")
    losing = _block(
        1, "a" * 64, GENESIS_HASH, submission_id="loser-submission",
        certificate_id="loser-certificate", creator_wallet=Account.create().address.lower(),
        content_hash="2" * 64, reward_type="meme_mining_reward",
        reward_recipient=Account.create().address.lower(), reward_amount="5",
        voter_rewards=[{"reward_id": "loser-voter"}],
    )
    winner = _block(
        1, "b" * 64, GENESIS_HASH, submission_id="winner-submission",
        certificate_id="winner-certificate", creator_wallet=Account.create().address.lower(),
        content_hash="3" * 64, reward_type="meme_mining_reward",
        reward_recipient=Account.create().address.lower(), reward_amount="5",
        voter_rewards=[{"reward_id": "winner-voter"}],
    )
    backend.save_blockchain_document(_document([genesis, losing], []))

    backend.atomic_update_blockchain_document(
        lambda document: CanonicalReorgService.rebuild_document(
            document, [genesis, winner], ledger
        )[0]
    )

    assert _claim_rows(
        backend, "canonical_reward_claims", "reward_id, reward_kind"
    ) == [
        ("creator:winner-submission", "creator"),
        ("winner-voter", "voter"),
    ]


@pytest.mark.parametrize("failure_stage", ["during_reorg_rebuild", "before_reorg_commit"])
def test_sqlite_failure_before_commit_leaves_complete_old_state(isolated_data_dir, failure_stage):
    backend = SQLiteStorageBackend(
        sqlite_db_path=str(isolated_data_dir / failure_stage / "zoidbergchain.db")
    )
    ledger = NativeLedgerService()
    genesis = _block(0, GENESIS_HASH, "0")
    losing = _block(1, "a" * 64, GENESIS_HASH)
    winner = _block(1, "b" * 64, GENESIS_HASH)
    backend.save_blockchain_document(_document([genesis, losing], []))
    before = backend.load_blockchain_document()

    def fault(stage):
        if stage == failure_stage:
            raise RuntimeError(failure_stage)

    def mutate(document):
        replacement, _report = CanonicalReorgService.rebuild_document(
            document, [genesis, winner], ledger, fault=fault
        )
        fault("before_reorg_commit")
        return replacement

    with pytest.raises(RuntimeError, match=failure_stage):
        backend.atomic_update_blockchain_document(mutate)

    assert backend.load_blockchain_document() == before


def _competing_legacy_branches(blockchain, recipient):
    genesis = blockchain.chain[0]
    blocks = []
    for offset in range(2):
        timestamp = 2_000_000.0 + offset
        blocks.append(Block(
            index=1, previous_hash=genesis.hash, timestamp=timestamp,
            transactions=[Transaction("REWARD_POOL", recipient, 1, created_at=timestamp)],
            miner=recipient,
            meme={"encoded_image": f"branch-{offset}", "text": f"branch-{offset}"},
        ))
    winner, loser = sorted(blocks, key=lambda block: block.hash)
    return [genesis, loser], [genesis, winner]


def test_failure_after_durable_commit_keeps_old_memory_and_restart_publishes_winner(
    blockchain, wallets
):
    losing, winning = _competing_legacy_branches(
        blockchain, wallets["contributor_one"].public_key
    )
    blockchain.chain = losing
    blockchain.save_blockchain()

    def fault(stage):
        if stage == "after_reorg_commit_before_publish":
            raise RuntimeError(stage)

    blockchain._canonical_reorg_fault_injector = fault
    with pytest.raises(RuntimeError, match="after_reorg_commit_before_publish"):
        blockchain.adopt_canonical_chain(winning)

    assert blockchain.get_latest_block().hash == losing[-1].hash
    assert blockchain.storage.load_blockchain_document()["chain"][-1]["hash"] == winning[-1].hash

    restarted = Blockchain(storage_backend=blockchain.storage)
    assert restarted.get_latest_block().hash == winning[-1].hash
    assert restarted.get_finalized_head() is None
    assert restarted.calculate_balances_from_chain() == blockchain._native_ledger_service.calculate_balances_from_chain(
        restarted._native_ledger_state(), restarted.chain_to_dicts, chain=winning,
        error_type=ValueError,
    )


def test_finalized_history_mismatch_is_rejected_before_reconstruction():
    genesis = _block(0, GENESIS_HASH, "0")
    losing = _block(1, "a" * 64, GENESIS_HASH)
    winner = _block(1, "b" * 64, GENESIS_HASH)
    document = _document([genesis, losing], [])
    document["finalized_blocks"] = [{"block_height": 1, "block_hash": losing["hash"]}]

    with pytest.raises(CanonicalReorgError, match="finalized"):
        CanonicalReorgService.rebuild_document(
            document, [genesis, winner], NativeLedgerService()
        )


def test_two_nodes_converge_after_winner_adoption_and_requeued_transaction_delivery(
    isolated_data_dir,
):
    node_a = SQLiteStorageBackend(
        sqlite_db_path=str(isolated_data_dir / "node-a" / "zoidbergchain.db")
    )
    node_b = SQLiteStorageBackend(
        sqlite_db_path=str(isolated_data_dir / "node-b" / "zoidbergchain.db")
    )
    ledger = NativeLedgerService()
    sender = Account.create()
    recipient = Account.create()
    creator = Account.create().address.lower()
    transaction = _signed_transaction(sender, recipient=recipient.address, amount="3")
    genesis = _block(
        0, GENESIS_HASH, "0",
        legacy=[{"sender": "REWARD_POOL", "recipient": sender.address.lower(), "amount": 10, "tip": 0}],
    )
    losing = _block(1, "a" * 64, GENESIS_HASH, native=[transaction])
    winner = _block(
        1, "b" * 64, GENESIS_HASH,
        legacy=[{"sender": "REWARD_POOL", "recipient": creator, "amount": 5, "tip": 0}],
        submission_id="winner-submission", certificate_id="winner-certificate",
        creator_wallet=creator, content_hash="4" * 64,
        reward_type="meme_mining_reward", reward_recipient=creator, reward_amount="5",
    )
    node_a.save_blockchain_document(
        _document([genesis, losing], [_settled(transaction, losing)])
    )
    node_b.save_blockchain_document(_document([genesis, winner], []))

    node_a.atomic_update_blockchain_document(
        lambda document: CanonicalReorgService.rebuild_document(
            document, [genesis, winner], ledger
        )[0]
    )
    node_a_document = node_a.load_blockchain_document()
    requeued = next(
        item for item in node_a_document["native_transactions"]
        if item["tx_id"] == transaction["tx_id"]
    )
    assert requeued["status"] == "mempool"

    def receive_requeued(document):
        state = NativeLedgerState(
            document["chain"], document["transfer_intents"], document["native_transactions"]
        )
        ledger.admit_received_native_transaction(
            state, node_b, transaction, now_iso="2026-09-06T02:00:00+00:00"
        )
        document["transfer_intents"] = state.transfer_intents
        document["native_transactions"] = state.native_transactions
        return document

    node_b.atomic_update_blockchain_document(receive_requeued)
    node_b_document = node_b.load_blockchain_document()

    assert [block["hash"] for block in node_a_document["chain"]] == [
        block["hash"] for block in node_b_document["chain"]
    ]
    assert [(item["tx_id"], item["status"]) for item in node_a_document["native_transactions"]] == [
        (item["tx_id"], item["status"]) for item in node_b_document["native_transactions"]
    ]
    state_a = NativeLedgerState(
        node_a_document["chain"], node_a_document["transfer_intents"], node_a_document["native_transactions"]
    )
    state_b = NativeLedgerState(
        node_b_document["chain"], node_b_document["transfer_intents"], node_b_document["native_transactions"]
    )
    balances_a = ledger.calculate_balances_from_chain(state_a, lambda chain: list(chain))
    balances_b = ledger.calculate_balances_from_chain(state_b, lambda chain: list(chain))
    assert balances_a == balances_b
    assert ledger.get_next_nonce(state_a, sender.address) == ledger.get_next_nonce(state_b, sender.address) == 2
    assert _claim_rows(node_a, "canonical_reward_claims", "reward_id, reward_kind") == _claim_rows(
        node_b, "canonical_reward_claims", "reward_id, reward_kind"
    )
