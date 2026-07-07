from __future__ import annotations

import argparse
import json
import os
import re
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config
from storage import (
    JSONStorageBackend,
    SQLiteStorageBackend,
    StorageBackend,
    check_storage_integrity,
    create_storage_backend,
)


EXPORT_VERSION = 1
_SECTION_TYPES = {
    "chain": list,
    "wallets": dict,
    "submissions": list,
    "mint_queue": list,
    "votes": list,
    "originality_certificates": list,
    "peers": list,
}
_SENSITIVE_KEYS = {
    "private_key",
    "privateKey",
    "signing_key",
    "seed",
    "seed_phrase",
    "secret",
    "raw_secret",
    "peer_secret",
    "shared_secret",
    "hmac_secret",
    "x_zoid_peer_secret",
}
_SAFE_BACKUP_EXTENSIONS = {
    "json": ".json",
    "sqlite": ".json",
}


def _utc_timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


def _safe_filename_part(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip())
    return text.strip("-") or "unknown"


def _backend_name(backend: StorageBackend) -> str:
    return "sqlite" if isinstance(backend, SQLiteStorageBackend) else "json"


def _default_backup_dir(data_dir: str | Path | None = None) -> Path:
    base_dir = Path(data_dir or config.DATA_DIR)
    return base_dir / "backups"


def _default_output_dir(data_dir: str | Path | None = None) -> Path:
    base_dir = Path(data_dir or config.DATA_DIR)
    return base_dir / "exports"


def _infer_data_dir_from_backend(backend: StorageBackend) -> Path:
    if isinstance(backend, SQLiteStorageBackend):
        return Path(backend.sqlite_db_path).parent
    return Path(backend.blockchain_file).parent


def _default_backend() -> StorageBackend:
    paths = config.build_data_paths(config.DATA_DIR)
    return create_storage_backend(
        name=config.STORAGE_BACKEND,
        blockchain_file=paths["blockchain_file"],
        peers_file=paths["peers_file"],
        sqlite_db_path=config.SQLITE_DB_PATH,
    )


def _load_state(backend: StorageBackend) -> dict[str, Any]:
    blockchain_state = backend.load_blockchain_state() or {}
    if not isinstance(blockchain_state, dict):
        raise ValueError("Storage state must be a dictionary.")

    state = {
        "chain": deepcopy(blockchain_state.get("chain", [])),
        "wallets": deepcopy(blockchain_state.get("wallets", {})),
        "submissions": deepcopy(blockchain_state.get("submissions", [])),
        "mint_queue": deepcopy(blockchain_state.get("mint_queue", [])),
        "votes": deepcopy(blockchain_state.get("votes", [])),
        "originality_certificates": deepcopy(blockchain_state.get("originality_certificates", [])),
        "peers": deepcopy(backend.load_peers() or blockchain_state.get("peers", [])),
    }
    _validate_state_shape(state, label="Storage state")
    return state


def _has_persisted_data(state: dict[str, Any]) -> bool:
    for key in ("chain", "wallets", "submissions", "mint_queue", "votes", "originality_certificates", "peers"):
        value = state.get(key)
        if isinstance(value, dict) and value:
            return True
        if isinstance(value, list) and value:
            return True
    return False


def _chain_height(chain: list[Any]) -> int | None:
    if not chain:
        return None
    last_block = chain[-1]
    if isinstance(last_block, dict):
        return last_block.get("index")
    return getattr(last_block, "index", None)


def _latest_block_hash(chain: list[Any]) -> str | None:
    if not chain:
        return None
    last_block = chain[-1]
    if isinstance(last_block, dict):
        return last_block.get("hash")
    return getattr(last_block, "hash", None)


def _genesis_block_hash(chain: list[Any]) -> str | None:
    if not chain:
        return None
    first_block = chain[0]
    if isinstance(first_block, dict):
        return first_block.get("hash")
    return getattr(first_block, "hash", None)


def _calculate_cumulative_originality_score(chain: list[Any]) -> float | None:
    total = 0.0
    found = False
    for block in chain:
        index = block.get("index") if isinstance(block, dict) else getattr(block, "index", None)
        if index == 0:
            continue
        score = block.get("originality_score") if isinstance(block, dict) else getattr(block, "originality_score", None)
        if score is None:
            continue
        found = True
        total += float(score)
    if not found:
        return None
    return round(total, 8)


