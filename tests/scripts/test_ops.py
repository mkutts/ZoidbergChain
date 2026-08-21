import json

import config
from scripts import ops as ops_script


def test_backup_status_cli_prints_safe_json(blockchain, monkeypatch, capsys):
    monkeypatch.setattr(config, "ADMIN_BOOTSTRAP_TOKEN", "super-secret-bootstrap")
    monkeypatch.setenv("PEER_SHARED_SECRET", "super-secret-peer")

    exit_code = ops_script.run_cli(["backup-status"])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert exit_code == 0
    assert "backup_status" in payload
    assert "super-secret-bootstrap" not in output
    assert "super-secret-peer" not in output


def test_verify_backup_cli_returns_nonzero_when_no_backup_exists(blockchain, capsys):
    exit_code = ops_script.run_cli(["verify-backup"])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert exit_code == 1
    assert payload["verify_backup"]["verified"] is False
    assert "No backup file found" in payload["verify_backup"]["message"]
