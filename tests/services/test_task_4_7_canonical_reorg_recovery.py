"""Focused Task 4.7 canonical reconstruction and orphan requeue coverage."""

from copy import deepcopy

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from native_transfer import (
    NativeTransferMessage,
    build_native_transaction,
    build_transfer_signing_message,
    hash_transfer_signing_message,
)
from protocol_v1 import PROTOCOL_VERSION
from protocol_v1_native_transfer import resolve_protocol_v1_network_id
from services.canonical_reorg_service import CanonicalReorgService
from services.native_ledger_service import NativeLedgerService


GENESIS_HASH = "1" * 64


def _signed_transaction(account, *, recipient=None, amount="1", nonce="1", memo="task-4.7"):
    recipient = (recipient or Account.create().address).lower()
    network = "zoidberg-testnet"
    network_id = resolve_protocol_v1_network_id(network_name=network)
    timestamp = f"2026-09-06T00:00:{int(nonce):02d}+00:00"
    message_fields = NativeTransferMessage(
        action="transfer_zoid", network=network,
        from_address=account.address.lower(), to_address=recipient,
        amount=amount, nonce=nonce, fee="0", timestamp=timestamp, memo=memo,
        transaction_version=PROTOCOL_VERSION, protocol_version=PROTOCOL_VERSION,
        network_id=network_id,
    )
    message = build_transfer_signing_message(message_fields)
    signature = Account.sign_message(encode_defunct(text=message), account.key).signature.hex()
    return build_native_transaction(
        network=network, transaction_version=PROTOCOL_VERSION,
        protocol_version=PROTOCOL_VERSION, network_id=network_id,
        from_address=message_fields.from_address, to_address=message_fields.to_address,
        amount=amount, fee="0", nonce=nonce, memo=memo, timestamp=timestamp,
        signature=signature, signature_scheme="personal_sign", signed_message=message,
        signed_message_hash=hash_transfer_signing_message(message),
        status="signed_pending", created_at=timestamp, updated_at=timestamp,
    ).to_dict()


def _funding_transaction(recipient, amount="10"):
    return {"sender": "REWARD_POOL", "recipient": recipient.lower(), "amount": float(amount), "tip": 0}


def _block(height, block_hash, previous_hash, *, native=(), legacy=(), **extra):
    return {
        "index": height,
        "hash": block_hash,
        "previous_hash": previous_hash,
        "timestamp": float(height),
        "minted_at": f"2026-09-06T00:01:{height:02d}+00:00",
        "transactions": list(legacy),
        "native_transactions": [deepcopy(transaction) for transaction in native],
        **extra,
    }


def _genesis(*funding):
    return _block(0, GENESIS_HASH, "0", legacy=funding)


def _settled_record(transaction, block):
    record = deepcopy(transaction)
    record.update({
        "status": "settled",
        "included_block_hash": block["hash"],
        "included_block_height": block["index"],
        "settled_at": block["minted_at"],
        "updated_at": block["minted_at"],
    })
    return record


def _pending_record(transaction):
    record = deepcopy(transaction)
    record.update({"status": "mempool", "admitted_at": record["created_at"]})
    return record


def _document(chain, records=(), **extra):
    return {
        "chain": deepcopy(chain),
        "native_transactions": deepcopy(list(records)),
        "transfer_intents": [],
        "submissions": [],
        "mint_queue": [],
        "originality_certificates": [],
        "finality_attestations": [],
        "finalized_blocks": [],
        **extra,
    }


@pytest.mark.parametrize(
    "old_hashes,new_hashes,expected_detached,expected_attached",
    [
        ([GENESIS_HASH, "a" * 64], [GENESIS_HASH, "b" * 64], 1, 1),
        ([GENESIS_HASH, "a" * 64, "c" * 64], [GENESIS_HASH, "b" * 64, "d" * 64], 2, 2),
        ([GENESIS_HASH, "a" * 64], [GENESIS_HASH, "b" * 64, "c" * 64], 1, 2),
        ([GENESIS_HASH, "a" * 64], [GENESIS_HASH, "a" * 64], 0, 0),
    ],
)
def test_branch_delta_uses_hash_linkage_for_one_multi_same_height_longer_and_repeat(
    old_hashes, new_hashes, expected_detached, expected_attached
):
    def chain(hashes):
        return [
            _block(index, block_hash, "0" if index == 0 else hashes[index - 1])
            for index, block_hash in enumerate(hashes)
        ]

    delta = CanonicalReorgService.branch_delta(chain(old_hashes), chain(new_hashes))

    assert delta.common_ancestor_hash == (
        old_hashes[-1] if old_hashes == new_hashes else GENESIS_HASH
    )
    assert len(delta.detached_blocks) == expected_detached
    assert len(delta.attached_blocks) == expected_attached


