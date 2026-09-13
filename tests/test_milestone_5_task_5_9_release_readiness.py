"""Integrated Milestone 5 release-readiness and reconstruction scenarios."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from eth_account import Account
from eth_account.messages import encode_defunct
from PIL import Image
import pytest

from blockchain import Blockchain
from milestone5_policy import (
    APPROVAL_THRESHOLD_BPS,
    MIN_ESTABLISHED_VOTES,
    MIN_VALID_VOTES,
    REPUTATION_RULE_VERSION,
    reviewer_policy_digest,
    reputation_rules_digest,
)
from originality_certificate import validate_certificate_for_submission
from originality import (
    FLAGGED_FOR_REVIEW,
    HARD_REJECT,
    ORIGINALITY_RULE_VERSION,
    originality_rule_digest,
)
from protocol_v1 import PUBLIC_TESTNET_V1_NETWORK_ID
from protocol_v1_finality import (
    build_protocol_v1_finality_attestation,
    build_protocol_v1_finality_attestation_message,
)
from protocol_v1_originality import (
    MILESTONE5_CERTIFICATE_V3_VERSION,
    build_protocol_v1_vote_message,
    calculate_signed_vote_identity,
)
from reviewer_reputation import (
    CREATOR_SELF_VOTE,
    RATE_LIMIT_ABUSE,
    SIGNED_VOTE_EQUIVOCATION,
    ReviewerReputationService,
    build_offense_evidence,
)
from services.collusion_analytics_service import CollusionAnalyticsService
from storage import SQLiteStorageBackend, check_storage_integrity
from storage_tools import export_storage, import_storage
from submission import HARD_REJECTED, Submission, VOTE_ORIGINAL
from test_support import fund_native_wallet_with_block
from wallet import Wallet
from wallet_auth import hash_wallet_message


def _sqlite_chain(tmp_path: Path, name: str, *, validators=()) -> Blockchain:
    backend = SQLiteStorageBackend(sqlite_db_path=str(tmp_path / name / "chain.db"))
    return Blockchain(
        Wallet(), Wallet(), Wallet(), storage_backend=backend,
        validator_set=tuple(account.address for account in validators),
    )


def _finality_attestation(account, block) -> dict:
    message = build_protocol_v1_finality_attestation_message(
        validator_address=account.address,
        block_height=block.index,
        block_hash=block.hash,
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
    )
    signature = Account.sign_message(encode_defunct(text=message), account.key).signature.hex()
    return build_protocol_v1_finality_attestation(
        validator_address=account.address,
        block_height=block.index,
        block_hash=block.hash,
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
        signature=signature,
    )


def _finalize(chain: Blockchain, validators, height: int) -> None:
    block = chain.chain[height]
    for validator in validators[:2]:
        chain.submit_validator_finality_attestation(_finality_attestation(validator, block))
    assert chain.is_finalized_canonical_reference(height, block.hash)


def _signed_vote(
    account,
    submission_id: str,
    content_hash: str,
    choice: str,
    number: int,
    *,
    status: str,
    height: int,
    block_hash: str,
    eligible: bool = True,
) -> dict:
    nonce = f"task-5-9-{number}"
    issued_at = f"172476{number:04d}.0"
    expires_at = f"182476{number:04d}.0"
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
        "reputation_rule_version": REPUTATION_RULE_VERSION,
        "reviewer_status": status,
        "reviewer_eligible": eligible,
        "reviewer_status_effective_height": height,
        "reviewer_status_reference_block_hash": block_hash,
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


def _mint_source_image(chain: Blockchain, image_path: Path) -> None:
    submission = chain.submit_content(
        image_path=str(image_path),
        text_content="canonical minted source",
        submitter="0x" + "1" * 40,
    )
    for number in range(5):
        chain.cast_submission_vote(
            submission.submission_id, f"legacy-reviewer-{number}", VOTE_ORIGINAL,
            created_at=1_000 + number,
        )
    chain.evaluate_submission(
        submission.submission_id, automated_originality_passed=True, now=2_000,
    )
    chain.add_to_mint_queue(submission.submission_id)
    assert chain.mint_next_queued_submission(miner="0x" + "2" * 40, validate_meme=False)


def _mint_qualification_submission(chain: Blockchain, creator, number: int) -> None:
    content = chain.upload_text_content(
        text_content=f"qualification content {number} for {creator.address.lower()}",
        submitted_by=creator.address,
    )
    submission = chain.submit_content_operation(
        content_hash=content.content_hash,
        content_id=content.content_id,
        text_content=content.text_content,
        submitter=creator.address,
    )
    for vote_number in range(5):
        chain.cast_submission_vote(
            submission.submission_id,
            f"qualification-reviewer-{number}-{vote_number}",
            VOTE_ORIGINAL,
            created_at=3_000 + number * 10 + vote_number,
        )
    chain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=4_000 + number,
    )
    chain.add_to_mint_queue(submission.submission_id)
    assert chain.mint_next_queued_submission(
        miner="0x" + "2" * 40,
        validate_meme=False,
    )


def _add_submission(chain: Blockchain, submission_id: str, creator: str, number: int) -> Submission:
    submission = Submission(
        image_path="",
        text_content=f"task 5.9 evidence submission {number}",
        submitter=creator,
        submission_id=submission_id,
        content_hash=f"{10_000 + number:064x}",
    )
    chain.submissions.append(submission)
    return submission


def test_integrated_adversarial_lifecycle_two_node_restart_and_reconstruction(tmp_path):
    validators = [Account.create() for _ in range(3)]
    reviewers = [Account.create() for _ in range(5)]
    creator = Account.create()
    source = _sqlite_chain(tmp_path, "source", validators=validators)

    image_path = tmp_path / "source.png"
    Image.new("RGB", (96, 96), "navy").save(image_path)
    _mint_source_image(source, image_path)

    qualification_number = 0
    for reviewer in reviewers:
        for _sequence in range(2):
            _mint_qualification_submission(source, reviewer, qualification_number)
            qualification_number += 1
    while source.get_latest_block().index < 35:
        fund_native_wallet_with_block(source, "0x" + "e" * 40)
    for height in (20, 25, 35):
        _finalize(source, validators, height)

    # One reviewer completes strong probation; the other four remain probationary.
    source._reviewer_eligibility_service.reconcile(
        reviewer_address=reviewers[0].address,
        chain=source.chain,
        finalized_head={"block_height": 20, "block_hash": source.chain[20].hash},
        storage=source.storage,
    )
    for number in range(10):
        height = 20 if number < 5 else 25
        history_vote = {
            "submission_id": f"probation-history-{number}",
            "voter": reviewers[0].address,
            "vote_type": "unsure",
            "reviewer_policy_version": 1,
            "reputation_rule_version": REPUTATION_RULE_VERSION,
            "reviewer_status": "PROBATIONARY_REVIEWER",
            "reviewer_status_effective_height": height,
            "reviewer_status_reference_block_hash": source.chain[height].hash,
            "created_at": f"history-{number}",
        }
        source.storage.record_durable_vote(history_vote)
        source.votes.append(history_vote)
    assert source.get_reviewer_status(reviewers[0].address)["status"] == "ESTABLISHED_REVIEWER"
    assert all(
        source.get_reviewer_status(reviewer.address)["status"] == "PROBATIONARY_REVIEWER"
        for reviewer in reviewers[1:]
    )

    content = source.upload_text_content(
        text_content="A new canonical public-testnet submission for integrated validation.",
        submitted_by=creator.address,
    )
    accepted = source.submit_content_operation(
        content_hash=content.content_hash,
        content_id=content.content_id,
        text_content=content.text_content,
        submitter=creator.address,
    )
    evidence = source.get_originality_evidence(accepted.submission_id)
    assert evidence["originality_rule_version"] == ORIGINALITY_RULE_VERSION

    main_votes = []
    for number, reviewer in enumerate(reviewers):
        vote = _signed_vote(
            reviewer,
            accepted.submission_id,
            accepted.content_hash,
            "original",
            100 + number,
            status=("ESTABLISHED_REVIEWER" if number == 0 else "PROBATIONARY_REVIEWER"),
            height=35,
            block_hash=source.chain[35].hash,
        )
        source.storage.record_durable_vote(vote)
        source.votes.append(vote)
        main_votes.append(vote)

    replay_count = len(source.storage.list_durable_votes(submission_id=accepted.submission_id))
    replay = source.storage.record_durable_vote(main_votes[0])
    assert replay["replay"] is True
    assert len(source.storage.list_durable_votes(submission_id=accepted.submission_id)) == replay_count
    assert source.storage.list_reviewer_offenses(reviewers[0].address) == []

    evaluation, queued, certificate = source.evaluate_submission_operation(accepted.submission_id)
    assert evaluation["reason"] == "approved_by_vote"
    assert queued.status == "queued"
    assert certificate.certificate_version == MILESTONE5_CERTIFICATE_V3_VERSION
    assert (certificate.minimum_valid_votes, certificate.minimum_established_votes) == (
        MIN_VALID_VOTES, MIN_ESTABLISHED_VOTES,
    )
    assert certificate.approval_threshold_bps == APPROVAL_THRESHOLD_BPS
    assert source.validate_originality_certificate(certificate, accepted)

    certificate_snapshot = source.build_reviewer_snapshot(
        [reviewer.address for reviewer in reviewers],
        reference={"block_height": 35, "block_hash": source.chain[35].hash},
    )
    media = source._certificate_media_context(accepted)
    validation_context = {
        "originality_evidence": evidence,
        "chain": source.chain,
        "media_bytes": media["media_bytes"],
        "mime_type": media["mime_type"],
        "reviewer_snapshot": certificate_snapshot,
        "reviewer_status_resolver": source.get_reviewer_status_at_reference,
        "finalized_reference_validator": source.is_finalized_canonical_reference,
    }
    assert validate_certificate_for_submission(
        certificate, accepted, votes=main_votes, **validation_context,
    )
    invalid_vote_sets = [
        main_votes[:-1],
        main_votes + [deepcopy(main_votes[0])],
        [{**main_votes[0], "vote_type": "not_original"}, *main_votes[1:]],
        [{**main_votes[0], "vote_version": None, "vote_signature": None}, *main_votes[1:]],
        [{**main_votes[0], "reviewer_eligible": False}, *main_votes[1:]],
    ]
    for vote_set in invalid_vote_sets:
        with pytest.raises(ValueError):
            validate_certificate_for_submission(
                certificate, accepted, votes=vote_set, **validation_context,
            )

    # Every certificate commitment is independently enforced, not merely hashed
    # into an opaque ID. The focused v3 suite covers missing/extra/altered vote
    # sets and historical eligibility; this integrated matrix covers the bound
    # evidence, policies, constants, references, tallies, and identity.
    for field, value in (
        ("originality_evidence_digest", "f" * 64),
        ("originality_reference_block_hash", source.chain[34].hash),
        ("reviewer_snapshot_digest", "e" * 64),
        ("established_vote_count", 2),
        ("reviewer_policy_version", 999),
        ("reputation_rule_version", 999),
        ("minimum_valid_votes", MIN_VALID_VOTES + 1),
        ("minimum_established_votes", MIN_ESTABLISHED_VOTES + 1),
        ("approval_threshold_bps", APPROVAL_THRESHOLD_BPS - 1),
        ("certificate_reference_block_hash", source.chain[34].hash),
        ("original_votes", certificate.original_votes - 1),
        ("vote_set_hash", "d" * 64),
        ("certificate_id", "c" * 64),
    ):
        tampered = deepcopy(certificate)
        setattr(tampered, field, value)
        with pytest.raises(ValueError):
            source.validate_originality_certificate(tampered, accepted)

    duplicate = source.submit_content_operation(
        image_path=str(image_path),
        text_content="caption changes do not change immutable media bytes",
        submitter=Account.create().address,
    )
    assert duplicate.status == HARD_REJECTED
    assert source.get_originality_evidence(duplicate.submission_id)["final_prevote_decision"] == HARD_REJECT
    with pytest.raises(ValueError, match="cannot receive votes"):
        source.cast_submission_vote(duplicate.submission_id, "reviewer", VOTE_ORIGINAL)
    with pytest.raises(ValueError, match="cannot enter the mint queue"):
        source.add_to_mint_queue(duplicate.submission_id)
    assert source.get_originality_certificate_for_submission(duplicate.submission_id) is None

    derivative_path = tmp_path / "derivative.png"
    with Image.open(image_path) as original:
        original.resize((128, 128), Image.Resampling.LANCZOS).save(derivative_path)
    derivative = source.submit_content_operation(
        image_path=str(derivative_path),
        text_content="review-only fuzzy derivative",
        submitter=Account.create().address,
    )
    assert source.get_originality_evidence(derivative.submission_id)["final_prevote_decision"] == FLAGGED_FOR_REVIEW

    # Advance one finalized epoch before offenses: the already-issued v3 certificate
    # must retain the historical status at height 35.
    while source.get_latest_block().index < 40:
        fund_native_wallet_with_block(source, "0x" + "e" * 40)
    _finalize(source, validators, 40)
    reference_hash = source.chain[40].hash

    self_submission = source.submit_content_operation(
        content_hash=source.upload_text_content(
            text_content="self-vote offense target", submitted_by=reviewers[1].address,
        ).content_hash,
        text_content="self-vote offense target",
        submitter=reviewers[1].address,
    )
    self_vote = _signed_vote(
        reviewers[1], self_submission.submission_id, self_submission.content_hash,
        "original", 200, status="PROBATIONARY_REVIEWER", height=40,
        block_hash=reference_hash,
    )
    self_offense = build_offense_evidence(
        offense_type=CREATOR_SELF_VOTE,
        votes=[self_vote],
        reference_finalized_height=40,
        reference_finalized_block_hash=reference_hash,
        review_epoch=8,
        creator_address=reviewers[1].address,
    )
    assert source.receive_reviewer_offense_evidence(self_offense)["action"] == "created"

    equivocation_submission = _add_submission(source, "integrated-equivocation", creator.address, 1)
    conflicting_votes = [
        _signed_vote(
            reviewers[2], equivocation_submission.submission_id,
            equivocation_submission.content_hash, choice, 210 + number,
            status="PROBATIONARY_REVIEWER", height=40, block_hash=reference_hash,
        )
        for number, choice in enumerate(("original", "not_original"))
    ]
    equivocation = build_offense_evidence(
        offense_type=SIGNED_VOTE_EQUIVOCATION,
        votes=conflicting_votes,
        reference_finalized_height=40,
        reference_finalized_block_hash=reference_hash,
        review_epoch=8,
    )
    assert source.receive_reviewer_offense_evidence(equivocation)["action"] == "created"

    rate_service = ReviewerReputationService(source.storage)
    quota_votes = []
    for number in range(5):
        submission = _add_submission(source, f"integrated-rate-{number}", creator.address, 20 + number)
        vote = _signed_vote(
            reviewers[3], submission.submission_id, submission.content_hash,
            "unsure", 300 + number, status="PROBATIONARY_REVIEWER",
            height=40, block_hash=reference_hash,
        )
        source.storage.record_durable_vote(vote)
        source.votes.append(vote)
        quota_votes.append(vote)
    rate_outcome = None
    for number in range(3):
        submission = _add_submission(source, f"integrated-rate-excess-{number}", creator.address, 30 + number)
        excess = _signed_vote(
            reviewers[3], submission.submission_id, submission.content_hash,
            "unsure", 400 + number, status="PROBATIONARY_REVIEWER",
            height=40, block_hash=reference_hash, eligible=False,
        )
        rate_outcome = rate_service.record_rate_limit_excess(
            excess,
            reference_finalized_height=40,
            reference_finalized_block_hash=reference_hash,
            review_epoch=8,
            state_before="PROBATIONARY_REVIEWER",
        )
    assert rate_outcome is not None and rate_outcome.offense["offense_type"] == RATE_LIMIT_ABUSE
    source._persist_reputation_outcome(rate_outcome)

    analytics_reviewers = [Account.create() for _ in range(3)]
    analytics_creator = Account.create().address
    for reviewer in analytics_reviewers:
        source.storage.initialize_reviewer_state(
            reviewer.address,
            current_status="PROBATIONARY_REVIEWER",
            status_effective_height=35,
            status_reference_block_hash=source.chain[35].hash,
        )
    for number in range(6):
        submission = _add_submission(source, f"integrated-collusion-{number}", analytics_creator, 50 + number)
        for reviewer_number, reviewer in enumerate(analytics_reviewers):
            analytics_vote = {
                "submission_id": submission.submission_id,
                "voter": reviewer.address,
                "vote_type": "original",
                "reviewer_status": "PROBATIONARY_REVIEWER",
                "reviewer_policy_version": 1,
                "reputation_rule_version": REPUTATION_RULE_VERSION,
                "reviewer_status_effective_height": 35 if number < 3 else 40,
                "reviewer_status_reference_block_hash": source.chain[35 if number < 3 else 40].hash,
                "created_at": 2_000 + number * 100 + reviewer_number,
            }
            source.storage.record_durable_vote(analytics_vote)
            source.votes.append(analytics_vote)

    source.save_blockchain()
    consensus_before = {
        "chain": source.chain_to_dicts,
        "votes": deepcopy(source.votes),
        "certificates": [item.to_dict() for item in source.originality_certificates],
        "states": source.storage.list_reviewer_states(),
        "offenses": source.storage.list_reviewer_offenses(),
        "penalties": source.storage.list_reviewer_penalties(),
    }
    analytics = CollusionAnalyticsService().analyze_storage(
        source.storage, chain=source.chain, finalized_head=source.get_finalized_head(),
    )
    assert analytics["non_consensus"] is True and analytics["alert_count"] > 0
    assert consensus_before == {
        "chain": source.chain_to_dicts,
        "votes": deepcopy(source.votes),
        "certificates": [item.to_dict() for item in source.originality_certificates],
        "states": source.storage.list_reviewer_states(),
        "offenses": source.storage.list_reviewer_offenses(),
        "penalties": source.storage.list_reviewer_penalties(),
    }
    assert source.validate_originality_certificate(certificate, accepted)

    restarted = Blockchain(
        storage_backend=source.storage,
        validator_set=tuple(account.address for account in validators),
    )
    assert restarted.get_originality_certificate(certificate.certificate_id).certificate_id == certificate.certificate_id
    assert restarted.get_submission(duplicate.submission_id).status == HARD_REJECTED
    assert restarted.validate_originality_certificate(
        restarted.get_originality_certificate(certificate.certificate_id),
        restarted.get_submission(accepted.submission_id),
    )

    export_path = tmp_path / "milestone-5-export.json"
    export_storage(source.storage, output_path=export_path)
    target_backend = SQLiteStorageBackend(sqlite_db_path=str(tmp_path / "target" / "chain.db"))
    import_storage(target_backend, input_path=export_path)
    target = Blockchain(
        storage_backend=target_backend,
        validator_set=tuple(account.address for account in validators),
    )
    assert check_storage_integrity(target_backend)["healthy"] is True

    target_certificate = target.get_originality_certificate(certificate.certificate_id)
    assert target_certificate.certificate_id == certificate.certificate_id
    assert target.get_originality_evidence(accepted.submission_id)["canonical_evidence_digest"] == evidence["canonical_evidence_digest"]
    reviewer_addresses = [reviewer.address for reviewer in reviewers]
    source_snapshot = source.build_reviewer_snapshot(reviewer_addresses, reference={
        "block_height": 35, "block_hash": source.chain[35].hash,
    })
    target_snapshot = target.build_reviewer_snapshot(reviewer_addresses, reference={
        "block_height": 35, "block_hash": target.chain[35].hash,
    })
    assert source_snapshot["reviewer_snapshot_digest"] == certificate.reviewer_snapshot_digest
    assert target_snapshot == source_snapshot, (source_snapshot, target_snapshot)
    assert target.validate_originality_certificate(
        target_certificate, target.get_submission(accepted.submission_id),
    )
    assert target.get_submission(duplicate.submission_id).status == HARD_REJECTED
    assert target.get_reviewer_status(reviewers[1].address)["status"] == "COOLDOWN"
    assert target.storage.list_reviewer_offenses(reviewers[2].address)[0]["offense_id"] == equivocation["offense_id"]
    target_rate = target.storage.list_reviewer_offenses(
        reviewers[3].address, offense_type=RATE_LIMIT_ABUSE,
    )[0]
    assert target_rate["offense_id"] == rate_outcome.offense["offense_id"]
    assert target.receive_reviewer_offense_evidence(target_rate)["action"] == "duplicate"

    assert originality_rule_digest() == "0be4f10129899a7da07da1fa5d07297b945d71065fc8474bcedb74a55dd497a5"
    assert reviewer_policy_digest() == "ac6140446255e0d2a4f076f0d257a48d6a6a446dde2272a51568e8f020ee90eb"
    assert reputation_rules_digest() == "0605b0cbd81ee7f7dade23651f44d88473d752661470de0035925fdc5a1c7c12"
