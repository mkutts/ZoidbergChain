"""Small executable-contract coverage for the Task 4.9 benchmark utility."""

from scripts.milestone_4_burst_benchmark import main


def test_small_burst_exercises_durable_admission_peer_recovery_and_content_settlement(tmp_path):
    result = main([
        "--output-dir", str(tmp_path / "task-4.9"), "--transactions", "4",
        "--calibration-transactions", "4", "--peer-transactions", "2",
        "--offline-transactions", "2", "--keep-data",
    ])

    assert len(result["admission_runs"]) == 3
    for run in result["admission_runs"]:
        assert run["attempted"] == run["acknowledged"] == 4
        assert run["rejected"] == run["unexpected_errors"] == 0
        assert run["restart"]["acknowledged_missing_after_restart"] == 0
        assert run["restart"]["incorrect_active_nonce_reservations"] == 0
    assert result["peer_propagation"]["receiver_duplicates"] == 0
    assert result["disconnect_recovery"]["unacknowledged_rows_remaining"] == 0
    assert result["settlement_sample"]["duplicate_settlements"] == 0
