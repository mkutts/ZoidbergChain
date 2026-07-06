from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from storage import JSONStorageBackend, SQLiteStorageBackend


_SECTION_DEFAULTS = {
    "chain": [],
    "wallets": {},
    "submissions": [],
    "mint_queue": [],
    "votes": [],
    "originality_certificates": [],
    "peers": [],
}


class MigrationError(RuntimeError):
    pass


@dataclass
class MigrationSummary:
    source_json_path: str
    source_peers_path: str
    target_sqlite_path: str
    chain_length: int
    wallet_count: int
    submission_count: int
    vote_count: int
    certificate_count: int
    peer_count: int
    mint_queue_count: int
    latest_block_hash: str | None
    backup_path: str | None
    status: str = "success"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source_json_path": self.source_json_path,
            "source_peers_path": self.source_peers_path,
            "target_sqlite_path": self.target_sqlite_path,
            "chain_length": self.chain_length,
            "wallet_count": self.wallet_count,
            "submission_count": self.submission_count,
            "vote_count": self.vote_count,
            "certificate_count": self.certificate_count,
            "peer_count": self.peer_count,
            "mint_queue_count": self.mint_queue_count,
            "latest_block_hash": self.latest_block_hash,
            "backup_path": self.backup_path,
        }


def _default_source_json_path(data_dir: str | Path) -> Path:
    return Path(data_dir) / "blockchain.json"


def _default_source_peers_path(data_dir: str | Path) -> Path:
    return Path(data_dir) / "peers.json"


def _default_target_sqlite_path(data_dir: str | Path) -> Path:
    return Path(data_dir) / "zoidbergchain.db"


def _load_json_file(path: Path, *, required: bool, label: str) -> Any:
    if not path.exists():
        if required:
            raise MigrationError(f"{label} not found: {path}")
        return None

    try:
        with path.open("r", encoding="utf-8") as file_handle:
            return json.load(file_handle)
    except json.JSONDecodeError as exc:
        raise MigrationError(f"Failed to parse {label}: {path}") from exc
    except OSError as exc:
        raise MigrationError(f"Failed to read {label}: {path}") from exc


def _normalize_snapshot(document: dict[str, Any] | None, peers: list[dict[str, Any]]) -> dict[str, Any]:
    document = document if isinstance(document, dict) else {}
    snapshot = {section: document.get(section, _SECTION_DEFAULTS[section]) for section in _SECTION_DEFAULTS}
    snapshot["peers"] = peers
    return snapshot


def _has_persisted_data(snapshot: dict[str, Any]) -> bool:
    return any(bool(snapshot.get(section)) for section in _SECTION_DEFAULTS)


def _section_count(snapshot: dict[str, Any], section: str) -> int:
    value = snapshot.get(section, _SECTION_DEFAULTS[section])
    if isinstance(value, dict):
        return len(value)
    if isinstance(value, list):
        return len(value)
    return 0


def _latest_block_hash(snapshot: dict[str, Any]) -> str | None:
    chain = snapshot.get("chain", [])
    if not chain:
        return None
    if not isinstance(chain, list):
        return None
    last_block = chain[-1]
    if not isinstance(last_block, dict):
        return None
    return last_block.get("hash")


def _load_source_snapshot(source_json_path: Path, source_peers_path: Path) -> dict[str, Any]:
    source_document = _load_json_file(source_json_path, required=True, label="source JSON")
    if not isinstance(source_document, dict):
        raise MigrationError(f"Source JSON must contain an object at top level: {source_json_path}")

    peers_document = _load_json_file(source_peers_path, required=False, label="source peers JSON")
    if peers_document is None:
        peers = []
    elif not isinstance(peers_document, list):
        raise MigrationError(f"Source peers JSON must contain an array: {source_peers_path}")
    else:
        peers = peers_document

    return _normalize_snapshot(source_document, peers)


def _source_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "chain_length": _section_count(snapshot, "chain"),
        "wallet_count": _section_count(snapshot, "wallets"),
        "submission_count": _section_count(snapshot, "submissions"),
        "vote_count": _section_count(snapshot, "votes"),
        "certificate_count": _section_count(snapshot, "originality_certificates"),
        "peer_count": _section_count(snapshot, "peers"),
        "mint_queue_count": _section_count(snapshot, "mint_queue"),
        "latest_block_hash": _latest_block_hash(snapshot),
    }


def _target_has_data(sqlite_db_path: Path) -> bool:
    if not sqlite_db_path.exists():
        return False
    backend = SQLiteStorageBackend(sqlite_db_path=str(sqlite_db_path))
    current_state = backend.load_blockchain_state() or {}
    return _has_persisted_data(current_state)


def _backup_existing_database(sqlite_db_path: Path) -> Path:
    backup_path = sqlite_db_path.with_suffix(sqlite_db_path.suffix + ".bak")
    shutil.copy2(sqlite_db_path, backup_path)
    return backup_path


