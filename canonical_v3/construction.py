"""Explicit offline admission-to-candidate bridge; never creates finality.

No signing keys, live mempool, active selection, SQLite or consensus imports.
Missing v2 evidence/state is incomplete, not invalid media or consensus failure.
"""
from dataclasses import dataclass
from typing import Callable, Mapping

from codec_prototype.isolated_decoder import Status
from . import block, evidence, media, transactions
from .admission import AdmissionAdapter, Failure, IntegrationError
from .primitives import (
    canonical, closed, decimal_units, h64, parse, pattern, rational, require, seconds, text, uint,
)

MISSING = object()


@dataclass(frozen=True)
class IncompleteConstruction:
    missing: tuple[str, ...]
    classification: Failure = Failure.INCOMPLETE
    canonical_record: None = None


@dataclass(frozen=True)
class ConstructionState:
    """Trusted test snapshot. Never infer ledger/reviewer authority from a cert."""
    parent_index: int
    parent_hash: str
    parent_timestamp: str
    reward_pool_units: int  # millionths of ZOID
    balances: Mapping[str, int]
    next_nonces: Mapping[str, int]
    reviewer_status_resolver: Callable


@dataclass(frozen=True)
class CandidateRecord:
    canonical_record: bytes
    sizes: block.Sizes
    identity_reservation: int
    finalized: bool = False
    # Full selection/state authorization and finality are separate protocols.
    remaining: tuple[str, ...] = ('canonical_selection_authorization', 'finality_proof')


