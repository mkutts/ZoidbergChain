from __future__ import annotations

import json
import sqlite3

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from milestone5_policy import (
    REVIEWER_POLICY_VERSION,
    REPUTATION_RULE_VERSION,
    bootstrap_established_reviewers,
    reputation_rules_canonical_text,
    reputation_rules_digest,
    reviewer_policy,
    reviewer_policy_canonical_text,
    reviewer_policy_digest,
)
from protocol_v1 import PUBLIC_TESTNET_V1_NETWORK_ID
from protocol_v1_originality import (
    PROTOCOL_V1_VOTE_VERSION,
    build_protocol_v1_vote_message,
    calculate_signed_vote_identity,
)
from storage import SQLiteStorageBackend
from wallet import Wallet
from wallet_auth import WalletAuthManager


CONTENT_HASH = "ab" * 32
BLOCK_HASH = "cd" * 32


def _signed_vote(account, *, submission_id="submission-1", vote_type="original", nonce="nonce-1"):
    issued_at = "2026-09-08T12:00:00+00:00"
    expires_at = "2026-09-08T12:05:00+00:00"
    message = build_protocol_v1_vote_message(
        wallet_address=account.address,
        submission_id=submission_id,
        content_hash=CONTENT_HASH,
        vote_type=vote_type,
        nonce=nonce,
        issued_at=issued_at,
        expires_at=expires_at,
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
    )
    signature = Account.sign_message(encode_defunct(text=message), account.key).signature.hex()
    identity = calculate_signed_vote_identity(
        wallet_address=account.address,
        submission_id=submission_id,
        content_hash=CONTENT_HASH,
        vote_type=vote_type,
        nonce=nonce,
        issued_at=issued_at,
        expires_at=expires_at,
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
        signature=signature,
    )
    return {
        "submission_id": submission_id,
        "content_hash": CONTENT_HASH,
        "voter": account.address,
        "voter_wallet_address": account.address,
        "vote_type": vote_type,
        "vote_version": PROTOCOL_V1_VOTE_VERSION,
        "protocol_version": 1,
        "network_id": PUBLIC_TESTNET_V1_NETWORK_ID,
        "vote_nonce": nonce,
        "vote_issued_at": issued_at,
        "vote_expires_at": expires_at,
        "vote_signature": signature,
        "signature_scheme": "personal_sign",
        "vote_message": message,
        "vote_identity": identity,
        "reviewer_policy_version": REVIEWER_POLICY_VERSION,
        "reputation_rule_version": REPUTATION_RULE_VERSION,
        "reviewer_status": "ESTABLISHED_REVIEWER",
        "reviewer_status_effective_height": 10,
        "reviewer_status_reference_block_hash": BLOCK_HASH,
        "created_at": "2026-09-08T12:00:01+00:00",
    }


def test_policy_is_canonical_versioned_and_environment_independent(monkeypatch):
    first_reviewer = reviewer_policy_canonical_text()
    first_reputation = reputation_rules_canonical_text()
    first_digests = reviewer_policy_digest(), reputation_rules_digest()

    monkeypatch.setenv("REVIEW_ALLOWLIST_WALLETS", Account.create().address)
    monkeypatch.setenv("REVIEW_MIN_VOTE_COUNT", "999999")
    monkeypatch.setenv("REVIEW_ELIGIBILITY_MODE", "allowlist")

    assert reviewer_policy_canonical_text() == first_reviewer
    assert reputation_rules_canonical_text() == first_reputation
    assert (reviewer_policy_digest(), reputation_rules_digest()) == first_digests
    assert reviewer_policy()["vote_weight"] == 1
    assert reviewer_policy_digest() == "ac6140446255e0d2a4f076f0d257a48d6a6a446dde2272a51568e8f020ee90eb"
    assert reputation_rules_digest(1) == "9bfdfc196fd6d54796d699b513a550672b6e12d659b9dbb52f1e44b065be17fb"
    assert bootstrap_established_reviewers() == ()
    with pytest.raises(ValueError, match="Unsupported reviewer policy version"):
        reviewer_policy(999)


