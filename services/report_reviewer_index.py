"""Finalized, durable qualification-height projection for report verification."""

from __future__ import annotations

from milestone5_policy import (
    CREATOR_PATH_MIN_FINALIZED_MINTED_SUBMISSIONS,
    MIN_WALLET_AGE_EPOCHS,
    MIXED_PATH_MIN_FINALIZED_MINTED_SUBMISSIONS,
    MIXED_PATH_MIN_FINALIZED_NATIVE_TRANSACTIONS,
    REVIEW_EPOCH_BLOCKS,
    ZOID_PATH_MIN_ACTIVITY_SPAN_EPOCHS,
    ZOID_PATH_MIN_FINALIZED_NATIVE_TRANSACTIONS,
    REVIEWER_POLICY_VERSION,
)
from native_transfer import normalize_wallet_address
from protocol_v1 import canonical_hash


INDEX_VERSION = 1


def reference_key(height: int, block_hash: str) -> str:
    return f"{height}:{str(block_hash).strip().lower()}"


def qualification_entry_digest(height: int, block_hash: str, wallet: str, qualified_height: int) -> str:
    return canonical_hash({"index_version": INDEX_VERSION,
                           "reviewer_policy_version": REVIEWER_POLICY_VERSION,
                           "height": height, "block_hash": block_hash.lower(),
                           "wallet": wallet, "qualification_height": qualified_height})


def _value(block, field, default=None):
    return block.get(field, default) if isinstance(block, dict) else getattr(block, field, default)


def qualification_snapshot(chain, height: int, block_hash: str) -> dict:
    """Traverse finalized ancestry once, outside the per-report path."""
    if height < 0 or height >= len(chain) or str(_value(chain[height], "hash")).lower() != block_hash.lower():
        raise ValueError("Report eligibility index reference is not canonical.")
    activity = {}

    def wallet_state(address, at_height):
        if address is None:
            return None
        return activity.setdefault(address, {
            "origin": at_height, "minted": set(), "native": set(),
            "creator_ready": None, "mixed_ready": None, "zoid_ready": None,
            "first_native_epoch": None, "last_native_epoch": None,
        })

    for block in chain[:height + 1]:
        at_height = int(_value(block, "index"))
        touched = set()
        creator = normalize_wallet_address(_value(block, "creator_wallet"))
        submission_id = str(_value(block, "submission_id") or "").strip()
        if creator is not None and submission_id:
            state = wallet_state(creator, at_height)
            state["minted"].add(submission_id)
            touched.add(creator)
        for transaction in _value(block, "native_transactions", []) or []:
            if not isinstance(transaction, dict):
                continue
            sender = normalize_wallet_address(transaction.get("from_address"))
            recipient = normalize_wallet_address(transaction.get("to_address"))
            tx_id = str(transaction.get("tx_id") or "").strip().lower()
            for address in {sender, recipient} - {None}:
                state = wallet_state(address, at_height)
                touched.add(address)
                if sender != recipient and tx_id and tx_id not in state["native"]:
                    state["native"].add(tx_id)
                    if state["first_native_epoch"] is None:
                        state["first_native_epoch"] = at_height // REVIEW_EPOCH_BLOCKS
                    state["last_native_epoch"] = at_height // REVIEW_EPOCH_BLOCKS
        for address in touched:
            state = activity[address]
            if state["creator_ready"] is None and len(state["minted"]) >= CREATOR_PATH_MIN_FINALIZED_MINTED_SUBMISSIONS:
                state["creator_ready"] = at_height
            if state["mixed_ready"] is None and (len(state["minted"]) >= MIXED_PATH_MIN_FINALIZED_MINTED_SUBMISSIONS
                                                   and len(state["native"]) >= MIXED_PATH_MIN_FINALIZED_NATIVE_TRANSACTIONS):
                state["mixed_ready"] = at_height
            if state["zoid_ready"] is None and (len(state["native"]) >= ZOID_PATH_MIN_FINALIZED_NATIVE_TRANSACTIONS
                                                  and state["last_native_epoch"] - state["first_native_epoch"] >= ZOID_PATH_MIN_ACTIVITY_SPAN_EPOCHS):
                state["zoid_ready"] = at_height
    qualifications = {}
    for address, state in activity.items():
        age_height = state["origin"] + MIN_WALLET_AGE_EPOCHS * REVIEW_EPOCH_BLOCKS
        candidates = [max(age_height, state[key]) for key in ("creator_ready", "mixed_ready", "zoid_ready")
                      if state[key] is not None]
        if candidates and min(candidates) <= height:
            qualifications[address] = min(candidates)
    payload = {"version": INDEX_VERSION, "reviewer_policy_version": REVIEWER_POLICY_VERSION,
               "height": height, "block_hash": block_hash.lower(),
               "qualification_heights": qualifications,
               "qualification_entry_digests": {
                   wallet: qualification_entry_digest(height, block_hash, wallet, qualified)
                   for wallet, qualified in qualifications.items()
               }}
    return {**payload, "digest": canonical_hash(payload)}


def validate_snapshot(snapshot, chain, finalized_references) -> bool:
    if not isinstance(snapshot, dict) or snapshot.get("version") != INDEX_VERSION or snapshot.get("reviewer_policy_version") != REVIEWER_POLICY_VERSION:
        return False
    height, block_hash = snapshot.get("height"), snapshot.get("block_hash")
    if (isinstance(height, bool) or not isinstance(height, int) or height < 0 or height >= len(chain)
        or not isinstance(block_hash, str) or (height, block_hash) not in finalized_references
        or str(_value(chain[height], "hash")).lower() != block_hash):
        return False
    qualifications = snapshot.get("qualification_heights")
    entry_digests = snapshot.get("qualification_entry_digests")
    if not isinstance(qualifications, dict) or any(
        normalize_wallet_address(wallet) != wallet or isinstance(qualified, bool)
        or not isinstance(qualified, int) or qualified < 0 or qualified > height
        for wallet, qualified in qualifications.items()
    ):
        return False
    if (not isinstance(entry_digests, dict) or set(entry_digests) != set(qualifications)
        or any(entry_digests[wallet] != qualification_entry_digest(height, block_hash, wallet, qualified)
               for wallet, qualified in qualifications.items())):
        return False
    payload = {key: snapshot[key] for key in ("version", "reviewer_policy_version", "height", "block_hash", "qualification_heights", "qualification_entry_digests")}
    return snapshot.get("digest") == canonical_hash(payload)
