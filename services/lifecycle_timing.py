"""Bounded, non-consensus lifecycle timing for Public Testnet v1 diagnostics."""

from threading import Lock
from time import monotonic_ns, time_ns


class LifecycleTimingRecorder:
    """Thread-safe lifecycle marks; timing data is never consensus state."""

    STAGES = ("vote_passed", "certificate_created", "ready_for_mint", "proposal_prepared", "accepted", "finalized")

    def __init__(self):
        self._lock = Lock()
        self._records = {}

    def mark(self, submission_id, stage, *, certificate_id=None, block_height=None, block_hash=None):
        if stage not in self.STAGES:
            raise ValueError(f"Unknown lifecycle timing stage: {stage}")
        key = str(submission_id)
        with self._lock:
            record = self._records.setdefault(key, {"submission_id": key, "stages": {}, "wall_clock_ns": time_ns()})
            record["stages"].setdefault(stage, monotonic_ns())
            if certificate_id:
                record["certificate_id"] = str(certificate_id)
            if block_height is not None:
                record["block_height"] = int(block_height)
            if block_hash:
                record["block_hash"] = str(block_hash)

    def snapshot(self):
        with self._lock:
            return {key: {**record, "stages": dict(record["stages"])} for key, record in self._records.items()}

    def completed_records(self):
        return [record for record in self.snapshot().values() if all(stage in record["stages"] for stage in self.STAGES)]
