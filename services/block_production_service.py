"""Candidate block construction without chain-state or persistence ownership."""

import base64
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

from block import Block, PROTOCOL_V1_BLOCK_VERSION
from content import TEXT_MIME_TYPE, compute_text_content_hash, guess_mime_type, resolve_declared_payload_hash
from transaction import Transaction
from utils import extract_text, hash_image


@dataclass(frozen=True)
class BlockProductionState:
    chain: object
    pending_transactions: object
    texts: object
    image_hashes: object
    reward_pool: float
    initial_reward_pool: float


@dataclass(frozen=True)
class BlockProductionCollaborators:
    is_valid_public_key: Callable
    encode_image: Callable
    select_native_transactions_for_block: Callable
    validate_transaction: Callable
    normalize_wallet_identity: Callable
    get_protocol_v1_block_for_submission: Callable
    get_protocol_v1_block_for_certificate: Callable
    select_voter_reward_records_for_block: Callable
    get_submission: Callable
    build_meme_reward_metadata: Callable
    certificate_block_metadata: Callable
    protocol_v1_network_id: Callable
    config: dict


class BlockProductionService:
    def build_candidate(
        self,
        state: BlockProductionState,
        c: BlockProductionCollaborators,
        image_path,
        text_content=None,
        miner=None,
        max_block_size_kb=500,
        validate_meme=True,
        certificate=None,
        reward_recipient=None,
    ):
        if not c.is_valid_public_key(miner):
            print(f"Debug: Invalid miner public key: {miner}")
            raise ValueError("Invalid public key provided for the miner.")

        file_exists = bool(image_path) and os.path.isfile(image_path)
        file_extension = os.path.splitext(image_path)[1].lower() if image_path else ""
        guessed_mime_type = guess_mime_type(os.path.basename(image_path), "image/jpeg") if file_exists else ""
        is_text_payload = bool(text_content and text_content.strip()) and (
            not file_exists or guessed_mime_type == TEXT_MIME_TYPE or file_extension == ".txt"
        )
        if not file_exists and not is_text_payload:
            print(f"Debug: Image path {image_path} does not exist.")
            raise ValueError("Invalid image path provided for the meme.")

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

        normalized_text = re.sub(r"[^\w\s]", "", text_content).strip().lower()
        image_hash = compute_text_content_hash(text_content) if is_text_payload else hash_image(image_path)
        if validate_meme:
            if is_text_payload:
                if normalized_text in state.texts:
                    print(f"Debug: Duplicate text payload detected: '{normalized_text}' already exists.")
                    raise ValueError("This meme has already been submitted.")
            elif image_hash in state.image_hashes and normalized_text in state.texts:
                print(f"Debug: Duplicate meme detected! Image hash {image_hash} and text '{normalized_text}' already exist.")
                raise ValueError("This meme has already been submitted.")

        protocol_media, canonical_text = None, text_content
        if certificate is not None:
            if is_text_payload:
                protocol_media = resolve_declared_payload_hash(text_content.encode("utf-8"), TEXT_MIME_TYPE)
                canonical_text = protocol_media["text_content"]
            else:
                with open(image_path, "rb") as image_file:
                    protocol_media = resolve_declared_payload_hash(
                        image_file.read(),
                        guessed_mime_type or guess_mime_type(os.path.basename(image_path), "image/jpeg"),
                    )
            declared_hash = str(getattr(certificate, "content_hash", "") or "").strip()
            if declared_hash != protocol_media["content_hash"]:
                raise ValueError("Certified submission content_hash does not match canonical media bytes.")

        if is_text_payload:
            print("Debug: Encoding text payload for block storage.")
            encoded_payload = protocol_media["stored_bytes"] if protocol_media is not None else text_content.encode("utf-8")
            meme_encoded = base64.b64encode(encoded_payload).decode("utf-8")
        elif protocol_media is not None:
            print(f"Debug: Encoding image at path {image_path}.")
            meme_encoded = base64.b64encode(protocol_media["stored_bytes"]).decode("utf-8")
        else:
            print(f"Debug: Encoding image at path {image_path}.")
            meme_encoded = c.encode_image(image_path)

        meme_size_kb = len(meme_encoded) / 1024
        text_size_kb = len(text_content.encode()) / 1024
        native_plan = c.select_native_transactions_for_block(max_transactions_per_block=c.config["max_transactions_per_block"])
        native_transactions = native_plan["transactions"]
        native_size_kb = (
            len(json.dumps(native_transactions, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")) / 1024
            if native_transactions else 0
        )

        valid_transactions, total_tx_size_kb, total_miner_tips = [], 0, 0.0
        candidate_reward_pool = float(state.reward_pool)
        print("Debug: Validating transactions concurrently...")
        with ThreadPoolExecutor() as executor:
            future_to_tx = {executor.submit(c.validate_transaction, tx): tx for tx in state.pending_transactions}
            for future in future_to_tx:
                tx = future_to_tx[future]
                try:
                    if future.result():
                        tip = float(tx.tip or 0)
                        tip_split = {"miner": 0.25, "reward_pool": 0.75} if candidate_reward_pool < state.initial_reward_pool * 0.25 else {"miner": 0.5, "reward_pool": 0.5}
                        miner_tip_share, pool_share = tip * tip_split["miner"], tip * tip_split["reward_pool"]
                        candidate_reward_pool += pool_share
                        total_miner_tips += miner_tip_share
                        print(f"Debug: Transaction Distribution - Tip Total: {tip:.4f}")
                        print(f"Debug: - Miner gets: {miner_tip_share:.4f}")
                        print(f"Debug: - Reward Pool gets: {pool_share:.4f}")
                        total_tx_size_kb += len(str(tx)) / 1024
                        valid_transactions.append(tx)
                except Exception as exc:
                    print(f"Debug: Transaction validation error: {exc}")

        total_block_size_kb = meme_size_kb + text_size_kb + total_tx_size_kb + native_size_kb
        if total_block_size_kb > max_block_size_kb:
            print(f"Debug: Block size {total_block_size_kb:.2f} KB exceeds max limit of {max_block_size_kb} KB. Rejecting block.")
            return None
        print(f"Debug: Final block size: {total_block_size_kb:.2f} KB (within limit: {max_block_size_kb} KB)")

        mining_reward = float(c.config["meme_block_reward"])
        reward_receiver = reward_recipient or miner
        if reward_receiver not in {"GENESIS", "REWARD_POOL"}:
            normalized = c.normalize_wallet_identity(reward_receiver)
            if normalized is None:
                raise ValueError("Minting reward recipient is missing or invalid for this submission.")
            reward_receiver = normalized
        if certificate is not None and (
            c.get_protocol_v1_block_for_submission(certificate.submission_id) is not None
            or c.get_protocol_v1_block_for_certificate(certificate.certificate_id) is not None
        ):
            raise ValueError("Certified submission already minted into a block.")

        voter_plan = (
            c.select_voter_reward_records_for_block(prioritized_submission_id=certificate.submission_id, reward_pool_balance=candidate_reward_pool)
            if c.config["voter_rewards_enabled"] and certificate is not None else {"selected": [], "skipped": []}
        )
        voter_total = sum(float(record["reward_amount"]) for record in voter_plan["selected"])
        if candidate_reward_pool < mining_reward + voter_total:
            print("Error: Insufficient funds in the reward pool.")
            return None
        voter_transactions = [Transaction("REWARD_POOL", record["reward_recipient"], float(record["reward_amount"])) for record in voter_plan["selected"]]
        reward_transaction = Transaction("REWARD_POOL", reward_receiver, mining_reward)

        latest_block = state.chain[-1]
        minted_at = time.time()
        reward_metadata = {}
        if certificate is not None:
            submission = c.get_submission(certificate.submission_id)
            if submission is None: raise ValueError(f"Submission not found: {certificate.submission_id}")
            reward_metadata = c.build_meme_reward_metadata(submission, certificate, minted_at=minted_at)
        block = Block(
            index=latest_block.index + 1,
            previous_hash=latest_block.hash,
            timestamp=minted_at,
            transactions=voter_transactions + [reward_transaction] + valid_transactions,
            meme={"encoded_image": meme_encoded, "text": canonical_text},
            miner=miner,
            block_version=PROTOCOL_V1_BLOCK_VERSION if certificate is not None else None,
            network_id=c.protocol_v1_network_id() if certificate is not None else None,
            media_hash=protocol_media["content_hash"] if protocol_media is not None else None,
            media_bytes=protocol_media["stored_bytes"] if protocol_media is not None else None,
            native_transactions=native_transactions,
            transaction_ids=native_plan["transaction_ids"],
            transaction_count=native_plan["transaction_count"],
            transactions_hash=native_plan["transactions_hash"],
            **(c.certificate_block_metadata(certificate) if certificate else {}),
            **reward_metadata,
            voter_rewards=voter_plan["selected"],
        )
        if certificate is not None:
            block.reward_type = "meme_mining_reward"; block.reward_recipient = reward_transaction.recipient
            block.reward_amount = mining_reward; block.reward_source = "reward_pool"; block.minted_at = minted_at
            block.voter_rewards = list(voter_plan["selected"]); block.hash = block.calculate_hash()
        return {
            "block": block,
            "candidate_type": "protocol_v1" if certificate is not None else "legacy",
            "image_path": image_path,
            "text_content": text_content,
            "normalized_text": normalized_text,
            "image_hash": image_hash,
            "total_block_size_kb": total_block_size_kb,
            "total_miner_tips": total_miner_tips,
            "valid_transactions": valid_transactions,
            "native_transaction_plan": native_plan,
        }
