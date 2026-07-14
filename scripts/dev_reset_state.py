from __future__ import annotations

import argparse
import json
import shutil
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from storage import create_storage_backend
from storage_tools import backup_storage


CONFIRMATION_FLAG = "--yes-i-understand-this-deletes-test-data"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROTECTED_ROOT_NAMES = {
    ".git",
    ".github",
    ".venv",
    "docs",
    "scripts",
    "tests",
    "zoidbergcoin-ui",
}


def _empty_state() -> dict[str, Any]:
    return {
        "chain": [],
        "wallets": {},
        "submissions": [],
        "content_objects": [],
        "mint_queue": [],
        "votes": [],
        "originality_certificates": [],
    }


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _resolve_workspace_path(value: str | Path | None) -> Path:
    raw_path = Path(value or config.DATA_DIR)
    if not raw_path.is_absolute():
        raw_path = PROJECT_ROOT / raw_path
    return raw_path.resolve()


def _ensure_development_only() -> None:
    if not config.is_development():
        raise ValueError("Dev reset is only allowed when ENVIRONMENT=development.")
    if config.public_api_mode_enabled():
        raise ValueError("Dev reset is not allowed when PUBLIC_API_MODE=true.")
    if not config.allow_dev_reset_endpoints():
        raise ValueError(
            "Dev reset is disabled by configuration. Set ALLOW_DEV_RESET_ENDPOINTS=true in development only."
        )


def _validate_safe_data_dir(data_dir: Path) -> None:
    if data_dir == PROJECT_ROOT:
        raise ValueError("Refusing to reset the project root. Pass a node data directory instead.")
    if not _is_relative_to(data_dir, PROJECT_ROOT):
        raise ValueError("Refusing to reset a path outside the project workspace.")

    relative_parts = data_dir.relative_to(PROJECT_ROOT).parts
    if not relative_parts:
        raise ValueError("Refusing to reset an empty data directory path.")
    if relative_parts[0] in PROTECTED_ROOT_NAMES:
        raise ValueError(
            f"Refusing to reset protected workspace path '{relative_parts[0]}'. "
            "Use a dedicated node data directory under data/ or temp/."
        )


def _content_dir_for(data_dir: Path) -> Path:
    configured = Path(config.CONTENT_STORAGE_DIR)
    if not configured.is_absolute():
        configured = (PROJECT_ROOT / configured).resolve()
    else:
        configured = configured.resolve()

    default_content_dir = (data_dir / "content").resolve()
    if _is_relative_to(configured, data_dir):
        return configured
    return default_content_dir


def _build_backend(data_dir: Path, backend_name: str | None = None):
    paths = config.build_data_paths(str(data_dir))
    return create_storage_backend(
        name=backend_name or config.STORAGE_BACKEND,
        blockchain_file=paths["blockchain_file"],
        peers_file=paths["peers_file"],
        sqlite_db_path=paths["sqlite_db_path"],
    )


def reset_state(
    *,
    node_data_dir: str | Path | None = None,
    backend: str | None = None,
    include_content_files: bool = False,
    include_peers: bool = False,
    backup_first_enabled: bool = False,
    confirmation: bool = False,
) -> dict[str, Any]:
    _ensure_development_only()
    if not confirmation:
        raise ValueError(
            "Refusing to delete test data without explicit confirmation. "
            f"Pass {CONFIRMATION_FLAG}."
        )

    data_dir = _resolve_workspace_path(node_data_dir)
    _validate_safe_data_dir(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    backend_instance = _build_backend(data_dir, backend)
    content_dir = _content_dir_for(data_dir)
    if not _is_relative_to(content_dir, data_dir):
        raise ValueError("Refusing to remove content files outside the selected node data directory.")

    preserved_peers = []
    try:
        preserved_peers = deepcopy(backend_instance.load_peers() or [])
    except Exception:
        preserved_peers = []

    backup_result = None
    if backup_first_enabled:
        backup_result = backup_storage(
            backend_instance,
            data_dir=data_dir,
            backup_dir=data_dir / "backups" / "reset-preflight",
        )

    deleted_paths: list[str] = []
    reinitialized_paths: list[str] = []

    temp_dir = data_dir / "temp"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
        deleted_paths.append(str(temp_dir))

    if include_content_files and content_dir.exists():
        shutil.rmtree(content_dir)
        deleted_paths.append(str(content_dir))

    if backend_instance.__class__.__name__ == "JSONStorageBackend":
        blockchain_path = Path(backend_instance.blockchain_file)
        for candidate in (blockchain_path, blockchain_path.with_name(blockchain_path.name + ".bak")):
            if candidate.exists():
                candidate.unlink()
                deleted_paths.append(str(candidate))

        peers_path = Path(backend_instance.peers_file)
        if include_peers:
            for candidate in (peers_path, peers_path.with_name(peers_path.name + ".bak")):
                if candidate.exists():
                    candidate.unlink()
                    deleted_paths.append(str(candidate))

        backend_instance = _build_backend(data_dir, "json")
        backend_instance.save_blockchain_state(_empty_state())
        backend_instance.save_peers([] if include_peers else preserved_peers)
        reinitialized_paths.extend([backend_instance.blockchain_file, backend_instance.peers_file])
    else:
        sqlite_path = Path(backend_instance.sqlite_db_path)
        backup_path = sqlite_path.with_name(sqlite_path.name + ".bak")
        if backup_path.exists():
            backup_path.unlink()
            deleted_paths.append(str(backup_path))

        backend_instance = _build_backend(data_dir, "sqlite")
        backend_instance.save_blockchain_state(_empty_state())
        backend_instance.save_peers([] if include_peers else preserved_peers)
        reinitialized_paths.append(backend_instance.sqlite_db_path)

    result = {
        "action": "dev_reset_state",
        "data_dir": str(data_dir),
        "backend": backend or config.STORAGE_BACKEND,
        "include_content_files": include_content_files,
        "include_peers": include_peers,
        "backup_first": backup_first_enabled,
        "backup": backup_result,
        "deleted_paths": deleted_paths,
        "reinitialized_paths": reinitialized_paths,
        "preserved_peer_count": 0 if include_peers else len(preserved_peers),
        "warning": "Development/testnet preparation only. Never run this in production.",
    }
    return result


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reset local ZoidbergChain development state for a clean MetaMask-era test environment."
    )
    parser.add_argument(
        "--yes-i-understand-this-deletes-test-data",
        dest="confirmed",
        action="store_true",
        help="Required explicit confirmation flag.",
    )
    parser.add_argument(
        "--backup-first",
        action="store_true",
        help="Create a backup snapshot before deleting local node state.",
    )
    parser.add_argument(
        "--include-content-files",
        action="store_true",
        help="Also delete local content binaries under the node content storage directory.",
    )
    parser.add_argument(
        "--include-peers",
        action="store_true",
        help="Also reset persisted peer state instead of preserving it.",
    )
    parser.add_argument(
        "--node-data-dir",
        help="Node data directory to reset. Defaults to the configured DATA_DIR.",
    )
    parser.add_argument(
        "--backend",
        choices=["json", "sqlite"],
        help="Storage backend for the selected node data directory.",
    )
    return parser


def run_cli(argv: list[str] | None = None) -> int:
    parser = build_cli_parser()
    try:
        args = parser.parse_args(argv)
        result = reset_state(
            node_data_dir=args.node_data_dir,
            backend=args.backend,
            include_content_files=args.include_content_files,
            include_peers=args.include_peers,
            backup_first_enabled=args.backup_first,
            confirmation=args.confirmed,
        )
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli(sys.argv[1:]))