class BlockConstructionBridge:
    def __init__(self, adapter):
        require(type(adapter) is AdmissionAdapter, 'admission_adapter_required')
        self.adapter = adapter

    def construct(self, prepared, *, header, certificate=MISSING, state=MISSING,
                  native_transactions=MISSING):
        self.adapter.verify_prepared(prepared)
        ctx = self.adapter.config.context
        try:
            closed(header, 'index previous_hash timestamp minted_at miner content_type', ('meme_text',))
            # Copy bounded JSON input; never retain mutable headers/transactions.
            header = parse(canonical(header))
            uint(header['index'], 1)
            h64(header['previous_hash'])
            seconds(header['timestamp']); seconds(header['minted_at'])
            pattern(header['miner'], r'[0-9a-f]{66}')
            mime = prepared.descriptor['mime_type']
            require(type(header['content_type']) is str and header['content_type'] in (
                ('text',) if mime == 'text/plain' else ('image', 'mixed')), 'content_type')
            if 'meme_text' in header:
                require(mime != 'text/plain', 'text_caption')
                text(header['meme_text'], 1000, 4096)
            if state is not MISSING:
                require(type(state) is ConstructionState and callable(state.reviewer_status_resolver), 'construction_state')
            if native_transactions is not MISSING:
                selected = parse(canonical(native_transactions))
                transactions.validate_transactions(selected, ctx)
            if certificate is not MISSING:
                certificate = parse(canonical(certificate))
                evidence.validate_certificate(certificate, ctx)
                app = prepared.certificate
                evidence.fields_equal(certificate, {k: app[k] for k in
                    ('submission_id', 'content_hash', 'creator_wallet')})
                # New policy/context needs newly signed evidence. Structural
                # observations must still be those independently validated above.
                observations = set(evidence.TECHNICAL_FIELDS) - {
                    'policy_id', 'policy_version', 'policy_digest', 'evidence_digest'}
                evidence.fields_equal(certificate['technical_evidence'],
                    {k: app['technical_evidence'][k] for k in observations})
            missing = tuple(name for name, value in (('v2_admission_certificate', certificate),
                ('construction_state', state), ('native_transaction_selection', native_transactions)) if value is MISSING)
            if missing:
                return IncompleteConstruction(missing)
            uint(state.parent_index)
            h64(state.parent_hash)
            seconds(state.parent_timestamp)
            uint(state.reward_pool_units)
            require(header['index'] == state.parent_index + 1 and
                    header['previous_hash'] == state.parent_hash, 'parent_binding')
            seconds(header['timestamp'])
            require(decimal_units(header['timestamp']) > decimal_units(state.parent_timestamp), 'parent_time')
            require(state.reward_pool_units >= 5000000, 'reward_pool_insufficient')
            for vote in certificate['votes']:
                try:
                    status = state.reviewer_status_resolver(vote['voter_wallet_address'],
                        vote['reviewer_status_effective_height'], vote['reviewer_status_reference_block_hash'])
                except Exception as exc:
                    raise IntegrationError(Failure.LOCAL_FAILURE, 'reviewer_lookup_unavailable') from exc
                if status is None:
                    return IncompleteConstruction(('historical_reviewer_state',))
                require(status == vote['reviewer_status'], 'reviewer_snapshot_mismatch')
            balances, nonces = dict(state.balances), dict(state.next_nonces)
            for tx in selected:
                sender, recipient = tx['from_address'], tx['to_address']
                if sender not in balances or recipient not in balances or sender not in nonces:
                    return IncompleteConstruction(('native_ledger_state',))
                uint(balances[sender]); uint(balances[recipient]); uint(nonces[sender], 1)
                amount = decimal_units(tx['amount'], positive=True)
                require(int(tx['nonce']) == nonces[sender], 'ledger_nonce')
                require(balances[sender] >= amount, 'ledger_balance')
                balances[sender] -= amount
                balances[recipient] += amount
                nonces[sender] += 1
            tally = certificate['originality']
            ratio = rational(tally['positive_votes'], tally['approval_denominator'])
            creator = certificate['creator_wallet']
            payload = dict(header, block_version=3, transactions=[transactions.reward(creator)],
                native_transactions=selected, transactions_hash=transactions.aggregate_hash(selected, ctx),
                submission_id=certificate['submission_id'], certificate_id=certificate['certificate_digest'],
                vote_hash=tally['vote_set_digest'], creator_wallet=creator,
                approval_percentage=ratio, originality_score=ratio,
                decisive_vote_total=tally['approval_denominator'], minimum_votes_required=5, approved_at=0,
                reward_type='meme_mining_reward', reward_source='reward_pool', reward_recipient=creator,
                reward_amount='5', voter_rewards=[], admission_certificate=certificate, media=prepared.descriptor)
            raw = block.encode_record(payload, ctx)  # exact final signatures/evidence/tx budgets
            record = parse(raw)  # encode_record already verified the entire closed payload/signatures.
            sizes = block.check_budgets(record, raw)
            require(sizes.complete <= prepared.capacity.complete_bound, 'identity_reservation_exceeded')
        except IntegrationError:
            raise
        except (ValueError, TypeError, KeyError) as exc:
            raise IntegrationError(Failure.INVALID_CANONICAL, getattr(exc, 'code', 'invalid_construction')) from exc
        except Exception as exc:
            raise IntegrationError(Failure.LOCAL_FAILURE, 'construction_operation_unavailable') from exc
        try:
            outcome = media.reconstruct(record['envelope']['payload']['media'], decoder=self.adapter.decoder)
        except Exception as exc:
            raise IntegrationError(Failure.LOCAL_FAILURE, 'codec_worker_unavailable') from exc
        if outcome.status != Status.VALID:
            classification = Failure.LOCAL_FAILURE if outcome.status == Status.INDETERMINATE_LOCAL_FAILURE else Failure.INVALID_CANONICAL
            raise IntegrationError(classification, outcome.reason or outcome.code, outcome=outcome)
        if outcome.original != prepared.original:
            raise IntegrationError(Failure.LOCAL_FAILURE, 'coordinator_original_bytes_mismatch')
        # A claim may have appeared during construction. No claim is committed here.
        self.adapter.verify_prepared(prepared)
        return CandidateRecord(raw, sizes, prepared.capacity.complete_bound)
