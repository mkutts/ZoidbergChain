"""Deterministic canonical-chain confirmation and finality views."""

from dataclasses import dataclass
from typing import Callable, Iterable


@dataclass(frozen=True)
class FinalityPolicy:
    confirmation_depth: int
    finality_depth: int
    finality_model: str = "operational_depth"
    finality_scope: str = "policy_not_bft"


class FinalityService:
    """Derive Protocol v1 lifecycle facts without owning chain state."""

    @staticmethod
    def policy(policy: FinalityPolicy) -> dict[str, object]:
        return {
            "confirmation_depth": int(policy.confirmation_depth),
            "finality_depth": int(policy.finality_depth),
            "finality_model": policy.finality_model,
            "finality_scope": policy.finality_scope,
        }

    @staticmethod
    def block_field(block, field_name, default=None):
        if isinstance(block, dict):
            return block.get(field_name, default)
        return getattr(block, field_name, default)

    def find_protocol_block(
        self,
        chain: Iterable,
        *,
        field_name: str,
        value,
        is_protocol_block: Callable[[object], bool],
    ):
        normalized_value = str(value or "").strip()
        if not normalized_value:
            return None
        for block in chain:
            if not is_protocol_block(block):
                continue
            if str(self.block_field(block, field_name) or "").strip() == normalized_value:
                return block
        return None

    def block_chain_state(self, block_or_hash, chain_dicts, policy: FinalityPolicy) -> dict[str, object]:
        policy_dict = self.policy(policy)
        target_hash = (
            str(block_or_hash or "").strip()
            if isinstance(block_or_hash, str)
            else str(self.block_field(block_or_hash, "hash") or "").strip()
        )
        state = {
            "accepted": False,
            "block_created": False,
            "block_accepted": False,
            "canonical": False,
            "confirmations": None,
            "confirmed": False,
            "finalized": False,
            **policy_dict,
            "block_hash": target_hash or None,
            "block_height": None,
            "phase": "none",
        }
        if not target_hash:
            return state

        target_block = next(
            (block for block in chain_dicts if str(block.get("hash") or "").strip() == target_hash),
            None,
        )
        if target_block is None:
            return state

        confirmations = int(chain_dicts[-1]["index"]) - int(target_block["index"])
        confirmed = confirmations >= policy.confirmation_depth
        finalized = confirmations >= policy.finality_depth
        phase = "finalized" if finalized else ("confirmed" if confirmed else "canonical")
        state.update(
            {
                "accepted": True,
                "block_created": True,
                "block_accepted": True,
                "canonical": True,
                "confirmations": confirmations,
                "confirmed": confirmed,
                "finalized": finalized,
                "block_height": int(target_block["index"]),
                "phase": phase,
            }
        )
        return state
