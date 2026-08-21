from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ops_support import (  # noqa: E402
    safe_backup_status,
    safe_environment_validation,
    safe_integrity_status,
    sqlite_integrity_status,
    verify_backup_status,
)
from storage import create_storage_backend  # noqa: E402


def _print_json(payload) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safe testnet operations diagnostics for ZoidbergChain.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("backup-status", help="Show current backup directory status.")
    subparsers.add_parser("verify-backup", help="Check whether the latest backup exists and is readable.")
    subparsers.add_parser("sqlite-integrity-check", help="Run PRAGMA quick_check for SQLite backends.")
    subparsers.add_parser("env-validate", help="Run safe environment validation checks.")
    subparsers.add_parser("storage-integrity", help="Run the storage integrity summary.")
    return parser


def run_cli(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    backend = create_storage_backend()

    if args.command == "backup-status":
        _print_json({"backup_status": safe_backup_status(backend)})
        return 0
    if args.command == "verify-backup":
        result = verify_backup_status(backend)
        _print_json({"verify_backup": result})
        return 0 if result.get("verified") else 1
    if args.command == "sqlite-integrity-check":
        result = sqlite_integrity_status(backend)
        _print_json({"sqlite_integrity": result})
        return 0 if result.get("healthy") else 1
    if args.command == "env-validate":
        result = safe_environment_validation()
        _print_json({"environment_validation": result})
        return 0 if result.get("healthy") else 1
    if args.command == "storage-integrity":
        result = safe_integrity_status(backend)
        _print_json({"storage_integrity": result})
        return 0 if result.get("healthy") else 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(run_cli())
