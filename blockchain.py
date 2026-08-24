# Import statements
import os
import hashlib
import math
import time
import base64
import binascii
import re
import secrets
from collections import Counter
from pathlib import Path
from PIL import Image
import imagehash
from concurrent.futures import ThreadPoolExecutor
import pytesseract
import time
from block import Block
from transaction import Transaction
from wallet import Wallet
from utils import hash_image
from utils import extract_text
import json
from decimal import Decimal
from datetime import datetime, timezone
from config import (
    ACTIVE_USER_LOOKBACK_DAYS,
    ACTIVE_USER_PERCENT_FOR_MIN_VOTES,
    COIN_NAME,
    ENVIRONMENT,
    MEME_BLOCK_REWARD,
    MAX_BLOCK_SIZE_BYTES,
    MAX_CANONICAL_CONTENT_BYTES,
    MAX_TRANSACTIONS_PER_BLOCK,
    MIN_VOTE_FLOOR,
    NETWORK_NAME,
    NODE_ID,
    ORIGINALITY_APPROVAL_THRESHOLD,
    REWARD_POOL_SUPPLY,
    REQUIRE_ACCESS_FOR_REWARDS,
    TOTAL_SUPPLY,
    VOTER_REWARDS_ENABLED,
    VOTER_REWARD_APPROVAL_SIDE,
    VOTER_REWARD_MAX_PER_WALLET_ZOID,
    VOTER_REWARD_MIN_DECISIVE_VOTES,
    VOTER_REWARD_POOL_PER_DECISION_ZOID,
    VOTER_REWARD_REJECTION_SIDE,
    VOTER_REWARD_REQUIRE_REVIEW_ELIGIBLE,
    VOTING_WINDOW_HOURS,
)
from review_policy import current_day_window, evaluate_review_eligibility, load_review_policy_config
from originality_certificate import OriginalityCertificate, validate_certificate_for_submission
from content import (
    CANONICAL_COMPRESSION_GZIP,
    CANONICAL_COMPRESSION_VERSION,
    CONTENT_TYPE_IMAGE,
    CONTENT_TYPE_MIXED,
    CONTENT_TYPE_TEXT,
    HASH_SCHEME_SHA256_BYTES,
    HASH_SCHEME_LEGACY,
    HASH_SCHEME_SHA256_TEXT,
    HASH_SCHEME_UNKNOWN,
    TEXT_MIME_TYPE,
    _validate_content_type,
    STORAGE_STATUS_LOCAL,
    STORAGE_STATUS_MISSING,
    STORAGE_STATUS_REMOTE,
    STORAGE_STATUS_VERIFIED,
    ContentObject,
    calculate_content_id,
    canonical_compress_content_bytes,
    canonical_decompress_content_bytes,
    canonicalize_text_content,
    compute_content_hash_bytes,
    content_object_from_submission_data,
    compute_text_content_hash,
    ensure_content_storage_dir,
    guess_mime_type,
    resolve_payload_hash,
    resolve_local_path,
    sanitize_original_filename,
    store_content_bytes,
    validate_caption,
    validate_text_content,
    verify_content_object_payload,
)
from submission import APPROVED, HARD_REJECTED, MINTED, PENDING, QUEUED, REJECTED, VOTE_NOT_ORIGINAL, VOTE_ORIGINAL, VOTE_TYPES, VOTE_UNSURE, Submission
from native_transfer import (
    NATIVE_TRANSACTION_INITIAL_NONCE,
    NATIVE_TRANSACTION_NONCE_POLICY,
    build_native_transaction,
    parse_native_zoid_amount,
    parse_transfer_signing_message,
    parse_transfer_nonce,
    validate_transaction_shape,
    verify_transfer_signature,
)
from storage import create_storage_backend
from validators import is_valid_ethereum_address, is_valid_user_wallet_identity
from wallet_auth import normalize_wallet_address
from access_control import access_decision_for_wallet, generate_access_code, hash_access_code, normalize_email, normalize_handle, normalize_text_field, utc_now_iso

ALLOWLIST_SCOPES = {"access", "review", "submission", "voting", "rewards", "all_beta"}
ALLOWLIST_SUBJECT_TYPES = {"wallet", "access_account", "email", "handle"}
ALLOWLIST_STATUSES = {"active", "inactive", "revoked"}
OVERRIDE_REQUEST_STATUSES = {"pending", "approved", "rejected", "duplicate", "spam"}
FEEDBACK_TYPES = {
    "bug",
    "confusing_ui",
    "wallet_connection_issue",
    "mobile_issue",
    "access_allowlist_issue",
    "submission_upload_issue",
    "voting_review_issue",
    "rewards_balance_issue",
    "general_suggestion",
    "other",
}
FEEDBACK_STATUSES = {"new", "reviewed", "in_progress", "resolved", "dismissed"}
ACTIVE_FEEDBACK_STATUSES = {"new", "reviewed", "in_progress"}
CLOSED_FEEDBACK_STATUSES = {"resolved", "dismissed"}
FEEDBACK_PRIORITIES = {"low", "normal", "high", "urgent"}


def _hash_number(value):
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        numeric_value = float(value)
        if numeric_value.is_integer():
            return str(int(numeric_value))
        return str(numeric_value)
    return str(value)


