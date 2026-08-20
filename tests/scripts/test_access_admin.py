from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


def _parse_last_json(stdout: str):
    lines = [line for line in str(stdout or "").splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if line.lstrip().startswith("{"):
            return json.loads("\n".join(lines[index:]))
    raise ValueError("No JSON payload found in CLI output.")


def _load_modules(monkeypatch, isolated_data_dir, **env):
    keys = {
        "ENVIRONMENT",
        "PUBLIC_API_MODE",
        "PEER_SHARED_SECRET",
        "NODE_DATA_DIR",
    }
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    monkeypatch.setenv("NODE_DATA_DIR", str(isolated_data_dir))

    import config
    import scripts.access_admin as access_admin

    importlib.reload(config)
    importlib.reload(access_admin)
    return config, access_admin


def test_create_invite_cli_creates_usable_access_account(monkeypatch, isolated_data_dir, capsys):
    _, access_admin = _load_modules(
        monkeypatch,
        isolated_data_dir,
        ENVIRONMENT="development",
        PUBLIC_API_MODE="false",
    )

    exit_code = access_admin.run_cli(
        [
            "create-invite",
            "--name",
            "Local Developer",
            "--email",
            "local@example.test",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = _parse_last_json(captured.out)
    assert payload["access_account"]["status"] == "active"
    assert payload["invite_code"].startswith("ZC-")


def test_approve_cli_turns_pending_request_into_invite(monkeypatch, isolated_data_dir, capsys):
    _, access_admin = _load_modules(
        monkeypatch,
        isolated_data_dir,
        ENVIRONMENT="development",
        PUBLIC_API_MODE="false",
    )
    blockchain = access_admin._bootstrap_blockchain()
    request_record = blockchain.create_access_request(
        name="Pending Tester",
        email="pending@example.test",
        reason="Need access",
    )
    blockchain.save_blockchain()

    exit_code = access_admin.run_cli(["approve", request_record["request_id"]])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = _parse_last_json(captured.out)
    assert payload["access_account"]["status"] == "active"
    assert payload["invite_code"].startswith("ZC-")


def test_suspend_and_revoke_wallet_cli_paths(monkeypatch, isolated_data_dir, capsys):
    _, access_admin = _load_modules(
        monkeypatch,
        isolated_data_dir,
        ENVIRONMENT="development",
        PUBLIC_API_MODE="false",
    )
    blockchain = access_admin._bootstrap_blockchain()
    access_account, _invite_code = blockchain.create_access_invite(
        name="Bound Tester",
        email="bound@example.test",
        reviewed_by="test",
    )
    binding = blockchain.bind_wallet_to_access_account(
        access_account["access_account_id"],
        "0x1111111111111111111111111111111111111111",
    )
    blockchain.save_blockchain()

    suspend_code = access_admin.run_cli(["suspend", access_account["access_account_id"]])
    suspend_output = _parse_last_json(capsys.readouterr().out)
    assert suspend_code == 0
    assert suspend_output["access_account"]["status"] == "suspended"

    revoke_code = access_admin.run_cli(["revoke-wallet", binding["wallet_address"]])
    revoke_output = _parse_last_json(capsys.readouterr().out)
    assert revoke_code == 0
    assert revoke_output["wallet_binding"]["status"] == "revoked"


def test_list_accounts_show_account_and_doctor_are_safe(monkeypatch, isolated_data_dir, capsys):
    config, access_admin = _load_modules(
        monkeypatch,
        isolated_data_dir,
        ENVIRONMENT="development",
        PUBLIC_API_MODE="false",
    )
    blockchain = access_admin._bootstrap_blockchain()
    access_account, _invite_code = blockchain.create_access_invite(
        name="Doctor Tester",
        email="doctor@example.test",
        reviewed_by="test",
    )
    blockchain.bind_wallet_to_access_account(
        access_account["access_account_id"],
        "0x1111111111111111111111111111111111111111",
    )
    blockchain.save_blockchain()

    list_code = access_admin.run_cli(["list-accounts"])
    list_output = _parse_last_json(capsys.readouterr().out)
    assert list_code == 0
    assert list_output["accounts"][0]["wallet_count"] == 1
    assert "invite_code_hash" not in str(list_output)

    show_code = access_admin.run_cli(["show-account", access_account["access_account_id"]])
    show_output = _parse_last_json(capsys.readouterr().out)
    assert show_code == 0
    assert show_output["access_account"]["invite_redeemed"] is True

    doctor_code = access_admin.run_cli(["doctor"])
    doctor_output = _parse_last_json(capsys.readouterr().out)
    assert doctor_code == 0
    assert doctor_output["doctor"]["storage_backend"] == config.STORAGE_BACKEND
    assert doctor_output["doctor"]["access_sessions_backend"] == "memory_only_process_local"


def test_generate_admin_password_hash_cli_outputs_env_instructions(monkeypatch, isolated_data_dir, capsys):
    _, access_admin = _load_modules(
        monkeypatch,
        isolated_data_dir,
        ENVIRONMENT="development",
        PUBLIC_API_MODE="false",
    )

    exit_code = access_admin.run_cli(
        [
            "generate-admin-password-hash",
            "--password",
            "super-secret-admin",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = _parse_last_json(captured.out)
    assert payload["admin_password_hash"].startswith("pbkdf2_sha256$")
    assert any("ADMIN_PASSWORD_HASH=" in line for line in payload["instructions"])


def test_script_and_module_invocation_work(monkeypatch, isolated_data_dir):
    _load_modules(
        monkeypatch,
        isolated_data_dir,
        ENVIRONMENT="development",
        PUBLIC_API_MODE="false",
    )
    env = {
        **dict(os.environ),
        "ENVIRONMENT": "development",
        "PUBLIC_API_MODE": "false",
        "NODE_DATA_DIR": str(isolated_data_dir),
    }
    repo_root = Path(__file__).resolve().parents[2]

    direct = subprocess.run(
        [sys.executable, "scripts/access_admin.py", "doctor"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert direct.returncode == 0
    assert _parse_last_json(direct.stdout)["doctor"]["environment"] == "development"

    module = subprocess.run(
        [sys.executable, "-m", "scripts.access_admin", "doctor"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert module.returncode == 0
    assert _parse_last_json(module.stdout)["doctor"]["environment"] == "development"
