import os
import time
import logging
from fastapi import FastAPI, UploadFile, Form, HTTPException, Depends, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.extension import _rate_limit_exceeded_handler

from blockchain import Blockchain
from wallet import Wallet
from transaction import Transaction
from submission import APPROVED, HARD_REJECTED, MINTED, PENDING, QUEUED, REJECTED
from utils import extract_text
from validators import is_valid_public_key, is_valid_amount, is_valid_image
from config import (
    ACTIVE_USER_LOOKBACK_DAYS,
    ADD_BLOCK_RATE_LIMIT,
    BLOCKCHAIN_FILE,
    COIN_NAME,
    NETWORK_NAME,
    NODE_ID,
    PUBLIC_NODE_URL,
    RATE_LIMIT_ENABLED,
    SUBMISSION_RATE_LIMIT,
    SUBMISSIONS_DIR,
    TRANSACTION_RATE_LIMIT,
    VOTE_RATE_LIMIT,
    WALLET_GENERATION_RATE_LIMIT,
)
from auth import validate_api_key  # ✅ API authentication

from peers import PeerStore, normalize_peer_url
from peer_sync import (
    ChainExtensionError,
    ConflictingVoteError,
    DuplicateBlockError,
    DuplicateSubmissionError,
    MalformedBlockError,
    MalformedSubmissionError,
    MalformedVoteError,
    UnauthorizedPeerError,
    UnknownSubmissionError,
    WrongNetworkError,
    broadcast_block_to_peers,
    broadcast_submission_to_peers,
    broadcast_vote_to_peers,
    broadcast_votes_to_peers,
    receive_peer_block,
    receive_peer_submission,
    receive_peer_vote,
    sync_chain_from_peers,
)

