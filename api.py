import os
import time
import logging
from fastapi import FastAPI, UploadFile, Form, HTTPException, Depends, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware

from blockchain import Blockchain
from wallet import Wallet
from transaction import Transaction
from utils import extract_text
from validators import is_valid_public_key, is_valid_amount, is_valid_image
from config import ACTIVE_USER_LOOKBACK_DAYS, COIN_NAME
from auth import validate_api_key  # ✅ API authentication

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
    allow_origins=["http://localhost:5173", "https://zoidbergcoin.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Initialize the rate limiter
limiter = Limiter(key_func=get_remote_address)
app.add_middleware(SlowAPIMiddleware)

# ✅ Exclude FastAPI Docs from rate limiting
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

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
if os.path.exists("blockchain.json"):
    print("✅ Debug: Loading existing blockchain from blockchain.json...")
    blockchain = Blockchain()  # ✅ Ensures it loads correctly
else:
    print("⚠️ Debug: No blockchain file found. Creating new blockchain...")
    blockchain = Blockchain(project_owner, contributor1, contributor2)  # ✅ Only creates new if no file exists

@app.post("/reset_blockchain")
async def reset_blockchain():
    """Reset blockchain to Genesis state."""
    try:
        if os.path.exists("blockchain.json"):
            os.remove("blockchain.json")  # ✅ Delete previous blockchain state

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

@app.get("/chain")
async def get_chain():
    """Retrieve the blockchain."""
    return {"chain": blockchain.get_chain()}

@app.post("/add_transaction")
@limiter.limit("5/minute")  # ✅ Keep rate limiting
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
@limiter.limit("5/minute")
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
        raise HTTPException(status_code=400, detail="Invalid image format. Allowed formats: jpg")

    os.makedirs("temp/submissions", exist_ok=True)
    image_path = f"temp/submissions/{image.filename}"
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

    return {"message": "Content submitted successfully.", "submission": submission.to_dict()}

@app.post("/submissions/{submission_id}/vote")
@limiter.limit("10/minute")
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

    return {"message": "Vote recorded successfully.", "vote": vote}

@app.get("/submissions/{submission_id}/votes")
async def get_submission_votes(submission_id: str):
    try:
        return blockchain.get_submission_votes(submission_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.post("/add_block")
@limiter.limit("3/minute")  # ✅ Keep rate limiting
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
        raise HTTPException(status_code=400, detail="Invalid image format. Allowed formats: jpg")

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
        new_block = blockchain.add_block(
            image_path=image_path,
            text_content=text_content,
            miner=miner,
            validate_meme=True  # ✅ Skip validation in add_block since it was done here
        )

        # Remove the temporary image file
        os.remove(image_path)

        return {"message": "Block added successfully.", "block": new_block}
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        print(f"Debug: Unexpected Error in add_block: {e}")  # ✅ Print error for debugging
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/generate_wallet", summary="Generate a new wallet", description="Creates a new wallet.")
@limiter.limit("2/minute")  # ✅ Keep rate limiting (2 requests per minute)
async def generate_wallet(request: Request):  # ✅ No more API key validation
    """
    Generate a new wallet.
    """
    wallet = Wallet()
    blockchain.wallets[wallet.public_key] = wallet  # Register the wallet in the blockchain

    # Debug: Confirm wallet registration
    print(f"Debug: Wallet registered with public key: {wallet.public_key}")

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
