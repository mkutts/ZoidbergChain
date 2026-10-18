from __future__ import annotations

import pytest
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from eth_account import Account
from eth_account.messages import encode_defunct

from dual_review import (
    ADMISSIBILITY, ORIGINALITY, REVIEW_VOTE_VERSION, combined_review,
    review_policy_digest, tally, vote_message,
)
from protocol_v1 import PUBLIC_TESTNET_V1_NETWORK_ID
from wallet_auth import WalletAuthManager, hash_wallet_message
from dual_review import vote_identity
from storage import JSONStorageBackend, SQLiteStorageBackend
from peer_sync import MalformedVoteError, _normalize_vote_payload
from reviewer_reputation import SIGNED_VOTE_EQUIVOCATION, build_offense_evidence, validate_offense_evidence


def _votes(dimension, positive, negative=0, unsure=0):
    choices = ([positive] * 4) + [negative if negative else "unsure"]
    if unsure:
        choices = ([positive] * (5 - unsure)) + (["unsure"] * unsure)
    return [
        {
            "dimension": dimension,
            "vote_version": REVIEW_VOTE_VERSION,
            "voter": f"0x{index + (0 if dimension == ORIGINALITY else 10):040x}",
            "vote_type": choice,
            "vote_identity": f"identity-{dimension}-{index}",
            "reviewer_eligible": True,
            "reviewer_status": "ESTABLISHED_REVIEWER" if index == 0 else "PROBATIONARY_REVIEWER",
        }
        for index, choice in enumerate(choices)
    ]


@pytest.mark.parametrize("originality_choice,admissibility_choice,qualified", [
    ("original", "admissible", True),
    ("original", "not_admissible", False),
    ("not_original", "admissible", False),
    ("not_original", "not_admissible", False),
])
def test_independent_outcomes(originality_choice, admissibility_choice, qualified):
    votes = _votes(ORIGINALITY, originality_choice) + _votes(ADMISSIBILITY, admissibility_choice)
    result = combined_review(votes)
    assert result["originality"]["outcome"] == originality_choice
    assert result["admissibility"]["outcome"] == admissibility_choice
    assert result["review_complete"]
    assert result["review_qualified"] is qualified
    assert combined_review(list(reversed(votes))) == result


def test_one_dimension_resolved_and_all_unsure_unresolved():
    original = _votes(ORIGINALITY, "original")
    unsure = _votes(ADMISSIBILITY, "admissible", unsure=5)
    result = combined_review(original + unsure)
    assert result["originality"]["resolved"]
    assert result["admissibility"]["eligible_valid_votes"] == 5
    assert result["admissibility"]["approval_denominator"] == 0
    assert result["admissibility"]["outcome"] == "unresolved"
    assert not result["review_complete"]
    assert not combined_review([])["review_complete"]


@pytest.mark.parametrize("dimension,positive", [(ORIGINALITY, "original"), (ADMISSIBILITY, "admissible")])
def test_unsure_quorum_and_threshold_boundary(dimension, positive):
    votes = _votes(dimension, positive, unsure=2)
    result = tally(votes, dimension)
    assert result["eligible_valid_votes"] == 5
    assert result["approval_denominator"] == 3
    assert result["outcome"] == positive
    votes[0]["reviewer_status"] = "PROBATIONARY_REVIEWER"
    assert tally(votes, dimension)["outcome"] == "unresolved"


@pytest.mark.parametrize("dimension,positive,negative", [
    (ORIGINALITY, "original", "not_original"),
    (ADMISSIBILITY, "admissible", "not_admissible"),
])
def test_exact_seventy_percent_boundary_and_ineligible_vote(dimension, positive, negative):
    votes = [
        {"dimension": dimension, "vote_version": REVIEW_VOTE_VERSION,
         "voter": f"0x{index + 1:040x}", "vote_type": positive if index < 7 else negative,
         "vote_identity": f"identity-{index}", "reviewer_eligible": True,
         "reviewer_status": "ESTABLISHED_REVIEWER" if index == 0 else "PROBATIONARY_REVIEWER"}
        for index in range(10)
    ]
    assert tally(votes, dimension)["outcome"] == positive
    votes[6]["vote_type"] = negative
    assert tally(votes, dimension)["outcome"] == negative
    votes[0]["reviewer_eligible"] = False
    assert tally(votes, dimension)["outcome"] == "unresolved"


def test_legacy_votes_do_not_become_dual_votes():
    legacy = _votes(ORIGINALITY, "original")
    for vote in legacy:
        vote.pop("vote_version")
        vote.pop("dimension")
    assert combined_review(legacy)["originality"]["eligible_valid_votes"] == 0


