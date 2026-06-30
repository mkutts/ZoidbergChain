# Import statements
import os
import hashlib
import math
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
import json
from config import (
    ACTIVE_USER_LOOKBACK_DAYS,
    ACTIVE_USER_PERCENT_FOR_MIN_VOTES,
    BLOCKCHAIN_FILE,
    COIN_NAME,
    MEME_BLOCK_REWARD,
    MIN_VOTE_FLOOR,
    ORIGINALITY_APPROVAL_THRESHOLD,
    REWARD_POOL_SUPPLY,
    TOTAL_SUPPLY,
    VOTING_WINDOW_HOURS,
)
from submission import APPROVED, HARD_REJECTED, MINTED, PENDING, QUEUED, REJECTED, VOTE_NOT_ORIGINAL, VOTE_ORIGINAL, VOTE_TYPES, VOTE_UNSURE, Submission

class Blockchain:
    def __init__(self, project_owner_wallet=None, Contributor_one=None, Contributor_two=None, initial_supply=TOTAL_SUPPLY):
        self.chain = []  # The blockchain
        self.pending_transactions = []  # Transaction pool
        self.wallets = {}  # Registered wallets
        self.text_validation_cache = {}  # Cache for validated texts
        self.image_validation_cache = {}  # Cache for validated images
        self.texts = []  # List of all validated text content
        self.image_hashes = set()  # Set to store unique image hashes
        self.submissions = []  # Submitted content waiting for review or minting
        self.mint_queue = []  # Approved submissions waiting to be minted
        self.votes = []  # Recorded content votes
        self.reward_pool = REWARD_POOL_SUPPLY  # Initial reward pool
        self.initial_reward_pool = self.reward_pool  # Set the initial reward pool value

        # ✅ Store wallets immediately before loading blockchain
        self.project_owner_wallet = project_owner_wallet
        self.Contributor_one = Contributor_one
        self.Contributor_two = Contributor_two

        # ✅ Load blockchain from file, ensuring wallets persist
        if os.path.exists(BLOCKCHAIN_FILE):
            print("Debug: Attempting to load existing blockchain...")
            self.load_blockchain()
        else:
            print("Debug: No blockchain file found. Creating Genesis blockchain...")
            self.create_genesis_block(self.project_owner_wallet, self.Contributor_one, self.Contributor_two)

        # ✅ Ensure wallets are always assigned even after loading blockchain
        if self.project_owner_wallet and self.project_owner_wallet.public_key not in self.wallets:
            self.wallets[self.project_owner_wallet.public_key] = self.project_owner_wallet
        if self.Contributor_one and self.Contributor_one.public_key not in self.wallets:
            self.wallets[self.Contributor_one.public_key] = self.Contributor_one
        if self.Contributor_two and self.Contributor_two.public_key not in self.wallets:
            self.wallets[self.Contributor_two.public_key] = self.Contributor_two

        # ✅ Debugging - Print wallet storage
        print("Debug: Registered Wallets -", {k: v.__dict__ for k, v in self.wallets.items()})

    def save_blockchain(self):
        """Save blockchain state to disk, including wallets and transactions."""
        os.makedirs(os.path.dirname(BLOCKCHAIN_FILE) or ".", exist_ok=True)
        with open(BLOCKCHAIN_FILE, "w") as f:
            json.dump({
                "chain": [
                    {
                        "index": block.index,
                        "previous_hash": block.previous_hash,
                        "timestamp": block.timestamp,
                        "transactions": [tx.to_dict() for tx in block.transactions],  # ✅ Convert transactions to dicts
                        "miner": block.miner,
                        "meme": block.meme,
                        "hash": block.hash,
                    }
                    for block in self.chain
                ],
                "submissions": [submission.to_dict() for submission in self.submissions],
                "mint_queue": self.mint_queue,
                "votes": self.votes,
                "wallets": {key: wallet.to_dict() for key, wallet in self.wallets.items()}  # ✅ Convert wallets to dicts
            }, f, indent=4)
        print("✅ Debug: Blockchain and wallets saved successfully.")

    def load_blockchain(self):
        """Load blockchain state from disk if it exists, ensuring wallets persist."""
        try:
            with open(BLOCKCHAIN_FILE, "r") as f:
                loaded_data = json.load(f)

                # ✅ Ensure data structure is valid
                if isinstance(loaded_data, dict) and "chain" in loaded_data and "wallets" in loaded_data:
                    self.chain = [
                        Block(
                            index=block_data["index"],
                            previous_hash=block_data["previous_hash"],
                            timestamp=block_data["timestamp"],
                            transactions=[Transaction.from_dict(tx) for tx in block_data["transactions"]],  # ✅ Convert transactions
                            miner=block_data["miner"],
                            meme=block_data.get("meme", {}),
                            hash=block_data.get("hash"),
                        )
                        for block_data in loaded_data["chain"]
                    ]

                    self.wallets = {key: Wallet.from_dict(data) for key, data in loaded_data["wallets"].items()}  # ✅ Load wallets correctly

                    print("✅ Debug: Blockchain and wallets loaded successfully from blockchain.json.")

                    self.submissions = [
                        Submission.from_dict(submission_data)
                        for submission_data in loaded_data.get("submissions", [])
                    ]
                    self.mint_queue = loaded_data.get("mint_queue", [])
                    self.votes = loaded_data.get("votes", [])

                else:
                    print("⚠️ Debug: Blockchain file found but is invalid. Resetting to Genesis state.")
                    self.chain = []
                    self.wallets = {}

        except FileNotFoundError:
            print("⚠️ Debug: No saved blockchain found. Creating new blockchain.")
            self.chain = []
            self.wallets = {}
        except json.JSONDecodeError:
            print("⚠️ Debug: Failed to parse blockchain.json. Resetting to Genesis state.")
            self.chain = []
            self.wallets = {}
        except Exception as e:
            print(f"⚠️ Debug: Unexpected error loading blockchain - {e}")
            self.chain = []
            self.wallets = {}

        # ✅ If blockchain is empty, create Genesis block
        if not self.chain:
            print("⚠️ Debug: No valid blockchain found. Creating Genesis block.")
            self.create_genesis_block(self.project_owner_wallet, self.Contributor_one, self.Contributor_two)

        # ✅ Debug - Print blockchain length
        print(f"✅ Debug: Blockchain length after loading - {len(self.chain)} blocks")
        print(f"✅ Debug: Wallets loaded: {len(self.wallets)} wallets")

    def create_genesis_block(self, project_owner_wallet, Contributor_one, Contributor_two, initial_supply=TOTAL_SUPPLY):
        """Create the Genesis block with initial transactions and optional encoded meme."""
        genesis_transactions = []

        # Create initial transactions to fund wallets
        if project_owner_wallet:
            tx = Transaction(sender="GENESIS", recipient=project_owner_wallet.public_key, amount=initial_supply * 0.79)
            genesis_transactions.append(tx)

        if Contributor_one:
            tx = Transaction(sender="GENESIS", recipient=Contributor_one.public_key, amount=initial_supply * 0.10)
            genesis_transactions.append(tx)

        if Contributor_two:
            tx = Transaction(sender="GENESIS", recipient=Contributor_two.public_key, amount=initial_supply * 0.01)
            genesis_transactions.append(tx)

        # Ensure the transactions are correctly formatted
        print("Debug: Genesis Transactions -", [tx.__dict__ for tx in genesis_transactions])

        # Encode the provided genesis image
        try:
            with open("./zoidberg.jpg", "rb") as image_file:
                encoded_image = base64.b64encode(image_file.read()).decode("utf-8")
        except Exception as e:
            raise ValueError(f"Failed to encode genesis image: {e}")

        # Create the genesis block with transactions
        genesis_block = Block(
            index=0,
            previous_hash="0",
            timestamp=time.time(),
            transactions=genesis_transactions,  # ✅ Assign transactions explicitly
            miner="GENESIS",
            meme={"encoded_image": encoded_image, "text": "LOOKING FOR A NEW MEME COIN? WHY NOT ZOIDBERGCOIN"}
        )
        self.chain.append(genesis_block)

        # ✅ Debugging to verify genesis block transactions
        print("\n🔍 Genesis Block Transactions:", [tx.__dict__ for tx in genesis_block.transactions])

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

    def submit_content(self, image_path, text_content, submitter):
        """Create a pending content submission without minting a block."""
        if not os.path.isfile(image_path):
            raise ValueError("Invalid image path provided for the submission.")

        submission = Submission(
            image_path=image_path,
            text_content=text_content,
            submitter=submitter,
            status=PENDING,
        )
        self.submissions.append(submission)
        return submission

    def get_submission(self, submission_id):
        for submission in self.submissions:
            if submission.submission_id == submission_id:
                return submission
        return None

    def update_submission_status(self, submission_id, new_status):
        submission = self.get_submission(submission_id)
        if not submission:
            raise ValueError(f"Submission not found: {submission_id}")

        return submission.transition_to(new_status)

    def hard_reject_submission(self, submission_id, reason):
        submission = self.get_submission(submission_id)
        if not submission:
            raise ValueError(f"Submission not found: {submission_id}")
        if not reason:
            raise ValueError("Hard reject reason is required.")

        submission.hard_reject_reason = reason
        submission.transition_to(HARD_REJECTED)
        self.mint_queue = [
            queued_submission_id
            for queued_submission_id in self.mint_queue
            if queued_submission_id != submission_id
        ]
        return submission

    def record_vote(self, voter, submission_id=None, created_at=None):
        vote = {
            "voter": voter,
            "submission_id": submission_id,
            "vote_type": None,
            "created_at": created_at if created_at is not None else time.time(),
        }
        self.votes.append(vote)
        return vote

    def cast_submission_vote(self, submission_id, voter, vote_type, created_at=None):
        submission = self.get_submission(submission_id)
        if not submission:
            raise ValueError(f"Submission not found: {submission_id}")

        if submission.status == HARD_REJECTED:
            raise ValueError("Hard rejected submissions cannot receive votes.")

        if vote_type not in VOTE_TYPES:
            raise ValueError(f"Invalid vote type: {vote_type}")

        if voter == submission.submitter:
            raise ValueError("Submission creator cannot vote on their own submission.")

        if any(vote.get("submission_id") == submission_id and vote.get("voter") == voter for vote in self.votes):
            raise ValueError("Wallet has already voted on this submission.")

        vote = {
            "voter": voter,
            "submission_id": submission_id,
            "vote_type": vote_type,
            "created_at": created_at if created_at is not None else time.time(),
        }
        self.votes.append(vote)
        return vote

    def get_submission_votes(self, submission_id):
        if not self.get_submission(submission_id):
            raise ValueError(f"Submission not found: {submission_id}")

        votes = [vote for vote in self.votes if vote.get("submission_id") == submission_id]
        original_votes = sum(1 for vote in votes if vote.get("vote_type") == VOTE_ORIGINAL)
        not_original_votes = sum(1 for vote in votes if vote.get("vote_type") == VOTE_NOT_ORIGINAL)
        unsure_votes = sum(1 for vote in votes if vote.get("vote_type") == VOTE_UNSURE)
        decisive_votes = original_votes + not_original_votes
        approval_percentage = original_votes / decisive_votes if decisive_votes else 0

        return {
            "submission_id": submission_id,
            "votes": votes,
            "counts": {
                VOTE_ORIGINAL: original_votes,
                VOTE_NOT_ORIGINAL: not_original_votes,
                VOTE_UNSURE: unsure_votes,
            },
            "approval_percentage": approval_percentage,
        }

    def evaluate_submission(self, submission_id, automated_originality_passed=None, now=None):
        submission = self.get_submission(submission_id)
        if not submission:
            raise ValueError(f"Submission not found: {submission_id}")

        vote_summary = self.get_submission_votes(submission_id)
        now = now if now is not None else time.time()
        voting_window_expired = now >= submission.created_at + (VOTING_WINDOW_HOURS * 60 * 60)
        minimum_votes = self.get_voting_threshold(now=now)["minimum_votes"]
        minimum_votes_reached = len(vote_summary["votes"]) >= minimum_votes

        result = {
            "submission_id": submission_id,
            "status": submission.status,
            "minimum_votes": minimum_votes,
            "votes_cast": len(vote_summary["votes"]),
            "approval_percentage": vote_summary["approval_percentage"],
            "voting_window_expired": voting_window_expired,
            "minimum_votes_reached": minimum_votes_reached,
        }

        if submission.status != PENDING:
            result["reason"] = "already_finalized"
            return result

        if automated_originality_passed is None:
            automated_originality_passed = self.is_meme_original(
                submission.image_path,
                submission.text_content,
            )

        result["automated_originality_passed"] = automated_originality_passed

        if not automated_originality_passed:
            submission.transition_to(REJECTED)
            result["status"] = submission.status
            result["reason"] = "automated_originality_rejected"
            return result

        if not (voting_window_expired or minimum_votes_reached):
            result["reason"] = "awaiting_votes_or_window"
            return result

        if vote_summary["approval_percentage"] >= ORIGINALITY_APPROVAL_THRESHOLD:
            submission.transition_to(APPROVED)
            result["reason"] = "approved_by_vote"
        else:
            submission.transition_to(REJECTED)
            result["reason"] = "rejected_by_vote"

        result["status"] = submission.status
        return result

    def get_active_users(self, lookback_days=ACTIVE_USER_LOOKBACK_DAYS, now=None):
        now = now if now is not None else time.time()
        cutoff = now - (lookback_days * 24 * 60 * 60)
        active_wallets = set()

        for submission in self.submissions:
            if submission.created_at >= cutoff and submission.submitter:
                active_wallets.add(submission.submitter)

        for vote in self.votes:
            if vote.get("created_at", 0) >= cutoff and vote.get("voter"):
                active_wallets.add(vote["voter"])

        for transaction in self.pending_transactions:
            if transaction.created_at >= cutoff and transaction.sender not in {"GENESIS", "REWARD_POOL"}:
                active_wallets.add(transaction.sender)

        for block in self.chain:
            for transaction in block.transactions:
                if transaction.created_at >= cutoff and transaction.sender not in {"GENESIS", "REWARD_POOL"}:
                    active_wallets.add(transaction.sender)

        return len(active_wallets)

    def calculate_minimum_votes_required(self, active_users):
        return max(
            MIN_VOTE_FLOOR,
            math.ceil(active_users * ACTIVE_USER_PERCENT_FOR_MIN_VOTES),
        )

    def get_voting_threshold(self, lookback_days=ACTIVE_USER_LOOKBACK_DAYS, now=None):
        active_users = self.get_active_users(lookback_days=lookback_days, now=now)
        return {
            "active_users": active_users,
            "minimum_votes": self.calculate_minimum_votes_required(active_users),
            "vote_floor": MIN_VOTE_FLOOR,
            "active_percentage": ACTIVE_USER_PERCENT_FOR_MIN_VOTES,
        }

    def add_to_mint_queue(self, submission_id):
        submission = self.get_submission(submission_id)
        if not submission:
            raise ValueError(f"Submission not found: {submission_id}")
        if submission.status == HARD_REJECTED:
            raise ValueError("Hard rejected submissions cannot enter the mint queue.")
        if submission.status != APPROVED:
            raise ValueError("Only approved submissions can be added to the mint queue.")
        if submission_id in self.mint_queue:
            raise ValueError("Submission is already in the mint queue.")

        self.mint_queue.append(submission_id)
        submission.transition_to(QUEUED)
        return submission

    def get_mint_queue(self):
        queued_submissions = []
        for submission_id in self.mint_queue:
            submission = self.get_submission(submission_id)
            if submission and submission.status == QUEUED:
                queued_submissions.append(submission.to_dict())

        return queued_submissions

    def mint_next_queued_submission(self, miner=None, max_block_size_kb=500, validate_meme=True):
        if not self.mint_queue:
            raise ValueError("Mint queue is empty.")

        submission_id = self.mint_queue[0]
        submission = self.get_submission(submission_id)
        if submission and submission.status == HARD_REJECTED:
            raise ValueError("Hard rejected submissions cannot become blocks.")
        if not submission or submission.status != QUEUED:
            raise ValueError(f"Invalid mint queue entry: {submission_id}")

        block_added = self.add_block(
            image_path=submission.image_path,
            text_content=submission.text_content,
            miner=miner or submission.submitter,
            max_block_size_kb=max_block_size_kb,
            validate_meme=validate_meme,
        )
        if block_added:
            self.mint_queue.pop(0)
            submission.transition_to(MINTED)

        return block_added

    def mint_submission(self, submission_id, miner=None, max_block_size_kb=500, validate_meme=True):
        if not self.mint_queue or self.mint_queue[0] != submission_id:
            raise ValueError("Submissions must be minted from the front of the mint queue.")

        return self.mint_next_queued_submission(
            miner=miner,
            max_block_size_kb=max_block_size_kb,
            validate_meme=validate_meme,
        )

    def remove_invalid_mint_queue_entries(self):
        valid_queue = []
        removed_entries = []
        for submission_id in self.mint_queue:
            submission = self.get_submission(submission_id)
            if submission and submission.status == QUEUED:
                valid_queue.append(submission_id)
            else:
                removed_entries.append(submission_id)

        self.mint_queue = valid_queue
        return removed_entries

    def add_block(self, image_path, text_content=None, miner=None, max_block_size_kb=500, validate_meme=True):
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

        # ✅ Meme Validation Check
        image_hash = hash_image(image_path)  # Compute image hash
        normalized_text = re.sub(r'[^\w\s]', '', text_content).strip().lower()  # Normalize text

        if validate_meme:
            if image_hash in self.image_hashes and normalized_text in self.texts:
                print(f"⚠️ Debug: Duplicate meme detected! Image hash {image_hash} and text '{normalized_text}' already exist.")
                raise ValueError("This meme has already been submitted.")

        # Encode the image as base64
        print(f"Debug: Encoding image at path {image_path}.")
        meme_encoded = self.encode_image(image_path)

        # ✅ Calculate meme size (base64 encoding increases size)
        meme_size_kb = len(meme_encoded) / 1024
        text_size_kb = len(text_content.encode()) / 1024  # Convert text content size to KB

        # Validate transactions and calculate total tips
        valid_transactions = []
        total_tx_size_kb = 0  # ✅ Track total transaction size
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

                        tx_size_kb = len(str(tx)) / 1024  # ✅ Convert transaction size to KB
                        total_tx_size_kb += tx_size_kb
                        valid_transactions.append(tx)
                except Exception as e:
                    print(f"Debug: Transaction validation error: {e}")

        # ✅ Calculate total block size
        total_block_size_kb = meme_size_kb + text_size_kb + total_tx_size_kb

        # ✅ Enforce block size limit
        if total_block_size_kb > max_block_size_kb:
            print(f"Debug: Block size {total_block_size_kb:.2f} KB exceeds max limit of {max_block_size_kb} KB. Rejecting block.")
            return False

        print(f"Debug: Final block size: {total_block_size_kb:.2f} KB (within limit: {max_block_size_kb} KB)")

        # ✅ Ensure miner’s balance is updated
        if miner in self.wallets:
            current_balance = self.get_balance(miner)  # ✅ Get miner's balance
            updated_balance = current_balance + total_miner_tips  # ✅ Add miner's earnings
            print(f"Debug: Before crediting miner {miner}: {current_balance:.4f} {COIN_NAME}")
            print(f"Debug: Miner earned: {total_miner_tips:.4f} {COIN_NAME}")

            # ✅ Store the updated balance at the blockchain level
            self.wallets[miner].stored_balance = updated_balance  # ✅ Store updated balance

            print(f"Debug: After crediting miner {miner}: {self.wallets[miner].stored_balance:.4f} {COIN_NAME}")
        else:
            print(f"Debug: WARNING! Miner {miner} not found in registered wallets. Initializing new wallet.")

            # ✅ Initialize the miner's wallet with the earned balance
            self.wallets[miner] = Wallet()
            self.wallets[miner].public_key = miner
            self.wallets[miner].private_key = None  # Miner’s private key is unknown
            self.wallets[miner].stored_balance = total_miner_tips  # ✅ Store the initial balance
            print(f"Debug: New miner wallet created for {miner} with balance: {total_miner_tips:.4f} {COIN_NAME}")

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

        # ✅ Cache meme data after block is added
        print(f"Debug: Caching meme data for image {image_path}.")
        self.image_hashes.add(image_hash)
        self.texts.append(normalized_text)

        print(f"Block {new_block.index} added with meme: {text_content}. Final size: {total_block_size_kb:.2f} KB.")
        print(f"Miner earned: {total_miner_tips:.4f} {COIN_NAME}.")

        self.save_blockchain()

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
    
