from __future__ import annotations

from eth_account import Account
import pytest
import milestone5_policy

from milestone5_policy import (
    ESTABLISHED_MAX_VOTES_PER_EPOCH,
    PROBATION_MAX_VOTES_PER_EPOCH,
    REVIEW_EPOCH_BLOCKS,
    review_epoch,
    reviewer_policy,
    reviewer_policy_canonical_text,
    reviewer_policy_digest,
    bootstrap_established_reviewers,
)
from services.reviewer_eligibility_service import ReviewerEligibilityService
from storage import SQLiteStorageBackend


def _hash(height):
    return f"{height:064x}"


def _block(height, *, creator=None, submission=None, transactions=()):
    return {
        "index": height,
        "hash": _hash(height),
        "creator_wallet": creator,
        "submission_id": submission,
        "native_transactions": list(transactions),
    }


def _tx(number, sender, recipient):
    return {"tx_id": f"{number:064x}", "from_address": sender, "to_address": recipient}


def _head(height):
    return {"block_height": height, "block_hash": _hash(height)}


def _chain_to(height, overrides=()):
    by_height = {block["index"]: block for block in overrides}
    return [by_height.get(index, _block(index)) for index in range(height + 1)]


def _vote(backend, wallet, number, *, height, status="PROBATIONARY_REVIEWER", accepted=True):
    return backend.record_durable_vote(
        {
            "submission_id": f"vote-submission-{number}",
            "voter": wallet,
            "vote_type": "unsure" if number % 2 else "not_original",
            "reviewer_policy_version": 1,
            "reputation_rule_version": 1,
            "reviewer_status": status,
            "reviewer_status_effective_height": height,
            "reviewer_status_reference_block_hash": _hash(height),
            "created_at": f"vote-{number}",
        },
        lifecycle_state="accepted" if accepted else "rejected",
        rejection_reason=None if accepted else "conflict",
    )


def test_policy_v1_constants_serialization_digest_and_epoch_boundaries(monkeypatch):
    policy = reviewer_policy()
    assert policy["review_epoch_blocks"] == REVIEW_EPOCH_BLOCKS == 5
    assert policy["minimum_wallet_age_epochs"] == 3
    assert policy["earned_admission"] == {
        "enabled": True,
        "canonical_path_order": ["creator", "zoid_activity", "mixed"],
        "creator_path_min_finalized_minted_submissions": 2,
        "zoid_path_min_finalized_native_transactions": 5,
        "zoid_path_min_activity_span_epochs": 3,
        "mixed_path_min_finalized_minted_submissions": 1,
        "mixed_path_min_finalized_native_transactions": 2,
    }
    assert policy["probation"] == {
        "minimum_duration_epochs": 3,
        "maximum_valid_votes_per_epoch": 5,
        "minimum_valid_votes_for_promotion": 10,
    }
    assert policy["established_reviewer"]["maximum_valid_votes_per_epoch"] == 25
    before = reviewer_policy_canonical_text(), reviewer_policy_digest()
    monkeypatch.setenv("REVIEW_ALLOWLIST_WALLETS", Account.create().address)
    assert (reviewer_policy_canonical_text(), reviewer_policy_digest()) == before
    assert bootstrap_established_reviewers() == ()
    assert [review_epoch(height) for height in (0, 4, 5, 9, 10, 24, 25)] == [0, 0, 1, 1, 2, 4, 5]
    with pytest.raises(ValueError, match="Unsupported reviewer policy version"):
        review_epoch(0, 999)


def test_creator_wallet_age_finality_and_duplicate_counting():
    service = ReviewerEligibilityService()
    wallet = Account.create().address
    chain = _chain_to(16, [_block(0, creator=wallet, submission="one"), _block(1, creator=wallet, submission="two"), _block(2, creator=wallet, submission="two"), _block(16, creator=wallet, submission="unfinalized")])
    under = service.qualification(reviewer_address=wallet, chain=chain, finalized_head=_head(14))
    exact = service.qualification(reviewer_address=wallet, chain=chain, finalized_head=_head(15))
    assert under["wallet_origin_height"] == 0 and under["wallet_age_epochs"] == 2
    assert under["creator_path"] == {"finalized_minted_submissions": 2, "qualified": False}
    assert exact["wallet_age_epochs"] == 3
    assert exact["creator_path"] == {"finalized_minted_submissions": 2, "qualified": True}
    assert exact["qualification_path"] == "creator"


