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
        creator_wallet=None,
        vote_hash=None,
        approval_percentage=None,
        decisive_vote_total=None,
        minimum_votes_required=None,
        approved_at=None,
        originality_score=None,
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
        self.creator_wallet = creator_wallet
        self.vote_hash = vote_hash
        self.approval_percentage = approval_percentage
        self.decisive_vote_total = decisive_vote_total
        self.minimum_votes_required = minimum_votes_required
        self.approved_at = approved_at
        self.originality_score = originality_score
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
            "creator_wallet": self.creator_wallet,
            "vote_hash": self.vote_hash,
            "approval_percentage": self.approval_percentage,
            "decisive_vote_total": self.decisive_vote_total,
            "minimum_votes_required": self.minimum_votes_required,
            "approved_at": self.approved_at,
            "originality_score": self.originality_score,
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
        block_string = f"{self.index}{self.previous_hash}{self.timestamp}{transaction_data}{self.meme}{self.miner}{certificate_data}"
        return hashlib.sha256(block_string.encode()).hexdigest()
