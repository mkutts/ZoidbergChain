from __future__ import annotations

import json
import logging
import os
import sqlite3
import shutil
import tempfile
from abc import ABC, abstractmethod
from copy import deepcopy
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import config


SUPPORTED_STORAGE_BACKENDS = {"json", "sqlite"}
_STORAGE_SECTIONS = (
    "chain",
    "wallets",
    "submissions",
    "mint_queue",
    "votes",
    "originality_certificates",
    "peers",
)
_BLOCKCHAIN_JSON_REQUIRED_SECTIONS = tuple(
    section for section in _STORAGE_SECTIONS if section != "peers"
)


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def _default_section_value(section_name):
    if section_name == "chain":
        return []
    if section_name == "wallets":
        return {}
    if section_name == "submissions":
        return []
    if section_name == "mint_queue":
        return []
    if section_name == "votes":
        return []
    if section_name == "originality_certificates":
        return []
    if section_name == "peers":
        return []
    return None


def _json_loads_or_default(value, default, *, strict: bool = False, label: str = "JSON data"):
    if value in (None, ""):
        return deepcopy(default)
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        if strict:
            raise StorageCorruptionError(f"Malformed JSON stored in {label}.")
        return deepcopy(default)


class StorageCorruptionError(RuntimeError):
    pass


@dataclass
class StorageIntegrityReport:
    backend: str
    healthy: bool
    details: list[str]
    main_path: str | None = None
    backup_path: str | None = None
    recovered_from_backup: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "healthy": self.healthy,
            "details": list(self.details),
            "main_path": self.main_path,
            "backup_path": self.backup_path,
            "recovered_from_backup": self.recovered_from_backup,
        }


def _backup_path_for(path: str | Path) -> str:
    path = Path(path)
    return str(path.with_name(path.name + ".bak"))


def _required_sections_missing(document: dict[str, Any], required_sections: tuple[str, ...]) -> list[str]:
    return [section for section in required_sections if section not in document]


def _validate_json_document_shape(
    document: Any,
    *,
    expected_type: type,
    required_sections: tuple[str, ...] | None,
    label: str,
) -> None:
    if not isinstance(document, expected_type):
        expected_name = expected_type.__name__
        raise StorageCorruptionError(f"{label} must contain a {expected_name} at the top level.")

    if expected_type is dict and required_sections:
        missing_sections = _required_sections_missing(document, required_sections)
        if missing_sections:
            missing = ", ".join(missing_sections)
            raise StorageCorruptionError(f"{label} is missing required sections: {missing}.")


def _read_json_document(path: str | Path, *, label: str, expected_type: type, required_sections: tuple[str, ...] | None) -> Any:
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8") as handle:
            document = json.load(handle)
    except (json.JSONDecodeError, OSError) as exc:
        raise StorageCorruptionError(f"Failed to read {label}: {path}") from exc

    _validate_json_document_shape(
        document,
        expected_type=expected_type,
        required_sections=required_sections,
        label=label,
    )
    return document


def _load_json_document_with_backup(
    main_path: str | Path,
    *,
    backup_path: str | Path,
    label: str,
    expected_type: type,
    required_sections: tuple[str, ...] | None = None,
) -> tuple[Any | None, bool]:
    main_path = Path(main_path)
    backup_path = Path(backup_path)

    if not main_path.exists():
        return None, False

    try:
        return (
            _read_json_document(
                main_path,
                label=label,
                expected_type=expected_type,
                required_sections=required_sections,
            ),
            False,
        )
    except StorageCorruptionError as main_error:
        if not backup_path.exists():
            raise StorageCorruptionError(
                f"{label} is corrupt and no usable backup was found at {backup_path}."
            ) from main_error

        try:
            recovered_document = _read_json_document(
                backup_path,
                label=f"{label} backup",
                expected_type=expected_type,
                required_sections=required_sections,
            )
        except StorageCorruptionError as backup_error:
            raise StorageCorruptionError(
                f"{label} is corrupt and the backup is also unreadable."
            ) from backup_error

        logging.warning(
            "%s is corrupt; recovered data from backup file %s.",
            label,
            backup_path,
        )
        return recovered_document, True


