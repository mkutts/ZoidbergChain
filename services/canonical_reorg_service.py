"""Deterministic reconstruction of canonical state after fork-choice adoption."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from dataclasses import dataclass

from block import PROTOCOL_V1_BLOCK_VERSION
from native_transfer import validate_transaction_shape
from services.native_ledger_service import NativeLedgerState
from services.native_transaction_validation_service import NativeTransactionValidationError
from submission import APPROVED, MINTED, QUEUED


class CanonicalReorgError(RuntimeError):
    """The requested canonical replacement cannot be reconstructed safely."""


@dataclass(frozen=True)
class ChainBranchDelta:
    common_ancestor_height: int
    common_ancestor_hash: str
    detached_blocks: tuple[dict, ...]
    attached_blocks: tuple[dict, ...]

    def to_dict(self) -> dict:
        return {
            "common_ancestor_height": self.common_ancestor_height,
            "common_ancestor_hash": self.common_ancestor_hash,
            "detached_blocks": [deepcopy(block) for block in self.detached_blocks],
            "attached_blocks": [deepcopy(block) for block in self.attached_blocks],
        }


class CanonicalReorgService:
    """Rebuild a complete durable document from a winning canonical chain.

    The service mutates only the caller's isolated document copy. Its caller is
    responsible for placing that copy inside the backend's atomic replacement
    boundary and publishing the committed result afterward.
    """

    @staticmethod
    def _block_dict(block) -> dict:
        return deepcopy(block.to_dict() if hasattr(block, "to_dict") else dict(block))

    @staticmethod
    def _hash(block: dict) -> str:
        return str(block.get("hash") or "").strip().lower()

    @staticmethod
    def _height(block: dict) -> int:
        try:
            return int(block.get("index"))
        except (TypeError, ValueError) as exc:
            raise CanonicalReorgError("Canonical branch contains an invalid block height.") from exc

    @classmethod
    def branch_delta(cls, old_chain, winning_chain) -> ChainBranchDelta:
        """Find the common ancestor by hash/previous-hash lineage, never height alone."""
        old_blocks = tuple(cls._block_dict(block) for block in old_chain or [])
        new_blocks = tuple(cls._block_dict(block) for block in winning_chain or [])
        if not old_blocks or not new_blocks:
            raise CanonicalReorgError("Canonical replacement requires non-empty old and winning chains.")

        old_by_hash = {cls._hash(block): block for block in old_blocks}
        new_by_hash = {cls._hash(block): block for block in new_blocks}
        if "" in old_by_hash or len(old_by_hash) != len(old_blocks):
            raise CanonicalReorgError("Old canonical chain has missing or duplicate block hashes.")
        if "" in new_by_hash or len(new_by_hash) != len(new_blocks):
            raise CanonicalReorgError("Winning canonical chain has missing or duplicate block hashes.")

        attached_reverse: list[dict] = []
        cursor = new_blocks[-1]
        visited: set[str] = set()
        while cls._hash(cursor) not in old_by_hash:
            cursor_hash = cls._hash(cursor)
            if cursor_hash in visited:
                raise CanonicalReorgError("Winning branch previous-hash lineage contains a cycle.")
            visited.add(cursor_hash)
            attached_reverse.append(cursor)
            previous_hash = str(cursor.get("previous_hash") or "").strip().lower()
            cursor = new_by_hash.get(previous_hash)
            if cursor is None:
                raise CanonicalReorgError("Winning branch has no hash-linked common ancestor with the old chain.")

        ancestor = old_by_hash[cls._hash(cursor)]
        if cls._height(ancestor) != cls._height(cursor):
            raise CanonicalReorgError("Common ancestor hash appears at conflicting block heights.")

        detached_reverse: list[dict] = []
        old_cursor = old_blocks[-1]
        visited.clear()
        while cls._hash(old_cursor) != cls._hash(ancestor):
            cursor_hash = cls._hash(old_cursor)
            if cursor_hash in visited:
                raise CanonicalReorgError("Old branch previous-hash lineage contains a cycle.")
            visited.add(cursor_hash)
            detached_reverse.append(old_cursor)
            previous_hash = str(old_cursor.get("previous_hash") or "").strip().lower()
            old_cursor = old_by_hash.get(previous_hash)
            if old_cursor is None:
                raise CanonicalReorgError("Old branch does not link back to the common ancestor.")

        return ChainBranchDelta(
            common_ancestor_height=cls._height(ancestor),
            common_ancestor_hash=cls._hash(ancestor),
            detached_blocks=tuple(reversed(detached_reverse)),
            attached_blocks=tuple(reversed(attached_reverse)),
        )

    @staticmethod
    def _block_event_time(block: dict, ledger) -> str:
        value = block.get("minted_at") or block.get("timestamp")
        converted = ledger.coerce_native_event_timestamp(
            value, now_iso="1970-01-01T00:00:00+00:00"
        )
        return converted or "1970-01-01T00:00:00+00:00"

    @classmethod
    def _reorg_event_time(cls, winning_chain: list[dict], ledger) -> str:
        return cls._block_event_time(winning_chain[-1], ledger)

    @staticmethod
    def _deterministic_transfer_id(tx_id: str) -> str:
        return hashlib.sha256(f"canonical-reorg-transfer-intent:{tx_id}".encode("utf-8")).hexdigest()

    @staticmethod
    def _transition_record(ledger, record: dict, target: str, *, event_time: str,
                           rejection_reason: str | None = None,
                           included_block_hash=None, included_block_height=None,
                           settled_at=None, admitted_at=None) -> dict:
        current = str(record.get("status") or "").strip().lower()
        ledger.validate_native_transaction_lifecycle_transition(current, target)
        updated = dict(record)
        updated.update({"status": target, "updated_at": event_time})
        if target in {"mempool", "rejected"}:
            updated.update({
                "included_block_hash": None,
                "included_block_height": None,
                "settled_at": None,
            })
        if target == "mempool":
            updated["admitted_at"] = admitted_at or record.get("admitted_at") or record.get("created_at") or record.get("timestamp")
            updated["rejection_reason"] = None
        elif target == "rejected":
            updated["rejection_reason"] = rejection_reason
        elif target == "settled":
            updated.update({
                "included_block_hash": included_block_hash,
                "included_block_height": included_block_height,
                "settled_at": settled_at,
                "rejection_reason": None,
            })
        return validate_transaction_shape(updated, network_name=ledger.network_name).to_dict()

    @classmethod
    def _catalog_chain_transactions(cls, state: NativeLedgerState, chains, ledger, *, event_time: str):
        by_id = {
            str(record.get("tx_id") or "").strip().lower(): dict(record)
            for record in state.native_transactions
        }
        order = list(by_id)
        for chain in chains:
            for block in chain:
                for payload in ledger.block_native_transactions(block):
                    checked = ledger.validation_service.validate_identity(
                        payload, network_name=ledger.network_name
                    )
                    tx_id = checked["tx_id"]
                    existing = by_id.get(tx_id)
                    if existing is not None:
                        if not ledger._same_immutable_signed_transaction(existing, checked):
                            raise CanonicalReorgError(
                                f"Native transaction {tx_id} conflicts across canonical branches."
                            )
                        continue
                    created_at = checked.get("timestamp") or event_time
                    checked.update({
                        "status": "validated_pending",
                        "created_at": created_at,
                        "updated_at": created_at,
                        "admitted_at": None,
                        "included_block_hash": None,
                        "included_block_height": None,
                        "settled_at": None,
                        "rejection_reason": None,
                    })
                    by_id[tx_id] = validate_transaction_shape(
                        checked, network_name=ledger.network_name
                    ).to_dict()
                    order.append(tx_id)
        state.native_transactions[:] = [by_id[tx_id] for tx_id in order]
        return by_id, order

    @staticmethod
    def _reconcile_submissions(document: dict, winning_chain: list[dict]) -> None:
        minted_ids = {
            str(block.get("submission_id") or "").strip()
            for block in winning_chain
            if block.get("block_version") == PROTOCOL_V1_BLOCK_VERSION
            and str(block.get("submission_id") or "").strip()
        }
        certificate_submission_ids = {
            str(certificate.get("submission_id") or "").strip()
            for certificate in document.get("originality_certificates", []) or []
            if isinstance(certificate, dict)
        }
        queue = list(document.get("mint_queue", []) or [])
        queue_set = set(queue)
        rebuilt = []
        for raw_submission in document.get("submissions", []) or []:
            submission = dict(raw_submission)
            submission_id = str(submission.get("submission_id") or "").strip()
            if submission_id in minted_ids:
                submission["status"] = MINTED
            elif submission.get("status") == MINTED and submission_id in certificate_submission_ids:
                submission["status"] = QUEUED if submission_id in queue_set else APPROVED
            rebuilt.append(submission)
        document["submissions"] = rebuilt
        document["mint_queue"] = [item for item in queue if item not in minted_ids]

    @staticmethod
    def _reconcile_finality(document: dict, winning_chain: list[dict]) -> dict:
        canonical = {
            (int(block.get("index")), str(block.get("hash") or "").strip().lower())
            for block in winning_chain
        }
        finalized = list(document.get("finalized_blocks", []) or [])
        for record in finalized:
            identity = (
                int(record.get("block_height")),
                str(record.get("block_hash") or "").strip().lower(),
            )
            if identity not in canonical:
                raise CanonicalReorgError(
                    "Winning branch would detach persisted quorum-finalized history."
                )
        old_attestations = list(document.get("finality_attestations", []) or [])
        kept_attestations = [
            attestation for attestation in old_attestations
            if (
                int(attestation.get("block_height")),
                str(attestation.get("block_hash") or "").strip().lower(),
            ) in canonical
        ]
        document["finality_attestations"] = kept_attestations
        return {
            "kept_finalized_blocks": len(finalized),
            "removed_noncanonical_attestations": len(old_attestations) - len(kept_attestations),
        }

    @staticmethod
    def _invalidate_stale_originality_evidence(document: dict, winning_chain: list[dict]) -> list[str]:
        canonical = {
            (int(block.get("index")), str(block.get("hash") or "").strip().lower())
            for block in winning_chain
        }
        retained = []
        invalidated = []
        for evidence in document.get("originality_evidence", []) or []:
            reference = (
                evidence.get("originality_reference_height"),
                str(evidence.get("originality_reference_block_hash") or "").strip().lower(),
            )
            if reference in canonical:
                retained.append(evidence)
            else:
                invalidated.append(str(evidence.get("submission_id") or ""))
        document["originality_evidence"] = retained
        invalidated_certificates = set()
        for certificate in document.get("originality_certificates", []) or []:
            if certificate.get("certificate_version") not in {2, 3}:
                continue
            references = {
                (
                    certificate.get("originality_reference_height"),
                    str(certificate.get("originality_reference_block_hash") or "").strip().lower(),
                ),
                (
                    certificate.get("certificate_reference_height"),
                    str(certificate.get("certificate_reference_block_hash") or "").strip().lower(),
                ),
            }
            if certificate.get("certificate_version") == 3:
                references.add((
                    certificate.get("reviewer_snapshot_reference_height"),
                    str(certificate.get("reviewer_snapshot_reference_block_hash") or "").strip().lower(),
                ))
            if not references <= canonical:
                certificate["evidence_binding_status"] = "invalidated_by_reorg"
                submission_id = str(certificate.get("submission_id") or "")
                invalidated_certificates.add(submission_id)
                invalidated.append(submission_id)
        for submission in document.get("submissions", []) or []:
            if str(submission.get("submission_id") or "") not in invalidated_certificates:
                continue
            if submission.get("status") != "minted":
                submission["certificate_id"] = None
                if submission.get("status") in {"approved", "queued"}:
                    submission["status"] = "pending"
        document["mint_queue"] = [
            submission_id for submission_id in document.get("mint_queue", []) or []
            if str(submission_id) not in invalidated_certificates
        ]
        return sorted(item for item in invalidated if item)

    @classmethod
    def rebuild_document(cls, document: dict, winning_chain, ledger, *, fault=None) -> tuple[dict, dict]:
        old_chain = [cls._block_dict(block) for block in document.get("chain", []) or []]
        new_chain = [cls._block_dict(block) for block in winning_chain or []]
        delta = cls.branch_delta(old_chain, new_chain)
        event_time = cls._reorg_event_time(new_chain, ledger)

        # Replay validates exact winning balances and canonical sender nonces
        # before any replacement state can be persisted.
        replay = ledger.calculate_balances_from_chain(
            NativeLedgerState(new_chain, [], []), lambda chain: list(chain), chain=new_chain
        )
        if fault is not None:
            fault("during_reorg_rebuild")

        state = NativeLedgerState(
            new_chain,
            deepcopy(document.get("transfer_intents", []) or []),
            deepcopy(document.get("native_transactions", []) or []),
        )
        by_id, record_order = cls._catalog_chain_transactions(
            state, (old_chain, new_chain), ledger, event_time=event_time
        )
        original_status = {
            tx_id: str(record.get("status") or "").strip().lower()
            for tx_id, record in by_id.items()
        }

        canonical_entries: dict[str, dict] = {}
        canonical_order: list[str] = []
        for block in new_chain:
            block_hash = cls._hash(block)
            height = cls._height(block)
            settled_at = cls._block_event_time(block, ledger)
            for payload in ledger.block_native_transactions(block):
                tx_id = str(payload.get("tx_id") or "").strip().lower()
                canonical_entries[tx_id] = {
                    "block_hash": block_hash,
                    "block_height": height,
                    "settled_at": settled_at,
                }
                canonical_order.append(tx_id)

        detached_ids = {
            str(payload.get("tx_id") or "").strip().lower()
            for block in delta.detached_blocks
            for payload in ledger.block_native_transactions(block)
        }
        winning_hashes = {cls._hash(block) for block in new_chain}
        candidates = []
        final_records: dict[str, dict] = {}

        for tx_id in canonical_order:
            record = by_id[tx_id]
            entry = canonical_entries[tx_id]
            if original_status[tx_id] == "finalized":
                if (
                    str(record.get("included_block_hash") or "").strip().lower()
                    != entry["block_hash"]
                    or record.get("included_block_height") != entry["block_height"]
                ):
                    raise CanonicalReorgError(
                        "A finalized native transaction does not match its preserved canonical block."
                    )
                final_records[tx_id] = record
                continue
            final_records[tx_id] = cls._transition_record(
                ledger, record, "settled", event_time=entry["settled_at"],
                included_block_hash=entry["block_hash"],
                included_block_height=entry["block_height"],
                settled_at=entry["settled_at"],
            )

        pending_statuses = ledger.native_mempool_eligible_statuses()
        for tx_id in record_order:
            if tx_id in canonical_entries:
                continue
            record = by_id[tx_id]
            status = original_status[tx_id]
            orphaned_canonical = (
                tx_id in detached_ids
                or (
                    status in {"included", "settled"}
                    and str(record.get("included_block_hash") or "").strip().lower() not in winning_hashes
                )
            )
            if status == "finalized" and orphaned_canonical:
                raise CanonicalReorgError("A finalized native transaction would be detached by the winning branch.")
            if status in pending_statuses or orphaned_canonical:
                candidates.append({
                    "record": record,
                    "was_pending": status in pending_statuses and not orphaned_canonical,
                })
            else:
                final_records[tx_id] = record

        # Existing active work wins a same-nonce tie over an orphan. Across
        # nonces, sender/nonce ordering is the native block ordering rule and
        # guarantees a later nonce cannot leapfrog an invalid missing nonce.
        candidates.sort(key=lambda item: (
            str(item["record"].get("from_address") or ""),
            ledger.coerce_native_nonce(item["record"].get("nonce")),
            0 if item["was_pending"] else 1,
            ledger.native_mempool_sort_key(item["record"]),
        ))

        working_state = NativeLedgerState(
            new_chain,
            [],
            [record for record in final_records.values()],
        )
        requeued: list[str] = []
        kept_pending: list[str] = []
        invalidated: list[dict] = []
        for item in candidates:
            record = item["record"]
            tx_id = str(record.get("tx_id") or "").strip().lower()
            try:
                ledger.validation_service.validate_admission_state(
                    ledger, working_state, record
                )
            except (NativeTransactionValidationError, ValueError) as exc:
                code = ledger.validation_service.code_for_error(exc)
                reason = f"reorg_{code}"
                updated = cls._transition_record(
                    ledger, record, "rejected", event_time=event_time,
                    rejection_reason=reason,
                )
                invalidated.append({"tx_id": tx_id, "reason": reason})
            else:
                updated = cls._transition_record(
                    ledger, record, "mempool", event_time=event_time,
                    admitted_at=(
                        record.get("admitted_at")
                        or record.get("created_at")
                        or record.get("timestamp")
                    ),
                )
                if item["was_pending"]:
                    kept_pending.append(tx_id)
                else:
                    requeued.append(tx_id)
            final_records[tx_id] = updated
            working_state.native_transactions.append(updated)

        state.native_transactions[:] = [final_records[tx_id] for tx_id in record_order]
        transaction_by_id = {record["tx_id"]: record for record in state.native_transactions}
        intent_by_tx_id = {}
        rebuilt_intents = []
        for raw_intent in state.transfer_intents:
            tx_id = str(raw_intent.get("tx_id") or "").strip().lower()
            if tx_id not in transaction_by_id or tx_id in intent_by_tx_id:
                continue
            intent = dict(raw_intent)
            transaction = transaction_by_id[tx_id]
            intent.update({"status": transaction["status"], "updated_at": transaction["updated_at"]})
            intent_by_tx_id[tx_id] = intent
            rebuilt_intents.append(intent)
        for tx_id in record_order:
            if tx_id in intent_by_tx_id:
                continue
            transaction = transaction_by_id[tx_id]
            rebuilt_intents.append(ledger.build_transfer_intent_record_from_transaction(
                transaction,
                transfer_id=cls._deterministic_transfer_id(tx_id),
                signed_at=transaction.get("timestamp"),
                created_at=transaction.get("created_at"),
                updated_at=transaction.get("updated_at"),
                now_iso=event_time,
            ))

        replacement = deepcopy(document)
        replacement["chain"] = new_chain
        replacement["native_transactions"] = state.native_transactions
        replacement["transfer_intents"] = rebuilt_intents
        cls._reconcile_submissions(replacement, new_chain)
        invalidated_originality = cls._invalidate_stale_originality_evidence(replacement, new_chain)
        finality_report = cls._reconcile_finality(replacement, new_chain)

        creator_rewards = sum(
            1 for block in new_chain
            if block.get("reward_type") == "meme_mining_reward" and block.get("submission_id")
        )
        voter_rewards = sum(len(block.get("voter_rewards", []) or []) for block in new_chain)
        report = {
            "adopted": True,
            "common_ancestor_height": delta.common_ancestor_height,
            "common_ancestor_hash": delta.common_ancestor_hash,
            "detached_block_hashes": [cls._hash(block) for block in delta.detached_blocks],
            "attached_block_hashes": [cls._hash(block) for block in delta.attached_blocks],
            "orphaned_transaction_ids": sorted(detached_ids - set(canonical_entries)),
            "canonical_transaction_ids": canonical_order,
            "requeued_transaction_ids": requeued,
            "kept_pending_transaction_ids": kept_pending,
            "invalidated_transactions": invalidated,
            "balances": {
                wallet: ledger.normalize_decimal_value(balance)
                for wallet, balance in sorted(replay["balances"].items())
            },
            "next_nonces": dict(sorted(replay["next_nonces"].items())),
            "canonical_native_claim_count": len(canonical_entries),
            "canonical_creator_reward_count": creator_rewards,
            "canonical_voter_reward_count": voter_rewards,
            "invalidated_originality_submission_ids": invalidated_originality,
            **finality_report,
        }
        return replacement, report