def _validate_migration(source_snapshot: dict[str, Any], sqlite_db_path: Path) -> None:
    backend = SQLiteStorageBackend(sqlite_db_path=str(sqlite_db_path))
    migrated_snapshot = backend.load_blockchain_state() or {}

    source_summary = _source_summary(source_snapshot)
    migrated_summary = _source_summary(migrated_snapshot)

    for key in (
        "chain_length",
        "wallet_count",
        "submission_count",
        "vote_count",
        "certificate_count",
        "peer_count",
        "mint_queue_count",
    ):
        if source_summary[key] != migrated_summary[key]:
            raise MigrationError(
                f"Migration validation failed for {key}: "
                f"source={source_summary[key]} migrated={migrated_summary[key]}"
            )

    if source_summary["latest_block_hash"] != migrated_summary["latest_block_hash"]:
        raise MigrationError(
            "Migration validation failed for latest_block_hash: "
            f"source={source_summary['latest_block_hash']} migrated={migrated_summary['latest_block_hash']}"
        )


def migrate_json_to_sqlite(
    source_json_path: str | Path,
    sqlite_db_path: str | Path,
    *,
    peers_json_path: str | Path | None = None,
    overwrite: bool = False,
) -> MigrationSummary:
    source_json_path = Path(source_json_path)
    sqlite_db_path = Path(sqlite_db_path)
    source_peers_path = Path(peers_json_path) if peers_json_path is not None else source_json_path.with_name("peers.json")

    source_snapshot = _load_source_snapshot(source_json_path, source_peers_path)
    if sqlite_db_path.exists() and _target_has_data(sqlite_db_path):
        if not overwrite:
            raise MigrationError(
                f"SQLite database already contains data: {sqlite_db_path}. "
                "Use overwrite=True or --overwrite to replace it."
            )
        backup_path = _backup_existing_database(sqlite_db_path)
    else:
        backup_path = None

    try:
        sqlite_db_path.parent.mkdir(parents=True, exist_ok=True)
        target_backend = SQLiteStorageBackend(sqlite_db_path=str(sqlite_db_path))
        target_backend.save_blockchain_state(source_snapshot)
        _validate_migration(source_snapshot, sqlite_db_path)
    except Exception:
        if backup_path and Path(backup_path).exists():
            shutil.copy2(backup_path, sqlite_db_path)
        elif sqlite_db_path.exists() and not backup_path:
            sqlite_db_path.unlink()
        raise

    summary = _source_summary(source_snapshot)
    return MigrationSummary(
        source_json_path=str(source_json_path),
        source_peers_path=str(source_peers_path),
        target_sqlite_path=str(sqlite_db_path),
        chain_length=summary["chain_length"],
        wallet_count=summary["wallet_count"],
        submission_count=summary["submission_count"],
        vote_count=summary["vote_count"],
        certificate_count=summary["certificate_count"],
        peer_count=summary["peer_count"],
        mint_queue_count=summary["mint_queue_count"],
        latest_block_hash=summary["latest_block_hash"],
        backup_path=str(backup_path) if backup_path else None,
    )


def build_migration_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migrate JSON storage into SQLite storage.")
    parser.add_argument("--data-dir", help="Node data directory containing blockchain.json and peers.json.")
    parser.add_argument("--source-json", help="Explicit path to blockchain.json.")
    parser.add_argument("--peers-json", help="Explicit path to peers.json.")
    parser.add_argument("--sqlite-db", help="Explicit path to the SQLite database file.")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing SQLite database that already contains data.")
    return parser


def migrate_from_args(args: argparse.Namespace) -> MigrationSummary:
    if args.data_dir:
        data_dir = Path(args.data_dir)
        source_json_path = Path(args.source_json) if args.source_json else _default_source_json_path(data_dir)
        peers_json_path = Path(args.peers_json) if args.peers_json else _default_source_peers_path(data_dir)
        sqlite_db_path = Path(args.sqlite_db) if args.sqlite_db else _default_target_sqlite_path(data_dir)
    else:
        if not args.source_json or not args.sqlite_db:
            raise MigrationError("Either --data-dir or both --source-json and --sqlite-db must be provided.")
        source_json_path = Path(args.source_json)
        peers_json_path = Path(args.peers_json) if args.peers_json else None
        sqlite_db_path = Path(args.sqlite_db)

    return migrate_json_to_sqlite(
        source_json_path=source_json_path,
        sqlite_db_path=sqlite_db_path,
        peers_json_path=peers_json_path,
        overwrite=bool(args.overwrite),
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_migration_parser()
    args = parser.parse_args(argv)
    try:
        summary = migrate_from_args(args)
    except MigrationError as exc:
        print(f"Migration failed: {exc}")
        return 1

    print(json.dumps(summary.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