def test_signature_message_binds_dimension_and_choice():
    payload = dict(
        wallet_address="0x" + "12" * 20,
        submission_id="a" * 32,
        content_hash="b" * 64,
        nonce="nonce", issued_at="2026-09-30T00:00:00Z",
        expires_at="2026-09-30T00:05:00Z",
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
    )
    original = vote_message(**payload, dimension=ORIGINALITY, choice="original")
    admissible = vote_message(**payload, dimension=ADMISSIBILITY, choice="admissible")
    assert original != admissible
    assert review_policy_digest() in original
    with pytest.raises(ValueError):
        vote_message(**payload, dimension=ADMISSIBILITY, choice="original")
    with pytest.raises(ValueError):
        vote_message(**(payload | {"network_id": "another-network"}), dimension=ORIGINALITY, choice="original")


def test_dual_review_policy_and_signed_vote_golden_vector():
    account = Account.from_key(bytes.fromhex("11" * 32))
    payload = dict(
        wallet_address=account.address, submission_id="a" * 32,
        content_hash="b" * 64, dimension=ADMISSIBILITY,
        choice="admissible", nonce="golden-nonce",
        issued_at="2026-09-30T00:00:00Z", expires_at="2026-09-30T00:05:00Z",
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
    )
    message = vote_message(**payload)
    signature = Account.sign_message(encode_defunct(text=message), account.key).signature.hex()
    assert review_policy_digest() == "e7121a30c376924acc5af64f9b6ab210bfbf4652ed61839602cb52faa190a6e2"
    assert sha256(message.encode()).hexdigest() == "9f52bef614c302a9f5c168c2d86d64a5e2ade2b2f38402c210d24e3c9753db7c"
    assert vote_identity(signature=signature, **payload) == "14253904911ad26ae4b39d2e040b6407a724960cada2f0f63923353eb70bd415"


def test_challenge_rejects_cross_dimension_and_replay():
    manager = WalletAuthManager(network_name="zoidberg-testnet", environment="development")
    account = Account.create()
    challenge = manager.issue_vote_challenge(
        wallet_address=account.address, submission_id="a" * 32,
        content_hash="b" * 64, vote_type="admissible", dimension=ADMISSIBILITY,
    )
    signature = Account.sign_message(encode_defunct(text=challenge["message"]), account.key).signature.hex()
    common = dict(
        wallet_address=account.address, message=challenge["message"],
        signature=signature, submission_id="a" * 32,
        content_hash="b" * 64, vote_type="admissible",
    )
    with pytest.raises(ValueError, match="dimension"):
        manager.verify_vote_signature(**common, dimension=ORIGINALITY)
    with pytest.raises(ValueError, match="submission_id"):
        manager.verify_vote_signature(**(common | {"submission_id": "c" * 32}), dimension=ADMISSIBILITY)
    verified = manager.verify_vote_signature(**common, dimension=ADMISSIBILITY)
    assert verified["vote_version"] == REVIEW_VOTE_VERSION
    with pytest.raises(ValueError, match="already been used"):
        manager.verify_vote_signature(**common, dimension=ADMISSIBILITY)


def test_sqlite_accepts_one_vote_per_dimension_and_survives_restart(tmp_path):
    path = tmp_path / "review.db"
    backend = SQLiteStorageBackend(sqlite_db_path=str(path))
    manager = WalletAuthManager(network_name="zoidberg-testnet", environment="development")
    account = Account.create()
    submission_id, content_hash = "a" * 32, "b" * 64
    votes = []
    for dimension, choice in ((ORIGINALITY, "original"), (ADMISSIBILITY, "not_admissible")):
        challenge = manager.issue_vote_challenge(
            wallet_address=account.address, submission_id=submission_id,
            content_hash=content_hash, vote_type=choice, dimension=dimension,
        )
        signature = Account.sign_message(encode_defunct(text=challenge["message"]), account.key).signature.hex()
        vote = {
            "voter": account.address.lower(), "voter_wallet_address": account.address.lower(),
            "submission_id": submission_id, "content_hash": content_hash,
            "vote_type": choice, "dimension": dimension, "vote_version": REVIEW_VOTE_VERSION,
            "protocol_version": 1, "network_id": challenge["network_id"],
            "signature_scheme": "personal_sign", "vote_signature": signature,
            "vote_message": challenge["message"], "vote_nonce": challenge["nonce"],
            "vote_issued_at": challenge["issued_at"], "vote_expires_at": challenge["expires_at"],
        }
        vote["vote_identity"] = vote_identity(
            signature=signature, wallet_address=account.address,
            submission_id=submission_id, content_hash=content_hash,
            dimension=dimension, choice=choice, nonce=challenge["nonce"],
            issued_at=challenge["issued_at"], expires_at=challenge["expires_at"],
            network_id=challenge["network_id"],
        )
        assert backend.record_durable_vote(vote)["lifecycle_state"] == "accepted"
        votes.append(vote)
    restarted = SQLiteStorageBackend(sqlite_db_path=str(path))
    records = restarted.list_durable_votes(submission_id=submission_id)
    assert {record["dimension"] for record in records} == {ORIGINALITY, ADMISSIBILITY}
    assert len(records) == 2
    json_backend = JSONStorageBackend(blockchain_file=str(tmp_path / "review.json"),
                                      peers_file=str(tmp_path / "peers.json"))
    json_backend.save_votes(votes)
    backend.save_votes(votes)
    assert combined_review(json_backend.load_votes()) == combined_review(restarted.load_votes())


