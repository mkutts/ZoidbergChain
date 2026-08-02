from __future__ import annotations

import os
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from wallet_auth import normalize_wallet_address


REVIEW_MODE_OPEN = "open"
REVIEW_MODE_ALLOWLIST = "allowlist"
REVIEW_MODE_ACTIVITY = "activity"
REVIEW_MODE_HYBRID = "hybrid"
VALID_REVIEW_MODES = {
    REVIEW_MODE_OPEN,
    REVIEW_MODE_ALLOWLIST,
    REVIEW_MODE_ACTIVITY,
    REVIEW_MODE_HYBRID,
}


@dataclass(frozen=True)
class ReviewPolicyConfig:
    environment: str
    eligibility_mode: str
    public_label: str
    allowlist_wallets: frozenset[str]
    denylist_wallets: frozenset[str]
    min_reviewer_account_age_seconds: int
    min_reviewer_submission_count: int
    min_reviewer_vote_count: int
    min_reviewer_reward_count: int
    min_reviewer_settled_balance_zoid: str
    min_reviewer_settled_transfer_count: int
    max_review_votes_per_wallet_per_day: int
    warnings: tuple[str, ...]

    @property
    def allowlist_enabled(self) -> bool:
        return self.eligibility_mode in {REVIEW_MODE_ALLOWLIST, REVIEW_MODE_HYBRID}

    @property
    def denylist_enabled(self) -> bool:
        return bool(self.denylist_wallets)

    @property
    def activity_enabled(self) -> bool:
        return self.eligibility_mode in {REVIEW_MODE_ACTIVITY, REVIEW_MODE_HYBRID}


@dataclass(frozen=True)
class ReviewEligibilityDecision:
    eligible: bool
    reason: str
    recommended_action: str
    matched_threshold: str | None = None


def _safe_int_env(name: str, default: int, warnings: list[str], *, minimum: int = 0) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        parsed = int(str(raw_value).strip())
    except (TypeError, ValueError):
        warnings.append(f"{name} was invalid and fell back to {default}.")
        return default
    if parsed < minimum:
        warnings.append(f"{name} was below {minimum} and fell back to {default}.")
        return default
    return parsed


def _safe_mode(environment: str, warnings: list[str]) -> str:
    default_mode = REVIEW_MODE_OPEN if environment == "development" else REVIEW_MODE_ALLOWLIST
    raw_mode = str(os.getenv("REVIEW_ELIGIBILITY_MODE", default_mode) or "").strip().lower()
    if raw_mode in VALID_REVIEW_MODES:
        return raw_mode
    warnings.append(
        f"REVIEW_ELIGIBILITY_MODE was invalid and fell back to {default_mode}."
    )
    return default_mode


def _safe_wallet_list(name: str, warnings: list[str]) -> frozenset[str]:
    raw_value = os.getenv(name)
    if not raw_value:
        return frozenset()

    normalized_wallets: list[str] = []
    invalid_wallets = 0
    for candidate in str(raw_value).split(","):
        normalized = normalize_wallet_address(str(candidate).strip())
        if normalized:
            normalized_wallets.append(normalized)
        elif str(candidate).strip():
            invalid_wallets += 1

    if invalid_wallets:
        warnings.append(
            f"{name} ignored {invalid_wallets} malformed wallet entr"
            f"{'y' if invalid_wallets == 1 else 'ies'}."
        )
    return frozenset(dict.fromkeys(normalized_wallets))


