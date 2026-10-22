"""Read-only, test-only application history integration for v2 evidence.

Local accepted lifecycle/finality records are trusted application state, not
cryptographic proofs supplied by a peer. Signatures authenticate the contents;
the existing eligibility/reputation services derive qualifications. The frozen
v2 journal port has no active implementation or public registration.
"""
from contextlib import closing, contextmanager
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Protocol

from admission_certificate import validate_admission_certificate
from milestone5_policy import ESTABLISHED_MAX_VOTES_PER_EPOCH, PROBATION_MAX_VOTES_PER_EPOCH, review_epoch
from native_transfer import normalize_wallet_address
from reviewer_reputation import canonical_signed_vote_evidence, ReviewerReputationService, validate_offense_evidence
from services.reviewer_eligibility_service import ReviewerEligibilityService
from storage import SQLiteStorageBackend, _normalized_vote_record

from . import evidence
from .admission import Failure, IntegrationError, TestOnlyConfig
from .issuance import EvidenceIssuer, IncompleteEvidence, IssuanceDependencies, ReviewerDecision, VerifiedCertificate
from .primitives import Context, V3Error, canonical, digest, h64, parse, require, uint


@dataclass(frozen=True)
class FrozenReview:
    """Accepted FULL selection and fresh rights record from a trusted journal.

    Context/reference metadata must be recorded at acceptance, never inferred
    from the certificate caller. Bytes have the unchanged Task 7.14 schemas.
    """
    context: Context
    votes_bytes: bytes
    attestation_bytes: bytes


class FrozenReviewJournal(Protocol):
    def load(self, connection, context, submission_id, original_hash) -> FrozenReview | None:
        """Read the immutable accepted selection in the supplied read transaction.

        None means unavailable, including no approved v2 selection/freeze policy.
        Implementations must not obtain the selection from the issuance caller.
        Acceptance must retain the application challenge/nonce, expiry, daily
        admission policy and participation checks at the recorded references.
        Missing acceptance history cannot be represented as an accepted record.
        """

    def claimed(self, connection, keys: tuple[str, ...]) -> tuple[str, ...]:
        """Return the already consumed replay keys in this SAME transaction."""


@dataclass(frozen=True)
class ReplayPlan:
    context: Context
    history_digest: str
    canonical_head: tuple[int, str]
    finalized_head: tuple[int, str]
    keys: tuple[str, ...]


@dataclass(frozen=True)
class CertificationProposal:
    """Verified evidence plus an UNCONSUMED replay plan; no mint authority."""
    evidence: VerifiedCertificate
    replay: ReplayPlan


class AtomicCertificationStore(Protocol):
    def commit(self, proposal: CertificationProposal, canonical_record: bytes):
        """Future boundary, deliberately unimplemented here.

        Under one write transaction: re-read head/finality/history revision,
        reverify admission/selection/ledger/queue and all replay keys, persist
        certificate AND canonical block AND claims, commit before acknowledge.
        On stale state, conflict, error or reorg, roll back ALL effects. A
        proposal or a successful read-only preflight is never authorization.
        """


class _TransactionStorage(SQLiteStorageBackend):
    """Reuse existing read methods without opening/committing nested connections."""
    def __init__(self, connection):
        self.connection = connection

    @contextmanager
    def _connect(self):
        yield self.connection


class SQLiteHistoryReader:
    """Only opens an EXISTING database read-only; no schema initialization.

    This database must be the trusted, already validated application's store.
    Validating an arbitrary uploaded database/chain/finality proof is out of scope.
    The application must explicitly pin the same genesis in TestOnlyConfig.
    """
    def __init__(self, config, storage, journal=None):
        require(type(config) is TestOnlyConfig and config.test_only is True, 'test_only_configuration_required')
        require(isinstance(storage, SQLiteStorageBackend), 'sqlite_history_required')
        self.config, self.path, self.journal = config, Path(storage.sqlite_db_path).resolve(), journal

    @contextmanager
    def read(self):
        with closing(sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True, timeout=5)) as connection:
            connection.execute('PRAGMA query_only=ON')
            connection.execute('BEGIN')
            try:
                yield _TransactionStorage(connection)
            finally:
                connection.rollback()


