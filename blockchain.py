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
    COIN_NAME,
    MEME_BLOCK_REWARD,
    MIN_VOTE_FLOOR,
    NETWORK_NAME,
    NODE_ID,
    ORIGINALITY_APPROVAL_THRESHOLD,
    REWARD_POOL_SUPPLY,
    TOTAL_SUPPLY,
    VOTING_WINDOW_HOURS,
)
from originality_certificate import OriginalityCertificate, validate_certificate_for_submission
from content import (
    CONTENT_TYPE_IMAGE,
    CONTENT_TYPE_MIXED,
    CONTENT_TYPE_TEXT,
    HASH_SCHEME_SHA256_BYTES,
    HASH_SCHEME_LEGACY,
    HASH_SCHEME_SHA256_TEXT,
    HASH_SCHEME_UNKNOWN,
    TEXT_MIME_TYPE,
    _validate_content_type,
    STORAGE_STATUS_LOCAL,
    STORAGE_STATUS_MISSING,
    STORAGE_STATUS_REMOTE,
    STORAGE_STATUS_VERIFIED,
    ContentObject,
    canonicalize_text_content,
    content_object_from_submission_data,
    compute_text_content_hash,
    ensure_content_storage_dir,
    guess_mime_type,
    resolve_payload_hash,
    resolve_local_path,
    sanitize_original_filename,
    store_content_bytes,
    validate_caption,
    validate_text_content,
    verify_content_object_payload,
)
from submission import APPROVED, HARD_REJECTED, MINTED, PENDING, QUEUED, REJECTED, VOTE_NOT_ORIGINAL, VOTE_ORIGINAL, VOTE_TYPES, VOTE_UNSURE, Submission
from storage import create_storage_backend
from validators import is_valid_ethereum_address


def _hash_number(value):
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        numeric_value = float(value)
        if numeric_value.is_integer():
            return str(int(numeric_value))
        return str(numeric_value)
    return str(value)


def _short_public_key(public_key):
    key = str(public_key or "")
    if len(key) <= 18:
        return key or "unknown"
    return f"{key[:10]}...{key[-8:]}"


