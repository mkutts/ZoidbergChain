import os
from fastapi import FastAPI, UploadFile, Form
from zoidbergCoin import Blockchain, Wallet, Transaction
from fastapi.responses import JSONResponse

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
    """Add a transaction to the blockchain."""
    tx = Transaction(sender, recipient, amount)
    try:
        # Sign the transaction
        tx.sign_transaction(private_key)

        # Add to blockchain
        blockchain.add_transaction(tx)
        return {"message": "Transaction added successfully"}
    except Exception as e:
        return {"error": str(e)}

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

@app.post("/submit_meme")
async def submit_meme(image: UploadFile):
    """
    Accept a meme image, extract its text, and check its uniqueness.
    """
    try:
        os.makedirs("temp", exist_ok=True)
        image_path = f"temp/{image.filename}"
        with open(image_path, "wb") as buffer:
            buffer.write(await image.read())

        # Extract text from the image
        extracted_text = blockchain.extract_text(image_path)

        # If no text is found, return an error
        if not extracted_text:
            os.remove(image_path)
            return JSONResponse(status_code=400, content={"error": "No text found in the image."})

        # Check text uniqueness
        text_is_unique = blockchain.is_text_unique(extracted_text)

        # Hash the image
        image_hash = blockchain.hash_image(image_path)

        # Remove the temporary image file
        os.remove(image_path)

        # Return results
        return {
            "image_hash": image_hash,
            "extracted_text": extracted_text,
            "text_is_unique": text_is_unique
        }

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/add_block")
async def add_block(image: UploadFile, miner: str = Form(...)):
    """
    Add a new block to the blockchain with the given meme image and transactions.
    """
    try:
        # Save the uploaded image temporarily
        os.makedirs("temp", exist_ok=True)
        image_path = f"temp/{image.filename}"
        with open(image_path, "wb") as buffer:
            buffer.write(await image.read())

        # Encode the meme as base64
        meme_encoded = blockchain.encode_image(image_path)

        # Extract text content from the image
        text_content = blockchain.extract_text(image_path)
        if not text_content:
            os.remove(image_path)
            return JSONResponse(status_code=400, content={"error": "No text found in the image."})

        # Validate the meme for originality
        if not blockchain.is_meme_original(image_path, text_content):
            os.remove(image_path)
            return JSONResponse(status_code=400, content={"error": "Meme is not original."})

        # Add a new block with the validated meme
        new_block = blockchain.add_block(
            image_path=image_path,
            text_content=text_content,
            miner=miner,
            validate_meme=False  # Skip validation inside add_block
        )

        # Remove the temporary image file
        os.remove(image_path)

        return {
            "message": "Block added successfully.",
            "block": new_block
        }
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/generate_wallet")
async def generate_wallet():
    """
    Generate a new wallet, register it in the blockchain, and return its public and private keys.
    """
    try:
        # Create a new wallet
        wallet = Wallet()

        # Register the wallet in the blockchain
        blockchain.wallets[wallet.public_key] = wallet

        # Return the wallet's keys
        return {
            "message": "Wallet generated and registered successfully.",
            "wallet": wallet.get_keys()
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

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
