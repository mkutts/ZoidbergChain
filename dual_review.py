"""Versioned, dimension-bound Public Testnet v1 community review rules.

The admissibility rules and authority still require the policy owner's approval.
This module records community judgment; it does not activate public minting.
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterable

from milestone5_policy import (
    APPROVAL_THRESHOLD_BPS,
    MIN_ESTABLISHED_VOTES,
    MIN_VALID_VOTES,
    REVIEWER_POLICY_VERSION,
    REPUTATION_RULE_VERSION,
)
from native_transfer import normalize_wallet_address
from protocol_v1 import PROTOCOL_VERSION, PUBLIC_TESTNET_V1_NETWORK_ID, canonical_hash, canonical_json_text
from validators import is_valid_content_hash
from wallet_signatures import recover_signed_wallet_address


REVIEW_POLICY_VERSION = 1
REVIEW_VOTE_VERSION = 2
ORIGINALITY = "originality"
ADMISSIBILITY = "admissibility"
DIMENSIONS = (ORIGINALITY, ADMISSIBILITY)
CHOICES = {
    ORIGINALITY: ("original", "not_original", "unsure"),
    ADMISSIBILITY: ("admissible", "not_admissible", "unsure"),
}
POSITIVE = {ORIGINALITY: "original", ADMISSIBILITY: "admissible"}
NEGATIVE = {ORIGINALITY: "not_original", ADMISSIBILITY: "not_admissible"}


def review_policy() -> dict[str, Any]:
    return {
        "network_id": PUBLIC_TESTNET_V1_NETWORK_ID,
        "policy_kind": "dual_community_review",
        "policy_version": REVIEW_POLICY_VERSION,
        "reviewer_policy_version": REVIEWER_POLICY_VERSION,
        "reputation_rule_version": REPUTATION_RULE_VERSION,
        "eligible_reviewer_statuses": ["PROBATIONARY_REVIEWER", "ESTABLISHED_REVIEWER"],
        "review_epoch_source": "finalized_canonical_height",
        "two_dimensions_consume_one_review_participation": True,
        "dimensions": {
            dimension: {
                "choices": list(CHOICES[dimension]),
                "minimum_valid_votes": MIN_VALID_VOTES,
                "minimum_established_votes": MIN_ESTABLISHED_VOTES,
                "approval_threshold_bps": APPROVAL_THRESHOLD_BPS,
                "unsure_counts_toward_quorum": True,
                "unsure_counts_in_approval_denominator": False,
                "unsure_counts_for_reviewer_participation": True,
            }
            for dimension in DIMENSIONS
        },
        "report": "separate_deferred_to_task_6_7",
        "activation": "inactive_owner_decision_required",
    }


def review_policy_digest() -> str:
    return canonical_hash(review_policy())


def validate_choice(dimension: str, choice: str) -> None:
    if dimension not in DIMENSIONS:
        raise ValueError("Unknown review dimension.")
    if choice not in CHOICES[dimension]:
        raise ValueError("Invalid choice for review dimension.")


def vote_payload(*, wallet_address: str, submission_id: str, content_hash: str,
                 dimension: str, choice: str, nonce: str, issued_at: str,
                 expires_at: str, network_id: str) -> dict[str, Any]:
    validate_choice(dimension, choice)
    wallet = normalize_wallet_address(wallet_address)
    if wallet is None or not submission_id or not is_valid_content_hash(content_hash):
        raise ValueError("Invalid review vote identity.")
    if network_id != PUBLIC_TESTNET_V1_NETWORK_ID:
        raise ValueError("Review vote belongs to a different network.")
    if not all(isinstance(item, str) and item.strip() for item in (nonce, issued_at, expires_at)):
        raise ValueError("Review vote nonce and timestamps are required.")
    return {
        "domain": "zoidbergchain/community-review/v2",
        "network_id": network_id,
        "vote_version": REVIEW_VOTE_VERSION,
        "policy_version": REVIEW_POLICY_VERSION,
        "policy_digest": review_policy_digest(),
        "reviewer_policy_version": REVIEWER_POLICY_VERSION,
        "reputation_rule_version": REPUTATION_RULE_VERSION,
        "wallet_address": wallet,
        "submission_id": submission_id,
        "content_hash": content_hash,
        "dimension": dimension,
        "choice": choice,
        "nonce": nonce,
        "issued_at": issued_at,
        "expires_at": expires_at,
    }


def vote_message(**kwargs: Any) -> str:
    return canonical_json_text(vote_payload(**kwargs))


def vote_identity(*, signature: str, **kwargs: Any) -> str:
    if not isinstance(signature, str):
        raise ValueError("Review signature must be 65-byte hex.")
    normalized = signature.lower().removeprefix("0x")
    if len(normalized) != 130 or any(character not in "0123456789abcdef" for character in normalized):
        raise ValueError("Review signature must be 65-byte hex.")
    return canonical_hash({"payload": vote_payload(**kwargs), "signature": "0x" + normalized})


def verify_vote_record(vote: dict[str, Any], *, submission_id: str,
                       content_hash: str, network_id: str, creator_address: str,
                       reviewer_status_resolver) -> bool:
    if vote.get("vote_version") != REVIEW_VOTE_VERSION:
        return False
    if vote.get("reviewer_eligible") is not True:
        return False
    wallet = normalize_wallet_address(vote.get("voter_wallet_address") or vote.get("voter"))
    creator = normalize_wallet_address(creator_address)
    if (wallet is None or creator is None or wallet == creator
        or vote.get("submission_id") != submission_id or vote.get("content_hash") != content_hash):
        return False
    if (vote.get("network_id") != network_id
        or vote.get("protocol_version") != PROTOCOL_VERSION
        or vote.get("signature_scheme") != "personal_sign"
        or vote.get("reviewer_policy_version") != REVIEWER_POLICY_VERSION
        or vote.get("reputation_rule_version") != REPUTATION_RULE_VERSION):
        return False
    if vote.get("reviewer_status") not in {"PROBATIONARY_REVIEWER", "ESTABLISHED_REVIEWER"}:
        return False
    height = vote.get("reviewer_status_effective_height")
    reference_hash = vote.get("reviewer_status_reference_block_hash")
    if (isinstance(height, bool) or not isinstance(height, int) or height < 0
        or not isinstance(reference_hash, str) or len(reference_hash) != 64
        or any(character not in "0123456789abcdef" for character in reference_hash.lower())):
        return False
    try:
        payload = dict(
            wallet_address=wallet, submission_id=submission_id, content_hash=content_hash,
            dimension=vote["dimension"], choice=vote["vote_type"],
            nonce=vote["vote_nonce"], issued_at=vote["vote_issued_at"],
            expires_at=vote["vote_expires_at"], network_id=network_id,
        )
        message = vote_message(**payload)
        signature = vote["vote_signature"]
        if vote.get("vote_message") != message:
            return False
        if vote.get("signed_message_hash") != hashlib.sha256(message.encode("utf-8")).hexdigest():
            return False
        if recover_signed_wallet_address(message, signature) != wallet:
            return False
        if vote.get("vote_identity") != vote_identity(signature=signature, **payload):
            return False
        status = reviewer_status_resolver(
            wallet, height, reference_hash,
        )
        return status == vote["reviewer_status"]
    except (KeyError, TypeError, ValueError):
        return False


def tally(votes: Iterable[dict[str, Any]], dimension: str) -> dict[str, Any]:
    if dimension not in DIMENSIONS:
        raise ValueError("Unknown review dimension.")
    # The signed identity is the stable ordering key; arrival time is advisory.
    selected = [vote for vote in votes if vote.get("dimension") == dimension
                and vote.get("vote_version") == REVIEW_VOTE_VERSION]
    selected.sort(key=lambda vote: (str(vote.get("voter_wallet_address") or vote.get("voter") or "").lower(),
                                    str(vote.get("vote_identity") or "")))
    unique: dict[str, dict[str, Any]] = {}
    for vote in selected:
        choice = vote.get("vote_type")
        validate_choice(dimension, choice)
        wallet = normalize_wallet_address(vote.get("voter_wallet_address") or vote.get("voter"))
        if wallet is None or vote.get("reviewer_eligible") is not True:
            continue
        if wallet in unique:
            if unique[wallet].get("vote_type") != choice:
                raise ValueError("Conflicting review votes in frozen vote set.")
            continue
        unique[wallet] = vote
    ordered = [unique[wallet] for wallet in sorted(unique)]
    positive = sum(vote["vote_type"] == POSITIVE[dimension] for vote in ordered)
    negative = sum(vote["vote_type"] == NEGATIVE[dimension] for vote in ordered)
    unsure = sum(vote["vote_type"] == "unsure" for vote in ordered)
    established = sum(vote.get("reviewer_status") == "ESTABLISHED_REVIEWER" for vote in ordered)
    denominator = positive + negative
    quorum = len(ordered) >= MIN_VALID_VOTES and established >= MIN_ESTABLISHED_VOTES
    approved = quorum and denominator > 0 and positive * 10_000 >= denominator * APPROVAL_THRESHOLD_BPS
    rejected = quorum and denominator > 0 and not approved
    vote_set = [{"wallet": wallet, "choice": unique[wallet]["vote_type"],
                 "identity": unique[wallet].get("vote_identity"),
                 "status": unique[wallet].get("reviewer_status")}
                for wallet in sorted(unique)]
    return {
        "dimension": dimension,
        "policy_version": REVIEW_POLICY_VERSION,
        "policy_digest": review_policy_digest(),
        "eligible_valid_votes": len(ordered),
        "established_reviewer_votes": established,
        "positive_votes": positive,
        "negative_votes": negative,
        "unsure_votes": unsure,
        "approval_denominator": denominator,
        "approval_threshold_bps": APPROVAL_THRESHOLD_BPS,
        "quorum_reached": quorum,
        "resolved": approved or rejected,
        "outcome": POSITIVE[dimension] if approved else NEGATIVE[dimension] if rejected else "unresolved",
        "vote_set_digest": canonical_hash(vote_set),
    }


def combined_review(votes: Iterable[dict[str, Any]]) -> dict[str, Any]:
    records = list(votes)
    originality = tally(records, ORIGINALITY)
    admissibility = tally(records, ADMISSIBILITY)
    complete = originality["resolved"] and admissibility["resolved"]
    qualified = (originality["outcome"] == "original"
                 and admissibility["outcome"] == "admissible")
    return {
        "originality": originality,
        "admissibility": admissibility,
        "review_complete": complete,
        "review_qualified": qualified,
        "review_evidence_digest": canonical_hash({
            "policy_digest": review_policy_digest(),
            "originality": originality,
            "admissibility": admissibility,
        }),
    }