def test_simple_orphan_rebuild_restores_balance_nonce_and_exact_mempool():
    ledger = NativeLedgerService()
    sender, recipient = Account.create(), Account.create()
    transaction = _signed_transaction(sender, recipient=recipient.address, amount="4")
    genesis = _genesis(_funding_transaction(sender.address, "10"))
    losing = _block(1, "a" * 64, GENESIS_HASH, native=[transaction])
    winner = _block(1, "b" * 64, GENESIS_HASH)

    replacement, report = CanonicalReorgService.rebuild_document(
        _document([genesis, losing], [_settled_record(transaction, losing)]),
        [genesis, winner], ledger,
    )

    rebuilt = replacement["native_transactions"]
    assert [(item["tx_id"], item["status"]) for item in rebuilt] == [(transaction["tx_id"], "mempool")]
    assert report["balances"][sender.address.lower()] == "10"
    assert recipient.address.lower() not in report["balances"]
    assert report["next_nonces"] == {}
    assert report["requeued_transaction_ids"] == [transaction["tx_id"]]


def test_winning_same_nonce_transaction_rejects_orphan_and_owns_canonical_claim():
    ledger = NativeLedgerService()
    sender = Account.create()
    transaction_a = _signed_transaction(sender, amount="3", memo="loser")
    transaction_b = _signed_transaction(sender, amount="2", memo="winner")
    genesis = _genesis(_funding_transaction(sender.address, "10"))
    losing = _block(1, "a" * 64, GENESIS_HASH, native=[transaction_a])
    winner = _block(1, "b" * 64, GENESIS_HASH, native=[transaction_b])

    replacement, report = CanonicalReorgService.rebuild_document(
        _document([genesis, losing], [_settled_record(transaction_a, losing)]),
        [genesis, winner], ledger,
    )
    by_id = {item["tx_id"]: item for item in replacement["native_transactions"]}

    assert by_id[transaction_b["tx_id"]]["status"] == "settled"
    assert by_id[transaction_a["tx_id"]]["status"] == "rejected"
    assert by_id[transaction_a["tx_id"]]["rejection_reason"] == "reorg_active_nonce_conflict"
    assert report["next_nonces"] == {sender.address.lower(): 2}
    assert report["canonical_transaction_ids"] == [transaction_b["tx_id"]]


def test_winning_balance_change_invalidates_orphan_deterministically():
    ledger = NativeLedgerService()
    sender = Account.create()
    transaction = _signed_transaction(sender, amount="8")
    genesis = _genesis(_funding_transaction(sender.address, "10"))
    losing = _block(1, "a" * 64, GENESIS_HASH, native=[transaction])
    winner = _block(
        1, "b" * 64, GENESIS_HASH,
        legacy=[{"sender": sender.address.lower(), "recipient": Account.create().address.lower(), "amount": 5, "tip": 0}],
    )

    replacement, report = CanonicalReorgService.rebuild_document(
        _document([genesis, losing], [_settled_record(transaction, losing)]),
        [genesis, winner], ledger,
    )

    rebuilt = replacement["native_transactions"][0]
    assert rebuilt["status"] == "rejected"
    assert rebuilt["rejection_reason"] == "reorg_insufficient_balance"
    assert report["requeued_transaction_ids"] == []


def test_transaction_on_both_branches_settles_once_in_winner_block():
    ledger = NativeLedgerService()
    sender = Account.create()
    transaction = _signed_transaction(sender, amount="2")
    genesis = _genesis(_funding_transaction(sender.address, "10"))
    losing = _block(1, "a" * 64, GENESIS_HASH, native=[transaction])
    winner = _block(1, "b" * 64, GENESIS_HASH, native=[transaction])

    replacement, report = CanonicalReorgService.rebuild_document(
        _document([genesis, losing], [_settled_record(transaction, losing)]),
        [genesis, winner], ledger,
    )

    assert len(replacement["native_transactions"]) == 1
    assert replacement["native_transactions"][0]["included_block_hash"] == winner["hash"]
    assert report["balances"][sender.address.lower()] == "8"
    assert report["canonical_native_claim_count"] == 1
    assert report["requeued_transaction_ids"] == []


