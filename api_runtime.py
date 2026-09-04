"""FastAPI runtime, compatibility seams, schemas, dependencies, and HTTP orchestration.

Routes are declared by the domain modules in :mod:`api_routers`.  This module keeps
the historical globals monkeypatched by the test suite and deployment integrations.
"""

import os
import time
import logging
import hmac
import hashlib
import json
from decimal import Decimal
from typing import Annotated, Any, Literal
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, Form, HTTPException, Depends, Request, Header, Query, Response
from fastapi.responses import JSONResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded

from blockchain import Blockchain
from content import (
    CONTENT_TYPE_MIXED,
    CONTENT_TYPE_TEXT,
    SUPPORTED_CONTENT_MIME_TYPES,
    SUPPORTED_IMAGE_MIME_TYPES,
    TEXT_MIME_TYPE,
    canonicalize_text_content,
    compute_content_hash_bytes,
    detect_mime_type_from_bytes,
    load_content_bytes,
    resolve_local_path,
    sanitize_original_filename,
    validate_caption,
    validate_content_size,
    validate_text_content,
    verify_content_object_payload,
)
from wallet import Wallet
from transaction import Transaction
from submission import APPROVED, HARD_REJECTED, MINTED, PENDING, QUEUED, REJECTED
from utils import extract_text
from validators import (
    ETHEREUM_ADDRESS_PATTERN,
    HEX_32_PATTERN,
    HEX_64_PATTERN,
    MAX_METADATA_FIELD_LENGTH,
    MAX_URL_LENGTH,
    MAX_SUBMISSION_TEXT_LENGTH,
    NETWORK_NAME_PATTERN,
    NODE_ID_PATTERN,
    PUBLIC_KEY_PATTERN,
    is_valid_certificate_id,
    is_valid_content_hash,
    is_valid_block_hash,
    is_valid_node_id,
    is_valid_network_name,
    is_valid_submission_id,
    is_valid_amount,
    is_valid_ethereum_address,
    is_valid_public_key,
    is_valid_wallet_public_key,
)
from config import (
    ACTIVE_USER_LOOKBACK_DAYS,
    API_BASE_URL,
    ACCESS_CONTROL_MODE,
    ACCESS_PUBLIC_LABEL,
    ADMIN_AUTH_ENABLED,
    ADMIN_BOOTSTRAP_TOKEN,
    ADMIN_PASSWORD_HASH,
    ADMIN_SESSION_TTL_SECONDS,
    ADMIN_UI_ENABLED,
    COIN_NAME,
    TICKER,
    MAX_WALLETS_PER_ACCESS_ACCOUNT,
    ENABLE_RATE_LIMITING,
    LOG_DIR,
    LOG_LEVEL,
    PEER_SIGNATURE_WINDOW_SECONDS,
    ENVIRONMENT,
    ENABLE_STRICT_MIME_VALIDATION,
    MAX_CAPTION_LENGTH,
    MAX_CONTENT_FILE_SIZE_BYTES,
    MAX_TEXT_CONTENT_BYTES,
    NODE_DATA_DIR,
    NETWORK_NAME,
    NODE_ID,
    ORIGINALITY_APPROVAL_THRESHOLD,
    PUBLIC_NODE_URL,
    SUBMISSIONS_DIR,
    MAX_FILENAME_LENGTH,
    STORAGE_BACKEND,
    ACCESS_REQUESTS_ENABLED,
    ACCESS_DEV_BYPASS_ENABLED,
    REQUIRE_ACCESS_FOR_APP,
    REQUIRE_ACCESS_FOR_REWARDS,
    REQUIRE_ACCESS_FOR_SUBMISSIONS,
    REQUIRE_ACCESS_FOR_TRANSFERS,
    REQUIRE_ACCESS_FOR_VOTES,
    VOTING_WINDOW_HOURS,
    allow_dev_reset_endpoints,
    allow_private_key_export,
    cors_allowed_origins,
    get_rate_limit,
    peer_replay_protection_enabled,
    is_development,
    is_production,
    public_api_mode_enabled,
    public_demo_mode_enabled,
    peer_auth_required,
    peer_shared_secret,
    peer_shared_secret_is_configured,
    signed_peer_messages_enabled,
    require_peer_auth,
)
from auth import API_KEYS, validate_api_key  # ✅ API authentication
from wallet_auth import (
    WalletAuthManager,
    get_verified_wallet_from_request,
    hash_wallet_message,
    normalize_wallet_address,
    resolve_verified_wallet_from_authorization,
)
from native_transfer import (
    MAX_TRANSFER_MEMO_LENGTH,
    NATIVE_TRANSFER_SIGNATURE_SCHEME,
    NATIVE_TRANSACTION_NONCE_POLICY,
    build_native_transaction,
    hash_transfer_signing_message,
    parse_native_zoid_amount,
    parse_transfer_signing_message,
)
from protocol_v1_native_transfer import (
    looks_like_protocol_v1_native_transfer_message,
    parse_protocol_v1_native_transfer_message,
    resolve_protocol_v1_network_id,
)
from protocol_v1_peer_message import (
    ExpiredPeerMessageError,
    InvalidPeerMessageIdError,
    InvalidPeerMessageTypeError,
    InvalidPeerNonceError,
    InvalidPeerSenderError,
    InvalidPeerSignatureError as ProtocolV1InvalidPeerSignatureError,
    InvalidPeerTimestampError as ProtocolV1InvalidPeerTimestampError,
    MissingProtocolV1PeerHeadersError,
    ProtocolV1PeerAuthContext,
    ProtocolV1PeerMessageError,
    ReplayStateUnavailableError,
    ReplayedPeerMessageError,
    UnsupportedPeerMessageVersionError,
    UnsupportedPeerProtocolVersionError,
    WrongPeerNetworkError,
    build_protocol_v1_peer_request_payload,
    get_protocol_v1_peer_replay_store,
    looks_like_protocol_v1_peer_headers,
    resolve_protocol_v1_peer_network_id,
    verify_protocol_v1_peer_request,
)
from access_control import (
    AccessSessionManager,
    access_decision_for_wallet,
    access_feature_required,
    access_mode_enforces_binding,
    dev_bypass_effective,
    normalize_email,
    normalize_handle,
    normalize_text_field,
    public_access_status_payload,
)
from admin_auth import (
    AdminSessionManager,
    admin_auth_is_configured,
    verify_admin_credential,
)
from ops_support import (
    safe_backup_status,
    safe_build_metadata,
    safe_environment_validation,
    safe_integrity_status,
    safe_latest_block_summary,
    safe_public_status_payload,
    safe_runtime_storage_status,
    sqlite_integrity_status,
)
from review_policy import (
    build_public_policy_summary,
    current_day_window,
    evaluate_review_eligibility,
    load_review_policy_config,
)

from peers import PeerStore, normalize_peer_url
from peer_sync import (
    ChainExtensionError,
    ConflictingVoteError,
    ConflictingTransactionError,
    ConflictingCertificateError,
    DuplicateBlockError,
    DuplicateSubmissionError,
    MalformedBlockError,
    MalformedCertificateError,
    MalformedSubmissionError,
    MalformedTransactionError,
    MalformedVoteError,
    UnauthorizedPeerError,
    UnknownSubmissionError,
    WrongNetworkError,
    broadcast_block_to_peers,
    broadcast_certificate_to_peers,
    broadcast_submission_to_peers,
    broadcast_transaction_to_peers,
    broadcast_vote_to_peers,
    broadcast_votes_to_peers,
    receive_peer_block,
    receive_peer_certificate,
    receive_peer_submission,
    receive_peer_transaction,
    receive_peer_vote,
    register_peer_operation,
    ExpiredPeerSignatureError,
    InvalidPeerSignatureError,
    InvalidPeerTimestampError,
    MissingSignedPeerHeadersError,
    ReplayedPeerNonceError,
    verify_peer_signature,
    sync_chain_from_peers,
    sync_missing_content,
)

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "api.log"),
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
APP_STARTED_AT = time.time()

# code?

DEV_ENDPOINT_WARNING = (
    "Development-only endpoint. Never expose this publicly."
)

WalletPublicKey = Annotated[str, Field(pattern=PUBLIC_KEY_PATTERN, min_length=66, max_length=66)]
NodeIdValue = Annotated[str, Field(pattern=NODE_ID_PATTERN, min_length=1, max_length=64)]
NetworkNameValue = Annotated[str, Field(pattern=NETWORK_NAME_PATTERN, min_length=3, max_length=64)]
SubmissionIdValue = Annotated[str, Field(pattern=HEX_32_PATTERN, min_length=32, max_length=32)]
CertificateIdValue = Annotated[str, Field(pattern=HEX_64_PATTERN, min_length=64, max_length=64)]
BlockHashValue = Annotated[str, Field(pattern=HEX_64_PATTERN, min_length=64, max_length=64)]
ContentHashValue = Annotated[str, Field(pattern=HEX_64_PATTERN, min_length=64, max_length=64)]
VoteTypeValue = Literal["original", "not_original", "unsure"]
SubmissionStatusValue = Literal["pending", "approved", "rejected", "minted", "queued", "hard_rejected"]
EthereumWalletAddressValue = Annotated[str, Field(pattern=ETHEREUM_ADDRESS_PATTERN, min_length=42, max_length=42)]


class _StrictBodyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PeerTransactionPayload(_StrictBodyModel):
    sender: Annotated[str, Field(min_length=1, max_length=128)]
    recipient: Annotated[str, Field(min_length=1, max_length=128)]
    amount: Annotated[float, Field(gt=0)]
    tip: Annotated[float, Field(ge=0)] = 0
    payload_size_kb: Annotated[float, Field(ge=0)] = 0
    created_at: Annotated[float, Field(ge=0)] | None = None
    signature: str | None = Field(default=None, max_length=2048)


class PeerSubmissionPayload(_StrictBodyModel):
    submission_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    image_path: str | None = None
    text_content: str | None = None
    submitter: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    status: str = "pending"
    created_at: Annotated[float, Field(ge=0)] | None = None
    hard_reject_reason: str | None = Field(default=None, max_length=MAX_METADATA_FIELD_LENGTH)
    content_hash: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    content_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    certificate_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    decision_reason: str | None = Field(default=None, max_length=MAX_METADATA_FIELD_LENGTH)
    decision_finalized_at: Annotated[float, Field(ge=0)] | None = None
    mint_blocked: bool | None = None
    mint_block_reason: str | None = Field(default=None, max_length=MAX_METADATA_FIELD_LENGTH)
    mint_blocked_at: Annotated[float, Field(ge=0)] | None = None
    mint_blocked_by: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    mint_block_notes: str | None = Field(default=None, max_length=MAX_METADATA_FIELD_LENGTH)
    creator_wallet_address: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    signature_scheme: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    submission_signature: Annotated[str, Field(min_length=1, max_length=4096)] | None = None
    submission_message: Annotated[str, Field(min_length=1, max_length=4096)] | None = None
    signed_message_hash: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    submission_nonce: Annotated[str, Field(min_length=1, max_length=256)] | None = None
    signed_at: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    identity_source: Annotated[str, Field(min_length=1, max_length=64)] | None = None


class PeerVotePayload(_StrictBodyModel):
    vote_version: Annotated[int, Field(ge=1)] | None = None
    protocol_version: Annotated[int, Field(ge=1)] | None = None
    network_id: Annotated[str, Field(min_length=3, max_length=128)] | None = None
    submission_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    voter: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    vote_type: str | None = None
    vote_value: str | None = None
    content_hash: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    voter_wallet_address: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    signature_scheme: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    vote_signature: Annotated[str, Field(min_length=1, max_length=4096)] | None = None
    vote_message: Annotated[str, Field(min_length=1, max_length=4096)] | None = None
    signed_message_hash: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    vote_nonce: Annotated[str, Field(min_length=1, max_length=256)] | None = None
    vote_issued_at: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    vote_expires_at: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    signed_at: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    identity_source: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    created_at: Annotated[float, Field(ge=0)] | None = None
    vote_timestamp: Annotated[float, Field(ge=0)] | None = None


class PeerCertificatePayload(_StrictBodyModel):
    certificate_version: Annotated[int, Field(ge=1)] | None = None
    protocol_version: Annotated[int, Field(ge=1)] | None = None
    network_id: Annotated[str, Field(min_length=3, max_length=128)] | None = None
    certificate_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    submission_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    content_hash: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    content_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    creator_wallet: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    vote_total: Annotated[int, Field(ge=0)] | None = None
    decisive_vote_total: Annotated[int, Field(ge=0)] | None = None
    original_votes: Annotated[int, Field(ge=0)] | None = None
    not_original_votes: Annotated[int, Field(ge=0)] | None = None
    unsure_votes: Annotated[int, Field(ge=0)] | None = None
    approval_percentage: Annotated[float, Field(ge=0)] | None = None
    minimum_votes_required: Annotated[int, Field(ge=0)] | None = None
    approved_at: Annotated[float, Field(ge=0)] | None = None
    network_name: NetworkNameValue | None = None
    issuing_node_id: NodeIdValue | None = None
    vote_hash: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    originality_score: Annotated[float, Field(ge=0)] | None = None
    approval_threshold: Annotated[float, Field(ge=0)] | None = None


class PeerBlockPayload(_StrictBodyModel):
    block_version: Annotated[int, Field(ge=1)] | None = None
    network_id: Annotated[str, Field(min_length=3, max_length=128)] | None = None
    media_hash: Annotated[str, Field(min_length=64, max_length=64)] | None = None
    media_bytes: dict[str, Any] | None = None
    index: Annotated[int, Field(ge=0)] | None = None
    previous_hash: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    timestamp: Annotated[float, Field(ge=0)] | None = None
    transactions: list[PeerTransactionPayload] | None = None
    native_transactions: list[dict[str, Any]] | None = None
    transaction_ids: list[Annotated[str, Field(min_length=1, max_length=128)]] | None = None
    transaction_count: Annotated[int, Field(ge=0)] | None = None
    transactions_hash: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    miner: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    meme: dict[str, Any] | str | None = None
    hash: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    submission_id: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    certificate_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    content_hash: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    content_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    content_type: Annotated[str, Field(min_length=1, max_length=32)] | None = None
    mime_type: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    creator_wallet: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    vote_hash: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    approval_percentage: Annotated[float, Field(ge=0)] | None = None
    decisive_vote_total: Annotated[int, Field(ge=0)] | None = None
    minimum_votes_required: Annotated[int, Field(ge=0)] | None = None
    approved_at: Annotated[float, Field(ge=0)] | None = None
    originality_score: Annotated[float, Field(ge=0)] | None = None
    reward_type: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    reward_recipient: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    reward_amount: Annotated[float, Field(ge=0)] | None = None
    reward_source: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    minted_at: Annotated[float, Field(ge=0)] | None = None
    voter_rewards: list[dict[str, Any]] | None = None


class MintBlockRequest(_StrictBodyModel):
    reason: Annotated[str, Field(min_length=1, max_length=MAX_METADATA_FIELD_LENGTH)]
    notes: Annotated[str | None, Field(default=None, max_length=MAX_METADATA_FIELD_LENGTH)] = None


class MintQueueCleanupRequest(_StrictBodyModel):
    dry_run: bool = True
    block_unmintable: bool = False


class PeerRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: NodeIdValue
    url: Annotated[str, Field(min_length=8, max_length=MAX_URL_LENGTH)]
    network_name: NetworkNameValue