logging.basicConfig(
    filename="api.log",  # Save logs to a file
    level=logging.INFO,  # Set log level to INFO
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# code? 

app = FastAPI()

# ✅ CORS: Allow both Local and Live Frontend
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
limiter = Limiter(key_func=get_remote_address, enabled=RATE_LIMIT_ENABLED)

# ✅ Exclude FastAPI Docs from rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


def api_limit(rate):
    return limiter.limit(rate)


class PeerRegistration(BaseModel):
    node_id: str
    url: str
    network_name: str


class PeerSubmissionReceive(BaseModel):
    origin_node_id: str
    network_name: str
    submission: dict


class PeerVoteReceive(BaseModel):
    origin_node_id: str | None = None
    network_name: str | None = None
    submission_id: str | None = None
    voter: str | None = None
    vote_type: str | None = None
    vote_value: str | None = None
    created_at: float | None = None
    vote_timestamp: float | None = None


class PeerBlockReceive(BaseModel):
    origin_node_id: str | None = None
    network_name: str | None = None
    block: dict | None = None
    related_submission_id: str | None = None


peer_store = PeerStore()


def sync_approved_submissions_to_mint_queue():
    queued_any = False
    for submission in blockchain.submissions:
        if submission.status == APPROVED and submission.submission_id not in blockchain.mint_queue:
            blockchain.add_to_mint_queue(submission.submission_id)
            queued_any = True
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
    log_message = f"{request.client.host} - {request.method} {request.url} - {response.status_code} ({process_time:.2f}s)"
    logging.info(log_message)
    return response

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global error handler to log unexpected errors."""
    if isinstance(exc, StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    logging.error(f"Exception: {str(exc)} - {request.method} {request.url}")
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
if os.path.exists(BLOCKCHAIN_FILE):
    print(f"✅ Debug: Loading existing blockchain from {BLOCKCHAIN_FILE}...")
    blockchain = Blockchain()  # ✅ Ensures it loads correctly
else:
    print("⚠️ Debug: No blockchain file found. Creating new blockchain...")
    blockchain = Blockchain(project_owner, contributor1, contributor2)  # ✅ Only creates new if no file exists

@app.post("/reset_blockchain")
async def reset_blockchain():
    """Reset blockchain to Genesis state."""
    try:
        if os.path.exists(BLOCKCHAIN_FILE):
            os.remove(BLOCKCHAIN_FILE)  # ✅ Delete previous blockchain state

        global project_owner, contributor1, contributor2, blockchain
        
        # ✅ RECREATE wallets
        project_owner = Wallet()
        contributor1 = Wallet()
        contributor2 = Wallet()

        # ✅ PASS wallets to Blockchain constructor
        blockchain = Blockchain(
            project_owner_wallet=project_owner,
            Contributor_one=contributor1,
            Contributor_two=contributor2
        )

        return {"message": "Blockchain reset to Genesis state."}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/sync")
async def sync_blockchain():
    """Returns the latest blockchain state for syncing with other nodes."""
    return {"chain": blockchain.get_chain()}


@app.get("/node-info")
async def node_info():
    latest_block = blockchain.get_latest_block()
    return {
        "node_id": NODE_ID,
        "public_node_url": PUBLIC_NODE_URL,
        "network_name": NETWORK_NAME,
        "chain_height": latest_block.index,
        "latest_block_hash": latest_block.hash,
    }


@app.post("/peers/register")
async def register_peer(registration: PeerRegistration):
    if registration.network_name.strip() != NETWORK_NAME:
        raise HTTPException(status_code=400, detail="Peer belongs to a different network.")

    try:
        peer_url = normalize_peer_url(registration.url)
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
async def get_peers():
    return {"peers": peer_store.list_peers()}


@app.post("/peers/submissions/receive")
async def receive_submission_from_peer(receive_request: PeerSubmissionReceive):
    try:
        return receive_peer_submission(
            blockchain=blockchain,
            peer_store=peer_store,
            origin_node_id=receive_request.origin_node_id,
            network_name=receive_request.network_name,
            submission_payload=receive_request.submission,
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
async def receive_vote_from_peer(receive_request: PeerVoteReceive):
    try:
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


@app.post("/peers/blocks/receive")
async def receive_block_from_peer(receive_request: PeerBlockReceive):
    try:
        return receive_peer_block(
            blockchain=blockchain,
            peer_store=peer_store,
            origin_node_id=receive_request.origin_node_id,
            network_name=receive_request.network_name,
            block_payload=receive_request.block,
            related_submission_id=receive_request.related_submission_id,
            local_network_name=NETWORK_NAME,
        )
    except UnauthorizedPeerError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except WrongNetworkError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except MalformedBlockError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DuplicateBlockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ChainExtensionError as e:
        raise HTTPException(status_code=409, detail=str(e))

@app.get("/chain")
async def get_chain():
    """Retrieve the blockchain."""
    return {"chain": blockchain.get_chain()}


@app.get("/chain/summary")
async def chain_summary():
    latest_block = blockchain.get_latest_block()
    return {
        "network_name": NETWORK_NAME,
        "node_id": NODE_ID,
        "chain_height": latest_block.index,
        "latest_block_hash": latest_block.hash,
        "genesis_hash": blockchain.chain[0].hash,
        "cumulative_work": None,
    }


@app.get("/chain/blocks")
async def chain_blocks(from_height: int = 0):
    if from_height < 0:
        raise HTTPException(status_code=400, detail="from_height must be non-negative.")

    return {
        "blocks": [
            block.to_dict()
            for block in blockchain.chain
            if block.index >= from_height
        ]
    }


@app.post("/chain/sync")
async def sync_chain():
    return sync_chain_from_peers(
        blockchain=blockchain,
        peer_store=peer_store,
        network_name=NETWORK_NAME,
    )


@app.post("/blocks/{block_hash}/broadcast")
async def broadcast_block(block_hash: str):
    block = next((block for block in blockchain.chain if block.hash == block_hash), None)
    if not block:
        raise HTTPException(status_code=404, detail=f"Block not found: {block_hash}")

    broadcast_result = broadcast_block_to_peers(
        block=block,
        peer_store=peer_store,
        origin_node_id=NODE_ID,
        network_name=NETWORK_NAME,
    )
    return {
        "message": "Block broadcast attempted.",
        "block": block.to_dict(),
        "broadcast": broadcast_result,
    }

@app.post("/add_transaction")
@api_limit(TRANSACTION_RATE_LIMIT)  # ✅ Keep rate limiting
async def add_transaction(
    request: Request,  # ✅ Required for rate limiter
    sender: str, recipient: str, amount: float, private_key: str
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
async def get_wallets():
    """
    Retrieve all registered wallets (public & private keys for setup only).
    REMOVE PRIVATE KEYS BEFORE GOING LIVE.
    """
    try:
        return {
            "message": "Registered wallets retrieved successfully.",
            "wallets": [
                {
                    "public_key": key,
                    "private_key": blockchain.wallets[key].private_key  # ✅ TEMPORARILY include private keys
                }
                for key in blockchain.wallets.keys()
            ]
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/transaction_pool")
async def transaction_pool():
    """Retrieve the current transaction pool."""
    return {"pending_transactions": blockchain.get_transaction_pool()}

@app.post("/submit_content")
@api_limit(SUBMISSION_RATE_LIMIT)
async def submit_content(
    request: Request,
    image: UploadFile,
    submitter: str = Form(...),
    text_content: str = Form(None),
):
    """Submit meme content for review without minting a blockchain block."""
    if not is_valid_public_key(submitter, blockchain.wallets):
        raise HTTPException(status_code=400, detail="Invalid submitter public key.")

    if not is_valid_image(image):
        raise HTTPException(status_code=400, detail="Invalid image format. Allowed formats: jpg, jpeg, png, webp")

    os.makedirs(SUBMISSIONS_DIR, exist_ok=True)
    image_path = os.path.join(SUBMISSIONS_DIR, image.filename)
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
async def get_submissions(status: str | None = None):
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
async def get_submission(submission_id: str):
    submission = blockchain.get_submission(submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail=f"Submission not found: {submission_id}")
    return {"submission": submission.to_dict()}


@app.get("/submissions/{submission_id}/certificate")
async def get_submission_certificate(submission_id: str):
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
async def get_certificate(certificate_id: str):
    certificate = blockchain.get_originality_certificate(certificate_id)
    if not certificate:
        raise HTTPException(
            status_code=404,
            detail=f"Originality certificate not found: {certificate_id}",
        )
    return {"certificate": certificate.to_dict()}


@app.post("/submissions/{submission_id}/broadcast")
async def broadcast_submission(submission_id: str):
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
@api_limit(VOTE_RATE_LIMIT)
async def vote_on_submission(
    request: Request,
    submission_id: str,
    voter: str = Form(...),
    vote_type: str = Form(...),
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
async def get_submission_votes(submission_id: str):
    try:
        return blockchain.get_submission_votes(submission_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/submissions/{submission_id}/votes/broadcast")
async def broadcast_submission_votes(submission_id: str):
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
async def evaluate_submission(
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
        if submission.status == APPROVED:
            queued_submission = blockchain.add_to_mint_queue(submission_id)
        blockchain.save_blockchain()
        certificate = blockchain.get_originality_certificate_for_submission(submission_id)
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
    }

@app.post("/add_block")
@api_limit(ADD_BLOCK_RATE_LIMIT)  # ✅ Keep rate limiting
async def add_block(
    request: Request,  # ✅ Required for rate limiting
    image: UploadFile,
    miner: str = Form(...),
    private_key: str = Form(...)  # ✅ Validate miner via wallet key
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
    print(f"Debug: Checking blockchain owner wallet... {getattr(blockchain, 'owner_wallet', 'NOT SET')}")
    print(f"Debug: Owner balance before block: {getattr(blockchain, 'owner_balance', 'NOT SET')}")

    # Validate image format
    if not is_valid_image(image):
        raise HTTPException(status_code=400, detail="Invalid image format. Allowed formats: jpg, jpeg, png, webp")

    try:
        # Create the temp directory if it doesn't exist
        os.makedirs("temp", exist_ok=True)

        # Save the uploaded image
        image_path = f"temp/{image.filename}"
        with open(image_path, "wb") as buffer:
            buffer.write(await image.read())

        # Debug: Check if the file exists
        if not os.path.isfile(image_path):
            print(f"Debug: File {image_path} does not exist after saving.")
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
        print(f"Debug: Unexpected Error in add_block: {e}")  # ✅ Print error for debugging
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/generate_wallet", summary="Generate a new wallet", description="Creates a new wallet.")
@api_limit(WALLET_GENERATION_RATE_LIMIT)  # ✅ Keep rate limiting in production
async def generate_wallet(request: Request):  # ✅ No more API key validation
    """
    Generate a new wallet.
    """
    wallet = Wallet()
    blockchain.wallets[wallet.public_key] = wallet  # Register the wallet in the blockchain

    # Debug: Confirm wallet registration
    print(f"Debug: Wallet registered with public key: {wallet.public_key}")
    blockchain.save_blockchain()

    return {"message": "Wallet generated successfully.", "wallet": wallet.get_keys()}

@app.get("/get_balance")
async def get_balance(public_key: str):
    """
    Retrieve the balance for a specific wallet.
    """
    try:
        if public_key not in blockchain.wallets:
            return JSONResponse(status_code=400, content={"error": f"Public key {public_key} is not registered in the blockchain."})

        balance = blockchain.get_balance(public_key)
        print(f"Debug: Returning balance for {public_key}: {balance}")

        return {"message": "Balance retrieved successfully.", "balance": balance}
    except Exception as e:
        print(f"Debug: ERROR retrieving balance - {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/get_reward_pool_balance")
async def get_reward_pool_balance():
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
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/active-users")
async def active_users():
    return {
        "active_users": blockchain.get_active_users(),
        "lookback_days": ACTIVE_USER_LOOKBACK_DAYS,
    }

@app.get("/voting-threshold")
async def voting_threshold():
    return blockchain.get_voting_threshold()

@app.get("/mint-queue")
async def mint_queue():
    if sync_approved_submissions_to_mint_queue():
        blockchain.save_blockchain()
    return {"mint_queue": blockchain.get_mint_queue()}


@app.post("/mint-queue/{submission_id}/mint")
async def mint_queued_submission(
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
    broadcast_result = (
        broadcast_block_to_peers(
            block=latest_block,
            peer_store=peer_store,
            origin_node_id=NODE_ID,
            network_name=NETWORK_NAME,
            related_submission_id=submission_id,
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