def test_zoid_and_mixed_paths_exclude_pending_or_self_transfer_representations():
    service = ReviewerEligibilityService()
    wallet, peer = Account.create().address, Account.create().address
    insufficient = [_block(0, transactions=[_tx(1, wallet, peer), _tx(99, wallet, wallet)]), _block(5, transactions=[_tx(2, peer, wallet), _tx(2, peer, wallet)]), _block(10, transactions=[_tx(3, wallet, peer), _tx(4, peer, wallet)])]
    result = service.qualification(reviewer_address=wallet, chain=_chain_to(15, insufficient), finalized_head=_head(15))
    assert result["zoid_path"]["finalized_native_transactions"] == 4
    assert result["zoid_path"]["qualified"] is False
    spanning = insufficient + [_block(15, transactions=[_tx(5, wallet, peer)])]
    result = service.qualification(reviewer_address=wallet, chain=_chain_to(15, spanning), finalized_head=_head(15))
    assert result["zoid_path"] == {"finalized_native_transactions": 5, "activity_span_epochs": 3, "qualified": True}
    mixed = [_block(0, creator=wallet, submission="minted", transactions=[_tx(10, wallet, peer)]), _block(1, transactions=[_tx(11, peer, wallet)])]
    result = service.qualification(reviewer_address=wallet, chain=_chain_to(15, mixed), finalized_head=_head(15))
    assert result["mixed_path"]["qualified"] is True


def test_probation_rate_promotion_restart_and_snapshot_determinism(isolated_data_dir):
    service = ReviewerEligibilityService()
    wallet = Account.create().address
    chain = _chain_to(35, [_block(0, creator=wallet, submission="one"), _block(1, creator=wallet, submission="two")])
    path = isolated_data_dir / "reviewers.db"
    backend = SQLiteStorageBackend(sqlite_db_path=str(path))
    state, _ = service.reconcile(reviewer_address=wallet, chain=chain, finalized_head=_head(15), storage=backend)
    assert state["current_status"] == "PROBATIONARY_REVIEWER"
    for number in range(PROBATION_MAX_VOTES_PER_EPOCH):
        assert service.vote_decision(reviewer_address=wallet, chain=chain, finalized_head=_head(15), storage=backend).eligible
        _vote(backend, wallet, number, height=15)
    limited = service.vote_decision(reviewer_address=wallet, chain=chain, finalized_head=_head(15), storage=backend)
    assert not limited.eligible and limited.reason == "review_epoch_vote_limit_reached"
    assert service.vote_decision(reviewer_address=wallet, chain=chain, finalized_head=_head(20), storage=backend).eligible
    for number in range(5, 10):
        _vote(backend, wallet, number, height=20)
    # Ten votes alone and time alone are independently insufficient.
    state, _ = service.reconcile(reviewer_address=wallet, chain=chain, finalized_head=_head(25), storage=backend)
    assert state["current_status"] == "PROBATIONARY_REVIEWER"
    restarted = SQLiteStorageBackend(sqlite_db_path=str(path))
    state, _ = service.reconcile(reviewer_address=wallet, chain=chain, finalized_head=_head(30), storage=restarted)
    assert state["current_status"] == "ESTABLISHED_REVIEWER"
    assert len(restarted.list_reviewer_state_history(wallet)) == 3
    snapshots = [service.snapshot(reviewer_addresses=[wallet], chain=chain, finalized_head=_head(30), storage=store) for store in (restarted, SQLiteStorageBackend(sqlite_db_path=str(path)))]
    assert snapshots[0]["reviewer_snapshot_digest"] == snapshots[1]["reviewer_snapshot_digest"]
    assert "observed_at" not in snapshots[0]["canonical_serialization"]
    for number in range(10, 10 + ESTABLISHED_MAX_VOTES_PER_EPOCH):
        _vote(restarted, wallet, number, height=30, status="ESTABLISHED_REVIEWER")
    assert not service.vote_decision(reviewer_address=wallet, chain=chain, finalized_head=_head(30), storage=restarted).eligible
    assert service.vote_decision(reviewer_address=wallet, chain=chain, finalized_head=_head(35), storage=restarted).eligible


def test_rejected_vote_does_not_consume_quota_and_state_is_idempotent(isolated_data_dir):
    service = ReviewerEligibilityService()
    wallet = Account.create().address
    chain = _chain_to(15, [_block(0, creator=wallet, submission="one"), _block(1, creator=wallet, submission="two")])
    backend = SQLiteStorageBackend(sqlite_db_path=str(isolated_data_dir / "idempotent.db"))
    service.reconcile(reviewer_address=wallet, chain=chain, finalized_head=_head(15), storage=backend)
    service.reconcile(reviewer_address=wallet, chain=chain, finalized_head=_head(15), storage=backend)
    _vote(backend, wallet, 1, height=15, accepted=False)
    decision = service.vote_decision(reviewer_address=wallet, chain=chain, finalized_head=_head(15), storage=backend)
    assert decision.votes_used_this_epoch == 0
    assert len(backend.list_reviewer_state_history(wallet)) == 2


