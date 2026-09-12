from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from types import SimpleNamespace

from eth_account import Account
from eth_account.messages import encode_defunct
import pytest
from fastapi.testclient import TestClient

from blockchain import Blockchain
from milestone5_policy import (
    REPUTATION_RULE_VERSION,
    reputation_rules,
    reputation_rules_canonical_text,
    reputation_rules_digest,
)
from originality_certificate import OriginalityCertificate
from protocol_v1 import PUBLIC_TESTNET_V1_NETWORK_ID, canonical_hash
from protocol_v1_genesis import canonical_public_testnet_v1_genesis_record
from protocol_v1_originality import MILESTONE5_CERTIFICATE_V3_VERSION, build_protocol_v1_vote_message, calculate_signed_vote_identity
from protocol_v1_peer_message import build_protocol_v1_peer_request_headers, clear_protocol_v1_peer_replay_store_cache
from reviewer_reputation import (
    CREATOR_SELF_VOTE,
    RATE_LIMIT_ABUSE,
    SIGNED_VOTE_EQUIVOCATION,
    VOTE_DURING_COOLDOWN,
    VOTE_DURING_SUSPENSION,
    ReviewerReputationService,
    build_offense_evidence,
    validate_offense_evidence,
)
from services.reviewer_eligibility_service import ReviewerEligibilityService
from storage import SQLiteStorageBackend
from storage_tools import build_export_snapshot, import_storage
from submission import APPROVED, Submission
from wallet import Wallet
from wallet_auth import hash_wallet_message


REFERENCE_HASH = "ab" * 32


def _signed_vote(
    account, submission_id, choice, number, *, content_hash="11" * 32,
    reviewer_status="ESTABLISHED_REVIEWER", reviewer_eligible=True,
    status_height=20, status_hash=REFERENCE_HASH,
):
    nonce = f"offense-{number}"
    issued_at = f"172476{number:04d}.0"
    expires_at = f"172486{number:04d}.0"
    message = build_protocol_v1_vote_message(
        wallet_address=account.address,
        submission_id=submission_id,
        content_hash=content_hash,
        vote_type=choice,
        nonce=nonce,
        issued_at=issued_at,
        expires_at=expires_at,
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
    )
    signature = Account.sign_message(encode_defunct(text=message), account.key).signature.hex()
    vote = {
        "vote_version": 1,
        "protocol_version": 1,
        "network_id": PUBLIC_TESTNET_V1_NETWORK_ID,
        "submission_id": submission_id,
        "content_hash": content_hash,
        "voter": account.address,
        "voter_wallet_address": account.address,
        "vote_type": choice,
        "signature_scheme": "personal_sign",
        "vote_signature": signature,
        "vote_message": message,
        "signed_message_hash": hash_wallet_message(message),
        "vote_nonce": nonce,
        "vote_issued_at": issued_at,
        "vote_expires_at": expires_at,
        "reviewer_policy_version": 1,
        "reputation_rule_version": 2,
        "reviewer_status": reviewer_status,
        "reviewer_eligible": reviewer_eligible,
        "reviewer_status_effective_height": status_height,
        "reviewer_status_reference_block_hash": status_hash,
        "created_at": 1_724_760_000 + number,
    }
    vote["vote_identity"] = calculate_signed_vote_identity(
        wallet_address=account.address,
        submission_id=submission_id,
        content_hash=content_hash,
        vote_type=choice,
        nonce=nonce,
        issued_at=issued_at,
        expires_at=expires_at,
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
        signature=signature,
    )
    return vote


def _record_probation_quota(storage, reviewer, epoch, number_base, *, status_hash=REFERENCE_HASH):
    votes = []
    for offset in range(5):
        vote = _signed_vote(
            reviewer, f"quota-{epoch}-{offset}", "unsure", number_base + offset,
            reviewer_status="PROBATIONARY_REVIEWER", status_height=epoch * 5,
            status_hash=status_hash,
        )
        storage.record_durable_vote(vote, lifecycle_state="accepted")
        votes.append(vote)
    return votes


def _evidence(kind, votes, epoch, *, creator=None, active_penalty_id=None, reference_hash=REFERENCE_HASH):
    return build_offense_evidence(
        offense_type=kind,
        votes=votes,
        reference_finalized_height=epoch * 5,
        reference_finalized_block_hash=reference_hash,
        review_epoch=epoch,
        creator_address=creator,
        active_penalty_id=active_penalty_id,
    )


def test_reputation_rule_v1_is_preserved_and_v2_is_active_and_deterministic():
    assert REPUTATION_RULE_VERSION == 2
    assert reputation_rules_digest(1) == "9bfdfc196fd6d54796d699b513a550672b6e12d659b9dbb52f1e44b065be17fb"
    assert reputation_rules_digest(2) == "0605b0cbd81ee7f7dade23651f44d88473d752661470de0035925fdc5a1c7c12"
    assert reputation_rules(1)["automatic_penalties"]["enabled"] is False
    assert reputation_rules(2)["automatic_penalties"]["enabled"] is True
    assert reputation_rules_canonical_text(2) == reputation_rules_canonical_text(REPUTATION_RULE_VERSION)
    with pytest.raises(ValueError, match="Unsupported reputation rule version"):
        reputation_rules(999)