def load_review_policy_config(environment: str) -> ReviewPolicyConfig:
    warnings: list[str] = []
    public_label_default = (
        "Open local review voting"
        if environment == "development"
        else "Controlled testnet reviewer eligibility"
    )
    raw_balance_threshold = str(os.getenv("MIN_REVIEWER_SETTLED_BALANCE_ZOID", "0") or "0").strip() or "0"
    try:
        if Decimal(raw_balance_threshold) < Decimal("0"):
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        warnings.append("MIN_REVIEWER_SETTLED_BALANCE_ZOID was invalid and fell back to 0.")
        raw_balance_threshold = "0"
    return ReviewPolicyConfig(
        environment=environment,
        eligibility_mode=_safe_mode(environment, warnings),
        public_label=str(
            os.getenv("REVIEW_POLICY_PUBLIC_LABEL", public_label_default) or public_label_default
        ).strip()
        or public_label_default,
        allowlist_wallets=_safe_wallet_list("REVIEW_ALLOWLIST_WALLETS", warnings),
        denylist_wallets=_safe_wallet_list("REVIEW_DENYLIST_WALLETS", warnings),
        min_reviewer_account_age_seconds=_safe_int_env(
            "MIN_REVIEWER_ACCOUNT_AGE_SECONDS",
            0,
            warnings,
            minimum=0,
        ),
        min_reviewer_submission_count=_safe_int_env(
            "MIN_REVIEWER_SUBMISSION_COUNT",
            0,
            warnings,
            minimum=0,
        ),
        min_reviewer_vote_count=_safe_int_env(
            "MIN_REVIEWER_VOTE_COUNT",
            0,
            warnings,
            minimum=0,
        ),
        min_reviewer_reward_count=_safe_int_env(
            "MIN_REVIEWER_REWARD_COUNT",
            0,
            warnings,
            minimum=0,
        ),
        min_reviewer_settled_balance_zoid=raw_balance_threshold,
        min_reviewer_settled_transfer_count=_safe_int_env(
            "MIN_REVIEWER_SETTLED_TRANSFER_COUNT",
            0,
            warnings,
            minimum=0,
        ),
        max_review_votes_per_wallet_per_day=_safe_int_env(
            "MAX_REVIEW_VOTES_PER_WALLET_PER_DAY",
            0,
            warnings,
            minimum=0,
        ),
        warnings=tuple(warnings),
    )


def _activity_thresholds(config: ReviewPolicyConfig) -> tuple[tuple[str, int | str], ...]:
    return (
        ("account_age_seconds", config.min_reviewer_account_age_seconds),
        ("submission_count", config.min_reviewer_submission_count),
        ("vote_count", config.min_reviewer_vote_count),
        ("reward_count", config.min_reviewer_reward_count),
        ("settled_balance_zoid", config.min_reviewer_settled_balance_zoid),
        ("settled_transfer_count", config.min_reviewer_settled_transfer_count),
    )


def activity_thresholds_enabled(config: ReviewPolicyConfig) -> bool:
    for _, value in _activity_thresholds(config):
        if isinstance(value, str):
            if value not in {"", "0", "0.0"}:
                return True
            continue
        if value > 0:
            return True
    return False


def evaluate_activity_eligibility(
    config: ReviewPolicyConfig,
    *,
    activity_summary: dict[str, Any] | None,
) -> ReviewEligibilityDecision:
    summary = activity_summary or {}
    if not activity_thresholds_enabled(config):
        return ReviewEligibilityDecision(
            eligible=False,
            reason="activity_thresholds_not_configured",
            recommended_action="Ask the operator to configure reviewer activity thresholds or use an allowlisted wallet.",
        )

    checks: tuple[tuple[str, int | str, Any], ...] = (
        (
            "account_age_seconds",
            config.min_reviewer_account_age_seconds,
            int(summary.get("account_age_seconds") or 0),
        ),
        (
            "submission_count",
            config.min_reviewer_submission_count,
            int(summary.get("submission_count") or 0),
        ),
        (
            "vote_count",
            config.min_reviewer_vote_count,
            int(summary.get("vote_count") or 0),
        ),
        (
            "reward_count",
            config.min_reviewer_reward_count,
            int(summary.get("reward_count") or 0),
        ),
        (
            "settled_balance_zoid",
            config.min_reviewer_settled_balance_zoid,
            str(summary.get("settled_balance_zoid") or "0"),
        ),
        (
            "settled_transfer_count",
            config.min_reviewer_settled_transfer_count,
            int(summary.get("settled_transfer_count") or 0),
        ),
    )

    for metric_name, threshold, actual_value in checks:
        if isinstance(threshold, str):
            if threshold not in {"", "0", "0.0"} and Decimal(str(actual_value)) >= Decimal(threshold):
                return ReviewEligibilityDecision(
                    eligible=True,
                    reason="activity_threshold_met",
                    matched_threshold=metric_name,
                    recommended_action="This wallet already meets the current reviewer activity policy.",
                )
            continue
        if threshold > 0 and int(actual_value) >= threshold:
            return ReviewEligibilityDecision(
                eligible=True,
                reason="activity_threshold_met",
                matched_threshold=metric_name,
                recommended_action="This wallet already meets the current reviewer activity policy.",
            )

    return ReviewEligibilityDecision(
        eligible=False,
        reason="insufficient_reviewer_activity",
        recommended_action="Use a more established testnet wallet or ask the operator to allowlist this wallet.",
    )