def test_reviewer_state_and_canonical_transition_history_survive_restart(isolated_data_dir):
    path = isolated_data_dir / "reviewer-state.db"
    reviewer = Account.create().address
    backend = SQLiteStorageBackend(sqlite_db_path=str(path))

    initial = backend.initialize_reviewer_state(reviewer)
    assert initial["current_status"] == "NEW"
    assert initial["status_effective_height"] is None
    backend.transition_reviewer_state(
        reviewer,
        to_status="PROBATIONARY_REVIEWER",
        status_effective_height=10,
        status_reference_block_hash=BLOCK_HASH,
        reason="future-earned-path-test",
    )

    restarted = SQLiteStorageBackend(sqlite_db_path=str(path))
    state = restarted.get_reviewer_state(reviewer)
    history = restarted.list_reviewer_state_history(reviewer)
    assert state["current_status"] == "PROBATIONARY_REVIEWER"
    assert state["status_effective_height"] == 10
    assert state["status_reference_block_hash"] == BLOCK_HASH
    assert [item["to_status"] for item in history] == ["NEW", "PROBATIONARY_REVIEWER"]
    assert history[1]["reason"] == "future-earned-path-test"


def test_invalid_reviewer_status_version_reference_and_bootstrap_fail(isolated_data_dir):
    backend = SQLiteStorageBackend(sqlite_db_path=str(isolated_data_dir / "invalid-reviewer.db"))
    reviewer = Account.create().address
    with pytest.raises(ValueError, match="Unsupported reviewer status"):
        backend.initialize_reviewer_state(reviewer, current_status="trusted")
    with pytest.raises(ValueError, match="Unsupported reviewer policy version"):
        backend.initialize_reviewer_state(reviewer, reviewer_policy_version=99)
    with pytest.raises(ValueError, match="status_reference_block_hash"):
        backend.initialize_reviewer_state(reviewer, status_effective_height=1)
    with pytest.raises(ValueError, match="versioned reviewer policy grant set"):
        backend.initialize_reviewer_state(
            reviewer, current_status="ESTABLISHED_REVIEWER", bootstrap_established=True
        )


def test_vote_restart_replay_counted_uniqueness_and_conflict_evidence(isolated_data_dir):
    path = isolated_data_dir / "votes.db"
    backend = SQLiteStorageBackend(sqlite_db_path=str(path))
    account = Account.create()
    accepted_vote = _signed_vote(account)

    accepted = backend.record_durable_vote(accepted_vote)
    replay = backend.record_durable_vote(dict(accepted_vote))
    conflicting_vote = _signed_vote(account, vote_type="not_original", nonce="nonce-2")
    conflict = backend.record_durable_vote(conflicting_vote)

    assert accepted["lifecycle_state"] == "accepted"
    assert replay["replay"] is True
    assert conflict["lifecycle_state"] == "rejected"
    assert conflict["rejection_reason"] == "conflicting_counted_vote"

    restarted = SQLiteStorageBackend(sqlite_db_path=str(path))
    records = restarted.list_durable_votes(submission_id="submission-1")
    assert len(records) == 2
    assert sum(record["lifecycle_state"] == "accepted" for record in records) == 1
    assert {record["vote_choice"] for record in records} == {"original", "not_original"}
    assert all(record["signature"] for record in records)


def test_signed_vote_path_persists_verified_payload_without_changing_vote_api(isolated_data_dir):
    from blockchain import Blockchain

    path = isolated_data_dir / "signed-path.db"
    backend = SQLiteStorageBackend(sqlite_db_path=str(path))
    chain = Blockchain(Wallet(), Wallet(), Wallet(), storage_backend=backend)
    submission = chain.submit_content_operation(
        image_path=str(isolated_data_dir / "zoidberg.jpg"),
        text_content="Task 5.2 signed persistence",
        submitter="creator-public-key",
    )
    account = Account.create()
    auth = WalletAuthManager(network_name="zoidberg-testnet", environment="testing")
    challenge = auth.issue_vote_challenge(
        wallet_address=account.address,
        submission_id=submission.submission_id,
        content_hash=submission.content_hash,
        vote_type="original",
    )
    signature = Account.sign_message(
        encode_defunct(text=challenge["message"]), account.key
    ).signature.hex()

    vote = chain.cast_signed_submission_vote_operation(
        submission_id=submission.submission_id,
        voter=account.address,
        vote_type="original",
        message=challenge["message"],
        signature=signature,
        auth_manager=auth,
    )

    assert vote["vote_identity"]
    record = SQLiteStorageBackend(sqlite_db_path=str(path)).list_durable_votes(
        submission_id=submission.submission_id
    )[0]
    assert record["lifecycle_state"] == "accepted"
    assert record["vote_identity"] == vote["vote_identity"]
    assert record["reviewer_policy_version"] is None
    assert record["reputation_rule_version"] is None


