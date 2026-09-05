from __future__ import annotations

import json
import logging
import os
import sqlite3
import shutil
import tempfile
import time
from contextlib import contextmanager
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
    "access_requests",
    "access_accounts",
    "wallet_bindings",
    "allowlist_entries",
    "override_requests",
    "feedback_records",
    "audit_logs",
    "finality_attestations",
    "finalized_blocks",
    "peers",
)
_BLOCKCHAIN_JSON_REQUIRED_SECTIONS = tuple(
    section for section in _STORAGE_SECTIONS if section not in {"peers", "transfer_intents", "native_transactions", "finality_attestations", "finalized_blocks"}
)
_OPTIONAL_SQLITE_SECTIONS = {"content_objects"}

# These are deliberately storage-level names rather than public API statuses.
# A transaction's finality remains derived from its canonical block and the
# persisted finality evidence; it is not a peer-delivery status.
NATIVE_TRANSACTION_LIFECYCLE_STATES = (
    "signed_pending",
    "validated_pending",
    "mempool",
    "included",
    "settled",
    "finalized",
    "rejected",
    "failed",
    "expired",
)
NATIVE_TRANSACTION_ACTIVE_STATES = (
    "signed_pending",
    "validated_pending",
    "mempool",
    "included",
    "settled",
    "finalized",
)
_NATIVE_TRANSACTION_IMMUTABLE_FIELDS = (
    "tx_id", "transaction_type", "network", "transaction_version",
    "protocol_version", "network_id", "from_address", "to_address",
    "amount", "fee", "nonce", "timestamp", "memo", "signature",
    "signature_scheme", "signed_message", "signed_message_hash",
)


def _native_transaction_immutable_payload(transaction: dict[str, Any]) -> str:
    """Canonical signed identity used to reject conflicting tx_id replays."""
    return _canonical_record({field: transaction.get(field) for field in _NATIVE_TRANSACTION_IMMUTABLE_FIELDS})


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
    if section_name == "access_requests":
        return []
    if section_name == "access_accounts":
        return []
    if section_name == "wallet_bindings":
        return []
    if section_name == "allowlist_entries":
        return []
    if section_name == "override_requests":
        return []
    if section_name == "feedback_records":
        return []
    if section_name == "audit_logs":
        return []
    if section_name == "finality_attestations":
        return []
    if section_name == "finalized_blocks":
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


class StaleCanonicalHeadError(RuntimeError):
    """A prepared commit no longer extends the durable canonical head."""


class StorageUniquenessError(RuntimeError):
    """Durable canonical state attempted to reuse an immutable claim."""


def _normalized_claim_value(value: Any) -> str:
    return str(value or "").strip().lower()


