"""Reproducible advisory-collusion corpus for Milestone 5 Task 5.8."""

from __future__ import annotations

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.collusion_analytics_service import CollusionAnalyticsService
from scripts.task_5_3_adversarial_corpus import build_report as originality_report


def _scenario(name, *, coordinated, funded=False, fresh=False, one_off=False):
    creator = "0xcreator"
    reviewers = ["0xa", "0xb", "0xc"]
    count = 1 if one_off else 6
    submissions = [{
        "submission_id": f"{name}-{number}",
        "creator_wallet_address": creator if coordinated else f"0xindependent-{number % 3}",
    } for number in range(count)]
    votes = []
    for number, submission in enumerate(submissions):
        for position, reviewer in enumerate(reviewers):
            choice = "original" if coordinated else ("original" if (number + position) % 3 == 0 else "not_original")
            votes.append({"evidence_id": f"{name}-{reviewer}-{number}", "submission_id": submission["submission_id"], "voter_address": reviewer, "vote_choice": choice, "lifecycle_state": "accepted", "reviewer_status_effective_height": 10 + number // 3, "observed_at": 1000 + number * 100 + position * (5 if coordinated else 900)})
    transactions = [{"tx_id": f"{name}-fund-{reviewer}", "from_address": creator, "to_address": reviewer, "status": "settled"} for reviewer in reviewers] if funded else []
    states = [{"reviewer_address": reviewer, "current_status": "PROBATIONARY_REVIEWER" if fresh else "ESTABLISHED_REVIEWER", "status_effective_height": 10} for reviewer in reviewers]
    report = CollusionAnalyticsService().analyze(votes=votes, submissions=submissions, native_transactions=transactions, reviewer_states=states)
    return {"name": name, "expected_alert": coordinated and not one_off, "reason_codes": [item["reason_code"] for item in report["alerts"]], "alert_count": report["alert_count"]}


def build_report():
    cases = [
        _scenario("fresh_wallet_swarm", coordinated=True, funded=True, fresh=True),
        _scenario("coordinated_cluster", coordinated=True),
        _scenario("creator_funded_cluster", coordinated=True, funded=True),
        _scenario("one_off_legitimate_transfer", coordinated=False, funded=True, one_off=True),
        _scenario("diverse_honest_reviewers", coordinated=False),
    ]
    return {
        "scope": "synthetic advisory patterns; alerts are not proof of collusion",
        "originality": originality_report(),
        "collusion": {
            "true_positive_alerts": sum(case["expected_alert"] and case["alert_count"] > 0 for case in cases),
            "true_negative_cases": sum(not case["expected_alert"] and case["alert_count"] == 0 for case in cases),
            "false_positive_alerts": sum(not case["expected_alert"] and case["alert_count"] > 0 for case in cases),
            "false_negative_cases": sum(case["expected_alert"] and case["alert_count"] == 0 for case in cases),
            "cases": cases,
        },
    }


if __name__ == "__main__":
    print(json.dumps(build_report(), indent=2, sort_keys=True))
