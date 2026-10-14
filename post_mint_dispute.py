"""Signed, additive evidence about finalized Public Testnet v1 media."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from community_report import ELIGIBLE_STATUSES
from milestone5_policy import REVIEWER_POLICY_VERSION, REPUTATION_RULE_VERSION
from native_transfer import normalize_wallet_address
from protocol_v1 import PUBLIC_TESTNET_V1_NETWORK_ID, canonical_hash, canonical_json_text
from validators import is_valid_content_hash
from wallet_signatures import recover_signed_wallet_address

DISPUTE_POLICY_ID = "zoidberg-public-testnet-v1/post-mint-dispute/1"
DISPUTE_POLICY_VERSION = 1
DISPUTE_DOMAIN = "zoidbergchain/post-mint-dispute/v1"
DISPUTE_REASONS = (
    "potentially_illegal_content",
    "nonconsensual_or_private_content",
    "exploitation_or_abuse_concern",
    "dangerous_or_harmful_content",
    "impersonation_or_deceptive_manipulation",
    "post_mint_provenance_or_originality_challenge",
    "other_policy_concern",
)


def dispute_policy() -> dict[str, Any]:
    return {
        "policy_id": DISPUTE_POLICY_ID,
        "policy_version": DISPUTE_POLICY_VERSION,
        "network_id": PUBLIC_TESTNET_V1_NETWORK_ID,
        "domain": DISPUTE_DOMAIN,
        "reasons": list(DISPUTE_REASONS),
        "minimum_valid_disputes": 3,
        "minimum_established_disputers": 1,
        "eligible_statuses": list(ELIGIBLE_STATUSES),
        "reviewer_policy_version": REVIEWER_POLICY_VERSION,
        "reputation_rule_version": REPUTATION_RULE_VERSION,
        "weight": "one_wallet_one_dispute",
        "duplicate_rule": "one_counted_per_wallet_finalized_media_policy_version",
        "conflict_rule": "lowest_signed_identity_then_record_digest",
        "threshold_action": "additive_post_mint_disputed_status_only",
    }


def dispute_policy_digest() -> str:
    return canonical_hash(dispute_policy())


def dispute_payload(*, wallet_address: str, submission_id: str, block_height: int,
                    block_hash: str, media_hash: str, reason: str, nonce: str,
                    issued_at: str, expires_at: str,
                    network_id: str = PUBLIC_TESTNET_V1_NETWORK_ID) -> dict[str, Any]:
    wallet = normalize_wallet_address(wallet_address)
    if wallet is None or not isinstance(submission_id, str) or not submission_id.strip():
        raise ValueError("Invalid dispute identity.")
    if isinstance(block_height, bool) or not isinstance(block_height, int) or block_height < 1:
        raise ValueError("Invalid finalized block height.")
    if not is_valid_content_hash(block_hash) or not is_valid_content_hash(media_hash):
        raise ValueError("Invalid finalized block or media hash.")
    if reason not in DISPUTE_REASONS:
        raise ValueError("Unknown dispute reason.")
    if network_id != PUBLIC_TESTNET_V1_NETWORK_ID:
        raise ValueError("Dispute belongs to a different network.")
    if not all(isinstance(value, str) and value.strip() for value in (nonce, issued_at, expires_at)):
        raise ValueError("Dispute challenge fields are required.")
    try:
        issued, expires = datetime.fromisoformat(issued_at), datetime.fromisoformat(expires_at)
        if issued.tzinfo is None or expires.tzinfo is None or expires <= issued:
            raise ValueError
    except ValueError as exc:
        raise ValueError("Invalid dispute challenge timestamps.") from exc
    return {
        "domain": DISPUTE_DOMAIN, "network_id": network_id,
        "policy_id": DISPUTE_POLICY_ID, "policy_version": DISPUTE_POLICY_VERSION,
        "policy_digest": dispute_policy_digest(),
        "reviewer_policy_version": REVIEWER_POLICY_VERSION,
        "reputation_rule_version": REPUTATION_RULE_VERSION,
        "wallet_address": wallet, "submission_id": submission_id,
        "block_height": block_height, "block_hash": block_hash.lower(),
        "media_hash": media_hash.lower(), "reason": reason, "nonce": nonce,
        "issued_at": issued_at, "expires_at": expires_at,
    }


def dispute_identity(payload: dict[str, Any], signature: str) -> str:
    normalized = str(signature or "").lower().removeprefix("0x")
    if len(normalized) != 130 or any(c not in "0123456789abcdef" for c in normalized):
        raise ValueError("Dispute signature must be 65-byte hex.")
    return canonical_hash({"payload": payload, "signature": "0x" + normalized})


def canonical_dispute_record(record: dict[str, Any]) -> dict[str, Any]:
    try:
        reference = record["reviewer_reference"]
        signature = str(record["signature"]).lower().removeprefix("0x")
        if len(signature) != 130 or any(c not in "0123456789abcdef" for c in signature):
            raise ValueError("Dispute signature must be 65-byte hex.")
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
        raise ValueError("Incomplete signed dispute record.") from exc


def verify_dispute(record: dict[str, Any], *, submission_id: str, block_height: int,
                   block_hash: str, media_hash: str, status_resolver) -> bool:
    try:
        payload = record["payload"]
        expected = dispute_payload(
            wallet_address=payload["wallet_address"], submission_id=submission_id,
            block_height=block_height, block_hash=block_hash, media_hash=media_hash,
            reason=payload["reason"], nonce=payload["nonce"],
            issued_at=payload["issued_at"], expires_at=payload["expires_at"],
            network_id=payload["network_id"],
        )
        if payload != expected or record["message"] != canonical_json_text(expected):
            return False
        if record["identity"] != dispute_identity(expected, record["signature"]):
            return False
        if recover_signed_wallet_address(record["message"], record["signature"]) != expected["wallet_address"]:
            return False
        reference = record["reviewer_reference"]
        return (reference["status"] in ELIGIBLE_STATUSES and
                status_resolver(expected["wallet_address"], reference["height"],
                                reference["block_hash"]) == reference["status"])
    except (KeyError, TypeError, ValueError):
        return False


def dispute_tally(records: list[dict[str, Any]], *, submission_id: str,
                  block_height: int, block_hash: str, media_hash: str) -> dict[str, Any]:
    ordered = sorted(records, key=lambda item: (
        item["payload"]["wallet_address"], item["identity"], canonical_hash(item)))
    representatives = {}
    established_evidence = {}
    seen = set()
    for record in ordered:
        digest = canonical_hash(record)
        if digest in seen:
            raise ValueError("Duplicate signed dispute observation.")
        seen.add(digest)
        wallet = record["payload"]["wallet_address"]
        representatives.setdefault(wallet, record)
        if record["reviewer_reference"]["status"] == "ESTABLISHED_REVIEWER":
            established_evidence.setdefault(wallet, record)
    counted = []
    for wallet, record in sorted(representatives.items()):
        established = established_evidence.get(wallet)
        counted.append({
            "wallet_address": wallet, "reason": record["payload"]["reason"],
            "identity": record["identity"], "reviewer_reference": record["reviewer_reference"],
            "established_evidence": ({"identity": established["identity"],
                                      "reviewer_reference": established["reviewer_reference"]}
                                     if established else None),
        })
    evidence = {
        "policy_digest": dispute_policy_digest(), "submission_id": submission_id,
        "block_height": block_height, "block_hash": block_hash,
        "media_hash": media_hash, "disputes": counted,
    }
    met = len(counted) >= 3 and len(established_evidence) >= 1
    return {
        "policy_id": DISPUTE_POLICY_ID, "policy_version": DISPUTE_POLICY_VERSION,
        "policy_digest": dispute_policy_digest(), "submission_id": submission_id,
        "block_height": block_height, "block_hash": block_hash, "media_hash": media_hash,
        "counted_dispute_count": len(counted), "observed_dispute_count": len(ordered),
        "observed_dispute_digest": canonical_hash([canonical_hash(item) for item in ordered]),
        "established_disputer_count": len(established_evidence),
        "minimum_valid_disputes": 3, "minimum_established_disputers": 1,
        "reason_counts": {reason: sum(item["reason"] == reason for item in counted)
                          for reason in DISPUTE_REASONS},
        "dispute_set": counted, "dispute_set_digest": canonical_hash(evidence),
        "threshold_met": met, "post_mint_status": "disputed" if met else "finalized",
        "finalized": True, "media_immutable": True,
    }
