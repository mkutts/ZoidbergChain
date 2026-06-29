# Import statements
import os
import hashlib
import time
import ecdsa
import base64
import re
from PIL import Image
import imagehash
from sentence_transformers import SentenceTransformer
from concurrent.futures import ThreadPoolExecutor
import random
import pytesseract
from config import COIN_NAME, MEME_BLOCK_REWARD, REWARD_POOL_SUPPLY

# Load the pre-trained model for text similarity
model = SentenceTransformer('all-MiniLM-L6-v2')


class Wallet:
    def __init__(self, private_key=None):
        if private_key:
            self.private_key = private_key
            self.public_key = self.generate_public_key()
        else:
            self.private_key, self.public_key = self.generate_key_pair()

    @staticmethod
    def generate_key_pair():
        sk = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)
        private_key = sk.to_string().hex()
        public_key = sk.verifying_key.to_string().hex()
        return private_key, public_key

    def generate_public_key(self):
        sk = ecdsa.SigningKey.from_string(bytes.fromhex(self.private_key), curve=ecdsa.SECP256k1)
        return sk.verifying_key.to_string().hex()
    
    def add_wallet(self, wallet):
        """Add a new wallet to the blockchain's wallet list."""
        self.wallets[wallet.public_key] = wallet
        print(f"Debug: Wallet added to blockchain - Public Key: {wallet.public_key}")

    def get_keys(self):
        """Return the private and public keys."""
        return {
            "private_key": self.private_key,
            "public_key": self.public_key,
        }

    def __str__(self):
        return f"Wallet(Public Key: {self.public_key}, Private Key: {self.private_key})"


class Transaction:
    def __init__(self, sender, recipient, amount, tip=0, payload_size_kb=0):
        self.sender = sender
        self.recipient = recipient
        self.amount = amount
        self.tip = tip  # Tip amount
        self.payload_size_kb = payload_size_kb
        self.signature = None

    def to_dict(self):
        """Convert transaction to a dictionary."""
        return {
            "sender": self.sender,
            "recipient": self.recipient,
            "amount": self.amount,
            "tip": self.tip,
            "signature": self.signature,
            "payload_size_kb": self.payload_size_kb,
        }

    def calculate_fee(self):
        """Calculate the total transaction fee based on payload size."""
        base_fee = 0.01  # Base fee
        additional_fee = 0.001 * self.payload_size_kb  # 0.001 coin per KB
        return base_fee + additional_fee

    def sign_transaction(self, private_key):
        if self.sender == "GENESIS" or self.sender == "REWARD_POOL":
            print("Debug: Skipping signing for GENESIS or REWARD_POOL transaction.")
            return  # Skip signing for special transactions

        if not private_key:
            raise Exception("No private key provided for signing!")

        # Create transaction data string for signing
        transaction_data = f"{self.sender}{self.recipient}{self.amount}{self.tip}"
        print(f"Debug: Signing transaction data: {transaction_data}")

        try:
            # Attempt to sign the transaction
            sk = ecdsa.SigningKey.from_string(bytes.fromhex(private_key), curve=ecdsa.SECP256k1)
            self.signature = base64.b64encode(sk.sign(transaction_data.encode())).decode()
            print(f"Debug: Transaction signed with signature: {self.signature}")
        except Exception as e:
            # Log any errors during the signing process
            print(f"Debug: Error during signing - {e}")
            raise Exception(f"Failed to sign transaction: {e}")


    def is_valid(self):
        try:
            if self.sender == "GENESIS" or self.sender == "REWARD_POOL":
                print("Debug: Skipping validation for GENESIS or REWARD_POOL transaction.")
                return True  # Skip validation for special transactions

            if not self.signature:
                raise Exception("Transaction signature is missing.")

            # Validate transaction data against the signature
            transaction_data = f"{self.sender}{self.recipient}{self.amount}{self.tip}"
            print(f"Debug: Validating transaction data: {transaction_data}")
            print(f"Debug: Signature: {self.signature}")

            vk = ecdsa.VerifyingKey.from_string(bytes.fromhex(self.sender), curve=ecdsa.SECP256k1)
            vk.verify(base64.b64decode(self.signature), transaction_data.encode())
            print("Debug: Transaction is valid.")
            return True
        except ecdsa.BadSignatureError:
            # Specific handling for invalid signature
            print("Debug: Invalid signature detected.")
            return False
        except Exception as e:
            # General exception handling
            print(f"Debug: Transaction is not valid - {e}")
            return False

