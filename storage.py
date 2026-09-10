from __future__ import annotations

import json
import hashlib
import logging
import os
import sqlite3
import shutil
import tempfile
import time
import secrets
from contextlib import contextmanager
from abc import ABC, abstractmethod
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import config
from content import ContentObject, content_object_from_submission_data, verify_content_object_payload
from milestone5_policy import (
    REVIEWER_POLICY_VERSION,
    REPUTATION_RULE_VERSION,
    bootstrap_established_reviewers,
    reputation_rules,
    reviewer_policy,
    validate_reviewer_status,
)
from native_transfer import normalize_wallet_address
from protocol_v1_originality import calculate_signed_vote_identity
from originality import CERTIFICATE_EVIDENCE_PROFILE, validate_originality_evidence


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
    "originality_evidence",
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
    section for section in _STORAGE_SECTIONS if section not in {"peers", "transfer_intents", "native_transactions", "finality_attestations", "finalized_blocks", "originality_evidence"}
)
# Native records are authoritative in ``native_transaction_records`` for the
# SQLite backend.  Keeping a second, whole-mempool JSON copy in
# ``storage_sections`` was legacy compatibility residue: it was never read
# (the relational records replace it on load), yet every admission rewrote it.
_OPTIONAL_SQLITE_SECTIONS = {"content_objects", "native_transactions", "originality_evidence"}

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
NATIVE_TRANSACTION_OUTBOX_STATES = (
    "queued",
    "in_flight",
    "retry_wait",
    "acknowledged",
    "permanent_failure",
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
    if section_name == "originality_evidence":
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


def _canonical_reference(height: Any, block_hash: Any) -> tuple[int | None, str | None]:
    if height is None and block_hash in (None, ""):
        return None, None
    if isinstance(height, bool) or not isinstance(height, int) or height < 0:
        raise ValueError("status_effective_height must be a non-negative integer.")
    normalized_hash = str(block_hash or "").strip().lower()
    if len(normalized_hash) != 64 or any(ch not in "0123456789abcdef" for ch in normalized_hash):
        raise ValueError("status_reference_block_hash must be a 64-character lowercase hexadecimal string.")
    return height, normalized_hash


def _normalized_vote_record(vote: dict[str, Any], *, legacy_index: int | None = None) -> dict[str, Any]:
    submission_id = str(vote.get("submission_id") or "").strip()
    voter = normalize_wallet_address(vote.get("voter_wallet_address") or vote.get("voter"))
    if voter is None:
        voter = str(vote.get("voter_wallet_address") or vote.get("voter") or "").strip()
    vote_choice = vote.get("vote_type")
    content_hash = str(vote.get("content_hash") or "").strip().lower() or None
    signature = str(vote.get("vote_signature") or vote.get("signature") or "").strip() or None
    signature_scheme = str(vote.get("signature_scheme") or "").strip().lower() or None
    nonce = str(vote.get("vote_nonce") or vote.get("nonce") or "").strip() or None
    issued_at = str(vote.get("vote_issued_at") or vote.get("issued_at") or "").strip() or None
    expires_at = str(vote.get("vote_expires_at") or vote.get("expires_at") or "").strip() or None
    network_id = str(vote.get("network_id") or "").strip().lower() or None
    identity = str(vote.get("vote_identity") or "").strip().lower() or None
    signed_complete = all((content_hash, signature, signature_scheme, nonce, issued_at, expires_at, network_id))
    if identity is not None and not signed_complete:
        raise StorageCorruptionError("Canonical vote_identity requires the complete signed Protocol v1 vote payload.")
    if signed_complete:
        calculated = calculate_signed_vote_identity(
            wallet_address=voter,
            submission_id=submission_id,
            content_hash=content_hash,
            vote_type=vote_choice,
            nonce=nonce,
            issued_at=issued_at,
            expires_at=expires_at,
            network_id=network_id,
            signature=signature,
            signature_scheme=signature_scheme,
        )
        if identity is not None and identity != calculated:
            raise StorageCorruptionError("Stored vote_identity does not match the canonical signed vote.")
        identity = calculated
        identity_status = "canonical"
        evidence_id = identity
    else:
        identity = None
        identity_status = "legacy_unverifiable"
        legacy_payload = {"legacy_index": legacy_index, "record": vote}
        evidence_id = "legacy:" + hashlib.sha256(_canonical_record(legacy_payload).encode("utf-8")).hexdigest()
    reviewer_policy_version = vote.get("reviewer_policy_version")
    reputation_rule_version = vote.get("reputation_rule_version")
    reviewer_status = vote.get("reviewer_status")
    reviewer_eligible = vote.get("reviewer_eligible")
    status_height = vote.get("reviewer_status_effective_height")
    status_hash = vote.get("reviewer_status_reference_block_hash")
    if any(value is not None for value in (reviewer_policy_version, reputation_rule_version, reviewer_status)):
        if reviewer_policy_version is None or reputation_rule_version is None or reviewer_status is None:
            raise ValueError("Reviewer policy version, reputation rule version, and reviewer status must be recorded together.")
        reviewer_policy(reviewer_policy_version)
        reputation_rules(reputation_rule_version)
        reviewer_status = validate_reviewer_status(reviewer_status)
        status_height, status_hash = _canonical_reference(status_height, status_hash)
        if reviewer_eligible is not None and not isinstance(reviewer_eligible, bool):
            raise ValueError("Reviewer eligibility result must be a boolean when recorded.")
    return {
        "evidence_id": evidence_id,
        "vote_identity": identity,
        "identity_status": identity_status,
        "submission_id": submission_id,
        "content_hash": content_hash,
        "voter_address": voter,
        "vote_choice": vote_choice,
        "signed_payload_version": vote.get("vote_version"),
        "protocol_version": vote.get("protocol_version"),
        "network_id": network_id,
        "nonce": nonce,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "signature": signature,
        "signature_scheme": signature_scheme,
        "signed_message": vote.get("vote_message"),
        "signed_message_hash": vote.get("signed_message_hash"),
        "reviewer_policy_version": reviewer_policy_version,
        "reputation_rule_version": reputation_rule_version,
        "reviewer_status": reviewer_status,
        "reviewer_eligible": reviewer_eligible,
        "reviewer_status_effective_height": status_height,
        "reviewer_status_reference_block_hash": status_hash,
        "observed_at": str(vote.get("created_at") or _utc_now_iso()),
        "source_record_json": _canonical_record(vote),
    }


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

    canonical_references = {
        (int(block["index"]), _normalized_claim_value(block.get("hash")))
        for block in list(document.get("chain", []) or [])
        if isinstance(block, dict) and block.get("index") is not None and block.get("hash")
    }
    finalized_references = {
        (int(record["block_height"]), _normalized_claim_value(record.get("block_hash")))
        for record in list(document.get("finalized_blocks", []) or [])
        if isinstance(record, dict) and record.get("block_height") is not None and record.get("block_hash")
    }
    evidence_submissions: set[str] = set()
    evidence_digests: set[str] = set()
    for raw_evidence in list(document.get("originality_evidence", []) or []):
        evidence = validate_originality_evidence(raw_evidence)
        submission_id = str(evidence["submission_id"]).strip()
        if submission_id in evidence_submissions:
            raise StorageUniquenessError("Current originality evidence must be unique per submission.")
        evidence_submissions.add(submission_id)
        evidence_digests.add(evidence["canonical_evidence_digest"])
        reference = (
            int(evidence["originality_reference_height"]),
            evidence["originality_reference_block_hash"],
        )
        if reference not in canonical_references:
            raise StorageUniquenessError("Current originality evidence references a non-canonical block.")
    for certificate in list(document.get("originality_certificates", []) or []):
        if not isinstance(certificate, dict) or certificate.get("certificate_version") not in {2, 3}:
            continue
        if certificate.get("evidence_binding_status", "active") != "active":
            continue
        if certificate.get("originality_evidence_digest") not in evidence_digests:
            raise StorageUniquenessError(
                "Active evidence-bound certificate references unavailable originality evidence."
            )
        for height_field, hash_field in (
            ("originality_reference_height", "originality_reference_block_hash"),
            ("certificate_reference_height", "certificate_reference_block_hash"),
        ):
            reference = (certificate.get(height_field), certificate.get(hash_field))
            if reference not in canonical_references:
                raise StorageUniquenessError(
                    "Active evidence-bound certificate references a non-canonical block."
                )
        if certificate.get("certificate_version") == 3:
            reviewer_reference = (
                certificate.get("reviewer_snapshot_reference_height"),
                certificate.get("reviewer_snapshot_reference_block_hash"),
            )
            certificate_reference = (
                certificate.get("certificate_reference_height"),
                certificate.get("certificate_reference_block_hash"),
            )
            if reviewer_reference not in finalized_references or certificate_reference not in finalized_references:
                raise StorageUniquenessError(
                    "Active certificate version 3 references non-finalized reviewer or certificate state."
                )
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

    def atomic_update_blockchain_document(
        self, mutate, *, outbox_records=None, received_peer_message=None,
        copy_document: bool = True,
    ):
        """Durably replace a document from a freshly locked/transactional read.

        Unlike the canonical-head compare-and-swap command, this is for local
        commands whose correctness depends on an up-to-date complete document
        (native transaction admission is the first user).  Backends must not
        return until the replacement is durable.
        """
        raise NotImplementedError

    @property
    def supports_durable_peer_outbox(self) -> bool:
        return False

    def list_native_transaction_outbox(self, **_filters):
        return []

    def get_native_transaction_outbox(self, **_identity):
        return None

    def enqueue_native_transaction_outbox(self, records):
        raise RuntimeError("Durable native transaction peer outbox requires SQLite storage.")

    def claim_native_transaction_outbox(self, **_options):
        return None

    def acknowledge_native_transaction_outbox(self, **_ack):
        return False

    def fail_native_transaction_outbox(self, **_failure):
        return False

    def refresh_native_transaction_outbox_destination(self, **_options):
        """Refresh a node-ID destination URL and optionally wake retryable work.

        JSON intentionally has no durable outbox implementation; this remains a
        SQLite Public Testnet v1 operation.
        """
        return 0

    def get_received_native_transaction_message(self, message_id):
        return None

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
        for certificate in certificates:
            if self._record_value(certificate, "submission_id") != submission_id.strip():
                continue
            if self._record_value(certificate, "evidence_binding_status") == "invalidated_by_reorg":
                continue
            return certificate
        return None

    def load_originality_evidence(self):
        document = self.load_blockchain_document()
        if not document:
            return []
        return list(document.get("originality_evidence", []) or [])

    def get_originality_evidence(self, submission_id, evidence=None):
        if not isinstance(submission_id, str) or not submission_id.strip():
            return None
        records = self.load_originality_evidence() if evidence is None else evidence
        return self._first_record_where(records, "submission_id", submission_id.strip())

    def list_originality_evidence_history(self, submission_id):
        """JSON compatibility retains only the current document projection."""
        record = self.get_originality_evidence(submission_id)
        return [record] if record is not None else []

    def load_minted_media_originality_index(self, *, rule_version, head_height, head_hash):
        return None

    def replace_minted_media_originality_index(self, *, rule_version, head_height, head_hash, records):
        return None

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

    def atomic_update_blockchain_document(
        self, mutate, *, outbox_records=None, received_peer_message=None,
        copy_document: bool = True,
    ):
        with self._commit_lock():
            replacement = self._normalize_blockchain_document(
                mutate(deepcopy(self._load_or_new_blockchain_document()))
            )
            # JSON remains a development compatibility backend. It cannot
            # provide relational outbox or durable message-dedup guarantees.
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
            "SQLite backend selected. Native transactions, reviewer state, and vote evidence use relational durable storage."
        )

    def delete_blockchain_document(self) -> None:
        for candidate in (self.sqlite_db_path, _backup_path_for(self.sqlite_db_path)):
            if os.path.exists(candidate):
                os.remove(candidate)

    def _connect(self):
        connection = sqlite3.connect(self.sqlite_db_path)
        # Concurrent request handlers must wait through a legitimate durable
        # admission rather than turn SQLite's short default busy timeout into a
        # user-visible false failure.  This changes neither lock ownership nor
        # the commit-before-ack rule; it only gives the serialized writer a
        # bounded, operationally useful wait window.
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @staticmethod
    def _insert_durable_vote_record(connection, record: dict[str, Any], *, lifecycle_state: str) -> dict[str, Any]:
        values = dict(record)
        values["lifecycle_state"] = lifecycle_state
        values["rejection_reason"] = values.get("rejection_reason")
        columns = tuple(values)
        sql = (
            f"INSERT INTO durable_vote_records ({', '.join(columns)}) "
            f"VALUES ({', '.join(':' + column for column in columns)})"
        )
        try:
            connection.execute(sql, values)
        except sqlite3.IntegrityError:
            existing = connection.execute(
                "SELECT evidence_id, lifecycle_state FROM durable_vote_records WHERE evidence_id = ? OR vote_identity = ?",
                (values["evidence_id"], values.get("vote_identity")),
            ).fetchone()
            if existing is not None:
                return {"evidence_id": existing[0], "lifecycle_state": existing[1], "replay": True}
            if lifecycle_state != "accepted":
                raise
            values["lifecycle_state"] = "rejected"
            values["rejection_reason"] = values.get("rejection_reason") or "conflicting_counted_vote"
            connection.execute(sql, values)
        return {
            "evidence_id": values["evidence_id"],
            "vote_identity": values.get("vote_identity"),
            "lifecycle_state": values["lifecycle_state"],
            "rejection_reason": values.get("rejection_reason"),
            "replay": False,
        }

    @classmethod
    def _synchronize_durable_vote_records(cls, connection, votes) -> None:
        for index, vote in enumerate(list(votes or [])):
            if not isinstance(vote, dict):
                raise StorageCorruptionError("Vote record must be an object.")
            record = _normalized_vote_record(vote, legacy_index=index)
            cls._insert_durable_vote_record(connection, record, lifecycle_state="accepted")

    def record_durable_vote(self, vote: dict[str, Any], *, lifecycle_state: str = "accepted", rejection_reason: str | None = None) -> dict[str, Any]:
        if lifecycle_state not in {"accepted", "rejected"}:
            raise ValueError("Vote lifecycle_state must be accepted or rejected.")
        record = _normalized_vote_record(vote)
        record["rejection_reason"] = rejection_reason
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            return self._insert_durable_vote_record(connection, record, lifecycle_state=lifecycle_state)

    def record_durable_vote_with_epoch_limit(
        self, vote: dict[str, Any], *, maximum_votes: int, epoch_start_height: int,
        epoch_end_height: int,
    ) -> dict[str, Any]:
        """Atomically enforce one reviewer's finalized-height epoch quota."""
        if isinstance(maximum_votes, bool) or not isinstance(maximum_votes, int) or maximum_votes <= 0:
            raise ValueError("maximum_votes must be a positive integer.")
        record = _normalized_vote_record(vote)
        if record["reviewer_policy_version"] is None or record["reviewer_status_effective_height"] is None:
            raise ValueError("Epoch-limited votes require a complete reviewer policy snapshot.")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT evidence_id, lifecycle_state FROM durable_vote_records WHERE evidence_id = ? OR vote_identity = ?",
                (record["evidence_id"], record.get("vote_identity")),
            ).fetchone()
            if existing is not None:
                return {"evidence_id": existing[0], "lifecycle_state": existing[1], "replay": True}
            used = connection.execute(
                """SELECT COUNT(*) FROM durable_vote_records
                   WHERE voter_address = ? AND reviewer_policy_version = ?
                     AND lifecycle_state = 'accepted'
                     AND reviewer_status_effective_height BETWEEN ? AND ?""",
                (record["voter_address"], record["reviewer_policy_version"], epoch_start_height, epoch_end_height),
            ).fetchone()[0]
            if int(used) >= maximum_votes:
                record["rejection_reason"] = "review_epoch_vote_limit_reached"
                return self._insert_durable_vote_record(connection, record, lifecycle_state="rejected")
            return self._insert_durable_vote_record(connection, record, lifecycle_state="accepted")

    def list_durable_votes(self, *, submission_id: str | None = None) -> list[dict[str, Any]]:
        columns = (
            "evidence_id", "vote_identity", "identity_status", "submission_id", "content_hash",
            "voter_address", "vote_choice", "lifecycle_state", "rejection_reason",
            "signed_payload_version", "protocol_version", "network_id", "nonce", "issued_at",
            "expires_at", "signature", "signature_scheme", "signed_message", "signed_message_hash",
            "reviewer_policy_version", "reputation_rule_version", "reviewer_status",
            "reviewer_eligible",
            "reviewer_status_effective_height", "reviewer_status_reference_block_hash", "observed_at",
        )
        where = " WHERE submission_id = ?" if submission_id is not None else ""
        parameters = (str(submission_id).strip(),) if submission_id is not None else ()
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT {', '.join(columns)} FROM durable_vote_records{where} ORDER BY observed_at, evidence_id",
                parameters,
            ).fetchall()
        results = [dict(zip(columns, row)) for row in rows]
        for result in results:
            if result.get("reviewer_eligible") is not None:
                result["reviewer_eligible"] = bool(result["reviewer_eligible"])
        return results

    @staticmethod
    def _normalize_reviewer_address(value: str) -> str:
        normalized = normalize_wallet_address(value)
        if normalized is None:
            raise ValueError("reviewer_address must be a valid Ethereum-style 0x address.")
        return normalized

    @staticmethod
    def _validate_reviewer_versions(reviewer_policy_version: int, reputation_rule_version: int) -> None:
        reviewer_policy(reviewer_policy_version)
        reputation_rules(reputation_rule_version)

    def initialize_reviewer_state(
        self, reviewer_address: str, *, current_status: str = "NEW",
        reviewer_policy_version: int = REVIEWER_POLICY_VERSION,
        reputation_rule_version: int = REPUTATION_RULE_VERSION,
        status_effective_height: int | None = None,
        status_reference_block_hash: str | None = None,
        bootstrap_established: bool = False,
        reason: str | None = "initial_state",
    ) -> dict[str, Any]:
        address = self._normalize_reviewer_address(reviewer_address)
        status = validate_reviewer_status(current_status)
        self._validate_reviewer_versions(reviewer_policy_version, reputation_rule_version)
        height, block_hash = _canonical_reference(status_effective_height, status_reference_block_hash)
        if bootstrap_established and (status != "ESTABLISHED_REVIEWER" or address not in bootstrap_established_reviewers(reviewer_policy_version)):
            raise ValueError("Bootstrap-established state must match the versioned reviewer policy grant set.")
        observed_at = _utc_now_iso()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT reviewer_address FROM reviewer_states WHERE reviewer_address = ?", (address,)).fetchone()
            if existing is None:
                connection.execute(
                    """INSERT INTO reviewer_states
                       (reviewer_address, current_status, reviewer_policy_version, reputation_rule_version,
                        status_effective_height, status_reference_block_hash, bootstrap_established, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (address, status, reviewer_policy_version, reputation_rule_version, height, block_hash, int(bootstrap_established), observed_at, observed_at),
                )
                connection.execute(
                    """INSERT INTO reviewer_state_transitions
                       (reviewer_address, transition_sequence, from_status, to_status, reviewer_policy_version,
                        reputation_rule_version, status_effective_height, status_reference_block_hash,
                        bootstrap_established, reason, observed_at)
                       VALUES (?, 0, NULL, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (address, status, reviewer_policy_version, reputation_rule_version, height, block_hash, int(bootstrap_established), reason, observed_at),
                )
        return self.get_reviewer_state(address)

    def transition_reviewer_state(
        self, reviewer_address: str, *, to_status: str,
        reviewer_policy_version: int = REVIEWER_POLICY_VERSION,
        reputation_rule_version: int = REPUTATION_RULE_VERSION,
        status_effective_height: int,
        status_reference_block_hash: str,
        bootstrap_established: bool = False,
        reason: str | None = None,
    ) -> dict[str, Any]:
        address = self._normalize_reviewer_address(reviewer_address)
        status = validate_reviewer_status(to_status)
        self._validate_reviewer_versions(reviewer_policy_version, reputation_rule_version)
        height, block_hash = _canonical_reference(status_effective_height, status_reference_block_hash)
        observed_at = _utc_now_iso()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT current_status, bootstrap_established FROM reviewer_states WHERE reviewer_address = ?", (address,)
            ).fetchone()
            if existing is None:
                raise ValueError(f"Reviewer state not found: {address}")
            if (
                existing[0] == status
                and bool(existing[1]) == bool(bootstrap_established and status == "ESTABLISHED_REVIEWER")
            ):
                return self.get_reviewer_state(address)
            if bootstrap_established and (
                status != "ESTABLISHED_REVIEWER"
                or address not in bootstrap_established_reviewers(reviewer_policy_version)
            ):
                raise ValueError("Bootstrap-established state must match the versioned reviewer policy grant set.")
            sequence = connection.execute(
                "SELECT COALESCE(MAX(transition_sequence), -1) + 1 FROM reviewer_state_transitions WHERE reviewer_address = ?", (address,)
            ).fetchone()[0]
            bootstrap = bool(bootstrap_established) or (bool(existing[1]) and status == "ESTABLISHED_REVIEWER")
            connection.execute(
                """UPDATE reviewer_states SET current_status = ?, reviewer_policy_version = ?, reputation_rule_version = ?,
                   status_effective_height = ?, status_reference_block_hash = ?, bootstrap_established = ?, updated_at = ?
                   WHERE reviewer_address = ?""",
                (status, reviewer_policy_version, reputation_rule_version, height, block_hash, int(bootstrap), observed_at, address),
            )
            connection.execute(
                """INSERT INTO reviewer_state_transitions
                   (reviewer_address, transition_sequence, from_status, to_status, reviewer_policy_version,
                    reputation_rule_version, status_effective_height, status_reference_block_hash,
                    bootstrap_established, reason, observed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (address, sequence, existing[0], status, reviewer_policy_version, reputation_rule_version, height, block_hash, int(bootstrap), reason, observed_at),
            )
        return self.get_reviewer_state(address)

    def list_reviewer_states(self) -> list[dict[str, Any]]:
        columns = ("reviewer_address", "current_status", "reviewer_policy_version", "reputation_rule_version", "status_effective_height", "status_reference_block_hash", "bootstrap_established", "created_at", "updated_at")
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT {', '.join(columns)} FROM reviewer_states ORDER BY reviewer_address"
            ).fetchall()
        results = [dict(zip(columns, row)) for row in rows]
        for result in results:
            result["bootstrap_established"] = bool(result["bootstrap_established"])
        return results

    def get_reviewer_state(self, reviewer_address: str) -> dict[str, Any] | None:
        address = self._normalize_reviewer_address(reviewer_address)
        columns = ("reviewer_address", "current_status", "reviewer_policy_version", "reputation_rule_version", "status_effective_height", "status_reference_block_hash", "bootstrap_established", "created_at", "updated_at")
        with self._connect() as connection:
            row = connection.execute(f"SELECT {', '.join(columns)} FROM reviewer_states WHERE reviewer_address = ?", (address,)).fetchone()
        if row is None:
            return None
        result = dict(zip(columns, row))
        result["bootstrap_established"] = bool(result["bootstrap_established"])
        return result

    def list_reviewer_state_history(self, reviewer_address: str) -> list[dict[str, Any]]:
        address = self._normalize_reviewer_address(reviewer_address)
        columns = ("reviewer_address", "transition_sequence", "from_status", "to_status", "reviewer_policy_version", "reputation_rule_version", "status_effective_height", "status_reference_block_hash", "bootstrap_established", "reason", "observed_at")
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT {', '.join(columns)} FROM reviewer_state_transitions WHERE reviewer_address = ? ORDER BY transition_sequence", (address,)
            ).fetchall()
        results = [dict(zip(columns, row)) for row in rows]
        for result in results:
            result["bootstrap_established"] = bool(result["bootstrap_established"])
        return results

    @staticmethod
    def _synchronize_originality_evidence_records(connection, evidence_records, document) -> None:
        records = list(evidence_records or [])
        by_submission: dict[str, dict[str, Any]] = {}
        for raw in records:
            evidence = validate_originality_evidence(raw)
            submission_id = str(evidence["submission_id"]).strip()
            if not submission_id or submission_id in by_submission:
                raise StorageUniquenessError("Current originality evidence must be unique per submission.")
            by_submission[submission_id] = evidence

        canonical = {
            (int(block.get("index")), str(block.get("hash") or "").strip().lower())
            for block in document.get("chain", []) or []
            if isinstance(block, dict) and block.get("index") is not None and block.get("hash")
        }
        current_rows = connection.execute(
            "SELECT submission_id, evidence_digest, reference_height, reference_block_hash FROM originality_evidence_records WHERE is_current = 1"
        ).fetchall()
        current_by_submission = {row[0]: row for row in current_rows}
        certificate_bound_digests = {
            certificate.get("originality_evidence_digest")
            for certificate in document.get("originality_certificates", []) or []
            if isinstance(certificate, dict)
            and certificate.get("certificate_version") in {2, 3}
            and certificate.get("evidence_binding_status", "active") == "active"
        }

        for submission_id, row in current_by_submission.items():
            if submission_id not in by_submission:
                connection.execute(
                    "UPDATE originality_evidence_records SET is_current = 0, invalidated_by_reorg = 1 WHERE evidence_digest = ?",
                    (row[1],),
                )

        for submission_id, evidence in sorted(by_submission.items()):
            reference = (
                int(evidence["originality_reference_height"]),
                evidence["originality_reference_block_hash"],
            )
            if reference not in canonical:
                raise StorageCorruptionError("Current originality evidence references a non-canonical block.")
            digest = evidence["canonical_evidence_digest"]
            existing = current_by_submission.get(submission_id)
            if existing is not None and existing[1] == digest:
                continue
            if existing is not None:
                old_reference = (int(existing[2]), str(existing[3]))
                is_unbound_certificate_profile_migration = (
                    evidence.get("certificate_verification_profile")
                    == CERTIFICATE_EVIDENCE_PROFILE
                    and existing[1] not in certificate_bound_digests
                )
                if old_reference in canonical and not is_unbound_certificate_profile_migration:
                    raise StorageUniquenessError(
                        "Immutable originality evidence cannot change while its reference remains canonical."
                    )
                connection.execute(
                    "UPDATE originality_evidence_records SET is_current = 0, invalidated_by_reorg = ? WHERE evidence_digest = ?",
                    (0 if old_reference in canonical else 1, existing[1]),
                )
            observed_at = _utc_now_iso()
            connection.execute(
                """INSERT OR IGNORE INTO originality_evidence_records
                   (evidence_digest, submission_id, evidence_version, originality_rule_version,
                    content_hash, reference_height, reference_block_hash, final_prevote_decision,
                    reason_codes_json, evidence_json, is_current, invalidated_by_reorg, observed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?)""",
                (
                    digest, submission_id, evidence["evidence_version"], evidence["originality_rule_version"],
                    evidence["content_hash"], evidence["originality_reference_height"],
                    evidence["originality_reference_block_hash"], evidence["final_prevote_decision"],
                    _canonical_record(evidence["reason_codes"]), _canonical_record(evidence), observed_at,
                ),
            )
            connection.execute(
                "UPDATE originality_evidence_records SET is_current = CASE WHEN evidence_digest = ? THEN 1 ELSE 0 END WHERE submission_id = ?",
                (digest, submission_id),
            )
            for layer, field in (
                ("exact", "exact_candidate_matches"),
                ("perceptual", "perceptual_candidate_matches"),
                ("ocr", "ocr_candidate_matches"),
                ("near_duplicate", "near_duplicate_candidate_matches"),
            ):
                for position, match in enumerate(evidence.get(field, [])):
                    connection.execute(
                        """INSERT OR IGNORE INTO originality_evidence_matches
                           (evidence_digest, layer, match_position, block_height, block_hash, content_hash, match_json)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            digest, layer, position, match["block_height"], match["block_hash"],
                            match["content_hash"], _canonical_record(match),
                        ),
                    )

    @staticmethod
    def _synchronize_certificate_evidence_bindings(connection, certificates) -> None:
        for certificate in certificates or []:
            if not isinstance(certificate, dict) or certificate.get("certificate_version") not in {2, 3}:
                continue
            immutable = (
                certificate.get("certificate_version"),
                certificate.get("submission_id"),
                certificate.get("content_hash"),
                certificate.get("originality_evidence_digest"),
                certificate.get("originality_reference_height"),
                certificate.get("originality_reference_block_hash"),
                certificate.get("certificate_reference_height"),
                certificate.get("certificate_reference_block_hash"),
            )
            certificate_id = str(certificate.get("certificate_id") or "").strip().lower()
            if not certificate_id or any(value is None for value in immutable):
                raise StorageCorruptionError("Evidence-bound certificate has an incomplete evidence binding.")
            existing = connection.execute(
                """SELECT certificate_version, submission_id, content_hash, evidence_digest,
                          originality_reference_height, originality_reference_block_hash,
                          certificate_reference_height, certificate_reference_block_hash
                   FROM originality_certificate_evidence_bindings WHERE certificate_id = ?""",
                (certificate_id,),
            ).fetchone()
            if existing is not None and tuple(existing) != immutable:
                raise StorageUniquenessError(
                    "An immutable certificate evidence binding cannot be replaced."
                )
            status = str(certificate.get("evidence_binding_status") or "active")
            connection.execute(
                """INSERT OR IGNORE INTO originality_certificate_evidence_bindings
                   (certificate_id, certificate_version, submission_id, content_hash,
                    evidence_digest, originality_reference_height,
                    originality_reference_block_hash, certificate_reference_height,
                    certificate_reference_block_hash, binding_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (certificate_id, *immutable, status),
            )
            connection.execute(
                "UPDATE originality_certificate_evidence_bindings SET binding_status = ? WHERE certificate_id = ?",
                (status, certificate_id),
            )

    def list_originality_evidence_history(self, submission_id):
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT evidence_json, is_current, invalidated_by_reorg, observed_at
                   FROM originality_evidence_records WHERE submission_id = ?
                   ORDER BY rowid""",
                (str(submission_id).strip(),),
            ).fetchall()
        results = []
        for evidence_json, is_current, invalidated, observed_at in rows:
            record = json.loads(evidence_json)
            record["is_current"] = bool(is_current)
            record["invalidated_by_reorg"] = bool(invalidated)
            record["observed_at"] = observed_at
            results.append(record)
        return results

    def load_minted_media_originality_index(self, *, rule_version, head_height, head_hash):
        with self._connect() as connection:
            metadata = connection.execute(
                "SELECT head_height, head_hash, index_digest FROM originality_index_metadata WHERE originality_rule_version = ?",
                (int(rule_version),),
            ).fetchone()
            if metadata is None or metadata[0] != int(head_height) or metadata[1] != str(head_hash).lower():
                return None
            rows = connection.execute(
                """SELECT record_json FROM minted_media_originality_index
                   WHERE originality_rule_version = ? ORDER BY block_height, block_hash""",
                (int(rule_version),),
            ).fetchall()
        records = [json.loads(row[0]) for row in rows]
        digest = hashlib.sha256(_canonical_record(records).encode("utf-8")).hexdigest()
        if digest != metadata[2]:
            return None
        return records

    def replace_minted_media_originality_index(self, *, rule_version, head_height, head_hash, records):
        normalized = sorted(
            [dict(record) for record in records],
            key=lambda item: (item["block_height"], item["block_hash"]),
        )
        digest = hashlib.sha256(_canonical_record(normalized).encode("utf-8")).hexdigest()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM minted_media_originality_index WHERE originality_rule_version = ?",
                (int(rule_version),),
            )
            connection.executemany(
                """INSERT INTO minted_media_originality_index
                   (originality_rule_version, block_hash, block_height, content_hash, record_json)
                   VALUES (?, ?, ?, ?, ?)""",
                [
                    (int(rule_version), item["block_hash"], item["block_height"], item["content_hash"], _canonical_record(item))
                    for item in normalized
                ],
            )
            connection.execute(
                """INSERT INTO originality_index_metadata
                   (originality_rule_version, head_height, head_hash, index_digest, rebuilt_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(originality_rule_version) DO UPDATE SET
                     head_height=excluded.head_height, head_hash=excluded.head_hash,
                     index_digest=excluded.index_digest, rebuilt_at=excluded.rebuilt_at""",
                (int(rule_version), int(head_height), str(head_hash).lower(), digest, _utc_now_iso()),
            )
        return normalized

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
                """
                CREATE TABLE IF NOT EXISTS reviewer_states (
                    reviewer_address TEXT PRIMARY KEY,
                    current_status TEXT NOT NULL CHECK (current_status IN ('NEW', 'PROBATIONARY_REVIEWER', 'ESTABLISHED_REVIEWER', 'COOLDOWN', 'SUSPENDED')),
                    reviewer_policy_version INTEGER NOT NULL CHECK (reviewer_policy_version > 0),
                    reputation_rule_version INTEGER NOT NULL CHECK (reputation_rule_version > 0),
                    status_effective_height INTEGER CHECK (status_effective_height IS NULL OR status_effective_height >= 0),
                    status_reference_block_hash TEXT,
                    bootstrap_established INTEGER NOT NULL DEFAULT 0 CHECK (bootstrap_established IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK ((status_effective_height IS NULL) = (status_reference_block_hash IS NULL)),
                    CHECK (bootstrap_established = 0 OR current_status = 'ESTABLISHED_REVIEWER')
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reviewer_state_transitions (
                    reviewer_address TEXT NOT NULL,
                    transition_sequence INTEGER NOT NULL CHECK (transition_sequence >= 0),
                    from_status TEXT CHECK (from_status IS NULL OR from_status IN ('NEW', 'PROBATIONARY_REVIEWER', 'ESTABLISHED_REVIEWER', 'COOLDOWN', 'SUSPENDED')),
                    to_status TEXT NOT NULL CHECK (to_status IN ('NEW', 'PROBATIONARY_REVIEWER', 'ESTABLISHED_REVIEWER', 'COOLDOWN', 'SUSPENDED')),
                    reviewer_policy_version INTEGER NOT NULL CHECK (reviewer_policy_version > 0),
                    reputation_rule_version INTEGER NOT NULL CHECK (reputation_rule_version > 0),
                    status_effective_height INTEGER CHECK (status_effective_height IS NULL OR status_effective_height >= 0),
                    status_reference_block_hash TEXT,
                    bootstrap_established INTEGER NOT NULL DEFAULT 0 CHECK (bootstrap_established IN (0, 1)),
                    reason TEXT,
                    observed_at TEXT NOT NULL,
                    PRIMARY KEY (reviewer_address, transition_sequence),
                    FOREIGN KEY (reviewer_address) REFERENCES reviewer_states(reviewer_address),
                    CHECK ((status_effective_height IS NULL) = (status_reference_block_hash IS NULL))
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS durable_vote_records (
                    evidence_id TEXT PRIMARY KEY,
                    vote_identity TEXT UNIQUE,
                    identity_status TEXT NOT NULL CHECK (identity_status IN ('canonical', 'legacy_unverifiable')),
                    submission_id TEXT NOT NULL,
                    content_hash TEXT,
                    voter_address TEXT NOT NULL,
                    vote_choice TEXT,
                    lifecycle_state TEXT NOT NULL CHECK (lifecycle_state IN ('accepted', 'rejected')),
                    rejection_reason TEXT,
                    signed_payload_version INTEGER,
                    protocol_version INTEGER,
                    network_id TEXT,
                    nonce TEXT,
                    issued_at TEXT,
                    expires_at TEXT,
                    signature TEXT,
                    signature_scheme TEXT,
                    signed_message TEXT,
                    signed_message_hash TEXT,
                    reviewer_policy_version INTEGER,
                    reputation_rule_version INTEGER,
                    reviewer_status TEXT CHECK (reviewer_status IS NULL OR reviewer_status IN ('NEW', 'PROBATIONARY_REVIEWER', 'ESTABLISHED_REVIEWER', 'COOLDOWN', 'SUSPENDED')),
                    reviewer_eligible INTEGER CHECK (reviewer_eligible IS NULL OR reviewer_eligible IN (0, 1)),
                    reviewer_status_effective_height INTEGER,
                    reviewer_status_reference_block_hash TEXT,
                    observed_at TEXT NOT NULL,
                    source_record_json TEXT NOT NULL
                )
                """
            )
            durable_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(durable_vote_records)").fetchall()
            }
            if "reviewer_eligible" not in durable_columns:
                connection.execute(
                    "ALTER TABLE durable_vote_records ADD COLUMN reviewer_eligible INTEGER "
                    "CHECK (reviewer_eligible IS NULL OR reviewer_eligible IN (0, 1))"
                )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS one_accepted_vote_per_submission_wallet
                ON durable_vote_records(submission_id, voter_address)
                WHERE lifecycle_state = 'accepted'
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS originality_evidence_records (
                    evidence_digest TEXT PRIMARY KEY,
                    submission_id TEXT NOT NULL,
                    evidence_version INTEGER NOT NULL CHECK (evidence_version > 0),
                    originality_rule_version INTEGER NOT NULL CHECK (originality_rule_version > 0),
                    content_hash TEXT NOT NULL,
                    reference_height INTEGER NOT NULL CHECK (reference_height >= 0),
                    reference_block_hash TEXT NOT NULL,
                    final_prevote_decision TEXT NOT NULL CHECK (final_prevote_decision IN ('PASS', 'FLAGGED_FOR_REVIEW', 'HARD_REJECT')),
                    reason_codes_json TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    is_current INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0, 1)),
                    invalidated_by_reorg INTEGER NOT NULL DEFAULT 0 CHECK (invalidated_by_reorg IN (0, 1)),
                    observed_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS one_current_originality_evidence_per_submission
                ON originality_evidence_records(submission_id) WHERE is_current = 1
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS originality_evidence_matches (
                    evidence_digest TEXT NOT NULL,
                    layer TEXT NOT NULL CHECK (layer IN ('exact', 'perceptual', 'ocr', 'near_duplicate')),
                    match_position INTEGER NOT NULL CHECK (match_position >= 0),
                    block_height INTEGER NOT NULL CHECK (block_height >= 0),
                    block_hash TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    match_json TEXT NOT NULL,
                    PRIMARY KEY (evidence_digest, layer, match_position),
                    FOREIGN KEY (evidence_digest) REFERENCES originality_evidence_records(evidence_digest)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS originality_certificate_evidence_bindings (
                    certificate_id TEXT PRIMARY KEY,
                    certificate_version INTEGER NOT NULL CHECK (certificate_version IN (2, 3)),
                    submission_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    evidence_digest TEXT NOT NULL,
                    originality_reference_height INTEGER NOT NULL CHECK (originality_reference_height >= 0),
                    originality_reference_block_hash TEXT NOT NULL,
                    certificate_reference_height INTEGER NOT NULL CHECK (certificate_reference_height >= 0),
                    certificate_reference_block_hash TEXT NOT NULL,
                    binding_status TEXT NOT NULL DEFAULT 'active'
                        CHECK (binding_status IN ('active', 'invalidated_by_reorg')),
                    FOREIGN KEY (evidence_digest) REFERENCES originality_evidence_records(evidence_digest)
                )
                """
            )
            binding_sql_row = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'originality_certificate_evidence_bindings'"
            ).fetchone()
            if binding_sql_row and "certificate_version = 2" in str(binding_sql_row[0]):
                connection.execute(
                    "ALTER TABLE originality_certificate_evidence_bindings "
                    "RENAME TO originality_certificate_evidence_bindings_task55"
                )
                connection.execute(
                    """
                    CREATE TABLE originality_certificate_evidence_bindings (
                        certificate_id TEXT PRIMARY KEY,
                        certificate_version INTEGER NOT NULL CHECK (certificate_version IN (2, 3)),
                        submission_id TEXT NOT NULL,
                        content_hash TEXT NOT NULL,
                        evidence_digest TEXT NOT NULL,
                        originality_reference_height INTEGER NOT NULL CHECK (originality_reference_height >= 0),
                        originality_reference_block_hash TEXT NOT NULL,
                        certificate_reference_height INTEGER NOT NULL CHECK (certificate_reference_height >= 0),
                        certificate_reference_block_hash TEXT NOT NULL,
                        binding_status TEXT NOT NULL DEFAULT 'active'
                            CHECK (binding_status IN ('active', 'invalidated_by_reorg')),
                        FOREIGN KEY (evidence_digest) REFERENCES originality_evidence_records(evidence_digest)
                    )
                    """
                )
                connection.execute(
                    """INSERT INTO originality_certificate_evidence_bindings
                       SELECT * FROM originality_certificate_evidence_bindings_task55"""
                )
                connection.execute("DROP TABLE originality_certificate_evidence_bindings_task55")
            connection.execute(
                """CREATE INDEX IF NOT EXISTS certificate_evidence_by_submission
                   ON originality_certificate_evidence_bindings(submission_id, binding_status)"""
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS originality_index_metadata (
                    originality_rule_version INTEGER PRIMARY KEY,
                    head_height INTEGER NOT NULL,
                    head_hash TEXT NOT NULL,
                    index_digest TEXT NOT NULL,
                    rebuilt_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS minted_media_originality_index (
                    originality_rule_version INTEGER NOT NULL,
                    block_hash TEXT NOT NULL,
                    block_height INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    PRIMARY KEY (originality_rule_version, block_hash)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS minted_media_originality_content_hash
                ON minted_media_originality_index(originality_rule_version, content_hash)
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
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS native_transaction_peer_outbox (
                    outbox_id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL,
                    message_type TEXT NOT NULL,
                    tx_id TEXT NOT NULL,
                    destination_peer_id TEXT NOT NULL,
                    destination_peer_url TEXT NOT NULL,
                    serialized_message TEXT NOT NULL,
                    delivery_state TEXT NOT NULL CHECK (delivery_state IN ({', '.join(repr(state) for state in NATIVE_TRANSACTION_OUTBOX_STATES)})),
                    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
                    created_at TEXT NOT NULL,
                    last_attempt_at TEXT,
                    next_attempt_at TEXT,
                    acknowledged_at TEXT,
                    claim_token TEXT,
                    claim_expires_at TEXT,
                    last_error_code TEXT,
                    last_error_detail TEXT,
                    UNIQUE(message_id, destination_peer_id),
                    FOREIGN KEY (tx_id) REFERENCES native_transaction_records(tx_id)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS native_transaction_peer_outbox_claimable
                ON native_transaction_peer_outbox(delivery_state, next_attempt_at, claim_expires_at, created_at)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS native_transaction_peer_outbox_tx_id
                ON native_transaction_peer_outbox(tx_id)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS received_native_transaction_messages (
                    message_id TEXT PRIMARY KEY,
                    message_type TEXT NOT NULL,
                    sender_node_id TEXT NOT NULL,
                    tx_id TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    acknowledged_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS received_native_transaction_messages_tx_id
                ON received_native_transaction_messages(tx_id)
                """
            )
            connection.execute(
                """
                CREATE TRIGGER IF NOT EXISTS native_transaction_peer_outbox_state_guard
                BEFORE UPDATE OF delivery_state ON native_transaction_peer_outbox
                WHEN NOT (
                    NEW.delivery_state = OLD.delivery_state OR
                    (OLD.delivery_state = 'queued' AND NEW.delivery_state IN ('in_flight', 'permanent_failure')) OR
                    (OLD.delivery_state = 'in_flight' AND NEW.delivery_state IN ('retry_wait', 'acknowledged', 'permanent_failure')) OR
                    (OLD.delivery_state = 'retry_wait' AND NEW.delivery_state IN ('in_flight', 'permanent_failure'))
                )
                BEGIN
                    SELECT RAISE(ABORT, 'illegal native transaction outbox transition');
                END
                """
            )
            # SQLite performs this check even if a caller bypasses the Python
            # lifecycle service.  Canonical inclusion is allowed to override a
            # prior local rejection because canonical chain contents remain the
            # settlement source of truth.
            connection.execute("DROP TRIGGER IF EXISTS native_transaction_lifecycle_guard")
            connection.execute(
                """
                CREATE TRIGGER IF NOT EXISTS native_transaction_lifecycle_guard
                BEFORE UPDATE OF lifecycle_state ON native_transaction_records
                WHEN NOT (
                    NEW.lifecycle_state = OLD.lifecycle_state OR
                    (OLD.lifecycle_state = 'signed_pending' AND NEW.lifecycle_state IN ('validated_pending', 'mempool', 'settled', 'rejected', 'failed', 'expired')) OR
                    (OLD.lifecycle_state = 'validated_pending' AND NEW.lifecycle_state IN ('mempool', 'settled', 'rejected', 'failed', 'expired')) OR
                    (OLD.lifecycle_state = 'mempool' AND NEW.lifecycle_state IN ('validated_pending', 'settled', 'rejected', 'failed', 'expired')) OR
                    (OLD.lifecycle_state = 'included' AND NEW.lifecycle_state IN ('settled', 'validated_pending', 'mempool', 'rejected', 'finalized')) OR
                    (OLD.lifecycle_state = 'settled' AND NEW.lifecycle_state IN ('validated_pending', 'mempool', 'rejected', 'finalized')) OR
                    (OLD.lifecycle_state = 'rejected' AND NEW.lifecycle_state = 'settled') OR
                    (OLD.lifecycle_state = 'failed' AND NEW.lifecycle_state = 'settled') OR
                    (OLD.lifecycle_state = 'expired' AND NEW.lifecycle_state = 'settled')
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
            self._synchronize_durable_vote_records(connection, sections.get("votes", []))
            self._synchronize_canonical_claims(connection, sections)
            self._synchronize_originality_evidence_records(
                connection, sections.get("originality_evidence", []), sections
            )
            self._synchronize_certificate_evidence_bindings(
                connection, sections.get("originality_certificates", [])
            )
            # One-time migration only: older SQLite databases stored a second
            # native-transaction JSON section.  Once relational rows exist,
            # that section is intentionally ignored so opening a node can
            # never replace durable records with its stale legacy snapshot.
            native_count = connection.execute(
                "SELECT COUNT(*) FROM native_transaction_records"
            ).fetchone()[0]
            if native_count == 0 and sections["native_transactions"]:
                sections["native_transactions"] = self._synchronize_native_transaction_records(
                    connection, sections["native_transactions"]
                )
            else:
                sections["native_transactions"] = self._load_native_transaction_records(
                    connection, strict=True
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
    def _synchronize_native_transaction_records(
        cls, connection, transactions, *, previous_transactions=None
    ) -> list[dict[str, Any]]:
        source_transactions = list(transactions or [])
        # Admission starts from relational rows that this same SQLite
        # transaction just loaded.  Their unchanged payloads were already
        # normalized and guarded by SQL constraints, so re-canonicalizing
        # every one on each new admission makes the path needlessly O(n) in
        # JSON work.  Still check every record's presence and duplicates, and
        # fully validate every new/changed record before it is written.
        if previous_transactions is not None:
            previous_by_id = {
                str(item.get("tx_id") or "").strip().lower(): item
                for item in previous_transactions
                if isinstance(item, dict) and str(item.get("tx_id") or "").strip()
            }
            normalized_by_id: dict[str, dict[str, Any]] = {}
            normalized = []
            for transaction in source_transactions:
                if not isinstance(transaction, dict):
                    raise StorageCorruptionError("Native transaction record must be an object.")
                tx_id = str(transaction.get("tx_id") or "").strip().lower()
                if not tx_id:
                    raise StorageCorruptionError("Native transaction record is missing tx_id, sender, or nonce.")
                existing = normalized_by_id.get(tx_id)
                if existing is not None:
                    if _native_transaction_immutable_payload(existing) != _native_transaction_immutable_payload(transaction):
                        raise StorageUniquenessError(f"Native transaction {tx_id} appears with conflicting signed payloads.")
                    continue
                copied = dict(transaction)
                normalized_by_id[tx_id] = copied
                normalized.append(copied)
            seen = set(normalized_by_id)
            stale_ids = set(previous_by_id) - seen
            if stale_ids:
                placeholders = ", ".join("?" for _ in stale_ids)
                connection.execute(
                    f"DELETE FROM native_transaction_records WHERE tx_id IN ({placeholders})",
                    tuple(sorted(stale_ids)),
                )
            changed = [
                transaction for transaction in normalized
                if previous_by_id.get(str(transaction.get("tx_id") or "").strip().lower()) != transaction
            ]
        else:
            source_ids = []
            seen: set[str] = set()
            normalized = []
            for transaction in source_transactions:
                values = cls._native_record_values(transaction)
                source_ids.append(values["tx_id"])
                if values["tx_id"] in seen:
                    existing = next(item for item in normalized if str(item.get("tx_id") or "").strip().lower() == values["tx_id"])
                    if _native_transaction_immutable_payload(existing) != values["immutable_payload"]:
                        raise StorageUniquenessError(f"Native transaction {values['tx_id']} appears with conflicting signed payloads.")
                    continue
                seen.add(values["tx_id"])
                normalized.append(dict(transaction))
        # The ordinary whole-document save path retains its conservative
        # synchronization behavior.  Admission already loaded the previous
        # relational state under this same SQLite transaction, though, so it
        # can prove precisely which rows changed.  Avoiding a write and a
        # lifecycle lookup for every unchanged pending record keeps the same
        # durable-before-ack boundary while eliminating quadratic write work.
        if previous_transactions is None:
            # Remove records absent from this complete document before
            # inserting a replacement. This preserves deliberate legacy
            # repair behavior while remaining atomic.
            if source_ids:
                placeholders = ", ".join("?" for _ in source_ids)
                connection.execute(
                    f"DELETE FROM native_transaction_records WHERE tx_id NOT IN ({placeholders})", tuple(source_ids)
                )
            else:
                connection.execute("DELETE FROM native_transaction_records")
            changed = normalized
        # A reorg can atomically swap ownership of one active sender/nonce.
        # Release every row whose final state is inactive before activating
        # winner or requeued rows, while still passing each real transition
        # through the lifecycle trigger and append-only transition recorder.
        inactive = [
            transaction for transaction in changed
            if str(transaction.get("status") or "").strip().lower()
            not in NATIVE_TRANSACTION_ACTIVE_STATES
        ]
        active = [
            transaction for transaction in changed
            if str(transaction.get("status") or "").strip().lower()
            in NATIVE_TRANSACTION_ACTIVE_STATES
        ]
        for transaction in inactive + active:
            cls._upsert_native_transaction_record(connection, transaction)
        return normalized if previous_transactions is not None else cls._load_native_transaction_records(connection, strict=True)

    @staticmethod
    def _save_sections_to_connection(connection, sections: dict[str, Any]) -> None:
        for section_name in _STORAGE_SECTIONS:
            if section_name == "native_transactions":
                # SQLite loads this section exclusively from its normalized
                # relational table; storing a redundant JSON snapshot makes
                # every pending admission serialize the entire mempool twice.
                continue
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
            self._synchronize_durable_vote_records(connection, sections.get("votes", []))
            self._synchronize_originality_evidence_records(
                connection, sections.get("originality_evidence", []), sections
            )
            self._synchronize_certificate_evidence_bindings(
                connection, sections.get("originality_certificates", [])
            )
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
            "originality_evidence": sections["originality_evidence"],
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
            self._synchronize_durable_vote_records(connection, replacement.get("votes", []))
            self._synchronize_originality_evidence_records(
                connection, replacement.get("originality_evidence", []), replacement
            )
            self._synchronize_certificate_evidence_bindings(
                connection, replacement.get("originality_certificates", [])
            )
            replacement["native_transactions"] = self._synchronize_native_transaction_records(
                connection, replacement.get("native_transactions", []),
                previous_transactions=sections.get("native_transactions", []),
            )
            self._save_sections_to_connection(connection, replacement)
            return replacement

    def atomic_update_blockchain_document(
        self, mutate, *, outbox_records=None, received_peer_message=None,
        copy_document: bool = True,
    ):
        # BEGIN IMMEDIATE serializes competing admissions before they inspect
        # pending balance and nonce reservations.  Returning from this method
        # happens only after the connection context has committed successfully.
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if received_peer_message is not None:
                self._check_received_native_transaction_message(
                    connection, received_peer_message
                )
            sections = self._load_sections_from_connection(connection)
            document = {section: sections[section] for section in _STORAGE_SECTIONS}
            previous_transactions = sections.get("native_transactions", [])
            if copy_document:
                replacement = self._normalize_blockchain_document(mutate(deepcopy(document)))
            else:
                # Native admission receives a just-deserialized document under
                # this transaction and only appends/replaces its own records.
                # Preserve the prior native list for relational synchronization
                # while avoiding repeated deep copies of the growing mempool.
                # The caller still gets no live in-memory state and all writes
                # remain inside this BEGIN IMMEDIATE / commit-before-ack path.
                document["chain"] = list(document["chain"])
                document["transfer_intents"] = list(document["transfer_intents"])
                document["native_transactions"] = list(document["native_transactions"])
                replacement = mutate(document)
            self._synchronize_canonical_claims(connection, replacement)
            self._synchronize_durable_vote_records(connection, replacement.get("votes", []))
            self._synchronize_originality_evidence_records(
                connection, replacement.get("originality_evidence", []), replacement
            )
            self._synchronize_certificate_evidence_bindings(
                connection, replacement.get("originality_certificates", [])
            )
            replacement["native_transactions"] = self._synchronize_native_transaction_records(
                connection, replacement.get("native_transactions", []),
                previous_transactions=previous_transactions,
            )
            records = (
                outbox_records(deepcopy(replacement) if copy_document else replacement)
                if callable(outbox_records)
                else outbox_records
            )
            if records:
                self._insert_native_transaction_outbox_records(connection, records)
            if received_peer_message is not None:
                self._insert_received_native_transaction_message(
                    connection, received_peer_message
                )
            self._save_sections_to_connection(connection, replacement)
            return replacement

    @property
    def supports_durable_peer_outbox(self) -> bool:
        return True

    @staticmethod
    def _bounded_error_detail(value) -> str | None:
        if value in (None, ""):
            return None
        return str(value).strip()[:512]

    @staticmethod
    def _outbox_record_from_row(row) -> dict[str, Any]:
        columns = (
            "outbox_id", "message_id", "message_type", "tx_id",
            "destination_peer_id", "destination_peer_url", "serialized_message",
            "delivery_state", "attempt_count", "created_at", "last_attempt_at",
            "next_attempt_at", "acknowledged_at", "claim_token",
            "claim_expires_at", "last_error_code", "last_error_detail",
        )
        record = dict(zip(columns, row))
        record["message"] = _json_loads_or_default(
            record["serialized_message"], {}, strict=True, label="native transaction outbox message"
        )
        return record

    @classmethod
    def _insert_native_transaction_outbox_records(cls, connection, records) -> None:
        for raw_record in records or []:
            record = dict(raw_record or {})
            required = (
                "outbox_id", "message_id", "message_type", "tx_id",
                "destination_peer_id", "destination_peer_url", "serialized_message",
                "delivery_state", "created_at",
            )
            if any(record.get(field) in (None, "") for field in required):
                raise StorageCorruptionError("Native transaction outbox record is incomplete.")
            existing = connection.execute(
                """SELECT outbox_id, message_type, tx_id, serialized_message
                   FROM native_transaction_peer_outbox
                   WHERE message_id = ? AND destination_peer_id = ?""",
                (record["message_id"], record["destination_peer_id"]),
            ).fetchone()
            expected_identity = (
                record["outbox_id"], record["message_type"], record["tx_id"],
                record["serialized_message"],
            )
            if existing is not None:
                if tuple(existing) != expected_identity:
                    raise StorageUniquenessError(
                        "Native transaction outbox identity conflicts with existing delivery work."
                    )
                continue
            connection.execute(
                """INSERT INTO native_transaction_peer_outbox
                   (outbox_id, message_id, message_type, tx_id, destination_peer_id,
                    destination_peer_url, serialized_message, delivery_state,
                    attempt_count, created_at, last_attempt_at, next_attempt_at,
                    acknowledged_at, claim_token, claim_expires_at,
                    last_error_code, last_error_detail)
                   VALUES (:outbox_id, :message_id, :message_type, :tx_id,
                           :destination_peer_id, :destination_peer_url,
                           :serialized_message, :delivery_state, :attempt_count,
                           :created_at, :last_attempt_at, :next_attempt_at,
                           :acknowledged_at, :claim_token, :claim_expires_at,
                           :last_error_code, :last_error_detail)""",
                {
                    **record,
                    "attempt_count": int(record.get("attempt_count", 0)),
                    "last_attempt_at": record.get("last_attempt_at"),
                    "next_attempt_at": record.get("next_attempt_at"),
                    "acknowledged_at": record.get("acknowledged_at"),
                    "claim_token": record.get("claim_token"),
                    "claim_expires_at": record.get("claim_expires_at"),
                    "last_error_code": record.get("last_error_code"),
                    "last_error_detail": cls._bounded_error_detail(record.get("last_error_detail")),
                },
            )

    @staticmethod
    def _check_received_native_transaction_message(connection, record) -> None:
        record = dict(record or {})
        existing = connection.execute(
            """SELECT message_type, sender_node_id, tx_id, payload_hash
               FROM received_native_transaction_messages WHERE message_id = ?""",
            (record.get("message_id"),),
        ).fetchone()
        if existing is None:
            return
        expected = (
            record.get("message_type"), record.get("sender_node_id"),
            record.get("tx_id"), record.get("payload_hash"),
        )
        if tuple(existing) != expected:
            raise StorageUniquenessError(
                "Peer native transaction message_id conflicts with a previously received message."
            )

    @classmethod
    def _insert_received_native_transaction_message(cls, connection, record) -> None:
        cls._check_received_native_transaction_message(connection, record)
        now = record.get("received_at") or _utc_now_iso()
        connection.execute(
            """INSERT OR IGNORE INTO received_native_transaction_messages
               (message_id, message_type, sender_node_id, tx_id, payload_hash,
                received_at, acknowledged_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                record.get("message_id"), record.get("message_type"),
                record.get("sender_node_id"), record.get("tx_id"),
                record.get("payload_hash"), now,
                record.get("acknowledged_at") or now,
            ),
        )

    def enqueue_native_transaction_outbox(self, records):
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._insert_native_transaction_outbox_records(connection, records)
        return self.list_native_transaction_outbox()

    def list_native_transaction_outbox(
        self, *, delivery_state=None, destination_peer_id=None, tx_id=None
    ):
        clauses = []
        parameters = []
        if delivery_state is not None:
            clauses.append("delivery_state = ?")
            parameters.append(str(delivery_state))
        if destination_peer_id is not None:
            clauses.append("destination_peer_id = ?")
            parameters.append(str(destination_peer_id))
        if tx_id is not None:
            clauses.append("tx_id = ?")
            parameters.append(str(tx_id).strip().lower())
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT outbox_id, message_id, message_type, tx_id,
                          destination_peer_id, destination_peer_url, serialized_message,
                          delivery_state, attempt_count, created_at, last_attempt_at,
                          next_attempt_at, acknowledged_at, claim_token,
                          claim_expires_at, last_error_code, last_error_detail
                   FROM native_transaction_peer_outbox""" + where +
                " ORDER BY created_at, outbox_id",
                tuple(parameters),
            ).fetchall()
        return [self._outbox_record_from_row(row) for row in rows]

    def get_native_transaction_outbox(
        self, *, outbox_id=None, message_id=None, destination_peer_id=None
    ):
        if outbox_id:
            clause, parameters = "outbox_id = ?", (str(outbox_id),)
        elif message_id and destination_peer_id:
            clause = "message_id = ? AND destination_peer_id = ?"
            parameters = (str(message_id), str(destination_peer_id))
        else:
            return None
        with self._connect() as connection:
            row = connection.execute(
                """SELECT outbox_id, message_id, message_type, tx_id,
                          destination_peer_id, destination_peer_url, serialized_message,
                          delivery_state, attempt_count, created_at, last_attempt_at,
                          next_attempt_at, acknowledged_at, claim_token,
                          claim_expires_at, last_error_code, last_error_detail
                   FROM native_transaction_peer_outbox WHERE """ + clause,
                parameters,
            ).fetchone()
        return self._outbox_record_from_row(row) if row else None

    def claim_native_transaction_outbox(
        self, *, destination_peer_id=None, tx_id=None, now=None, lease_seconds=30
    ):
        if int(lease_seconds) < 0:
            raise ValueError("Outbox claim lease_seconds must be non-negative.")
        now_value = (
            datetime.now(timezone.utc)
            if now is None
            else datetime.fromisoformat(str(now).replace("Z", "+00:00"))
        )
        if now_value.tzinfo is None:
            now_value = now_value.replace(tzinfo=timezone.utc)
        now_iso = now_value.astimezone(timezone.utc).isoformat()
        claim_expires_at = (
            now_value.astimezone(timezone.utc) + timedelta(seconds=int(lease_seconds))
        ).isoformat()
        claim_token = secrets.token_hex(16)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """UPDATE native_transaction_peer_outbox
                   SET delivery_state = 'retry_wait', claim_token = NULL,
                       claim_expires_at = NULL, last_error_code = 'claim_expired',
                       last_error_detail = 'Previous delivery claim expired before acknowledgement.'
                   WHERE delivery_state = 'in_flight' AND claim_expires_at <= ?""",
                (now_iso,),
            )
            destination_clause = " AND destination_peer_id = ?" if destination_peer_id else ""
            tx_clause = " AND tx_id = ?" if tx_id else ""
            parameters = [now_iso]
            if destination_peer_id:
                parameters.append(str(destination_peer_id))
            if tx_id:
                parameters.append(str(tx_id).strip().lower())
            row = connection.execute(
                """SELECT outbox_id FROM native_transaction_peer_outbox
                   WHERE delivery_state IN ('queued', 'retry_wait')
                     AND (next_attempt_at IS NULL OR next_attempt_at <= ?)"""
                + destination_clause
                + tx_clause
                + " ORDER BY created_at, outbox_id LIMIT 1",
                tuple(parameters),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """UPDATE native_transaction_peer_outbox
                   SET delivery_state = 'in_flight', attempt_count = attempt_count + 1,
                       last_attempt_at = ?, claim_token = ?, claim_expires_at = ?,
                       last_error_code = NULL, last_error_detail = NULL
                   WHERE outbox_id = ? AND delivery_state IN ('queued', 'retry_wait')""",
                (now_iso, claim_token, claim_expires_at, row[0]),
            )
        return self.get_native_transaction_outbox(outbox_id=row[0])

    def acknowledge_native_transaction_outbox(
        self, *, message_id, destination_peer_id, tx_id, acknowledged_at=None,
        claim_token=None
    ):
        acknowledged_at = acknowledged_at or _utc_now_iso()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT outbox_id, tx_id, delivery_state, claim_token
                   FROM native_transaction_peer_outbox
                   WHERE message_id = ? AND destination_peer_id = ?""",
                (message_id, destination_peer_id),
            ).fetchone()
            if row is None or row[1] != str(tx_id).strip().lower():
                return False
            if row[2] == "acknowledged":
                return True
            if row[2] != "in_flight":
                return False
            if claim_token is not None and row[3] != claim_token:
                return False
            connection.execute(
                """UPDATE native_transaction_peer_outbox
                   SET delivery_state = 'acknowledged', acknowledged_at = ?,
                       claim_token = NULL, claim_expires_at = NULL,
                       next_attempt_at = NULL, last_error_code = NULL,
                       last_error_detail = NULL WHERE outbox_id = ?""",
                (acknowledged_at, row[0]),
            )
            return True

    def fail_native_transaction_outbox(
        self, *, outbox_id, claim_token, error_code, error_detail=None,
        permanent=False, next_attempt_at=None
    ):
        target_state = "permanent_failure" if permanent else "retry_wait"
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """UPDATE native_transaction_peer_outbox
                   SET delivery_state = ?, next_attempt_at = ?, claim_token = NULL,
                       claim_expires_at = NULL, last_error_code = ?,
                       last_error_detail = ?
                   WHERE outbox_id = ? AND delivery_state = 'in_flight'
                     AND claim_token = ?""",
                (
                    target_state, next_attempt_at, str(error_code or "delivery_failed")[:128],
                    self._bounded_error_detail(error_detail), outbox_id, claim_token,
                ),
            )
            return cursor.rowcount == 1

    def refresh_native_transaction_outbox_destination(
        self, *, destination_peer_id, destination_peer_url, now=None, expedite=False
    ):
        """Keep node-ID based delivery stable across peer URL changes.

        Only a positive lifecycle signal (new/re-registered peer) shortens a
        retry wait.  Ordinary periodic reconciliation preserves the persisted
        backoff schedule and attempt history.
        """
        peer_id = str(destination_peer_id or "").strip()
        peer_url = str(destination_peer_url or "").strip().rstrip("/")
        if not peer_id or not peer_url:
            return 0
        now_iso = str(now or _utc_now_iso())
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if expedite:
                cursor = connection.execute(
                    """UPDATE native_transaction_peer_outbox
                       SET destination_peer_url = ?,
                           next_attempt_at = CASE
                               WHEN delivery_state = 'retry_wait' THEN ?
                               ELSE next_attempt_at END
                       WHERE destination_peer_id = ?
                         AND delivery_state IN ('queued', 'retry_wait', 'in_flight')""",
                    (peer_url, now_iso, peer_id),
                )
            else:
                cursor = connection.execute(
                    """UPDATE native_transaction_peer_outbox
                       SET destination_peer_url = ?
                       WHERE destination_peer_id = ?
                         AND delivery_state IN ('queued', 'retry_wait', 'in_flight')""",
                    (peer_url, peer_id),
                )
            return cursor.rowcount

    def get_received_native_transaction_message(self, message_id):
        with self._connect() as connection:
            row = connection.execute(
                """SELECT message_id, message_type, sender_node_id, tx_id,
                          payload_hash, received_at, acknowledged_at
                   FROM received_native_transaction_messages WHERE message_id = ?""",
                (str(message_id).strip().lower(),),
            ).fetchone()
        if row is None:
            return None
        columns = (
            "message_id", "message_type", "sender_node_id", "tx_id",
            "payload_hash", "received_at", "acknowledged_at",
        )
        return dict(zip(columns, row))

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