def _canonical_record(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def canonical_document_claims(document: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Validate and project the immutable claims represented by a chain.

    JSON storage has no relational indexes, so this is its equivalent invariant
    check.  SQLite persists the returned projections in unique-indexed tables.
    Keeping the projection derived from the immutable canonical chain avoids a
    second source of truth for settlement or mint state.
    """
    claims = {"commits": [], "native_transactions": [], "rewards": []}
    seen_heights: set[Any] = set()
    seen_hashes: set[str] = set()
    seen_submissions: set[str] = set()
    seen_certificates: set[str] = set()
    seen_native_ids: set[str] = set()
    seen_nonces: set[tuple[str, str]] = set()
    seen_rewards: dict[str, str] = {}

    for block in list(document.get("chain", []) or []):
        if not isinstance(block, dict):
            raise StorageUniquenessError("Canonical chain contains a malformed block record.")
        height = block.get("index")
        block_hash = _normalized_claim_value(block.get("hash"))
        if height in seen_heights:
            raise StorageUniquenessError(f"Canonical block height {height!r} is duplicated.")
        if block_hash and block_hash in seen_hashes:
            raise StorageUniquenessError(f"Canonical block hash {block_hash} is duplicated.")
        seen_heights.add(height)
        if block_hash:
            seen_hashes.add(block_hash)

        submission_id = _normalized_claim_value(block.get("submission_id"))
        certificate_id = _normalized_claim_value(block.get("certificate_id"))
        if submission_id or certificate_id:
            if not submission_id or not certificate_id:
                raise StorageUniquenessError("Certified canonical block must retain submission and certificate identities.")
            if submission_id in seen_submissions:
                raise StorageUniquenessError(f"Submission {submission_id} is already minted in the canonical chain.")
            if certificate_id in seen_certificates:
                raise StorageUniquenessError(f"Certificate {certificate_id} is already consumed in the canonical chain.")
            seen_submissions.add(submission_id)
            seen_certificates.add(certificate_id)
            claims["commits"].append({
                "commit_identity": certificate_id,
                "submission_id": submission_id,
                "certificate_id": certificate_id,
                "block_hash": block_hash,
                "block_height": height,
                "content_hash": _normalized_claim_value(block.get("content_hash")),
                "creator_wallet": _normalized_claim_value(block.get("creator_wallet")),
            })

        for transaction in list(block.get("native_transactions", []) or []):
            if not isinstance(transaction, dict):
                raise StorageUniquenessError("Canonical block contains a malformed native transaction.")
            tx_id = _normalized_claim_value(transaction.get("tx_id"))
            sender = _normalized_claim_value(transaction.get("from_address"))
            nonce = str(transaction.get("nonce") or "").strip()
            if not tx_id or not sender or not nonce:
                raise StorageUniquenessError("Canonical native transaction is missing its immutable identity fields.")
            if tx_id in seen_native_ids:
                raise StorageUniquenessError(f"Native transaction {tx_id} is already settled in the canonical chain.")
            nonce_key = (sender, nonce)
            if nonce_key in seen_nonces:
                raise StorageUniquenessError(f"Native sender nonce {sender}:{nonce} is already settled in the canonical chain.")
            seen_native_ids.add(tx_id)
            seen_nonces.add(nonce_key)
            claims["native_transactions"].append({"tx_id": tx_id, "sender": sender, "nonce": nonce, "block_hash": block_hash, "block_height": height})

        if block.get("reward_type") == "meme_mining_reward" and submission_id:
            creator_reward_id = f"creator:{submission_id}"
            seen_rewards[creator_reward_id] = _canonical_record({"reward_recipient": block.get("reward_recipient"), "reward_amount": block.get("reward_amount"), "submission_id": submission_id})
            claims["rewards"].append({"reward_id": creator_reward_id, "reward_kind": "creator", "block_hash": block_hash, "block_height": height, "payload": seen_rewards[creator_reward_id]})
        for reward in list(block.get("voter_rewards", []) or []):
            if not isinstance(reward, dict):
                raise StorageUniquenessError("Canonical block contains malformed voter reward metadata.")
            reward_id = _normalized_claim_value(reward.get("reward_id"))
            if not reward_id:
                raise StorageUniquenessError("Canonical voter reward is missing reward_id.")
            payload = _canonical_record(reward)
            if reward_id in seen_rewards:
                if seen_rewards[reward_id] != payload:
                    raise StorageUniquenessError(f"Reward {reward_id} conflicts with an existing canonical reward.")
                raise StorageUniquenessError(f"Reward {reward_id} is already settled in the canonical chain.")
            seen_rewards[reward_id] = payload
            claims["rewards"].append({"reward_id": reward_id, "reward_kind": "voter", "block_hash": block_hash, "block_height": height, "payload": payload})
    return claims


def canonical_head_identity(document: dict[str, Any] | None) -> dict[str, Any]:
    """Return the durable tip identity used by the block-commit CAS guard."""
    chain = (document or {}).get("chain") or []
    if not chain:
        return {"height": None, "hash": None}
    head = chain[-1]
    return {"height": head.get("index"), "hash": head.get("hash")}


def _verify_expected_canonical_head(document: dict[str, Any], expected_head: dict[str, Any]) -> None:
    actual = canonical_head_identity(document)
    # The hash is authoritative; retaining height makes diagnostics and
    # backwards-compatible callers unambiguous.
    if expected_head.get("hash") != actual.get("hash") or expected_head.get("height") != actual.get("height"):
        raise StaleCanonicalHeadError(
            "The canonical head changed before this block could be committed "
            f"(expected {expected_head}, found {actual})."
        )


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

    def atomic_commit_blockchain_document(self, expected_head: dict[str, Any], mutate, replay=None):
        """Atomically compare the durable tip and replace the complete state.

        ``mutate`` receives a fresh, durable document and returns the complete
        replacement document.  ``replay`` may resolve an already committed
        logical operation under that same boundary before the head comparison.
        Backends override this so the read, comparison, mutation, and write are
        one recoverable persistence boundary.
        """
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

    # Focused durable-record interface.  JSON retains the existing document
    # implementation; SQLite overrides the read path with relational rows.
    def list_durable_native_transaction_records(self):
        return self.load_native_transactions()

    def get_durable_native_transaction_record(self, tx_id):
        return self.get_native_transaction(tx_id)

    def load_mempool_transactions(self):
        return self.list_mempool_transactions()

    def save_mempool_transactions(self, transactions) -> None:
        existing_transactions = list(self.load_native_transactions())
        existing_by_tx_id = {
            str(transaction.get("tx_id") or "").strip(): dict(transaction)
            for transaction in existing_transactions
            if isinstance(transaction, dict) and str(transaction.get("tx_id") or "").strip()
        }
        mempool_tx_ids = set()
        for transaction in transactions or []:
            if not isinstance(transaction, dict):
                continue
            tx_id = str(transaction.get("tx_id") or "").strip()
            if not tx_id:
                continue
            mempool_tx_ids.add(tx_id)
            updated_transaction = dict(existing_by_tx_id.get(tx_id, {}))
            updated_transaction.update(transaction)
            updated_transaction["status"] = "mempool"
            existing_by_tx_id[tx_id] = updated_transaction

        for tx_id, transaction in list(existing_by_tx_id.items()):
            if tx_id not in mempool_tx_ids and str(transaction.get("status") or "").strip().lower() == "mempool":
                updated_transaction = dict(transaction)
                updated_transaction["status"] = "validated_pending"
                existing_by_tx_id[tx_id] = updated_transaction

        self.save_native_transactions(list(existing_by_tx_id.values()))

    def add_transaction_to_mempool(self, transaction) -> None:
        if not isinstance(transaction, dict):
            raise ValueError("transaction must be an object.")
        tx_id = str(transaction.get("tx_id") or "").strip()
        if not tx_id:
            raise ValueError("transaction tx_id is required.")
        existing_transactions = list(self.load_native_transactions())
        updated = False
        for index, existing_transaction in enumerate(existing_transactions):
            if str(existing_transaction.get("tx_id") or "").strip() != tx_id:
                continue
            merged = dict(existing_transaction)
            merged.update(transaction)
            merged["status"] = "mempool"
            existing_transactions[index] = merged
            updated = True
            break
        if not updated:
            merged = dict(transaction)
            merged["status"] = "mempool"
            existing_transactions.append(merged)
        self.save_native_transactions(existing_transactions)

    def remove_transaction_from_mempool(self, tx_id) -> None:
        if not isinstance(tx_id, str) or not tx_id.strip():
            return
        existing_transactions = list(self.load_native_transactions())
        for index, existing_transaction in enumerate(existing_transactions):
            if str(existing_transaction.get("tx_id") or "").strip() != tx_id.strip():
                continue
            if str(existing_transaction.get("status") or "").strip().lower() == "mempool":
                updated_transaction = dict(existing_transaction)
                updated_transaction["status"] = "validated_pending"
                existing_transactions[index] = updated_transaction
                self.save_native_transactions(existing_transactions)
            return

    def get_mempool_transaction(self, tx_id):
        if not isinstance(tx_id, str) or not tx_id.strip():
            return None
        transaction = self.get_native_transaction(tx_id.strip())
        if transaction is None:
            return None
        if str(transaction.get("status") or "").strip().lower() != "mempool":
            return None
        return transaction

    def list_mempool_transactions(self):
        return [
            transaction
            for transaction in self.load_native_transactions()
            if str(self._record_value(transaction, "status") or "").strip().lower() == "mempool"
        ]

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
        canonical_document_claims(document)
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

    @contextmanager
    def _commit_lock(self):
        """Use an OS-held advisory lock, not a process-local mutex.

        The JSON backend writes by atomic replacement.  The separate lock file
        stays open while the durable document is reread and replaced, which
        prevents two node processes from both passing the expected-head check.
        """
        try:
            import msvcrt
        except ImportError:  # pragma: no cover - exercised on POSIX nodes
            msvcrt = None
            import fcntl

        lock_path = self.blockchain_file + ".commit.lock"
        os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            descriptor = None
        if descriptor is not None:
            try:
                os.write(descriptor, b"0")
            finally:
                os.close(descriptor)
        # A concurrent creator can expose the path a few instructions before
        # its one-byte lock region is written.
        for _ in range(100):
            if os.path.getsize(lock_path) >= 1:
                break
            time.sleep(0.001)
        with open(lock_path, "r+b") as handle:
            handle.seek(0)
            if msvcrt is not None:
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:  # pragma: no cover - exercised on POSIX nodes
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                handle.seek(0)
                if msvcrt is not None:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:  # pragma: no cover - exercised on POSIX nodes
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def atomic_commit_blockchain_document(self, expected_head: dict[str, Any], mutate, replay=None):
        with self._commit_lock():
            document = self._load_or_new_blockchain_document()
            if replay is not None and replay(deepcopy(document)):
                return document
            _verify_expected_canonical_head(document, expected_head)
            replacement = mutate(deepcopy(document))
            self.save_blockchain_document(replacement)
            return replacement

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
            "SQLite backend selected. Native transaction records use relational durable storage."
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
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS native_transaction_records (
                    tx_id TEXT PRIMARY KEY,
                    immutable_payload TEXT NOT NULL,
                    transaction_json TEXT NOT NULL,
                    transaction_type TEXT,
                    network TEXT,
                    transaction_version INTEGER,
                    protocol_version INTEGER,
                    network_id TEXT,
                    sender TEXT NOT NULL,
                    recipient TEXT,
                    amount TEXT,
                    fee TEXT,
                    nonce TEXT NOT NULL,
                    transaction_timestamp TEXT,
                    memo TEXT,
                    signature TEXT,
                    signature_scheme TEXT,
                    signed_message TEXT,
                    signed_message_hash TEXT,
                    lifecycle_state TEXT NOT NULL CHECK (lifecycle_state IN ({', '.join(repr(state) for state in NATIVE_TRANSACTION_LIFECYCLE_STATES)})),
                    rejection_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    admitted_at TEXT,
                    included_block_hash TEXT,
                    included_block_height INTEGER,
                    settled_at TEXT
                )
                """
            )
            connection.execute(
                f"""
                CREATE UNIQUE INDEX IF NOT EXISTS active_native_transaction_sender_nonce
                ON native_transaction_records(sender, nonce)
                WHERE lifecycle_state IN ({', '.join(repr(state) for state in NATIVE_TRANSACTION_ACTIVE_STATES)})
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS native_transaction_lifecycle_transitions (
                    tx_id TEXT NOT NULL,
                    transition_sequence INTEGER NOT NULL,
                    from_state TEXT,
                    to_state TEXT NOT NULL,
                    transitioned_at TEXT NOT NULL,
                    rejection_reason TEXT,
                    PRIMARY KEY (tx_id, transition_sequence),
                    FOREIGN KEY (tx_id) REFERENCES native_transaction_records(tx_id)
                )
                """
            )
            # SQLite performs this check even if a caller bypasses the Python
            # lifecycle service.  Canonical inclusion is allowed to override a
            # prior local rejection because canonical chain contents remain the
            # settlement source of truth.
            connection.execute(
                """
                CREATE TRIGGER IF NOT EXISTS native_transaction_lifecycle_guard
                BEFORE UPDATE OF lifecycle_state ON native_transaction_records
                WHEN NOT (
                    NEW.lifecycle_state = OLD.lifecycle_state OR
                    (OLD.lifecycle_state = 'signed_pending' AND NEW.lifecycle_state IN ('validated_pending', 'mempool', 'settled', 'rejected', 'failed', 'expired')) OR
                    (OLD.lifecycle_state = 'validated_pending' AND NEW.lifecycle_state IN ('mempool', 'settled', 'rejected', 'failed', 'expired')) OR
                    (OLD.lifecycle_state = 'mempool' AND NEW.lifecycle_state IN ('validated_pending', 'settled', 'rejected', 'failed', 'expired')) OR
                    (OLD.lifecycle_state = 'included' AND NEW.lifecycle_state IN ('settled', 'validated_pending', 'finalized')) OR
                    (OLD.lifecycle_state = 'settled' AND NEW.lifecycle_state IN ('validated_pending', 'finalized')) OR
                    (OLD.lifecycle_state = 'rejected' AND NEW.lifecycle_state = 'settled')
                )
                BEGIN
                    SELECT RAISE(ABORT, 'illegal native transaction lifecycle transition');
                END
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS certified_commit_claims (
                    commit_identity TEXT PRIMARY KEY,
                    submission_id TEXT NOT NULL UNIQUE,
                    certificate_id TEXT NOT NULL UNIQUE,
                    block_hash TEXT NOT NULL UNIQUE,
                    block_height INTEGER NOT NULL UNIQUE,
                    content_hash TEXT NOT NULL,
                    creator_wallet TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS canonical_native_transaction_claims (
                    tx_id TEXT PRIMARY KEY,
                    sender TEXT NOT NULL,
                    nonce TEXT NOT NULL,
                    block_hash TEXT NOT NULL,
                    block_height INTEGER NOT NULL,
                    UNIQUE(sender, nonce)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS canonical_reward_claims (
                    reward_id TEXT PRIMARY KEY,
                    reward_kind TEXT NOT NULL,
                    block_hash TEXT NOT NULL,
                    block_height INTEGER NOT NULL,
                    payload TEXT NOT NULL
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
            sections = self._load_sections_from_connection(connection, strict=False, include_native_records=False)
            self._synchronize_canonical_claims(connection, sections)
            sections["native_transactions"] = self._synchronize_native_transaction_records(
                connection, sections["native_transactions"]
            )
            self._save_sections_to_connection(connection, sections)

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
            defaults["native_transactions"] = self._load_native_transaction_records(connection, strict=strict)
        return defaults

    def _load_sections_from_connection(self, connection, *, strict: bool = True, include_native_records: bool = True) -> dict[str, Any]:
        defaults = {section: deepcopy(_default_section_value(section)) for section in _STORAGE_SECTIONS}
        rows = connection.execute("SELECT section_name, json_data FROM storage_sections").fetchall()
        seen_sections = set()
        for section_name, json_data_value in rows:
            if section_name in defaults:
                seen_sections.add(section_name)
                defaults[section_name] = _json_loads_or_default(
                    json_data_value, _default_section_value(section_name), strict=strict,
                    label=f"SQLite section {section_name}",
                )
        missing_sections = [section for section in _STORAGE_SECTIONS if section not in seen_sections and section not in _OPTIONAL_SQLITE_SECTIONS]
        if missing_sections and strict:
            raise StorageCorruptionError("SQLite storage is missing required sections: " + ", ".join(missing_sections))
        if include_native_records:
            defaults["native_transactions"] = self._load_native_transaction_records(connection, strict=strict)
        return defaults

    @staticmethod
    def _native_record_from_row(row, *, strict: bool) -> dict[str, Any]:
        try:
            record = json.loads(row[0])
        except (TypeError, json.JSONDecodeError) as exc:
            if strict:
                raise StorageCorruptionError("Malformed JSON stored in SQLite native transaction record.") from exc
            return {}
        if not isinstance(record, dict):
            if strict:
                raise StorageCorruptionError("SQLite native transaction record must be an object.")
            return {}
        return record

    @staticmethod
    def _load_native_transaction_records(connection, *, strict: bool) -> list[dict[str, Any]]:
        try:
            rows = connection.execute(
                "SELECT transaction_json FROM native_transaction_records ORDER BY created_at, tx_id"
            ).fetchall()
        except sqlite3.Error as exc:
            if strict:
                raise StorageCorruptionError("Failed to read SQLite native transaction records.") from exc
            return []
        records = [SQLiteStorageBackend._native_record_from_row(row, strict=strict) for row in rows]
        return [record for record in records if record]

    @staticmethod
    def _native_record_values(transaction: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(transaction, dict):
            raise StorageCorruptionError("Native transaction record must be an object.")
        tx_id = str(transaction.get("tx_id") or "").strip().lower()
        sender = str(transaction.get("from_address") or "").strip().lower()
        nonce = str(transaction.get("nonce") or "").strip()
        status = str(transaction.get("status") or "signed_pending").strip().lower()
        if not tx_id or not sender or not nonce:
            raise StorageCorruptionError("Native transaction record is missing tx_id, sender, or nonce.")
        if status not in NATIVE_TRANSACTION_LIFECYCLE_STATES:
            raise StorageCorruptionError(f"Native transaction record has unknown lifecycle state: {status}.")
        created_at = str(transaction.get("created_at") or transaction.get("timestamp") or _utc_now_iso())
        updated_at = str(transaction.get("updated_at") or created_at)
        return {
            "tx_id": tx_id,
            "immutable_payload": _native_transaction_immutable_payload(transaction),
            "transaction_json": _canonical_record(transaction),
            "transaction_type": transaction.get("transaction_type"),
            "network": transaction.get("network"),
            "transaction_version": transaction.get("transaction_version"),
            "protocol_version": transaction.get("protocol_version"),
            "network_id": transaction.get("network_id"),
            "sender": sender,
            "recipient": transaction.get("to_address"),
            "amount": transaction.get("amount"),
            "fee": transaction.get("fee"),
            "nonce": nonce,
            "transaction_timestamp": transaction.get("timestamp"),
            "memo": transaction.get("memo"),
            "signature": transaction.get("signature"),
            "signature_scheme": transaction.get("signature_scheme"),
            "signed_message": transaction.get("signed_message"),
            "signed_message_hash": transaction.get("signed_message_hash"),
            "lifecycle_state": status,
            "rejection_reason": transaction.get("rejection_reason"),
            "created_at": created_at,
            "updated_at": updated_at,
            "admitted_at": transaction.get("admitted_at"),
            "included_block_hash": transaction.get("included_block_hash"),
            "included_block_height": transaction.get("included_block_height"),
            "settled_at": transaction.get("settled_at"),
        }

    @classmethod
    def _upsert_native_transaction_record(cls, connection, transaction: dict[str, Any]) -> None:
        values = cls._native_record_values(transaction)
        existing = connection.execute(
            "SELECT immutable_payload, lifecycle_state FROM native_transaction_records WHERE tx_id = ?",
            (values["tx_id"],),
        ).fetchone()
        if existing is not None and existing[0] != values["immutable_payload"]:
            raise StorageUniquenessError(
                f"Native transaction {values['tx_id']} conflicts with its durable signed identity."
            )
        if existing is None:
            columns = ", ".join(values)
            placeholders = ", ".join(f":{column}" for column in values)
            connection.execute(
                f"INSERT INTO native_transaction_records ({columns}) VALUES ({placeholders})", values
            )
            connection.execute(
                """INSERT INTO native_transaction_lifecycle_transitions
                   (tx_id, transition_sequence, from_state, to_state, transitioned_at, rejection_reason)
                   VALUES (?, 1, NULL, ?, ?, ?)""",
                (values["tx_id"], values["lifecycle_state"], values["created_at"], values["rejection_reason"]),
            )
            return
        assignments = ", ".join(f"{column} = :{column}" for column in values if column != "tx_id")
        connection.execute(
            f"UPDATE native_transaction_records SET {assignments} WHERE tx_id = :tx_id", values
        )
        if existing[1] != values["lifecycle_state"]:
            sequence = connection.execute(
                "SELECT COALESCE(MAX(transition_sequence), 0) + 1 FROM native_transaction_lifecycle_transitions WHERE tx_id = ?",
                (values["tx_id"],),
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO native_transaction_lifecycle_transitions
                   (tx_id, transition_sequence, from_state, to_state, transitioned_at, rejection_reason)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (values["tx_id"], sequence, existing[1], values["lifecycle_state"], values["updated_at"], values["rejection_reason"]),
            )

    @classmethod
    def _synchronize_native_transaction_records(cls, connection, transactions) -> list[dict[str, Any]]:
        source_transactions = list(transactions or [])
        source_ids = []
        for transaction in source_transactions:
            if not isinstance(transaction, dict):
                raise StorageCorruptionError("Native transaction record must be an object.")
            tx_id = str(transaction.get("tx_id") or "").strip().lower()
            if not tx_id:
                raise StorageCorruptionError("Native transaction record is missing tx_id, sender, or nonce.")
            source_ids.append(tx_id)
        # Remove records absent from this complete document before inserting a
        # replacement. This preserves the established load-time repair behavior
        # for deliberately corrupted legacy snapshots while remaining atomic.
        if source_ids:
            placeholders = ", ".join("?" for _ in source_ids)
            connection.execute(f"DELETE FROM native_transaction_records WHERE tx_id NOT IN ({placeholders})", tuple(source_ids))
        else:
            connection.execute("DELETE FROM native_transaction_records")

        seen: set[str] = set()
        normalized: list[dict[str, Any]] = []
        for transaction in source_transactions:
            values = cls._native_record_values(transaction)
            if values["tx_id"] in seen:
                existing = next(item for item in normalized if str(item.get("tx_id") or "").strip().lower() == values["tx_id"])
                if _native_transaction_immutable_payload(existing) != values["immutable_payload"]:
                    raise StorageUniquenessError(f"Native transaction {values['tx_id']} appears with conflicting signed payloads.")
                continue
            seen.add(values["tx_id"])
            cls._upsert_native_transaction_record(connection, transaction)
            normalized.append(dict(transaction))
        return cls._load_native_transaction_records(connection, strict=True)

    @staticmethod
    def _save_sections_to_connection(connection, sections: dict[str, Any]) -> None:
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

    @staticmethod
    def _synchronize_canonical_claims(connection, document: dict[str, Any]) -> None:
        claims = canonical_document_claims(document)
        connection.execute("DELETE FROM certified_commit_claims")
        connection.execute("DELETE FROM canonical_native_transaction_claims")
        connection.execute("DELETE FROM canonical_reward_claims")
        connection.executemany(
            """INSERT INTO certified_commit_claims
               (commit_identity, submission_id, certificate_id, block_hash, block_height, content_hash, creator_wallet)
               VALUES (:commit_identity, :submission_id, :certificate_id, :block_hash, :block_height, :content_hash, :creator_wallet)""",
            claims["commits"],
        )
        connection.executemany(
            """INSERT INTO canonical_native_transaction_claims
               (tx_id, sender, nonce, block_hash, block_height)
               VALUES (:tx_id, :sender, :nonce, :block_hash, :block_height)""",
            claims["native_transactions"],
        )
        connection.executemany(
            """INSERT INTO canonical_reward_claims
               (reward_id, reward_kind, block_hash, block_height, payload)
               VALUES (:reward_id, :reward_kind, :block_hash, :block_height, :payload)""",
            claims["rewards"],
        )

    def _save_sections(self, sections: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._synchronize_canonical_claims(connection, sections)
            sections["native_transactions"] = self._synchronize_native_transaction_records(
                connection, sections.get("native_transactions", [])
            )
            self._save_sections_to_connection(connection, sections)

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
            "access_requests": sections["access_requests"],
            "access_accounts": sections["access_accounts"],
            "wallet_bindings": sections["wallet_bindings"],
            "allowlist_entries": sections["allowlist_entries"],
            "override_requests": sections["override_requests"],
            "feedback_records": sections["feedback_records"],
            "audit_logs": sections["audit_logs"],
            "finality_attestations": sections["finality_attestations"],
            "finalized_blocks": sections["finalized_blocks"],
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

    def atomic_commit_blockchain_document(self, expected_head: dict[str, Any], mutate, replay=None):
        # BEGIN IMMEDIATE obtains SQLite's reserved write lock before reading
        # the head, so separate processes cannot both win the compare-and-swap.
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            sections = self._load_sections_from_connection(connection)
            document = {section: sections[section] for section in _STORAGE_SECTIONS}
            if replay is not None and replay(deepcopy(document)):
                return document
            _verify_expected_canonical_head(document, expected_head)
            replacement = self._normalize_blockchain_document(mutate(deepcopy(document)))
            self._synchronize_canonical_claims(connection, replacement)
            replacement["native_transactions"] = self._synchronize_native_transaction_records(
                connection, replacement.get("native_transactions", [])
            )
            self._save_sections_to_connection(connection, replacement)
            return replacement

    def list_durable_native_transaction_records(self):
        with self._connect() as connection:
            return self._load_native_transaction_records(connection, strict=True)

    def get_durable_native_transaction_record(self, tx_id):
        normalized = str(tx_id or "").strip().lower()
        if not normalized:
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT transaction_json FROM native_transaction_records WHERE tx_id = ?", (normalized,)
            ).fetchone()
            return self._native_record_from_row(row, strict=True) if row else None

    def list_native_transaction_lifecycle_transitions(self, tx_id):
        normalized = str(tx_id or "").strip().lower()
        if not normalized:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT transition_sequence, from_state, to_state, transitioned_at, rejection_reason
                   FROM native_transaction_lifecycle_transitions WHERE tx_id = ? ORDER BY transition_sequence""",
                (normalized,),
            ).fetchall()
        return [
            {"transition_sequence": row[0], "from_state": row[1], "to_state": row[2], "transitioned_at": row[3], "rejection_reason": row[4]}
            for row in rows
        ]

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
