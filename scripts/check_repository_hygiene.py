"""Fail when generated or operator-owned runtime files are tracked by Git."""

from __future__ import annotations

import subprocess
import sys
from pathlib import PurePosixPath
from typing import Iterable


EXACT_PROHIBITED = {
    ".env": "local environment file",
    "blockchain.json": "mutable blockchain state",
    "blockchain.json.bak": "blockchain backup",
    "peers.json": "peer runtime state",
    "peers.json.bak": "peer state backup",
    "wallets.json": "wallet runtime state",
    "wallets.json.bak": "wallet state backup",
    "collect.txt": "diagnostic collection output",
    "DIAGNOSTIC_REPORT.txt": "diagnostic report",
}

PROHIBITED_ROOT_DIRECTORIES = {
    ".venv": "Python virtual environment",
    "venv": "Python virtual environment",
    "env": "Python virtual environment",
    "ENV": "Python virtual environment",
    "__pycache__": "Python bytecode cache",
    ".pytest_cache": "pytest cache",
    "node_modules": "Node dependency installation",
    "dist": "frontend build output",
    "dist-ssr": "frontend build output",
    "data": "runtime data directory",
    "content": "runtime content cache",
    "temp": "temporary runtime directory",
    "tmp": "temporary runtime directory",
    "backups": "operator backup directory",
    "exports": "operator export directory",
    "downloads": "download cache",
    "legacy-chain-backup": "legacy chain backup",
    "pre-genesis-meme-v1-backup": "pre-genesis runtime backup",
    "logs": "runtime logs",
}

PROHIBITED_SUFFIXES = {
    ".bak": "backup file",
    ".sqlite": "SQLite runtime database",
    ".sqlite3": "SQLite runtime database",
    ".sqlite-journal": "SQLite journal",
    ".sqlite-wal": "SQLite write-ahead log",
    ".sqlite-shm": "SQLite shared-memory file",
    ".patch": "local patch artifact",
    ".diff": "local diff artifact",
    ".log": "runtime log",
    ".tmp": "temporary file",
    ".temp": "temporary file",
    ".zip": "generated archive",
    ".tar": "generated archive",
    ".tgz": "generated archive",
    ".tar.gz": "generated archive",
}


def classify_path(path: str) -> str | None:
    """Return a concise failure category without opening the tracked file."""
    normalized = path.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized in EXACT_PROHIBITED:
        return EXACT_PROHIBITED[normalized]

    candidate = PurePosixPath(normalized)
    if candidate.name == ".env" or (
        candidate.name.startswith(".env.") and not candidate.name.endswith(".example")
    ):
        return "local environment file"

    if candidate.parts and candidate.parts[0] in PROHIBITED_ROOT_DIRECTORIES:
        return PROHIBITED_ROOT_DIRECTORIES[candidate.parts[0]]

    lower_name = candidate.name.lower()
    for suffix, category in PROHIBITED_SUFFIXES.items():
        if lower_name.endswith(suffix):
            return category
    return None


def find_prohibited_paths(paths: Iterable[str]) -> list[tuple[str, str]]:
    return [
        (path, category)
        for path in paths
        if (category := classify_path(path)) is not None
    ]


def tracked_paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [path for path in result.stdout.splitlines() if path]


def main() -> int:
    try:
        failures = find_prohibited_paths(tracked_paths())
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"repository hygiene check could not inspect tracked paths: {exc}", file=sys.stderr)
        return 2

    if not failures:
        print("Repository hygiene check passed.")
        return 0

    print("Repository hygiene check failed:")
    for path, category in failures:
        print(f"- {path}: {category}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