def _coerce_timestamp(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    candidate = str(value).strip()
    if not candidate:
        return None
    try:
        return float(candidate)
    except ValueError:
        pass
    try:
        normalized = candidate.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        return None


_NATIVE_ZOID_REWARD_SCALE = Decimal("1000000")


def _canonical_block_json_bytes(block_dict):
    return json.dumps(
        block_dict,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


class NativeBlockValidationError(ValueError):
    def __init__(self, code, message, *, details=None):
        super().__init__(message)
        self.code = str(code).strip() or "invalid_block"
        self.details = dict(details or {})

    def to_detail(self):
        payload = {"code": self.code, "message": str(self)}
        payload.update(self.details)
        return payload


def _short_public_key(public_key):
    key = str(public_key or "")
    if len(key) <= 18:
        return key or "unknown"
    return f"{key[:10]}...{key[-8:]}"


class Blockchain:
    def __init__(
        self,
        project_owner_wallet=None,
        Contributor_one=None,
        Contributor_two=None,
        initial_supply=TOTAL_SUPPLY,
        storage_backend=None,
    ):
        self.chain = []  # The blockchain
        self.pending_transactions = []  # Transaction pool
        self.wallets = {}  # Registered wallets
        self.text_validation_cache = {}  # Cache for validated texts
        self.image_validation_cache = {}  # Cache for validated images
        self.texts = []  # List of all validated text content
        self.image_hashes = set()  # Set to store unique image hashes
        self.submissions = []  # Submitted content waiting for review or minting
        self.content_objects = []  # Persisted content payload metadata
        self.mint_queue = []  # Approved submissions waiting to be minted
        self.votes = []  # Recorded content votes
        self.transfer_intents = []  # Signed pending native transfer intents
        self.native_transactions = []  # Canonical native transaction records
        self.originality_certificates = []  # Community approval certificates
        self.access_requests = []  # Controlled-testnet access requests
        self.access_accounts = []  # Approved access accounts
        self.wallet_bindings = []  # Wallet-to-access-account bindings
        self.allowlist_entries = []  # Operator-managed beta overrides
        self.override_requests = []  # User-submitted beta override requests
        self.feedback_records = []  # In-app beta feedback records
        self.audit_logs = []  # Persistent admin audit trail
        self._last_reward_excluded_voters = []
        self.reward_pool = REWARD_POOL_SUPPLY  # Initial reward pool
        self.initial_reward_pool = self.reward_pool  # Set the initial reward pool value
        self.storage = storage_backend or create_storage_backend()
        ensure_content_storage_dir(data_dir=self.storage.data_dir)

        # âœ… Store wallets immediately before loading blockchain
        self.project_owner_wallet = project_owner_wallet
        self.Contributor_one = Contributor_one
        self.Contributor_two = Contributor_two

        # âœ… Load blockchain from storage, ensuring wallets persist
        self.load_blockchain()
        if not self.chain:
            print("Debug: No valid blockchain found. Creating Genesis blockchain...")
            self.create_genesis_block(self.project_owner_wallet, self.Contributor_one, self.Contributor_two)

        # âœ… Ensure wallets are always assigned even after loading blockchain
        if self.project_owner_wallet and self.project_owner_wallet.public_key not in self.wallets:
            self.wallets[self.project_owner_wallet.public_key] = self.project_owner_wallet
        if self.Contributor_one and self.Contributor_one.public_key not in self.wallets:
            self.wallets[self.Contributor_one.public_key] = self.Contributor_one
        if self.Contributor_two and self.Contributor_two.public_key not in self.wallets:
            self.wallets[self.Contributor_two.public_key] = self.Contributor_two

        # âœ… Debugging - Print wallet storage
        print("Debug: Registered Wallets -", [_short_public_key(key) for key in self.wallets.keys()])

    def _serialize_blockchain_state(self):
        return {
            "chain": [
                {
                    "index": block.index,
                    "previous_hash": block.previous_hash,
                    "timestamp": block.timestamp,
                    "transactions": [tx.to_dict() for tx in block.transactions],
                    "miner": block.miner,
                    "meme": block.meme,
                    "hash": block.hash,
                    **block.certificate_metadata(),
                }
                for block in self.chain
            ],
            "submissions": [submission.to_dict() for submission in self.submissions],
            "content_objects": [content_object.to_dict() for content_object in self.content_objects],
            "mint_queue": self.mint_queue,
            "votes": self.votes,
            "transfer_intents": self.transfer_intents,
            "native_transactions": self.native_transactions,
            "originality_certificates": [
                certificate.to_dict()
                for certificate in self.originality_certificates
            ],
            "access_requests": self.access_requests,
            "access_accounts": self.access_accounts,
            "wallet_bindings": self.wallet_bindings,
            "allowlist_entries": self.allowlist_entries,
            "override_requests": self.override_requests,
            "feedback_records": self.feedback_records,
            "audit_logs": self.audit_logs,
            "wallets": {key: wallet.to_dict() for key, wallet in self.wallets.items()},
        }

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _coerce_native_event_timestamp(value) -> str:
        if isinstance(value, bool):
            return Blockchain._utc_now_iso()
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        candidate = str(value or "").strip()
        return candidate

    @staticmethod
    def serialized_block_size_bytes(block_or_dict) -> int:
        if isinstance(block_or_dict, dict):
            block_dict = dict(block_or_dict)
        elif hasattr(block_or_dict, "to_dict"):
            block_dict = block_or_dict.to_dict()
        else:
            raise ValueError("Block serialization requires a block object or dictionary.")
        return len(_canonical_block_json_bytes(block_dict))

    def validate_serialized_block_size(self, block_or_dict) -> int:
        size_bytes = self.serialized_block_size_bytes(block_or_dict)
        if size_bytes > MAX_BLOCK_SIZE_BYTES:
            raise ValueError(
                f"Serialized block exceeds MAX_BLOCK_SIZE_BYTES ({MAX_BLOCK_SIZE_BYTES} bytes)."
            )
        return size_bytes

    @staticmethod
    def _build_transfer_intent_record_from_transaction(
        transaction,
        *,
        transfer_id=None,
        signed_at=None,
        created_at=None,
        updated_at=None,
    ):
        payload = transaction.to_dict() if hasattr(transaction, "to_dict") else dict(transaction or {})
        record = {
            "transfer_id": str(transfer_id or os.urandom(16).hex()),
            "tx_id": payload.get("tx_id"),
            "from_address": payload.get("from_address"),
            "to_address": payload.get("to_address"),
            "amount": payload.get("amount"),
            "fee": payload.get("fee"),
            "memo": payload.get("memo"),
            "network": payload.get("network"),
            "signature_scheme": payload.get("signature_scheme"),
            "signature": payload.get("signature"),
            "signed_message": payload.get("signed_message"),
            "signed_message_hash": payload.get("signed_message_hash"),
            "transfer_nonce": payload.get("nonce"),
            "signed_at": str(signed_at or payload.get("timestamp") or payload.get("created_at") or Blockchain._utc_now_iso()),
            "status": payload.get("status"),
            "created_at": str(created_at or payload.get("created_at") or Blockchain._utc_now_iso()),
        }
        if updated_at not in (None, ""):
            record["updated_at"] = str(updated_at)
        return record

    def _restore_native_transaction_state(self, raw_transactions, raw_transfer_intents):
        sanitized_transactions = []
        sanitized_transfer_intents = []
        seen_tx_ids = set()
        seen_nonce_keys = {}
        transfer_ids = set()
        transfer_tx_ids = set()
        changed = False
        removed = 0

        for transaction in list(raw_transactions or []):
            if not isinstance(transaction, dict):
                changed = True
                removed += 1
                continue
            try:
                validated_transaction = self.validate_signed_native_transaction(transaction)
            except ValueError:
                changed = True
                removed += 1
                continue

            tx_id = str(validated_transaction.get("tx_id") or "").strip().lower()
            if tx_id in seen_tx_ids:
                changed = True
                removed += 1
                continue

            status = str(validated_transaction.get("status") or "").strip().lower()
            if status in self._native_nonce_unavailable_statuses():
                nonce_key = (
                    self._normalize_native_wallet_identity(validated_transaction.get("from_address")),
                    self._coerce_native_nonce(validated_transaction.get("nonce")),
                )
                existing_tx_id = seen_nonce_keys.get(nonce_key)
                if existing_tx_id is not None and existing_tx_id != tx_id:
                    changed = True
                    removed += 1
                    continue
                seen_nonce_keys[nonce_key] = tx_id

            if dict(transaction) != validated_transaction:
                changed = True
            sanitized_transactions.append(validated_transaction)
            seen_tx_ids.add(tx_id)

        transactions_by_tx_id = {
            str(transaction.get("tx_id") or "").strip().lower(): dict(transaction)
            for transaction in sanitized_transactions
        }

        for transfer_intent in list(raw_transfer_intents or []):
            if not isinstance(transfer_intent, dict):
                changed = True
                removed += 1
                continue

            transfer_id = str(transfer_intent.get("transfer_id") or "").strip()
            tx_id = str(transfer_intent.get("tx_id") or "").strip().lower()
            if not transfer_id or transfer_id in transfer_ids or not tx_id or tx_id in transfer_tx_ids:
                changed = True
                removed += 1
                continue

            transaction = transactions_by_tx_id.get(tx_id)
            if transaction is None:
                changed = True
                removed += 1
                continue

            rebuilt_record = self._build_transfer_intent_record_from_transaction(
                transaction,
                transfer_id=transfer_id,
                signed_at=transfer_intent.get("signed_at"),
                created_at=transfer_intent.get("created_at"),
                updated_at=transfer_intent.get("updated_at"),
            )
            if dict(transfer_intent) != rebuilt_record:
                changed = True
            sanitized_transfer_intents.append(rebuilt_record)
            transfer_ids.add(transfer_id)
            transfer_tx_ids.add(tx_id)

        for transaction in sanitized_transactions:
            tx_id = str(transaction.get("tx_id") or "").strip().lower()
            if tx_id in transfer_tx_ids:
                continue
            sanitized_transfer_intents.append(
                self._build_transfer_intent_record_from_transaction(transaction)
            )
            transfer_tx_ids.add(tx_id)
            changed = True

        return {
            "native_transactions": sanitized_transactions,
            "transfer_intents": sanitized_transfer_intents,
            "changed": changed,
            "removed": removed,
        }

    def save_blockchain(self):
        """Save blockchain state to disk, including wallets and transactions."""
        self.storage.save_blockchain_state(self._serialize_blockchain_state())
        print("Debug: Blockchain and wallets saved successfully.")

    def refresh_access_control_state_from_storage(self):
        """Refresh only access-control records from storage without reloading the full chain."""
        try:
            loaded_data = self.storage.load_blockchain_state()
        except Exception as exc:
            print(f"Debug: Failed to refresh access control state from storage - {exc}")
            return False

        if not isinstance(loaded_data, dict):
            return False

        self.access_requests = list(loaded_data.get("access_requests", []) or [])
        self.access_accounts = list(loaded_data.get("access_accounts", []) or [])
        self.wallet_bindings = list(loaded_data.get("wallet_bindings", []) or [])
        self.allowlist_entries = list(loaded_data.get("allowlist_entries", []) or [])
        self.override_requests = list(loaded_data.get("override_requests", []) or [])
        self.feedback_records = list(loaded_data.get("feedback_records", []) or [])
        self.audit_logs = list(loaded_data.get("audit_logs", []) or [])
        return True

    @staticmethod
    def _normalize_access_wallet(wallet_address):
        return normalize_wallet_address(wallet_address or "")

    @staticmethod
    def _normalize_allowlist_scope(scope):
        normalized_scope = str(scope or "").strip().lower()
        if normalized_scope not in ALLOWLIST_SCOPES:
            raise ValueError(
                "Allowlist scope must be access, review, submission, voting, rewards, or all_beta."
            )
        return normalized_scope

    @staticmethod
    def _normalize_allowlist_status(status):
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in ALLOWLIST_STATUSES:
            raise ValueError("Allowlist status must be active, inactive, or revoked.")
        return normalized_status

    @staticmethod
    def _normalize_override_request_status(status):
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in OVERRIDE_REQUEST_STATUSES:
            raise ValueError("Override request status must be pending, approved, rejected, duplicate, or spam.")
        return normalized_status

    @staticmethod
    def _normalize_feedback_type(feedback_type):
        normalized_type = str(feedback_type or "").strip().lower()
        if normalized_type not in FEEDBACK_TYPES:
            raise ValueError(
                "Feedback type must be bug, confusing_ui, wallet_connection_issue, mobile_issue, "
                "access_allowlist_issue, submission_upload_issue, voting_review_issue, "
                "rewards_balance_issue, general_suggestion, or other."
            )
        return normalized_type

    @staticmethod
    def _normalize_feedback_status(status):
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in FEEDBACK_STATUSES:
            raise ValueError("Feedback status must be new, reviewed, in_progress, resolved, or dismissed.")
        return normalized_status

    @staticmethod
    def _normalize_feedback_priority(priority):
        normalized_priority = str(priority or "").strip().lower() or "normal"
        if normalized_priority not in FEEDBACK_PRIORITIES:
            raise ValueError("Feedback priority must be low, normal, high, or urgent.")
        return normalized_priority

    @staticmethod
    def _normalize_feedback_dimension(value):
        if value in (None, ""):
            return None
        if isinstance(value, bool):
            raise ValueError("Viewport dimensions must be numeric when provided.")
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Viewport dimensions must be numeric when provided.") from exc
        if number < 0 or number > 20000:
            raise ValueError("Viewport dimensions must be between 0 and 20000.")
        return number

    @staticmethod
    def _normalize_feedback_snapshot(value):
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("Feedback context snapshots must be objects when provided.")
        return json.loads(json.dumps(value))

    @staticmethod
    def _normalize_allowlist_subject(subject_type, subject_value):
        normalized_subject_type = str(subject_type or "").strip().lower()
        if normalized_subject_type not in ALLOWLIST_SUBJECT_TYPES:
            raise ValueError("Allowlist subject_type must be wallet, access_account, email, or handle.")

        if normalized_subject_type == "wallet":
            normalized_subject_value = normalize_wallet_address(subject_value or "")
            if normalized_subject_value is None:
                raise ValueError("Allowlist wallet subject_value must be a valid Ethereum-style 0x address.")
            return normalized_subject_type, normalized_subject_value

        if normalized_subject_type == "access_account":
            normalized_subject_value = normalize_text_field(subject_value)
        elif normalized_subject_type == "email":
            normalized_subject_value = normalize_email(subject_value)
        else:
            normalized_subject_value = normalize_handle(subject_value)

        if not normalized_subject_value:
            raise ValueError("Allowlist subject_value is required.")
        return normalized_subject_type, normalized_subject_value

    @staticmethod
    def _allowlist_scope_matches(entry_scope, requested_scope):
        normalized_entry_scope = str(entry_scope or "").strip().lower()
        normalized_requested_scope = str(requested_scope or "").strip().lower()
        scope_map = {
            "access": {"access", "all_beta"},
            "review": {"review", "all_beta"},
            "submission": {"submission", "review", "all_beta"},
            "voting": {"voting", "review", "all_beta"},
            "rewards": {"rewards", "review", "all_beta"},
            "all_beta": {"all_beta"},
        }
        return normalized_entry_scope in scope_map.get(normalized_requested_scope, set())

    @staticmethod
    def _allowlist_entry_active(entry, *, now_iso=None):
        if str(entry.get("status") or "").strip().lower() != "active":
            return False
        expires_at = str(entry.get("expires_at") or "").strip()
        if expires_at and expires_at <= str(now_iso or utc_now_iso()):
            return False
        return True

    def _allowlist_subject_candidates(self, *, wallet_address=None, access_account=None):
        candidates = []
        normalized_wallet = self._normalize_access_wallet(wallet_address)
        if normalized_wallet:
            candidates.append(("wallet", normalized_wallet))
        if access_account:
            access_account_id = normalize_text_field(access_account.get("access_account_id"))
            email = normalize_email(access_account.get("email"))
            handle = normalize_handle(access_account.get("handle"))
            if access_account_id:
                candidates.append(("access_account", access_account_id))
            if email:
                candidates.append(("email", email))
            if handle:
                candidates.append(("handle", handle))
        return candidates

    def get_allowlist_entry(self, allowlist_entry_id):
        candidate = str(allowlist_entry_id or "").strip()
        if not candidate:
            return None
        for entry in self.allowlist_entries:
            if str(entry.get("allowlist_entry_id") or "").strip() == candidate:
                return entry
        return None

    def list_allowlist_entries(self, *, scope=None, subject_type=None, subject_value=None, status=None):
        entries = list(self.allowlist_entries)
        normalized_subject_type = None
        if scope is not None:
            normalized_scope = str(scope or "").strip().lower()
            entries = [
                entry for entry in entries
                if str(entry.get("scope") or "").strip().lower() == normalized_scope
            ]
        if subject_type is not None:
            normalized_subject_type = str(subject_type or "").strip().lower()
            entries = [
                entry for entry in entries
                if str(entry.get("subject_type") or "").strip().lower() == normalized_subject_type
            ]
        if subject_value is not None:
            if normalized_subject_type == "wallet":
                normalized_subject_value = self._normalize_access_wallet(subject_value)
            elif normalized_subject_type == "email":
                normalized_subject_value = normalize_email(subject_value)
            elif normalized_subject_type == "handle":
                normalized_subject_value = normalize_handle(subject_value)
            elif normalized_subject_type == "access_account":
                normalized_subject_value = normalize_text_field(subject_value)
            else:
                normalized_subject_value = normalize_text_field(subject_value)
            entries = [
                entry for entry in entries
                if str(entry.get("subject_value") or "").strip() == normalized_subject_value
            ]
        if status is not None:
            normalized_status = str(status or "").strip().lower()
            entries = [
                entry for entry in entries
                if str(entry.get("status") or "").strip().lower() == normalized_status
            ]
        entries.sort(key=lambda entry: str(entry.get("updated_at") or entry.get("created_at") or ""), reverse=True)
        return entries

    def find_matching_allowlist_entry(self, scope, *, wallet_address=None, access_account=None):
        normalized_scope = self._normalize_allowlist_scope(scope)
        candidates = self._allowlist_subject_candidates(
            wallet_address=wallet_address,
            access_account=access_account,
        )
        if not candidates:
            return None

        now_iso = utc_now_iso()
        subject_priority = {subject_type: index for index, (subject_type, _value) in enumerate(candidates)}
        for entry in sorted(
            self.allowlist_entries,
            key=lambda item: (
                subject_priority.get(str(item.get("subject_type") or "").strip().lower(), 999),
                str(item.get("updated_at") or item.get("created_at") or ""),
            ),
            reverse=False,
        ):
            if not self._allowlist_entry_active(entry, now_iso=now_iso):
                continue
            if not self._allowlist_scope_matches(entry.get("scope"), normalized_scope):
                continue
            entry_subject_type = str(entry.get("subject_type") or "").strip().lower()
            entry_subject_value = str(entry.get("subject_value") or "").strip()
            for subject_type, subject_value in candidates:
                if entry_subject_type == subject_type and entry_subject_value == subject_value:
                    return entry
        return None

    def create_allowlist_entry(
        self,
        *,
        scope,
        subject_type,
        subject_value,
        reason=None,
        expires_at=None,
        created_by=None,
        status="active",
    ):
        normalized_scope = self._normalize_allowlist_scope(scope)
        normalized_subject_type, normalized_subject_value = self._normalize_allowlist_subject(
            subject_type,
            subject_value,
        )
        normalized_status = self._normalize_allowlist_status(status)
        timestamp = utc_now_iso()
        entry = {
            "allowlist_entry_id": secrets.token_hex(16),
            "scope": normalized_scope,
            "subject_type": normalized_subject_type,
            "subject_value": normalized_subject_value,
            "status": normalized_status,
            "reason": normalize_text_field(reason),
            "created_at": timestamp,
            "updated_at": timestamp,
            "expires_at": normalize_text_field(expires_at) or None,
            "created_by": normalize_text_field(created_by),
            "revoked_at": None,
            "revoked_reason": "",
        }
        self.allowlist_entries.append(entry)
        return entry

    def update_allowlist_entry(
        self,
        allowlist_entry_id,
        *,
        scope=None,
        subject_type=None,
        subject_value=None,
        reason=None,
        expires_at=None,
        status=None,
    ):
        entry = self.get_allowlist_entry(allowlist_entry_id)
        if entry is None:
            raise ValueError(f"Allowlist entry not found: {allowlist_entry_id}")

        if scope is not None:
            entry["scope"] = self._normalize_allowlist_scope(scope)
        if subject_type is not None or subject_value is not None:
            next_subject_type = subject_type if subject_type is not None else entry.get("subject_type")
            next_subject_value = subject_value if subject_value is not None else entry.get("subject_value")
            normalized_subject_type, normalized_subject_value = self._normalize_allowlist_subject(
                next_subject_type,
                next_subject_value,
            )
            entry["subject_type"] = normalized_subject_type
            entry["subject_value"] = normalized_subject_value
        if reason is not None:
            entry["reason"] = normalize_text_field(reason)
        if expires_at is not None:
            entry["expires_at"] = normalize_text_field(expires_at) or None
        if status is not None:
            normalized_status = self._normalize_allowlist_status(status)
            if normalized_status == "revoked":
                raise ValueError("Use revoke_allowlist_entry to revoke an allowlist entry.")
            entry["status"] = normalized_status
        entry["updated_at"] = utc_now_iso()
        return entry

    def revoke_allowlist_entry(self, allowlist_entry_id, *, revoked_reason=None):
        entry = self.get_allowlist_entry(allowlist_entry_id)
        if entry is None:
            raise ValueError(f"Allowlist entry not found: {allowlist_entry_id}")
        timestamp = utc_now_iso()
        entry["status"] = "revoked"
        entry["updated_at"] = timestamp
        entry["revoked_at"] = timestamp
        entry["revoked_reason"] = normalize_text_field(revoked_reason)
        return entry

    def reactivate_allowlist_entry(self, allowlist_entry_id, *, reason=None):
        entry = self.get_allowlist_entry(allowlist_entry_id)
        if entry is None:
            raise ValueError(f"Allowlist entry not found: {allowlist_entry_id}")
        entry["status"] = "active"
        if reason is not None:
            entry["reason"] = normalize_text_field(reason)
        entry["updated_at"] = utc_now_iso()
        entry["revoked_at"] = None
        entry["revoked_reason"] = ""
        return entry

    def get_override_request(self, override_request_id):
        candidate = str(override_request_id or "").strip()
        if not candidate:
            return None
        for request_record in self.override_requests:
            if str(request_record.get("override_request_id") or "").strip() == candidate:
                return request_record
        return None

    def list_override_requests(self, *, status=None, requested_scope=None):
        records = list(self.override_requests)
        if status is not None:
            normalized_status = str(status or "").strip().lower()
            records = [
                record for record in records
                if str(record.get("status") or "").strip().lower() == normalized_status
            ]
        if requested_scope is not None:
            normalized_scope = str(requested_scope or "").strip().lower()
            records = [
                record for record in records
                if str(record.get("requested_scope") or "").strip().lower() == normalized_scope
            ]
        records.sort(key=lambda record: str(record.get("updated_at") or record.get("created_at") or ""), reverse=True)
        return records

    def get_feedback(self, feedback_id):
        candidate = str(feedback_id or "").strip()
        if not candidate:
            return None
        for record in self.feedback_records:
            if str(record.get("feedback_id") or "").strip() == candidate:
                return record
        return None

    def list_feedback(self, *, status=None, feedback_type=None, priority=None, limit=None):
        records = list(self.feedback_records)
        if status is not None:
            requested_status = str(status or "").strip().lower()
            if requested_status == "active":
                records = [
                    record for record in records
                    if str(record.get("status") or "").strip().lower() in ACTIVE_FEEDBACK_STATUSES
                ]
            elif requested_status == "closed":
                records = [
                    record for record in records
                    if str(record.get("status") or "").strip().lower() in CLOSED_FEEDBACK_STATUSES
                ]
            elif requested_status:
                normalized_status = self._normalize_feedback_status(requested_status)
                records = [
                    record for record in records
                    if str(record.get("status") or "").strip().lower() == normalized_status
                ]
        if feedback_type is not None:
            normalized_type = self._normalize_feedback_type(feedback_type)
            records = [
                record for record in records
                if str(record.get("type") or "").strip().lower() == normalized_type
            ]
        if priority is not None:
            normalized_priority = self._normalize_feedback_priority(priority)
            records = [
                record for record in records
                if str(record.get("priority") or "").strip().lower() == normalized_priority
            ]
        records.sort(key=lambda record: str(record.get("updated_at") or record.get("created_at") or ""), reverse=True)
        if limit is not None:
            try:
                limit_value = max(0, int(limit))
            except (TypeError, ValueError):
                limit_value = 0
            if limit_value:
                records = records[:limit_value]
        return records

    def feedback_summary(self) -> dict:
        records = self.list_feedback()
        high_priorities = {"high", "urgent"}
        return {
            "new_feedback_count": sum(1 for record in records if str(record.get("status") or "").strip().lower() == "new"),
            "open_feedback_count": sum(
                1 for record in records
                if str(record.get("status") or "").strip().lower() in ACTIVE_FEEDBACK_STATUSES
            ),
            "high_priority_feedback_count": sum(
                1 for record in records
                if str(record.get("status") or "").strip().lower() in ACTIVE_FEEDBACK_STATUSES
                and str(record.get("priority") or "").strip().lower() in high_priorities
            ),
            "latest_feedback_timestamp": next(
                (
                    str(record.get("created_at") or "").strip()
                    for record in records
                    if str(record.get("created_at") or "").strip()
                ),
                None,
            ),
        }

    def create_feedback(
        self,
        *,
        feedback_type,
        title,
        description,
        name=None,
        email=None,
        handle=None,
        wallet_address=None,
        access_account_id=None,
        current_page=None,
        current_flow=None,
        user_agent=None,
        remote_ip=None,
        browser_metadata=None,
        eligibility_snapshot=None,
        viewport_width=None,
        viewport_height=None,
        is_mobile=None,
        priority="normal",
    ):
        timestamp = utc_now_iso()
        normalized_wallet = self._normalize_access_wallet(wallet_address) if wallet_address else None
        record = {
            "feedback_id": secrets.token_hex(16),
            "type": self._normalize_feedback_type(feedback_type),
            "title": normalize_text_field(title),
            "description": normalize_text_field(description),
            "status": "new",
            "priority": self._normalize_feedback_priority(priority),
            "name": normalize_text_field(name),
            "email": normalize_email(email),
            "handle": normalize_handle(handle),
            "wallet_address": normalized_wallet,
            "access_account_id": normalize_text_field(access_account_id),
            "current_page": normalize_text_field(current_page)[:240],
            "current_flow": normalize_text_field(current_flow)[:128],
            "user_agent": normalize_text_field(user_agent)[:240],
            "remote_ip": normalize_text_field(remote_ip)[:120],
            "browser_metadata": self._normalize_feedback_snapshot(browser_metadata),
            "eligibility_snapshot": self._normalize_feedback_snapshot(eligibility_snapshot),
            "viewport_width": self._normalize_feedback_dimension(viewport_width),
            "viewport_height": self._normalize_feedback_dimension(viewport_height),
            "is_mobile": bool(is_mobile) if is_mobile is not None else None,
            "admin_notes": [],
            "created_at": timestamp,
            "updated_at": timestamp,
            "reviewed_at": None,
            "reviewed_by": None,
            "status_updated_at": timestamp,
            "status_updated_by": None,
            "resolved_at": None,
            "dismissed_at": None,
        }
        if not record["title"]:
            raise ValueError("Feedback title is required.")
        if not record["description"]:
            raise ValueError("Feedback description is required.")
        self.feedback_records.append(record)
        return record

    def update_feedback(
        self,
        feedback_id,
        *,
        status=None,
        priority=None,
        reviewed_by="operator",
    ):
        record = self.get_feedback(feedback_id)
        if record is None:
            raise ValueError(f"Feedback not found: {feedback_id}")

        timestamp = utc_now_iso()
        if status is not None:
            normalized_status = self._normalize_feedback_status(status)
            record["status"] = normalized_status
            record["status_updated_at"] = timestamp
            record["status_updated_by"] = normalize_text_field(reviewed_by)
            if normalized_status != "new" and not record.get("reviewed_at"):
                record["reviewed_at"] = timestamp
                record["reviewed_by"] = normalize_text_field(reviewed_by)
            if normalized_status == "resolved":
                record["resolved_at"] = timestamp
                record["dismissed_at"] = None
            elif normalized_status == "dismissed":
                record["dismissed_at"] = timestamp
                record["resolved_at"] = None
            else:
                record["resolved_at"] = None
                record["dismissed_at"] = None
        if priority is not None:
            record["priority"] = self._normalize_feedback_priority(priority)
        record["updated_at"] = timestamp
        return record

    def add_feedback_admin_note(self, feedback_id, *, note, created_by="operator"):
        record = self.get_feedback(feedback_id)
        if record is None:
            raise ValueError(f"Feedback not found: {feedback_id}")
        note_text = normalize_text_field(note)
        if not note_text:
            raise ValueError("Admin note is required.")
        note_record = {
            "note_id": secrets.token_hex(12),
            "note": note_text,
            "created_at": utc_now_iso(),
            "created_by": normalize_text_field(created_by) or "operator",
        }
        notes = list(record.get("admin_notes") or [])
        notes.append(note_record)
        record["admin_notes"] = notes
        record["updated_at"] = note_record["created_at"]
        return note_record

    def create_override_request(
        self,
        *,
        requested_scope,
        name=None,
        email=None,
        handle=None,
        wallet_address=None,
        access_account_id=None,
        reason=None,
        current_page=None,
        detected_blocked_reason=None,
        user_agent=None,
        remote_ip=None,
    ):
        normalized_scope = self._normalize_allowlist_scope(requested_scope)
        normalized_wallet = self._normalize_access_wallet(wallet_address) if wallet_address else None
        timestamp = utc_now_iso()
        record = {
            "override_request_id": secrets.token_hex(16),
            "requested_scope": normalized_scope,
            "name": normalize_text_field(name),
            "email": normalize_email(email),
            "handle": normalize_handle(handle),
            "wallet_address": normalized_wallet,
            "access_account_id": normalize_text_field(access_account_id),
            "reason": normalize_text_field(reason),
            "current_page": normalize_text_field(current_page),
            "detected_blocked_reason": normalize_text_field(detected_blocked_reason),
            "user_agent": normalize_text_field(user_agent)[:240],
            "remote_ip": normalize_text_field(remote_ip)[:120],
            "status": "pending",
            "created_at": timestamp,
            "updated_at": timestamp,
            "reviewed_at": None,
            "reviewed_by": None,
            "admin_note": "",
            "resolved_scope": None,
            "approved_allowlist_entry_id": None,
        }
        self.override_requests.append(record)
        return record

    def update_override_request_status(
        self,
        override_request_id,
        *,
        status,
        reviewed_by="operator",
        admin_note=None,
        resolved_scope=None,
        approved_allowlist_entry_id=None,
    ):
        record = self.get_override_request(override_request_id)
        if record is None:
            raise ValueError(f"Override request not found: {override_request_id}")
        normalized_status = self._normalize_override_request_status(status)
        record["status"] = normalized_status
        record["updated_at"] = utc_now_iso()
        record["reviewed_at"] = record["updated_at"]
        record["reviewed_by"] = normalize_text_field(reviewed_by)
        record["admin_note"] = normalize_text_field(admin_note)
        record["resolved_scope"] = (
            self._normalize_allowlist_scope(resolved_scope)
            if resolved_scope is not None
            else record.get("resolved_scope")
        )
        record["approved_allowlist_entry_id"] = normalize_text_field(approved_allowlist_entry_id)
        return record

    def get_access_request(self, request_id):
        candidate = str(request_id or "").strip()
        if not candidate:
            return None
        for request_record in self.access_requests:
            if str(request_record.get("request_id") or "").strip() == candidate:
                return request_record
        return None

    def get_access_account(self, access_account_id):
        candidate = str(access_account_id or "").strip()
        if not candidate:
            return None
        for account in self.access_accounts:
            if str(account.get("access_account_id") or "").strip() == candidate:
                return account
        return None

    def get_wallet_binding(self, wallet_address):
        normalized_wallet = self._normalize_access_wallet(wallet_address)
        if normalized_wallet is None:
            return None
        for binding in self.wallet_bindings:
            if self._normalize_access_wallet(binding.get("wallet_address")) == normalized_wallet:
                return binding
        return None

    def get_access_account_for_wallet(self, wallet_address):
        binding = self.get_wallet_binding(wallet_address)
        if not binding:
            return None
        return self.get_access_account(binding.get("access_account_id"))

    def list_access_requests(self, *, status=None):
        if status is None:
            return list(self.access_requests)
        normalized_status = str(status or "").strip().lower()
        return [
            request_record
            for request_record in self.access_requests
            if str(request_record.get("status") or "").strip().lower() == normalized_status
        ]

    def list_access_accounts(self, *, status=None):
        if status is None:
            return list(self.access_accounts)
        normalized_status = str(status or "").strip().lower()
        return [
            account
            for account in self.access_accounts
            if str(account.get("status") or "").strip().lower() == normalized_status
        ]

    def count_active_wallet_bindings(self):
        return sum(
            1
            for binding in self.wallet_bindings
            if str(binding.get("status") or "").strip().lower() == "active"
        )

    def list_wallet_bindings(self, *, access_account_id=None, status=None):
        records = list(self.wallet_bindings)
        if access_account_id is not None:
            candidate_account_id = str(access_account_id or "").strip()
            records = [
                binding
                for binding in records
                if str(binding.get("access_account_id") or "").strip() == candidate_account_id
            ]
        if status is not None:
            normalized_status = str(status or "").strip().lower()
            records = [
                binding
                for binding in records
                if str(binding.get("status") or "").strip().lower() == normalized_status
            ]
        return records

    def append_audit_log_entry(self, entry):
        normalized_entry = dict(entry or {})
        normalized_entry.setdefault("audit_id", secrets.token_hex(16))
        normalized_entry.setdefault("timestamp", utc_now_iso())
        normalized_entry["action"] = normalize_text_field(normalized_entry.get("action"))
        normalized_entry["result"] = normalize_text_field(normalized_entry.get("result")) or "ok"
        self.audit_logs.append(normalized_entry)
        return normalized_entry

    def list_audit_log_entries(self, *, action=None, since=None, before=None, limit=None):
        entries = list(self.audit_logs)
        if action:
            normalized_action = str(action or "").strip().lower()
            entries = [
                entry
                for entry in entries
                if str(entry.get("action") or "").strip().lower() == normalized_action
            ]
        if since:
            entries = [
                entry
                for entry in entries
                if str(entry.get("timestamp") or "").strip() >= str(since).strip()
            ]
        if before:
            entries = [
                entry
                for entry in entries
                if str(entry.get("timestamp") or "").strip() <= str(before).strip()
            ]
        entries.sort(key=lambda entry: str(entry.get("timestamp") or ""), reverse=True)
        if limit is not None:
            try:
                limit_value = max(0, int(limit))
            except (TypeError, ValueError):
                limit_value = 0
            if limit_value:
                entries = entries[:limit_value]
        return entries

    def create_access_request(self, *, name, email, handle=None, reason=None, notes=None):
        normalized_email = normalize_email(email)
        if not normalized_email:
            raise ValueError("email is required.")
        request_record = {
            "request_id": secrets.token_hex(16),
            "name": normalize_text_field(name),
            "email": normalized_email,
            "handle": normalize_handle(handle),
            "reason": normalize_text_field(reason),
            "notes": normalize_text_field(notes),
            "status": "pending",
            "created_at": utc_now_iso(),
            "reviewed_at": None,
            "reviewed_by": None,
            "operator_notes": "",
            "approved_access_account_id": None,
        }
        self.access_requests.append(request_record)
        return request_record

    def _create_access_account_record(
        self,
        *,
        name,
        email,
        handle=None,
        notes=None,
        reviewed_by="operator",
        operator_notes=None,
        max_wallets=1,
    ):
        access_code = generate_access_code()
        approved_at = utc_now_iso()
        reviewed_by_value = normalize_text_field(reviewed_by)
        operator_notes_value = normalize_text_field(operator_notes)
        account = {
            "access_account_id": secrets.token_hex(16),
            "name": normalize_text_field(name),
            "email": normalize_email(email),
            "handle": normalize_handle(handle),
            "status": "active",
            "created_at": utc_now_iso(),
            "approved_at": approved_at,
            "invite_code_generated_at": approved_at,
            "invite_code_hash": hash_access_code(access_code),
            "redeemed_invite_code_hash": None,
            "invite_code_redeemed_at": None,
            "bound_wallets": [],
            "max_wallets": int(max_wallets),
            "notes": normalize_text_field(notes),
            "operator_notes": operator_notes_value,
            "reviewed_by": reviewed_by_value,
            "last_login_at": None,
            "status_updated_at": approved_at,
            "status_updated_by": reviewed_by_value,
            "status_reason": operator_notes_value,
        }
        self.access_accounts.append(account)
        return account, access_code

    def create_access_invite(
        self,
        *,
        name,
        email,
        handle=None,
        notes=None,
        reviewed_by="operator",
        operator_notes=None,
        max_wallets=1,
    ):
        if not normalize_email(email):
            raise ValueError("email is required.")
        return self._create_access_account_record(
            name=name,
            email=email,
            handle=handle,
            notes=notes,
            reviewed_by=reviewed_by,
            operator_notes=operator_notes,
            max_wallets=max_wallets,
        )

    def approve_access_request(self, request_id, *, reviewed_by="operator", operator_notes=None, max_wallets=1):
        request_record = self.get_access_request(request_id)
        if request_record is None:
            raise ValueError(f"Access request not found: {request_id}")
        if str(request_record.get("status") or "").strip().lower() == "approved":
            access_account = self.get_access_account(request_record.get("approved_access_account_id"))
            if access_account is None:
                raise ValueError("Access request was approved but the access account is missing.")
            return access_account, None
        if str(request_record.get("status") or "").strip().lower() == "rejected":
            raise ValueError("Rejected access requests cannot be approved later.")
        account, access_code = self._create_access_account_record(
            name=request_record.get("name"),
            email=request_record.get("email"),
            handle=request_record.get("handle"),
            notes=request_record.get("notes"),
            reviewed_by=reviewed_by,
            operator_notes=operator_notes,
            max_wallets=max_wallets,
        )
        request_record["status"] = "approved"
        request_record["reviewed_at"] = utc_now_iso()
        request_record["reviewed_by"] = normalize_text_field(reviewed_by)
        request_record["operator_notes"] = normalize_text_field(operator_notes)
        request_record["approved_access_account_id"] = account["access_account_id"]
        return account, access_code

    def reject_access_request(self, request_id, *, reviewed_by="operator", operator_notes=None):
        request_record = self.get_access_request(request_id)
        if request_record is None:
            raise ValueError(f"Access request not found: {request_id}")
        request_record["status"] = "rejected"
        request_record["reviewed_at"] = utc_now_iso()
        request_record["reviewed_by"] = normalize_text_field(reviewed_by)
        request_record["operator_notes"] = normalize_text_field(operator_notes)
        return request_record

    def resolve_access_account_by_invite_code(self, access_code, *, include_redeemed=False):
        code_hash = hash_access_code(access_code)
        for account in self.access_accounts:
            if str(account.get("invite_code_hash") or "").strip() == code_hash:
                return account
            if include_redeemed and str(account.get("redeemed_invite_code_hash") or "").strip() == code_hash:
                return account
        return None

    def mark_access_account_login(self, access_account_id):
        account = self.get_access_account(access_account_id)
        if account is None:
            raise ValueError(f"Access account not found: {access_account_id}")
        account["last_login_at"] = utc_now_iso()
        return account

    def bind_wallet_to_access_account(self, access_account_id, wallet_address, *, source="invite_code"):
        account = self.get_access_account(access_account_id)
        if account is None:
            raise ValueError(f"Access account not found: {access_account_id}")
        normalized_wallet = self._normalize_access_wallet(wallet_address)
        if normalized_wallet is None:
            raise ValueError("Invalid wallet address. Expected an Ethereum-style 0x address.")
        status = str(account.get("status") or "").strip().lower()
        if status != "active":
            raise ValueError(f"Access account is {status or 'inactive'}.")

        existing_binding = self.get_wallet_binding(normalized_wallet)
        if existing_binding:
            existing_account_id = str(existing_binding.get("access_account_id") or "").strip()
            if existing_account_id != account["access_account_id"]:
                raise ValueError("Wallet is already bound to a different access account.")
            if str(existing_binding.get("status") or "").strip().lower() != "active":
                existing_binding["status"] = "active"
                existing_binding["bound_at"] = existing_binding.get("bound_at") or utc_now_iso()
                existing_binding["revoked_at"] = None
                existing_binding["revoked_by"] = ""
                existing_binding["revoke_reason"] = ""
            if normalized_wallet not in account["bound_wallets"]:
                account["bound_wallets"].append(normalized_wallet)
            if account.get("invite_code_hash"):
                account["redeemed_invite_code_hash"] = account.get("invite_code_hash")
                account["invite_code_hash"] = None
            if account.get("redeemed_invite_code_hash") and not account.get("invite_code_redeemed_at"):
                account["invite_code_redeemed_at"] = utc_now_iso()
            return existing_binding

        bound_wallets = [
            wallet
            for wallet in account.get("bound_wallets", [])
            if self._normalize_access_wallet(wallet) is not None
        ]
        account["bound_wallets"] = bound_wallets
        max_wallets = int(account.get("max_wallets") or 1)
        if len(bound_wallets) >= max_wallets:
            raise ValueError("Access account has reached the maximum number of bound wallets.")

        binding = {
            "wallet_address": normalized_wallet,
            "access_account_id": account["access_account_id"],
            "bound_at": utc_now_iso(),
            "status": "active",
            "source": normalize_text_field(source) or "invite_code",
            "revoked_at": None,
            "revoked_by": "",
            "revoke_reason": "",
        }
        self.wallet_bindings.append(binding)
        account["bound_wallets"].append(normalized_wallet)
        if account.get("invite_code_hash"):
            account["redeemed_invite_code_hash"] = account.get("invite_code_hash")
            account["invite_code_hash"] = None
            account["invite_code_redeemed_at"] = utc_now_iso()
        return binding

    def update_access_account_status(self, access_account_id, status, *, updated_by="operator", reason=None):
        account = self.get_access_account(access_account_id)
        if account is None:
            raise ValueError(f"Access account not found: {access_account_id}")
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in {"active", "suspended", "revoked"}:
            raise ValueError("Access account status must be active, suspended, or revoked.")
        account["status"] = normalized_status
        account["status_updated_at"] = utc_now_iso()
        account["status_updated_by"] = normalize_text_field(updated_by)
        account["status_reason"] = normalize_text_field(reason)
        return account

    def revoke_wallet_binding(self, wallet_address, *, revoked_by="operator", reason=None):
        binding = self.get_wallet_binding(wallet_address)
        if binding is None:
            raise ValueError(f"Wallet binding not found: {wallet_address}")
        binding["status"] = "revoked"
        binding["revoked_at"] = utc_now_iso()
        binding["revoked_by"] = normalize_text_field(revoked_by)
        binding["revoke_reason"] = normalize_text_field(reason)
        account = self.get_access_account(binding.get("access_account_id"))
        normalized_wallet = self._normalize_access_wallet(binding.get("wallet_address"))
        if account is not None and normalized_wallet in account.get("bound_wallets", []):
            account["bound_wallets"] = [
                wallet for wallet in account.get("bound_wallets", [])
                if self._normalize_access_wallet(wallet) != normalized_wallet
            ]
        return binding

    def recompute_reward_pool_balance(self, *, chain=None):
        reward_pool = float(REWARD_POOL_SUPPLY)
        initial_reward_pool = float(REWARD_POOL_SUPPLY)
        for block in chain or self.chain:
            transactions = block.get("transactions", []) if isinstance(block, dict) else block.transactions
            for transaction in transactions:
                sender_value = transaction.get("sender") if isinstance(transaction, dict) else transaction.sender
                amount_value = transaction.get("amount") if isinstance(transaction, dict) else transaction.amount
                tip_value = transaction.get("tip", 0) if isinstance(transaction, dict) else transaction.tip
                sender = self._normalize_native_wallet_identity(sender_value) or sender_value
                tip = float(tip_value or 0)
                if sender not in {None, "", "GENESIS", "REWARD_POOL"} and tip > 0:
                    tip_split = {"miner": 0.25, "reward_pool": 0.75} if reward_pool < (initial_reward_pool * 0.25) else {"miner": 0.5, "reward_pool": 0.5}
                    reward_pool += tip * tip_split["reward_pool"]
                if sender_value == "REWARD_POOL":
                    reward_pool -= float(amount_value or 0)
        self.reward_pool = reward_pool
        self.initial_reward_pool = initial_reward_pool
        return reward_pool

    def load_blockchain(self):
        """Load blockchain state from disk if it exists, ensuring wallets persist."""
        try:
            loaded_data = self.storage.load_blockchain_state()

            if isinstance(loaded_data, dict) and "chain" in loaded_data and "wallets" in loaded_data:
                self.chain = [
                    Block(
                        index=block_data["index"],
                        previous_hash=block_data["previous_hash"],
                        timestamp=block_data["timestamp"],
                        transactions=[Transaction.from_dict(tx) for tx in block_data["transactions"]],
                        miner=block_data["miner"],
                        meme=block_data.get("meme", {}),
                        hash=block_data.get("hash"),
                        submission_id=block_data.get("submission_id"),
                        certificate_id=block_data.get("certificate_id"),
                        content_hash=block_data.get("content_hash"),
                        original_content_hash=block_data.get("original_content_hash"),
                        content_id=block_data.get("content_id"),
                        content_type=block_data.get("content_type"),
                        mime_type=block_data.get("mime_type"),
                        compression_algorithm=block_data.get("compression_algorithm"),
                        compression_version=block_data.get("compression_version"),
                        canonical_size_bytes=block_data.get("canonical_size_bytes"),
                        original_size_bytes=block_data.get("original_size_bytes"),
                        creator_wallet=block_data.get("creator_wallet"),
                        vote_hash=block_data.get("vote_hash"),
                        approval_percentage=block_data.get("approval_percentage"),
                        decisive_vote_total=block_data.get("decisive_vote_total"),
                        minimum_votes_required=block_data.get("minimum_votes_required"),
                        minimum_decisive_votes_required=block_data.get("minimum_decisive_votes_required"),
                        approved_at=block_data.get("approved_at"),
                        originality_score=block_data.get("originality_score"),
                        reward_type=block_data.get("reward_type"),
                        reward_recipient=block_data.get("reward_recipient"),
                        reward_amount=block_data.get("reward_amount"),
                        reward_source=block_data.get("reward_source"),
                        minted_at=block_data.get("minted_at"),
                        voter_rewards=block_data.get("voter_rewards", []),
                        native_transactions=block_data.get("native_transactions", []),
                        transaction_ids=block_data.get("transaction_ids"),
                        transaction_count=block_data.get("transaction_count"),
                        transactions_hash=block_data.get("transactions_hash"),
                    )
                    for block_data in loaded_data["chain"]
                ]

                self.wallets = {key: Wallet.from_dict(data) for key, data in loaded_data["wallets"].items()}

                print("Debug: Blockchain and wallets loaded successfully from blockchain.json.")

                self.submissions = [
                    Submission.from_dict(submission_data)
                    for submission_data in loaded_data.get("submissions", [])
                ]
                self.content_objects = [
                    ContentObject.from_dict(content_object_data)
                    for content_object_data in loaded_data.get("content_objects", [])
                ]
                self.mint_queue = loaded_data.get("mint_queue", [])
                self.votes = loaded_data.get("votes", [])
                native_state = self._restore_native_transaction_state(
                    loaded_data.get("native_transactions", []),
                    loaded_data.get("transfer_intents", []),
                )
                self.transfer_intents = native_state["transfer_intents"]
                self.native_transactions = native_state["native_transactions"]
                self.originality_certificates = [
                    OriginalityCertificate.from_dict(certificate_data)
                    for certificate_data in loaded_data.get("originality_certificates", [])
                ]
                self.access_requests = list(loaded_data.get("access_requests", []) or [])
                self.access_accounts = list(loaded_data.get("access_accounts", []) or [])
                self.wallet_bindings = list(loaded_data.get("wallet_bindings", []) or [])
                self.allowlist_entries = list(loaded_data.get("allowlist_entries", []) or [])
                self.override_requests = list(loaded_data.get("override_requests", []) or [])
                self.feedback_records = list(loaded_data.get("feedback_records", []) or [])
                self.audit_logs = list(loaded_data.get("audit_logs", []) or [])
                self.recompute_reward_pool_balance(chain=self.chain)
                self.link_content_objects_to_submissions()
                self.refresh_content_object_storage_statuses()
                self.link_certificates_to_submissions()
                mempool_report = self.revalidate_mempool_transactions(save=False)
                if native_state["changed"] or mempool_report["removed"] > 0:
                    self.save_blockchain()
                if native_state["removed"] > 0:
                    print(
                        "Debug: Dropped invalid native transaction state during load - "
                        f"{native_state['removed']} record(s) removed."
                    )
                print(f"Debug: Blockchain length after loading - {len(self.chain)} blocks")
                print(f"Debug: Wallets loaded: {len(self.wallets)} wallets")
                return True

            if loaded_data is not None:
                print("Debug: Blockchain file found but is invalid. Resetting to Genesis state.")
                self.chain = []
                self.wallets = {}
                self.submissions = []
                self.content_objects = []
                self.mint_queue = []
                self.votes = []
                self.transfer_intents = []
                self.native_transactions = []
                self.originality_certificates = []
                self.access_requests = []
                self.access_accounts = []
                self.wallet_bindings = []
                self.allowlist_entries = []
                self.override_requests = []
                self.feedback_records = []
                self.audit_logs = []

        except FileNotFoundError:
            print("Debug: No saved blockchain found. Creating new blockchain.")
            self.chain = []
            self.wallets = {}
            self.submissions = []
            self.content_objects = []
            self.mint_queue = []
            self.votes = []
            self.transfer_intents = []
            self.native_transactions = []
            self.originality_certificates = []
            self.access_requests = []
            self.access_accounts = []
            self.wallet_bindings = []
            self.allowlist_entries = []
            self.override_requests = []
            self.feedback_records = []
            self.audit_logs = []
        except json.JSONDecodeError:
            print("Debug: Failed to parse blockchain.json. Resetting to Genesis state.")
            self.chain = []
            self.wallets = {}
            self.submissions = []
            self.content_objects = []
            self.mint_queue = []
            self.votes = []
            self.transfer_intents = []
            self.native_transactions = []
            self.originality_certificates = []
            self.access_requests = []
            self.access_accounts = []
            self.wallet_bindings = []
            self.allowlist_entries = []
            self.override_requests = []
            self.feedback_records = []
            self.audit_logs = []
        except Exception as e:
            print(f"Debug: Unexpected error loading blockchain - {e}")
            self.chain = []
            self.wallets = {}
            self.submissions = []
            self.content_objects = []
            self.mint_queue = []
            self.votes = []
            self.transfer_intents = []
            self.native_transactions = []
            self.originality_certificates = []
            self.access_requests = []
            self.access_accounts = []
            self.wallet_bindings = []
            self.allowlist_entries = []
            self.override_requests = []
            self.feedback_records = []
            self.audit_logs = []

        return False

    def create_genesis_block(self, project_owner_wallet, Contributor_one, Contributor_two, initial_supply=TOTAL_SUPPLY):
        """Create the Genesis block with initial transactions and optional encoded meme."""
        genesis_transactions = []

        # Create initial transactions to fund wallets
        if project_owner_wallet:
            tx = Transaction(sender="GENESIS", recipient=project_owner_wallet.public_key, amount=initial_supply * 0.79)
            genesis_transactions.append(tx)

        if Contributor_one:
            tx = Transaction(sender="GENESIS", recipient=Contributor_one.public_key, amount=initial_supply * 0.10)
            genesis_transactions.append(tx)

        if Contributor_two:
            tx = Transaction(sender="GENESIS", recipient=Contributor_two.public_key, amount=initial_supply * 0.01)
            genesis_transactions.append(tx)

        # Ensure the transactions are correctly formatted
        print("Debug: Genesis Transactions -", [tx.__dict__ for tx in genesis_transactions])

        # Encode the provided genesis image
        try:
            with open("./zoidberg.jpg", "rb") as image_file:
                encoded_image = base64.b64encode(image_file.read()).decode("utf-8")
        except Exception as e:
            raise ValueError(f"Failed to encode genesis image: {e}")

        # Create the genesis block with transactions
        genesis_block = Block(
            index=0,
            previous_hash="0",
            timestamp=time.time(),
            transactions=genesis_transactions,  # âœ… Assign transactions explicitly
            miner="GENESIS",
            meme={"encoded_image": encoded_image, "text": "LOOKING FOR A NEW MEME COIN? WHY NOT ZOIDBERGCOIN"}
        )
        self.chain.append(genesis_block)

        # âœ… Debugging to verify genesis block transactions
        print("\nGenesis Block Transactions:", [tx.__dict__ for tx in genesis_block.transactions])

        print("\nGenesis wallets initialized:")
        if project_owner_wallet:
            print(f"Project Owner Wallet Public Key: {_short_public_key(project_owner_wallet.public_key)}")
        if Contributor_one:
            print(f"Contributor One Public Key: {_short_public_key(Contributor_one.public_key)}")
        if Contributor_two:
            print(f"Contributor Two Public Key: {_short_public_key(Contributor_two.public_key)}")
        print("Private keys are not printed. Use the development-only export endpoint for local setup.\n")


    def encode_image(self, image_path):
        """Encode an image as a base64 string."""
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode("utf-8")
        except Exception as e:
            raise ValueError("Failed to encode image.")

    def get_chain(self):
        """Return the entire blockchain as a list of dictionaries."""
        return [block.to_dict() for block in self.chain]

    def add_wallet(self, wallet):
        """Add a wallet to the blockchain."""
        if wallet.public_key in self.wallets:
            print(f"Debug: Wallet with public key {wallet.public_key} already exists.")
            return False
        self.wallets[wallet.public_key] = wallet
        print(f"Debug: Wallet added to blockchain - Public Key: {wallet.public_key}")
        return True

    def update_wallets(self, new_wallets):
        self.wallets.update(new_wallets)
        print(f"Debug: Wallets updated. Total wallets: {len(self.wallets)}")

    def get_wallet(self, public_key):
        """Retrieve a wallet by its public key."""
        print(f"Debug: Retrieving wallet for public key {public_key}")
        print(f"Debug: Current wallets: {list(self.wallets.keys())}")  # Log all available public keys
        return self.storage.get_wallet(public_key, self.wallets)

    def is_image_unique(self, image_path):
        """Check if the image is unique with caching."""
        if image_path in self.image_validation_cache:
            new_hash = self.image_validation_cache[image_path]
            print(f"Debug: Cache hit for image hash computation: {new_hash}")
        else:
            new_hash = hash_image(image_path)
            self.image_validation_cache[image_path] = new_hash
            print(f"Debug: Computed and cached image hash: {new_hash}")

        print(f"Debug: Checking uniqueness for image hash: {new_hash}")
        print(f"Debug: Current image hashes: {self.image_hashes}")

        if new_hash in self.image_hashes:
            print(f"Debug: Image hash {new_hash} is NOT unique (cached).")
            return False

        print(f"Debug: Image hash {new_hash} is unique.")
        self.image_hashes.add(new_hash)
        return True

    def is_text_unique(self, text_content):
        """Check if the text is unique with caching."""
        normalized_text = re.sub(r'[^\w\s]', '', text_content).strip().lower()
        print(f"Debug: Checking text: '{text_content}' (normalized: '{normalized_text}')")

        if normalized_text in self.text_validation_cache:
            print(f"Debug: Cache hit for text uniqueness: {normalized_text}")
            return self.text_validation_cache[normalized_text]

        if normalized_text in self.texts:
            print(f"Debug: Text '{normalized_text}' is NOT unique.")
            self.text_validation_cache[normalized_text] = False
            return False

        print(f"Debug: Text '{normalized_text}' is unique.")
        self.text_validation_cache[normalized_text] = True
        self.texts.append(normalized_text)
        return True

    def is_meme_original(self, image_path, text_content):
        """Validate meme originality without caching."""
        print(f"Debug: Validating meme originality for image: {image_path} and text: '{text_content}'")

        # Validate image hash uniqueness
        image_hash = hash_image(image_path)
        print(f"Debug: Image hash: {image_hash}")
        if image_hash in self.image_hashes:
            print("Debug: Image is not unique.")
            return False

        # Validate text uniqueness
        if not self.is_text_unique(text_content):
            print("Debug: Text is not unique.")
            return False

        print("Debug: Meme is original.")
        return True

    def _build_content_object_for_submission(self, submission, image_path="", text_content="", storage_status=None):
        try:
            return content_object_from_submission_data(
                {
                    "submission_id": submission.submission_id,
                    "image_path": image_path,
                    "text_content": text_content,
                    "submitter": submission.submitter,
                    "created_at": submission.created_at,
                    "content_hash": submission.content_hash,
                    "content_id": submission.content_id,
                    "certificate_id": submission.certificate_id,
                },
                network_name=NETWORK_NAME,
                storage_status=storage_status,
                data_dir=self.storage.data_dir,
            )
        except ValueError:
            return None

    def _apply_stored_content_to_object(self, content_object, stored_content, *, submission_id=None, text_content=""):
        metadata = dict(content_object.metadata or {})
        if stored_content.get("byte_hash"):
            metadata["byte_hash"] = stored_content["byte_hash"]
        if stored_content.get("original_filename"):
            metadata["original_filename"] = stored_content["original_filename"]
        if submission_id:
            metadata["submission_id"] = submission_id

        content_object.mime_type = stored_content["mime_type"]
        content_object.file_size_bytes = stored_content["file_size_bytes"]
        content_object.storage_status = stored_content["storage_status"]
        content_object.local_path = stored_content["local_path"]
        content_object.hash_scheme = stored_content.get("hash_scheme", content_object.hash_scheme)
        if stored_content.get("file_name"):
            content_object.file_name = stored_content["file_name"]
        if text_content and not content_object.text_content:
            content_object.text_content = text_content
        if text_content and not content_object.caption:
            content_object.caption = text_content
        content_object.metadata = metadata
        verification = verify_content_object_payload(content_object, data_dir=self.storage.data_dir)
        content_object.hash_scheme = verification["hash_scheme"]
        content_object.verified_at = verification["verified_at"]
        content_object.verification_error = verification["error"]
        return content_object

    def _resolve_content_object_for_submission(self, submission):
        content_object = None
        if submission.content_hash:
            content_object = self.get_content_object_by_hash(submission.content_hash)
        if content_object is None and submission.content_id:
            content_object = self.get_content_object(submission.content_id)
        return content_object

    def _original_content_hash_for_content_object(self, content_object, original_bytes):
        if content_object is None:
            return compute_content_hash_bytes(original_bytes)
        metadata = dict(content_object.metadata or {})
        byte_hash = str(metadata.get("byte_hash") or "").strip().lower()
        if byte_hash:
            return byte_hash
        if content_object.hash_scheme in {HASH_SCHEME_SHA256_BYTES, HASH_SCHEME_SHA256_TEXT}:
            return content_object.content_hash
        return compute_content_hash_bytes(original_bytes)

    def _canonical_block_content_for_submission(self, submission, *, content_object=None):
        content_object = content_object or self._resolve_content_object_for_submission(submission)
        if content_object is None:
            raise ValueError("Content metadata is missing for this submission.")

        if content_object.hash_scheme not in {HASH_SCHEME_SHA256_BYTES, HASH_SCHEME_SHA256_TEXT}:
            raise ValueError("Legacy/non-canonical content must be re-uploaded before minting.")

        resolved_local_path = resolve_local_path(content_object.local_path, data_dir=self.storage.data_dir)
        if resolved_local_path and os.path.isfile(resolved_local_path):
            original_bytes = Path(resolved_local_path).read_bytes()
        elif content_object.mime_type == TEXT_MIME_TYPE and content_object.text_content:
            original_bytes = canonicalize_text_content(content_object.text_content).encode("utf-8")
        else:
            raise ValueError("Canonical minting requires verified local content bytes.")

        verification = verify_content_object_payload(content_object, data_dir=self.storage.data_dir)
        if not verification["verified"]:
            raise ValueError("Canonical minting requires verified local content bytes.")

        original_content_hash = self._original_content_hash_for_content_object(content_object, original_bytes)
        canonical_bytes = canonical_compress_content_bytes(
            original_bytes,
            compression_algorithm=CANONICAL_COMPRESSION_GZIP,
            compression_version=CANONICAL_COMPRESSION_VERSION,
        )
        canonical_size_bytes = len(canonical_bytes)
        if canonical_size_bytes > MAX_CANONICAL_CONTENT_BYTES:
            raise ValueError(
                f"Canonical compressed content exceeds MAX_CANONICAL_CONTENT_BYTES ({MAX_CANONICAL_CONTENT_BYTES} bytes)."
            )

        return {
            "content_hash": compute_content_hash_bytes(canonical_bytes),
            "original_content_hash": original_content_hash,
            "compression_algorithm": CANONICAL_COMPRESSION_GZIP,
            "compression_version": CANONICAL_COMPRESSION_VERSION,
            "canonical_size_bytes": canonical_size_bytes,
            "original_size_bytes": len(original_bytes),
            "mime_type": content_object.mime_type,
            "content_type": content_object.content_type,
            "content_id": content_object.content_id,
            "encoded_content": base64.b64encode(canonical_bytes).decode("ascii"),
        }

    def _ensure_content_object_for_submission(
        self,
        submission,
        image_path="",
        text_content="",
        stored_content=None,
        storage_status=None,
    ):
        content_object = self.get_content_object_by_hash(submission.content_hash)
        if content_object:
            if submission.content_id and submission.content_id != content_object.content_id:
                raise ValueError("content_id does not match content_hash.")
            if not submission.content_id:
                submission.content_id = content_object.content_id
            if stored_content:
                self._apply_stored_content_to_object(
                    content_object,
                    stored_content,
                    submission_id=submission.submission_id,
                    text_content=text_content,
                )
            elif storage_status in {STORAGE_STATUS_REMOTE, STORAGE_STATUS_MISSING} and content_object.storage_status != STORAGE_STATUS_VERIFIED:
                content_object.storage_status = storage_status
                if storage_status == STORAGE_STATUS_REMOTE:
                    content_object.local_path = None
            return content_object

        content_object = self._build_content_object_for_submission(
            submission,
            image_path=image_path,
            text_content=text_content,
            storage_status=storage_status,
        )
        if content_object is None:
            return None
        if stored_content:
            self._apply_stored_content_to_object(
                content_object,
                stored_content,
                submission_id=submission.submission_id,
                text_content=text_content,
            )
        elif storage_status == STORAGE_STATUS_REMOTE:
            content_object.local_path = None
        self.content_objects.append(content_object)
        submission.content_id = content_object.content_id
        return content_object

    def _store_submission_content(self, submission, image_path="", text_content=""):
        if image_path:
            with open(image_path, "rb") as image_file:
                image_bytes = image_file.read()
            payload_hash = compute_content_hash_bytes(image_bytes)
            stored_content = store_content_bytes(
                payload_hash,
                image_bytes,
                mime_type=guess_mime_type(os.path.basename(image_path), "image/jpeg"),
                original_filename=os.path.basename(image_path),
                data_dir=self.storage.data_dir,
                hash_scheme=HASH_SCHEME_SHA256_BYTES,
            )
            submission.content_hash = stored_content["content_hash"]
            submission.content_id = calculate_content_id(submission.content_hash)
            submission.image_path = os.path.abspath(stored_content["path"])
            return stored_content

        normalized_text = validate_text_content(text_content)
        if not normalized_text:
            return None

        payload_hash = compute_text_content_hash(normalized_text)
        stored_content = store_content_bytes(
            payload_hash,
            normalized_text.encode("utf-8"),
            mime_type=TEXT_MIME_TYPE,
            data_dir=self.storage.data_dir,
            hash_scheme=HASH_SCHEME_SHA256_TEXT,
        )
        submission.text_content = normalized_text
        submission.content_hash = stored_content["content_hash"]
        submission.content_id = calculate_content_id(submission.content_hash)
        return stored_content

    def refresh_content_object_storage_statuses(self):
        refreshed_any = False
        for content_object in self.content_objects:
            verification = verify_content_object_payload(content_object, data_dir=self.storage.data_dir)
            new_status = content_object.storage_status
            if verification["verified"]:
                new_status = STORAGE_STATUS_VERIFIED
            elif verification["error"] == "missing_file":
                if content_object.storage_status in {STORAGE_STATUS_LOCAL, STORAGE_STATUS_VERIFIED}:
                    new_status = STORAGE_STATUS_MISSING
            elif verification["exists"]:
                new_status = STORAGE_STATUS_LOCAL

            if content_object.storage_status != new_status:
                content_object.storage_status = new_status
                refreshed_any = True
            if content_object.hash_scheme != verification["hash_scheme"]:
                content_object.hash_scheme = verification["hash_scheme"]
                refreshed_any = True
            if content_object.verification_error != verification["error"]:
                content_object.verification_error = verification["error"]
                refreshed_any = True
            if content_object.verified_at != verification["verified_at"]:
                content_object.verified_at = verification["verified_at"]
                refreshed_any = True
            if verification["local_path"] and content_object.local_path != verification["local_path"]:
                content_object.local_path = verification["local_path"]
                refreshed_any = True
            if verification["file_size_bytes"] is not None and content_object.file_size_bytes != verification["file_size_bytes"]:
                content_object.file_size_bytes = verification["file_size_bytes"]
                refreshed_any = True
        return refreshed_any

    def submit_content(self, image_path="", text_content="", submitter=""):
        """Create a pending content submission without minting a block."""
        if image_path and not os.path.isfile(image_path):
            raise ValueError("Invalid image path provided for the submission.")
        if not image_path and not (text_content or "").strip():
            raise ValueError("At least image_path or text_content is required for a submission.")

        submission = Submission(
            image_path=image_path or "",
            text_content=text_content,
            submitter=submitter,
            status=PENDING,
        )
        stored_content = self._store_submission_content(
            submission,
            image_path=image_path or "",
            text_content=text_content or "",
        )
        self.submissions.append(submission)
        self._ensure_content_object_for_submission(
            submission,
            image_path=submission.image_path or "",
            text_content=text_content or "",
            stored_content=stored_content,
        )
        return submission

    def get_submission(self, submission_id):
        return self.storage.get_submission(submission_id, self.submissions)

    def get_content_object(self, content_id):
        return self.storage.get_content_object(content_id, self.content_objects)

    def get_content_object_by_hash(self, content_hash):
        return self.storage.get_content_object_by_hash(content_hash, self.content_objects)

    def list_content_objects(self, status=None):
        return self.storage.list_content_objects(status=status, content_objects=self.content_objects)

    def _content_type_hint_for_submission(self, image_path="", text_content=""):
        has_image = bool(image_path)
        has_text = bool((text_content or "").strip())
        if has_image and has_text:
            return CONTENT_TYPE_MIXED
        if has_image:
            return CONTENT_TYPE_IMAGE
        return CONTENT_TYPE_TEXT

    def register_remote_content_reference(
        self,
        *,
        content_hash,
        content_id=None,
        submitted_by=None,
        mime_type="application/octet-stream",
        content_type=CONTENT_TYPE_IMAGE,
        caption=None,
        text_content=None,
        file_name=None,
        created_at=None,
        storage_status=STORAGE_STATUS_REMOTE,
        submission_id=None,
    ):
        content_object = self.get_content_object_by_hash(content_hash)
        if content_object is not None:
            if content_id and content_object.content_id != content_id:
                raise ValueError("content_id does not match content_hash.")
            if mime_type and (
                not content_object.mime_type
                or content_object.mime_type == "application/octet-stream"
                or content_object.mime_type == TEXT_MIME_TYPE
            ):
                content_object.mime_type = mime_type
            if (
                content_type
                and content_object.content_type == CONTENT_TYPE_IMAGE
                and content_type in {CONTENT_TYPE_TEXT, CONTENT_TYPE_MIXED}
            ):
                content_object.content_type = content_type
            elif content_type and not content_object.content_type:
                content_object.content_type = content_type
            if submitted_by and content_object.submitted_by == "peer-content":
                content_object.submitted_by = submitted_by
            if content_object.storage_status != STORAGE_STATUS_VERIFIED:
                content_object.storage_status = storage_status
                content_object.local_path = None
                content_object.verified_at = None
            if content_object.hash_scheme == HASH_SCHEME_UNKNOWN:
                content_object.verification_error = "legacy_unverifiable"
            if caption and not content_object.caption:
                content_object.caption = caption.strip()
            if text_content and not content_object.text_content:
                content_object.text_content = text_content.strip()
            if file_name and not content_object.file_name:
                content_object.file_name = file_name
            if submission_id:
                metadata = dict(content_object.metadata or {})
                metadata.setdefault("submission_id", submission_id)
                content_object.metadata = metadata
            return content_object

        content_object = ContentObject(
            content_hash=content_hash,
            content_type=content_type,
            mime_type=mime_type,
            submitted_by=(submitted_by or "peer-content"),
            network_name=NETWORK_NAME,
            created_at=time.time() if created_at is None else created_at,
            file_name=file_name,
            file_size_bytes=None,
            storage_status=storage_status,
            local_path=None,
            text_content=text_content,
            caption=caption,
            metadata=({"submission_id": submission_id} if submission_id else {}),
            hash_scheme=HASH_SCHEME_UNKNOWN,
            verification_error="legacy_unverifiable",
        )
        self.content_objects.append(content_object)
        return content_object

    def register_uploaded_content(
        self,
        *,
        content_hash,
        submitted_by,
        mime_type,
        file_size_bytes,
        storage_status,
        local_path=None,
        file_name=None,
        original_filename=None,
        caption=None,
        text_content=None,
        content_type_hint=None,
        created_at=None,
        byte_hash=None,
        hash_scheme=None,
    ):
        content_type = None
        if content_type_hint:
            content_type = _validate_content_type(content_type_hint)
        elif mime_type == TEXT_MIME_TYPE:
            content_type = CONTENT_TYPE_TEXT
        elif (text_content or "").strip() or (caption or "").strip():
            content_type = CONTENT_TYPE_MIXED
        else:
            content_type = CONTENT_TYPE_IMAGE

        if mime_type == TEXT_MIME_TYPE and content_type == CONTENT_TYPE_IMAGE:
            content_type = CONTENT_TYPE_TEXT

        content_object = self.get_content_object_by_hash(content_hash)
        if content_object:
            metadata = dict(content_object.metadata or {})
            if byte_hash:
                metadata["byte_hash"] = byte_hash
            if original_filename:
                metadata["original_filename"] = original_filename
            content_object.mime_type = mime_type
            content_object.file_size_bytes = file_size_bytes
            content_object.storage_status = storage_status
            content_object.hash_scheme = hash_scheme or content_object.hash_scheme
            if local_path:
                content_object.local_path = local_path
            if file_name:
                content_object.file_name = file_name
            if caption:
                content_object.caption = caption.strip()
            if text_content:
                content_object.text_content = text_content.strip()
            if content_object.content_type == CONTENT_TYPE_IMAGE and content_type == CONTENT_TYPE_MIXED:
                content_object.content_type = CONTENT_TYPE_MIXED
            content_object.metadata = metadata
            verification = verify_content_object_payload(content_object, data_dir=self.storage.data_dir)
            content_object.hash_scheme = verification["hash_scheme"]
            content_object.verified_at = verification["verified_at"]
            content_object.verification_error = verification["error"]
            return content_object

        content_object = ContentObject(
            content_hash=content_hash,
            content_type=content_type,
            mime_type=mime_type,
            submitted_by=submitted_by,
            network_name=NETWORK_NAME,
            created_at=time.time() if created_at is None else created_at,
            file_name=file_name,
            file_size_bytes=file_size_bytes,
            storage_status=storage_status,
            local_path=local_path,
            text_content=text_content,
            caption=caption,
            metadata=(
                {
                    **({"byte_hash": byte_hash} if byte_hash else {}),
                    **({"original_filename": original_filename} if original_filename else {}),
                }
            ),
            hash_scheme=hash_scheme or HASH_SCHEME_UNKNOWN,
            verified_at=time.time() if storage_status == STORAGE_STATUS_VERIFIED else None,
            verification_error=None,
        )
        verification = verify_content_object_payload(content_object, data_dir=self.storage.data_dir)
        content_object.hash_scheme = verification["hash_scheme"]
        content_object.verified_at = verification["verified_at"]
        content_object.verification_error = verification["error"]
        self.content_objects.append(content_object)
        return content_object

    def upload_binary_content(
        self,
        *,
        file_bytes,
        submitted_by,
        mime_type,
        original_filename=None,
        caption=None,
        content_type_hint=None,
    ):
        resolved_payload = resolve_payload_hash(file_bytes, mime_type)
        content_hash = resolved_payload["content_hash"]
        normalized_text_content = resolved_payload["text_content"]
        stored_content = store_content_bytes(
            content_hash,
            resolved_payload["stored_bytes"],
            mime_type=resolved_payload["mime_type"],
            original_filename=sanitize_original_filename(original_filename),
            data_dir=self.storage.data_dir,
            hash_scheme=resolved_payload["hash_scheme"],
        )
        content_object = self.register_uploaded_content(
            content_hash=content_hash,
            submitted_by=submitted_by,
            mime_type=stored_content["mime_type"],
            file_size_bytes=stored_content["file_size_bytes"],
            storage_status=stored_content["storage_status"],
            local_path=stored_content["local_path"],
            file_name=stored_content["file_name"],
            original_filename=stored_content["original_filename"],
            caption=validate_caption(caption),
            text_content=normalized_text_content,
            content_type_hint=content_type_hint,
            byte_hash=stored_content["byte_hash"],
            hash_scheme=stored_content["hash_scheme"],
        )
        return content_object

    def upload_text_content(
        self,
        *,
        text_content,
        submitted_by,
        caption=None,
    ):
        normalized_text = validate_text_content(text_content)
        content_hash = compute_text_content_hash(normalized_text)
        stored_content = store_content_bytes(
            content_hash,
            normalized_text.encode("utf-8"),
            mime_type=TEXT_MIME_TYPE,
            data_dir=self.storage.data_dir,
            hash_scheme=HASH_SCHEME_SHA256_TEXT,
        )
        content_object = self.register_uploaded_content(
            content_hash=content_hash,
            submitted_by=submitted_by,
            mime_type=TEXT_MIME_TYPE,
            file_size_bytes=stored_content["file_size_bytes"],
            storage_status=stored_content["storage_status"],
            local_path=stored_content["local_path"],
            file_name=stored_content["file_name"],
            original_filename=stored_content["original_filename"],
            caption=validate_caption(caption),
            text_content=normalized_text,
            content_type_hint=CONTENT_TYPE_TEXT,
            byte_hash=stored_content["byte_hash"],
            hash_scheme=stored_content["hash_scheme"],
        )
        return content_object

    def submit_existing_content(self, *, content_hash=None, submitter, text_content="", content_id=None):
        content_object = None
        if content_id:
            content_object = self.get_content_object(content_id)
            if content_object is None:
                raise ValueError(f"Content not found: {content_id}")
        if content_hash:
            hashed_content_object = self.get_content_object_by_hash(content_hash)
            if content_object is not None and content_object.content_hash != content_hash:
                raise ValueError("content_id does not match content_hash.")
            if hashed_content_object is not None:
                content_object = hashed_content_object
        if content_object is None and content_hash:
            content_object = self.register_remote_content_reference(
                content_hash=content_hash,
                content_id=content_id,
                submitted_by=submitter,
                mime_type=TEXT_MIME_TYPE if (text_content or "").strip() else "application/octet-stream",
                content_type=self._content_type_hint_for_submission("", text_content),
                caption=(text_content or "").strip() or None,
                text_content=(text_content or "").strip() or None,
                storage_status=STORAGE_STATUS_MISSING,
            )
        if content_object is None:
            raise ValueError("content_hash or content_id is required.")

        image_path = ""
        if content_object.content_type in {CONTENT_TYPE_IMAGE, CONTENT_TYPE_MIXED, CONTENT_TYPE_TEXT}:
            resolved_image_path = resolve_local_path(content_object.local_path, data_dir=self.storage.data_dir)
            if resolved_image_path and os.path.isfile(resolved_image_path):
                image_path = resolved_image_path

        verification = verify_content_object_payload(content_object, data_dir=self.storage.data_dir)
        if content_object.storage_status == STORAGE_STATUS_VERIFIED and not verification["verified"]:
            raise ValueError("Uploaded content file failed content_hash verification.")
        if verification["exists"] and verification["verified"]:
            content_object.hash_scheme = verification["hash_scheme"]
            content_object.verified_at = verification["verified_at"]
            content_object.verification_error = None
            content_object.storage_status = STORAGE_STATUS_VERIFIED

        submission_text = (text_content or "").strip() or content_object.text_content or content_object.caption or ""
        submission = Submission(
            image_path=image_path,
            text_content=submission_text,
            submitter=submitter,
            status=PENDING,
            content_hash=content_object.content_hash,
            content_id=content_object.content_id,
        )
        self.submissions.append(submission)
        self._ensure_content_object_for_submission(
            submission,
            image_path=image_path,
            text_content=submission_text,
            storage_status=(
                content_object.storage_status
                if content_object.storage_status in {STORAGE_STATUS_REMOTE, STORAGE_STATUS_MISSING}
                else None
            ),
        )
        return submission

    def update_submission_status(self, submission_id, new_status):
        submission = self.get_submission(submission_id)
        if not submission:
            raise ValueError(f"Submission not found: {submission_id}")

        return submission.transition_to(new_status)

    def hard_reject_submission(self, submission_id, reason):
        submission = self.get_submission(submission_id)
        if not submission:
            raise ValueError(f"Submission not found: {submission_id}")
        if not reason:
            raise ValueError("Hard reject reason is required.")

        submission.hard_reject_reason = reason
        submission.transition_to(HARD_REJECTED)
        self.mint_queue = [
            queued_submission_id
            for queued_submission_id in self.mint_queue
            if queued_submission_id != submission_id
        ]
        return submission

    def record_vote(self, voter, submission_id=None, created_at=None):
        vote = {
            "voter": voter,
            "submission_id": submission_id,
            "vote_type": None,
            "created_at": created_at if created_at is not None else time.time(),
        }
        self.votes.append(vote)
        return vote

    def cast_submission_vote(self, submission_id, voter, vote_type, created_at=None):
        submission = self.get_submission(submission_id)
        if not submission:
            raise ValueError(f"Submission not found: {submission_id}")

        if vote_type not in VOTE_TYPES:
            raise ValueError(f"Invalid vote type: {vote_type}")

        if voter == submission.submitter:
            raise ValueError("Submission creator cannot vote on their own submission.")

        if self.storage.get_vote(submission_id, voter, self.votes):
            raise ValueError("Wallet has already voted on this submission.")

        if self.is_submission_voting_locked(submission):
            raise ValueError("Finalized or certified submissions cannot receive votes.")

        vote = {
            "voter": voter,
            "submission_id": submission_id,
            "vote_type": vote_type,
            "created_at": created_at if created_at is not None else time.time(),
        }
        self.votes.append(vote)
        return vote

    def get_submission_votes(self, submission_id):
        if not self.get_submission(submission_id):
            raise ValueError(f"Submission not found: {submission_id}")

        votes = self.storage.get_votes_for_submission(submission_id, self.votes)
        original_votes = sum(1 for vote in votes if vote.get("vote_type") == VOTE_ORIGINAL)
        not_original_votes = sum(1 for vote in votes if vote.get("vote_type") == VOTE_NOT_ORIGINAL)
        unsure_votes = sum(1 for vote in votes if vote.get("vote_type") == VOTE_UNSURE)
        decisive_votes = original_votes + not_original_votes
        approval_percentage = original_votes / decisive_votes if decisive_votes else 0

        return {
            "submission_id": submission_id,
            "votes": votes,
            "counts": {
                VOTE_ORIGINAL: original_votes,
                VOTE_NOT_ORIGINAL: not_original_votes,
                VOTE_UNSURE: unsure_votes,
            },
            "decisive_vote_total": decisive_votes,
            "approval_percentage": approval_percentage,
        }

    def is_submission_voting_locked(self, submission):
        return (
            submission.status in {APPROVED, QUEUED, REJECTED, HARD_REJECTED, MINTED}
            or self.get_originality_certificate_for_submission(submission.submission_id) is not None
        )

    def get_originality_certificate(self, certificate_id):
        return self.storage.get_certificate(certificate_id, self.originality_certificates)

    def get_originality_certificate_for_submission(self, submission_id):
        return self.storage.get_certificate_for_submission(submission_id, self.originality_certificates)

    def link_certificates_to_submissions(self):
        linked_any = False
        for certificate in self.originality_certificates:
            submission = self.get_submission(certificate.submission_id)
            if submission and submission.certificate_id != certificate.certificate_id:
                submission.certificate_id = certificate.certificate_id
                linked_any = True
        return linked_any

    def link_content_objects_to_submissions(self):
        linked_any = False
        for submission in self.submissions:
            content_object = self.get_content_object_by_hash(submission.content_hash)
            if content_object:
                if submission.content_id != content_object.content_id:
                    submission.content_id = content_object.content_id
                    linked_any = True
                resolved_image_path = resolve_local_path(
                    content_object.local_path,
                    data_dir=self.storage.data_dir,
                )
                if (
                    resolved_image_path
                    and content_object.content_type in {"image", "mixed"}
                    and submission.image_path != resolved_image_path
                    and os.path.isfile(resolved_image_path)
                ):
                    submission.image_path = resolved_image_path
                    linked_any = True
            else:
                created_content_object = self._ensure_content_object_for_submission(
                    submission,
                    image_path=submission.image_path,
                    text_content=submission.text_content,
                )
                if created_content_object:
                    linked_any = True
        return linked_any

    def certificate_block_metadata(self, certificate):
        return {
            "submission_id": certificate.submission_id,
            "certificate_id": certificate.certificate_id,
            "creator_wallet": certificate.creator_wallet,
            "vote_hash": certificate.vote_hash,
            "approval_percentage": certificate.approval_percentage,
            "decisive_vote_total": certificate.decisive_vote_total,
            "minimum_votes_required": certificate.minimum_votes_required,
            "minimum_decisive_votes_required": getattr(
                certificate,
                "minimum_decisive_votes_required",
                certificate.minimum_votes_required,
            ),
            "approved_at": certificate.approved_at,
            "originality_score": certificate.originality_score,
        }

    def _normalize_native_wallet_identity(self, wallet_address):
        candidate = str(wallet_address or "").strip()
        normalized_wallet = normalize_wallet_address(candidate)
        if normalized_wallet:
            return normalized_wallet
        if candidate and is_valid_user_wallet_identity(candidate):
            return candidate
        return None

    def resolve_meme_reward_recipient(self, submission, certificate):
        for candidate in [
            getattr(submission, "creator_wallet_address", None),
            getattr(certificate, "creator_wallet", None),
            getattr(submission, "submitter", None),
        ]:
            normalized = self._normalize_native_wallet_identity(candidate)
            if normalized:
                return normalized
        raise ValueError("Minting reward recipient is missing or invalid for this submission.")

    def build_meme_reward_metadata(self, submission, certificate, *, minted_at):
        reward_recipient = self.resolve_meme_reward_recipient(submission, certificate)
        return {
            "reward_type": "meme_mining_reward",
            "reward_recipient": reward_recipient,
            "reward_amount": float(MEME_BLOCK_REWARD),
            "reward_source": "reward_pool",
            "minted_at": minted_at,
        }

    @staticmethod
    def _block_voter_rewards(block) -> list[dict[str, object]]:
        if isinstance(block, dict):
            return list(block.get("voter_rewards", []) or [])
        return list(getattr(block, "voter_rewards", []) or [])

    @staticmethod
    def _reward_record_sort_key(record):
        block_height = record.get("block_height")
        minted_at = record.get("minted_at")
        reward_id = record.get("reward_id") or ""
        return (
            -(int(block_height) if isinstance(block_height, int) else -1),
            -(int(minted_at) if isinstance(minted_at, (int, float)) else -1),
            str(reward_id),
        )

    @staticmethod
    def _reward_units_from_decimal(amount: Decimal) -> int:
        return int((amount * _NATIVE_ZOID_REWARD_SCALE).to_integral_value())

    @staticmethod
    def _decimal_from_reward_units(units: int) -> Decimal:
        return Decimal(units) / _NATIVE_ZOID_REWARD_SCALE

    def _reward_units_from_amount_string(self, amount, *, allow_zero=True) -> int:
        normalized_amount = parse_native_zoid_amount(amount or "0", allow_zero=allow_zero)
        return self._reward_units_from_decimal(Decimal(normalized_amount))

    def _normalize_reward_amount(self, amount: Decimal | int) -> str:
        decimal_amount = amount if isinstance(amount, Decimal) else self._decimal_from_reward_units(int(amount))
        return self._normalize_decimal_value(decimal_amount)

    def _reward_id(self, submission_id, wallet_address, final_decision):
        return f"voter_reward:{submission_id}:{wallet_address}:{final_decision}"

    @staticmethod
    def _is_creator_reward_transaction(transaction) -> bool:
        sender_value = transaction.get("sender") if isinstance(transaction, dict) else transaction.sender
        if sender_value != "REWARD_POOL":
            return False
        return float(transaction.get("tip", 0) if isinstance(transaction, dict) else transaction.tip) == 0.0

    def _build_creator_reward_record(self, block):
        reward_recipient = self._normalize_native_wallet_identity(
            block.get("reward_recipient") if isinstance(block, dict) else getattr(block, "reward_recipient", None)
        )
        if reward_recipient is None:
            return None
        reward_type = block.get("reward_type") if isinstance(block, dict) else getattr(block, "reward_type", None)
        if reward_type != "meme_mining_reward":
            return None
        submission_id = block.get("submission_id") if isinstance(block, dict) else getattr(block, "submission_id", None)
        minted_at = block.get("minted_at") if isinstance(block, dict) else getattr(block, "minted_at", None)
        block_hash = block.get("hash") if isinstance(block, dict) else getattr(block, "hash", None)
        block_height = block.get("index") if isinstance(block, dict) else getattr(block, "index", None)
        certificate_id = block.get("certificate_id") if isinstance(block, dict) else getattr(block, "certificate_id", None)
        content_hash = block.get("content_hash") if isinstance(block, dict) else getattr(block, "content_hash", None)
        return {
            "reward_id": f"creator_reward:{submission_id or block_hash}:{reward_recipient}",
            "reward_type": reward_type,
            "reward_recipient": reward_recipient,
            "reward_amount": block.get("reward_amount") if isinstance(block, dict) else getattr(block, "reward_amount", None),
            "reward_source": block.get("reward_source") if isinstance(block, dict) else getattr(block, "reward_source", None),
            "reward_status": "settled",
            "settlement_state": "final",
            "submission_id": submission_id,
            "certificate_id": certificate_id,
            "content_hash": content_hash,
            "block_hash": block_hash,
            "block_height": block_height,
            "created_at": minted_at,
            "finalized_at": minted_at,
            "minted_at": minted_at,
            "network_name": NETWORK_NAME,
        }

    def _build_voter_reward_record(self, reward_entry, block):
        reward_recipient = self._normalize_native_wallet_identity(reward_entry.get("reward_recipient"))
        if reward_recipient is None:
            return None
        minted_at = block.get("minted_at") if isinstance(block, dict) else getattr(block, "minted_at", None)
        block_hash = block.get("hash") if isinstance(block, dict) else getattr(block, "hash", None)
        block_height = block.get("index") if isinstance(block, dict) else getattr(block, "index", None)
        return {
            "reward_id": reward_entry.get("reward_id"),
            "reward_type": reward_entry.get("reward_type", "voter_majority_reward"),
            "reward_recipient": reward_recipient,
            "voter_wallet_address": reward_recipient,
            "reward_amount": reward_entry.get("reward_amount"),
            "reward_source": reward_entry.get("reward_source", "reward_pool"),
            "reward_status": "settled",
            "settlement_state": "final",
            "submission_id": reward_entry.get("submission_id"),
            "certificate_id": reward_entry.get("certificate_id"),
            "content_hash": reward_entry.get("content_hash"),
            "vote_choice": reward_entry.get("vote_choice"),
            "final_decision": reward_entry.get("final_decision"),
            "decision_reason": reward_entry.get("decision_reason"),
            "decision_finalized_at": reward_entry.get("decision_finalized_at"),
            "created_at": reward_entry.get("created_at") or minted_at,
            "finalized_at": reward_entry.get("finalized_at") or minted_at,
            "minted_at": minted_at,
            "block_hash": block_hash,
            "block_height": block_height,
            "network_name": reward_entry.get("network_name") or NETWORK_NAME,
        }

    def _all_reward_records(self):
        reward_records = []
        for block in self.chain:
            creator_record = self._build_creator_reward_record(block)
            if creator_record is not None:
                reward_records.append(creator_record)
            for reward_entry in self._block_voter_rewards(block):
                voter_record = self._build_voter_reward_record(reward_entry, block)
                if voter_record is not None:
                    reward_records.append(voter_record)
        reward_records.sort(key=self._reward_record_sort_key)
        return reward_records

    def _get_reward_record(self, reward_id):
        for reward_record in self._all_reward_records():
            if reward_record.get("reward_id") == reward_id:
                return reward_record
        return None

    def _get_settled_voter_reward_ids(self, *, chain=None):
        settled_ids = set()
        for block in chain or self.chain:
            for reward_entry in self._block_voter_rewards(block):
                reward_id = str(reward_entry.get("reward_id") or "").strip()
                if reward_id:
                    settled_ids.add(reward_id)
        return settled_ids

    @staticmethod
    def _block_reward_transactions(block) -> list[dict[str, object]]:
        transactions = block.get("transactions", []) if isinstance(block, dict) else getattr(block, "transactions", [])
        reward_transactions = []
        for transaction in transactions:
            sender_value = transaction.get("sender") if isinstance(transaction, dict) else getattr(transaction, "sender", None)
            if sender_value != "REWARD_POOL":
                continue
            reward_transactions.append(
                transaction.to_dict() if hasattr(transaction, "to_dict") else dict(transaction)
            )
        return reward_transactions

    def _build_reward_transaction_key(self, recipient, amount) -> tuple[str, int]:
        normalized_recipient = self._normalize_native_wallet_identity(recipient)
        if normalized_recipient is None:
            raise ValueError("Reward recipient is invalid.")
        reward_units = self._reward_units_from_amount_string(amount, allow_zero=False)
        return normalized_recipient, reward_units

    def _expected_voter_reward_records_by_id(self, submission_id):
        plan = self.build_submission_voter_reward_plan(submission_id)
        if not plan.get("eligible"):
            return {}
        return {
            str(record.get("reward_id")): record
            for record in plan.get("reward_records", [])
            if record.get("reward_id")
        }

    def _decision_finalized_at_for_submission(self, submission, vote_summary, *, now=None):
        certificate = self.get_originality_certificate_for_submission(submission.submission_id)
        if certificate is not None and certificate.approved_at is not None:
            return certificate.approved_at
        if getattr(submission, "decision_finalized_at", None) is not None:
            return submission.decision_finalized_at
        vote_timestamps = [
            _coerce_timestamp(vote.get("created_at"))
            for vote in vote_summary.get("votes", [])
        ]
        vote_timestamps = [timestamp for timestamp in vote_timestamps if timestamp is not None]
        if vote_timestamps:
            return max(vote_timestamps)
        return float(now if now is not None else time.time())

    def get_submission_reward_decision(self, submission_id, *, now=None):
        submission = self.get_submission(submission_id)
        if submission is None:
            raise ValueError(f"Submission not found: {submission_id}")

        decision_now = float(now if now is not None else time.time())
        vote_summary = self.get_submission_votes(submission_id)
        decisive_vote_total = vote_summary["counts"][VOTE_ORIGINAL] + vote_summary["counts"][VOTE_NOT_ORIGINAL]
        if decisive_vote_total < VOTER_REWARD_MIN_DECISIVE_VOTES:
            return None

        certificate = self.get_originality_certificate_for_submission(submission_id)
        decision_reason = getattr(submission, "decision_reason", None)
        if certificate is not None or submission.status in {APPROVED, QUEUED, MINTED}:
            return {
                "submission_id": submission_id,
                "outcome": "approved_original",
                "final_decision": VOTER_REWARD_APPROVAL_SIDE,
                "vote_choice": VOTE_ORIGINAL,
                "certificate_id": certificate.certificate_id if certificate else getattr(submission, "certificate_id", None),
                "content_hash": submission.content_hash,
                "decision_reason": decision_reason or "approved_by_vote",
                "decision_finalized_at": self._decision_finalized_at_for_submission(
                    submission,
                    vote_summary,
                    now=decision_now,
                ),
            }

        if submission.status != REJECTED:
            return None
        if decision_reason not in {None, "rejected_by_vote"}:
            return None

        voting_window_expired = decision_now >= submission.created_at + (VOTING_WINDOW_HOURS * 60 * 60)
        minimum_votes = self.get_voting_threshold(now=decision_now)["minimum_votes"]
        minimum_votes_reached = len(vote_summary["votes"]) >= minimum_votes
        if not (voting_window_expired or minimum_votes_reached):
            return None
        if vote_summary["approval_percentage"] >= ORIGINALITY_APPROVAL_THRESHOLD:
            return None

        return {
            "submission_id": submission_id,
            "outcome": "rejected_not_original",
            "final_decision": VOTER_REWARD_REJECTION_SIDE,
            "vote_choice": VOTE_NOT_ORIGINAL,
            "certificate_id": None,
            "content_hash": submission.content_hash,
            "decision_reason": decision_reason or "rejected_by_vote",
            "decision_finalized_at": self._decision_finalized_at_for_submission(
                submission,
                vote_summary,
                now=decision_now,
            ),
        }

    def _eligible_voter_reward_wallets(self, reward_decision):
        vote_summary = self.get_submission_votes(reward_decision["submission_id"])
        target_vote = reward_decision["vote_choice"]
        submission = self.get_submission(reward_decision["submission_id"])
        creator_wallet = None
        if submission is not None:
            creator_wallet = self._normalize_native_wallet_identity(
                getattr(submission, "creator_wallet_address", None) or getattr(submission, "submitter", None)
            )
        qualifying_votes = [
            vote
            for vote in vote_summary["votes"]
            if vote.get("vote_type") == target_vote
        ]
        qualifying_votes.sort(
            key=lambda vote: (
                self._normalize_native_wallet_identity(vote.get("voter_wallet_address") or vote.get("voter")) or "",
                _coerce_timestamp(vote.get("created_at")) or 0,
            )
        )
        unique_votes = []
        seen_wallets = set()
        excluded_voters = []
        for vote in qualifying_votes:
            wallet_address = self._normalize_native_wallet_identity(
                vote.get("voter_wallet_address") or vote.get("voter")
            )
            if wallet_address is None or wallet_address == creator_wallet or wallet_address in seen_wallets:
                continue
            seen_wallets.add(wallet_address)
            unique_votes.append(vote)
        qualifying_votes = unique_votes
        config = load_review_policy_config(ENVIRONMENT)
        eligible_votes = []
        for vote in qualifying_votes:
            wallet_address = self._normalize_native_wallet_identity(vote.get("voter_wallet_address") or vote.get("voter"))
            if wallet_address is None:
                continue
            if REQUIRE_ACCESS_FOR_REWARDS:
                access_decision = access_decision_for_wallet(self, wallet_address, feature="rewards")
                if not access_decision.allowed:
                    excluded_voters.append({
                        "wallet_address": wallet_address,
                        "reason": access_decision.reason,
                    })
                    continue
            if VOTER_REWARD_REQUIRE_REVIEW_ELIGIBLE:
                binding = self.get_wallet_binding(wallet_address)
                access_account = self.get_access_account_for_wallet(wallet_address)
                if binding and str(binding.get("status") or "").strip().lower() == "revoked":
                    excluded_voters.append({
                        "wallet_address": wallet_address,
                        "reason": "wallet_binding_revoked",
                    })
                    continue
                if access_account:
                    account_status = str(access_account.get("status") or "").strip().lower()
                    if account_status in {"suspended", "revoked"}:
                        excluded_voters.append({
                            "wallet_address": wallet_address,
                            "reason": f"access_account_{account_status}",
                        })
                        continue
                override_entry = self.find_matching_allowlist_entry(
                    "rewards",
                    wallet_address=wallet_address,
                    access_account=access_account,
                )
                if override_entry:
                    eligible_votes.append(vote)
                    continue
                activity_summary = self.get_account_activity_summary(wallet_address)
                recent_vote_count = self.count_votes_by_wallet_since(wallet_address, current_day_window())
                eligibility = evaluate_review_eligibility(
                    config,
                    wallet_address=wallet_address,
                    activity_summary=activity_summary,
                    recent_vote_count=recent_vote_count,
                )
                if not eligibility.eligible:
                    excluded_voters.append({
                        "wallet_address": wallet_address,
                        "reason": "review_eligibility_required",
                    })
                    continue
            eligible_votes.append(vote)
        self._last_reward_excluded_voters = excluded_voters
        return eligible_votes

    def build_submission_voter_reward_plan(self, submission_id, *, now=None):
        self._last_reward_excluded_voters = []
        reward_decision = self.get_submission_reward_decision(submission_id, now=now)
        if reward_decision is None:
            return {
                "submission_id": submission_id,
                "rewards_enabled": VOTER_REWARDS_ENABLED,
                "eligible": False,
                "reason": "decision_not_reward_eligible",
                "reward_records": [],
                "excluded_voters": [],
                "reward_count": 0,
                "reward_amount_per_voter": "0",
                "total_distributed": "0",
                "undistributed_remainder": "0",
            }

        majority_votes = self._eligible_voter_reward_wallets(reward_decision)
        if not VOTER_REWARDS_ENABLED:
            return {
                **reward_decision,
                "rewards_enabled": False,
                "eligible": False,
                "reason": "voter_rewards_disabled",
                "reward_records": [],
                "excluded_voters": list(self._last_reward_excluded_voters),
                "reward_count": 0,
                "reward_amount_per_voter": "0",
                "total_distributed": "0",
                "undistributed_remainder": "0",
            }

        if not majority_votes:
            return {
                **reward_decision,
                "rewards_enabled": True,
                "eligible": False,
                "reason": "no_eligible_majority_voters",
                "reward_records": [],
                "excluded_voters": list(self._last_reward_excluded_voters),
                "reward_count": 0,
                "reward_amount_per_voter": "0",
                "total_distributed": "0",
                "undistributed_remainder": self._normalize_reward_amount(
                    self._reward_units_from_amount_string(
                        VOTER_REWARD_POOL_PER_DECISION_ZOID,
                        allow_zero=True,
                    )
                ),
            }

        total_units = self._reward_units_from_amount_string(
            VOTER_REWARD_POOL_PER_DECISION_ZOID,
            allow_zero=True,
        )
        if total_units <= 0:
            return {
                **reward_decision,
                "rewards_enabled": True,
                "eligible": False,
                "reason": "reward_pool_zero",
                "reward_records": [],
                "excluded_voters": list(self._last_reward_excluded_voters),
                "reward_count": 0,
                "reward_amount_per_voter": "0",
                "total_distributed": "0",
                "undistributed_remainder": "0",
            }

        per_wallet_units = total_units // len(majority_votes)
        max_per_wallet_units = self._reward_units_from_amount_string(
            VOTER_REWARD_MAX_PER_WALLET_ZOID,
            allow_zero=True,
        )
        if max_per_wallet_units > 0:
            per_wallet_units = min(per_wallet_units, max_per_wallet_units)
        if per_wallet_units <= 0:
            return {
                **reward_decision,
                "rewards_enabled": True,
                "eligible": False,
                "reason": "reward_amount_rounds_to_zero",
                "reward_records": [],
                "excluded_voters": list(self._last_reward_excluded_voters),
                "reward_count": 0,
                "reward_amount_per_voter": "0",
                "total_distributed": "0",
                "undistributed_remainder": self._normalize_reward_amount(total_units),
            }

        reward_amount = self._normalize_reward_amount(per_wallet_units)
        reward_records = []
        for vote in majority_votes:
            wallet_address = self._normalize_native_wallet_identity(vote.get("voter_wallet_address") or vote.get("voter"))
            if wallet_address is None:
                continue
            reward_records.append(
                {
                    "reward_id": self._reward_id(submission_id, wallet_address, reward_decision["final_decision"]),
                    "reward_type": "voter_majority_reward",
                    "reward_recipient": wallet_address,
                    "voter_wallet_address": wallet_address,
                    "reward_amount": reward_amount,
                    "reward_source": "reward_pool",
                    "reward_status": "pending",
                    "submission_id": submission_id,
                    "certificate_id": reward_decision.get("certificate_id"),
                    "content_hash": reward_decision.get("content_hash"),
                    "vote_choice": reward_decision["vote_choice"],
                    "final_decision": reward_decision["final_decision"],
                    "decision_reason": reward_decision["decision_reason"],
                    "decision_finalized_at": reward_decision["decision_finalized_at"],
                    "created_at": reward_decision["decision_finalized_at"],
                    "network_name": NETWORK_NAME,
                }
            )

        distributed_units = per_wallet_units * len(reward_records)
        return {
            **reward_decision,
            "rewards_enabled": True,
            "eligible": True,
            "reason": "reward_plan_ready",
            "reward_records": reward_records,
            "excluded_voters": list(self._last_reward_excluded_voters),
            "reward_count": len(reward_records),
            "reward_amount_per_voter": reward_amount,
            "total_distributed": self._normalize_reward_amount(distributed_units),
            "undistributed_remainder": self._normalize_reward_amount(total_units - distributed_units),
        }

    def _due_voter_reward_records(self):
        settled_reward_ids = self._get_settled_voter_reward_ids()
        due_records = []
        for submission in self.submissions:
            plan = self.build_submission_voter_reward_plan(submission.submission_id)
            if not plan.get("eligible"):
                continue
            for reward_record in plan["reward_records"]:
                if reward_record["reward_id"] in settled_reward_ids:
                    continue
                due_records.append(reward_record)
        due_records.sort(
            key=lambda record: (
                record.get("decision_finalized_at") or 0,
                record.get("submission_id") or "",
                record.get("reward_recipient") or "",
            )
        )
        return due_records

    def _priority_voter_reward_records_for_submission(self, submission_id):
        plan = self.build_submission_voter_reward_plan(submission_id)
        if not plan.get("eligible"):
            return []
        if plan.get("final_decision") != VOTER_REWARD_APPROVAL_SIDE:
            return []
        settled_reward_ids = self._get_settled_voter_reward_ids()
        return [
            reward_record
            for reward_record in plan.get("reward_records", [])
            if reward_record.get("reward_id") not in settled_reward_ids
        ]

    def _select_voter_reward_records_for_block(self, *, prioritized_submission_id=None):
        selected = []
        skipped = []
        remaining_units = self._reward_units_from_decimal(Decimal(str(self.reward_pool))) - self._reward_units_from_decimal(Decimal(str(MEME_BLOCK_REWARD)))
        if remaining_units <= 0:
            return {"selected": [], "skipped": self._due_voter_reward_records()}
        selected_reward_ids = set()

        if prioritized_submission_id:
            prioritized_records = self._priority_voter_reward_records_for_submission(prioritized_submission_id)
            prioritized_units = sum(
                self._reward_units_from_amount_string(record["reward_amount"], allow_zero=False)
                for record in prioritized_records
            )
            if prioritized_units > remaining_units:
                raise ValueError("Insufficient reward pool to finalize approved-original voter rewards in the mint block.")
            selected.extend(prioritized_records)
            selected_reward_ids.update(
                str(record.get("reward_id") or "").strip()
                for record in prioritized_records
                if record.get("reward_id")
            )
            remaining_units -= prioritized_units

        grouped_records: dict[str, list[dict[str, object]]] = {}
        for reward_record in self._due_voter_reward_records():
            reward_id = str(reward_record.get("reward_id") or "").strip()
            if reward_id and reward_id in selected_reward_ids:
                continue
            grouped_records.setdefault(str(reward_record.get("submission_id") or ""), []).append(reward_record)

        for submission_id in sorted(grouped_records.keys()):
            group = grouped_records[submission_id]
            group_units = sum(self._reward_units_from_amount_string(record["reward_amount"], allow_zero=False) for record in group)
            if group_units > remaining_units:
                skipped.extend(group)
                continue
            selected.extend(group)
            remaining_units -= group_units
        return {"selected": selected, "skipped": skipped}

    def get_submission_voter_reward_summary(self, submission_id, *, now=None):
        plan = self.build_submission_voter_reward_plan(submission_id, now=now)
        settled_records = [
            reward_record
            for reward_record in self._all_reward_records()
            if reward_record.get("reward_type") == "voter_majority_reward"
            and reward_record.get("submission_id") == submission_id
        ]
        settled_reward_ids = {reward_record.get("reward_id") for reward_record in settled_records}
        pending_records = [
            reward_record
            for reward_record in plan.get("reward_records", [])
            if reward_record.get("reward_id") not in settled_reward_ids
        ]
        reward_amount_per_voter = plan.get("reward_amount_per_voter", "0")
        if settled_records:
            reward_amount_per_voter = settled_records[0].get("reward_amount", reward_amount_per_voter)
        total_distributed = self._normalize_reward_amount(
            sum(
                self._reward_units_from_amount_string(record.get("reward_amount") or "0", allow_zero=True)
                for record in settled_records
            )
        )
        return {
            "submission_id": submission_id,
            "voter_rewards_enabled": VOTER_REWARDS_ENABLED,
            "eligible": bool(plan.get("eligible")),
            "reason": plan.get("reason"),
            "excluded_voters": plan.get("excluded_voters", []),
            "final_majority_side": plan.get("final_decision"),
            "decision_reason": plan.get("decision_reason"),
            "reward_status": "finalized" if settled_records and not pending_records else ("pending" if pending_records else "none"),
            "reward_amount_per_voter": reward_amount_per_voter,
            "rewarded_voter_count": len(settled_records),
            "pending_voter_count": len(pending_records),
            "total_distributed": total_distributed,
            "undistributed_remainder": plan.get("undistributed_remainder", "0"),
            "review_eligibility_required": VOTER_REWARD_REQUIRE_REVIEW_ELIGIBLE,
            "reward_records": settled_records,
            "pending_reward_records": pending_records,
        }

    def get_reward_records_for_wallet(self, wallet_address):
        normalized_wallet = self._normalize_native_wallet_identity(wallet_address)
        if normalized_wallet is None:
            return []

        return [
            reward_record
            for reward_record in self._all_reward_records()
            if self._normalize_native_wallet_identity(
                reward_record.get("reward_recipient") or reward_record.get("voter_wallet_address")
            ) == normalized_wallet
        ]

    def create_signed_transfer_intent(
        self,
        *,
        from_address,
        to_address,
        amount,
        fee,
        memo,
        network,
        signature_scheme,
        signature,
        signed_message_hash,
        signed_message,
        transfer_nonce,
        transaction_timestamp=None,
        signed_at,
        status="signed_pending",
        created_at=None,
    ):
        transaction = build_native_transaction(
            network=str(network),
            from_address=from_address,
            to_address=to_address,
            amount=str(amount),
            fee=str(fee),
            nonce=str(transfer_nonce),
            memo=str(memo or "").strip() or None,
            timestamp=str(transaction_timestamp or signed_at),
            signature=str(signature),
            signature_scheme=str(signature_scheme),
            signed_message=str(signed_message),
            signed_message_hash=str(signed_message_hash),
            status=str(status),
            created_at=str(created_at) if created_at is not None else None,
        )
        existing_transaction = self.reserve_transaction_nonce(transaction.to_dict())
        if existing_transaction is not None:
            existing_transfer_intent = self._get_transfer_intent_by_tx_id(existing_transaction.get("tx_id"))
            if existing_transfer_intent is None:
                raise ValueError("Transaction already recorded, but the local transfer intent record is missing.")
            duplicate_record = dict(existing_transfer_intent)
            duplicate_record["duplicate"] = True
            return duplicate_record
        record = self._build_transfer_intent_record_from_transaction(
            transaction,
            signed_at=signed_at,
            created_at=transaction.created_at,
        )
        if not record["from_address"] or not record["to_address"]:
            raise ValueError("Transfer intent wallet addresses are invalid.")
        self.transfer_intents.append(record)
        self.native_transactions.append(transaction.to_dict())
        return record

    def get_transfer_intent(self, transfer_id):
        return self.storage.get_transfer_intent(transfer_id, self.transfer_intents)

    def get_transfer_intent_by_tx_id(self, tx_id):
        return self._get_transfer_intent_by_tx_id(tx_id)

    def get_native_transaction(self, tx_id):
        return self.storage.get_native_transaction(tx_id, self.native_transactions)

    def _wallet_matches_submission(self, submission, normalized_wallet):
        for candidate in [
            getattr(submission, "creator_wallet_address", None),
            getattr(submission, "submitter", None),
        ]:
            if self._normalize_native_wallet_identity(candidate) == normalized_wallet:
                return True
        return False

    def _wallet_matches_vote(self, vote, normalized_wallet):
        for candidate in [vote.get("voter_wallet_address"), vote.get("voter")]:
            if self._normalize_native_wallet_identity(candidate) == normalized_wallet:
                return True
        return False

    def count_votes_by_wallet_since(self, wallet_address, since_timestamp):
        normalized_wallet = self._normalize_native_wallet_identity(wallet_address)
        if normalized_wallet is None:
            return 0
        count = 0
        for vote in self.votes:
            created_at = _coerce_timestamp(vote.get("created_at")) or 0
            if created_at < float(since_timestamp):
                continue
            if self._wallet_matches_vote(vote, normalized_wallet):
                count += 1
        return count

    def get_account_activity_summary(self, wallet_address, *, now=None):
        normalized_wallet = self._normalize_native_wallet_identity(wallet_address)
        if normalized_wallet is None:
            return {
                "wallet_address": str(wallet_address or "").strip(),
                "normalized_wallet_address": None,
                "exists": False,
                "first_activity_at": None,
                "account_age_seconds": 0,
                "submission_count": 0,
                "vote_count": 0,
                "reward_count": 0,
                "settled_transfer_count": 0,
                "settled_balance_zoid": "0",
            }

        submissions = [
            submission
            for submission in self.submissions
            if self._wallet_matches_submission(submission, normalized_wallet)
        ]
        votes = [
            vote
            for vote in self.votes
            if self._wallet_matches_vote(vote, normalized_wallet)
        ]
        rewards = self.get_reward_records_for_wallet(normalized_wallet)
        transactions = self.get_native_transactions_for_wallet(normalized_wallet)
        settled_transfer_count = sum(
            1
            for transaction in transactions
            if str(transaction.get("status") or "").strip().lower() == "settled"
        )

        activity_timestamps = []
        for submission in submissions:
            timestamp = _coerce_timestamp(getattr(submission, "created_at", None))
            if timestamp is not None:
                activity_timestamps.append(timestamp)
        for vote in votes:
            timestamp = _coerce_timestamp(vote.get("created_at"))
            if timestamp is not None:
                activity_timestamps.append(timestamp)
        for reward in rewards:
            timestamp = _coerce_timestamp(reward.get("minted_at"))
            if timestamp is not None:
                activity_timestamps.append(timestamp)
        for transaction in transactions:
            timestamp = _coerce_timestamp(
                transaction.get("created_at")
                or transaction.get("updated_at")
                or transaction.get("timestamp")
            )
            if timestamp is not None:
                activity_timestamps.append(timestamp)

        first_activity_at = min(activity_timestamps) if activity_timestamps else None
        current_time = float(now if now is not None else time.time())
        account_age_seconds = max(0, int(current_time - first_activity_at)) if first_activity_at is not None else 0
        settled_balance_zoid = self.get_native_balance_snapshot(normalized_wallet)["final_balance"]
        return {
            "wallet_address": normalized_wallet,
            "normalized_wallet_address": normalized_wallet,
            "exists": bool(activity_timestamps) or Decimal(settled_balance_zoid) > Decimal("0"),
            "first_activity_at": first_activity_at,
            "account_age_seconds": account_age_seconds,
            "submission_count": len(submissions),
            "vote_count": len(votes),
            "reward_count": len(rewards),
            "settled_transfer_count": settled_transfer_count,
            "settled_balance_zoid": settled_balance_zoid,
        }

    def get_transfer_intents_for_wallet(self, wallet_address):
        normalized_wallet = self._normalize_native_wallet_identity(wallet_address)
        if normalized_wallet is None:
            return []
        return [
            record
            for record in self.transfer_intents
            if self._normalize_native_wallet_identity(record.get("from_address")) == normalized_wallet
            or self._normalize_native_wallet_identity(record.get("to_address")) == normalized_wallet
        ]

    def get_native_transactions_for_wallet(self, wallet_address):
        normalized_wallet = self._normalize_native_wallet_identity(wallet_address)
        if normalized_wallet is None:
            return []
        return [
            record
            for record in self.native_transactions
            if self._normalize_native_wallet_identity(record.get("from_address")) == normalized_wallet
            or self._normalize_native_wallet_identity(record.get("to_address")) == normalized_wallet
        ]

    @staticmethod
    def _native_mempool_eligible_statuses():
        return {"signed_pending", "validated_pending", "mempool"}

    @staticmethod
    def _native_ineligible_mempool_statuses():
        return {"included", "settled", "rejected", "expired", "failed"}

    @staticmethod
    def _native_mempool_sort_key(transaction):
        admitted_at = str(transaction.get("admitted_at") or transaction.get("updated_at") or transaction.get("created_at") or "")
        from_address = str(transaction.get("from_address") or "")
        nonce = int(parse_transfer_nonce(transaction.get("nonce")))
        tx_id = str(transaction.get("tx_id") or "")
        return (admitted_at, from_address, nonce, tx_id)

    def _find_native_transaction_index(self, tx_id):
        normalized_tx_id = str(tx_id or "").strip().lower()
        for index, transaction in enumerate(self.native_transactions):
            if str(transaction.get("tx_id") or "").strip().lower() == normalized_tx_id:
                return index
        return None

    def _find_transfer_intent_index_by_tx_id(self, tx_id):
        normalized_tx_id = str(tx_id or "").strip().lower()
        for index, record in enumerate(self.transfer_intents):
            if str(record.get("tx_id") or "").strip().lower() == normalized_tx_id:
                return index
        return None

    @staticmethod
    def _normalize_rejection_reason(reason: str) -> str:
        candidate = str(reason or "").strip().lower()
        candidate = re.sub(r"[^a-z0-9]+", "_", candidate).strip("_")
        return candidate or "validation_failed"

    def _update_transfer_intent_status(self, tx_id, *, status, updated_at=None):
        index = self._find_transfer_intent_index_by_tx_id(tx_id)
        if index is None:
            return None
        record = dict(self.transfer_intents[index])
        record["status"] = str(status).strip().lower()
        if updated_at:
            record["updated_at"] = updated_at
        self.transfer_intents[index] = record
        return record

    def _replace_native_transaction(self, transaction):
        index = self._find_native_transaction_index(transaction.get("tx_id"))
        if index is None:
            raise ValueError("Transaction not found.")
        self.native_transactions[index] = dict(transaction)
        return self.native_transactions[index]

    def discard_native_transaction(self, tx_id):
        native_index = self._find_native_transaction_index(tx_id)
        if native_index is None:
            return False
        del self.native_transactions[native_index]

        transfer_index = self._find_transfer_intent_index_by_tx_id(tx_id)
        if transfer_index is not None:
            del self.transfer_intents[transfer_index]
        return True

    def update_native_transaction_status(
        self,
        tx_id,
        *,
        status,
        rejection_reason=None,
        admitted_at=None,
        included_block_hash=None,
        included_block_height=None,
        settled_at=None,
        updated_at=None,
    ):
        transaction = self.get_native_transaction(tx_id)
        if transaction is None:
            raise ValueError(f"Transaction not found: {tx_id}")
        normalized_status = str(status).strip().lower()
        now_iso = str(updated_at or self._utc_now_iso())
        updated_transaction = dict(transaction)
        updated_transaction["status"] = normalized_status
        updated_transaction["updated_at"] = now_iso
        if admitted_at is not None:
            updated_transaction["admitted_at"] = admitted_at
        if included_block_hash is not None:
            updated_transaction["included_block_hash"] = included_block_hash
        if included_block_height is not None:
            updated_transaction["included_block_height"] = included_block_height
        if settled_at is not None:
            updated_transaction["settled_at"] = settled_at
        if rejection_reason is not None:
            updated_transaction["rejection_reason"] = rejection_reason
        elif updated_transaction["status"] not in {"rejected", "expired"}:
            updated_transaction["rejection_reason"] = None
        try:
            validated = validate_transaction_shape(updated_transaction, network_name=NETWORK_NAME)
            stored_record = validated.to_dict()
        except ValueError:
            if normalized_status not in {"rejected", "failed", "expired"}:
                raise
            stored_record = dict(updated_transaction)
        self._replace_native_transaction(stored_record)
        self._update_transfer_intent_status(stored_record["tx_id"], status=stored_record["status"], updated_at=now_iso)
        return dict(stored_record)

    def record_native_transaction(
        self,
        transaction_payload,
        *,
        status="signed_pending",
        created_at=None,
        updated_at=None,
    ):
        candidate_transaction = dict(transaction_payload or {})
        now_iso = str(created_at or self._utc_now_iso())
        candidate_transaction.setdefault("created_at", now_iso)
        candidate_transaction.setdefault("updated_at", str(updated_at or now_iso))
        validated_transaction = validate_transaction_shape(candidate_transaction, network_name=NETWORK_NAME)
        existing_transaction = self.get_native_transaction(validated_transaction.tx_id)
        if existing_transaction is not None:
            return dict(existing_transaction), True

        stored_transaction = validated_transaction.to_dict()
        stored_transaction["status"] = str(status).strip().lower()
        stored_transaction["created_at"] = now_iso
        stored_transaction["updated_at"] = str(updated_at or now_iso)
        stored_transaction["admitted_at"] = None
        stored_transaction["included_block_hash"] = None
        stored_transaction["included_block_height"] = None
        stored_transaction["settled_at"] = None
        stored_transaction["rejection_reason"] = None
        validate_transaction_shape(stored_transaction, network_name=NETWORK_NAME)
        self.native_transactions.append(stored_transaction)
        return dict(stored_transaction), False

    @staticmethod
    def _native_finalized_statuses():
        return {"included", "settled"}

    @staticmethod
    def _native_block_candidate_statuses():
        return {"validated_pending", "mempool"}

    @staticmethod
    def _native_block_sort_key(transaction):
        from_address = str(transaction.get("from_address") or "")
        nonce = int(parse_transfer_nonce(transaction.get("nonce")))
        tx_id = str(transaction.get("tx_id") or "")
        return (from_address, nonce, tx_id)

    @staticmethod
    def _serialize_native_transaction_for_block(transaction):
        return {
            "tx_id": transaction.get("tx_id"),
            "transaction_type": transaction.get("transaction_type"),
            "network": transaction.get("network"),
            "from_address": transaction.get("from_address"),
            "to_address": transaction.get("to_address"),
            "amount": transaction.get("amount"),
            "fee": transaction.get("fee"),
            "nonce": transaction.get("nonce"),
            "memo": transaction.get("memo"),
            "timestamp": transaction.get("timestamp"),
            "signature": transaction.get("signature"),
            "signature_scheme": transaction.get("signature_scheme"),
            "signed_message": transaction.get("signed_message"),
            "signed_message_hash": transaction.get("signed_message_hash"),
        }

    @staticmethod
    def _compute_block_native_transactions_hash(transactions) -> str:
        canonical = json.dumps(
            [dict(transaction) for transaction in transactions or []],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _block_native_transactions(block):
        if isinstance(block, dict):
            return list(block.get("native_transactions", []) or [])
        return list(getattr(block, "native_transactions", []) or [])

    @staticmethod
    def _native_nonce_used_statuses():
        return {"included", "settled"}

    @staticmethod
    def _native_nonce_reserved_statuses():
        return {"signed_pending", "validated_pending", "mempool"}

    @classmethod
    def _native_nonce_unavailable_statuses(cls):
        return cls._native_nonce_used_statuses() | cls._native_nonce_reserved_statuses()

    def _coerce_native_nonce(self, nonce) -> int:
        return int(parse_transfer_nonce(nonce))

    def _native_transaction_sender_matches(self, transaction, normalized_wallet: str) -> bool:
        return self._normalize_native_wallet_identity(transaction.get("from_address")) == normalized_wallet

    def _get_transfer_intent_by_tx_id(self, tx_id):
        for record in self.transfer_intents:
            if str(record.get("tx_id") or "").strip() == str(tx_id or "").strip():
                return record
        return None

    def _find_sender_nonce_transaction(self, wallet_address, nonce):
        normalized_wallet = self._normalize_native_wallet_identity(wallet_address)
        if normalized_wallet is None:
            return None
        normalized_nonce = self._coerce_native_nonce(nonce)
        for transaction in self.native_transactions:
            if not self._native_transaction_sender_matches(transaction, normalized_wallet):
                continue
            if self._coerce_native_nonce(transaction.get("nonce")) != normalized_nonce:
                continue
            if str(transaction.get("status") or "").strip().lower() not in self._native_nonce_unavailable_statuses():
                continue
            return transaction
        return None

    def get_used_nonces(self, wallet_address):
        normalized_wallet = self._normalize_native_wallet_identity(wallet_address)
        if normalized_wallet is None:
            return []
        used = {
            self._coerce_native_nonce(transaction.get("nonce"))
            for transaction in self.native_transactions
            if self._native_transaction_sender_matches(transaction, normalized_wallet)
            and str(transaction.get("status") or "").strip().lower() in self._native_nonce_used_statuses()
        }
        return sorted(used)

    def get_reserved_nonces(self, wallet_address):
        normalized_wallet = self._normalize_native_wallet_identity(wallet_address)
        if normalized_wallet is None:
            return []
        reserved = {
            self._coerce_native_nonce(transaction.get("nonce"))
            for transaction in self.native_transactions
            if self._native_transaction_sender_matches(transaction, normalized_wallet)
            and str(transaction.get("status") or "").strip().lower() in self._native_nonce_reserved_statuses()
        }
        return sorted(reserved)

    def get_next_nonce(self, wallet_address):
        normalized_wallet = self._normalize_native_wallet_identity(wallet_address)
        if normalized_wallet is None:
            return NATIVE_TRANSACTION_INITIAL_NONCE
        used_nonces = set(self.get_used_nonces(normalized_wallet))
        reserved_nonces = set(self.get_reserved_nonces(normalized_wallet))
        unavailable_nonces = used_nonces | reserved_nonces
        next_nonce = NATIVE_TRANSACTION_INITIAL_NONCE
        while next_nonce in unavailable_nonces:
            next_nonce += 1
        return next_nonce

    def is_nonce_available(self, wallet_address, nonce):
        normalized_wallet = self._normalize_native_wallet_identity(wallet_address)
        if normalized_wallet is None:
            return False
        return self._coerce_native_nonce(nonce) == self.get_next_nonce(normalized_wallet)

    def validate_transaction_nonce(self, transaction):
        normalized_wallet = self._normalize_native_wallet_identity(transaction.get("from_address"))
        if normalized_wallet is None:
            raise ValueError("Transaction from_address is invalid.")
        transaction_nonce = self._coerce_native_nonce(transaction.get("nonce"))
        tx_id = str(transaction.get("tx_id") or "").strip().lower()

        existing_nonce_transaction = self._find_sender_nonce_transaction(normalized_wallet, transaction_nonce)
        if existing_nonce_transaction:
            existing_tx_id = str(existing_nonce_transaction.get("tx_id") or "").strip().lower()
            if existing_tx_id == tx_id:
                return existing_nonce_transaction
            raise ValueError("Nonce already used or reserved. Refresh and try again.")

        expected_nonce = self.get_next_nonce(normalized_wallet)
        if transaction_nonce < expected_nonce:
            raise ValueError("Transaction nonce is lower than the next expected nonce. Refresh and try again.")
        if transaction_nonce > expected_nonce:
            raise ValueError("Transaction nonce is ahead of the next expected nonce. Strict sequential nonces are required.")
        return None

    def reserve_transaction_nonce(self, transaction):
        return self.validate_transaction_nonce(transaction)

    def get_nonce_state(self, wallet_address):
        normalized_wallet = self._normalize_native_wallet_identity(wallet_address)
        if normalized_wallet is None:
            raise ValueError("wallet_address must be a valid Ethereum-style 0x address.")
        return {
            "wallet_address": normalized_wallet,
            "next_nonce": self.get_next_nonce(normalized_wallet),
            "used_nonces": self.get_used_nonces(normalized_wallet),
            "reserved_nonces": self.get_reserved_nonces(normalized_wallet),
            "policy": NATIVE_TRANSACTION_NONCE_POLICY,
            "initial_nonce": NATIVE_TRANSACTION_INITIAL_NONCE,
        }

    @staticmethod
    def _normalize_decimal_value(value: Decimal) -> str:
        normalized_total = format(value.normalize(), "f")
        if "." in normalized_total:
            normalized_total = normalized_total.rstrip("0").rstrip(".")
        return normalized_total if normalized_total and normalized_total != "-0" else "0"

    @staticmethod
    def _native_funds_reserved_statuses():
        return {"signed_pending", "validated_pending", "mempool"}

    def _get_reserved_native_transactions_for_wallet(self, wallet_address, *, exclude_tx_ids=None):
        normalized_wallet = self._normalize_native_wallet_identity(wallet_address)
        if normalized_wallet is None:
            return []
        excluded_ids = {
            str(tx_id or "").strip().lower()
            for tx_id in (exclude_tx_ids or set())
            if str(tx_id or "").strip()
        }
        return [
            transaction
            for transaction in self.native_transactions
            if str(transaction.get("status") or "").strip().lower() in self._native_funds_reserved_statuses()
            and str(transaction.get("tx_id") or "").strip().lower() not in excluded_ids
            and (
                self._normalize_native_wallet_identity(transaction.get("from_address")) == normalized_wallet
                or self._normalize_native_wallet_identity(transaction.get("to_address")) == normalized_wallet
            )
        ]

    def _get_settled_native_transaction_records_for_wallet(self, wallet_address, *, chain=None):
        normalized_wallet = self._normalize_native_wallet_identity(wallet_address)
        if normalized_wallet is None:
            return []
        settled_transactions = []
        for block in chain or self.chain:
            for transaction in self._block_native_transactions(block):
                sender = self._normalize_native_wallet_identity(transaction.get("from_address"))
                recipient = self._normalize_native_wallet_identity(transaction.get("to_address"))
                if sender == normalized_wallet or recipient == normalized_wallet:
                    settled_transactions.append(transaction)
        return settled_transactions

    def get_chain_native_transaction_ids(self, *, chain=None):
        tx_ids = []
        for block in chain or self.chain:
            for transaction in self._block_native_transactions(block):
                tx_id = str(transaction.get("tx_id") or "").strip().lower()
                if tx_id:
                    tx_ids.append(tx_id)
        return tx_ids

    def get_settled_used_nonces(self, wallet_address, *, chain=None):
        normalized_wallet = self._normalize_native_wallet_identity(wallet_address)
        if normalized_wallet is None:
            return []
        used = {
            self._coerce_native_nonce(transaction.get("nonce"))
            for transaction in self._get_settled_native_transaction_records_for_wallet(normalized_wallet, chain=chain)
            if self._normalize_native_wallet_identity(transaction.get("from_address")) == normalized_wallet
        }
        return sorted(used)

    def get_next_settled_nonce(self, wallet_address, *, chain=None):
        normalized_wallet = self._normalize_native_wallet_identity(wallet_address)
        if normalized_wallet is None:
            return NATIVE_TRANSACTION_INITIAL_NONCE
        used_nonces = set(self.get_settled_used_nonces(normalized_wallet, chain=chain))
        next_nonce = NATIVE_TRANSACTION_INITIAL_NONCE
        while next_nonce in used_nonces:
            next_nonce += 1
        return next_nonce

    def get_next_chain_nonce(self, wallet_address, chain_before_block=None):
        return self.get_next_settled_nonce(wallet_address, chain=chain_before_block)

    def calculate_balances_from_chain(self, chain=None):
        chain_dicts = self.chain_to_dicts(chain or self.chain)
        balances: dict[str, Decimal] = {}
        seen_tx_ids = set()
        next_nonces: dict[str, int] = {}
        rewarded_submissions = set()

        def _balance_for(wallet_address):
            if wallet_address is None:
                return Decimal("0")
            return balances.get(wallet_address, Decimal("0"))

        for block_dict in chain_dicts:
            submission_id = block_dict.get("submission_id")
            reward_type = block_dict.get("reward_type")
            if reward_type == "meme_mining_reward" and submission_id:
                if submission_id in rewarded_submissions:
                    raise NativeBlockValidationError(
                        "duplicate_reward",
                        "Chain contains duplicate meme reward settlement for the same submission.",
                        details={"submission_id": submission_id},
                    )
                rewarded_submissions.add(submission_id)

            for transaction in list(block_dict.get("transactions", []) or []):
                sender_value = transaction.get("sender") if isinstance(transaction, dict) else transaction.sender
                recipient_value = transaction.get("recipient") if isinstance(transaction, dict) else transaction.recipient
                amount_value = transaction.get("amount") if isinstance(transaction, dict) else transaction.amount
                tip_value = transaction.get("tip", 0) if isinstance(transaction, dict) else transaction.tip
                sender = self._normalize_native_wallet_identity(sender_value) or sender_value
                recipient = self._normalize_native_wallet_identity(recipient_value) or recipient_value
                transaction_total = Decimal(str(amount_value)) + Decimal(str(tip_value))
                if sender not in {None, "", "GENESIS", "REWARD_POOL"}:
                    balances[sender] = _balance_for(sender) - transaction_total
                if recipient:
                    balances[recipient] = _balance_for(recipient) + transaction_total

            for transaction in self._block_native_transactions(block_dict):
                validated_transaction = self.validate_signed_native_transaction(transaction)
                tx_id = str(validated_transaction.get("tx_id") or "").strip().lower()
                if tx_id in seen_tx_ids:
                    raise NativeBlockValidationError(
                        "duplicate_transaction_id",
                        "Chain contains the same native transaction more than once.",
                        details={"tx_id": tx_id},
                    )

                sender = self._normalize_native_wallet_identity(validated_transaction.get("from_address"))
                recipient = self._normalize_native_wallet_identity(validated_transaction.get("to_address"))
                if sender is None or recipient is None:
                    raise NativeBlockValidationError(
                        "malformed_transaction",
                        "Chain contains a native transaction with an invalid sender or recipient.",
                        details={"tx_id": tx_id},
                    )

                transaction_nonce = self._coerce_native_nonce(validated_transaction.get("nonce"))
                expected_nonce = next_nonces.get(sender, NATIVE_TRANSACTION_INITIAL_NONCE)
                if transaction_nonce < expected_nonce:
                    error_code = "duplicate_nonce" if transaction_nonce == expected_nonce - 1 else "nonce_too_low"
                    raise NativeBlockValidationError(
                        error_code,
                        "Chain contains a native transaction with a nonce lower than the next expected chain nonce.",
                        details={
                            "tx_id": tx_id,
                            "from_address": sender,
                            "expected_nonce": expected_nonce,
                            "received_nonce": transaction_nonce,
                        },
                    )
                if transaction_nonce > expected_nonce:
                    raise NativeBlockValidationError(
                        "nonce_gap",
                        "Chain contains a native transaction with a nonce gap.",
                        details={
                            "tx_id": tx_id,
                            "from_address": sender,
                            "expected_nonce": expected_nonce,
                            "received_nonce": transaction_nonce,
                        },
                    )

                fee_amount = Decimal(str(validated_transaction.get("fee") or "0"))
                if fee_amount != Decimal("0"):
                    raise NativeBlockValidationError(
                        "invalid_fee",
                        "Chain contains a native transaction with a nonzero fee.",
                        details={"tx_id": tx_id, "fee": str(validated_transaction.get("fee") or "0")},
                    )
                amount = Decimal(str(validated_transaction.get("amount") or "0"))
                required_total = amount + fee_amount
                sender_balance = _balance_for(sender)
                if sender_balance < required_total:
                    raise NativeBlockValidationError(
                        "insufficient_balance",
                        "Chain contains a native transaction that would overdraw the sender.",
                        details={
                            "tx_id": tx_id,
                            "from_address": sender,
                            "available_balance": self._normalize_decimal_value(sender_balance),
                            "required_total": self._normalize_decimal_value(required_total),
                        },
                    )

                balances[sender] = sender_balance - required_total
                balances[recipient] = _balance_for(recipient) + amount
                next_nonces[sender] = expected_nonce + 1
                seen_tx_ids.add(tx_id)

        return {
            "balances": balances,
            "seen_tx_ids": seen_tx_ids,
            "next_nonces": next_nonces,
            "rewarded_submissions": rewarded_submissions,
        }

    def get_final_native_balance_amount(self, wallet_address, *, chain=None) -> Decimal:
        normalized_wallet = self._normalize_native_wallet_identity(wallet_address)
        if normalized_wallet is None:
            return Decimal("0")
        balance = Decimal("0")
        for block in chain or self.chain:
            ledger_transactions = block.get("transactions", []) if isinstance(block, dict) else block.transactions
            for transaction in ledger_transactions:
                sender_value = transaction.get("sender") if isinstance(transaction, dict) else transaction.sender
                recipient_value = transaction.get("recipient") if isinstance(transaction, dict) else transaction.recipient
                amount_value = transaction.get("amount") if isinstance(transaction, dict) else transaction.amount
                tip_value = transaction.get("tip", 0) if isinstance(transaction, dict) else transaction.tip
                sender = self._normalize_native_wallet_identity(sender_value) or sender_value
                recipient = self._normalize_native_wallet_identity(recipient_value) or recipient_value
                transaction_total = Decimal(str(amount_value)) + Decimal(str(tip_value))
                if sender == normalized_wallet:
                    balance -= transaction_total
                if recipient == normalized_wallet:
                    balance += transaction_total
            for transaction in self._block_native_transactions(block):
                sender = self._normalize_native_wallet_identity(transaction.get("from_address"))
                recipient = self._normalize_native_wallet_identity(transaction.get("to_address"))
                transaction_total = Decimal(str(transaction.get("amount") or "0")) + Decimal(str(transaction.get("fee") or "0"))
                if sender == normalized_wallet:
                    balance -= transaction_total
                if recipient == normalized_wallet:
                    balance += Decimal(str(transaction.get("amount") or "0"))
        return balance

    @staticmethod
    def _native_block_requires_certificate_context(block_dict) -> bool:
        if not list(block_dict.get("native_transactions", []) or []):
            return False
        required_fields = [
            "submission_id",
            "certificate_id",
            "content_hash",
            "original_content_hash",
            "compression_algorithm",
            "compression_version",
            "canonical_size_bytes",
            "original_size_bytes",
            "creator_wallet",
            "vote_hash",
            "approval_percentage",
            "decisive_vote_total",
            "minimum_votes_required",
            "minimum_decisive_votes_required",
            "approved_at",
            "originality_score",
            "reward_type",
            "reward_recipient",
            "reward_amount",
            "reward_source",
            "minted_at",
        ]
        metadata = {
            field_name: block_dict.get(field_name)
            for field_name in required_fields
            if block_dict.get(field_name) is not None
        }
        return len(metadata) == len(required_fields)

    @staticmethod
    def _raise_native_block_validation_error(code, message, **details):
        raise NativeBlockValidationError(code, message, details=details or None)

    def get_pending_outgoing_balance_amount(self, wallet_address, *, exclude_tx_ids=None) -> Decimal:
        normalized_wallet = self._normalize_native_wallet_identity(wallet_address)
        if normalized_wallet is None:
            return Decimal("0")
        total = Decimal("0")
        for transaction in self._get_reserved_native_transactions_for_wallet(normalized_wallet, exclude_tx_ids=exclude_tx_ids):
            if self._normalize_native_wallet_identity(transaction.get("from_address")) != normalized_wallet:
                continue
            total += Decimal(str(transaction.get("amount") or "0"))
            total += Decimal(str(transaction.get("fee") or "0"))
        return total

    def get_pending_incoming_balance_amount(self, wallet_address, *, exclude_tx_ids=None) -> Decimal:
        normalized_wallet = self._normalize_native_wallet_identity(wallet_address)
        if normalized_wallet is None:
            return Decimal("0")
        total = Decimal("0")
        for transaction in self._get_reserved_native_transactions_for_wallet(normalized_wallet, exclude_tx_ids=exclude_tx_ids):
            if self._normalize_native_wallet_identity(transaction.get("to_address")) != normalized_wallet:
                continue
            total += Decimal(str(transaction.get("amount") or "0"))
        return total

    def get_available_native_balance_amount(self, wallet_address, *, exclude_tx_ids=None) -> Decimal:
        return self.get_final_native_balance_amount(wallet_address) - self.get_pending_outgoing_balance_amount(
            wallet_address,
            exclude_tx_ids=exclude_tx_ids,
        )

    def get_native_balance_snapshot(self, wallet_address, *, exclude_tx_ids=None) -> dict[str, str]:
        final_balance = self.get_final_native_balance_amount(wallet_address)
        pending_outgoing = self.get_pending_outgoing_balance_amount(wallet_address, exclude_tx_ids=exclude_tx_ids)
        pending_incoming = self.get_pending_incoming_balance_amount(wallet_address, exclude_tx_ids=exclude_tx_ids)
        available_balance = final_balance - pending_outgoing
        return {
            "final_balance": self._normalize_decimal_value(final_balance),
            "pending_outgoing": self._normalize_decimal_value(pending_outgoing),
            "pending_incoming": self._normalize_decimal_value(pending_incoming),
            "available_balance": self._normalize_decimal_value(available_balance),
            "native_balance": self._normalize_decimal_value(final_balance),
        }

    def validate_transaction_balance_sufficiency(self, transaction, *, exclude_tx_id=None):
        normalized_wallet = self._normalize_native_wallet_identity(transaction.get("from_address"))
        if normalized_wallet is None:
            raise ValueError("Transaction from_address is invalid.")
        fee_amount = Decimal(parse_native_zoid_amount(transaction.get("fee") or "0", allow_zero=True))
        if fee_amount != Decimal("0"):
            raise ValueError("Nonzero fees are not enabled yet.")
        amount = Decimal(parse_native_zoid_amount(transaction.get("amount") or "0", allow_zero=False))
        required_total = amount + fee_amount
        excluded_ids = {exclude_tx_id} if exclude_tx_id else None
        available_balance = self.get_available_native_balance_amount(normalized_wallet, exclude_tx_ids=excluded_ids)
        if required_total > available_balance:
            snapshot = self.get_native_balance_snapshot(normalized_wallet, exclude_tx_ids=excluded_ids)
            raise ValueError(
                "Insufficient available balance. "
                f"Final balance: {snapshot['final_balance']} ZOID, "
                f"pending outgoing: {snapshot['pending_outgoing']} ZOID, "
                f"available: {snapshot['available_balance']} ZOID."
            )

    def list_mempool_transactions(self):
        mempool_transactions = [
            dict(transaction)
            for transaction in self.native_transactions
            if str(transaction.get("status") or "").strip().lower() == "mempool"
        ]
        mempool_transactions.sort(key=self._native_mempool_sort_key)
        return mempool_transactions

    def get_mempool_transaction(self, tx_id):
        transaction = self.get_native_transaction(tx_id)
        if transaction is None:
            return None
        if str(transaction.get("status") or "").strip().lower() != "mempool":
            return None
        return transaction

    def _resolve_native_transaction_record(self, transaction_or_tx_id):
        if isinstance(transaction_or_tx_id, str):
            transaction = self.get_native_transaction(transaction_or_tx_id)
            if transaction is None:
                raise ValueError(f"Transaction not found: {transaction_or_tx_id}")
            return dict(transaction)
        if not isinstance(transaction_or_tx_id, dict):
            raise ValueError("transaction must be a tx_id string or transaction object.")
        return dict(transaction_or_tx_id)

    def validate_signed_native_transaction(self, transaction_or_tx_id, *, allowed_statuses=None):
        transaction = self._resolve_native_transaction_record(transaction_or_tx_id)
        transaction_payload = dict(transaction)
        canonical_timestamp = transaction_payload.get("timestamp")
        if canonical_timestamp not in (None, ""):
            transaction_payload.setdefault("created_at", canonical_timestamp)
            transaction_payload.setdefault("updated_at", canonical_timestamp)
        validated_transaction = validate_transaction_shape(transaction_payload, network_name=NETWORK_NAME)
        status = validated_transaction.status
        if allowed_statuses is not None and status not in allowed_statuses:
            raise ValueError(f"Transaction status {status} is not eligible for this operation.")

        signed_transfer = parse_transfer_signing_message(
            validated_transaction.signed_message,
            network_name=NETWORK_NAME,
        )
        expected_fields = {
            "from_address": validated_transaction.from_address,
            "to_address": validated_transaction.to_address,
            "amount": validated_transaction.amount,
            "fee": validated_transaction.fee,
            "nonce": validated_transaction.nonce,
            "timestamp": validated_transaction.timestamp,
            "memo": validated_transaction.memo,
        }
        actual_fields = {
            "from_address": signed_transfer.from_address,
            "to_address": signed_transfer.to_address,
            "amount": signed_transfer.amount,
            "fee": signed_transfer.fee,
            "nonce": signed_transfer.nonce,
            "timestamp": signed_transfer.timestamp,
            "memo": signed_transfer.memo,
        }
        if actual_fields != expected_fields:
            raise ValueError("signed_message does not match the canonical transaction payload.")

        verify_transfer_signature(
            validated_transaction.signed_message,
            validated_transaction.signature,
            validated_transaction.from_address,
        )
        return validated_transaction.to_dict()

    def validate_transaction_for_mempool(self, transaction_or_tx_id):
        validated_transaction = self.validate_signed_native_transaction(
            transaction_or_tx_id,
            allowed_statuses=self._native_mempool_eligible_statuses(),
        )
        self.validate_transaction_nonce(validated_transaction)
        self.validate_transaction_balance_sufficiency(
            validated_transaction,
            exclude_tx_id=validated_transaction["tx_id"],
        )
        return validated_transaction

    def select_native_transactions_for_block(self, *, max_transactions_per_block=MAX_TRANSACTIONS_PER_BLOCK):
        candidates = [
            dict(transaction)
            for transaction in self.native_transactions
            if str(transaction.get("status") or "").strip().lower() in self._native_block_candidate_statuses()
        ]
        candidates.sort(key=self._native_block_sort_key)

        selected = []
        skipped = []
        chain_state = self.calculate_balances_from_chain()
        seen_tx_ids = set(chain_state["seen_tx_ids"])
        next_nonces = dict(chain_state["next_nonces"])
        balances: dict[str, Decimal] = dict(chain_state["balances"])

        for transaction in candidates:
            tx_id = str(transaction.get("tx_id") or "").strip().lower()
            if not tx_id or tx_id in seen_tx_ids:
                skipped.append({"tx_id": tx_id, "reason": "already_settled"})
                continue

            try:
                validated_transaction = self.validate_signed_native_transaction(
                    transaction,
                    allowed_statuses=self._native_block_candidate_statuses(),
                )
            except ValueError as exc:
                skipped.append(
                    {
                        "tx_id": tx_id,
                        "reason": self._normalize_rejection_reason(str(exc)),
                        "message": str(exc),
                    }
                )
                continue

            sender = self._normalize_native_wallet_identity(validated_transaction.get("from_address"))
            recipient = self._normalize_native_wallet_identity(validated_transaction.get("to_address"))
            expected_nonce = next_nonces.get(sender, self.get_next_chain_nonce(sender))
            transaction_nonce = self._coerce_native_nonce(validated_transaction.get("nonce"))
            if transaction_nonce != expected_nonce:
                skipped.append(
                    {
                        "tx_id": tx_id,
                        "reason": "invalid_nonce",
                        "message": f"Expected nonce {expected_nonce}, got {transaction_nonce}.",
                    }
                )
                continue

            amount = Decimal(str(validated_transaction.get("amount") or "0"))
            fee = Decimal(str(validated_transaction.get("fee") or "0"))
            required_total = amount + fee
            sender_balance = balances.get(sender, Decimal("0"))
            if sender_balance < required_total:
                skipped.append(
                    {
                        "tx_id": tx_id,
                        "reason": "insufficient_available_balance",
                        "message": "Transaction would overdraw the sender when applied in block order.",
                    }
                )
                continue

            recipient_balance = balances.get(recipient, Decimal("0"))

            balances[sender] = sender_balance - required_total
            balances[recipient] = recipient_balance + amount
            next_nonces[sender] = expected_nonce + 1
            selected.append(self._serialize_native_transaction_for_block(validated_transaction))
            seen_tx_ids.add(tx_id)

            if len(selected) >= max_transactions_per_block:
                break

        return {
            "transactions": selected,
            "transaction_ids": [transaction["tx_id"] for transaction in selected],
            "transaction_count": len(selected),
            "transactions_hash": self._compute_block_native_transactions_hash(selected),
            "skipped": skipped,
        }

    def validate_block_native_transactions(self, block_dict, *, prior_chain=None):
        native_transactions = list(block_dict.get("native_transactions", []) or [])
        transaction_ids = list(block_dict.get("transaction_ids", []) or [])
        transaction_count = block_dict.get("transaction_count", len(native_transactions))
        transactions_hash = block_dict.get("transactions_hash")

        if transaction_count != len(native_transactions):
            self._raise_native_block_validation_error(
                "invalid_transaction_count",
                "Block transaction_count does not match native_transactions length.",
                transaction_count=transaction_count,
                actual_count=len(native_transactions),
            )
        expected_transaction_ids = [transaction.get("tx_id") for transaction in native_transactions]
        if transaction_ids != expected_transaction_ids:
            self._raise_native_block_validation_error(
                "transaction_id_mismatch",
                "Block transaction_ids do not match native_transactions.",
                transaction_ids=transaction_ids,
                expected_transaction_ids=expected_transaction_ids,
            )
        if native_transactions and transactions_hash != self._compute_block_native_transactions_hash(native_transactions):
            self._raise_native_block_validation_error(
                "transactions_hash_mismatch",
                "Block transactions_hash does not match native_transactions.",
                transactions_hash=transactions_hash,
            )

        if native_transactions and not self._native_block_requires_certificate_context(block_dict):
            self._raise_native_block_validation_error(
                "invalid_block_context",
                "Blocks containing native transactions must remain meme-mined blocks.",
            )

        prior_chain = self.chain_to_dicts(prior_chain or self.chain)
        chain_state = self.calculate_balances_from_chain(prior_chain)
        seen_prior_tx_ids = set(chain_state["seen_tx_ids"])
        next_nonces = dict(chain_state["next_nonces"])
        balances: dict[str, Decimal] = dict(chain_state["balances"])
        seen_block_tx_ids = set()
        seen_block_nonces = set()
        validated_transactions = []

        for index, transaction in enumerate(native_transactions):
            if not isinstance(transaction, dict):
                self._raise_native_block_validation_error(
                    "malformed_transaction",
                    "Block native transaction payload must be an object.",
                    transaction_index=index,
                )
            try:
                validated_transaction = self.validate_signed_native_transaction(transaction)
            except ValueError as exc:
                message = str(exc)
                code = "malformed_transaction"
                if "tx_id does not match" in message:
                    code = "transaction_id_mismatch"
                elif "network does not match" in message:
                    code = "wrong_network"
                elif "transaction_type must be exactly" in message:
                    code = "unsupported_transaction_type"
                elif "signature_scheme must be" in message or "signature is required" in message or "Malformed signature" in message or "signature" in message:
                    code = "invalid_transaction_signature"
                elif "fee" in message:
                    code = "invalid_fee"
                self._raise_native_block_validation_error(
                    code,
                    message,
                    transaction_index=index,
                    tx_id=str(transaction.get("tx_id") or "").strip().lower() or None,
                )

            tx_id = str(validated_transaction.get("tx_id") or "").strip().lower()
            if tx_id in seen_block_tx_ids:
                self._raise_native_block_validation_error(
                    "duplicate_transaction_id",
                    "Block contains the same native transaction more than once.",
                    tx_id=tx_id,
                    transaction_index=index,
                )
            if tx_id in seen_prior_tx_ids:
                self._raise_native_block_validation_error(
                    "transaction_already_settled",
                    "Block contains a native transaction that was already settled in an earlier block.",
                    tx_id=tx_id,
                    transaction_index=index,
                )

            sender = self._normalize_native_wallet_identity(validated_transaction.get("from_address"))
            recipient = self._normalize_native_wallet_identity(validated_transaction.get("to_address"))
            transaction_nonce = self._coerce_native_nonce(validated_transaction.get("nonce"))
            sender_nonce_key = (sender, transaction_nonce)
            if sender_nonce_key in seen_block_nonces:
                self._raise_native_block_validation_error(
                    "duplicate_nonce",
                    "Block contains multiple native transactions with the same sender nonce.",
                    tx_id=tx_id,
                    from_address=sender,
                    nonce=transaction_nonce,
                    transaction_index=index,
                )

            expected_nonce = next_nonces.get(sender, self.get_next_chain_nonce(sender, prior_chain))
            if transaction_nonce < expected_nonce:
                self._raise_native_block_validation_error(
                    "nonce_too_low",
                    "Block native transaction nonce is lower than the next expected chain nonce.",
                    tx_id=tx_id,
                    from_address=sender,
                    expected_nonce=expected_nonce,
                    received_nonce=transaction_nonce,
                    transaction_index=index,
                )
            if transaction_nonce > expected_nonce:
                self._raise_native_block_validation_error(
                    "nonce_gap",
                    "Block native transaction nonce creates a gap against the prior chain state.",
                    tx_id=tx_id,
                    from_address=sender,
                    expected_nonce=expected_nonce,
                    received_nonce=transaction_nonce,
                    transaction_index=index,
                )

            amount = Decimal(str(validated_transaction.get("amount") or "0"))
            fee = Decimal(str(validated_transaction.get("fee") or "0"))
            if fee != Decimal("0"):
                self._raise_native_block_validation_error(
                    "invalid_fee",
                    "Block native transaction fee must be zero under the current fee policy.",
                    tx_id=tx_id,
                    fee=str(validated_transaction.get("fee") or "0"),
                    transaction_index=index,
                )
            required_total = amount + fee
            sender_balance = balances.get(sender, Decimal("0"))
            if sender_balance < required_total:
                self._raise_native_block_validation_error(
                    "insufficient_balance",
                    "Block native transaction would overdraw the sender when applied in block order.",
                    tx_id=tx_id,
                    from_address=sender,
                    available_balance=self._normalize_decimal_value(sender_balance),
                    required_total=self._normalize_decimal_value(required_total),
                    transaction_index=index,
                )

            recipient_balance = balances.get(recipient, Decimal("0"))
            balances[sender] = sender_balance - required_total
            balances[recipient] = recipient_balance + amount
            next_nonces[sender] = expected_nonce + 1
            seen_prior_tx_ids.add(tx_id)
            seen_block_tx_ids.add(tx_id)
            seen_block_nonces.add(sender_nonce_key)
            validated_transactions.append(validated_transaction)

        expected_order = sorted(validated_transactions, key=self._native_block_sort_key)
        if [transaction.get("tx_id") for transaction in validated_transactions] != [
            transaction.get("tx_id") for transaction in expected_order
        ]:
            self._raise_native_block_validation_error(
                "transaction_order_invalid",
                "Block native transaction ordering does not match the canonical block ordering policy.",
            )

        return True

    def settle_block_native_transactions(self, block):
        native_transactions = self._block_native_transactions(block)
        if not native_transactions:
            return []
        block_hash = getattr(block, "hash", None) if not isinstance(block, dict) else block.get("hash")
        block_height = getattr(block, "index", None) if not isinstance(block, dict) else block.get("index")
        settled_at = self._coerce_native_event_timestamp(
            getattr(block, "minted_at", None) if not isinstance(block, dict) else block.get("minted_at")
        ) or self._coerce_native_event_timestamp(
            getattr(block, "timestamp", None) if not isinstance(block, dict) else block.get("timestamp")
        ) or self._utc_now_iso()
        settled_tx_ids = []
        for transaction in native_transactions:
            stored_transaction, _duplicate = self.record_native_transaction(transaction, status="validated_pending")
            settled = self.update_native_transaction_status(
                stored_transaction["tx_id"],
                status="settled",
                included_block_hash=block_hash,
                included_block_height=block_height,
                settled_at=settled_at,
                updated_at=settled_at,
            )
            settled_tx_ids.append(settled["tx_id"])
        return settled_tx_ids

    def reconcile_native_transactions_with_chain(self, *, chain=None):
        accepted_chain = self.chain_to_dicts(chain or self.chain)
        accepted_block_hashes = {
            str(block.get("hash") or "").strip()
            for block in accepted_chain
            if str(block.get("hash") or "").strip()
        }

        for index, transaction in enumerate(list(self.native_transactions)):
            if str(transaction.get("status") or "").strip().lower() != "settled":
                continue
            included_block_hash = str(transaction.get("included_block_hash") or "").strip()
            if included_block_hash and included_block_hash in accepted_block_hashes:
                continue
            downgraded = dict(transaction)
            downgraded["status"] = "validated_pending"
            downgraded["included_block_hash"] = None
            downgraded["included_block_height"] = None
            downgraded["settled_at"] = None
            downgraded["updated_at"] = self._utc_now_iso()
            validated = validate_transaction_shape(downgraded, network_name=NETWORK_NAME)
            self.native_transactions[index] = validated.to_dict()
            self._update_transfer_intent_status(validated.tx_id, status=validated.status, updated_at=validated.updated_at)

        settled_tx_ids = []
        for block in accepted_chain:
            settled_tx_ids.extend(self.settle_block_native_transactions(block))
        return settled_tx_ids

    def admit_transaction_to_mempool(self, tx_id):
        validated_transaction = self.validate_transaction_for_mempool(tx_id)
        existing_transaction = self.get_native_transaction(validated_transaction["tx_id"])
        admitted_at = str(existing_transaction.get("admitted_at") or self._utc_now_iso())
        updated_transaction = self.update_native_transaction_status(
            validated_transaction["tx_id"],
            status="mempool",
            admitted_at=admitted_at,
        )
        return {
            "tx_id": updated_transaction["tx_id"],
            "status": updated_transaction["status"],
            "admitted": True,
            "admitted_at": updated_transaction.get("admitted_at"),
            "message": "Transaction admitted to local mempool. It is not settled until included in a block.",
        }

    def revalidate_mempool_transactions(self, *, save=False):
        report = {
            "checked": 0,
            "kept": 0,
            "removed": 0,
            "items": [],
        }
        for transaction in list(self.list_mempool_transactions()):
            report["checked"] += 1
            tx_id = transaction.get("tx_id")
            try:
                self.validate_transaction_for_mempool(transaction)
                report["kept"] += 1
                report["items"].append(
                    {
                        "tx_id": tx_id,
                        "valid": True,
                        "status": "mempool",
                    }
                )
            except ValueError as exc:
                reason = str(exc)
                self.update_native_transaction_status(
                    tx_id,
                    status="rejected",
                    rejection_reason=self._normalize_rejection_reason(reason),
                )
                report["removed"] += 1
                report["items"].append(
                    {
                        "tx_id": tx_id,
                        "valid": False,
                        "status": "rejected",
                        "reason": self._normalize_rejection_reason(reason),
                        "message": reason,
                    }
                )
        if save and report["checked"] > 0:
            self.save_blockchain()
        return report

    def get_pending_outgoing_transfer_amount(self, wallet_address):
        return self.get_native_balance_snapshot(wallet_address)["pending_outgoing"]

    def get_pending_incoming_transfer_amount(self, wallet_address):
        return self.get_native_balance_snapshot(wallet_address)["pending_incoming"]

    def require_valid_certificate_for_submission(self, submission):
        certificate = self.get_originality_certificate_for_submission(submission.submission_id)
        validate_certificate_for_submission(certificate, submission, network_name=NETWORK_NAME)
        return certificate

    def _build_originality_certificate(
        self,
        submission,
        approved_at,
        network_name,
        issuing_node_id,
    ):
        vote_summary = self.get_submission_votes(submission.submission_id)
        return OriginalityCertificate.from_approved_submission(
            submission=submission,
            votes=vote_summary["votes"],
            minimum_votes_required=self.get_voting_threshold(now=approved_at)["minimum_votes"],
            approved_at=approved_at,
            network_name=network_name,
            issuing_node_id=issuing_node_id,
        )

    def create_originality_certificate(
        self,
        submission_id,
        approved_at=None,
        network_name=NETWORK_NAME,
        issuing_node_id=NODE_ID,
        allow_pending=False,
        save=True,
    ):
        submission = self.get_submission(submission_id)
        if not submission:
            raise ValueError(f"Submission not found: {submission_id}")
        allowed_statuses = {APPROVED, QUEUED}
        if allow_pending:
            allowed_statuses.add(PENDING)
        if submission.status not in allowed_statuses:
            raise ValueError("Only approved unminted submissions can receive originality certificates.")

        existing_certificate = self.get_originality_certificate_for_submission(submission_id)
        if existing_certificate:
            submission.certificate_id = existing_certificate.certificate_id
            if save:
                self.save_blockchain()
            return existing_certificate

        approved_at = approved_at if approved_at is not None else time.time()
        certificate = self._build_originality_certificate(
            submission,
            approved_at,
            network_name,
            issuing_node_id,
        )
        validate_certificate_for_submission(
            certificate,
            submission,
            network_name=network_name,
            allowed_submission_statuses=allowed_statuses,
        )
        self.originality_certificates.append(certificate)
        submission.certificate_id = certificate.certificate_id
        if save:
            self.save_blockchain()
        return certificate

    def evaluate_submission(self, submission_id, automated_originality_passed=None, now=None):
        submission = self.get_submission(submission_id)
        if not submission:
            raise ValueError(f"Submission not found: {submission_id}")

        vote_summary = self.get_submission_votes(submission_id)
        now = now if now is not None else time.time()
        voting_window_expired = now >= submission.created_at + (VOTING_WINDOW_HOURS * 60 * 60)
        minimum_decisive_votes_required = self.get_voting_threshold(now=now)["minimum_votes"]
        decisive_votes_cast = vote_summary["decisive_vote_total"]
        minimum_decisive_votes_reached = decisive_votes_cast >= minimum_decisive_votes_required

        result = {
            "submission_id": submission_id,
            "status": submission.status,
            "minimum_votes": minimum_decisive_votes_required,
            "minimum_decisive_votes_required": minimum_decisive_votes_required,
            "votes_cast": len(vote_summary["votes"]),
            "decisive_votes_cast": decisive_votes_cast,
            "approval_percentage": vote_summary["approval_percentage"],
            "voting_window_expired": voting_window_expired,
            "minimum_votes_reached": minimum_decisive_votes_reached,
            "minimum_decisive_votes_reached": minimum_decisive_votes_reached,
        }

        if submission.status != PENDING:
            result["reason"] = "already_finalized"
            return result

        if automated_originality_passed is None:
            automated_originality_passed = self.is_meme_original(
                submission.image_path,
                submission.text_content,
            )

        result["automated_originality_passed"] = automated_originality_passed

        if not automated_originality_passed:
            submission.transition_to(REJECTED)
            submission.decision_reason = "automated_originality_rejected"
            submission.decision_finalized_at = now
            result["status"] = submission.status
            result["reason"] = "automated_originality_rejected"
            return result

        if not minimum_decisive_votes_reached:
            result["reason"] = (
                "awaiting_decisive_votes_window_expired"
                if voting_window_expired
                else "awaiting_decisive_votes"
            )
            return result

        if vote_summary["approval_percentage"] >= ORIGINALITY_APPROVAL_THRESHOLD:
            previous_status = submission.status
            previous_certificate_id = submission.certificate_id
            existing_certificate = self.get_originality_certificate_for_submission(submission_id)
            created_certificate_id = None
            try:
                certificate = self.create_originality_certificate(
                    submission_id,
                    approved_at=now,
                    allow_pending=True,
                    save=False,
                )
                created_certificate_id = certificate.certificate_id
                if not self.get_originality_certificate_for_submission(submission_id):
                    raise ValueError("certificate could not be retrieved after creation")
                self.save_blockchain()
                submission.transition_to(APPROVED)
                validate_certificate_for_submission(certificate, submission, network_name=NETWORK_NAME)
                if self.get_originality_certificate_for_submission(submission_id) is None:
                    raise ValueError("certificate could not be retrieved after approval")
                self.save_blockchain()
                submission.decision_reason = "approved_by_vote"
                submission.decision_finalized_at = now
            except Exception as exc:
                submission.status = previous_status
                submission.certificate_id = previous_certificate_id
                submission.decision_reason = None
                submission.decision_finalized_at = None
                if not existing_certificate and created_certificate_id:
                    self.originality_certificates = [
                        stored_certificate
                        for stored_certificate in self.originality_certificates
                        if stored_certificate.certificate_id != created_certificate_id
                    ]
                raise ValueError(f"Originality certificate creation failed: {exc}") from exc
            result["certificate_id"] = certificate.certificate_id
            result["certificate"] = certificate.to_dict()
            result["reason"] = "approved_by_vote"
        else:
            submission.transition_to(REJECTED)
            submission.decision_reason = "rejected_by_vote"
            submission.decision_finalized_at = now
            result["reason"] = "rejected_by_vote"

        result["status"] = submission.status
        return result

    def get_active_users(self, lookback_days=ACTIVE_USER_LOOKBACK_DAYS, now=None):
        return self.storage.count_active_users(
            submissions=self.submissions,
            votes=self.votes,
            pending_transactions=self.pending_transactions,
            chain=self.chain,
            lookback_days=lookback_days,
            now=now,
        )

    def calculate_minimum_votes_required(self, active_users):
        return max(
            MIN_VOTE_FLOOR,
            math.ceil(active_users * ACTIVE_USER_PERCENT_FOR_MIN_VOTES),
        )

    def get_voting_threshold(self, lookback_days=ACTIVE_USER_LOOKBACK_DAYS, now=None):
        active_users = self.get_active_users(lookback_days=lookback_days, now=now)
        return {
            "active_users": active_users,
            "minimum_votes": self.calculate_minimum_votes_required(active_users),
            "vote_floor": MIN_VOTE_FLOOR,
            "active_percentage": ACTIVE_USER_PERCENT_FOR_MIN_VOTES,
        }

    def add_to_mint_queue(self, submission_id):
        submission = self.get_submission(submission_id)
        if not submission:
            raise ValueError(f"Submission not found: {submission_id}")
        if submission.status == HARD_REJECTED:
            raise ValueError("Hard rejected submissions cannot enter the mint queue.")
        if submission.status != APPROVED:
            raise ValueError("Only approved submissions can be added to the mint queue.")
        if submission.mint_blocked:
            raise ValueError(submission.mint_block_reason or "Submission is blocked from minting.")
        self.require_valid_certificate_for_submission(submission)
        if self.storage.mint_queue_contains(submission_id, self.mint_queue):
            raise ValueError("Submission is already in the mint queue.")

        self.mint_queue.append(submission_id)
        submission.transition_to(QUEUED)
        return submission

    def _queue_submission_record(self, submission, *, content_object=None, certificate=None):
        record = submission.to_dict()
        record["submission_status"] = submission.status
        record["certificate_status"] = "missing" if certificate is None else "valid"
        record["content_status"] = STORAGE_STATUS_MISSING
        record["storage_status"] = STORAGE_STATUS_MISSING
        record["content_metadata_missing"] = True
        record["missing_fields"] = []
        record["mintable"] = False
        record["mint_block_reason"] = None
        record["download_url"] = None

        if certificate is not None:
            record["certificate_id"] = certificate.certificate_id
            record["originality_score"] = certificate.originality_score
        else:
            record["originality_score"] = None

        record["mint_blocked"] = submission.mint_blocked
        record["mint_blocked_at"] = submission.mint_blocked_at
        record["mint_blocked_by"] = submission.mint_blocked_by
        record["mint_block_notes"] = submission.mint_block_notes

        if submission.mint_blocked:
            record["mintable"] = False
            record["mint_block_reason"] = submission.mint_block_reason or "mint_blocked_manually"
            record["certificate_status"] = "blocked"
            return record

        if submission.status == MINTED:
            record["mint_block_reason"] = "already_minted"
            record["missing_fields"].append("status")
            return record
        if submission.status != QUEUED:
            record["mint_block_reason"] = "submission_not_approved"
            record["missing_fields"].append("status")
            return record

        if certificate is None:
            record["mint_block_reason"] = "certificate_missing"
            record["missing_fields"].append("certificate_id")
            return record

        try:
            validate_certificate_for_submission(certificate, submission, network_name=NETWORK_NAME)
        except ValueError as exc:
            message = str(exc).lower()
            record["certificate_status"] = "invalid"
            if "content_hash" in message and "mismatch" in message:
                record["mint_block_reason"] = "certificate_content_hash_mismatch"
            elif "content_id" in message and "mismatch" in message:
                record["mint_block_reason"] = "certificate_content_hash_mismatch"
            else:
                record["mint_block_reason"] = "unknown_error"
            record["missing_fields"].append("certificate")
            record["validation_error"] = str(exc)
            return record

        if content_object is None:
            record["mint_block_reason"] = "content_metadata_missing"
            record["missing_fields"].extend(["content_hash", "content_id", "mime_type", "content_type"])
            return record

        record["content_metadata_missing"] = False
        record["content_id"] = content_object.content_id
        record["content_type"] = content_object.content_type
        record["mime_type"] = content_object.mime_type
        record["content_status"] = content_object.storage_status
        record["storage_status"] = content_object.storage_status
        if content_object.storage_status in {STORAGE_STATUS_LOCAL, STORAGE_STATUS_VERIFIED}:
            record["download_url"] = f"/content/{content_object.content_hash}"

        if content_object.storage_status == STORAGE_STATUS_REMOTE:
            record["mint_block_reason"] = "content_payload_missing"
            record["missing_fields"].append("content_payload")
            return record
        if content_object.storage_status == STORAGE_STATUS_MISSING:
            record["mint_block_reason"] = "content_metadata_missing"
            record["missing_fields"].append("content_payload")
            return record

        verification = verify_content_object_payload(content_object, data_dir=self.storage.data_dir)
        if not verification["verified"]:
            error = str(verification.get("error") or "").lower()
            if error == "missing_file":
                record["mint_block_reason"] = "content_payload_missing"
            elif error == "legacy_unverifiable":
                record["mint_block_reason"] = "legacy_noncanonical_content"
            elif error in {"hash_mismatch", "file_size_mismatch"}:
                record["mint_block_reason"] = "content_hash_mismatch"
            else:
                record["mint_block_reason"] = "content_not_verified"
            record["missing_fields"].append("content_payload")
            record["verification_error"] = verification.get("error")
            return record

        record["mintable"] = True
        record["mint_block_reason"] = None
        record["missing_fields"] = []
        record["certificate_status"] = "valid"
        record["content_status"] = STORAGE_STATUS_VERIFIED if content_object.storage_status == STORAGE_STATUS_VERIFIED else content_object.storage_status

        is_text_payload = (
            content_object.mime_type == TEXT_MIME_TYPE
            or content_object.content_type == CONTENT_TYPE_TEXT
        )
        if not is_text_payload and not str(submission.text_content or "").strip():
            file_path = resolve_local_path(content_object.local_path, data_dir=self.storage.data_dir)
            extracted_text = extract_text(file_path) if file_path and os.path.isfile(file_path) else ""
            if not str(extracted_text or "").strip():
                record["mintable"] = False
                record["mint_block_reason"] = "no_text_content_extracted"
                record["missing_fields"].append("text_content")

        return record

    def _evaluate_mint_queue_item(self, submission_id):
        submission = self.get_submission(submission_id)
        if submission is None:
            return {
                "submission_id": submission_id,
                "submission_status": None,
                "certificate_status": "missing",
                "content_status": STORAGE_STATUS_MISSING,
                "storage_status": STORAGE_STATUS_MISSING,
                "mintable": False,
                "mint_block_reason": "submission_not_found",
                "missing_fields": ["submission"],
                "content_metadata_missing": True,
                "mint_blocked": False,
                "mint_blocked_at": None,
                "mint_blocked_by": None,
                "mint_block_notes": None,
                "download_url": None,
            }

        content_object = None
        if submission.content_hash:
            content_object = self.get_content_object_by_hash(submission.content_hash)
        if content_object is None and submission.content_id:
            content_object = self.get_content_object(submission.content_id)

        certificate = self.get_originality_certificate_for_submission(submission.submission_id)
        record = self._queue_submission_record(
            submission,
            content_object=content_object,
            certificate=certificate,
        )
        if submission.status == QUEUED and certificate is None and record.get("mint_block_reason") == "certificate_missing":
            submission.status = APPROVED
            record["submission_status"] = APPROVED
        return record

    def get_mint_queue(self, include_blocked=True, mintable_only=False):
        queued_submissions = []
        for submission_id in self.mint_queue:
            record = self._evaluate_mint_queue_item(submission_id)
            if mintable_only and not record.get("mintable"):
                continue
            if not include_blocked and not record.get("mintable"):
                continue
            queued_submissions.append(record)

        return queued_submissions

    def _mint_submission_record(self, submission, certificate, miner=None, max_block_size_kb=500, validate_meme=True):
        reward_recipient = self.resolve_meme_reward_recipient(submission, certificate)
        block_added = self.add_block(
            image_path=submission.image_path,
            text_content=submission.text_content,
            miner=miner or submission.submitter,
            max_block_size_kb=max_block_size_kb,
            validate_meme=validate_meme,
            certificate=certificate,
            reward_recipient=reward_recipient,
        )
        if block_added:
            if submission.submission_id in self.mint_queue:
                self.mint_queue = [
                    queued_submission_id
                    for queued_submission_id in self.mint_queue
                    if queued_submission_id != submission.submission_id
                ]
            submission.transition_to(MINTED)
        return block_added

    def mint_next_queued_submission(self, miner=None, max_block_size_kb=500, validate_meme=True):
        if not self.mint_queue:
            raise ValueError("Mint queue is empty.")

        blocked_records = []
        for submission_id in self.mint_queue:
            submission = self.get_submission(submission_id)
            if submission is not None and submission.status == HARD_REJECTED:
                raise ValueError("Hard rejected submissions cannot become blocks.")
            record = self._evaluate_mint_queue_item(submission_id)
            if record.get("mintable"):
                certificate = self.require_valid_certificate_for_submission(submission)
                return self._mint_submission_record(
                    submission,
                    certificate,
                    miner=miner,
                    max_block_size_kb=max_block_size_kb,
                    validate_meme=validate_meme,
                )
            blocked_records.append(record)

        blocked_summary = ", ".join(
            f"{record['submission_id'][:8]}:{record.get('mint_block_reason') or 'unknown_error'}"
            for record in blocked_records[:5]
        )
        raise ValueError(
            "No mintable submissions in the queue. "
            f"Blocked items: {blocked_summary or 'none'}."
        )

    def mint_submission(self, submission_id, miner=None, max_block_size_kb=500, validate_meme=True):
        submission = self.get_submission(submission_id)
        if submission is None:
            raise ValueError(f"Submission not found: {submission_id}")
        if submission.status == HARD_REJECTED:
            raise ValueError("Hard rejected submissions cannot become blocks.")
        if submission.status == MINTED:
            raise ValueError("Submission has already been minted.")
        if submission.status not in {APPROVED, QUEUED}:
            raise ValueError("Only approved unminted submissions can be minted.")

        if submission.status == APPROVED:
            submission = self.add_to_mint_queue(submission_id)

        record = self._evaluate_mint_queue_item(submission_id)
        if not record.get("mintable"):
            raise ValueError(record.get("mint_block_reason") or "Submission is not mintable.")

        certificate = self.require_valid_certificate_for_submission(submission)
        return self._mint_submission_record(
            submission,
            certificate,
            miner=miner,
            max_block_size_kb=max_block_size_kb,
            validate_meme=validate_meme,
        )

    def block_minting_for_submission(self, submission_id, reason, notes=None, blocked_by=None):
        submission = self.get_submission(submission_id)
        if submission is None:
            raise ValueError(f"Submission not found: {submission_id}")
        if submission.status == MINTED:
            raise ValueError("Minted submissions cannot be blocked from minting.")
        submission.mint_blocked = True
        submission.mint_block_reason = (reason or "mint_blocked_manually").strip() or "mint_blocked_manually"
        submission.mint_blocked_at = time.time()
        submission.mint_blocked_by = blocked_by
        submission.mint_block_notes = notes
        return submission

    def _resolve_mintable_submission_certificate(self, submission):
        if submission is None:
            return None
        if submission.mint_blocked:
            return None
        certificate = self.require_valid_certificate_for_submission(submission)
        transient_content_object = self.get_content_object_by_hash(submission.content_hash)
        if transient_content_object is None:
            transient_content_object = self._build_content_object_for_submission(
                submission,
                image_path=submission.image_path,
                text_content=submission.text_content,
            )
        if transient_content_object is None:
            return None

        verification = verify_content_object_payload(transient_content_object, data_dir=self.storage.data_dir)
        if verification["verified"]:
            if transient_content_object.content_id and submission.content_id != transient_content_object.content_id:
                submission.content_id = transient_content_object.content_id
            return certificate
        if verification.get("error") == "legacy_unverifiable" and (
            transient_content_object.local_path or submission.image_path or submission.text_content
        ):
            if transient_content_object.content_id and submission.content_id != transient_content_object.content_id:
                submission.content_id = transient_content_object.content_id
            return certificate
        return None

    def unblock_minting_for_submission(self, submission_id):
        submission = self.get_submission(submission_id)
        if submission is None:
            raise ValueError(f"Submission not found: {submission_id}")
        submission.mint_blocked = False
        submission.mint_block_reason = None
        submission.mint_blocked_at = None
        submission.mint_blocked_by = None
        submission.mint_block_notes = None
        return submission

    def cleanup_bad_mint_queue_items(self, *, block_unmintable=False):
        report = {
            "checked": 0,
            "mintable": 0,
            "blocked": 0,
            "items": [],
        }
        candidate_ids = [
            submission_id
            for submission_id in self.mint_queue
            if self.get_submission(submission_id) is not None
        ]
        for submission in self.submissions:
            if submission.status in {APPROVED, QUEUED} and submission.submission_id not in candidate_ids:
                candidate_ids.append(submission.submission_id)

        for submission_id in candidate_ids:
            record = self._evaluate_mint_queue_item(submission_id)
            report["checked"] += 1
            if record.get("mintable"):
                report["mintable"] += 1
                continue
            report["blocked"] += 1
            report["items"].append(
                {
                    "submission_id": submission_id,
                    "content_hash": record.get("content_hash"),
                    "mintable": False,
                    "reason": record.get("mint_block_reason") or "unknown_error",
                }
            )
            if block_unmintable and record.get("submission_status") in {APPROVED, QUEUED}:
                try:
                    self.block_minting_for_submission(
                        submission_id,
                        reason=record.get("mint_block_reason") or "mint_blocked_manually",
                        notes="Auto-blocked by cleanup_bad_mint_queue_items.",
                        blocked_by="dev-cleanup",
                    )
                except ValueError:
                    continue

        return report

    def remove_invalid_mint_queue_entries(self):
        valid_queue = []
        removed_entries = []
        for submission_id in self.mint_queue:
            submission = self.get_submission(submission_id)
            try:
                certificate_ready = (
                    submission
                    and submission.status == QUEUED
                    and self.require_valid_certificate_for_submission(submission)
                )
            except ValueError:
                certificate_ready = False

            if certificate_ready:
                valid_queue.append(submission_id)
            else:
                if submission and submission.status == QUEUED:
                    submission.status = APPROVED
                if submission and not self.get_originality_certificate_for_submission(submission.submission_id):
                    submission.certificate_id = None
                removed_entries.append(submission_id)

        self.mint_queue = valid_queue
        return removed_entries

    def remove_invalid_mint_queue_entries(self):
        valid_queue = []
        removed_entries = []
        for submission_id in self.mint_queue:
            submission = self.get_submission(submission_id)
            try:
                certificate_ready = (
                    submission
                    and submission.status == QUEUED
                    and self.require_valid_certificate_for_submission(submission)
                )
            except ValueError:
                certificate_ready = False

            if certificate_ready:
                valid_queue.append(submission_id)
            else:
                if submission and submission.status == QUEUED:
                    submission.status = APPROVED
                if submission and not self.get_originality_certificate_for_submission(submission.submission_id):
                    submission.certificate_id = None
                removed_entries.append(submission_id)

        self.mint_queue = valid_queue
        return removed_entries

    def add_block(
        self,
        image_path,
        text_content=None,
        miner=None,
        max_block_size_kb=None,
        validate_meme=True,
        certificate=None,
        reward_recipient=None,
    ):
        """
        Add a block with tip distribution, enforce block size limit, and validate memes.
        """
        if not self.is_valid_public_key(miner):
            print(f"Debug: Invalid miner public key: {miner}")
            raise ValueError(f"Invalid public key provided for the miner.")
        if certificate is None:
            raise ValueError(
                "Legacy/non-canonical minting is not allowed. Mint an approved submission through the canonical submission flow."
            )

        file_exists = bool(image_path) and os.path.isfile(image_path)
        file_extension = os.path.splitext(image_path)[1].lower() if image_path else ""
        guessed_mime_type = guess_mime_type(os.path.basename(image_path), "image/jpeg") if file_exists else ""
        is_text_payload = bool(text_content and text_content.strip()) and (
            not file_exists
            or guessed_mime_type == TEXT_MIME_TYPE
            or file_extension == ".txt"
        )

        if not file_exists and not is_text_payload:
            print(f"Debug: Image path {image_path} does not exist.")
            raise ValueError("Invalid image path provided for the meme.")

        certificate_submission = self.get_submission(certificate.submission_id)
        if certificate_submission is None:
            raise ValueError(f"Submission not found: {certificate.submission_id}")
        canonical_content = self._canonical_block_content_for_submission(certificate_submission)

        # Extract text content if not provided.
        if not text_content:
            if is_text_payload and file_exists:
                print("Debug: Reading text content from the stored text payload.")
                with open(image_path, "r", encoding="utf-8") as text_file:
                    text_content = text_file.read()
            else:
                print("Debug: Extracting text content from the image.")
                text_content = extract_text(image_path)
            if not text_content:
                print(f"Debug: No text extracted from image {image_path}.")
                raise ValueError("No text content could be extracted from the image.")

        # ✅ Meme Validation Check
        normalized_text = re.sub(r'[^\w\s]', '', text_content).strip().lower()  # Normalize text
        if is_text_payload:
            image_hash = compute_text_content_hash(text_content)
        else:
            image_hash = hash_image(image_path)  # Compute image hash

        if validate_meme:
            if is_text_payload:
                if normalized_text in self.texts:
                    print(f"Debug: Duplicate text payload detected: '{normalized_text}' already exists.")
                    raise ValueError("This meme has already been submitted.")
            elif image_hash in self.image_hashes and normalized_text in self.texts:
                print(f"Debug: Duplicate meme detected! Image hash {image_hash} and text '{normalized_text}' already exist.")
                raise ValueError("This meme has already been submitted.")

        meme_encoded = canonical_content["encoded_content"]

        # âœ… Calculate meme size (base64 encoding increases size)
        meme_size_kb = len(meme_encoded) / 1024
        text_size_kb = len(text_content.encode()) / 1024  # Convert text content size to KB

        native_transaction_plan = self.select_native_transactions_for_block(
            max_transactions_per_block=MAX_TRANSACTIONS_PER_BLOCK,
        )
        native_transactions_for_block = native_transaction_plan["transactions"]
        native_tx_size_kb = len(
            json.dumps(
                native_transactions_for_block,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        ) / 1024 if native_transactions_for_block else 0

        # Validate transactions and calculate total tips
        valid_transactions = []
        total_tx_size_kb = 0  # âœ… Track total transaction size
        total_miner_tips = 0  # âœ… Only track minerâ€™s tip earnings

        print("Debug: Validating transactions concurrently...")
        with ThreadPoolExecutor() as executor:
            future_to_tx = {executor.submit(self.validate_transaction, tx): tx for tx in self.pending_transactions}
            for future in future_to_tx:
                tx = future_to_tx[future]
                try:
                    if future.result():
                        tip = tx.tip  # âœ… Keep tip logic

                        # âœ… Tip Distribution (Existing Model)
                        if self.reward_pool < (self.initial_reward_pool * 0.25):
                            tip_split = {"miner": 0.25, "reward_pool": 0.75}
                        else:
                            tip_split = {"miner": 0.5, "reward_pool": 0.5}

                        miner_tip_share = tip * tip_split["miner"]
                        reward_pool_tip_share = tip * tip_split["reward_pool"]

                        # âœ… Add to balances
                        self.reward_pool += reward_pool_tip_share  # âœ… Only tips go to reward pool
                        total_miner_tips += miner_tip_share  # âœ… Miner gets tip only

                        # âœ… Debugging Output
                        print(f"Debug: Transaction Distribution - Tip Total: {tip:.4f}")
                        print(f"Debug: - Miner gets: {miner_tip_share:.4f}")
                        print(f"Debug: - Reward Pool gets: {reward_pool_tip_share:.4f}")

                        tx_size_kb = len(str(tx)) / 1024  # âœ… Convert transaction size to KB
                        total_tx_size_kb += tx_size_kb
                        valid_transactions.append(tx)
                except Exception as e:
                    print(f"Debug: Transaction validation error: {e}")

        # âœ… Calculate total block size
        total_block_size_kb = meme_size_kb + text_size_kb + total_tx_size_kb + native_tx_size_kb

        # âœ… Enforce block size limit
        print(f"Debug: Approximate pre-serialization block size: {total_block_size_kb:.2f} KB")

        # âœ… Ensure minerâ€™s balance is updated
        if miner in self.wallets:
            current_balance = self.get_balance(miner)  # âœ… Get miner's balance
            updated_balance = current_balance + total_miner_tips  # âœ… Add miner's earnings
            print(f"Debug: Before crediting miner {miner}: {current_balance:.4f} {COIN_NAME}")
            print(f"Debug: Miner earned: {total_miner_tips:.4f} {COIN_NAME}")

            # âœ… Store the updated balance at the blockchain level
            self.wallets[miner].stored_balance = updated_balance  # âœ… Store updated balance

            print(f"Debug: After crediting miner {miner}: {self.wallets[miner].stored_balance:.4f} {COIN_NAME}")
        else:
            print(f"Debug: WARNING! Miner {miner} not found in registered wallets. Initializing new wallet.")

            # âœ… Initialize the miner's wallet with the earned balance
            self.wallets[miner] = Wallet()
            self.wallets[miner].public_key = miner
            self.wallets[miner].private_key = None  # Minerâ€™s private key is unknown
            self.wallets[miner].stored_balance = total_miner_tips  # âœ… Store the initial balance
            print(f"Debug: New miner wallet created for {miner} with balance: {total_miner_tips:.4f} {COIN_NAME}")

        # Add creator reward
        mining_reward = float(MEME_BLOCK_REWARD)
        if self.reward_pool < mining_reward:
            print("Error: Insufficient funds in the reward pool.")
            raise ValueError("Insufficient funds in the reward pool.")

        reward_receiver = reward_recipient or miner
        if reward_receiver not in {"GENESIS", "REWARD_POOL"}:
            normalized_reward_receiver = self._normalize_native_wallet_identity(reward_receiver)
            if normalized_reward_receiver is None:
                raise ValueError("Minting reward recipient is missing or invalid for this submission.")
            reward_receiver = normalized_reward_receiver

        voter_reward_plan = (
            self._select_voter_reward_records_for_block(
                prioritized_submission_id=certificate.submission_id,
            )
            if VOTER_REWARDS_ENABLED and certificate is not None
            else {"selected": [], "skipped": []}
        )
        voter_reward_transactions = [
            Transaction("REWARD_POOL", reward_record["reward_recipient"], float(reward_record["reward_amount"]))
            for reward_record in voter_reward_plan["selected"]
        ]
        total_voter_reward_amount = sum(
            float(reward_record["reward_amount"])
            for reward_record in voter_reward_plan["selected"]
        )
        reward_transaction = Transaction("REWARD_POOL", reward_receiver, float(mining_reward))
        self.reward_pool -= mining_reward
        self.reward_pool -= total_voter_reward_amount

        # Create the new block
        latest_block = self.get_latest_block()
        minted_at = time.time()
        reward_metadata = self.build_meme_reward_metadata(
            certificate_submission,
            certificate,
            minted_at=minted_at,
        )
        new_block = Block(
            index=latest_block.index + 1,
            previous_hash=latest_block.hash,
            timestamp=minted_at,
            transactions=voter_reward_transactions + [reward_transaction] + valid_transactions,
            meme={
                "encoded_content": meme_encoded,
                "text": text_content,
                "compression_algorithm": canonical_content["compression_algorithm"],
                "compression_version": canonical_content["compression_version"],
            },
            miner=miner,
            native_transactions=native_transactions_for_block,
            transaction_ids=native_transaction_plan["transaction_ids"],
            transaction_count=native_transaction_plan["transaction_count"],
            transactions_hash=native_transaction_plan["transactions_hash"],
            **(self.certificate_block_metadata(certificate) if certificate else {}),
            content_hash=canonical_content["content_hash"],
            original_content_hash=canonical_content["original_content_hash"],
            compression_algorithm=canonical_content["compression_algorithm"],
            compression_version=canonical_content["compression_version"],
            canonical_size_bytes=canonical_content["canonical_size_bytes"],
            original_size_bytes=canonical_content["original_size_bytes"],
            content_id=canonical_content["content_id"],
            mime_type=canonical_content["mime_type"],
            content_type=canonical_content["content_type"],
            **reward_metadata,
            voter_rewards=voter_reward_plan["selected"],
        )
        new_block.reward_type = "meme_mining_reward"
        new_block.reward_recipient = reward_transaction.recipient
        new_block.reward_amount = float(mining_reward)
        new_block.reward_source = "reward_pool"
        new_block.minted_at = minted_at
        new_block.voter_rewards = list(voter_reward_plan["selected"])
        new_block.hash = new_block.calculate_hash()
        self.validate_serialized_block_size(new_block)
        self.chain.append(new_block)
        self.settle_block_native_transactions(new_block)
        self.pending_transactions = [tx for tx in self.pending_transactions if tx not in valid_transactions]
        for skipped in native_transaction_plan["skipped"]:
            tx_id = skipped.get("tx_id")
            if not tx_id or self.get_native_transaction(tx_id) is None:
                continue
            if skipped.get("reason") == "already_settled":
                continue
            self.update_native_transaction_status(
                tx_id,
                status="rejected",
                rejection_reason=skipped.get("reason") or "validation_failed",
            )

        # âœ… Cache meme data after block is added
        print(f"Debug: Caching meme data for image {image_path}.")
        self.image_hashes.add(image_hash)
        self.texts.append(normalized_text)

        print(f"Block {new_block.index} added with meme: {text_content}. Final size: {total_block_size_kb:.2f} KB.")
        print(f"Miner earned: {total_miner_tips:.4f} {COIN_NAME}.")

        self.save_blockchain()

        return True

    def get_latest_block(self):
        return self.chain[-1]

    def get_block_by_hash(self, block_hash):
        return self.storage.get_block_by_hash(block_hash, self.chain)

    def get_block_by_height(self, height):
        return self.storage.get_block_by_height(height, self.chain)

    @staticmethod
    def calculate_cumulative_originality_score(chain):
        cumulative_score = 0
        for block in chain:
            if isinstance(block, dict):
                if block.get("index") == 0:
                    continue
                originality_score = block.get("originality_score", 0)
            else:
                if getattr(block, "index", None) == 0:
                    continue
                originality_score = getattr(block, "originality_score", 0)

            if originality_score is not None:
                cumulative_score += originality_score

        return round(cumulative_score, 8)

    def get_cumulative_originality_score(self):
        return self.calculate_cumulative_originality_score(self.chain)

    @staticmethod
    def chain_to_dicts(chain):
        return [
            block.to_dict() if hasattr(block, "to_dict") else block
            for block in chain
        ]

    @staticmethod
    def chain_height(chain_dicts):
        if not chain_dicts:
            return None
        return chain_dicts[-1].get("index")

    @staticmethod
    def chain_latest_hash(chain_dicts):
        if not chain_dicts:
            return None
        return chain_dicts[-1].get("hash")

    def compare_chains_by_originality(self, local_chain, candidate_chain):
        local_chain_dicts = self.chain_to_dicts(local_chain)
        candidate_chain_dicts = self.chain_to_dicts(candidate_chain)
        local_score = self.calculate_cumulative_originality_score(local_chain_dicts)
        candidate_score = self.calculate_cumulative_originality_score(candidate_chain_dicts)
        local_height = self.chain_height(local_chain_dicts)
        candidate_height = self.chain_height(candidate_chain_dicts)
        local_latest_hash = self.chain_latest_hash(local_chain_dicts)
        candidate_latest_hash = self.chain_latest_hash(candidate_chain_dicts)

        result = {
            "local_score": local_score,
            "candidate_score": candidate_score,
            "local_height": local_height,
            "candidate_height": candidate_height,
            "local_latest_hash": local_latest_hash,
            "candidate_latest_hash": candidate_latest_hash,
        }

        if not local_chain_dicts or not candidate_chain_dicts:
            return {
                **result,
                "decision": "invalid_candidate",
                "preferred": "local",
                "reason": "candidate_chain_invalid",
            }
        if candidate_chain_dicts[0].get("hash") != local_chain_dicts[0].get("hash"):
            return {
                **result,
                "decision": "invalid_candidate",
                "preferred": "local",
                "reason": "different_genesis_hash",
            }
        if not self.is_chain_valid(candidate_chain_dicts):
            return {
                **result,
                "decision": "invalid_candidate",
                "preferred": "local",
                "reason": "candidate_chain_invalid",
            }
        if candidate_score > local_score:
            return {
                **result,
                "decision": "replace_with_candidate",
                "preferred": "candidate",
                "reason": "higher_originality_score",
            }
        if candidate_score < local_score:
            return {
                **result,
                "decision": "keep_local",
                "preferred": "local",
                "reason": "lower_originality_score",
            }
        if candidate_height > local_height:
            return {
                **result,
                "decision": "replace_with_candidate",
                "preferred": "candidate",
                "reason": "higher_chain_height",
            }
        if candidate_height < local_height:
            return {
                **result,
                "decision": "keep_local",
                "preferred": "local",
                "reason": "lower_chain_height",
            }
        if candidate_latest_hash < local_latest_hash:
            return {
                **result,
                "decision": "replace_with_candidate",
                "preferred": "candidate",
                "reason": "lower_latest_block_hash",
            }
        if candidate_latest_hash > local_latest_hash:
            return {
                **result,
                "decision": "keep_local",
                "preferred": "local",
                "reason": "higher_latest_block_hash",
            }
        return {
            **result,
            "decision": "equivalent",
            "preferred": "equivalent",
            "reason": "same_latest_block_hash",
        }

    def extract_block_certificate_metadata(self, block_dict):
        fields = [
            "submission_id",
            "certificate_id",
            "content_hash",
            "original_content_hash",
            "content_id",
            "content_type",
            "mime_type",
            "compression_algorithm",
            "compression_version",
            "canonical_size_bytes",
            "original_size_bytes",
            "creator_wallet",
            "vote_hash",
            "approval_percentage",
            "decisive_vote_total",
            "minimum_votes_required",
            "minimum_decisive_votes_required",
            "approved_at",
            "originality_score",
            "reward_type",
            "reward_recipient",
            "reward_amount",
            "reward_source",
            "minted_at",
            "native_transactions",
            "transaction_ids",
            "transaction_count",
            "transactions_hash",
        ]
        meme = block_dict.get("meme") if isinstance(block_dict.get("meme"), dict) else {}
        metadata = {}
        for field_name in fields:
            if block_dict.get(field_name) is not None:
                metadata[field_name] = block_dict.get(field_name)
            elif meme.get(field_name) is not None:
                metadata[field_name] = meme.get(field_name)
        return metadata

    def validate_block_native_transaction_metadata(self, block_dict, *, prior_chain=None):
        self.validate_block_native_transactions(block_dict, prior_chain=prior_chain)
        return True

    def validate_block_with_native_transactions(self, block_dict, *, prior_chain=None):
        self.validate_serialized_block_size(block_dict)
        self.validate_block_certificate_metadata(block_dict, prior_chain=prior_chain)
        self.validate_block_native_transactions(block_dict, prior_chain=prior_chain)
        return True

    def _validate_block_canonical_content(self, block_dict, metadata):
        if block_dict.get("index") == 0:
            return None

        required_fields = [
            "content_hash",
            "original_content_hash",
            "compression_algorithm",
            "compression_version",
            "canonical_size_bytes",
            "original_size_bytes",
        ]
        for field_name in required_fields:
            if metadata.get(field_name) in (None, ""):
                self._raise_native_block_validation_error(
                    "invalid_block_content",
                    f"Block canonical content metadata missing {field_name}.",
                    block_index=block_dict.get("index"),
                    field_name=field_name,
                )

        meme = block_dict.get("meme")
        if not isinstance(meme, dict):
            self._raise_native_block_validation_error(
                "invalid_block_content",
                "Block meme payload must be an object for canonical content validation.",
                block_index=block_dict.get("index"),
            )
        encoded_content = str(meme.get("encoded_content") or "").strip()
        if not encoded_content:
            self._raise_native_block_validation_error(
                "invalid_block_content",
                "Block is missing canonical embedded content.",
                block_index=block_dict.get("index"),
            )

        try:
            canonical_bytes = base64.b64decode(encoded_content.encode("ascii"), validate=True)
        except (ValueError, binascii.Error):
            self._raise_native_block_validation_error(
                "malformed_embedded_content",
                "Block embedded canonical content is malformed base64.",
                block_index=block_dict.get("index"),
            )

        canonical_size_bytes = int(metadata["canonical_size_bytes"])
        if len(canonical_bytes) != canonical_size_bytes:
            self._raise_native_block_validation_error(
                "canonical_size_mismatch",
                "Block canonical_size_bytes does not match decoded embedded content length.",
                block_index=block_dict.get("index"),
                expected_size=canonical_size_bytes,
                actual_size=len(canonical_bytes),
            )
        if canonical_size_bytes > MAX_CANONICAL_CONTENT_BYTES:
            self._raise_native_block_validation_error(
                "canonical_content_oversize",
                "Block canonical content exceeds MAX_CANONICAL_CONTENT_BYTES.",
                block_index=block_dict.get("index"),
                canonical_size_bytes=canonical_size_bytes,
            )

        canonical_hash = compute_content_hash_bytes(canonical_bytes)
        if canonical_hash != metadata["content_hash"]:
            self._raise_native_block_validation_error(
                "content_hash_mismatch",
                "Block embedded canonical content does not match block content_hash.",
                block_index=block_dict.get("index"),
            )

        try:
            original_bytes = canonical_decompress_content_bytes(
                canonical_bytes,
                compression_algorithm=str(metadata["compression_algorithm"]),
                compression_version=int(metadata["compression_version"]),
            )
        except ValueError as exc:
            self._raise_native_block_validation_error(
                "malformed_embedded_content",
                str(exc),
                block_index=block_dict.get("index"),
            )

        original_size_bytes = int(metadata["original_size_bytes"])
        if len(original_bytes) != original_size_bytes:
            self._raise_native_block_validation_error(
                "original_size_mismatch",
                "Block original_size_bytes does not match decompressed content length.",
                block_index=block_dict.get("index"),
                expected_size=original_size_bytes,
                actual_size=len(original_bytes),
            )

        original_hash = compute_content_hash_bytes(original_bytes)
        if original_hash != metadata["original_content_hash"]:
            self._raise_native_block_validation_error(
                "original_content_hash_mismatch",
                "Block embedded content does not match block original_content_hash.",
                block_index=block_dict.get("index"),
            )

        return {
            "canonical_hash": canonical_hash,
            "original_hash": original_hash,
        }

    def _validate_block_voter_rewards(self, block_dict, *, prior_chain=None):
        voter_rewards = block_dict.get("voter_rewards")
        if voter_rewards in (None, []):
            return []
        if not isinstance(voter_rewards, list):
            self._raise_native_block_validation_error(
                "invalid_voter_reward_metadata",
                "Block voter_rewards must be a list when provided.",
                block_index=block_dict.get("index"),
            )

        prior_reward_ids = self._get_settled_voter_reward_ids(chain=self.chain_to_dicts(prior_chain or []))
        seen_reward_ids = set()
        validated_rewards = []

        for reward_entry in voter_rewards:
            if not isinstance(reward_entry, dict):
                self._raise_native_block_validation_error(
                    "invalid_voter_reward_metadata",
                    "Each voter reward entry must be an object.",
                    block_index=block_dict.get("index"),
                )

            required_fields = [
                "reward_id",
                "reward_type",
                "reward_recipient",
                "reward_amount",
                "reward_source",
                "submission_id",
                "vote_choice",
                "final_decision",
                "decision_reason",
                "decision_finalized_at",
                "created_at",
                "network_name",
            ]
            for field_name in required_fields:
                field_value = reward_entry.get(field_name)
                if field_value is None or (isinstance(field_value, str) and not field_value.strip()):
                    self._raise_native_block_validation_error(
                        "invalid_voter_reward_metadata",
                        f"Block voter reward metadata missing {field_name}.",
                        block_index=block_dict.get("index"),
                        field_name=field_name,
                    )

            reward_id = str(reward_entry["reward_id"]).strip()
            if reward_id in seen_reward_ids:
                self._raise_native_block_validation_error(
                    "duplicate_reward",
                    "Block contains duplicate voter reward IDs.",
                    block_index=block_dict.get("index"),
                    reward_id=reward_id,
                )
            if reward_id in prior_reward_ids:
                self._raise_native_block_validation_error(
                    "duplicate_reward",
                    "Block duplicates a voter reward that was already settled earlier in the chain.",
                    block_index=block_dict.get("index"),
                    reward_id=reward_id,
                )

            reward_type = str(reward_entry["reward_type"]).strip()
            if reward_type != "voter_majority_reward":
                self._raise_native_block_validation_error(
                    "invalid_voter_reward_metadata",
                    "Block voter reward_type is invalid.",
                    block_index=block_dict.get("index"),
                    reward_id=reward_id,
                )

            reward_source = str(reward_entry["reward_source"]).strip()
            if reward_source != "reward_pool":
                self._raise_native_block_validation_error(
                    "invalid_voter_reward_metadata",
                    "Block voter reward_source is invalid.",
                    block_index=block_dict.get("index"),
                    reward_id=reward_id,
                )

            normalized_reward_recipient = self._normalize_native_wallet_identity(reward_entry["reward_recipient"])
            if normalized_reward_recipient is None:
                self._raise_native_block_validation_error(
                    "invalid_voter_reward_metadata",
                    "Block voter reward_recipient is invalid.",
                    block_index=block_dict.get("index"),
                    reward_id=reward_id,
                )

            vote_choice = str(reward_entry["vote_choice"]).strip().lower()
            final_decision = str(reward_entry["final_decision"]).strip().lower()
            if vote_choice not in {VOTE_ORIGINAL, VOTE_NOT_ORIGINAL}:
                self._raise_native_block_validation_error(
                    "invalid_voter_reward_metadata",
                    "Block voter reward vote_choice must be decisive.",
                    block_index=block_dict.get("index"),
                    reward_id=reward_id,
                )
            if final_decision not in {VOTER_REWARD_APPROVAL_SIDE, VOTER_REWARD_REJECTION_SIDE}:
                self._raise_native_block_validation_error(
                    "invalid_voter_reward_metadata",
                    "Block voter reward final_decision is invalid.",
                    block_index=block_dict.get("index"),
                    reward_id=reward_id,
                )
            if (final_decision == VOTER_REWARD_APPROVAL_SIDE and vote_choice != VOTE_ORIGINAL) or (
                final_decision == VOTER_REWARD_REJECTION_SIDE and vote_choice != VOTE_NOT_ORIGINAL
            ):
                self._raise_native_block_validation_error(
                    "invalid_voter_reward_metadata",
                    "Block voter reward vote_choice does not match final_decision.",
                    block_index=block_dict.get("index"),
                    reward_id=reward_id,
                )

            try:
                reward_key = self._build_reward_transaction_key(
                    normalized_reward_recipient,
                    reward_entry["reward_amount"],
                )
            except ValueError as exc:
                self._raise_native_block_validation_error(
                    "invalid_voter_reward_metadata",
                    str(exc),
                    block_index=block_dict.get("index"),
                    reward_id=reward_id,
                )

            submission_id = str(reward_entry["submission_id"]).strip()
            expected_rewards = self._expected_voter_reward_records_by_id(submission_id)
            expected_reward = expected_rewards.get(reward_id)
            if expected_reward is None:
                self._raise_native_block_validation_error(
                    "invalid_voter_reward_metadata",
                    "Block voter reward does not match the deterministic reward plan for this submission.",
                    block_index=block_dict.get("index"),
                    reward_id=reward_id,
                    submission_id=submission_id,
                )

            expected_fields = [
                "reward_type",
                "reward_recipient",
                "reward_amount",
                "reward_source",
                "submission_id",
                "certificate_id",
                "content_hash",
                "vote_choice",
                "final_decision",
                "decision_reason",
                "decision_finalized_at",
                "created_at",
                "network_name",
            ]
            for field_name in expected_fields:
                if reward_entry.get(field_name) != expected_reward.get(field_name):
                    self._raise_native_block_validation_error(
                        "invalid_voter_reward_metadata",
                        f"Block voter reward {field_name} does not match the deterministic reward plan.",
                        block_index=block_dict.get("index"),
                        reward_id=reward_id,
                        field_name=field_name,
                    )

            seen_reward_ids.add(reward_id)
            validated_rewards.append(
                {
                    "reward_id": reward_id,
                    "reward_key": reward_key,
                }
            )

        return validated_rewards

    def validate_block_certificate_metadata(self, block_dict, *, prior_chain=None):
        if block_dict.get("index") == 0:
            return True

        metadata = self.extract_block_certificate_metadata(block_dict)
        validated_voter_rewards = self._validate_block_voter_rewards(block_dict, prior_chain=prior_chain)
        if not metadata:
            if validated_voter_rewards:
                self._raise_native_block_validation_error(
                    "invalid_voter_reward_metadata",
                    "Blocks with voter rewards must include certified meme block metadata.",
                    block_index=block_dict.get("index"),
                )
            return True

        required_fields = [
            "submission_id",
            "certificate_id",
            "content_hash",
            "creator_wallet",
            "vote_hash",
            "approval_percentage",
            "decisive_vote_total",
            "minimum_votes_required",
            "approved_at",
            "originality_score",
        ]
        if self._block_native_transactions(block_dict) and not self._native_block_requires_certificate_context(block_dict):
            self._raise_native_block_validation_error(
                "invalid_block_context",
                "Blocks containing native transactions must include certified meme block metadata and reward metadata.",
                block_index=block_dict.get("index"),
            )
        if not any(metadata.get(field_name) is not None for field_name in required_fields):
            return True
        for field_name in required_fields:
            if field_name not in metadata:
                self._raise_native_block_validation_error(
                    "invalid_block_context",
                    f"Block certificate metadata missing {field_name}.",
                    block_index=block_dict.get("index"),
                    field_name=field_name,
                )

        self._validate_block_canonical_content(block_dict, metadata)
        certificate = self.get_originality_certificate(metadata["certificate_id"])
        if not certificate:
            self._raise_native_block_validation_error(
                "unknown_certificate",
                "Block references unknown originality certificate.",
                certificate_id=metadata["certificate_id"],
            )

        if certificate.submission_id != metadata["submission_id"]:
            self._raise_native_block_validation_error(
                "certificate_submission_mismatch",
                "Block certificate_id does not match block submission_id.",
                certificate_id=metadata["certificate_id"],
                submission_id=metadata["submission_id"],
            )
        if certificate.content_hash != metadata["original_content_hash"]:
            self._raise_native_block_validation_error(
                "original_content_hash_mismatch",
                "Block certificate content_hash does not match block original_content_hash.",
                certificate_id=metadata["certificate_id"],
                submission_id=metadata["submission_id"],
            )
        if metadata.get("content_id") is not None:
            certificate_content_id = getattr(certificate, "content_id", None)
            if certificate_content_id is not None and certificate_content_id != metadata["content_id"]:
                self._raise_native_block_validation_error(
                    "content_id_mismatch",
                    "Block content_id does not match certificate content_id.",
                    certificate_id=metadata["certificate_id"],
                    submission_id=metadata["submission_id"],
                )

        submission = self.get_submission(metadata["submission_id"])
        if submission:
            validate_certificate_for_submission(certificate, submission, network_name=NETWORK_NAME)
            if metadata["original_content_hash"] != submission.content_hash:
                self._raise_native_block_validation_error(
                    "original_content_hash_mismatch",
                    "Block original_content_hash does not match submission.",
                    submission_id=metadata["submission_id"],
                )
            if metadata.get("content_id") is not None and metadata["content_id"] != submission.content_id:
                self._raise_native_block_validation_error(
                    "content_id_mismatch",
                    "Block content_id does not match submission.",
                    submission_id=metadata["submission_id"],
                )

        for field_name in [
            "submission_id",
            "certificate_id",
            "creator_wallet",
            "vote_hash",
            "approval_percentage",
            "decisive_vote_total",
            "minimum_votes_required",
            "minimum_decisive_votes_required",
            "approved_at",
            "originality_score",
        ]:
            certificate_value = getattr(certificate, field_name)
            metadata_value = metadata.get(field_name)
            if field_name == "minimum_decisive_votes_required" and metadata_value is None:
                metadata_value = metadata.get("minimum_votes_required")
            if metadata_value != certificate_value:
                self._raise_native_block_validation_error(
                    "certificate_metadata_mismatch",
                    f"Block certificate metadata {field_name} does not match certificate.",
                    field_name=field_name,
                    certificate_id=metadata["certificate_id"],
                    submission_id=metadata["submission_id"],
                )

        reward_fields_present = any(
            metadata.get(field_name) is not None
            for field_name in ["reward_type", "reward_recipient", "reward_amount", "reward_source", "minted_at"]
        )
        if reward_fields_present:
            reward_required_fields = [
                "reward_type",
                "reward_recipient",
                "reward_amount",
                "reward_source",
                "minted_at",
            ]
            for field_name in reward_required_fields:
                if metadata.get(field_name) is None:
                    self._raise_native_block_validation_error(
                        "invalid_reward_metadata",
                        f"Block reward metadata missing {field_name}.",
                        submission_id=metadata["submission_id"],
                        field_name=field_name,
                    )
            if metadata["reward_type"] != "meme_mining_reward":
                self._raise_native_block_validation_error(
                    "invalid_reward_metadata",
                    "Block reward_type is invalid.",
                    submission_id=metadata["submission_id"],
                )
            if metadata["reward_source"] != "reward_pool":
                self._raise_native_block_validation_error(
                    "invalid_reward_metadata",
                    "Block reward_source is invalid.",
                    submission_id=metadata["submission_id"],
                )
            normalized_reward_recipient = self._normalize_native_wallet_identity(metadata["reward_recipient"])
            if normalized_reward_recipient is None:
                self._raise_native_block_validation_error(
                    "reward_recipient_mismatch",
                    "Block reward_recipient is invalid.",
                    submission_id=metadata["submission_id"],
                )
            if float(metadata["reward_amount"]) != float(MEME_BLOCK_REWARD):
                self._raise_native_block_validation_error(
                    "reward_amount_mismatch",
                    "Block reward_amount does not match configured reward.",
                    submission_id=metadata["submission_id"],
                    reward_amount=metadata["reward_amount"],
                )
            if submission:
                expected_reward_recipient = self.resolve_meme_reward_recipient(submission, certificate)
                if normalized_reward_recipient != expected_reward_recipient:
                    self._raise_native_block_validation_error(
                        "reward_recipient_mismatch",
                        "Block reward_recipient does not match submission creator wallet.",
                        submission_id=metadata["submission_id"],
                        reward_recipient=normalized_reward_recipient,
                    )
            prior_chain_dicts = self.chain_to_dicts(prior_chain or [])
            if any(
                prior_block.get("submission_id") == metadata["submission_id"]
                and prior_block.get("reward_type") == "meme_mining_reward"
                for prior_block in prior_chain_dicts
            ):
                self._raise_native_block_validation_error(
                    "duplicate_reward",
                    "Block duplicates the meme reward for an already minted submission.",
                    submission_id=metadata["submission_id"],
                )

        expected_reward_transaction_keys = [
            validated_reward["reward_key"]
            for validated_reward in validated_voter_rewards
        ]
        if expected_reward_transaction_keys:
            reward_transaction_counter = Counter()
            for transaction in self._block_reward_transactions(block_dict):
                try:
                    reward_key = self._build_reward_transaction_key(
                        transaction.get("recipient"),
                        transaction.get("amount"),
                    )
                except ValueError:
                    self._raise_native_block_validation_error(
                        "invalid_reward_metadata",
                        "Block contains an invalid REWARD_POOL transaction.",
                        block_index=block_dict.get("index"),
                    )
                reward_transaction_counter[reward_key] += 1

            expected_reward_counter = Counter(expected_reward_transaction_keys)
            if any(
                reward_transaction_counter[reward_key] < expected_count
                for reward_key, expected_count in expected_reward_counter.items()
            ):
                self._raise_native_block_validation_error(
                    "invalid_reward_metadata",
                    "Block voter reward transactions do not match the declared reward metadata.",
                    block_index=block_dict.get("index"),
                    expected_voter_reward_transactions=sum(expected_reward_counter.values()),
                    actual_reward_transactions=sum(reward_transaction_counter.values()),
                )

        content_object = self.get_content_object_by_hash(metadata["original_content_hash"])
        if content_object is not None:
            if metadata.get("content_id") is not None and metadata["content_id"] != content_object.content_id:
                self._raise_native_block_validation_error(
                    "content_id_mismatch",
                    "Block content_id does not match content object.",
                    submission_id=metadata["submission_id"],
                )
            if metadata.get("content_type") is not None and metadata["content_type"] != content_object.content_type:
                if not (
                    content_object.storage_status in {STORAGE_STATUS_REMOTE, STORAGE_STATUS_MISSING}
                    and content_object.content_type == CONTENT_TYPE_IMAGE
                    and metadata["content_type"] in {CONTENT_TYPE_MIXED, CONTENT_TYPE_TEXT}
                ):
                    self._raise_native_block_validation_error(
                        "content_type_mismatch",
                        "Block content_type does not match content object.",
                        submission_id=metadata["submission_id"],
                    )
            if metadata.get("mime_type") is not None and metadata["mime_type"] != content_object.mime_type:
                if not (
                    content_object.storage_status in {STORAGE_STATUS_REMOTE, STORAGE_STATUS_MISSING}
                    and content_object.mime_type == "application/octet-stream"
                ):
                    self._raise_native_block_validation_error(
                        "mime_type_mismatch",
                        "Block mime_type does not match content object.",
                        submission_id=metadata["submission_id"],
                    )
            if content_object.storage_status == STORAGE_STATUS_VERIFIED:
                verification = verify_content_object_payload(content_object, data_dir=self.storage.data_dir)
                if not verification["verified"]:
                    self._raise_native_block_validation_error(
                        "original_content_hash_mismatch",
                        "Verified local content file does not match block original_content_hash.",
                        submission_id=metadata["submission_id"],
                    )

        return True

    def is_chain_valid(self, chain):
        """Validate a given chain."""
        for i in range(1, len(chain)):
            current_block = chain[i]
            previous_block = chain[i - 1]

            # Validate the hash of the block
            if current_block["hash"] != self.calculate_hash_from_dict(current_block):
                print(f"Debug: Block {current_block['index']} hash is invalid!")
                return False

            # Validate the previous hash link
            if current_block["previous_hash"] != previous_block["hash"]:
                print(f"Debug: Block {current_block['index']} previous hash does not match!")
                return False

            try:
                self.validate_block_with_native_transactions(current_block, prior_chain=chain[:i])
            except ValueError as e:
                print(f"Debug: Block {current_block['index']} transaction or certificate metadata is invalid: {e}")
                return False

        return True

    def get_native_balance(self, wallet_address):
        normalized_wallet = self._normalize_native_wallet_identity(wallet_address)
        if normalized_wallet is None:
            return 0
        return float(self.get_final_native_balance_amount(normalized_wallet))

    def get_balance(self, public_key):
        """Calculate balance based on on-chain native transactions."""
        return self.get_native_balance(public_key)

    def add_transaction(self, transaction):
        try:
            print(f"Debug: Validating transaction from {transaction.sender} to {transaction.recipient} "
                f"for {transaction.amount} + tip {transaction.tip}")

            if not transaction.is_valid():
                raise Exception("Invalid transaction: Signature is not valid.")

            sender_balance = self.get_balance(transaction.sender)
            total_deduction = transaction.amount + transaction.tip  # âœ… Only deduct amount + tip (NO FEE)
            print(f"Debug: Sender balance: {sender_balance}, Total Deduction: {total_deduction}")

            if sender_balance < total_deduction:
                raise Exception("Insufficient balance to cover the transaction and tip.")

            # Add to pending transactions
            self.pending_transactions.append(transaction)
            print(f"Debug: Transaction added to pending transactions. Pending count: {len(self.pending_transactions)}")
        except Exception as e:
            print(f"Debug: Transaction validation error: {e}")
            raise

    def get_transaction_pool(self):
        """Retrieve the current transaction pool."""
        return [tx.to_dict() for tx in self.pending_transactions]

    def validate_transaction(self, transaction):
        """Validates a single transaction, including checking sender balance."""
        try:
            if not transaction.is_valid():
                return False

            sender_balance = self.get_balance(transaction.sender)
            total_deduction = transaction.amount + transaction.tip  # âœ… Only deduct amount + tip (NO FEE)
            print(f"Debug: Validating Transaction - Sender Balance: {sender_balance}, Required: {total_deduction}")

            if sender_balance < total_deduction:
                print("Debug: Insufficient balance to cover the transaction and tip.")
                return False

            return True
        except Exception as e:
            print(f"Debug: Transaction validation failed - {e}")
            return False

    def get_chain_as_dict(self):
        """Return the blockchain as a list of dictionaries."""
        return [block.__dict__ for block in self.chain]
    
    def replace_chain(self, new_chain):
        """Replace the current chain only when the originality fork-choice rule prefers it."""
        comparison = self.compare_chains_by_originality(self.chain, new_chain)
        if comparison["decision"] == "replace_with_candidate":
            self.chain = new_chain
            print(f"Debug: Replaced local chain: {comparison['reason']}.")
            return True
        print(f"Debug: Received chain not selected: {comparison['reason']}.")
        return False
    
    def calculate_hash_from_dict(self, block_dict):
        """Calculate the hash for a block dictionary."""
        transaction_data = "".join(
            [
                f"{tx['sender']}{tx['recipient']}{_hash_number(tx['amount'])}{_hash_number(tx['tip'])}{_hash_number(tx['payload_size_kb'])}{tx['signature']}"
                for tx in block_dict["transactions"]
            ]
        )
        certificate_data = ""
        certificate_metadata = self.extract_block_certificate_metadata(block_dict)
        if certificate_metadata:
            certificate_data = json.dumps(
                certificate_metadata,
                sort_keys=True,
                separators=(",", ":"),
            )
        meme_data = json.dumps(
            block_dict["meme"],
            sort_keys=True,
            separators=(",", ":"),
        )
        block_string = f"{block_dict['index']}{block_dict['previous_hash']}{block_dict['timestamp']}{transaction_data}{meme_data}{block_dict['miner']}{certificate_data}"
        return hashlib.sha256(block_string.encode()).hexdigest()
    
    def is_valid_public_key(self, public_key):
        """Check if the given public key is valid."""
        if is_valid_ethereum_address(str(public_key or "").strip()):
            return True
        if public_key in self.wallets:
            return True
        print(f"Debug: Invalid public key: {public_key}")
        return False
    