def test_equivocation_is_grouped_once_and_escalates_per_distinct_submission(tmp_path):
    reviewer = Account.create()
    storage = SQLiteStorageBackend(sqlite_db_path=str(tmp_path / "equivocation.db"))
    service = ReviewerReputationService(storage)
    outcomes = []
    for sequence in range(1, 4):
        votes = [
            _signed_vote(reviewer, f"submission-{sequence}", "original", sequence * 10),
            _signed_vote(reviewer, f"submission-{sequence}", "not_original", sequence * 10 + 1),
        ]
        offense = _evidence(SIGNED_VOTE_EQUIVOCATION, list(reversed(votes)), sequence)
        assert validate_offense_evidence(offense)["offense_id"] == offense["offense_id"]
        outcomes.append(service.apply_verified_offense(offense, state_before="ESTABLISHED_REVIEWER"))
        replay = service.apply_verified_offense(_evidence(SIGNED_VOTE_EQUIVOCATION, votes, sequence), state_before="ESTABLISHED_REVIEWER")
        assert replay.replay
    assert [(item.penalty or {}).get("penalty_status") for item in outcomes] == ["COOLDOWN", "COOLDOWN", "SUSPENDED"]
    assert [(item.penalty or {}).get("penalty_duration_epochs") for item in outcomes] == [3, 10, 25]
    assert len(storage.list_reviewer_offenses(reviewer.address, offense_type=SIGNED_VOTE_EQUIVOCATION)) == 3


def test_identical_or_same_choice_votes_do_not_prove_equivocation():
    reviewer = Account.create()
    vote = _signed_vote(reviewer, "same", "unsure", 1)
    with pytest.raises(ValueError, match="conflicting signed choices"):
        validate_offense_evidence(_evidence(SIGNED_VOTE_EQUIVOCATION, [vote, vote], 1))
    other = _signed_vote(reviewer, "same", "unsure", 2)
    with pytest.raises(ValueError, match="conflicting signed choices"):
        validate_offense_evidence(_evidence(SIGNED_VOTE_EQUIVOCATION, [vote, other], 1))


def test_peer_style_validation_rejects_tampering_fake_creator_and_nonfinal_reference():
    reviewer = Account.create()
    other = Account.create()
    vote = _signed_vote(reviewer, "peer-self", "original", 8)
    offense = _evidence(CREATOR_SELF_VOTE, [vote], 2, creator=reviewer.address)
    assert validate_offense_evidence(
        offense,
        finalized_reference_validator=lambda height, block_hash: height == 10 and block_hash == REFERENCE_HASH,
        creator_resolver=lambda submission_id: reviewer.address,
    )["offense_id"] == offense["offense_id"]
    tampered = deepcopy(offense)
    tampered["evidence_payload"]["review_epoch"] = 99
    with pytest.raises(ValueError, match="digest"):
        validate_offense_evidence(tampered)
    with pytest.raises(ValueError, match="canonical creator"):
        validate_offense_evidence(offense, creator_resolver=lambda submission_id: other.address)
    with pytest.raises(ValueError, match="not finalized"):
        validate_offense_evidence(offense, finalized_reference_validator=lambda height, block_hash: False)


def test_self_vote_escalation_and_canonical_address_normalization(tmp_path):
    creator = Account.create()
    storage = SQLiteStorageBackend(sqlite_db_path=str(tmp_path / "self.db"))
    service = ReviewerReputationService(storage)
    durations = []
    for sequence in range(1, 4):
        vote = _signed_vote(creator, f"self-{sequence}", "original", sequence)
        offense = _evidence(CREATOR_SELF_VOTE, [vote], sequence, creator="0x" + creator.address[2:].upper())
        outcome = service.apply_verified_offense(offense, state_before="PROBATIONARY_REVIEWER")
        durations.append((outcome.penalty or {}).get("penalty_duration_epochs"))
    assert durations == [1, 3, 25]
    assert service.effective_penalty(creator.address, 3)["effective_status"] == "SUSPENDED"


