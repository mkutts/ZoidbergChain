"""Deterministic creator and voter reward planning over canonical chain state."""

from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal

from config import (
    ENVIRONMENT, MEME_BLOCK_REWARD, REWARD_POOL_SUPPLY, REQUIRE_ACCESS_FOR_REWARDS,
    VOTER_REWARDS_ENABLED, VOTER_REWARD_APPROVAL_SIDE, VOTER_REWARD_MAX_PER_WALLET_ZOID,
    VOTER_REWARD_MIN_DECISIVE_VOTES, VOTER_REWARD_POOL_PER_DECISION_ZOID,
    VOTER_REWARD_REJECTION_SIDE, VOTER_REWARD_REQUIRE_REVIEW_ELIGIBLE,
    VOTING_WINDOW_HOURS, ORIGINALITY_APPROVAL_THRESHOLD,
)
from review_policy import current_day_window, evaluate_review_eligibility, load_review_policy_config
from submission import APPROVED, MINTED, QUEUED, REJECTED, VOTE_NOT_ORIGINAL, VOTE_ORIGINAL

_SCALE = Decimal("1000000")


@dataclass
class RewardState:
    chain: list
    submissions: list
    reward_pool: float
    config: dict


@dataclass
class RewardCollaborators:
    normalize_wallet: object
    get_submission: object
    get_votes: object
    get_certificate: object
    get_voting_threshold: object
    get_activity_summary: object
    count_votes_since: object
    access_decision: object
    get_wallet_binding: object
    get_access_account: object
    find_allowlist_entry: object


