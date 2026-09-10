from copy import deepcopy
import sqlite3
from types import SimpleNamespace

from eth_account import Account
from eth_account.messages import encode_defunct
import pytest

import originality_certificate as certificate_module
from milestone5_policy import (
    APPROVAL_THRESHOLD_BPS,
    MIN_ESTABLISHED_VOTES,
    MIN_VALID_VOTES,
    certificate_v3_approval_passes,
    certificate_v3_quorum_satisfied,
    reputation_rules_digest,
    reviewer_policy_digest,
)
from originality_certificate import (
    OriginalityCertificate,
    build_certificate_identity_payload_v3,
    calculate_certificate_id,
    validate_certificate_for_submission,
)
from protocol_v1 import PUBLIC_TESTNET_V1_NETWORK_ID, canonical_hash, canonical_json_text
from protocol_v1_originality import (
    MILESTONE5_CERTIFICATE_V3_VERSION,
    build_protocol_v1_vote_message,
    calculate_signed_vote_identity,
)
from submission import APPROVED
from storage import SQLiteStorageBackend
from submission import Submission
from blockchain import Blockchain
from wallet import Wallet
from wallet_auth import hash_wallet_message


GOLDEN_V3_CERTIFICATE_ID = "602fab0ee3ef97a46c5fa759399636a8ea6729a4fde386c2d8bc3f6ef0b7766e"
GOLDEN_V3_CANONICAL_PAYLOAD = (
    '{"approval_threshold_bps":7000,"certificate_reference_block_hash":"6666666666666666666666666666666666666666666666666666666666666666",'
    '"certificate_reference_height":8,"certificate_version":3,"content_hash":"1111111111111111111111111111111111111111111111111111111111111111",'
    '"creator_address":"0x2222222222222222222222222222222222222222","established_vote_count":2,"issued_timestamp":"1724760002.75",'
    '"minimum_established_votes":1,"minimum_valid_votes":5,"network_id":"zoidberg-public-testnet-v1","not_original_votes":1,"original_votes":4,'
    '"originality_decision":"FLAGGED_FOR_REVIEW","originality_evidence_digest":"4444444444444444444444444444444444444444444444444444444444444444",'
    '"originality_reference_block_hash":"3333333333333333333333333333333333333333333333333333333333333333","originality_reference_height":7,'
    '"originality_rule_version":1,"protocol_version":1,"reputation_rule_version":1,"reviewer_policy_version":1,'
    '"reviewer_snapshot_digest":"5555555555555555555555555555555555555555555555555555555555555555",'
    '"reviewer_snapshot_reference_block_hash":"6666666666666666666666666666666666666666666666666666666666666666",'
    '"reviewer_snapshot_reference_height":8,"submission_id":"submission-v3-golden","total_valid_votes":6,"unsure_votes":1,'
    '"vote_set_hash":"7777777777777777777777777777777777777777777777777777777777777777"}'
)


def _golden_fields():
    return {
        "certificate_version": 3,
        "protocol_version": 1,
        "network_id": PUBLIC_TESTNET_V1_NETWORK_ID,
        "submission_id": "submission-v3-golden",
        "content_hash": "11" * 32,
        "creator_address": "0x" + "22" * 20,
        "originality_rule_version": 1,
        "originality_decision": "FLAGGED_FOR_REVIEW",
        "originality_reference_height": 7,
        "originality_reference_block_hash": "33" * 32,
        "originality_evidence_digest": "44" * 32,
        "reviewer_policy_version": 1,
        "reputation_rule_version": 1,
        "reviewer_snapshot_reference_height": 8,
        "reviewer_snapshot_reference_block_hash": "66" * 32,
        "reviewer_snapshot_digest": "55" * 32,
        "minimum_valid_votes": 5,
        "minimum_established_votes": 1,
        "approval_threshold_bps": 7000,
        "total_valid_votes": 6,
        "established_vote_count": 2,
        "original_votes": 4,
        "not_original_votes": 1,
        "unsure_votes": 1,
        "vote_set_hash": "77" * 32,
        "certificate_reference_height": 8,
        "certificate_reference_block_hash": "66" * 32,
        "issued_timestamp": "1724760002.75",
    }


