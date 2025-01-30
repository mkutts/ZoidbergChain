import os
from fastapi import FastAPI, UploadFile, Form, HTTPException
from blockchain import Blockchain
from wallet import Wallet
from transaction import Transaction
from fastapi.responses import JSONResponse
from utils import extract_text
from validators import is_valid_public_key, is_valid_amount
from validators import is_valid_image, is_valid_public_key

app = FastAPI()

# Initialize blockchain
wallet1 = Wallet()
wallet2 = Wallet()
meme_creator = Wallet()
blockchain = Blockchain(wallet1=wallet1, wallet2=wallet2, meme_creator=meme_creator)

@app.get("/chain")
async def get_chain():
    """Retrieve the blockchain."""
    return {"chain": blockchain.get_chain()}

@app.post("/add_transaction")
async def add_transaction(sender: str, recipient: str, amount: float, private_key: str):
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
async def add_block(image: UploadFile, miner: str = Form(...)):
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

@app.post("/generate_wallet")
async def generate_wallet():
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
