"""Deterministic Milestone 5 reviewer and reputation policy definitions.

These definitions are network data, not operator configuration.  Task 5.2
intentionally reserves thresholds and transition rules for later tasks while
freezing the fields that have already been decided.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from native_transfer import normalize_wallet_address
from protocol_v1 import PUBLIC_TESTNET_V1_NETWORK_ID, canonical_hash, canonical_json_text


REVIEWER_POLICY_VERSION = 1
REPUTATION_RULE_VERSION = 1

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
        "earned_admission": {
            "enabled": False,
            "paths": [],
            "reserved_for_task": "5.5",
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
