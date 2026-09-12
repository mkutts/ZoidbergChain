"""Canonical finalized-chain reviewer qualification, transitions, and snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from milestone5_policy import (
    CREATOR_PATH_MIN_FINALIZED_MINTED_SUBMISSIONS,
    ESTABLISHED_MAX_VOTES_PER_EPOCH,
    MIN_WALLET_AGE_EPOCHS,
    MIXED_PATH_MIN_FINALIZED_MINTED_SUBMISSIONS,
    MIXED_PATH_MIN_FINALIZED_NATIVE_TRANSACTIONS,
    PROBATION_MAX_VOTES_PER_EPOCH,
    PROBATION_MIN_DURATION_EPOCHS,
    PROBATION_MIN_VALID_VOTES_FOR_PROMOTION,
    REVIEWER_POLICY_VERSION,
    REPUTATION_RULE_VERSION,
    ZOID_PATH_MIN_ACTIVITY_SPAN_EPOCHS,
    ZOID_PATH_MIN_FINALIZED_NATIVE_TRANSACTIONS,
    bootstrap_established_reviewers,
    reputation_rules,
    review_epoch,
    reviewer_policy,
)
from native_transfer import normalize_wallet_address
from protocol_v1 import canonical_hash, canonical_json_data, canonical_json_text
from reviewer_reputation import ReviewerReputationService


PATH_ORDER = ("creator", "zoid_activity", "mixed")


@dataclass(frozen=True)
class ReviewerVoteDecision:
    eligible: bool
    reason: str
    status: str
    votes_used_this_epoch: int
    votes_remaining_this_epoch: int
    review_epoch: int | None
    snapshot: dict[str, Any]


class ReviewerEligibilityService:
    """Derives reviewer facts solely from versioned policy and finalized ancestry."""

    @staticmethod
    def _block_value(block, field: str, default=None):
        return block.get(field, default) if isinstance(block, dict) else getattr(block, field, default)

    @classmethod
    def finalized_context(cls, chain, finalized_head) -> tuple[int | None, str | None, list]:
        if not finalized_head:
            return None, None, []
        height = int(finalized_head["block_height"])
        block_hash = str(finalized_head["block_hash"]).strip().lower()
        blocks = sorted(
            (block for block in chain if int(cls._block_value(block, "index", -1)) <= height),
            key=lambda block: int(cls._block_value(block, "index")),
        )
        canonical = next((block for block in blocks if int(cls._block_value(block, "index")) == height), None)
        if canonical is None or str(cls._block_value(canonical, "hash") or "").strip().lower() != block_hash:
            raise ValueError("Finalized reviewer reference does not match the canonical chain.")
        return height, block_hash, blocks

    @classmethod
    def _canonical_activity(cls, address: str, blocks: list) -> tuple[list[dict], list[dict], int | None]:
        minted_by_submission: dict[str, dict] = {}
        native_by_id: dict[str, dict] = {}
        origin_heights: list[int] = []
        for block in blocks:
            height = int(cls._block_value(block, "index"))
            submission_id = str(cls._block_value(block, "submission_id") or "").strip()
            creator = normalize_wallet_address(cls._block_value(block, "creator_wallet"))
            if submission_id and creator == address:
                minted_by_submission.setdefault(submission_id, {"submission_id": submission_id, "block_height": height})
                origin_heights.append(height)
            for transaction in list(cls._block_value(block, "native_transactions", []) or []):
                if not isinstance(transaction, dict):
                    continue
                tx_id = str(transaction.get("tx_id") or "").strip().lower()
                sender = normalize_wallet_address(transaction.get("from_address"))
                recipient = normalize_wallet_address(transaction.get("to_address"))
                if address not in {sender, recipient}:
                    continue
                origin_heights.append(height)
                # Self-transfers are canonical participation for wallet age but are
                # excluded from the earned transaction count as a simple anti-farming rule.
                if tx_id and sender != recipient:
                    native_by_id.setdefault(tx_id, {"tx_id": tx_id, "block_height": height})
        minted = sorted(minted_by_submission.values(), key=lambda item: (item["block_height"], item["submission_id"]))
        native = sorted(native_by_id.values(), key=lambda item: (item["block_height"], item["tx_id"]))
        return minted, native, min(origin_heights) if origin_heights else None

    def qualification(self, *, reviewer_address: str, chain, finalized_head, policy_version: int = REVIEWER_POLICY_VERSION) -> dict[str, Any]:
        reviewer_policy(policy_version)  # deterministic unknown-version failure
        address = normalize_wallet_address(reviewer_address)
        if address is None:
            raise ValueError("reviewer_address must be a valid Ethereum-style 0x address.")
        height, block_hash, blocks = self.finalized_context(chain, finalized_head)
        minted, native, origin = self._canonical_activity(address, blocks)
        epoch = review_epoch(height, policy_version) if height is not None else None
        wallet_age = ((height - origin) // reviewer_policy(policy_version)["review_epoch_blocks"]
                      if height is not None and origin is not None else 0)
        activity_epochs = [review_epoch(item["block_height"], policy_version) for item in native]
        span = max(activity_epochs) - min(activity_epochs) if activity_epochs else 0
        age_ok = origin is not None and wallet_age >= MIN_WALLET_AGE_EPOCHS
        creator_ok = age_ok and len(minted) >= CREATOR_PATH_MIN_FINALIZED_MINTED_SUBMISSIONS
        zoid_ok = age_ok and len(native) >= ZOID_PATH_MIN_FINALIZED_NATIVE_TRANSACTIONS and span >= ZOID_PATH_MIN_ACTIVITY_SPAN_EPOCHS
        mixed_ok = age_ok and len(minted) >= MIXED_PATH_MIN_FINALIZED_MINTED_SUBMISSIONS and len(native) >= MIXED_PATH_MIN_FINALIZED_NATIVE_TRANSACTIONS
        path_values = {"creator": creator_ok, "zoid_activity": zoid_ok, "mixed": mixed_ok}
        qualified_paths = [name for name in PATH_ORDER if path_values[name]]
        return canonical_json_data({
            "reviewer_address": address,
            "reviewer_policy_version": policy_version,
            "reference_finalized_height": height,
            "reference_finalized_block_hash": block_hash,
            "review_epoch": epoch,
            "wallet_origin_height": origin,
            "wallet_age_epochs": wallet_age,
            "creator_path": {"finalized_minted_submissions": len(minted), "qualified": creator_ok},
            "zoid_path": {"finalized_native_transactions": len(native), "activity_span_epochs": span, "qualified": zoid_ok},
            "mixed_path": {"finalized_minted_submissions": len(minted), "finalized_native_transactions": len(native), "qualified": mixed_ok},
            "overall_qualified": bool(qualified_paths),
            "qualification_path": qualified_paths[0] if qualified_paths else None,
            "qualifying_paths": qualified_paths,
        })

    @staticmethod
    def _accepted_votes(storage, address: str) -> list[dict]:
        if not hasattr(storage, "list_durable_votes"):
            return []
        return [vote for vote in storage.list_durable_votes() if vote.get("lifecycle_state") == "accepted" and normalize_wallet_address(vote.get("voter_address")) == address]

    def reconcile(self, *, reviewer_address: str, chain, finalized_head, storage, policy_version: int = REVIEWER_POLICY_VERSION, persist: bool = True) -> tuple[dict, dict]:
        evidence = self.qualification(reviewer_address=reviewer_address, chain=chain, finalized_head=finalized_head, policy_version=policy_version)
        address = evidence["reviewer_address"]
        state = storage.get_reviewer_state(address) if hasattr(storage, "get_reviewer_state") else None
        if persist and state is None and hasattr(storage, "initialize_reviewer_state"):
            state = storage.initialize_reviewer_state(address)
        state = state or {"reviewer_address": address, "current_status": "NEW", "bootstrap_established": False, "status_effective_height": None}
        height, block_hash, epoch = evidence["reference_finalized_height"], evidence["reference_finalized_block_hash"], evidence["review_epoch"]
        if height is None:
            return state, evidence
        bootstrap = address in bootstrap_established_reviewers(policy_version)
        durable_transitions = persist and hasattr(storage, "transition_reviewer_state")
        reputation = ReviewerReputationService(storage)
        active_penalty = reputation.effective_penalty(address, epoch)
        underlying_projection = None
        if state["current_status"] in {"COOLDOWN", "SUSPENDED"} and hasattr(storage, "list_reviewer_state_history"):
            eligible_history = [
                item for item in storage.list_reviewer_state_history(address)
                if item.get("to_status") not in {"COOLDOWN", "SUSPENDED"}
                and item.get("status_effective_height") is not None
                and int(item["status_effective_height"]) <= height
            ]
            if eligible_history:
                latest_underlying = eligible_history[-1]
                underlying_projection = {
                    **state,
                    "current_status": latest_underlying["to_status"],
                    "status_effective_height": latest_underlying["status_effective_height"],
                    "status_reference_block_hash": latest_underlying["status_reference_block_hash"],
                }
        if state["current_status"] in {"COOLDOWN", "SUSPENDED"} and active_penalty is None:
            penalties = reputation.penalties(address)
            if penalties:
                restoration = underlying_projection["current_status"] if underlying_projection else penalties[-1]["prior_reviewer_status"]
                if restoration in {"COOLDOWN", "SUSPENDED"}:
                    restoration = "ESTABLISHED_REVIEWER" if bootstrap else "PROBATIONARY_REVIEWER" if evidence["overall_qualified"] else "NEW"
                reason = canonical_json_text({"reason_code": "REPUTATION_PENALTY_EXPIRED", "effective_review_epoch": epoch})
                if durable_transitions:
                    state = storage.transition_reviewer_state(
                        address, to_status=restoration, reviewer_policy_version=policy_version,
                        reputation_rule_version=REPUTATION_RULE_VERSION,
                        status_effective_height=height, status_reference_block_hash=block_hash,
                        bootstrap_established=bootstrap and restoration == "ESTABLISHED_REVIEWER",
                        reason=reason,
                    )
                else:
                    state = {**state, "current_status": restoration}
        elif active_penalty is not None and underlying_projection is not None:
            state = underlying_projection
        if not durable_transitions and state["current_status"] == "NEW":
            if bootstrap:
                state = {**state, "current_status": "ESTABLISHED_REVIEWER", "bootstrap_established": True, "status_effective_height": height, "status_reference_block_hash": block_hash}
            elif evidence["overall_qualified"]:
                state = {**state, "current_status": "PROBATIONARY_REVIEWER", "status_effective_height": height, "status_reference_block_hash": block_hash}
            return state, evidence
        if state["current_status"] == "NEW" and bootstrap:
            reason = canonical_json_text({"reason_code": "BOOTSTRAP_POLICY_GRANT", "policy_version": policy_version, "provenance": "PUBLIC_TESTNET_V1_BOOTSTRAP_ESTABLISHED_REVIEWERS"})
            state = storage.transition_reviewer_state(address, to_status="ESTABLISHED_REVIEWER", reviewer_policy_version=policy_version, reputation_rule_version=REPUTATION_RULE_VERSION, status_effective_height=height, status_reference_block_hash=block_hash, bootstrap_established=True, reason=reason)
        elif state["current_status"] == "NEW" and evidence["overall_qualified"]:
            reason = canonical_json_text({"reason_code": "EARNED_QUALIFICATION", "qualification_path": evidence["qualification_path"], "qualification_evidence_digest": canonical_hash(evidence), "effective_review_epoch": epoch})
            state = storage.transition_reviewer_state(address, to_status="PROBATIONARY_REVIEWER", reviewer_policy_version=policy_version, reputation_rule_version=REPUTATION_RULE_VERSION, status_effective_height=height, status_reference_block_hash=block_hash, reason=reason)
        if state["current_status"] == "PROBATIONARY_REVIEWER":
            started_epoch = review_epoch(int(state["status_effective_height"]), policy_version)
            probation_votes = sum(
                1 for vote in self._accepted_votes(storage, address)
                if vote.get("reviewer_status") == "PROBATIONARY_REVIEWER"
                and vote.get("reviewer_policy_version") == policy_version
                and vote.get("reviewer_status_effective_height") is not None
                and int(vote["reviewer_status_effective_height"]) >= int(state["status_effective_height"])
            )
            if epoch - started_epoch >= PROBATION_MIN_DURATION_EPOCHS and probation_votes >= PROBATION_MIN_VALID_VOTES_FOR_PROMOTION:
                reason = canonical_json_text({"reason_code": "PROBATION_COMPLETED", "probation_started_epoch": started_epoch, "effective_review_epoch": epoch, "valid_probationary_votes": probation_votes})
                if durable_transitions:
                    state = storage.transition_reviewer_state(address, to_status="ESTABLISHED_REVIEWER", reviewer_policy_version=policy_version, reputation_rule_version=REPUTATION_RULE_VERSION, status_effective_height=height, status_reference_block_hash=block_hash, reason=reason)
                else:
                    state = {**state, "current_status": "ESTABLISHED_REVIEWER", "status_effective_height": height, "status_reference_block_hash": block_hash}
        underlying_status = state["current_status"]
        if active_penalty is not None:
            effective_status = active_penalty["effective_status"]
            if durable_transitions and state["current_status"] != effective_status:
                reason = canonical_json_text({"reason_code": "ACTIVE_REPUTATION_PENALTY", "offense_id": active_penalty["offense_id"], "penalty_end_epoch": active_penalty["effective_end_epoch"]})
                state = storage.transition_reviewer_state(
                    address, to_status=effective_status,
                    reviewer_policy_version=policy_version,
                    reputation_rule_version=REPUTATION_RULE_VERSION,
                    status_effective_height=height,
                    status_reference_block_hash=block_hash,
                    reason=reason,
                )
            else:
                state = {**state, "current_status": effective_status}
        state = {**state, "underlying_reviewer_status": underlying_status}
        return state, evidence

    def vote_decision(self, *, reviewer_address: str, chain, finalized_head, storage, policy_version: int = REVIEWER_POLICY_VERSION) -> ReviewerVoteDecision:
        state, evidence = self.reconcile(reviewer_address=reviewer_address, chain=chain, finalized_head=finalized_head, storage=storage, policy_version=policy_version)
        status, epoch = state["current_status"], evidence["review_epoch"]
        votes = self._accepted_votes(storage, evidence["reviewer_address"])
        used = sum(1 for vote in votes if vote.get("reviewer_policy_version") == policy_version and vote.get("reviewer_status_reference_block_hash") and review_epoch(int(vote["reviewer_status_effective_height"]), policy_version) == epoch) if epoch is not None else 0
        limit = PROBATION_MAX_VOTES_PER_EPOCH if status == "PROBATIONARY_REVIEWER" else ESTABLISHED_MAX_VOTES_PER_EPOCH if status == "ESTABLISHED_REVIEWER" else 0
        reason = "eligible" if limit and used < limit else "review_epoch_vote_limit_reached" if limit else "reviewer_status_ineligible"
        return ReviewerVoteDecision(bool(limit and used < limit), reason, status, used, max(0, limit - used), epoch, self.status_payload(state, evidence, votes))

    @staticmethod
    def status_payload(state: dict, evidence: dict, votes: list[dict]) -> dict:
        status = state["current_status"]
        epoch = evidence["review_epoch"]
        started = review_epoch(int(state["status_effective_height"])) if status == "PROBATIONARY_REVIEWER" and state.get("status_effective_height") is not None else None
        probation_start_height = int(state["status_effective_height"]) if started is not None else None
        probation_votes = sum(
            1 for vote in votes
            if vote.get("lifecycle_state") == "accepted"
            and vote.get("reviewer_status") == "PROBATIONARY_REVIEWER"
            and vote.get("reviewer_policy_version") == REVIEWER_POLICY_VERSION
            and vote.get("reviewer_status_effective_height") is not None
            and (probation_start_height is None or int(vote["reviewer_status_effective_height"]) >= probation_start_height)
        )
        limit = PROBATION_MAX_VOTES_PER_EPOCH if status == "PROBATIONARY_REVIEWER" else ESTABLISHED_MAX_VOTES_PER_EPOCH if status == "ESTABLISHED_REVIEWER" else 0
        used = sum(1 for vote in votes if epoch is not None and vote.get("reviewer_status_effective_height") is not None and review_epoch(int(vote["reviewer_status_effective_height"])) == epoch)
        return {"address": evidence["reviewer_address"], "status": status, "underlying_reviewer_status": state.get("underlying_reviewer_status", status), "reviewer_policy_version": REVIEWER_POLICY_VERSION, "reputation_rule_version": REPUTATION_RULE_VERSION, "current_review_epoch": epoch, "wallet_age_epochs": evidence["wallet_age_epochs"], "qualification_paths": evidence["qualifying_paths"], "probation_started_epoch": started, "probation_valid_vote_count": probation_votes, "votes_used_this_epoch": used, "votes_remaining_this_epoch": max(0, limit - used), "promotion_requirements": {"minimum_duration_epochs": PROBATION_MIN_DURATION_EPOCHS, "minimum_valid_votes": PROBATION_MIN_VALID_VOTES_FOR_PROMOTION}, "bootstrap_established": bool(state.get("bootstrap_established"))}

    def status_at_reference(self, *, reviewer_address: str, chain, finalized_head, storage, policy_version: int = REVIEWER_POLICY_VERSION, reputation_rule_version: int = REPUTATION_RULE_VERSION) -> dict[str, Any]:
        """Reconstruct policy status at an explicit finalized canonical reference.

        Earned status is derived from canonical ancestry and durable accepted
        votes instead of a node's current projection.  Explicit cooldown and
        suspension transitions remain authoritative when their canonical
        effective reference is at or before the requested snapshot.
        """
        address = normalize_wallet_address(reviewer_address)
        if address is None:
            raise ValueError("reviewer_address must be a valid Ethereum-style 0x address.")
        height, block_hash, blocks = self.finalized_context(chain, finalized_head)
        if height is None:
            return {"status": "NEW", "bootstrap_established": False, "qualification_effective_height": None}
        reputation_rules(reputation_rule_version)
        penalties = ReviewerReputationService(storage).penalties(address)
        if not penalties and hasattr(storage, "list_reviewer_state_history"):
            applicable = [
                item for item in storage.list_reviewer_state_history(address)
                if item.get("status_effective_height") is not None
                and int(item["status_effective_height"]) <= height
                and item.get("reviewer_policy_version") == policy_version
                and item.get("reputation_rule_version") == reputation_rule_version
            ]
            if applicable and applicable[-1].get("to_status") in {"COOLDOWN", "SUSPENDED"}:
                return {"status": applicable[-1]["to_status"], "underlying_status": "NEW", "bootstrap_established": False, "qualification_effective_height": None}
        if address in bootstrap_established_reviewers(policy_version):
            underlying = "ESTABLISHED_REVIEWER"
            active = ReviewerReputationService(storage).effective_penalty(address, review_epoch(height, policy_version), reputation_rule_version=reputation_rule_version)
            return {"status": active["effective_status"] if active else underlying, "underlying_status": underlying, "bootstrap_established": True, "qualification_effective_height": 0}
        evidence = self.qualification(
            reviewer_address=address, chain=blocks, finalized_head=finalized_head,
            policy_version=policy_version,
        )
        if not evidence["overall_qualified"]:
            underlying = "NEW"
            active = ReviewerReputationService(storage).effective_penalty(address, review_epoch(height, policy_version), reputation_rule_version=reputation_rule_version)
            return {"status": active["effective_status"] if active else underlying, "underlying_status": underlying, "bootstrap_established": False, "qualification_effective_height": None}
        qualification_height = None
        for candidate_height in range(height + 1):
            candidate_block = next(
                block for block in blocks if int(self._block_value(block, "index")) == candidate_height
            )
            candidate_head = {
                "block_height": candidate_height,
                "block_hash": str(self._block_value(candidate_block, "hash")).strip().lower(),
            }
            candidate = self.qualification(
                reviewer_address=address, chain=blocks,
                finalized_head=candidate_head, policy_version=policy_version,
            )
            if candidate["overall_qualified"]:
                qualification_height = candidate_height
                break
        accepted = [
            vote for vote in self._accepted_votes(storage, address)
            if vote.get("reviewer_policy_version") == policy_version
            and vote.get("reviewer_status") == "PROBATIONARY_REVIEWER"
            and vote.get("reviewer_status_effective_height") is not None
            and qualification_height is not None
            and qualification_height <= int(vote["reviewer_status_effective_height"]) <= height
        ]
        duration_met = (
            qualification_height is not None
            and review_epoch(height, policy_version) - review_epoch(qualification_height, policy_version)
            >= PROBATION_MIN_DURATION_EPOCHS
        )
        status = (
            "ESTABLISHED_REVIEWER"
            if duration_met and len(accepted) >= PROBATION_MIN_VALID_VOTES_FOR_PROMOTION
            else "PROBATIONARY_REVIEWER"
        )
        active = ReviewerReputationService(storage).effective_penalty(address, review_epoch(height, policy_version), reputation_rule_version=reputation_rule_version)
        return {"status": active["effective_status"] if active else status, "underlying_status": status, "bootstrap_established": False, "qualification_effective_height": qualification_height}

    def snapshot(self, *, reviewer_addresses, chain, finalized_head, storage, policy_version: int = REVIEWER_POLICY_VERSION, reputation_rule_version: int = REPUTATION_RULE_VERSION) -> dict[str, Any]:
        height, block_hash, _ = self.finalized_context(chain, finalized_head)
        reviewers = []
        for address in sorted({normalize_wallet_address(value) for value in reviewer_addresses if normalize_wallet_address(value)}):
            state = self.status_at_reference(
                reviewer_address=address, chain=chain, finalized_head=finalized_head,
                storage=storage, policy_version=policy_version,
                reputation_rule_version=reputation_rule_version,
            )
            reviewers.append({"address": address, "status": state["status"], "bootstrap_provenance": "PUBLIC_TESTNET_V1_BOOTSTRAP_ESTABLISHED_REVIEWERS" if state.get("bootstrap_established") else None})
        payload = canonical_json_data({"reviewer_policy_version": policy_version, "reputation_rule_version": reputation_rule_version, "reference_finalized_height": height, "reference_finalized_block_hash": block_hash, "review_epoch": review_epoch(height, policy_version) if height is not None else None, "reviewers": reviewers})
        return {**payload, "reviewer_snapshot_digest": canonical_hash(payload), "canonical_serialization": canonical_json_text(payload)}
