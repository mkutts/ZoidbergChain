from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config
from admin_auth import admin_auth_is_configured
from storage import JSONStorageBackend, SQLiteStorageBackend, check_storage_integrity, create_storage_backend


BUILD_INFO_ENV_KEYS = {
    "version": "APP_VERSION",
    "git_commit": "GIT_COMMIT",
    "build_timestamp": "BUILD_TIMESTAMP",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_build_metadata() -> dict[str, str | None]:
    return {
        key: (os.getenv(env_name) or "").strip() or None
        for key, env_name in BUILD_INFO_ENV_KEYS.items()
    }


def safe_latest_block_summary(blockchain) -> dict[str, Any]:
    latest_block = blockchain.get_latest_block()
    return {
        "index": getattr(latest_block, "index", None),
        "hash": getattr(latest_block, "hash", None),
        "timestamp": getattr(latest_block, "timestamp", None),
        "certificate_id": getattr(latest_block, "certificate_id", None),
        "submission_id": getattr(latest_block, "submission_id", None),
        "transaction_count": getattr(latest_block, "transaction_count", None),
    }


def pending_submission_count(blockchain) -> int:
    return len(blockchain.storage.list_submissions(blockchain.submissions, status="pending"))


def pending_access_request_count(blockchain) -> int:
    return len(blockchain.list_access_requests(status="pending"))


def mempool_transaction_count(blockchain) -> int:
    return len(blockchain.list_mempool_transactions())


def _path_writable(path: Path) -> bool:
    target = path if path.exists() else path.parent
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return os.access(target, os.W_OK)


def _content_storage_runtime_status() -> dict[str, Any]:
    content_dir = Path(config.CONTENT_STORAGE_DIR)
    exists = content_dir.exists()
    return {
        "reachable": exists or _path_writable(content_dir),
        "exists": exists,
        "writable": _path_writable(content_dir),
        "path": str(content_dir),
    }


def _database_runtime_status(backend) -> dict[str, Any]:
    if isinstance(backend, SQLiteStorageBackend):
        db_path = Path(backend.sqlite_db_path)
        exists = db_path.exists()
        quick_check = "not_run"
        reachable = False
        error = None
        if exists:
            try:
                with sqlite3.connect(backend.sqlite_db_path) as connection:
                    quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
                reachable = quick_check == "ok"
            except sqlite3.Error as exc:
                error = str(exc)
        else:
            reachable = _path_writable(db_path)
        return {
            "reachable": reachable,
            "exists": exists,
            "writable": _path_writable(db_path),
            "quick_check": quick_check,
            "path": str(db_path),
            "error": error,
        }

    blockchain_file = Path(getattr(backend, "blockchain_file", ""))
    peers_file = Path(getattr(backend, "peers_file", ""))
    return {
        "reachable": blockchain_file.exists() or _path_writable(blockchain_file),
        "exists": blockchain_file.exists(),
        "writable": _path_writable(blockchain_file),
        "path": str(blockchain_file),
        "peers_path": str(peers_file),
        "error": None,
    }


def safe_runtime_storage_status(backend=None) -> dict[str, Any]:
    backend = backend or create_storage_backend()
    database = _database_runtime_status(backend)
    content_storage = _content_storage_runtime_status()
    return {
        "storage_backend": config.STORAGE_BACKEND,
        "database": database,
        "content_storage": content_storage,
        "healthy": bool(database.get("reachable") and content_storage.get("reachable")),
    }


def safe_environment_validation() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add_check(code: str, *, ok: bool, level: str, message: str) -> None:
        checks.append({
            "code": code,
            "ok": bool(ok),
            "level": level,
            "message": message,
        })

    restricted_environment = config.ENVIRONMENT in {"testnet", "production"}
    add_check(
        "restricted_access_mode",
        ok=not restricted_environment or config.ACCESS_CONTROL_MODE in {"invite_only", "allowlist"},
        level="error",
        message="Testnet or production should not run with open or disabled access control.",
    )
    add_check(
        "dev_bypass_disabled",
        ok=not restricted_environment or not config.ACCESS_DEV_BYPASS_ENABLED,
        level="error",
        message="ACCESS_DEV_BYPASS_ENABLED must be false outside development.",
    )
    add_check(
        "admin_auth_configured",
        ok=not (config.ADMIN_UI_ENABLED and config.ADMIN_AUTH_ENABLED) or admin_auth_is_configured(
            config.ADMIN_PASSWORD_HASH,
            config.ADMIN_BOOTSTRAP_TOKEN,
        ),
        level="error",
        message="Admin auth is enabled but no admin credential is configured.",
    )
    add_check(
        "peer_secret_configured",
        ok=not (config.require_peer_auth() or config.signed_peer_messages_enabled()) or config.peer_shared_secret_is_configured(),
        level="error",
        message="Peer auth or signed peer messages require a non-default PEER_SHARED_SECRET.",
    )

    runtime_storage = safe_runtime_storage_status()
    add_check(
        "storage_writable",
        ok=runtime_storage["database"]["writable"],
        level="error",
        message="Configured storage path is not writable.",
    )
    add_check(
        "content_storage_writable",
        ok=runtime_storage["content_storage"]["writable"],
        level="error",
        message="Configured content storage directory is not writable.",
    )

    frontend_origin = (os.getenv("FRONTEND_ORIGIN") or "").strip()
    allowed_origins = set(config.cors_allowed_origins())
    add_check(
        "frontend_origin_in_cors",
        ok=not frontend_origin or frontend_origin in allowed_origins,
        level="warning",
        message="FRONTEND_ORIGIN is not present in the configured CORS allowlist.",
    )
    add_check(
        "public_demo_mode",
        ok=config.ENVIRONMENT != "testnet" or config.public_demo_mode_enabled(),
        level="warning",
        message="PUBLIC_DEMO_MODE should be enabled for the controlled public testnet.",
    )
    add_check(
        "upload_limit_reasonable",
        ok=config.MAX_CONTENT_FILE_SIZE_BYTES > 0 and config.MAX_CONTENT_FILE_SIZE_BYTES <= (25 * 1024 * 1024),
        level="warning",
        message="MAX_CONTENT_FILE_SIZE_BYTES should stay within a conservative testnet range.",
    )

    error_count = sum(1 for check in checks if not check["ok"] and check["level"] == "error")
    warning_count = sum(1 for check in checks if not check["ok"] and check["level"] == "warning")
    return {
        "generated_at": _utc_now_iso(),
        "healthy": error_count == 0,
        "error_count": error_count,
        "warning_count": warning_count,
        "checks": checks,
    }


def _infer_data_dir_from_backend(backend) -> Path:
    if isinstance(backend, SQLiteStorageBackend):
        return Path(backend.sqlite_db_path).parent
    return Path(backend.blockchain_file).parent


def safe_backup_status(backend=None) -> dict[str, Any]:
    backend = backend or create_storage_backend()
    data_dir = _infer_data_dir_from_backend(backend)
    backup_dir = data_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_files = sorted(
        [path for path in backup_dir.iterdir() if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    latest = backup_files[0] if backup_files else None
    return {
        "data_dir": str(data_dir),
        "backup_dir": str(backup_dir),
        "backup_count": len(backup_files),
        "latest_backup": (
            {
                "name": latest.name,
                "path": str(latest),
                "size_bytes": latest.stat().st_size,
                "modified_at": datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc).isoformat(),
            }
            if latest
            else None
        ),
        "recent_backups": [
            {
                "name": path.name,
                "size_bytes": path.stat().st_size,
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
            }
            for path in backup_files[:5]
        ],
    }


def verify_backup_status(backend=None) -> dict[str, Any]:
    backend = backend or create_storage_backend()
    status = safe_backup_status(backend)
    latest_backup = status.get("latest_backup")
    if not latest_backup:
        return {
            **status,
            "verified": False,
            "message": "No backup file found in the backup directory.",
        }

    backup_path = Path(latest_backup["path"])
    try:
        payload = json.loads(backup_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            **status,
            "verified": False,
            "message": f"Latest backup is unreadable: {exc}",
        }

    metadata = payload.get("metadata") if isinstance(payload, dict) else None
    return {
        **status,
        "verified": bool(isinstance(payload, dict) and isinstance(metadata, dict)),
        "message": "Latest backup file is readable." if isinstance(metadata, dict) else "Latest backup file is missing expected metadata.",
        "metadata": metadata if isinstance(metadata, dict) else None,
    }


def sqlite_integrity_status(backend=None) -> dict[str, Any]:
    backend = backend or create_storage_backend()
    if not isinstance(backend, SQLiteStorageBackend):
        return {
            "backend": config.STORAGE_BACKEND,
            "checked": False,
            "healthy": True,
            "message": "SQLite integrity check skipped because STORAGE_BACKEND is not sqlite.",
        }

    db_path = Path(backend.sqlite_db_path)
    if not db_path.exists():
        return {
            "backend": "sqlite",
            "checked": False,
            "healthy": False,
            "message": "SQLite database file does not exist yet.",
            "path": str(db_path),
        }

    try:
        with sqlite3.connect(backend.sqlite_db_path) as connection:
            quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
    except sqlite3.Error as exc:
        return {
            "backend": "sqlite",
            "checked": True,
            "healthy": False,
            "message": f"SQLite integrity check failed: {exc}",
            "path": str(db_path),
        }

    return {
        "backend": "sqlite",
        "checked": True,
        "healthy": quick_check == "ok",
        "message": "SQLite integrity check passed." if quick_check == "ok" else quick_check,
        "path": str(db_path),
    }


def safe_integrity_status(backend=None) -> dict[str, Any]:
    backend = backend or create_storage_backend()
    return check_storage_integrity(backend)


def safe_public_status_payload(*, blockchain, peer_store, started_at: float) -> dict[str, Any]:
    runtime_storage = safe_runtime_storage_status(blockchain.storage)
    latest_block = safe_latest_block_summary(blockchain)
    uptime_seconds = max(0, int(time.time() - float(started_at)))
    return {
        "service_alive": True,
        "status": "ok",
        "environment": config.ENVIRONMENT,
        "network_name": config.NETWORK_NAME,
        "node_id": config.NODE_ID,
        "public_demo_mode": config.public_demo_mode_enabled(),
        "storage_backend": config.STORAGE_BACKEND,
        "database_reachable": runtime_storage["database"]["reachable"],
        "content_storage_reachable": runtime_storage["content_storage"]["reachable"],
        "chain_height": latest_block["index"],
        "latest_block_hash": latest_block["hash"],
        "pending_submissions_count": pending_submission_count(blockchain),
        "pending_access_requests_count": pending_access_request_count(blockchain),
        "mempool_transaction_count": mempool_transaction_count(blockchain),
        "peer_count": len(peer_store.list_active_peers(network_name=config.NETWORK_NAME)),
        "uptime_seconds": uptime_seconds,
        "build": safe_build_metadata(),
    }
