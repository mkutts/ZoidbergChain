import os
import time
import logging
import hmac
from typing import Annotated, Any, Literal
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, Form, HTTPException, Depends, Request, Header, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded

from blockchain import Blockchain
from wallet import Wallet
from transaction import Transaction
from submission import APPROVED, HARD_REJECTED, MINTED, PENDING, QUEUED, REJECTED
from utils import extract_text
from validators import (
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
    is_safe_filename,
    is_valid_amount,
    is_valid_image,
    is_valid_public_key,
    is_valid_wallet_public_key,
)
from config import (
    ACTIVE_USER_LOOKBACK_DAYS,
    COIN_NAME,
    ENABLE_RATE_LIMITING,
    PEER_SIGNATURE_WINDOW_SECONDS,
    ENVIRONMENT,
    NETWORK_NAME,
    NODE_ID,
    ORIGINALITY_APPROVAL_THRESHOLD,
    PUBLIC_NODE_URL,
    SUBMISSIONS_DIR,
    VOTING_WINDOW_HOURS,
    allow_dev_reset_endpoints,
    allow_private_key_export,
    get_rate_limit,
    peer_replay_protection_enabled,
    is_development,
    is_production,
    public_api_mode_enabled,
    peer_auth_required,
    peer_shared_secret,
    peer_shared_secret_is_configured,
    signed_peer_messages_enabled,
    require_peer_auth,
)
from auth import validate_api_key  # ✅ API authentication

from peers import PeerStore, normalize_peer_url
from peer_sync import (
    ChainExtensionError,
    ConflictingVoteError,
    ConflictingCertificateError,
    DuplicateBlockError,
    DuplicateSubmissionError,
    MalformedBlockError,
    MalformedCertificateError,
    MalformedSubmissionError,
    MalformedVoteError,
    UnauthorizedPeerError,
    UnknownSubmissionError,
    WrongNetworkError,
    broadcast_block_to_peers,
    broadcast_certificate_to_peers,
    broadcast_submission_to_peers,
    broadcast_vote_to_peers,
    broadcast_votes_to_peers,
    receive_peer_block,
    receive_peer_certificate,
    receive_peer_submission,
    receive_peer_vote,
    ExpiredPeerSignatureError,
    InvalidPeerSignatureError,
    InvalidPeerTimestampError,
    MissingSignedPeerHeadersError,
    ReplayedPeerNonceError,
    verify_peer_signature,
    sync_chain_from_peers,
)

logging.basicConfig(
    filename="api.log",  # Save logs to a file
    level=logging.INFO,  # Set log level to INFO
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

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


class _StrictBodyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PeerTransactionPayload(_StrictBodyModel):
    sender: Annotated[str, Field(min_length=1, max_length=128)]
    recipient: WalletPublicKey
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


class PeerVotePayload(_StrictBodyModel):
    submission_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    voter: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    vote_type: str | None = None
    vote_value: str | None = None
    created_at: Annotated[float, Field(ge=0)] | None = None
    vote_timestamp: Annotated[float, Field(ge=0)] | None = None


class PeerCertificatePayload(_StrictBodyModel):
    certificate_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    submission_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    content_hash: Annotated[str, Field(min_length=1, max_length=128)] | None = None
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


class PeerBlockPayload(_StrictBodyModel):
    index: Annotated[int, Field(ge=0)] | None = None
    previous_hash: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    timestamp: Annotated[float, Field(ge=0)] | None = None
    transactions: list[PeerTransactionPayload] | None = None
    miner: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    meme: dict[str, Any] | str | None = None
    hash: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    submission_id: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    certificate_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    content_hash: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    creator_wallet: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    vote_hash: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    approval_percentage: Annotated[float, Field(ge=0)] | None = None
    decisive_vote_total: Annotated[int, Field(ge=0)] | None = None
    minimum_votes_required: Annotated[int, Field(ge=0)] | None = None
    approved_at: Annotated[float, Field(ge=0)] | None = None
    originality_score: Annotated[float, Field(ge=0)] | None = None


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
    submission_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    voter: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    vote_type: str | None = None
    vote_value: str | None = None
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
    if not is_valid_wallet_public_key(payload.get("submitter", "")):
        raise HTTPException(status_code=422, detail="Submission submitter is required.")


def _validate_unregistered_peer_vote_shape(receive_request: PeerVoteReceive):
    payload = receive_request.model_dump()
    if _has_forbidden_key_fields(payload):
        raise HTTPException(status_code=422, detail="Vote payload contains forbidden or unexpected fields.")
    if not isinstance(payload.get("submission_id"), str) or not payload["submission_id"].strip():
        raise HTTPException(status_code=422, detail="Vote submission_id is required.")
    if not is_valid_wallet_public_key(payload.get("voter", "")):
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


def _dev_private_key_export_enabled():
    return development_tools_enabled(allow_private_key_export())


def _require_dev_private_key_export():
    require_development_mode(
        allow_private_key_export(),
        "Development private key export",
    )


async def require_peer_secret(
    request: Request,
    x_zoid_peer_secret: str | None = Header(default=None, alias="X-ZOID-Peer-Secret"),
):
    if signed_peer_messages_enabled():
        body_bytes = await request.body()
        try:
            verify_peer_signature(
                method=request.method,
                path=request.url.path,
                headers=request.headers,
                body_bytes=body_bytes,
            )
            return
        except MissingSignedPeerHeadersError as exc:
            raise HTTPException(status_code=401, detail=str(exc))
        except InvalidPeerTimestampError as exc:
            raise HTTPException(status_code=401, detail=str(exc))
        except ExpiredPeerSignatureError as exc:
            raise HTTPException(status_code=401, detail=str(exc))
        except InvalidPeerSignatureError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ReplayedPeerNonceError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

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
        "allow_dev_wallet_private_key_export=%s",
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
    )

