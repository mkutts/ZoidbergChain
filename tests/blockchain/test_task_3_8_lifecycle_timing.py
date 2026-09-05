"""Task 3.8 lifecycle timing instrumentation contract tests."""

from services import LifecycleTimingRecorder


def test_lifecycle_timing_is_monotonic_thread_safe_and_idempotent():
    recorder = LifecycleTimingRecorder()
    recorder.mark("submission-1", "vote_passed")
    recorder.mark("submission-1", "vote_passed")
    recorder.mark("submission-1", "certificate_created", certificate_id="certificate-1")
    record = recorder.snapshot()["submission-1"]
    assert list(record["stages"]) == ["vote_passed", "certificate_created"]
    assert record["stages"]["vote_passed"] <= record["stages"]["certificate_created"]
    assert record["certificate_id"] == "certificate-1"
    assert recorder.completed_records() == []
