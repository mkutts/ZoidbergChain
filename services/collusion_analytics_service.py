"""Read-only, advisory collusion pattern projections for Milestone 5.

This module deliberately consumes historical records and returns findings only.
It never imports consensus services or mutates storage, reviewer state, votes,
certificates, or reputation records.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from itertools import combinations
from typing import Any, Iterable


ANALYSIS_VERSION = 1
ALERT_VERSION = 1
NON_CONSENSUS_NOTE = "Advisory analytics only; this result has no consensus or reputation effect."

HIGH_COVOTING_CORRELATION = "HIGH_COVOTING_CORRELATION"
RECURRING_REVIEWER_CLUSTER = "RECURRING_REVIEWER_CLUSTER"
CREATOR_REVIEWER_RECURRENCE = "CREATOR_REVIEWER_RECURRENCE"
CREATOR_FUNDED_REVIEWERS = "CREATOR_FUNDED_REVIEWERS"
FRESH_WALLET_COORDINATION = "FRESH_WALLET_COORDINATION"
SYNCHRONIZED_VOTING_PATTERN = "SYNCHRONIZED_VOTING_PATTERN"
REPEATED_SAME_CREATOR_SUPPORT = "REPEATED_SAME_CREATOR_SUPPORT"

REASON_CODES = frozenset({
    HIGH_COVOTING_CORRELATION, RECURRING_REVIEWER_CLUSTER,
    CREATOR_REVIEWER_RECURRENCE, CREATOR_FUNDED_REVIEWERS,
    FRESH_WALLET_COORDINATION, SYNCHRONIZED_VOTING_PATTERN,
    REPEATED_SAME_CREATOR_SUPPORT,
})
SEVERITIES = ("INFO", "LOW", "MEDIUM", "HIGH")


def _value(record: Any, name: str, default: Any = None) -> Any:
    return record.get(name, default) if isinstance(record, dict) else getattr(record, name, default)


def _address(value: Any) -> str:
    return str(value or "").strip().lower()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _epoch(vote: dict[str, Any]) -> int:
    """Use the persisted status reference as a stable review epoch proxy."""
    value = vote.get("reviewer_status_effective_height")
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0


def _time(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


class CollusionAnalyticsService:
    """Deterministic, transparent analysis over network-visible stored records."""

    minimum_shared_reviews = 3
    minimum_epochs = 2
    minimum_agreement_numerator = 4  # >= 4/5 agreement, calculated with integers
    agreement_denominator = 5
    fresh_height_window = 8
    synchronized_seconds = 300

    def _alert(self, *, reason_code: str, severity: str, reviewers=(), creators=(),
               submissions=(), epochs=(), reference_height=None, reference_block_hash=None,
               metrics: dict[str, Any] | None = None, summary: str = "") -> dict[str, Any]:
        if reason_code not in REASON_CODES or severity not in SEVERITIES:
            raise ValueError("Unknown advisory collusion alert classification.")
        identity = {
            "alert_version": ALERT_VERSION, "analysis_version": ANALYSIS_VERSION,
            "reason_code": reason_code, "reviewer_addresses": sorted(set(reviewers)),
            "creator_addresses": sorted(set(creators)), "submission_ids": sorted(set(submissions)),
            "review_epochs": sorted(set(int(epoch) for epoch in epochs)),
            "reference_height": reference_height, "reference_block_hash": reference_block_hash,
            "evidence_metrics": metrics or {},
        }
        alert_id = "collusion:" + hashlib.sha256(_canonical(identity).encode("utf-8")).hexdigest()
        return {
            "alert_id": alert_id, "alert_version": ALERT_VERSION, "reason_code": reason_code,
            "severity": severity, "reviewer_addresses": identity["reviewer_addresses"],
            "creator_addresses": identity["creator_addresses"], "submission_ids": identity["submission_ids"],
            "review_epochs": identity["review_epochs"], "reference_height": reference_height,
            "reference_block_hash": reference_block_hash, "evidence_summary": summary,
            "evidence_metrics": identity["evidence_metrics"],
            "first_observed_epoch": min(identity["review_epochs"], default=None),
            "last_observed_epoch": max(identity["review_epochs"], default=None),
            "analysis_version": ANALYSIS_VERSION, "non_consensus": True,
        }

    @staticmethod
    def _severity(*, count: int, epochs: int, corroborating: int = 0) -> str:
        if count >= 6 and epochs >= 3 and corroborating >= 1:
            return "HIGH"
        if count >= 4 and epochs >= 2:
            return "MEDIUM"
        return "LOW"

    def analyze(self, *, votes: Iterable[Any], submissions: Iterable[Any],
                native_transactions: Iterable[Any] = (), reviewer_states: Iterable[Any] = (),
                reference_height: int | None = None, reference_block_hash: str | None = None) -> dict[str, Any]:
        """Return a stable alert projection. Input ordering never changes output."""
        submission_creators = {
            str(_value(item, "submission_id") or "").strip(): _address(
                _value(item, "creator_wallet_address") or _value(item, "submitter")
            ) for item in submissions
        }
        accepted = []
        for item in votes:
            vote = dict(item) if isinstance(item, dict) else dict(vars(item))
            if str(vote.get("lifecycle_state") or "accepted") != "accepted":
                continue
            reviewer = _address(vote.get("voter_address") or vote.get("voter"))
            submission_id = str(vote.get("submission_id") or "").strip()
            choice = str(vote.get("vote_choice") or vote.get("vote_type") or "").strip().lower()
            if reviewer and submission_id and choice:
                vote.update(reviewer=reviewer, submission_id=submission_id, choice=choice, epoch=_epoch(vote))
                accepted.append(vote)
        accepted.sort(key=lambda row: (row["submission_id"], row["reviewer"], str(row.get("observed_at") or ""), str(row.get("evidence_id") or "")))

        by_submission: dict[str, list[dict[str, Any]]] = defaultdict(list)
        by_reviewer: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for vote in accepted:
            by_submission[vote["submission_id"]].append(vote)
            by_reviewer[vote["reviewer"]].append(vote)

        alerts: list[dict[str, Any]] = []
        pair_rows: dict[tuple[str, str], list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
        for rows in by_submission.values():
            for left, right in combinations(rows, 2):
                if left["reviewer"] != right["reviewer"]:
                    pair_rows[tuple(sorted((left["reviewer"], right["reviewer"])))].append((left, right))

        correlated_pairs: list[tuple[str, str]] = []
        for pair, rows in sorted(pair_rows.items()):
            shared = len(rows)
            agreements = sum(left["choice"] == right["choice"] for left, right in rows)
            epochs = {left["epoch"] for left, _ in rows} | {right["epoch"] for _, right in rows}
            if shared < self.minimum_shared_reviews or len(epochs) < self.minimum_epochs:
                continue
            if agreements * self.agreement_denominator < shared * self.minimum_agreement_numerator:
                continue
            submissions_seen = [left["submission_id"] for left, _ in rows]
            creators = [submission_creators.get(item, "") for item in submissions_seen]
            correlated_pairs.append(pair)
            alerts.append(self._alert(
                reason_code=HIGH_COVOTING_CORRELATION,
                severity=self._severity(count=shared, epochs=len(epochs)), reviewers=pair,
                creators=[item for item in creators if item], submissions=submissions_seen, epochs=epochs,
                reference_height=reference_height, reference_block_hash=reference_block_hash,
                metrics={"shared_review_count": shared, "agreement_count": agreements,
                         "disagreement_count": shared - agreements,
                         "agreement_ratio": [agreements, shared], "epoch_count": len(epochs),
                         "creator_concentration": dict(sorted(Counter(creators).items()))},
                summary="Repeated correlated reviewer voting pattern detected; not proof of collusion.",
            ))

        # Connected components of strong pairs are transparent recurring clusters.
        adjacency: dict[str, set[str]] = defaultdict(set)
        for left, right in correlated_pairs:
            adjacency[left].add(right); adjacency[right].add(left)
        seen: set[str] = set()
        for reviewer in sorted(adjacency):
            if reviewer in seen:
                continue
            stack, component = [reviewer], set()
            while stack:
                current = stack.pop()
                if current in component:
                    continue
                component.add(current); stack.extend(adjacency[current] - component)
            seen.update(component)
            if len(component) < 3:
                continue
            component_votes = [vote for vote in accepted if vote["reviewer"] in component]
            epochs = {vote["epoch"] for vote in component_votes}
            submissions_seen = {vote["submission_id"] for vote in component_votes}
            alerts.append(self._alert(
                reason_code=RECURRING_REVIEWER_CLUSTER, severity=self._severity(count=len(submissions_seen), epochs=len(epochs), corroborating=1),
                reviewers=component, creators=[submission_creators.get(item, "") for item in submissions_seen], submissions=submissions_seen, epochs=epochs,
                reference_height=reference_height, reference_block_hash=reference_block_hash,
                metrics={"reviewer_count": len(component), "strong_pair_count": sum(1 for pair in correlated_pairs if set(pair) <= component),
                         "submission_count": len(submissions_seen), "epoch_count": len(epochs)},
                summary="Recurring reviewer cluster pattern detected; not proof of collusion.",
            ))

        creator_reviewer_votes: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for vote in accepted:
            creator = submission_creators.get(vote["submission_id"], "")
            if creator:
                creator_reviewer_votes[(creator, vote["reviewer"])].append(vote)
        for (creator, reviewer), rows in sorted(creator_reviewer_votes.items()):
            epochs = {row["epoch"] for row in rows}
            reviewer_total = len(by_reviewer[reviewer])
            support_count = sum(row["choice"] == "original" for row in rows)
            if len(rows) >= 3 and len(epochs) >= 2 and len(rows) * 100 >= reviewer_total * 60:
                common = dict(review_count=len(rows), reviewer_total=reviewer_total, reviewer_creator_percent=[len(rows), reviewer_total], epoch_count=len(epochs))
                alerts.append(self._alert(reason_code=CREATOR_REVIEWER_RECURRENCE, severity=self._severity(count=len(rows), epochs=len(epochs)), reviewers=[reviewer], creators=[creator], submissions=[row["submission_id"] for row in rows], epochs=epochs, reference_height=reference_height, reference_block_hash=reference_block_hash, metrics=common, summary="Recurring creator-reviewer concentration detected; not proof of collusion."))
                if support_count >= 3:
                    alerts.append(self._alert(reason_code=REPEATED_SAME_CREATOR_SUPPORT, severity=self._severity(count=support_count, epochs=len(epochs)), reviewers=[reviewer], creators=[creator], submissions=[row["submission_id"] for row in rows if row["choice"] == "original"], epochs=epochs, reference_height=reference_height, reference_block_hash=reference_block_hash, metrics={**common, "support_count": support_count}, summary="Repeated same-creator support pattern detected; not proof of collusion."))

        transfers = []
        for transaction in native_transactions:
            sender = _address(_value(transaction, "from_address") or _value(transaction, "sender"))
            recipient = _address(_value(transaction, "to_address") or _value(transaction, "recipient"))
            state = str(_value(transaction, "lifecycle_state") or _value(transaction, "status") or "").lower()
            if sender and recipient and state in {"included", "settled", "finalized"}:
                transfers.append((sender, recipient, str(_value(transaction, "tx_id") or "")))
        for creator in sorted(set(submission_creators.values()) - {""}):
            funded = {recipient for sender, recipient, _ in transfers if sender == creator}
            linked = [reviewer for reviewer in sorted(funded) if len(creator_reviewer_votes.get((creator, reviewer), [])) >= 2]
            if linked:
                rows = [vote for reviewer in linked for vote in creator_reviewer_votes[(creator, reviewer)]]
                alerts.append(self._alert(reason_code=CREATOR_FUNDED_REVIEWERS, severity=self._severity(count=len(rows), epochs=len({row['epoch'] for row in rows}), corroborating=1), reviewers=linked, creators=[creator], submissions=[row["submission_id"] for row in rows], epochs=[row["epoch"] for row in rows], reference_height=reference_height, reference_block_hash=reference_block_hash, metrics={"funded_reviewer_count": len(linked), "linked_review_count": len(rows), "funding_transfer_count": sum(1 for sender, recipient, _ in transfers if sender == creator and recipient in linked)}, summary="Creator funding and recurring review relationship detected; not proof of collusion."))

        state_by_reviewer = {_address(_value(state, "reviewer_address")): state for state in reviewer_states}
        fresh = set()
        for reviewer, rows in by_reviewer.items():
            state = state_by_reviewer.get(reviewer, {})
            status = str(_value(state, "current_status") or "")
            effective = _value(state, "status_effective_height")
            first_epoch = min(row["epoch"] for row in rows)
            if status == "PROBATIONARY_REVIEWER" or (effective is not None and int(effective) >= first_epoch - self.fresh_height_window):
                fresh.add(reviewer)
        for pair in correlated_pairs:
            if not set(pair) <= fresh:
                continue
            rows = [row for row in accepted if row["reviewer"] in pair]
            shared_creators = Counter(submission_creators.get(row["submission_id"], "") for row in rows)
            concentrated = [creator for creator, count in shared_creators.items() if creator and count >= 3]
            if concentrated:
                alerts.append(self._alert(reason_code=FRESH_WALLET_COORDINATION, severity="MEDIUM", reviewers=pair, creators=concentrated, submissions=[row["submission_id"] for row in rows if submission_creators.get(row["submission_id"], "") in concentrated], epochs=[row["epoch"] for row in rows], reference_height=reference_height, reference_block_hash=reference_block_hash, metrics={"fresh_reviewer_count": 2, "coordinated_creator_count": len(concentrated), "coordination_evidence": "correlated co-voting plus creator concentration"}, summary="Fresh-wallet coordination pattern detected; not proof of collusion."))

        for pair, rows in sorted(pair_rows.items()):
            close = []
            for left, right in rows:
                left_time, right_time = _time(left.get("observed_at")), _time(right.get("observed_at"))
                if left_time is not None and right_time is not None and abs(left_time - right_time) <= self.synchronized_seconds and left["choice"] == right["choice"]:
                    close.append((left, right))
            epochs = {left["epoch"] for left, _ in close} | {right["epoch"] for _, right in close}
            if len(close) >= 3 and len(epochs) >= 2:
                alerts.append(self._alert(reason_code=SYNCHRONIZED_VOTING_PATTERN, severity=self._severity(count=len(close), epochs=len(epochs)), reviewers=pair, creators=[submission_creators.get(left["submission_id"], "") for left, _ in close], submissions=[left["submission_id"] for left, _ in close], epochs=epochs, reference_height=reference_height, reference_block_hash=reference_block_hash, metrics={"synchronized_vote_count": len(close), "maximum_relative_seconds": self.synchronized_seconds, "timing_source": "durably observed_at (analytics-only)"}, summary="Synchronized voting pattern detected; timing is advisory and not consensus data."))

        alerts.sort(key=lambda item: (item["reason_code"], item["alert_id"]))
        return {"analysis_version": ANALYSIS_VERSION, "non_consensus": True, "note": NON_CONSENSUS_NOTE, "alert_count": len(alerts), "alerts": alerts}

    def analyze_storage(self, storage: Any, *, chain: Iterable[Any] = (), finalized_head: dict[str, Any] | None = None) -> dict[str, Any]:
        votes = storage.list_durable_votes() if hasattr(storage, "list_durable_votes") else storage.load_votes()
        transactions = storage.list_durable_native_transaction_records() if hasattr(storage, "list_durable_native_transaction_records") else []
        states = storage.list_reviewer_states() if hasattr(storage, "list_reviewer_states") else []
        submissions = storage.load_submissions()
        head = finalized_head or {}
        return self.analyze(votes=votes, submissions=submissions, native_transactions=transactions, reviewer_states=states,
                            reference_height=head.get("block_height"), reference_block_hash=head.get("block_hash"))