def _sanitize_value(value: Any, *, include_private_keys: bool) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, child_value in value.items():
            if key in _SENSITIVE_KEYS and not (include_private_keys and key == "private_key"):
                continue
            sanitized[key] = _sanitize_value(child_value, include_private_keys=include_private_keys)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_value(item, include_private_keys=include_private_keys) for item in value]
    return deepcopy(value)


def _snapshot_contains_private_keys(state: dict[str, Any]) -> bool:
    wallets = state.get("wallets", {})
    if isinstance(wallets, dict):
        for wallet in wallets.values():
            if isinstance(wallet, dict) and wallet.get("private_key"):
                return True
    return False


def _validate_export_snapshot(snapshot: dict[str, Any]) -> None:
    required_keys = {"export_version", "exported_at", "metadata", "state"}
    missing = required_keys.difference(snapshot)
    if missing:
        raise ValueError(f"Export snapshot is missing required keys: {', '.join(sorted(missing))}.")
    if snapshot["export_version"] != EXPORT_VERSION:
        raise ValueError(f"Unsupported export version: {snapshot['export_version']!r}.")
    if not isinstance(snapshot["metadata"], dict):
        raise ValueError("Export snapshot metadata must be an object.")
    if not isinstance(snapshot["state"], dict):
        raise ValueError("Export snapshot state must be an object.")


def _validate_state_shape(state: dict[str, Any], *, label: str) -> None:
    if not isinstance(state, dict):
        raise ValueError(f"{label} must be an object.")
    for section_name, expected_type in _SECTION_TYPES.items():
        if section_name not in state:
            raise ValueError(f"{label} is missing state section: {section_name}.")
        if not isinstance(state[section_name], expected_type):
            raise ValueError(
                f"{label} section {section_name!r} must be a {expected_type.__name__}."
            )


def _validate_import_snapshot(snapshot: dict[str, Any]) -> None:
    _validate_export_snapshot(snapshot)
    _validate_state_shape(snapshot["state"], label="Export snapshot state")


def build_export_snapshot(
    backend: StorageBackend | None = None,
    *,
    include_private_keys: bool = False,
) -> dict[str, Any]:
    backend = backend or _default_backend()
    if include_private_keys and not _private_key_export_allowed():
        raise ValueError(
            "Private key export is only allowed in development when PUBLIC_API_MODE is false and "
            "ALLOW_DEV_WALLET_PRIVATE_KEY_EXPORT=true."
        )

    state = _load_state(backend)
    sanitized_state = _sanitize_value(state, include_private_keys=include_private_keys)
    chain = sanitized_state.get("chain", [])
    metadata = {
        "node_id": config.NODE_ID,
        "network_name": config.NETWORK_NAME,
        "storage_backend": _backend_name(backend),
        "chain_height": _chain_height(chain),
        "latest_block_hash": _latest_block_hash(chain),
        "cumulative_originality_score": _calculate_cumulative_originality_score(chain),
        "contains_private_keys": bool(include_private_keys and _snapshot_contains_private_keys(state)),
    }
    if include_private_keys:
        metadata["warning"] = (
            "This export includes private keys. Do not share it and keep it in a protected location."
        )

    snapshot = {
        "export_version": EXPORT_VERSION,
        "exported_at": _utc_timestamp(),
        "metadata": metadata,
        "state": sanitized_state,
    }
    _validate_export_snapshot(snapshot)
    return snapshot