def _signed_vote(account, submission_id, content_hash, choice, status, number):
    nonce = f"nonce-{number}"
    issued_at = f"17247600{number}.0"
    expires_at = f"17248600{number}.0"
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
        "voter": account.address.lower(),
        "voter_wallet_address": account.address.lower(),
        "vote_type": choice,
        "signature_scheme": "personal_sign",
        "vote_signature": signature,
        "vote_message": message,
        "signed_message_hash": hash_wallet_message(message),
        "vote_nonce": nonce,
        "vote_issued_at": issued_at,
        "vote_expires_at": expires_at,
        "created_at": 1_724_760_000 + number,
        "reviewer_policy_version": 1,
        "reputation_rule_version": 1,
        "reviewer_status": status,
        "reviewer_eligible": True,
        "reviewer_status_effective_height": 8,
        "reviewer_status_reference_block_hash": "66" * 32,
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


def test_v3_constants_and_policy_identities_are_locked():
    assert (MIN_VALID_VOTES, MIN_ESTABLISHED_VOTES, APPROVAL_THRESHOLD_BPS) == (5, 1, 7000)
    assert reviewer_policy_digest() == "ac6140446255e0d2a4f076f0d257a48d6a6a446dde2272a51568e8f020ee90eb"
    assert reputation_rules_digest() == "9bfdfc196fd6d54796d699b513a550672b6e12d659b9dbb52f1e44b065be17fb"


def test_v3_canonical_payload_and_certificate_id_golden_vector():
    fields = _golden_fields()
    assert canonical_json_text(build_certificate_identity_payload_v3(fields)) == GOLDEN_V3_CANONICAL_PAYLOAD
    assert calculate_certificate_id(
        fields, certificate_version=3, network_id=PUBLIC_TESTNET_V1_NETWORK_ID
    ) == GOLDEN_V3_CERTIFICATE_ID


def test_integer_approval_boundaries_and_unsure_quorum_semantics():
    assert certificate_v3_approval_passes(7, 3)
    assert not certificate_v3_approval_passes(69, 31)
    assert certificate_v3_quorum_satisfied(
        total_valid_votes=5, established_vote_count=1,
        original_votes=7, not_original_votes=3,
    )
    assert not certificate_v3_quorum_satisfied(
        total_valid_votes=4, established_vote_count=1,
        original_votes=7, not_original_votes=3,
    )
    assert not certificate_v3_quorum_satisfied(
        total_valid_votes=5, established_vote_count=0,
        original_votes=7, not_original_votes=3,
    )


