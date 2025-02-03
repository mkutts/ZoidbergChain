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
from auth import validate_api_key  # ✅ API authentication

logging.basicConfig(
    filename="api.log",  # Save logs to a file
    level=logging.INFO,  # Set log level to INFO
    format="%(asctime)s - %(levelname)s - %(message)s",
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Allow Vue frontend
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
    pdf_path = os.path.join("static", "ZoidbergCoin_WhitePaper.pdf")
    if os.path.exists(pdf_path):
        return FileResponse(pdf_path, filename="ZoidbergCoin_WhitePaper.pdf", media_type="application/pdf")
    return JSONResponse(status_code=404, content={"error": "White paper not found."})


# Initialize blockchain
wallet1 = Wallet()
wallet2 = Wallet()
meme_creator = Wallet()
blockchain = Blockchain(wallet1=wallet1, wallet2=wallet2, meme_creator=meme_creator)

@app.get("/sync")
async def sync_blockchain():
    """Returns the latest blockchain state for syncing with other nodes."""
    return {"chain": blockchain.get_chain()}

@app.get("/chain")
async def get_chain():
    """Retrieve the blockchain."""
    return {"chain": blockchain.get_chain()}

@app.post("/add_transaction")
@limiter.limit("5/minute")  # ✅ Limit to 5 requests per minute
async def add_transaction(
    request: Request,  # ✅ Required for rate limiter
    sender: str, recipient: str, amount: float, private_key: str,
    user_role: str = Depends(validate_api_key)  # ✅ Require API key
):
    """Add a transaction to the blockchain."""
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

@app.get("/get_wallets")
async def get_wallets():
    """
    Retrieve all registered wallets.
    """
    try:
        return {
            "message": "Registered wallets retrieved successfully.",
            "wallets": [
                {"public_key": key, "private_key": wallet.private_key}
                for key, wallet in blockchain.wallets.items()
            ]
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/transaction_pool")
async def transaction_pool():
    """Retrieve the current transaction pool."""
    return {"pending_transactions": blockchain.get_transaction_pool()}

@app.post("/add_block")
@limiter.limit("3/minute")  # ✅ Limit to 3 requests per minute
async def add_block(
    request: Request,  # ✅ Required for rate limite
    image: UploadFile, miner: str = Form(...),
    user_role: str = Depends(validate_api_key)  # ✅ Require API key
):
    """
    Add a new block to the blockchain with the given meme image and transactions.
    """

    # Validate miner's public key
    if not is_valid_public_key(miner, blockchain.wallets):
        raise HTTPException(status_code=400, detail="Invalid miner public key.")

    # Validate image format
    if not is_valid_image(image):
        raise HTTPException(status_code=400, detail="Invalid image format. Allowed formats: jpg, jpeg, png.")

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

        # Add a new block
        new_block = blockchain.add_block(
            image_path=image_path,
            text_content=text_content,
            miner=miner,
            validate_meme=False  # Skip validation in add_block since it was done here
        )

        # Remove the temporary image file
        os.remove(image_path)

        return {"message": "Block added successfully.", "block": new_block}
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/generate_wallet", summary="Generate a new wallet", description="Requires an API key.")
@limiter.limit("2/minute")  # ✅ Limit to 2 requests per minute
async def generate_wallet(
    request: Request,  # ✅ Required for rate limiter
    user_role: str = Depends(validate_api_key)  # ✅ Require API key
):
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
    
    Args:
        public_key (str): The public key of the wallet.

    Returns:
        dict: The wallet's balance or an error message.
    """
    try:
        # Ensure the public key is valid
        if public_key not in blockchain.wallets:
            return JSONResponse(
                status_code=400,
                content={"error": f"Public key {public_key} is not registered in the blockchain."}
            )

        # Calculate the wallet balance
        balance = blockchain.get_balance(public_key)

        return {
            "message": f"Balance retrieved successfully for wallet {public_key}.",
            "balance": balance
        }
    except Exception as e:
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
