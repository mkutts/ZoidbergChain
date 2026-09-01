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


def _record_admin_audit_event(
    *,
    request: Request,
    action: str,
    result: str = "ok",
    session=None,
    request_id: str | None = None,
    override_request_id: str | None = None,
    feedback_id: str | None = None,
    access_account_id: str | None = None,
    allowlist_entry_id: str | None = None,
    wallet_address: str | None = None,
    reason: str | None = None,
    operator_note: str | None = None,
) -> dict:
    entry = blockchain.append_audit_log_entry({
        "action": action,
        "result": result,
        "actor_session_id": _safe_session_identifier(session),
        "request_id": request_id,
        "override_request_id": override_request_id,
        "feedback_id": normalize_text_field(feedback_id),
        "access_account_id": access_account_id,
        "allowlist_entry_id": allowlist_entry_id,
        "wallet_address": wallet_address,
        "reason": normalize_text_field(reason),
        "operator_note": normalize_text_field(operator_note),
        **_safe_request_metadata(request),
    })
    blockchain.save_blockchain()
    return entry


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


def _verified_wallet_dependency(authorization: str | None = Header(default=None)):
    return resolve_verified_wallet_from_authorization(authorization, manager=wallet_auth_manager)


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
@app.get("/")
async def home():
    """Serve the backend info page."""
    index_path = os.path.join("static", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse(status_code=404, content={"error": "Home page not found."})

@app.get("/about")
async def about():
    """Serve the About Us page (White Paper)."""
    about_path = os.path.join("static", "about.html")
    if os.path.exists(about_path):
        return FileResponse(about_path)
    return JSONResponse(status_code=404, content={"error": "About page not found."})

@app.get("/download_whitepaper")
async def download_whitepaper():
    """Serve the White Paper PDF for download."""
    pdf_path = os.path.join("static", f"{COIN_NAME}_WhitePaper.pdf")
    if os.path.exists(pdf_path):
        return FileResponse(pdf_path, filename=f"{COIN_NAME}_WhitePaper.pdf", media_type="application/pdf")
    return JSONResponse(status_code=404, content={"error": "White paper not found."})

project_owner = Wallet()  # ✅ Project owner (holds 79% of the supply)
contributor1 = Wallet()  # ✅ First contributor (receives 10%)
contributor2 = Wallet()  # ✅ Second contributor (receives 1%)

# Defer creating the global Blockchain instance until the app startup/lifespan
# so importing this module in tests does not load repository-root persistent
# files (blockchain.json) before test fixtures can set an isolated cwd/data dir.
blockchain = None

def _reset_blockchain_to_genesis():
    global project_owner, contributor1, contributor2, blockchain
    blockchain.storage.delete_blockchain_document()
    wallet_auth_manager.clear()

    project_owner = Wallet()
    contributor1 = Wallet()
    contributor2 = Wallet()

    blockchain = Blockchain(
        project_owner_wallet=project_owner,
        Contributor_one=contributor1,
        Contributor_two=contributor2
    )
    return {"message": "Blockchain reset to Genesis state."}


@app.post("/dev/reset")
@api_limit("dev_endpoint")
async def dev_reset_blockchain(request: Request):
    """Development-only reset to Genesis state."""
    require_development_mode(allow_dev_reset_endpoints(), "Development reset endpoints")
    try:
        return {
            "warning": DEV_ENDPOINT_WARNING,
            **_reset_blockchain_to_genesis(),
        }
    except Exception:
        logger.exception("Development reset failed")
        return _safe_server_error()


@app.post("/reset_blockchain")
@api_limit("dev_endpoint")
async def reset_blockchain(request: Request):
    """Legacy development-only reset route. Prefer /dev/reset."""
    require_development_mode(allow_dev_reset_endpoints(), "Development reset endpoints")
    return {
        "warning": DEV_ENDPOINT_WARNING,
        "deprecated_route": True,
        "replacement": "/dev/reset",
        **_reset_blockchain_to_genesis(),
    }

@app.get("/dev/debug")
@api_limit("dev_endpoint")
async def dev_debug(request: Request):
    """Development-only node diagnostics with no key material."""
    require_development_mode(allow_dev_reset_endpoints(), "Development debug endpoints")
    latest_block = blockchain.get_latest_block()
    return {
        "warning": DEV_ENDPOINT_WARNING,
        "environment": ENVIRONMENT,
        "network_name": NETWORK_NAME,
        "node_id": NODE_ID,
        "public_node_url": PUBLIC_NODE_URL,
        "chain_height": latest_block.index,
        "latest_block_hash": latest_block.hash,
        "wallet_count": len(blockchain.wallets),
        "peer_count": len(peer_store.list_peers()),
    }


@app.get("/sync")
@api_limit("chain_sync")
async def sync_blockchain(request: Request):
    """Returns the latest blockchain state for syncing with other nodes."""
    return {"chain": blockchain.get_chain()}


@app.get("/health")
@api_limit("public_read")
async def health(request: Request):
    return _health_payload()


@app.get("/status")
@api_limit("public_read")
async def status(request: Request):
    return _status_payload()


@app.get("/ops/status")
@api_limit("public_read")
async def public_ops_status(request: Request):
    return _status_payload()


@app.get("/node-info")
@api_limit("public_read")
async def node_info(request: Request):
    payload = _health_payload()
    payload.update({
        "node_id": NODE_ID,
        "public_node_url": PUBLIC_NODE_URL,
        "cumulative_originality_score": blockchain.get_cumulative_originality_score(),
    })
    return payload


@app.post("/feedback")
@api_limit("submission_create")
async def create_feedback(
    request: Request,
    payload: FeedbackCreateRequest,
    authorization: str | None = Header(default=None),
    x_zoid_access_session: str | None = Header(default=None, alias="X-ZOID-Access-Session"),
):
    blockchain.refresh_access_control_state_from_storage()
    verified_wallet_address = None
    access_account = None

    if authorization:
        try:
            verified_wallet_address = resolve_verified_wallet_from_authorization(
                authorization,
                manager=wallet_auth_manager,
            )
            access_account = blockchain.get_access_account_for_wallet(verified_wallet_address)
        except HTTPException:
            verified_wallet_address = None

    if access_account is None and x_zoid_access_session:
        try:
            access_account = _resolve_access_account_from_session(x_zoid_access_session)
        except ValueError:
            access_account = None

    request_metadata = _safe_request_metadata(request)
    try:
        feedback = blockchain.create_feedback(
            feedback_type=payload.type,
            title=payload.title,
            description=payload.description,
            name=payload.name or (access_account.get("name") if access_account else None),
            email=payload.email or (access_account.get("email") if access_account else None),
            handle=payload.handle or (access_account.get("handle") if access_account else None),
            wallet_address=verified_wallet_address or payload.wallet_address,
            access_account_id=payload.access_account_id or (access_account.get("access_account_id") if access_account else None),
            current_page=payload.current_page,
            current_flow=payload.current_flow,
            user_agent=request_metadata["user_agent"],
            remote_ip=request_metadata["remote_ip"],
            browser_metadata=_sanitize_feedback_browser_metadata(payload.browser_metadata),
            eligibility_snapshot=_sanitize_feedback_eligibility_snapshot(payload.eligibility_snapshot),
            viewport_width=payload.viewport_width,
            viewport_height=payload.viewport_height,
            is_mobile=payload.is_mobile,
        )
        blockchain.save_blockchain()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "message": "Feedback submitted. Thanks for helping test the controlled beta.",
        "feedback": _public_feedback(feedback),
    }


@app.get("/access/status")
@api_limit("public_read")
async def get_access_status(request: Request):
    return public_access_status_payload()


@app.post("/access/request")
@api_limit("submission_create")
async def create_access_request(request: Request, payload: AccessRequestCreate):
    if not ACCESS_REQUESTS_ENABLED:
        raise HTTPException(status_code=403, detail="Access requests are disabled on this node.")
    if ACCESS_CONTROL_MODE == "disabled":
        raise HTTPException(status_code=403, detail="Access control is disabled on this node.")
    try:
        access_request = blockchain.create_access_request(
            name=payload.name,
            email=payload.email,
            handle=payload.handle,
            reason=payload.reason,
            notes=payload.notes,
        )
        blockchain.save_blockchain()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": "Access request submitted.",
        "request": _public_access_request(access_request),
    }


@app.post("/access/login")
@api_limit("wallet_create")
async def login_with_access_code(request: Request, payload: AccessLoginRequest):
    blockchain.refresh_access_control_state_from_storage()
    account = blockchain.resolve_access_account_by_invite_code(payload.access_code, include_redeemed=True)
    if account is None:
        raise HTTPException(status_code=401, detail="Invalid invite/access code.")
    if not account.get("invite_code_hash"):
        raise HTTPException(status_code=409, detail="Invite/access code has already been redeemed.")
    if str(account.get("status") or "").strip().lower() != "active":
        raise HTTPException(status_code=403, detail="Access account is not active.")
    session = access_session_manager.issue_session(account["access_account_id"])
    blockchain.mark_access_account_login(account["access_account_id"])
    blockchain.save_blockchain()
    return {
        "message": "Invite accepted. Connect and verify MetaMask to bind the wallet.",
        "access_account": _public_access_account(account),
        **session,
    }


@app.post("/access/bind-wallet")
@api_limit("wallet_create")
async def bind_access_wallet(
    request: Request,
    payload: AccessBindWalletRequest | None = None,
    access_session_token: str = Depends(_access_session_dependency),
    wallet_address: str = Depends(_verified_wallet_dependency),
):
    try:
        access_account = _resolve_access_account_from_session(access_session_token)
        normalized_payload_wallet = normalize_wallet_address(payload.wallet_address) if payload and payload.wallet_address else None
        normalized_verified_wallet = normalize_wallet_address(wallet_address)
        if normalized_payload_wallet and normalized_payload_wallet != normalized_verified_wallet:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "verified_wallet_mismatch",
                    "reason": "verified_wallet_session_does_not_match_requested_wallet",
                    "message": "The verified MetaMask wallet session does not match the requested wallet binding.",
                },
            )
        binding = blockchain.bind_wallet_to_access_account(
            access_account["access_account_id"],
            wallet_address,
            source="invite_code",
        )
        access_session_manager.mark_wallet_bound(access_session_token, wallet_address)
        blockchain.save_blockchain()
        access_account = blockchain.get_access_account(access_account["access_account_id"])
    except ValueError as exc:
        detail = str(exc)
        status_code = 400
        if "missing access session" in detail.lower() or "no active access session" in detail.lower() or "expired" in detail.lower():
            status_code = 401
        elif "already associated with a different verified wallet" in detail.lower():
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "access_session_wallet_mismatch",
                    "reason": "access_session_already_bound_to_different_wallet",
                    "message": detail,
                },
            ) from exc
        elif "already bound to a different access account" in detail.lower():
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "wallet_already_bound_elsewhere",
                    "reason": "wallet_is_already_bound_to_different_access_account",
                    "message": detail,
                },
            ) from exc
        elif "maximum number of bound wallets" in detail.lower():
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "wallet_limit_reached",
                    "reason": "access_account_already_has_maximum_wallets",
                    "message": detail,
                },
            ) from exc
        elif "not found" in detail.lower() or "not active" in detail.lower():
            status_code = 403
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return {
        "message": "Wallet bound to controlled-testnet access account.",
        "access_account": _public_access_account(access_account),
        "wallet_binding": _public_wallet_binding(binding),
        "access": _access_status_payload(
            wallet_address=wallet_address,
            access_account=access_account,
            binding=binding,
            session_access_account=access_account,
            invite_authenticated=True,
            wallet_session_authenticated=True,
        ),
    }


@app.get("/access/me")
@api_limit("public_read")
async def get_access_me(
    request: Request,
    authorization: str | None = Header(default=None),
    x_zoid_access_session: str | None = Header(default=None, alias="X-ZOID-Access-Session"),
):
    blockchain.refresh_access_control_state_from_storage()
    wallet_address = None
    access_account = None
    binding = None
    session_access_account = None
    wallet_session_authenticated = False
    invite_authenticated = False
    access_decision = None

    if authorization:
        try:
            wallet_address = resolve_verified_wallet_from_authorization(
                authorization,
                manager=wallet_auth_manager,
            )
            wallet_session_authenticated = True
            binding = blockchain.get_wallet_binding(wallet_address)
            access_account = blockchain.get_access_account_for_wallet(wallet_address)
            access_decision = access_decision_for_wallet(blockchain, wallet_address, feature="app")
        except HTTPException as exc:
            raise HTTPException(status_code=401, detail=exc.detail) from exc

    if x_zoid_access_session:
        try:
            session_access_account = _resolve_access_account_from_session(x_zoid_access_session)
            invite_authenticated = True
        except ValueError as exc:
            if not wallet_session_authenticated or access_account is None:
                raise HTTPException(status_code=401, detail=str(exc)) from exc

    return _access_status_payload(
        wallet_address=wallet_address,
        access_account=access_account,
        binding=binding,
        session_access_account=session_access_account,
        invite_authenticated=invite_authenticated,
        wallet_session_authenticated=wallet_session_authenticated,
        access_decision=access_decision,
    )


@app.get("/eligibility/status")
@api_limit("public_read")
async def get_eligibility_status(
    request: Request,
    authorization: str | None = Header(default=None),
    x_zoid_access_session: str | None = Header(default=None, alias="X-ZOID-Access-Session"),
):
    blockchain.refresh_access_control_state_from_storage()
    wallet_address = None
    access_account = None
    binding = None
    session_access_account = None
    wallet_session_authenticated = False
    invite_authenticated = False
    access_decision = None

    if authorization:
        try:
            wallet_address = resolve_verified_wallet_from_authorization(
                authorization,
                manager=wallet_auth_manager,
            )
            wallet_session_authenticated = True
            binding = blockchain.get_wallet_binding(wallet_address)
            access_account = blockchain.get_access_account_for_wallet(wallet_address)
            access_decision = access_decision_for_wallet(blockchain, wallet_address, feature="app")
        except HTTPException as exc:
            raise HTTPException(status_code=401, detail=exc.detail) from exc

    if x_zoid_access_session:
        try:
            session_access_account = _resolve_access_account_from_session(x_zoid_access_session)
            invite_authenticated = True
        except ValueError as exc:
            if not wallet_session_authenticated or access_account is None:
                raise HTTPException(status_code=401, detail=str(exc)) from exc

    return _build_eligibility_status_payload(
        wallet_address=wallet_address,
        access_account=access_account,
        binding=binding,
        session_access_account=session_access_account,
        invite_authenticated=invite_authenticated,
        wallet_session_authenticated=wallet_session_authenticated,
        access_decision=access_decision,
    )


