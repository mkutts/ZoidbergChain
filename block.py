import hashlib
import json

def _hash_number(value):
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        numeric_value = float(value)
        if numeric_value.is_integer():
            return str(int(numeric_value))
        return str(numeric_value)
    return str(value)


class Block:
    def __init__(
        self,
        index,
        previous_hash,
        timestamp,
        transactions,
        miner,
        meme=None,
        hash=None,
        submission_id=None,
        certificate_id=None,
        content_hash=None,
        original_content_hash=None,
        content_id=None,
        content_type=None,
        mime_type=None,
        compression_algorithm=None,
        compression_version=None,
        canonical_size_bytes=None,
        original_size_bytes=None,
        creator_wallet=None,
        vote_hash=None,
        approval_percentage=None,
        decisive_vote_total=None,
        minimum_votes_required=None,
        minimum_decisive_votes_required=None,
        approved_at=None,
        originality_score=None,
        reward_type=None,
        reward_recipient=None,
        reward_amount=None,
        reward_source=None,
        minted_at=None,
        voter_rewards=None,
        native_transactions=None,
        transaction_ids=None,
        transaction_count=None,
        transactions_hash=None,
    ):
        self.index = index
        self.previous_hash = previous_hash
        self.timestamp = timestamp
        self.transactions = transactions
        self.miner = miner
        self.meme = meme or "default-meme"
        self.submission_id = submission_id
        self.certificate_id = certificate_id
        self.content_hash = content_hash
        self.original_content_hash = original_content_hash
        self.content_id = content_id
        self.content_type = content_type
        self.mime_type = mime_type
        self.compression_algorithm = compression_algorithm
        self.compression_version = compression_version
        self.canonical_size_bytes = canonical_size_bytes
        self.original_size_bytes = original_size_bytes
        self.creator_wallet = creator_wallet
        self.vote_hash = vote_hash
        self.approval_percentage = approval_percentage
        self.decisive_vote_total = decisive_vote_total
        self.minimum_votes_required = minimum_votes_required
        self.minimum_decisive_votes_required = (
            minimum_decisive_votes_required
            if minimum_decisive_votes_required is not None
            else minimum_votes_required
        )
        self.approved_at = approved_at
        self.originality_score = originality_score
        self.reward_type = reward_type
        self.reward_recipient = reward_recipient
        self.reward_amount = reward_amount
        self.reward_source = reward_source
        self.minted_at = minted_at
        self.voter_rewards = list(voter_rewards or [])
        self.native_transactions = list(native_transactions or [])
        self.transaction_ids = list(transaction_ids or [tx.get("tx_id") for tx in self.native_transactions if isinstance(tx, dict) and tx.get("tx_id")])
        self.transaction_count = int(transaction_count if transaction_count is not None else len(self.native_transactions))
        self.transactions_hash = transactions_hash
        self.hash = hash or self.calculate_hash()

    def to_dict(self):
        """Convert block to a dictionary."""
        block_dict = {
            "index": self.index,
            "transactions": [tx.to_dict() for tx in self.transactions],
            "previous_hash": self.previous_hash,
            "miner": self.miner,
            "meme": self.meme,
            "timestamp": self.timestamp,
            "hash": self.hash,
        }
        block_dict.update(self.certificate_metadata())
        return block_dict

    def certificate_metadata(self):
        metadata = {
            "submission_id": self.submission_id,
            "certificate_id": self.certificate_id,
            "content_hash": self.content_hash,
            "original_content_hash": self.original_content_hash,
            "content_id": self.content_id,
            "content_type": self.content_type,
            "mime_type": self.mime_type,
            "compression_algorithm": self.compression_algorithm,
            "compression_version": self.compression_version,
            "canonical_size_bytes": self.canonical_size_bytes,
            "original_size_bytes": self.original_size_bytes,
            "creator_wallet": self.creator_wallet,
            "vote_hash": self.vote_hash,
            "approval_percentage": self.approval_percentage,
            "decisive_vote_total": self.decisive_vote_total,
            "minimum_votes_required": self.minimum_votes_required,
            "minimum_decisive_votes_required": self.minimum_decisive_votes_required,
            "approved_at": self.approved_at,
            "originality_score": self.originality_score,
            "reward_type": self.reward_type,
            "reward_recipient": self.reward_recipient,
            "reward_amount": self.reward_amount,
            "reward_source": self.reward_source,
            "minted_at": self.minted_at,
            "voter_rewards": self.voter_rewards or None,
            "native_transactions": self.native_transactions or None,
            "transaction_ids": self.transaction_ids or None,
            "transaction_count": self.transaction_count if self.native_transactions else None,
            "transactions_hash": self.transactions_hash,
        }
        return {
            key: value
            for key, value in metadata.items()
            if value is not None
        }

    def calculate_hash(self):
        """Calculate the hash of the block."""
        transaction_data = "".join(
            [
                f"{tx.sender}{tx.recipient}{_hash_number(tx.amount)}{_hash_number(tx.tip)}{_hash_number(tx.payload_size_kb)}{tx.signature}"
                for tx in self.transactions
            ]
        )
        certificate_data = ""
        if self.certificate_metadata():
            certificate_data = json.dumps(
                self.certificate_metadata(),
                sort_keys=True,
                separators=(",", ":"),
            )
        meme_data = json.dumps(
            self.meme,
            sort_keys=True,
            separators=(",", ":"),
        )
        block_string = f"{self.index}{self.previous_hash}{self.timestamp}{transaction_data}{meme_data}{self.miner}{certificate_data}"
        return hashlib.sha256(block_string.encode()).hexdigest()
