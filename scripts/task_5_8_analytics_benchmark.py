"""Small deterministic scaling check for advisory collusion analytics."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.collusion_analytics_service import CollusionAnalyticsService


def build_dataset(reviewers=200, votes=3000):
    creator_count = 30
    submissions = [{"submission_id": f"s{number}", "creator_wallet_address": f"0xc{number % creator_count}"} for number in range(votes // 15)]
    records = []
    for number in range(votes):
        reviewer = f"0xr{number % reviewers}"
        submission = submissions[(number // 15) % len(submissions)]
        records.append({"evidence_id": f"v{number}", "submission_id": submission["submission_id"], "voter_address": reviewer, "vote_choice": "original" if number % 5 else "not_original", "lifecycle_state": "accepted", "reviewer_status_effective_height": 10 + (number // 1000), "observed_at": 1_000_000 + number})
    states = [{"reviewer_address": f"0xr{number}", "current_status": "ESTABLISHED_REVIEWER", "status_effective_height": 0} for number in range(reviewers)]
    return records, submissions, states


def main():
    votes, submissions, states = build_dataset()
    started = time.perf_counter()
    report = CollusionAnalyticsService().analyze(votes=votes, submissions=submissions, reviewer_states=states)
    print(json.dumps({"reviewers": 200, "votes": 3000, "submissions": len(submissions), "runtime_seconds": round(time.perf_counter() - started, 4), "alert_count": report["alert_count"], "complexity_note": "pair generation is O(sum(reviewers-per-submission squared))"}, sort_keys=True))


if __name__ == "__main__":
    main()