@app.post("/eligibility/override-requests")
@api_limit("submission_create")
async def create_override_request(
    request: Request,
    payload: OverrideRequestCreate,
    authorization: str | None = Header(default=None),
    x_zoid_access_session: str | None = Header(default=None, alias="X-ZOID-Access-Session"),
):
    blockchain.refresh_access_control_state_from_storage()
    wallet_address = None
    access_account = None
    if authorization:
        try:
            wallet_address = resolve_verified_wallet_from_authorization(
                authorization,
                manager=wallet_auth_manager,
            )
            access_account = blockchain.get_access_account_for_wallet(wallet_address)
        except HTTPException:
            wallet_address = None
    if not access_account and x_zoid_access_session:
        try:
            access_account = _resolve_access_account_from_session(x_zoid_access_session)
        except ValueError:
            access_account = None

    try:
        override_request = blockchain.create_override_request(
            requested_scope=payload.requested_scope,
            name=payload.name,
            email=payload.email or (access_account.get("email") if access_account else None),
            handle=payload.handle or (access_account.get("handle") if access_account else None),
            wallet_address=payload.wallet_address or wallet_address,
            access_account_id=payload.access_account_id or (access_account.get("access_account_id") if access_account else None),
            reason=payload.reason,
            current_page=payload.current_page,
            detected_blocked_reason=payload.detected_blocked_reason,
            user_agent=(request.headers.get("user-agent") or ""),
            remote_ip=(request.client.host if request.client else ""),
        )
        blockchain.save_blockchain()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _record_admin_audit_event(
        request=request,
        action="override_request_submitted",
        override_request_id=override_request.get("override_request_id"),
        access_account_id=override_request.get("access_account_id"),
        wallet_address=override_request.get("wallet_address"),
        reason=override_request.get("detected_blocked_reason"),
    )
    return {
        "message": "Override request submitted.",
        "override_request": _public_override_request(override_request),
    }


@app.post("/admin/login")
@api_limit("admin_login")
async def admin_login(request: Request, response: Response, payload: AdminLoginRequest):
    _require_admin_ui_enabled()
    if _admin_auth_disabled_for_local_dev():
        return {
            "message": "Admin auth is disabled for local development.",
            **_admin_session_status_payload(authenticated=True, reason="development_admin_auth_disabled"),
        }
    if not _admin_auth_configured():
        raise HTTPException(status_code=503, detail="Admin auth is not configured on this node.")
    if not verify_admin_credential(
        payload.password,
        password_hash=ADMIN_PASSWORD_HASH,
        bootstrap_token=ADMIN_BOOTSTRAP_TOKEN,
    ):
        client_host = request.client.host if request.client else "unknown"
        logger.warning("Failed admin login attempt from %s", client_host)
        _record_admin_audit_event(
            request=request,
            action="admin_login_failure",
            result="failure",
            reason="invalid_admin_credential",
        )
        raise HTTPException(status_code=401, detail="Invalid admin credential.")

    session_payload = admin_session_manager.issue_session()
    _set_admin_session_cookie(
        response,
        request=request,
        token=session_payload["admin_session_token"],
        expires_at=session_payload["expires_at"],
    )
    session = admin_session_manager.get_session(session_payload["admin_session_token"])
    _record_admin_audit_event(
        request=request,
        action="admin_login_success",
        session=session,
    )
    return {
        "message": "Admin session started.",
        **_admin_session_status_payload(authenticated=True, session=session),
    }


@app.post("/admin/logout")
@api_limit("public_read")
async def admin_logout(
    request: Request,
    response: Response,
    x_zoid_admin_session: str | None = Header(default=None, alias="X-ZOID-Admin-Session"),
):
    _require_admin_ui_enabled()
    token = _get_admin_session_token(request, x_zoid_admin_session)
    session = None
    if token:
        try:
            session = admin_session_manager.get_session(token)
        except ValueError:
            session = None
    if token:
        admin_session_manager.revoke_session(token)
    if session is not None:
        _record_admin_audit_event(
            request=request,
            action="admin_logout",
            session=session,
        )
    _clear_admin_session_cookie(response, request=request)
    return {
        "message": "Admin session ended.",
        **_admin_session_status_payload(authenticated=False, reason="logged_out"),
    }


@app.get("/admin/session")
@api_limit("public_read")
async def admin_session_status(
    request: Request,
    x_zoid_admin_session: str | None = Header(default=None, alias="X-ZOID-Admin-Session"),
):
    _require_admin_ui_enabled()
    if _admin_auth_disabled_for_local_dev():
        return _admin_session_status_payload(
            authenticated=True,
            reason="development_admin_auth_disabled",
        )
    if not _admin_auth_configured():
        return _admin_session_status_payload(
            authenticated=False,
            reason="admin_auth_not_configured",
        )

    token = _get_admin_session_token(request, x_zoid_admin_session)
    if not token:
        return _admin_session_status_payload(
            authenticated=False,
            reason="not_authenticated",
        )

    try:
        session = admin_session_manager.get_session(token)
    except ValueError:
        return _admin_session_status_payload(
            authenticated=False,
            reason="invalid_or_expired_session",
        )
    return _admin_session_status_payload(authenticated=True, session=session)


@app.get("/admin/access/requests")
@api_limit("public_read")
async def admin_list_access_requests(
    request: Request,
    status: str | None = Query(default=None),
    _admin_session=Depends(_require_admin_session),
):
    blockchain.refresh_access_control_state_from_storage()
    return {
        "requests": [
            _admin_access_request(item)
            for item in blockchain.list_access_requests(status=status.strip() if isinstance(status, str) and status.strip() else None)
        ],
    }


@app.post("/admin/access/requests/{request_id}/approve")
@api_limit("wallet_create")
async def admin_approve_access_request(
    request: Request,
    request_id: str,
    payload: AdminApproveAccessRequest,
    _admin_session=Depends(_require_admin_session),
):
    blockchain.refresh_access_control_state_from_storage()
    try:
        access_account, invite_code = blockchain.approve_access_request(
            request_id,
            reviewed_by=payload.reviewed_by,
            operator_notes=payload.operator_notes,
            max_wallets=payload.max_wallets,
        )
        blockchain.save_blockchain()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_admin_audit_event(
        request=request,
        action="access_request_approved",
        session=_admin_session,
        request_id=request_id,
        access_account_id=access_account.get("access_account_id"),
        operator_note=payload.operator_notes,
    )
    return {
        "message": "Access request approved.",
        "warning": "Invite codes are shown once. Copy before leaving this screen.",
        "invite_code": invite_code,
        "access_account": _admin_access_account(access_account),
        "request": _admin_access_request(blockchain.get_access_request(request_id)),
    }


@app.post("/admin/access/requests/{request_id}/reject")
@api_limit("wallet_create")
async def admin_reject_access_request(
    request: Request,
    request_id: str,
    payload: AdminRejectAccessRequest,
    _admin_session=Depends(_require_admin_session),
):
    blockchain.refresh_access_control_state_from_storage()
    try:
        request_record = blockchain.reject_access_request(
            request_id,
            reviewed_by=payload.reviewed_by,
            operator_notes=payload.operator_notes,
        )
        blockchain.save_blockchain()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_admin_audit_event(
        request=request,
        action="access_request_rejected",
        session=_admin_session,
        request_id=request_id,
        operator_note=payload.operator_notes,
    )
    return {
        "message": "Access request rejected.",
        "request": _admin_access_request(request_record),
    }


@app.post("/admin/access/invites")
@api_limit("wallet_create")
async def admin_create_access_invite(
    request: Request,
    payload: AdminCreateInviteRequest,
    _admin_session=Depends(_require_admin_session),
):
    blockchain.refresh_access_control_state_from_storage()
    try:
        access_account, invite_code = blockchain.create_access_invite(
            name=payload.name,
            email=payload.email,
            handle=payload.handle,
            notes=payload.notes,
            reviewed_by=payload.reviewed_by,
            operator_notes=payload.operator_notes,
            max_wallets=payload.max_wallets,
        )
        blockchain.save_blockchain()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_admin_audit_event(
        request=request,
        action="direct_invite_created",
        session=_admin_session,
        access_account_id=access_account.get("access_account_id"),
        operator_note=payload.operator_notes,
    )
    return {
        "message": "Access invite created.",
        "warning": "Invite codes are shown once. Copy before leaving this screen.",
        "invite_code": invite_code,
        "access_account": _admin_access_account(access_account),
    }


@app.get("/admin/access/accounts")
@api_limit("public_read")
async def admin_list_access_accounts(
    request: Request,
    status: str | None = Query(default=None),
    _admin_session=Depends(_require_admin_session),
):
    blockchain.refresh_access_control_state_from_storage()
    return {
        "accounts": [
            _admin_access_account(item)
            for item in blockchain.list_access_accounts(status=status.strip() if isinstance(status, str) and status.strip() else None)
        ],
    }


@app.get("/admin/access/accounts/{access_account_id}")
@api_limit("public_read")
async def admin_get_access_account(
    request: Request,
    access_account_id: str,
    _admin_session=Depends(_require_admin_session),
):
    blockchain.refresh_access_control_state_from_storage()
    access_account = blockchain.get_access_account(access_account_id)
    if access_account is None:
        raise HTTPException(status_code=404, detail=f"Access account not found: {access_account_id}")
    return {
        "access_account": _admin_access_account(access_account),
        "wallet_bindings": [
            _admin_wallet_binding(binding)
            for binding in blockchain.list_wallet_bindings(access_account_id=access_account_id)
        ],
    }


@app.get("/admin/allowlist")
@api_limit("public_read")
async def admin_list_allowlist(
    request: Request,
    scope: str | None = Query(default=None),
    subject_type: str | None = Query(default=None),
    subject_value: str | None = Query(default=None),
    status: str | None = Query(default=None),
    _admin_session=Depends(_require_admin_session),
):
    blockchain.refresh_access_control_state_from_storage()
    return {
        "allowlist_entries": [
            _admin_allowlist_entry(entry)
            for entry in blockchain.list_allowlist_entries(
                scope=scope,
                subject_type=subject_type,
                subject_value=subject_value,
                status=status,
            )
        ],
    }


@app.post("/admin/allowlist")
@api_limit("wallet_create")
async def admin_create_allowlist_entry(
    request: Request,
    payload: AdminAllowlistCreateRequest,
    _admin_session=Depends(_require_admin_session),
):
    blockchain.refresh_access_control_state_from_storage()
    try:
        entry = blockchain.create_allowlist_entry(
            scope=payload.scope,
            subject_type=payload.subject_type,
            subject_value=payload.subject_value,
            reason=payload.reason,
            expires_at=payload.expires_at,
            created_by=_safe_session_identifier(_admin_session),
        )
        blockchain.save_blockchain()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_admin_audit_event(
        request=request,
        action="allowlist_entry_created",
        session=_admin_session,
        allowlist_entry_id=entry.get("allowlist_entry_id"),
        access_account_id=entry.get("subject_value") if entry.get("subject_type") == "access_account" else None,
        wallet_address=entry.get("subject_value") if entry.get("subject_type") == "wallet" else None,
        reason=entry.get("scope"),
        operator_note=entry.get("reason"),
    )
    return {
        "message": "Allowlist entry created.",
        "allowlist_entry": _admin_allowlist_entry(entry),
    }