class RewardService:
    """Pure reward record, eligibility, planning, and pool calculations."""

    @staticmethod
    def config_value(state, key, default): return state.config.get(key, default)

    @staticmethod
    def block_voter_rewards(block): return list(block.get("voter_rewards", []) or []) if isinstance(block, dict) else list(getattr(block, "voter_rewards", []) or [])
    @staticmethod
    def reward_record_sort_key(record):
        height, minted, reward_id = record.get("block_height"), record.get("minted_at"), record.get("reward_id") or ""
        return (-(int(height) if isinstance(height, int) else -1), -(int(minted) if isinstance(minted, (int, float)) else -1), str(reward_id))
    @staticmethod
    def reward_units_from_decimal(amount): return int((amount * _SCALE).to_integral_value())
    @staticmethod
    def decimal_from_reward_units(units): return Decimal(units) / _SCALE
    @staticmethod
    def normalize_decimal_value(value):
        result = format(value.normalize(), "f")
        if "." in result: result = result.rstrip("0").rstrip(".")
        return result if result and result != "-0" else "0"
    def reward_units_from_amount_string(self, amount, *, allow_zero=True):
        from native_transfer import parse_native_zoid_amount
        return self.reward_units_from_decimal(Decimal(parse_native_zoid_amount(amount or "0", allow_zero=allow_zero)))
    def normalize_reward_amount(self, amount): return self.normalize_decimal_value(amount if isinstance(amount, Decimal) else self.decimal_from_reward_units(int(amount)))
    @staticmethod
    def reward_id(submission_id, wallet_address, final_decision): return f"voter_reward:{submission_id}:{wallet_address}:{final_decision}"

    def resolve_meme_reward_recipient(self, submission, certificate, collaborators):
        for candidate in (getattr(submission, "creator_wallet_address", None), getattr(certificate, "creator_wallet", None), getattr(submission, "submitter", None)):
            normalized = collaborators.normalize_wallet(candidate)
            if normalized: return normalized
        raise ValueError("Minting reward recipient is missing or invalid for this submission.")

    def build_meme_reward_metadata(self, submission, certificate, collaborators, *, minted_at):
        return {"reward_type": "meme_mining_reward", "reward_recipient": self.resolve_meme_reward_recipient(submission, certificate, collaborators), "reward_amount": float(MEME_BLOCK_REWARD), "reward_source": "reward_pool", "minted_at": minted_at}

    def build_creator_reward_record(self, block, collaborators):
        value = lambda field: block.get(field) if isinstance(block, dict) else getattr(block, field, None)
        recipient = collaborators.normalize_wallet(value("reward_recipient"))
        if recipient is None or value("reward_type") != "meme_mining_reward": return None
        submission_id, minted_at, block_hash = value("submission_id"), value("minted_at"), value("hash")
        return {"reward_id": f"creator_reward:{submission_id or block_hash}:{recipient}", "reward_type": value("reward_type"), "reward_recipient": recipient, "reward_amount": value("reward_amount"), "reward_source": value("reward_source"), "reward_status": "settled", "settlement_state": "final", "submission_id": submission_id, "certificate_id": value("certificate_id"), "content_hash": value("content_hash"), "block_hash": block_hash, "block_height": value("index"), "created_at": minted_at, "finalized_at": minted_at, "minted_at": minted_at, "network_name": "zoidberg-testnet"}

    def build_voter_reward_record(self, entry, block, collaborators):
        recipient = collaborators.normalize_wallet(entry.get("reward_recipient"))
        if recipient is None: return None
        value = lambda field: block.get(field) if isinstance(block, dict) else getattr(block, field, None); minted_at = value("minted_at")
        return {"reward_id": entry.get("reward_id"), "reward_type": entry.get("reward_type", "voter_majority_reward"), "reward_recipient": recipient, "voter_wallet_address": recipient, "reward_amount": entry.get("reward_amount"), "reward_source": entry.get("reward_source", "reward_pool"), "reward_status": "settled", "settlement_state": "final", "submission_id": entry.get("submission_id"), "certificate_id": entry.get("certificate_id"), "content_hash": entry.get("content_hash"), "vote_choice": entry.get("vote_choice"), "final_decision": entry.get("final_decision"), "decision_reason": entry.get("decision_reason"), "decision_finalized_at": entry.get("decision_finalized_at"), "created_at": entry.get("created_at") or minted_at, "finalized_at": entry.get("finalized_at") or minted_at, "minted_at": minted_at, "block_hash": value("hash"), "block_height": value("index"), "network_name": entry.get("network_name") or "zoidberg-testnet"}

    def all_reward_records(self, state, collaborators):
        records = []
        for block in state.chain:
            creator = self.build_creator_reward_record(block, collaborators)
            if creator is not None: records.append(creator)
            records.extend(record for entry in self.block_voter_rewards(block) if (record := self.build_voter_reward_record(entry, block, collaborators)) is not None)
        records.sort(key=self.reward_record_sort_key)
        return records

    def settled_voter_reward_ids(self, state):
        return {str(entry.get("reward_id") or "").strip() for block in state.chain for entry in self.block_voter_rewards(block) if str(entry.get("reward_id") or "").strip()}

    def decision_finalized_at(self, submission, vote_summary, collaborators, *, now=None):
        certificate = collaborators.get_certificate(submission.submission_id)
        if certificate is not None and certificate.approved_at is not None: return certificate.approved_at
        if getattr(submission, "decision_finalized_at", None) is not None: return submission.decision_finalized_at
        timestamps = [self._timestamp(vote.get("created_at")) for vote in vote_summary.get("votes", [])]; timestamps = [item for item in timestamps if item is not None]
        return max(timestamps) if timestamps else float(now if now is not None else time.time())

    @staticmethod
    def _timestamp(value):
        if value in (None, ""): return None
        try: return float(value)
        except (TypeError, ValueError):
            from datetime import datetime
            try: return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
            except ValueError: return None

    def get_submission_reward_decision(self, submission_id, collaborators, *, now=None):
        submission = collaborators.get_submission(submission_id)
        if submission is None: raise ValueError(f"Submission not found: {submission_id}")
        decision_now = float(now if now is not None else time.time()); summary = collaborators.get_votes(submission_id); decisive = summary["counts"][VOTE_ORIGINAL] + summary["counts"][VOTE_NOT_ORIGINAL]
        if decisive < VOTER_REWARD_MIN_DECISIVE_VOTES: return None
        certificate = collaborators.get_certificate(submission_id); reason = getattr(submission, "decision_reason", None)
        if certificate is not None or submission.status in {APPROVED, QUEUED, MINTED}:
            return {"submission_id": submission_id, "outcome": "approved_original", "final_decision": VOTER_REWARD_APPROVAL_SIDE, "vote_choice": VOTE_ORIGINAL, "certificate_id": certificate.certificate_id if certificate else getattr(submission, "certificate_id", None), "content_hash": submission.content_hash, "decision_reason": reason or "approved_by_vote", "decision_finalized_at": self.decision_finalized_at(submission, summary, collaborators, now=decision_now)}
        if submission.status != REJECTED or reason not in {None, "rejected_by_vote"}: return None
        expired = decision_now >= submission.created_at + (VOTING_WINDOW_HOURS * 60 * 60); minimum = collaborators.get_voting_threshold(now=decision_now)["minimum_votes"]
        if not (expired or len(summary["votes"]) >= minimum) or summary["approval_percentage"] >= ORIGINALITY_APPROVAL_THRESHOLD: return None
        return {"submission_id": submission_id, "outcome": "rejected_not_original", "final_decision": VOTER_REWARD_REJECTION_SIDE, "vote_choice": VOTE_NOT_ORIGINAL, "certificate_id": None, "content_hash": submission.content_hash, "decision_reason": reason or "rejected_by_vote", "decision_finalized_at": self.decision_finalized_at(submission, summary, collaborators, now=decision_now)}

    def eligible_voter_reward_wallets(self, state, decision, collaborators):
        summary = collaborators.get_votes(decision["submission_id"]); submission = collaborators.get_submission(decision["submission_id"]); creator = collaborators.normalize_wallet(getattr(submission, "creator_wallet_address", None) or getattr(submission, "submitter", None)) if submission else None
        votes = [vote for vote in summary["votes"] if vote.get("vote_type") == decision["vote_choice"]]
        votes.sort(key=lambda vote: (collaborators.normalize_wallet(vote.get("voter_wallet_address") or vote.get("voter")) or "", self._timestamp(vote.get("created_at")) or 0))
        unique, seen, excluded = [], set(), []
        for vote in votes:
            wallet = collaborators.normalize_wallet(vote.get("voter_wallet_address") or vote.get("voter"))
            if wallet is None or wallet == creator or wallet in seen: continue
            seen.add(wallet); unique.append(vote)
        config, eligible = load_review_policy_config(ENVIRONMENT), []
        for vote in unique:
            wallet = collaborators.normalize_wallet(vote.get("voter_wallet_address") or vote.get("voter"))
            if self.config_value(state, "require_access_for_rewards", REQUIRE_ACCESS_FOR_REWARDS):
                access = collaborators.access_decision(wallet)
                if not access.allowed: excluded.append({"wallet_address": wallet, "reason": access.reason}); continue
            if self.config_value(state, "voter_reward_require_review_eligible", VOTER_REWARD_REQUIRE_REVIEW_ELIGIBLE):
                binding, account = collaborators.get_wallet_binding(wallet), collaborators.get_access_account(wallet)
                if binding and str(binding.get("status") or "").strip().lower() == "revoked": excluded.append({"wallet_address": wallet, "reason": "wallet_binding_revoked"}); continue
                if account and str(account.get("status") or "").strip().lower() in {"suspended", "revoked"}: excluded.append({"wallet_address": wallet, "reason": f"access_account_{str(account.get('status')).strip().lower()}"}); continue
                if not collaborators.find_allowlist_entry("rewards", wallet, account):
                    eligibility = evaluate_review_eligibility(config, wallet_address=wallet, activity_summary=collaborators.get_activity_summary(wallet), recent_vote_count=collaborators.count_votes_since(wallet, current_day_window()))
                    if not eligibility.eligible: excluded.append({"wallet_address": wallet, "reason": "review_eligibility_required"}); continue
            eligible.append(vote)
        return eligible, excluded

    def build_submission_voter_reward_plan(self, state, submission_id, collaborators, *, now=None):
        decision = self.get_submission_reward_decision(submission_id, collaborators, now=now)
        if decision is None: return self._empty_plan(submission_id, "decision_not_reward_eligible", VOTER_REWARDS_ENABLED)
        votes, excluded = self.eligible_voter_reward_wallets(state, decision, collaborators)
        enabled = self.config_value(state, "voter_rewards_enabled", VOTER_REWARDS_ENABLED)
        pool_per_decision = self.config_value(state, "voter_reward_pool_per_decision_zoid", VOTER_REWARD_POOL_PER_DECISION_ZOID)
        max_per_wallet = self.config_value(state, "voter_reward_max_per_wallet_zoid", VOTER_REWARD_MAX_PER_WALLET_ZOID)
        if not enabled: return {**decision, **self._empty_plan(submission_id, "voter_rewards_disabled", False), "excluded_voters": excluded}
        if not votes:
            result = {**decision, **self._empty_plan(submission_id, "no_eligible_majority_voters", True), "excluded_voters": excluded}; result["undistributed_remainder"] = self.normalize_reward_amount(self.reward_units_from_amount_string(pool_per_decision)); return result
        total = self.reward_units_from_amount_string(pool_per_decision)
        if total <= 0: return {**decision, **self._empty_plan(submission_id, "reward_pool_zero", True), "excluded_voters": excluded}
        per_wallet = total // len(votes); maximum = self.reward_units_from_amount_string(max_per_wallet)
        if maximum > 0: per_wallet = min(per_wallet, maximum)
        if per_wallet <= 0:
            result = {**decision, **self._empty_plan(submission_id, "reward_amount_rounds_to_zero", True), "excluded_voters": excluded}; result["undistributed_remainder"] = self.normalize_reward_amount(total); return result
        amount, records = self.normalize_reward_amount(per_wallet), []
        for vote in votes:
            wallet = collaborators.normalize_wallet(vote.get("voter_wallet_address") or vote.get("voter"))
            if wallet: records.append({"reward_id": self.reward_id(submission_id, wallet, decision["final_decision"]), "reward_type": "voter_majority_reward", "reward_recipient": wallet, "voter_wallet_address": wallet, "reward_amount": amount, "reward_source": "reward_pool", "reward_status": "pending", "submission_id": submission_id, "certificate_id": decision.get("certificate_id"), "content_hash": decision.get("content_hash"), "vote_choice": decision["vote_choice"], "final_decision": decision["final_decision"], "decision_reason": decision["decision_reason"], "decision_finalized_at": decision["decision_finalized_at"], "created_at": decision["decision_finalized_at"], "network_name": "zoidberg-testnet"})
        distributed = per_wallet * len(records)
        return {**decision, "rewards_enabled": True, "eligible": True, "reason": "reward_plan_ready", "reward_records": records, "excluded_voters": excluded, "reward_count": len(records), "reward_amount_per_voter": amount, "total_distributed": self.normalize_reward_amount(distributed), "undistributed_remainder": self.normalize_reward_amount(total - distributed)}

    @staticmethod
    def _empty_plan(submission_id, reason, enabled): return {"submission_id": submission_id, "rewards_enabled": enabled, "eligible": False, "reason": reason, "reward_records": [], "excluded_voters": [], "reward_count": 0, "reward_amount_per_voter": "0", "total_distributed": "0", "undistributed_remainder": "0"}

    def due_voter_reward_records(self, state, collaborators):
        settled, due = self.settled_voter_reward_ids(state), []
        for submission in state.submissions:
            plan = self.build_submission_voter_reward_plan(state, submission.submission_id, collaborators)
            if plan.get("eligible"): due.extend(record for record in plan["reward_records"] if record["reward_id"] not in settled)
        due.sort(key=lambda record: (record.get("decision_finalized_at") or 0, record.get("submission_id") or "", record.get("reward_recipient") or "")); return due

    def select_voter_reward_records_for_block(self, state, collaborators, *, prioritized_submission_id=None, reward_pool_balance=None):
        selected, skipped = [], []; available = state.reward_pool if reward_pool_balance is None else reward_pool_balance; remaining = self.reward_units_from_decimal(Decimal(str(available))) - self.reward_units_from_decimal(Decimal(str(MEME_BLOCK_REWARD)))
        due = self.due_voter_reward_records(state, collaborators)
        if remaining <= 0: return {"selected": [], "skipped": due}
        ids = set()
        if prioritized_submission_id:
            plan = self.build_submission_voter_reward_plan(state, prioritized_submission_id, collaborators); prioritized = [] if not plan.get("eligible") or plan.get("final_decision") != VOTER_REWARD_APPROVAL_SIDE else [record for record in plan["reward_records"] if record.get("reward_id") not in self.settled_voter_reward_ids(state)]
            units = sum(self.reward_units_from_amount_string(record["reward_amount"], allow_zero=False) for record in prioritized)
            if units > remaining: raise ValueError("Insufficient reward pool to finalize approved-original voter rewards in the mint block.")
            selected.extend(prioritized); ids.update(record["reward_id"] for record in prioritized); remaining -= units
        grouped = {}
        for record in due:
            if record.get("reward_id") not in ids: grouped.setdefault(str(record.get("submission_id") or ""), []).append(record)
        for submission_id in sorted(grouped):
            group = grouped[submission_id]; units = sum(self.reward_units_from_amount_string(record["reward_amount"], allow_zero=False) for record in group)
            if units > remaining: skipped.extend(group)
            else: selected.extend(group); remaining -= units
        return {"selected": selected, "skipped": skipped}

    def get_submission_voter_reward_summary(self, state, submission_id, collaborators, *, now=None):
        plan = self.build_submission_voter_reward_plan(state, submission_id, collaborators, now=now); settled = [record for record in self.all_reward_records(state, collaborators) if record.get("reward_type") == "voter_majority_reward" and record.get("submission_id") == submission_id]; ids = {record.get("reward_id") for record in settled}; pending = [record for record in plan.get("reward_records", []) if record.get("reward_id") not in ids]
        amount = settled[0].get("reward_amount", plan.get("reward_amount_per_voter", "0")) if settled else plan.get("reward_amount_per_voter", "0")
        total = self.normalize_reward_amount(sum(self.reward_units_from_amount_string(record.get("reward_amount") or "0") for record in settled))
        return {"submission_id": submission_id, "voter_rewards_enabled": self.config_value(state, "voter_rewards_enabled", VOTER_REWARDS_ENABLED), "eligible": bool(plan.get("eligible")), "reason": plan.get("reason"), "excluded_voters": plan.get("excluded_voters", []), "final_majority_side": plan.get("final_decision"), "decision_reason": plan.get("decision_reason"), "reward_status": "finalized" if settled and not pending else ("pending" if pending else "none"), "reward_amount_per_voter": amount, "rewarded_voter_count": len(settled), "pending_voter_count": len(pending), "total_distributed": total, "undistributed_remainder": plan.get("undistributed_remainder", "0"), "review_eligibility_required": self.config_value(state, "voter_reward_require_review_eligible", VOTER_REWARD_REQUIRE_REVIEW_ELIGIBLE), "reward_records": settled, "pending_reward_records": pending}

    def get_reward_records_for_wallet(self, state, wallet_address, collaborators):
        wallet = collaborators.normalize_wallet(wallet_address)
        return [] if wallet is None else [record for record in self.all_reward_records(state, collaborators) if collaborators.normalize_wallet(record.get("reward_recipient") or record.get("voter_wallet_address")) == wallet]

    def recompute_reward_pool_balance(self, state, collaborators, *, chain=None):
        pool = initial = float(self.config_value(state, "reward_pool_supply", REWARD_POOL_SUPPLY))
        for block in (chain if chain is not None else state.chain):
            transactions = block.get("transactions", []) if isinstance(block, dict) else block.transactions
            for transaction in transactions:
                sender_value = transaction.get("sender") if isinstance(transaction, dict) else transaction.sender; amount = transaction.get("amount") if isinstance(transaction, dict) else transaction.amount; tip = transaction.get("tip", 0) if isinstance(transaction, dict) else transaction.tip; sender = collaborators.normalize_wallet(sender_value) or sender_value
                if sender not in {None, "", "GENESIS", "REWARD_POOL"} and float(tip or 0) > 0: pool += float(tip) * (0.75 if pool < initial * 0.25 else 0.5)
                if sender_value == "REWARD_POOL": pool -= float(amount or 0)
        return pool
