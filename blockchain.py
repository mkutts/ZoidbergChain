# Import statements
import os
import hashlib
import math
import time
import base64
import re
import secrets
from collections import Counter
from PIL import Image
import imagehash
from concurrent.futures import ThreadPoolExecutor
import pytesseract
import time
from block import Block, PROTOCOL_V1_BLOCK_VERSION
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
    MAX_TRANSACTIONS_PER_BLOCK,
    MIN_VOTE_FLOOR,
    NETWORK_NAME,
    NODE_ID,
    ORIGINALITY_APPROVAL_THRESHOLD,
    PROTOCOL_V1_CONFIRMATION_DEPTH,
    PROTOCOL_V1_FINALITY_DEPTH,
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
    canonicalize_text_content,
    content_object_from_submission_data,
    compute_text_content_hash,
    ensure_content_storage_dir,
    guess_mime_type,
    load_content_bytes,
    resolve_declared_payload_hash,
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
from protocol_v1_native_transfer import (
    PROTOCOL_V1_NATIVE_TRANSFER_VERSION,
    build_protocol_v1_native_transfer_message,
    looks_like_protocol_v1_native_transfer_message,
    resolve_protocol_v1_network_id,
)
from storage import create_storage_backend
from protocol_v1 import PROTOCOL_VERSION, resolve_network_id
from protocol_v1_genesis import (
    GenesisValidationError,
    PUBLIC_TESTNET_V1_INITIAL_REWARD_POOL,
    PUBLIC_TESTNET_V1_TOTAL_SUPPLY,
    canonical_public_testnet_v1_genesis_hash,
    canonical_public_testnet_v1_genesis_record,
    validate_public_testnet_v1_genesis_record,
)
from validators import is_valid_content_hash, is_valid_ethereum_address, is_valid_user_wallet_identity
from wallet_auth import hash_wallet_message, normalize_wallet_address
from access_control import access_decision_for_wallet, generate_access_code, hash_access_code, normalize_email, normalize_handle, normalize_text_field, utc_now_iso
from services import AccessAdminService, AccessAdminState, ContentCoordinationService, ContentCoordinationState, FeedbackService, FeedbackState, MintQueueService, MintQueueState, NativeLedgerService, NativeLedgerState, NativeMempoolService, RewardCollaborators, RewardService, RewardState, SubmissionOriginalityService, SubmissionOriginalityState

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
        self._access_admin_service = AccessAdminService()
        self._feedback_service = FeedbackService()
        self._content_coordination_service = ContentCoordinationService()
        self._submission_originality_service = SubmissionOriginalityService()
        self._mint_queue_service = MintQueueService()
        self._native_ledger_service = NativeLedgerService()
        self._native_mempool_service = NativeMempoolService(self._native_ledger_service)
        self._reward_service = RewardService()
        self._last_reward_excluded_voters = []
        self.reward_pool = REWARD_POOL_SUPPLY  # Initial reward pool
        self.initial_reward_pool = self.reward_pool  # Set the initial reward pool value
        self.storage = storage_backend or create_storage_backend()
        ensure_content_storage_dir(data_dir=self.storage.data_dir)
        self._validate_frozen_public_testnet_v1_runtime_constants()

        # Ã¢Å“â€¦ Store wallets immediately before loading blockchain
        self.project_owner_wallet = project_owner_wallet
        self.Contributor_one = Contributor_one
        self.Contributor_two = Contributor_two

        # Ã¢Å“â€¦ Load blockchain from storage, ensuring wallets persist
        self.load_blockchain()
        if not self.chain:
            print("Debug: No valid blockchain found. Creating Genesis blockchain...")
            self.create_genesis_block(self.project_owner_wallet, self.Contributor_one, self.Contributor_two)
            self.save_blockchain()

        # Ã¢Å“â€¦ Ensure wallets are always assigned even after loading blockchain
        if self.project_owner_wallet and self.project_owner_wallet.public_key not in self.wallets:
            self.wallets[self.project_owner_wallet.public_key] = self.project_owner_wallet
        if self.Contributor_one and self.Contributor_one.public_key not in self.wallets:
            self.wallets[self.Contributor_one.public_key] = self.Contributor_one
        if self.Contributor_two and self.Contributor_two.public_key not in self.wallets:
            self.wallets[self.Contributor_two.public_key] = self.Contributor_two

        # Ã¢Å“â€¦ Debugging - Print wallet storage
        print("Debug: Registered Wallets -", [_short_public_key(key) for key in self.wallets.keys()])

    def _serialize_blockchain_state(self):
        return {
            "chain": [block.to_dict() for block in self.chain],
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
    def _validate_frozen_public_testnet_v1_runtime_constants() -> None:
        if TOTAL_SUPPLY != PUBLIC_TESTNET_V1_TOTAL_SUPPLY:
            raise GenesisValidationError(
                "genesis_configuration_mismatch",
                "TOTAL_SUPPLY does not match the frozen Public Testnet v1 genesis definition.",
                details={
                    "total_supply": TOTAL_SUPPLY,
                    "expected_total_supply": PUBLIC_TESTNET_V1_TOTAL_SUPPLY,
                },
            )
        if REWARD_POOL_SUPPLY != PUBLIC_TESTNET_V1_INITIAL_REWARD_POOL:
            raise GenesisValidationError(
                "genesis_configuration_mismatch",
                "REWARD_POOL_SUPPLY does not match the frozen Public Testnet v1 genesis definition.",
                details={
                    "initial_reward_pool": REWARD_POOL_SUPPLY,
                    "expected_initial_reward_pool": PUBLIC_TESTNET_V1_INITIAL_REWARD_POOL,
                },
            )

    @staticmethod
    def public_testnet_v1_genesis_hash() -> str:
        return canonical_public_testnet_v1_genesis_hash()

    @staticmethod
    def canonical_public_testnet_v1_genesis_block() -> Block:
        return Block.from_dict(canonical_public_testnet_v1_genesis_record())

    def validate_canonical_public_testnet_v1_genesis(self, block) -> bool:
        block_dict = block.to_dict() if hasattr(block, "to_dict") else dict(block)
        validate_public_testnet_v1_genesis_record(block_dict)
        calculated_hash = self.calculate_hash_from_dict(block_dict)
        expected_hash = self.public_testnet_v1_genesis_hash()
        if calculated_hash != expected_hash:
            raise GenesisValidationError(
                "genesis_mismatch",
                "Genesis hash does not match the frozen Public Testnet v1 hash.",
                details={
                    "expected_genesis_hash": expected_hash,
                    "actual_genesis_hash": calculated_hash,
                },
            )
        return True

    @staticmethod
    def _coerce_native_event_timestamp(value) -> str:
        if isinstance(value, bool):
            return Blockchain._utc_now_iso()
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        candidate = str(value or "").strip()
        return candidate

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
            "transaction_version": payload.get("transaction_version"),
            "protocol_version": payload.get("protocol_version"),
            "network_id": payload.get("network_id"),
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
        return self._native_ledger_service.restore_native_transaction_state(raw_transactions, raw_transfer_intents)
    def save_blockchain(self):
        """Save blockchain state to disk, including wallets and transactions."""
        self.storage.save_blockchain_state(self._serialize_blockchain_state())
        print("Debug: Blockchain and wallets saved successfully.")
    def _access_admin_state(self):
        return AccessAdminState(
            self.access_requests,
            self.access_accounts,
            self.wallet_bindings,
            self.allowlist_entries,
            self.override_requests,
            self.audit_logs,
        )

    def _feedback_state(self):
        return FeedbackState(self.feedback_records)

    def _content_coordination_state(self):
        return ContentCoordinationState(self.submissions, self.content_objects, self.text_validation_cache, self.image_validation_cache, self.texts, self.image_hashes)

    def _submission_originality_state(self):
        return SubmissionOriginalityState(self.submissions, self.votes, self.originality_certificates, self.mint_queue)

    def _mint_queue_state(self):
        return MintQueueState(self.submissions, self.content_objects, self.originality_certificates, self.mint_queue)

    def _native_ledger_state(self):
        return NativeLedgerState(self.chain, self.transfer_intents, self.native_transactions)

    def _reward_state(self):
        return RewardState(self.chain, self.submissions, self.reward_pool, {
            "reward_pool_supply": REWARD_POOL_SUPPLY,
            "require_access_for_rewards": REQUIRE_ACCESS_FOR_REWARDS,
            "voter_rewards_enabled": VOTER_REWARDS_ENABLED,
            "voter_reward_pool_per_decision_zoid": VOTER_REWARD_POOL_PER_DECISION_ZOID,
            "voter_reward_max_per_wallet_zoid": VOTER_REWARD_MAX_PER_WALLET_ZOID,
            "voter_reward_require_review_eligible": VOTER_REWARD_REQUIRE_REVIEW_ELIGIBLE,
        })

    def _reward_collaborators(self):
        return RewardCollaborators(
            normalize_wallet=self._native_ledger_service.normalize_wallet_identity,
            get_submission=self.get_submission,
            get_votes=self.get_submission_votes,
            get_certificate=self.get_originality_certificate_for_submission,
            get_voting_threshold=self.get_voting_threshold,
            get_activity_summary=self.get_account_activity_summary,
            count_votes_since=self.count_votes_by_wallet_since,
            access_decision=lambda wallet: access_decision_for_wallet(self, wallet, feature="rewards"),
            get_wallet_binding=self.get_wallet_binding,
            get_access_account=self.get_access_account_for_wallet,
            find_allowlist_entry=lambda scope, wallet, account: self.find_matching_allowlist_entry(scope, wallet_address=wallet, access_account=account),
        )

    def refresh_access_control_state_from_storage(self):
        """Refresh access/admin/feedback records without reloading the chain."""
        loaded_data = AccessAdminService.refresh_from_storage(self.storage.load_blockchain_state)
        if loaded_data is None:
            return False
        self.access_requests = list(loaded_data.get("access_requests", []) or [])
        self.access_accounts = list(loaded_data.get("access_accounts", []) or [])
        self.wallet_bindings = list(loaded_data.get("wallet_bindings", []) or [])
        self.allowlist_entries = list(loaded_data.get("allowlist_entries", []) or [])
        self.override_requests = list(loaded_data.get("override_requests", []) or [])
        self.feedback_records = list(loaded_data.get("feedback_records", []) or [])
        self.audit_logs = list(loaded_data.get("audit_logs", []) or [])
        return True

    _normalize_access_wallet = staticmethod(AccessAdminService.normalize_access_wallet)
    _normalize_allowlist_scope = staticmethod(AccessAdminService.normalize_allowlist_scope)
    _normalize_allowlist_status = staticmethod(AccessAdminService.normalize_allowlist_status)
    _normalize_override_request_status = staticmethod(AccessAdminService.normalize_override_request_status)
    _normalize_allowlist_subject = staticmethod(AccessAdminService.normalize_allowlist_subject)
    _allowlist_scope_matches = staticmethod(AccessAdminService.allowlist_scope_matches)
    _allowlist_entry_active = staticmethod(AccessAdminService.allowlist_entry_active)
    _normalize_feedback_type = staticmethod(FeedbackService.normalize_feedback_type)
    _normalize_feedback_status = staticmethod(FeedbackService.normalize_feedback_status)
    _normalize_feedback_priority = staticmethod(FeedbackService.normalize_feedback_priority)
    _normalize_feedback_dimension = staticmethod(FeedbackService.normalize_feedback_dimension)
    _normalize_feedback_snapshot = staticmethod(FeedbackService.normalize_feedback_snapshot)

    def _allowlist_subject_candidates(self, *, wallet_address=None, access_account=None):
        return self._access_admin_service.allowlist_subject_candidates(wallet_address=wallet_address, access_account=access_account)
    def get_allowlist_entry(self, allowlist_entry_id): return self._access_admin_service.get_allowlist_entry(self._access_admin_state(), allowlist_entry_id)
    def list_allowlist_entries(self, *, scope=None, subject_type=None, subject_value=None, status=None): return self._access_admin_service.list_allowlist_entries(self._access_admin_state(), scope=scope, subject_type=subject_type, subject_value=subject_value, status=status)
    def find_matching_allowlist_entry(self, scope, *, wallet_address=None, access_account=None): return self._access_admin_service.find_matching_allowlist_entry(self._access_admin_state(), scope, wallet_address=wallet_address, access_account=access_account)
    def create_allowlist_entry(self, *, scope, subject_type, subject_value, reason=None, expires_at=None, created_by=None, status="active"): return self._access_admin_service.create_allowlist_entry(self._access_admin_state(), scope=scope, subject_type=subject_type, subject_value=subject_value, reason=reason, expires_at=expires_at, created_by=created_by, status=status)
    def update_allowlist_entry(self, allowlist_entry_id, *, scope=None, subject_type=None, subject_value=None, reason=None, expires_at=None, status=None): return self._access_admin_service.update_allowlist_entry(self._access_admin_state(), allowlist_entry_id, scope=scope, subject_type=subject_type, subject_value=subject_value, reason=reason, expires_at=expires_at, status=status)
    def revoke_allowlist_entry(self, allowlist_entry_id, *, revoked_reason=None): return self._access_admin_service.revoke_allowlist_entry(self._access_admin_state(), allowlist_entry_id, revoked_reason=revoked_reason)
    def reactivate_allowlist_entry(self, allowlist_entry_id, *, reason=None): return self._access_admin_service.reactivate_allowlist_entry(self._access_admin_state(), allowlist_entry_id, reason=reason)
    def get_override_request(self, override_request_id): return self._access_admin_service.get_override_request(self._access_admin_state(), override_request_id)
    def list_override_requests(self, *, status=None, requested_scope=None): return self._access_admin_service.list_override_requests(self._access_admin_state(), status=status, requested_scope=requested_scope)
    def create_override_request(self, *, requested_scope, name=None, email=None, handle=None, wallet_address=None, access_account_id=None, reason=None, current_page=None, detected_blocked_reason=None, user_agent=None, remote_ip=None): return self._access_admin_service.create_override_request(self._access_admin_state(), requested_scope=requested_scope, name=name, email=email, handle=handle, wallet_address=wallet_address, access_account_id=access_account_id, reason=reason, current_page=current_page, detected_blocked_reason=detected_blocked_reason, user_agent=user_agent, remote_ip=remote_ip)
    def update_override_request_status(self, override_request_id, *, status, reviewed_by="operator", admin_note=None, resolved_scope=None, approved_allowlist_entry_id=None): return self._access_admin_service.update_override_request_status(self._access_admin_state(), override_request_id, status=status, reviewed_by=reviewed_by, admin_note=admin_note, resolved_scope=resolved_scope, approved_allowlist_entry_id=approved_allowlist_entry_id)
    def get_access_request(self, request_id): return self._access_admin_service.get_access_request(self._access_admin_state(), request_id)
    def get_access_account(self, access_account_id): return self._access_admin_service.get_access_account(self._access_admin_state(), access_account_id)
    def get_wallet_binding(self, wallet_address): return self._access_admin_service.get_wallet_binding(self._access_admin_state(), wallet_address)
    def get_access_account_for_wallet(self, wallet_address): return self._access_admin_service.get_access_account_for_wallet(self._access_admin_state(), wallet_address)
    def list_access_requests(self, *, status=None): return self._access_admin_service.list_access_requests(self._access_admin_state(), status=status)
    def list_access_accounts(self, *, status=None): return self._access_admin_service.list_access_accounts(self._access_admin_state(), status=status)
    def count_active_wallet_bindings(self): return self._access_admin_service.count_active_wallet_bindings(self._access_admin_state())
    def list_wallet_bindings(self, *, access_account_id=None, status=None): return self._access_admin_service.list_wallet_bindings(self._access_admin_state(), access_account_id=access_account_id, status=status)
    def create_access_request(self, *, name, email, handle=None, reason=None, notes=None): return self._access_admin_service.create_access_request(self._access_admin_state(), name=name, email=email, handle=handle, reason=reason, notes=notes)
    def _create_access_account_record(self, *, name, email, handle=None, notes=None, reviewed_by="operator", operator_notes=None, max_wallets=1): return self._access_admin_service._create_access_account_record(self._access_admin_state(), name=name, email=email, handle=handle, notes=notes, reviewed_by=reviewed_by, operator_notes=operator_notes, max_wallets=max_wallets)
    def create_access_invite(self, *, name, email, handle=None, notes=None, reviewed_by="operator", operator_notes=None, max_wallets=1): return self._access_admin_service.create_access_invite(self._access_admin_state(), name=name, email=email, handle=handle, notes=notes, reviewed_by=reviewed_by, operator_notes=operator_notes, max_wallets=max_wallets)
    def approve_access_request(self, request_id, *, reviewed_by="operator", operator_notes=None, max_wallets=1): return self._access_admin_service.approve_access_request(self._access_admin_state(), request_id, reviewed_by=reviewed_by, operator_notes=operator_notes, max_wallets=max_wallets)
    def reject_access_request(self, request_id, *, reviewed_by="operator", operator_notes=None): return self._access_admin_service.reject_access_request(self._access_admin_state(), request_id, reviewed_by=reviewed_by, operator_notes=operator_notes)
    def resolve_access_account_by_invite_code(self, access_code, *, include_redeemed=False): return self._access_admin_service.resolve_access_account_by_invite_code(self._access_admin_state(), access_code, include_redeemed=include_redeemed)
    def mark_access_account_login(self, access_account_id): return self._access_admin_service.mark_access_account_login(self._access_admin_state(), access_account_id)
    def bind_wallet_to_access_account(self, access_account_id, wallet_address, *, source="invite_code"): return self._access_admin_service.bind_wallet_to_access_account(self._access_admin_state(), access_account_id, wallet_address, source=source)
    def update_access_account_status(self, access_account_id, status, *, updated_by="operator", reason=None): return self._access_admin_service.update_access_account_status(self._access_admin_state(), access_account_id, status, updated_by=updated_by, reason=reason)
    def revoke_wallet_binding(self, wallet_address, *, revoked_by="operator", reason=None): return self._access_admin_service.revoke_wallet_binding(self._access_admin_state(), wallet_address, revoked_by=revoked_by, reason=reason)
    def append_audit_log_entry(self, entry): return self._access_admin_service.append_audit_log_entry(self._access_admin_state(), entry)
    def list_audit_log_entries(self, *, action=None, since=None, before=None, limit=None): return self._access_admin_service.list_audit_log_entries(self._access_admin_state(), action=action, since=since, before=before, limit=limit)
    def get_feedback(self, feedback_id): return self._feedback_service.get_feedback(self._feedback_state(), feedback_id)
    def list_feedback(self, *, status=None, feedback_type=None, priority=None, limit=None): return self._feedback_service.list_feedback(self._feedback_state(), status=status, feedback_type=feedback_type, priority=priority, limit=limit)
    def feedback_summary(self): return self._feedback_service.feedback_summary(self._feedback_state())
    def create_feedback(self, *, feedback_type, title, description, name=None, email=None, handle=None, wallet_address=None, access_account_id=None, current_page=None, current_flow=None, user_agent=None, remote_ip=None, browser_metadata=None, eligibility_snapshot=None, viewport_width=None, viewport_height=None, is_mobile=None, priority="normal"): return self._feedback_service.create_feedback(self._feedback_state(), feedback_type=feedback_type, title=title, description=description, name=name, email=email, handle=handle, wallet_address=wallet_address, access_account_id=access_account_id, current_page=current_page, current_flow=current_flow, user_agent=user_agent, remote_ip=remote_ip, browser_metadata=browser_metadata, eligibility_snapshot=eligibility_snapshot, viewport_width=viewport_width, viewport_height=viewport_height, is_mobile=is_mobile, priority=priority)
    def update_feedback(self, feedback_id, *, status=None, priority=None, reviewed_by="operator"): return self._feedback_service.update_feedback(self._feedback_state(), feedback_id, status=status, priority=priority, reviewed_by=reviewed_by)
    def add_feedback_admin_note(self, feedback_id, *, note, created_by="operator"): return self._feedback_service.add_feedback_admin_note(self._feedback_state(), feedback_id, note=note, created_by=created_by)

    def recompute_reward_pool_balance(self, *, chain=None):
        self.reward_pool = self._reward_service.recompute_reward_pool_balance(self._reward_state(), self._reward_collaborators(), chain=chain)
        self.initial_reward_pool = float(REWARD_POOL_SUPPLY)
        return self.reward_pool
    def load_blockchain(self):
        """Load blockchain state from disk if it exists, ensuring wallets persist."""
        try:
            loaded_data = self.storage.load_blockchain_state()

            if isinstance(loaded_data, dict) and "chain" in loaded_data and "wallets" in loaded_data:
                self.chain = [Block.from_dict(block_data) for block_data in loaded_data["chain"]]

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
                self.reconcile_submission_canonical_state()
                mempool_report = self.revalidate_mempool_transactions(save=False)
                if native_state["changed"] or mempool_report["removed"] > 0:
                    self.save_blockchain()
                if native_state["removed"] > 0:
                    print(
                        "Debug: Dropped invalid native transaction state during load - "
                        f"{native_state['removed']} record(s) removed."
                    )
                if self.chain:
                    self.validate_canonical_public_testnet_v1_genesis(self.chain[0])
                    if not self.is_chain_valid(self.chain_to_dicts(self.chain)):
                        raise GenesisValidationError(
                            "invalid_chain_state",
                            "Persisted blockchain state failed chain validation.",
                        )
                print(f"Debug: Blockchain length after loading - {len(self.chain)} blocks")
                print(f"Debug: Wallets loaded: {len(self.wallets)} wallets")
                return True

            if loaded_data is not None:
                raise GenesisValidationError(
                    "invalid_chain_state",
                    "Persisted blockchain state is malformed and cannot be loaded safely.",
                )

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
        except json.JSONDecodeError as exc:
            raise GenesisValidationError(
                "invalid_chain_state",
                "Persisted blockchain state is not valid JSON. Reset the local node data explicitly before restarting.",
            ) from exc
        except GenesisValidationError:
            raise
        except Exception as e:
            raise GenesisValidationError(
                "invalid_chain_state",
                f"Persisted blockchain state failed to load safely: {e}",
            ) from e

        return False

    def create_genesis_block(self, project_owner_wallet, Contributor_one, Contributor_two, initial_supply=TOTAL_SUPPLY):
        """Create the frozen canonical Public Testnet v1 genesis block."""
        self._validate_frozen_public_testnet_v1_runtime_constants()
        genesis_block = self.canonical_public_testnet_v1_genesis_block()
        self.chain = [genesis_block]
        self.validate_canonical_public_testnet_v1_genesis(genesis_block)
        print("Debug: Loaded frozen Public Testnet v1 genesis block.")


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
        return self._content_coordination_service.is_image_unique(self._content_coordination_state(), image_path)
    def is_text_unique(self, text_content):
        """Check if the text is unique with caching."""
        return self._content_coordination_service.is_text_unique(self._content_coordination_state(), text_content)
    def is_meme_original(self, image_path, text_content):
        """Validate meme originality without caching."""
        return self._content_coordination_service.is_meme_original(self._content_coordination_state(), image_path, text_content)
    def _build_content_object_for_submission(self, submission, image_path="", text_content="", storage_status=None):
        return self._content_coordination_service._build_content_object_for_submission(self._content_coordination_state(), self.storage, NETWORK_NAME, submission, image_path, text_content, storage_status)
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

    def _promote_submission_content_for_protocol_v1(self, submission):
        if submission is None:
            raise ValueError("Submission is required.")

        existing_content_object = self.get_content_object_by_hash(submission.content_hash)
        resolved_image_path = resolve_local_path(submission.image_path, data_dir=self.storage.data_dir)
        if not (resolved_image_path and os.path.isfile(resolved_image_path)):
            resolved_image_path = resolve_local_path(
                getattr(existing_content_object, "local_path", None),
                data_dir=self.storage.data_dir,
            )

        expects_binary_payload = bool((submission.image_path or "").strip())
        if getattr(existing_content_object, "content_type", None) in {CONTENT_TYPE_IMAGE, CONTENT_TYPE_MIXED}:
            expects_binary_payload = True

        if resolved_image_path and os.path.isfile(resolved_image_path):
            with open(resolved_image_path, "rb") as image_file:
                content_object = self.upload_binary_content(
                    file_bytes=image_file.read(),
                    submitted_by=submission.submitter,
                    mime_type=guess_mime_type(os.path.basename(resolved_image_path), "image/jpeg"),
                    original_filename=os.path.basename(resolved_image_path),
                    caption=validate_caption(submission.text_content),
                    content_type_hint=self._content_type_hint_for_submission(
                        resolved_image_path,
                        submission.text_content,
                    ),
                )
            submission.image_path = resolved_image_path
        else:
            if expects_binary_payload:
                raise ValueError("Protocol v1 certification requires recoverable binary media bytes.")
            text_content = (
                (submission.text_content or "").strip()
                or (
                    getattr(existing_content_object, "text_content", None)
                    or getattr(existing_content_object, "caption", "")
                ).strip()
            )
            if not text_content:
                raise ValueError("Protocol v1 certification requires recoverable submission content.")
            content_object = self.upload_text_content(
                text_content=text_content,
                submitted_by=submission.submitter,
                caption=validate_caption(text_content),
            )
            submission.text_content = content_object.text_content or text_content

        submission.content_hash = content_object.content_hash
        submission.content_id = content_object.content_id
        metadata = dict(content_object.metadata or {})
        metadata.setdefault("submission_id", submission.submission_id)
        content_object.metadata = metadata
        return content_object

    def promote_submission_content_for_protocol_v1(self, submission):
        return self._promote_submission_content_for_protocol_v1(submission)

    def _store_submission_content(self, submission, image_path="", text_content=""):
        if image_path:
            with open(image_path, "rb") as image_file:
                image_bytes = image_file.read()
            stored_content = store_content_bytes(
                submission.content_hash,
                image_bytes,
                mime_type=guess_mime_type(os.path.basename(image_path), "image/jpeg"),
                original_filename=os.path.basename(image_path),
                data_dir=self.storage.data_dir,
                hash_scheme=HASH_SCHEME_LEGACY,
            )
            submission.image_path = os.path.abspath(stored_content["path"])
            return stored_content

        normalized_text = (text_content or "").strip()
        if not normalized_text:
            return None

        return store_content_bytes(
            submission.content_hash,
            normalized_text.encode("utf-8"),
            mime_type=TEXT_MIME_TYPE,
            data_dir=self.storage.data_dir,
            hash_scheme=HASH_SCHEME_LEGACY,
        )

    def refresh_content_object_storage_statuses(self):
        return self._content_coordination_service.refresh_storage_statuses(self._content_coordination_state(), self.storage)
    def submit_content(self, image_path="", text_content="", submitter=""):
        """Create a pending content submission without minting a block."""
        return self._content_coordination_service.submit_content(self._content_coordination_state(), self.storage, NETWORK_NAME, image_path, text_content, submitter)
    def get_submission(self, submission_id):
        return self.storage.get_submission(submission_id, self.submissions)

    def get_content_object(self, content_id):
        return self._content_coordination_service.get_content_object(self._content_coordination_state(), self.storage, content_id)
    def get_content_object_by_hash(self, content_hash):
        return self._content_coordination_service.get_content_object_by_hash(self._content_coordination_state(), self.storage, content_hash)
    def list_content_objects(self, status=None):
        return self._content_coordination_service.list_content_objects(self._content_coordination_state(), self.storage, status)
    @staticmethod
    def _block_field(block, field_name, default=None):
        if isinstance(block, dict):
            return block.get(field_name, default)
        return getattr(block, field_name, default)

    @staticmethod
    def is_protocol_v1_block_payload(block) -> bool:
        return Blockchain._block_field(block, "block_version") == PROTOCOL_V1_BLOCK_VERSION

    @staticmethod
    def protocol_v1_network_id() -> str:
        return resolve_network_id(network_name=NETWORK_NAME)

    @staticmethod
    def protocol_v1_lifecycle_policy() -> dict[str, object]:
        return {
            "confirmation_depth": int(PROTOCOL_V1_CONFIRMATION_DEPTH),
            "finality_depth": int(PROTOCOL_V1_FINALITY_DEPTH),
            "finality_model": "operational_depth",
            "finality_scope": "policy_not_bft",
        }

    def get_protocol_v1_block_for_submission(self, submission_id, *, chain=None):
        normalized_submission_id = str(submission_id or "").strip()
        if not normalized_submission_id:
            return None
        for block in chain or self.chain:
            if not self.is_protocol_v1_block_payload(block):
                continue
            if str(self._block_field(block, "submission_id") or "").strip() == normalized_submission_id:
                return block
        return None

    def get_protocol_v1_block_for_certificate(self, certificate_id, *, chain=None):
        normalized_certificate_id = str(certificate_id or "").strip()
        if not normalized_certificate_id:
            return None
        for block in chain or self.chain:
            if not self.is_protocol_v1_block_payload(block):
                continue
            if str(self._block_field(block, "certificate_id") or "").strip() == normalized_certificate_id:
                return block
        return None

    def get_block_chain_state(self, block_or_hash, *, chain=None) -> dict[str, object]:
        policy = self.protocol_v1_lifecycle_policy()
        chain_dicts = self.chain_to_dicts(chain or self.chain)
        target_hash = (
            str(block_or_hash or "").strip()
            if isinstance(block_or_hash, str)
            else str(self._block_field(block_or_hash, "hash") or "").strip()
        )
        state = {
            "accepted": False,
            "block_created": False,
            "block_accepted": False,
            "canonical": False,
            "confirmations": None,
            "confirmed": False,
            "finalized": False,
            "confirmation_depth": policy["confirmation_depth"],
            "finality_depth": policy["finality_depth"],
            "finality_model": policy["finality_model"],
            "finality_scope": policy["finality_scope"],
            "block_hash": target_hash or None,
            "block_height": None,
            "phase": "none",
        }
        if not target_hash:
            return state

        target_block = next(
            (
                block_dict
                for block_dict in chain_dicts
                if str(block_dict.get("hash") or "").strip() == target_hash
            ),
            None,
        )
        if target_block is None:
            return state

        confirmations = int(chain_dicts[-1]["index"]) - int(target_block["index"])
        confirmed = confirmations >= int(policy["confirmation_depth"])
        finalized = confirmations >= int(policy["finality_depth"])
        phase = "canonical"
        if finalized:
            phase = "finalized"
        elif confirmed:
            phase = "confirmed"

        state.update(
            {
                "accepted": True,
                "block_created": True,
                "block_accepted": True,
                "canonical": True,
                "confirmations": confirmations,
                "confirmed": confirmed,
                "finalized": finalized,
                "block_height": int(target_block["index"]),
                "phase": phase,
            }
        )
        return state

    def get_submission_certificate_state(self, submission) -> dict[str, object]:
        certificate = self.get_originality_certificate_for_submission(submission.submission_id)
        if certificate is None:
            return {
                "certificate_status": "missing",
                "certificate_id": None,
                "certificate": None,
                "validation_error": None,
            }
        try:
            validate_certificate_for_submission(certificate, submission, network_name=NETWORK_NAME)
        except ValueError as exc:
            return {
                "certificate_status": "invalid",
                "certificate_id": certificate.certificate_id,
                "certificate": certificate,
                "validation_error": str(exc),
            }
        return {
            "certificate_status": "valid",
            "certificate_id": certificate.certificate_id,
            "certificate": certificate,
            "validation_error": None,
        }

    def get_submission_protocol_v1_lifecycle(self, submission_id) -> dict[str, object]:
        submission = self.get_submission(submission_id)
        if submission is None:
            raise ValueError(f"Submission not found: {submission_id}")

        certificate_state = self.get_submission_certificate_state(submission)
        certificate = certificate_state["certificate"]
        block = self.get_protocol_v1_block_for_submission(submission.submission_id)
        block_state = self.get_block_chain_state(block) if block is not None else self.get_block_chain_state(None)
        rejected = submission.status in {REJECTED, HARD_REJECTED}
        voting = submission.status == PENDING and not rejected and not self.is_submission_voting_locked(submission)
        certified = certificate_state["certificate_status"] == "valid"
        mint_eligible = False
        mint_status = "not_ready"

        if block is not None or submission.status == MINTED:
            mint_status = "minted"
        elif rejected:
            mint_status = "rejected"
        elif submission.mint_blocked:
            mint_status = "blocked"
        elif certified and self.get_protocol_v1_block_for_certificate(certificate.certificate_id) is not None:
            mint_status = "minted"
        elif certified and self._resolve_mintable_submission_certificate(submission) is not None:
            mint_eligible = True
            mint_status = "mint_eligible"
        elif certified:
            mint_status = "certified_unmintable"

        phase = "submitted"
        if block_state["finalized"]:
            phase = "finalized"
        elif block_state["confirmed"]:
            phase = "confirmed"
        elif block_state["canonical"]:
            phase = "canonical"
        elif block_state["block_accepted"]:
            phase = "block-accepted"
        elif mint_eligible:
            phase = "mint-eligible"
        elif certified:
            phase = "certified"
        elif rejected:
            phase = "rejected"
        elif voting:
            phase = "voting"

        return {
            "phase": phase,
            "submitted": True,
            "voting": voting,
            "rejected": rejected,
            "certified": certified,
            "mint_eligible": mint_eligible,
            "block_created": bool(block_state["block_created"]),
            "block_accepted": bool(block_state["block_accepted"]),
            "canonical": bool(block_state["canonical"]),
            "confirmations": block_state["confirmations"],
            "confirmed": bool(block_state["confirmed"]),
            "finalized": bool(block_state["finalized"]),
            "confirmation_depth": block_state["confirmation_depth"],
            "finality_depth": block_state["finality_depth"],
            "finality_model": block_state["finality_model"],
            "finality_scope": block_state["finality_scope"],
            "certificate_status": certificate_state["certificate_status"],
            "mint_status": mint_status,
            "block_status": block_state["phase"],
            "block_hash": block_state["block_hash"],
            "block_height": block_state["block_height"],
            "queue_present": self.storage.mint_queue_contains(submission.submission_id, self.mint_queue),
        }

    def reconcile_submission_canonical_state(self) -> bool:
        minted_submission_ids = {
            str(self._block_field(block, "submission_id") or "").strip()
            for block in self.chain
            if self.is_protocol_v1_block_payload(block)
            and str(self._block_field(block, "submission_id") or "").strip()
        }
        changed = False
        for submission in self.submissions:
            certificate = self.get_originality_certificate_for_submission(submission.submission_id)
            if submission.submission_id in minted_submission_ids:
                if submission.status != MINTED:
                    submission.status = MINTED
                    changed = True
                if self.storage.mint_queue_contains(submission.submission_id, self.mint_queue):
                    self.mint_queue = [
                        queued_submission_id
                        for queued_submission_id in self.mint_queue
                        if queued_submission_id != submission.submission_id
                    ]
                    changed = True
                continue

            if submission.status == MINTED and certificate is not None:
                restored_status = QUEUED if self.storage.mint_queue_contains(submission.submission_id, self.mint_queue) else APPROVED
                if submission.status != restored_status:
                    submission.status = restored_status
                    changed = True
        return changed

    def recover_block_media_bytes(self, block_or_hash):
        return self._content_coordination_service.recover_block_media_bytes(self.storage, block_or_hash, self.get_block_by_hash)
    def _resolve_protocol_v1_block_media(self, block):
        return self._content_coordination_service.resolve_protocol_v1_block_media(self.storage, block, self.get_block_by_hash)
    def cache_protocol_v1_block_content(self, block, *, submission_id=None):
        if not self.is_protocol_v1_block_payload(block):
            return None

        resolved_media = self._resolve_protocol_v1_block_media(block)
        content_hash = self._block_field(block, "content_hash")
        if not isinstance(content_hash, str) or not content_hash.strip():
            raise ValueError("Protocol v1 blocks must include content_hash.")

        hash_scheme = (
            resolved_media["hash_scheme"]
            if content_hash == resolved_media["content_hash"]
            else HASH_SCHEME_LEGACY
        )
        stored_content = store_content_bytes(
            content_hash,
            resolved_media["stored_bytes"],
            mime_type=resolved_media["mime_type"],
            data_dir=self.storage.data_dir,
            hash_scheme=hash_scheme,
        )
        caption = None
        meme_value = self._block_field(block, "meme")
        if isinstance(meme_value, dict):
            caption = (meme_value.get("text") or "").strip() or None

        content_object = self.register_uploaded_content(
            content_hash=content_hash,
            submitted_by=(
                self._block_field(block, "creator_wallet")
                or self._block_field(block, "miner")
                or "protocol-v1-block"
            ),
            mime_type=stored_content["mime_type"],
            file_size_bytes=stored_content["file_size_bytes"],
            storage_status=stored_content["storage_status"],
            local_path=stored_content["local_path"],
            file_name=stored_content["file_name"],
            caption=caption,
            text_content=resolved_media["text_content"],
            content_type_hint=self._block_field(block, "content_type"),
            byte_hash=stored_content["byte_hash"],
            hash_scheme=hash_scheme,
        )
        metadata = dict(content_object.metadata or {})
        metadata["media_hash"] = resolved_media["content_hash"]
        if submission_id:
            metadata["submission_id"] = submission_id
        content_object.metadata = metadata
        return content_object

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
        return self._content_coordination_service.upload_binary_content(self._content_coordination_state(), self.storage, NETWORK_NAME, file_bytes=file_bytes, submitted_by=submitted_by, mime_type=mime_type, original_filename=original_filename, caption=caption, content_type_hint=content_type_hint)
    def upload_text_content(
        self,
        *,
        text_content,
        submitted_by,
        caption=None,
    ):
        return self._content_coordination_service.upload_text_content(self._content_coordination_state(), self.storage, NETWORK_NAME, text_content=text_content, submitted_by=submitted_by, caption=caption)
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
        return self._submission_originality_service.update_submission_status(self._submission_originality_state(), self.storage, submission_id, new_status)
    def hard_reject_submission(self, submission_id, reason):
        return self._submission_originality_service.hard_reject_submission(self._submission_originality_state(), self.storage, submission_id, reason)
    def record_vote(self, voter, submission_id=None, created_at=None):
        return self._submission_originality_service.record_vote(self._submission_originality_state(), voter, submission_id, created_at)
    def cast_submission_vote(self, submission_id, voter, vote_type, created_at=None):
        return self._submission_originality_service.cast_submission_vote(self._submission_originality_state(), self.storage, submission_id, voter, vote_type, created_at)
    def get_submission_votes(self, submission_id):
        return self._submission_originality_service.get_submission_votes(self._submission_originality_state(), self.storage, submission_id)
    def is_submission_voting_locked(self, submission):
        return self._submission_originality_service.is_submission_voting_locked(self._submission_originality_state(), self.storage, submission)
    def get_originality_certificate(self, certificate_id):
        return self._submission_originality_service.get_certificate(self._submission_originality_state(), self.storage, certificate_id)
    def get_originality_certificate_for_submission(self, submission_id):
        return self._submission_originality_service.get_certificate_for_submission(self._submission_originality_state(), self.storage, submission_id)
    def link_certificates_to_submissions(self):
        return self._submission_originality_service.link_certificates_to_submissions(self._submission_originality_state(), self.storage)
    def link_content_objects_to_submissions(self):
        return self._content_coordination_service.link_content_objects_to_submissions(self._content_coordination_state(), self.storage, NETWORK_NAME)
    def certificate_block_metadata(self, certificate):
        submission = self.get_submission(certificate.submission_id)
        content_object = self.get_content_object_by_hash(certificate.content_hash)
        metadata = {
            "submission_id": certificate.submission_id,
            "certificate_id": certificate.certificate_id,
            "content_hash": certificate.content_hash,
            "content_id": (
                certificate.content_id
                or (submission.content_id if submission is not None else None)
                or (content_object.content_id if content_object is not None else None)
            ),
            "creator_wallet": certificate.creator_wallet,
            "vote_hash": certificate.vote_hash,
            "approval_percentage": certificate.approval_percentage,
            "decisive_vote_total": certificate.decisive_vote_total,
            "minimum_votes_required": certificate.minimum_votes_required,
            "approved_at": certificate.approved_at,
            "originality_score": certificate.originality_score,
        }
        if content_object is not None:
            metadata["content_type"] = content_object.content_type
            metadata["mime_type"] = content_object.mime_type
        return metadata

    def _normalize_native_wallet_identity(self, wallet_address):
        return self._native_ledger_service.normalize_wallet_identity(wallet_address)

    def resolve_meme_reward_recipient(self, submission, certificate):
        return self._reward_service.resolve_meme_reward_recipient(submission, certificate, self._reward_collaborators())

    def build_meme_reward_metadata(self, submission, certificate, *, minted_at):
        return self._reward_service.build_meme_reward_metadata(submission, certificate, self._reward_collaborators(), minted_at=minted_at)

    _block_voter_rewards = staticmethod(RewardService.block_voter_rewards)
    _reward_record_sort_key = staticmethod(RewardService.reward_record_sort_key)
    _reward_units_from_decimal = staticmethod(RewardService.reward_units_from_decimal)
    _decimal_from_reward_units = staticmethod(RewardService.decimal_from_reward_units)
    _normalize_decimal_value = staticmethod(RewardService.normalize_decimal_value)
    _reward_id = staticmethod(RewardService.reward_id)

    def _reward_units_from_amount_string(self, amount, *, allow_zero=True):
        return self._reward_service.reward_units_from_amount_string(amount, allow_zero=allow_zero)

    def _normalize_reward_amount(self, amount):
        return self._reward_service.normalize_reward_amount(amount)

    def _build_creator_reward_record(self, block):
        return self._reward_service.build_creator_reward_record(block, self._reward_collaborators())

    def _build_voter_reward_record(self, reward_entry, block):
        return self._reward_service.build_voter_reward_record(reward_entry, block, self._reward_collaborators())

    def _all_reward_records(self):
        return self._reward_service.all_reward_records(self._reward_state(), self._reward_collaborators())

    def _get_reward_record(self, reward_id):
        return next((record for record in self._all_reward_records() if record.get("reward_id") == reward_id), None)

    def _get_settled_voter_reward_ids(self, *, chain=None):
        state = RewardState(chain if chain is not None else self.chain, self.submissions, self.reward_pool, self._reward_state().config)
        return self._reward_service.settled_voter_reward_ids(state)

    def _block_reward_transactions(self, block):
        transactions = block.get("transactions", []) if isinstance(block, dict) else getattr(block, "transactions", [])
        return [transaction.to_dict() if hasattr(transaction, "to_dict") else dict(transaction) for transaction in transactions if (transaction.get("sender") if isinstance(transaction, dict) else getattr(transaction, "sender", None)) == "REWARD_POOL"]

    def _build_reward_transaction_key(self, recipient, amount):
        wallet = self._normalize_native_wallet_identity(recipient)
        if wallet is None:
            raise ValueError("Reward recipient is invalid.")
        return wallet, self._reward_units_from_amount_string(amount, allow_zero=False)

    def _expected_voter_reward_records_by_id(self, submission_id):
        plan = self.build_submission_voter_reward_plan(submission_id)
        return {str(record.get("reward_id")): record for record in plan.get("reward_records", []) if plan.get("eligible") and record.get("reward_id")}

    def _decision_finalized_at_for_submission(self, submission, vote_summary, *, now=None):
        return self._reward_service.decision_finalized_at(submission, vote_summary, self._reward_collaborators(), now=now)

    def get_submission_reward_decision(self, submission_id, *, now=None):
        return self._reward_service.get_submission_reward_decision(submission_id, self._reward_collaborators(), now=now)

    def _eligible_voter_reward_wallets(self, reward_decision):
        votes, excluded = self._reward_service.eligible_voter_reward_wallets(reward_decision, self._reward_collaborators())
        self._last_reward_excluded_voters = excluded
        return votes

    def build_submission_voter_reward_plan(self, submission_id, *, now=None):
        return self._reward_service.build_submission_voter_reward_plan(self._reward_state(), submission_id, self._reward_collaborators(), now=now)

    def _due_voter_reward_records(self):
        return self._reward_service.due_voter_reward_records(self._reward_state(), self._reward_collaborators())

    def _priority_voter_reward_records_for_submission(self, submission_id):
        plan = self.build_submission_voter_reward_plan(submission_id)
        return [] if not plan.get("eligible") or plan.get("final_decision") != VOTER_REWARD_APPROVAL_SIDE else [record for record in plan["reward_records"] if record.get("reward_id") not in self._get_settled_voter_reward_ids()]

    def _select_voter_reward_records_for_block(self, *, prioritized_submission_id=None, reward_pool_balance=None):
        return self._reward_service.select_voter_reward_records_for_block(self._reward_state(), self._reward_collaborators(), prioritized_submission_id=prioritized_submission_id, reward_pool_balance=reward_pool_balance)

    def get_submission_voter_reward_summary(self, submission_id, *, now=None):
        return self._reward_service.get_submission_voter_reward_summary(self._reward_state(), submission_id, self._reward_collaborators(), now=now)

    def get_reward_records_for_wallet(self, wallet_address):
        return self._reward_service.get_reward_records_for_wallet(self._reward_state(), wallet_address, self._reward_collaborators())
    def create_signed_transfer_intent(self, *, from_address, to_address, amount, fee, memo, network, transaction_version=None, protocol_version=None, network_id=None, signature_scheme, signature, signed_message_hash, signed_message, transfer_nonce, transaction_timestamp=None, signed_at, status="signed_pending", created_at=None):
        return self._native_ledger_service.create_signed_transfer_intent(self._native_ledger_state(), self.storage, from_address=from_address, to_address=to_address, amount=amount, fee=fee, memo=memo, network=network, transaction_version=transaction_version, protocol_version=protocol_version, network_id=network_id, signature_scheme=signature_scheme, signature=signature, signed_message_hash=signed_message_hash, signed_message=signed_message, transfer_nonce=transfer_nonce, transaction_timestamp=transaction_timestamp, signed_at=signed_at, status=status, created_at=created_at)

    def get_transfer_intent(self, transfer_id): return self._native_ledger_service.get_transfer_intent(self._native_ledger_state(), self.storage, transfer_id)
    def get_transfer_intent_by_tx_id(self, tx_id): return self._native_ledger_service.get_transfer_intent_by_tx_id(self._native_ledger_state(), tx_id)
    def get_native_transaction(self, tx_id): return self._native_ledger_service.get_native_transaction(self._native_ledger_state(), self.storage, tx_id)

    def _wallet_matches_submission(self, submission, normalized_wallet):
        return any(self._normalize_native_wallet_identity(candidate) == normalized_wallet for candidate in (getattr(submission, "creator_wallet_address", None), getattr(submission, "submitter", None)))

    def _wallet_matches_vote(self, vote, normalized_wallet):
        return any(self._normalize_native_wallet_identity(candidate) == normalized_wallet for candidate in (vote.get("voter_wallet_address"), vote.get("voter")))

    def count_votes_by_wallet_since(self, wallet_address, since_timestamp):
        wallet = self._normalize_native_wallet_identity(wallet_address)
        return 0 if wallet is None else sum(1 for vote in self.votes if (_coerce_timestamp(vote.get("created_at")) or 0) >= float(since_timestamp) and self._wallet_matches_vote(vote, wallet))

    def get_account_activity_summary(self, wallet_address, *, now=None):
        wallet = self._normalize_native_wallet_identity(wallet_address)
        if wallet is None:
            return {"wallet_address": str(wallet_address or "").strip(), "normalized_wallet_address": None, "exists": False, "first_activity_at": None, "account_age_seconds": 0, "submission_count": 0, "vote_count": 0, "reward_count": 0, "settled_transfer_count": 0, "settled_balance_zoid": "0"}
        submissions = [item for item in self.submissions if self._wallet_matches_submission(item, wallet)]; votes = [item for item in self.votes if self._wallet_matches_vote(item, wallet)]; rewards = self.get_reward_records_for_wallet(wallet); transactions = self.get_native_transactions_for_wallet(wallet)
        timestamps = [_coerce_timestamp(getattr(item, "created_at", None)) for item in submissions] + [_coerce_timestamp(item.get("created_at")) for item in votes] + [_coerce_timestamp(item.get("minted_at")) for item in rewards] + [_coerce_timestamp(item.get("created_at") or item.get("updated_at") or item.get("timestamp")) for item in transactions]
        timestamps = [item for item in timestamps if item is not None]; first = min(timestamps) if timestamps else None; balance = self.get_native_balance_snapshot(wallet)["final_balance"]
        return {"wallet_address": wallet, "normalized_wallet_address": wallet, "exists": bool(timestamps) or Decimal(balance) > Decimal("0"), "first_activity_at": first, "account_age_seconds": max(0, int(float(now if now is not None else time.time()) - first)) if first is not None else 0, "submission_count": len(submissions), "vote_count": len(votes), "reward_count": len(rewards), "settled_transfer_count": sum(1 for item in transactions if str(item.get("status") or "").strip().lower() == "settled"), "settled_balance_zoid": balance}

    def get_transfer_intents_for_wallet(self, wallet_address): return self._native_ledger_service.get_transfer_intents_for_wallet(self._native_ledger_state(), wallet_address)
    def get_native_transactions_for_wallet(self, wallet_address): return self._native_ledger_service.get_native_transactions_for_wallet(self._native_ledger_state(), wallet_address)
    _native_mempool_eligible_statuses = staticmethod(NativeLedgerService.native_mempool_eligible_statuses)
    _native_ineligible_mempool_statuses = staticmethod(NativeLedgerService.native_ineligible_mempool_statuses)
    _native_mempool_sort_key = staticmethod(NativeLedgerService.native_mempool_sort_key)
    _native_finalized_statuses = staticmethod(NativeLedgerService.native_finalized_statuses)
    _native_block_candidate_statuses = staticmethod(NativeLedgerService.native_block_candidate_statuses)
    _native_block_sort_key = staticmethod(NativeLedgerService.native_block_sort_key)
    _serialize_native_transaction_for_block = staticmethod(NativeLedgerService.serialize_native_transaction_for_block)
    _compute_block_native_transactions_hash = staticmethod(NativeLedgerService.compute_block_native_transactions_hash)
    _block_native_transactions = staticmethod(NativeLedgerService.block_native_transactions)
    _native_nonce_used_statuses = staticmethod(NativeLedgerService.native_nonce_used_statuses)
    _native_nonce_reserved_statuses = staticmethod(NativeLedgerService.native_nonce_reserved_statuses)
    _native_nonce_unavailable_statuses = classmethod(lambda cls: NativeLedgerService.native_nonce_unavailable_statuses())
    _coerce_native_nonce = staticmethod(NativeLedgerService.coerce_native_nonce)
    _normalize_rejection_reason = staticmethod(NativeLedgerService.normalize_rejection_reason)

    def _find_native_transaction_index(self, tx_id): return self._native_ledger_service.find_native_transaction_index(self._native_ledger_state(), tx_id)
    def _find_transfer_intent_index_by_tx_id(self, tx_id): return self._native_ledger_service.find_transfer_intent_index_by_tx_id(self._native_ledger_state(), tx_id)
    def _update_transfer_intent_status(self, tx_id, *, status, updated_at=None): return self._native_ledger_service.update_transfer_intent_status(self._native_ledger_state(), tx_id, status=status, updated_at=updated_at)
    def _replace_native_transaction(self, transaction): return self._native_ledger_service.replace_native_transaction(self._native_ledger_state(), transaction)
    def discard_native_transaction(self, tx_id): return self._native_ledger_service.discard_native_transaction(self._native_ledger_state(), tx_id)
    def update_native_transaction_status(self, tx_id, *, status, rejection_reason=None, admitted_at=None, included_block_hash=None, included_block_height=None, settled_at=None, updated_at=None): return self._native_ledger_service.update_native_transaction_status(self._native_ledger_state(), self.storage, tx_id, status=status, rejection_reason=rejection_reason, admitted_at=admitted_at, included_block_hash=included_block_hash, included_block_height=included_block_height, settled_at=settled_at, updated_at=updated_at)
    def record_native_transaction(self, transaction_payload, *, status="signed_pending", created_at=None, updated_at=None): return self._native_ledger_service.record_native_transaction(self._native_ledger_state(), self.storage, transaction_payload, status=status, created_at=created_at, updated_at=updated_at)
    def _native_transaction_sender_matches(self, transaction, normalized_wallet): return self._native_ledger_service.native_transaction_sender_matches(transaction, normalized_wallet)
    def _get_transfer_intent_by_tx_id(self, tx_id): return self.get_transfer_intent_by_tx_id(tx_id)
    def _find_sender_nonce_transaction(self, wallet_address, nonce): return self._native_ledger_service.find_sender_nonce_transaction(self._native_ledger_state(), wallet_address, nonce)
    def get_used_nonces(self, wallet_address): return self._native_ledger_service.get_used_nonces(self._native_ledger_state(), wallet_address)
    def get_reserved_nonces(self, wallet_address): return self._native_ledger_service.get_reserved_nonces(self._native_ledger_state(), wallet_address)
    def get_next_nonce(self, wallet_address): return self._native_ledger_service.get_next_nonce(self._native_ledger_state(), wallet_address)
    def is_nonce_available(self, wallet_address, nonce): return self._native_ledger_service.is_nonce_available(self._native_ledger_state(), wallet_address, nonce)
    def validate_transaction_nonce(self, transaction): return self._native_ledger_service.validate_transaction_nonce(self._native_ledger_state(), transaction)
    def reserve_transaction_nonce(self, transaction): return self._native_ledger_service.reserve_transaction_nonce(self._native_ledger_state(), transaction)
    def get_nonce_state(self, wallet_address): return self._native_ledger_service.get_nonce_state(self._native_ledger_state(), wallet_address)
    def _get_reserved_native_transactions_for_wallet(self, wallet_address, *, exclude_tx_ids=None): return self._native_ledger_service.get_reserved_native_transactions_for_wallet(self._native_ledger_state(), wallet_address, exclude_tx_ids=exclude_tx_ids)
    def _get_settled_native_transaction_records_for_wallet(self, wallet_address, *, chain=None): return self._native_ledger_service.get_settled_native_transaction_records_for_wallet(self._native_ledger_state(), wallet_address, chain=chain)
    def get_chain_native_transaction_ids(self, *, chain=None): return self._native_ledger_service.get_chain_native_transaction_ids(self._native_ledger_state(), chain=chain)
    def get_settled_used_nonces(self, wallet_address, *, chain=None): return self._native_ledger_service.get_settled_used_nonces(self._native_ledger_state(), wallet_address, chain=chain)
    def get_next_settled_nonce(self, wallet_address, *, chain=None): return self._native_ledger_service.get_next_settled_nonce(self._native_ledger_state(), wallet_address, chain=chain)
    def get_next_chain_nonce(self, wallet_address, chain_before_block=None): return self._native_ledger_service.get_next_chain_nonce(self._native_ledger_state(), wallet_address, chain_before_block)
    def calculate_balances_from_chain(self, chain=None): return self._native_ledger_service.calculate_balances_from_chain(self._native_ledger_state(), self.chain_to_dicts, chain=chain, error_type=NativeBlockValidationError)
    def get_final_native_balance_amount(self, wallet_address, *, chain=None): return self._native_ledger_service.get_final_native_balance_amount(self._native_ledger_state(), wallet_address, chain=chain)
    def get_pending_outgoing_balance_amount(self, wallet_address, *, exclude_tx_ids=None): return self._native_ledger_service.get_pending_outgoing_balance_amount(self._native_ledger_state(), wallet_address, exclude_tx_ids=exclude_tx_ids)
    def get_pending_incoming_balance_amount(self, wallet_address, *, exclude_tx_ids=None): return self._native_ledger_service.get_pending_incoming_balance_amount(self._native_ledger_state(), wallet_address, exclude_tx_ids=exclude_tx_ids)
    def get_available_native_balance_amount(self, wallet_address, *, exclude_tx_ids=None): return self._native_ledger_service.get_available_native_balance_amount(self._native_ledger_state(), wallet_address, exclude_tx_ids=exclude_tx_ids)
    def get_native_balance_snapshot(self, wallet_address, *, exclude_tx_ids=None): return self._native_ledger_service.get_native_balance_snapshot(self._native_ledger_state(), wallet_address, exclude_tx_ids=exclude_tx_ids)
    def validate_transaction_balance_sufficiency(self, transaction, *, exclude_tx_id=None): return self._native_ledger_service.validate_transaction_balance_sufficiency(self._native_ledger_state(), transaction, exclude_tx_id=exclude_tx_id)
    def list_mempool_transactions(self): return self._native_mempool_service.list_transactions(self._native_ledger_state())
    def get_mempool_transaction(self, tx_id): return self._native_mempool_service.get_transaction(self._native_ledger_state(), self.storage, tx_id)
    def validate_signed_native_transaction(self, transaction_or_tx_id, *, allowed_statuses=None): return self._native_ledger_service.validate_signed_native_transaction(self._native_ledger_state(), self.storage, transaction_or_tx_id, allowed_statuses=allowed_statuses)
    def validate_transaction_for_mempool(self, transaction_or_tx_id): return self._native_mempool_service.validate_transaction(self._native_ledger_state(), self.storage, transaction_or_tx_id)
    def select_native_transactions_for_block(self, *, max_transactions_per_block=MAX_TRANSACTIONS_PER_BLOCK): return self._native_mempool_service.select_for_block(self._native_ledger_state(), self.storage, self.chain_to_dicts, max_transactions_per_block=max_transactions_per_block, error_type=NativeBlockValidationError)

    @staticmethod
    def _native_block_requires_certificate_context(block_dict) -> bool:
        if not list(block_dict.get("native_transactions", []) or []):
            return False
        fields = ("submission_id", "certificate_id", "content_hash", "creator_wallet", "vote_hash", "approval_percentage", "decisive_vote_total", "minimum_votes_required", "approved_at", "originality_score", "reward_type", "reward_recipient", "reward_amount", "reward_source", "minted_at")
        return all(block_dict.get(field) is not None for field in fields)

    @staticmethod
    def _raise_native_block_validation_error(code, message, **details):
        raise NativeBlockValidationError(code, message, details=details or None)

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
            if (
                self.is_protocol_v1_block_payload(block_dict)
                and validated_transaction.get("transaction_version") != PROTOCOL_V1_NATIVE_TRANSFER_VERSION
            ):
                self._raise_native_block_validation_error(
                    "unsupported_transaction_version",
                    "Protocol v1 blocks cannot include legacy native transactions.",
                    tx_id=tx_id,
                    transaction_index=index,
                )
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
        return self._native_ledger_service.settle_block_native_transactions(self._native_ledger_state(), self.storage, block)

    def reconcile_native_transactions_with_chain(self, *, chain=None):
        return self._native_ledger_service.reconcile_native_transactions_with_chain(self._native_ledger_state(), self.storage, self.chain_to_dicts, chain=chain)

    def admit_transaction_to_mempool(self, tx_id):
        return self._native_mempool_service.admit(self._native_ledger_state(), self.storage, tx_id, now_iso=self._utc_now_iso)

    def revalidate_mempool_transactions(self, *, save=False):
        report = self._native_mempool_service.revalidate(self._native_ledger_state(), self.storage, now_iso=self._utc_now_iso)
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
        return self._submission_originality_service.create_certificate(self._submission_originality_state(), self.storage, submission_id, approved_at=approved_at, network_name=network_name, issuing_node_id=issuing_node_id, allow_pending=allow_pending, promote_content=self._promote_submission_content_for_protocol_v1, save=self.save_blockchain if save else None, voting_threshold=self.get_voting_threshold)
    def evaluate_submission(self, submission_id, automated_originality_passed=None, now=None):
        submission = self.get_submission(submission_id)
        if not submission:
            raise ValueError(f"Submission not found: {submission_id}")

        vote_summary = self.get_submission_votes(submission_id)
        now = now if now is not None else time.time()
        voting_window_expired = now >= submission.created_at + (VOTING_WINDOW_HOURS * 60 * 60)
        minimum_votes = self.get_voting_threshold(now=now)["minimum_votes"]
        minimum_votes_reached = len(vote_summary["votes"]) >= minimum_votes

        result = {
            "submission_id": submission_id,
            "status": submission.status,
            "minimum_votes": minimum_votes,
            "votes_cast": len(vote_summary["votes"]),
            "approval_percentage": vote_summary["approval_percentage"],
            "voting_window_expired": voting_window_expired,
            "minimum_votes_reached": minimum_votes_reached,
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

        if not (voting_window_expired or minimum_votes_reached):
            result["reason"] = "awaiting_votes_or_window"
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
        return self._submission_originality_service.calculate_minimum_votes_required(active_users)
    def get_voting_threshold(self, lookback_days=ACTIVE_USER_LOOKBACK_DAYS, now=None):
        return self._submission_originality_service.get_voting_threshold(self.get_active_users, lookback_days, now)
    def add_to_mint_queue(self, submission_id):
        return self._mint_queue_service.add(self._mint_queue_state(), self.storage, submission_id, self.require_valid_certificate_for_submission)
    def _queue_submission_record(self, submission, *, content_object=None, certificate=None):
        return self._mint_queue_service.record(self.storage, submission, content_object=content_object, certificate=certificate, network_name=NETWORK_NAME, extract_text_func=extract_text)
    def _evaluate_mint_queue_item(self, submission_id):
        return self._mint_queue_service.evaluate(self._mint_queue_state(), self.storage, submission_id, NETWORK_NAME, extract_text)
    def get_mint_queue(self, include_blocked=True, mintable_only=False):
        return self._mint_queue_service.list(self._mint_queue_state(), self.storage, network_name=NETWORK_NAME, include_blocked=include_blocked, mintable_only=mintable_only, extract_text_func=extract_text)
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
            self.reconcile_submission_canonical_state()
            if self.get_protocol_v1_block_for_submission(submission.submission_id) is None:
                if submission.submission_id in self.mint_queue:
                    self.mint_queue = [
                        queued_submission_id
                        for queued_submission_id in self.mint_queue
                        if queued_submission_id != submission.submission_id
                    ]
                if submission.status != MINTED:
                    submission.status = MINTED
            self.save_blockchain()
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
            if record.get("mint_block_reason") in {
                "content_metadata_missing",
                "content_payload_missing",
                "legacy_unverifiable_content",
                "content_not_verified",
            }:
                submission = self.get_submission(submission_id)
                certificate = self._resolve_mintable_submission_certificate(submission)
                if certificate is not None:
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
            if record.get("mint_block_reason") in {
                "content_metadata_missing",
                "content_payload_missing",
                "legacy_unverifiable_content",
                "content_not_verified",
            }:
                certificate = self._resolve_mintable_submission_certificate(submission)
                if certificate is not None:
                    return self._mint_submission_record(
                        submission,
                        certificate,
                        miner=miner,
                        max_block_size_kb=max_block_size_kb,
                        validate_meme=validate_meme,
                    )
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
        return self._mint_queue_service.block(self._mint_queue_state(), self.storage, submission_id, reason, notes, blocked_by)
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
        return self._mint_queue_service.unblock(self._mint_queue_state(), self.storage, submission_id)
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
        return self._mint_queue_service.remove_invalid(self._mint_queue_state(), self.storage, self.require_valid_certificate_for_submission)
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

    def validate_candidate_block_for_local_acceptance(self, block, *, current_chain=None):
        working_chain = current_chain or self.chain
        latest_block = working_chain[-1]
        if block.previous_hash != latest_block.hash:
            raise ValueError("Block does not extend the local chain tip.")
        if block.index != latest_block.index + 1:
            raise ValueError("Block index must extend the local chain by one.")

        calculated_hash = block.calculate_hash()
        if block.hash != calculated_hash:
            raise ValueError("Block hash does not match block contents.")

        block_dict = block.to_dict()
        expected_hash = self.calculate_hash_from_dict(block_dict)
        if block.hash != expected_hash:
            raise ValueError("Block hash does not match existing block validation.")

        for transaction in block.transactions:
            if not transaction.is_valid():
                raise ValueError("Block contains an invalid transaction.")
            if transaction.sender not in {"GENESIS", "REWARD_POOL"} and not self.validate_transaction(transaction):
                raise ValueError("Block contains an invalid transaction.")

        prior_chain = self.chain_to_dicts(working_chain)
        self.validate_block_with_native_transactions(block_dict, prior_chain=prior_chain)
        candidate_chain = prior_chain + [block_dict]
        if not self.is_chain_valid(candidate_chain):
            raise ValueError("Block failed chain validation.")
        return True

    def build_block_candidate(
        self,
        image_path,
        text_content=None,
        miner=None,
        max_block_size_kb=500,
        validate_meme=True,
        certificate=None,
        reward_recipient=None,
    ):
        if not self.is_valid_public_key(miner):
            print(f"Debug: Invalid miner public key: {miner}")
            raise ValueError("Invalid public key provided for the miner.")

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

        normalized_text = re.sub(r'[^\w\s]', '', text_content).strip().lower()
        if is_text_payload:
            image_hash = compute_text_content_hash(text_content)
        else:
            image_hash = hash_image(image_path)

        if validate_meme:
            if is_text_payload:
                if normalized_text in self.texts:
                    print(f"Debug: Duplicate text payload detected: '{normalized_text}' already exists.")
                    raise ValueError("This meme has already been submitted.")
            elif image_hash in self.image_hashes and normalized_text in self.texts:
                print(
                    f"Debug: Duplicate meme detected! Image hash {image_hash} and text "
                    f"'{normalized_text}' already exist."
                )
                raise ValueError("This meme has already been submitted.")

        protocol_v1_media = None
        canonical_block_text = text_content
        if certificate is not None:
            if is_text_payload:
                protocol_v1_media = resolve_declared_payload_hash(
                    text_content.encode("utf-8"),
                    TEXT_MIME_TYPE,
                )
                canonical_block_text = protocol_v1_media["text_content"]
            else:
                with open(image_path, "rb") as image_file:
                    protocol_v1_media = resolve_declared_payload_hash(
                        image_file.read(),
                        guessed_mime_type or guess_mime_type(os.path.basename(image_path), "image/jpeg"),
                    )
            declared_content_hash = str(getattr(certificate, "content_hash", "") or "").strip()
            if declared_content_hash != protocol_v1_media["content_hash"]:
                raise ValueError("Certified submission content_hash does not match canonical media bytes.")

        if is_text_payload:
            print("Debug: Encoding text payload for block storage.")
            encoded_payload = (
                protocol_v1_media["stored_bytes"]
                if protocol_v1_media is not None
                else text_content.encode("utf-8")
            )
            meme_encoded = base64.b64encode(encoded_payload).decode("utf-8")
        else:
            if protocol_v1_media is not None:
                print(f"Debug: Encoding image at path {image_path}.")
                meme_encoded = base64.b64encode(protocol_v1_media["stored_bytes"]).decode("utf-8")
            else:
                print(f"Debug: Encoding image at path {image_path}.")
                meme_encoded = self.encode_image(image_path)

        meme_size_kb = len(meme_encoded) / 1024
        text_size_kb = len(text_content.encode()) / 1024

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

        valid_transactions = []
        total_tx_size_kb = 0
        total_miner_tips = 0.0
        candidate_reward_pool = float(self.reward_pool)

        print("Debug: Validating transactions concurrently...")
        with ThreadPoolExecutor() as executor:
            future_to_tx = {executor.submit(self.validate_transaction, tx): tx for tx in self.pending_transactions}
            for future in future_to_tx:
                tx = future_to_tx[future]
                try:
                    if future.result():
                        tip = float(tx.tip or 0)
                        if candidate_reward_pool < (self.initial_reward_pool * 0.25):
                            tip_split = {"miner": 0.25, "reward_pool": 0.75}
                        else:
                            tip_split = {"miner": 0.5, "reward_pool": 0.5}

                        miner_tip_share = tip * tip_split["miner"]
                        reward_pool_tip_share = tip * tip_split["reward_pool"]
                        candidate_reward_pool += reward_pool_tip_share
                        total_miner_tips += miner_tip_share

                        print(f"Debug: Transaction Distribution - Tip Total: {tip:.4f}")
                        print(f"Debug: - Miner gets: {miner_tip_share:.4f}")
                        print(f"Debug: - Reward Pool gets: {reward_pool_tip_share:.4f}")

                        tx_size_kb = len(str(tx)) / 1024
                        total_tx_size_kb += tx_size_kb
                        valid_transactions.append(tx)
                except Exception as e:
                    print(f"Debug: Transaction validation error: {e}")

        total_block_size_kb = meme_size_kb + text_size_kb + total_tx_size_kb + native_tx_size_kb
        if total_block_size_kb > max_block_size_kb:
            print(
                f"Debug: Block size {total_block_size_kb:.2f} KB exceeds max limit of "
                f"{max_block_size_kb} KB. Rejecting block."
            )
            return None

        print(f"Debug: Final block size: {total_block_size_kb:.2f} KB (within limit: {max_block_size_kb} KB)")

        mining_reward = float(MEME_BLOCK_REWARD)
        reward_receiver = reward_recipient or miner
        if reward_receiver not in {"GENESIS", "REWARD_POOL"}:
            normalized_reward_receiver = self._normalize_native_wallet_identity(reward_receiver)
            if normalized_reward_receiver is None:
                raise ValueError("Minting reward recipient is missing or invalid for this submission.")
            reward_receiver = normalized_reward_receiver
        if certificate is not None and (
            self.get_protocol_v1_block_for_submission(certificate.submission_id) is not None
            or self.get_protocol_v1_block_for_certificate(certificate.certificate_id) is not None
        ):
            raise ValueError("Certified submission already minted into a block.")

        voter_reward_plan = (
            self._select_voter_reward_records_for_block(
                prioritized_submission_id=certificate.submission_id,
                reward_pool_balance=candidate_reward_pool,
            )
            if VOTER_REWARDS_ENABLED and certificate is not None
            else {"selected": [], "skipped": []}
        )
        total_voter_reward_amount = sum(
            float(reward_record["reward_amount"])
            for reward_record in voter_reward_plan["selected"]
        )
        if candidate_reward_pool < (mining_reward + total_voter_reward_amount):
            print("Error: Insufficient funds in the reward pool.")
            return None

        voter_reward_transactions = [
            Transaction("REWARD_POOL", reward_record["reward_recipient"], float(reward_record["reward_amount"]))
            for reward_record in voter_reward_plan["selected"]
        ]
        reward_transaction = Transaction("REWARD_POOL", reward_receiver, mining_reward)

        latest_block = self.get_latest_block()
        minted_at = time.time()
        reward_metadata = {}
        if certificate is not None:
            certificate_submission = self.get_submission(certificate.submission_id)
            if certificate_submission is None:
                raise ValueError(f"Submission not found: {certificate.submission_id}")
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
            meme={"encoded_image": meme_encoded, "text": canonical_block_text},
            miner=miner,
            block_version=PROTOCOL_V1_BLOCK_VERSION if certificate is not None else None,
            network_id=self.protocol_v1_network_id() if certificate is not None else None,
            media_hash=protocol_v1_media["content_hash"] if protocol_v1_media is not None else None,
            media_bytes=protocol_v1_media["stored_bytes"] if protocol_v1_media is not None else None,
            native_transactions=native_transactions_for_block,
            transaction_ids=native_transaction_plan["transaction_ids"],
            transaction_count=native_transaction_plan["transaction_count"],
            transactions_hash=native_transaction_plan["transactions_hash"],
            **(self.certificate_block_metadata(certificate) if certificate else {}),
            **reward_metadata,
            voter_rewards=voter_reward_plan["selected"],
        )
        if certificate is not None:
            new_block.reward_type = "meme_mining_reward"
            new_block.reward_recipient = reward_transaction.recipient
            new_block.reward_amount = mining_reward
            new_block.reward_source = "reward_pool"
            new_block.minted_at = minted_at
            new_block.voter_rewards = list(voter_reward_plan["selected"])
            new_block.hash = new_block.calculate_hash()

        return {
            "block": new_block,
            "candidate_type": "protocol_v1" if certificate is not None else "legacy",
            "image_path": image_path,
            "text_content": text_content,
            "normalized_text": normalized_text,
            "image_hash": image_hash,
            "total_block_size_kb": total_block_size_kb,
            "total_miner_tips": total_miner_tips,
            "valid_transactions": valid_transactions,
            "native_transaction_plan": native_transaction_plan,
        }

    def accept_block_candidate(self, candidate):
        if candidate is None:
            return False

        new_block = candidate["block"]
        self.validate_candidate_block_for_local_acceptance(new_block, current_chain=self.chain)

        total_miner_tips = float(candidate.get("total_miner_tips") or 0)
        miner = new_block.miner
        if miner in self.wallets:
            current_balance = self.get_balance(miner)
            updated_balance = current_balance + total_miner_tips
            print(f"Debug: Before crediting miner {miner}: {current_balance:.4f} {COIN_NAME}")
            print(f"Debug: Miner earned: {total_miner_tips:.4f} {COIN_NAME}")
            self.wallets[miner].stored_balance = updated_balance
            print(f"Debug: After crediting miner {miner}: {self.wallets[miner].stored_balance:.4f} {COIN_NAME}")
        else:
            print(f"Debug: WARNING! Miner {miner} not found in registered wallets. Initializing new wallet.")
            self.wallets[miner] = Wallet()
            self.wallets[miner].public_key = miner
            self.wallets[miner].private_key = None
            self.wallets[miner].stored_balance = total_miner_tips
            print(f"Debug: New miner wallet created for {miner} with balance: {total_miner_tips:.4f} {COIN_NAME}")

        self.chain.append(new_block)
        self.settle_block_native_transactions(new_block)
        self.pending_transactions = [
            tx for tx in self.pending_transactions
            if tx not in candidate.get("valid_transactions", [])
        ]
        for skipped in candidate.get("native_transaction_plan", {}).get("skipped", []):
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

        print(f"Debug: Caching meme data for image {candidate['image_path']}.")
        self.image_hashes.add(candidate["image_hash"])
        self.texts.append(candidate["normalized_text"])
        self.recompute_reward_pool_balance(chain=self.chain)
        self.save_blockchain()

        print(
            f"Block {new_block.index} added with meme: {candidate['text_content']}. "
            f"Final size: {candidate['total_block_size_kb']:.2f} KB."
        )
        print(f"Miner earned: {total_miner_tips:.4f} {COIN_NAME}.")
        return True

    def add_block(
        self,
        image_path,
        text_content=None,
        miner=None,
        max_block_size_kb=500,
        validate_meme=True,
        certificate=None,
        reward_recipient=None,
    ):
        """
        Add a block with tip distribution, enforce block size limit, and validate memes.
        """
        candidate = self.build_block_candidate(
            image_path=image_path,
            text_content=text_content,
            miner=miner,
            max_block_size_kb=max_block_size_kb,
            validate_meme=validate_meme,
            certificate=certificate,
            reward_recipient=reward_recipient,
        )
        return self.accept_block_candidate(candidate)

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
            "content_id",
            "content_type",
            "mime_type",
            "creator_wallet",
            "vote_hash",
            "approval_percentage",
            "decisive_vote_total",
            "minimum_votes_required",
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

    def validate_protocol_v1_block_payload(self, block_dict):
        if not self.is_protocol_v1_block_payload(block_dict):
            return True

        block_version = block_dict.get("block_version")
        if block_version != PROTOCOL_V1_BLOCK_VERSION:
            self._raise_native_block_validation_error(
                "invalid_block_version",
                "Unsupported Protocol v1 block_version.",
                block_index=block_dict.get("index"),
                block_version=block_version,
            )

        network_id = block_dict.get("network_id")
        expected_network_id = self.protocol_v1_network_id()
        if network_id != expected_network_id:
            self._raise_native_block_validation_error(
                "wrong_network",
                "Protocol v1 block network_id does not match the local network.",
                block_index=block_dict.get("index"),
                network_id=network_id,
                expected_network_id=expected_network_id,
            )

        media_hash = block_dict.get("media_hash")
        if not is_valid_content_hash(media_hash):
            self._raise_native_block_validation_error(
                "invalid_media_hash",
                "Protocol v1 block media_hash must be a 64-character lowercase hexadecimal string.",
                block_index=block_dict.get("index"),
            )

        content_hash = block_dict.get("content_hash")
        if not is_valid_content_hash(content_hash):
            self._raise_native_block_validation_error(
                "invalid_content_hash",
                "Protocol v1 block content_hash must be a 64-character lowercase hexadecimal string.",
                block_index=block_dict.get("index"),
            )

        if block_dict.get("media_bytes") is None:
            self._raise_native_block_validation_error(
                "missing_media_bytes",
                "Protocol v1 blocks must embed immutable media bytes.",
                block_index=block_dict.get("index"),
            )

        try:
            content_type = _validate_content_type(block_dict.get("content_type"))
        except ValueError as exc:
            self._raise_native_block_validation_error(
                "invalid_content_metadata",
                str(exc),
                block_index=block_dict.get("index"),
            )

        try:
            resolved_media = self._resolve_protocol_v1_block_media(block_dict)
        except (UnicodeDecodeError, ValueError) as exc:
            self._raise_native_block_validation_error(
                "invalid_embedded_media",
                str(exc),
                block_index=block_dict.get("index"),
            )

        if media_hash != resolved_media["content_hash"]:
            self._raise_native_block_validation_error(
                "media_hash_mismatch",
                "Protocol v1 block media_hash does not match embedded media bytes.",
                block_index=block_dict.get("index"),
                media_hash=media_hash,
                actual_media_hash=resolved_media["content_hash"],
            )
        if content_hash != resolved_media["content_hash"]:
            self._raise_native_block_validation_error(
                "content_hash_mismatch",
                "Protocol v1 block content_hash does not match embedded media bytes.",
                block_index=block_dict.get("index"),
                content_hash=content_hash,
                actual_content_hash=resolved_media["content_hash"],
            )

        if resolved_media["mime_type"] == TEXT_MIME_TYPE and content_type != CONTENT_TYPE_TEXT:
            self._raise_native_block_validation_error(
                "content_type_mismatch",
                "Protocol v1 text blocks must declare content_type='text'.",
                block_index=block_dict.get("index"),
            )
        if resolved_media["mime_type"] != TEXT_MIME_TYPE and content_type not in {CONTENT_TYPE_IMAGE, CONTENT_TYPE_MIXED}:
            self._raise_native_block_validation_error(
                "content_type_mismatch",
                "Protocol v1 binary blocks must declare content_type='image' or 'mixed'.",
                block_index=block_dict.get("index"),
            )

        return True

    def validate_block_native_transaction_metadata(self, block_dict, *, prior_chain=None):
        self.validate_block_native_transactions(block_dict, prior_chain=prior_chain)
        return True

    def validate_block_with_native_transactions(self, block_dict, *, prior_chain=None):
        self.validate_protocol_v1_block_payload(block_dict)
        self.validate_block_certificate_metadata(block_dict, prior_chain=prior_chain)
        self.validate_block_native_transactions(block_dict, prior_chain=prior_chain)
        return True

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
        if certificate.content_hash != metadata["content_hash"]:
            self._raise_native_block_validation_error(
                "content_hash_mismatch",
                "Block certificate content_hash does not match block content_hash.",
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
            if metadata["content_hash"] != submission.content_hash:
                self._raise_native_block_validation_error(
                    "content_hash_mismatch",
                    "Block content_hash does not match submission.",
                    submission_id=metadata["submission_id"],
                )
            if metadata.get("content_id") is not None and metadata["content_id"] != submission.content_id:
                self._raise_native_block_validation_error(
                    "content_id_mismatch",
                    "Block content_id does not match submission.",
                    submission_id=metadata["submission_id"],
                )

        for field_name in required_fields:
            certificate_value = getattr(certificate, field_name)
            if metadata[field_name] != certificate_value:
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

        content_object = self.get_content_object_by_hash(metadata["content_hash"])
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
                        "content_hash_mismatch",
                        "Verified local content file does not match block content_hash.",
                        submission_id=metadata["submission_id"],
                    )

        return True

    def is_chain_valid(self, chain):
        """Validate a given chain."""
        chain_dicts = self.chain_to_dicts(chain)
        if not chain_dicts:
            return False

        try:
            self.validate_canonical_public_testnet_v1_genesis(chain_dicts[0])
        except GenesisValidationError as exc:
            print(f"Debug: Genesis validation failed - {exc}")
            return False

        for i in range(1, len(chain_dicts)):
            current_block = chain_dicts[i]
            previous_block = chain_dicts[i - 1]

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
            total_deduction = transaction.amount + transaction.tip  # Ã¢Å“â€¦ Only deduct amount + tip (NO FEE)
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
            total_deduction = transaction.amount + transaction.tip  # Ã¢Å“â€¦ Only deduct amount + tip (NO FEE)
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
        return [block.to_dict() for block in self.chain]
    
    def replace_chain(self, new_chain):
        """Replace the current chain only when the originality fork-choice rule prefers it."""
        comparison = self.compare_chains_by_originality(self.chain, new_chain)
        if comparison["decision"] == "replace_with_candidate":
            self.chain = new_chain
            self.recompute_reward_pool_balance(chain=self.chain)
            self.reconcile_submission_canonical_state()
            self.reconcile_native_transactions_with_chain(chain=self.chain)
            print(f"Debug: Replaced local chain: {comparison['reason']}.")
            return True
        print(f"Debug: Received chain not selected: {comparison['reason']}.")
        return False
    
    def calculate_hash_from_dict(self, block_dict):
        """Calculate the hash for a block dictionary."""
        if block_dict.get("genesis_version") is not None:
            validate_public_testnet_v1_genesis_record(block_dict)
            return self.public_testnet_v1_genesis_hash()
        if self.is_protocol_v1_block_payload(block_dict):
            return Block.calculate_hash_v1_from_dict(block_dict)
        return Block.from_dict(block_dict).calculate_hash()
    
    def is_valid_public_key(self, public_key):
        """Check if the given public key is valid."""
        if is_valid_ethereum_address(str(public_key or "").strip()):
            return True
        if public_key in self.wallets:
            return True
        print(f"Debug: Invalid public key: {public_key}")
        return False