@app.get("/admin/allowlist/{allowlist_entry_id}")
@api_limit("public_read")
async def admin_get_allowlist_entry(
    request: Request,
    allowlist_entry_id: str,
    _admin_session=Depends(_require_admin_session),
):
    blockchain.refresh_access_control_state_from_storage()
    entry = blockchain.get_allowlist_entry(allowlist_entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Allowlist entry not found: {allowlist_entry_id}")
    return {
        "allowlist_entry": _admin_allowlist_entry(entry),
    }


@app.patch("/admin/allowlist/{allowlist_entry_id}")
@api_limit("wallet_create")
async def admin_update_allowlist_entry(
    request: Request,
    allowlist_entry_id: str,
    payload: AdminAllowlistUpdateRequest,
    _admin_session=Depends(_require_admin_session),
):
    blockchain.refresh_access_control_state_from_storage()
    try:
        entry = blockchain.update_allowlist_entry(
            allowlist_entry_id,
            scope=payload.scope,
            subject_type=payload.subject_type,
            subject_value=payload.subject_value,
            reason=payload.reason,
            expires_at=payload.expires_at,
            status=payload.status,
        )
        blockchain.save_blockchain()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_admin_audit_event(
        request=request,
        action="allowlist_entry_updated",
        session=_admin_session,
        allowlist_entry_id=entry.get("allowlist_entry_id"),
        access_account_id=entry.get("subject_value") if entry.get("subject_type") == "access_account" else None,
        wallet_address=entry.get("subject_value") if entry.get("subject_type") == "wallet" else None,
        reason=entry.get("scope"),
        operator_note=entry.get("reason"),
    )
    return {
        "message": "Allowlist entry updated.",
        "allowlist_entry": _admin_allowlist_entry(entry),
    }


@app.post("/admin/allowlist/{allowlist_entry_id}/revoke")
@api_limit("wallet_create")
async def admin_revoke_allowlist_entry(
    request: Request,
    allowlist_entry_id: str,
    payload: AdminAllowlistRevokeRequest,
    _admin_session=Depends(_require_admin_session),
):
    blockchain.refresh_access_control_state_from_storage()
    try:
        entry = blockchain.revoke_allowlist_entry(
            allowlist_entry_id,
            revoked_reason=payload.revoked_reason,
        )
        blockchain.save_blockchain()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_admin_audit_event(
        request=request,
        action="allowlist_entry_revoked",
        session=_admin_session,
        allowlist_entry_id=entry.get("allowlist_entry_id"),
        access_account_id=entry.get("subject_value") if entry.get("subject_type") == "access_account" else None,
        wallet_address=entry.get("subject_value") if entry.get("subject_type") == "wallet" else None,
        reason=entry.get("scope"),
        operator_note=payload.revoked_reason,
    )
    return {
        "message": "Allowlist entry revoked.",
        "allowlist_entry": _admin_allowlist_entry(entry),
    }


@app.post("/admin/allowlist/{allowlist_entry_id}/reactivate")
@api_limit("wallet_create")
async def admin_reactivate_allowlist_entry(
    request: Request,
    allowlist_entry_id: str,
    payload: AdminAllowlistReactivateRequest,
    _admin_session=Depends(_require_admin_session),
):
    blockchain.refresh_access_control_state_from_storage()
    try:
        entry = blockchain.reactivate_allowlist_entry(
            allowlist_entry_id,
            reason=payload.reason,
        )
        blockchain.save_blockchain()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_admin_audit_event(
        request=request,
        action="allowlist_entry_reactivated",
        session=_admin_session,
        allowlist_entry_id=entry.get("allowlist_entry_id"),
        access_account_id=entry.get("subject_value") if entry.get("subject_type") == "access_account" else None,
        wallet_address=entry.get("subject_value") if entry.get("subject_type") == "wallet" else None,
        reason=entry.get("scope"),
        operator_note=payload.reason,
    )
    return {
        "message": "Allowlist entry reactivated.",
        "allowlist_entry": _admin_allowlist_entry(entry),
    }


@app.get("/admin/override-requests")
@api_limit("public_read")
async def admin_list_override_requests(
    request: Request,
    status: str | None = Query(default=None),
    requested_scope: str | None = Query(default=None),
    _admin_session=Depends(_require_admin_session),
):
    blockchain.refresh_access_control_state_from_storage()
    return {
        "override_requests": [
            _admin_override_request(record)
            for record in blockchain.list_override_requests(
                status=status,
                requested_scope=requested_scope,
            )
        ],
    }


@app.post("/admin/override-requests/{override_request_id}/approve")
@api_limit("wallet_create")
async def admin_approve_override_request(
    request: Request,
    override_request_id: str,
    payload: AdminOverrideRequestDecision,
    _admin_session=Depends(_require_admin_session),
):
    blockchain.refresh_access_control_state_from_storage()
    override_request = blockchain.get_override_request(override_request_id)
    if override_request is None:
        raise HTTPException(status_code=404, detail=f"Override request not found: {override_request_id}")
    resolved_scope = payload.resolved_scope or override_request.get("requested_scope")
    subject_type = "wallet" if override_request.get("wallet_address") else "access_account"
    subject_value = override_request.get("wallet_address") or override_request.get("access_account_id")
    if not subject_value:
        normalized_email = normalize_email(override_request.get("email"))
        normalized_handle = normalize_handle(override_request.get("handle"))
        if normalized_email:
            subject_type = "email"
            subject_value = normalized_email
        elif normalized_handle:
            subject_type = "handle"
            subject_value = normalized_handle
    if not subject_value:
        raise HTTPException(status_code=400, detail="Override request cannot be approved without a wallet, access account, email, or handle.")
    try:
        entry = blockchain.create_allowlist_entry(
            scope=resolved_scope,
            subject_type=subject_type,
            subject_value=subject_value,
            reason=payload.admin_note or override_request.get("reason"),
            created_by=_safe_session_identifier(_admin_session),
        )
        override_request = blockchain.update_override_request_status(
            override_request_id,
            status="approved",
            reviewed_by=payload.reviewed_by,
            admin_note=payload.admin_note,
            resolved_scope=resolved_scope,
            approved_allowlist_entry_id=entry.get("allowlist_entry_id"),
        )
        blockchain.save_blockchain()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_admin_audit_event(
        request=request,
        action="allowlist_entry_created",
        session=_admin_session,
        allowlist_entry_id=entry.get("allowlist_entry_id"),
        access_account_id=override_request.get("access_account_id"),
        wallet_address=override_request.get("wallet_address"),
        reason=resolved_scope,
        operator_note=payload.admin_note or override_request.get("reason"),
    )
    _record_admin_audit_event(
        request=request,
        action="override_request_approved",
        session=_admin_session,
        override_request_id=override_request_id,
        allowlist_entry_id=entry.get("allowlist_entry_id"),
        access_account_id=override_request.get("access_account_id"),
        wallet_address=override_request.get("wallet_address"),
        reason=resolved_scope,
        operator_note=payload.admin_note,
    )
    return {
        "message": "Override request approved and allowlist entry created.",
        "override_request": _admin_override_request(override_request),
        "allowlist_entry": _admin_allowlist_entry(entry),
    }


@app.post("/admin/override-requests/{override_request_id}/reject")
@api_limit("wallet_create")
async def admin_reject_override_request(
    request: Request,
    override_request_id: str,
    payload: AdminOverrideRequestDecision,
    _admin_session=Depends(_require_admin_session),
):
    blockchain.refresh_access_control_state_from_storage()
    try:
        override_request = blockchain.update_override_request_status(
            override_request_id,
            status="rejected",
            reviewed_by=payload.reviewed_by,
            admin_note=payload.admin_note,
            resolved_scope=payload.resolved_scope,
        )
        blockchain.save_blockchain()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_admin_audit_event(
        request=request,
        action="override_request_rejected",
        session=_admin_session,
        override_request_id=override_request_id,
        access_account_id=override_request.get("access_account_id"),
        wallet_address=override_request.get("wallet_address"),
        reason=payload.resolved_scope or override_request.get("requested_scope"),
        operator_note=payload.admin_note,
    )
    return {
        "message": "Override request rejected.",
        "override_request": _admin_override_request(override_request),
    }


@app.get("/admin/feedback")
@api_limit("public_read")
async def admin_list_feedback(
    request: Request,
    status: str | None = Query(default=None),
    feedback_type: str | None = Query(default=None, alias="type"),
    priority: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _admin_session=Depends(_require_admin_session),
):
    blockchain.refresh_access_control_state_from_storage()
    try:
        records = blockchain.list_feedback(
            status=status,
            feedback_type=feedback_type,
            priority=priority,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "summary": blockchain.feedback_summary(),
        "feedback_items": [_admin_feedback(record) for record in records],
    }


@app.get("/admin/feedback/{feedback_id}")
@api_limit("public_read")
async def admin_get_feedback(
    request: Request,
    feedback_id: str,
    _admin_session=Depends(_require_admin_session),
):
    blockchain.refresh_access_control_state_from_storage()
    record = blockchain.get_feedback(feedback_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Feedback not found: {feedback_id}")
    _record_admin_audit_event(
        request=request,
        action="feedback_viewed",
        session=_admin_session,
        feedback_id=feedback_id,
    )
    return {
        "feedback": _admin_feedback(record),
    }


@app.patch("/admin/feedback/{feedback_id}")
@api_limit("wallet_create")
async def admin_update_feedback(
    request: Request,
    feedback_id: str,
    payload: AdminFeedbackUpdateRequest,
    _admin_session=Depends(_require_admin_session),
):
    blockchain.refresh_access_control_state_from_storage()
    record = blockchain.get_feedback(feedback_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Feedback not found: {feedback_id}")
    if payload.status is None and payload.priority is None and not payload.admin_note:
        raise HTTPException(status_code=400, detail="At least one feedback update field is required.")

    previous_status = str(record.get("status") or "").strip().lower()
    previous_priority = str(record.get("priority") or "").strip().lower()
    try:
        if payload.status is not None or payload.priority is not None:
            record = blockchain.update_feedback(
                feedback_id,
                status=payload.status,
                priority=payload.priority,
                reviewed_by=payload.reviewed_by,
            )
        if payload.admin_note:
            blockchain.add_feedback_admin_note(
                feedback_id,
                note=payload.admin_note,
                created_by=payload.reviewed_by,
            )
        blockchain.save_blockchain()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    current_status = str(record.get("status") or "").strip().lower()
    current_priority = str(record.get("priority") or "").strip().lower()
    if payload.status is not None and current_status != previous_status:
        _record_admin_audit_event(
            request=request,
            action="feedback_status_changed",
            session=_admin_session,
            feedback_id=feedback_id,
            reason=current_status,
        )
    if payload.priority is not None and current_priority != previous_priority:
        _record_admin_audit_event(
            request=request,
            action="feedback_priority_changed",
            session=_admin_session,
            feedback_id=feedback_id,
            reason=current_priority,
        )
    if payload.admin_note:
        _record_admin_audit_event(
            request=request,
            action="feedback_note_added",
            session=_admin_session,
            feedback_id=feedback_id,
            operator_note=payload.admin_note,
        )
    return {
        "message": "Feedback updated.",
        "feedback": _admin_feedback(record),
    }


@app.post("/admin/feedback/{feedback_id}/status")
@api_limit("wallet_create")
async def admin_update_feedback_status(
    request: Request,
    feedback_id: str,
    payload: AdminFeedbackStatusRequest,
    _admin_session=Depends(_require_admin_session),
):
    blockchain.refresh_access_control_state_from_storage()
    record = blockchain.get_feedback(feedback_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Feedback not found: {feedback_id}")
    previous_status = str(record.get("status") or "").strip().lower()
    try:
        record = blockchain.update_feedback(
            feedback_id,
            status=payload.status,
            reviewed_by=payload.reviewed_by,
        )
        blockchain.save_blockchain()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    current_status = str(record.get("status") or "").strip().lower()
    if current_status != previous_status:
        _record_admin_audit_event(
            request=request,
            action="feedback_status_changed",
            session=_admin_session,
            feedback_id=feedback_id,
            reason=current_status,
        )
    return {
        "message": "Feedback status updated.",
        "feedback": _admin_feedback(record),
    }


@app.post("/admin/feedback/{feedback_id}/note")
@api_limit("wallet_create")
async def admin_add_feedback_note(
    request: Request,
    feedback_id: str,
    payload: AdminFeedbackNoteRequest,
    _admin_session=Depends(_require_admin_session),
):
    blockchain.refresh_access_control_state_from_storage()
    record = blockchain.get_feedback(feedback_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Feedback not found: {feedback_id}")
    try:
        note = blockchain.add_feedback_admin_note(
            feedback_id,
            note=payload.note,
            created_by=payload.created_by,
        )
        blockchain.save_blockchain()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_admin_audit_event(
        request=request,
        action="feedback_note_added",
        session=_admin_session,
        feedback_id=feedback_id,
        operator_note=note.get("note"),
    )
    return {
        "message": "Feedback note added.",
        "feedback": _admin_feedback(record),
        "note": note,
    }


@app.get("/admin/ops/status")
@api_limit("public_read")
async def admin_ops_status(
    request: Request,
    _admin_session=Depends(_require_admin_session),
):
    payload = _admin_ops_status_payload()
    _record_admin_audit_event(
        request=request,
        action="admin_ops_viewed",
        session=_admin_session,
    )
    return payload


@app.get("/admin/audit-log")
@api_limit("public_read")
async def admin_audit_log(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    action: str | None = Query(default=None),
    since: str | None = Query(default=None),
    before: str | None = Query(default=None),
    _admin_session=Depends(_require_admin_session),
):
    return {
        "audit_log": [
            _admin_audit_entry(entry)
            for entry in blockchain.list_audit_log_entries(
                limit=limit,
                action=action,
                since=since,
                before=before,
            )
        ],
    }


async def _admin_update_access_account_status(
    *,
    request: Request,
    access_account_id: str,
    status: str,
    action_name: str,
    session=None,
):
    blockchain.refresh_access_control_state_from_storage()
    try:
        access_account = blockchain.update_access_account_status(
            access_account_id,
            status,
            updated_by="admin",
        )
        blockchain.save_blockchain()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_admin_audit_event(
        request=request,
        action=action_name,
        session=session,
        access_account_id=access_account_id,
    )
    return {
        "message": f"Access account {status}.",
        "access_account": _admin_access_account(access_account),
    }


@app.post("/admin/access/accounts/{access_account_id}/suspend")
@api_limit("wallet_create")
async def admin_suspend_access_account(
    request: Request,
    access_account_id: str,
    _admin_session=Depends(_require_admin_session),
):
    return await _admin_update_access_account_status(
        request=request,
        access_account_id=access_account_id,
        status="suspended",
        action_name="access_account_suspended",
        session=_admin_session,
    )


@app.post("/admin/access/accounts/{access_account_id}/reactivate")
@api_limit("wallet_create")
async def admin_reactivate_access_account(
    request: Request,
    access_account_id: str,
    _admin_session=Depends(_require_admin_session),
):
    return await _admin_update_access_account_status(
        request=request,
        access_account_id=access_account_id,
        status="active",
        action_name="access_account_reactivated",
        session=_admin_session,
    )


@app.post("/admin/access/accounts/{access_account_id}/revoke")
@api_limit("wallet_create")
async def admin_revoke_access_account(
    request: Request,
    access_account_id: str,
    _admin_session=Depends(_require_admin_session),
):
    return await _admin_update_access_account_status(
        request=request,
        access_account_id=access_account_id,
        status="revoked",
        action_name="access_account_revoked",
        session=_admin_session,
    )


@app.post("/admin/access/wallet-bindings/{wallet_address}/revoke")
@api_limit("wallet_create")
async def admin_revoke_wallet_binding(
    request: Request,
    wallet_address: str,
    _admin_session=Depends(_require_admin_session),
):
    blockchain.refresh_access_control_state_from_storage()
    try:
        binding = blockchain.revoke_wallet_binding(
            wallet_address,
            revoked_by="admin",
        )
        blockchain.save_blockchain()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_admin_audit_event(
        request=request,
        action="wallet_binding_revoked",
        session=_admin_session,
        wallet_address=wallet_address,
        access_account_id=binding.get("access_account_id"),
    )
    return {
        "message": "Wallet binding revoked.",
        "wallet_binding": _admin_wallet_binding(binding),
    }


@app.post("/auth/wallet/challenge")
@api_limit("wallet_create")
async def create_wallet_challenge(request: Request, payload: WalletChallengeRequest):
    if not is_valid_ethereum_address(payload.wallet_address):
        raise HTTPException(status_code=400, detail="Invalid wallet address. Expected an Ethereum-style 0x address.")
    try:
        challenge = wallet_auth_manager.issue_challenge(payload.wallet_address)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return challenge


@app.post("/auth/wallet/verify")
@api_limit("wallet_create")
async def verify_wallet_challenge(request: Request, payload: WalletVerifyRequest):
    if not is_valid_ethereum_address(payload.wallet_address):
        raise HTTPException(status_code=400, detail="Invalid wallet address. Expected an Ethereum-style 0x address.")
    normalized = normalize_wallet_address(payload.wallet_address)
    if normalized is None:
        raise HTTPException(status_code=400, detail="Invalid wallet address. Expected an Ethereum-style 0x address.")

    try:
        verification = wallet_auth_manager.verify_signature(
            payload.wallet_address,
            payload.message,
            payload.signature,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 400
        if "expired" in detail.lower() or "already been used" in detail.lower():
            status_code = 401
        raise HTTPException(status_code=status_code, detail=detail) from exc

    return verification


@app.post("/auth/wallet/submission-challenge")
@api_limit("submission_create")
async def create_wallet_submission_challenge(
    request: Request,
    payload: WalletSubmissionChallengeRequest,
    wallet_address: str = Depends(_verified_wallet_dependency),
):
    normalized_wallet = normalize_wallet_address(payload.wallet_address)
    if normalized_wallet is None or normalized_wallet != wallet_address:
        raise HTTPException(status_code=403, detail="wallet_address must match the verified wallet session.")
    _enforce_submission_eligibility(wallet_address)

    content_object = _require_content_reference(payload.content_hash, payload.content_id)
    safe_caption = validate_caption(payload.caption)

    try:
        challenge = wallet_auth_manager.issue_submission_challenge(
            wallet_address=wallet_address,
            content_hash=content_object.content_hash,
            content_id=content_object.content_id,
            caption=safe_caption,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return challenge


@app.post("/auth/wallet/vote-challenge")
@api_limit("submission_create")
async def create_wallet_vote_challenge(
    request: Request,
    payload: WalletVoteChallengeRequest,
    wallet_address: str = Depends(_verified_wallet_dependency),
):
    normalized_wallet = normalize_wallet_address(payload.wallet_address)
    if normalized_wallet is None or normalized_wallet != wallet_address:
        raise HTTPException(status_code=403, detail="wallet_address must match the verified wallet session.")
    _enforce_access_for_feature(wallet_address, feature="votes")

    submission = blockchain.get_submission(payload.submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail=f"Submission not found: {payload.submission_id}")
    if blockchain.is_submission_voting_locked(submission):
        raise HTTPException(status_code=400, detail="Finalized or certified submissions cannot receive votes.")
    if wallet_address == submission.submitter:
        raise HTTPException(status_code=400, detail="Submission creator cannot vote on their own submission.")
    if blockchain.storage.get_vote(payload.submission_id, wallet_address, blockchain.votes):
        raise HTTPException(status_code=400, detail="Wallet has already voted on this submission.")
    _enforce_review_policy(wallet_address, scope="voting")

    try:
        challenge = wallet_auth_manager.issue_vote_challenge(
            wallet_address=wallet_address,
            submission_id=payload.submission_id,
            content_hash=submission.content_hash or "",
            vote_type=payload.vote,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return challenge


@app.get("/review/policy")
@api_limit("public_read")
async def get_review_policy(
    request: Request,
    wallet_address: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
):
    config = _current_review_policy_config()
    normalized_wallet = None

    if authorization:
        try:
            verified_wallet = resolve_verified_wallet_from_authorization(
                authorization,
                manager=wallet_auth_manager,
            )
        except HTTPException as exc:
            raise HTTPException(status_code=401, detail=exc.detail) from exc
        normalized_wallet = verified_wallet
        if wallet_address:
            requested_wallet = _normalize_native_account_address(wallet_address)
            if requested_wallet != verified_wallet:
                raise HTTPException(
                    status_code=403,
                    detail="wallet_address must match the verified wallet session.",
                )
    elif wallet_address:
        normalized_wallet = _normalize_native_account_address(wallet_address)

    eligibility = None
    if normalized_wallet:
        _, eligibility = _review_eligibility_for_wallet(normalized_wallet)
    return build_public_policy_summary(
        config,
        wallet_address=normalized_wallet,
        eligibility=eligibility,
    )


@app.post("/auth/wallet/transfer-challenge")
@api_limit("wallet_create")
async def create_wallet_transfer_challenge(
    request: Request,
    payload: WalletTransferChallengeRequest,
    wallet_address: str = Depends(_verified_wallet_dependency),
):
    normalized_from = normalize_wallet_address(payload.from_address)
    if normalized_from is None or normalized_from != wallet_address:
        raise HTTPException(status_code=403, detail="from_address must match the verified wallet session.")
    _enforce_access_for_feature(wallet_address, feature="transfers")

    try:
        expected_nonce = blockchain.get_next_nonce(wallet_address)
        if payload.nonce is not None and int(payload.nonce) != expected_nonce:
            raise HTTPException(
                status_code=400,
                detail=f"nonce must match the expected next nonce {expected_nonce}.",
            )
        challenge = wallet_auth_manager.issue_transfer_challenge(
            from_address=wallet_address,
            to_address=payload.to_address,
            amount=payload.amount,
            fee=payload.fee,
            memo=payload.memo,
            nonce=str(expected_nonce),
        )
        balance_snapshot = blockchain.get_native_balance_snapshot(wallet_address)
        estimated_total = parse_native_zoid_amount(payload.amount, allow_zero=False)
        would_be_sufficient = Decimal(estimated_total) <= Decimal(balance_snapshot["available_balance"])
        challenge["available_balance"] = balance_snapshot["available_balance"]
        challenge["estimated_total"] = estimated_total
        challenge["would_be_sufficient_at_challenge_time"] = would_be_sufficient
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return challenge


@app.get("/auth/wallet/session")
@api_limit("public_read")
async def get_wallet_session(
    request: Request,
    authorization: str | None = Header(default=None),
    wallet_address: str = Depends(_verified_wallet_dependency),
):
    token = (authorization or "")[len("Bearer "):].strip() if authorization else ""
    try:
        return wallet_auth_manager.session_payload(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.post("/auth/wallet/logout")
@api_limit("public_read")
async def logout_wallet_session(request: Request, authorization: str | None = Header(default=None)):
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer "):].strip()
    revoked = wallet_auth_manager.revoke_session(token)
    return {
        "logged_out": True,
        "revoked": revoked,
        "message": "Wallet session cleared.",
    }


@app.post("/transfers/submit")
@api_limit("wallet_create")
async def submit_transfer_intent(
    request: Request,
    payload: WalletTransferSubmitRequest,
    wallet_address: str = Depends(_verified_wallet_dependency),
):
    normalized_from = normalize_wallet_address(payload.from_address)
    if normalized_from is None or normalized_from != wallet_address:
        raise HTTPException(status_code=403, detail="from_address must match the verified wallet session.")
    _enforce_access_for_feature(wallet_address, feature="transfers")

    starting_balance = blockchain.get_native_balance_snapshot(wallet_address)["native_balance"]
    try:
        transaction_preview = _build_submitted_native_transaction_preview(payload)
        existing_transaction = blockchain.get_native_transaction(transaction_preview.tx_id)
        if existing_transaction:
            existing_transfer_intent = blockchain.get_transfer_intent_by_tx_id(existing_transaction["tx_id"])
            if existing_transfer_intent is None:
                raise HTTPException(status_code=409, detail="Transaction already exists but local transfer record is missing.")
            body = _serialize_transfer_intent(existing_transfer_intent)
            body["duplicate"] = True
            body["message"] = "Transaction already recorded."
            return body

        verification = wallet_auth_manager.verify_transfer_signature(
            wallet_address=wallet_address,
            from_address=payload.from_address,
            to_address=payload.to_address,
            amount=payload.amount,
            fee=payload.fee,
            memo=payload.memo,
            message=payload.message,
            signature=payload.signature,
        )
        if str(verification["fee"]) != "0":
            raise ValueError("Nonzero fees are not enabled yet.")
        blockchain.validate_transaction_balance_sufficiency(transaction_preview.to_dict())
        transfer_intent = blockchain.create_signed_transfer_intent(
            from_address=str(verification["from_address"]),
            to_address=str(verification["to_address"]),
            amount=str(verification["amount"]),
            fee=str(verification["fee"]),
            memo=str(verification["memo"] or ""),
            network=NETWORK_NAME,
            transaction_version=verification.get("transaction_version"),
            protocol_version=verification.get("protocol_version"),
            network_id=verification.get("network_id"),
            signature_scheme=str(verification["signature_scheme"]),
            signature=str(verification["transfer_signature"]),
            signed_message_hash=str(verification["signed_message_hash"]),
            signed_message=str(verification["transfer_message"]),
            transfer_nonce=str(verification["nonce"]),
            transaction_timestamp=str(verification["timestamp"]),
            signed_at=str(verification["signed_at"]),
            status="signed_pending",
        )
        blockchain.save_blockchain()
    except ValueError as exc:
        detail = str(exc)
        status_code = 400
        if "expired" in detail.lower() or "already been used" in detail.lower():
            status_code = 401
        raise HTTPException(status_code=status_code, detail=detail) from exc

    ending_balance = blockchain.get_native_balance_snapshot(wallet_address)["native_balance"]
    if ending_balance != starting_balance:
        raise HTTPException(status_code=500, detail="Transfer intent submission must not mutate balances.")

    body = _serialize_transfer_intent(transfer_intent)
    if transfer_intent.get("duplicate"):
        body["duplicate"] = True
        body["message"] = "Transaction already recorded."
        return body
    if payload.admit_to_mempool:
        try:
            admission = blockchain.admit_transaction_to_mempool(transfer_intent["tx_id"])
            blockchain.save_blockchain()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        admitted_transfer = blockchain.get_transfer_intent_by_tx_id(transfer_intent["tx_id"]) or transfer_intent
        body = _serialize_transfer_intent(admitted_transfer)
        body["admitted"] = True
        body["admitted_at"] = admission.get("admitted_at")
        body["message"] = admission["message"]
        return body
    body["message"] = "Signed native ZOID transaction recorded. It is not settled until included in a meme-mined block."
    return body


@app.post("/peers/register")
@api_limit("peer_receive")
async def register_peer(request: Request, registration: PeerRegistration, _: None = Depends(require_peer_secret)):
    if registration.network_name.strip() != NETWORK_NAME:
        raise HTTPException(status_code=400, detail="Peer belongs to a different network.")

    try:
        authenticated_peer = _require_protocol_v1_peer_claims_match_auth(
            request,
            claimed_node_id=registration.node_id,
            claimed_network_name=registration.network_name,
        )
        claimed_node_id = (
            authenticated_peer.sender_node_id
            if authenticated_peer is not None
            else registration.node_id
        )
        peer_url = normalize_peer_url(str(registration.url))
        public_node_url = normalize_peer_url(PUBLIC_NODE_URL)
        if claimed_node_id.strip() == NODE_ID or peer_url == public_node_url:
            raise HTTPException(status_code=400, detail="Cannot register this node as a peer.")

        peer = peer_store.register_peer(
            node_id=claimed_node_id,
            url=peer_url,
            network_name=registration.network_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"message": "Peer registered successfully.", "peer": peer}


@app.get("/peers")
@api_limit("public_read")
async def get_peers(request: Request):
    return {"peers": peer_store.list_peers()}


@app.post("/peers/transactions/receive")
@api_limit("peer_receive")
async def receive_transaction_from_peer(
    request: Request,
    receive_request: PeerTransactionReceive,
    _: None = Depends(require_peer_secret),
):
    try:
        authenticated_peer = _require_protocol_v1_peer_claims_match_auth(
            request,
            claimed_node_id=receive_request.origin_node_id,
            claimed_network_name=receive_request.network_name,
        )
        return receive_peer_transaction(
            blockchain=blockchain,
            peer_store=peer_store,
            origin_node_id=(
                authenticated_peer.sender_node_id
                if authenticated_peer is not None
                else receive_request.origin_node_id
            ),
            network_name=receive_request.network_name,
            transaction_payload=receive_request.transaction,
            local_network_name=NETWORK_NAME,
        )
    except UnauthorizedPeerError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except WrongNetworkError as exc:
        return _peer_transaction_error_response(
            400,
            tx_id=(receive_request.transaction or {}).get("tx_id"),
            reason="wrong_network",
            message=str(exc),
        )
    except ConflictingTransactionError as exc:
        return _peer_transaction_error_response(
            409,
            tx_id=(receive_request.transaction or {}).get("tx_id"),
            reason="conflicting_nonce",
            message=str(exc),
        )
    except MalformedTransactionError as exc:
        message = str(exc)
        reason = "validation_failed"
        lowered = message.lower()
        if "tx_id does not match" in lowered:
            reason = "invalid_tx_id"
        elif "mempool admission" in lowered and ("transaction version is required" in lowered or "transaction_version" in lowered):
            reason = "unsupported_transaction_version"
        elif "signature" in lowered:
            reason = "invalid_signature"
        elif "insufficient available balance" in lowered:
            reason = "insufficient_available_balance"
        elif "nonzero fees are not enabled yet" in lowered:
            reason = "invalid_fee_policy"
        elif "nonce" in lowered:
            reason = "invalid_nonce"
        return _peer_transaction_error_response(
            400,
            tx_id=(receive_request.transaction or {}).get("tx_id"),
            reason=reason,
            message=message,
        )


@app.get("/peers/transactions/{tx_id}")
@api_limit("peer_receive")
async def get_peer_transaction(
    request: Request,
    tx_id: str,
    _: None = Depends(require_peer_secret),
):
    _require_protocol_v1_active_peer(request)
    transaction = blockchain.get_native_transaction(tx_id)
    if not transaction:
        raise HTTPException(status_code=404, detail=f"Transaction not found: {tx_id}")
    return {
        "transaction": transaction,
        "network_name": NETWORK_NAME,
    }


@app.get("/peers/mempool/summary")
@api_limit("peer_receive")
async def get_peer_mempool_summary(
    request: Request,
    _: None = Depends(require_peer_secret),
):
    _require_protocol_v1_active_peer(request)
    transactions = blockchain.list_mempool_transactions()
    return {
        "tx_ids": [transaction.get("tx_id") for transaction in transactions if transaction.get("tx_id")],
        "count": len(transactions),
        "network_name": NETWORK_NAME,
    }


@app.post("/peers/submissions/receive")
@api_limit("peer_receive")
async def receive_submission_from_peer(request: Request, receive_request: PeerSubmissionReceive, _: None = Depends(require_peer_secret)):
    try:
        authenticated_peer = _require_protocol_v1_peer_claims_match_auth(
            request,
            claimed_node_id=receive_request.origin_node_id,
            claimed_network_name=receive_request.network_name,
        )
        origin_node_id = (
            authenticated_peer.sender_node_id
            if authenticated_peer is not None
            else receive_request.origin_node_id
        )
        if not peer_store.get_active_peer(origin_node_id):
            _validate_unregistered_peer_submission_shape(receive_request)
        return receive_peer_submission(
            blockchain=blockchain,
            peer_store=peer_store,
            origin_node_id=origin_node_id,
            network_name=receive_request.network_name,
            submission_payload=receive_request.submission.model_dump(),
            local_network_name=NETWORK_NAME,
        )
    except UnauthorizedPeerError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except WrongNetworkError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except MalformedSubmissionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DuplicateSubmissionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/peers/votes/receive")
@api_limit("peer_receive")
async def receive_vote_from_peer(request: Request, receive_request: PeerVoteReceive, _: None = Depends(require_peer_secret)):
    try:
        authenticated_peer = _require_protocol_v1_peer_claims_match_auth(
            request,
            claimed_node_id=receive_request.origin_node_id,
            claimed_network_name=receive_request.network_name,
        )
        origin_node_id = (
            authenticated_peer.sender_node_id
            if authenticated_peer is not None
            else receive_request.origin_node_id
        )
        if not peer_store.get_active_peer(origin_node_id):
            _validate_unregistered_peer_vote_shape(receive_request)
        return receive_peer_vote(
            blockchain=blockchain,
            peer_store=peer_store,
            origin_node_id=origin_node_id,
            network_name=receive_request.network_name,
            vote_payload={
                "vote_version": receive_request.vote_version,
                "protocol_version": receive_request.protocol_version,
                "network_id": receive_request.network_id,
                "submission_id": receive_request.submission_id,
                "voter": receive_request.voter,
                "vote_type": receive_request.vote_type,
                "vote_value": receive_request.vote_value,
                "content_hash": receive_request.content_hash,
                "voter_wallet_address": receive_request.voter_wallet_address,
                "signature_scheme": receive_request.signature_scheme,
                "vote_signature": receive_request.vote_signature,
                "vote_message": receive_request.vote_message,
                "signed_message_hash": receive_request.signed_message_hash,
                "vote_nonce": receive_request.vote_nonce,
                "vote_issued_at": receive_request.vote_issued_at,
                "vote_expires_at": receive_request.vote_expires_at,
                "signed_at": receive_request.signed_at,
                "identity_source": receive_request.identity_source,
                "created_at": receive_request.created_at,
                "vote_timestamp": receive_request.vote_timestamp,
            },
            local_network_name=NETWORK_NAME,
        )
    except UnauthorizedPeerError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except WrongNetworkError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except MalformedVoteError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except UnknownSubmissionError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictingVoteError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/peers/certificates/receive")
@api_limit("peer_receive")
async def receive_certificate_from_peer(request: Request, receive_request: PeerCertificateReceive, _: None = Depends(require_peer_secret)):
    try:
        if receive_request.certificate is None:
            raise HTTPException(status_code=400, detail="Certificate payload is required.")
        authenticated_peer = _require_protocol_v1_peer_claims_match_auth(
            request,
            claimed_node_id=receive_request.origin_node_id,
            claimed_network_name=receive_request.network_name,
        )
        origin_node_id = (
            authenticated_peer.sender_node_id
            if authenticated_peer is not None
            else receive_request.origin_node_id
        )
        if not peer_store.get_active_peer(origin_node_id):
            _validate_unregistered_peer_certificate_shape(receive_request)
        return receive_peer_certificate(
            blockchain=blockchain,
            peer_store=peer_store,
            origin_node_id=origin_node_id,
            network_name=receive_request.network_name,
            certificate_payload=receive_request.certificate.model_dump(),
            local_network_name=NETWORK_NAME,
        )
    except UnauthorizedPeerError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except WrongNetworkError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except MalformedCertificateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ConflictingCertificateError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/peers/blocks/receive")
@api_limit("peer_receive")
async def receive_block_from_peer(request: Request, receive_request: PeerBlockReceive, _: None = Depends(require_peer_secret)):
    try:
        raw_payload = await request.json()
        if receive_request.block is None:
            raise HTTPException(status_code=400, detail="Block payload is required.")
        authenticated_peer = _require_protocol_v1_peer_claims_match_auth(
            request,
            claimed_node_id=receive_request.origin_node_id,
            claimed_network_name=receive_request.network_name,
        )
        origin_node_id = (
            authenticated_peer.sender_node_id
            if authenticated_peer is not None
            else receive_request.origin_node_id
        )
        if not peer_store.get_active_peer(origin_node_id):
            _validate_unregistered_peer_block_shape(receive_request)
        return receive_peer_block(
            blockchain=blockchain,
            peer_store=peer_store,
            origin_node_id=origin_node_id,
            network_name=receive_request.network_name,
            block_payload=(
                raw_payload.get("block")
                if isinstance(raw_payload, dict) and isinstance(raw_payload.get("block"), dict)
                else receive_request.block.model_dump(exclude_none=True)
            ),
            related_submission_id=receive_request.related_submission_id,
            local_network_name=NETWORK_NAME,
            certificate_payload=(
                raw_payload.get("certificate")
                if receive_request.certificate
                and isinstance(raw_payload, dict)
                and isinstance(raw_payload.get("certificate"), dict)
                else (
                    receive_request.certificate.model_dump(exclude_none=True)
                    if receive_request.certificate
                    else None
                )
            ),
        )
    except UnauthorizedPeerError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except WrongNetworkError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except MalformedCertificateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ConflictingCertificateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except MalformedBlockError as e:
        raise HTTPException(
            status_code=400,
            detail=e.to_detail() if hasattr(e, "to_detail") else str(e),
        )
    except DuplicateBlockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ChainExtensionError as e:
        raise HTTPException(status_code=409, detail=str(e))

@app.get("/chain")
@api_limit("public_read")
async def get_chain(request: Request):
    """Retrieve the blockchain."""
    return {"chain": [_serialize_block(block) for block in blockchain.chain]}


@app.get("/chain/summary")
@api_limit("public_read")
async def chain_summary(request: Request):
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


@app.get("/peers/chain/summary")
@api_limit("peer_receive")
async def peer_chain_summary(
    request: Request,
    _: None = Depends(require_peer_secret),
):
    _require_protocol_v1_active_peer(request)
    return await chain_summary(request)


@app.get("/chain/blocks")
@api_limit("public_read")
async def chain_blocks(request: Request, from_height: int = 0, include_media_bytes: bool = False):
    if from_height < 0:
        raise HTTPException(status_code=400, detail="from_height must be non-negative.")

    blocks = [
        block
        for block in blockchain.chain
        if block.index >= from_height
    ]
    certificate_ids = {
        block.certificate_id
        for block in blocks
        if block.certificate_id
    }
    return {
        "blocks": [
            _serialize_block(block, include_media_bytes=include_media_bytes)
            for block in blocks
        ],
        "certificates": [
            _serialize_certificate(certificate)
            for certificate in blockchain.originality_certificates
            if certificate.certificate_id in certificate_ids
        ],
    }


@app.get("/peers/chain/blocks")
@api_limit("peer_receive")
async def peer_chain_blocks(
    request: Request,
    from_height: int = 0,
    include_media_bytes: bool = False,
    _: None = Depends(require_peer_secret),
):
    _require_protocol_v1_active_peer(request)
    if from_height < 0:
        raise HTTPException(status_code=400, detail="from_height must be non-negative.")

    blocks = [
        block
        for block in blockchain.chain
        if block.index >= from_height
    ]
    certificate_ids = {
        block.certificate_id
        for block in blocks
        if block.certificate_id
    }
    return {
        "blocks": [
            block.to_dict(include_media_bytes=include_media_bytes)
            for block in blocks
        ],
        "certificates": [
            certificate.to_dict()
            for certificate in blockchain.originality_certificates
            if certificate.certificate_id in certificate_ids
        ],
    }


@app.post("/chain/sync")
@api_limit("chain_sync")
async def sync_chain(request: Request):
    return sync_chain_from_peers(
        blockchain=blockchain,
        peer_store=peer_store,
        network_name=NETWORK_NAME,
        origin_node_id=NODE_ID,
    )


@app.get("/blocks/{block_hash}/media")
@api_limit("public_read")
async def download_block_media(request: Request, block_hash: str):
    if not is_valid_block_hash(block_hash):
        raise HTTPException(status_code=422, detail="block_hash must be a 64-character lowercase hexadecimal string.")

    block = blockchain.get_block_by_hash(block_hash)
    if block is None:
        raise HTTPException(status_code=404, detail=f"Block not found: {block_hash}")

    try:
        media_bytes = blockchain.recover_block_media_bytes(block)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=f"Block does not contain recoverable media bytes: {block_hash}") from exc

    media_hash = str(getattr(block, "media_hash", "") or "").strip().lower()
    actual_media_hash = hashlib.sha256(media_bytes).hexdigest()
    if media_hash and media_hash != actual_media_hash:
        raise HTTPException(status_code=409, detail="Block media bytes failed integrity verification.")

    mime_type = str(getattr(block, "mime_type", "") or "").strip().lower() or "application/octet-stream"
    if mime_type == TEXT_MIME_TYPE:
        try:
            return PlainTextResponse(content=media_bytes.decode("utf-8"), media_type=TEXT_MIME_TYPE)
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=409, detail="Block text media could not be decoded safely.") from exc

    return Response(content=media_bytes, media_type=mime_type)


@app.post("/blocks/{block_hash}/broadcast")
@api_limit("mint")
async def broadcast_block(request: Request, block_hash: str):
    block = blockchain.get_block_by_hash(block_hash)
    if not block:
        raise HTTPException(status_code=404, detail=f"Block not found: {block_hash}")

    broadcast_result = broadcast_block_to_peers(
        block=block,
        peer_store=peer_store,
        origin_node_id=NODE_ID,
        network_name=NETWORK_NAME,
        certificate=(
            blockchain.get_originality_certificate(block.certificate_id)
            if block.certificate_id
            else None
        ),
    )
    return {
        "message": "Block broadcast attempted.",
        "block": _serialize_block(block),
        "broadcast": broadcast_result,
    }

@app.post("/add_transaction")
@api_limit("transaction_create")
async def add_transaction(
    request: Request,
    sender: Annotated[str, Query(..., min_length=66, max_length=66, pattern=PUBLIC_KEY_PATTERN)],
    recipient: Annotated[str, Query(..., min_length=66, max_length=66, pattern=PUBLIC_KEY_PATTERN)],
    amount: Annotated[float, Query(gt=0)],
    private_key: Annotated[str, Query(..., min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")],
):
    """Add a transaction to the blockchain using wallet validation (no API key)."""

    # Debug: Print all registered wallets
    print(f"Debug: Wallets in blockchain: {list(blockchain.wallets.keys())}")

    # Validate sender's public key
    print(f"Debug: Sender key provided: {sender}")
    if sender not in blockchain.wallets:
        print(f"Debug: Sender key {sender} not found in wallets.")
        raise HTTPException(status_code=400, detail="Invalid sender public key.")

    # Validate recipient's public key
    print(f"Debug: Recipient key provided: {recipient}")
    if recipient not in blockchain.wallets:
        print(f"Debug: Recipient key {recipient} not found in wallets.")
        raise HTTPException(status_code=400, detail="Invalid recipient public key.")

    # Validate sender's private key matches their public key
    sender_wallet = blockchain.get_wallet(sender)
    if not sender_wallet:
        raise HTTPException(status_code=400, detail="Sender wallet not found.")

    if not sender_wallet.validate_private_key(private_key, sender):
        raise HTTPException(status_code=400, detail="Invalid private key for sender's wallet.")

    # Validate amount
    if not is_valid_amount(amount):
        raise HTTPException(status_code=400, detail="Invalid amount. Must be greater than 0.")

    # Create and sign the transaction
    transaction = Transaction(sender, recipient, amount)
    try:
        transaction.sign_transaction(private_key)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Transaction signing failed: {e}")

    # Add the transaction to the blockchain
    blockchain.add_transaction(transaction)

    return {"message": "Transaction added successfully."}

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

@app.get("/get_wallets")
@api_limit("public_read")
async def get_wallets(request: Request):
    """
    Retrieve development-only server wallets using public-safe fields only.
    """
    try:
        return {
            "message": "Development-only server wallets retrieved successfully.",
            "warning": "Development-only server wallets are local test tools and are not the native ZoidbergChain account registry for MetaMask users.",
            "wallets": [
                _wallet_public_response(key, wallet)
                for key, wallet in blockchain.wallets.items()
            ],
        }
    except Exception:
        logger.exception("Failed to retrieve development wallet summaries")
        return _safe_server_error()


@app.get("/dev/wallets")
@api_limit("dev_endpoint")
async def get_dev_wallets(request: Request):
    _require_dev_private_key_export()
    return {
        "warning": DEV_ENDPOINT_WARNING,
        "message": "Development-only server wallets with private-key export.",
        "wallets": [
            {
                **_wallet_public_response(key, wallet),
                "private_key": wallet.private_key,
            }
            for key, wallet in blockchain.wallets.items()
        ],
    }

@app.get("/transaction_pool")
@api_limit("public_read")
async def transaction_pool(request: Request):
    """Retrieve the current transaction pool."""
    return {"pending_transactions": blockchain.get_transaction_pool()}

@app.post("/content/upload")
@api_limit("submission_create")
async def upload_content(
    request: Request,
    file: UploadFile,
    submitted_by: Annotated[str, Form(..., min_length=1, max_length=128)],
    caption: Annotated[str | None, Form(max_length=MAX_CAPTION_LENGTH)] = None,
    content_type_hint: Annotated[str | None, Form(max_length=32)] = None,
):
    submitted_by = _normalize_supported_user_identity(submitted_by, field_name="submitted_by")

    file_bytes = await file.read()
    try:
        validate_content_size(len(file_bytes))
        safe_caption = validate_caption(caption)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    declared_mime_type = (file.content_type or "").strip().lower() or None
    if declared_mime_type == "application/octet-stream":
        declared_mime_type = None
    if declared_mime_type is not None and declared_mime_type not in SUPPORTED_CONTENT_MIME_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported mime_type for uploaded content.")

    try:
        safe_original_filename = sanitize_original_filename(file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        content_object = blockchain.upload_binary_content(
            file_bytes=file_bytes,
            submitted_by=submitted_by,
            mime_type=declared_mime_type,
            original_filename=safe_original_filename,
            caption=safe_caption,
            content_type_hint=content_type_hint,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    blockchain.save_blockchain()
    return _public_content_upload_response(content_object)


@app.post("/content/text")
@api_limit("submission_create")
async def upload_text_content(request: Request, payload: TextContentUpload):
    submitted_by = _normalize_supported_user_identity(payload.submitted_by, field_name="submitted_by")

    try:
        content_object = blockchain.upload_text_content(
            text_content=validate_text_content(payload.text_content),
            submitted_by=submitted_by,
            caption=validate_caption(payload.caption),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    blockchain.save_blockchain()
    return _public_content_upload_response(content_object)


@app.get("/content/{content_hash}/metadata")
@api_limit("public_read")
async def get_content_metadata(request: Request, content_hash: str):
    content_object = _require_content_object(content_hash)
    return {"content": _safe_content_metadata(content_object)}


@app.get("/peers/content/{content_hash}/metadata")
@api_limit("peer_receive")
async def get_peer_content_metadata(
    request: Request,
    content_hash: str,
    _: None = Depends(require_peer_secret),
):
    _require_protocol_v1_active_peer(request)
    content_object = _require_content_object(content_hash)
    return {"content": _peer_safe_content_metadata(content_object)}


@app.get("/content/{content_hash}")
@api_limit("public_read")
async def download_content(request: Request, content_hash: str):
    content_object = _require_content_object(content_hash)
    verification = verify_content_object_payload(content_object, data_dir=blockchain.storage.data_dir)
    if verification["error"] == "missing_file":
        raise HTTPException(status_code=404, detail=f"Content file not found for hash: {content_hash}")
    if not verification["verified"]:
        raise HTTPException(status_code=409, detail="Content file failed integrity verification.")
    content_object.hash_scheme = verification["hash_scheme"]
    content_object.verified_at = verification["verified_at"]
    content_object.verification_error = None
    content_object.storage_status = "verified"
    if verification["file_size_bytes"] is not None:
        content_object.file_size_bytes = verification["file_size_bytes"]

    if content_object.mime_type == TEXT_MIME_TYPE and content_object.text_content:
        return PlainTextResponse(content=content_object.text_content, media_type=TEXT_MIME_TYPE)

    file_path = resolve_local_path(content_object.local_path, data_dir=blockchain.storage.data_dir)
    if not file_path or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail=f"Content file not found for hash: {content_hash}")

    if content_object.mime_type == TEXT_MIME_TYPE:
        try:
            text_body = load_content_bytes(
                content_object.content_hash,
                content_object.mime_type,
                data_dir=blockchain.storage.data_dir,
            ).decode("utf-8")
        except (FileNotFoundError, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=409, detail="Stored text content could not be decoded safely.") from exc
        return PlainTextResponse(content=text_body, media_type=TEXT_MIME_TYPE)

    return FileResponse(
        path=file_path,
        media_type=content_object.mime_type,
        filename=content_object.file_name or os.path.basename(file_path),
    )


@app.get("/peers/content/{content_hash}")
@api_limit("peer_receive")
async def download_peer_content(
    request: Request,
    content_hash: str,
    _: None = Depends(require_peer_secret),
):
    _require_protocol_v1_active_peer(request)
    content_object = _require_content_object(content_hash)
    verification = verify_content_object_payload(content_object, data_dir=blockchain.storage.data_dir)
    if verification["error"] == "missing_file":
        raise HTTPException(status_code=404, detail=f"Content file not found for hash: {content_hash}")
    if not verification["verified"]:
        raise HTTPException(status_code=409, detail="Content file failed integrity verification.")
    content_object.hash_scheme = verification["hash_scheme"]
    content_object.verified_at = verification["verified_at"]
    content_object.verification_error = None
    content_object.storage_status = "verified"
    if verification["file_size_bytes"] is not None:
        content_object.file_size_bytes = verification["file_size_bytes"]

    if content_object.mime_type == TEXT_MIME_TYPE and content_object.text_content:
        return PlainTextResponse(content=content_object.text_content, media_type=TEXT_MIME_TYPE)

    file_path = resolve_local_path(content_object.local_path, data_dir=blockchain.storage.data_dir)
    if not file_path or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail=f"Content file not found for hash: {content_hash}")

    if content_object.mime_type == TEXT_MIME_TYPE:
        try:
            text_body = load_content_bytes(
                content_object.content_hash,
                content_object.mime_type,
                data_dir=blockchain.storage.data_dir,
            ).decode("utf-8")
        except (FileNotFoundError, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=409, detail="Stored text content could not be decoded safely.") from exc
        return PlainTextResponse(content=text_body, media_type=TEXT_MIME_TYPE)

    return FileResponse(
        path=file_path,
        media_type=content_object.mime_type,
        filename=content_object.file_name or os.path.basename(file_path),
    )


@app.post("/content/{content_hash}/sync")
@api_limit("dev_endpoint")
async def sync_content_from_peers_endpoint(request: Request, content_hash: str):
    require_development_mode(True, "Manual content sync")
    if not is_valid_content_hash(content_hash):
        raise HTTPException(status_code=422, detail="content_hash must be a 64-character lowercase hexadecimal string.")

    result = sync_missing_content(
        blockchain=blockchain,
        peer_store=peer_store,
        content_hash=content_hash,
        origin_node_id=NODE_ID,
        network_name=NETWORK_NAME,
    )
    content_object = blockchain.get_content_object_by_hash(content_hash)
    return {
        "result": result,
        "content": _safe_content_metadata(content_object) if content_object else None,
    }


@app.post("/submit_content")
@api_limit("submission_create")
async def submit_content(
    request: Request,
    authorization: str | None = Header(default=None),
    submitter: Annotated[str | None, Form(min_length=1, max_length=128)] = None,
    wallet_address: Annotated[str | None, Form(min_length=42, max_length=42, pattern=ETHEREUM_ADDRESS_PATTERN)] = None,
    message: Annotated[str | None, Form(min_length=1, max_length=4096)] = None,
    signature: Annotated[str | None, Form(min_length=1, max_length=4096)] = None,
    image: UploadFile | None = None,
    text_content: Annotated[str | None, Form(max_length=MAX_SUBMISSION_TEXT_LENGTH)] = None,
    content_hash: Annotated[str | None, Form(min_length=64, max_length=64, pattern=HEX_64_PATTERN)] = None,
    content_id: Annotated[str | None, Form(min_length=32, max_length=32, pattern=HEX_32_PATTERN)] = None,
):
    """Submit meme content for review without minting a blockchain block."""
    signed_submission_requested = any(
        value is not None and str(value).strip()
        for value in [authorization, wallet_address, message, signature, content_hash, content_id]
    ) and not (submitter and not authorization and not wallet_address and not message and not signature)

    if signed_submission_requested:
        try:
            verified_wallet = resolve_verified_wallet_from_authorization(
                authorization,
                manager=wallet_auth_manager,
            )
        except HTTPException as exc:
            raise HTTPException(status_code=401, detail=exc.detail) from exc

        if image is not None:
            raise HTTPException(
                status_code=400,
                detail="Direct file submission is no longer supported here. Upload content first, then create a signed submission.",
            )
        if not message:
            raise HTTPException(status_code=400, detail="signed submission message is required.")
        if not signature:
            raise HTTPException(status_code=400, detail="signature is required.")

        content_object = _require_content_reference(content_hash, content_id)
        normalized_wallet = normalize_wallet_address(wallet_address or verified_wallet)
        if normalized_wallet is None or normalized_wallet != verified_wallet:
            raise HTTPException(status_code=403, detail="wallet_address must match the verified wallet session.")
        _enforce_submission_eligibility(verified_wallet)

        try:
            verification = wallet_auth_manager.verify_submission_signature(
                wallet_address=verified_wallet,
                message=message,
                signature=signature,
                content_hash=content_object.content_hash,
                content_id=content_object.content_id,
            )
            submission = blockchain.submit_existing_content(
                content_hash=content_object.content_hash,
                content_id=content_object.content_id,
                submitter=verified_wallet,
                text_content=text_content or "",
            )
        except ValueError as exc:
            detail = str(exc)
            status_code = 400
            if "expired" in detail.lower() or "already been used" in detail.lower():
                status_code = 401
            raise HTTPException(status_code=status_code, detail=detail) from exc

        submission.creator_wallet_address = verified_wallet
        submission.signature_scheme = str(verification["signature_scheme"])
        submission.submission_signature = str(verification["submission_signature"])
        submission.submission_message = str(verification["submission_message"])
        submission.signed_message_hash = str(verification["signed_message_hash"])
        submission.submission_nonce = str(verification["nonce"])
        submission.signed_at = str(verification["signed_at"])
        submission.identity_source = str(verification["identity_source"])
    else:
        if not is_development():
            raise HTTPException(
                status_code=401,
                detail="MetaMask-signed submissions are required outside development mode.",
            )
        if not submitter:
            raise HTTPException(status_code=422, detail="submitter is required for the development-only submission path.")

        submitter = _normalize_supported_user_identity(submitter, field_name="submitter")

        if image is not None and (content_hash is not None or content_id is not None):
            raise HTTPException(status_code=400, detail="Provide either image upload or content linkage, not both.")

        if content_hash is not None or content_id is not None:
            try:
                submission = blockchain.submit_existing_content(
                    content_hash=content_hash,
                    content_id=content_id,
                    submitter=submitter,
                    text_content=text_content or "",
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        else:
            if image is None or not image.filename:
                raise HTTPException(status_code=400, detail="Invalid image format. Allowed formats: jpg, jpeg, png, webp")

            file_bytes = await image.read()
            try:
                validate_content_size(len(file_bytes))
                safe_original_filename, _detected_mime_type = _validate_uploaded_image_payload(image, file_bytes)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            os.makedirs(SUBMISSIONS_DIR, exist_ok=True)
            image_path = os.path.join(SUBMISSIONS_DIR, os.path.basename(safe_original_filename))
            with open(image_path, "wb") as buffer:
                buffer.write(file_bytes)

            try:
                if not os.path.isfile(image_path):
                    return JSONResponse(status_code=400, content={"error": "Failed to save the uploaded image."})

                if not text_content:
                    text_content = extract_text(image_path)
                if not text_content:
                    return JSONResponse(status_code=400, content={"error": "No text found in the image."})

                submission = blockchain.submit_content(
                    image_path=image_path,
                    text_content=text_content,
                    submitter=submitter,
                )
            finally:
                if os.path.isfile(image_path):
                    os.remove(image_path)

    blockchain.save_blockchain()
    broadcast_result = broadcast_submission_to_peers(
        submission=submission,
        peer_store=peer_store,
        origin_node_id=NODE_ID,
        network_name=NETWORK_NAME,
    )

    return {
        "message": "Content submitted successfully.",
        "submission": _serialize_submission(submission),
        "broadcast": broadcast_result,
    }


@app.get("/submissions")
@api_limit("public_read")
async def get_submissions(request: Request, status: SubmissionStatusValue | None = None):
    submissions = [_serialize_submission(submission) for submission in blockchain.submissions]
    if status:
        submissions = [
            submission
            for submission in submissions
            if submission.get("status") == status
        ]
    submissions.sort(key=lambda submission: submission.get("created_at", 0), reverse=True)
    return {"submissions": submissions}


@app.get("/submissions/{submission_id}")
@api_limit("public_read")
async def get_submission(request: Request, submission_id: str):
    submission = blockchain.get_submission(submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail=f"Submission not found: {submission_id}")
    return {"submission": _serialize_submission(submission)}


@app.get("/submissions/{submission_id}/certificate")
@api_limit("public_read")
async def get_submission_certificate(request: Request, submission_id: str):
    submission = blockchain.get_submission(submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail=f"Submission not found: {submission_id}")

    certificate = blockchain.get_originality_certificate_for_submission(submission_id)
    if not certificate:
        raise HTTPException(
            status_code=404,
            detail=f"Originality certificate not found for submission: {submission_id}",
        )
    return {"certificate": _serialize_certificate(certificate)}


@app.get("/submissions/{submission_id}/voter-rewards")
@api_limit("public_read")
async def get_submission_voter_rewards(request: Request, submission_id: str):
    try:
        return blockchain.get_submission_voter_reward_summary(submission_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/certificates/{certificate_id}")
@api_limit("public_read")
async def get_certificate(request: Request, certificate_id: str):
    certificate = blockchain.get_originality_certificate(certificate_id)
    if not certificate:
        raise HTTPException(
            status_code=404,
            detail=f"Originality certificate not found: {certificate_id}",
        )
    return {"certificate": _serialize_certificate(certificate)}


@app.post("/dev/submissions/{submission_id}/repair-certificate")
@api_limit("dev_endpoint")
async def repair_submission_certificate(request: Request, submission_id: str):
    require_development_mode(allow_dev_reset_endpoints(), "Development repair endpoints")

    submission = blockchain.get_submission(submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail=f"Submission not found: {submission_id}")

    existing_certificate = blockchain.get_originality_certificate_for_submission(submission_id)
    if existing_certificate:
        submission.certificate_id = existing_certificate.certificate_id
        blockchain.save_blockchain()
        return {
            "message": "Originality certificate already exists.",
            "submission": _serialize_submission(submission),
            "certificate": _serialize_certificate(existing_certificate),
        }

    if submission.status == QUEUED:
        submission.status = APPROVED
        if submission_id in blockchain.mint_queue:
            blockchain.mint_queue = [
                queued_id for queued_id in blockchain.mint_queue if queued_id != submission_id
            ]

    if submission.status != APPROVED:
        raise HTTPException(
            status_code=400,
            detail="Only approved submissions can be repaired with an originality certificate.",
        )

    vote_summary = blockchain.get_submission_votes(submission_id)
    voting_threshold = blockchain.get_voting_threshold()
    voting_window_expired = time.time() >= submission.created_at + (VOTING_WINDOW_HOURS * 60 * 60)
    if not vote_summary["votes"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot repair certificate: finalized vote data is missing.",
        )
    if not (len(vote_summary["votes"]) >= voting_threshold["minimum_votes"] or voting_window_expired):
        raise HTTPException(
            status_code=400,
            detail="Cannot repair certificate: vote data has not reached finality.",
        )
    if vote_summary["approval_percentage"] < ORIGINALITY_APPROVAL_THRESHOLD:
        raise HTTPException(
            status_code=400,
            detail="Cannot repair certificate: approval percentage is below the required threshold.",
        )

    try:
        certificate = blockchain.create_originality_certificate(submission_id, approved_at=time.time())
        persisted_certificate = blockchain.get_originality_certificate_for_submission(submission_id)
        if not persisted_certificate:
            raise ValueError("certificate could not be retrieved after repair")
        submission.certificate_id = persisted_certificate.certificate_id
        blockchain.save_blockchain()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Cannot repair certificate: {e}")

    return {
        "message": "Originality certificate repaired.",
        "submission": _serialize_submission(submission),
        "certificate": _serialize_certificate(certificate),
    }


@app.post("/certificates/{certificate_id}/broadcast")
@api_limit("mint")
async def broadcast_certificate(request: Request, certificate_id: str):
    certificate = blockchain.get_originality_certificate(certificate_id)
    if not certificate:
        raise HTTPException(
            status_code=404,
            detail=f"Originality certificate not found: {certificate_id}",
        )

    broadcast_result = broadcast_certificate_to_peers(
        certificate=certificate,
        peer_store=peer_store,
        origin_node_id=NODE_ID,
        network_name=NETWORK_NAME,
    )
    return {
        "message": "Originality certificate broadcast attempted.",
        "certificate": _serialize_certificate(certificate),
        "broadcast": broadcast_result,
    }


@app.post("/submissions/{submission_id}/broadcast")
@api_limit("submission_create")
async def broadcast_submission(request: Request, submission_id: str):
    submission = blockchain.get_submission(submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail=f"Submission not found: {submission_id}")

    broadcast_result = broadcast_submission_to_peers(
        submission=submission,
        peer_store=peer_store,
        origin_node_id=NODE_ID,
        network_name=NETWORK_NAME,
    )
    return {
        "message": "Submission broadcast attempted.",
        "submission": _serialize_submission(submission),
        "broadcast": broadcast_result,
    }

@app.post("/submissions/{submission_id}/vote")
@api_limit("vote")
async def vote_on_submission(
    request: Request,
    submission_id: str,
    vote_type: Annotated[VoteTypeValue, Form(...)],
    authorization: str | None = Header(default=None),
    voter: Annotated[str | None, Form(min_length=1, max_length=128)] = None,
    wallet_address: Annotated[str | None, Form(min_length=42, max_length=42, pattern=ETHEREUM_ADDRESS_PATTERN)] = None,
    message: Annotated[str | None, Form(min_length=1, max_length=4096)] = None,
    signature: Annotated[str | None, Form(min_length=1, max_length=4096)] = None,
):
    signed_vote_requested = any(
        value is not None and str(value).strip()
        for value in [authorization, wallet_address, message, signature]
    ) and not (voter and not authorization and not wallet_address and not message and not signature)

    if signed_vote_requested:
        try:
            verified_wallet = resolve_verified_wallet_from_authorization(
                authorization,
                manager=wallet_auth_manager,
            )
        except HTTPException as exc:
            raise HTTPException(status_code=401, detail=exc.detail) from exc

        if not message:
            raise HTTPException(status_code=400, detail="signed vote message is required.")
        if not signature:
            raise HTTPException(status_code=400, detail="signature is required.")

        submission = blockchain.get_submission(submission_id)
        if not submission:
            raise HTTPException(status_code=404, detail=f"Submission not found: {submission_id}")

        normalized_wallet = normalize_wallet_address(wallet_address or verified_wallet)
        if normalized_wallet is None or normalized_wallet != verified_wallet:
            raise HTTPException(status_code=403, detail="wallet_address must match the verified wallet session.")
        _enforce_access_for_feature(verified_wallet, feature="votes")
        _enforce_review_policy(verified_wallet, scope="voting")

        try:
            verification = wallet_auth_manager.verify_vote_signature(
                wallet_address=verified_wallet,
                message=message,
                signature=signature,
                submission_id=submission_id,
                content_hash=submission.content_hash or "",
                vote_type=vote_type,
            )
            vote = blockchain.cast_submission_vote(
                submission_id=submission_id,
                voter=verified_wallet,
                vote_type=vote_type,
            )
        except ValueError as e:
            detail = str(e)
            status_code = 400
            if detail.startswith("Submission not found"):
                status_code = 404
            elif "expired" in detail.lower() or "already been used" in detail.lower():
                status_code = 401
            raise HTTPException(status_code=status_code, detail=detail) from e

        vote["voter_wallet_address"] = verified_wallet
        vote["content_hash"] = submission.content_hash
        vote["vote_version"] = verification.get("vote_version")
        vote["protocol_version"] = verification.get("protocol_version")
        vote["network_id"] = verification.get("network_id")
        vote["signature_scheme"] = str(verification["signature_scheme"])
        vote["vote_signature"] = str(verification["vote_signature"])
        vote["vote_message"] = str(verification["vote_message"])
        vote["signed_message_hash"] = str(verification["signed_message_hash"])
        vote["vote_nonce"] = str(verification["nonce"])
        vote["vote_issued_at"] = str(verification["vote_issued_at"])
        vote["vote_expires_at"] = str(verification["vote_expires_at"])
        vote["signed_at"] = str(verification["signed_at"])
        vote["identity_source"] = str(verification["identity_source"])
    else:
        if not is_development():
            raise HTTPException(
                status_code=401,
                detail="MetaMask-signed votes are required outside development mode.",
            )
        if not voter:
            raise HTTPException(status_code=422, detail="voter is required for the development-only vote path.")
        if not is_valid_public_key(voter, blockchain.wallets):
            raise HTTPException(status_code=400, detail="Invalid voter public key.")

        try:
            vote = blockchain.cast_submission_vote(
                submission_id=submission_id,
                voter=voter,
                vote_type=vote_type,
            )
        except ValueError as e:
            message_text = str(e)
            if message_text.startswith("Submission not found"):
                raise HTTPException(status_code=404, detail=message_text)
            raise HTTPException(status_code=400, detail=message_text)

    blockchain.save_blockchain()
    broadcast_result = broadcast_vote_to_peers(
        vote=vote,
        peer_store=peer_store,
        origin_node_id=NODE_ID,
        network_name=NETWORK_NAME,
    )
    return {
        "message": "Vote recorded successfully.",
        "vote": vote,
        "broadcast": broadcast_result,
    }

@app.get("/submissions/{submission_id}/votes")
@api_limit("public_read")
async def get_submission_votes(request: Request, submission_id: str):
    try:
        return blockchain.get_submission_votes(submission_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/submissions/{submission_id}/votes/broadcast")
@api_limit("vote")
async def broadcast_submission_votes(request: Request, submission_id: str):
    try:
        vote_summary = blockchain.get_submission_votes(submission_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    broadcast_result = broadcast_votes_to_peers(
        votes=vote_summary["votes"],
        peer_store=peer_store,
        origin_node_id=NODE_ID,
        network_name=NETWORK_NAME,
    )
    return {
        "message": "Submission vote broadcast attempted.",
        "submission_id": submission_id,
        "broadcast": broadcast_result,
    }


@app.post("/submissions/{submission_id}/evaluate")
@api_limit("evaluate")
async def evaluate_submission(
    request: Request,
    submission_id: str,
    automated_originality_passed: bool | None = Form(None),
):
    submission = blockchain.get_submission(submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail=f"Submission not found: {submission_id}")
    if submission.status == HARD_REJECTED:
        raise HTTPException(status_code=400, detail="Hard rejected submissions cannot be evaluated.")
    if submission.status != PENDING:
        raise HTTPException(status_code=400, detail="Only pending submissions can be evaluated.")

    try:
        evaluation = blockchain.evaluate_submission(
            submission_id,
            automated_originality_passed=automated_originality_passed,
        )
        queued_submission = None
        certificate = blockchain.get_originality_certificate_for_submission(submission_id)
        if submission.status == APPROVED:
            if not certificate:
                raise ValueError(
                    "Approved submission is missing an originality certificate and cannot enter the mint queue."
                )
            queued_submission = blockchain.add_to_mint_queue(submission_id)
            certificate = blockchain.get_originality_certificate_for_submission(submission_id)
        blockchain.save_blockchain()
        if submission.status in {APPROVED, QUEUED}:
            certificate = blockchain.get_originality_certificate_for_submission(submission_id)
            if not certificate:
                raise ValueError(
                    "Originality certificate creation failed: certificate could not be retrieved after approval."
                )
            submission.certificate_id = certificate.certificate_id
        logging.debug(
            "evaluate_submission certificate lifecycle: submission_id=%s votes_cast=%s "
            "approval_percentage=%s decision=%s certificate_creation_attempted=%s "
            "certificate_id=%s certificate_lookup_after_save=%s",
            submission_id,
            evaluation.get("votes_cast"),
            evaluation.get("approval_percentage"),
            evaluation.get("reason"),
            evaluation.get("reason") == "approved_by_vote",
            certificate.certificate_id if certificate else None,
            certificate is not None,
        )
        certificate_broadcast = (
            broadcast_certificate_to_peers(
                certificate=certificate,
                peer_store=peer_store,
                origin_node_id=NODE_ID,
                network_name=NETWORK_NAME,
            )
            if certificate
            else {"attempted": 0, "succeeded": 0, "failed": 0, "results": []}
        )
    except ValueError as e:
        message = str(e)
        if message.startswith("Submission not found"):
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=400, detail=message)

    return {
        "message": "Submission evaluated successfully.",
        "evaluation": evaluation,
        "submission": _serialize_submission(queued_submission or submission),
        "certificate": _serialize_certificate(certificate) if certificate else None,
        "voter_reward_summary": blockchain.get_submission_voter_reward_summary(submission_id),
        "certificate_broadcast": certificate_broadcast,
    }

@app.post("/add_block")
@api_limit("mint")
async def add_block(
    request: Request,
    image: UploadFile,
    miner: Annotated[str, Form(..., min_length=66, max_length=66, pattern=PUBLIC_KEY_PATTERN)],
    private_key: Annotated[str, Form(..., min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")],  # ✅ Validate miner via wallet key
    role: str = Depends(require_legacy_direct_block_access),
):
    """
    Add a legacy direct block for development-only workflows.
    """

    print(f"Debug: Received add_block request - Miner: {miner}")

    # Validate miner's public key
    if not is_valid_public_key(miner, blockchain.wallets):
        print(f"Debug: Invalid miner public key {miner}")
        raise HTTPException(status_code=400, detail="Invalid miner public key.")

    # Validate the private key matches the public key
    wallet = blockchain.wallets.get(miner)
    if not wallet:
        print(f"Debug: Wallet for miner {miner} not found!")
        raise HTTPException(status_code=400, detail="Wallet not found.")

    if not wallet.validate_private_key(private_key, miner):
        print(f"Debug: Private key does not match public key {miner}")
        raise HTTPException(status_code=400, detail="Private key does not match the wallet ID.")

    # ✅ Print blockchain owner info (debugging `self.owner_wallet`)
    owner_wallet = getattr(blockchain, "owner_wallet", None)
    owner_public_key = getattr(owner_wallet, "public_key", None)
    print(f"Debug: Checking blockchain owner wallet... {_short_key(owner_public_key)}")
    print(f"Debug: Owner balance before block: {getattr(blockchain, 'owner_balance', 'NOT SET')}")

    # Validate image format
    if not image.filename:
        raise HTTPException(status_code=400, detail="Invalid image format. Allowed formats: jpg, jpeg, png, webp")

    file_bytes = await image.read()
    try:
        validate_content_size(len(file_bytes))
        safe_original_filename, _detected_mime_type = _validate_uploaded_image_payload(image, file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        # Create the temp directory if it doesn't exist
        os.makedirs("temp", exist_ok=True)

        # Save the uploaded image
        image_path = f"temp/{os.path.basename(safe_original_filename)}"
        with open(image_path, "wb") as buffer:
            buffer.write(file_bytes)

        # Debug: Check if the file exists
        if not os.path.isfile(image_path):
            print(f"Debug: File {os.path.basename(image.filename)} does not exist after saving.")
            return JSONResponse(status_code=400, content={"error": "Failed to save the uploaded image."})

        # Extract text content
        from utils import extract_text
        text_content = extract_text(image_path)
        if not text_content:
            os.remove(image_path)
            return JSONResponse(status_code=400, content={"error": "No text found in the image."})

        # ✅ Debug before calling `add_block`
        print(f"Debug: Calling blockchain.add_block() with Miner: {miner}")

        # Add a new block
        block_added = blockchain.add_block(
            image_path=image_path,
            text_content=text_content,
            miner=miner,
            validate_meme=True  # ✅ Skip validation in add_block since it was done here
        )

        # Remove the temporary image file
        os.remove(image_path)

        latest_block = blockchain.get_latest_block() if block_added else None
        broadcast_result = (
            broadcast_block_to_peers(
                block=latest_block,
                peer_store=peer_store,
                origin_node_id=NODE_ID,
                network_name=NETWORK_NAME,
            )
            if latest_block
            else {"attempted": 0, "succeeded": 0, "failed": 0, "results": []}
        )

        return {
            "message": "Legacy direct block added successfully.",
            "legacy_direct_block": True,
            "protocol_v1_mint_path": False,
            "access_role": role,
            "block": _serialize_block(latest_block) if latest_block else False,
            "broadcast": broadcast_result,
        }
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        logging.error("Unexpected error in add_block for miner %s: %s", _short_key(miner), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})

@app.post("/generate_wallet", summary="Generate a new wallet", description="Creates a new wallet.")
@api_limit("wallet_create")
async def generate_wallet(request: Request):  # ✅ No more API key validation
    """
    Generate a development-only server wallet.
    """
    require_development_mode(True, "Development wallet generation")
    wallet = Wallet()
    blockchain.wallets[wallet.public_key] = wallet  # Register the wallet in the blockchain

    logger.info("Wallet registered with public key: %s", _short_key(wallet.public_key))
    blockchain.save_blockchain()

    response = {
        "message": "Development-only server wallet generated successfully.",
        "warning": "This endpoint creates local test wallets only. MetaMask-backed 0x addresses are the normal native ZoidbergChain account model.",
        "wallet": _wallet_public_response(wallet.public_key, wallet),
    }
    if _dev_private_key_export_enabled():
        response["key_export"] = {
            "enabled": True,
            "endpoint": "/dev/wallets",
            "warning": DEV_ENDPOINT_WARNING,
        }
    else:
        response["key_export"] = {
            "enabled": False,
            "message": "Private key export is disabled for this environment.",
        }
    return response


@app.get("/accounts/{wallet_address}")
@api_limit("public_read")
async def get_native_account_summary(request: Request, wallet_address: str):
    try:
        normalized_wallet = _normalize_native_account_address(wallet_address)
        return _build_account_summary(normalized_wallet)
    except HTTPException:
        raise
    except Exception as e:
        logging.error("ERROR retrieving native account summary for wallet %s: %s", _short_key(wallet_address), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@app.get("/accounts/{wallet_address}/submissions")
@api_limit("public_read")
async def get_native_account_submissions(request: Request, wallet_address: str):
    try:
        normalized_wallet = _normalize_native_account_address(wallet_address)
        submissions = [
            _serialize_account_submission(submission)
            for submission in _get_account_submissions(normalized_wallet)
        ]
        return {
            "wallet_address": normalized_wallet,
            "normalized_wallet_address": normalized_wallet,
            "account_type": "metamask_native",
            "network_name": NETWORK_NAME,
            "submissions": submissions,
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error("ERROR retrieving native account submissions for wallet %s: %s", _short_key(wallet_address), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@app.get("/accounts/{wallet_address}/votes")
@api_limit("public_read")
async def get_native_account_votes(request: Request, wallet_address: str):
    try:
        normalized_wallet = _normalize_native_account_address(wallet_address)
        votes = [
            _serialize_account_vote(vote)
            for vote in _get_account_votes(normalized_wallet)
        ]
        return {
            "wallet_address": normalized_wallet,
            "normalized_wallet_address": normalized_wallet,
            "account_type": "metamask_native",
            "network_name": NETWORK_NAME,
            "votes": votes,
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error("ERROR retrieving native account votes for wallet %s: %s", _short_key(wallet_address), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@app.get("/accounts/{wallet_address}/rewards")
@api_limit("public_read")
async def get_native_account_rewards(request: Request, wallet_address: str):
    try:
        normalized_wallet = _normalize_native_account_address(wallet_address)
        return {
            "wallet_address": normalized_wallet,
            "normalized_wallet_address": normalized_wallet,
            "account_type": "metamask_native",
            "symbol": TICKER,
            "network_name": NETWORK_NAME,
            "rewards": _get_account_rewards(normalized_wallet),
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error("ERROR retrieving native account rewards for wallet %s: %s", _short_key(wallet_address), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@app.get("/accounts/{wallet_address}/transfers")
@api_limit("public_read")
async def get_native_account_transfers(request: Request, wallet_address: str):
    try:
        normalized_wallet = _normalize_native_account_address(wallet_address)
        return {
            "wallet_address": normalized_wallet,
            "normalized_wallet_address": normalized_wallet,
            "account_type": "metamask_native",
            "network_name": NETWORK_NAME,
            "transfers": _get_account_transfers(normalized_wallet),
            "note": "Transfer intents are pending and non-final until included in a meme-mined block.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error("ERROR retrieving native account transfers for wallet %s: %s", _short_key(wallet_address), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@app.get("/accounts/{wallet_address}/nonce")
@api_limit("public_read")
async def get_native_account_nonce(request: Request, wallet_address: str):
    try:
        normalized_wallet = _normalize_native_account_address(wallet_address)
        return blockchain.get_nonce_state(normalized_wallet)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as e:
        logging.error("ERROR retrieving native account nonce for wallet %s: %s", _short_key(wallet_address), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@app.get("/accounts/{wallet_address}/transactions")
@api_limit("public_read")
async def get_native_account_transactions(request: Request, wallet_address: str):
    try:
        normalized_wallet = _normalize_native_account_address(wallet_address)
        return {
            "wallet_address": normalized_wallet,
            "normalized_wallet_address": normalized_wallet,
            "account_type": "metamask_native",
            "network_name": NETWORK_NAME,
            "transactions": _get_account_transactions(normalized_wallet),
            "note": "Canonical native ZOID transaction history for this MetaMask-backed ZoidbergChain account.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error("ERROR retrieving native account transactions for wallet %s: %s", _short_key(wallet_address), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@app.get("/accounts/{wallet_address}/balance")
@api_limit("public_read")
async def get_native_account_balance(request: Request, wallet_address: str):
    try:
        normalized_wallet = _normalize_native_account_address(wallet_address)
        balance_snapshot = blockchain.get_native_balance_snapshot(normalized_wallet)
        return {
            "wallet_address": normalized_wallet,
            "normalized_wallet_address": normalized_wallet,
            "account_type": "metamask_native",
            "final_balance": balance_snapshot["final_balance"],
            "native_balance": balance_snapshot["native_balance"],
            "pending_outgoing": balance_snapshot["pending_outgoing"],
            "pending_incoming": balance_snapshot["pending_incoming"],
            "available_balance": balance_snapshot["available_balance"],
            "symbol": TICKER,
            "network_name": NETWORK_NAME,
            "note": "Pending outgoing transfers reduce available balance. Final balance changes only when a transfer is settled in a meme-mined block.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error("ERROR retrieving native account balance for wallet %s: %s", _short_key(wallet_address), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})

@app.get("/get_balance")
@api_limit("public_read")
async def get_balance(
    request: Request,
    public_key: Annotated[str, Query(..., min_length=66, max_length=66, pattern=PUBLIC_KEY_PATTERN)],
):
    """
    Retrieve the balance for a specific wallet.
    """
    try:
        if public_key not in blockchain.wallets:
            return JSONResponse(status_code=400, content={"error": f"Public key {public_key} is not registered in the blockchain."})

        balance = blockchain.get_balance(public_key)
        logging.info("Returning balance for wallet %s", _short_key(public_key))

        return {"message": "Balance retrieved successfully.", "balance": balance}
    except Exception as e:
        logging.error("ERROR retrieving balance for wallet %s: %s", _short_key(public_key), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@app.get("/wallets/{wallet_address}/balance")
@api_limit("public_read")
async def get_native_wallet_balance(request: Request, wallet_address: str):
    try:
        normalized_wallet = _normalize_supported_user_identity(wallet_address, field_name="wallet address")
        balance_snapshot = blockchain.get_native_balance_snapshot(normalized_wallet)
        return {
            "wallet_address": normalized_wallet,
            "final_balance": balance_snapshot["final_balance"],
            "native_balance": balance_snapshot["native_balance"],
            "pending_outgoing": balance_snapshot["pending_outgoing"],
            "pending_incoming": balance_snapshot["pending_incoming"],
            "available_balance": balance_snapshot["available_balance"],
            "symbol": TICKER,
            "network_name": NETWORK_NAME,
            "note": "Legacy compatibility balance read. Pending outgoing transfers reduce available balance. Final balance changes only when a transfer is settled in a meme-mined block.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error("ERROR retrieving native balance for wallet %s: %s", _short_key(wallet_address), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@app.get("/wallets/{wallet_address}/rewards")
@api_limit("public_read")
async def get_native_wallet_rewards(request: Request, wallet_address: str):
    try:
        normalized_wallet = _normalize_supported_user_identity(wallet_address, field_name="wallet address")
        rewards = blockchain.get_reward_records_for_wallet(normalized_wallet)
        return {
            "wallet_address": normalized_wallet,
            "symbol": COIN_NAME,
            "network_name": NETWORK_NAME,
            "rewards": rewards,
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error("ERROR retrieving rewards for wallet %s: %s", _short_key(wallet_address), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@app.get("/wallets/{wallet_address}/transfers")
@api_limit("public_read")
async def get_wallet_transfer_intents(request: Request, wallet_address: str):
    try:
        normalized_wallet = _normalize_supported_user_identity(wallet_address, field_name="wallet address")
        transfers = [
            _serialize_transfer_intent(record)
            for record in blockchain.get_transfer_intents_for_wallet(normalized_wallet)
        ]
        transfers.sort(key=lambda record: record.get("created_at") or 0, reverse=True)
        return {
            "wallet_address": normalized_wallet,
            "network_name": NETWORK_NAME,
            "transfers": transfers,
            "note": "Legacy compatibility transfer-intent read. Native ZOID transactions settle only when included in a meme-mined block.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error("ERROR retrieving transfer intents for wallet %s: %s", _short_key(wallet_address), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@app.get("/wallets/{wallet_address}/transactions")
@api_limit("public_read")
async def get_wallet_transactions(request: Request, wallet_address: str):
    try:
        normalized_wallet = _normalize_supported_user_identity(wallet_address, field_name="wallet address")
        return {
            "wallet_address": normalized_wallet,
            "network_name": NETWORK_NAME,
            "transactions": _get_account_transactions(normalized_wallet),
            "note": "Legacy compatibility transaction history read for native ZOID account activity.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error("ERROR retrieving transactions for wallet %s: %s", _short_key(wallet_address), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@app.get("/transfers/{transfer_id}")
@api_limit("public_read")
async def get_transfer_intent(request: Request, transfer_id: str):
    transfer_intent = blockchain.get_transfer_intent(transfer_id)
    if not transfer_intent:
        raise HTTPException(status_code=404, detail=f"Transfer intent not found: {transfer_id}")
    return {
        "transfer": _serialize_transfer_intent(transfer_intent),
        "note": "Transfer intents are pending and non-final until included in a meme-mined block.",
    }


@app.get("/transactions/{tx_id}")
@api_limit("public_read")
async def get_native_transaction(request: Request, tx_id: str):
    transaction = blockchain.get_native_transaction(tx_id)
    if not transaction:
        raise HTTPException(status_code=404, detail=f"Transaction not found: {tx_id}")
    return {
        "transaction": _serialize_native_transaction(transaction),
        "note": "Native ZOID transaction record. Non-final until included in a meme-mined block unless status is settled.",
    }


@app.post("/transactions/{tx_id}/admit")
@api_limit("transaction_create")
async def admit_native_transaction_to_mempool(request: Request, tx_id: str):
    try:
        admission = blockchain.admit_transaction_to_mempool(tx_id)
        blockchain.save_blockchain()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return admission


@app.post("/transactions/{tx_id}/broadcast")
@api_limit("transaction_create")
async def broadcast_native_transaction(
    request: Request,
    tx_id: str,
    _: str = Depends(require_transaction_broadcast_access),
):
    transaction = blockchain.get_native_transaction(tx_id)
    if not transaction:
        raise HTTPException(status_code=404, detail=f"Transaction not found: {tx_id}")
    status = str(transaction.get("status") or "").strip().lower()
    if status not in {"signed_pending", "validated_pending", "mempool"}:
        raise HTTPException(status_code=400, detail="Only signed pending or mempool-eligible transactions can be broadcast.")

    if status != "mempool":
        try:
            blockchain.admit_transaction_to_mempool(tx_id)
            blockchain.save_blockchain()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        report = broadcast_transaction_to_peers(
            blockchain=blockchain,
            tx_id=tx_id,
            peer_store=peer_store,
            origin_node_id=NODE_ID,
            network_name=NETWORK_NAME,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "tx_id": tx_id,
        "broadcasted": True,
        "peers_attempted": report["attempted"],
        "peers_accepted": report["accepted"],
        "results": report["results"],
    }


@app.get("/mempool")
@api_limit("public_read")
async def get_mempool(request: Request):
    transactions = [
        _serialize_native_transaction(transaction)
        for transaction in blockchain.list_mempool_transactions()
    ]
    return {
        "count": len(transactions),
        "transactions": transactions,
        "ordering_policy": "admitted_at ascending, then from_address ascending, then nonce ascending, then tx_id ascending",
        "note": "Local mempool only. Transactions are not settled until included in a block.",
    }


@app.get("/mempool/{tx_id}")
@api_limit("public_read")
async def get_mempool_transaction(request: Request, tx_id: str):
    transaction = blockchain.get_mempool_transaction(tx_id)
    if not transaction:
        raise HTTPException(status_code=404, detail=f"Mempool transaction not found: {tx_id}")
    return {
        "transaction": _serialize_native_transaction(transaction),
        "note": "Present in the local mempool. Not settled until included in a block.",
    }


@app.post("/mempool/revalidate")
@api_limit("transaction_create")
async def revalidate_mempool(request: Request):
    report = blockchain.revalidate_mempool_transactions(save=True)
    report["message"] = "Local mempool revalidation complete."
    return report

@app.get("/get_reward_pool_balance")
@api_limit("public_read")
async def get_reward_pool_balance(request: Request):
    """
    Retrieve the balance of the reward pool.
    
    Returns:
        dict: The current balance of the reward pool.
    """
    try:
        # Get the reward pool balance
        balance = blockchain.reward_pool

        return {
            "message": "Reward pool balance retrieved successfully.",
            "reward_pool_balance": balance
        }
    except Exception as e:
        logging.error("ERROR retrieving reward pool balance: %s", e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})

@app.get("/active-users")
@api_limit("public_read")
async def active_users(request: Request):
    return {
        "active_users": blockchain.get_active_users(),
        "lookback_days": ACTIVE_USER_LOOKBACK_DAYS,
    }

@app.get("/voting-threshold")
@api_limit("public_read")
async def voting_threshold(request: Request):
    return blockchain.get_voting_threshold()

@app.get("/mint-queue")
@api_limit("public_read")
async def mint_queue(
    request: Request,
    include_blocked: bool = Query(True),
    mintable_only: bool = Query(False),
):
    changed = False
    if blockchain.link_certificates_to_submissions():
        changed = True
    if sync_approved_submissions_to_mint_queue():
        changed = True
    if changed:
        blockchain.save_blockchain()
    return {"mint_queue": blockchain.get_mint_queue(include_blocked=include_blocked, mintable_only=mintable_only)}


@app.post("/mint/{submission_id}")
@app.post("/mint-queue/{submission_id}/mint")
@api_limit("mint")
async def mint_queued_submission(
    request: Request,
    submission_id: str,
    miner: str | None = Form(None),
):
    submission = blockchain.get_submission(submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail=f"Submission not found: {submission_id}")
    if submission.status == HARD_REJECTED:
        raise HTTPException(status_code=400, detail="Hard rejected submissions cannot be minted.")
    try:
        minted = blockchain.mint_submission(
            submission_id,
            miner=miner,
            validate_meme=False,
        )
        blockchain.save_blockchain()
    except ValueError as e:
        message = str(e)
        if message.startswith("Submission not found"):
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=400, detail=message)

    submission = blockchain.get_submission(submission_id) or submission
    latest_block = blockchain.get_latest_block()
    certificate = (
        blockchain.get_originality_certificate(latest_block.certificate_id)
        if latest_block.certificate_id
        else None
    )
    broadcast_result = (
        broadcast_block_to_peers(
            block=latest_block,
            peer_store=peer_store,
            origin_node_id=NODE_ID,
            network_name=NETWORK_NAME,
            related_submission_id=submission_id,
            certificate=certificate,
        )
        if minted
        else {"attempted": 0, "succeeded": 0, "failed": 0, "results": []}
    )

    return {
        "message": "Meme block minted with native ZOID transactions.",
        "minted": minted,
        "submission": _serialize_submission(submission),
        "block": _serialize_block(latest_block),
        "block_hash": latest_block.hash,
        "block_height": latest_block.index,
        "reward_recipient": latest_block.reward_recipient,
        "reward_amount": latest_block.reward_amount,
        "reward_type": latest_block.reward_type,
        "voter_reward_summary": blockchain.get_submission_voter_reward_summary(submission_id),
        "transactions_included": getattr(latest_block, "transaction_count", 0) or 0,
        "transaction_ids": list(getattr(latest_block, "transaction_ids", []) or []),
        "broadcast": broadcast_result,
    }


@app.post("/submissions/{submission_id}/block-minting")
@api_limit("dev_endpoint")
async def block_submission_minting(
    request: Request,
    submission_id: str,
    payload: MintBlockRequest,
    role: str = Depends(require_mint_queue_management_access),
):
    try:
        submission = blockchain.block_minting_for_submission(
            submission_id,
            reason=payload.reason,
            notes=payload.notes,
            blocked_by=role,
        )
        blockchain.save_blockchain()
    except ValueError as exc:
        message = str(exc)
        if message.startswith("Submission not found"):
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc

    return {
        "message": "Submission minting blocked successfully.",
        "submission": _serialize_submission(submission),
    }


@app.post("/submissions/{submission_id}/unblock-minting")
@api_limit("dev_endpoint")
async def unblock_submission_minting(
    request: Request,
    submission_id: str,
    role: str = Depends(require_mint_queue_management_access),
):
    try:
        submission = blockchain.unblock_minting_for_submission(submission_id)
        blockchain.save_blockchain()
    except ValueError as exc:
        message = str(exc)
        if message.startswith("Submission not found"):
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc

    return {
        "message": "Submission minting unblocked successfully.",
        "submission": _serialize_submission(submission),
    }


@app.post("/dev/mint-queue/cleanup-bad-items")
@api_limit("dev_endpoint")
async def cleanup_bad_mint_queue_items(
    request: Request,
    payload: MintQueueCleanupRequest,
    role: str = Depends(require_mint_queue_management_access),
):
    report = blockchain.cleanup_bad_mint_queue_items(block_unmintable=payload.block_unmintable and not payload.dry_run)
    if payload.block_unmintable and not payload.dry_run:
        blockchain.save_blockchain()
    return report
