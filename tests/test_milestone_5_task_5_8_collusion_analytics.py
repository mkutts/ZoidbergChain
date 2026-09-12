from copy import deepcopy

from services.collusion_analytics_service import (
    CollusionAnalyticsService, CREATOR_FUNDED_REVIEWERS, FRESH_WALLET_COORDINATION,
    HIGH_COVOTING_CORRELATION, REASON_CODES, SYNCHRONIZED_VOTING_PATTERN,
)
from scripts.task_5_8_adversarial_corpus import build_report as build_corpus_report


def _data(*, coordinated=True, funded=True, fresh=True):
    creator = "0xcreator"
    reviewers = ["0xr1", "0xr2", "0xr3"]
    submissions = [{"submission_id": f"s{number}", "creator_wallet_address": creator} for number in range(6)]
    votes = []
    for number, submission in enumerate(submissions):
        for reviewer in reviewers:
            votes.append({"evidence_id": f"{reviewer}-{number}", "submission_id": submission["submission_id"], "voter_address": reviewer, "vote_choice": "original" if coordinated else ("original" if reviewer == "0xr1" else "not_original"), "lifecycle_state": "accepted", "reviewer_status_effective_height": 10 + number // 3, "observed_at": 1000 + number * 100 + (0 if reviewer == "0xr1" else 10)})
    states = [{"reviewer_address": reviewer, "current_status": "PROBATIONARY_REVIEWER" if fresh else "ESTABLISHED_REVIEWER", "status_effective_height": 10} for reviewer in reviewers]
    transactions = [{"tx_id": f"fund-{reviewer}", "from_address": creator, "to_address": reviewer, "status": "settled"} for reviewer in reviewers] if funded else []
    return votes, submissions, transactions, states


def test_recomputed_alerts_are_stable_and_use_machine_reason_codes():
    service = CollusionAnalyticsService()
    data = _data()
    first = service.analyze(votes=data[0], submissions=data[1], native_transactions=data[2], reviewer_states=data[3], reference_height=20, reference_block_hash="a" * 64)
    second = service.analyze(votes=list(reversed(data[0])), submissions=data[1], native_transactions=data[2], reviewer_states=data[3], reference_height=20, reference_block_hash="a" * 64)
    assert first == second
    assert {alert["reason_code"] for alert in first["alerts"]} <= REASON_CODES
    assert HIGH_COVOTING_CORRELATION in {alert["reason_code"] for alert in first["alerts"]}
    assert CREATOR_FUNDED_REVIEWERS in {alert["reason_code"] for alert in first["alerts"]}
    assert FRESH_WALLET_COORDINATION in {alert["reason_code"] for alert in first["alerts"]}
    assert all(alert["non_consensus"] is True and alert["alert_id"].startswith("collusion:") for alert in first["alerts"])


def test_one_off_and_fresh_wallets_alone_are_not_collusion_alerts():
    service = CollusionAnalyticsService()
    votes, submissions, _, states = _data()
    report = service.analyze(votes=votes[:2], submissions=submissions[:1], reviewer_states=states)
    assert report["alerts"] == []


def test_disagreement_prevents_high_covoting_and_timestamp_is_not_alert_identity():
    service = CollusionAnalyticsService()
    votes, submissions, transactions, states = _data(coordinated=False)
    for vote in votes:
        number = int(vote["submission_id"][1:])
        if vote["voter_address"] == "0xr2":
            vote["vote_choice"] = "original" if number % 2 else "not_original"
        elif vote["voter_address"] == "0xr3":
            vote["vote_choice"] = "not_original" if number % 2 else "original"
        if vote["voter_address"] != "0xr1":
            vote["observed_at"] += 1000
    report = service.analyze(votes=votes, submissions=submissions, native_transactions=transactions, reviewer_states=states)
    assert HIGH_COVOTING_CORRELATION not in {alert["reason_code"] for alert in report["alerts"]}
    assert SYNCHRONIZED_VOTING_PATTERN not in {alert["reason_code"] for alert in report["alerts"]}
    # Operational timestamps are not part of alert identity when no timing alert is emitted.
    shifted = deepcopy(votes)
    for vote in shifted:
        vote["observed_at"] += 9999
    shifted_report = service.analyze(votes=shifted, submissions=submissions, native_transactions=transactions, reviewer_states=states)
    assert [alert["alert_id"] for alert in report["alerts"]] == [alert["alert_id"] for alert in shifted_report["alerts"]]


def test_alert_analysis_never_mutates_input_or_consensus_state():
    service = CollusionAnalyticsService()
    votes, submissions, transactions, states = _data()
    before = deepcopy((votes, submissions, transactions, states))
    service.analyze(votes=votes, submissions=submissions, native_transactions=transactions, reviewer_states=states)
    assert (votes, submissions, transactions, states) == before


def test_expanded_adversarial_corpus_is_reproducible():
    report = build_corpus_report()
    assert report["originality"]["exact_hard_reject"]["true_positives"] == 3
    assert report["collusion"]["true_positive_alerts"] == 3
    assert report["collusion"]["true_negative_cases"] == 2
    assert report["collusion"]["false_positive_alerts"] == 0
    assert report["collusion"]["false_negative_cases"] == 0