def test_rate_limit_first_two_are_reject_only_third_penalizes_and_replay_is_idempotent(tmp_path):
    reviewer = Account.create()
    storage = SQLiteStorageBackend(sqlite_db_path=str(tmp_path / "rate.db"))
    service = ReviewerReputationService(storage)
    outcomes = []
    _record_probation_quota(storage, reviewer, 4, 100)
    votes = [
        _signed_vote(
            reviewer, f"rate-{number}", "unsure", number,
            reviewer_status="PROBATIONARY_REVIEWER", reviewer_eligible=False,
            status_height=20,
        )
        for number in range(1, 4)
    ]
    for vote in votes:
        outcomes.append(service.record_rate_limit_excess(
            vote, reference_finalized_height=20,
            reference_finalized_block_hash=REFERENCE_HASH,
            review_epoch=4, state_before="PROBATIONARY_REVIEWER",
        ))
    assert [item.offense is None for item in outcomes] == [True, True, False]
    assert outcomes[2].offense["offense_type"] == RATE_LIMIT_ABUSE
    assert outcomes[2].penalty["penalty_duration_epochs"] == 1
    assert len(outcomes[2].offense["evidence_payload"]["rate_limit_context"]["accepted_votes"]) == 5
    fabricated = build_offense_evidence(
        offense_type=RATE_LIMIT_ABUSE, votes=votes,
        reference_finalized_height=20,
        reference_finalized_block_hash=REFERENCE_HASH, review_epoch=4,
    )
    with pytest.raises(ValueError, match="exhausted reviewer quota"):
        validate_offense_evidence(fabricated)
    assert validate_offense_evidence(
        outcomes[2].offense,
        creator_resolver=lambda submission_id: Account.create().address,
    )["offense_id"] == outcomes[2].offense["offense_id"]
    replay = service.record_rate_limit_excess(
        votes[2], reference_finalized_height=20,
        reference_finalized_block_hash=REFERENCE_HASH,
        review_epoch=4, state_before="PROBATIONARY_REVIEWER",
    )
    assert replay.replay
    assert len(storage.list_rate_limit_excess_attempts(reviewer.address)) == 3
    later_durations = []
    for epoch in (5, 6):
        _record_probation_quota(storage, reviewer, epoch, epoch * 100)
        outcome = None
        for offset in range(3):
            number = epoch * 10 + offset
            outcome = service.record_rate_limit_excess(
                _signed_vote(
                    reviewer, f"rate-{number}", "unsure", number,
                    reviewer_status="PROBATIONARY_REVIEWER", reviewer_eligible=False,
                    status_height=epoch * 5,
                ),
                reference_finalized_height=epoch * 5,
                reference_finalized_block_hash=REFERENCE_HASH,
                review_epoch=epoch, state_before="PROBATIONARY_REVIEWER",
            )
        later_durations.append(outcome.penalty["penalty_duration_epochs"])
    assert later_durations == [3, 25]


def test_cooldown_attempt_extends_without_shortening_and_suspension_attempt_records_only(tmp_path):
    reviewer = Account.create()
    storage = SQLiteStorageBackend(sqlite_db_path=str(tmp_path / "active.db"))
    service = ReviewerReputationService(storage)
    first = _evidence(
        SIGNED_VOTE_EQUIVOCATION,
        [_signed_vote(reviewer, "first", "original", 1), _signed_vote(reviewer, "first", "unsure", 2)],
        4,
    )
    first_outcome = service.apply_verified_offense(first, state_before="ESTABLISHED_REVIEWER")
    cooldown_vote = _signed_vote(reviewer, "during-cooldown", "not_original", 3)
    extension = service.apply_verified_offense(
        _evidence(VOTE_DURING_COOLDOWN, [cooldown_vote], 6, active_penalty_id=first_outcome.penalty["penalty_id"]),
        state_before="ESTABLISHED_REVIEWER",
    )
    assert extension.penalty["penalty_end_epoch"] == 9
    assert service.effective_penalty(reviewer.address, 8)["effective_status"] == "COOLDOWN"

    for number in (2, 3):
        service.apply_verified_offense(
            _evidence(
                SIGNED_VOTE_EQUIVOCATION,
                [_signed_vote(reviewer, f"equiv-{number}", "original", number * 10), _signed_vote(reviewer, f"equiv-{number}", "unsure", number * 10 + 1)],
                6,
            ),
            state_before="ESTABLISHED_REVIEWER",
        )
    suspension = service.effective_penalty(reviewer.address, 6)
    assert suspension["effective_status"] == "SUSPENDED"
    attempt = service.apply_verified_offense(
        _evidence(VOTE_DURING_SUSPENSION, [_signed_vote(reviewer, "during-suspension", "original", 99)], 7, active_penalty_id=suspension["penalty_id"]),
        state_before="ESTABLISHED_REVIEWER",
    )
    assert attempt.penalty is None
    assert service.effective_penalty(reviewer.address, 7)["effective_end_epoch"] == suspension["effective_end_epoch"]


