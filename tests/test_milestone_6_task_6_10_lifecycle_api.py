"""Milestone 6 Task 6.10 derived lifecycle/API integration coverage."""

from __future__ import annotations

from copy import deepcopy

from submission import ATTESTATION_LEGACY, Submission
from tests.api.test_wallet_auth_api import _client
from tests.test_milestone_6_task_6_6_admission import _current_submission, _signed_votes
from tests.test_milestone_6_task_6_8_post_mint_dispute import _minted_node


def _lifecycle(client, submission_id, *, verify_integrity=True):
    response = client.get(
        f"/submissions/{submission_id}/lifecycle",
        params={"verify_integrity": str(verify_integrity).lower()},
    )
    assert response.status_code == 200, response.text
    return response.json()["lifecycle"]


def test_current_pending_lifecycle_is_structured_public_and_read_only(blockchain):
    submission, content, evidence = _current_submission(blockchain)
    before = deepcopy(submission.to_dict())
    client, _ = _client(blockchain)

    lifecycle = _lifecycle(client, submission.submission_id)

    assert lifecycle["stage"] == "awaiting_review"
    assert lifecycle["technical_validation"] == {
        "status": "accepted",
        "outcome": "ACCEPT",
        "reason_codes": evidence["reason_codes"],
        "evidence_version": evidence["evidence_version"],
        "evidence_digest": evidence["evidence_digest"],
        "media_hash": content.content_hash,
        "byte_length": len(content.text_content.encode("utf-8")),
        "detected_mime_type": "text/plain",
    }
    assert lifecycle["attestation"]["status"] == "valid"
    assert lifecycle["review"]["originality"]["outcome"] == "unresolved"
    assert lifecycle["review"]["admissibility"]["outcome"] == "unresolved"
    assert lifecycle["reporting"]["status"] == "below_threshold"
    assert lifecycle["quarantine"]["quarantined"] is False
    assert lifecycle["media_integrity"]["status"] == "unavailable"
    assert set(lifecycle["activation"]) >= {
        "state", "activation_height", "first_enforced_height",
        "last_legacy_height", "canonical_tip_height",
    }
    assert submission.to_dict() == before

    listing = client.get("/submissions")
    assert listing.status_code == 200
    embedded = listing.json()["submissions"][0]["lifecycle"]
    assert embedded["schema_version"] == 1
    assert "image_path" not in str(embedded)
    assert "local_path" not in str(embedded)


def test_admission_qualified_summary_freezes_distinct_review_results(blockchain):
    submission, _content, _evidence = _current_submission(blockchain)
    votes, statuses = _signed_votes(blockchain, submission)
    blockchain.get_reviewer_status_at_reference = lambda wallet, height, block_hash: statuses[wallet]
    blockchain.votes.extend(votes)
    blockchain.evaluate_submission_operation(submission.submission_id)
    client, _ = _client(blockchain)

    lifecycle = _lifecycle(client, submission.submission_id, verify_integrity=False)

    assert lifecycle["stage"] == "mintable"
    assert lifecycle["review"]["originality"]["outcome"] == "original"
    assert lifecycle["review"]["admissibility"]["outcome"] == "admissible"
    assert lifecycle["admission"]["qualified"] is True
    certificate = lifecycle["admission"]["certificate"]
    assert certificate["scope"] == "current_dual_admission"
    assert certificate["certificate_version"] == 1
    assert certificate["certificate_digest"] == submission.admission_certificate["certificate_digest"]
    assert certificate["technical_evidence_binding"]["digest"]
    assert certificate["attestation_binding"]["message_hash"]


def test_quarantine_reason_and_legacy_scope_are_not_collapsed(blockchain):
    submission, _content, _evidence = _current_submission(blockchain)
    votes, statuses = _signed_votes(blockchain, submission, originality="not_original")
    blockchain.get_reviewer_status_at_reference = lambda wallet, height, block_hash: statuses[wallet]
    blockchain.votes.extend(votes)
    blockchain.evaluate_submission_operation(submission.submission_id)
    client, _ = _client(blockchain)

    lifecycle = _lifecycle(client, submission.submission_id, verify_integrity=False)
    assert lifecycle["stage"] == "quarantined"
    assert lifecycle["quarantine"] == {
        "quarantined": True,
        "reason": "review_rejected_originality",
        "category": "originality_rejection",
        "deletion": False,
        "can_mint_current_round": False,
    }

    legacy = Submission(
        image_path="", text_content="legacy", submitter="legacy",
        attestation_requirement=ATTESTATION_LEGACY,
    )
    blockchain.submissions.append(legacy)
    legacy_view = _lifecycle(client, legacy.submission_id, verify_integrity=False)
    assert legacy_view["stage"] == "legacy_pre_activation"
    assert legacy_view["attestation"]["status"] == "legacy_pre_activation"
    assert legacy_view["review"]["admissibility"] is None
    assert legacy_view["legacy"]["certificate_scope"] == "legacy_originality_only"
    assert legacy_view["legacy"]["missing_fields_are_not_inferred"] is True


def test_finalized_lifecycle_integrity_and_dispute_overlay_are_separate(
    isolated_data_dir, monkeypatch
):
    node, block, _ = _minted_node(isolated_data_dir, "json", monkeypatch)
    client, _ = _client(node)

    lifecycle = _lifecycle(client, block.submission_id)

    assert lifecycle["stage"] == "finalized"
    assert lifecycle["finality"]["finalized"] is True
    assert lifecycle["media_integrity"]["status"] == "verified"
    assert lifecycle["media_integrity"]["sha256"] == block.media_hash
    assert lifecycle["media_integrity"]["byte_length"] == len(block.media_bytes)
    assert lifecycle["post_mint_dispute"]["status"] == "finalized"
    assert lifecycle["post_mint_dispute"]["block_remains_finalized"] is True

    chain = client.get("/chain").json()["chain"]
    summary = next(item for item in chain if item["hash"] == block.hash)
    assert summary["certificate_scope"] == "current_dual_admission"
    assert summary["media_integrity"]["verification"] == "verified_on_exact_download"
    assert summary["post_mint_dispute"]["post_mint_status"] == "finalized"