def test_existing_sqlite_vote_table_upgrades_additively_and_idempotently(tmp_path):
    path = tmp_path / "upgrade.db"
    backend = SQLiteStorageBackend(sqlite_db_path=str(path))
    legacy_vote = {"submission_id": "a" * 32, "voter": "0x" + "12" * 20,
                   "vote_type": "original", "created_at": 1.0}
    assert backend.record_durable_vote(legacy_vote)["lifecycle_state"] == "accepted"
    with sqlite3.connect(path) as connection:
        connection.execute("DROP INDEX one_accepted_vote_per_submission_wallet")
        connection.execute("ALTER TABLE durable_vote_records DROP COLUMN dimension")
        connection.execute("""CREATE UNIQUE INDEX one_accepted_vote_per_submission_wallet
                           ON durable_vote_records(submission_id, voter_address)
                           WHERE lifecycle_state = 'accepted'""")

    for _ in range(2):
        upgraded = SQLiteStorageBackend(sqlite_db_path=str(path))
        records = upgraded.list_durable_votes(submission_id=legacy_vote["submission_id"])
        assert len(records) == 1
        assert records[0]["dimension"] == ORIGINALITY
        assert records[0]["vote_choice"] == "original"
        with sqlite3.connect(path) as connection:
            columns = [row[2] for row in connection.execute(
                "PRAGMA index_info(one_accepted_vote_per_submission_wallet)")]
        assert columns == ["submission_id", "voter_address", "dimension"]


def test_concurrent_same_dimension_votes_have_one_durable_winner(tmp_path):
    backend = SQLiteStorageBackend(sqlite_db_path=str(tmp_path / "concurrent.db"))
    manager = WalletAuthManager(network_name="zoidberg-testnet", environment="development")
    account = Account.create()
    submission_id, content_hash = "a" * 32, "b" * 64

    def signed_vote(choice):
        challenge = manager.issue_vote_challenge(
            wallet_address=account.address, submission_id=submission_id,
            content_hash=content_hash, vote_type=choice, dimension=ORIGINALITY,
        )
        signature = Account.sign_message(encode_defunct(text=challenge["message"]), account.key).signature.hex()
        vote = {
            "voter": account.address.lower(), "voter_wallet_address": account.address.lower(),
            "submission_id": submission_id, "content_hash": content_hash,
            "vote_type": choice, "dimension": ORIGINALITY, "vote_version": REVIEW_VOTE_VERSION,
            "protocol_version": 1, "network_id": challenge["network_id"],
            "signature_scheme": "personal_sign", "vote_signature": signature,
            "vote_message": challenge["message"], "vote_nonce": challenge["nonce"],
            "vote_issued_at": challenge["issued_at"], "vote_expires_at": challenge["expires_at"],
        }
        vote["vote_identity"] = vote_identity(
            signature=signature, wallet_address=account.address,
            submission_id=submission_id, content_hash=content_hash,
            dimension=ORIGINALITY, choice=choice, nonce=challenge["nonce"],
            issued_at=challenge["issued_at"], expires_at=challenge["expires_at"],
            network_id=challenge["network_id"],
        )
        return vote

    first, second = signed_vote("original"), signed_vote("not_original")
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(backend.record_durable_vote, (first, second)))
    assert {result["lifecycle_state"] for result in outcomes} == {"accepted", "rejected"}
    assert sum(record["lifecycle_state"] == "accepted"
               for record in backend.list_durable_votes(submission_id=submission_id)) == 1