def test_vote_identity_and_policy_identity_match_across_independent_nodes(isolated_data_dir):
    account = Account.create()
    vote = _signed_vote(account)
    node_a = SQLiteStorageBackend(sqlite_db_path=str(isolated_data_dir / "node-a.db"))
    node_b = SQLiteStorageBackend(sqlite_db_path=str(isolated_data_dir / "node-b.db"))

    result_a = node_a.record_durable_vote(dict(vote))
    result_b = node_b.record_durable_vote(dict(vote))

    assert result_a["vote_identity"] == result_b["vote_identity"] == vote["vote_identity"]
    assert reviewer_policy_digest() == reviewer_policy_digest(REVIEWER_POLICY_VERSION)
    assert bootstrap_established_reviewers() == bootstrap_established_reviewers(REVIEWER_POLICY_VERSION)


def test_vote_identity_binds_payload_and_signature():
    account = Account.create()
    first = _signed_vote(account)
    changed = _signed_vote(account, vote_type="unsure", nonce="nonce-2")
    assert first["vote_identity"] != changed["vote_identity"]
    assert calculate_signed_vote_identity(
        wallet_address=first["voter"], submission_id=first["submission_id"],
        content_hash=first["content_hash"], vote_type=first["vote_type"],
        nonce=first["vote_nonce"], issued_at=first["vote_issued_at"],
        expires_at=first["vote_expires_at"], network_id=first["network_id"],
        signature="0x" + first["vote_signature"].removeprefix("0x"),
    ) == first["vote_identity"]


def test_vote_reviewer_snapshot_rejects_partial_or_unknown_policy(isolated_data_dir):
    backend = SQLiteStorageBackend(sqlite_db_path=str(isolated_data_dir / "invalid-vote-policy.db"))
    vote = _signed_vote(Account.create())
    vote["reviewer_policy_version"] = 999
    with pytest.raises(ValueError, match="Unsupported reviewer policy version"):
        backend.record_durable_vote(vote)
    vote["reviewer_policy_version"] = REVIEWER_POLICY_VERSION
    vote["reviewer_status"] = None
    with pytest.raises(ValueError, match="must be recorded together"):
        backend.record_durable_vote(vote)


def test_pre_task_5_2_sqlite_schema_migrates_idempotently_and_preserves_votes(isolated_data_dir):
    path = isolated_data_dir / "legacy.db"
    legacy_vote = {
        "submission_id": "legacy-submission",
        "voter": "legacy-public-key",
        "vote_type": "original",
        "created_at": 123,
    }
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE storage_sections (section_name TEXT PRIMARY KEY, json_data TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO storage_sections VALUES ('votes', ?, 'legacy')", (json.dumps([legacy_vote]),)
        )

    first = SQLiteStorageBackend(sqlite_db_path=str(path))
    assert first.load_votes() == [legacy_vote]
    migrated = first.list_durable_votes()
    assert len(migrated) == 1
    assert migrated[0]["identity_status"] == "legacy_unverifiable"
    assert migrated[0]["vote_identity"] is None

    second = SQLiteStorageBackend(sqlite_db_path=str(path))
    assert second.load_votes() == [legacy_vote]
    assert second.list_durable_votes() == migrated
    with sqlite3.connect(path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"reviewer_states", "reviewer_state_transitions", "durable_vote_records"} <= tables