def test_sequential_orphans_requeue_in_nonce_order_and_invalid_gap_blocks_later_nonce():
    ledger = NativeLedgerService()
    sender = Account.create()
    first = _signed_transaction(sender, amount="4", nonce="1", memo="first")
    second = _signed_transaction(sender, amount="4", nonce="2", memo="second")
    genesis = _genesis(_funding_transaction(sender.address, "10"))
    losing = _block(1, "a" * 64, GENESIS_HASH, native=[first, second])
    winner = _block(1, "b" * 64, GENESIS_HASH)
    source = _document(
        [genesis, losing],
        [_settled_record(second, losing), _settled_record(first, losing)],
    )

    replacement, report = CanonicalReorgService.rebuild_document(source, [genesis, winner], ledger)
    assert report["requeued_transaction_ids"] == [first["tx_id"], second["tx_id"]]
    assert [item["nonce"] for item in replacement["native_transactions"] if item["status"] == "mempool"] == ["2", "1"]

    unaffordable = _signed_transaction(sender, amount="11", nonce="1", memo="invalid first")
    later = _signed_transaction(sender, amount="1", nonce="2", memo="blocked later")
    losing_invalid = _block(1, "c" * 64, GENESIS_HASH, native=[unaffordable, later])
    invalid_source = _document(
        [genesis, losing_invalid],
        [_settled_record(later, losing_invalid), _settled_record(unaffordable, losing_invalid)],
    )
    invalid_replacement, invalid_report = CanonicalReorgService.rebuild_document(
        invalid_source, [genesis, winner], ledger
    )
    reasons = {item["tx_id"]: item["reason"] for item in invalid_report["invalidated_transactions"]}
    assert reasons[unaffordable["tx_id"]] == "reorg_insufficient_balance"
    assert reasons[later["tx_id"]] == "reorg_future_nonce"
    assert not [item for item in invalid_replacement["native_transactions"] if item["status"] == "mempool"]


def test_existing_pending_same_nonce_wins_deterministic_tie_over_orphan():
    ledger = NativeLedgerService()
    sender = Account.create()
    orphan = _signed_transaction(sender, amount="2", memo="orphan")
    existing = _signed_transaction(sender, amount="1", memo="existing pending")
    genesis = _genesis(_funding_transaction(sender.address, "10"))
    losing = _block(1, "a" * 64, GENESIS_HASH, native=[orphan])
    winner = _block(1, "b" * 64, GENESIS_HASH)

    replacement, _report = CanonicalReorgService.rebuild_document(
        _document(
            [genesis, losing],
            [_settled_record(orphan, losing), _pending_record(existing)],
        ),
        [genesis, winner], ledger,
    )
    by_id = {item["tx_id"]: item for item in replacement["native_transactions"]}

    assert by_id[existing["tx_id"]]["status"] == "mempool"
    assert by_id[orphan["tx_id"]]["status"] == "rejected"
    assert by_id[orphan["tx_id"]]["rejection_reason"] == "reorg_active_nonce_conflict"


def test_rewards_and_nonfinal_attestations_follow_only_winning_chain():
    ledger = NativeLedgerService()
    losing_creator = Account.create().address.lower()
    winning_creator = Account.create().address.lower()
    losing_voter = Account.create().address.lower()
    winning_voter = Account.create().address.lower()
    genesis = _genesis()
    losing = _block(
        1, "a" * 64, GENESIS_HASH, block_version=1,
        submission_id="loser-submission", certificate_id="loser-certificate",
        reward_type="meme_mining_reward", reward_recipient=losing_creator,
        reward_amount="5", voter_rewards=[{"reward_id": "loser-voter"}],
        legacy=[
            _funding_transaction(losing_creator, "5"),
            _funding_transaction(losing_voter, "1"),
        ],
    )
    winner = _block(
        1, "b" * 64, GENESIS_HASH, block_version=1,
        submission_id="winner-submission", certificate_id="winner-certificate",
        reward_type="meme_mining_reward", reward_recipient=winning_creator,
        reward_amount="5", voter_rewards=[{"reward_id": "winner-voter"}],
        legacy=[
            _funding_transaction(winning_creator, "5"),
            _funding_transaction(winning_voter, "1"),
        ],
    )
    attestations = [
        {"block_height": 1, "block_hash": losing["hash"]},
        {"block_height": 0, "block_hash": GENESIS_HASH},
    ]

    replacement, report = CanonicalReorgService.rebuild_document(
        _document([genesis, losing], finality_attestations=attestations),
        [genesis, winner], ledger,
    )

    assert report["canonical_creator_reward_count"] == 1
    assert report["canonical_voter_reward_count"] == 1
    assert report["removed_noncanonical_attestations"] == 1
    assert replacement["finality_attestations"] == [attestations[1]]
    assert report["balances"][winning_creator] == "5"
    assert report["balances"][winning_voter] == "1"
    assert losing_creator not in report["balances"]
    assert losing_voter not in report["balances"]
