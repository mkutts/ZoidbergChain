"""Framework-independent block and whole-chain consensus validation."""

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from block import PROTOCOL_V1_BLOCK_VERSION
from content import (
    CONTENT_TYPE_IMAGE,
    CONTENT_TYPE_MIXED,
    CONTENT_TYPE_TEXT,
    STORAGE_STATUS_MISSING,
    STORAGE_STATUS_REMOTE,
    STORAGE_STATUS_VERIFIED,
    TEXT_MIME_TYPE,
    _validate_content_type,
)
from originality_certificate import validate_certificate_for_submission
from protocol_v1_native_transfer import PROTOCOL_V1_NATIVE_TRANSFER_VERSION
from submission import VOTE_NOT_ORIGINAL, VOTE_ORIGINAL
from validators import is_valid_content_hash


class NativeBlockValidationError(ValueError):
    def __init__(self, code, message, *, details=None):
        super().__init__(message)
        self.code = str(code).strip() or "invalid_block"
        self.details = dict(details or {})

    def to_detail(self):
        payload = {"code": self.code, "message": str(self)}
        payload.update(self.details)
        return payload


@dataclass(frozen=True)
class BlockValidationCollaborators:
    chain: object
    chain_to_dicts: Callable
    calculate_balances_from_chain: Callable
    validate_signed_native_transaction: Callable
    is_protocol_v1_block_payload: Callable
    normalize_wallet_identity: Callable
    coerce_native_nonce: Callable
    get_next_chain_nonce: Callable
    native_block_sort_key: Callable
    normalize_decimal_value: Callable
    compute_native_transactions_hash: Callable
    block_native_transactions: Callable
    resolve_protocol_v1_block_media: Callable
    protocol_v1_network_id: Callable
    get_settled_voter_reward_ids: Callable
    build_reward_transaction_key: Callable
    expected_voter_reward_records_by_id: Callable
    block_reward_transactions: Callable
    get_originality_certificate: Callable
    get_submission: Callable
    resolve_meme_reward_recipient: Callable
    get_content_object_by_hash: Callable
    verify_content_object_payload: Callable
    calculate_hash_from_dict: Callable
    validate_transaction: Callable
    validate_genesis: Callable
    config: dict


