### block.py
# Import statements
import hashlib

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
            "meme": self.meme,
            "timestamp": self.timestamp,
            "hash": self.hash,
        }

    def calculate_hash(self):
        """Calculate the hash of the block."""
        transaction_data = "".join(
            [f"{tx.sender}{tx.recipient}{tx.amount}{tx.tip}{tx.payload_size_kb}{tx.signature}" for tx in self.transactions]
        )
        block_string = f"{self.index}{self.previous_hash}{self.timestamp}{transaction_data}{self.meme}{self.miner}"
        return hashlib.sha256(block_string.encode()).hexdigest()