@asynccontextmanager
async def lifespan(app):
    log_startup_security_config()
    yield


app = FastAPI(lifespan=lifespan)

# CORS: allow both local and live frontend origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://zoidbergcoin.com",
    ],
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
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Try again later."},
    )

app.add_middleware(SlowAPIMiddleware)


def api_limit(category):
    return limiter.limit(get_rate_limit(category))


peer_store = PeerStore()


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


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Preserve expected FastAPI/HTTPException responses."""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


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
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    logging.error(f"Exception: {str(exc)} - {request.method} {request.url.path}")
    return JSONResponse(status_code=500, content={"error": "Internal Server Error"})

# ✅ Serve the Home Page (Splash Page)
@app.get("/")
async def home():
    """Serve the splash page (index.html)."""
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

# ✅ Load blockchain properly when FastAPI starts
blockchain = Blockchain(project_owner, contributor1, contributor2)

def _reset_blockchain_to_genesis():
    global project_owner, contributor1, contributor2, blockchain
    blockchain.storage.delete_blockchain_document()

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
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


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


@app.get("/node-info")
@api_limit("public_read")
async def node_info(request: Request):
    latest_block = blockchain.get_latest_block()
    return {
        "node_id": NODE_ID,
        "public_node_url": PUBLIC_NODE_URL,
        "network_name": NETWORK_NAME,
        "chain_height": latest_block.index,
        "latest_block_hash": latest_block.hash,
        "cumulative_originality_score": blockchain.get_cumulative_originality_score(),
    }


@app.post("/peers/register")
@api_limit("peer_receive")
async def register_peer(request: Request, registration: PeerRegistration, _: None = Depends(require_peer_secret)):
    if registration.network_name.strip() != NETWORK_NAME:
        raise HTTPException(status_code=400, detail="Peer belongs to a different network.")

    try:
        peer_url = normalize_peer_url(str(registration.url))
        public_node_url = normalize_peer_url(PUBLIC_NODE_URL)
        if registration.node_id.strip() == NODE_ID or peer_url == public_node_url:
            raise HTTPException(status_code=400, detail="Cannot register this node as a peer.")

        peer = peer_store.register_peer(
            node_id=registration.node_id,
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


@app.post("/peers/submissions/receive")
@api_limit("peer_receive")
async def receive_submission_from_peer(request: Request, receive_request: PeerSubmissionReceive, _: None = Depends(require_peer_secret)):
    try:
        if not peer_store.get_active_peer(receive_request.origin_node_id):
            _validate_unregistered_peer_submission_shape(receive_request)
        return receive_peer_submission(
            blockchain=blockchain,
            peer_store=peer_store,
            origin_node_id=receive_request.origin_node_id,
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
        if not peer_store.get_active_peer(receive_request.origin_node_id):
            _validate_unregistered_peer_vote_shape(receive_request)
        return receive_peer_vote(
            blockchain=blockchain,
            peer_store=peer_store,
            origin_node_id=receive_request.origin_node_id,
            network_name=receive_request.network_name,
            vote_payload={
                "submission_id": receive_request.submission_id,
                "voter": receive_request.voter,
                "vote_type": receive_request.vote_type,
                "vote_value": receive_request.vote_value,
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
        if not peer_store.get_active_peer(receive_request.origin_node_id):
            _validate_unregistered_peer_certificate_shape(receive_request)
        return receive_peer_certificate(
            blockchain=blockchain,
            peer_store=peer_store,
            origin_node_id=receive_request.origin_node_id,
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
        if receive_request.block is None:
            raise HTTPException(status_code=400, detail="Block payload is required.")
        if not peer_store.get_active_peer(receive_request.origin_node_id):
            _validate_unregistered_peer_block_shape(receive_request)
        return receive_peer_block(
            blockchain=blockchain,
            peer_store=peer_store,
            origin_node_id=receive_request.origin_node_id,
            network_name=receive_request.network_name,
            block_payload=receive_request.block.model_dump(),
            related_submission_id=receive_request.related_submission_id,
            local_network_name=NETWORK_NAME,
            certificate_payload=receive_request.certificate.model_dump() if receive_request.certificate else None,
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
        raise HTTPException(status_code=400, detail=str(e))
    except DuplicateBlockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ChainExtensionError as e:
        raise HTTPException(status_code=409, detail=str(e))

@app.get("/chain")
@api_limit("public_read")
async def get_chain(request: Request):
    """Retrieve the blockchain."""
    return {"chain": blockchain.get_chain()}


@app.get("/chain/summary")
@api_limit("public_read")
async def chain_summary(request: Request):
    latest_block = blockchain.get_latest_block()
    return {
        "network_name": NETWORK_NAME,
        "node_id": NODE_ID,
        "chain_height": latest_block.index,
        "latest_block_hash": latest_block.hash,
        "genesis_hash": blockchain.chain[0].hash,
        "cumulative_originality_score": blockchain.get_cumulative_originality_score(),
        "cumulative_work": None,
    }


@app.get("/chain/blocks")
@api_limit("public_read")
async def chain_blocks(request: Request, from_height: int = 0):
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
            block.to_dict()
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
    )


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
        "block": block.to_dict(),
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
    Retrieve registered wallets using public-safe fields only.
    """
    try:
        return {
            "message": "Registered wallets retrieved successfully.",
            "wallets": [
                _wallet_public_response(key, wallet)
                for key, wallet in blockchain.wallets.items()
            ],
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/dev/wallets")
@api_limit("dev_endpoint")
async def get_dev_wallets(request: Request):
    _require_dev_private_key_export()
    return {
        "warning": DEV_ENDPOINT_WARNING,
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

@app.post("/submit_content")
@api_limit("submission_create")
async def submit_content(
    request: Request,
    image: UploadFile,
    submitter: Annotated[str, Form(..., min_length=66, max_length=66, pattern=PUBLIC_KEY_PATTERN)],
    text_content: Annotated[str | None, Form(max_length=MAX_SUBMISSION_TEXT_LENGTH)] = None,
):
    """Submit meme content for review without minting a blockchain block."""
    if not is_valid_public_key(submitter, blockchain.wallets):
        raise HTTPException(status_code=400, detail="Invalid submitter public key.")

    if not image.filename or not is_safe_filename(image.filename) or not is_valid_image(image):
        raise HTTPException(status_code=400, detail="Invalid image format. Allowed formats: jpg, jpeg, png, webp")

    os.makedirs(SUBMISSIONS_DIR, exist_ok=True)
    image_path = os.path.join(SUBMISSIONS_DIR, os.path.basename(image.filename))
    with open(image_path, "wb") as buffer:
        buffer.write(await image.read())

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
    blockchain.save_blockchain()
    broadcast_result = broadcast_submission_to_peers(
        submission=submission,
        peer_store=peer_store,
        origin_node_id=NODE_ID,
        network_name=NETWORK_NAME,
    )

    return {
        "message": "Content submitted successfully.",
        "submission": submission.to_dict(),
        "broadcast": broadcast_result,
    }


@app.get("/submissions")
@api_limit("public_read")
async def get_submissions(request: Request, status: SubmissionStatusValue | None = None):
    submissions = [submission.to_dict() for submission in blockchain.submissions]
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
    return {"submission": submission.to_dict()}


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
    return {"certificate": certificate.to_dict()}


@app.get("/certificates/{certificate_id}")
@api_limit("public_read")
async def get_certificate(request: Request, certificate_id: str):
    certificate = blockchain.get_originality_certificate(certificate_id)
    if not certificate:
        raise HTTPException(
            status_code=404,
            detail=f"Originality certificate not found: {certificate_id}",
        )
    return {"certificate": certificate.to_dict()}


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
            "submission": submission.to_dict(),
            "certificate": existing_certificate.to_dict(),
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
        "submission": submission.to_dict(),
        "certificate": certificate.to_dict(),
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
        "certificate": certificate.to_dict(),
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
        "submission": submission.to_dict(),
        "broadcast": broadcast_result,
    }

@app.post("/submissions/{submission_id}/vote")
@api_limit("vote")
async def vote_on_submission(
    request: Request,
    submission_id: str,
    voter: Annotated[str, Form(..., min_length=66, max_length=66, pattern=PUBLIC_KEY_PATTERN)],
    vote_type: Annotated[VoteTypeValue, Form(...)],
):
    if not is_valid_public_key(voter, blockchain.wallets):
        raise HTTPException(status_code=400, detail="Invalid voter public key.")

    try:
        vote = blockchain.cast_submission_vote(
            submission_id=submission_id,
            voter=voter,
            vote_type=vote_type,
        )
    except ValueError as e:
        message = str(e)
        if message.startswith("Submission not found"):
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=400, detail=message)

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
        "submission": (queued_submission or submission).to_dict(),
        "certificate": certificate.to_dict() if certificate else None,
        "certificate_broadcast": certificate_broadcast,
    }

