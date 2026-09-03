"""Deterministic originality-based chain scoring and fork choice."""

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ForkChoiceCollaborators:
    chain_to_dicts: Callable[[object], list[dict]]
    validate_chain: Callable[[object], bool]


class ForkChoiceService:
    @staticmethod
    def cumulative_originality_score(chain) -> float:
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

    @staticmethod
    def chain_height(chain_dicts):
        return chain_dicts[-1].get("index") if chain_dicts else None

    @staticmethod
    def chain_latest_hash(chain_dicts):
        return chain_dicts[-1].get("hash") if chain_dicts else None

    @staticmethod
    def compare_summary_metrics(
        *, local_score, candidate_score, local_height, candidate_height,
        local_latest_hash, candidate_latest_hash,
    ):
        """Rank normalized summaries using the frozen fork-choice order."""
        result = {
            "local_score": local_score,
            "candidate_score": candidate_score,
            "local_height": local_height,
            "candidate_height": candidate_height,
            "local_latest_hash": local_latest_hash,
            "candidate_latest_hash": candidate_latest_hash,
        }
        if candidate_score > local_score:
            return {**result, "decision": "replace_with_candidate", "preferred": "candidate", "reason": "higher_originality_score"}
        if candidate_score < local_score:
            return {**result, "decision": "keep_local", "preferred": "local", "reason": "lower_originality_score"}
        if candidate_height > local_height:
            return {**result, "decision": "replace_with_candidate", "preferred": "candidate", "reason": "higher_chain_height"}
        if candidate_height < local_height:
            return {**result, "decision": "keep_local", "preferred": "local", "reason": "lower_chain_height"}
        if candidate_latest_hash < local_latest_hash:
            return {**result, "decision": "replace_with_candidate", "preferred": "candidate", "reason": "lower_latest_block_hash"}
        if candidate_latest_hash > local_latest_hash:
            return {**result, "decision": "keep_local", "preferred": "local", "reason": "higher_latest_block_hash"}
        return {**result, "decision": "equivalent", "preferred": "equivalent", "reason": "same_latest_block_hash"}

    def compare(self, local_chain, candidate_chain, collaborators: ForkChoiceCollaborators):
        local = collaborators.chain_to_dicts(local_chain)
        candidate = collaborators.chain_to_dicts(candidate_chain)
        local_score = self.cumulative_originality_score(local)
        candidate_score = self.cumulative_originality_score(candidate)
        local_height = self.chain_height(local)
        candidate_height = self.chain_height(candidate)
        local_hash = self.chain_latest_hash(local)
        candidate_hash = self.chain_latest_hash(candidate)
        result = {
            "local_score": local_score,
            "candidate_score": candidate_score,
            "local_height": local_height,
            "candidate_height": candidate_height,
            "local_latest_hash": local_hash,
            "candidate_latest_hash": candidate_hash,
        }

        if not local or not candidate:
            return {**result, "decision": "invalid_candidate", "preferred": "local", "reason": "candidate_chain_invalid"}
        if candidate[0].get("hash") != local[0].get("hash"):
            return {**result, "decision": "invalid_candidate", "preferred": "local", "reason": "different_genesis_hash"}
        if not collaborators.validate_chain(candidate):
            return {**result, "decision": "invalid_candidate", "preferred": "local", "reason": "candidate_chain_invalid"}
        return self.compare_summary_metrics(
            local_score=local_score,
            candidate_score=candidate_score,
            local_height=local_height,
            candidate_height=candidate_height,
            local_latest_hash=local_hash,
            candidate_latest_hash=candidate_hash,
        )
