# Import statements
import os
import hashlib
import time
import base64
import re
from PIL import Image
import imagehash
from concurrent.futures import ThreadPoolExecutor
import pytesseract
import time
from block import Block
from transaction import Transaction
from wallet import Wallet
from utils import hash_image
from utils import extract_text


class Blockchain:
    def __init__(self, project_owner_wallet=None, Contributor_one=None, Contributor_two=None, initial_supply=1000000000):
        self.chain = []  # The blockchain
        self.pending_transactions = []  # Transaction pool
        self.wallets = {}  # Registered wallets
        self.text_validation_cache = {}  # Cache for validated texts
        self.image_validation_cache = {}  # Cache for validated images
        self.texts = []  # List of all validated text content
        self.image_hashes = set()  # Set to store unique image hashes
        self.reward_pool = initial_supply * 0.1  # Initial reward pool
        self.initial_reward_pool = self.reward_pool  # Set the initial reward pool value

        if project_owner_wallet:
            self.wallets[project_owner_wallet.public_key] = project_owner_wallet  # ✅ Store like other wallets

        # ✅ Set Contributor Wallets
        if Contributor_one:
            self.wallets[Contributor_one.public_key] = Contributor_one
        if Contributor_two:
            self.wallets[Contributor_two.public_key] = Contributor_two

        # ✅ Create the Genesis Block
        self.create_genesis_block(project_owner_wallet, Contributor_one, Contributor_two)

    def create_genesis_block(self, project_owner_wallet, Contributor_one, Contributor_two, initial_supply=1000000000):
        """Create the Genesis block with initial transactions and optional encoded meme."""
        genesis_transactions = []

        # Create initial transactions to fund wallets
        if project_owner_wallet:
            genesis_transactions.append(
                Transaction(sender="GENESIS", recipient=project_owner_wallet.public_key, amount=initial_supply * 0.79)
            )

        if Contributor_one:
            genesis_transactions.append(
                Transaction(sender="GENESIS", recipient=Contributor_one.public_key, amount=initial_supply * 0.10)
            )

        if Contributor_two:
            genesis_transactions.append(
                Transaction(sender="GENESIS", recipient=Contributor_two.public_key, amount=initial_supply * 0.01)
            )

        # Create the genesis block with transactions
        genesis_block = Block(
            index=0,
            previous_hash="0",
            timestamp=time.time(),
            transactions=genesis_transactions,
            miner="GENESIS",
            meme={"encoded_image": "default"}
        )
        self.chain.append(genesis_block)

        # ✅ Securely print the wallet details ONCE (store securely)
        print("\n🔐 **Genesis Wallets (Store These Securely!)** 🔐")
        if project_owner_wallet:
            print(f"📌 Project Owner Wallet:\n   - Public Key: {project_owner_wallet.public_key}\n   - Private Key: {project_owner_wallet.private_key}")
        if Contributor_one:
            print(f"📌 Contributor One:\n   - Public Key: {Contributor_one.public_key}\n   - Private Key: {Contributor_one.private_key}")
        if Contributor_two:
            print(f"📌 Contributor Two:\n   - Public Key: {Contributor_two.public_key}\n   - Private Key: {Contributor_two.private_key}")
        print("\n🚨 **Secure these keys immediately! They will NOT be shown again.** 🚨\n")


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

    def is_image_unique(self, image_path):
        """Check if the image is unique with caching."""
        if image_path in self.image_validation_cache:
            new_hash = self.image_validation_cache[image_path]
            print(f"Debug: Cache hit for image hash computation: {new_hash}")
        else:
            new_hash = hash_image(image_path)
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
        image_hash = hash_image(image_path)
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

    def add_block(self, image_path, text_content=None, miner=None, max_block_size_kb=10, validate_meme=True):
        """
        Add a block with tip distribution, enforce block size limit, and validate memes.
        """
        # Check if the image path is valid and the file exists
        if not os.path.isfile(image_path):
            print(f"Debug: Image path {image_path} does not exist.")
            raise ValueError("Invalid image path provided for the meme.")

        if not self.is_valid_public_key(miner):
            print(f"Debug: Invalid miner public key: {miner}")
            raise ValueError(f"Invalid public key provided for the miner.")

        # Extract text content if not provided
        if not text_content:
            print("Debug: Extracting text content from the image.")
            text_content = extract_text(image_path)
            if not text_content:
                print(f"Debug: No text extracted from image {image_path}.")
                raise ValueError("No text content could be extracted from the image.")

        # Encode the image as base64
        print(f"Debug: Encoding image at path {image_path}.")
        meme_encoded = self.encode_image(image_path)

        # Validate the meme if required
        if validate_meme and not self.is_meme_original(image_path, text_content):
            print(f"Debug: Meme validation failed for image {image_path}.")
            return False

        # Validate transactions and calculate total tips
        valid_transactions = []
        total_size = 0
        total_miner_tips = 0  # ✅ Only track miner’s tip earnings

        print("Debug: Validating transactions concurrently...")
        with ThreadPoolExecutor() as executor:
            future_to_tx = {executor.submit(self.validate_transaction, tx): tx for tx in self.pending_transactions}
            for future in future_to_tx:
                tx = future_to_tx[future]
                try:
                    if future.result():
                        tip = tx.tip  # ✅ Keep tip logic

                        # ✅ Tip Distribution (Existing Model)
                        if self.reward_pool < (self.initial_reward_pool * 0.25):
                            tip_split = {"miner": 0.25, "reward_pool": 0.75}
                        else:
                            tip_split = {"miner": 0.5, "reward_pool": 0.5}

                        miner_tip_share = tip * tip_split["miner"]
                        reward_pool_tip_share = tip * tip_split["reward_pool"]

                        # ✅ Add to balances
                        self.reward_pool += reward_pool_tip_share  # ✅ Only tips go to reward pool
                        total_miner_tips += miner_tip_share  # ✅ Miner gets tip only

                        # ✅ Debugging Output
                        print(f"Debug: Transaction Distribution - Tip Total: {tip:.4f}")
                        print(f"Debug: - Miner gets: {miner_tip_share:.4f}")
                        print(f"Debug: - Reward Pool gets: {reward_pool_tip_share:.4f}")

                        tx_size = len(str(tx))
                        valid_transactions.append(tx)
                        total_size += tx_size
                except Exception as e:
                    print(f"Debug: Transaction validation error: {e}")

        # ✅ Ensure miner’s balance is updated
        if miner in self.wallets:
            current_balance = self.get_balance(miner)  # ✅ Get miner's balance
            updated_balance = current_balance + total_miner_tips  # ✅ Add miner's earnings
            print(f"Debug: Before crediting miner {miner}: {current_balance:.4f} ZoidbergCoins")
            print(f"Debug: Miner earned: {total_miner_tips:.4f} ZoidbergCoins")

            # ✅ Store the updated balance at the blockchain level
            self.wallets[miner].stored_balance = updated_balance  # ✅ Store updated balance

            print(f"Debug: After crediting miner {miner}: {self.wallets[miner].stored_balance:.4f} ZoidbergCoins")
        else:
            print(f"Debug: WARNING! Miner {miner} not found in registered wallets. Initializing new wallet.")

            # ✅ Initialize the miner's wallet with the earned balance
            self.wallets[miner] = Wallet()
            self.wallets[miner].public_key = miner
            self.wallets[miner].private_key = None  # Miner’s private key is unknown
            self.wallets[miner].stored_balance = total_miner_tips  # ✅ Store the initial balance
            print(f"Debug: New miner wallet created for {miner} with balance: {total_miner_tips:.4f} ZoidbergCoins")

        # Enforce block size limit
        while total_size > (max_block_size_kb * 1024):
            removed_tx = valid_transactions.pop()
            total_size -= len(str(removed_tx))
            print(f"Debug: Removed transaction to reduce size. New total size: {total_size / 1024:.2f} KB")

        print(f"Debug: Final block size: {total_size / 1024:.2f} KB")

        # Add mining reward
        mining_reward = 5
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
        print(f"Debug: Caching meme data for image {image_path}.")
        image_hash = hash_image(image_path)
        self.image_hashes.add(image_hash)
        self.text_validation_cache[text_content] = True

        print(f"Block {new_block.index} added with meme: {text_content}. Final size: {total_size / 1024:.2f} KB.")
        print(f"Miner earned: {total_miner_tips:.4f} ZoidbergCoins.")
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
        """Calculate balance based on transaction history and tips (NO FEES)."""
        balance = 0
        for block in self.chain:
            for transaction in block.transactions:
                if transaction.sender == public_key:
                    balance -= transaction.amount + transaction.tip  # ✅ Deduct amount + tip (NO FEE)
                if transaction.recipient == public_key:
                    balance += transaction.amount + transaction.tip
        return balance

    def add_transaction(self, transaction):
        try:
            print(f"Debug: Validating transaction from {transaction.sender} to {transaction.recipient} "
                f"for {transaction.amount} + tip {transaction.tip}")

            if not transaction.is_valid():
                raise Exception("Invalid transaction: Signature is not valid.")

            sender_balance = self.get_balance(transaction.sender)
            total_deduction = transaction.amount + transaction.tip  # ✅ Only deduct amount + tip (NO FEE)
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
            total_deduction = transaction.amount + transaction.tip  # ✅ Only deduct amount + tip (NO FEE)
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
    
    def add_wallet(self, wallet):
        """Add a new wallet to the blockchain's wallet list."""
        self.wallets[wallet.public_key] = wallet
        print(f"Debug: Wallet added to blockchain - Public Key: {wallet.public_key}")