def test_time_alone_does_not_promote_and_cooldown_is_respected(isolated_data_dir):
    service = ReviewerEligibilityService()
    wallet = Account.create().address
    chain = _chain_to(30, [_block(0, creator=wallet, submission="one"), _block(1, creator=wallet, submission="two")])
    backend = SQLiteStorageBackend(sqlite_db_path=str(isolated_data_dir / "time-only.db"))
    state, _ = service.reconcile(reviewer_address=wallet, chain=chain, finalized_head=_head(15), storage=backend)
    assert state["current_status"] == "PROBATIONARY_REVIEWER"
    state, _ = service.reconcile(reviewer_address=wallet, chain=chain, finalized_head=_head(30), storage=backend)
    assert state["current_status"] == "PROBATIONARY_REVIEWER"
    backend.transition_reviewer_state(wallet, to_status="COOLDOWN", status_effective_height=30, status_reference_block_hash=_hash(30), reason="fixture")
    assert not service.vote_decision(reviewer_address=wallet, chain=chain, finalized_head=_head(30), storage=backend).eligible
    assert backend.get_reviewer_state(wallet)["current_status"] == "COOLDOWN"


def test_two_nodes_match_and_unfinalized_changes_do_not_change_snapshot(isolated_data_dir):
    service = ReviewerEligibilityService()
    wallet = Account.create().address
    canonical = _chain_to(15, [_block(0, creator=wallet, submission="one"), _block(1, creator=wallet, submission="two")])
    with_unfinalized_a = canonical + [_block(16, creator=wallet, submission="a")]
    with_unfinalized_b = canonical + [{**_block(16, creator=wallet, submission="b"), "hash": "f" * 64}]
    stores = [SQLiteStorageBackend(sqlite_db_path=str(isolated_data_dir / f"node-{index}.db")) for index in (1, 2)]
    results = [service.qualification(reviewer_address=wallet, chain=chain, finalized_head=_head(15)) for chain in (with_unfinalized_a, with_unfinalized_b)]
    assert results[0] == results[1]
    snapshots = [service.snapshot(reviewer_addresses=[wallet], chain=chain, finalized_head=_head(15), storage=store) for chain, store in zip((with_unfinalized_a, with_unfinalized_b), stores)]
    assert snapshots[0]["reviewer_snapshot_digest"] == snapshots[1]["reviewer_snapshot_digest"]
    assert snapshots[0]["reviewers"][0]["status"] == "PROBATIONARY_REVIEWER"
    before = snapshots[0]["reviewer_snapshot_digest"]
    service.reconcile(reviewer_address=wallet, chain=with_unfinalized_a, finalized_head=_head(15), storage=stores[0])
    stores[0].transition_reviewer_state(wallet, to_status="SUSPENDED", status_effective_height=15, status_reference_block_hash=_hash(15), reason="fixture")
    after = service.snapshot(reviewer_addresses=[wallet], chain=with_unfinalized_a, finalized_head=_head(15), storage=stores[0])
    assert after["reviewer_snapshot_digest"] != before


def test_versioned_bootstrap_grant_becomes_established_without_legacy_allowlist(monkeypatch, isolated_data_dir):
    service = ReviewerEligibilityService()
    wallet = Account.create().address.lower()
    monkeypatch.setitem(
        milestone5_policy._REVIEWER_POLICIES[1],
        "bootstrap_established_reviewers",
        [wallet],
    )
    backend = SQLiteStorageBackend(sqlite_db_path=str(isolated_data_dir / "bootstrap.db"))
    chain = _chain_to(0)
    state, evidence = service.reconcile(
        reviewer_address=wallet,
        chain=chain,
        finalized_head=_head(0),
        storage=backend,
    )
    assert evidence["overall_qualified"] is False
    assert state["current_status"] == "ESTABLISHED_REVIEWER"
    assert state["bootstrap_established"] is True
    assert "BOOTSTRAP_POLICY_GRANT" in backend.list_reviewer_state_history(wallet)[-1]["reason"]


def test_sqlite_epoch_limit_is_atomic_and_replay_safe(isolated_data_dir):
    backend = SQLiteStorageBackend(sqlite_db_path=str(isolated_data_dir / "atomic-rate.db"))
    wallet = Account.create().address
    votes = []
    for number in range(6):
        vote = {
            "submission_id": f"rate-{number}", "voter": wallet, "vote_type": "original",
            "reviewer_policy_version": 1, "reputation_rule_version": 1,
            "reviewer_status": "PROBATIONARY_REVIEWER",
            "reviewer_status_effective_height": 15,
            "reviewer_status_reference_block_hash": _hash(15),
            "created_at": f"rate-vote-{number}",
        }
        votes.append(vote)
        result = backend.record_durable_vote_with_epoch_limit(
            vote, maximum_votes=5, epoch_start_height=15, epoch_end_height=19,
        )
        assert result["lifecycle_state"] == ("accepted" if number < 5 else "rejected")
    replay = backend.record_durable_vote_with_epoch_limit(
        votes[0], maximum_votes=5, epoch_start_height=15, epoch_end_height=19,
    )
    assert replay["replay"] is True and replay["lifecycle_state"] == "accepted"