def _atomic_write_json_document(
    path: str | Path,
    document: Any,
    *,
    backup_path: str | Path,
    create_backup_from_existing: bool,
) -> None:
    path = Path(path)
    backup_path = Path(backup_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if create_backup_from_existing and path.exists():
        shutil.copy2(path, backup_path)

    fd, temp_path = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=4)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temp_path, path)

        if not backup_path.exists():
            shutil.copy2(path, backup_path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


class StorageBackend(ABC):
    def __init__(
        self,
        blockchain_file: str | None = None,
        peers_file: str | None = None,
        sqlite_db_path: str | None = None,
    ):
        self.blockchain_file = blockchain_file or config.BLOCKCHAIN_FILE
        self.peers_file = peers_file or config.PEERS_FILE
        self.sqlite_db_path = sqlite_db_path or config.SQLITE_DB_PATH

    @abstractmethod
    def load_blockchain_document(self) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def save_blockchain_document(self, document: dict[str, Any]) -> None:
        raise NotImplementedError

    def delete_blockchain_document(self) -> None:
        for candidate in (self.blockchain_file, _backup_path_for(self.blockchain_file)):
            if os.path.exists(candidate):
                os.remove(candidate)

    def load_chain(self):
        document = self.load_blockchain_document()
        if not document:
            return []
        return document.get("chain", [])

    def save_chain(self, chain) -> None:
        document = self._load_or_new_blockchain_document()
        document["chain"] = chain
        self.save_blockchain_document(document)

    def load_wallets(self):
        document = self.load_blockchain_document()
        if not document:
            return {}
        return document.get("wallets", {})

    def save_wallets(self, wallets) -> None:
        document = self._load_or_new_blockchain_document()
        document["wallets"] = wallets
        self.save_blockchain_document(document)

    def load_submissions(self):
        document = self.load_blockchain_document()
        if not document:
            return []
        return document.get("submissions", [])

    def save_submissions(self, submissions) -> None:
        document = self._load_or_new_blockchain_document()
        document["submissions"] = submissions
        self.save_blockchain_document(document)

    def load_mint_queue(self):
        document = self.load_blockchain_document()
        if not document:
            return []
        return document.get("mint_queue", [])

    def save_mint_queue(self, mint_queue) -> None:
        document = self._load_or_new_blockchain_document()
        document["mint_queue"] = mint_queue
        self.save_blockchain_document(document)

    def load_votes(self):
        document = self.load_blockchain_document()
        if not document:
            return []
        return document.get("votes", [])

    def save_votes(self, votes) -> None:
        document = self._load_or_new_blockchain_document()
        document["votes"] = votes
        self.save_blockchain_document(document)

    def load_certificates(self):
        document = self.load_blockchain_document()
        if not document:
            return []
        return document.get("originality_certificates", [])

    def save_certificates(self, certificates) -> None:
        document = self._load_or_new_blockchain_document()
        document["originality_certificates"] = certificates
        self.save_blockchain_document(document)

    def load_blockchain_state(self):
        return self.load_blockchain_document()

    def save_blockchain_state(self, state: dict[str, Any]) -> None:
        self.save_blockchain_document(state)

    @abstractmethod
    def load_peers(self):
        raise NotImplementedError

    @abstractmethod
    def save_peers(self, peers) -> None:
        raise NotImplementedError

    def _load_or_new_blockchain_document(self) -> dict[str, Any]:
        document = self.load_blockchain_document()
        if isinstance(document, dict):
            return deepcopy(document)
        return {}


class JSONStorageBackend(StorageBackend):
    def __init__(
        self,
        blockchain_file: str | None = None,
        peers_file: str | None = None,
        sqlite_db_path: str | None = None,
    ):
        super().__init__(
            blockchain_file=blockchain_file,
            peers_file=peers_file,
            sqlite_db_path=sqlite_db_path,
        )
        self._blockchain_recovered_from_backup = False
        self._peers_recovered_from_backup = False

    def load_blockchain_document(self) -> dict[str, Any] | None:
        document, recovered_from_backup = _load_json_document_with_backup(
            self.blockchain_file,
            backup_path=_backup_path_for(self.blockchain_file),
            label="blockchain JSON",
            expected_type=dict,
            required_sections=None,
        )
        self._blockchain_recovered_from_backup = recovered_from_backup
        return document

    def save_blockchain_document(self, document: dict[str, Any]) -> None:
        backup_path = _backup_path_for(self.blockchain_file)
        create_backup = False
        if os.path.exists(self.blockchain_file) and not self._blockchain_recovered_from_backup:
            try:
                _read_json_document(
                    self.blockchain_file,
                    label="blockchain JSON",
                    expected_type=dict,
                    required_sections=None,
                )
            except StorageCorruptionError:
                create_backup = False
            else:
                create_backup = True

        _atomic_write_json_document(
            self.blockchain_file,
            document,
            backup_path=backup_path,
            create_backup_from_existing=create_backup,
        )
        self._blockchain_recovered_from_backup = False

    def load_peers(self):
        peers, recovered_from_backup = _load_json_document_with_backup(
            self.peers_file,
            backup_path=_backup_path_for(self.peers_file),
            label="peers JSON",
            expected_type=list,
        )
        self._peers_recovered_from_backup = recovered_from_backup
        return peers or []

    def save_peers(self, peers) -> None:
        backup_path = _backup_path_for(self.peers_file)
        create_backup = False
        if os.path.exists(self.peers_file) and not self._peers_recovered_from_backup:
            try:
                _read_json_document(
                    self.peers_file,
                    label="peers JSON",
                    expected_type=list,
                    required_sections=None,
                )
            except StorageCorruptionError:
                create_backup = False
            else:
                create_backup = True

        _atomic_write_json_document(
            self.peers_file,
            peers,
            backup_path=backup_path,
            create_backup_from_existing=create_backup,
        )
        self._peers_recovered_from_backup = False


class SQLiteStorageBackend(StorageBackend):
    def __init__(
        self,
        blockchain_file: str | None = None,
        peers_file: str | None = None,
        sqlite_db_path: str | None = None,
    ):
        super().__init__(
            blockchain_file=blockchain_file,
            peers_file=peers_file,
            sqlite_db_path=sqlite_db_path,
        )
        self._initialize_database()
        logging.warning(
            "SQLite backend selected. Existing JSON data will not be migrated automatically until Task 5.3."
        )

    def delete_blockchain_document(self) -> None:
        for candidate in (self.sqlite_db_path, _backup_path_for(self.sqlite_db_path)):
            if os.path.exists(candidate):
                os.remove(candidate)

    def _connect(self):
        return sqlite3.connect(self.sqlite_db_path)

    def _initialize_database(self) -> None:
        os.makedirs(os.path.dirname(self.sqlite_db_path) or ".", exist_ok=True)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS storage_sections (
                    section_name TEXT PRIMARY KEY,
                    json_data TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            for section_name in _STORAGE_SECTIONS:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO storage_sections (section_name, json_data, updated_at)
                    VALUES (?, ?, ?)
                    """,
                    (section_name, json.dumps(_default_section_value(section_name)), _utc_now_iso()),
                )

    def _load_sections(self, *, strict: bool = True) -> dict[str, Any]:
        defaults = {section: deepcopy(_default_section_value(section)) for section in _STORAGE_SECTIONS}
        if not os.path.exists(self.sqlite_db_path):
            return defaults

        with self._connect() as connection:
            try:
                cursor = connection.execute(
                    "SELECT section_name, json_data FROM storage_sections"
                )
                rows = cursor.fetchall()
            except sqlite3.Error as exc:
                raise StorageCorruptionError(
                    f"Failed to read SQLite storage at {self.sqlite_db_path}."
                ) from exc

            seen_sections = set()
            for section_name, json_data_value in rows:
                if section_name in defaults:
                    seen_sections.add(section_name)
                    defaults[section_name] = _json_loads_or_default(
                        json_data_value,
                        _default_section_value(section_name),
                        strict=strict,
                        label=f"SQLite section {section_name}",
                    )

            missing_sections = [section for section in _STORAGE_SECTIONS if section not in seen_sections]
            if missing_sections and strict:
                missing = ", ".join(missing_sections)
                raise StorageCorruptionError(
                    f"SQLite storage is missing required sections: {missing}."
                )
        return defaults

    def _save_sections(self, sections: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for section_name in _STORAGE_SECTIONS:
                payload = sections.get(section_name, _default_section_value(section_name))
                connection.execute(
                    """
                    INSERT INTO storage_sections (section_name, json_data, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(section_name) DO UPDATE SET
                        json_data = excluded.json_data,
                        updated_at = excluded.updated_at
                    """,
                    (section_name, json.dumps(payload), _utc_now_iso()),
                )

    def load_blockchain_document(self) -> dict[str, Any] | None:
        if not os.path.exists(self.sqlite_db_path):
            return None
        sections = self._load_sections()
        return {
            "chain": sections["chain"],
            "wallets": sections["wallets"],
            "submissions": sections["submissions"],
            "mint_queue": sections["mint_queue"],
            "votes": sections["votes"],
            "originality_certificates": sections["originality_certificates"],
            "peers": sections["peers"],
        }

    def save_blockchain_document(self, document: dict[str, Any]) -> None:
        current_document = self._load_sections()
        merged_document = {
            section_name: deepcopy(
                document.get(section_name, current_document.get(section_name, _default_section_value(section_name)))
            )
            for section_name in _STORAGE_SECTIONS
        }
        self._save_sections(merged_document)

    def load_peers(self):
        if not os.path.exists(self.sqlite_db_path):
            return []
        return self._load_sections().get("peers", [])

    def save_peers(self, peers) -> None:
        sections = self._load_sections()
        sections["peers"] = peers
        self._save_sections(sections)

    def backup_sqlite_database(self, target_path: str | None = None) -> str:
        backup_path = Path(target_path) if target_path else Path(_backup_path_for(self.sqlite_db_path))
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.sqlite_db_path, backup_path)
        return str(backup_path)


def check_storage_integrity(backend: StorageBackend | None = None) -> dict[str, Any]:
    backend = backend or create_storage_backend()

    if isinstance(backend, JSONStorageBackend):
        details: list[str] = []
        recovered_from_backup = False

        blockchain_state, blockchain_recovered = _load_json_document_with_backup(
            backend.blockchain_file,
            backup_path=_backup_path_for(backend.blockchain_file),
            label="blockchain JSON",
            expected_type=dict,
            required_sections=_BLOCKCHAIN_JSON_REQUIRED_SECTIONS,
        )
        if blockchain_state is None:
            details.append("blockchain JSON missing; bootstrap expected")
        else:
            details.append("blockchain JSON readable")
            recovered_from_backup = recovered_from_backup or blockchain_recovered

        peers_state, peers_recovered = _load_json_document_with_backup(
            backend.peers_file,
            backup_path=_backup_path_for(backend.peers_file),
            label="peers JSON",
            expected_type=list,
        )
        if peers_state is None:
            details.append("peers JSON missing; bootstrap expected")
        else:
            details.append("peers JSON readable")
            recovered_from_backup = recovered_from_backup or peers_recovered

        report = StorageIntegrityReport(
            backend="json",
            healthy=True,
            details=details,
            main_path=backend.blockchain_file,
            backup_path=_backup_path_for(backend.blockchain_file),
            recovered_from_backup=recovered_from_backup,
        )
        return report.to_dict()

    if isinstance(backend, SQLiteStorageBackend):
        details = []
        if not os.path.exists(backend.sqlite_db_path):
            return StorageIntegrityReport(
                backend="sqlite",
                healthy=True,
                details=["sqlite database missing; bootstrap expected"],
                main_path=backend.sqlite_db_path,
                backup_path=_backup_path_for(backend.sqlite_db_path),
            ).to_dict()

        sections = backend._load_sections(strict=True)
        details.append("sqlite database opened")
        details.append(f"storage sections present: {len(sections)}")
        report = StorageIntegrityReport(
            backend="sqlite",
            healthy=True,
            details=details,
            main_path=backend.sqlite_db_path,
            backup_path=_backup_path_for(backend.sqlite_db_path),
        )
        return report.to_dict()

    raise ValueError(f"Unsupported storage backend type: {type(backend)!r}.")


def create_storage_backend(name: str | None = None, **kwargs) -> StorageBackend:
    backend_name = (name or config.STORAGE_BACKEND or "json").strip().lower()
    if backend_name == "json":
        return JSONStorageBackend(**kwargs)
    if backend_name == "sqlite":
        return SQLiteStorageBackend(**kwargs)
    supported = ", ".join(sorted(SUPPORTED_STORAGE_BACKENDS))
    raise ValueError(
        f"Unsupported STORAGE_BACKEND value: {backend_name!r}. "
        f"Supported values: {supported}."
    )
