"""Deterministic reviewer offense evidence and Reputation Rule v2 penalties."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from milestone5_policy import (
    EQUIVOCATION_COOLDOWN_EPOCHS,
    OFFENSE_EVIDENCE_VERSION,
    RATE_LIMIT_ABUSE_COOLDOWN_EPOCHS,
    RATE_LIMIT_EXCESS_THRESHOLD,
    REPUTATION_RULE_VERSION,
    PROBATION_MAX_VOTES_PER_EPOCH,
    ESTABLISHED_MAX_VOTES_PER_EPOCH,
    SELF_VOTE_COOLDOWN_EPOCHS,
    SUSPENSION_EPOCHS,
    reputation_rules,
)
from native_transfer import normalize_wallet_address
from protocol_v1 import PROTOCOL_VERSION, canonical_hash, canonical_json_data
from protocol_v1_originality import (
    PROTOCOL_V1_VOTE_VERSION,
    build_protocol_v1_vote_message,
    calculate_signed_vote_identity,
)
from submission import VOTE_TYPES
from wallet_auth import hash_wallet_message, recover_signed_wallet_address


SIGNED_VOTE_EQUIVOCATION = "SIGNED_VOTE_EQUIVOCATION"
CREATOR_SELF_VOTE = "CREATOR_SELF_VOTE"
RATE_LIMIT_ABUSE = "RATE_LIMIT_ABUSE"
VOTE_DURING_COOLDOWN = "VOTE_DURING_COOLDOWN"
VOTE_DURING_SUSPENSION = "VOTE_DURING_SUSPENSION"

ESCALATING_OFFENSE_TYPES = {
    SIGNED_VOTE_EQUIVOCATION,
    CREATOR_SELF_VOTE,
    RATE_LIMIT_ABUSE,
}
OFFENSE_TYPES = ESCALATING_OFFENSE_TYPES | {
    VOTE_DURING_COOLDOWN,
    VOTE_DURING_SUSPENSION,
}


@dataclass(frozen=True)
class ReputationOutcome:
    offense: dict[str, Any] | None
    replay: bool = False
    penalty: dict[str, Any] | None = None


def _canonical_hash_value(value: Any, *, field_name: str) -> str:
    normalized = str(value or "").strip().lower()
    if len(normalized) != 64 or any(character not in "0123456789abcdef" for character in normalized):
        raise ValueError(f"{field_name} must be a canonical 64-character lowercase hash.")
    return normalized


def canonical_signed_vote_evidence(vote: dict[str, Any]) -> dict[str, Any]:
    """Validate and project the signed fields needed to prove an offense."""
    if not isinstance(vote, dict):
        raise ValueError("Signed vote evidence must be an object.")
    reviewer = normalize_wallet_address(vote.get("reviewer_address") or vote.get("voter_address") or vote.get("voter_wallet_address") or vote.get("voter"))
    if reviewer is None:
        raise ValueError("Signed vote evidence requires a canonical reviewer address.")
    submission_id = str(vote.get("submission_id") or "").strip()
    if not submission_id:
        raise ValueError("Signed vote evidence requires submission_id.")
    content_hash = _canonical_hash_value(vote.get("content_hash"), field_name="content_hash")
    vote_choice = vote.get("vote_choice", vote.get("vote_type", vote.get("vote_value")))
    if vote_choice not in VOTE_TYPES:
        raise ValueError("Signed vote evidence has an unsupported vote choice.")
    vote_version = vote.get("vote_version", vote.get("signed_payload_version"))
    if vote_version != PROTOCOL_V1_VOTE_VERSION or vote.get("protocol_version") != PROTOCOL_VERSION:
        raise ValueError("Offense evidence requires a signed Protocol v1 vote.")
    network_id = str(vote.get("network_id") or "").strip().lower()
    nonce = str(vote.get("vote_nonce") or vote.get("nonce") or "").strip()
    issued_at = str(vote.get("vote_issued_at") or vote.get("issued_at") or "").strip()
    expires_at = str(vote.get("vote_expires_at") or vote.get("expires_at") or "").strip()
    signature = str(vote.get("vote_signature") or vote.get("signature") or "").strip()
    signature_scheme = str(vote.get("signature_scheme") or "").strip().lower()
    message = str(vote.get("vote_message") or vote.get("signed_message") or "")
    if not all((network_id, nonce, issued_at, expires_at, signature, message)):
        raise ValueError("Offense evidence requires the complete signed vote payload.")
    if signature_scheme != "personal_sign":
        raise ValueError("Offense evidence requires personal_sign.")
    signature = signature.lower()
    if not signature.startswith("0x"):
        signature = "0x" + signature
    expected_message = build_protocol_v1_vote_message(
        wallet_address=reviewer,
        submission_id=submission_id,
        content_hash=content_hash,
        vote_type=vote_choice,
        nonce=nonce,
        issued_at=issued_at,
        expires_at=expires_at,
        network_id=network_id,
    )
    if message != expected_message:
        raise ValueError("Signed vote evidence message does not match its canonical payload.")
    if recover_signed_wallet_address(message, signature) != reviewer:
        raise ValueError("Signed vote evidence signature does not match reviewer.")
    message_hash = hash_wallet_message(message)
    if vote.get("signed_message_hash") not in {None, message_hash}:
        raise ValueError("Signed vote evidence message hash is inconsistent.")
    identity = calculate_signed_vote_identity(
        wallet_address=reviewer,
        submission_id=submission_id,
        content_hash=content_hash,
        vote_type=vote_choice,
        nonce=nonce,
        issued_at=issued_at,
        expires_at=expires_at,
        network_id=network_id,
        signature=signature,
        signature_scheme=signature_scheme,
    )
    if vote.get("vote_identity") not in {None, identity}:
        raise ValueError("Signed vote evidence identity is inconsistent.")
    status_height = vote.get("reviewer_status_effective_height")
    status_hash = vote.get("reviewer_status_reference_block_hash")
    return canonical_json_data({
        "content_hash": content_hash,
        "expires_at": expires_at,
        "issued_at": issued_at,
        "network_id": network_id,
        "nonce": nonce,
        "protocol_version": PROTOCOL_VERSION,
        "reviewer_address": reviewer,
        "reviewer_eligible": vote.get("reviewer_eligible"),
        "reviewer_policy_version": vote.get("reviewer_policy_version"),
        "reviewer_status": vote.get("reviewer_status"),
        "reviewer_status_effective_height": status_height,
        "reviewer_status_reference_block_hash": status_hash,
        "reputation_rule_version": vote.get("reputation_rule_version"),
        "signature": signature.lower(),
        "signature_scheme": signature_scheme,
        "signed_message": message,
        "signed_message_hash": message_hash,
        "submission_id": submission_id,
        "vote_choice": vote_choice,
        "vote_identity": identity,
        "vote_version": PROTOCOL_V1_VOTE_VERSION,
    })


def _incident_identity(
    offense_type: str, reviewer: str, *, submission_id: str | None,
    content_hash: str | None, vote_identities: list[str], review_epoch: int,
    active_penalty_id: str | None,
) -> dict[str, Any]:
    identity: dict[str, Any] = {
        "identity_kind": "reviewer-offense-v1",
        "offense_type": offense_type,
        "reputation_rule_version": REPUTATION_RULE_VERSION,
        "reviewer_address": reviewer,
    }
    if offense_type == SIGNED_VOTE_EQUIVOCATION:
        identity.update({"submission_id": submission_id, "content_hash": content_hash})
    elif offense_type == CREATOR_SELF_VOTE:
        identity["vote_identity"] = vote_identities[0]
    elif offense_type == RATE_LIMIT_ABUSE:
        identity["review_epoch"] = review_epoch
    else:
        identity.update({"active_penalty_id": active_penalty_id, "vote_identity": vote_identities[0]})
    return canonical_json_data(identity)


def build_offense_evidence(
    *, offense_type: str, votes: list[dict[str, Any]],
    reference_finalized_height: int, reference_finalized_block_hash: str,
    review_epoch: int, creator_address: str | None = None,
    active_penalty_id: str | None = None,
    rate_limit_accepted_votes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    reputation_rules(REPUTATION_RULE_VERSION)
    if offense_type not in OFFENSE_TYPES:
        raise ValueError(f"Unsupported offense type: {offense_type}")
    canonical_votes = sorted(
        (canonical_signed_vote_evidence(vote) for vote in votes),
        key=lambda item: item["vote_identity"],
    )
    if not canonical_votes:
        raise ValueError("Offense evidence requires at least one signed vote.")
    reviewer = canonical_votes[0]["reviewer_address"]
    if any(vote["reviewer_address"] != reviewer for vote in canonical_votes):
        raise ValueError("Offense vote evidence must belong to one reviewer.")
    height = int(reference_finalized_height)
    epoch = int(review_epoch)
    if height < 0 or epoch < 0:
        raise ValueError("Offense canonical reference must be non-negative.")
    block_hash = _canonical_hash_value(reference_finalized_block_hash, field_name="reference_finalized_block_hash")
    vote_identities = [vote["vote_identity"] for vote in canonical_votes]
    submission_id = canonical_votes[0]["submission_id"]
    content_hash = canonical_votes[0]["content_hash"]
    normalized_creator = normalize_wallet_address(creator_address) if creator_address is not None else None
    accepted_context = sorted(
        (canonical_signed_vote_evidence(vote) for vote in (rate_limit_accepted_votes or [])),
        key=lambda item: item["vote_identity"],
    )
    rate_limit_context = None
    if offense_type == RATE_LIMIT_ABUSE:
        status = canonical_votes[0].get("reviewer_status")
        maximum = PROBATION_MAX_VOTES_PER_EPOCH if status == "PROBATIONARY_REVIEWER" else ESTABLISHED_MAX_VOTES_PER_EPOCH if status == "ESTABLISHED_REVIEWER" else 0
        rate_limit_context = {"maximum_votes": maximum, "accepted_votes": accepted_context}
    identity_payload = _incident_identity(
        offense_type, reviewer, submission_id=submission_id,
        content_hash=content_hash, vote_identities=vote_identities,
        review_epoch=epoch, active_penalty_id=active_penalty_id,
    )
    evidence_payload = canonical_json_data({
        "active_penalty_id": active_penalty_id,
        "content_hash": content_hash,
        "creator_address": normalized_creator,
        "offense_type": offense_type,
        "offense_version": OFFENSE_EVIDENCE_VERSION,
        "reference_finalized_block_hash": block_hash,
        "reference_finalized_height": height,
        "reputation_rule_version": REPUTATION_RULE_VERSION,
        "rate_limit_context": rate_limit_context,
        "review_epoch": epoch,
        "reviewer_address": reviewer,
        "submission_id": submission_id,
        "votes": canonical_votes,
    })
    return {
        "offense_id": canonical_hash(identity_payload),
        "offense_version": OFFENSE_EVIDENCE_VERSION,
        "reviewer_address": reviewer,
        "offense_type": offense_type,
        "submission_id": submission_id,
        "content_hash": content_hash,
        "vote_identities": vote_identities,
        "reputation_rule_version": REPUTATION_RULE_VERSION,
        "reference_finalized_height": height,
        "reference_finalized_block_hash": block_hash,
        "review_epoch": epoch,
        "evidence_payload": evidence_payload,
        "evidence_digest": canonical_hash(evidence_payload),
        "reason_code": offense_type,
    }


def validate_offense_evidence(
    offense: dict[str, Any], *,
    finalized_reference_validator: Callable[[int, str], bool] | None = None,
    creator_resolver: Callable[[str], str | None] | None = None,
    accepted_vote_resolver: Callable[[str], dict[str, Any] | None] | None = None,
    reviewer_status_resolver: Callable[[dict[str, Any]], str | None] | None = None,
) -> dict[str, Any]:
    if not isinstance(offense, dict):
        raise ValueError("Reviewer offense must be an object.")
    if offense.get("reputation_rule_version") != REPUTATION_RULE_VERSION:
        reputation_rules(offense.get("reputation_rule_version"))
        raise ValueError("Reviewer offense does not use the active reputation rule.")
    payload = offense.get("evidence_payload")
    if not isinstance(payload, dict) or canonical_hash(payload) != offense.get("evidence_digest"):
        raise ValueError("Reviewer offense evidence digest is inconsistent.")
    rebuilt = build_offense_evidence(
        offense_type=payload.get("offense_type"),
        votes=list(payload.get("votes") or []),
        reference_finalized_height=payload.get("reference_finalized_height"),
        reference_finalized_block_hash=payload.get("reference_finalized_block_hash"),
        review_epoch=payload.get("review_epoch"),
        creator_address=payload.get("creator_address"),
        active_penalty_id=payload.get("active_penalty_id"),
        rate_limit_accepted_votes=list((payload.get("rate_limit_context") or {}).get("accepted_votes") or []),
    )
    for field in (
        "offense_id", "offense_version", "reviewer_address", "offense_type",
        "submission_id", "content_hash", "vote_identities",
        "reputation_rule_version", "reference_finalized_height",
        "reference_finalized_block_hash", "review_epoch", "evidence_digest",
        "reason_code",
    ):
        if offense.get(field) != rebuilt.get(field):
            raise ValueError(f"Reviewer offense {field} is inconsistent.")
    votes = payload["votes"]
    if rebuilt["offense_type"] == SIGNED_VOTE_EQUIVOCATION:
        if len(votes) < 2:
            raise ValueError("Equivocation evidence requires two signed votes.")
        bindings = {(vote["submission_id"], vote["content_hash"], vote["reviewer_address"]) for vote in votes}
        if len(bindings) != 1 or len({vote["vote_choice"] for vote in votes}) < 2:
            raise ValueError("Equivocation evidence does not prove conflicting signed choices.")
    elif rebuilt["offense_type"] == CREATOR_SELF_VOTE:
        creator = normalize_wallet_address(payload.get("creator_address"))
        if creator_resolver is not None:
            creator = normalize_wallet_address(creator_resolver(rebuilt["submission_id"]))
        if creator is None or creator != rebuilt["reviewer_address"]:
            raise ValueError("Self-vote evidence does not match the canonical creator.")
    elif rebuilt["offense_type"] == RATE_LIMIT_ABUSE:
        if len(set(rebuilt["vote_identities"])) < RATE_LIMIT_EXCESS_THRESHOLD:
            raise ValueError("Rate-limit abuse evidence does not meet the excess-attempt threshold.")
        context = payload.get("rate_limit_context")
        if not isinstance(context, dict):
            raise ValueError("Rate-limit abuse evidence requires quota context.")
        accepted = list(context.get("accepted_votes") or [])
        expected_maximum = (
            PROBATION_MAX_VOTES_PER_EPOCH
            if votes[0].get("reviewer_status") == "PROBATIONARY_REVIEWER"
            else ESTABLISHED_MAX_VOTES_PER_EPOCH
            if votes[0].get("reviewer_status") == "ESTABLISHED_REVIEWER"
            else 0
        )
        if expected_maximum <= 0 or context.get("maximum_votes") != expected_maximum or len(accepted) != expected_maximum:
            raise ValueError("Rate-limit abuse evidence does not prove exhausted reviewer quota.")
        accepted_identities = {vote["vote_identity"] for vote in accepted}
        if len(accepted_identities) != len(accepted) or accepted_identities.intersection(rebuilt["vote_identities"]):
            raise ValueError("Rate-limit abuse quota evidence contains duplicate vote identities.")
        if len({vote["submission_id"] for vote in accepted}) != len(accepted):
            raise ValueError("Rate-limit abuse quota evidence must contain distinct submissions.")
        for vote in accepted + votes:
            if vote.get("reviewer_address") != rebuilt["reviewer_address"]:
                raise ValueError("Rate-limit abuse votes do not belong to one reviewer.")
            height = vote.get("reviewer_status_effective_height")
            if (
                vote.get("reviewer_policy_version") != 1
                or vote.get("reputation_rule_version") != REPUTATION_RULE_VERSION
                or isinstance(height, bool) or not isinstance(height, int)
                or height // 5 != rebuilt["review_epoch"]
            ):
                raise ValueError("Rate-limit abuse vote does not bind the canonical review epoch.")
        if any(vote.get("reviewer_eligible") is not True for vote in accepted):
            raise ValueError("Rate-limit abuse quota evidence contains a non-countable accepted vote.")
        if any(vote.get("reviewer_eligible") is not False for vote in votes):
            raise ValueError("Rate-limit abuse excess evidence is not bound to quota rejection.")
        if accepted_vote_resolver is not None:
            for vote in accepted:
                stored_vote = accepted_vote_resolver(vote["vote_identity"])
                if (
                    not isinstance(stored_vote, dict)
                    or stored_vote.get("lifecycle_state") != "accepted"
                    or canonical_signed_vote_evidence(stored_vote) != vote
                ):
                    raise ValueError("Rate-limit abuse quota vote is not in canonical accepted history.")
        if reviewer_status_resolver is not None:
            for vote in accepted + votes:
                if reviewer_status_resolver(vote) != vote.get("reviewer_status"):
                    raise ValueError("Rate-limit abuse vote has an invalid historical reviewer status.")
        if creator_resolver is not None:
            for vote in accepted + votes:
                creator = normalize_wallet_address(creator_resolver(vote["submission_id"]))
                if creator is None or creator == rebuilt["reviewer_address"]:
                    raise ValueError("Rate-limit abuse quota evidence contains a non-countable submission vote.")
    elif not payload.get("active_penalty_id"):
        raise ValueError("In-penalty vote evidence must reference an active penalty.")
    if finalized_reference_validator is not None and not finalized_reference_validator(
        rebuilt["reference_finalized_height"], rebuilt["reference_finalized_block_hash"]
    ):
        raise ValueError("Reviewer offense reference is not finalized and canonical.")
    return rebuilt


class ReviewerReputationService:
    """Apply only locally verified canonical offenses to durable state."""

    def __init__(self, storage):
        self.storage = storage

    def offenses(self, reviewer_address: str, offense_type: str | None = None) -> list[dict[str, Any]]:
        if not hasattr(self.storage, "list_reviewer_offenses"):
            return []
        return self.storage.list_reviewer_offenses(reviewer_address, offense_type=offense_type)

    def penalties(self, reviewer_address: str) -> list[dict[str, Any]]:
        if not hasattr(self.storage, "list_reviewer_penalties"):
            return []
        return self.storage.list_reviewer_penalties(reviewer_address)

    def active_penalties(self, reviewer_address: str, epoch: int, *, reputation_rule_version: int = REPUTATION_RULE_VERSION) -> list[dict[str, Any]]:
        reputation_rules(reputation_rule_version)
        if reputation_rule_version != REPUTATION_RULE_VERSION:
            return []
        return [
            penalty for penalty in self.penalties(reviewer_address)
            if penalty["reputation_rule_version"] == reputation_rule_version
            and int(penalty["penalty_start_epoch"]) <= int(epoch) < int(penalty["penalty_end_epoch"])
        ]

    def effective_penalty(self, reviewer_address: str, epoch: int, *, reputation_rule_version: int = REPUTATION_RULE_VERSION) -> dict[str, Any] | None:
        active = self.active_penalties(reviewer_address, epoch, reputation_rule_version=reputation_rule_version)
        if not active:
            return None
        status = "SUSPENDED" if any(item["penalty_status"] == "SUSPENDED" for item in active) else "COOLDOWN"
        candidates = [item for item in active if item["penalty_status"] == status]
        chosen = max(candidates, key=lambda item: (int(item["penalty_end_epoch"]), item["penalty_id"]))
        return dict(chosen) | {
            "effective_status": status,
            "effective_end_epoch": max(int(item["penalty_end_epoch"]) for item in active),
        }

    @staticmethod
    def _schedule(offense_type: str, sequence: int) -> tuple[str, int]:
        cooldowns = {
            SIGNED_VOTE_EQUIVOCATION: EQUIVOCATION_COOLDOWN_EPOCHS,
            CREATOR_SELF_VOTE: SELF_VOTE_COOLDOWN_EPOCHS,
            RATE_LIMIT_ABUSE: RATE_LIMIT_ABUSE_COOLDOWN_EPOCHS,
        }[offense_type]
        return ("COOLDOWN", cooldowns[sequence - 1]) if sequence <= len(cooldowns) else ("SUSPENDED", SUSPENSION_EPOCHS)

    def apply_verified_offense(self, offense: dict[str, Any], *, state_before: str) -> ReputationOutcome:
        validated = validate_offense_evidence(offense)
        existing = next((item for item in self.offenses(validated["reviewer_address"]) if item["offense_id"] == validated["offense_id"]), None)
        if existing is not None:
            return ReputationOutcome(existing, replay=True)
        epoch = validated["review_epoch"]
        current = self.effective_penalty(validated["reviewer_address"], epoch)
        offense_type = validated["offense_type"]
        penalty = None
        sequence = 0
        resulting_state = current["effective_status"] if current else state_before
        start_epoch = end_epoch = None
        if offense_type in ESCALATING_OFFENSE_TYPES:
            sequence = len(self.offenses(validated["reviewer_address"], offense_type)) + 1
            penalty_status, duration = self._schedule(offense_type, sequence)
            start_epoch, end_epoch = epoch, epoch + duration
            if current and current["effective_status"] == "SUSPENDED":
                resulting_state = "SUSPENDED"
                penalty = None
                start_epoch = end_epoch = None
            else:
                resulting_state = "SUSPENDED" if penalty_status == "SUSPENDED" else (current["effective_status"] if current and current["effective_status"] == "SUSPENDED" else "COOLDOWN")
                penalty = {
                    "penalty_id": validated["offense_id"],
                    "offense_id": validated["offense_id"],
                    "reviewer_address": validated["reviewer_address"],
                    "penalty_type": offense_type,
                    "penalty_status": penalty_status,
                    "penalty_start_epoch": start_epoch,
                    "penalty_duration_epochs": duration,
                    "penalty_end_epoch": end_epoch,
                    "reference_finalized_height": validated["reference_finalized_height"],
                    "reference_finalized_block_hash": validated["reference_finalized_block_hash"],
                    "reputation_rule_version": REPUTATION_RULE_VERSION,
                    "prior_reviewer_status": state_before,
                }
        elif offense_type == VOTE_DURING_COOLDOWN:
            if current is None or current["effective_status"] != "COOLDOWN":
                raise ValueError("Cooldown-vote offense does not reference an active cooldown.")
            duration = int(current["penalty_duration_epochs"])
            start_epoch = epoch
            end_epoch = max(int(current["effective_end_epoch"]), epoch + duration)
            resulting_state = "COOLDOWN"
            penalty = {
                "penalty_id": validated["offense_id"],
                "offense_id": validated["offense_id"],
                "reviewer_address": validated["reviewer_address"],
                "penalty_type": offense_type,
                "penalty_status": "COOLDOWN",
                "penalty_start_epoch": start_epoch,
                "penalty_duration_epochs": duration,
                "penalty_end_epoch": end_epoch,
                "reference_finalized_height": validated["reference_finalized_height"],
                "reference_finalized_block_hash": validated["reference_finalized_block_hash"],
                "reputation_rule_version": REPUTATION_RULE_VERSION,
                "prior_reviewer_status": state_before,
            }
        elif offense_type == VOTE_DURING_SUSPENSION:
            if current is None or current["effective_status"] != "SUSPENDED":
                raise ValueError("Suspension-vote offense does not reference an active suspension.")
            resulting_state = "SUSPENDED"
        record = validated | {
            "recorded_state_before": state_before,
            "resulting_state": resulting_state,
            "penalty_start_epoch": start_epoch,
            "penalty_end_epoch": end_epoch,
            "escalation_count": sequence,
        }
        inserted = self.storage.record_reviewer_offense(record)
        if inserted.get("replay"):
            return ReputationOutcome(record, replay=True)
        if penalty is not None:
            self.storage.record_reviewer_penalty(penalty)
        return ReputationOutcome(record, penalty=penalty)

    def record_rate_limit_excess(
        self, vote: dict[str, Any], *, reference_finalized_height: int,
        reference_finalized_block_hash: str, review_epoch: int, state_before: str,
    ) -> ReputationOutcome:
        result = self.storage.record_rate_limit_excess_attempt(
            vote, review_epoch=review_epoch,
            reference_finalized_height=reference_finalized_height,
            reference_finalized_block_hash=reference_finalized_block_hash,
        )
        if result["replay"] or result["count"] < RATE_LIMIT_EXCESS_THRESHOLD:
            return ReputationOutcome(None, replay=result["replay"])
        canonical_vote = canonical_signed_vote_evidence(vote)
        status = canonical_vote.get("reviewer_status")
        maximum_votes = (
            PROBATION_MAX_VOTES_PER_EPOCH
            if status == "PROBATIONARY_REVIEWER"
            else ESTABLISHED_MAX_VOTES_PER_EPOCH
            if status == "ESTABLISHED_REVIEWER"
            else 0
        )
        accepted_votes = sorted(
            (
                stored_vote
                for stored_vote in self.storage.list_durable_votes()
                if stored_vote.get("lifecycle_state") == "accepted"
                and stored_vote.get("identity_status") == "canonical"
                and stored_vote.get("voter_address") == canonical_vote["reviewer_address"]
                and stored_vote.get("reviewer_policy_version") == 1
                and stored_vote.get("reputation_rule_version") == REPUTATION_RULE_VERSION
                and stored_vote.get("reviewer_eligible") is True
                and isinstance(stored_vote.get("reviewer_status_effective_height"), int)
                and stored_vote["reviewer_status_effective_height"] // 5 == int(review_epoch)
            ),
            key=lambda item: item["vote_identity"],
        )
        if maximum_votes <= 0 or len(accepted_votes) < maximum_votes:
            raise ValueError("Rate-limit abuse cannot be proven without the accepted epoch quota evidence.")
        offense = build_offense_evidence(
            offense_type=RATE_LIMIT_ABUSE,
            votes=result["votes"][:RATE_LIMIT_EXCESS_THRESHOLD],
            reference_finalized_height=reference_finalized_height,
            reference_finalized_block_hash=reference_finalized_block_hash,
            review_epoch=review_epoch,
            rate_limit_accepted_votes=accepted_votes[:maximum_votes],
        )
        return self.apply_verified_offense(offense, state_before=state_before)

    def summary(self, reviewer_address: str, epoch: int | None, underlying_status: str) -> dict[str, Any]:
        address = normalize_wallet_address(reviewer_address)
        if address is None:
            raise ValueError("reviewer_address must be a valid Ethereum-style 0x address.")
        offenses = self.offenses(address)
        active = self.effective_penalty(address, epoch) if epoch is not None else None
        counts = {kind: sum(item["offense_type"] == kind for item in offenses) for kind in ESCALATING_OFFENSE_TYPES}
        return {
            "reviewer_address": address,
            "underlying_reviewer_status": underlying_status,
            "effective_reviewer_status": active["effective_status"] if active else underlying_status,
            "active_penalty_type": active["penalty_type"] if active else None,
            "penalty_start_epoch": active["penalty_start_epoch"] if active else None,
            "penalty_end_epoch": active["effective_end_epoch"] if active else None,
            "epochs_remaining": max(0, int(active["effective_end_epoch"]) - int(epoch)) if active and epoch is not None else 0,
            "equivocation_offense_count": counts[SIGNED_VOTE_EQUIVOCATION],
            "self_vote_offense_count": counts[CREATOR_SELF_VOTE],
            "rate_limit_abuse_offense_count": counts[RATE_LIMIT_ABUSE],
            "latest_offense_id": offenses[-1]["offense_id"] if offenses else None,
            "reputation_rule_version": REPUTATION_RULE_VERSION,
        }