def test_schema_migration_is_idempotent_and_records_survive_restart(tmp_path):
    path = tmp_path / "restart.db"
    reviewer = Account.create()
    first = SQLiteStorageBackend(sqlite_db_path=str(path))
    service = ReviewerReputationService(first)
    offense = _evidence(CREATOR_SELF_VOTE, [_signed_vote(reviewer, "restart", "original", 1)], 2, creator=reviewer.address)
    service.apply_verified_offense(offense, state_before="PROBATIONARY_REVIEWER")
    SQLiteStorageBackend(sqlite_db_path=str(path))
    reopened = SQLiteStorageBackend(sqlite_db_path=str(path))
    assert reopened.list_reviewer_offenses(reviewer.address)[0]["offense_id"] == offense["offense_id"]
    assert reopened.list_reviewer_penalties(reviewer.address)[0]["penalty_end_epoch"] == 3
    backup_path = reopened.backup_sqlite_database(str(tmp_path / "reputation-backup.db"))
    backup = SQLiteStorageBackend(sqlite_db_path=backup_path)
    assert backup.list_reviewer_offenses(reviewer.address)[0]["offense_id"] == offense["offense_id"]
    with sqlite3.connect(path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"reviewer_offense_records", "reviewer_penalties", "reviewer_rate_limit_excess_attempts"} <= tables


def test_finalized_epoch_expiry_restores_probation_and_historical_status(tmp_path):
    reviewer = Account.create()
    address = reviewer.address
    chain = [
        {
            "index": height,
            "hash": f"{height:064x}",
            "creator_wallet": address if height in {0, 1} else None,
            "submission_id": f"qualification-{height}" if height in {0, 1} else None,
            "native_transactions": [],
        }
        for height in range(31)
    ]
    storage = SQLiteStorageBackend(sqlite_db_path=str(tmp_path / "expiry.db"))
    eligibility = ReviewerEligibilityService()
    state, _ = eligibility.reconcile(
        reviewer_address=address, chain=chain,
        finalized_head={"block_height": 20, "block_hash": f"{20:064x}"},
        storage=storage,
    )
    assert state["current_status"] == "PROBATIONARY_REVIEWER"
    vote = _signed_vote(reviewer, "self-expiry", "original", 77)
    outcome = ReviewerReputationService(storage).apply_verified_offense(
        _evidence(CREATOR_SELF_VOTE, [vote], 4, creator=address, reference_hash=f"{20:064x}"),
        state_before="PROBATIONARY_REVIEWER",
    )
    storage.transition_reviewer_state(
        address, to_status="COOLDOWN", reputation_rule_version=2,
        status_effective_height=20, status_reference_block_hash=f"{20:064x}",
        reason=CREATOR_SELF_VOTE,
    )
    assert not eligibility.vote_decision(
        reviewer_address=address, chain=chain,
        finalized_head={"block_height": 20, "block_hash": f"{20:064x}"},
        storage=storage,
    ).eligible
    assert eligibility.status_at_reference(
        reviewer_address=address, chain=chain,
        finalized_head={"block_height": 19, "block_hash": f"{19:064x}"},
        storage=storage, reputation_rule_version=2,
    )["status"] == "PROBATIONARY_REVIEWER"
    assert eligibility.status_at_reference(
        reviewer_address=address, chain=chain,
        finalized_head={"block_height": 20, "block_hash": f"{20:064x}"},
        storage=storage, reputation_rule_version=2,
    )["status"] == "COOLDOWN"
    restored, _ = eligibility.reconcile(
        reviewer_address=address, chain=chain,
        finalized_head={"block_height": 25, "block_hash": f"{25:064x}"},
        storage=storage,
    )
    assert restored["current_status"] == "PROBATIONARY_REVIEWER"
    assert outcome.penalty["penalty_end_epoch"] == 5


def test_export_import_retains_offense_penalty_and_excess_history(tmp_path):
    source = SQLiteStorageBackend(sqlite_db_path=str(tmp_path / "source.db"))
    source.save_blockchain_state({"chain": [canonical_public_testnet_v1_genesis_record()]})
    reviewer = Account.create()
    source.initialize_reviewer_state(
        reviewer.address, current_status="PROBATIONARY_REVIEWER",
        reputation_rule_version=2, status_effective_height=0,
        status_reference_block_hash=canonical_public_testnet_v1_genesis_record()["hash"],
    )
    service = ReviewerReputationService(source)
    _record_probation_quota(source, reviewer, 0, 100)
    votes = [
        _signed_vote(
            reviewer, f"export-rate-{number}", "unsure", number,
            reviewer_status="PROBATIONARY_REVIEWER", reviewer_eligible=False,
            status_height=0,
        )
        for number in range(1, 4)
    ]
    for vote in votes:
        service.record_rate_limit_excess(
            vote, reference_finalized_height=0,
            reference_finalized_block_hash=canonical_public_testnet_v1_genesis_record()["hash"],
            review_epoch=0, state_before="NEW",
        )
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(build_export_snapshot(source)), encoding="utf-8")
    target = SQLiteStorageBackend(sqlite_db_path=str(tmp_path / "target.db"))
    result = import_storage(target, input_path=snapshot_path)
    assert result["written"]
    assert len(target.list_reviewer_offenses(reviewer.address)) == 1
    assert len(target.list_reviewer_penalties(reviewer.address)) == 1
    assert len(target.list_rate_limit_excess_attempts(reviewer.address)) == 3
    assert target.get_reviewer_state(reviewer.address)["current_status"] == "PROBATIONARY_REVIEWER"
    assert len(target.list_reviewer_state_history(reviewer.address)) == 1


