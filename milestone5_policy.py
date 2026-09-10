"""Deterministic Milestone 5 reviewer and reputation policy definitions.

These definitions are network data, not operator configuration.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from native_transfer import normalize_wallet_address
from protocol_v1 import PUBLIC_TESTNET_V1_NETWORK_ID, canonical_hash, canonical_json_text


REVIEWER_POLICY_VERSION = 1
REPUTATION_RULE_VERSION = 1

REVIEW_EPOCH_BLOCKS = 5
MIN_WALLET_AGE_EPOCHS = 3
CREATOR_PATH_MIN_FINALIZED_MINTED_SUBMISSIONS = 2
ZOID_PATH_MIN_FINALIZED_NATIVE_TRANSACTIONS = 5
ZOID_PATH_MIN_ACTIVITY_SPAN_EPOCHS = 3
MIXED_PATH_MIN_FINALIZED_MINTED_SUBMISSIONS = 1
MIXED_PATH_MIN_FINALIZED_NATIVE_TRANSACTIONS = 2
PROBATION_MIN_DURATION_EPOCHS = 3
PROBATION_MAX_VOTES_PER_EPOCH = 5
PROBATION_MIN_VALID_VOTES_FOR_PROMOTION = 10
ESTABLISHED_MAX_VOTES_PER_EPOCH = 25

# Certificate-v3 consensus constants are deliberately separate from Reviewer
# Policy v1.  Reviewer Policy v1 was already activated by Task 5.5 and its
# canonical digest must not be reinterpreted by a later certificate version.
MIN_VALID_VOTES = 5
MIN_ESTABLISHED_VOTES = 1
APPROVAL_THRESHOLD_BPS = 7000


def certificate_v3_approval_passes(original_votes: int, not_original_votes: int) -> bool:
    for label, value in (("original_votes", original_votes), ("not_original_votes", not_original_votes)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{label} must be a non-negative integer.")
    decisive = original_votes + not_original_votes
    return decisive > 0 and original_votes * 10_000 >= decisive * APPROVAL_THRESHOLD_BPS


def certificate_v3_quorum_satisfied(
    *, total_valid_votes: int, established_vote_count: int,
    original_votes: int, not_original_votes: int,
) -> bool:
    for label, value in (("total_valid_votes", total_valid_votes), ("established_vote_count", established_vote_count)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{label} must be a non-negative integer.")
    return (
        total_valid_votes >= MIN_VALID_VOTES
        and established_vote_count >= MIN_ESTABLISHED_VOTES
        and certificate_v3_approval_passes(original_votes, not_original_votes)
    )

REVIEWER_STATUSES = (
    "NEW",
    "PROBATIONARY_REVIEWER",
    "ESTABLISHED_REVIEWER",
    "COOLDOWN",
    "SUSPENDED",
)

# Public Testnet v1 has no locked bootstrap wallet grants yet.  Keeping the set
# literal (including when empty) means adding or removing a grant requires a
# reviewed policy-version change rather than a node-local environment edit.
PUBLIC_TESTNET_V1_BOOTSTRAP_ESTABLISHED_REVIEWERS: tuple[str, ...] = ()

_REVIEWER_POLICIES: dict[int, dict[str, Any]] = {
    REVIEWER_POLICY_VERSION: {
        "network_id": PUBLIC_TESTNET_V1_NETWORK_ID,
        "policy_kind": "reviewer",
        "reviewer_policy_version": REVIEWER_POLICY_VERSION,
        "statuses": list(REVIEWER_STATUSES),
        "vote_weight": 1,
        "bootstrap_established_reviewers": list(PUBLIC_TESTNET_V1_BOOTSTRAP_ESTABLISHED_REVIEWERS),
        "review_epoch_blocks": REVIEW_EPOCH_BLOCKS,
        "minimum_wallet_age_epochs": MIN_WALLET_AGE_EPOCHS,
        "earned_admission": {
            "enabled": True,
            "canonical_path_order": ["creator", "zoid_activity", "mixed"],
            "creator_path_min_finalized_minted_submissions": CREATOR_PATH_MIN_FINALIZED_MINTED_SUBMISSIONS,
            "zoid_path_min_finalized_native_transactions": ZOID_PATH_MIN_FINALIZED_NATIVE_TRANSACTIONS,
            "zoid_path_min_activity_span_epochs": ZOID_PATH_MIN_ACTIVITY_SPAN_EPOCHS,
            "mixed_path_min_finalized_minted_submissions": MIXED_PATH_MIN_FINALIZED_MINTED_SUBMISSIONS,
            "mixed_path_min_finalized_native_transactions": MIXED_PATH_MIN_FINALIZED_NATIVE_TRANSACTIONS,
        },
        "probation": {
            "minimum_duration_epochs": PROBATION_MIN_DURATION_EPOCHS,
            "maximum_valid_votes_per_epoch": PROBATION_MAX_VOTES_PER_EPOCH,
            "minimum_valid_votes_for_promotion": PROBATION_MIN_VALID_VOTES_FOR_PROMOTION,
        },
        "established_reviewer": {
            "maximum_valid_votes_per_epoch": ESTABLISHED_MAX_VOTES_PER_EPOCH,
        },
        "quorum": {
            "activation": "reserved_for_later_milestone_5_task",
            "fixed_minimum_valid_votes": None,
            "fixed_minimum_established_reviewer_votes": None,
            "integer_approval_numerator": None,
            "integer_approval_denominator": None,
        },
    }
}

_REPUTATION_RULES: dict[int, dict[str, Any]] = {
    REPUTATION_RULE_VERSION: {
        "network_id": PUBLIC_TESTNET_V1_NETWORK_ID,
        "policy_kind": "reputation",
        "reputation_rule_version": REPUTATION_RULE_VERSION,
        "automatic_penalties": {
            "enabled": False,
            "objective_protocol_violations_only": True,
            "rules": [],
            "reserved_for_task": "5.6",
        },
        "collusion_analytics": "alert_only",
    }
}


def _policy_by_version(definitions: dict[int, dict[str, Any]], version: int, label: str) -> dict[str, Any]:
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError(f"{label} version must be an integer.")
    try:
        return deepcopy(definitions[version])
    except KeyError as exc:
        raise ValueError(f"Unsupported {label} version: {version}") from exc


def reviewer_policy(version: int = REVIEWER_POLICY_VERSION) -> dict[str, Any]:
    return _policy_by_version(_REVIEWER_POLICIES, version, "reviewer policy")


def reputation_rules(version: int = REPUTATION_RULE_VERSION) -> dict[str, Any]:
    return _policy_by_version(_REPUTATION_RULES, version, "reputation rule")


def reviewer_policy_canonical_text(version: int = REVIEWER_POLICY_VERSION) -> str:
    return canonical_json_text(reviewer_policy(version))


def reputation_rules_canonical_text(version: int = REPUTATION_RULE_VERSION) -> str:
    return canonical_json_text(reputation_rules(version))


def reviewer_policy_digest(version: int = REVIEWER_POLICY_VERSION) -> str:
    return canonical_hash(reviewer_policy(version))


def reputation_rules_digest(version: int = REPUTATION_RULE_VERSION) -> str:
    return canonical_hash(reputation_rules(version))


def bootstrap_established_reviewers(version: int = REVIEWER_POLICY_VERSION) -> tuple[str, ...]:
    values = reviewer_policy(version)["bootstrap_established_reviewers"]
    normalized = []
    for value in values:
        wallet = normalize_wallet_address(value)
        if wallet is None:
            raise ValueError(f"Reviewer policy {version} contains an invalid bootstrap wallet.")
        normalized.append(wallet)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"Reviewer policy {version} contains duplicate bootstrap wallets.")
    return tuple(sorted(normalized))


def validate_reviewer_status(status: str) -> str:
    normalized = str(status or "").strip().upper()
    if normalized not in REVIEWER_STATUSES:
        raise ValueError(f"Unsupported reviewer status: {status!r}")
    return normalized


def review_epoch(finalized_height: int, version: int = REVIEWER_POLICY_VERSION) -> int:
    """Return the zero-based epoch: finalized canonical height // 5."""
    policy = reviewer_policy(version)
    if isinstance(finalized_height, bool) or not isinstance(finalized_height, int) or finalized_height < 0:
        raise ValueError("finalized_height must be a non-negative integer.")
    return finalized_height // int(policy["review_epoch_blocks"])
