# Import statements
import os
import hashlib
import math
import time
import base64
import secrets
from PIL import Image
import imagehash
import pytesseract
from block import Block, PROTOCOL_V1_BLOCK_VERSION
from transaction import Transaction
from wallet import Wallet
from utils import extract_text
import json
from copy import deepcopy
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
    PUBLIC_TESTNET_V1_VALIDATOR_ADDRESSES,
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
from protocol_v1_originality import calculate_signed_vote_identity, MILESTONE5_CERTIFICATE_V3_VERSION
from originality_certificate import OriginalityCertificate, validate_certificate_for_submission, validate_certificate_v3_vote_record
from originality import (
    CERTIFICATE_EVIDENCE_PROFILE,
    EXACT_MINTED_CONTENT_DUPLICATE,
    FLAGGED_FOR_REVIEW,
    HARD_REJECT,
    ORIGINALITY_RULE_VERSION,
    PASS as ORIGINALITY_PASS,
    OriginalityPipeline,
    canonical_minted_media_features,
    validate_originality_evidence,
)
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
    detect_mime_type_from_bytes,
    ensure_content_storage_dir,
    guess_mime_type,
    load_content_bytes,
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
    build_protocol_v1_native_transfer_message,
    looks_like_protocol_v1_native_transfer_message,
    resolve_protocol_v1_network_id,
)
from storage import StaleCanonicalHeadError, StorageUniquenessError, canonical_head_identity, create_storage_backend
from protocol_v1 import PROTOCOL_VERSION, resolve_network_id
from milestone5_policy import APPROVAL_THRESHOLD_BPS, ESTABLISHED_MAX_VOTES_PER_EPOCH, MIN_ESTABLISHED_VOTES, MIN_VALID_VOTES, PROBATION_MAX_VOTES_PER_EPOCH, REVIEW_EPOCH_BLOCKS, REVIEWER_POLICY_VERSION, REPUTATION_RULE_VERSION, bootstrap_established_reviewers
from protocol_v1_genesis import (
    GenesisValidationError,
    PUBLIC_TESTNET_V1_INITIAL_REWARD_POOL,
    PUBLIC_TESTNET_V1_TOTAL_SUPPLY,
    canonical_public_testnet_v1_genesis_hash,
    canonical_public_testnet_v1_genesis_record,
    validate_public_testnet_v1_genesis_record,
)
from validators import is_valid_ethereum_address, is_valid_public_key, is_valid_user_wallet_identity
from wallet_auth import hash_wallet_message, normalize_wallet_address
from reviewer_reputation import (
    CREATOR_SELF_VOTE,
    SIGNED_VOTE_EQUIVOCATION,
    VOTE_DURING_COOLDOWN,
    VOTE_DURING_SUSPENSION,
    ReviewerReputationService,
    build_offense_evidence,
)
from access_control import access_decision_for_wallet, generate_access_code, hash_access_code, normalize_email, normalize_handle, normalize_text_field, utc_now_iso
from services import AccessAdminService, AccessAdminState, BlockProductionCollaborators, BlockProductionService, BlockProductionState, BlockValidationCollaborators, BlockValidationService, CanonicalReorgError, CanonicalReorgService, ContentCoordinationService, ContentCoordinationState, FeedbackService, FeedbackState, FinalityAttestationError, FinalityPolicy, FinalityService, ForkChoiceCollaborators, ForkChoiceService, LifecycleTimingRecorder, MintQueueService, MintQueueState, NativeBlockValidationError, NativeLedgerService, NativeLedgerState, NativeMempoolService, RewardCollaborators, RewardService, RewardState, ReviewerEligibilityService, SubmissionOriginalityService, SubmissionOriginalityState, build_native_transaction_outbox_records, normalize_validator_set

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
        validator_set=None,
        lifecycle_timing=None,
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
        self.originality_evidence = []  # Immutable current pre-vote evidence projection
        self.access_requests = []  # Controlled-testnet access requests
        self.access_accounts = []  # Approved access accounts
        self.wallet_bindings = []  # Wallet-to-access-account bindings
        self.allowlist_entries = []  # Operator-managed beta overrides
        self.override_requests = []  # User-submitted beta override requests
        self.feedback_records = []  # In-app beta feedback records
        self.audit_logs = []  # Persistent admin audit trail
        self.finality_attestations = []  # Valid canonical validator attestations
        self.finalized_blocks = []  # Immutable validator-quorum finality evidence
        self.lifecycle_timing = lifecycle_timing or LifecycleTimingRecorder()
        self.validator_set = normalize_validator_set(
            PUBLIC_TESTNET_V1_VALIDATOR_ADDRESSES if validator_set is None else validator_set
        )
        self._access_admin_service = AccessAdminService()
        self._feedback_service = FeedbackService()
        self._content_coordination_service = ContentCoordinationService()
        self._submission_originality_service = SubmissionOriginalityService()
        self._originality_pipeline = OriginalityPipeline(certificate_consensus=True)
        self._originality_index_cache_head = None
        self._originality_index_cache_records = None
        self._mint_queue_service = MintQueueService()
        self._native_ledger_service = NativeLedgerService()
        self._native_mempool_service = NativeMempoolService(self._native_ledger_service)
        self._reward_service = RewardService()
        self._fork_choice_service = ForkChoiceService()
        self._canonical_reorg_service = CanonicalReorgService()
        self._finality_service = FinalityService()
        self._reviewer_eligibility_service = ReviewerEligibilityService()
        self._block_validation_service = BlockValidationService()
        self._block_production_service = BlockProductionService()
        self._last_reward_excluded_voters = []
        self._last_canonical_reorg_report = None
        self.reward_pool = REWARD_POOL_SUPPLY  # Initial reward pool
        self.initial_reward_pool = self.reward_pool  # Set the initial reward pool value
        self.storage = storage_backend or create_storage_backend()
        self._reviewer_reputation_service = ReviewerReputationService(self.storage)
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
            "originality_evidence": deepcopy(self.originality_evidence),
            "access_requests": self.access_requests,
            "access_accounts": self.access_accounts,
            "wallet_bindings": self.wallet_bindings,
            "allowlist_entries": self.allowlist_entries,
            "override_requests": self.override_requests,
            "feedback_records": self.feedback_records,
            "audit_logs": self.audit_logs,
            "finality_attestations": self.finality_attestations,
            "finalized_blocks": self.finalized_blocks,
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

    def _current_canonical_head(self):
        if not self.chain:
            return {"height": None, "hash": None}
        return {"height": self.chain[-1].index, "hash": self.chain[-1].hash}

    @staticmethod
    def certified_commit_identity(certificate):
        """The immutable certificate ID is the certified-commit replay key."""
        certificate_id = str(getattr(certificate, "certificate_id", "") or "").strip().lower()
        if not certificate_id:
            raise ValueError("Certified commit requires an immutable certificate identity.")
        return certificate_id

    def _prepare_certified_commit_request(self, submission_id, miner):
        submission = self.get_submission(submission_id)
        if submission is None:
            raise ValueError("Submission not found for certified commit.")
        certificate = self.get_originality_certificate_for_submission(submission.submission_id)
        if certificate is None:
            raise ValueError("Certified commit requires an originality certificate.")
        self.validate_originality_certificate(certificate, submission)
        return {
            "commit_identity": self.certified_commit_identity(certificate),
            "submission_id": str(submission.submission_id),
            "certificate_id": str(certificate.certificate_id),
            "content_hash": str(submission.content_hash),
            "content_id": submission.content_id,
            "creator_wallet": str(submission.submitter),
            "miner": str(miner or submission.submitter),
        }

    @staticmethod
    def _committed_certified_blocks(document, request):
        matches = []
        for block in list(document.get("chain", []) or []):
            if not isinstance(block, dict):
                continue
            if (
                str(block.get("submission_id") or "") == request["submission_id"]
                or str(block.get("certificate_id") or "") == request["certificate_id"]
            ):
                matches.append(block)
        return matches

    def _resolve_certified_commit_replay(self, document, request):
        """Return a matching committed block or reject a conflicting reuse."""
        matches = self._committed_certified_blocks(document, request)
        if not matches:
            return None
        if len(matches) != 1:
            raise ValueError("Conflicting replay: canonical state has multiple blocks for one certified commit.")
        block = matches[0]
        expected = {
            "submission_id": request["submission_id"],
            "certificate_id": request["certificate_id"],
            "content_hash": request["content_hash"],
            "creator_wallet": request["creator_wallet"],
            "miner": request["miner"],
        }
        actual = {field: str(block.get(field) or "") for field in expected}
        if actual != expected:
            raise ValueError("Conflicting replay: existing certified block does not match the requested immutable commitment.")
        if request["content_id"] is not None and block.get("content_id") != request["content_id"]:
            raise ValueError("Conflicting replay: existing certified block content ID does not match the request.")
        return block

    def _restore_blockchain_state_document(self, loaded_data):
        """Restore a durable state without running repair or persistence hooks.

        Atomic commitment uses this while holding the storage transaction.  It
        deliberately avoids load-time reconciliation because that would add
        unrequested mutations to the commit boundary.
        """
        existing_wallets = dict(self.wallets)
        existing_submissions = {item.submission_id: item for item in self.submissions}
        existing_certificates = {item.certificate_id: item for item in self.originality_certificates}
        self.chain = [Block.from_dict(block_data) for block_data in loaded_data.get("chain", [])]
        wallets = {}
        for key, data in loaded_data.get("wallets", {}).items():
            restored = Wallet.from_dict(data)
            wallet = existing_wallets.get(key, restored)
            if wallet is not restored:
                wallet.__dict__.update(restored.__dict__)
            wallets[key] = wallet
        self.wallets = wallets
        submissions = []
        for item in loaded_data.get("submissions", []):
            restored = Submission.from_dict(item)
            submission = existing_submissions.get(restored.submission_id, restored)
            if submission is not restored:
                submission.__dict__.update(restored.__dict__)
            submissions.append(submission)
        self.submissions = submissions
        self.content_objects = [ContentObject.from_dict(item) for item in loaded_data.get("content_objects", [])]
        self.mint_queue = list(loaded_data.get("mint_queue", []) or [])
        self.votes = list(loaded_data.get("votes", []) or [])
        native_state = self._restore_native_transaction_state(loaded_data.get("native_transactions", []), loaded_data.get("transfer_intents", []))
        self.transfer_intents = native_state["transfer_intents"]
        self.native_transactions = native_state["native_transactions"]
        certificates = []
        for item in loaded_data.get("originality_certificates", []):
            restored = OriginalityCertificate.from_dict(item)
            certificate = existing_certificates.get(restored.certificate_id, restored)
            if certificate is not restored:
                certificate.__dict__.update(restored.__dict__)
            certificates.append(certificate)
        self.originality_certificates = certificates
        self.originality_evidence = [
            validate_originality_evidence(item)
            for item in loaded_data.get("originality_evidence", []) or []
        ]
        self.access_requests = list(loaded_data.get("access_requests", []) or [])
        self.access_accounts = list(loaded_data.get("access_accounts", []) or [])
        self.wallet_bindings = list(loaded_data.get("wallet_bindings", []) or [])
        self.allowlist_entries = list(loaded_data.get("allowlist_entries", []) or [])
        self.override_requests = list(loaded_data.get("override_requests", []) or [])
        self.feedback_records = list(loaded_data.get("feedback_records", []) or [])
        self.audit_logs = list(loaded_data.get("audit_logs", []) or [])
        self.finality_attestations = list(loaded_data.get("finality_attestations", []) or [])
        self.finalized_blocks = list(loaded_data.get("finalized_blocks", []) or [])
        self._validate_persisted_finality_state()
        self.recompute_reward_pool_balance(chain=self.chain)

    def _commit_fault(self, stage):
        hook = getattr(self, "_atomic_commit_fault_injector", None)
        if hook is not None:
            hook(stage)

    def _reorg_fault(self, stage):
        hook = getattr(self, "_canonical_reorg_fault_injector", None)
        if hook is not None:
            hook(stage)
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

    def _block_validation_collaborators(self):
        return BlockValidationCollaborators(
            chain=self.chain,
            chain_to_dicts=self.chain_to_dicts,
            calculate_balances_from_chain=self.calculate_balances_from_chain,
            validate_signed_native_transaction=self.validate_signed_native_transaction,
            native_transaction_validator=self._native_ledger_service.validation_service,
            is_protocol_v1_block_payload=self.is_protocol_v1_block_payload,
            normalize_wallet_identity=self._normalize_native_wallet_identity,
            coerce_native_nonce=self._coerce_native_nonce,
            get_next_chain_nonce=self.get_next_chain_nonce,
            native_block_sort_key=self._native_block_sort_key,
            normalize_decimal_value=self._normalize_decimal_value,
            compute_native_transactions_hash=self._compute_block_native_transactions_hash,
            block_native_transactions=self._block_native_transactions,
            resolve_protocol_v1_block_media=self._resolve_protocol_v1_block_media,
            protocol_v1_network_id=self.protocol_v1_network_id,
            get_settled_voter_reward_ids=self._get_settled_voter_reward_ids,
            build_reward_transaction_key=self._build_reward_transaction_key,
            expected_voter_reward_records_by_id=self._expected_voter_reward_records_by_id,
            block_reward_transactions=self._block_reward_transactions,
            get_originality_certificate=self.get_originality_certificate,
            validate_originality_certificate=self.validate_originality_certificate,
            get_submission=self.get_submission,
            resolve_meme_reward_recipient=self.resolve_meme_reward_recipient,
            get_content_object_by_hash=self.get_content_object_by_hash,
            verify_content_object_payload=lambda content_object: verify_content_object_payload(content_object, data_dir=self.storage.data_dir),
            calculate_hash_from_dict=self.calculate_hash_from_dict,
            validate_transaction=self.validate_transaction,
            validate_genesis=self.validate_canonical_public_testnet_v1_genesis,
            config={
                "network_name": NETWORK_NAME,
                "meme_block_reward": MEME_BLOCK_REWARD,
                "voter_reward_approval_side": VOTER_REWARD_APPROVAL_SIDE,
                "voter_reward_rejection_side": VOTER_REWARD_REJECTION_SIDE,
            },
        )

    def _block_production_state(self):
        return BlockProductionState(
            self.chain,
            self.pending_transactions,
            self.texts,
            self.image_hashes,
            self.reward_pool,
            self.initial_reward_pool,
        )

    def _block_production_collaborators(self):
        return BlockProductionCollaborators(
            is_valid_public_key=self.is_valid_public_key,
            encode_image=self.encode_image,
            select_native_transactions_for_block=self.select_native_transactions_for_block,
            validate_transaction=self.validate_transaction,
            normalize_wallet_identity=self._normalize_native_wallet_identity,
            get_protocol_v1_block_for_submission=self.get_protocol_v1_block_for_submission,
            get_protocol_v1_block_for_certificate=self.get_protocol_v1_block_for_certificate,
            select_voter_reward_records_for_block=self._select_voter_reward_records_for_block,
            get_submission=self.get_submission,
            build_meme_reward_metadata=self.build_meme_reward_metadata,
            certificate_block_metadata=self.certificate_block_metadata,
            protocol_v1_network_id=self.protocol_v1_network_id,
            config={
                "max_transactions_per_block": MAX_TRANSACTIONS_PER_BLOCK,
                "meme_block_reward": MEME_BLOCK_REWARD,
                "voter_rewards_enabled": VOTER_REWARDS_ENABLED,
            },
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

    # HTTP-facing access/admin application operations.  These keep the Task 6
    # services as the state-transition owner while this facade remains the only
    # persistence coordinator.  The API supplies only already-authenticated
    # actor/request metadata; operation names and audit decisions live here.
    def _access_admin_audit_entry(self, action, context=None, **fields):
        return self.append_audit_log_entry({"action": action, **dict(context or {}), **fields})

    def _persist_access_admin_operation(self, result, *, audit_entries=()):
        self.save_blockchain()
        for entry in audit_entries:
            self.append_audit_log_entry(entry)
            self.save_blockchain()
        return result

    def _record_access_admin_audit(self, action, *, audit_context=None, **fields):
        entry = self.append_audit_log_entry({"action": action, **dict(audit_context or {}), **fields})
        self.save_blockchain()
        return entry

    def record_admin_login_failure_operation(self, *, audit_context=None):
        return self._record_access_admin_audit("admin_login_failure", audit_context=audit_context, result="failure", reason="invalid_admin_credential")

    def record_admin_login_success_operation(self, *, audit_context=None):
        return self._record_access_admin_audit("admin_login_success", audit_context=audit_context)

    def record_admin_logout_operation(self, *, audit_context=None):
        return self._record_access_admin_audit("admin_logout", audit_context=audit_context)

    def get_feedback_for_admin_operation(self, feedback_id, *, audit_context=None):
        self.refresh_access_control_state_from_storage()
        record = self.get_feedback(feedback_id)
        if record is None:
            raise LookupError(f"Feedback not found: {feedback_id}")
        self._record_access_admin_audit("feedback_viewed", audit_context=audit_context, feedback_id=feedback_id)
        return record

    def record_admin_ops_view_operation(self, *, audit_context=None):
        return self._record_access_admin_audit("admin_ops_viewed", audit_context=audit_context)

    def submit_feedback_operation(self, **values):
        self.refresh_access_control_state_from_storage()
        return self._persist_access_admin_operation(self.create_feedback(**values))

    def submit_access_request_operation(self, **values):
        return self._persist_access_admin_operation(self.create_access_request(**values))

    def complete_access_login_operation(self, access_code, *, issue_session):
        self.refresh_access_control_state_from_storage()
        account = self.resolve_access_account_by_invite_code(access_code, include_redeemed=True)
        if account is None:
            raise ValueError("Invalid invite/access code.")
        if not account.get("invite_code_hash"):
            raise RuntimeError("Invite/access code has already been redeemed.")
        if str(account.get("status") or "").strip().lower() != "active":
            raise PermissionError("Access account is not active.")
        session = issue_session(account["access_account_id"])
        self.mark_access_account_login(account["access_account_id"])
        self._persist_access_admin_operation(None)
        return account, session

    def bind_access_wallet_operation(self, access_account_id, wallet_address, *, mark_wallet_bound):
        binding = self.bind_wallet_to_access_account(access_account_id, wallet_address, source="invite_code")
        mark_wallet_bound(wallet_address)
        account = self.get_access_account(access_account_id)
        self._persist_access_admin_operation(None)
        return binding, account

    def submit_override_request_operation(self, *, audit_context=None, **values):
        record = self.create_override_request(**values)
        audit = {"action": "override_request_submitted", **dict(audit_context or {}),
                 "override_request_id": record.get("override_request_id"),
                 "access_account_id": record.get("access_account_id"),
                 "wallet_address": record.get("wallet_address"),
                 "reason": record.get("detected_blocked_reason")}
        return self._persist_access_admin_operation(record, audit_entries=(audit,))

    def approve_access_request_operation(self, request_id, *, reviewed_by="operator", operator_notes=None, max_wallets=1, audit_context=None):
        self.refresh_access_control_state_from_storage()
        account, invite_code = self.approve_access_request(request_id, reviewed_by=reviewed_by, operator_notes=operator_notes, max_wallets=max_wallets)
        request_record = self.get_access_request(request_id)
        audit = {"action": "access_request_approved", **dict(audit_context or {}), "request_id": request_id,
                 "access_account_id": account.get("access_account_id"), "operator_note": operator_notes}
        self._persist_access_admin_operation(None, audit_entries=(audit,))
        return account, invite_code, request_record

    def reject_access_request_operation(self, request_id, *, reviewed_by="operator", operator_notes=None, audit_context=None):
        self.refresh_access_control_state_from_storage()
        record = self.reject_access_request(request_id, reviewed_by=reviewed_by, operator_notes=operator_notes)
        audit = {"action": "access_request_rejected", **dict(audit_context or {}), "request_id": request_id, "operator_note": operator_notes}
        return self._persist_access_admin_operation(record, audit_entries=(audit,))

    def create_access_invite_operation(self, *, name, email, handle=None, notes=None, reviewed_by="operator", operator_notes=None, max_wallets=1, audit_context=None):
        self.refresh_access_control_state_from_storage()
        account, invite_code = self.create_access_invite(name=name, email=email, handle=handle, notes=notes, reviewed_by=reviewed_by, operator_notes=operator_notes, max_wallets=max_wallets)
        audit = {"action": "direct_invite_created", **dict(audit_context or {}), "access_account_id": account.get("access_account_id"), "operator_note": operator_notes}
        self._persist_access_admin_operation(None, audit_entries=(audit,))
        return account, invite_code

    def create_allowlist_entry_operation(self, *, audit_context=None, **values):
        self.refresh_access_control_state_from_storage()
        entry = self.create_allowlist_entry(**values)
        audit = {"action": "allowlist_entry_created", **dict(audit_context or {}), "allowlist_entry_id": entry.get("allowlist_entry_id"),
                 "access_account_id": entry.get("subject_value") if entry.get("subject_type") == "access_account" else None,
                 "wallet_address": entry.get("subject_value") if entry.get("subject_type") == "wallet" else None,
                 "reason": entry.get("scope"), "operator_note": entry.get("reason")}
        return self._persist_access_admin_operation(entry, audit_entries=(audit,))

    def update_allowlist_entry_operation(self, allowlist_entry_id, *, audit_context=None, **values):
        self.refresh_access_control_state_from_storage()
        entry = self.update_allowlist_entry(allowlist_entry_id, **values)
        audit = {"action": "allowlist_entry_updated", **dict(audit_context or {}), "allowlist_entry_id": entry.get("allowlist_entry_id"),
                 "access_account_id": entry.get("subject_value") if entry.get("subject_type") == "access_account" else None,
                 "wallet_address": entry.get("subject_value") if entry.get("subject_type") == "wallet" else None,
                 "reason": entry.get("scope"), "operator_note": entry.get("reason")}
        return self._persist_access_admin_operation(entry, audit_entries=(audit,))

    def revoke_allowlist_entry_operation(self, allowlist_entry_id, *, revoked_reason=None, audit_context=None):
        self.refresh_access_control_state_from_storage()
        entry = self.revoke_allowlist_entry(allowlist_entry_id, revoked_reason=revoked_reason)
        audit = {"action": "allowlist_entry_revoked", **dict(audit_context or {}), "allowlist_entry_id": entry.get("allowlist_entry_id"),
                 "access_account_id": entry.get("subject_value") if entry.get("subject_type") == "access_account" else None,
                 "wallet_address": entry.get("subject_value") if entry.get("subject_type") == "wallet" else None,
                 "reason": entry.get("scope"), "operator_note": revoked_reason}
        return self._persist_access_admin_operation(entry, audit_entries=(audit,))

    def reactivate_allowlist_entry_operation(self, allowlist_entry_id, *, reason=None, audit_context=None):
        self.refresh_access_control_state_from_storage()
        entry = self.reactivate_allowlist_entry(allowlist_entry_id, reason=reason)
        audit = {"action": "allowlist_entry_reactivated", **dict(audit_context or {}), "allowlist_entry_id": entry.get("allowlist_entry_id"),
                 "access_account_id": entry.get("subject_value") if entry.get("subject_type") == "access_account" else None,
                 "wallet_address": entry.get("subject_value") if entry.get("subject_type") == "wallet" else None,
                 "reason": entry.get("scope"), "operator_note": reason}
        return self._persist_access_admin_operation(entry, audit_entries=(audit,))

    def approve_override_request_operation(self, override_request_id, *, reviewed_by="operator", admin_note=None, resolved_scope=None, created_by=None, audit_context=None):
        self.refresh_access_control_state_from_storage()
        record = self.get_override_request(override_request_id)
        if record is None:
            raise LookupError(f"Override request not found: {override_request_id}")
        scope = resolved_scope or record.get("requested_scope")
        subject_type = "wallet" if record.get("wallet_address") else "access_account"
        subject_value = record.get("wallet_address") or record.get("access_account_id")
        if not subject_value:
            normalized_email, normalized_handle = normalize_email(record.get("email")), normalize_handle(record.get("handle"))
            if normalized_email:
                subject_type, subject_value = "email", normalized_email
            elif normalized_handle:
                subject_type, subject_value = "handle", normalized_handle
        if not subject_value:
            raise ValueError("Override request cannot be approved without a wallet, access account, email, or handle.")
        entry = self.create_allowlist_entry(scope=scope, subject_type=subject_type, subject_value=subject_value, reason=admin_note or record.get("reason"), created_by=created_by)
        record = self.update_override_request_status(override_request_id, status="approved", reviewed_by=reviewed_by, admin_note=admin_note, resolved_scope=scope, approved_allowlist_entry_id=entry.get("allowlist_entry_id"))
        common = {**dict(audit_context or {}), "allowlist_entry_id": entry.get("allowlist_entry_id"), "access_account_id": record.get("access_account_id"), "wallet_address": record.get("wallet_address")}
        audits = ({"action": "allowlist_entry_created", **common, "reason": scope, "operator_note": admin_note or record.get("reason")},
                  {"action": "override_request_approved", **common, "override_request_id": override_request_id, "reason": scope, "operator_note": admin_note})
        self._persist_access_admin_operation(None, audit_entries=audits)
        return record, entry

    def reject_override_request_operation(self, override_request_id, *, reviewed_by="operator", admin_note=None, resolved_scope=None, audit_context=None):
        self.refresh_access_control_state_from_storage()
        record = self.update_override_request_status(override_request_id, status="rejected", reviewed_by=reviewed_by, admin_note=admin_note, resolved_scope=resolved_scope)
        audit = {"action": "override_request_rejected", **dict(audit_context or {}), "override_request_id": override_request_id,
                 "access_account_id": record.get("access_account_id"), "wallet_address": record.get("wallet_address"),
                 "reason": resolved_scope or record.get("requested_scope"), "operator_note": admin_note}
        return self._persist_access_admin_operation(record, audit_entries=(audit,))

    def update_feedback_operation(self, feedback_id, *, status=None, priority=None, reviewed_by="operator", admin_note=None, audit_context=None):
        self.refresh_access_control_state_from_storage()
        record = self.get_feedback(feedback_id)
        if record is None:
            raise LookupError(f"Feedback not found: {feedback_id}")
        if status is None and priority is None and not admin_note:
            raise ValueError("At least one feedback update field is required.")
        previous_status, previous_priority = str(record.get("status") or "").strip().lower(), str(record.get("priority") or "").strip().lower()
        if status is not None or priority is not None:
            record = self.update_feedback(feedback_id, status=status, priority=priority, reviewed_by=reviewed_by)
        note = self.add_feedback_admin_note(feedback_id, note=admin_note, created_by=reviewed_by) if admin_note else None
        audits = []
        if status is not None and str(record.get("status") or "").strip().lower() != previous_status:
            audits.append({"action": "feedback_status_changed", **dict(audit_context or {}), "feedback_id": feedback_id, "reason": record.get("status")})
        if priority is not None and str(record.get("priority") or "").strip().lower() != previous_priority:
            audits.append({"action": "feedback_priority_changed", **dict(audit_context or {}), "feedback_id": feedback_id, "reason": record.get("priority")})
        if note:
            audits.append({"action": "feedback_note_added", **dict(audit_context or {}), "feedback_id": feedback_id, "operator_note": note.get("note")})
        self._persist_access_admin_operation(None, audit_entries=audits)
        return record, note

    def update_feedback_status_operation(self, feedback_id, *, status, reviewed_by="operator", audit_context=None):
        return self.update_feedback_operation(feedback_id, status=status, reviewed_by=reviewed_by, audit_context=audit_context)

    def add_feedback_note_operation(self, feedback_id, *, note, created_by="operator", audit_context=None):
        self.refresh_access_control_state_from_storage()
        record = self.get_feedback(feedback_id)
        if record is None:
            raise LookupError(f"Feedback not found: {feedback_id}")
        note_record = self.add_feedback_admin_note(feedback_id, note=note, created_by=created_by)
        audit = {"action": "feedback_note_added", **dict(audit_context or {}), "feedback_id": feedback_id, "operator_note": note_record.get("note")}
        self._persist_access_admin_operation(None, audit_entries=(audit,))
        return record, note_record

    def update_access_account_status_operation(self, access_account_id, status, *, updated_by="operator", audit_context=None):
        self.refresh_access_control_state_from_storage()
        account = self.update_access_account_status(access_account_id, status, updated_by=updated_by)
        action = {"suspended": "access_account_suspended", "active": "access_account_reactivated", "revoked": "access_account_revoked"}.get(status, "access_account_updated")
        audit = {"action": action, **dict(audit_context or {}), "access_account_id": access_account_id}
        return self._persist_access_admin_operation(account, audit_entries=(audit,))

    def revoke_wallet_binding_operation(self, wallet_address, *, revoked_by="operator", audit_context=None):
        self.refresh_access_control_state_from_storage()
        binding = self.revoke_wallet_binding(wallet_address, revoked_by=revoked_by)
        audit = {"action": "wallet_binding_revoked", **dict(audit_context or {}), "wallet_address": wallet_address, "access_account_id": binding.get("access_account_id")}
        return self._persist_access_admin_operation(binding, audit_entries=(audit,))

    # Task 11B content/native application operations.  Each delegates its state
    # transition through the established Task 7/8/9 facade methods and performs
    # exactly one whole-document save after a successful mutation.
    def upload_binary_content_operation(self, **values):
        result = self.upload_binary_content(**values)
        self.save_blockchain()
        return result

    def upload_text_content_operation(self, **values):
        result = self.upload_text_content(**values)
        self.save_blockchain()
        return result

    def _local_native_transaction_outbox_builder(
        self, outcome, *, origin_node_id=None, network_name=None
    ):
        sender_node_id = str(origin_node_id or NODE_ID).strip()
        selected_network = str(network_name or NETWORK_NAME).strip()

        def build(document):
            result = outcome.get("result") or {}
            transaction = result.get("transaction")
            if not isinstance(transaction, dict):
                result_tx_id = str(result.get("tx_id") or "").strip().lower()
                transaction = next(
                    (
                        item
                        for item in document.get("native_transactions", []) or []
                        if str(item.get("tx_id") or "").strip().lower() == result_tx_id
                    ),
                    None,
                )
            if not isinstance(transaction, dict) or transaction.get("status") != "mempool":
                return []
            return build_native_transaction_outbox_records(
                transaction,
                list(document.get("peers", []) or []),
                sender_node_id=sender_node_id,
                network_name=selected_network,
                created_at=transaction.get("admitted_at") or self._utc_now_iso(),
            )

        return build

    def admit_native_transaction_operation(
        self, tx_id, *, origin_node_id=None, network_name=None
    ):
        # If this process already holds the record, fail closed on a corrupted
        # local copy before consulting the durable view.  The locked operation
        # below repeats validation against the durable record for race safety.
        if self.get_native_transaction(tx_id) is not None:
            self.validate_transaction_for_mempool(tx_id)
        outcome = {}

        def mutate(document):
            state = NativeLedgerState(
                document["chain"], document["transfer_intents"], document["native_transactions"]
            )
            outcome["result"] = self._native_mempool_service.admit(
                state, self.storage, tx_id, now_iso=self._utc_now_iso
            )
            return document

        try:
            document = self.storage.atomic_update_blockchain_document(
                mutate,
                outbox_records=self._local_native_transaction_outbox_builder(
                    outcome,
                    origin_node_id=origin_node_id,
                    network_name=network_name,
                ),
            )
        except (ValueError, RuntimeError):
            raise
        except Exception as exc:
            raise RuntimeError("Native transaction admission could not be durably committed.") from exc
        self._publish_durable_native_transaction_state(document)
        return outcome["result"]

    def _publish_durable_native_transaction_state(self, document):
        """Publish only committed native state to this process's memory view."""
        self.transfer_intents = list(document.get("transfer_intents", []) or [])
        self.native_transactions = list(document.get("native_transactions", []) or [])

    def _merge_safe_local_chain_append(self, document):
        """Carry an unsaved local append into an admission transaction safely.

        Test/development callers may stage a funding block before submitting a
        transfer.  Only an append whose durable chain is an exact prefix is
        eligible; a stale node can therefore never replace another node's head.
        """
        durable_chain = list(document.get("chain", []) or [])
        local_chain = self.chain_to_dicts(self.chain)
        if len(local_chain) <= len(durable_chain):
            return
        durable_identity = [(item.get("index"), item.get("hash")) for item in durable_chain]
        local_identity = [(item.get("index"), item.get("hash")) for item in local_chain[:len(durable_chain)]]
        if durable_identity == local_identity:
            document["chain"] = local_chain

    def _admit_signed_transfer_durably(
        self, *, admit_to_mempool, origin_node_id=None, **values
    ):
        outcome = {}

        def mutate(document):
            self._merge_safe_local_chain_append(document)
            state = NativeLedgerState(
                document["chain"], document["transfer_intents"], document["native_transactions"]
            )
            outcome["result"] = self._native_ledger_service.admit_signed_transfer(
                state, self.storage, admit_to_mempool=admit_to_mempool,
                now_iso=self._utc_now_iso(), **values,
            )
            return document

        try:
            document = self.storage.atomic_update_blockchain_document(
                mutate,
                outbox_records=(
                    self._local_native_transaction_outbox_builder(
                        outcome,
                        origin_node_id=origin_node_id,
                        network_name=values.get("network"),
                    )
                    if admit_to_mempool
                    else None
                ),
                copy_document=False,
            )
        except StorageUniquenessError as exc:
            if "outbox" in str(exc).lower():
                raise RuntimeError(
                    "Native transaction propagation intent could not be durably committed."
                ) from exc
            # This is a defensive translation for a database invariant that is
            # also checked under the same admission transaction.
            raise ValueError("Nonce already used or reserved. Refresh and try again.") from exc
        except (ValueError, RuntimeError):
            raise
        except Exception as exc:
            raise RuntimeError("Native transaction admission could not be durably committed.") from exc
        self._publish_durable_native_transaction_state(document)
        result = outcome["result"]
        transaction = self.get_native_transaction(result["transaction"]["tx_id"])
        intent = self.get_transfer_intent_by_tx_id(transaction["tx_id"]) if transaction else None
        if transaction is None or intent is None:
            raise RuntimeError("Committed native transaction could not be published to the local mempool.")
        result["transaction"] = dict(transaction)
        result["transfer_intent"] = dict(intent)
        if result["admission"] is not None:
            result["admission"]["status"] = transaction["status"]
            result["admission"]["admitted_at"] = transaction.get("admitted_at")
        return result

    def admit_received_native_transaction_operation(
        self, transaction_payload, *, received_peer_message=None
    ):
        """Durably admit a peer-ready signed payload through local policy.

        This contains no peer authentication, routing, relay, or delivery
        behavior.  It is the common service boundary for any future transport.
        """
        outcome = {}

        def mutate(document):
            self._merge_safe_local_chain_append(document)
            state = NativeLedgerState(
                document["chain"], document["transfer_intents"], document["native_transactions"]
            )
            outcome["result"] = self._native_ledger_service.admit_received_native_transaction(
                state, self.storage, transaction_payload, now_iso=self._utc_now_iso()
            )
            return document

        try:
            document = self.storage.atomic_update_blockchain_document(
                mutate, received_peer_message=received_peer_message
            )
        except StorageUniquenessError as exc:
            raise ValueError(str(exc)) from exc
        except (ValueError, RuntimeError):
            raise
        except Exception as exc:
            raise RuntimeError("Native transaction admission could not be durably committed.") from exc
        self._publish_durable_native_transaction_state(document)
        return outcome["result"]

    def revalidate_mempool_operation(self):
        return self.revalidate_mempool_transactions(save=True)

    def block_submission_minting_operation(self, submission_id, *, reason, notes=None, blocked_by=None):
        result = self.block_minting_for_submission(submission_id, reason=reason, notes=notes, blocked_by=blocked_by)
        self.save_blockchain()
        return result

    def unblock_submission_minting_operation(self, submission_id):
        result = self.unblock_minting_for_submission(submission_id)
        self.save_blockchain()
        return result

    def mint_submission_operation(self, submission_id, *, miner=None):
        submission = self.get_submission(submission_id)
        if not submission:
            raise ValueError(f"Submission not found: {submission_id}")
        if submission.status == HARD_REJECTED:
            raise ValueError("Hard rejected submissions cannot be minted.")
        minted = self.mint_submission(submission_id, miner=miner, validate_meme=False)
        self.save_blockchain()
        latest_block = self.get_latest_block()
        certificate = self.get_originality_certificate(latest_block.certificate_id) if latest_block.certificate_id else None
        return minted, self.get_submission(submission_id) or submission, latest_block, certificate

    def get_mint_queue_operation(self, *, include_blocked=True, mintable_only=False):
        changed = self.link_certificates_to_submissions()
        for submission in self.storage.list_submissions(self.submissions, status=APPROVED):
            if not self.storage.mint_queue_contains(submission.submission_id, self.mint_queue):
                try:
                    self.add_to_mint_queue(submission.submission_id)
                    changed = True
                except ValueError as exc:
                    if "certificate" not in str(exc).lower():
                        raise
        if changed:
            self.save_blockchain()
        return self.get_mint_queue(include_blocked=include_blocked, mintable_only=mintable_only)

    def evaluate_submission_operation(self, submission_id, *, automated_originality_passed=None):
        submission = self.get_submission(submission_id)
        if not submission:
            raise ValueError(f"Submission not found: {submission_id}")
        if submission.status == HARD_REJECTED:
            raise ValueError("Hard rejected submissions cannot be evaluated.")
        if submission.status != PENDING:
            raise ValueError("Only pending submissions can be evaluated.")
        evaluation = self.evaluate_submission(submission_id, automated_originality_passed=automated_originality_passed)
        queued_submission = None
        certificate = self.get_originality_certificate_for_submission(submission_id)
        if submission.status == APPROVED:
            if not certificate:
                raise ValueError("Approved submission is missing an originality certificate and cannot enter the mint queue.")
            queued_submission = self.add_to_mint_queue(submission_id)
            certificate = self.get_originality_certificate_for_submission(submission_id)
        self.save_blockchain()
        if submission.status in {APPROVED, QUEUED}:
            certificate = self.get_originality_certificate_for_submission(submission_id)
            if not certificate:
                raise ValueError("Originality certificate creation failed: certificate could not be retrieved after approval.")
            submission.certificate_id = certificate.certificate_id
        return evaluation, queued_submission or submission, certificate

    def submit_signed_content_operation(self, *, wallet_address, message, signature, content_hash, content_id, text_content, auth_manager):
        verification = auth_manager.verify_submission_signature(wallet_address=wallet_address, message=message, signature=signature, content_hash=content_hash, content_id=content_id)
        submission = self.submit_existing_content(content_hash=content_hash, content_id=content_id, submitter=wallet_address, text_content=text_content or "")
        submission.creator_wallet_address = wallet_address
        submission.signature_scheme = str(verification["signature_scheme"])
        submission.submission_signature = str(verification["submission_signature"])
        submission.submission_message = str(verification["submission_message"])
        submission.signed_message_hash = str(verification["signed_message_hash"])
        submission.submission_nonce = str(verification["nonce"])
        submission.signed_at = str(verification["signed_at"])
        submission.identity_source = str(verification["identity_source"])
        self.evaluate_prevote_originality(submission.submission_id)
        self.save_blockchain()
        return submission

    def submit_content_operation(self, *, content_hash=None, content_id=None, image_path=None, text_content="", submitter=""):
        if content_hash is not None or content_id is not None:
            submission = self.submit_existing_content(content_hash=content_hash, content_id=content_id, submitter=submitter, text_content=text_content or "")
        else:
            submission = self.submit_content(image_path=image_path or "", text_content=text_content, submitter=submitter)
        self.evaluate_prevote_originality(submission.submission_id)
        self.save_blockchain()
        return submission

    def cast_signed_submission_vote_operation(self, *, submission_id, voter, vote_type, message, signature, auth_manager):
        submission = self.get_submission(submission_id)
        if not submission:
            raise ValueError(f"Submission not found: {submission_id}")
        verification = auth_manager.verify_vote_signature(wallet_address=voter, message=message, signature=signature, submission_id=submission_id, content_hash=submission.content_hash or "", vote_type=vote_type)
        voter = normalize_wallet_address(voter) or voter
        reviewer_decision = self.get_reviewer_vote_decision(voter) if self.get_finalized_head() is not None or ENVIRONMENT != "development" else None
        durable_vote = {
            "voter": voter, "submission_id": submission_id, "vote_type": vote_type,
            "voter_wallet_address": voter, "content_hash": submission.content_hash,
            "vote_version": verification.get("vote_version"), "protocol_version": verification.get("protocol_version"),
            "network_id": verification.get("network_id"), "signature_scheme": str(verification["signature_scheme"]),
            "vote_signature": str(verification["vote_signature"]), "vote_message": str(verification["vote_message"]),
            "signed_message_hash": str(verification["signed_message_hash"]), "vote_nonce": str(verification["nonce"]),
            "vote_issued_at": str(verification["vote_issued_at"]), "vote_expires_at": str(verification["vote_expires_at"]),
            "signed_at": str(verification["signed_at"]), "identity_source": str(verification["identity_source"]),
            "reviewer_policy_version": REVIEWER_POLICY_VERSION if reviewer_decision else None,
            "reputation_rule_version": REPUTATION_RULE_VERSION if reviewer_decision else None,
            "reviewer_status": reviewer_decision.status if reviewer_decision else None,
            "reviewer_eligible": reviewer_decision.eligible if reviewer_decision else None,
            "reviewer_status_effective_height": reviewer_decision.snapshot.get("reference_finalized_height") if reviewer_decision else None,
            "reviewer_status_reference_block_hash": reviewer_decision.snapshot.get("reference_finalized_block_hash") if reviewer_decision else None,
        }
        durable_vote["vote_identity"] = calculate_signed_vote_identity(
            wallet_address=voter,
            submission_id=submission_id,
            content_hash=submission.content_hash,
            vote_type=vote_type,
            nonce=durable_vote["vote_nonce"],
            issued_at=durable_vote["vote_issued_at"],
            expires_at=durable_vote["vote_expires_at"],
            network_id=durable_vote["network_id"],
            signature=durable_vote["vote_signature"],
            signature_scheme=durable_vote["signature_scheme"],
        )
        if hasattr(self.storage, "list_durable_votes"):
            prior_identity = next((item for item in self.storage.list_durable_votes(submission_id=submission_id) if item.get("vote_identity") == durable_vote["vote_identity"]), None)
            if prior_identity is not None:
                raise ValueError("Wallet has already submitted this signed vote.")
        finalized = self.get_finalized_head()
        epoch = reviewer_decision.review_epoch if reviewer_decision else None
        state_before = reviewer_decision.snapshot.get("underlying_reviewer_status", reviewer_decision.status) if reviewer_decision else "NEW"

        def record_offense(offense_type, votes, *, active_penalty_id=None):
            if finalized is None or epoch is None or not hasattr(self.storage, "record_reviewer_offense"):
                return None
            offense = build_offense_evidence(
                offense_type=offense_type, votes=votes,
                reference_finalized_height=int(finalized["block_height"]),
                reference_finalized_block_hash=finalized["block_hash"],
                review_epoch=int(epoch), creator_address=submission.submitter,
                active_penalty_id=active_penalty_id,
            )
            outcome = self._reviewer_reputation_service.apply_verified_offense(offense, state_before=state_before)
            self._persist_reputation_outcome(outcome)
            return outcome

        existing = self.storage.get_vote(submission_id, voter, self.votes)
        if existing is not None:
            if hasattr(self.storage, "record_durable_vote"):
                self.storage.record_durable_vote(durable_vote, lifecycle_state="rejected", rejection_reason="conflicting_counted_vote")
            if existing.get("vote_type") != vote_type and existing.get("vote_identity") and existing.get("vote_signature"):
                record_offense(SIGNED_VOTE_EQUIVOCATION, [existing, durable_vote])
            raise ValueError("Wallet has already voted on this submission.")
        if normalize_wallet_address(submission.submitter) == voter:
            if hasattr(self.storage, "record_durable_vote"):
                self.storage.record_durable_vote(durable_vote, lifecycle_state="rejected", rejection_reason="creator_self_vote")
            record_offense(CREATOR_SELF_VOTE, [durable_vote])
            raise ValueError("Submission creator cannot vote on their own submission.")
        if reviewer_decision and reviewer_decision.status in {"COOLDOWN", "SUSPENDED"}:
            active = self._reviewer_reputation_service.effective_penalty(voter, int(epoch))
            if hasattr(self.storage, "record_durable_vote"):
                self.storage.record_durable_vote(durable_vote, lifecycle_state="rejected", rejection_reason="reviewer_status_ineligible")
            record_offense(
                VOTE_DURING_COOLDOWN if reviewer_decision.status == "COOLDOWN" else VOTE_DURING_SUSPENSION,
                [durable_vote], active_penalty_id=active["penalty_id"] if active else None,
            )
            raise ValueError(f"Reviewer is not eligible: {reviewer_decision.reason}.")
        if reviewer_decision and not reviewer_decision.eligible:
            if hasattr(self.storage, "record_durable_vote"):
                self.storage.record_durable_vote(durable_vote, lifecycle_state="rejected", rejection_reason=reviewer_decision.reason)
            if reviewer_decision.reason == "review_epoch_vote_limit_reached" and finalized is not None:
                outcome = self._reviewer_reputation_service.record_rate_limit_excess(
                    durable_vote, reference_finalized_height=int(finalized["block_height"]),
                    reference_finalized_block_hash=finalized["block_hash"],
                    review_epoch=int(epoch), state_before=state_before,
                )
                self._persist_reputation_outcome(outcome)
            raise ValueError(f"Reviewer is not eligible: {reviewer_decision.reason}.")
        vote = self.cast_submission_vote(submission_id=submission_id, voter=voter, vote_type=vote_type)
        vote.update(durable_vote)
        if reviewer_decision and hasattr(self.storage, "record_durable_vote_with_epoch_limit"):
            epoch_start = int(reviewer_decision.review_epoch) * REVIEW_EPOCH_BLOCKS
            limit = PROBATION_MAX_VOTES_PER_EPOCH if reviewer_decision.status == "PROBATIONARY_REVIEWER" else ESTABLISHED_MAX_VOTES_PER_EPOCH
            durable_result = self.storage.record_durable_vote_with_epoch_limit(
                vote, maximum_votes=limit, epoch_start_height=epoch_start,
                epoch_end_height=epoch_start + REVIEW_EPOCH_BLOCKS - 1,
            )
        elif hasattr(self.storage, "record_durable_vote"):
            durable_result = self.storage.record_durable_vote(vote, lifecycle_state="accepted")
        else:
            durable_result = {"lifecycle_state": "accepted"}
        if hasattr(self.storage, "record_durable_vote"):
            if durable_result["lifecycle_state"] != "accepted":
                self.votes.remove(vote)
                if durable_result.get("rejection_reason") == "review_epoch_vote_limit_reached":
                    if finalized is not None:
                        outcome = self._reviewer_reputation_service.record_rate_limit_excess(
                            vote, reference_finalized_height=int(finalized["block_height"]),
                            reference_finalized_block_hash=finalized["block_hash"],
                            review_epoch=int(epoch), state_before=state_before,
                        )
                        self._persist_reputation_outcome(outcome)
                    raise ValueError("Reviewer has reached the valid vote limit for this review epoch.")
                raise ValueError("Wallet has already voted on this submission.")
        self.save_blockchain()
        return vote

    def cast_development_submission_vote_operation(self, *, submission_id, voter, vote_type):
        vote = self.cast_submission_vote(submission_id=submission_id, voter=voter, vote_type=vote_type)
        self.save_blockchain()
        return vote

    def legacy_add_transaction_operation(self, sender, recipient, amount, private_key):
        if sender not in self.wallets:
            raise ValueError("Invalid sender public key.")
        if recipient not in self.wallets:
            raise ValueError("Invalid recipient public key.")
        sender_wallet = self.get_wallet(sender)
        if not sender_wallet:
            raise ValueError("Sender wallet not found.")
        if not sender_wallet.validate_private_key(private_key, sender):
            raise ValueError("Invalid private key for sender's wallet.")
        if not isinstance(amount, (int, float)) or amount <= 0:
            raise ValueError("Invalid amount. Must be greater than 0.")
        transaction = Transaction(sender, recipient, amount)
        transaction.sign_transaction(private_key)
        self.add_transaction(transaction)
        return transaction

    def submit_signed_transfer_operation(
        self, *, payload, wallet_address, auth_manager, build_preview,
        network_name, origin_node_id=None
    ):
        preview = build_preview(payload)
        durable_existing = self.storage.get_durable_native_transaction_record(preview.tx_id)
        if durable_existing is not None:
            if not self._native_ledger_service._same_immutable_signed_transaction(durable_existing, preview.to_dict()):
                raise ValueError("Conflicting native transaction replay: tx_id is already bound to different signed transaction data.")
            durable_intent = next(
                (record for record in self.storage.load_transfer_intents()
                 if str(record.get("tx_id") or "").strip().lower() == preview.tx_id),
                None,
            )
            if durable_intent is None:
                raise RuntimeError("Transaction already exists but local transfer record is missing.")
            self._publish_durable_native_transaction_state({
                "transfer_intents": self.storage.load_transfer_intents(),
                "native_transactions": self.storage.list_durable_native_transaction_records(),
            })
            return durable_intent, None, True
        verification = auth_manager.verify_transfer_signature(
            wallet_address=wallet_address, from_address=payload.from_address, to_address=payload.to_address,
            amount=payload.amount, fee=payload.fee, memo=payload.memo, message=payload.message, signature=payload.signature,
        )
        if str(verification["fee"]) != "0":
            raise ValueError("Nonzero fees are not enabled yet.")
        result = self._admit_signed_transfer_durably(
            admit_to_mempool=bool(payload.admit_to_mempool),
            origin_node_id=origin_node_id,
            from_address=str(verification["from_address"]), to_address=str(verification["to_address"]),
            amount=str(verification["amount"]), fee=str(verification["fee"]), memo=str(verification["memo"] or ""),
            network=network_name, transaction_version=verification.get("transaction_version"),
            protocol_version=verification.get("protocol_version"), network_id=verification.get("network_id"),
            signature_scheme=str(verification["signature_scheme"]), signature=str(verification["transfer_signature"]),
            signed_message_hash=str(verification["signed_message_hash"]), signed_message=str(verification["transfer_message"]),
            transfer_nonce=str(verification["nonce"]), transaction_timestamp=str(verification["timestamp"]),
            signed_at=str(verification["signed_at"]),
        )
        if result["transaction"]["tx_id"] != preview.tx_id:
            raise ValueError("Submitted transaction identity does not match its canonical signed payload.")
        return result["transfer_intent"], result["admission"], result["duplicate"]

    def verify_content_download_operation(self, content_object, *, verifier, data_dir):
        verification = verifier(content_object, data_dir=data_dir)
        if verification["verified"]:
            content_object.hash_scheme = verification["hash_scheme"]
            content_object.verified_at = verification["verified_at"]
            content_object.verification_error = None
            content_object.storage_status = "verified"
            if verification["file_size_bytes"] is not None:
                content_object.file_size_bytes = verification["file_size_bytes"]
        return verification

    # Task 11C guarded development/application operations. HTTP adapters pass
    # already-parsed values; state changes, temporary-file handling, and save
    # coordination remain here with the established Task 7-9 facade paths.
    def reset_to_genesis_operation(self):
        self.storage.delete_blockchain_document()
        return Blockchain(
            project_owner_wallet=Wallet(),
            Contributor_one=Wallet(),
            Contributor_two=Wallet(),
        )

    def repair_submission_certificate_operation(self, submission_id, *, approved_at=None):
        submission = self.get_submission(submission_id)
        if not submission:
            raise LookupError(f"Submission not found: {submission_id}")
        existing_certificate = self.get_originality_certificate_for_submission(submission_id)
        if existing_certificate:
            submission.certificate_id = existing_certificate.certificate_id
            self.save_blockchain()
            return submission, existing_certificate, True
        if submission.status == QUEUED:
            submission.status = APPROVED
            if submission_id in self.mint_queue:
                self.mint_queue = [queued_id for queued_id in self.mint_queue if queued_id != submission_id]
        if submission.status != APPROVED:
            raise ValueError("Only approved submissions can be repaired with an originality certificate.")
        vote_summary = self.get_submission_votes(submission_id)
        voting_threshold = self.get_voting_threshold()
        voting_window_expired = time.time() >= submission.created_at + (VOTING_WINDOW_HOURS * 60 * 60)
        if not vote_summary["votes"]:
            raise ValueError("Cannot repair certificate: finalized vote data is missing.")
        if not (len(vote_summary["votes"]) >= voting_threshold["minimum_votes"] or voting_window_expired):
            raise ValueError("Cannot repair certificate: vote data has not reached finality.")
        if vote_summary["approval_percentage"] < ORIGINALITY_APPROVAL_THRESHOLD:
            raise ValueError("Cannot repair certificate: approval percentage is below the required threshold.")
        certificate = self.create_originality_certificate(submission_id, approved_at=approved_at or time.time())
        persisted_certificate = self.get_originality_certificate_for_submission(submission_id)
        if not persisted_certificate:
            raise ValueError("certificate could not be retrieved after repair")
        submission.certificate_id = persisted_certificate.certificate_id
        self.save_blockchain()
        return submission, certificate, False

    def legacy_add_block_upload_operation(self, *, file_bytes, original_filename, miner, private_key):
        if not is_valid_public_key(miner, self.wallets):
            raise ValueError("Invalid miner public key.")
        wallet = self.wallets.get(miner)
        if not wallet:
            raise ValueError("Wallet not found.")
        if not wallet.validate_private_key(private_key, miner):
            raise ValueError("Private key does not match the wallet ID.")
        image_path = os.path.join("temp", os.path.basename(original_filename))
        os.makedirs("temp", exist_ok=True)
        try:
            with open(image_path, "wb") as buffer:
                buffer.write(file_bytes)
            if not os.path.isfile(image_path):
                raise ValueError("Failed to save the uploaded image.")
            # Resolve at operation time to preserve the established development
            # seam used by the legacy HTTP endpoint and its isolated tests.
            from utils import extract_text as extract_uploaded_text
            text_content = extract_uploaded_text(image_path)
            if not text_content:
                raise ValueError("No text found in the image.")
            block_added = self.add_block(
                image_path=image_path,
                text_content=text_content,
                miner=miner,
                validate_meme=True,
            )
            return block_added, self.get_latest_block() if block_added else None
        finally:
            if os.path.isfile(image_path):
                os.remove(image_path)

    def generate_development_wallet_operation(self):
        wallet = Wallet()
        self.wallets[wallet.public_key] = wallet
        self.save_blockchain()
        return wallet

    def cleanup_bad_mint_queue_items_operation(self, *, block_unmintable=False):
        report = self.cleanup_bad_mint_queue_items(block_unmintable=block_unmintable)
        if block_unmintable:
            self.save_blockchain()
        return report

    def admit_transaction_for_broadcast_operation(
        self, tx_id, *, origin_node_id=None, network_name=None
    ):
        transaction = self.get_native_transaction(tx_id)
        if not transaction:
            raise LookupError(f"Transaction not found: {tx_id}")
        status = str(transaction.get("status") or "").strip().lower()
        if status not in {"signed_pending", "validated_pending", "mempool"}:
            raise ValueError("Only signed pending or mempool-eligible transactions can be broadcast.")
        if status != "mempool":
            self.admit_native_transaction_operation(
                tx_id,
                origin_node_id=origin_node_id,
                network_name=network_name,
            )
        return self.get_native_transaction(tx_id) or transaction

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
                self.originality_evidence = [
                    validate_originality_evidence(item)
                    for item in loaded_data.get("originality_evidence", []) or []
                ]
                self.access_requests = list(loaded_data.get("access_requests", []) or [])
                self.access_accounts = list(loaded_data.get("access_accounts", []) or [])
                self.wallet_bindings = list(loaded_data.get("wallet_bindings", []) or [])
                self.allowlist_entries = list(loaded_data.get("allowlist_entries", []) or [])
                self.override_requests = list(loaded_data.get("override_requests", []) or [])
                self.feedback_records = list(loaded_data.get("feedback_records", []) or [])
                self.audit_logs = list(loaded_data.get("audit_logs", []) or [])
                self.finality_attestations = list(loaded_data.get("finality_attestations", []) or [])
                self.finalized_blocks = list(loaded_data.get("finalized_blocks", []) or [])
                self._validate_persisted_finality_state()
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
            self.originality_evidence = []
            self.access_requests = []
            self.access_accounts = []
            self.wallet_bindings = []
            self.allowlist_entries = []
            self.override_requests = []
            self.feedback_records = []
            self.audit_logs = []
            self.finality_attestations = []
            self.finalized_blocks = []
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
            payload_mime_type = guess_mime_type(os.path.basename(resolved_image_path), "image/jpeg")
            if payload_mime_type == TEXT_MIME_TYPE:
                with open(resolved_image_path, "r", encoding="utf-8") as text_file:
                    text_content = text_file.read()
                content_object = self.upload_text_content(
                    text_content=text_content,
                    submitted_by=submission.submitter,
                    caption=validate_caption(text_content),
                )
                submission.text_content = content_object.text_content or text_content
            else:
                with open(resolved_image_path, "rb") as image_file:
                    content_object = self.upload_binary_content(
                        file_bytes=image_file.read(),
                        submitted_by=submission.submitter,
                        mime_type=payload_mime_type,
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
        submission = self._content_coordination_service.submit_content(self._content_coordination_state(), self.storage, NETWORK_NAME, image_path, text_content, submitter)
        self.evaluate_prevote_originality(submission.submission_id)
        return submission
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

    def protocol_v1_lifecycle_policy(self) -> dict[str, object]:
        return FinalityService.policy(
            FinalityPolicy(PROTOCOL_V1_CONFIRMATION_DEPTH, PROTOCOL_V1_FINALITY_DEPTH),
            self.validator_set,
        )

    def get_protocol_v1_block_for_submission(self, submission_id, *, chain=None):
        return self._finality_service.find_protocol_block(chain or self.chain, field_name="submission_id", value=submission_id, is_protocol_block=self.is_protocol_v1_block_payload)

    def get_protocol_v1_block_for_certificate(self, certificate_id, *, chain=None):
        return self._finality_service.find_protocol_block(chain or self.chain, field_name="certificate_id", value=certificate_id, is_protocol_block=self.is_protocol_v1_block_payload)

    def get_block_chain_state(self, block_or_hash, *, chain=None) -> dict[str, object]:
        chain_dicts = self.chain_to_dicts(chain or self.chain)
        return self._finality_service.block_chain_state(
            block_or_hash,
            chain_dicts,
            FinalityPolicy(PROTOCOL_V1_CONFIRMATION_DEPTH, PROTOCOL_V1_FINALITY_DEPTH),
            finalized_blocks=self.finalized_blocks,
            validator_set=self.validator_set,
            attestations=self.finality_attestations,
            expected_network_id=self.protocol_v1_network_id(),
        )

    def get_finalized_head(self) -> dict[str, object] | None:
        """Return the highest persisted quorum-finalized block on the current chain."""
        canonical_by_height = {int(block.index): block for block in self.chain}
        candidates = [
            record for record in self.finalized_blocks
            if isinstance(record, dict)
            and canonical_by_height.get(record.get("block_height")) is not None
            and canonical_by_height[record["block_height"]].hash == record.get("block_hash")
        ]
        if not candidates:
            return None
        record = max(candidates, key=lambda item: int(item["block_height"]))
        return {"block_height": int(record["block_height"]), "block_hash": record["block_hash"]}

    def evaluate_reviewer_qualification(self, reviewer_address, *, policy_version=REVIEWER_POLICY_VERSION):
        return self._reviewer_eligibility_service.qualification(
            reviewer_address=reviewer_address, chain=self.chain,
            finalized_head=self.get_finalized_head(), policy_version=policy_version,
        )

    def get_reviewer_status(self, reviewer_address, *, policy_version=REVIEWER_POLICY_VERSION, persist=True):
        state, evidence = self._reviewer_eligibility_service.reconcile(
            reviewer_address=reviewer_address, chain=self.chain,
            finalized_head=self.get_finalized_head(), storage=self.storage,
            policy_version=policy_version, persist=persist,
        )
        votes = self._reviewer_eligibility_service._accepted_votes(self.storage, evidence["reviewer_address"])
        payload = self._reviewer_eligibility_service.status_payload(state, evidence, votes) | {
            "reference_finalized_height": evidence["reference_finalized_height"],
            "reference_finalized_block_hash": evidence["reference_finalized_block_hash"],
            "qualification_evidence": evidence,
        }
        reputation = self._reviewer_reputation_service.summary(
            evidence["reviewer_address"], evidence["review_epoch"],
            state.get("underlying_reviewer_status", state["current_status"]),
        )
        payload.update(reputation)
        payload["reputation"] = reputation
        return payload

    def get_reviewer_offenses(self, reviewer_address):
        address = normalize_wallet_address(reviewer_address)
        if address is None:
            raise ValueError("reviewer_address must be a valid Ethereum-style 0x address.")
        return self._reviewer_reputation_service.offenses(address)

    def receive_reviewer_offense_evidence(self, offense):
        from reviewer_reputation import validate_offense_evidence

        durable_votes = self.storage.list_durable_votes() if hasattr(self.storage, "list_durable_votes") else []
        accepted_votes = {
            vote.get("vote_identity"): vote
            for vote in durable_votes
            if vote.get("vote_identity") and vote.get("lifecycle_state") == "accepted"
        }

        def historical_underlying_status(vote):
            state = self._reviewer_eligibility_service.status_at_reference(
                reviewer_address=vote["reviewer_address"], chain=self.chain,
                finalized_head={
                    "block_height": vote["reviewer_status_effective_height"],
                    "block_hash": vote["reviewer_status_reference_block_hash"],
                },
                storage=self.storage,
                policy_version=vote["reviewer_policy_version"],
                reputation_rule_version=vote["reputation_rule_version"],
            )
            return state.get("underlying_status", state["status"])

        validated = validate_offense_evidence(
            offense,
            finalized_reference_validator=self.is_finalized_canonical_reference,
            creator_resolver=lambda submission_id: (
                self.get_submission(submission_id).submitter
                if self.get_submission(submission_id) is not None else None
            ),
            accepted_vote_resolver=accepted_votes.get,
            reviewer_status_resolver=historical_underlying_status,
        )
        status = self.get_reviewer_status(validated["reviewer_address"])
        outcome = self._reviewer_reputation_service.apply_verified_offense(
            validated,
            state_before=status.get("underlying_reviewer_status", status["status"]),
        )
        self._persist_reputation_outcome(outcome)
        return {"accepted": True, "action": "duplicate" if outcome.replay else "created", "offense": outcome.offense}

    def _persist_reputation_outcome(self, outcome):
        if outcome.offense is None or outcome.replay:
            return
        offense = outcome.offense
        finalized = self.get_finalized_head()
        if finalized is None:
            return
        active = self._reviewer_reputation_service.effective_penalty(
            offense["reviewer_address"], int(finalized["block_height"]) // REVIEW_EPOCH_BLOCKS,
        )
        if active is None:
            return
        resulting = active["effective_status"]
        current = self.storage.get_reviewer_state(offense["reviewer_address"])
        if current is None:
            current = self.storage.initialize_reviewer_state(offense["reviewer_address"])
        if current["current_status"] != resulting:
            from protocol_v1 import canonical_json_text
            self.storage.transition_reviewer_state(
                offense["reviewer_address"], to_status=resulting,
                reviewer_policy_version=REVIEWER_POLICY_VERSION,
                reputation_rule_version=REPUTATION_RULE_VERSION,
                status_effective_height=offense["reference_finalized_height"],
                status_reference_block_hash=offense["reference_finalized_block_hash"],
                reason=canonical_json_text({"reason_code": offense["reason_code"], "offense_id": offense["offense_id"]}),
            )

    def get_reviewer_vote_decision(self, reviewer_address, *, policy_version=REVIEWER_POLICY_VERSION):
        decision = self._reviewer_eligibility_service.vote_decision(
            reviewer_address=reviewer_address, chain=self.chain,
            finalized_head=self.get_finalized_head(), storage=self.storage,
            policy_version=policy_version,
        )
        # Supply the exact canonical reference copied into an accepted vote.
        evidence = self.evaluate_reviewer_qualification(reviewer_address, policy_version=policy_version)
        return type(decision)(
            decision.eligible, decision.reason, decision.status,
            decision.votes_used_this_epoch, decision.votes_remaining_this_epoch,
            decision.review_epoch, decision.snapshot | {
                "reference_finalized_height": evidence["reference_finalized_height"],
                "reference_finalized_block_hash": evidence["reference_finalized_block_hash"],
            },
        )

    def is_finalized_canonical_reference(self, height, block_hash):
        if isinstance(height, bool) or not isinstance(height, int) or height < 0:
            return False
        normalized_hash = str(block_hash or "").strip().lower()
        if height >= len(self.chain) or str(self.chain[height].hash).strip().lower() != normalized_hash:
            return False
        return any(
            int(record.get("block_height", -1)) == height
            and str(record.get("block_hash") or "").strip().lower() == normalized_hash
            for record in self.finalized_blocks if isinstance(record, dict)
        )

    def get_reviewer_status_at_reference(self, reviewer_address, height, block_hash, *, policy_version=REVIEWER_POLICY_VERSION, reputation_rule_version=REPUTATION_RULE_VERSION):
        if not self.is_finalized_canonical_reference(height, block_hash):
            raise ValueError("Reviewer reference is not a finalized canonical block.")
        return self._reviewer_eligibility_service.status_at_reference(
            reviewer_address=reviewer_address, chain=self.chain,
            finalized_head={"block_height": height, "block_hash": str(block_hash).lower()},
            storage=self.storage, policy_version=policy_version,
            reputation_rule_version=reputation_rule_version,
        )["status"]

    def build_reviewer_snapshot(self, reviewer_addresses=None, *, policy_version=REVIEWER_POLICY_VERSION, reputation_rule_version=REPUTATION_RULE_VERSION, reference=None):
        if reviewer_addresses is None:
            addresses = set(bootstrap_established_reviewers(policy_version))
            if hasattr(self.storage, "list_reviewer_states"):
                addresses.update(item["reviewer_address"] for item in self.storage.list_reviewer_states())
        else:
            addresses = set(reviewer_addresses)
        return self._reviewer_eligibility_service.snapshot(
            reviewer_addresses=addresses, chain=self.chain,
            finalized_head=reference or self.get_finalized_head(), storage=self.storage,
            policy_version=policy_version, reputation_rule_version=reputation_rule_version,
        )

    def get_certificate_v3_vote_context(self, submission_id, *, reference=None):
        """Return independently validated votes and their finalized snapshot."""
        submission = self.get_submission(submission_id)
        if submission is None:
            raise ValueError(f"Submission not found: {submission_id}")
        finalized = reference or self.get_finalized_head()
        if finalized is None or not self.is_finalized_canonical_reference(
            int(finalized["block_height"]), finalized["block_hash"]
        ):
            return {"votes": [], "snapshot": None, "established_vote_count": 0}
        accepted_identities = set()
        if hasattr(self.storage, "list_durable_votes"):
            accepted_identities = {
                item.get("vote_identity")
                for item in self.storage.list_durable_votes(submission_id=submission_id)
                if item.get("lifecycle_state") == "accepted"
                and item.get("identity_status") == "canonical"
                and item.get("reviewer_eligible") is True
                and item.get("reputation_rule_version") == REPUTATION_RULE_VERSION
            }
        valid_votes = []
        for vote in self.storage.get_votes_for_submission(submission_id, self.votes):
            if vote.get("vote_identity") not in accepted_identities:
                continue
            try:
                validate_certificate_v3_vote_record(
                    vote,
                    submission_id=submission_id,
                    content_hash=submission.content_hash,
                    creator_address=submission.submitter,
                    network_id=self.protocol_v1_network_id(),
                    reviewer_status_resolver=self.get_reviewer_status_at_reference,
                )
            except ValueError:
                continue
            valid_votes.append(vote)
        snapshot = self.build_reviewer_snapshot(
            [vote.get("voter_wallet_address") or vote.get("voter") for vote in valid_votes],
            reference=finalized,
        )
        eligible_by_address = {
            item["address"]: item["status"]
            for item in snapshot["reviewers"]
            if item["status"] in {"PROBATIONARY_REVIEWER", "ESTABLISHED_REVIEWER"}
        }
        valid_votes = [
            vote for vote in valid_votes
            if normalize_wallet_address(vote.get("voter_wallet_address") or vote.get("voter")) in eligible_by_address
        ]
        if len(valid_votes) != len(snapshot["reviewers"]):
            snapshot = self.build_reviewer_snapshot(
                [vote.get("voter_wallet_address") or vote.get("voter") for vote in valid_votes],
                reference=finalized,
            )
        established = sum(item["status"] == "ESTABLISHED_REVIEWER" for item in snapshot["reviewers"])
        return {"votes": valid_votes, "snapshot": snapshot, "established_vote_count": established}

    def reconcile_canonical_reviewer_states(self):
        """Apply all transitions implied by the current finalized ancestry."""
        if self.get_finalized_head() is None or not hasattr(self.storage, "initialize_reviewer_state"):
            return []
        addresses = set(bootstrap_established_reviewers())
        if hasattr(self.storage, "list_reviewer_states"):
            addresses.update(item["reviewer_address"] for item in self.storage.list_reviewer_states())
        height = int(self.get_finalized_head()["block_height"])
        for block in self.chain:
            if int(block.index) > height:
                continue
            creator = normalize_wallet_address(getattr(block, "creator_wallet", None))
            if creator:
                addresses.add(creator)
            for transaction in list(getattr(block, "native_transactions", []) or []):
                for field in ("from_address", "to_address"):
                    wallet = normalize_wallet_address(transaction.get(field))
                    if wallet:
                        addresses.add(wallet)
        return [self.get_reviewer_status(address) for address in sorted(addresses)]

    def get_finality_evidence(self, block_or_hash):
        """Return durable quorum evidence for a canonical finalized block, if any."""
        block_hash = str(block_or_hash or "").strip() if isinstance(block_or_hash, str) else str(self._block_field(block_or_hash, "hash") or "").strip()
        for record in self.finalized_blocks:
            if isinstance(record, dict) and record.get("block_hash") == block_hash:
                return dict(record)
        return None

    def _validate_persisted_finality_state(self):
        seen_heights = set()
        for record in self.finalized_blocks:
            self._finality_service.validate_finalization_evidence(
                record, expected_network_id=self.protocol_v1_network_id()
            )
            height = record["block_height"]
            if height in seen_heights:
                raise FinalityAttestationError("Persisted finality evidence has duplicate finalized heights.")
            seen_heights.add(height)
            canonical = next((block for block in self.chain if int(block.index) == height), None)
            if canonical is None or canonical.hash != record["block_hash"]:
                raise FinalityAttestationError("Persisted finality evidence does not match the canonical chain.")

    def submit_validator_finality_attestations(self, attestations) -> list[dict]:
        """Validate and durably apply one or more votes against one chain snapshot.

        Batching is an operational optimization only: every attestation still
        passes the existing canonical validator, signature, quorum, and
        finalized-height checks.  A shared chain validation and one durable
        checkpoint prevent a received quorum from doing duplicate full-chain
        work and writes.
        """
        if not isinstance(attestations, (list, tuple)) or not attestations:
            raise FinalityAttestationError("Finality attestations must be a non-empty list.")
        if not self.is_chain_valid(self.chain_to_dicts(self.chain)):
            raise FinalityAttestationError("Finality cannot be applied while canonical chain validation fails.")

        updated_attestations = list(self.finality_attestations)
        updated_finalized_blocks = list(self.finalized_blocks)
        results = []
        canonical_by_height = {int(block.index): block.to_dict() for block in self.chain}
        for attestation in attestations:
            if not isinstance(attestation, dict):
                raise FinalityAttestationError("Finality attestation must be an object.")
            height = self._finality_service._height(attestation.get("block_height"))
            canonical = canonical_by_height.get(height)
            if canonical is None:
                raise FinalityAttestationError("Finality attestation references a nonexistent canonical block.")
            if canonical.get("hash") != self.calculate_hash_from_dict(canonical):
                raise FinalityAttestationError("Finality attestation references a canonical block with an invalid stored hash.")
            result = self._finality_service.process_attestation(
                attestation,
                validator_set=self.validator_set,
                expected_network_id=self.protocol_v1_network_id(),
                canonical_block=canonical,
                existing_attestations=updated_attestations,
                finalized_blocks=updated_finalized_blocks,
            )
            if result["status"] != "duplicate":
                updated_attestations.append(result["attestation"])
            if result["status"] != "duplicate" and result.get("finalization") is not None:
                updated_finalized_blocks.append(result["finalization"])
            results.append((result, canonical))

        if any(result["status"] != "duplicate" for result, _ in results):
            self.finality_attestations = sorted(
                updated_attestations,
                key=lambda value: (value["block_height"], value["block_hash"], value["validator_address"], value["signature"]),
            )
            self.finalized_blocks = sorted(
                updated_finalized_blocks,
                key=lambda value: (value["block_height"], value["block_hash"]),
            )
            self.save_blockchain()
        for result, canonical in results:
            if result.get("finalization") is not None:
                submission_id = canonical.get("submission_id")
                if submission_id:
                    self.lifecycle_timing.mark(
                        submission_id,
                        "finalized",
                        block_height=canonical["index"],
                        block_hash=canonical["hash"],
                    )
        if any(result.get("finalization") is not None for result, _ in results):
            self.reconcile_canonical_reviewer_states()
        return [result for result, _ in results]

    def submit_validator_finality_attestation(self, attestation) -> dict:
        """Validate, durably record, and deterministically apply one validator vote."""
        return self.submit_validator_finality_attestations([attestation])[0]

    def _candidate_preserves_finalized_blocks(self, candidate_chain) -> bool:
        candidate_by_height = {
            int(self._block_field(block, "index")): str(self._block_field(block, "hash") or "")
            for block in candidate_chain or []
        }
        return all(
            candidate_by_height.get(record.get("block_height")) == record.get("block_hash")
            for record in self.finalized_blocks if isinstance(record, dict)
        )

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
            self.validate_originality_certificate(certificate, submission)
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
        self.evaluate_prevote_originality(submission.submission_id)
        return submission

    def get_originality_evidence(self, submission_id):
        return self.storage.get_originality_evidence(
            submission_id, self.originality_evidence
        )

    def get_originality_evidence_by_digest(self, evidence_digest):
        digest = str(evidence_digest or "").strip().lower()
        for evidence in self.originality_evidence:
            if evidence.get("canonical_evidence_digest") == digest:
                return deepcopy(evidence)
        return None

    def get_originality_evidence_history(self, submission_id):
        if self.get_submission(submission_id) is None:
            raise ValueError(f"Submission not found: {submission_id}")
        return self.storage.list_originality_evidence_history(submission_id)

    def _minted_originality_index(self):
        head = self._current_canonical_head()
        head_identity = (head["height"], head["hash"])
        if self._originality_index_cache_head == head_identity:
            return deepcopy(self._originality_index_cache_records)
        cached = self.storage.load_minted_media_originality_index(
            rule_version=ORIGINALITY_RULE_VERSION,
            head_height=head["height"],
            head_hash=head["hash"],
        )
        if cached is not None:
            self._originality_index_cache_head = head_identity
            self._originality_index_cache_records = deepcopy(cached)
            return cached
        records = canonical_minted_media_features(
            self.chain,
            ocr=self._originality_pipeline.ocr,
            certificate_consensus=self._originality_pipeline.certificate_consensus,
        )
        self.storage.replace_minted_media_originality_index(
            rule_version=ORIGINALITY_RULE_VERSION,
            head_height=head["height"],
            head_hash=head["hash"],
            records=records,
        )
        self._originality_index_cache_head = head_identity
        self._originality_index_cache_records = deepcopy(records)
        return records

    def _originality_reference_is_canonical(self, evidence):
        height = evidence.get("originality_reference_height")
        if isinstance(height, bool) or not isinstance(height, int):
            return False
        if height < 0 or height >= len(self.chain):
            return False
        return self.chain[height].hash == evidence.get("originality_reference_block_hash")

    def evaluate_prevote_originality(self, submission_id, *, force=False):
        submission = self.get_submission(submission_id)
        if submission is None:
            raise ValueError(f"Submission not found: {submission_id}")
        existing = self.get_originality_evidence(submission_id)
        if existing is not None and self._originality_reference_is_canonical(existing) and not force:
            return deepcopy(existing)

        if existing is not None:
            self.originality_evidence = [
                record for record in self.originality_evidence
                if record.get("submission_id") != submission_id
            ]

        content_object = self.get_content_object_by_hash(submission.content_hash)
        evidence = self._originality_pipeline.evaluate(
            submission,
            content_object,
            self.chain,
            data_dir=self.storage.data_dir,
            minted_index=self._minted_originality_index(),
        )
        self.originality_evidence.append(evidence)

        if evidence["final_prevote_decision"] == HARD_REJECT:
            reason = ",".join(evidence["reason_codes"])
            if submission.status != HARD_REJECTED:
                self.hard_reject_submission(submission_id, reason)
            else:
                submission.hard_reject_reason = reason
        elif (
            submission.status == HARD_REJECTED
            and (
                existing is not None
                or EXACT_MINTED_CONTENT_DUPLICATE in str(submission.hard_reject_reason or "")
            )
        ):
            # A pre-certification stale-fork exact match can disappear.  Its
            # immutable old evidence remains in SQLite history while the
            # submission deterministically returns to the pre-vote state.
            submission.status = PENDING
            submission.hard_reject_reason = None
            submission.decision_reason = None
            submission.decision_finalized_at = None
        return deepcopy(evidence)

    def ensure_current_originality_evidence(self, submission_id):
        evidence = self.get_originality_evidence(submission_id)
        if evidence is None or not self._originality_reference_is_canonical(evidence):
            evidence = self.evaluate_prevote_originality(submission_id, force=evidence is not None)
            self.save_blockchain()
        return evidence

    def ensure_certificate_originality_evidence(self, submission_id):
        evidence = self.ensure_current_originality_evidence(submission_id)
        submission = self.get_submission(submission_id)
        media = self._certificate_media_context(submission)
        if media["media_bytes"] is None:
            raise ValueError(
                "Canonical media bytes are required before certificate issuance."
            )
        if (
            evidence.get("certificate_verification_profile")
            != CERTIFICATE_EVIDENCE_PROFILE
            or evidence.get("content_hash") != submission.content_hash
            or (
                str(media["mime_type"]).startswith("image/")
                and evidence.get("perceptual_hash_result", {}).get("status") != "SUCCESS"
            )
        ):
            # Legacy submissions may first have been screened while their
            # media was still typed as an opaque remote reference.  Once the
            # exact bytes are promoted, recompute before issuing anything.
            evidence = self.evaluate_prevote_originality(submission_id, force=True)
            self.save_blockchain()
        if evidence.get("certificate_verification_profile") != CERTIFICATE_EVIDENCE_PROFILE:
            raise ValueError(
                "Originality evidence could not be migrated to the deterministic certificate profile."
            )
        if evidence.get("content_hash") != submission.content_hash:
            raise ValueError("Originality evidence content_hash does not match submission.")
        if not self._originality_reference_is_canonical(evidence):
            raise ValueError("Originality evidence reference is not canonical.")
        return evidence

    def _certificate_media_context(self, submission):
        content_object = self.get_content_object_by_hash(submission.content_hash)
        mime_type = str(getattr(content_object, "mime_type", None) or "application/octet-stream").lower()
        media_bytes = None
        if content_object is not None:
            try:
                media_bytes = load_content_bytes(
                    content_object.content_hash,
                    mime_type,
                    data_dir=self.storage.data_dir,
                )
            except (FileNotFoundError, UnicodeDecodeError, ValueError):
                if mime_type == TEXT_MIME_TYPE and content_object.text_content:
                    media_bytes = content_object.text_content.encode("utf-8")
        if media_bytes is None:
            for block in reversed(self.chain):
                if block.content_hash == submission.content_hash and block.media_bytes is not None:
                    media_bytes = bytes(block.media_bytes)
                    mime_type = str(block.mime_type or mime_type).lower()
                    break
        if media_bytes is not None:
            detected = detect_mime_type_from_bytes(media_bytes)
            if detected is not None:
                mime_type = detected
        return {"media_bytes": media_bytes, "mime_type": mime_type}

    def validate_originality_certificate(
        self, certificate, submission, *, allowed_submission_statuses=None, chain=None
    ):
        validation_chain = self.chain if chain is None else chain
        kwargs = {}
        if certificate is not None and certificate.is_milestone5_certificate():
            evidence = self.get_originality_evidence_by_digest(
                certificate.originality_evidence_digest
            )
            media = self._certificate_media_context(submission)
            kwargs = {
                "originality_evidence": evidence,
                "chain": validation_chain,
                **media,
            }
            if certificate.is_certificate_v3():
                context = self.get_certificate_v3_vote_context(
                    submission.submission_id,
                    reference={
                        "block_height": certificate.reviewer_snapshot_reference_height,
                        "block_hash": certificate.reviewer_snapshot_reference_block_hash,
                    },
                )
                kwargs.update({
                    "votes": context["votes"],
                    "reviewer_snapshot": context["snapshot"],
                    "reviewer_status_resolver": self.get_reviewer_status_at_reference,
                    "finalized_reference_validator": self.is_finalized_canonical_reference,
                })
        return validate_certificate_for_submission(
            certificate,
            submission,
            network_name=NETWORK_NAME,
            allowed_submission_statuses=allowed_submission_statuses,
            **kwargs,
        )

    def update_submission_status(self, submission_id, new_status):
        return self._submission_originality_service.update_submission_status(self._submission_originality_state(), self.storage, submission_id, new_status)
    def hard_reject_submission(self, submission_id, reason):
        return self._submission_originality_service.hard_reject_submission(self._submission_originality_state(), self.storage, submission_id, reason)
    def record_vote(self, voter, submission_id=None, created_at=None):
        return self._submission_originality_service.record_vote(self._submission_originality_state(), voter, submission_id, created_at)
    def cast_submission_vote(self, submission_id, voter, vote_type, created_at=None):
        evidence = self.ensure_current_originality_evidence(submission_id)
        if evidence["final_prevote_decision"] == HARD_REJECT:
            raise ValueError("Hard rejected submissions cannot receive votes.")
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
            # Text payloads must be declared as text even when older content
            # records retained a mixed hint from a captioned submission.
            metadata["content_type"] = (
                CONTENT_TYPE_TEXT
                if content_object.mime_type == TEXT_MIME_TYPE
                else content_object.content_type
            )
            metadata["mime_type"] = content_object.mime_type
        elif submission is not None:
            # A legacy content-object hash can differ from the canonical
            # certificate payload hash.  The promoted local text file remains
            # authoritative for media typing, so retain the required Protocol
            # V1 text metadata instead of emitting an untyped text block.
            promoted_mime_type = guess_mime_type(
                os.path.basename(submission.image_path or ""), ""
            )
            if promoted_mime_type == TEXT_MIME_TYPE or str(submission.image_path or "").lower().endswith(".txt"):
                metadata["content_type"] = CONTENT_TYPE_TEXT
                metadata["mime_type"] = TEXT_MIME_TYPE
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
    _native_transaction_lifecycle_transitions = staticmethod(NativeLedgerService.native_transaction_lifecycle_transitions)
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
        return self._block_validation_service.validate_native_transactions(
            block_dict, self._block_validation_collaborators(), prior_chain=prior_chain
        )
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
        self.validate_originality_certificate(certificate, submission)
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
        if submission is None:
            raise ValueError(f"Submission not found: {submission_id}")
        # Model A requires canonical bytes.  Promote legacy local content
        # before producing the evidence that the new certificate will bind.
        self._promote_submission_content_for_protocol_v1(submission)
        evidence = self.ensure_certificate_originality_evidence(submission_id)
        if evidence["final_prevote_decision"] == HARD_REJECT:
            raise ValueError("Hard rejected submissions cannot receive originality certificates.")
        finalized = self.get_finalized_head()
        issue_v3 = finalized is not None
        tip = self.chain[int(finalized["block_height"])] if issue_v3 else self.get_latest_block()
        vote_context = self.get_certificate_v3_vote_context(submission_id, reference=finalized) if issue_v3 else None
        if issue_v3:
            votes = vote_context["votes"]
            original = sum(vote.get("vote_type") == VOTE_ORIGINAL for vote in votes)
            not_original = sum(vote.get("vote_type") == VOTE_NOT_ORIGINAL for vote in votes)
            if len(votes) < MIN_VALID_VOTES:
                raise ValueError("Certificate-v3 requires at least 5 canonically valid votes.")
            if vote_context["established_vote_count"] < MIN_ESTABLISHED_VOTES:
                raise ValueError("Certificate-v3 requires at least one established-reviewer vote.")
            if original * 10_000 < (original + not_original) * APPROVAL_THRESHOLD_BPS:
                raise ValueError("Certificate-v3 approval threshold is not satisfied.")
        media = self._certificate_media_context(submission)
        certificate = self._submission_originality_service.create_certificate(
            self._submission_originality_state(), self.storage, submission_id,
            approved_at=approved_at, network_name=network_name,
            issuing_node_id=issuing_node_id, allow_pending=allow_pending,
            promote_content=self._promote_submission_content_for_protocol_v1,
            save=self.save_blockchain if save else None,
            voting_threshold=self.get_voting_threshold,
            originality_evidence=evidence,
            certificate_version=(MILESTONE5_CERTIFICATE_V3_VERSION if issue_v3 else 2),
            counted_votes=(vote_context["votes"] if issue_v3 else None),
            reviewer_snapshot=(vote_context["snapshot"] if issue_v3 else None),
            established_vote_count=(vote_context["established_vote_count"] if issue_v3 else None),
            certificate_reference={
                "height": tip.index,
                "hash": tip.hash,
                "timestamp": str(tip.timestamp),
            },
            validation_context={
                "originality_evidence": evidence,
                "chain": self.chain,
                **media,
                **({
                    "votes": vote_context["votes"],
                    "reviewer_snapshot": vote_context["snapshot"],
                    "reviewer_status_resolver": self.get_reviewer_status_at_reference,
                    "finalized_reference_validator": self.is_finalized_canonical_reference,
                } if issue_v3 else {}),
            },
        )
        self.lifecycle_timing.mark(submission_id, "certificate_created", certificate_id=certificate.certificate_id)
        return certificate
    def evaluate_submission(self, submission_id, automated_originality_passed=None, now=None):
        submission = self.get_submission(submission_id)
        if not submission:
            raise ValueError(f"Submission not found: {submission_id}")

        evidence = self.ensure_current_originality_evidence(submission_id)

        vote_summary = self.get_submission_votes(submission_id)
        now = now if now is not None else time.time()
        voting_window_expired = now >= submission.created_at + (VOTING_WINDOW_HOURS * 60 * 60)
        issue_v3 = self.get_finalized_head() is not None
        vote_context = self.get_certificate_v3_vote_context(submission_id) if issue_v3 else None
        counted_votes = vote_context["votes"] if issue_v3 else vote_summary["votes"]
        original_votes = sum(vote.get("vote_type") == VOTE_ORIGINAL for vote in counted_votes)
        not_original_votes = sum(vote.get("vote_type") == VOTE_NOT_ORIGINAL for vote in counted_votes)
        decisive_votes = original_votes + not_original_votes
        approval_percentage = original_votes / decisive_votes if decisive_votes else 0
        minimum_votes = MIN_VALID_VOTES if issue_v3 else self.get_voting_threshold(now=now)["minimum_votes"]
        minimum_votes_reached = len(counted_votes) >= minimum_votes
        established_votes_reached = bool(not issue_v3 or vote_context["established_vote_count"] >= MIN_ESTABLISHED_VOTES)
        integer_approval_reached = bool(
            decisive_votes > 0
            and original_votes * 10_000 >= decisive_votes * APPROVAL_THRESHOLD_BPS
        )

        result = {
            "submission_id": submission_id,
            "status": submission.status,
            "minimum_votes": minimum_votes,
            "votes_cast": len(counted_votes),
            "approval_percentage": approval_percentage,
            "voting_window_expired": voting_window_expired,
            "minimum_votes_reached": minimum_votes_reached,
        }
        if issue_v3:
            result.update({
                "certificate_version": MILESTONE5_CERTIFICATE_V3_VERSION,
                "minimum_established_votes": MIN_ESTABLISHED_VOTES,
                "established_vote_count": vote_context["established_vote_count"],
                "established_votes_reached": established_votes_reached,
                "approval_threshold_bps": APPROVAL_THRESHOLD_BPS,
            })

        if submission.status != PENDING:
            result["reason"] = "already_finalized"
            return result

        # A caller may still conservatively fail the legacy compatibility
        # check, but a caller-supplied True can never override canonical
        # pre-vote evidence (especially an exact minted duplicate).
        automated_originality_passed = (
            automated_originality_passed is not False
            and evidence["final_prevote_decision"] != HARD_REJECT
        )

        result["automated_originality_passed"] = automated_originality_passed
        result["originality_evidence_digest"] = evidence["canonical_evidence_digest"]
        result["pre_vote_originality_decision"] = evidence["final_prevote_decision"]

        if not automated_originality_passed:
            submission.transition_to(REJECTED)
            submission.decision_reason = "automated_originality_rejected"
            submission.decision_finalized_at = now
            result["status"] = submission.status
            result["reason"] = "automated_originality_rejected"
            return result

        if issue_v3 and not (minimum_votes_reached and established_votes_reached):
            result["reason"] = "awaiting_fixed_quorum"
            return result

        if not issue_v3 and not (voting_window_expired or minimum_votes_reached):
            result["reason"] = "awaiting_votes_or_window"
            return result

        approval_passed = integer_approval_reached if issue_v3 else approval_percentage >= ORIGINALITY_APPROVAL_THRESHOLD
        if approval_passed:
            self.lifecycle_timing.mark(submission_id, "vote_passed")
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
                self.validate_originality_certificate(certificate, submission)
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
        submission = self._mint_queue_service.add(self._mint_queue_state(), self.storage, submission_id, self.require_valid_certificate_for_submission)
        # Queue admission must be durable before an atomic commit can reread
        # transaction-bound state.  The block transition itself remains a
        # separate all-or-nothing operation below.
        self.save_blockchain()
        self.lifecycle_timing.mark(submission_id, "ready_for_mint")
        return submission
    def _queue_submission_record(self, submission, *, content_object=None, certificate=None):
        return self._mint_queue_service.record(self.storage, submission, content_object=content_object, certificate=certificate, network_name=NETWORK_NAME, extract_text_func=extract_text, certificate_validator=self.validate_originality_certificate)
    def _evaluate_mint_queue_item(self, submission_id):
        return self._mint_queue_service.evaluate(self._mint_queue_state(), self.storage, submission_id, NETWORK_NAME, extract_text, self.validate_originality_certificate)
    def get_mint_queue(self, include_blocked=True, mintable_only=False):
        return self._mint_queue_service.list(self._mint_queue_state(), self.storage, network_name=NETWORK_NAME, include_blocked=include_blocked, mintable_only=mintable_only, extract_text_func=extract_text, certificate_validator=self.validate_originality_certificate)
    def _apply_certified_candidate_in_commit(self, candidate, submission):
        """Apply all durable effects of one already-validated certified block.

        This helper intentionally performs no save.  Its caller owns the sole
        storage transaction, so an exception at any point leaves no durable
        partial block, settlement, reward, or submission transition.
        """
        new_block = candidate["block"]
        self._commit_fault("before_block_persistence")
        self.chain.append(new_block)
        self._commit_fault("after_block_persistence")

        self._commit_fault("during_transaction_settlement")
        self.settle_block_native_transactions(new_block)
        self.pending_transactions = [tx for tx in self.pending_transactions if tx not in candidate.get("valid_transactions", [])]
        for skipped in candidate.get("native_transaction_plan", {}).get("skipped", []):
            tx_id = skipped.get("tx_id")
            if tx_id and self.get_native_transaction(tx_id) is None:
                overlay = getattr(self, "_atomic_commit_native_overlay", {}).get(str(tx_id).lower())
                if overlay is not None:
                    self.native_transactions.append(dict(overlay))
            if tx_id and self.get_native_transaction(tx_id) is not None and skipped.get("reason") != "already_settled":
                self.update_native_transaction_status(tx_id, status="rejected", rejection_reason=skipped.get("reason") or "validation_failed")
        self._commit_fault("after_transaction_settlement")

        # Reward records are immutable block metadata.  The miner credit and
        # derived reward-pool balance are their current durable settlement
        # representation, and therefore belong in this same boundary.
        self._commit_fault("during_reward_settlement")
        total_miner_tips = float(candidate.get("total_miner_tips") or 0)
        miner = new_block.miner
        if miner in self.wallets:
            self.wallets[miner].stored_balance = self.get_balance(miner) + total_miner_tips
        else:
            wallet = Wallet(); wallet.public_key = miner; wallet.private_key = None; wallet.stored_balance = total_miner_tips
            self.wallets[miner] = wallet
        self.image_hashes.add(candidate["image_hash"])
        self.texts.append(candidate["normalized_text"])
        self.recompute_reward_pool_balance(chain=self.chain)
        self._commit_fault("after_rewards_before_submission_minted")

        if submission.status != QUEUED:
            raise ValueError("Certified submission is no longer queued for minting.")
        submission.transition_to(MINTED)
        self.mint_queue[:] = [item for item in self.mint_queue if item != submission.submission_id]
        self._commit_fault("after_submission_mutation_before_canonical_head_update")
        # The immutable chain tail is the canonical-head state in the current
        # storage model; appending this block advances it only on outer commit.
        self._commit_fault("before_transaction_commit")

    def commit_certified_submission(self, submission_id, *, expected_head=None, miner=None, max_block_size_kb=500, validate_meme=True):
        """Authoritatively commit one ready certified submission.

        Candidate construction, native selection, validation, settlement, and
        canonical-head compare-and-swap all run after the storage backend has
        acquired its transaction/lock.  A stale caller receives
        ``StaleCanonicalHeadError`` and must explicitly prepare again.
        """
        request = self._prepare_certified_commit_request(submission_id, miner)
        expected_head = dict(expected_head or self._current_canonical_head())
        memory_snapshot = json.loads(json.dumps(self._serialize_blockchain_state()))
        # Native mempool records and the configurable reward-pool test value
        # are facade-owned inputs.  Preserve their current values while the
        # canonical collections are reread under the storage boundary; native
        # records are still fully revalidated against the locked chain below.
        local_native_transactions = json.loads(json.dumps(self.native_transactions))
        local_reward_pool = self.reward_pool
        replayed = False

        def replay(document):
            nonlocal replayed
            block = self._resolve_certified_commit_replay(document, request)
            if block is None:
                return False
            # A successful replay is deliberately resolved before the expected
            # head check.  A lost response must not turn into a stale-head
            # failure or another state transition.
            self._restore_blockchain_state_document(document)
            replayed = True
            return True

        def mutate(document):
            # The backend has already locked and reread this document.  Restore
            # it so every service observes transaction-bound balances, nonces,
            # mempool records, rewards, and canonical chain state.
            if canonical_head_identity(document) != expected_head:
                raise StaleCanonicalHeadError("The expected canonical head is stale.")
            self._restore_blockchain_state_document(document)
            local_native_by_id = {str(item.get("tx_id") or "").lower(): item for item in local_native_transactions}
            self._atomic_commit_native_overlay = local_native_by_id
            restored_native_ids = {str(item.get("tx_id") or "").lower() for item in self.native_transactions}
            self.native_transactions[:] = [
                local_native_by_id.get(str(item.get("tx_id") or "").lower(), item)
                for item in self.native_transactions
            ]
            self.native_transactions.extend(
                dict(item) for tx_id, item in local_native_by_id.items() if tx_id not in restored_native_ids
            )
            self.reward_pool = local_reward_pool
            submission = self.get_submission(submission_id)
            if submission is None:
                raise ValueError("Submission not found for atomic certified commit.")
            current_request = self._prepare_certified_commit_request(submission_id, miner)
            if current_request != request:
                raise ValueError("Conflicting certified commit: durable submission or certificate changed before commit.")
            if submission.status != QUEUED:
                raise ValueError("Only a queued certified submission can be committed.")
            certificate = self.require_valid_certificate_for_submission(submission)
            queue_record = self._evaluate_mint_queue_item(submission_id)
            if not queue_record.get("mintable"):
                # Preserve the established legacy-content compatibility path;
                # build_candidate still verifies Model A bytes when available.
                certificate = self._resolve_mintable_submission_certificate(submission)
                if certificate is None:
                    raise ValueError(queue_record.get("mint_block_reason") or "Submission is not eligible for minting.")
            reward_recipient = self.resolve_meme_reward_recipient(submission, certificate)
            candidate = self.build_block_candidate(
                image_path=submission.image_path,
                text_content=submission.text_content,
                miner=miner or submission.submitter,
                max_block_size_kb=max_block_size_kb,
                validate_meme=validate_meme,
                certificate=certificate,
                reward_recipient=reward_recipient,
            )
            if candidate is None:
                raise ValueError("Certified block candidate is invalid or exceeds the block limit.")
            self.validate_candidate_block_for_local_acceptance(candidate["block"], current_chain=self.chain)
            self.lifecycle_timing.mark(
                submission_id,
                "proposal_prepared",
                certificate_id=certificate.certificate_id,
                block_height=candidate["block"].index,
                block_hash=candidate["block"].hash,
            )
            self._apply_certified_candidate_in_commit(candidate, submission)
            return self._serialize_blockchain_state()

        committed = False
        try:
            self.storage.atomic_commit_blockchain_document(expected_head, mutate, replay=replay)
            committed = True
            block = self.get_protocol_v1_block_for_submission(submission_id)
            if block is not None:
                self.lifecycle_timing.mark(
                    submission_id,
                    "accepted",
                    certificate_id=block.certificate_id,
                    block_height=block.index,
                    block_hash=block.hash,
                )
            if not replayed:
                # Test seam for the real uncertain-outcome window: persistence
                # has succeeded, but the caller has not received its result.
                self._commit_fault("after_durable_commit_before_response")
        except Exception:
            if not committed:
                self._restore_blockchain_state_document(memory_snapshot)
            raise
        finally:
            self.__dict__.pop("_atomic_commit_native_overlay", None)
        return True

    @staticmethod
    def _is_sqlite_busy_error(error):
        """Whether an operational failure is SQLite's retryable write contention."""
        message = str(error).lower()
        return "database is locked" in message or "database is busy" in message

    def commit_next_certified_submission_with_retry(
        self,
        *,
        miner=None,
        max_block_size_kb=500,
        validate_meme=True,
        max_retries=200,
    ):
        """Commit the canonical ready submission, safely retrying write contention.

        This is the concurrency coordinator for certified minting.  Every
        attempt reloads durable state and selects the first Task 3.2 ordered
        queue item before preparing the expected-head commit.  Consequently a
        stale attempt can never retry a later-ranked submission ahead of the
        current canonical choice.

        The returned counters are deliberately per-call operational results,
        rather than persistent telemetry.  They support callers that need to
        report contention without changing consensus state.
        """
        stale_head_retries = 0
        sqlite_busy_retries = 0
        for attempt in range(max_retries + 1):
            document = self.storage.load_blockchain_state()
            self._restore_blockchain_state_document(document)
            ready = self.get_mint_queue(include_blocked=True, mintable_only=True)
            if not ready:
                return {
                    "committed": False,
                    "submission_id": None,
                    "retries": attempt,
                    "stale_head_retries": stale_head_retries,
                    "sqlite_busy_retries": sqlite_busy_retries,
                }
            submission_id = ready[0]["submission_id"]
            expected_head = self._current_canonical_head()
            try:
                self.commit_certified_submission(
                    submission_id,
                    expected_head=expected_head,
                    miner=miner,
                    max_block_size_kb=max_block_size_kb,
                    validate_meme=validate_meme,
                )
                return {
                    "committed": True,
                    "submission_id": submission_id,
                    "retries": attempt,
                    "stale_head_retries": stale_head_retries,
                    "sqlite_busy_retries": sqlite_busy_retries,
                }
            except StaleCanonicalHeadError:
                stale_head_retries += 1
            except Exception as exc:
                if not self._is_sqlite_busy_error(exc):
                    raise
                sqlite_busy_retries += 1

            if attempt == max_retries:
                break
            # A deterministic, bounded backoff avoids a SQLite write-lock
            # spin without affecting canonical ordering or block contents.
            time.sleep(min(0.001 * (2 ** min(attempt, 5)), 0.032))
        raise RuntimeError(
            "Certified mint retry limit exceeded "
            f"(stale_head_retries={stale_head_retries}, sqlite_busy_retries={sqlite_busy_retries})."
        )

    def _mint_submission_record(self, submission, certificate, miner=None, max_block_size_kb=500, validate_meme=True):
        # Retain the historical seam used by queue-only callers/tests that
        # replace ``add_block`` with a no-op.  Real certified commits always
        # take the atomic coordinator below.
        if getattr(self.add_block, "__func__", None) is not Blockchain.add_block:
            block_added = self.add_block(
                image_path=submission.image_path, text_content=submission.text_content,
                miner=miner or submission.submitter, max_block_size_kb=max_block_size_kb,
                validate_meme=validate_meme, certificate=certificate,
                reward_recipient=self.resolve_meme_reward_recipient(submission, certificate),
            )
            if block_added:
                if submission.submission_id in self.mint_queue:
                    self.mint_queue[:] = [item for item in self.mint_queue if item != submission.submission_id]
                submission.transition_to(MINTED)
            return block_added
        return self.commit_certified_submission(
            submission.submission_id,
            miner=miner or submission.submitter,
            max_block_size_kb=max_block_size_kb,
            validate_meme=validate_meme,
        )

    def mint_next_queued_submission(self, miner=None, max_block_size_kb=500, validate_meme=True):
        if not self.mint_queue:
            raise ValueError("Mint queue is empty.")

        blocked_records = []
        # get_mint_queue() applies MintQueueService.canonical_mint_order_key
        # to every ready entry before this canonical selection step.
        for queue_record in self.get_mint_queue(include_blocked=True):
            submission_id = queue_record["submission_id"]
            submission = self.get_submission(submission_id)
            if submission is not None and submission.status == HARD_REJECTED:
                raise ValueError("Hard rejected submissions cannot become blocks.")
            record = queue_record
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
        submission = self._mint_queue_service.block(self._mint_queue_state(), self.storage, submission_id, reason, notes, blocked_by)
        self.save_blockchain()
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
        return self._block_validation_service.validate_candidate(
            block, self._block_validation_collaborators(), current_chain=current_chain
        )
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
        return self._block_production_service.build_candidate(
            self._block_production_state(),
            self._block_production_collaborators(),
            image_path,
            text_content=text_content,
            miner=miner,
            max_block_size_kb=max_block_size_kb,
            validate_meme=validate_meme,
            certificate=certificate,
            reward_recipient=reward_recipient,
        )
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
        return ForkChoiceService.cumulative_originality_score(chain)

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
        return ForkChoiceService.chain_height(chain_dicts)

    @staticmethod
    def chain_latest_hash(chain_dicts):
        return ForkChoiceService.chain_latest_hash(chain_dicts)

    def compare_chains_by_originality(self, local_chain, candidate_chain):
        comparison = self._fork_choice_service.compare(
            local_chain,
            candidate_chain,
            ForkChoiceCollaborators(self.chain_to_dicts, self.is_chain_valid),
        )
        if comparison["decision"] == "replace_with_candidate" and not self._candidate_preserves_finalized_blocks(candidate_chain):
            return {**comparison, "decision": "invalid_candidate", "preferred": "local", "reason": "violates_finalized_chain"}
        return comparison

    def compare_chain_summaries(
        self, *, local_score, candidate_score, local_height, candidate_height,
        local_latest_hash, candidate_latest_hash,
    ):
        return self._fork_choice_service.compare_summary_metrics(
            local_score=local_score,
            candidate_score=candidate_score,
            local_height=local_height,
            candidate_height=candidate_height,
            local_latest_hash=local_latest_hash,
            candidate_latest_hash=candidate_latest_hash,
        )

    def extract_block_certificate_metadata(self, block_dict):
        return self._block_validation_service.extract_certificate_metadata(block_dict)
    def validate_protocol_v1_block_payload(self, block_dict):
        return self._block_validation_service.validate_protocol_v1_payload(
            block_dict, self._block_validation_collaborators()
        )
    def validate_block_native_transaction_metadata(self, block_dict, *, prior_chain=None):
        self.validate_block_native_transactions(block_dict, prior_chain=prior_chain)
        return True

    def validate_block_with_native_transactions(self, block_dict, *, prior_chain=None):
        return self._block_validation_service.validate_block(
            block_dict, self._block_validation_collaborators(), prior_chain=prior_chain
        )
    def _validate_block_voter_rewards(self, block_dict, *, prior_chain=None):
        return self._block_validation_service.validate_voter_rewards(
            block_dict, self._block_validation_collaborators(), prior_chain=prior_chain
        )
    def validate_block_certificate_metadata(self, block_dict, *, prior_chain=None):
        return self._block_validation_service.validate_certificate_metadata(
            block_dict, self._block_validation_collaborators(), prior_chain=prior_chain
        )
    def is_chain_valid(self, chain):
        """Validate a given chain."""
        return self._block_validation_service.validate_chain(
            chain, self._block_validation_collaborators()
        )
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

    def get_chain_branch_delta(self, old_chain, winning_chain):
        """Return the hash-linked common ancestor and canonical branch delta."""
        return self._canonical_reorg_service.branch_delta(old_chain, winning_chain).to_dict()

    @staticmethod
    def _candidate_preserves_finality_records(candidate_chain, finalized_blocks):
        candidate_by_height = {
            int(Blockchain._block_field(block, "index")): str(
                Blockchain._block_field(block, "hash") or ""
            ).strip().lower()
            for block in candidate_chain or []
        }
        return all(
            candidate_by_height.get(int(record.get("block_height")))
            == str(record.get("block_hash") or "").strip().lower()
            for record in finalized_blocks or []
            if isinstance(record, dict)
        )

    def _canonical_reorg_outbox_builder(self, outcome):
        def build(document):
            report = outcome.get("report") or {}
            requeued = set(report.get("requeued_transaction_ids") or [])
            if not requeued:
                return []
            records = []
            for transaction in document.get("native_transactions", []) or []:
                if transaction.get("tx_id") not in requeued or transaction.get("status") != "mempool":
                    continue
                records.extend(build_native_transaction_outbox_records(
                    transaction,
                    list(document.get("peers", []) or []),
                    sender_node_id=NODE_ID,
                    network_name=NETWORK_NAME,
                    created_at=(
                        transaction.get("admitted_at")
                        or transaction.get("updated_at")
                        or transaction.get("created_at")
                    ),
                ))
            return records

        return build

    @staticmethod
    def _merge_local_noncanonical_reorg_state(document, local_document):
        """Preserve facade-owned metadata that existing commands may not checkpoint eagerly."""
        key_fields = {
            "submissions": ("submission_id",),
            "content_objects": ("content_id", "content_hash"),
            "votes": ("submission_id", "voter"),
            "originality_certificates": ("certificate_id",),
            "originality_evidence": ("submission_id",),
            "access_requests": ("request_id",),
            "access_accounts": ("access_account_id",),
            "wallet_bindings": ("wallet_address",),
            "allowlist_entries": ("allowlist_entry_id",),
            "override_requests": ("override_request_id",),
            "feedback_records": ("feedback_id",),
            "audit_logs": ("audit_id", "created_at", "action"),
        }
        for section, fields in key_fields.items():
            durable_items = list(document.get(section, []) or [])
            local_items = list(local_document.get(section, []) or [])
            positions = {}
            merged = []
            for item in durable_items + local_items:
                if not isinstance(item, dict):
                    continue
                identity = tuple(str(item.get(field) or "") for field in fields)
                if not any(identity):
                    identity = (json.dumps(item, sort_keys=True, default=str),)
                if identity in positions:
                    merged[positions[identity]] = deepcopy(item)
                else:
                    positions[identity] = len(merged)
                    merged.append(deepcopy(item))
            document[section] = merged
        document["mint_queue"] = list(dict.fromkeys(
            list(document.get("mint_queue", []) or [])
            + list(local_document.get("mint_queue", []) or [])
        ))
        document["wallets"] = {
            **dict(document.get("wallets", {}) or {}),
            **dict(local_document.get("wallets", {}) or {}),
        }
        return document

    def adopt_canonical_chain(self, new_chain):
        """Atomically persist a winning chain and every canonical projection.

        SQLite performs the document, relational transaction/lifecycle rows,
        canonical claims, reward claims, and requeued-outbox inserts in one
        ``BEGIN IMMEDIATE`` transaction. JSON uses its existing locked atomic
        document replacement. Live state is published only after that boundary
        returns successfully.
        """
        candidate = [
            block if isinstance(block, Block) else Block.from_dict(block)
            for block in new_chain or []
        ]
        comparison = self.compare_chains_by_originality(self.chain, candidate)
        if comparison["decision"] != "replace_with_candidate":
            report = {
                "adopted": False,
                "reason": comparison["reason"],
                "latest_block_hash": self.get_latest_block().hash if self.chain else None,
                "appended": 0,
            }
            self._last_canonical_reorg_report = report
            return report

        candidate_document = self.chain_to_dicts(candidate)
        local_document = self._serialize_blockchain_state()
        outcome = {}
        self._reorg_fault("before_reorg_rebuild")

        def mutate(document):
            self._merge_local_noncanonical_reorg_state(document, local_document)
            durable_chain = list(document.get("chain", []) or [])
            durable_hashes = [str(block.get("hash") or "").strip().lower() for block in durable_chain]
            candidate_hashes = [str(block.get("hash") or "").strip().lower() for block in candidate_document]
            if durable_hashes == candidate_hashes:
                outcome["report"] = {
                    "adopted": False,
                    "reason": "already_canonical",
                    "latest_block_hash": candidate_hashes[-1] if candidate_hashes else None,
                    "appended": 0,
                }
                return document

            durable_comparison = self._fork_choice_service.compare(
                durable_chain,
                candidate_document,
                ForkChoiceCollaborators(self.chain_to_dicts, self.is_chain_valid),
            )
            if durable_comparison["decision"] != "replace_with_candidate":
                raise CanonicalReorgError(
                    "Durable canonical head changed before the winning branch could be adopted."
                )
            if not self._candidate_preserves_finality_records(
                candidate_document, document.get("finalized_blocks", [])
            ):
                raise CanonicalReorgError(
                    "Winning branch would replace persisted quorum-finalized history."
                )

            replacement, report = self._canonical_reorg_service.rebuild_document(
                document,
                candidate_document,
                self._native_ledger_service,
                fault=self._reorg_fault,
            )
            report.update({
                "reason": durable_comparison["reason"],
                "latest_block_hash": candidate_hashes[-1],
                "appended": len(report["attached_block_hashes"]),
            })
            outcome["report"] = report
            self._reorg_fault("before_reorg_commit")
            return replacement

        document = self.storage.atomic_update_blockchain_document(
            mutate,
            outbox_records=self._canonical_reorg_outbox_builder(outcome),
        )
        self._reorg_fault("after_reorg_commit_before_publish")
        self._restore_blockchain_state_document(document)

        recomputed_originality = []
        for submission_id in outcome.get("report", {}).get(
            "invalidated_originality_submission_ids", []
        ):
            submission = self.get_submission(submission_id)
            if submission is None or submission.status == MINTED:
                continue
            evidence = self.evaluate_prevote_originality(submission_id)
            recomputed_originality.append(evidence["canonical_evidence_digest"])
        if recomputed_originality:
            self.save_blockchain()

        # Legacy transactions are not part of Task 4.7 requeue semantics, but
        # retaining an already-confirmed legacy pool entry would be stale.
        confirmed_legacy = [
            transaction.to_dict() if hasattr(transaction, "to_dict") else dict(transaction)
            for block in candidate
            for transaction in block.transactions
        ]
        self.pending_transactions = [
            pending for pending in self.pending_transactions
            if pending.to_dict() not in confirmed_legacy
        ]
        report = outcome["report"]
        report["recomputed_originality_evidence_digests"] = recomputed_originality
        self._last_canonical_reorg_report = report
        return report

    def replace_chain(self, new_chain):
        """Replace the current chain only when the originality fork-choice rule prefers it."""
        report = self.adopt_canonical_chain(new_chain)
        if report["adopted"]:
            print(f"Debug: Replaced local chain: {report['reason']}.")
            return True
        print(f"Debug: Received chain not selected: {report['reason']}.")
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