def _write_json_document(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_state_to_backend(backend: StorageBackend, state: dict[str, Any]) -> None:
    blockchain_state = {
        "chain": deepcopy(state.get("chain", [])),
        "wallets": deepcopy(state.get("wallets", {})),
        "submissions": deepcopy(state.get("submissions", [])),
        "mint_queue": deepcopy(state.get("mint_queue", [])),
        "votes": deepcopy(state.get("votes", [])),
        "originality_certificates": deepcopy(state.get("originality_certificates", [])),
    }
    backend.save_blockchain_state(blockchain_state)
    backend.save_peers(deepcopy(state.get("peers", [])))


def _build_backup_filename(backend: StorageBackend, chain: list[Any], *, include_suffix: bool = True) -> str:
    timestamp = _utc_timestamp()
    node_id = _safe_filename_part(config.NODE_ID)
    backend_name = _backend_name(backend)
    parts = [node_id, backend_name, timestamp]
    latest_hash = _latest_block_hash(chain)
    if latest_hash:
        parts.append(_safe_filename_part(latest_hash[:12]))
    suffix = _SAFE_BACKUP_EXTENSIONS[backend_name] if include_suffix else ""
    return "-".join(parts) + suffix


def _resolve_backend(
    *,
    data_dir: str | Path | None = None,
    storage_backend: str | None = None,
    sqlite_db_path: str | Path | None = None,
) -> StorageBackend:
    data_dir = Path(data_dir or config.DATA_DIR)
    paths = config.build_data_paths(str(data_dir))
    return create_storage_backend(
        name=storage_backend or config.STORAGE_BACKEND,
        blockchain_file=paths["blockchain_file"],
        peers_file=paths["peers_file"],
        sqlite_db_path=str(sqlite_db_path or paths["sqlite_db_path"]),
    )


def _private_key_export_allowed() -> bool:
    return bool(
        config.is_development()
        and not config.public_api_mode_enabled()
        and config.allow_private_key_export()
    )


def backup_storage(
    backend: StorageBackend | None = None,
    *,
    data_dir: str | Path | None = None,
    backup_dir: str | Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    backend = backend or _default_backend()
    state = _load_state(backend)
    snapshot = build_export_snapshot(backend, include_private_keys=False)
    inferred_data_dir = data_dir or _infer_data_dir_from_backend(backend)
    backup_dir = Path(backup_dir or _default_backup_dir(inferred_data_dir))
    backup_path = backup_dir / _build_backup_filename(backend, state.get("chain", []))

    result = {
        "action": "backup",
        "backend": _backend_name(backend),
        "dry_run": dry_run,
        "backup_path": str(backup_path),
        "node_id": config.NODE_ID,
        "network_name": config.NETWORK_NAME,
        "chain_height": snapshot["metadata"]["chain_height"],
        "latest_block_hash": snapshot["metadata"]["latest_block_hash"],
    }
    if dry_run:
        return result

    _write_json_document(backup_path, snapshot)
    result["written"] = True
    return result


def export_storage(
    backend: StorageBackend | None = None,
    *,
    output_path: str | Path,
    include_private_keys: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    backend = backend or _default_backend()
    snapshot = build_export_snapshot(backend, include_private_keys=include_private_keys)
    output_path = Path(output_path)
    result = {
        "action": "export",
        "backend": _backend_name(backend),
        "dry_run": dry_run,
        "output_path": str(output_path),
        "export_version": EXPORT_VERSION,
        "contains_private_keys": bool(include_private_keys),
    }
    if dry_run:
        return result

    _write_json_document(output_path, snapshot)
    result["written"] = True
    return result


def _snapshot_has_sensitive_wallet_data(snapshot: dict[str, Any]) -> bool:
    state = snapshot.get("state", {})
    wallets = state.get("wallets", {})
    if not isinstance(wallets, dict):
        return False
    return any(isinstance(wallet, dict) and "private_key" in wallet for wallet in wallets.values())


def _read_snapshot_file(input_path: Path) -> dict[str, Any]:
    try:
        snapshot = json.loads(input_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Snapshot file not found: {input_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Snapshot file is not valid JSON: {input_path}") from exc
    except OSError as exc:
        raise ValueError(f"Failed to read snapshot file: {input_path}") from exc

    if not isinstance(snapshot, dict):
        raise ValueError("Snapshot file must contain a JSON object at the top level.")
    return snapshot


def import_storage(
    backend: StorageBackend | None = None,
    *,
    input_path: str | Path,
    overwrite: bool = False,
    allow_network_override: bool = False,
    include_private_keys: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    backend = backend or _default_backend()
    input_path = Path(input_path)
    snapshot = _read_snapshot_file(input_path)
    _validate_import_snapshot(snapshot)

    metadata = snapshot["metadata"]
    state = snapshot["state"]
    if metadata.get("network_name") != config.NETWORK_NAME and not allow_network_override:
        raise ValueError(
            f"Snapshot network_name {metadata.get('network_name')!r} does not match this node's network "
            f"{config.NETWORK_NAME!r}. Use allow_network_override=True or --allow-network-override to import anyway."
        )

    if _snapshot_has_sensitive_wallet_data(snapshot):
        if not include_private_keys or not _private_key_export_allowed():
            raise ValueError(
                "Snapshot contains private keys. Private keys may only be imported in development when "
                "PUBLIC_API_MODE is false, ALLOW_DEV_WALLET_PRIVATE_KEY_EXPORT=true, and include_private_keys is enabled."
            )

    existing_state = _load_state(backend)
    existing_has_data = _has_persisted_data(existing_state)
    backup_info = None
    if existing_has_data and not overwrite:
        raise ValueError("Target storage already contains data. Use overwrite=True or --overwrite to replace it.")

    if existing_has_data and overwrite:
        backup_info = backup_storage(backend, dry_run=dry_run)

    result = {
        "action": "import",
        "backend": _backend_name(backend),
        "dry_run": dry_run,
        "input_path": str(input_path),
        "overwrite": overwrite,
        "network_override_used": allow_network_override,
        "backup": backup_info,
    }

    if dry_run:
        return result

    imported_state = {
        "chain": deepcopy(state.get("chain", [])),
        "wallets": deepcopy(state.get("wallets", {})),
        "submissions": deepcopy(state.get("submissions", [])),
        "mint_queue": deepcopy(state.get("mint_queue", [])),
        "votes": deepcopy(state.get("votes", [])),
        "originality_certificates": deepcopy(state.get("originality_certificates", [])),
        "peers": deepcopy(state.get("peers", [])),
    }

    if _has_persisted_data(existing_state):
        existing_genesis = _genesis_block_hash(existing_state.get("chain", []))
        imported_genesis = _genesis_block_hash(imported_state.get("chain", []))
        if existing_genesis and imported_genesis and existing_genesis != imported_genesis:
            raise ValueError(
                "Imported snapshot genesis hash does not match the existing node data."
            )

    _write_state_to_backend(backend, imported_state)
    integrity_report = check_storage_integrity(backend)
    if not integrity_report.get("healthy", False):
        raise ValueError("Imported storage failed integrity validation.")

    result["integrity_report"] = integrity_report
    result["written"] = True
    return result


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backup, export, and import ZoidbergChain storage.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data-dir", help="Node data directory. Defaults to the configured DATA_DIR.")
    common.add_argument("--storage-backend", choices=["json", "sqlite"], help="Override STORAGE_BACKEND.")
    common.add_argument("--sqlite-db-path", help="Explicit SQLite database path.")
    common.add_argument("--dry-run", action="store_true", help="Validate only; do not write files.")

    backup_parser = subparsers.add_parser("backup", parents=[common], help="Create a storage backup.")
    backup_parser.add_argument("--backup-dir", help="Backup directory. Defaults to DATA_DIR/backups.")

    export_parser = subparsers.add_parser("export", parents=[common], help="Export a portable storage snapshot.")
    export_parser.add_argument("--output", required=True, help="Output JSON file.")
    export_parser.add_argument(
        "--include-private-keys",
        action="store_true",
        help="Include private keys in the export. Development-only.",
    )

    import_parser = subparsers.add_parser("import", parents=[common], help="Import a portable storage snapshot.")
    import_parser.add_argument("--input", required=True, help="Input JSON snapshot.")
    import_parser.add_argument("--overwrite", action="store_true", help="Replace existing data.")
    import_parser.add_argument(
        "--allow-network-override",
        action="store_true",
        help="Allow importing a snapshot from a different network.",
    )
    import_parser.add_argument(
        "--include-private-keys",
        action="store_true",
        help="Allow importing private keys from a development-only export.",
    )

    return parser


def run_cli(argv: list[str] | None = None) -> int:
    parser = build_cli_parser()
    try:
        args = parser.parse_args(argv)
        backend = _resolve_backend(
            data_dir=args.data_dir,
            storage_backend=args.storage_backend,
            sqlite_db_path=args.sqlite_db_path,
        )

        if args.command == "backup":
            result = backup_storage(
                backend,
                data_dir=args.data_dir,
                backup_dir=args.backup_dir,
                dry_run=args.dry_run,
            )
        elif args.command == "export":
            result = export_storage(
                backend,
                output_path=args.output,
                include_private_keys=args.include_private_keys,
                dry_run=args.dry_run,
            )
        elif args.command == "import":
            result = import_storage(
                backend,
                input_path=args.input,
                overwrite=args.overwrite,
                allow_network_override=args.allow_network_override,
                include_private_keys=args.include_private_keys,
                dry_run=args.dry_run,
            )
        else:
            raise ValueError(f"Unsupported command: {args.command}")
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