def test_peer_reconstructs_dimension_bound_message():
    manager = WalletAuthManager(network_name="zoidberg-testnet", environment="development")
    account = Account.create()
    challenge = manager.issue_vote_challenge(
        wallet_address=account.address, submission_id="a" * 32,
        content_hash="b" * 64, vote_type="admissible", dimension=ADMISSIBILITY,
    )
    signature = Account.sign_message(encode_defunct(text=challenge["message"]), account.key).signature.hex()
    vote = {
        "submission_id": "a" * 32, "content_hash": "b" * 64,
        "voter": account.address, "voter_wallet_address": account.address,
        "vote_type": "admissible", "dimension": ADMISSIBILITY,
        "vote_version": REVIEW_VOTE_VERSION, "protocol_version": 1,
        "network_id": challenge["network_id"], "created_at": 1.0,
        "signature_scheme": "personal_sign", "vote_signature": signature,
        "vote_message": challenge["message"], "vote_nonce": challenge["nonce"],
        "signed_message_hash": hash_wallet_message(challenge["message"]),
        "vote_issued_at": challenge["issued_at"], "vote_expires_at": challenge["expires_at"],
    }
    assert _normalize_vote_payload(vote, "zoidberg-testnet")["dimension"] == ADMISSIBILITY
    with pytest.raises(MalformedVoteError):
        _normalize_vote_payload(vote | {"dimension": ORIGINALITY}, "zoidberg-testnet")
    with pytest.raises(MalformedVoteError):
        _normalize_vote_payload(vote | {"vote_type": "not_admissible"}, "zoidberg-testnet")
    with pytest.raises(MalformedVoteError):
        _normalize_vote_payload(vote | {"vote_version": 99}, "zoidberg-testnet")


def test_independent_nodes_tally_signed_peer_votes_in_any_arrival_order():
    manager = WalletAuthManager(network_name="zoidberg-testnet", environment="development")
    peer_votes = []
    for index in range(5):
        account = Account.create()
        for dimension, choice in ((ORIGINALITY, "original"), (ADMISSIBILITY, "admissible")):
            challenge = manager.issue_vote_challenge(
                wallet_address=account.address, submission_id="a" * 32,
                content_hash="b" * 64, vote_type=choice, dimension=dimension,
            )
            signature = Account.sign_message(encode_defunct(text=challenge["message"]), account.key).signature.hex()
            vote = {
                "submission_id": "a" * 32, "content_hash": "b" * 64,
                "voter": account.address, "voter_wallet_address": account.address,
                "vote_type": choice, "dimension": dimension,
                "vote_version": REVIEW_VOTE_VERSION, "protocol_version": 1,
                "network_id": challenge["network_id"], "created_at": float(index),
                "signature_scheme": "personal_sign", "vote_signature": signature,
                "vote_message": challenge["message"], "vote_nonce": challenge["nonce"],
                "signed_message_hash": hash_wallet_message(challenge["message"]),
                "vote_issued_at": challenge["issued_at"], "vote_expires_at": challenge["expires_at"],
            }
            normalized = _normalize_vote_payload(vote, "zoidberg-testnet")
            normalized.update(reviewer_eligible=True,
                              reviewer_status=("ESTABLISHED_REVIEWER" if index == 0
                                               else "PROBATIONARY_REVIEWER"))
            peer_votes.append(normalized)
    first_node = combined_review(peer_votes)
    second_node = combined_review(list(reversed(peer_votes)))
    assert first_node == second_node
    assert first_node["review_qualified"] is True


def test_equivocation_is_scoped_to_one_dimension():
    manager = WalletAuthManager(network_name="zoidberg-testnet", environment="development")
    account = Account.create()

    def signed(dimension, choice):
        challenge = manager.issue_vote_challenge(
            wallet_address=account.address, submission_id="a" * 32,
            content_hash="b" * 64, vote_type=choice, dimension=dimension,
        )
        signature = Account.sign_message(encode_defunct(text=challenge["message"]), account.key).signature.hex()
        return {
            "submission_id": "a" * 32, "content_hash": "b" * 64,
            "voter": account.address, "vote_type": choice, "dimension": dimension,
            "vote_version": REVIEW_VOTE_VERSION, "protocol_version": 1,
            "network_id": challenge["network_id"], "vote_nonce": challenge["nonce"],
            "vote_issued_at": challenge["issued_at"], "vote_expires_at": challenge["expires_at"],
            "vote_message": challenge["message"], "vote_signature": signature,
            "signature_scheme": "personal_sign",
        }

    original, not_original = signed(ORIGINALITY, "original"), signed(ORIGINALITY, "not_original")
    admissible = signed(ADMISSIBILITY, "admissible")
    kwargs = dict(offense_type=SIGNED_VOTE_EQUIVOCATION,
                  reference_finalized_height=10, reference_finalized_block_hash="c" * 64,
                  review_epoch=2)
    offense = build_offense_evidence(votes=[original, not_original], **kwargs)
    assert validate_offense_evidence(offense)["offense_id"] == offense["offense_id"]
    cross_dimension = build_offense_evidence(votes=[original, admissible], **kwargs)
    with pytest.raises(ValueError, match="does not prove conflicting"):
        validate_offense_evidence(cross_dimension)