def test_v3_validation_recomputes_votes_snapshot_established_count_and_identity(monkeypatch):
    creator = Account.create()
    reviewers = [Account.create() for _ in range(5)]
    submission_id = "submission-v3-validation"
    content_hash = "11" * 32
    votes = [
        _signed_vote(
            account, submission_id, content_hash,
            "original" if index < 4 else "not_original",
            "ESTABLISHED_REVIEWER" if index == 0 else "PROBATIONARY_REVIEWER",
            index,
        )
        for index, account in enumerate(reviewers)
    ]
    snapshot_payload = {
        "reviewer_policy_version": 1,
        "reputation_rule_version": 1,
        "reference_finalized_height": 8,
        "reference_finalized_block_hash": "66" * 32,
        "review_epoch": 1,
        "reviewers": sorted([
            {
                "address": vote["voter_wallet_address"],
                "status": vote["reviewer_status"],
                "bootstrap_provenance": None,
            }
            for vote in votes
        ], key=lambda item: item["address"]),
    }
    snapshot = {
        **snapshot_payload,
        "reviewer_snapshot_digest": canonical_hash(snapshot_payload),
        "canonical_serialization": canonical_json_text(snapshot_payload),
    }
    evidence = {
        "originality_rule_version": 1,
        "final_prevote_decision": "FLAGGED_FOR_REVIEW",
        "originality_reference_height": 7,
        "originality_reference_block_hash": "33" * 32,
        "canonical_evidence_digest": "44" * 32,
    }
    submission = SimpleNamespace(
        submission_id=submission_id,
        content_hash=content_hash,
        content_id=None,
        submitter=creator.address,
        status=APPROVED,
    )
    certificate = OriginalityCertificate.from_approved_submission(
        submission, votes, minimum_votes_required=5,
        network_name="zoidberg-testnet", issuing_node_id="node-v3",
        approved_at=1724760002.75,
        certificate_version=MILESTONE5_CERTIFICATE_V3_VERSION,
        originality_evidence=evidence,
        reviewer_snapshot=snapshot,
        established_vote_count=1,
        certificate_reference_height=8,
        certificate_reference_block_hash="66" * 32,
        issued_timestamp="1724760002.75",
    )
    chain = [{"index": index, "hash": ("33" * 32 if index == 7 else "66" * 32 if index == 8 else f"{index:064x}")} for index in range(9)]
    monkeypatch.setattr(certificate_module, "revalidate_certificate_originality_evidence", lambda *args, **kwargs: evidence)
    statuses = {vote["voter_wallet_address"]: vote["reviewer_status"] for vote in votes}
    validate = lambda candidate, vote_set=votes, snapshot_value=snapshot: validate_certificate_for_submission(
        candidate, submission, originality_evidence=evidence, chain=chain,
        media_bytes=b"media", mime_type="image/jpeg", votes=vote_set,
        reviewer_snapshot=snapshot_value,
        reviewer_status_resolver=lambda address, height, block_hash: statuses[address],
        finalized_reference_validator=lambda height, block_hash: height == 8 and block_hash == "66" * 32,
    )
    assert validate(certificate)
    assert all(getattr(certificate, field) is not None for field in (
        "reviewer_policy_version", "reputation_rule_version",
        "reviewer_snapshot_reference_height", "reviewer_snapshot_reference_block_hash",
        "reviewer_snapshot_digest", "minimum_valid_votes",
        "minimum_established_votes", "approval_threshold_bps",
        "total_valid_votes", "established_vote_count", "vote_set_hash",
    ))
    with pytest.raises(ValueError, match="counted vote set is incomplete"):
        validate(certificate, votes[:-1])
    tampered = deepcopy(certificate)
    tampered.established_vote_count = 2
    with pytest.raises(ValueError, match="established vote count"):
        validate(tampered)
    tampered = deepcopy(certificate)
    tampered.reviewer_snapshot_digest = "ff" * 32
    with pytest.raises(ValueError, match="snapshot digest"):
        validate(tampered)
    tampered = deepcopy(certificate)
    tampered.reviewer_policy_version = 2
    with pytest.raises(ValueError, match="reviewer_policy_version"):
        validate(tampered)
    tampered = deepcopy(certificate)
    tampered.minimum_valid_votes = tampered.minimum_votes_required = 6
    with pytest.raises(ValueError, match="minimum valid-vote quorum"):
        validate(tampered)
    tampered = deepcopy(certificate)
    tampered.vote_hash = tampered.vote_set_hash = "ee" * 32
    with pytest.raises(ValueError, match="vote-set hash"):
        validate(tampered)
    statuses[votes[0]["voter_wallet_address"]] = "PROBATIONARY_REVIEWER"
    with pytest.raises(ValueError, match="not locally reproducible"):
        validate(certificate)


def test_expired_voting_window_cannot_bypass_v3_fixed_quorum(blockchain, submission_image):
    creator = Account.create()
    submission = blockchain.submit_content(
        image_path=str(submission_image), text_content="fixed quorum expiry",
        submitter=creator.address,
    )
    genesis = blockchain.chain[0]
    blockchain.finalized_blocks = [{
        "block_height": 0,
        "block_hash": genesis.hash,
    }]
    result = blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=submission.created_at + (48 * 60 * 60),
    )
    assert result["voting_window_expired"] is True
    assert result["minimum_votes"] == 5
    assert result["minimum_votes_reached"] is False
    assert result["reason"] == "awaiting_fixed_quorum"
    assert blockchain.get_originality_certificate_for_submission(submission.submission_id) is None


def test_self_vote_uses_normalized_wallet_identity(blockchain, submission_image):
    creator = Account.create()
    submission = blockchain.submit_content(
        image_path=str(submission_image), text_content="normalized self vote",
        submitter=creator.address,
    )
    with pytest.raises(ValueError, match="creator cannot vote"):
        blockchain.cast_submission_vote(
            submission.submission_id, creator.address.lower(), "original"
        )