class Block:
    def __init__(self, index, previous_hash, timestamp, transactions, miner, meme=None, hash=None):
        self.index = index
        self.previous_hash = previous_hash
        self.timestamp = timestamp
        self.transactions = transactions
        self.miner = miner
        self.meme = meme or "default-meme"
        self.hash = hash or self.calculate_hash()

    def to_dict(self):
        """Convert block to a dictionary."""
        return {
            "index": self.index,
            "transactions": [tx.to_dict() for tx in self.transactions],
            "previous_hash": self.previous_hash,
            "miner": self.miner,
            "meme": self.meme,  # Include encoded meme data
            "timestamp": self.timestamp,
        }

    def calculate_hash(self):
        """Calculate the hash of the block."""
        transaction_data = "".join(
            [f"{tx.sender}{tx.recipient}{tx.amount}{tx.tip}{tx.payload_size_kb}{tx.signature}" for tx in self.transactions]
        )
        block_string = f"{self.index}{self.previous_hash}{self.timestamp}{transaction_data}{self.meme}{self.miner}"
        return hashlib.sha256(block_string.encode()).hexdigest()

class Blockchain:
    def __init__(self, wallet1=None, wallet2=None, meme_creator=None):
        self.chain = []  # The blockchain
        self.pending_transactions = []  # Transaction pool
        self.wallets = {}  # Registered wallets
        self.text_validation_cache = {}  # Cache for validated texts
        self.image_validation_cache = {}  # Cache for validated images
        self.texts = []  # List of all validated text content
        self.image_hashes = set()  # Set to store unique image hashes
        self.reward_pool = REWARD_POOL_SUPPLY  # Initial reward pool
        self.initial_reward_pool = self.reward_pool  # Set the initial reward pool value

        self.initial_reward_pool = REWARD_POOL_SUPPLY
        self.reward_pool = self.initial_reward_pool  # Set initial reward pool balance

        # Save wallets if provided
        if wallet1:
            self.wallets[wallet1.public_key] = wallet1
        if wallet2:
            self.wallets[wallet2.public_key] = wallet2
        if meme_creator:
            self.wallets[meme_creator.public_key] = meme_creator

        # Create the Genesis block
        self.create_genesis_block(wallet1, wallet2, meme_creator)

    def create_genesis_block(self, wallet1, wallet2, meme_creator):
        """Create the Genesis block with initial transactions and optional encoded meme."""
        genesis_transactions = []

        # Create initial transactions to fund wallets
        if wallet1:
            genesis_transactions.append(
                Transaction(sender="GENESIS", recipient=wallet1.public_key, amount=100)
            )
        if wallet2:
            genesis_transactions.append(
                Transaction(sender="GENESIS", recipient=wallet2.public_key, amount=100)
            )
        if meme_creator:
            genesis_transactions.append(
                Transaction(sender="GENESIS", recipient=meme_creator.public_key, amount=100)
            )

        # Create the genesis block with transactions
        genesis_block = Block(
            index=0,
            previous_hash="0",
            timestamp=time.time(),
            transactions=genesis_transactions,
            miner="GENESIS",
            meme={"encoded_image": "default"}  # Default meme for Genesis block
        )
        self.chain.append(genesis_block)

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
        return self.wallets.get(public_key)

    def calculate_transaction_fee(self, payload_size_kb):
        """Calculate the transaction fee based on payload size."""
        base_fee = 0.01  # Base fee for up to 1 KB
        scaling_factor = 0.01  # Fee per additional KB
        return base_fee + (scaling_factor * max(0, payload_size_kb - 1))
    
    def distribute_transaction_fee(self, transaction, miner):
        """Distribute the transaction fee between the miner and reward pool."""
        payload_size_kb = len(str(transaction)) / 1024  # Approximate payload size in KB
        total_fee = self.calculate_transaction_fee(payload_size_kb)

        miner_share = total_fee * 0.7
        reward_pool_share = total_fee * 0.3

        self.reward_pool += reward_pool_share

        print(f"Debug: Transaction Fee Distribution - Total Fee: {total_fee:.4f}, "
              f"Miner Share: {miner_share:.4f}, Reward Pool Share: {reward_pool_share:.4f}")

        return miner_share

    def hash_image(self, image_path):
        """Generate a perceptual hash for an image."""
        try:
            print(f"Debug: Hashing image at path: {image_path}")

            # Check if the file exists
            if not os.path.isfile(image_path):
                print(f"Error: File does not exist at {image_path}")
                raise ValueError("Invalid image path provided for the meme.")

            img = Image.open(image_path)
            return str(imagehash.average_hash(img))  # Convert hash to string for storage and comparison
        except Exception as e:
            print(f"Error in hash_image: {e}")
            raise ValueError("Invalid image path provided for the meme.")


    def is_image_unique(self, image_path):
        """Check if the image is unique with caching."""
        if image_path in self.image_validation_cache:
            new_hash = self.image_validation_cache[image_path]
            print(f"Debug: Cache hit for image hash computation: {new_hash}")
        else:
            new_hash = self.hash_image(image_path)
            self.image_validation_cache[image_path] = new_hash
            print(f"Debug: Computed and cached image hash: {new_hash}")

        print(f"Debug: Checking uniqueness for image hash: {new_hash}")
        print(f"Debug: Current image hashes: {self.image_hashes}")

        if new_hash in self.image_hashes:
            print(f"Debug: Image hash {new_hash} is NOT unique (cached).")
            return False

        print(f"Debug: Image hash {new_hash} is unique.")
        self.image_hashes.add(new_hash)
        return True

    def extract_text(self, image_path):
        """Extract text from an image using pytesseract and clean it."""
        try:
            img = Image.open(image_path)

            # Use Tesseract to extract text
            raw_text = pytesseract.image_to_string(img, config="--psm 11")
            print(f"Raw Extracted Text: {raw_text}")  # Debug output

            # Clean the text: remove newlines, extra spaces, and unusual characters
            cleaned_text = re.sub(r'\s+', ' ', raw_text)  # Replace newlines and extra spaces with a single space
            cleaned_text = re.sub(r'[^\w\s]', '', cleaned_text)  # Remove non-alphanumeric characters except spaces
            cleaned_text = cleaned_text.strip()  # Remove leading/trailing whitespace

            print(f"Cleaned Text: {cleaned_text}")  # Debug output
            return cleaned_text
        except Exception as e:
            print(f"Error extracting text: {e}")
            return None

    def is_text_unique(self, text_content):
        """Check if the text is unique with caching."""
        normalized_text = re.sub(r'[^\w\s]', '', text_content).strip().lower()
        print(f"Debug: Checking text: '{text_content}' (normalized: '{normalized_text}')")

        if normalized_text in self.text_validation_cache:
            print(f"Debug: Cache hit for text uniqueness: {normalized_text}")
            return self.text_validation_cache[normalized_text]

        if normalized_text in self.texts:
            print(f"Debug: Text '{normalized_text}' is NOT unique.")
            self.text_validation_cache[normalized_text] = False
            return False

        print(f"Debug: Text '{normalized_text}' is unique.")
        self.text_validation_cache[normalized_text] = True
        self.texts.append(normalized_text)
        return True

    def is_meme_original(self, image_path, text_content):
        """Validate meme originality without caching."""
        print(f"Debug: Validating meme originality for image: {image_path} and text: '{text_content}'")

        # Validate image hash uniqueness
        image_hash = self.hash_image(image_path)
        print(f"Debug: Image hash: {image_hash}")
        if image_hash in self.image_hashes:
            print("Debug: Image is not unique.")
            return False

        # Validate text uniqueness
        if not self.is_text_unique(text_content):
            print("Debug: Text is not unique.")
            return False

        print("Debug: Meme is original.")
        return True

    def add_block(self, image_path, text_content, miner, max_block_size_kb=10, propagation_delay=0, validate_meme=True):
        """Add a block with transaction fee and tip distribution, enforce block size limit, and cache memes after validation."""
        if not os.path.isfile(image_path):
            raise ValueError("Invalid image path provided for the meme.")

        # Validate the miner's public key
        if not self.is_valid_public_key(miner):
            raise ValueError(f"Invalid public key provided for the miner: {miner}")

        # Encode the image as base64
        meme_encoded = self.encode_image(image_path)

        # Skip validation if already performed
        if validate_meme and not self.is_meme_original(image_path, text_content):
            print("Error: Meme must be original to validate the block!")
            return False

        # Validate transactions and calculate total fees/tips
        valid_transactions = []
        total_size = 0
        total_miner_fees = 0

        print("Debug: Validating transactions concurrently...")
        with ThreadPoolExecutor() as executor:
            future_to_tx = {executor.submit(self.validate_transaction, tx): tx for tx in self.pending_transactions}
            for future in future_to_tx:
                tx = future_to_tx[future]
                try:
                    if future.result():
                        tx_fee = tx.calculate_fee()
                        tip = tx.tip

                        # Reward pool split
                        if self.reward_pool < (self.initial_reward_pool * 0.25):
                            fee_split = {"miner": 0.5, "reward_pool": 0.5}
                            tip_split = {"miner": 0.25, "reward_pool": 0.75}
                        else:
                            fee_split = {"miner": 0.7, "reward_pool": 0.3}
                            tip_split = {"miner": 0.5, "reward_pool": 0.5}

                        miner_share = (tx_fee * fee_split["miner"]) + (tip * tip_split["miner"])
                        reward_pool_share = (tx_fee * fee_split["reward_pool"]) + (tip * tip_split["reward_pool"])

                        self.reward_pool += reward_pool_share
                        total_miner_fees += miner_share

                        tx_size = len(str(tx))
                        valid_transactions.append(tx)
                        total_size += tx_size
                except Exception as e:
                    print(f"Debug: Transaction validation error: {e}")

        # Enforce block size limit
        while total_size > (max_block_size_kb * 1024):
            removed_tx = valid_transactions.pop()
            total_size -= len(str(removed_tx))
            print(f"Debug: Removed transaction to reduce size. New total size: {total_size / 1024:.2f} KB")

        print(f"Debug: Final block size: {total_size / 1024:.2f} KB")

        # Add mining reward
        mining_reward = MEME_BLOCK_REWARD
        if self.reward_pool < mining_reward:
            print("Error: Insufficient funds in the reward pool.")
            return False

        reward_transaction = Transaction("REWARD_POOL", miner, mining_reward)
        self.reward_pool -= mining_reward

        # Create the new block
        latest_block = self.get_latest_block()
        new_block = Block(
            index=latest_block.index + 1,
            previous_hash=latest_block.hash,
            timestamp=time.time(),
            transactions=[reward_transaction] + valid_transactions,
            meme={"encoded_image": meme_encoded, "text": text_content},
            miner=miner,
        )
        self.chain.append(new_block)
        self.pending_transactions = [tx for tx in self.pending_transactions if tx not in valid_transactions]

        # Cache meme data after block is added
        image_hash = self.hash_image(image_path)
        self.image_hashes.add(image_hash)
        self.text_validation_cache[text_content] = True

        print(f"Block {new_block.index} added with meme: {text_content}. Final size: {total_size / 1024:.2f} KB.")
        print(f"Miner earned: {total_miner_fees:.4f} {COIN_NAME}.")
        return True

    def get_latest_block(self):
        return self.chain[-1]

    def is_chain_valid(self, chain):
        """Validate a given chain."""
        for i in range(1, len(chain)):
            current_block = chain[i]
            previous_block = chain[i - 1]

            # Validate the hash of the block
            if current_block["hash"] != self.calculate_hash_from_dict(current_block):
                print(f"Debug: Block {current_block['index']} hash is invalid!")
                return False

            # Validate the previous hash link
            if current_block["previous_hash"] != previous_block["hash"]:
                print(f"Debug: Block {current_block['index']} previous hash does not match!")
                return False

        return True

    def get_balance(self, public_key):
        balance = 0
        for block in self.chain:
            for transaction in block.transactions:
                if transaction.sender == public_key:
                    balance -= transaction.amount + transaction.tip
                if transaction.recipient == public_key:
                    balance += transaction.amount + transaction.tip
        return balance

    def add_transaction(self, transaction, fee=1):
        try:
            print(f"Debug: Validating transaction from {transaction.sender} to {transaction.recipient} for {transaction.amount} + tip {transaction.tip} + fee {fee}")
            if not transaction.is_valid():
                raise Exception("Invalid transaction: Signature is not valid.")

            sender_balance = self.get_balance(transaction.sender)
            total_deduction = transaction.amount + transaction.tip + fee
            print(f"Debug: Sender balance: {sender_balance}, Total Deduction: {total_deduction}")

            if sender_balance < total_deduction:
                raise Exception("Insufficient balance to cover the transaction, tip, and fee.")

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
        """Validates a single transaction."""
        try:
            if transaction.is_valid():
                return True
        except Exception as e:
            print(f"Debug: Transaction validation failed - {e}")
        return False
    
    def get_chain_as_dict(self):
        """Return the blockchain as a list of dictionaries."""
        return [block.__dict__ for block in self.chain]
    
    def replace_chain(self, new_chain):
        """Replace the current chain with a new one if it is longer and valid."""
        if len(new_chain) > len(self.chain) and self.is_chain_valid(new_chain):
            self.chain = new_chain
            print("Debug: Replaced local chain with the received chain.")
            return True
        print("Debug: Received chain is invalid or not longer.")
        return False
    
    def calculate_hash_from_dict(self, block_dict):
        """Calculate the hash for a block dictionary."""
        transaction_data = "".join(
            [f"{tx['sender']}{tx['recipient']}{tx['amount']}{tx['tip']}{tx['payload_size_kb']}{tx['signature']}" for tx in block_dict["transactions"]]
        )
        block_string = f"{block_dict['index']}{block_dict['previous_hash']}{block_dict['timestamp']}{transaction_data}{block_dict['meme']}{block_dict['miner']}"
        return hashlib.sha256(block_string.encode()).hexdigest()
    
    def is_valid_public_key(self, public_key):
        """Check if the given public key is valid."""
        if public_key in self.wallets:
            return True
        print(f"Debug: Invalid public key: {public_key}")
        return False

