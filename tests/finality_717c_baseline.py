"""Frozen Task 7.17C durability witnesses; NEVER imported by production.

Exact two method bodies from f025e6097cceca6b9286bf2cefaff35825fff7a7.
The historical diagnostic harness disables the new storage guard explicitly;
current repaired behavior is tested separately in Task 7.17E. This snapshot is
unsafe historical evidence, not a fallback or alternate production path.
"""
from copy import deepcopy
from blockchain import Blockchain
from services import FinalityAttestationError


class HistoricalFinalityBlockchain(Blockchain):
    def save_blockchain(self):
        """Save blockchain state to disk, including wallets and transactions."""
        local_state = self._serialize_blockchain_state()
        def reject_stale_reports(durable):
            # Legacy callers replace a whole state snapshot. Under the same
            # storage lock used by report admission and mint, refuse a snapshot
            # that differs from committed report or report-quarantine state.
            local_by_id = {item["submission_id"]: item for item in local_state["submissions"]}
            durable_by_id = {item["submission_id"]: item for item in durable.get("submissions", [])}
            for submission_id in local_by_id.keys() | durable_by_id.keys():
                local = local_by_id.get(submission_id) or {}
                committed = durable_by_id.get(submission_id) or {}
                if not (local.get("community_reports") or committed.get("community_reports")
                        or local.get("quarantine_reason") == "community_report_threshold"
                        or committed.get("quarantine_reason") == "community_report_threshold"):
                    continue
                if (local.get("community_reports") != committed.get("community_reports")
                    or local.get("report_quarantine_evidence") != committed.get("report_quarantine_evidence")
                    or (committed.get("quarantine_reason") == "community_report_threshold" and (
                        local.get("status") != committed.get("status")
                        or local.get("quarantine_reason") != committed.get("quarantine_reason")
                        or submission_id in local_state["mint_queue"]
                    ))):
                    raise ValueError("Stale community reporting state; reload before saving.")
            # The facade does not serialize peer records or future storage
            # sections. Keep those locked durable sections in the replacement.
            # Disputes are an independent finalized-content overlay. A stale
            # facade saving other state must carry forward the durable set,
            # never erase it or block an otherwise valid chain update.
            return {**durable, **local_state,
                    "post_mint_disputes": deepcopy(durable.get("post_mint_disputes", {}) or {})}

        self.storage.atomic_update_blockchain_document(reject_stale_reports)
        print("Debug: Blockchain and wallets saved successfully.")

    def submit_validator_finality_attestations(self, attestations) -> list[dict]:
        """Validate and durably apply one or more votes against one chain snapshot.

        Batching is an operational optimization only: every attestation still
        passes the existing canonical validator, signature, quorum, and
        finalized-height checks.  A shared chain validation and one durable
        checkpoint prevent a received quorum from doing duplicate full-chain
        work and writes.
        """
        if not isinstance(attestations, (list, tuple)) or not attestations:
            raise FinalityAttestationError("Finality attestations must be a non-empty list.")
        if not self.is_chain_valid(self.chain_to_dicts(self.chain)):
            raise FinalityAttestationError("Finality cannot be applied while canonical chain validation fails.")

        updated_attestations = list(self.finality_attestations)
        updated_finalized_blocks = list(self.finalized_blocks)
        results = []
        canonical_by_height = {int(block.index): block.to_dict() for block in self.chain}
        for attestation in attestations:
            if not isinstance(attestation, dict):
                raise FinalityAttestationError("Finality attestation must be an object.")
            height = self._finality_service._height(attestation.get("block_height"))
            canonical = canonical_by_height.get(height)
            if canonical is None:
                raise FinalityAttestationError("Finality attestation references a nonexistent canonical block.")
            if canonical.get("hash") != self.calculate_hash_from_dict(canonical):
                raise FinalityAttestationError("Finality attestation references a canonical block with an invalid stored hash.")
            result = self._finality_service.process_attestation(
                attestation,
                validator_set=self.validator_set,
                expected_network_id=self.protocol_v1_network_id(),
                canonical_block=canonical,
                existing_attestations=updated_attestations,
                finalized_blocks=updated_finalized_blocks,
            )
            if result["status"] != "duplicate":
                updated_attestations.append(result["attestation"])
            if result["status"] != "duplicate" and result.get("finalization") is not None:
                updated_finalized_blocks.append(result["finalization"])
            results.append((result, canonical))

        if any(result["status"] != "duplicate" for result, _ in results):
            self.finality_attestations = sorted(
                updated_attestations,
                key=lambda value: (value["block_height"], value["block_hash"], value["validator_address"], value["signature"]),
            )
            self.finalized_blocks = sorted(
                updated_finalized_blocks,
                key=lambda value: (value["block_height"], value["block_hash"]),
            )
            self._set_report_reviewer_index(self._report_reviewer_index, rebuild=True)
            self.save_blockchain()
        for result, canonical in results:
            if result.get("finalization") is not None:
                submission_id = canonical.get("submission_id")
                if submission_id:
                    self.lifecycle_timing.mark(
                        submission_id,
                        "finalized",
                        block_height=canonical["index"],
                        block_hash=canonical["hash"],
                    )
        if any(result.get("finalization") is not None for result, _ in results):
            self.reconcile_canonical_reviewer_states()
        return [result for result, _ in results]