class _Projection:
    """Disposable verified inputs to the EXISTING reviewer/reputation services."""
    def __init__(self):
        self.votes, self.offenses, self.penalties = [], [], []

    def list_durable_votes(self):
        return self.votes

    def list_reviewer_offenses(self, address, *, offense_type=None):
        return [o for o in self.offenses if o['reviewer_address'] == address
                and (offense_type is None or o['offense_type'] == offense_type)]

    def list_reviewer_penalties(self, address):
        return [p for p in self.penalties if p['reviewer_address'] == address]

    def record_reviewer_offense(self, record):
        self.offenses.append(record)
        return {'replay': False}

    def record_reviewer_penalty(self, record):
        self.penalties.append(record)


class _History:
    def __init__(self, storage, context, wallets):
        self.context = context
        document = storage._load_sections_from_connection(storage.connection, include_native_records=False)
        self.chain = document['chain']
        self.submissions = {s['submission_id']: s for s in document['submissions']}
        require(len(self.submissions) == len(document['submissions']), 'duplicate_history_submission')
        if not self.chain or not document['finalized_blocks']:
            raise IntegrationError(Failure.INCOMPLETE, 'finalized_application_history')
        for height, block in enumerate(self.chain):
            require(type(block) is dict and type(block['index']) is int and block['index'] == height,
                    'history_chain_order')
            h64(block['hash'])
            if block.get('network_id') is None:
                raise IntegrationError(Failure.INCOMPLETE, 'history_network_provenance')
            require(block['network_id'] == context.network_id, 'history_network_mismatch')
            if height:
                require(block['previous_hash'] == self.chain[height - 1]['hash'], 'history_ancestry')
        require(self.chain[0]['hash'] == context.genesis_hash, 'history_genesis_mismatch')
        self.references = set()
        for record in document['finalized_blocks']:
            height, block_hash = uint(record['block_height']), h64(record['block_hash'])
            require(height < len(self.chain) and self.chain[height]['hash'] == block_hash,
                    'contradictory_finalized_history')
            self.references.add((height, block_hash))
        self.finalized = max(self.references)
        self.head = (len(self.chain) - 1, self.chain[-1]['hash'])
        self.service, self.projection = ReviewerEligibilityService(), _Projection()
        # Only these reviewers can affect the selected qualification. No current
        # reviewer_states/status labels or caller reputation summary is consulted.
        rows, offenses, penalties, transitions = [], [], [], []
        for wallet in sorted(wallets):
            wallet_rows = storage.list_durable_votes_for_reviewer(wallet)
            for row in wallet_rows:
                if row['lifecycle_state'] != 'accepted' or row['identity_status'] == 'legacy_unverifiable':
                    continue
                source = storage.connection.execute(
                    'SELECT source_record_json FROM durable_vote_records WHERE evidence_id=?', (row['evidence_id'],)
                ).fetchone()
                normalized = _normalized_vote_record(json.loads(source[0]))
                columns = set(row) - {'lifecycle_state', 'rejection_reason', 'observed_at'}
                require(canonical({k: row[k] for k in columns}) ==
                        canonical({k: normalized[k] for k in columns}), 'contradictory_vote_storage')
            rows.extend(wallet_rows)
            offenses.extend(storage.list_reviewer_offenses(wallet))
            wallet_penalties = storage.list_reviewer_penalties(wallet)
            penalties.extend(wallet_penalties)
            transitions.extend(storage.list_reviewer_state_history(wallet))
        # Retain the full source fingerprint for later write-transaction CAS.
        # Legacy application state contains floats. This LOCAL revision uses
        # its JSON representation, never the new consensus serializer/hash.
        source = dict(chain=self.chain, submissions=document['submissions'],
                      finalized=document['finalized_blocks'], votes=rows, offenses=offenses,
                      penalties=penalties, transitions=transitions)
        self.fingerprint = hashlib.sha256(json.dumps(source, sort_keys=True, separators=(',', ':'),
            ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()
        self._authenticate(rows, offenses, penalties)
        for transition in transitions:
            if transition['to_status'] not in ('COOLDOWN', 'SUSPENDED'):
                continue  # Positive/current labels never grant qualification.
            height, block_hash = transition['status_effective_height'], transition['status_reference_block_hash']
            if height is None or block_hash is None:
                raise IntegrationError(Failure.INCOMPLETE, 'historical_penalty_reference')
            self.reference(height, block_hash)
            require(transition['reviewer_policy_version'] == 1 and transition['reputation_rule_version'] == 2,
                    'history_penalty_policy')
            if not any(p['reviewer_address'] == transition['reviewer_address']
                    and p['penalty_status'] == transition['to_status']
                    and p['reference_finalized_height'] <= height
                    and p['penalty_start_epoch'] <= review_epoch(height) < p['penalty_end_epoch']
                    for p in self.projection.penalties):
                raise IntegrationError(Failure.INCOMPLETE, 'unbacked_penalty_transition')

    def reference(self, height, block_hash):
        uint(height)
        h64(block_hash)
        require((height, block_hash) in self.references, 'unfinalized_reviewer_reference')

    def state(self, wallet, height, block_hash):
        self.reference(height, block_hash)
        # Future participation/penalties must not affect an earlier reference.
        projection = _Projection()
        projection.votes = [v for v in self.projection.votes if v['reviewer_status_effective_height'] <= height]
        projection.penalties = [p for p in self.projection.penalties if p['reference_finalized_height'] <= height]
        return self.service.status_at_reference(reviewer_address=wallet, chain=self.chain,
            finalized_head=dict(block_height=height, block_hash=block_hash), storage=projection,
            policy_version=1, reputation_rule_version=2)

    def status(self, wallet, height, block_hash):
        return self.state(wallet, height, block_hash)['status']

    def _authenticate(self, rows, offenses, penalties):
        events = [(r['observed_at'], 0, r['evidence_id'], r) for r in rows if r['lifecycle_state'] == 'accepted']
        events += [(o['recorded_at'], 1, o['offense_id'], o) for o in offenses]
        seen = set()
        for _, kind, _, record in sorted(events):
            if kind:
                require(all(v['network_id'] == self.context.network_id for v in record['evidence_payload']['votes']),
                        'offense_history_network_mismatch')
                verified = validate_offense_evidence(record,
                    finalized_reference_validator=lambda h, b: (h, b) in self.references,
                    creator_resolver=lambda sid: self.submissions.get(sid, {}).get('submitter'),
                    accepted_vote_resolver=lambda identity: next((v for v in self.projection.votes
                        if v['vote_identity'] == identity), None),
                    reviewer_status_resolver=lambda vote: self.status(vote['reviewer_address'],
                        vote['reviewer_status_effective_height'], vote['reviewer_status_reference_block_hash']))
                height, block_hash = verified['reference_finalized_height'], verified['reference_finalized_block_hash']
                state = self.state(verified['reviewer_address'], height, block_hash)
                status = state.get('underlying_status', state['status'])
                # Use the unchanged service to reproduce penalty schedule and
                # escalation, never a caller's summary or stored penalty label.
                outcome = ReviewerReputationService(self.projection).apply_verified_offense(verified, state_before=status)
                for field in ('recorded_state_before', 'resulting_state', 'penalty_start_epoch',
                              'penalty_end_epoch', 'escalation_count'):
                    require(record[field] == outcome.offense[field], 'history_offense_projection')
                continue
            if record['identity_status'] == 'legacy_unverifiable':
                raise IntegrationError(Failure.INCOMPLETE, 'unsigned_reviewer_participation')
            require(record['identity_status'] == 'canonical' and record['vote_identity'], 'history_vote_identity')
            signed = canonical_signed_vote_evidence(record)
            require(signed['network_id'] == self.context.network_id, 'participation_history_network_mismatch')
            require(signed['vote_identity'] == record['vote_identity'], 'history_vote_identity')
            height, block_hash = record['reviewer_status_effective_height'], record['reviewer_status_reference_block_hash']
            if height is None or block_hash is None:
                raise IntegrationError(Failure.INCOMPLETE, 'historical_vote_reference')
            status = self.status(record['voter_address'], height, block_hash)
            require(record['reviewer_policy_version'] == 1 and record['reputation_rule_version'] == 2,
                    'history_reviewer_policy')
            require(record['reviewer_eligible'] is True and record['reviewer_status'] == status
                    and status in ('PROBATIONARY_REVIEWER', 'ESTABLISHED_REVIEWER'), 'history_reviewer_status')
            submission = self.submissions.get(record['submission_id'])
            if submission is None:
                raise IntegrationError(Failure.INCOMPLETE, 'historical_vote_submission')
            creator = normalize_wallet_address(submission['submitter'])
            require(creator is not None and submission['content_hash'] == record['content_hash']
                    and creator != record['voter_address'], 'history_vote_binding')
            key = (record['voter_address'], record['submission_id'], record['dimension'])
            require(key not in seen, 'duplicate_history_vote')
            seen.add(key)
            require(self.quota(record['voter_address'], record['submission_id'], height, status), 'history_epoch_quota')
            self.projection.votes.append(record)
        expected = [{k: v for k, v in p.items() if k != 'recorded_at'} for p in penalties]
        require(canonical(sorted(expected, key=lambda p: p['penalty_id'])) ==
                canonical(sorted(self.projection.penalties, key=lambda p: p['penalty_id'])), 'history_penalty_mismatch')

    def quota(self, wallet, submission, height, status):
        epoch = review_epoch(height)
        participation = {v['submission_id'] for v in self.projection.votes
            if v['voter_address'] == wallet and v['reviewer_status_effective_height'] <= height
            and review_epoch(v['reviewer_status_effective_height']) == epoch}
        limit = (PROBATION_MAX_VOTES_PER_EPOCH if status == 'PROBATIONARY_REVIEWER'
                 else ESTABLISHED_MAX_VOTES_PER_EPOCH if status == 'ESTABLISHED_REVIEWER' else 0)
        return bool(limit and (submission in participation or len(participation) < limit))

    def decision(self, context, vote):
        require(context == self.context, 'history_context_mismatch')
        status = self.status(vote['voter_wallet_address'], vote['reviewer_status_effective_height'],
                             vote['reviewer_status_reference_block_hash'])
        eligible = self.quota(vote['voter_wallet_address'], vote['submission_id'],
                              vote['reviewer_status_effective_height'], status)
        return ReviewerDecision(status, eligible)


def replay_keys(context, certificate):
    """Local claim identifiers, NOT new signing domains or wire evidence fields.

    Namespace excludes policies so changing policy cannot re-mint an original.
    Message/nonce keys also block high-S equivalent signatures of the same vote.
    """
    prefix = dict(network_id=context.network_id, genesis_hash=context.genesis_hash, protocol_version=2)
    keys = []

    def add(kind, *identity):
        keys.append(digest(dict(**prefix, kind=kind, identity=list(identity))))

    add('original', certificate['content_hash'])
    add('submission', certificate['submission_id'])
    add('certificate', certificate['certificate_digest'])
    attestation = certificate['attestation']
    add('attestation_nonce', attestation['signer_wallet'], attestation['nonce'])
    add('attestation_message', attestation['canonical_message_hash'])
    add('attestation_signature', attestation['signature'])
    for vote in certificate['votes']:
        add('review', vote['submission_id'], vote['dimension'], vote['voter_wallet_address'])
        add('vote_nonce', vote['voter_wallet_address'], vote['vote_nonce'])
        add('vote_message', vote['signed_message_hash'])
        add('vote_signature', vote['vote_signature'])
    require(len(set(keys)) == len(keys), 'duplicate_replay_claim')
    return tuple(sorted(keys))


class AuthenticatedHistoryAdapter:
    """No caller votes, eligibility flags or reputation summaries enter issue()."""
    def __init__(self, adapter, reader):
        require(type(reader) is SQLiteHistoryReader and reader.config == adapter.config,
                'matching_history_reader_required')
        self.adapter, self.reader = adapter, reader

    def issue(self, prepared):
        try:
            return self._issue(prepared)
        except IntegrationError as exc:
            if exc.classification == Failure.INCOMPLETE:
                return IncompleteEvidence((exc.code,))
            raise
        except (V3Error, ValueError, TypeError, KeyError) as exc:
            raise IntegrationError(Failure.INVALID_CANONICAL, getattr(exc, 'code', 'invalid_application_history')) from exc
        except Exception as exc:
            raise IntegrationError(Failure.LOCAL_FAILURE, 'history_storage_unavailable') from exc

    def _issue(self, prepared):
        self.adapter.verify_prepared(prepared)
        if self.reader.journal is None:
            return IncompleteEvidence(('accepted_v2_history_journal',))
        app, context = prepared.certificate, self.adapter.config.context
        with self.reader.read() as storage:
            try:
                frozen = self.reader.journal.load(storage.connection, context, app['submission_id'], app['content_hash'])
            except Exception as exc:
                raise IntegrationError(Failure.LOCAL_FAILURE, 'frozen_history_unavailable') from exc
            if frozen is None:
                return IncompleteEvidence(('accepted_v2_review_snapshot',))
            if type(frozen) is not FrozenReview:
                raise IntegrationError(Failure.LOCAL_FAILURE, 'invalid_frozen_history_contract')
            require(frozen.context == context, 'frozen_history_context')
            votes, attestation = parse(frozen.votes_bytes, limit=196608), parse(frozen.attestation_bytes, limit=16384)
            evidence.validate_votes(votes, context)
            evidence.validate_attestation(attestation, context)
            wallets = {v['voter_wallet_address'] for v in votes}
            wallets.update(v['voter_wallet_address'] for v in app['votes'])
            history = _History(storage, context, wallets)
            stored = history.submissions.get(app['submission_id'])
            if stored is None or stored.get('admission_certificate') is None:
                return IncompleteEvidence(('application_submission_certificate',))
            require(stored['content_hash'] == app['content_hash'] and stored['submitter'] == app['creator_wallet']
                    and canonical(stored['admission_certificate']) == prepared.application_certificate_bytes,
                    'application_submission_binding')
            require(not any(b.get('content_hash') == app['content_hash'] or b.get('submission_id') == app['submission_id']
                            for b in history.chain), 'previously_minted_original_or_submission')
            validate_admission_certificate(app, media_bytes=prepared.original,
                                           reviewer_status_resolver=history.status)
            # The issuer independently checks signatures, bindings, complete
            # selection, separate quorum, exact tallies and technical evidence.
            issuer = EvidenceIssuer(self.adapter, IssuanceDependencies(
                lambda ctx, sid, original: frozen.votes_bytes if ctx == context and
                    (sid, original) == (app['submission_id'], app['content_hash']) else None,
                history.decision))
            # Precheck here so typed invalid/missing history is not hidden by the
            # Task 7.14 callback-exception (operational failure) contract.
            for vote in votes:
                decision = history.decision(context, vote)
                require(decision.eligible and decision.status == vote['reviewer_status'], 'history_reviewer_ineligible')
            result = issuer.issue(prepared, attestation=attestation, votes=votes)
            if type(result) is IncompleteEvidence:
                return result
            keys = replay_keys(context, result.certificate)
            try:
                claimed = self.reader.journal.claimed(storage.connection, keys)
            except Exception as exc:
                raise IntegrationError(Failure.LOCAL_FAILURE, 'replay_history_unavailable') from exc
            if type(claimed) is not tuple or not all(type(k) is str and k in keys for k in claimed):
                raise IntegrationError(Failure.LOCAL_FAILURE, 'replay_lookup_contract')
            require(not claimed, 'evidence_replay_conflict')
            fingerprint = digest(dict(application=history.fingerprint, votes=digest(votes), attestation=digest(attestation)))
            return CertificationProposal(result, ReplayPlan(context, fingerprint, history.head, history.finalized, keys))