class PeerSubmissionReceive(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin_node_id: NodeIdValue
    network_name: NetworkNameValue
    submission: PeerSubmissionPayload


class PeerVoteReceive(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin_node_id: NodeIdValue
    network_name: NetworkNameValue
    vote_version: Annotated[int, Field(ge=1)] | None = None
    protocol_version: Annotated[int, Field(ge=1)] | None = None
    network_id: Annotated[str, Field(min_length=3, max_length=128)] | None = None
    submission_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    voter: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    vote_type: str | None = None
    vote_value: str | None = None
    content_hash: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    voter_wallet_address: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    signature_scheme: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    vote_signature: Annotated[str, Field(min_length=1, max_length=4096)] | None = None
    vote_message: Annotated[str, Field(min_length=1, max_length=4096)] | None = None
    signed_message_hash: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    vote_nonce: Annotated[str, Field(min_length=1, max_length=256)] | None = None
    vote_issued_at: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    vote_expires_at: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    signed_at: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    identity_source: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    created_at: Annotated[float, Field(ge=0)] | None = None
    vote_timestamp: Annotated[float, Field(ge=0)] | None = None


class PeerBlockReceive(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin_node_id: NodeIdValue
    network_name: NetworkNameValue
    block: PeerBlockPayload
    related_submission_id: SubmissionIdValue | None = None
    certificate: PeerCertificatePayload | None = None


class PeerCertificateReceive(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin_node_id: NodeIdValue
    network_name: NetworkNameValue
    certificate: PeerCertificatePayload


class PeerTransactionReceive(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin_node_id: NodeIdValue
    network_name: NetworkNameValue
    transaction: dict[str, Any]


class TextContentUpload(_StrictBodyModel):
    text_content: Annotated[str, Field(min_length=1)]
    submitted_by: Annotated[str, Field(min_length=1, max_length=128)]
    caption: Annotated[str | None, Field(max_length=MAX_CAPTION_LENGTH)] = None


class WalletChallengeRequest(_StrictBodyModel):
    wallet_address: EthereumWalletAddressValue


class WalletVerifyRequest(_StrictBodyModel):
    wallet_address: EthereumWalletAddressValue
    message: Annotated[str, Field(min_length=1, max_length=4096)]
    signature: Annotated[str, Field(min_length=1, max_length=4096)]


class WalletSubmissionChallengeRequest(_StrictBodyModel):
    wallet_address: EthereumWalletAddressValue
    content_hash: ContentHashValue
    content_id: Annotated[str | None, Field(min_length=32, max_length=32, pattern=HEX_32_PATTERN)] = None
    caption: Annotated[str | None, Field(max_length=MAX_CAPTION_LENGTH)] = None


class WalletVoteChallengeRequest(_StrictBodyModel):
    wallet_address: EthereumWalletAddressValue
    submission_id: SubmissionIdValue
    vote: VoteTypeValue


class WalletTransferChallengeRequest(_StrictBodyModel):
    from_address: EthereumWalletAddressValue
    to_address: EthereumWalletAddressValue
    amount: Annotated[str, Field(min_length=1, max_length=64)]
    fee: Annotated[str, Field(min_length=1, max_length=64)] = "0"
    memo: Annotated[str | None, Field(max_length=MAX_TRANSFER_MEMO_LENGTH)] = None
    nonce: Annotated[int | None, Field(ge=1)] = None


class WalletTransferSubmitRequest(_StrictBodyModel):
    from_address: EthereumWalletAddressValue
    to_address: EthereumWalletAddressValue
    amount: Annotated[str, Field(min_length=1, max_length=64)]
    fee: Annotated[str, Field(min_length=1, max_length=64)] = "0"
    memo: Annotated[str | None, Field(max_length=MAX_TRANSFER_MEMO_LENGTH)] = None
    message: Annotated[str, Field(min_length=1, max_length=4096)]
    signature: Annotated[str, Field(min_length=1, max_length=4096)]
    admit_to_mempool: bool = False


class AccessRequestCreate(_StrictBodyModel):
    name: Annotated[str, Field(min_length=1, max_length=128)]
    email: Annotated[str, Field(min_length=3, max_length=320)]
    handle: Annotated[str | None, Field(default=None, max_length=128)] = None
    reason: Annotated[str, Field(min_length=1, max_length=1000)]
    notes: Annotated[str | None, Field(default=None, max_length=2000)] = None


class AccessLoginRequest(_StrictBodyModel):
    access_code: Annotated[str, Field(min_length=3, max_length=128)]


class AccessBindWalletRequest(_StrictBodyModel):
    wallet_address: Annotated[str | None, Field(default=None, max_length=128)] = None


class AdminLoginRequest(_StrictBodyModel):
    password: Annotated[str, Field(min_length=1, max_length=512)]


class AdminApproveAccessRequest(_StrictBodyModel):
    reviewed_by: Annotated[str, Field(min_length=1, max_length=128)] = "operator"
    operator_notes: Annotated[str | None, Field(default=None, max_length=2000)] = None
    max_wallets: Annotated[int, Field(ge=1, le=50)] = 1


class AdminRejectAccessRequest(_StrictBodyModel):
    reviewed_by: Annotated[str, Field(min_length=1, max_length=128)] = "operator"
    operator_notes: Annotated[str | None, Field(default=None, max_length=2000)] = None


class AdminCreateInviteRequest(_StrictBodyModel):
    name: Annotated[str, Field(min_length=1, max_length=128)]
    email: Annotated[str, Field(min_length=3, max_length=320)]
    handle: Annotated[str | None, Field(default=None, max_length=128)] = None
    notes: Annotated[str | None, Field(default=None, max_length=2000)] = None
    reviewed_by: Annotated[str, Field(min_length=1, max_length=128)] = "operator"
    operator_notes: Annotated[str | None, Field(default=None, max_length=2000)] = None
    max_wallets: Annotated[int, Field(ge=1, le=50)] = 1


class AdminAllowlistCreateRequest(_StrictBodyModel):
    scope: Annotated[str, Field(min_length=3, max_length=32)]
    subject_type: Annotated[str, Field(min_length=4, max_length=32)]
    subject_value: Annotated[str, Field(min_length=1, max_length=320)]
    reason: Annotated[str | None, Field(default=None, max_length=2000)] = None
    expires_at: Annotated[str | None, Field(default=None, max_length=64)] = None


class AdminAllowlistUpdateRequest(_StrictBodyModel):
    scope: Annotated[str | None, Field(default=None, min_length=3, max_length=32)] = None
    subject_type: Annotated[str | None, Field(default=None, min_length=4, max_length=32)] = None
    subject_value: Annotated[str | None, Field(default=None, min_length=1, max_length=320)] = None
    status: Annotated[str | None, Field(default=None, min_length=6, max_length=16)] = None
    reason: Annotated[str | None, Field(default=None, max_length=2000)] = None
    expires_at: Annotated[str | None, Field(default=None, max_length=64)] = None


class AdminAllowlistRevokeRequest(_StrictBodyModel):
    revoked_reason: Annotated[str | None, Field(default=None, max_length=2000)] = None


class AdminAllowlistReactivateRequest(_StrictBodyModel):
    reason: Annotated[str | None, Field(default=None, max_length=2000)] = None


class OverrideRequestCreate(_StrictBodyModel):
    requested_scope: Annotated[str, Field(min_length=3, max_length=32)]
    name: Annotated[str | None, Field(default=None, max_length=128)] = None
    email: Annotated[str | None, Field(default=None, max_length=320)] = None
    handle: Annotated[str | None, Field(default=None, max_length=128)] = None
    wallet_address: Annotated[str | None, Field(default=None, max_length=128)] = None
    access_account_id: Annotated[str | None, Field(default=None, max_length=128)] = None
    reason: Annotated[str, Field(min_length=1, max_length=2000)]
    current_page: Annotated[str | None, Field(default=None, max_length=240)] = None
    detected_blocked_reason: Annotated[str | None, Field(default=None, max_length=240)] = None


class AdminOverrideRequestDecision(_StrictBodyModel):
    reviewed_by: Annotated[str, Field(min_length=1, max_length=128)] = "operator"
    admin_note: Annotated[str | None, Field(default=None, max_length=2000)] = None
    resolved_scope: Annotated[str | None, Field(default=None, min_length=3, max_length=32)] = None


class FeedbackCreateRequest(_StrictBodyModel):
    type: Annotated[str, Field(min_length=3, max_length=64)]
    title: Annotated[str, Field(min_length=1, max_length=160)]
    description: Annotated[str, Field(min_length=1, max_length=5000)]
    name: Annotated[str | None, Field(default=None, max_length=128)] = None
    email: Annotated[str | None, Field(default=None, max_length=320)] = None
    handle: Annotated[str | None, Field(default=None, max_length=128)] = None
    current_page: Annotated[str | None, Field(default=None, max_length=240)] = None
    current_flow: Annotated[str | None, Field(default=None, max_length=128)] = None
    wallet_address: Annotated[str | None, Field(default=None, max_length=128)] = None
    access_account_id: Annotated[str | None, Field(default=None, max_length=128)] = None
    browser_metadata: dict[str, Any] | None = None
    eligibility_snapshot: dict[str, Any] | None = None
    viewport_width: Annotated[int | None, Field(default=None, ge=0, le=20000)] = None
    viewport_height: Annotated[int | None, Field(default=None, ge=0, le=20000)] = None
    is_mobile: bool | None = None


class AdminFeedbackUpdateRequest(_StrictBodyModel):
    status: Annotated[str | None, Field(default=None, min_length=2, max_length=32)] = None
    priority: Annotated[str | None, Field(default=None, min_length=2, max_length=16)] = None
    reviewed_by: Annotated[str, Field(min_length=1, max_length=128)] = "operator"
    admin_note: Annotated[str | None, Field(default=None, max_length=2000)] = None


class AdminFeedbackStatusRequest(_StrictBodyModel):
    status: Annotated[str, Field(min_length=2, max_length=32)]
    reviewed_by: Annotated[str, Field(min_length=1, max_length=128)] = "operator"


class AdminFeedbackNoteRequest(_StrictBodyModel):
    note: Annotated[str, Field(min_length=1, max_length=2000)]
    created_by: Annotated[str, Field(min_length=1, max_length=128)] = "operator"


def _short_key(public_key):
    key = str(public_key or "")
    if len(key) <= 18:
        return key or "unknown"
    return f"{key[:10]}...{key[-8:]}"


def _wallet_public_response(public_key, wallet):
    return {
        "public_key": public_key,
        "balance": blockchain.get_balance(public_key),
    }


def _safe_content_metadata(content_object):
    return {
        "content_id": content_object.content_id,
        "content_hash": content_object.content_hash,
        "hash_scheme": content_object.hash_scheme,
        "content_type": content_object.content_type,
        "mime_type": content_object.mime_type,
        "file_size_bytes": content_object.file_size_bytes,
        "storage_status": content_object.storage_status,
        "verified_at": content_object.verified_at,
        "verification_error": content_object.verification_error,
        "caption": content_object.caption,
        "submitted_by": content_object.submitted_by,
        "created_at": content_object.created_at,
        "network_name": content_object.network_name,
    }


def _content_download_url(content_object):
    if content_object is None:
        return None
    if content_object.storage_status not in {"local", "verified"}:
        return None
    return f"/content/{content_object.content_hash}"


def _block_media_download_url(block):
    if getattr(block, "media_bytes", None) is None:
        return None
    block_hash = str(getattr(block, "hash", "") or "").strip()
    if not block_hash:
        return None
    return f"/blocks/{block_hash}/media"


def _validate_uploaded_image_payload(image: UploadFile, file_bytes: bytes) -> tuple[str, str]:
    try:
        safe_original_filename = sanitize_original_filename(image.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not safe_original_filename:
        raise HTTPException(status_code=400, detail="Invalid image format. Allowed formats: jpg, jpeg, png, webp")

    declared_mime_type = (image.content_type or "").strip().lower() or None
    if declared_mime_type == "application/octet-stream":
        declared_mime_type = None
    if declared_mime_type is not None and declared_mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
        raise HTTPException(status_code=400, detail="Invalid image format. Allowed formats: jpg, jpeg, png, webp")

    detected_mime_type = detect_mime_type_from_bytes(file_bytes)
    if detected_mime_type is None or detected_mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
        raise HTTPException(status_code=400, detail="Invalid image format. Allowed formats: jpg, jpeg, png, webp")

    if (
        declared_mime_type
        and declared_mime_type != detected_mime_type
        and ENABLE_STRICT_MIME_VALIDATION
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Declared mime_type {declared_mime_type!r} does not match detected mime_type "
                f"{detected_mime_type!r}."
            ),
        )

    return safe_original_filename, detected_mime_type


def _serialize_submission(submission):
    content_object = blockchain.get_content_object_by_hash(submission.content_hash) if submission.content_hash else None
    lifecycle = blockchain.get_submission_protocol_v1_lifecycle(submission.submission_id)
    body = {
        "submission_id": submission.submission_id,
        "text_content": submission.text_content,
        "submitter": submission.submitter,
        "creator_wallet_address": submission.creator_wallet_address or submission.submitter,
        "identity_source": submission.identity_source,
        "signature_scheme": submission.signature_scheme,
        "signed_at": submission.signed_at,
        "signed_message_hash": submission.signed_message_hash,
        "status": submission.status,
        "created_at": submission.created_at,
        "hard_reject_reason": submission.hard_reject_reason,
        "content_hash": submission.content_hash,
        "content_id": submission.content_id,
        "certificate_id": submission.certificate_id,
        "decision_reason": getattr(submission, "decision_reason", None),
        "decision_finalized_at": getattr(submission, "decision_finalized_at", None),
        "submission_status": submission.status,
        "certificate_status": lifecycle["certificate_status"],
        "mint_status": lifecycle["mint_status"],
        "block_status": lifecycle["block_status"],
        "confirmations": lifecycle["confirmations"],
        "confirmed": lifecycle["confirmed"],
        "finalized": lifecycle["finalized"],
        "protocol_v1_lifecycle": lifecycle,
        "voter_reward_summary": blockchain.get_submission_voter_reward_summary(submission.submission_id),
    }
    if content_object is not None:
        body["content_type"] = content_object.content_type
        body["storage_status"] = content_object.storage_status
        download_url = _content_download_url(content_object)
        if download_url:
            body["download_url"] = download_url
    return body


def _serialize_certificate(certificate):
    content_object = blockchain.get_content_object_by_hash(certificate.content_hash) if certificate.content_hash else None
    body = certificate.to_dict()
    if content_object is not None:
        body["content_type"] = content_object.content_type
        body["mime_type"] = content_object.mime_type
        body["storage_status"] = content_object.storage_status
        download_url = _content_download_url(content_object)
        if download_url:
            body["download_url"] = download_url
    return body


def _serialize_block(block, *, include_media_bytes=False):
    body = block.to_dict(include_media_bytes=include_media_bytes)
    chain_state = blockchain.get_block_chain_state(block)
    body["transaction_count"] = body.get("transaction_count", len(body.get("native_transactions", []) or []))
    body["transaction_ids"] = body.get("transaction_ids", [tx.get("tx_id") for tx in body.get("native_transactions", []) if tx.get("tx_id")])
    body["is_genesis"] = body.get("index") == 0
    body["object_type"] = "genesis" if body["is_genesis"] else "block"
    body["block_status"] = chain_state["phase"]
    body["accepted"] = chain_state["accepted"]
    body["canonical"] = chain_state["canonical"]
    body["confirmations"] = chain_state["confirmations"]
    body["confirmed"] = chain_state["confirmed"]
    body["finalized"] = chain_state["finalized"]
    body["confirmation_depth"] = chain_state["confirmation_depth"]
    body["finality_depth"] = chain_state["finality_depth"]
    body["finality_model"] = chain_state["finality_model"]
    body["finality_scope"] = chain_state["finality_scope"]
    if body["is_genesis"]:
        body["canonical_genesis_hash"] = blockchain.public_testnet_v1_genesis_hash()
    if not include_media_bytes and getattr(block, "media_bytes", None) is not None:
        body["media_embedded"] = True
        body["media_size_bytes"] = len(block.media_bytes)
        body["storage_status"] = body.get("storage_status") or "embedded"
        download_url = _block_media_download_url(block)
        if download_url:
            body["download_url"] = download_url
    content_hash = body.get("content_hash")
    content_object = blockchain.get_content_object_by_hash(content_hash) if content_hash else None
    if content_object is not None:
        body["content_id"] = body.get("content_id") or content_object.content_id
        body["content_type"] = body.get("content_type") or content_object.content_type
        body["mime_type"] = body.get("mime_type") or content_object.mime_type
        body["storage_status"] = content_object.storage_status
        download_url = _content_download_url(content_object)
        if download_url:
            body["download_url"] = download_url
    return body


def _serialize_transfer_intent(transfer_intent):
    status = transfer_intent.get("status")
    status_detail = "Signed native ZOID transfer recorded. Not settled yet."
    if status == "mempool":
        status_detail = "In local mempool. Not settled yet."
    elif status == "validated_pending":
        status_detail = "Signed native ZOID transfer recorded. Not settled yet."
    elif status == "included":
        status_detail = "Included in meme-mined block."
    elif status == "settled":
        status_detail = "Settled on ZoidbergChain."
    elif status == "rejected":
        status_detail = "Rejected during transaction validation. Not settled."
    elif status == "expired":
        status_detail = "Expired before mempool inclusion. Not settled."
    return {
        "transfer_id": transfer_intent.get("transfer_id"),
        "tx_id": transfer_intent.get("tx_id"),
        "nonce": transfer_intent.get("transfer_nonce"),
        "status": transfer_intent.get("status"),
        "from_address": transfer_intent.get("from_address"),
        "to_address": transfer_intent.get("to_address"),
        "amount": transfer_intent.get("amount"),
        "fee": transfer_intent.get("fee"),
        "memo": transfer_intent.get("memo"),
        "network": transfer_intent.get("network"),
        "transaction_version": transfer_intent.get("transaction_version"),
        "protocol_version": transfer_intent.get("protocol_version"),
        "network_id": transfer_intent.get("network_id"),
        "signature_scheme": transfer_intent.get("signature_scheme"),
        "signed_message_hash": transfer_intent.get("signed_message_hash"),
        "transfer_nonce": transfer_intent.get("transfer_nonce"),
        "signed_at": transfer_intent.get("signed_at"),
        "created_at": transfer_intent.get("created_at"),
        "settlement_state": "non_final",
        "status_detail": status_detail,
    }


def _serialize_native_transaction(transaction):
    status = transaction.get("status")
    status_detail = "Signed native ZOID transfer recorded. Not settled yet."
    if status == "mempool":
        status_detail = "In local mempool. Not settled yet."
    elif status == "validated_pending":
        status_detail = "Signed native ZOID transfer recorded. Not settled yet."
    elif status == "included":
        status_detail = "Included in meme-mined block."
    elif status == "settled":
        status_detail = "Settled on ZoidbergChain."
    elif status == "rejected":
        status_detail = "Rejected during transaction validation. Not settled."
    elif status == "expired":
        status_detail = "Expired before inclusion. Not settled."
    return {
        "tx_id": transaction.get("tx_id"),
        "transaction_type": transaction.get("transaction_type"),
        "status": transaction.get("status"),
        "from_address": transaction.get("from_address"),
        "to_address": transaction.get("to_address"),
        "amount": transaction.get("amount"),
        "fee": transaction.get("fee"),
        "nonce": transaction.get("nonce"),
        "memo": transaction.get("memo"),
        "network": transaction.get("network"),
        "transaction_version": transaction.get("transaction_version"),
        "protocol_version": transaction.get("protocol_version"),
        "network_id": transaction.get("network_id"),
        "timestamp": transaction.get("timestamp"),
        "created_at": transaction.get("created_at"),
        "updated_at": transaction.get("updated_at"),
        "admitted_at": transaction.get("admitted_at"),
        "included_block_hash": transaction.get("included_block_hash"),
        "included_block_height": transaction.get("included_block_height"),
        "settled_at": transaction.get("settled_at"),
        "rejection_reason": transaction.get("rejection_reason"),
        "settlement_state": "non_final" if status != "settled" else "settled",
        "status_detail": status_detail,
    }


def _peer_transaction_error_response(status_code: int, *, tx_id=None, reason: str, message: str):
    return JSONResponse(
        status_code=status_code,
        content={
            "accepted": False,
            "tx_id": tx_id,
            "reason": reason,
            "message": message,
        },
    )


def _build_submitted_native_transaction_preview(payload: WalletTransferSubmitRequest):
    if looks_like_protocol_v1_native_transfer_message(payload.message):
        signed_transfer = parse_protocol_v1_native_transfer_message(
            payload.message,
            expected_network_id=resolve_protocol_v1_network_id(network_name=NETWORK_NAME),
        )
    else:
        signed_transfer = parse_transfer_signing_message(
            payload.message,
            network_name=NETWORK_NAME,
        )
    normalized_from = normalize_wallet_address(payload.from_address)
    normalized_to = normalize_wallet_address(payload.to_address)
    normalized_memo = str(payload.memo or "").strip() or None
    normalized_amount = parse_native_zoid_amount(payload.amount, allow_zero=False)
    normalized_fee = parse_native_zoid_amount(payload.fee, allow_zero=True)

    signed_from = signed_transfer["from_address"] if isinstance(signed_transfer, dict) else signed_transfer.from_address
    signed_to = signed_transfer["to_address"] if isinstance(signed_transfer, dict) else signed_transfer.to_address
    signed_amount = signed_transfer["amount"] if isinstance(signed_transfer, dict) else signed_transfer.amount
    signed_fee = signed_transfer["fee"] if isinstance(signed_transfer, dict) else signed_transfer.fee
    signed_memo = signed_transfer["memo"] if isinstance(signed_transfer, dict) else signed_transfer.memo
    signed_nonce = signed_transfer["nonce"] if isinstance(signed_transfer, dict) else signed_transfer.nonce
    signed_timestamp = signed_transfer["timestamp"] if isinstance(signed_transfer, dict) else signed_transfer.timestamp
    signed_transaction_version = signed_transfer.get("transaction_version") if isinstance(signed_transfer, dict) else signed_transfer.transaction_version
    signed_protocol_version = signed_transfer.get("protocol_version") if isinstance(signed_transfer, dict) else signed_transfer.protocol_version
    signed_network_id = signed_transfer.get("network_id") if isinstance(signed_transfer, dict) else signed_transfer.network_id

    if normalized_from != signed_from:
        raise ValueError("from_address does not match the signed transfer message.")
    if normalized_to != signed_to:
        raise ValueError("to_address does not match the signed transfer message.")
    if normalized_amount != signed_amount:
        raise ValueError("amount does not match the signed transfer message.")
    if normalized_fee != signed_fee:
        raise ValueError("fee does not match the signed transfer message.")
    if normalized_memo != signed_memo:
        raise ValueError("memo does not match the signed transfer message.")

    return build_native_transaction(
        network=NETWORK_NAME,
        transaction_version=signed_transaction_version,
        protocol_version=signed_protocol_version,
        network_id=signed_network_id,
        from_address=signed_from,
        to_address=signed_to,
        amount=signed_amount,
        fee=signed_fee,
        nonce=signed_nonce,
        memo=signed_memo,
        timestamp=signed_timestamp,
        signature=payload.signature,
        signature_scheme=NATIVE_TRANSFER_SIGNATURE_SCHEME,
        signed_message=payload.message,
        signed_message_hash=hash_transfer_signing_message(payload.message),
        status="signed_pending",
    )


def _serialize_wallet_transaction_history_entry(transaction, wallet_address: str):
    normalized_wallet = normalize_wallet_address(wallet_address)
    from_address = normalize_wallet_address(transaction.get("from_address"))
    direction = "incoming"
    if normalized_wallet and from_address == normalized_wallet:
        direction = "outgoing"
    body = _serialize_native_transaction(transaction)
    body["direction"] = direction
    return body


def _serialize_account_submission(submission):
    body = _serialize_submission(submission)
    return {
        "submission_id": body.get("submission_id"),
        "content_hash": body.get("content_hash"),
        "content_id": body.get("content_id"),
        "status": body.get("status"),
        "certificate_id": body.get("certificate_id"),
        "creator_wallet_address": body.get("creator_wallet_address"),
        "created_at": body.get("created_at"),
        "signed": bool(body.get("signature_scheme") or body.get("identity_source") == "metamask_signed"),
        "signed_at": body.get("signed_at"),
        "signature_scheme": body.get("signature_scheme"),
    }


def _serialize_account_vote(vote):
    return {
        "vote_version": vote.get("vote_version"),
        "protocol_version": vote.get("protocol_version"),
        "network_id": vote.get("network_id"),
        "submission_id": vote.get("submission_id"),
        "vote": vote.get("vote_type"),
        "vote_type": vote.get("vote_type"),
        "content_hash": vote.get("content_hash"),
        "voter_wallet_address": vote.get("voter_wallet_address") or vote.get("voter"),
        "created_at": vote.get("created_at"),
        "signed": bool(vote.get("signature_scheme") or vote.get("identity_source") == "metamask_signed"),
        "signed_at": vote.get("signed_at"),
        "signature_scheme": vote.get("signature_scheme"),
        "identity_source": vote.get("identity_source"),
    }


def _public_content_upload_response(content_object):
    metadata = _safe_content_metadata(content_object)
    metadata["download_url"] = f"/content/{content_object.content_hash}"
    return metadata


def _peer_safe_content_metadata(content_object):
    metadata = _safe_content_metadata(content_object)
    byte_hash = (content_object.metadata or {}).get("byte_hash")
    if isinstance(byte_hash, str) and byte_hash.strip():
        metadata["byte_hash"] = byte_hash.strip()
    return metadata


def _require_registered_submitter(submitted_by):
    if not is_valid_public_key(submitted_by, blockchain.wallets):
        raise HTTPException(status_code=400, detail="Invalid submitter public key.")


def _normalize_supported_user_identity(identity: str, *, field_name: str = "wallet identity") -> str:
    candidate = str(identity or "").strip()
    normalized_wallet = normalize_wallet_address(candidate)
    if normalized_wallet:
        return normalized_wallet
    if is_valid_public_key(candidate, blockchain.wallets):
        return candidate
    raise HTTPException(
        status_code=400,
        detail=f"Invalid {field_name}. Expected a registered development public key or an Ethereum-style 0x address.",
    )


def _normalize_native_account_address(identity: str, *, field_name: str = "wallet address") -> str:
    normalized_wallet = normalize_wallet_address(str(identity or "").strip())
    if normalized_wallet:
        return normalized_wallet
    raise HTTPException(
        status_code=400,
        detail=f"Invalid {field_name}. Expected an Ethereum-style 0x address.",
    )


def _submission_wallet_matches(submission, normalized_wallet: str) -> bool:
    for candidate in [
        getattr(submission, "creator_wallet_address", None),
        getattr(submission, "submitter", None),
    ]:
        if normalize_wallet_address(str(candidate or "").strip()) == normalized_wallet:
            return True
    return False


def _vote_wallet_matches(vote: dict[str, Any], normalized_wallet: str) -> bool:
    for candidate in [
        vote.get("voter_wallet_address"),
        vote.get("voter"),
    ]:
        if normalize_wallet_address(str(candidate or "").strip()) == normalized_wallet:
            return True
    return False


def _get_account_submissions(normalized_wallet: str):
    submissions = [
        submission
        for submission in blockchain.submissions
        if _submission_wallet_matches(submission, normalized_wallet)
    ]
    submissions.sort(key=lambda submission: getattr(submission, "created_at", 0) or 0, reverse=True)
    return submissions


def _get_account_votes(normalized_wallet: str):
    votes = [
        vote
        for vote in blockchain.votes
        if _vote_wallet_matches(vote, normalized_wallet)
    ]
    votes.sort(key=lambda vote: vote.get("created_at") or 0, reverse=True)
    return votes


def _get_account_rewards(normalized_wallet: str):
    rewards = blockchain.get_reward_records_for_wallet(normalized_wallet)
    rewards.sort(key=lambda reward: reward.get("minted_at") or 0, reverse=True)
    return rewards


def _get_account_transfers(normalized_wallet: str):
    transfers = [
        _serialize_transfer_intent(record)
        for record in blockchain.get_transfer_intents_for_wallet(normalized_wallet)
    ]
    transfers.sort(key=lambda record: record.get("created_at") or 0, reverse=True)
    return transfers


def _get_account_transactions(normalized_wallet: str):
    transactions = [
        _serialize_wallet_transaction_history_entry(record, normalized_wallet)
        for record in blockchain.get_native_transactions_for_wallet(normalized_wallet)
    ]
    transactions.sort(key=lambda record: record.get("created_at") or "", reverse=True)
    return transactions


def _count_pending_transfer_intents(transfers: list[dict[str, Any]]) -> int:
    pending_statuses = {"signed_pending", "pending", "draft_signed", "signed", "validated_pending", "mempool"}
    return sum(1 for transfer in transfers if str(transfer.get("status") or "").strip().lower() in pending_statuses)


def _count_settled_transactions(transactions: list[dict[str, Any]]) -> int:
    return sum(1 for transaction in transactions if str(transaction.get("status") or "").strip().lower() == "settled")


def _build_account_summary(normalized_wallet: str):
    submissions = _get_account_submissions(normalized_wallet)
    votes = _get_account_votes(normalized_wallet)
    rewards = _get_account_rewards(normalized_wallet)
    transactions = _get_account_transactions(normalized_wallet)
    balance_snapshot = blockchain.get_native_balance_snapshot(normalized_wallet)
    nonce_state = blockchain.get_nonce_state(normalized_wallet)
    return {
        "wallet_address": normalized_wallet,
        "normalized_wallet_address": normalized_wallet,
        "account_type": "metamask_native",
        "network_name": NETWORK_NAME,
        "final_balance": balance_snapshot["final_balance"],
        "native_balance": balance_snapshot["native_balance"],
        "pending_outgoing": balance_snapshot["pending_outgoing"],
        "pending_incoming": balance_snapshot["pending_incoming"],
        "available_balance": balance_snapshot["available_balance"],
        "symbol": TICKER,
        "submission_count": len(submissions),
        "vote_count": len(votes),
        "reward_count": len(rewards),
        "transaction_count": len(transactions),
        "pending_transaction_count": _count_pending_transfer_intents(transactions),
        "settled_transaction_count": _count_settled_transactions(transactions),
        "pending_transfer_count": _count_pending_transfer_intents(transactions),
        "nonce": {
            "next_nonce": nonce_state["next_nonce"],
            "policy": nonce_state["policy"],
        },
        "note": (
            "Pending outgoing transactions reduce available balance. Final balance changes only when a transfer is settled in a meme-mined block. "
            "Native accounts do not need to be pre-registered in the old development-only server wallet list. "
            "A verified 0x address becomes a ZoidbergChain account when it submits, votes, receives rewards, or holds balance."
        ),
    }


def _current_review_policy_config():
    return load_review_policy_config(ENVIRONMENT)


def _review_eligibility_for_wallet(wallet_address: str, *, scope: str = "review", now: float | None = None):
    config = _current_review_policy_config()
    activity_summary = blockchain.get_account_activity_summary(wallet_address, now=now)
    recent_vote_count = blockchain.count_votes_by_wallet_since(
        wallet_address,
        current_day_window(now=now),
    )
    decision = evaluate_review_eligibility(
        config,
        wallet_address=wallet_address,
        activity_summary=activity_summary,
        recent_vote_count=recent_vote_count,
    )
    access_account, _binding, hard_block_reason = _review_hard_block_for_wallet(wallet_address)
    if hard_block_reason:
        detail_message = {
            "wallet_binding_revoked": "This wallet binding was revoked. Ask the operator to rebind or reapprove it.",
            "access_account_suspended": "This access account is suspended. Ask the operator to reactivate it before trying again.",
            "access_account_revoked": "This access account is revoked. Ask the operator to restore access before trying again.",
        }.get(
            hard_block_reason,
            "This wallet is blocked for controlled beta review actions.",
        )
        return config, _review_decision_with_status(
            decision,
            eligible=False,
            reason=hard_block_reason,
            recommended_action=detail_message,
            eligibility_status="blocked",
            blocked_reason=hard_block_reason,
        )

    override_entry = blockchain.find_matching_allowlist_entry(
        scope,
        wallet_address=wallet_address,
        access_account=access_account,
    )
    if override_entry:
        return config, _review_decision_with_status(
            decision,
            eligible=True,
            reason="allowlist_override",
            recommended_action="An admin override is active for this wallet.",
            matched_threshold=None,
            allowlist_override_applied=True,
            allowlist_scope=str(override_entry.get("scope") or "").strip().lower() or None,
            eligibility_status="allowlist_override",
            blocked_reason=None,
        )

    return config, _review_decision_with_status(
        decision,
        eligibility_status="eligible" if decision.eligible else "blocked",
        blocked_reason=None if decision.eligible else decision.reason,
    )


def _review_policy_http_exception(reason: str, recommended_action: str):
    raise HTTPException(
        status_code=403,
        detail={
            "error": "reviewer_not_eligible",
            "reason": reason,
            "recommended_action": recommended_action,
        },
    )


def _enforce_review_policy(wallet_address: str, *, scope: str = "review"):
    _, decision = _review_eligibility_for_wallet(wallet_address, scope=scope)
    if not decision.eligible:
        _review_policy_http_exception(decision.reason, decision.recommended_action)


def _require_content_reference(content_hash: str | None, content_id: str | None):
    normalized_hash = (content_hash or "").strip() or None
    normalized_id = (content_id or "").strip() or None

    content_object = None
    if normalized_id:
        content_object = blockchain.get_content_object(normalized_id)
        if content_object is None:
            raise HTTPException(status_code=404, detail=f"Content not found: {normalized_id}")
    if normalized_hash:
        hashed_content_object = blockchain.get_content_object_by_hash(normalized_hash)
        if content_object is not None and hashed_content_object is not None and hashed_content_object.content_id != content_object.content_id:
            raise HTTPException(status_code=400, detail="content_id does not match content_hash.")
        if hashed_content_object is not None:
            content_object = hashed_content_object
        elif content_object is None:
            raise HTTPException(status_code=404, detail=f"Content not found: {normalized_hash}")

    if content_object is None:
        raise HTTPException(status_code=400, detail="content_hash or content_id is required.")

    if normalized_hash and content_object.content_hash != normalized_hash:
        raise HTTPException(status_code=400, detail="content_hash does not match stored content.")
    if normalized_id and content_object.content_id != normalized_id:
        raise HTTPException(status_code=400, detail="content_id does not match content_hash.")
    return content_object


def _require_content_object(content_hash):
    if not is_valid_content_hash(content_hash):
        raise HTTPException(status_code=422, detail="content_hash must be a 64-character lowercase hexadecimal string.")
    content_object = blockchain.get_content_object_by_hash(content_hash)
    if content_object is None:
        raise HTTPException(status_code=404, detail=f"Content not found: {content_hash}")
    return content_object


def _has_forbidden_key_fields(payload: dict[str, Any]) -> bool:
    forbidden_fields = {"private_key", "privateKey", "signing_key", "seed", "seed_phrase", "secret", "raw_secret"}
    return any(field in payload for field in forbidden_fields)


def _validate_unregistered_peer_submission_shape(receive_request: PeerSubmissionReceive):
    payload = receive_request.submission.model_dump()
    if _has_forbidden_key_fields(payload):
        raise HTTPException(status_code=422, detail="Submission payload contains forbidden or unexpected fields.")
    if not isinstance(payload.get("submission_id"), str) or not payload["submission_id"].strip():
        raise HTTPException(status_code=422, detail="Submission submission_id is required.")
    if not isinstance(payload.get("image_path"), str) or not payload["image_path"].strip():
        raise HTTPException(status_code=422, detail="Submission image_path is required.")
    if not isinstance(payload.get("text_content"), str) or not payload["text_content"].strip():
        raise HTTPException(status_code=422, detail="Submission text_content is required.")
    submitter = str(payload.get("submitter", "")).strip()
    if not (is_valid_wallet_public_key(submitter) or is_valid_ethereum_address(submitter)):
        raise HTTPException(status_code=422, detail="Submission submitter is required.")


def _validate_unregistered_peer_vote_shape(receive_request: PeerVoteReceive):
    payload = receive_request.model_dump()
    if _has_forbidden_key_fields(payload):
        raise HTTPException(status_code=422, detail="Vote payload contains forbidden or unexpected fields.")
    if not isinstance(payload.get("submission_id"), str) or not payload["submission_id"].strip():
        raise HTTPException(status_code=422, detail="Vote submission_id is required.")
    voter = str(payload.get("voter", "")).strip()
    if not (is_valid_wallet_public_key(voter) or is_valid_ethereum_address(voter)):
        raise HTTPException(status_code=422, detail="Vote voter is required.")
    if payload.get("vote_type") not in {"original", "not_original", "unsure"}:
        raise HTTPException(status_code=422, detail="Vote vote_type is required.")


def _validate_unregistered_peer_certificate_shape(receive_request: PeerCertificateReceive):
    payload = receive_request.certificate.model_dump()
    if _has_forbidden_key_fields(payload):
        raise HTTPException(status_code=422, detail="Certificate payload contains forbidden or unexpected fields.")
    if not is_valid_certificate_id(payload.get("certificate_id", "")):
        raise HTTPException(status_code=422, detail="Certificate certificate_id is required.")
    if not is_valid_submission_id(payload.get("submission_id", "")):
        raise HTTPException(status_code=422, detail="Certificate submission_id is required.")
    if not is_valid_content_hash(payload.get("content_hash", "")):
        raise HTTPException(status_code=422, detail="Certificate content_hash is required.")
    if not is_valid_wallet_public_key(payload.get("creator_wallet", "")):
        raise HTTPException(status_code=422, detail="Certificate creator_wallet is required.")
    if not is_valid_node_id(payload.get("issuing_node_id", "")):
        raise HTTPException(status_code=422, detail="Certificate issuing_node_id is required.")
    if not is_valid_network_name(payload.get("network_name", "")):
        raise HTTPException(status_code=422, detail="Certificate network_name is required.")
    if not is_valid_content_hash(payload.get("vote_hash", "")):
        raise HTTPException(status_code=422, detail="Certificate vote_hash is required.")


def _validate_unregistered_peer_block_shape(receive_request: PeerBlockReceive):
    payload = receive_request.block.model_dump()
    if _has_forbidden_key_fields(payload):
        raise HTTPException(status_code=422, detail="Block payload contains forbidden or unexpected fields.")
    if payload.get("index") is None:
        raise HTTPException(status_code=422, detail="Block index is required.")
    if payload.get("previous_hash") is None:
        raise HTTPException(status_code=422, detail="Block previous_hash is required.")
    if payload.get("timestamp") is None:
        raise HTTPException(status_code=422, detail="Block timestamp is required.")
    if payload.get("transactions") is None:
        raise HTTPException(status_code=422, detail="Block transactions are required.")
    if payload.get("miner") is None:
        raise HTTPException(status_code=422, detail="Block miner is required.")
    if payload.get("meme") is None:
        raise HTTPException(status_code=422, detail="Block meme is required.")
    if payload.get("hash") is None:
        raise HTTPException(status_code=422, detail="Block hash is required.")
    if not is_valid_block_hash(str(payload.get("previous_hash", "")).strip()):
        raise HTTPException(status_code=422, detail="Block previous_hash is required.")
    if not is_valid_block_hash(str(payload.get("hash", "")).strip()):
        raise HTTPException(status_code=422, detail="Block hash is required.")


def development_tools_enabled(feature_enabled=True):
    return is_development() and not public_api_mode_enabled() and bool(feature_enabled)


def require_development_mode(feature_enabled=True, feature_name="Development tools"):
    if not development_tools_enabled(feature_enabled):
        raise HTTPException(
            status_code=403,
            detail=f"{feature_name} is disabled.",
        )


def _public_error(detail, *, status_code=400, code=None):
    body = {"detail": detail}
    if code:
        body["code"] = code
    return JSONResponse(status_code=status_code, content=body)


def _safe_server_error():
    return _public_error(
        "Internal server error.",
        status_code=500,
        code="internal_server_error",
    )


def static_asset_response(filename: str, *, download_name: str | None = None, media_type: str | None = None, missing_message: str):
    """Narrow HTTP support helper for static deployment assets."""
    path = os.path.join("static", filename)
    if os.path.exists(path):
        return FileResponse(path, filename=download_name, media_type=media_type)
    return JSONResponse(status_code=404, content={"error": missing_message})


def reset_runtime_blockchain_operation():
    """Install the replacement returned by the guarded Blockchain reset facade."""
    global blockchain, project_owner, contributor1, contributor2
    blockchain = blockchain.reset_to_genesis_operation()
    project_owner = blockchain.project_owner_wallet
    contributor1 = blockchain.Contributor_one
    contributor2 = blockchain.Contributor_two
    wallet_auth_manager.clear()
    return {"message": "Blockchain reset to Genesis state."}


def _health_payload():
    return safe_public_status_payload(
        blockchain=blockchain,
        peer_store=peer_store,
        started_at=APP_STARTED_AT,
    )


def _status_payload():
    payload = _health_payload()
    payload.update({
        "latest_block": safe_latest_block_summary(blockchain),
        "environment_validation": {
            "healthy": safe_environment_validation()["healthy"],
            "error_count": safe_environment_validation()["error_count"],
            "warning_count": safe_environment_validation()["warning_count"],
        },
    })
    return payload


def _safe_request_metadata(request: Request) -> dict[str, str]:
    client_host = request.client.host if request.client else "unknown"
    user_agent = str(request.headers.get("user-agent") or "").strip()
    return {
        "remote_ip": client_host,
        "user_agent": user_agent[:240],
    }


def _safe_session_identifier(session) -> str | None:
    session_id = str(getattr(session, "session_id", "") or "").strip()
    if not session_id:
        return None
    return session_id[:12]


def _admin_audit_entry(entry: dict | None) -> dict:
    payload = dict(entry or {})
    return {
        "audit_id": payload.get("audit_id"),
        "timestamp": payload.get("timestamp"),
        "action": payload.get("action"),
        "result": payload.get("result"),
        "actor_session_id": payload.get("actor_session_id"),
        "remote_ip": payload.get("remote_ip"),
        "user_agent": payload.get("user_agent"),
        "request_id": payload.get("request_id"),
        "override_request_id": payload.get("override_request_id"),
        "feedback_id": payload.get("feedback_id"),
        "access_account_id": payload.get("access_account_id"),
        "allowlist_entry_id": payload.get("allowlist_entry_id"),
        "wallet_address": payload.get("wallet_address"),
        "reason": payload.get("reason"),
        "operator_note": payload.get("operator_note"),
    }


def _recent_access_lifecycle_events(limit: int = 5) -> dict[str, list[dict]]:
    recent_requests = sorted(
        blockchain.list_access_requests(),
        key=lambda item: str(item.get("reviewed_at") or item.get("created_at") or ""),
        reverse=True,
    )[:limit]
    recent_accounts = sorted(
        blockchain.list_access_accounts(),
        key=lambda item: str(item.get("status_updated_at") or item.get("approved_at") or item.get("created_at") or ""),
        reverse=True,
    )[:limit]
    recent_bindings = sorted(
        blockchain.list_wallet_bindings(),
        key=lambda item: str(item.get("revoked_at") or item.get("bound_at") or ""),
        reverse=True,
    )[:limit]
    return {
        "recent_access_requests": [_admin_access_request(item) for item in recent_requests],
        "recent_access_accounts": [_admin_access_account(item) for item in recent_accounts],
        "recent_wallet_bindings": [_admin_wallet_binding(item) for item in recent_bindings],
    }


def _admin_ops_status_payload() -> dict:
    runtime_storage = safe_runtime_storage_status(blockchain.storage)
    validation = safe_environment_validation()
    backup_status = safe_backup_status(blockchain.storage)
    integrity_status = safe_integrity_status(blockchain.storage)
    latest_block = safe_latest_block_summary(blockchain)
    lifecycle = _recent_access_lifecycle_events(limit=5)
    feedback_summary = blockchain.feedback_summary()
    recent_audit = [
        _admin_audit_entry(entry)
        for entry in blockchain.list_audit_log_entries(limit=20)
    ]
    return {
        "health": _status_payload(),
        "environment": ENVIRONMENT,
        "network_name": NETWORK_NAME,
        "public_demo_mode": public_demo_mode_enabled(),
        "storage_backend": STORAGE_BACKEND,
        "runtime_storage": runtime_storage,
        "environment_validation": validation,
        "backup_status": backup_status,
        "integrity_status": integrity_status,
        "sqlite_integrity": sqlite_integrity_status(blockchain.storage),
        "metrics": {
            "chain_height": latest_block.get("index"),
            "pending_access_requests": len(blockchain.list_access_requests(status="pending")),
            "pending_review_submissions": len(blockchain.storage.list_submissions(blockchain.submissions, status=PENDING)),
            "mempool_size": len(blockchain.list_mempool_transactions()),
            "peer_count": len(peer_store.list_active_peers(network_name=NETWORK_NAME)),
            "active_admin_sessions": admin_session_manager.count_active_sessions(),
            "active_access_sessions": access_session_manager.count_active_sessions(),
            "active_wallet_bindings": blockchain.count_active_wallet_bindings(),
            "new_feedback_count": feedback_summary["new_feedback_count"],
            "open_feedback_count": feedback_summary["open_feedback_count"],
            "high_priority_feedback_count": feedback_summary["high_priority_feedback_count"],
        },
        "latest_block": latest_block,
        "feedback_summary": feedback_summary,
        "recent_admin_actions": recent_audit,
        **lifecycle,
    }


async def require_mint_queue_management_access(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    if development_tools_enabled(allow_dev_reset_endpoints()):
        return "dev"
    if public_api_mode_enabled():
        if API_KEYS.get(x_api_key) == "admin":
            return "admin"
        raise HTTPException(status_code=403, detail="Admin API key required for mint queue management.")
    raise HTTPException(status_code=403, detail="Mint queue management is disabled.")


async def require_legacy_direct_block_access():
    require_development_mode(
        allow_dev_reset_endpoints(),
        "Legacy direct block route",
    )
    return "dev"


async def require_transaction_broadcast_access(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    if not public_api_mode_enabled():
        return "local"
    if API_KEYS.get(x_api_key) == "admin":
        return "admin"
    raise HTTPException(status_code=403, detail="Admin API key required for transaction broadcast.")


def _dev_private_key_export_enabled():
    return development_tools_enabled(allow_private_key_export())


def _require_dev_private_key_export():
    require_development_mode(
        allow_private_key_export(),
        "Development private key export",
    )


def _protocol_v1_peer_request_payload(request: Request, body_bytes: bytes) -> dict[str, Any]:
    body_payload = None
    if request.method.upper() == "POST":
        if body_bytes in (b"", None):
            raise HTTPException(status_code=400, detail="Protocol v1 peer request payload is required.")
        try:
            body_payload = json.loads(body_bytes)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail="Protocol v1 peer request payload must be valid JSON.") from exc
        if not isinstance(body_payload, dict):
            raise HTTPException(status_code=400, detail="Protocol v1 peer request payload must be a JSON object.")

    try:
        payload = build_protocol_v1_peer_request_payload(
            request.method,
            request.url.path,
            body_payload=body_payload,
            query_params=request.query_params,
        )
    except ProtocolV1PeerMessageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Protocol v1 peer request payload must resolve to a JSON object.")
    return payload


def _protocol_v1_peer_auth_context(request: Request) -> ProtocolV1PeerAuthContext | None:
    context = getattr(request.state, "protocol_v1_peer_auth", None)
    return context if isinstance(context, ProtocolV1PeerAuthContext) else None


def _require_protocol_v1_peer_claims_match_auth(
    request: Request,
    *,
    claimed_node_id: str,
    claimed_network_name: str,
) -> ProtocolV1PeerAuthContext | None:
    context = _protocol_v1_peer_auth_context(request)
    if context is None:
        return None

    if str(claimed_node_id).strip() != context.sender_node_id:
        raise HTTPException(status_code=403, detail="Peer sender node_id does not match authenticated sender.")

    try:
        claimed_network_id = resolve_protocol_v1_peer_network_id(network_name=claimed_network_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if claimed_network_id != context.network_id:
        raise HTTPException(status_code=400, detail="Peer message network does not match authenticated network.")

    return context


def _require_protocol_v1_active_peer(request: Request) -> ProtocolV1PeerAuthContext | None:
    context = _protocol_v1_peer_auth_context(request)
    if context is None:
        return None

    peer = peer_store.get_active_peer(context.sender_node_id)
    if not peer:
        raise HTTPException(status_code=403, detail="Peer is not registered or active.")
    if peer.get("network_name") != NETWORK_NAME:
        raise HTTPException(status_code=400, detail="Registered peer belongs to a different network.")
    return context


async def require_peer_secret(
    request: Request,
    x_zoid_peer_secret: str | None = Header(default=None, alias="X-ZOID-Peer-Secret"),
):
    if signed_peer_messages_enabled():
        if not peer_shared_secret_is_configured():
            raise HTTPException(status_code=500, detail="Peer auth is enabled but the shared secret is not configured.")
        if not looks_like_protocol_v1_peer_headers(request.headers):
            raise HTTPException(status_code=401, detail="Missing Protocol v1 peer headers.")

        body_bytes = await request.body()
        payload = _protocol_v1_peer_request_payload(request, body_bytes)
        replay_store = None
        if peer_replay_protection_enabled():
            replay_store = get_protocol_v1_peer_replay_store(
                data_dir=peer_store.storage.data_dir,
                retention_window_seconds=PEER_SIGNATURE_WINDOW_SECONDS,
            )
        try:
            context = verify_protocol_v1_peer_request(
                method=request.method,
                path=request.url.path,
                headers=request.headers,
                payload=payload,
                expected_network_id=resolve_protocol_v1_peer_network_id(network_name=NETWORK_NAME),
                secret=peer_shared_secret(),
                timestamp_window_seconds=PEER_SIGNATURE_WINDOW_SECONDS,
                replay_store=replay_store,
                now=int(time.time()),
            )
            request.state.protocol_v1_peer_auth = context
            return
        except MissingProtocolV1PeerHeadersError as exc:
            raise HTTPException(status_code=401, detail=str(exc))
        except UnsupportedPeerMessageVersionError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except UnsupportedPeerProtocolVersionError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except WrongPeerNetworkError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except InvalidPeerMessageTypeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except InvalidPeerSenderError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except InvalidPeerNonceError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except ProtocolV1InvalidPeerTimestampError as exc:
            raise HTTPException(status_code=401, detail=str(exc))
        except ExpiredPeerMessageError as exc:
            raise HTTPException(status_code=401, detail=str(exc))
        except InvalidPeerMessageIdError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ProtocolV1InvalidPeerSignatureError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ReplayedPeerMessageError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except ReplayStateUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc))

    if not peer_auth_required():
        return

    expected_secret = peer_shared_secret()
    if not peer_shared_secret_is_configured():
        raise HTTPException(status_code=500, detail="Peer auth is enabled but the shared secret is not configured.")
    if x_zoid_peer_secret is None:
        raise HTTPException(status_code=401, detail="Peer auth required. Missing shared secret.")
    if not hmac.compare_digest(x_zoid_peer_secret, expected_secret):
        raise HTTPException(status_code=403, detail="Invalid peer shared secret.")

def log_startup_security_config():
    logger.info(
        "Startup config: environment=%s network_name=%s node_id=%s "
        "public_node_url=%s public_api_mode=%s require_peer_auth=%s "
        "signed_peer_messages=%s peer_signature_window_seconds=%s "
        "peer_replay_protection_enabled=%s peer_secret_configured=%s "
        "allow_dev_wallet_private_key_export=%s public_demo_mode=%s "
        "storage_backend=%s cors_allowed_origins=%s node_data_dir=%s log_dir=%s",
        ENVIRONMENT,
        NETWORK_NAME,
        NODE_ID,
        PUBLIC_NODE_URL,
        public_api_mode_enabled(),
        require_peer_auth(),
        signed_peer_messages_enabled(),
        PEER_SIGNATURE_WINDOW_SECONDS,
        peer_replay_protection_enabled(),
        peer_shared_secret_is_configured(),
        allow_private_key_export(),
        public_demo_mode_enabled(),
        STORAGE_BACKEND,
        ",".join(cors_allowed_origins()),
        NODE_DATA_DIR,
        LOG_DIR,
    )

@asynccontextmanager
async def lifespan(app):
    log_startup_security_config()
    validation = safe_environment_validation()
    if validation["healthy"] and validation["warning_count"] == 0:
        logger.info("Startup ops validation passed with no warnings.")
    else:
        for check in validation["checks"]:
            if check["ok"]:
                continue
            logger.warning(
                "Startup ops validation %s [%s]: %s",
                check["level"],
                check["code"],
                check["message"],
            )
    # Initialize or recreate the global blockchain instance at app startup.
    # This avoids loading repository-root persistent state at import time
    # (which breaks test isolation). Tests can still import this module and
    # then replace `api.blockchain` with a fixture-provided instance.
    global blockchain, project_owner, contributor1, contributor2
    if blockchain is None:
        try:
            project_owner = Wallet()
            contributor1 = Wallet()
            contributor2 = Wallet()
            blockchain = Blockchain(project_owner, contributor1, contributor2)
        except Exception:
            logger.exception("Failed to initialize blockchain at startup")

    wallet_auth_manager.clear()
    yield


app = FastAPI(lifespan=lifespan)

# CORS: allow both local and live frontend origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Initialize the rate limiter
limiter = Limiter(key_func=get_remote_address, enabled=ENABLE_RATE_LIMITING)

# ✅ Exclude FastAPI Docs from rate limiting
app.state.limiter = limiter
@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return _public_error(
        "Rate limit exceeded. Try again later.",
        status_code=429,
        code="rate_limit_exceeded",
    )

app.add_middleware(SlowAPIMiddleware)


def api_limit(category):
    return limiter.limit(get_rate_limit(category))


peer_store = PeerStore()
wallet_auth_manager = WalletAuthManager(
    network_name=NETWORK_NAME,
    environment=ENVIRONMENT,
)
access_session_manager = AccessSessionManager()
admin_session_manager = AdminSessionManager(session_ttl_seconds=ADMIN_SESSION_TTL_SECONDS)


def sync_approved_submissions_to_mint_queue():
    queued_any = False
    for submission in blockchain.storage.list_submissions(blockchain.submissions, status=APPROVED):
        if not blockchain.storage.mint_queue_contains(submission.submission_id, blockchain.mint_queue):
            try:
                blockchain.add_to_mint_queue(submission.submission_id)
                queued_any = True
            except ValueError as e:
                if "certificate" not in str(e).lower():
                    raise
    return queued_any


def _verified_wallet_dependency(
    request: Request,
    authorization: str | None = Header(default=None),
):
    runtime = getattr(request.app.state, "api_runtime", None)
    if runtime is None:
        return resolve_verified_wallet_from_authorization(authorization, manager=wallet_auth_manager)
    return runtime.resolve_verified_wallet_from_authorization(
        authorization,
        manager=runtime.wallet_auth_manager,
    )


def _access_session_dependency(x_zoid_access_session: str | None = Header(default=None, alias="X-ZOID-Access-Session")):
    return x_zoid_access_session or ""


ADMIN_SESSION_COOKIE_NAME = "zoidberg_admin_session"


def _admin_auth_disabled_for_local_dev() -> bool:
    return is_development() and not ADMIN_AUTH_ENABLED


def _admin_auth_configured() -> bool:
    return admin_auth_is_configured(ADMIN_PASSWORD_HASH, ADMIN_BOOTSTRAP_TOKEN)


def _require_admin_ui_enabled():
    if not ADMIN_UI_ENABLED:
        raise HTTPException(status_code=404, detail="Admin UI is disabled on this node.")


def _admin_cookie_should_be_secure(request: Request) -> bool:
    forwarded_proto = str(request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    if forwarded_proto == "https":
        return True

    request_scheme = str(getattr(request.url, "scheme", "") or "").lower()
    if request_scheme == "https":
        return True

    if str(API_BASE_URL).startswith("https://") or str(PUBLIC_NODE_URL).startswith("https://"):
        return True

    host = str(request.headers.get("host") or "").lower()
    if request_scheme == "http" and host and host.split(":", 1)[0] in {"localhost", "127.0.0.1", "testserver.local"}:
        return False

    return False


def _set_admin_session_cookie(response: Response, *, request: Request, token: str, expires_at: str) -> None:
    response.set_cookie(
        key=ADMIN_SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=_admin_cookie_should_be_secure(request),
        samesite="lax",
        max_age=ADMIN_SESSION_TTL_SECONDS,
        expires=expires_at,
        path="/",
    )


def _clear_admin_session_cookie(response: Response, *, request: Request) -> None:
    response.delete_cookie(
        key=ADMIN_SESSION_COOKIE_NAME,
        httponly=True,
        secure=_admin_cookie_should_be_secure(request),
        samesite="lax",
        path="/",
    )


def _get_admin_session_token(request: Request, x_zoid_admin_session: str | None = None) -> str:
    cookie_token = str(request.cookies.get(ADMIN_SESSION_COOKIE_NAME) or "").strip()
    if cookie_token:
        return cookie_token
    return str(x_zoid_admin_session or "").strip()


def _admin_session_status_payload(*, authenticated: bool, session=None, reason: str | None = None) -> dict:
    return {
        "admin_ui_enabled": ADMIN_UI_ENABLED,
        "admin_auth_enabled": ADMIN_AUTH_ENABLED,
        "admin_auth_configured": _admin_auth_configured(),
        "authenticated": bool(authenticated),
        "reason": reason,
        "issued_at": session.issued_at.isoformat() if session else None,
        "expires_at": session.expires_at.isoformat() if session else None,
        "session_backend": admin_session_manager.backend_description(),
    }


def _require_admin_session(
    request: Request,
    x_zoid_admin_session: str | None = Header(default=None, alias="X-ZOID-Admin-Session"),
):
    _require_admin_ui_enabled()
    if _admin_auth_disabled_for_local_dev():
        return None

    token = _get_admin_session_token(request, x_zoid_admin_session)
    try:
        return admin_session_manager.get_session(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def _public_access_account(account: dict | None) -> dict | None:
    if not account:
        return None
    bound_wallets = list(account.get("bound_wallets", []))
    return {
        "access_account_id": account.get("access_account_id"),
        "name": account.get("name"),
        "email": account.get("email"),
        "handle": account.get("handle"),
        "status": account.get("status"),
        "created_at": account.get("created_at"),
        "approved_at": account.get("approved_at"),
        "invite_code_generated_at": account.get("invite_code_generated_at"),
        "invite_code_redeemed_at": account.get("invite_code_redeemed_at"),
        "bound_wallets": bound_wallets,
        "wallet_count": len(bound_wallets),
        "max_wallets": account.get("max_wallets"),
        "notes": account.get("notes"),
        "last_login_at": account.get("last_login_at"),
        "status_updated_at": account.get("status_updated_at"),
        "status_updated_by": account.get("status_updated_by"),
        "status_reason": account.get("status_reason"),
    }


def _public_access_request(request_record: dict | None) -> dict | None:
    if not request_record:
        return None
    return {
        "request_id": request_record.get("request_id"),
        "name": request_record.get("name"),
        "email": request_record.get("email"),
        "handle": request_record.get("handle"),
        "reason": request_record.get("reason"),
        "notes": request_record.get("notes"),
        "status": request_record.get("status"),
        "created_at": request_record.get("created_at"),
        "reviewed_at": request_record.get("reviewed_at"),
        "reviewed_by": request_record.get("reviewed_by"),
        "operator_notes": request_record.get("operator_notes"),
        "approved_access_account_id": request_record.get("approved_access_account_id"),
    }


def _public_wallet_binding(binding: dict | None) -> dict | None:
    if not binding:
        return None
    return {
        "wallet_address": binding.get("wallet_address"),
        "access_account_id": binding.get("access_account_id"),
        "bound_at": binding.get("bound_at"),
        "status": binding.get("status"),
        "source": binding.get("source"),
        "revoked_at": binding.get("revoked_at"),
        "revoked_by": binding.get("revoked_by"),
        "revoke_reason": binding.get("revoke_reason"),
    }


def _admin_access_account(account: dict | None) -> dict | None:
    body = _public_access_account(account)
    if not body or not account:
        return body
    body.update({
        "reviewed_by": account.get("reviewed_by"),
        "operator_notes": account.get("operator_notes"),
        "invite_redeemed": bool(account.get("invite_code_redeemed_at")),
    })
    return body


def _admin_access_request(request_record: dict | None) -> dict | None:
    return _public_access_request(request_record)


def _admin_wallet_binding(binding: dict | None) -> dict | None:
    return _public_wallet_binding(binding)


def _public_allowlist_entry(entry: dict | None) -> dict | None:
    if not entry:
        return None
    return {
        "allowlist_entry_id": entry.get("allowlist_entry_id"),
        "scope": entry.get("scope"),
        "subject_type": entry.get("subject_type"),
        "subject_value": entry.get("subject_value"),
        "status": entry.get("status"),
        "reason": entry.get("reason"),
        "created_at": entry.get("created_at"),
        "updated_at": entry.get("updated_at"),
        "expires_at": entry.get("expires_at"),
        "created_by": entry.get("created_by"),
        "revoked_at": entry.get("revoked_at"),
        "revoked_reason": entry.get("revoked_reason"),
    }


def _admin_allowlist_entry(entry: dict | None) -> dict | None:
    body = _public_allowlist_entry(entry)
    if not body or not entry:
        return body
    subject_type = str(entry.get("subject_type") or "").strip().lower()
    subject_value = str(entry.get("subject_value") or "").strip()
    related_account = None
    related_binding = None
    related_request = None
    if subject_type == "wallet":
        related_binding = blockchain.get_wallet_binding(subject_value)
        if related_binding:
            related_account = blockchain.get_access_account(related_binding.get("access_account_id"))
    elif subject_type == "access_account":
        related_account = blockchain.get_access_account(subject_value)
    elif subject_type == "email":
        related_account = next(
            (
                account for account in blockchain.list_access_accounts()
                if normalize_email(account.get("email")) == normalize_email(subject_value)
            ),
            None,
        )
        related_request = next(
            (
                request_record for request_record in blockchain.list_access_requests()
                if normalize_email(request_record.get("email")) == normalize_email(subject_value)
            ),
            None,
        )
    elif subject_type == "handle":
        related_account = next(
            (
                account for account in blockchain.list_access_accounts()
                if normalize_handle(account.get("handle")) == normalize_handle(subject_value)
            ),
            None,
        )
        related_request = next(
            (
                request_record for request_record in blockchain.list_access_requests()
                if normalize_handle(request_record.get("handle")) == normalize_handle(subject_value)
            ),
            None,
        )
    is_expired = not blockchain._allowlist_entry_active(entry) and str(entry.get("status") or "").strip().lower() == "active"
    effective_status = "expired" if is_expired else str(entry.get("status") or "").strip().lower()
    diagnostic_messages: list[str] = []
    if subject_type == "wallet":
        if entry.get("scope") == "access":
            if blockchain.find_matching_allowlist_entry("access", wallet_address=subject_value, access_account=related_account):
                diagnostic_messages.append("This wallet is currently recognized as allowlisted for app access.")
            else:
                diagnostic_messages.append("This wallet is not currently matching an active app access allowlist path.")
        elif entry.get("scope") in {"review", "voting", "rewards", "all_beta", "submission"}:
            if blockchain.find_matching_allowlist_entry(str(entry.get("scope") or "review"), wallet_address=subject_value, access_account=related_account):
                diagnostic_messages.append(f"This wallet is currently recognized as allowlisted for {entry.get('scope')}.")
            else:
                diagnostic_messages.append(f"This wallet is not currently matching an active {entry.get('scope')} allowlist path.")
        if related_binding is None:
            diagnostic_messages.append("This wallet has no active known wallet binding on this node.")
    body["normalized_subject_value"] = subject_value
    body["is_expired"] = is_expired
    body["is_active_now"] = blockchain._allowlist_entry_active(entry)
    body["effective_status"] = effective_status
    body["matches_known_wallet_binding"] = bool(related_binding)
    body["matches_known_access_account"] = bool(related_account)
    body["diagnostic_messages"] = diagnostic_messages
    body["related_access_account"] = _public_access_account(related_account)
    body["related_wallet_binding"] = _public_wallet_binding(related_binding)
    body["related_access_request"] = _public_access_request(related_request)
    return body


def _public_override_request(record: dict | None) -> dict | None:
    if not record:
        return None
    return {
        "override_request_id": record.get("override_request_id"),
        "requested_scope": record.get("requested_scope"),
        "name": record.get("name"),
        "email": record.get("email"),
        "handle": record.get("handle"),
        "wallet_address": record.get("wallet_address"),
        "access_account_id": record.get("access_account_id"),
        "reason": record.get("reason"),
        "current_page": record.get("current_page"),
        "detected_blocked_reason": record.get("detected_blocked_reason"),
        "status": record.get("status"),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
    }


def _admin_override_request(record: dict | None) -> dict | None:
    body = _public_override_request(record)
    if not body or not record:
        return body
    body.update({
        "reviewed_at": record.get("reviewed_at"),
        "reviewed_by": record.get("reviewed_by"),
        "admin_note": record.get("admin_note"),
        "resolved_scope": record.get("resolved_scope"),
        "approved_allowlist_entry_id": record.get("approved_allowlist_entry_id"),
        "user_agent": record.get("user_agent"),
        "remote_ip": record.get("remote_ip"),
    })
    related_account = None
    related_binding = None
    wallet_address = normalize_wallet_address(record.get("wallet_address") or "")
    access_account_id = normalize_text_field(record.get("access_account_id"))
    if wallet_address:
        related_binding = blockchain.get_wallet_binding(wallet_address)
        if related_binding:
            related_account = blockchain.get_access_account(related_binding.get("access_account_id"))
    if related_account is None and access_account_id:
        related_account = blockchain.get_access_account(access_account_id)
    body["related_access_account"] = _public_access_account(related_account)
    body["related_wallet_binding"] = _public_wallet_binding(related_binding)
    return body


def _sanitize_feedback_browser_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(metadata, dict):
        return None

    text_limits = {
        "browser_label": 120,
        "platform": 120,
        "language": 64,
        "timezone": 64,
    }
    number_limits = {
        "screen_width": 20000,
        "screen_height": 20000,
    }
    bool_fields = {"prefers_reduced_motion"}
    payload: dict[str, Any] = {}

    for field_name, max_length in text_limits.items():
        value = normalize_text_field(metadata.get(field_name))
        if value:
            payload[field_name] = value[:max_length]

    for field_name, max_value in number_limits.items():
        value = metadata.get(field_name)
        if value in (None, ""):
            continue
        try:
            numeric_value = int(value)
        except (TypeError, ValueError):
            continue
        if 0 <= numeric_value <= max_value:
            payload[field_name] = numeric_value

    for field_name in bool_fields:
        if field_name in metadata and metadata.get(field_name) is not None:
            payload[field_name] = bool(metadata.get(field_name))

    return payload or None


def _sanitize_feedback_eligibility_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(snapshot, dict):
        return None

    blocked_reasons: list[dict[str, str | None]] = []
    for item in list(snapshot.get("blocked_reasons") or [])[:5]:
        if not isinstance(item, dict):
            continue
        blocked_reasons.append({
            "scope": normalize_text_field(item.get("scope"))[:32] or None,
            "reason": normalize_text_field(item.get("reason"))[:120] or None,
            "rule_id": normalize_text_field(item.get("rule_id"))[:120] or None,
        })

    payload: dict[str, Any] = {
        "access_granted": bool(snapshot.get("access_granted")),
        "can_access_app": bool(snapshot.get("can_access_app")),
        "wallet_bound": bool(snapshot.get("wallet_bound")),
        "can_submit": bool(snapshot.get("can_submit")),
        "can_vote": bool(snapshot.get("can_vote")),
        "can_receive_rewards": bool(snapshot.get("can_receive_rewards")),
    }

    submission = snapshot.get("submission")
    if isinstance(submission, dict):
        payload["submission"] = {
            "can_submit": bool(submission.get("can_submit")),
            "eligibility_source": normalize_text_field(submission.get("eligibility_source"))[:120] or None,
            "blocked_reason": normalize_text_field(submission.get("blocked_reason"))[:120] or None,
        }

    if blocked_reasons:
        payload["blocked_reasons"] = blocked_reasons

    return payload


def _public_feedback(record: dict | None) -> dict | None:
    if not record:
        return None
    return {
        "feedback_id": record.get("feedback_id"),
        "type": record.get("type"),
        "title": record.get("title"),
        "status": record.get("status"),
        "priority": record.get("priority"),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
        "current_page": record.get("current_page"),
        "current_flow": record.get("current_flow"),
    }


def _admin_feedback(record: dict | None) -> dict | None:
    body = _public_feedback(record)
    if not body or not record:
        return body
    body.update({
        "description": record.get("description"),
        "name": record.get("name"),
        "email": record.get("email"),
        "handle": record.get("handle"),
        "wallet_address": record.get("wallet_address"),
        "access_account_id": record.get("access_account_id"),
        "user_agent": record.get("user_agent"),
        "remote_ip": record.get("remote_ip"),
        "browser_metadata": record.get("browser_metadata"),
        "eligibility_snapshot": record.get("eligibility_snapshot"),
        "viewport_width": record.get("viewport_width"),
        "viewport_height": record.get("viewport_height"),
        "is_mobile": record.get("is_mobile"),
        "admin_notes": list(record.get("admin_notes") or []),
        "reviewed_at": record.get("reviewed_at"),
        "reviewed_by": record.get("reviewed_by"),
        "status_updated_at": record.get("status_updated_at"),
        "status_updated_by": record.get("status_updated_by"),
        "resolved_at": record.get("resolved_at"),
        "dismissed_at": record.get("dismissed_at"),
    })
    related_account = None
    related_binding = None
    wallet_address = normalize_wallet_address(record.get("wallet_address") or "")
    access_account_id = normalize_text_field(record.get("access_account_id"))
    if wallet_address:
        related_binding = blockchain.get_wallet_binding(wallet_address)
        if related_binding:
            related_account = blockchain.get_access_account(related_binding.get("access_account_id"))
    if related_account is None and access_account_id:
        related_account = blockchain.get_access_account(access_account_id)
    body["related_access_account"] = _public_access_account(related_account)
    body["related_wallet_binding"] = _public_wallet_binding(related_binding)
    return body


def _review_hard_block_for_wallet(wallet_address: str):
    binding = blockchain.get_wallet_binding(wallet_address)
    access_account = blockchain.get_access_account_for_wallet(wallet_address)
    if binding and str(binding.get("status") or "").strip().lower() == "revoked":
        return access_account, binding, "wallet_binding_revoked"
    if access_account:
        account_status = str(access_account.get("status") or "").strip().lower()
        if account_status in {"suspended", "revoked"}:
            return access_account, binding, f"access_account_{account_status}"
    return access_account, binding, None


def _review_decision_with_status(
    decision,
    *,
    eligible: bool | None = None,
    reason: str | None = None,
    recommended_action: str | None = None,
    matched_threshold=None,
    allowlist_override_applied: bool | None = None,
    allowlist_scope: str | None = None,
    eligibility_status: str | None = None,
    blocked_reason: str | None = None,
):
    return type(decision)(
        eligible=decision.eligible if eligible is None else eligible,
        reason=decision.reason if reason is None else reason,
        recommended_action=decision.recommended_action if recommended_action is None else recommended_action,
        matched_threshold=decision.matched_threshold if matched_threshold is None else matched_threshold,
        allowlist_override_applied=(
            decision.allowlist_override_applied
            if allowlist_override_applied is None
            else allowlist_override_applied
        ),
        allowlist_scope=decision.allowlist_scope if allowlist_scope is None else allowlist_scope,
        eligibility_status=decision.eligibility_status if eligibility_status is None else eligibility_status,
        blocked_reason=decision.blocked_reason if blocked_reason is None else blocked_reason,
    )


def _session_access_allowlist_entry(session_access_account: dict | None):
    if not session_access_account:
        return None
    if str(session_access_account.get("status") or "").strip().lower() != "active":
        return None
    return blockchain.find_matching_allowlist_entry(
        "access",
        access_account=session_access_account,
    )


def _eligibility_reason_message(scope: str, reason: str) -> str:
    labels = {
        "wallet_not_verified": "Verify a wallet to continue.",
        "wallet_not_bound": "This wallet is connected but not approved for the controlled beta yet.",
        "wallet_binding_revoked": "This wallet binding was revoked and must be reapproved.",
        "access_account_suspended": "This access account is suspended.",
        "access_account_revoked": "This access account is revoked.",
        "wallet_not_allowlisted": "This wallet is not on the current review eligibility allowlist.",
        "insufficient_reviewer_activity": "This wallet does not meet the current reviewer activity rules yet.",
        "daily_vote_limit_reached": "This wallet reached the current daily review limit.",
        "wallet_denylisted": "This wallet is blocked from review actions on this node.",
    }
    default_label = f"{scope.title()} is currently blocked."
    return labels.get(str(reason or "").strip().lower(), default_label)


def _eligibility_rule_check(
    *,
    rule_id: str,
    label: str,
    description: str,
    passed: bool,
    required: bool,
    scope: str,
    current_value: Any = None,
    required_value: Any = None,
    applicable: bool = True,
):
    return {
        "rule_id": str(rule_id or "").strip(),
        "label": str(label or "").strip(),
        "description": str(description or "").strip(),
        "passed": bool(passed),
        "required": bool(required),
        "scope": str(scope or "").strip().lower(),
        "current_value": current_value,
        "required_value": required_value,
        "applicable": bool(applicable),
    }


def _format_age_days(seconds: Any) -> str:
    try:
        total_seconds = max(int(seconds or 0), 0)
    except (TypeError, ValueError):
        total_seconds = 0
    days = Decimal(total_seconds) / Decimal(86400)
    return f"{days.quantize(Decimal('0.01'))} days"


def _configured_activity_thresholds(config) -> list[tuple[str, str, Any, Any, str]]:
    thresholds: list[tuple[str, str, Any, Any, str]] = []
    if int(config.min_reviewer_account_age_seconds or 0) > 0:
        thresholds.append((
            "reviewer_account_age",
            "Account age requirement",
            _format_age_days(config.min_reviewer_account_age_seconds),
            config.min_reviewer_account_age_seconds,
            "Your wallet needs a testnet account age that meets the configured minimum.",
        ))
    if int(config.min_reviewer_submission_count or 0) > 0:
        thresholds.append((
            "reviewer_submission_count",
            "Submission activity requirement",
            int(config.min_reviewer_submission_count),
            int(config.min_reviewer_submission_count),
            "Your wallet needs enough prior submissions to satisfy the reviewer activity policy.",
        ))
    if int(config.min_reviewer_vote_count or 0) > 0:
        thresholds.append((
            "reviewer_vote_count",
            "Prior vote requirement",
            int(config.min_reviewer_vote_count),
            int(config.min_reviewer_vote_count),
            "Your wallet needs enough completed votes to satisfy the reviewer activity policy.",
        ))
    if int(config.min_reviewer_reward_count or 0) > 0:
        thresholds.append((
            "reviewer_reward_count",
            "Reward history requirement",
            int(config.min_reviewer_reward_count),
            int(config.min_reviewer_reward_count),
            "Your wallet needs enough prior rewards to satisfy the reviewer activity policy.",
        ))
    if str(config.min_reviewer_settled_balance_zoid or "0") not in {"", "0", "0.0"}:
        thresholds.append((
            "reviewer_settled_balance",
            "Settled balance requirement",
            str(config.min_reviewer_settled_balance_zoid),
            str(config.min_reviewer_settled_balance_zoid),
            "Your wallet needs enough settled native ZOID balance to satisfy the reviewer activity policy.",
        ))
    if int(config.min_reviewer_settled_transfer_count or 0) > 0:
        thresholds.append((
            "reviewer_settled_transfer_count",
            "Settled transfer requirement",
            int(config.min_reviewer_settled_transfer_count),
            int(config.min_reviewer_settled_transfer_count),
            "Your wallet needs enough settled transfers to satisfy the reviewer activity policy.",
        ))
    return thresholds


def _review_scope_label(scope: str) -> str:
    labels = {
        "review": "review access",
        "voting": "voting",
        "rewards": "reward eligibility",
    }
    return labels.get(str(scope or "").strip().lower(), str(scope or "review").strip().lower())


def _build_access_rule_checks(
    *,
    wallet_address: str | None,
    access_account: dict | None,
    binding: dict | None,
    session_access_account: dict | None,
    wallet_session_authenticated: bool,
    access_decision,
    access_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    effective_account = access_account or session_access_account
    access_gate_required = access_feature_required("app")
    binding_required = access_mode_enforces_binding()
    access_allowlist_entry = None
    if wallet_address or effective_account:
        access_allowlist_entry = blockchain.find_matching_allowlist_entry(
            "access",
            wallet_address=wallet_address,
            access_account=effective_account,
        )

    checks.append(_eligibility_rule_check(
        rule_id="wallet_verified",
        label="Connect and verify a wallet",
        description="You need to connect MetaMask and sign a wallet verification message before gated beta checks can run.",
        passed=bool(wallet_session_authenticated and wallet_address),
        required=True,
        scope="access",
        current_value=wallet_address or "not verified",
        required_value="verified wallet session",
    ))
    checks.append(_eligibility_rule_check(
        rule_id="access_control_mode",
        label="Access gate mode",
        description="This shows whether the app is currently using open access or controlled beta access rules.",
        passed=True,
        required=False,
        scope="access",
        current_value=ACCESS_CONTROL_MODE,
        required_value="invite_only or allowlist when gating is enabled",
    ))
    checks.append(_eligibility_rule_check(
        rule_id="access_gate_enabled",
        label="App access gate enabled",
        description="App access is only restricted when the controlled beta gate for app access is enabled on this node.",
        passed=not access_gate_required or bool(access_payload.get("access_granted")),
        required=False,
        scope="access",
        current_value="enabled" if access_gate_required else "disabled",
        required_value="disabled or approved access path",
    ))

    binding_status = str(binding.get("status") or "").strip().lower() if binding else "not_bound"
    checks.append(_eligibility_rule_check(
        rule_id="wallet_binding_not_revoked",
        label="Wallet binding is not revoked",
        description="Previously revoked wallet bindings stay blocked until an operator explicitly reapproves or rebinds the wallet.",
        passed=binding_status != "revoked",
        required=True,
        scope="access",
        current_value=binding_status,
        required_value="not revoked",
        applicable=bool(binding),
    ))

    account_status = str(effective_account.get("status") or "").strip().lower() if effective_account else "not_linked"
    checks.append(_eligibility_rule_check(
        rule_id="access_account_active",
        label="Access account is active",
        description="Suspended or revoked access accounts remain blocked even if a stale allowlist entry exists.",
        passed=not effective_account or account_status == "active",
        required=True,
        scope="access",
        current_value=account_status,
        required_value="active",
        applicable=bool(effective_account),
    ))

    checks.append(_eligibility_rule_check(
        rule_id="access_allowlist_match",
        label="Access allowlist entry",
        description="A verified wallet can unlock controlled beta access directly when it matches an active access or all beta allowlist entry.",
        passed=bool(access_allowlist_entry),
        required=False,
        scope="access",
        current_value=(
            f"matched {access_allowlist_entry.get('scope')}"
            if access_allowlist_entry
            else "no active access or all_beta allowlist entry"
        ),
        required_value="active access or all_beta allowlist entry",
        applicable=bool(wallet_address or effective_account),
    ))

    approval_path = "not approved"
    if dev_bypass_effective():
        approval_path = "development bypass"
    elif not binding_required:
        approval_path = "open access mode"
    elif binding_status == "active" and account_status in {"active", "not_linked"}:
        approval_path = "active bound wallet"
    elif access_allowlist_entry:
        approval_path = f"allowlist override ({access_allowlist_entry.get('scope')})"

    checks.append(_eligibility_rule_check(
        rule_id="access_approval_path",
        label="Approved app access path",
        description="When app access is gated, you need either an active approved wallet binding or an active access/all beta allowlist entry.",
        passed=bool(access_payload.get("access_granted")),
        required=bool(access_gate_required),
        scope="access",
        current_value=approval_path,
        required_value="active bound wallet or active access/all_beta allowlist entry",
    ))
    return checks


def _build_submission_rule_checks(
    *,
    wallet_address: str | None,
    wallet_session_authenticated: bool,
    submission_status: dict[str, Any],
    access_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    approval_path = "submission blocked"
    if submission_status.get("can_submit"):
        approval_path = "verified wallet plus active controlled beta access"
    elif not wallet_session_authenticated:
        approval_path = "wallet not verified"
    elif not access_payload.get("access_granted"):
        approval_path = "app access not approved"

    return [
        _eligibility_rule_check(
            rule_id="submission_wallet_verified",
            label="Wallet is verified for submissions",
            description="Submission signing requires the currently connected wallet to be verified in this session.",
            passed=bool(wallet_session_authenticated and wallet_address),
            required=True,
            scope="submission",
            current_value=wallet_address or "not verified",
            required_value="verified wallet session",
        ),
        _eligibility_rule_check(
            rule_id="submission_access_path",
            label="Submission access path",
            description="This node allows submissions when the verified wallet also has controlled beta access for submissions.",
            passed=bool(submission_status.get("can_submit")),
            required=True,
            scope="submission",
            current_value=approval_path,
            required_value="verified wallet plus active controlled beta access",
        ),
        _eligibility_rule_check(
            rule_id="submission_policy_mode",
            label="Submission policy",
            description="This describes the current backend submission rule so the UI does not imply a fake extra override path.",
            passed=True,
            required=False,
            scope="submission",
            current_value=submission_status.get("policy_rule"),
            required_value=None,
        ),
    ]


def _build_review_scope_rule_checks(
    *,
    wallet_address: str | None,
    scope: str,
    decision,
    access_payload: dict[str, Any],
    wallet_session_authenticated: bool,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    normalized_wallet = normalize_wallet_address(wallet_address or "")
    config = _current_review_policy_config()
    scope_label = _review_scope_label(scope)
    activity_summary = blockchain.get_account_activity_summary(normalized_wallet) if normalized_wallet else {}
    recent_vote_count = blockchain.count_votes_by_wallet_since(
        normalized_wallet,
        current_day_window(),
    ) if normalized_wallet else 0
    access_account, binding, hard_block_reason = _review_hard_block_for_wallet(normalized_wallet) if normalized_wallet else (None, None, None)
    override_entry = blockchain.find_matching_allowlist_entry(
        scope,
        wallet_address=normalized_wallet,
        access_account=access_account,
    ) if normalized_wallet else None
    wallet_allowlisted = bool(normalized_wallet and normalized_wallet in config.allowlist_wallets)
    denylisted = bool(normalized_wallet and normalized_wallet in config.denylist_wallets)

    checks.append(_eligibility_rule_check(
        rule_id=f"{scope}_wallet_verified",
        label=f"Wallet is verified for {scope_label}",
        description=f"A verified wallet session is required before the app can evaluate {scope_label} eligibility.",
        passed=bool(wallet_session_authenticated and normalized_wallet),
        required=True,
        scope=scope,
        current_value=normalized_wallet or "not verified",
        required_value="verified wallet session",
    ))

    binding_status = str(binding.get("status") or "").strip().lower() if binding else "not_bound"
    checks.append(_eligibility_rule_check(
        rule_id=f"{scope}_wallet_binding_not_revoked",
        label="Wallet binding is not revoked",
        description="Revoked wallet bindings stay blocked for beta review actions until an operator explicitly restores them.",
        passed=binding_status != "revoked",
        required=True,
        scope=scope,
        current_value=binding_status,
        required_value="not revoked",
        applicable=bool(binding),
    ))

    account_status = str(access_account.get("status") or "").strip().lower() if access_account else "not_linked"
    checks.append(_eligibility_rule_check(
        rule_id=f"{scope}_access_account_active",
        label="Access account is in good standing",
        description="Suspended or revoked access accounts remain blocked for beta review actions.",
        passed=not access_account or account_status == "active",
        required=True,
        scope=scope,
        current_value=account_status,
        required_value="active",
        applicable=bool(access_account),
    ))

    checks.append(_eligibility_rule_check(
        rule_id=f"{scope}_admin_allowlist_override",
        label="Admin allowlist override",
        description=f"An operator can grant a scoped allowlist override for {scope_label} when normal reviewer rules would otherwise block this wallet.",
        passed=bool(override_entry),
        required=False,
        scope=scope,
        current_value=(
            f"matched {override_entry.get('scope')}"
            if override_entry
            else "no scoped admin override"
        ),
        required_value=f"active {scope}, review, or all_beta override",
        applicable=bool(normalized_wallet),
    ))

    checks.append(_eligibility_rule_check(
        rule_id=f"{scope}_review_policy_mode",
        label="Reviewer eligibility mode",
        description=f"The node applies the configured reviewer policy mode before {scope_label} is allowed.",
        passed=True,
        required=False,
        scope=scope,
        current_value=config.eligibility_mode,
        required_value="open, allowlist, activity, or hybrid",
        applicable=bool(normalized_wallet),
    ))

    checks.append(_eligibility_rule_check(
        rule_id=f"{scope}_denylist_check",
        label="Wallet is not denylisted",
        description="Denylisted wallets stay blocked even if other reviewer checks would pass.",
        passed=not denylisted,
        required=bool(config.denylist_enabled),
        scope=scope,
        current_value="denylisted" if denylisted else "not denylisted",
        required_value="not denylisted",
        applicable=bool(config.denylist_enabled and normalized_wallet),
    ))

    if scope == "voting" and int(config.max_review_votes_per_wallet_per_day or 0) > 0:
        checks.append(_eligibility_rule_check(
            rule_id="voting_daily_limit",
            label="Daily vote limit",
            description="Voting stays blocked after the wallet reaches the configured daily review vote limit.",
            passed=recent_vote_count < int(config.max_review_votes_per_wallet_per_day),
            required=True,
            scope="voting",
            current_value=int(recent_vote_count),
            required_value=int(config.max_review_votes_per_wallet_per_day),
            applicable=bool(normalized_wallet),
        ))

    if config.eligibility_mode in {"allowlist", "hybrid"}:
        checks.append(_eligibility_rule_check(
            rule_id=f"{scope}_config_review_allowlist",
            label="Configured review allowlist",
            description=f"The configured review allowlist can satisfy {scope_label} when the node is running in allowlist or hybrid reviewer mode.",
            passed=wallet_allowlisted,
            required=(config.eligibility_mode == "allowlist" and not bool(override_entry)),
            scope=scope,
            current_value="wallet on configured review allowlist" if wallet_allowlisted else "wallet not on configured review allowlist",
            required_value="wallet on configured review allowlist",
            applicable=bool(normalized_wallet),
        ))

    configured_thresholds = _configured_activity_thresholds(config)
    threshold_results: list[bool] = []
    metric_value_map = {
        "reviewer_account_age": int(activity_summary.get("account_age_seconds") or 0),
        "reviewer_submission_count": int(activity_summary.get("submission_count") or 0),
        "reviewer_vote_count": int(activity_summary.get("vote_count") or 0),
        "reviewer_reward_count": int(activity_summary.get("reward_count") or 0),
        "reviewer_settled_balance": str(activity_summary.get("settled_balance_zoid") or "0"),
        "reviewer_settled_transfer_count": int(activity_summary.get("settled_transfer_count") or 0),
    }
    if config.eligibility_mode in {"activity", "hybrid"}:
        for metric_key, label, required_value, raw_required_value, description in configured_thresholds:
            actual_value = metric_value_map.get(metric_key)
            if metric_key == "reviewer_settled_balance":
                passed = Decimal(str(actual_value or "0")) >= Decimal(str(raw_required_value))
                current_value = str(actual_value or "0")
            elif metric_key == "reviewer_account_age":
                passed = int(actual_value or 0) >= int(raw_required_value)
                current_value = _format_age_days(actual_value)
            else:
                passed = int(actual_value or 0) >= int(raw_required_value)
                current_value = int(actual_value or 0)
            threshold_results.append(bool(passed))
            checks.append(_eligibility_rule_check(
                rule_id=metric_key,
                label=label,
                description=description,
                passed=bool(passed),
                required=False,
                scope=scope,
                current_value=current_value,
                required_value=required_value,
                applicable=bool(normalized_wallet),
            ))

        if config.eligibility_mode == "activity":
            activity_passed = bool(decision.eligible or decision.matched_threshold or any(threshold_results))
            checks.append(_eligibility_rule_check(
                rule_id=f"{scope}_activity_path",
                label="Reviewer activity path",
                description=f"When reviewer activity mode is enabled, this wallet must satisfy at least one configured reviewer threshold before {scope_label} is allowed.",
                passed=activity_passed,
                required=True,
                scope=scope,
                current_value=decision.matched_threshold or ("no configured thresholds passed" if configured_thresholds else "no reviewer thresholds configured"),
                required_value="at least one configured reviewer threshold",
                applicable=bool(normalized_wallet),
            ))
        elif config.eligibility_mode == "hybrid":
            hybrid_passed = bool(override_entry or wallet_allowlisted or any(threshold_results))
            checks.append(_eligibility_rule_check(
                rule_id=f"{scope}_hybrid_policy_path",
                label="Hybrid reviewer policy path",
                description=f"When hybrid reviewer mode is enabled, {scope_label} can pass through either the configured review allowlist or reviewer activity thresholds.",
                passed=hybrid_passed,
                required=True,
                scope=scope,
                current_value=(
                    f"admin override ({override_entry.get('scope')})"
                    if override_entry
                    else "configured review allowlist"
                    if wallet_allowlisted
                    else decision.matched_threshold
                    or ("no configured thresholds passed" if configured_thresholds else "no reviewer thresholds configured")
                ),
                required_value="configured review allowlist or at least one configured reviewer threshold",
                applicable=bool(normalized_wallet),
            ))

    checks.append(_eligibility_rule_check(
        rule_id=f"{scope}_final_decision",
        label=f"{scope_label.title()} decision",
        description=f"This is the final backend decision after the configured {scope_label} rules and overrides are evaluated together.",
        passed=bool(decision.eligible),
        required=True,
        scope=scope,
        current_value=decision.reason or hard_block_reason or "eligible",
        required_value="eligible",
        applicable=bool(normalized_wallet),
    ))
    return checks


def _submission_policy_rule() -> str:
    return (
        "Submissions currently require controlled beta access for submissions plus a verified wallet session. "
        "This node does not apply a separate submission-only override gate."
    )


def _submission_status_message(reason: str | None) -> tuple[str, str | None]:
    normalized_reason = str(reason or "").strip().lower()
    message_map = {
        "wallet_not_verified": (
            "Submission is blocked until this wallet is verified.",
            "Connect and verify the wallet you want to use for submissions.",
        ),
        "wallet_not_bound": (
            "Submission is blocked because this wallet is not approved for the controlled beta yet.",
            "Ask an admin to approve this wallet for controlled beta access before submitting.",
        ),
        "wallet_binding_revoked": (
            "Submission is blocked because this wallet binding was revoked.",
            "Ask an admin to reapprove or rebind this wallet before submitting again.",
        ),
        "access_account_suspended": (
            "Submission is blocked because this access account is suspended.",
            "Ask an admin to reactivate this access account before submitting again.",
        ),
        "access_account_revoked": (
            "Submission is blocked because this access account is revoked.",
            "Ask an admin to reactivate this access account before submitting again.",
        ),
        "access_account_missing": (
            "Submission is blocked because this wallet is not attached to an active access account.",
            "Reconnect an approved wallet or ask an admin to restore access before submitting again.",
        ),
    }
    return message_map.get(normalized_reason, ("Submission is currently blocked.", None))


def _submission_eligibility_for_wallet(
    wallet_address: str | None,
    *,
    wallet_session_authenticated: bool,
    access_decision=None,
) -> dict[str, Any]:
    policy_rule = _submission_policy_rule()
    if not wallet_session_authenticated or not wallet_address:
        message, recommended_action = _submission_status_message("wallet_not_verified")
        return {
            "can_submit": False,
            "eligibility_status": "blocked",
            "eligibility_source": "blocked",
            "blocked_reason": "wallet_not_verified",
            "message": message,
            "recommended_action": recommended_action,
            "policy_rule": policy_rule,
            "allowlist_override_applied": False,
            "allowlist_scope": None,
        }

    decision = access_decision or access_decision_for_wallet(blockchain, wallet_address, feature="submissions")
    if not decision.allowed:
        message, recommended_action = _submission_status_message(decision.reason)
        return {
            "can_submit": False,
            "eligibility_status": "blocked",
            "eligibility_source": "blocked",
            "blocked_reason": decision.reason,
            "message": message,
            "recommended_action": recommended_action,
            "policy_rule": policy_rule,
            "allowlist_override_applied": False,
            "allowlist_scope": None,
        }

    return {
        "can_submit": True,
        "eligibility_status": "eligible",
        "eligibility_source": "normal_access_verified_wallet",
        "blocked_reason": None,
        "message": "Submission is allowed because this wallet has controlled beta access and the wallet session is verified.",
        "recommended_action": None,
        "policy_rule": policy_rule,
        "allowlist_override_applied": False,
        "allowlist_scope": None,
    }


def _enforce_submission_eligibility(wallet_address: str):
    decision = access_decision_for_wallet(blockchain, wallet_address, feature="submissions")
    submission_status = _submission_eligibility_for_wallet(
        wallet_address,
        wallet_session_authenticated=True,
        access_decision=decision,
    )
    if submission_status["can_submit"]:
        return decision, submission_status
    raise HTTPException(
        status_code=403,
        detail={
            "error": "submission_not_eligible",
            "reason": submission_status["blocked_reason"],
            "message": submission_status["message"],
            "recommended_action": submission_status["recommended_action"],
            "submission_policy": submission_status["policy_rule"],
            "allowlist_override_applied": submission_status["allowlist_override_applied"],
            "allowlist_scope": submission_status["allowlist_scope"],
            "access_control_mode": ACCESS_CONTROL_MODE,
        },
    )


def _build_eligibility_status_payload(
    *,
    wallet_address: str | None,
    access_account: dict | None,
    binding: dict | None,
    session_access_account: dict | None,
    invite_authenticated: bool,
    wallet_session_authenticated: bool,
    access_decision,
):
    access_payload = _access_status_payload(
        wallet_address=wallet_address,
        access_account=access_account,
        binding=binding,
        session_access_account=session_access_account,
        invite_authenticated=invite_authenticated,
        wallet_session_authenticated=wallet_session_authenticated,
        access_decision=access_decision,
    )
    blocked_reasons: list[dict[str, str]] = []
    possible_next_steps: list[str] = []
    allowlist_overrides_applied: list[dict[str, str]] = []
    rule_checks: list[dict[str, Any]] = []

    if access_payload.get("allowlist_override_applied"):
        allowlist_overrides_applied.append({
            "scope": "access",
            "allowlist_scope": str(access_payload.get("allowlist_scope") or "access"),
        })
    rule_checks.extend(_build_access_rule_checks(
        wallet_address=wallet_address,
        access_account=access_account,
        binding=binding,
        session_access_account=session_access_account,
        wallet_session_authenticated=wallet_session_authenticated,
        access_decision=access_decision,
        access_payload=access_payload,
    ))

    submission_status = _submission_eligibility_for_wallet(
        wallet_address,
        wallet_session_authenticated=wallet_session_authenticated,
    )
    can_submit = bool(submission_status.get("can_submit"))
    rule_checks.extend(_build_submission_rule_checks(
        wallet_address=wallet_address,
        wallet_session_authenticated=wallet_session_authenticated,
        submission_status=submission_status,
        access_payload=access_payload,
    ))
    can_vote = False
    can_receive_rewards = False

    voting_decision = None
    rewards_decision = None
    if wallet_address:
        _config, voting_decision = _review_eligibility_for_wallet(wallet_address, scope="voting")
        _config, rewards_decision = _review_eligibility_for_wallet(wallet_address, scope="rewards")
        can_vote = bool(access_payload.get("can_vote") and voting_decision.eligible and wallet_session_authenticated)
        can_receive_rewards = bool(
            access_payload.get("can_receive_rewards")
            and rewards_decision.eligible
            and wallet_session_authenticated
        )
        rule_checks.extend(_build_review_scope_rule_checks(
            wallet_address=wallet_address,
            scope="voting",
            decision=voting_decision,
            access_payload=access_payload,
            wallet_session_authenticated=wallet_session_authenticated,
        ))
        rule_checks.extend(_build_review_scope_rule_checks(
            wallet_address=wallet_address,
            scope="rewards",
            decision=rewards_decision,
            access_payload=access_payload,
            wallet_session_authenticated=wallet_session_authenticated,
        ))
        for scope_name, decision in (("voting", voting_decision), ("rewards", rewards_decision)):
            if decision.allowlist_override_applied:
                allowlist_overrides_applied.append({
                    "scope": scope_name,
                    "allowlist_scope": str(decision.allowlist_scope or scope_name),
                })
            if not decision.eligible:
                blocked_reasons.append({
                    "scope": scope_name,
                    "rule_id": f"{scope_name}_final_decision",
                    "reason": str(decision.blocked_reason or decision.reason or ""),
                    "message": _eligibility_reason_message(scope_name, decision.blocked_reason or decision.reason or ""),
                })
                possible_next_steps.append(decision.recommended_action)
    elif wallet_session_authenticated is False:
        possible_next_steps.append("Connect and verify a wallet so the app can show your current beta eligibility.")

    if not access_payload.get("access_granted"):
        blocked_reason = str(access_payload.get("blocked_reason") or "")
        if blocked_reason:
            blocked_reasons.insert(0, {
                "scope": "access",
                "rule_id": "access_approval_path",
                "reason": blocked_reason,
                "message": _eligibility_reason_message("access", blocked_reason),
            })
        if blocked_reason in {"wallet_not_bound", "wallet_not_allowlisted"}:
            possible_next_steps.append("Request an override or ask an admin to approve this wallet for controlled beta access.")
        elif blocked_reason == "wallet_not_verified":
            possible_next_steps.append("Connect and verify your wallet, then refresh your eligibility status.")
        elif blocked_reason.startswith("access_account_") or blocked_reason == "wallet_binding_revoked":
            possible_next_steps.append("Ask an admin to reactivate or reapprove this account before trying again.")

    if wallet_session_authenticated and access_payload.get("access_granted") and not can_vote:
        possible_next_steps.append("You can access the app, but review actions may still need reviewer eligibility or an override.")

    if not can_submit and submission_status.get("blocked_reason"):
        blocked_reasons.append({
            "scope": "submission",
            "rule_id": "submission_access_path",
            "reason": str(submission_status.get("blocked_reason") or ""),
            "message": str(submission_status.get("message") or _eligibility_reason_message("submission", submission_status.get("blocked_reason") or "")),
        })

    if submission_status.get("recommended_action"):
        possible_next_steps.append(str(submission_status["recommended_action"]))

    deduped_steps = list(dict.fromkeys([step for step in possible_next_steps if step]))
    deduped_blocked_reasons = []
    seen_block_keys = set()
    for item in blocked_reasons:
        key = (item.get("scope"), item.get("reason"), item.get("rule_id"))
        if key in seen_block_keys:
            continue
        seen_block_keys.add(key)
        deduped_blocked_reasons.append(item)

    return {
        "can_access_app": bool(access_payload.get("access_granted")),
        "access_granted": bool(access_payload.get("access_granted")),
        "connected_wallet": wallet_address,
        "wallet_bound": bool(access_payload.get("wallet_bound")),
        "can_submit": can_submit,
        "can_vote": can_vote,
        "can_receive_rewards": can_receive_rewards,
        "blocked_reasons": deduped_blocked_reasons,
        "allowlist_overrides_applied": allowlist_overrides_applied,
        "rule_checks": rule_checks,
        "next_steps": deduped_steps,
        "possible_next_steps": deduped_steps,
        "override_requests_enabled": True,
        "submission": submission_status,
        "access": access_payload,
    }


def _access_status_payload(
    *,
    wallet_address: str | None = None,
    access_account: dict | None = None,
    binding: dict | None = None,
    session_access_account: dict | None = None,
    invite_authenticated: bool = False,
    wallet_session_authenticated: bool = False,
    access_decision=None,
):
    effective_account = access_account or session_access_account
    account_status = str(effective_account.get("status") or "").strip().lower() if effective_account else ""
    wallet_bound = bool(
        binding
        and str(binding.get("status") or "").strip().lower() == "active"
        and access_account
        and str(access_account.get("status") or "").strip().lower() == "active"
    )
    allowlist_entry = _session_access_allowlist_entry(session_access_account)
    allowlist_override_applied = bool(
        (access_decision and access_decision.allowlist_override_applied)
        or allowlist_entry
    )
    allowlist_scope = None
    if access_decision and access_decision.allowlist_scope:
        allowlist_scope = access_decision.allowlist_scope
    elif allowlist_entry:
        allowlist_scope = str(allowlist_entry.get("scope") or "").strip().lower() or None
    access_granted = bool(
        wallet_bound
        or (access_decision and access_decision.allowed)
        or allowlist_entry
    )
    wallet_count = len(list(effective_account.get("bound_wallets", []))) if effective_account else 0
    payload = public_access_status_payload()
    blocked_reason = None
    eligibility_status = "blocked"
    if access_granted:
        eligibility_status = "approved"
        if allowlist_override_applied:
            eligibility_status = "allowlist_override"
    elif access_decision and access_decision.reason:
        blocked_reason = access_decision.reason
    elif binding and str(binding.get("status") or "").strip().lower() == "revoked":
        blocked_reason = "wallet_binding_revoked"
    elif account_status:
        blocked_reason = f"access_account_{account_status}"
    elif wallet_session_authenticated:
        blocked_reason = "wallet_not_allowlisted"
    elif invite_authenticated:
        blocked_reason = "wallet_not_bound"
    payload.update({
        "authenticated": bool(invite_authenticated or wallet_session_authenticated),
        "invite_authenticated": bool(invite_authenticated),
        "wallet_session_authenticated": bool(wallet_session_authenticated),
        "wallet_address": wallet_address,
        "wallet_bound": wallet_bound,
        "access_account_id": effective_account.get("access_account_id") if effective_account else None,
        "status": account_status or None,
        "access_account": _public_access_account(effective_account),
        "wallet_binding": _public_wallet_binding(binding),
        "access_granted": access_granted,
        "eligibility_status": eligibility_status,
        "blocked_reason": blocked_reason,
        "allowlist_override_applied": allowlist_override_applied,
        "allowlist_scope": allowlist_scope,
        "max_wallets": effective_account.get("max_wallets") if effective_account else None,
        "wallet_count": wallet_count,
        "can_submit": bool((access_granted or not REQUIRE_ACCESS_FOR_SUBMISSIONS) and wallet_session_authenticated),
        "can_vote": bool(access_granted or not REQUIRE_ACCESS_FOR_VOTES),
        "can_receive_rewards": bool(access_granted or not REQUIRE_ACCESS_FOR_REWARDS),
        "can_transfer": bool(access_granted or not REQUIRE_ACCESS_FOR_TRANSFERS),
    })
    return payload


def _enforce_access_for_feature(wallet_address: str | None, *, feature: str):
    blockchain.refresh_access_control_state_from_storage()
    decision = access_decision_for_wallet(blockchain, wallet_address, feature=feature)
    if decision.allowed:
        return decision
    reason_messages = {
        "wallet_not_verified": "Verify a wallet before trying this action.",
        "wallet_not_bound": "This wallet is not approved for the controlled beta yet.",
        "wallet_binding_revoked": "This wallet binding was revoked and must be reapproved before it can be used again.",
        "access_account_suspended": "This access account is suspended and must be reactivated by an admin.",
        "access_account_revoked": "This access account is revoked and must be reactivated by an admin.",
    }
    detail = {
        "error": "access_required",
        "reason": decision.reason,
        "feature": feature,
        "message": reason_messages.get(
            decision.reason,
            "A bound active controlled-testnet access account or approved access override is required for this action.",
        ),
        "access_control_mode": ACCESS_CONTROL_MODE,
        "recommended_action": "Enter an invite code or request access, then bind the verified MetaMask wallet.",
        "allowlist_override_applied": decision.allowlist_override_applied,
        "allowlist_scope": decision.allowlist_scope,
    }
    raise HTTPException(status_code=403, detail=detail)


def _resolve_access_account_from_session(access_session_token: str):
    access_account_id = access_session_manager.resolve_access_account_id(access_session_token)
    blockchain.refresh_access_control_state_from_storage()
    access_account = blockchain.get_access_account(access_account_id)
    if access_account is None:
        raise ValueError("Access account for this session no longer exists.")
    return access_account


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Preserve expected FastAPI/HTTPException responses."""
    return _public_error(exc.detail, status_code=exc.status_code)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Middleware to log API requests."""
    # Explicit Task 11A routers are shared module objects. Bind their existing
    # compatibility globals to this app's runtime before dependency resolution
    # and endpoint execution, including isolated two-node test runtimes.
    runtime = getattr(request.app.state, "api_runtime", None)
    if runtime is not None:
        routers = _importlib.import_module("api_routers")
        for router_module in (
            routers.public_chain,
            routers.access,
            routers.admin,
            routers.content,
            routers.native,
            routers.peer,
            routers.operations,
        ):
            router_module._runtime = runtime
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    client_host = request.client.host if request.client else "unknown"
    log_message = f"{client_host} - {request.method} {request.url.path} - {response.status_code} ({process_time:.2f}s)"
    logging.info(log_message)
    return response

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global error handler to log unexpected errors."""
    if isinstance(exc, StarletteHTTPException):
        return _public_error(exc.detail, status_code=exc.status_code)

    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return _safe_server_error()

# Backend info page for deployments where the Vue app is served separately.



project_owner = Wallet()  # ✅ Project owner (holds 79% of the supply)
contributor1 = Wallet()  # ✅ First contributor (receives 10%)
contributor2 = Wallet()  # ✅ Second contributor (receives 1%)

# Defer creating the global Blockchain instance until the app startup/lifespan
# so importing this module in tests does not load repository-root persistent
# files (blockchain.json) before test fixtures can set an isolated cwd/data dir.
blockchain = None















































































































































# @app.get("/get_wallets")
# async def get_wallets():
#     """
#     Retrieve all registered wallets (public keys only).
#     """
#     try:
#         return {
#             "message": "Registered wallets retrieved successfully.",
#             "wallets": [
#                 {"public_key": key}  # ✅ Only return public key (NO private key)
#                 for key in blockchain.wallets.keys()
#             ]
#         }
#     except Exception as e:
#         return JSONResponse(status_code=500, content={"error": str(e)})
































































































def _access_admin_audit_context(request: Request, session=None) -> dict[str, str | None]:
    """HTTP request metadata passed to facade-owned access/admin audit operations."""
    return {
        "actor_session_id": _safe_session_identifier(session),
        **_safe_request_metadata(request),
    }


def _refresh_access_control_read_state() -> None:
    """Shared read-side refresh boundary for access/admin HTTP adapters."""
    blockchain.refresh_access_control_state_from_storage()


def _chain_summary_payload() -> dict:
    """Shared public/peer chain-summary serialization compatibility helper."""
    payload = _health_payload()
    payload.update({
        "protocol_version": 1,
        "network_id": blockchain.protocol_v1_network_id(),
        "genesis_hash": blockchain.chain[0].hash,
        "canonical_genesis_hash": blockchain.public_testnet_v1_genesis_hash(),
        "cumulative_originality_score": blockchain.get_cumulative_originality_score(),
        "cumulative_work": None,
    })
    return payload


# Explicit routers capture decorators such as ``api_limit`` at import time.
# A reload of this runtime creates a new limiter, so router assembly uses this
# generation token to rebuild those HTTP adapters against the new shared wiring.
_ROUTER_RUNTIME_GENERATION = object()


__all__ = tuple(name for name in globals() if not name.startswith("__"))


# Keep direct imports and importlib.reload(api) compatible.  The dynamic import
# avoids reversing the architectural dependency: router modules depend on this
# runtime, while domain services remain entirely unaware of the API layer.
import importlib as _importlib

_routers = _importlib.import_module("api_routers")
app.state.api_runtime = _importlib.import_module(__name__)
if hasattr(_routers, "install_routers"):
    _routers.install_routers(app, _importlib.import_module(__name__))