def test_public_signed_vote_conflict_retains_rejected_evidence_and_applies_penalty(tmp_path, monkeypatch):
    backend = SQLiteStorageBackend(sqlite_db_path=str(tmp_path / "public-path.db"))
    chain = Blockchain(Wallet(), Wallet(), Wallet(), storage_backend=backend)
    reviewer = Account.create()
    creator = Account.create()
    chain.chain = [
        SimpleNamespace(
            index=height,
            hash=f"{height:064x}",
            creator_wallet=reviewer.address if height in {0, 1} else None,
            submission_id=f"qualification-{height}" if height in {0, 1} else None,
            native_transactions=[],
        )
        for height in range(16)
    ]
    chain.finalized_blocks = [{"block_height": 15, "block_hash": f"{15:064x}"}]
    submission = Submission(
        image_path="", text_content="reputation path", submitter=creator.address,
        submission_id="public-equivocation", content_hash="11" * 32,
    )
    chain.submissions = [submission]
    chain.votes = []

    def cast_vote(*, submission_id, voter, vote_type, created_at=None):
        vote = {"submission_id": submission_id, "voter": voter, "vote_type": vote_type, "created_at": created_at or 1}
        chain.votes.append(vote)
        return vote

    monkeypatch.setattr(chain, "cast_submission_vote", cast_vote)
    monkeypatch.setattr(chain, "save_blockchain", lambda: None)

    def cast(candidate):
        verification = {
            "vote_version": candidate["vote_version"],
            "protocol_version": candidate["protocol_version"],
            "network_id": candidate["network_id"],
            "signature_scheme": candidate["signature_scheme"],
            "vote_signature": candidate["vote_signature"],
            "vote_message": candidate["vote_message"],
            "signed_message_hash": candidate["signed_message_hash"],
            "nonce": candidate["vote_nonce"],
            "vote_issued_at": candidate["vote_issued_at"],
            "vote_expires_at": candidate["vote_expires_at"],
            "signed_at": candidate["vote_issued_at"],
            "identity_source": "metamask_signed",
        }
        auth = SimpleNamespace(verify_vote_signature=lambda **kwargs: verification)
        return chain.cast_signed_submission_vote_operation(
            submission_id=submission.submission_id, voter=reviewer.address,
            vote_type=candidate["vote_type"], message=candidate["vote_message"],
            signature=candidate["vote_signature"], auth_manager=auth,
        )

    first = _signed_vote(reviewer, submission.submission_id, "original", 201)
    cast(first)
    with pytest.raises(ValueError, match="already"):
        cast(first)
    assert backend.list_reviewer_offenses(reviewer.address) == []
    conflicting = _signed_vote(reviewer, submission.submission_id, "not_original", 202)
    with pytest.raises(ValueError, match="already voted"):
        cast(conflicting)
    offenses = backend.list_reviewer_offenses(reviewer.address)
    assert len(offenses) == 1 and offenses[0]["offense_type"] == SIGNED_VOTE_EQUIVOCATION
    rejected = [vote for vote in backend.list_durable_votes(submission_id=submission.submission_id) if vote["lifecycle_state"] == "rejected"]
    assert len(rejected) == 1 and rejected[0]["vote_identity"] == conflicting["vote_identity"]
    assert chain.get_reviewer_vote_decision(reviewer.address).status == "COOLDOWN"