class Blockchain:
    def __init__(
        self,
        project_owner_wallet=None,
        Contributor_one=None,
        Contributor_two=None,
        initial_supply=TOTAL_SUPPLY,
        storage_backend=None,
    ):
        self.chain = []  # The blockchain
        self.pending_transactions = []  # Transaction pool
        self.wallets = {}  # Registered wallets
        self.text_validation_cache = {}  # Cache for validated texts
        self.image_validation_cache = {}  # Cache for validated images
        self.texts = []  # List of all validated text content
        self.image_hashes = set()  # Set to store unique image hashes
        self.submissions = []  # Submitted content waiting for review or minting
        self.content_objects = []  # Persisted content payload metadata
        self.mint_queue = []  # Approved submissions waiting to be minted
        self.votes = []  # Recorded content votes
        self.originality_certificates = []  # Community approval certificates
        self.reward_pool = REWARD_POOL_SUPPLY  # Initial reward pool
        self.initial_reward_pool = self.reward_pool  # Set the initial reward pool value
        self.storage = storage_backend or create_storage_backend()
        ensure_content_storage_dir(data_dir=self.storage.data_dir)

        # âœ… Store wallets immediately before loading blockchain
        self.project_owner_wallet = project_owner_wallet
        self.Contributor_one = Contributor_one
        self.Contributor_two = Contributor_two

        # âœ… Load blockchain from storage, ensuring wallets persist
        self.load_blockchain()
        if not self.chain:
            print("Debug: No valid blockchain found. Creating Genesis blockchain...")
            self.create_genesis_block(self.project_owner_wallet, self.Contributor_one, self.Contributor_two)

        # âœ… Ensure wallets are always assigned even after loading blockchain
        if self.project_owner_wallet and self.project_owner_wallet.public_key not in self.wallets:
            self.wallets[self.project_owner_wallet.public_key] = self.project_owner_wallet
        if self.Contributor_one and self.Contributor_one.public_key not in self.wallets:
            self.wallets[self.Contributor_one.public_key] = self.Contributor_one
        if self.Contributor_two and self.Contributor_two.public_key not in self.wallets:
            self.wallets[self.Contributor_two.public_key] = self.Contributor_two

        # âœ… Debugging - Print wallet storage
        print("Debug: Registered Wallets -", [_short_public_key(key) for key in self.wallets.keys()])

    def _serialize_blockchain_state(self):
        return {
            "chain": [
                {
                    "index": block.index,
                    "previous_hash": block.previous_hash,
                    "timestamp": block.timestamp,
                    "transactions": [tx.to_dict() for tx in block.transactions],
                    "miner": block.miner,
                    "meme": block.meme,
                    "hash": block.hash,
                    **block.certificate_metadata(),
                }
                for block in self.chain
            ],
            "submissions": [submission.to_dict() for submission in self.submissions],
            "content_objects": [content_object.to_dict() for content_object in self.content_objects],
            "mint_queue": self.mint_queue,
            "votes": self.votes,
            "originality_certificates": [
                certificate.to_dict()
                for certificate in self.originality_certificates
            ],
            "wallets": {key: wallet.to_dict() for key, wallet in self.wallets.items()},
        }

    def save_blockchain(self):
        """Save blockchain state to disk, including wallets and transactions."""
        self.storage.save_blockchain_state(self._serialize_blockchain_state())
        print("Debug: Blockchain and wallets saved successfully.")

    def load_blockchain(self):
        """Load blockchain state from disk if it exists, ensuring wallets persist."""
        try:
            loaded_data = self.storage.load_blockchain_state()

            if isinstance(loaded_data, dict) and "chain" in loaded_data and "wallets" in loaded_data:
                self.chain = [
                    Block(
                        index=block_data["index"],
                        previous_hash=block_data["previous_hash"],
                        timestamp=block_data["timestamp"],
                        transactions=[Transaction.from_dict(tx) for tx in block_data["transactions"]],
                        miner=block_data["miner"],
                        meme=block_data.get("meme", {}),
                        hash=block_data.get("hash"),
                        submission_id=block_data.get("submission_id"),
                        certificate_id=block_data.get("certificate_id"),
                        content_hash=block_data.get("content_hash"),
                        content_id=block_data.get("content_id"),
                        content_type=block_data.get("content_type"),
                        mime_type=block_data.get("mime_type"),
                        creator_wallet=block_data.get("creator_wallet"),
                        vote_hash=block_data.get("vote_hash"),
                        approval_percentage=block_data.get("approval_percentage"),
                        decisive_vote_total=block_data.get("decisive_vote_total"),
                        minimum_votes_required=block_data.get("minimum_votes_required"),
                        approved_at=block_data.get("approved_at"),
                        originality_score=block_data.get("originality_score"),
                    )
                    for block_data in loaded_data["chain"]
                ]

                self.wallets = {key: Wallet.from_dict(data) for key, data in loaded_data["wallets"].items()}

                print("Debug: Blockchain and wallets loaded successfully from blockchain.json.")

                self.submissions = [
                    Submission.from_dict(submission_data)
                    for submission_data in loaded_data.get("submissions", [])
                ]
                self.content_objects = [
                    ContentObject.from_dict(content_object_data)
                    for content_object_data in loaded_data.get("content_objects", [])
                ]
                self.mint_queue = loaded_data.get("mint_queue", [])
                self.votes = loaded_data.get("votes", [])
                self.originality_certificates = [
                    OriginalityCertificate.from_dict(certificate_data)
                    for certificate_data in loaded_data.get("originality_certificates", [])
                ]
                self.link_content_objects_to_submissions()
                self.refresh_content_object_storage_statuses()
                self.link_certificates_to_submissions()
                print(f"Debug: Blockchain length after loading - {len(self.chain)} blocks")
                print(f"Debug: Wallets loaded: {len(self.wallets)} wallets")
                return True

            if loaded_data is not None:
                print("Debug: Blockchain file found but is invalid. Resetting to Genesis state.")
                self.chain = []
                self.wallets = {}
                self.submissions = []
                self.content_objects = []
                self.mint_queue = []
                self.votes = []
                self.originality_certificates = []

        except FileNotFoundError:
            print("Debug: No saved blockchain found. Creating new blockchain.")
            self.chain = []
            self.wallets = {}
            self.submissions = []
            self.content_objects = []
            self.mint_queue = []
            self.votes = []
            self.originality_certificates = []
        except json.JSONDecodeError:
            print("Debug: Failed to parse blockchain.json. Resetting to Genesis state.")
            self.chain = []
            self.wallets = {}
            self.submissions = []
            self.content_objects = []
            self.mint_queue = []
            self.votes = []
            self.originality_certificates = []
        except Exception as e:
            print(f"Debug: Unexpected error loading blockchain - {e}")
            self.chain = []
            self.wallets = {}
            self.submissions = []
            self.content_objects = []
            self.mint_queue = []
            self.votes = []
            self.originality_certificates = []

        return False

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
            transactions=genesis_transactions,  # âœ… Assign transactions explicitly
            miner="GENESIS",
            meme={"encoded_image": encoded_image, "text": "LOOKING FOR A NEW MEME COIN? WHY NOT ZOIDBERGCOIN"}
        )
        self.chain.append(genesis_block)

        # âœ… Debugging to verify genesis block transactions
        print("\nGenesis Block Transactions:", [tx.__dict__ for tx in genesis_block.transactions])

        print("\nGenesis wallets initialized:")
        if project_owner_wallet:
            print(f"Project Owner Wallet Public Key: {_short_public_key(project_owner_wallet.public_key)}")
        if Contributor_one:
            print(f"Contributor One Public Key: {_short_public_key(Contributor_one.public_key)}")
        if Contributor_two:
            print(f"Contributor Two Public Key: {_short_public_key(Contributor_two.public_key)}")
        print("Private keys are not printed. Use the development-only export endpoint for local setup.\n")


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
        return self.storage.get_wallet(public_key, self.wallets)

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

    def _build_content_object_for_submission(self, submission, image_path="", text_content="", storage_status=None):
        try:
            return content_object_from_submission_data(
                {
                    "submission_id": submission.submission_id,
                    "image_path": image_path,
                    "text_content": text_content,
                    "submitter": submission.submitter,
                    "created_at": submission.created_at,
                    "content_hash": submission.content_hash,
                    "content_id": submission.content_id,
                    "certificate_id": submission.certificate_id,
                },
                network_name=NETWORK_NAME,
                storage_status=storage_status,
                data_dir=self.storage.data_dir,
            )
        except ValueError:
            return None

    def _apply_stored_content_to_object(self, content_object, stored_content, *, submission_id=None, text_content=""):
        metadata = dict(content_object.metadata or {})
        if stored_content.get("byte_hash"):
            metadata["byte_hash"] = stored_content["byte_hash"]
        if stored_content.get("original_filename"):
            metadata["original_filename"] = stored_content["original_filename"]
        if submission_id:
            metadata["submission_id"] = submission_id

        content_object.mime_type = stored_content["mime_type"]
        content_object.file_size_bytes = stored_content["file_size_bytes"]
        content_object.storage_status = stored_content["storage_status"]
        content_object.local_path = stored_content["local_path"]
        content_object.hash_scheme = stored_content.get("hash_scheme", content_object.hash_scheme)
        if stored_content.get("file_name"):
            content_object.file_name = stored_content["file_name"]
        if text_content and not content_object.text_content:
            content_object.text_content = text_content
        if text_content and not content_object.caption:
            content_object.caption = text_content
        content_object.metadata = metadata
        verification = verify_content_object_payload(content_object, data_dir=self.storage.data_dir)
        content_object.hash_scheme = verification["hash_scheme"]
        content_object.verified_at = verification["verified_at"]
        content_object.verification_error = verification["error"]
        return content_object

    def _ensure_content_object_for_submission(
        self,
        submission,
        image_path="",
        text_content="",
        stored_content=None,
        storage_status=None,
    ):
        content_object = self.get_content_object_by_hash(submission.content_hash)
        if content_object:
            if submission.content_id and submission.content_id != content_object.content_id:
                raise ValueError("content_id does not match content_hash.")
            if not submission.content_id:
                submission.content_id = content_object.content_id
            if stored_content:
                self._apply_stored_content_to_object(
                    content_object,
                    stored_content,
                    submission_id=submission.submission_id,
                    text_content=text_content,
                )
            elif storage_status in {STORAGE_STATUS_REMOTE, STORAGE_STATUS_MISSING} and content_object.storage_status != STORAGE_STATUS_VERIFIED:
                content_object.storage_status = storage_status
                if storage_status == STORAGE_STATUS_REMOTE:
                    content_object.local_path = None
            return content_object

        content_object = self._build_content_object_for_submission(
            submission,
            image_path=image_path,
            text_content=text_content,
            storage_status=storage_status,
        )
        if content_object is None:
            return None
        if stored_content:
            self._apply_stored_content_to_object(
                content_object,
                stored_content,
                submission_id=submission.submission_id,
                text_content=text_content,
            )
        elif storage_status == STORAGE_STATUS_REMOTE:
            content_object.local_path = None
        self.content_objects.append(content_object)
        submission.content_id = content_object.content_id
        return content_object

    def _store_submission_content(self, submission, image_path="", text_content=""):
        if image_path:
            with open(image_path, "rb") as image_file:
                image_bytes = image_file.read()
            stored_content = store_content_bytes(
                submission.content_hash,
                image_bytes,
                mime_type=guess_mime_type(os.path.basename(image_path), "image/jpeg"),
                original_filename=os.path.basename(image_path),
                data_dir=self.storage.data_dir,
                hash_scheme=HASH_SCHEME_LEGACY,
            )
            submission.image_path = os.path.abspath(stored_content["path"])
            return stored_content

        normalized_text = (text_content or "").strip()
        if not normalized_text:
            return None

        return store_content_bytes(
            submission.content_hash,
            normalized_text.encode("utf-8"),
            mime_type=TEXT_MIME_TYPE,
            data_dir=self.storage.data_dir,
            hash_scheme=HASH_SCHEME_LEGACY,
        )

    def refresh_content_object_storage_statuses(self):
        refreshed_any = False
        for content_object in self.content_objects:
            verification = verify_content_object_payload(content_object, data_dir=self.storage.data_dir)
            new_status = content_object.storage_status
            if verification["verified"]:
                new_status = STORAGE_STATUS_VERIFIED
            elif verification["error"] == "missing_file":
                if content_object.storage_status in {STORAGE_STATUS_LOCAL, STORAGE_STATUS_VERIFIED}:
                    new_status = STORAGE_STATUS_MISSING
            elif verification["exists"]:
                new_status = STORAGE_STATUS_LOCAL

            if content_object.storage_status != new_status:
                content_object.storage_status = new_status
                refreshed_any = True
            if content_object.hash_scheme != verification["hash_scheme"]:
                content_object.hash_scheme = verification["hash_scheme"]
                refreshed_any = True
            if content_object.verification_error != verification["error"]:
                content_object.verification_error = verification["error"]
                refreshed_any = True
            if content_object.verified_at != verification["verified_at"]:
                content_object.verified_at = verification["verified_at"]
                refreshed_any = True
            if verification["local_path"] and content_object.local_path != verification["local_path"]:
                content_object.local_path = verification["local_path"]
                refreshed_any = True
            if verification["file_size_bytes"] is not None and content_object.file_size_bytes != verification["file_size_bytes"]:
                content_object.file_size_bytes = verification["file_size_bytes"]
                refreshed_any = True
        return refreshed_any

    def submit_content(self, image_path="", text_content="", submitter=""):
        """Create a pending content submission without minting a block."""
        if image_path and not os.path.isfile(image_path):
            raise ValueError("Invalid image path provided for the submission.")
        if not image_path and not (text_content or "").strip():
            raise ValueError("At least image_path or text_content is required for a submission.")

        submission = Submission(
            image_path=image_path or "",
            text_content=text_content,
            submitter=submitter,
            status=PENDING,
        )
        stored_content = self._store_submission_content(
            submission,
            image_path=image_path or "",
            text_content=text_content or "",
        )
        self.submissions.append(submission)
        self._ensure_content_object_for_submission(
            submission,
            image_path=submission.image_path or "",
            text_content=text_content or "",
            stored_content=stored_content,
        )
        return submission

    def get_submission(self, submission_id):
        return self.storage.get_submission(submission_id, self.submissions)

    def get_content_object(self, content_id):
        return self.storage.get_content_object(content_id, self.content_objects)

    def get_content_object_by_hash(self, content_hash):
        return self.storage.get_content_object_by_hash(content_hash, self.content_objects)

    def list_content_objects(self, status=None):
        return self.storage.list_content_objects(status=status, content_objects=self.content_objects)

    def _content_type_hint_for_submission(self, image_path="", text_content=""):
        has_image = bool(image_path)
        has_text = bool((text_content or "").strip())
        if has_image and has_text:
            return CONTENT_TYPE_MIXED
        if has_image:
            return CONTENT_TYPE_IMAGE
        return CONTENT_TYPE_TEXT

    def register_remote_content_reference(
        self,
        *,
        content_hash,
        content_id=None,
        submitted_by=None,
        mime_type="application/octet-stream",
        content_type=CONTENT_TYPE_IMAGE,
        caption=None,
        text_content=None,
        file_name=None,
        created_at=None,
        storage_status=STORAGE_STATUS_REMOTE,
        submission_id=None,
    ):
        content_object = self.get_content_object_by_hash(content_hash)
        if content_object is not None:
            if content_id and content_object.content_id != content_id:
                raise ValueError("content_id does not match content_hash.")
            if mime_type and (
                not content_object.mime_type
                or content_object.mime_type == "application/octet-stream"
                or content_object.mime_type == TEXT_MIME_TYPE
            ):
                content_object.mime_type = mime_type
            if (
                content_type
                and content_object.content_type == CONTENT_TYPE_IMAGE
                and content_type in {CONTENT_TYPE_TEXT, CONTENT_TYPE_MIXED}
            ):
                content_object.content_type = content_type
            elif content_type and not content_object.content_type:
                content_object.content_type = content_type
            if submitted_by and content_object.submitted_by == "peer-content":
                content_object.submitted_by = submitted_by
            if content_object.storage_status != STORAGE_STATUS_VERIFIED:
                content_object.storage_status = storage_status
                content_object.local_path = None
                content_object.verified_at = None
            if content_object.hash_scheme == HASH_SCHEME_UNKNOWN:
                content_object.verification_error = "legacy_unverifiable"
            if caption and not content_object.caption:
                content_object.caption = caption.strip()
            if text_content and not content_object.text_content:
                content_object.text_content = text_content.strip()
            if file_name and not content_object.file_name:
                content_object.file_name = file_name
            if submission_id:
                metadata = dict(content_object.metadata or {})
                metadata.setdefault("submission_id", submission_id)
                content_object.metadata = metadata
            return content_object

        content_object = ContentObject(
            content_hash=content_hash,
            content_type=content_type,
            mime_type=mime_type,
            submitted_by=(submitted_by or "peer-content"),
            network_name=NETWORK_NAME,
            created_at=time.time() if created_at is None else created_at,
            file_name=file_name,
            file_size_bytes=None,
            storage_status=storage_status,
            local_path=None,
            text_content=text_content,
            caption=caption,
            metadata=({"submission_id": submission_id} if submission_id else {}),
            hash_scheme=HASH_SCHEME_UNKNOWN,
            verification_error="legacy_unverifiable",
        )
        self.content_objects.append(content_object)
        return content_object

    def register_uploaded_content(
        self,
        *,
        content_hash,
        submitted_by,
        mime_type,
        file_size_bytes,
        storage_status,
        local_path=None,
        file_name=None,
        original_filename=None,
        caption=None,
        text_content=None,
        content_type_hint=None,
        created_at=None,
        byte_hash=None,
        hash_scheme=None,
    ):
        content_type = None
        if content_type_hint:
            content_type = _validate_content_type(content_type_hint)
        elif mime_type == TEXT_MIME_TYPE:
            content_type = CONTENT_TYPE_TEXT
        elif (text_content or "").strip() or (caption or "").strip():
            content_type = CONTENT_TYPE_MIXED
        else:
            content_type = CONTENT_TYPE_IMAGE

        if mime_type == TEXT_MIME_TYPE and content_type == CONTENT_TYPE_IMAGE:
            content_type = CONTENT_TYPE_TEXT

        content_object = self.get_content_object_by_hash(content_hash)
        if content_object:
            metadata = dict(content_object.metadata or {})
            if byte_hash:
                metadata["byte_hash"] = byte_hash
            if original_filename:
                metadata["original_filename"] = original_filename
            content_object.mime_type = mime_type
            content_object.file_size_bytes = file_size_bytes
            content_object.storage_status = storage_status
            content_object.hash_scheme = hash_scheme or content_object.hash_scheme
            if local_path:
                content_object.local_path = local_path
            if file_name:
                content_object.file_name = file_name
            if caption:
                content_object.caption = caption.strip()
            if text_content:
                content_object.text_content = text_content.strip()
            if content_object.content_type == CONTENT_TYPE_IMAGE and content_type == CONTENT_TYPE_MIXED:
                content_object.content_type = CONTENT_TYPE_MIXED
            content_object.metadata = metadata
            verification = verify_content_object_payload(content_object, data_dir=self.storage.data_dir)
            content_object.hash_scheme = verification["hash_scheme"]
            content_object.verified_at = verification["verified_at"]
            content_object.verification_error = verification["error"]
            return content_object

        content_object = ContentObject(
            content_hash=content_hash,
            content_type=content_type,
            mime_type=mime_type,
            submitted_by=submitted_by,
            network_name=NETWORK_NAME,
            created_at=time.time() if created_at is None else created_at,
            file_name=file_name,
            file_size_bytes=file_size_bytes,
            storage_status=storage_status,
            local_path=local_path,
            text_content=text_content,
            caption=caption,
            metadata=(
                {
                    **({"byte_hash": byte_hash} if byte_hash else {}),
                    **({"original_filename": original_filename} if original_filename else {}),
                }
            ),
            hash_scheme=hash_scheme or HASH_SCHEME_UNKNOWN,
            verified_at=time.time() if storage_status == STORAGE_STATUS_VERIFIED else None,
            verification_error=None,
        )
        verification = verify_content_object_payload(content_object, data_dir=self.storage.data_dir)
        content_object.hash_scheme = verification["hash_scheme"]
        content_object.verified_at = verification["verified_at"]
        content_object.verification_error = verification["error"]
        self.content_objects.append(content_object)
        return content_object

    def upload_binary_content(
        self,
        *,
        file_bytes,
        submitted_by,
        mime_type,
        original_filename=None,
        caption=None,
        content_type_hint=None,
    ):
        resolved_payload = resolve_payload_hash(file_bytes, mime_type)
        content_hash = resolved_payload["content_hash"]
        normalized_text_content = resolved_payload["text_content"]
        stored_content = store_content_bytes(
            content_hash,
            resolved_payload["stored_bytes"],
            mime_type=resolved_payload["mime_type"],
            original_filename=sanitize_original_filename(original_filename),
            data_dir=self.storage.data_dir,
            hash_scheme=resolved_payload["hash_scheme"],
        )
        content_object = self.register_uploaded_content(
            content_hash=content_hash,
            submitted_by=submitted_by,
            mime_type=stored_content["mime_type"],
            file_size_bytes=stored_content["file_size_bytes"],
            storage_status=stored_content["storage_status"],
            local_path=stored_content["local_path"],
            file_name=stored_content["file_name"],
            original_filename=stored_content["original_filename"],
            caption=validate_caption(caption),
            text_content=normalized_text_content,
            content_type_hint=content_type_hint,
            byte_hash=stored_content["byte_hash"],
            hash_scheme=stored_content["hash_scheme"],
        )
        return content_object

    def upload_text_content(
        self,
        *,
        text_content,
        submitted_by,
        caption=None,
    ):
        normalized_text = validate_text_content(text_content)
        content_hash = compute_text_content_hash(normalized_text)
        stored_content = store_content_bytes(
            content_hash,
            normalized_text.encode("utf-8"),
            mime_type=TEXT_MIME_TYPE,
            data_dir=self.storage.data_dir,
            hash_scheme=HASH_SCHEME_SHA256_TEXT,
        )
        content_object = self.register_uploaded_content(
            content_hash=content_hash,
            submitted_by=submitted_by,
            mime_type=TEXT_MIME_TYPE,
            file_size_bytes=stored_content["file_size_bytes"],
            storage_status=stored_content["storage_status"],
            local_path=stored_content["local_path"],
            file_name=stored_content["file_name"],
            original_filename=stored_content["original_filename"],
            caption=validate_caption(caption),
            text_content=normalized_text,
            content_type_hint=CONTENT_TYPE_TEXT,
            byte_hash=stored_content["byte_hash"],
            hash_scheme=stored_content["hash_scheme"],
        )
        return content_object

    def submit_existing_content(self, *, content_hash=None, submitter, text_content="", content_id=None):
        content_object = None
        if content_id:
            content_object = self.get_content_object(content_id)
            if content_object is None:
                raise ValueError(f"Content not found: {content_id}")
        if content_hash:
            hashed_content_object = self.get_content_object_by_hash(content_hash)
            if content_object is not None and content_object.content_hash != content_hash:
                raise ValueError("content_id does not match content_hash.")
            if hashed_content_object is not None:
                content_object = hashed_content_object
        if content_object is None and content_hash:
            content_object = self.register_remote_content_reference(
                content_hash=content_hash,
                content_id=content_id,
                submitted_by=submitter,
                mime_type=TEXT_MIME_TYPE if (text_content or "").strip() else "application/octet-stream",
                content_type=self._content_type_hint_for_submission("", text_content),
                caption=(text_content or "").strip() or None,
                text_content=(text_content or "").strip() or None,
                storage_status=STORAGE_STATUS_MISSING,
            )
        if content_object is None:
            raise ValueError("content_hash or content_id is required.")

        image_path = ""
        if content_object.content_type in {CONTENT_TYPE_IMAGE, CONTENT_TYPE_MIXED, CONTENT_TYPE_TEXT}:
            resolved_image_path = resolve_local_path(content_object.local_path, data_dir=self.storage.data_dir)
            if resolved_image_path and os.path.isfile(resolved_image_path):
                image_path = resolved_image_path

        verification = verify_content_object_payload(content_object, data_dir=self.storage.data_dir)
        if content_object.storage_status == STORAGE_STATUS_VERIFIED and not verification["verified"]:
            raise ValueError("Uploaded content file failed content_hash verification.")
        if verification["exists"] and verification["verified"]:
            content_object.hash_scheme = verification["hash_scheme"]
            content_object.verified_at = verification["verified_at"]
            content_object.verification_error = None
            content_object.storage_status = STORAGE_STATUS_VERIFIED

        submission_text = (text_content or "").strip() or content_object.text_content or content_object.caption or ""
        submission = Submission(
            image_path=image_path,
            text_content=submission_text,
            submitter=submitter,
            status=PENDING,
            content_hash=content_object.content_hash,
            content_id=content_object.content_id,
        )
        self.submissions.append(submission)
        self._ensure_content_object_for_submission(
            submission,
            image_path=image_path,
            text_content=submission_text,
            storage_status=(
                content_object.storage_status
                if content_object.storage_status in {STORAGE_STATUS_REMOTE, STORAGE_STATUS_MISSING}
                else None
            ),
        )
        return submission

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

        if vote_type not in VOTE_TYPES:
            raise ValueError(f"Invalid vote type: {vote_type}")

        if voter == submission.submitter:
            raise ValueError("Submission creator cannot vote on their own submission.")

        if self.storage.get_vote(submission_id, voter, self.votes):
            raise ValueError("Wallet has already voted on this submission.")

        if self.is_submission_voting_locked(submission):
            raise ValueError("Finalized or certified submissions cannot receive votes.")

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

        votes = self.storage.get_votes_for_submission(submission_id, self.votes)
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

    def is_submission_voting_locked(self, submission):
        return (
            submission.status in {APPROVED, QUEUED, REJECTED, HARD_REJECTED, MINTED}
            or self.get_originality_certificate_for_submission(submission.submission_id) is not None
        )

    def get_originality_certificate(self, certificate_id):
        return self.storage.get_certificate(certificate_id, self.originality_certificates)

    def get_originality_certificate_for_submission(self, submission_id):
        return self.storage.get_certificate_for_submission(submission_id, self.originality_certificates)

    def link_certificates_to_submissions(self):
        linked_any = False
        for certificate in self.originality_certificates:
            submission = self.get_submission(certificate.submission_id)
            if submission and submission.certificate_id != certificate.certificate_id:
                submission.certificate_id = certificate.certificate_id
                linked_any = True
        return linked_any

    def link_content_objects_to_submissions(self):
        linked_any = False
        for submission in self.submissions:
            content_object = self.get_content_object_by_hash(submission.content_hash)
            if content_object:
                if submission.content_id != content_object.content_id:
                    submission.content_id = content_object.content_id
                    linked_any = True
                resolved_image_path = resolve_local_path(
                    content_object.local_path,
                    data_dir=self.storage.data_dir,
                )
                if (
                    resolved_image_path
                    and content_object.content_type in {"image", "mixed"}
                    and submission.image_path != resolved_image_path
                    and os.path.isfile(resolved_image_path)
                ):
                    submission.image_path = resolved_image_path
                    linked_any = True
            else:
                created_content_object = self._ensure_content_object_for_submission(
                    submission,
                    image_path=submission.image_path,
                    text_content=submission.text_content,
                )
                if created_content_object:
                    linked_any = True
        return linked_any

    def certificate_block_metadata(self, certificate):
        submission = self.get_submission(certificate.submission_id)
        content_object = self.get_content_object_by_hash(certificate.content_hash)
        metadata = {
            "submission_id": certificate.submission_id,
            "certificate_id": certificate.certificate_id,
            "content_hash": certificate.content_hash,
            "content_id": (
                certificate.content_id
                or (submission.content_id if submission is not None else None)
                or (content_object.content_id if content_object is not None else None)
            ),
            "creator_wallet": certificate.creator_wallet,
            "vote_hash": certificate.vote_hash,
            "approval_percentage": certificate.approval_percentage,
            "decisive_vote_total": certificate.decisive_vote_total,
            "minimum_votes_required": certificate.minimum_votes_required,
            "approved_at": certificate.approved_at,
            "originality_score": certificate.originality_score,
        }
        if content_object is not None:
            metadata["content_type"] = content_object.content_type
            metadata["mime_type"] = content_object.mime_type
        return metadata

    def require_valid_certificate_for_submission(self, submission):
        certificate = self.get_originality_certificate_for_submission(submission.submission_id)
        validate_certificate_for_submission(certificate, submission, network_name=NETWORK_NAME)
        return certificate

    def _build_originality_certificate(
        self,
        submission,
        approved_at,
        network_name,
        issuing_node_id,
    ):
        vote_summary = self.get_submission_votes(submission.submission_id)
        return OriginalityCertificate.from_approved_submission(
            submission=submission,
            votes=vote_summary["votes"],
            minimum_votes_required=self.get_voting_threshold(now=approved_at)["minimum_votes"],
            approved_at=approved_at,
            network_name=network_name,
            issuing_node_id=issuing_node_id,
        )

    def create_originality_certificate(
        self,
        submission_id,
        approved_at=None,
        network_name=NETWORK_NAME,
        issuing_node_id=NODE_ID,
        allow_pending=False,
        save=True,
    ):
        submission = self.get_submission(submission_id)
        if not submission:
            raise ValueError(f"Submission not found: {submission_id}")
        allowed_statuses = {APPROVED, QUEUED}
        if allow_pending:
            allowed_statuses.add(PENDING)
        if submission.status not in allowed_statuses:
            raise ValueError("Only approved unminted submissions can receive originality certificates.")

        existing_certificate = self.get_originality_certificate_for_submission(submission_id)
        if existing_certificate:
            submission.certificate_id = existing_certificate.certificate_id
            if save:
                self.save_blockchain()
            return existing_certificate

        approved_at = approved_at if approved_at is not None else time.time()
        certificate = self._build_originality_certificate(
            submission,
            approved_at,
            network_name,
            issuing_node_id,
        )
        validate_certificate_for_submission(
            certificate,
            submission,
            network_name=network_name,
            allowed_submission_statuses=allowed_statuses,
        )
        self.originality_certificates.append(certificate)
        submission.certificate_id = certificate.certificate_id
        if save:
            self.save_blockchain()
        return certificate

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
            previous_status = submission.status
            previous_certificate_id = submission.certificate_id
            existing_certificate = self.get_originality_certificate_for_submission(submission_id)
            created_certificate_id = None
            try:
                certificate = self.create_originality_certificate(
                    submission_id,
                    approved_at=now,
                    allow_pending=True,
                    save=False,
                )
                created_certificate_id = certificate.certificate_id
                if not self.get_originality_certificate_for_submission(submission_id):
                    raise ValueError("certificate could not be retrieved after creation")
                self.save_blockchain()
                submission.transition_to(APPROVED)
                validate_certificate_for_submission(certificate, submission, network_name=NETWORK_NAME)
                if self.get_originality_certificate_for_submission(submission_id) is None:
                    raise ValueError("certificate could not be retrieved after approval")
                self.save_blockchain()
            except Exception as exc:
                submission.status = previous_status
                submission.certificate_id = previous_certificate_id
                if not existing_certificate and created_certificate_id:
                    self.originality_certificates = [
                        stored_certificate
                        for stored_certificate in self.originality_certificates
                        if stored_certificate.certificate_id != created_certificate_id
                    ]
                raise ValueError(f"Originality certificate creation failed: {exc}") from exc
            result["certificate_id"] = certificate.certificate_id
            result["certificate"] = certificate.to_dict()
            result["reason"] = "approved_by_vote"
        else:
            submission.transition_to(REJECTED)
            result["reason"] = "rejected_by_vote"

        result["status"] = submission.status
        return result

    def get_active_users(self, lookback_days=ACTIVE_USER_LOOKBACK_DAYS, now=None):
        return self.storage.count_active_users(
            submissions=self.submissions,
            votes=self.votes,
            pending_transactions=self.pending_transactions,
            chain=self.chain,
            lookback_days=lookback_days,
            now=now,
        )

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
        if submission.mint_blocked:
            raise ValueError(submission.mint_block_reason or "Submission is blocked from minting.")
        self.require_valid_certificate_for_submission(submission)
        if self.storage.mint_queue_contains(submission_id, self.mint_queue):
            raise ValueError("Submission is already in the mint queue.")

        self.mint_queue.append(submission_id)
        submission.transition_to(QUEUED)
        return submission

    def _queue_submission_record(self, submission, *, content_object=None, certificate=None):
        record = submission.to_dict()
        record["submission_status"] = submission.status
        record["certificate_status"] = "missing" if certificate is None else "valid"
        record["content_status"] = STORAGE_STATUS_MISSING
        record["storage_status"] = STORAGE_STATUS_MISSING
        record["content_metadata_missing"] = True
        record["missing_fields"] = []
        record["mintable"] = False
        record["mint_block_reason"] = None
        record["download_url"] = None

        if certificate is not None:
            record["certificate_id"] = certificate.certificate_id
            record["originality_score"] = certificate.originality_score
        else:
            record["originality_score"] = None

        record["mint_blocked"] = submission.mint_blocked
        record["mint_blocked_at"] = submission.mint_blocked_at
        record["mint_blocked_by"] = submission.mint_blocked_by
        record["mint_block_notes"] = submission.mint_block_notes

        if submission.mint_blocked:
            record["mintable"] = False
            record["mint_block_reason"] = submission.mint_block_reason or "mint_blocked_manually"
            record["certificate_status"] = "blocked"
            return record

        if submission.status == MINTED:
            record["mint_block_reason"] = "already_minted"
            record["missing_fields"].append("status")
            return record
        if submission.status != QUEUED:
            record["mint_block_reason"] = "submission_not_approved"
            record["missing_fields"].append("status")
            return record

        if certificate is None:
            record["mint_block_reason"] = "certificate_missing"
            record["missing_fields"].append("certificate_id")
            return record

        try:
            validate_certificate_for_submission(certificate, submission, network_name=NETWORK_NAME)
        except ValueError as exc:
            message = str(exc).lower()
            record["certificate_status"] = "invalid"
            if "content_hash" in message and "mismatch" in message:
                record["mint_block_reason"] = "certificate_content_hash_mismatch"
            elif "content_id" in message and "mismatch" in message:
                record["mint_block_reason"] = "certificate_content_hash_mismatch"
            else:
                record["mint_block_reason"] = "unknown_error"
            record["missing_fields"].append("certificate")
            record["validation_error"] = str(exc)
            return record

        if content_object is None:
            record["mint_block_reason"] = "content_metadata_missing"
            record["missing_fields"].extend(["content_hash", "content_id", "mime_type", "content_type"])
            return record

        record["content_metadata_missing"] = False
        record["content_id"] = content_object.content_id
        record["content_type"] = content_object.content_type
        record["mime_type"] = content_object.mime_type
        record["content_status"] = content_object.storage_status
        record["storage_status"] = content_object.storage_status
        if content_object.storage_status in {STORAGE_STATUS_LOCAL, STORAGE_STATUS_VERIFIED}:
            record["download_url"] = f"/content/{content_object.content_hash}"

        if content_object.storage_status == STORAGE_STATUS_REMOTE:
            record["mint_block_reason"] = "content_payload_missing"
            record["missing_fields"].append("content_payload")
            return record
        if content_object.storage_status == STORAGE_STATUS_MISSING:
            record["mint_block_reason"] = "content_metadata_missing"
            record["missing_fields"].append("content_payload")
            return record

        verification = verify_content_object_payload(content_object, data_dir=self.storage.data_dir)
        if not verification["verified"]:
            error = str(verification.get("error") or "").lower()
            if error == "legacy_unverifiable":
                record["mintable"] = True
                record["mint_block_reason"] = None
                record["content_metadata_missing"] = False
                record["content_status"] = content_object.storage_status
                record["storage_status"] = content_object.storage_status
                if content_object.storage_status in {STORAGE_STATUS_LOCAL, STORAGE_STATUS_VERIFIED}:
                    record["download_url"] = f"/content/{content_object.content_hash}"
                return record
            if error == "missing_file":
                record["mint_block_reason"] = "content_payload_missing"
            elif error == "legacy_unverifiable":
                record["mint_block_reason"] = "legacy_unverifiable_content"
            elif error in {"hash_mismatch", "file_size_mismatch"}:
                record["mint_block_reason"] = "content_hash_mismatch"
            else:
                record["mint_block_reason"] = "content_not_verified"
            record["missing_fields"].append("content_payload")
            record["verification_error"] = verification.get("error")
            return record

        record["mintable"] = True
        record["mint_block_reason"] = None
        record["missing_fields"] = []
        record["certificate_status"] = "valid"
        record["content_status"] = STORAGE_STATUS_VERIFIED if content_object.storage_status == STORAGE_STATUS_VERIFIED else content_object.storage_status
        return record

    def _evaluate_mint_queue_item(self, submission_id):
        submission = self.get_submission(submission_id)
        if submission is None:
            return {
                "submission_id": submission_id,
                "submission_status": None,
                "certificate_status": "missing",
                "content_status": STORAGE_STATUS_MISSING,
                "storage_status": STORAGE_STATUS_MISSING,
                "mintable": False,
                "mint_block_reason": "submission_not_found",
                "missing_fields": ["submission"],
                "content_metadata_missing": True,
                "mint_blocked": False,
                "mint_blocked_at": None,
                "mint_blocked_by": None,
                "mint_block_notes": None,
                "download_url": None,
            }

        content_object = None
        if submission.content_hash:
            content_object = self.get_content_object_by_hash(submission.content_hash)
        if content_object is None and submission.content_id:
            content_object = self.get_content_object(submission.content_id)

        certificate = self.get_originality_certificate_for_submission(submission.submission_id)
        record = self._queue_submission_record(
            submission,
            content_object=content_object,
            certificate=certificate,
        )
        if submission.status == QUEUED and certificate is None and record.get("mint_block_reason") == "certificate_missing":
            submission.status = APPROVED
            record["submission_status"] = APPROVED
        return record

    def get_mint_queue(self, include_blocked=True, mintable_only=False):
        queued_submissions = []
        for submission_id in self.mint_queue:
            record = self._evaluate_mint_queue_item(submission_id)
            if mintable_only and not record.get("mintable"):
                continue
            if not include_blocked and not record.get("mintable"):
                continue
            queued_submissions.append(record)

        return queued_submissions

    def _mint_submission_record(self, submission, certificate, miner=None, max_block_size_kb=500, validate_meme=True):
        block_added = self.add_block(
            image_path=submission.image_path,
            text_content=submission.text_content,
            miner=miner or submission.submitter,
            max_block_size_kb=max_block_size_kb,
            validate_meme=validate_meme,
            certificate=certificate,
        )
        if block_added:
            if submission.submission_id in self.mint_queue:
                self.mint_queue = [
                    queued_submission_id
                    for queued_submission_id in self.mint_queue
                    if queued_submission_id != submission.submission_id
                ]
            submission.transition_to(MINTED)
        return block_added

    def mint_next_queued_submission(self, miner=None, max_block_size_kb=500, validate_meme=True):
        if not self.mint_queue:
            raise ValueError("Mint queue is empty.")

        blocked_records = []
        for submission_id in self.mint_queue:
            submission = self.get_submission(submission_id)
            if submission is not None and submission.status == HARD_REJECTED:
                raise ValueError("Hard rejected submissions cannot become blocks.")
            record = self._evaluate_mint_queue_item(submission_id)
            if record.get("mintable"):
                certificate = self.require_valid_certificate_for_submission(submission)
                return self._mint_submission_record(
                    submission,
                    certificate,
                    miner=miner,
                    max_block_size_kb=max_block_size_kb,
                    validate_meme=validate_meme,
                )
            if record.get("mint_block_reason") in {
                "content_metadata_missing",
                "content_payload_missing",
                "legacy_unverifiable_content",
                "content_not_verified",
            }:
                submission = self.get_submission(submission_id)
                certificate = self._resolve_mintable_submission_certificate(submission)
                if certificate is not None:
                    return self._mint_submission_record(
                        submission,
                        certificate,
                        miner=miner,
                        max_block_size_kb=max_block_size_kb,
                        validate_meme=validate_meme,
                    )
            blocked_records.append(record)

        blocked_summary = ", ".join(
            f"{record['submission_id'][:8]}:{record.get('mint_block_reason') or 'unknown_error'}"
            for record in blocked_records[:5]
        )
        raise ValueError(
            "No mintable submissions in the queue. "
            f"Blocked items: {blocked_summary or 'none'}."
        )

    def mint_submission(self, submission_id, miner=None, max_block_size_kb=500, validate_meme=True):
        submission = self.get_submission(submission_id)
        if submission is None:
            raise ValueError(f"Submission not found: {submission_id}")
        if submission.status == HARD_REJECTED:
            raise ValueError("Hard rejected submissions cannot become blocks.")
        if submission.status == MINTED:
            raise ValueError("Submission has already been minted.")
        if submission.status not in {APPROVED, QUEUED}:
            raise ValueError("Only approved unminted submissions can be minted.")

        if submission.status == APPROVED:
            submission = self.add_to_mint_queue(submission_id)

        record = self._evaluate_mint_queue_item(submission_id)
        if not record.get("mintable"):
            if record.get("mint_block_reason") in {
                "content_metadata_missing",
                "content_payload_missing",
                "legacy_unverifiable_content",
                "content_not_verified",
            }:
                certificate = self._resolve_mintable_submission_certificate(submission)
                if certificate is not None:
                    return self._mint_submission_record(
                        submission,
                        certificate,
                        miner=miner,
                        max_block_size_kb=max_block_size_kb,
                        validate_meme=validate_meme,
                    )
            raise ValueError(record.get("mint_block_reason") or "Submission is not mintable.")

        certificate = self.require_valid_certificate_for_submission(submission)
        return self._mint_submission_record(
            submission,
            certificate,
            miner=miner,
            max_block_size_kb=max_block_size_kb,
            validate_meme=validate_meme,
        )

    def block_minting_for_submission(self, submission_id, reason, notes=None, blocked_by=None):
        submission = self.get_submission(submission_id)
        if submission is None:
            raise ValueError(f"Submission not found: {submission_id}")
        if submission.status == MINTED:
            raise ValueError("Minted submissions cannot be blocked from minting.")
        submission.mint_blocked = True
        submission.mint_block_reason = (reason or "mint_blocked_manually").strip() or "mint_blocked_manually"
        submission.mint_blocked_at = time.time()
        submission.mint_blocked_by = blocked_by
        submission.mint_block_notes = notes
        return submission

    def _resolve_mintable_submission_certificate(self, submission):
        if submission is None:
            return None
        if submission.mint_blocked:
            return None
        certificate = self.require_valid_certificate_for_submission(submission)
        transient_content_object = self.get_content_object_by_hash(submission.content_hash)
        if transient_content_object is None:
            transient_content_object = self._build_content_object_for_submission(
                submission,
                image_path=submission.image_path,
                text_content=submission.text_content,
            )
        if transient_content_object is None:
            return None

        verification = verify_content_object_payload(transient_content_object, data_dir=self.storage.data_dir)
        if verification["verified"]:
            if transient_content_object.content_id and submission.content_id != transient_content_object.content_id:
                submission.content_id = transient_content_object.content_id
            return certificate
        if verification.get("error") == "legacy_unverifiable" and (
            transient_content_object.local_path or submission.image_path or submission.text_content
        ):
            if transient_content_object.content_id and submission.content_id != transient_content_object.content_id:
                submission.content_id = transient_content_object.content_id
            return certificate
        return None

    def unblock_minting_for_submission(self, submission_id):
        submission = self.get_submission(submission_id)
        if submission is None:
            raise ValueError(f"Submission not found: {submission_id}")
        submission.mint_blocked = False
        submission.mint_block_reason = None
        submission.mint_blocked_at = None
        submission.mint_blocked_by = None
        submission.mint_block_notes = None
        return submission

    def cleanup_bad_mint_queue_items(self, *, block_unmintable=False):
        report = {
            "checked": 0,
            "mintable": 0,
            "blocked": 0,
            "items": [],
        }
        candidate_ids = [
            submission_id
            for submission_id in self.mint_queue
            if self.get_submission(submission_id) is not None
        ]
        for submission in self.submissions:
            if submission.status in {APPROVED, QUEUED} and submission.submission_id not in candidate_ids:
                candidate_ids.append(submission.submission_id)

        for submission_id in candidate_ids:
            record = self._evaluate_mint_queue_item(submission_id)
            report["checked"] += 1
            if record.get("mintable"):
                report["mintable"] += 1
                continue
            report["blocked"] += 1
            report["items"].append(
                {
                    "submission_id": submission_id,
                    "content_hash": record.get("content_hash"),
                    "mintable": False,
                    "reason": record.get("mint_block_reason") or "unknown_error",
                }
            )
            if block_unmintable and record.get("submission_status") in {APPROVED, QUEUED}:
                try:
                    self.block_minting_for_submission(
                        submission_id,
                        reason=record.get("mint_block_reason") or "mint_blocked_manually",
                        notes="Auto-blocked by cleanup_bad_mint_queue_items.",
                        blocked_by="dev-cleanup",
                    )
                except ValueError:
                    continue

        return report

    def remove_invalid_mint_queue_entries(self):
        valid_queue = []
        removed_entries = []
        for submission_id in self.mint_queue:
            submission = self.get_submission(submission_id)
            try:
                certificate_ready = (
                    submission
                    and submission.status == QUEUED
                    and self.require_valid_certificate_for_submission(submission)
                )
            except ValueError:
                certificate_ready = False

            if certificate_ready:
                valid_queue.append(submission_id)
            else:
                if submission and submission.status == QUEUED:
                    submission.status = APPROVED
                if submission and not self.get_originality_certificate_for_submission(submission.submission_id):
                    submission.certificate_id = None
                removed_entries.append(submission_id)

        self.mint_queue = valid_queue
        return removed_entries

    def remove_invalid_mint_queue_entries(self):
        valid_queue = []
        removed_entries = []
        for submission_id in self.mint_queue:
            submission = self.get_submission(submission_id)
            try:
                certificate_ready = (
                    submission
                    and submission.status == QUEUED
                    and self.require_valid_certificate_for_submission(submission)
                )
            except ValueError:
                certificate_ready = False

            if certificate_ready:
                valid_queue.append(submission_id)
            else:
                if submission and submission.status == QUEUED:
                    submission.status = APPROVED
                if submission and not self.get_originality_certificate_for_submission(submission.submission_id):
                    submission.certificate_id = None
                removed_entries.append(submission_id)

        self.mint_queue = valid_queue
        return removed_entries

    def add_block(
        self,
        image_path,
        text_content=None,
        miner=None,
        max_block_size_kb=500,
        validate_meme=True,
        certificate=None,
    ):
        """
        Add a block with tip distribution, enforce block size limit, and validate memes.
        """
        if not self.is_valid_public_key(miner):
            print(f"Debug: Invalid miner public key: {miner}")
            raise ValueError(f"Invalid public key provided for the miner.")

        file_exists = bool(image_path) and os.path.isfile(image_path)
        file_extension = os.path.splitext(image_path)[1].lower() if image_path else ""
        guessed_mime_type = guess_mime_type(os.path.basename(image_path), "image/jpeg") if file_exists else ""
        is_text_payload = bool(text_content and text_content.strip()) and (
            not file_exists
            or guessed_mime_type == TEXT_MIME_TYPE
            or file_extension == ".txt"
        )

        if not file_exists and not is_text_payload:
            print(f"Debug: Image path {image_path} does not exist.")
            raise ValueError("Invalid image path provided for the meme.")

        # Extract text content if not provided.
        if not text_content:
            if is_text_payload and file_exists:
                print("Debug: Reading text content from the stored text payload.")
                with open(image_path, "r", encoding="utf-8") as text_file:
                    text_content = text_file.read()
            else:
                print("Debug: Extracting text content from the image.")
                text_content = extract_text(image_path)
            if not text_content:
                print(f"Debug: No text extracted from image {image_path}.")
                raise ValueError("No text content could be extracted from the image.")

        # ✅ Meme Validation Check
        normalized_text = re.sub(r'[^\w\s]', '', text_content).strip().lower()  # Normalize text
        if is_text_payload:
            image_hash = compute_text_content_hash(text_content)
        else:
            image_hash = hash_image(image_path)  # Compute image hash

        if validate_meme:
            if is_text_payload:
                if normalized_text in self.texts:
                    print(f"Debug: Duplicate text payload detected: '{normalized_text}' already exists.")
                    raise ValueError("This meme has already been submitted.")
            elif image_hash in self.image_hashes and normalized_text in self.texts:
                print(f"Debug: Duplicate meme detected! Image hash {image_hash} and text '{normalized_text}' already exist.")
                raise ValueError("This meme has already been submitted.")

        # Encode the payload for block storage.
        if is_text_payload:
            print("Debug: Encoding text payload for block storage.")
            meme_encoded = base64.b64encode(text_content.encode("utf-8")).decode("utf-8")
        else:
            print(f"Debug: Encoding image at path {image_path}.")
            meme_encoded = self.encode_image(image_path)

        # âœ… Calculate meme size (base64 encoding increases size)
        meme_size_kb = len(meme_encoded) / 1024
        text_size_kb = len(text_content.encode()) / 1024  # Convert text content size to KB

        # Validate transactions and calculate total tips
        valid_transactions = []
        total_tx_size_kb = 0  # âœ… Track total transaction size
        total_miner_tips = 0  # âœ… Only track minerâ€™s tip earnings

        print("Debug: Validating transactions concurrently...")
        with ThreadPoolExecutor() as executor:
            future_to_tx = {executor.submit(self.validate_transaction, tx): tx for tx in self.pending_transactions}
            for future in future_to_tx:
                tx = future_to_tx[future]
                try:
                    if future.result():
                        tip = tx.tip  # âœ… Keep tip logic

                        # âœ… Tip Distribution (Existing Model)
                        if self.reward_pool < (self.initial_reward_pool * 0.25):
                            tip_split = {"miner": 0.25, "reward_pool": 0.75}
                        else:
                            tip_split = {"miner": 0.5, "reward_pool": 0.5}

                        miner_tip_share = tip * tip_split["miner"]
                        reward_pool_tip_share = tip * tip_split["reward_pool"]

                        # âœ… Add to balances
                        self.reward_pool += reward_pool_tip_share  # âœ… Only tips go to reward pool
                        total_miner_tips += miner_tip_share  # âœ… Miner gets tip only

                        # âœ… Debugging Output
                        print(f"Debug: Transaction Distribution - Tip Total: {tip:.4f}")
                        print(f"Debug: - Miner gets: {miner_tip_share:.4f}")
                        print(f"Debug: - Reward Pool gets: {reward_pool_tip_share:.4f}")

                        tx_size_kb = len(str(tx)) / 1024  # âœ… Convert transaction size to KB
                        total_tx_size_kb += tx_size_kb
                        valid_transactions.append(tx)
                except Exception as e:
                    print(f"Debug: Transaction validation error: {e}")

        # âœ… Calculate total block size
        total_block_size_kb = meme_size_kb + text_size_kb + total_tx_size_kb

        # âœ… Enforce block size limit
        if total_block_size_kb > max_block_size_kb:
            print(f"Debug: Block size {total_block_size_kb:.2f} KB exceeds max limit of {max_block_size_kb} KB. Rejecting block.")
            return False

        print(f"Debug: Final block size: {total_block_size_kb:.2f} KB (within limit: {max_block_size_kb} KB)")

        # âœ… Ensure minerâ€™s balance is updated
        if miner in self.wallets:
            current_balance = self.get_balance(miner)  # âœ… Get miner's balance
            updated_balance = current_balance + total_miner_tips  # âœ… Add miner's earnings
            print(f"Debug: Before crediting miner {miner}: {current_balance:.4f} {COIN_NAME}")
            print(f"Debug: Miner earned: {total_miner_tips:.4f} {COIN_NAME}")

            # âœ… Store the updated balance at the blockchain level
            self.wallets[miner].stored_balance = updated_balance  # âœ… Store updated balance

            print(f"Debug: After crediting miner {miner}: {self.wallets[miner].stored_balance:.4f} {COIN_NAME}")
        else:
            print(f"Debug: WARNING! Miner {miner} not found in registered wallets. Initializing new wallet.")

            # âœ… Initialize the miner's wallet with the earned balance
            self.wallets[miner] = Wallet()
            self.wallets[miner].public_key = miner
            self.wallets[miner].private_key = None  # Minerâ€™s private key is unknown
            self.wallets[miner].stored_balance = total_miner_tips  # âœ… Store the initial balance
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
            **(self.certificate_block_metadata(certificate) if certificate else {}),
        )
        self.chain.append(new_block)
        self.pending_transactions = [tx for tx in self.pending_transactions if tx not in valid_transactions]

        # âœ… Cache meme data after block is added
        print(f"Debug: Caching meme data for image {image_path}.")
        self.image_hashes.add(image_hash)
        self.texts.append(normalized_text)

        print(f"Block {new_block.index} added with meme: {text_content}. Final size: {total_block_size_kb:.2f} KB.")
        print(f"Miner earned: {total_miner_tips:.4f} {COIN_NAME}.")

        self.save_blockchain()

        return True

    def get_latest_block(self):
        return self.chain[-1]

    def get_block_by_hash(self, block_hash):
        return self.storage.get_block_by_hash(block_hash, self.chain)

    def get_block_by_height(self, height):
        return self.storage.get_block_by_height(height, self.chain)

    @staticmethod
    def calculate_cumulative_originality_score(chain):
        cumulative_score = 0
        for block in chain:
            if isinstance(block, dict):
                if block.get("index") == 0:
                    continue
                originality_score = block.get("originality_score", 0)
            else:
                if getattr(block, "index", None) == 0:
                    continue
                originality_score = getattr(block, "originality_score", 0)

            if originality_score is not None:
                cumulative_score += originality_score

        return round(cumulative_score, 8)

    def get_cumulative_originality_score(self):
        return self.calculate_cumulative_originality_score(self.chain)

    @staticmethod
    def chain_to_dicts(chain):
        return [
            block.to_dict() if hasattr(block, "to_dict") else block
            for block in chain
        ]

    @staticmethod
    def chain_height(chain_dicts):
        if not chain_dicts:
            return None
        return chain_dicts[-1].get("index")

    @staticmethod
    def chain_latest_hash(chain_dicts):
        if not chain_dicts:
            return None
        return chain_dicts[-1].get("hash")

    def compare_chains_by_originality(self, local_chain, candidate_chain):
        local_chain_dicts = self.chain_to_dicts(local_chain)
        candidate_chain_dicts = self.chain_to_dicts(candidate_chain)
        local_score = self.calculate_cumulative_originality_score(local_chain_dicts)
        candidate_score = self.calculate_cumulative_originality_score(candidate_chain_dicts)
        local_height = self.chain_height(local_chain_dicts)
        candidate_height = self.chain_height(candidate_chain_dicts)
        local_latest_hash = self.chain_latest_hash(local_chain_dicts)
        candidate_latest_hash = self.chain_latest_hash(candidate_chain_dicts)

        result = {
            "local_score": local_score,
            "candidate_score": candidate_score,
            "local_height": local_height,
            "candidate_height": candidate_height,
            "local_latest_hash": local_latest_hash,
            "candidate_latest_hash": candidate_latest_hash,
        }

        if not local_chain_dicts or not candidate_chain_dicts:
            return {
                **result,
                "decision": "invalid_candidate",
                "preferred": "local",
                "reason": "candidate_chain_invalid",
            }
        if candidate_chain_dicts[0].get("hash") != local_chain_dicts[0].get("hash"):
            return {
                **result,
                "decision": "invalid_candidate",
                "preferred": "local",
                "reason": "different_genesis_hash",
            }
        if not self.is_chain_valid(candidate_chain_dicts):
            return {
                **result,
                "decision": "invalid_candidate",
                "preferred": "local",
                "reason": "candidate_chain_invalid",
            }
        if candidate_score > local_score:
            return {
                **result,
                "decision": "replace_with_candidate",
                "preferred": "candidate",
                "reason": "higher_originality_score",
            }
        if candidate_score < local_score:
            return {
                **result,
                "decision": "keep_local",
                "preferred": "local",
                "reason": "lower_originality_score",
            }
        if candidate_height > local_height:
            return {
                **result,
                "decision": "replace_with_candidate",
                "preferred": "candidate",
                "reason": "higher_chain_height",
            }
        if candidate_height < local_height:
            return {
                **result,
                "decision": "keep_local",
                "preferred": "local",
                "reason": "lower_chain_height",
            }
        if candidate_latest_hash < local_latest_hash:
            return {
                **result,
                "decision": "replace_with_candidate",
                "preferred": "candidate",
                "reason": "lower_latest_block_hash",
            }
        if candidate_latest_hash > local_latest_hash:
            return {
                **result,
                "decision": "keep_local",
                "preferred": "local",
                "reason": "higher_latest_block_hash",
            }
        return {
            **result,
            "decision": "equivalent",
            "preferred": "equivalent",
            "reason": "same_latest_block_hash",
        }

    def extract_block_certificate_metadata(self, block_dict):
        fields = [
            "submission_id",
            "certificate_id",
            "content_hash",
            "content_id",
            "content_type",
            "mime_type",
            "creator_wallet",
            "vote_hash",
            "approval_percentage",
            "decisive_vote_total",
            "minimum_votes_required",
            "approved_at",
            "originality_score",
        ]
        meme = block_dict.get("meme") if isinstance(block_dict.get("meme"), dict) else {}
        metadata = {}
        for field_name in fields:
            if block_dict.get(field_name) is not None:
                metadata[field_name] = block_dict.get(field_name)
            elif meme.get(field_name) is not None:
                metadata[field_name] = meme.get(field_name)
        return metadata

    def validate_block_certificate_metadata(self, block_dict):
        if block_dict.get("index") == 0:
            return True

        metadata = self.extract_block_certificate_metadata(block_dict)
        if not metadata:
            return True

        required_fields = [
            "submission_id",
            "certificate_id",
            "content_hash",
            "creator_wallet",
            "vote_hash",
            "approval_percentage",
            "decisive_vote_total",
            "minimum_votes_required",
            "approved_at",
            "originality_score",
        ]
        for field_name in required_fields:
            if field_name not in metadata:
                raise ValueError(f"Block certificate metadata missing {field_name}.")

        certificate = self.get_originality_certificate(metadata["certificate_id"])
        if not certificate:
            raise ValueError("Block references unknown originality certificate.")

        if certificate.submission_id != metadata["submission_id"]:
            raise ValueError("Block certificate_id does not match block submission_id.")
        if certificate.content_hash != metadata["content_hash"]:
            raise ValueError("Block certificate content_hash does not match block content_hash.")
        if metadata.get("content_id") is not None:
            certificate_content_id = getattr(certificate, "content_id", None)
            if certificate_content_id is not None and certificate_content_id != metadata["content_id"]:
                raise ValueError("Block content_id does not match certificate content_id.")

        submission = self.get_submission(metadata["submission_id"])
        if submission:
            validate_certificate_for_submission(certificate, submission, network_name=NETWORK_NAME)
            if metadata["content_hash"] != submission.content_hash:
                raise ValueError("Block content_hash does not match submission.")
            if metadata.get("content_id") is not None and metadata["content_id"] != submission.content_id:
                raise ValueError("Block content_id does not match submission.")

        for field_name in required_fields:
            certificate_value = getattr(certificate, field_name)
            if metadata[field_name] != certificate_value:
                raise ValueError(f"Block certificate metadata {field_name} does not match certificate.")

        content_object = self.get_content_object_by_hash(metadata["content_hash"])
        if content_object is not None:
            if metadata.get("content_id") is not None and metadata["content_id"] != content_object.content_id:
                raise ValueError("Block content_id does not match content object.")
            if metadata.get("content_type") is not None and metadata["content_type"] != content_object.content_type:
                if not (
                    content_object.storage_status in {STORAGE_STATUS_REMOTE, STORAGE_STATUS_MISSING}
                    and content_object.content_type == CONTENT_TYPE_IMAGE
                    and metadata["content_type"] in {CONTENT_TYPE_MIXED, CONTENT_TYPE_TEXT}
                ):
                    raise ValueError("Block content_type does not match content object.")
            if metadata.get("mime_type") is not None and metadata["mime_type"] != content_object.mime_type:
                if not (
                    content_object.storage_status in {STORAGE_STATUS_REMOTE, STORAGE_STATUS_MISSING}
                    and content_object.mime_type == "application/octet-stream"
                ):
                    raise ValueError("Block mime_type does not match content object.")
            if content_object.storage_status == STORAGE_STATUS_VERIFIED:
                verification = verify_content_object_payload(content_object, data_dir=self.storage.data_dir)
                if not verification["verified"]:
                    raise ValueError("Verified local content file does not match block content_hash.")

        return True

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

            try:
                self.validate_block_certificate_metadata(current_block)
            except ValueError as e:
                print(f"Debug: Block {current_block['index']} certificate metadata is invalid: {e}")
                return False

        return True

    def get_balance(self, public_key):
        """Calculate balance based on transaction history and tips (NO FEES)."""
        balance = 0
        for block in self.chain:
            for transaction in block.transactions:
                if transaction.sender == public_key:
                    balance -= transaction.amount + transaction.tip  # âœ… Deduct amount + tip (NO FEE)
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
            total_deduction = transaction.amount + transaction.tip  # âœ… Only deduct amount + tip (NO FEE)
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
            total_deduction = transaction.amount + transaction.tip  # âœ… Only deduct amount + tip (NO FEE)
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
        """Replace the current chain only when the originality fork-choice rule prefers it."""
        comparison = self.compare_chains_by_originality(self.chain, new_chain)
        if comparison["decision"] == "replace_with_candidate":
            self.chain = new_chain
            print(f"Debug: Replaced local chain: {comparison['reason']}.")
            return True
        print(f"Debug: Received chain not selected: {comparison['reason']}.")
        return False
    
    def calculate_hash_from_dict(self, block_dict):
        """Calculate the hash for a block dictionary."""
        transaction_data = "".join(
            [
                f"{tx['sender']}{tx['recipient']}{_hash_number(tx['amount'])}{_hash_number(tx['tip'])}{_hash_number(tx['payload_size_kb'])}{tx['signature']}"
                for tx in block_dict["transactions"]
            ]
        )
        certificate_data = ""
        certificate_metadata = self.extract_block_certificate_metadata(block_dict)
        if certificate_metadata:
            certificate_data = json.dumps(
                certificate_metadata,
                sort_keys=True,
                separators=(",", ":"),
            )
        block_string = f"{block_dict['index']}{block_dict['previous_hash']}{block_dict['timestamp']}{transaction_data}{block_dict['meme']}{block_dict['miner']}{certificate_data}"
        return hashlib.sha256(block_string.encode()).hexdigest()
    
    def is_valid_public_key(self, public_key):
        """Check if the given public key is valid."""
        if is_valid_ethereum_address(str(public_key or "").strip()):
            return True
        if public_key in self.wallets:
            return True
        print(f"Debug: Invalid public key: {public_key}")
        return False
    


