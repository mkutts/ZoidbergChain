import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Any

from protocol_v1 import (
    OBJECT_TYPE_BLOCK,
    PROTOCOL_VERSION,
    canonical_domain_bytes,
    decode_canonical_bytes,
    encode_canonical_bytes,
    normalize_network_id,
)
from protocol_v1_genesis import (
    PUBLIC_TESTNET_V1_GENESIS_VERSION,
    canonical_public_testnet_v1_genesis_hash,
    canonical_public_testnet_v1_genesis_payload_from_record,
)
from transaction import Transaction


PROTOCOL_V1_BLOCK_VERSION = PROTOCOL_VERSION


def _hash_number(value):
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        numeric_value = float(value)
        if numeric_value.is_integer():
            return str(int(numeric_value))
        return str(numeric_value)
    return str(value)


def _normalize_decimal_string(value: Any, *, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} is required.")
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be numeric.")

    candidate = value.strip() if isinstance(value, str) else value
    if candidate == "":
        raise ValueError(f"{field_name} is required.")
    try:
        decimal_value = Decimal(str(candidate))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric.") from exc
    if not decimal_value.is_finite():
        raise ValueError(f"{field_name} must be finite.")

    normalized = format(decimal_value, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    if normalized in {"", "-0"}:
        normalized = "0"
    return normalized


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
        block_version=None,
        genesis_version=None,
        protocol_version=None,
        network_id=None,
        media_hash=None,
        media_bytes=None,
        submission_id=None,
        certificate_id=None,
        content_hash=None,
        content_id=None,
        content_type=None,
        mime_type=None,
        creator_wallet=None,
        vote_hash=None,
        approval_percentage=None,
        decisive_vote_total=None,
        minimum_votes_required=None,
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
        total_supply=None,
        initial_reward_pool=None,
    ):
        self.index = index
        self.previous_hash = previous_hash
        self.timestamp = timestamp
        self.transactions = list(transactions or [])
        self.miner = miner
        self.meme = meme or "default-meme"
        self.block_version = block_version
        self.genesis_version = genesis_version
        self.protocol_version = protocol_version
        self.network_id = normalize_network_id(network_id) if network_id is not None else None
        self.media_hash = media_hash
        self.media_bytes = self._coerce_media_bytes(media_bytes)
        self.submission_id = submission_id
        self.certificate_id = certificate_id
        self.content_hash = content_hash
        self.content_id = content_id
        self.content_type = content_type
        self.mime_type = mime_type
        self.creator_wallet = creator_wallet
        self.vote_hash = vote_hash
        self.approval_percentage = approval_percentage
        self.decisive_vote_total = decisive_vote_total
        self.minimum_votes_required = minimum_votes_required
        self.approved_at = approved_at
        self.originality_score = originality_score
        self.reward_type = reward_type
        self.reward_recipient = reward_recipient
        self.reward_amount = reward_amount
        self.reward_source = reward_source
        self.minted_at = minted_at
        self.voter_rewards = list(voter_rewards or [])
        self.native_transactions = [dict(transaction) for transaction in (native_transactions or [])]
        self.transaction_ids = list(
            transaction_ids
            or [
                tx.get("tx_id")
                for tx in self.native_transactions
                if isinstance(tx, dict) and tx.get("tx_id")
            ]
        )
        self.transaction_count = int(transaction_count if transaction_count is not None else len(self.native_transactions))
        self.transactions_hash = transactions_hash
        self.total_supply = total_supply
        self.initial_reward_pool = initial_reward_pool
        self.hash = hash or self.calculate_hash()

    @staticmethod
    def _coerce_media_bytes(value):
        if value is None:
            return None
        if isinstance(value, (bytes, bytearray, memoryview)):
            return bytes(value)
        return decode_canonical_bytes(value)

    @staticmethod
    def _transaction_to_dict(transaction):
        if isinstance(transaction, Transaction):
            return transaction.to_dict()
        if hasattr(transaction, "to_dict"):
            return transaction.to_dict()
        if isinstance(transaction, dict):
            return dict(transaction)
        raise ValueError("Block transactions must provide to_dict().")

    @classmethod
    def from_dict(cls, block_data):
        return cls(
            index=block_data["index"],
            previous_hash=block_data["previous_hash"],
            timestamp=block_data["timestamp"],
            transactions=[
                transaction
                if isinstance(transaction, Transaction)
                else Transaction.from_dict(transaction)
                for transaction in block_data["transactions"]
            ],
            miner=block_data["miner"],
            meme=block_data.get("meme", {}),
            hash=block_data.get("hash"),
            block_version=block_data.get("block_version"),
            genesis_version=block_data.get("genesis_version"),
            protocol_version=block_data.get("protocol_version"),
            network_id=block_data.get("network_id"),
            media_hash=block_data.get("media_hash"),
            media_bytes=block_data.get("media_bytes"),
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
            reward_type=block_data.get("reward_type"),
            reward_recipient=block_data.get("reward_recipient"),
            reward_amount=block_data.get("reward_amount"),
            reward_source=block_data.get("reward_source"),
            minted_at=block_data.get("minted_at"),
            voter_rewards=block_data.get("voter_rewards", []),
            native_transactions=block_data.get("native_transactions", []),
            transaction_ids=block_data.get("transaction_ids"),
            transaction_count=block_data.get("transaction_count"),
            transactions_hash=block_data.get("transactions_hash"),
            total_supply=block_data.get("total_supply"),
            initial_reward_pool=block_data.get("initial_reward_pool"),
        )

    def is_protocol_v1_block(self) -> bool:
        return self.block_version == PROTOCOL_V1_BLOCK_VERSION

    def is_protocol_v1_genesis_block(self) -> bool:
        return self.genesis_version == PUBLIC_TESTNET_V1_GENESIS_VERSION

    def protocol_v1_metadata(self, *, include_media_bytes=True):
        metadata = {
            "block_version": self.block_version,
            "genesis_version": self.genesis_version,
            "protocol_version": self.protocol_version,
            "network_id": self.network_id,
            "media_hash": self.media_hash,
            "total_supply": self.total_supply,
            "initial_reward_pool": self.initial_reward_pool,
        }
        if include_media_bytes and self.media_bytes is not None:
            metadata["media_bytes"] = encode_canonical_bytes(self.media_bytes)
        return {
            key: value
            for key, value in metadata.items()
            if value is not None
        }

    def to_dict(self, *, include_media_bytes=True):
        block_dict = {
            "index": self.index,
            "transactions": [self._transaction_to_dict(tx) for tx in self.transactions],
            "previous_hash": self.previous_hash,
            "miner": self.miner,
            "meme": self.meme,
            "timestamp": self.timestamp,
            "hash": self.hash,
        }
        block_dict.update(self.protocol_v1_metadata(include_media_bytes=include_media_bytes))
        block_dict.update(self.certificate_metadata())
        return block_dict

    def certificate_metadata(self):
        metadata = {
            "submission_id": self.submission_id,
            "certificate_id": self.certificate_id,
            "content_hash": self.content_hash,
            "content_id": self.content_id,
            "content_type": self.content_type,
            "mime_type": self.mime_type,
            "creator_wallet": self.creator_wallet,
            "vote_hash": self.vote_hash,
            "approval_percentage": self.approval_percentage,
            "decisive_vote_total": self.decisive_vote_total,
            "minimum_votes_required": self.minimum_votes_required,
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

    @classmethod
    def _normalize_protocol_v1_value(cls, value: Any, *, field_name: str):
        if value is None:
            return None
        if isinstance(value, (bool, int, str)):
            return value
        if isinstance(value, (bytes, bytearray, memoryview)):
            return bytes(value)
        if isinstance(value, (float, Decimal)):
            return _normalize_decimal_string(value, field_name=field_name)
        if isinstance(value, list):
            return [
                cls._normalize_protocol_v1_value(item, field_name=field_name)
                for item in value
            ]
        if isinstance(value, dict):
            normalized = {}
            for key, child in value.items():
                if not isinstance(key, str):
                    raise ValueError(f"{field_name} dictionary keys must be strings.")
                if child is None:
                    continue
                normalized[key] = cls._normalize_protocol_v1_value(
                    child,
                    field_name=f"{field_name}.{key}",
                )
            return normalized
        raise ValueError(f"{field_name} contains unsupported value type {type(value).__name__}.")

    @staticmethod
    def _required_string(value, *, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} is required.")
        return value.strip()

    @staticmethod
    def _required_non_negative_int(value, *, field_name: str) -> int:
        if isinstance(value, bool):
            raise ValueError(f"{field_name} must be a non-negative integer.")
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be a non-negative integer.") from exc
        if normalized < 0:
            raise ValueError(f"{field_name} must be a non-negative integer.")
        return normalized

    def _consensus_transactions_v1(self):
        payload = []
        for index, transaction in enumerate(self.transactions):
            tx = self._transaction_to_dict(transaction)
            payload.append(
                self._normalize_protocol_v1_value(
                    {
                        "sender": self._required_string(tx.get("sender"), field_name=f"transactions[{index}].sender"),
                        "recipient": self._required_string(tx.get("recipient"), field_name=f"transactions[{index}].recipient"),
                        "amount": tx.get("amount"),
                        "tip": tx.get("tip", 0),
                        "payload_size_kb": tx.get("payload_size_kb", 0),
                        "signature": tx.get("signature"),
                    },
                    field_name=f"transactions[{index}]",
                )
            )
        return payload

    def _consensus_native_transactions_v1(self):
        return [
            self._normalize_protocol_v1_value(dict(transaction), field_name=f"native_transactions[{index}]")
            for index, transaction in enumerate(self.native_transactions)
        ]

    def _consensus_voter_rewards_v1(self):
        return [
            self._normalize_protocol_v1_value(dict(reward_entry), field_name=f"voter_rewards[{index}]")
            for index, reward_entry in enumerate(self.voter_rewards)
        ]

    def consensus_payload_v1(self):
        if not self.is_protocol_v1_block():
            raise ValueError("Legacy blocks do not define a Protocol v1 consensus payload.")
        if self.media_bytes is None:
            raise ValueError("Protocol v1 blocks must include media_bytes.")
        payload = {
            "block_version": PROTOCOL_V1_BLOCK_VERSION,
            "index": self._required_non_negative_int(self.index, field_name="index"),
            "previous_hash": self._required_string(self.previous_hash, field_name="previous_hash"),
            "timestamp": self.timestamp,
            "transactions": self._consensus_transactions_v1(),
            "miner": self._required_string(self.miner, field_name="miner"),
            "submission_id": self._required_string(self.submission_id, field_name="submission_id"),
            "certificate_id": self._required_string(self.certificate_id, field_name="certificate_id"),
            "content_hash": self._required_string(self.content_hash, field_name="content_hash"),
            "content_type": self._required_string(self.content_type, field_name="content_type"),
            "mime_type": self._required_string(self.mime_type, field_name="mime_type"),
            "media_hash": self._required_string(self.media_hash, field_name="media_hash"),
            "media_bytes": self.media_bytes,
            "creator_wallet": self._required_string(self.creator_wallet, field_name="creator_wallet"),
            "vote_hash": self._required_string(self.vote_hash, field_name="vote_hash"),
            "approval_percentage": self.approval_percentage,
            "decisive_vote_total": self._required_non_negative_int(
                self.decisive_vote_total,
                field_name="decisive_vote_total",
            ),
            "minimum_votes_required": self._required_non_negative_int(
                self.minimum_votes_required,
                field_name="minimum_votes_required",
            ),
            "approved_at": self.approved_at,
            "originality_score": self.originality_score,
            "reward_type": self._required_string(self.reward_type, field_name="reward_type"),
            "reward_recipient": self._required_string(self.reward_recipient, field_name="reward_recipient"),
            "reward_amount": self.reward_amount,
            "reward_source": self._required_string(self.reward_source, field_name="reward_source"),
            "minted_at": self.minted_at,
            "transactions_hash": self.transactions_hash,
            "native_transactions": self._consensus_native_transactions_v1(),
            "voter_rewards": self._consensus_voter_rewards_v1(),
        }
        if self.content_id is not None:
            payload["content_id"] = self._required_string(self.content_id, field_name="content_id")
        if isinstance(self.meme, dict):
            meme_text = self.meme.get("text")
            if meme_text not in (None, ""):
                payload["meme_text"] = self._required_string(meme_text, field_name="meme.text")
        return self._normalize_protocol_v1_value(payload, field_name="block")

    @classmethod
    def consensus_payload_v1_from_dict(cls, block_dict):
        if not isinstance(block_dict, dict):
            raise ValueError("Block payload must be a dictionary.")

        transactions = []
        for transaction in block_dict.get("transactions", []) or []:
            tx = cls._transaction_to_dict(transaction)
            transactions.append(
                {
                    "sender": tx.get("sender"),
                    "recipient": tx.get("recipient"),
                    "amount": tx.get("amount"),
                    "tip": tx.get("tip", 0),
                    "payload_size_kb": tx.get("payload_size_kb", 0),
                    "signature": tx.get("signature"),
                }
            )

        payload = {
            "block_version": block_dict.get("block_version", PROTOCOL_V1_BLOCK_VERSION),
            "index": block_dict.get("index"),
            "previous_hash": block_dict.get("previous_hash"),
            "timestamp": block_dict.get("timestamp"),
            "transactions": transactions,
            "miner": block_dict.get("miner"),
            "submission_id": block_dict.get("submission_id"),
            "certificate_id": block_dict.get("certificate_id"),
            "content_hash": block_dict.get("content_hash"),
            "content_id": block_dict.get("content_id"),
            "content_type": block_dict.get("content_type"),
            "mime_type": block_dict.get("mime_type"),
            "media_hash": block_dict.get("media_hash"),
            "media_bytes": (
                cls._coerce_media_bytes(block_dict.get("media_bytes"))
                if block_dict.get("media_bytes") is not None
                else None
            ),
            "creator_wallet": block_dict.get("creator_wallet"),
            "vote_hash": block_dict.get("vote_hash"),
            "approval_percentage": block_dict.get("approval_percentage"),
            "decisive_vote_total": block_dict.get("decisive_vote_total"),
            "minimum_votes_required": block_dict.get("minimum_votes_required"),
            "approved_at": block_dict.get("approved_at"),
            "originality_score": block_dict.get("originality_score"),
            "reward_type": block_dict.get("reward_type"),
            "reward_recipient": block_dict.get("reward_recipient"),
            "reward_amount": block_dict.get("reward_amount"),
            "reward_source": block_dict.get("reward_source"),
            "minted_at": block_dict.get("minted_at"),
            "transactions_hash": block_dict.get("transactions_hash"),
            "native_transactions": [
                dict(transaction)
                for transaction in (block_dict.get("native_transactions", []) or [])
            ],
            "voter_rewards": [
                dict(reward_entry)
                for reward_entry in (block_dict.get("voter_rewards", []) or [])
            ],
        }
        meme = block_dict.get("meme")
        if isinstance(meme, dict):
            meme_text = meme.get("text")
            if meme_text not in (None, ""):
                payload["meme_text"] = meme_text
        payload = {
            key: value
            for key, value in payload.items()
            if value is not None or key in {"transactions", "native_transactions", "voter_rewards"}
        }
        return cls._normalize_protocol_v1_value(payload, field_name="block")

    def consensus_payload_v1_bytes(self):
        network_id = normalize_network_id(
            self._required_string(self.network_id, field_name="network_id")
        )
        return canonical_domain_bytes(
            self.consensus_payload_v1(),
            object_type=OBJECT_TYPE_BLOCK,
            network_id=network_id,
        )

    @classmethod
    def consensus_payload_v1_bytes_from_dict(cls, block_dict):
        network_id = normalize_network_id(block_dict.get("network_id"))
        return canonical_domain_bytes(
            cls.consensus_payload_v1_from_dict(block_dict),
            object_type=OBJECT_TYPE_BLOCK,
            network_id=network_id,
        )

    def calculate_hash_legacy(self):
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

    def calculate_hash_v1(self):
        return hashlib.sha256(self.consensus_payload_v1_bytes()).hexdigest()

    @classmethod
    def calculate_hash_v1_from_dict(cls, block_dict):
        return hashlib.sha256(cls.consensus_payload_v1_bytes_from_dict(block_dict)).hexdigest()

    def calculate_hash_genesis(self):
        record = self.to_dict(include_media_bytes=True)
        canonical_public_testnet_v1_genesis_payload_from_record(record)
        return canonical_public_testnet_v1_genesis_hash()

    def calculate_hash(self):
        if self.is_protocol_v1_genesis_block():
            return self.calculate_hash_genesis()
        if self.is_protocol_v1_block():
            return self.calculate_hash_v1()
        return self.calculate_hash_legacy()
