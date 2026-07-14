from __future__ import annotations

import csv
import importlib
import json
import re
from pathlib import Path

import pytest


ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
PRIVATE_KEY_RE = re.compile(r"^[a-f0-9]{64}$")


def _load_modules(monkeypatch, **env):
    keys = {"ENVIRONMENT", "PUBLIC_API_MODE", "PEER_SHARED_SECRET"}
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    import config
    import scripts.dev_generate_metamask_wallets as dev_generate_metamask_wallets

    importlib.reload(config)
    importlib.reload(dev_generate_metamask_wallets)
    return config, dev_generate_metamask_wallets


def test_wallet_generator_refuses_outside_development(monkeypatch):
    _, generator = _load_modules(
        monkeypatch,
        ENVIRONMENT="testnet",
        PUBLIC_API_MODE="true",
        PEER_SHARED_SECRET="testnet-secret",
    )

    with pytest.raises(ValueError, match="ENVIRONMENT=development"):
        generator.generate_wallet_records(1)


def test_wallet_generator_generates_requested_count(monkeypatch):
    _, generator = _load_modules(
        monkeypatch,
        ENVIRONMENT="development",
        PUBLIC_API_MODE="false",
    )

    wallets = generator.generate_wallet_records(5)
    assert len(wallets) == 5


def test_generated_wallets_have_valid_addresses_and_private_keys(monkeypatch):
    _, generator = _load_modules(
        monkeypatch,
        ENVIRONMENT="development",
        PUBLIC_API_MODE="false",
    )

    wallets = generator.generate_wallet_records(5)

    assert all(ADDRESS_RE.match(wallet["address"]) for wallet in wallets)
    assert all(PRIVATE_KEY_RE.match(wallet["private_key"]) for wallet in wallets)


def test_wallet_generator_default_output_path_is_under_ignored_data_dir(monkeypatch):
    _, generator = _load_modules(
        monkeypatch,
        ENVIRONMENT="development",
        PUBLIC_API_MODE="false",
    )

    output_path = generator._default_output_path("json")
    assert output_path.name == "dev_wallets.json"
    assert "data" in output_path.parts


def test_wallet_generator_writes_json_and_warning(monkeypatch, isolated_data_dir):
    _, generator = _load_modules(
        monkeypatch,
        ENVIRONMENT="development",
        PUBLIC_API_MODE="false",
    )
    wallets = generator.generate_wallet_records(3)
    output_path = isolated_data_dir / "wallets.json"

    written_path = generator.write_wallet_export(wallets, output_path=output_path, fmt="json")
    payload = json.loads(written_path.read_text(encoding="utf-8"))

    assert written_path == output_path
    assert payload["warning"] == generator.DEV_ONLY_WARNING
    assert len(payload["wallets"]) == 3


def test_wallet_generator_writes_csv(monkeypatch, isolated_data_dir):
    _, generator = _load_modules(
        monkeypatch,
        ENVIRONMENT="development",
        PUBLIC_API_MODE="false",
    )
    wallets = generator.generate_wallet_records(2)
    output_path = isolated_data_dir / "wallets.csv"

    written_path = generator.write_wallet_export(wallets, output_path=output_path, fmt="csv")
    with written_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert written_path == output_path
    assert len(rows) == 2
    assert rows[0]["label"] == "dev-wallet-1"


def test_wallet_generator_run_cli_prints_warning_and_writes_file(monkeypatch, isolated_data_dir, capsys):
    _, generator = _load_modules(
        monkeypatch,
        ENVIRONMENT="development",
        PUBLIC_API_MODE="false",
    )
    output_path = isolated_data_dir / "cli-wallets.json"

    exit_code = generator.run_cli(["--count", "2", "--output", str(output_path), "--format", "json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert generator.DEV_ONLY_WARNING in captured.out
    assert output_path.exists()


def test_generated_wallets_are_unique(monkeypatch):
    _, generator = _load_modules(
        monkeypatch,
        ENVIRONMENT="development",
        PUBLIC_API_MODE="false",
    )

    wallets = generator.generate_wallet_records(10)
    addresses = {wallet["address"] for wallet in wallets}
    private_keys = {wallet["private_key"] for wallet in wallets}

    assert len(addresses) == 10
    assert len(private_keys) == 10