def test_task55_sqlite_schema_migrates_idempotently_for_v3(tmp_path):
    path = tmp_path / "task55.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """CREATE TABLE originality_certificate_evidence_bindings (
                certificate_id TEXT PRIMARY KEY,
                certificate_version INTEGER NOT NULL CHECK (certificate_version = 2),
                submission_id TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                evidence_digest TEXT NOT NULL,
                originality_reference_height INTEGER NOT NULL,
                originality_reference_block_hash TEXT NOT NULL,
                certificate_reference_height INTEGER NOT NULL,
                certificate_reference_block_hash TEXT NOT NULL,
                binding_status TEXT NOT NULL
            )"""
        )
        connection.execute(
            "INSERT INTO originality_certificate_evidence_bindings VALUES (?, 2, ?, ?, ?, 0, ?, 0, ?, 'active')",
            ("aa" * 32, "historical", "bb" * 32, "cc" * 32, "dd" * 32, "dd" * 32),
        )
    SQLiteStorageBackend(sqlite_db_path=str(path))
    SQLiteStorageBackend(sqlite_db_path=str(path))
    with sqlite3.connect(path) as connection:
        sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='originality_certificate_evidence_bindings'"
        ).fetchone()[0]
        columns = {row[1] for row in connection.execute("PRAGMA table_info(durable_vote_records)")}
        rows = connection.execute(
            "SELECT certificate_id, certificate_version FROM originality_certificate_evidence_bindings"
        ).fetchall()
    assert "IN (2, 3)" in sql
    assert "reviewer_eligible" in columns
    assert rows == [("aa" * 32, 2)]


def test_blockchain_reconstructs_established_participation_without_weighting(tmp_path):
    backend = SQLiteStorageBackend(sqlite_db_path=str(tmp_path / "context.db"))
    chain = Blockchain(Wallet(), Wallet(), Wallet(), storage_backend=backend)
    creator = Account.create()
    reviewers = [Account.create() for _ in range(5)]
    creator_by_height = {
        index: reviewers[index // 2].address
        for index in range(10)
    }
    chain.chain = [
        SimpleNamespace(
            index=height,
            hash=f"{height:064x}",
            creator_wallet=creator_by_height.get(height),
            submission_id=(f"qualification-{height}" if height in creator_by_height else None),
            native_transactions=[],
        )
        for height in range(31)
    ]
    chain.finalized_blocks = [
        {"block_height": height, "block_hash": f"{height:064x}"}
        for height in (15, 20, 30)
    ]
    established = reviewers[0]
    for number in range(10):
        backend.record_durable_vote({
            "submission_id": f"probation-history-{number}",
            "voter": established.address,
            "vote_type": "unsure",
            "reviewer_policy_version": 1,
            "reputation_rule_version": 1,
            "reviewer_status": "PROBATIONARY_REVIEWER",
            "reviewer_status_effective_height": 15 if number < 5 else 20,
            "reviewer_status_reference_block_hash": f"{15 if number < 5 else 20:064x}",
            "created_at": f"history-{number}",
        })
    submission = Submission(
        image_path="", text_content="v3 vote context", submitter=creator.address,
        submission_id="v3-context", content_hash="11" * 32,
    )
    chain.submissions = [submission]
    chain.votes = []
    for index, reviewer in enumerate(reviewers):
        status = "ESTABLISHED_REVIEWER" if index == 0 else "PROBATIONARY_REVIEWER"
        vote = _signed_vote(
            reviewer, submission.submission_id, submission.content_hash,
            "original", status, index,
        )
        vote["reviewer_status_effective_height"] = 30
        vote["reviewer_status_reference_block_hash"] = f"{30:064x}"
        backend.record_durable_vote(vote)
        chain.votes.append(vote)
    context = chain.get_certificate_v3_vote_context(submission.submission_id)
    assert len(context["votes"]) == 5
    assert context["established_vote_count"] == 1
    assert [vote["vote_type"] for vote in context["votes"]] == ["original"] * 5
