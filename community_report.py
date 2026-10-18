"""Versioned, signed pre-mint community reports, independent of review votes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from dual_review import REVIEW_POLICY_VERSION
from milestone5_policy import REVIEWER_POLICY_VERSION, REPUTATION_RULE_VERSION
from native_transfer import normalize_wallet_address
from protocol_v1 import PUBLIC_TESTNET_V1_NETWORK_ID, canonical_hash, canonical_json_text
from validators import is_valid_content_hash
from wallet_signatures import recover_signed_wallet_address


REPORT_POLICY_ID = "zoidberg-public-testnet-v1/community-report/1"
REPORT_POLICY_VERSION = 1
REPORT_DOMAIN = "zoidbergchain/community-report/v1"
REPORT_REASONS = (
    "potentially_illegal_content",
    "nonconsensual_or_private_content",
    "exploitation_or_abuse_concern",
    "dangerous_or_harmful_content",
    "impersonation_or_deceptive_manipulation",
    "other_policy_concern",
)
ELIGIBLE_STATUSES = ("PROBATIONARY_REVIEWER", "ESTABLISHED_REVIEWER")


def report_policy() -> dict[str, Any]:
    return {
        "policy_id": REPORT_POLICY_ID,
        "policy_version": REPORT_POLICY_VERSION,
        "network_id": PUBLIC_TESTNET_V1_NETWORK_ID,
        "domain": REPORT_DOMAIN,
        "reasons": list(REPORT_REASONS),
        "minimum_valid_reports": 3,
        "minimum_established_reporters": 1,
        "eligible_statuses": list(ELIGIBLE_STATUSES),
        "reviewer_policy_version": REVIEWER_POLICY_VERSION,
        "reputation_rule_version": REPUTATION_RULE_VERSION,
        "weight": "one_wallet_one_report",
        "duplicate_rule": "one_accepted_per_wallet_submission_policy_version",
        "threshold_action": "pre_mint_quarantine",
        "activation": "task_6_6_admission_activation_boundary",
    }


def report_policy_digest() -> str:
    return canonical_hash(report_policy())


def report_payload(*, wallet_address: str, submission_id: str, content_hash: str,
                   reason: str, nonce: str, issued_at: str, expires_at: str,
                   network_id: str = PUBLIC_TESTNET_V1_NETWORK_ID) -> dict[str, Any]:
    wallet = normalize_wallet_address(wallet_address)
    if wallet is None or not isinstance(submission_id, str) or not submission_id.strip():
        raise ValueError("Invalid report identity.")
    if not is_valid_content_hash(content_hash):
        raise ValueError("Invalid report media hash.")
    if reason not in REPORT_REASONS:
        raise ValueError("Unknown report reason.")
    if network_id != PUBLIC_TESTNET_V1_NETWORK_ID:
        raise ValueError("Report belongs to a different network.")
    if not all(isinstance(value, str) and value.strip() for value in (nonce, issued_at, expires_at)):
        raise ValueError("Report challenge fields are required.")
    try:
        issued = datetime.fromisoformat(issued_at)
        expires = datetime.fromisoformat(expires_at)
        if issued.tzinfo is None or expires.tzinfo is None or expires <= issued:
            raise ValueError
    except ValueError as exc:
        raise ValueError("Invalid report challenge timestamps.") from exc
    return {
        "domain": REPORT_DOMAIN,
        "network_id": network_id,
        "policy_id": REPORT_POLICY_ID,
        "policy_version": REPORT_POLICY_VERSION,
        "policy_digest": report_policy_digest(),
        "reviewer_policy_version": REVIEWER_POLICY_VERSION,
        "reputation_rule_version": REPUTATION_RULE_VERSION,
        "wallet_address": wallet,
        "submission_id": submission_id,
        "content_hash": content_hash,
        "reason": reason,
        "nonce": nonce,
        "issued_at": issued_at,
        "expires_at": expires_at,
    }


def report_message(**kwargs: Any) -> str:
    return canonical_json_text(report_payload(**kwargs))


def report_identity(payload: dict[str, Any], signature: str) -> str:
    normalized = str(signature or "").lower().removeprefix("0x")
    if len(normalized) != 130 or any(c not in "0123456789abcdef" for c in normalized):
        raise ValueError("Report signature must be 65-byte hex.")
    return canonical_hash({"payload": payload, "signature": "0x" + normalized})


def canonical_report_record(record: dict[str, Any]) -> dict[str, Any]:
    """Strip unsigned transport fields and normalize one signed observation."""
    try:
        signature = str(record["signature"]).lower().removeprefix("0x")
        if len(signature) != 130 or any(c not in "0123456789abcdef" for c in signature):
            raise ValueError("Report signature must be 65-byte hex.")
        reference = record["reviewer_reference"]
        return {
            "payload": record["payload"], "message": record["message"],
            "signature": "0x" + signature, "identity": record["identity"],
            "reviewer_reference": {
                "height": reference["height"],
                "block_hash": str(reference["block_hash"]).lower(),
                "status": reference["status"],
            },
        }
    except (KeyError, TypeError) as exc:
        raise ValueError("Incomplete signed report record.") from exc


def verify_report(record: dict[str, Any], *, submission_id: str, content_hash: str,
                  status_resolver) -> bool:
    try:
        payload = record["payload"]
        expected = report_payload(
            wallet_address=payload["wallet_address"], submission_id=submission_id,
            content_hash=content_hash, reason=payload["reason"], nonce=payload["nonce"],
            issued_at=payload["issued_at"], expires_at=payload["expires_at"],
            network_id=payload["network_id"],
        )
        if payload != expected or record.get("message") != canonical_json_text(expected):
            return False
        if record.get("identity") != report_identity(expected, record["signature"]):
            return False
        if recover_signed_wallet_address(record["message"], record["signature"]) != expected["wallet_address"]:
            return False
        reference = record["reviewer_reference"]
        if reference["status"] not in ELIGIBLE_STATUSES:
            return False
        return status_resolver(
            expected["wallet_address"], reference["height"], reference["block_hash"]
        ) == reference["status"]
    except (KeyError, TypeError, ValueError):
        return False


def report_tally(records: list[dict[str, Any]], *, submission_id: str,
                 content_hash: str) -> dict[str, Any]:
    ordered = sorted(records, key=lambda record: (
        record["payload"]["wallet_address"], record["identity"], canonical_hash(record)
    ))
    # The durable list is the observed signed evidence. A wallet contributes
    # exactly one canonical representative, regardless of delivery order.
    representatives = {}
    established_evidence = {}
    seen = set()
    for record in ordered:
        fingerprint = canonical_hash(record)
        if fingerprint in seen:
            raise ValueError("Duplicate signed report observation.")
        seen.add(fingerprint)
        wallet = record["payload"]["wallet_address"]
        representatives.setdefault(wallet, record)
        if record["reviewer_reference"]["status"] == "ESTABLISHED_REVIEWER":
            established_evidence.setdefault(wallet, record)
    counted = sorted(representatives.values(), key=lambda record: record["payload"]["wallet_address"])
    report_set = [{
        "wallet_address": record["payload"]["wallet_address"],
        "reason": record["payload"]["reason"],
        "identity": record["identity"],
        "reviewer_reference": record["reviewer_reference"],
        "established_evidence": ({
            "identity": established_evidence[record["payload"]["wallet_address"]]["identity"],
            "reviewer_reference": established_evidence[record["payload"]["wallet_address"]]["reviewer_reference"],
        } if record["payload"]["wallet_address"] in established_evidence else None),
    } for record in counted]
    established = len(established_evidence)
    reasons = {reason: sum(item["reason"] == reason for item in report_set)
               for reason in REPORT_REASONS}
    met = len(counted) >= 3 and established >= 1
    digest = canonical_hash({
        "policy_digest": report_policy_digest(), "submission_id": submission_id,
        "content_hash": content_hash, "reports": report_set,
    })
    trigger_set = None
    if met:
        trigger_set = report_set[:3]
        if not any(item["established_evidence"] is not None
                   for item in trigger_set):
            trigger_set = sorted(
                report_set[:2] + [next(item for item in report_set[3:]
                                       if item["established_evidence"] is not None)],
                key=lambda item: (item["wallet_address"], item["identity"]),
            )
    trigger_digest = canonical_hash({
        "policy_digest": report_policy_digest(), "submission_id": submission_id,
        "content_hash": content_hash, "reports": trigger_set,
    }) if trigger_set else None
    return {
        "policy_id": REPORT_POLICY_ID, "policy_version": REPORT_POLICY_VERSION,
        "policy_digest": report_policy_digest(), "submission_id": submission_id,
        "content_hash": content_hash, "accepted_report_count": len(counted),
        "observed_report_count": len(ordered),
        "observed_report_digest": canonical_hash([canonical_hash(record) for record in ordered]),
        "established_reporter_count": established,
        "minimum_valid_reports": 3, "minimum_established_reporters": 1,
        "threshold_met": met, "reason_counts": reasons,
        "report_set": report_set, "report_set_digest": digest,
        "canonical_trigger_report_set": trigger_set,
        "canonical_trigger_report_set_digest": trigger_digest,
        "quarantine_trigger_identity": canonical_hash({
            "policy_digest": report_policy_digest(), "submission_id": submission_id,
            "content_hash": content_hash, "report_set_digest": digest,
            "action": "community_report_threshold",
        }) if met else None,
    }