def test_public_rate_limit_path_proves_quota_and_third_excess_penalizes(tmp_path, monkeypatch):
    backend = SQLiteStorageBackend(sqlite_db_path=str(tmp_path / "public-rate.db"))
    chain = Blockchain(Wallet(), Wallet(), Wallet(), storage_backend=backend)
    reviewer = Account.create()
    creator = Account.create()
    chain.chain = [
        SimpleNamespace(
            index=height, hash=f"{height:064x}",
            creator_wallet=reviewer.address if height in {0, 1} else None,
            submission_id=f"qualification-{height}" if height in {0, 1} else None,
            native_transactions=[],
        )
        for height in range(21)
    ]
    chain.finalized_blocks = [{"block_height": 20, "block_hash": f"{20:064x}"}]
    chain.submissions = [
        Submission(
            image_path="", text_content=f"rate path {number}", submitter=creator.address,
            submission_id=f"public-rate-{number}", content_hash=f"{number + 1:064x}",
        )
        for number in range(8)
    ]
    chain.votes = []

    def cast_vote(*, submission_id, voter, vote_type, created_at=None):
        vote = {"submission_id": submission_id, "voter": voter, "vote_type": vote_type, "created_at": created_at or 1}
        chain.votes.append(vote)
        return vote

    monkeypatch.setattr(chain, "cast_submission_vote", cast_vote)
    monkeypatch.setattr(chain, "save_blockchain", lambda: None)

    last_operation = None
    for number, submission in enumerate(chain.submissions):
        candidate = _signed_vote(
            reviewer, submission.submission_id, "unsure", 500 + number,
            content_hash=submission.content_hash,
        )
        verification = {
            "vote_version": candidate["vote_version"],
            "protocol_version": candidate["protocol_version"],
            "network_id": candidate["network_id"],
            "signature_scheme": candidate["signature_scheme"],
            "vote_signature": candidate["vote_signature"],
            "vote_message": candidate["vote_message"],
            "signed_message_hash": candidate["signed_message_hash"],
            "nonce": candidate["vote_nonce"],
            "vote_issued_at": candidate["vote_issued_at"],
            "vote_expires_at": candidate["vote_expires_at"],
            "signed_at": candidate["vote_issued_at"],
            "identity_source": "metamask_signed",
        }
        auth = SimpleNamespace(verify_vote_signature=lambda **kwargs: verification)
        operation = lambda: chain.cast_signed_submission_vote_operation(
            submission_id=submission.submission_id, voter=reviewer.address,
            vote_type=candidate["vote_type"], message=candidate["vote_message"],
            signature=candidate["vote_signature"], auth_manager=auth,
        )
        last_operation = operation
        if number < 5:
            operation()
        else:
            with pytest.raises(ValueError, match="vote.limit"):
                operation()
            if number < 7:
                assert backend.list_reviewer_offenses(reviewer.address, offense_type=RATE_LIMIT_ABUSE) == []
                assert backend.list_reviewer_penalties(reviewer.address) == []

    with pytest.raises(ValueError, match="already submitted"):
        last_operation()

    offenses = backend.list_reviewer_offenses(reviewer.address, offense_type=RATE_LIMIT_ABUSE)
    assert len(offenses) == 1
    context = offenses[0]["evidence_payload"]["rate_limit_context"]
    assert context["maximum_votes"] == 5
    assert len(context["accepted_votes"]) == 5
    assert len(offenses[0]["vote_identities"]) == 3
    assert len(backend.list_rate_limit_excess_attempts(reviewer.address)) == 3
    assert chain.get_reviewer_vote_decision(reviewer.address).status == "COOLDOWN"