class BlockValidationService:
    @staticmethod
    def _raise(code, message, **details):
        raise NativeBlockValidationError(code, message, details=details or None)

    @staticmethod
    def native_block_requires_certificate_context(block_dict) -> bool:
        if not list(block_dict.get("native_transactions", []) or []):
            return False
        fields = (
            "submission_id", "certificate_id", "content_hash", "creator_wallet", "vote_hash",
            "approval_percentage", "decisive_vote_total", "minimum_votes_required", "approved_at",
            "originality_score", "reward_type", "reward_recipient", "reward_amount", "reward_source", "minted_at",
        )
        return all(block_dict.get(field) is not None for field in fields)

    @staticmethod
    def extract_certificate_metadata(block_dict):
        fields = [
            "submission_id", "certificate_id", "content_hash", "content_id", "content_type", "mime_type",
            "creator_wallet", "vote_hash", "approval_percentage", "decisive_vote_total", "minimum_votes_required",
            "approved_at", "originality_score", "reward_type", "reward_recipient", "reward_amount",
            "reward_source", "minted_at", "native_transactions", "transaction_ids", "transaction_count",
            "transactions_hash",
        ]
        meme = block_dict.get("meme") if isinstance(block_dict.get("meme"), dict) else {}
        metadata = {}
        for field in fields:
            if block_dict.get(field) is not None:
                metadata[field] = block_dict.get(field)
            elif meme.get(field) is not None:
                metadata[field] = meme.get(field)
        return metadata

    def validate_native_transactions(self, block_dict, c: BlockValidationCollaborators, *, prior_chain=None):
        native_transactions = list(block_dict.get("native_transactions", []) or [])
        transaction_ids = list(block_dict.get("transaction_ids", []) or [])
        transaction_count = block_dict.get("transaction_count", len(native_transactions))
        transactions_hash = block_dict.get("transactions_hash")
        if transaction_count != len(native_transactions):
            self._raise("invalid_transaction_count", "Block transaction_count does not match native_transactions length.", transaction_count=transaction_count, actual_count=len(native_transactions))
        expected_ids = [transaction.get("tx_id") for transaction in native_transactions]
        if transaction_ids != expected_ids:
            self._raise("transaction_id_mismatch", "Block transaction_ids do not match native_transactions.", transaction_ids=transaction_ids, expected_transaction_ids=expected_ids)
        if native_transactions and transactions_hash != c.compute_native_transactions_hash(native_transactions):
            self._raise("transactions_hash_mismatch", "Block transactions_hash does not match native_transactions.", transactions_hash=transactions_hash)
        if native_transactions and not self.native_block_requires_certificate_context(block_dict):
            self._raise("invalid_block_context", "Blocks containing native transactions must remain meme-mined blocks.")

        prior_chain = c.chain_to_dicts(prior_chain or c.chain)
        chain_state = c.calculate_balances_from_chain(prior_chain)
        seen_prior_tx_ids = set(chain_state["seen_tx_ids"])
        next_nonces = dict(chain_state["next_nonces"])
        balances = dict(chain_state["balances"])
        seen_block_tx_ids, seen_block_nonces, validated = set(), set(), []
        for index, transaction in enumerate(native_transactions):
            if not isinstance(transaction, dict):
                self._raise("malformed_transaction", "Block native transaction payload must be an object.", transaction_index=index)
            try:
                checked = c.validate_signed_native_transaction(transaction)
            except ValueError as exc:
                message, code = str(exc), "malformed_transaction"
                if "tx_id does not match" in message: code = "transaction_id_mismatch"
                elif "network does not match" in message: code = "wrong_network"
                elif "transaction_type must be exactly" in message: code = "unsupported_transaction_type"
                elif "signature_scheme must be" in message or "signature is required" in message or "Malformed signature" in message or "signature" in message: code = "invalid_transaction_signature"
                elif "fee" in message: code = "invalid_fee"
                self._raise(code, message, transaction_index=index, tx_id=str(transaction.get("tx_id") or "").strip().lower() or None)
            tx_id = str(checked.get("tx_id") or "").strip().lower()
            if c.is_protocol_v1_block_payload(block_dict) and checked.get("transaction_version") != PROTOCOL_V1_NATIVE_TRANSFER_VERSION:
                self._raise("unsupported_transaction_version", "Protocol v1 blocks cannot include legacy native transactions.", tx_id=tx_id, transaction_index=index)
            if tx_id in seen_block_tx_ids:
                self._raise("duplicate_transaction_id", "Block contains the same native transaction more than once.", tx_id=tx_id, transaction_index=index)
            if tx_id in seen_prior_tx_ids:
                self._raise("transaction_already_settled", "Block contains a native transaction that was already settled in an earlier block.", tx_id=tx_id, transaction_index=index)
            sender = c.normalize_wallet_identity(checked.get("from_address"))
            recipient = c.normalize_wallet_identity(checked.get("to_address"))
            nonce = c.coerce_native_nonce(checked.get("nonce"))
            nonce_key = (sender, nonce)
            if nonce_key in seen_block_nonces:
                self._raise("duplicate_nonce", "Block contains multiple native transactions with the same sender nonce.", tx_id=tx_id, from_address=sender, nonce=nonce, transaction_index=index)
            expected_nonce = next_nonces.get(sender, c.get_next_chain_nonce(sender, prior_chain))
            if nonce < expected_nonce:
                self._raise("nonce_too_low", "Block native transaction nonce is lower than the next expected chain nonce.", tx_id=tx_id, from_address=sender, expected_nonce=expected_nonce, received_nonce=nonce, transaction_index=index)
            if nonce > expected_nonce:
                self._raise("nonce_gap", "Block native transaction nonce creates a gap against the prior chain state.", tx_id=tx_id, from_address=sender, expected_nonce=expected_nonce, received_nonce=nonce, transaction_index=index)
            amount, fee = Decimal(str(checked.get("amount") or "0")), Decimal(str(checked.get("fee") or "0"))
            if fee != Decimal("0"):
                self._raise("invalid_fee", "Block native transaction fee must be zero under the current fee policy.", tx_id=tx_id, fee=str(checked.get("fee") or "0"), transaction_index=index)
            required = amount + fee
            sender_balance = balances.get(sender, Decimal("0"))
            if sender_balance < required:
                self._raise("insufficient_balance", "Block native transaction would overdraw the sender when applied in block order.", tx_id=tx_id, from_address=sender, available_balance=c.normalize_decimal_value(sender_balance), required_total=c.normalize_decimal_value(required), transaction_index=index)
            balances[sender] = sender_balance - required
            balances[recipient] = balances.get(recipient, Decimal("0")) + amount
            next_nonces[sender] = expected_nonce + 1
            seen_prior_tx_ids.add(tx_id); seen_block_tx_ids.add(tx_id); seen_block_nonces.add(nonce_key); validated.append(checked)
        expected_order = sorted(validated, key=c.native_block_sort_key)
        if [tx.get("tx_id") for tx in validated] != [tx.get("tx_id") for tx in expected_order]:
            self._raise("transaction_order_invalid", "Block native transaction ordering does not match the canonical block ordering policy.")
        return True

    def validate_protocol_v1_payload(self, block_dict, c: BlockValidationCollaborators):
        if not c.is_protocol_v1_block_payload(block_dict):
            return True
        if block_dict.get("block_version") != PROTOCOL_V1_BLOCK_VERSION:
            self._raise("invalid_block_version", "Unsupported Protocol v1 block_version.", block_index=block_dict.get("index"), block_version=block_dict.get("block_version"))
        network_id, expected_network_id = block_dict.get("network_id"), c.protocol_v1_network_id()
        if network_id != expected_network_id:
            self._raise("wrong_network", "Protocol v1 block network_id does not match the local network.", block_index=block_dict.get("index"), network_id=network_id, expected_network_id=expected_network_id)
        media_hash, content_hash = block_dict.get("media_hash"), block_dict.get("content_hash")
        if not is_valid_content_hash(media_hash): self._raise("invalid_media_hash", "Protocol v1 block media_hash must be a 64-character lowercase hexadecimal string.", block_index=block_dict.get("index"))
        if not is_valid_content_hash(content_hash): self._raise("invalid_content_hash", "Protocol v1 block content_hash must be a 64-character lowercase hexadecimal string.", block_index=block_dict.get("index"))
        if block_dict.get("media_bytes") is None: self._raise("missing_media_bytes", "Protocol v1 blocks must embed immutable media bytes.", block_index=block_dict.get("index"))
        try: content_type = _validate_content_type(block_dict.get("content_type"))
        except ValueError as exc: self._raise("invalid_content_metadata", str(exc), block_index=block_dict.get("index"))
        try: resolved = c.resolve_protocol_v1_block_media(block_dict)
        except (UnicodeDecodeError, ValueError) as exc: self._raise("invalid_embedded_media", str(exc), block_index=block_dict.get("index"))
        if media_hash != resolved["content_hash"]: self._raise("media_hash_mismatch", "Protocol v1 block media_hash does not match embedded media bytes.", block_index=block_dict.get("index"), media_hash=media_hash, actual_media_hash=resolved["content_hash"])
        if content_hash != resolved["content_hash"]: self._raise("content_hash_mismatch", "Protocol v1 block content_hash does not match embedded media bytes.", block_index=block_dict.get("index"), content_hash=content_hash, actual_content_hash=resolved["content_hash"])
        if resolved["mime_type"] == TEXT_MIME_TYPE and content_type != CONTENT_TYPE_TEXT: self._raise("content_type_mismatch", "Protocol v1 text blocks must declare content_type='text'.", block_index=block_dict.get("index"))
        if resolved["mime_type"] != TEXT_MIME_TYPE and content_type not in {CONTENT_TYPE_IMAGE, CONTENT_TYPE_MIXED}: self._raise("content_type_mismatch", "Protocol v1 binary blocks must declare content_type='image' or 'mixed'.", block_index=block_dict.get("index"))
        return True

    def validate_voter_rewards(self, block_dict, c: BlockValidationCollaborators, *, prior_chain=None):
        voter_rewards = block_dict.get("voter_rewards")
        if voter_rewards in (None, []): return []
        if not isinstance(voter_rewards, list): self._raise("invalid_voter_reward_metadata", "Block voter_rewards must be a list when provided.", block_index=block_dict.get("index"))
        prior_ids = c.get_settled_voter_reward_ids(chain=c.chain_to_dicts(prior_chain or []))
        seen, validated = set(), []
        for entry in voter_rewards:
            if not isinstance(entry, dict): self._raise("invalid_voter_reward_metadata", "Each voter reward entry must be an object.", block_index=block_dict.get("index"))
            required = ["reward_id", "reward_type", "reward_recipient", "reward_amount", "reward_source", "submission_id", "vote_choice", "final_decision", "decision_reason", "decision_finalized_at", "created_at", "network_name"]
            for field in required:
                value = entry.get(field)
                if value is None or (isinstance(value, str) and not value.strip()): self._raise("invalid_voter_reward_metadata", f"Block voter reward metadata missing {field}.", block_index=block_dict.get("index"), field_name=field)
            reward_id = str(entry["reward_id"]).strip()
            if reward_id in seen: self._raise("duplicate_reward", "Block contains duplicate voter reward IDs.", block_index=block_dict.get("index"), reward_id=reward_id)
            if reward_id in prior_ids: self._raise("duplicate_reward", "Block duplicates a voter reward that was already settled earlier in the chain.", block_index=block_dict.get("index"), reward_id=reward_id)
            if str(entry["reward_type"]).strip() != "voter_majority_reward": self._raise("invalid_voter_reward_metadata", "Block voter reward_type is invalid.", block_index=block_dict.get("index"), reward_id=reward_id)
            if str(entry["reward_source"]).strip() != "reward_pool": self._raise("invalid_voter_reward_metadata", "Block voter reward_source is invalid.", block_index=block_dict.get("index"), reward_id=reward_id)
            recipient = c.normalize_wallet_identity(entry["reward_recipient"])
            if recipient is None: self._raise("invalid_voter_reward_metadata", "Block voter reward_recipient is invalid.", block_index=block_dict.get("index"), reward_id=reward_id)
            vote_choice, decision = str(entry["vote_choice"]).strip().lower(), str(entry["final_decision"]).strip().lower()
            if vote_choice not in {VOTE_ORIGINAL, VOTE_NOT_ORIGINAL}: self._raise("invalid_voter_reward_metadata", "Block voter reward vote_choice must be decisive.", block_index=block_dict.get("index"), reward_id=reward_id)
            if decision not in {c.config["voter_reward_approval_side"], c.config["voter_reward_rejection_side"]}: self._raise("invalid_voter_reward_metadata", "Block voter reward final_decision is invalid.", block_index=block_dict.get("index"), reward_id=reward_id)
            if (decision == c.config["voter_reward_approval_side"] and vote_choice != VOTE_ORIGINAL) or (decision == c.config["voter_reward_rejection_side"] and vote_choice != VOTE_NOT_ORIGINAL): self._raise("invalid_voter_reward_metadata", "Block voter reward vote_choice does not match final_decision.", block_index=block_dict.get("index"), reward_id=reward_id)
            try: reward_key = c.build_reward_transaction_key(recipient, entry["reward_amount"])
            except ValueError as exc: self._raise("invalid_voter_reward_metadata", str(exc), block_index=block_dict.get("index"), reward_id=reward_id)
            submission_id = str(entry["submission_id"]).strip()
            expected = c.expected_voter_reward_records_by_id(submission_id).get(reward_id)
            if expected is None: self._raise("invalid_voter_reward_metadata", "Block voter reward does not match the deterministic reward plan for this submission.", block_index=block_dict.get("index"), reward_id=reward_id, submission_id=submission_id)
            expected_fields = ["reward_type", "reward_recipient", "reward_amount", "reward_source", "submission_id", "certificate_id", "content_hash", "vote_choice", "final_decision", "decision_reason", "decision_finalized_at", "created_at", "network_name"]
            for field in expected_fields:
                if entry.get(field) != expected.get(field): self._raise("invalid_voter_reward_metadata", f"Block voter reward {field} does not match the deterministic reward plan.", block_index=block_dict.get("index"), reward_id=reward_id, field_name=field)
            seen.add(reward_id); validated.append({"reward_id": reward_id, "reward_key": reward_key})
        return validated

    def validate_certificate_metadata(self, block_dict, c: BlockValidationCollaborators, *, prior_chain=None):
        if block_dict.get("index") == 0: return True
        metadata = self.extract_certificate_metadata(block_dict)
        voter_rewards = self.validate_voter_rewards(block_dict, c, prior_chain=prior_chain)
        if not metadata:
            if voter_rewards: self._raise("invalid_voter_reward_metadata", "Blocks with voter rewards must include certified meme block metadata.", block_index=block_dict.get("index"))
            return True
        required = ["submission_id", "certificate_id", "content_hash", "creator_wallet", "vote_hash", "approval_percentage", "decisive_vote_total", "minimum_votes_required", "approved_at", "originality_score"]
        if c.block_native_transactions(block_dict) and not self.native_block_requires_certificate_context(block_dict): self._raise("invalid_block_context", "Blocks containing native transactions must include certified meme block metadata and reward metadata.", block_index=block_dict.get("index"))
        if not any(metadata.get(field) is not None for field in required): return True
        for field in required:
            if field not in metadata: self._raise("invalid_block_context", f"Block certificate metadata missing {field}.", block_index=block_dict.get("index"), field_name=field)
        certificate = c.get_originality_certificate(metadata["certificate_id"])
        if not certificate: self._raise("unknown_certificate", "Block references unknown originality certificate.", certificate_id=metadata["certificate_id"])
        if certificate.submission_id != metadata["submission_id"]: self._raise("certificate_submission_mismatch", "Block certificate_id does not match block submission_id.", certificate_id=metadata["certificate_id"], submission_id=metadata["submission_id"])
        if certificate.content_hash != metadata["content_hash"]: self._raise("content_hash_mismatch", "Block certificate content_hash does not match block content_hash.", certificate_id=metadata["certificate_id"], submission_id=metadata["submission_id"])
        if metadata.get("content_id") is not None and getattr(certificate, "content_id", None) is not None and certificate.content_id != metadata["content_id"]: self._raise("content_id_mismatch", "Block content_id does not match certificate content_id.", certificate_id=metadata["certificate_id"], submission_id=metadata["submission_id"])
        submission = c.get_submission(metadata["submission_id"])
        if submission:
            validate_certificate_for_submission(certificate, submission, network_name=c.config["network_name"])
            if metadata["content_hash"] != submission.content_hash: self._raise("content_hash_mismatch", "Block content_hash does not match submission.", submission_id=metadata["submission_id"])
            if metadata.get("content_id") is not None and metadata["content_id"] != submission.content_id: self._raise("content_id_mismatch", "Block content_id does not match submission.", submission_id=metadata["submission_id"])
        for field in required:
            if metadata[field] != getattr(certificate, field): self._raise("certificate_metadata_mismatch", f"Block certificate metadata {field} does not match certificate.", field_name=field, certificate_id=metadata["certificate_id"], submission_id=metadata["submission_id"])
        reward_fields = ["reward_type", "reward_recipient", "reward_amount", "reward_source", "minted_at"]
        if any(metadata.get(field) is not None for field in reward_fields):
            for field in reward_fields:
                if metadata.get(field) is None: self._raise("invalid_reward_metadata", f"Block reward metadata missing {field}.", submission_id=metadata["submission_id"], field_name=field)
            if metadata["reward_type"] != "meme_mining_reward": self._raise("invalid_reward_metadata", "Block reward_type is invalid.", submission_id=metadata["submission_id"])
            if metadata["reward_source"] != "reward_pool": self._raise("invalid_reward_metadata", "Block reward_source is invalid.", submission_id=metadata["submission_id"])
            recipient = c.normalize_wallet_identity(metadata["reward_recipient"])
            if recipient is None: self._raise("reward_recipient_mismatch", "Block reward_recipient is invalid.", submission_id=metadata["submission_id"])
            if float(metadata["reward_amount"]) != float(c.config["meme_block_reward"]): self._raise("reward_amount_mismatch", "Block reward_amount does not match configured reward.", submission_id=metadata["submission_id"], reward_amount=metadata["reward_amount"])
            if submission and recipient != c.resolve_meme_reward_recipient(submission, certificate): self._raise("reward_recipient_mismatch", "Block reward_recipient does not match submission creator wallet.", submission_id=metadata["submission_id"], reward_recipient=recipient)
            prior = c.chain_to_dicts(prior_chain or [])
            if any(block.get("submission_id") == metadata["submission_id"] and block.get("reward_type") == "meme_mining_reward" for block in prior): self._raise("duplicate_reward", "Block duplicates the meme reward for an already minted submission.", submission_id=metadata["submission_id"])
        expected_keys = [reward["reward_key"] for reward in voter_rewards]
        if expected_keys:
            actual = Counter()
            for transaction in c.block_reward_transactions(block_dict):
                try: key = c.build_reward_transaction_key(transaction.get("recipient"), transaction.get("amount"))
                except ValueError: self._raise("invalid_reward_metadata", "Block contains an invalid REWARD_POOL transaction.", block_index=block_dict.get("index"))
                actual[key] += 1
            expected = Counter(expected_keys)
            if any(actual[key] < count for key, count in expected.items()): self._raise("invalid_reward_metadata", "Block voter reward transactions do not match the declared reward metadata.", block_index=block_dict.get("index"), expected_voter_reward_transactions=sum(expected.values()), actual_reward_transactions=sum(actual.values()))
        content_object = c.get_content_object_by_hash(metadata["content_hash"])
        if content_object is not None:
            if metadata.get("content_id") is not None and metadata["content_id"] != content_object.content_id: self._raise("content_id_mismatch", "Block content_id does not match content object.", submission_id=metadata["submission_id"])
            if metadata.get("content_type") is not None and metadata["content_type"] != content_object.content_type:
                compatible = content_object.storage_status in {STORAGE_STATUS_REMOTE, STORAGE_STATUS_MISSING} and content_object.content_type == CONTENT_TYPE_IMAGE and metadata["content_type"] in {CONTENT_TYPE_MIXED, CONTENT_TYPE_TEXT}
                if not compatible: self._raise("content_type_mismatch", "Block content_type does not match content object.", submission_id=metadata["submission_id"])
            if metadata.get("mime_type") is not None and metadata["mime_type"] != content_object.mime_type:
                compatible = content_object.storage_status in {STORAGE_STATUS_REMOTE, STORAGE_STATUS_MISSING} and content_object.mime_type == "application/octet-stream"
                if not compatible: self._raise("mime_type_mismatch", "Block mime_type does not match content object.", submission_id=metadata["submission_id"])
            if content_object.storage_status == STORAGE_STATUS_VERIFIED and not c.verify_content_object_payload(content_object)["verified"]: self._raise("content_hash_mismatch", "Verified local content file does not match block content_hash.", submission_id=metadata["submission_id"])
        return True

    def validate_block(self, block_dict, c: BlockValidationCollaborators, *, prior_chain=None):
        self.validate_protocol_v1_payload(block_dict, c)
        self.validate_certificate_metadata(block_dict, c, prior_chain=prior_chain)
        self.validate_native_transactions(block_dict, c, prior_chain=prior_chain)
        return True

    def validate_candidate(self, block, c: BlockValidationCollaborators, *, current_chain=None):
        working_chain = current_chain or c.chain
        latest = working_chain[-1]
        if block.previous_hash != latest.hash: raise ValueError("Block does not extend the local chain tip.")
        if block.index != latest.index + 1: raise ValueError("Block index must extend the local chain by one.")
        if block.hash != block.calculate_hash(): raise ValueError("Block hash does not match block contents.")
        block_dict = block.to_dict()
        if block.hash != c.calculate_hash_from_dict(block_dict): raise ValueError("Block hash does not match existing block validation.")
        for transaction in block.transactions:
            if not transaction.is_valid(): raise ValueError("Block contains an invalid transaction.")
            if transaction.sender not in {"GENESIS", "REWARD_POOL"} and not c.validate_transaction(transaction): raise ValueError("Block contains an invalid transaction.")
        prior = c.chain_to_dicts(working_chain)
        self.validate_block(block_dict, c, prior_chain=prior)
        if not self.validate_chain(prior + [block_dict], c): raise ValueError("Block failed chain validation.")
        return True

    def validate_chain(self, chain, c: BlockValidationCollaborators):
        chain_dicts = c.chain_to_dicts(chain)
        if not chain_dicts: return False
        try: c.validate_genesis(chain_dicts[0])
        except ValueError as exc:
            print(f"Debug: Genesis validation failed - {exc}")
            return False
        for index in range(1, len(chain_dicts)):
            block, previous = chain_dicts[index], chain_dicts[index - 1]
            if block["hash"] != c.calculate_hash_from_dict(block):
                print(f"Debug: Block {block['index']} hash is invalid!")
                return False
            if block["previous_hash"] != previous["hash"]:
                print(f"Debug: Block {block['index']} previous hash does not match!")
                return False
            try: self.validate_block(block, c, prior_chain=chain[:index])
            except ValueError as exc:
                print(f"Debug: Block {block['index']} transaction or certificate metadata is invalid: {exc}")
                return False
        return True