@app.post("/add_block")
@api_limit("mint")
async def add_block(
    request: Request,
    image: UploadFile,
    miner: Annotated[str, Form(..., min_length=66, max_length=66, pattern=PUBLIC_KEY_PATTERN)],
    private_key: Annotated[str, Form(..., min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")],  # ✅ Validate miner via wallet key
):
    """
    Add a new block to the blockchain with the given meme image and transactions.
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
    if not image.filename or not is_safe_filename(image.filename) or not is_valid_image(image):
        raise HTTPException(status_code=400, detail="Invalid image format. Allowed formats: jpg, jpeg, png, webp")

    try:
        # Create the temp directory if it doesn't exist
        os.makedirs("temp", exist_ok=True)

        # Save the uploaded image
        image_path = f"temp/{os.path.basename(image.filename)}"
        with open(image_path, "wb") as buffer:
            buffer.write(await image.read())

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
            "message": "Block added successfully.",
            "block": latest_block.to_dict() if latest_block else False,
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
    Generate a new wallet.
    """
    wallet = Wallet()
    blockchain.wallets[wallet.public_key] = wallet  # Register the wallet in the blockchain

    logger.info("Wallet registered with public key: %s", _short_key(wallet.public_key))
    blockchain.save_blockchain()

    response = {
        "message": "Wallet generated successfully.",
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
async def mint_queue(request: Request):
    changed = False
    if blockchain.link_certificates_to_submissions():
        changed = True
    if sync_approved_submissions_to_mint_queue():
        changed = True
    if blockchain.remove_invalid_mint_queue_entries():
        changed = True
    if changed:
        blockchain.save_blockchain()
    return {"mint_queue": blockchain.get_mint_queue()}


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
    if submission.status == MINTED:
        raise HTTPException(status_code=400, detail="Submission has already been minted.")
    if submission.status in {PENDING, REJECTED}:
        raise HTTPException(status_code=400, detail="Only approved unminted submissions can be minted.")

    try:
        if submission.status == APPROVED:
            submission = blockchain.add_to_mint_queue(submission_id)
        if submission.status != QUEUED:
            raise ValueError("Only approved unminted submissions can be minted.")

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
        "message": "Submission minted successfully.",
        "minted": minted,
        "submission": submission.to_dict(),
        "block": latest_block.to_dict(),
        "broadcast": broadcast_result,
    }