def current_day_window(*, now: float | None = None) -> float:
    current_time = float(now if now is not None else time.time())
    return current_time - 86400


def evaluate_review_eligibility(
    config: ReviewPolicyConfig,
    *,
    wallet_address: str,
    activity_summary: dict[str, Any] | None,
    recent_vote_count: int,
) -> ReviewEligibilityDecision:
    normalized_wallet = normalize_wallet_address(wallet_address)
    if normalized_wallet is None:
        return ReviewEligibilityDecision(
            eligible=False,
            reason="invalid_wallet_address",
            recommended_action="Reconnect MetaMask and try again with a valid wallet address.",
        )

    if normalized_wallet in config.denylist_wallets:
        return ReviewEligibilityDecision(
            eligible=False,
            reason="wallet_denylisted",
            recommended_action="Use a different approved testnet wallet or ask the operator for help.",
        )

    if (
        config.max_review_votes_per_wallet_per_day > 0
        and recent_vote_count >= config.max_review_votes_per_wallet_per_day
    ):
        return ReviewEligibilityDecision(
            eligible=False,
            reason="daily_vote_limit_reached",
            recommended_action="Wait for the daily review window to reset or ask the operator to raise the limit.",
        )

    wallet_allowlisted = normalized_wallet in config.allowlist_wallets
    if config.eligibility_mode == REVIEW_MODE_OPEN:
        return ReviewEligibilityDecision(
            eligible=True,
            reason="open_mode",
            recommended_action="This wallet can review as long as the normal vote rules pass.",
        )
    if config.eligibility_mode == REVIEW_MODE_ALLOWLIST:
        if wallet_allowlisted:
            return ReviewEligibilityDecision(
                eligible=True,
                reason="wallet_allowlisted",
                recommended_action="This wallet is allowlisted for controlled testnet reviews.",
            )
        return ReviewEligibilityDecision(
            eligible=False,
            reason="wallet_not_allowlisted",
            recommended_action="Use an approved testnet wallet or ask the operator for access.",
        )

    activity_decision = evaluate_activity_eligibility(
        config,
        activity_summary=activity_summary,
    )
    if config.eligibility_mode == REVIEW_MODE_ACTIVITY:
        return activity_decision
    if wallet_allowlisted:
        return ReviewEligibilityDecision(
            eligible=True,
            reason="wallet_allowlisted",
            recommended_action="This wallet is allowlisted for controlled testnet reviews.",
        )
    return activity_decision


def build_public_policy_summary(
    config: ReviewPolicyConfig,
    *,
    wallet_address: str | None = None,
    eligibility: ReviewEligibilityDecision | None = None,
) -> dict[str, Any]:
    payload = {
        "environment": config.environment,
        "eligibility_mode": config.eligibility_mode,
        "public_label": config.public_label,
        "allowlist_mode_enabled": config.allowlist_enabled,
        "denylist_configured": config.denylist_enabled,
        "thresholds": {
            "min_reviewer_account_age_seconds": config.min_reviewer_account_age_seconds,
            "min_reviewer_submission_count": config.min_reviewer_submission_count,
            "min_reviewer_vote_count": config.min_reviewer_vote_count,
            "min_reviewer_reward_count": config.min_reviewer_reward_count,
            "min_reviewer_settled_balance_zoid": config.min_reviewer_settled_balance_zoid,
            "min_reviewer_settled_transfer_count": config.min_reviewer_settled_transfer_count,
            "max_review_votes_per_wallet_per_day": config.max_review_votes_per_wallet_per_day,
        },
        "warnings": list(config.warnings),
        "notes": [
            "This is anti-Sybil friction for a controlled public testnet, not proof-of-personhood.",
            "Without KYC, proof-of-personhood, staking, or real economic cost, multiple-wallet abuse is only reduced, not solved.",
        ],
    }
    if wallet_address:
        payload["wallet_address"] = wallet_address
    if eligibility is not None:
        payload["eligibility"] = {
            "eligible": eligibility.eligible,
            "reason": eligibility.reason,
            "recommended_action": eligibility.recommended_action,
            "matched_threshold": eligibility.matched_threshold,
        }
    return payload
