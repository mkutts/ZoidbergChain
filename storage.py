from __future__ import annotations

import json
import logging
import os
import sqlite3
import shutil
import tempfile
import time
from abc import ABC, abstractmethod
from copy import deepcopy
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import config
from content import ContentObject, content_object_from_submission_data, verify_content_object_payload


SUPPORTED_STORAGE_BACKENDS = {"json", "sqlite"}
_STORAGE_SECTIONS = (
    "chain",
    "wallets",
    "submissions",
    "content_objects",
    "mint_queue",
    "votes",
    "transfer_intents",
    "native_transactions",
    "originality_certificates",
    "peers",
)
_BLOCKCHAIN_JSON_REQUIRED_SECTIONS = tuple(
    section for section in _STORAGE_SECTIONS if section not in {"peers", "transfer_intents", "native_transactions"}
)
_OPTIONAL_SQLITE_SECTIONS = {"content_objects"}


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def _default_section_value(section_name):
    if section_name == "chain":
        return []
    if section_name == "wallets":
        return {}
    if section_name == "submissions":
        return []
    if section_name == "content_objects":
        return []
    if section_name == "mint_queue":
        return []
    if section_name == "votes":
        return []
    if section_name == "transfer_intents":
        return []
    if section_name == "native_transactions":
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

        last_error = None
        for attempt in range(3):
            try:
                os.replace(temp_path, path)
                last_error = None
                break
            except PermissionError as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.05 * (attempt + 1))
                else:
                    raise

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
        provided_blockchain_file = blockchain_file
        provided_peers_file = peers_file
        provided_sqlite_db_path = sqlite_db_path
        self.blockchain_file = blockchain_file or config.BLOCKCHAIN_FILE
        self.peers_file = peers_file or config.PEERS_FILE
        self.sqlite_db_path = sqlite_db_path or config.SQLITE_DB_PATH
        self.data_dir = self._resolve_data_dir(
            blockchain_file=provided_blockchain_file,
            peers_file=provided_peers_file,
            sqlite_db_path=provided_sqlite_db_path,
        )

    def _resolve_data_dir(
        self,
        *,
        blockchain_file: str | None,
        peers_file: str | None,
        sqlite_db_path: str | None,
    ) -> str:
        if blockchain_file:
            return str(Path(blockchain_file).parent)
        if peers_file:
            return str(Path(peers_file).parent)
        if sqlite_db_path:
            return str(Path(self.sqlite_db_path).parent)
        if self.blockchain_file:
            return str(Path(self.blockchain_file).parent)
        return str(Path(config.DATA_DIR))

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

    @staticmethod
    def _record_value(record: Any, field_name: str) -> Any:
        if isinstance(record, dict):
            return record.get(field_name)
        return getattr(record, field_name, None)

    @classmethod
    def _first_record_where(cls, records, field_name: str, field_value: Any):
        if not records:
            return None
        for record in records:
            if cls._record_value(record, field_name) == field_value:
                return record
        return None

    @classmethod
    def _records_where(cls, records, field_name: str, field_value: Any):
        if not records:
            return []
        return [
            record
            for record in records
            if cls._record_value(record, field_name) == field_value
        ]

    def load_wallets(self):
        document = self.load_blockchain_document()
        if not document:
            return {}
        return document.get("wallets", {})

    def save_wallets(self, wallets) -> None:
        document = self._load_or_new_blockchain_document()
        document["wallets"] = wallets
        self.save_blockchain_document(document)

    def get_wallet(self, public_key, wallets=None):
        if not isinstance(public_key, str) or not public_key.strip():
            return None
        wallets = self.load_wallets() if wallets is None else wallets
        public_key = public_key.strip()
        if isinstance(wallets, dict):
            return wallets.get(public_key)
        return self._first_record_where(wallets, "public_key", public_key)

    def load_submissions(self):
        document = self.load_blockchain_document()
        if not document:
            return []
        return document.get("submissions", [])

    def save_submissions(self, submissions) -> None:
        document = self._load_or_new_blockchain_document()
        document["submissions"] = submissions
        self.save_blockchain_document(document)

    def load_content_objects(self):
        document = self.load_blockchain_document()
        if not document:
            return []
        content_objects = list(document.get("content_objects", []) or [])
        seen_hashes: set[str] = {
            content_object.get("content_hash")
            for content_object in content_objects
            if isinstance(content_object, dict) and isinstance(content_object.get("content_hash"), str)
        }

        submissions = document.get("submissions", []) or []
        for submission in submissions:
            content_hash = self._record_value(submission, "content_hash")
            if not isinstance(content_hash, str) or not content_hash.strip():
                continue
            normalized_hash = content_hash.strip()
            if normalized_hash in seen_hashes:
                continue
            try:
                content_object = content_object_from_submission_data(
                    submission if isinstance(submission, dict) else getattr(submission, "to_dict", lambda: {})(),
                    network_name=config.NETWORK_NAME,
                    data_dir=self.data_dir,
                )
            except ValueError:
                continue
            content_objects.append(content_object.to_dict())
            seen_hashes.add(normalized_hash)
        return content_objects

    def save_content_objects(self, content_objects) -> None:
        document = self._load_or_new_blockchain_document()
        document["content_objects"] = [
            content_object.to_dict() if isinstance(content_object, ContentObject) else content_object
            for content_object in content_objects or []
        ]
        self.save_blockchain_document(document)

    def get_content_object(self, content_id, content_objects=None):
        if not isinstance(content_id, str) or not content_id.strip():
            return None
        content_objects = self.load_content_objects() if content_objects is None else content_objects
        return self._first_record_where(content_objects, "content_id", content_id.strip())

    def get_content_object_by_hash(self, content_hash, content_objects=None):
        if not isinstance(content_hash, str) or not content_hash.strip():
            return None
        content_objects = self.load_content_objects() if content_objects is None else content_objects
        return self._first_record_where(content_objects, "content_hash", content_hash.strip())

    def list_content_objects(self, status=None, content_objects=None):
        content_objects = self.load_content_objects() if content_objects is None else content_objects
        if status is None:
            return list(content_objects or [])
        return [
            content_object
            for content_object in (content_objects or [])
            if self._record_value(content_object, "storage_status") == status
        ]

    def get_submission(self, submission_id, submissions=None):
        if not isinstance(submission_id, str) or not submission_id.strip():
            return None
        submissions = self.load_submissions() if submissions is None else submissions
        return self._first_record_where(submissions, "submission_id", submission_id.strip())

    def get_submission_by_content_hash(self, content_hash, submissions=None):
        if not isinstance(content_hash, str) or not content_hash.strip():
            return None
        submissions = self.load_submissions() if submissions is None else submissions
        return self._first_record_where(submissions, "content_hash", content_hash.strip())

    def list_submissions(self, submissions=None, status=None):
        submissions = self.load_submissions() if submissions is None else submissions
        if status is None:
            return list(submissions or [])
        return [
            submission
            for submission in (submissions or [])
            if self._record_value(submission, "status") == status
        ]

    def load_mint_queue(self):
        document = self.load_blockchain_document()
        if not document:
            return []
        return document.get("mint_queue", [])

    def save_mint_queue(self, mint_queue) -> None:
        document = self._load_or_new_blockchain_document()
        document["mint_queue"] = mint_queue
        self.save_blockchain_document(document)

    def mint_queue_contains(self, submission_id, mint_queue=None) -> bool:
        if not isinstance(submission_id, str) or not submission_id.strip():
            return False
        mint_queue = self.load_mint_queue() if mint_queue is None else mint_queue
        return submission_id.strip() in list(mint_queue or [])

    def load_votes(self):
        document = self.load_blockchain_document()
        if not document:
            return []
        return document.get("votes", [])

    def save_votes(self, votes) -> None:
        document = self._load_or_new_blockchain_document()
        document["votes"] = votes
        self.save_blockchain_document(document)

    def get_vote(self, submission_id, voter, votes=None):
        if not isinstance(submission_id, str) or not submission_id.strip():
            return None
        if not isinstance(voter, str) or not voter.strip():
            return None
        votes = self.load_votes() if votes is None else votes
        submission_id = submission_id.strip()
        voter = voter.strip()
        for vote in votes or []:
            if self._record_value(vote, "submission_id") == submission_id and self._record_value(vote, "voter") == voter:
                return vote
        return None

    def get_votes_for_submission(self, submission_id, votes=None):
        if not isinstance(submission_id, str) or not submission_id.strip():
            return []
        votes = self.load_votes() if votes is None else votes
        return self._records_where(votes, "submission_id", submission_id.strip())

    def load_transfer_intents(self):
        document = self.load_blockchain_document()
        if not document:
            return []
        return document.get("transfer_intents", [])

    def save_transfer_intents(self, transfer_intents) -> None:
        document = self._load_or_new_blockchain_document()
        document["transfer_intents"] = transfer_intents
        self.save_blockchain_document(document)

    def get_transfer_intent(self, transfer_id, transfer_intents=None):
        if not isinstance(transfer_id, str) or not transfer_id.strip():
            return None
        transfer_intents = self.load_transfer_intents() if transfer_intents is None else transfer_intents
        return self._first_record_where(transfer_intents, "transfer_id", transfer_id.strip())

    def load_native_transactions(self):
        document = self.load_blockchain_document()
        if not document:
            return []
        return document.get("native_transactions", [])

    def save_native_transactions(self, native_transactions) -> None:
        document = self._load_or_new_blockchain_document()
        document["native_transactions"] = native_transactions
        self.save_blockchain_document(document)

    def get_native_transaction(self, tx_id, native_transactions=None):
        if not isinstance(tx_id, str) or not tx_id.strip():
            return None
        native_transactions = self.load_native_transactions() if native_transactions is None else native_transactions
        return self._first_record_where(native_transactions, "tx_id", tx_id.strip())

    def load_certificates(self):
        document = self.load_blockchain_document()
        if not document:
            return []
        return document.get("originality_certificates", [])

    def save_certificates(self, certificates) -> None:
        document = self._load_or_new_blockchain_document()
        document["originality_certificates"] = certificates
        self.save_blockchain_document(document)

    def get_certificate(self, certificate_id, certificates=None):
        if not isinstance(certificate_id, str) or not certificate_id.strip():
            return None
        certificates = self.load_certificates() if certificates is None else certificates
        return self._first_record_where(certificates, "certificate_id", certificate_id.strip())

    def get_certificate_for_submission(self, submission_id, certificates=None):
        if not isinstance(submission_id, str) or not submission_id.strip():
            return None
        certificates = self.load_certificates() if certificates is None else certificates
        return self._first_record_where(certificates, "submission_id", submission_id.strip())

    def load_blockchain_state(self):
        document = self.load_blockchain_document()
        if document is None:
            return None
        state = deepcopy(document)
        state["content_objects"] = self.load_content_objects()
        return state

    def save_blockchain_state(self, state: dict[str, Any]) -> None:
        self.save_blockchain_document(state)

    def get_block_by_hash(self, block_hash, chain=None):
        if not isinstance(block_hash, str) or not block_hash.strip():
            return None
        chain = self.load_chain() if chain is None else chain
        return self._first_record_where(chain, "hash", block_hash.strip())

    def get_block_by_height(self, height, chain=None):
        if height is None:
            return None
        chain = self.load_chain() if chain is None else chain
        for block in chain or []:
            if self._record_value(block, "index") == height:
                return block
        return None

    def count_active_users(
        self,
        *,
        submissions=None,
        votes=None,
        pending_transactions=None,
        chain=None,
        lookback_days: int = 7,
        now=None,
    ) -> int:
        if now is None:
            now_timestamp = datetime.now(timezone.utc).timestamp()
        elif isinstance(now, datetime):
            now_timestamp = now.timestamp()
        else:
            now_timestamp = float(now)
        cutoff = now_timestamp - (lookback_days * 24 * 60 * 60)
        active_wallets = set()

        for submission in submissions if submissions is not None else self.load_submissions():
            created_at = self._record_value(submission, "created_at") or 0
            if created_at >= cutoff:
                submitter = self._record_value(submission, "submitter")
                if submitter:
                    active_wallets.add(submitter)

        for vote in votes if votes is not None else self.load_votes():
            created_at = self._record_value(vote, "created_at") or 0
            if created_at >= cutoff:
                voter = self._record_value(vote, "voter")
                if voter:
                    active_wallets.add(voter)

        for transaction in pending_transactions or []:
            created_at = self._record_value(transaction, "created_at") or 0
            sender = self._record_value(transaction, "sender")
            if created_at >= cutoff and sender not in {"GENESIS", "REWARD_POOL"}:
                active_wallets.add(sender)

        for block in chain if chain is not None else self.load_chain():
            for transaction in self._record_value(block, "transactions") or []:
                created_at = self._record_value(transaction, "created_at") or 0
                sender = self._record_value(transaction, "sender")
                if created_at >= cutoff and sender not in {"GENESIS", "REWARD_POOL"}:
                    active_wallets.add(sender)

        return len(active_wallets)

    @abstractmethod
    def load_peers(self):
        raise NotImplementedError

    @abstractmethod
    def save_peers(self, peers) -> None:
        raise NotImplementedError

    def get_peer(self, node_id, peers=None):
        if not isinstance(node_id, str) or not node_id.strip():
            return None
        peers = self.load_peers() if peers is None else peers
        return self._first_record_where(peers, "node_id", node_id.strip())

    def list_active_peers(self, peers=None, network_name=None):
        peers = self.load_peers() if peers is None else peers
        active_peers = [
            peer
            for peer in peers or []
            if self._record_value(peer, "status") == "active"
        ]
        if network_name:
            active_peers = [
                peer
                for peer in active_peers
                if self._record_value(peer, "network_name") == network_name
            ]
        return active_peers

    def _load_or_new_blockchain_document(self) -> dict[str, Any]:
        document = self.load_blockchain_document()
        if isinstance(document, dict):
            return self._normalize_blockchain_document(document)
        return {}

    @staticmethod
    def _normalize_blockchain_document(document: dict[str, Any]) -> dict[str, Any]:
        normalized = deepcopy(document)
        for section_name in _STORAGE_SECTIONS:
            normalized.setdefault(section_name, _default_section_value(section_name))
        return normalized


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
        document = self._normalize_blockchain_document(document)
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

            missing_sections = [
                section
                for section in _STORAGE_SECTIONS
                if section not in seen_sections and section not in _OPTIONAL_SQLITE_SECTIONS
            ]
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
            "content_objects": sections["content_objects"],
            "mint_queue": sections["mint_queue"],
            "votes": sections["votes"],
            "transfer_intents": sections["transfer_intents"],
            "native_transactions": sections["native_transactions"],
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

    def _content_integrity_details() -> tuple[list[str], bool]:
        details: list[str] = []
        healthy = True
        for payload in backend.load_content_objects():
            try:
                content_object = ContentObject.from_dict(payload)
            except ValueError as exc:
                details.append(f"content object unreadable: {exc}")
                healthy = False
                continue

            verification = verify_content_object_payload(content_object, data_dir=backend.data_dir)
            if verification["verified"]:
                details.append(f"content verified: {content_object.content_hash}")
                continue
            if verification["error"] == "legacy_unverifiable":
                details.append(f"warning: content legacy/unverifiable: {content_object.content_hash}")
                continue
            if (
                verification["error"] == "missing_file"
                and content_object.storage_status in {"missing", "remote"}
            ):
                details.append(f"warning: content missing locally: {content_object.content_hash}")
                continue
            if verification["error"] in {"missing_file", "hash_mismatch", "malformed_hash", "file_size_mismatch"}:
                healthy = False
            details.append(
                f"content issue ({verification['error']}): {content_object.content_hash}"
            )
        return details, healthy

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

        content_details, content_healthy = _content_integrity_details()
        details.extend(content_details)

        report = StorageIntegrityReport(
            backend="json",
            healthy=content_healthy,
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
        content_details, content_healthy = _content_integrity_details()
        details.extend(content_details)
        report = StorageIntegrityReport(
            backend="sqlite",
            healthy=content_healthy,
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