def test_peer_rate_offense_is_independently_verified_and_duplicate_is_idempotent(tmp_path, monkeypatch):
    reviewer = Account.create()
    creator = Account.create()
    source = SQLiteStorageBackend(sqlite_db_path=str(tmp_path / "peer-rate-source.db"))
    quota_votes = _record_probation_quota(source, reviewer, 4, 700, status_hash=f"{20:064x}")
    service = ReviewerReputationService(source)
    outcome = None
    for number in range(3):
        outcome = service.record_rate_limit_excess(
            _signed_vote(
                    reviewer, f"peer-rate-{number}", "unsure", 800 + number,
                    reviewer_status="PROBATIONARY_REVIEWER", reviewer_eligible=False,
                    status_height=20, status_hash=f"{20:064x}",
            ),
            reference_finalized_height=20,
            reference_finalized_block_hash=f"{20:064x}", review_epoch=4,
            state_before="PROBATIONARY_REVIEWER",
        )
    offense = outcome.offense

    target_storage = SQLiteStorageBackend(sqlite_db_path=str(tmp_path / "peer-rate-target.db"))
    target = Blockchain(Wallet(), Wallet(), Wallet(), storage_backend=target_storage)
    target.chain = [
        SimpleNamespace(
            index=height, hash=f"{height:064x}",
            creator_wallet=reviewer.address if height in {0, 1} else None,
            submission_id=f"qualification-{height}" if height in {0, 1} else None,
            native_transactions=[],
        )
        for height in range(21)
    ]
    target.finalized_blocks = [{"block_height": 20, "block_hash": f"{20:064x}"}]
    evidence_votes = (
        offense["evidence_payload"]["rate_limit_context"]["accepted_votes"]
        + offense["evidence_payload"]["votes"]
    )
    target.submissions = [
        Submission(
            image_path="", text_content="peer rate evidence", submitter=creator.address,
            submission_id=vote["submission_id"], content_hash=vote["content_hash"],
        )
        for vote in evidence_votes
    ]
    with pytest.raises(ValueError, match="canonical accepted history"):
        target.receive_reviewer_offense_evidence(offense)
    for vote in quota_votes:
        target_storage.record_durable_vote(vote, lifecycle_state="accepted")

    missing_quota = deepcopy(offense)
    missing_quota["evidence_payload"]["rate_limit_context"]["accepted_votes"] = []
    missing_quota["evidence_digest"] = canonical_hash(missing_quota["evidence_payload"])
    with pytest.raises(ValueError, match="exhausted reviewer quota"):
        target.receive_reviewer_offense_evidence(missing_quota)

    wrong_epoch = build_offense_evidence(
        offense_type=RATE_LIMIT_ABUSE,
        votes=offense["evidence_payload"]["votes"],
        rate_limit_accepted_votes=offense["evidence_payload"]["rate_limit_context"]["accepted_votes"],
        reference_finalized_height=20,
        reference_finalized_block_hash=f"{20:064x}", review_epoch=3,
    )
    with pytest.raises(ValueError, match="canonical review epoch"):
        target.receive_reviewer_offense_evidence(wrong_epoch)

    wrong_quota = deepcopy(offense)
    wrong_quota["evidence_payload"]["rate_limit_context"]["maximum_votes"] = 25
    wrong_quota["evidence_digest"] = canonical_hash(wrong_quota["evidence_payload"])
    with pytest.raises(ValueError, match="evidence_digest is inconsistent"):
        target.receive_reviewer_offense_evidence(wrong_quota)

    wrong_status_votes = deepcopy(offense["evidence_payload"]["votes"])
    for vote in wrong_status_votes:
        vote["reviewer_status"] = "ESTABLISHED_REVIEWER"
    wrong_status = build_offense_evidence(
        offense_type=RATE_LIMIT_ABUSE, votes=wrong_status_votes,
        rate_limit_accepted_votes=offense["evidence_payload"]["rate_limit_context"]["accepted_votes"],
        reference_finalized_height=20,
        reference_finalized_block_hash=f"{20:064x}", review_epoch=4,
    )
    with pytest.raises(ValueError, match="exhausted reviewer quota"):
        target.receive_reviewer_offense_evidence(wrong_status)

    duplicate_excess = build_offense_evidence(
        offense_type=RATE_LIMIT_ABUSE,
        votes=[offense["evidence_payload"]["votes"][0]] * 3,
        rate_limit_accepted_votes=offense["evidence_payload"]["rate_limit_context"]["accepted_votes"],
        reference_finalized_height=20,
        reference_finalized_block_hash=f"{20:064x}", review_epoch=4,
    )
    with pytest.raises(ValueError, match="excess-attempt threshold"):
        target.receive_reviewer_offense_evidence(duplicate_excess)

    fabricated_vote = _signed_vote(
        reviewer, "fabricated-quota", "unsure", 999,
        reviewer_status="PROBATIONARY_REVIEWER", status_height=20,
    )
    target.submissions.append(Submission(
        image_path="", text_content="fabricated quota", submitter=creator.address,
        submission_id=fabricated_vote["submission_id"], content_hash=fabricated_vote["content_hash"],
    ))
    fabricated_quota = build_offense_evidence(
        offense_type=RATE_LIMIT_ABUSE,
        votes=offense["evidence_payload"]["votes"],
        rate_limit_accepted_votes=[fabricated_vote] + quota_votes[1:],
        reference_finalized_height=20,
        reference_finalized_block_hash=f"{20:064x}", review_epoch=4,
    )
    with pytest.raises(ValueError, match="canonical accepted history"):
        target.receive_reviewer_offense_evidence(fabricated_quota)

    tampered = deepcopy(offense)
    tampered["evidence_digest"] = "00" * 32
    with pytest.raises(ValueError, match="digest"):
        target.receive_reviewer_offense_evidence(tampered)
    tampered_id = deepcopy(offense)
    tampered_id["offense_id"] = "00" * 32
    with pytest.raises(ValueError, match="offense_id"):
        target.receive_reviewer_offense_evidence(tampered_id)

    first = target.receive_reviewer_offense_evidence(offense)
    duplicate = target.receive_reviewer_offense_evidence(offense)
    assert first["action"] == "created"
    assert duplicate["action"] == "duplicate"
    assert len(target_storage.list_reviewer_offenses(reviewer.address)) == 1
    assert target_storage.list_reviewer_offenses(reviewer.address)[0]["offense_id"] == offense["offense_id"]
    target_penalty = target_storage.list_reviewer_penalties(reviewer.address)[0]
    assert target_penalty["penalty_status"] == outcome.penalty["penalty_status"]
    assert target_penalty["penalty_duration_epochs"] == outcome.penalty["penalty_duration_epochs"]
    assert target_penalty["penalty_end_epoch"] == outcome.penalty["penalty_end_epoch"]
    assert target.get_reviewer_vote_decision(reviewer.address).status == "COOLDOWN"

    import api
    import peer_sync
    from peers import PeerStore

    secret = "task-5-7-peer-secret"
    api.limiter.reset()
    api.NODE_ID = "local-node"
    api.PUBLIC_NODE_URL = "http://localhost:8000"
    api.NETWORK_NAME = "zoidberg-testnet"
    api.blockchain = target
    api.peer_store = PeerStore(storage_backend=target_storage)
    api.peer_store.register_peer(
        node_id="peer-node-1", url="http://peer-one.test:8000",
        network_name="zoidberg-testnet",
    )
    monkeypatch.setattr(api, "signed_peer_messages_enabled", lambda: True)
    monkeypatch.setattr(api, "peer_auth_required", lambda: False)
    monkeypatch.setattr(api, "peer_shared_secret", lambda: secret)
    monkeypatch.setattr(api, "peer_shared_secret_is_configured", lambda: True)
    monkeypatch.setattr(api, "peer_replay_protection_enabled", lambda: False)
    monkeypatch.setattr(api, "PEER_SIGNATURE_WINDOW_SECONDS", 300)
    monkeypatch.setattr(api.time, "time", lambda: 1_700_000_000)
    monkeypatch.setattr(peer_sync, "signed_peer_messages_enabled", lambda: True)
    monkeypatch.setattr(peer_sync, "peer_auth_required", lambda: False)
    monkeypatch.setattr(peer_sync, "peer_shared_secret", lambda: secret)
    monkeypatch.setattr(peer_sync, "peer_shared_secret_is_configured", lambda: True)
    monkeypatch.setattr(peer_sync, "peer_replay_protection_enabled", lambda: False)
    monkeypatch.setattr(peer_sync, "peer_signature_window_seconds", lambda: 300)
    monkeypatch.setattr(peer_sync.time, "time", lambda: 1_700_000_000)
    clear_protocol_v1_peer_replay_store_cache(data_dir=api.peer_store.storage.data_dir)
    payload = {
        "origin_node_id": "peer-node-1",
        "network_name": "zoidberg-testnet",
        "offense": offense,
    }
    headers = build_protocol_v1_peer_request_headers(
        "POST", "/peers/reviewer-offenses/receive", payload, "peer-node-1",
        network_name="zoidberg-testnet", secret=secret,
        timestamp=1_700_000_000, nonce="task-5-7-offense-nonce",
    )
    response = TestClient(api.app).post(
        "/peers/reviewer-offenses/receive", json=payload, headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["action"] == "duplicate"


def test_new_certificate_v3_binds_active_rule_while_historical_rule_remains_available():
    creator = Account.create()
    reviewers = [Account.create() for _ in range(5)]
    votes = [_signed_vote(reviewer, "active-v3", "original", 300 + index) for index, reviewer in enumerate(reviewers)]
    for index, vote in enumerate(votes):
        vote["reviewer_status"] = "ESTABLISHED_REVIEWER" if index == 0 else "PROBATIONARY_REVIEWER"
    snapshot = {
        "reviewer_policy_version": 1,
        "reputation_rule_version": 2,
        "reference_finalized_height": 20,
        "reference_finalized_block_hash": REFERENCE_HASH,
        "review_epoch": 4,
        "reviewers": sorted([
            {"address": vote["voter_wallet_address"].lower(), "status": vote["reviewer_status"], "bootstrap_provenance": None}
            for vote in votes
        ], key=lambda item: item["address"]),
    }
    from protocol_v1 import canonical_hash, canonical_json_text
    snapshot["reviewer_snapshot_digest"] = canonical_hash(snapshot)
    snapshot["canonical_serialization"] = canonical_json_text({key: value for key, value in snapshot.items() if key not in {"reviewer_snapshot_digest", "canonical_serialization"}})
    submission = SimpleNamespace(
        submission_id="active-v3", content_hash="11" * 32, content_id=None,
        submitter=creator.address.lower(), status=APPROVED,
    )
    evidence = {
        "originality_rule_version": 1,
        "final_prevote_decision": "FLAGGED_FOR_REVIEW",
        "originality_reference_height": 19,
        "originality_reference_block_hash": "19" * 32,
        "canonical_evidence_digest": "33" * 32,
    }
    certificate = OriginalityCertificate.from_approved_submission(
        submission, votes, minimum_votes_required=5,
        network_name="zoidberg-testnet", issuing_node_id="task-5-7-node",
        certificate_version=MILESTONE5_CERTIFICATE_V3_VERSION,
        originality_evidence=evidence, reviewer_snapshot=snapshot,
        established_vote_count=1, certificate_reference_height=20,
        certificate_reference_block_hash=REFERENCE_HASH,
        approved_at=1724760000.0, issued_timestamp="1724760000",
    )
    assert certificate.reputation_rule_version == 2
    assert reputation_rules(1)["automatic_penalties"]["enabled"] is False


def test_read_only_reputation_api_exposes_effective_state_and_history(blockchain):
    import api
    from peers import PeerStore

    api.limiter.reset()
    api.blockchain = blockchain
    api.peer_store = PeerStore(storage_backend=blockchain.storage)
    reviewer = Account.create()
    client = TestClient(api.app)
    status = client.get(f"/reviewers/{reviewer.address}/reputation")
    assert status.status_code == 200
    payload = status.json()
    assert payload["reviewer_address"] == reviewer.address.lower()
    assert payload["underlying_reviewer_status"] == "NEW"
    assert payload["effective_reviewer_status"] == "NEW"
    assert payload["reputation_rule_version"] == 2
    history = client.get(f"/reviewers/{reviewer.address}/offenses")
    assert history.status_code == 200
    assert history.json() == {"reviewer_address": reviewer.address.lower(), "offenses": []}
