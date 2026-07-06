from __future__ import annotations

import json
import logging
import os
import sqlite3
from abc import ABC, abstractmethod
from copy import deepcopy
from datetime import datetime, timezone
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


def _json_loads_or_default(value, default):
    if value in (None, ""):
        return deepcopy(default)
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return deepcopy(default)


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
        if os.path.exists(self.blockchain_file):
            os.remove(self.blockchain_file)

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
    def load_blockchain_document(self) -> dict[str, Any] | None:
        if not os.path.exists(self.blockchain_file):
            return None

        try:
            with open(self.blockchain_file, "r", encoding="utf-8") as blockchain_file:
                document = json.load(blockchain_file)
        except (json.JSONDecodeError, OSError):
            return None

        if not isinstance(document, dict):
            return None

        return document

    def save_blockchain_document(self, document: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self.blockchain_file) or ".", exist_ok=True)
        with open(self.blockchain_file, "w", encoding="utf-8") as blockchain_file:
            json.dump(document, blockchain_file, indent=4)

    def load_peers(self):
        if not os.path.exists(self.peers_file):
            return []

        try:
            with open(self.peers_file, "r", encoding="utf-8") as peer_file:
                peers = json.load(peer_file)
        except (json.JSONDecodeError, OSError):
            return []

        if not isinstance(peers, list):
            return []

        return peers

    def save_peers(self, peers) -> None:
        os.makedirs(os.path.dirname(self.peers_file) or ".", exist_ok=True)
        with open(self.peers_file, "w", encoding="utf-8") as peer_file:
            json.dump(peers, peer_file, indent=4)


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
        if os.path.exists(self.sqlite_db_path):
            os.remove(self.sqlite_db_path)

    def _connect(self):
        return sqlite3.connect(self.sqlite_db_path)

    def _initialize_database(self) -> None:
        os.makedirs(os.path.dirname(self.sqlite_db_path) or ".", exist_ok=True)
        with self._connect() as connection:
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
            connection.commit()

    def _load_sections(self) -> dict[str, Any]:
        defaults = {section: deepcopy(_default_section_value(section)) for section in _STORAGE_SECTIONS}
        if not os.path.exists(self.sqlite_db_path):
            return defaults

        with self._connect() as connection:
            cursor = connection.execute(
                "SELECT section_name, json_data FROM storage_sections"
            )
            for section_name, json_data_value in cursor.fetchall():
                if section_name in defaults:
                    defaults[section_name] = _json_loads_or_default(
                        json_data_value,
                        _default_section_value(section_name),
                    )
        return defaults

    def _save_sections(self, sections: dict[str, Any]) -> None:
        with self._connect() as connection:
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
            connection.commit()

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
