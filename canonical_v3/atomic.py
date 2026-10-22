"""Nonactivated, single-file SQLite certification laboratory (Task 7.16).

Only explicit test configuration and trusted local snapshots are accepted.
No production factory, route, signer, fork choice or ledger settlement exists.
"""
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass
from decimal import Decimal
import hashlib
from pathlib import Path
import sqlite3

from admission_certificate import validate_admission_certificate
from milestone5_policy import ESTABLISHED_MAX_VOTES_PER_EPOCH, PROBATION_MAX_VOTES_PER_EPOCH, review_epoch
from codec_prototype.isolated_decoder import Status

from . import evidence, media
from .admission import AdmissionAdapter, Failure, IntegrationError, TestOnlyConfig
from .construction import BlockConstructionBridge, ConstructionState, IncompleteConstruction, MISSING
from .history import CertificationProposal, FrozenReview, SQLiteHistoryReader, _History, _TransactionStorage, replay_keys
from .issuance import EvidenceIssuer, IncompleteEvidence, IssuanceDependencies
from .primitives import Context, V3Error, canonical, closed, digest, h64, parse, require, seconds, uint, wallet
from .storage import (
    ChainSelectionError, SCHEMA as BLOCK_SCHEMA, StorageCorruption, StorageUnavailable,
    V3Store, _schema_objects,
)

APPLICATION_ID = 0x5A563316
SCHEMA_VERSION = 1
MAX_HISTORY = 64 * 1024 * 1024  # Local laboratory bound, never a consensus limit.
EXTRA_SCHEMA = (
    f"CREATE TABLE snapshots (id TEXT PRIMARY KEY, context BLOB NOT NULL, history BLOB NOT NULL CHECK(typeof(history)='blob' AND length(history) BETWEEN 1 AND {MAX_HISTORY}), reviews BLOB NOT NULL CHECK(typeof(reviews)='blob' AND length(reviews)<=16777216), ledger BLOB NOT NULL CHECK(typeof(ledger)='blob' AND length(ledger)<=1048576)) WITHOUT ROWID",
    "CREATE TABLE certification_state (id INTEGER PRIMARY KEY CHECK(id=1), current_snapshot TEXT NOT NULL REFERENCES snapshots(id), anchor_snapshot TEXT NOT NULL REFERENCES snapshots(id))",
    "CREATE TABLE certifications (operation TEXT PRIMARY KEY, snapshot TEXT NOT NULL REFERENCES snapshots(id), certificate_id TEXT NOT NULL UNIQUE, original TEXT NOT NULL UNIQUE, submission TEXT NOT NULL UNIQUE, certificate BLOB NOT NULL CHECK(typeof(certificate)='blob' AND length(certificate)<=196608), application BLOB NOT NULL CHECK(typeof(application)='blob' AND length(application)<=196608)) WITHOUT ROWID",
    "CREATE TABLE replay_claims (claim TEXT PRIMARY KEY, operation TEXT NOT NULL REFERENCES certifications(operation)) WITHOUT ROWID",
    "CREATE TABLE certification_participation (wallet TEXT NOT NULL, submission TEXT NOT NULL, epoch INTEGER NOT NULL, height INTEGER NOT NULL, operation TEXT NOT NULL REFERENCES certifications(operation), PRIMARY KEY(wallet,submission,epoch)) WITHOUT ROWID",
    "CREATE TABLE candidate_certifications (block_hash TEXT PRIMARY KEY REFERENCES blocks(hash), operation TEXT NOT NULL REFERENCES certifications(operation), snapshot TEXT NOT NULL REFERENCES snapshots(id)) WITHOUT ROWID",
    "CREATE TABLE selected_claims (kind TEXT NOT NULL, identity TEXT NOT NULL, block_hash TEXT NOT NULL REFERENCES blocks(hash), PRIMARY KEY(kind,identity)) WITHOUT ROWID",
    "CREATE TRIGGER immutable_anchor BEFORE UPDATE OF anchor_snapshot ON certification_state BEGIN SELECT RAISE(ABORT,'immutable snapshot anchor'); END",
) + tuple(
    f"CREATE TRIGGER immutable_{table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'immutable certification source'); END"
    for table in ('snapshots', 'certifications', 'replay_claims', 'certification_participation', 'candidate_certifications')
    for action in ('UPDATE', 'DELETE')
)
SCHEMA = BLOCK_SCHEMA + EXTRA_SCHEMA


def wal_is_fixed(version):
    """SQLite's published WAL-reset fix and supported backport families."""
    return (version >= (3, 51, 3) or
            ((3, 50, 7) <= version < (3, 51, 0)) or
            ((3, 44, 6) <= version < (3, 45, 0)))


@dataclass(frozen=True)
class TrustedSnapshot:
    """A local accepted-state checkpoint, NOT a peer proof or upload format.

    History bytes are copied with SQLite backup from one reader transaction.
    Ledger authority is supplied explicitly by the offline trusted harness.
    The frozen journal keeps its Task 7.15 acceptance/provenance obligations.
    """
    context: Context
    history: bytes
    reviews: bytes
    ledger: bytes

    @property
    def identity(self):
        return digest(dict(context=asdict(self.context),
            history=hashlib.sha256(self.history).hexdigest(),
            reviews=hashlib.sha256(self.reviews).hexdigest(),
            ledger=hashlib.sha256(self.ledger).hexdigest()))

    @classmethod
    def capture(cls, reader, references, ledger):
        require(type(reader) is SQLiteHistoryReader, 'trusted_history_reader_required')
        records = []
        with reader.read() as source:
            # Establish the source read snapshot before invoking the journal.
            source.connection.execute('SELECT count(*) FROM sqlite_master').fetchone()
            for submission, original in sorted(set(references)):
                frozen = None if reader.journal is None else reader.journal.load(
                    source.connection, reader.config.context, submission, original)
                if frozen is None:
                    continue
                require(type(frozen) is FrozenReview, 'frozen_review_contract')
                records.append(dict(submission=submission, original=original,
                    context=asdict(frozen.context), votes=frozen.votes_bytes.decode('utf-8'),
                    attestation=frozen.attestation_bytes.decode('utf-8')))
            # An in-memory backup removes WAL-file dependencies from the retained
            # image. It is a projection, not another durable transaction owner.
            with closing(sqlite3.connect(':memory:')) as copied:
                source.connection.backup(copied)
                image = copied.serialize()
        require(len(image) <= MAX_HISTORY, 'local_history_capacity')
        return cls(reader.config.context, image, canonical(records), canonical(ledger))

    @contextmanager
    def history_view(self, wallets):
        require(type(self.history) is bytes and 1 <= len(self.history) <= MAX_HISTORY, 'history_image_size')
        with closing(sqlite3.connect(':memory:')) as projection:
            projection.deserialize(self.history)
            projection.execute('PRAGMA query_only=ON')
            yield _History(_TransactionStorage(projection), self.context, wallets)


class CertificationConflict(Exception):
    """Deterministic durable ownership conflict, never invalid media."""
    classification = 'conflict'

    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class PersistedCandidate:
    operation: str
    block_hash: str
    canonical_record: bytes
    snapshot: str
    idempotent: bool
    classification: str = 'persisted_provisional'
    # This reports persistence, not the candidate's later selection/finality.


class AtomicV3Store(V3Store):
    """Explicit disposable unified schema; never upgrades a V3Store/active DB.

    Inherited block verification/lookup/finality primitives operate on THIS
    connection. Certification uses one BEGIN IMMEDIATE through COMMIT.
    Each instance belongs to one thread; separate instances serialize in SQLite.
    """
    def __init__(self, path, config, *, decoder, initial=None, timeout=5, journal_mode='DELETE'):
        require(type(config) is TestOnlyConfig and config.test_only, 'test_only_configuration_required')
        require(journal_mode in ('DELETE', 'WAL'), 'isolated_journal_mode')
        if journal_mode == 'WAL' and not wal_is_fixed(sqlite3.sqlite_version_info):
            raise StorageUnavailable('WAL requires SQLite WAL-reset fix (3.51.3+ or supported backport)')
        self.journal_mode = journal_mode
        self.path, self.ctx, self.decoder = Path(path).resolve(), config.context, decoder
        self.config, self.context_bytes = config, canonical(asdict(config.context))
        self.connection = None
        if initial is not None:
            require(type(initial) is TrustedSnapshot and initial.context == self.ctx, 'snapshot_context')
            with initial.history_view(set()) as history:
                ledger = self._ledger(initial)
                require((ledger['parent_index'], ledger['parent_hash']) == history.head, 'snapshot_ledger_parent')
                require(Decimal(ledger['parent_timestamp']) == Decimal(str(history.chain[-1]['timestamp'])),
                        'snapshot_ledger_time')
                self.anchor_height, self.anchor_hash = history.head
            with self.path.open('xb'):
                pass
        try:
            self.connection = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True,
                                             isolation_level=None, timeout=timeout)
            self.connection.execute('PRAGMA foreign_keys=ON')
            if initial is None:
                self._validate_schema()  # Refuse active/block-only DBs before any write pragma.
                if self.connection.execute('PRAGMA journal_mode').fetchone()[0] != journal_mode.lower():
                    raise StorageCorruption('journal mode mismatch; no migration attempted')
            elif self.connection.execute(f'PRAGMA journal_mode={journal_mode}').fetchone()[0] != journal_mode.lower():
                raise StorageUnavailable('requested journal mode unavailable')
            # EXTRA syncs deletion of a rollback journal's directory entry.
            # FULL is sufficient in WAL, which requires a fixed runtime above.
            self.connection.execute('PRAGMA synchronous=' + ('EXTRA' if journal_mode == 'DELETE' else 'FULL'))
            self.connection.execute('PRAGMA wal_autocheckpoint=0')
            if initial is not None:
                with self._transaction(write=True) as connection:
                    for statement in SCHEMA:
                        connection.execute(statement)
                    connection.execute(f'PRAGMA application_id={APPLICATION_ID}')
                    connection.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
                    self._put_snapshot(connection, initial)
                    connection.execute('INSERT INTO settings VALUES(1,?,?,?,NULL)',
                        (self.context_bytes, self.anchor_height, self.anchor_hash))
                    connection.execute('INSERT INTO certification_state VALUES(1,?,?)',
                                       (initial.identity, initial.identity))
            self._validate_schema()
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _ledger(snapshot):
        ledger = parse(snapshot.ledger, limit=1048576)
        closed(ledger, 'parent_index parent_hash parent_timestamp reward_pool_units balances next_nonces')
        uint(ledger['parent_index']); h64(ledger['parent_hash']); seconds(ledger['parent_timestamp'])
        uint(ledger['reward_pool_units'])
        require(type(ledger['balances']) is dict and type(ledger['next_nonces']) is dict, 'ledger_maps')
        for address, value in ledger['balances'].items():
            wallet(address); uint(value)
        for address, value in ledger['next_nonces'].items():
            wallet(address); uint(value, 1)
        return ledger

    def _validate_schema(self):
        connection = self.connection
        with closing(sqlite3.connect(':memory:')) as expected:
            for statement in SCHEMA:
                expected.execute(statement)
            if _schema_objects(connection) != _schema_objects(expected):
                raise StorageCorruption('unknown unified schema; no migration attempted')
        if (connection.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID or
                connection.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION):
            raise StorageCorruption('unified schema version')
        rows = connection.execute('SELECT id,context,anchor_height,anchor_hash FROM settings').fetchall()
        if len(rows) != 1 or rows[0][:2] != (1, self.context_bytes):
            raise StorageCorruption('unified context')
        self.anchor_height, self.anchor_hash = rows[0][2:]
        control = connection.execute('SELECT id,current_snapshot,anchor_snapshot FROM certification_state').fetchall()
        if len(control) != 1 or control[0][0] != 1:
            raise StorageCorruption('missing snapshot authority')
        snapshot = self._snapshot(connection, control[0][2])
        with snapshot.history_view(set()) as history:
            if history.head != (self.anchor_height, self.anchor_hash):
                raise StorageCorruption('snapshot anchor mismatch')

    def _put_snapshot(self, connection, snapshot):
        require(type(snapshot) is TrustedSnapshot and snapshot.context == self.ctx, 'snapshot_context')
        self._ledger(snapshot)
        records = parse(snapshot.reviews, limit=16777216)
        require(type(records) is list, 'accepted_reviews_array')
        seen = set()
        for record in records:
            closed(record, 'submission original context votes attestation')
            require(Context(**record['context']) == self.ctx, 'frozen_history_context')
            key = (record['submission'], record['original'])
            require(key not in seen, 'duplicate_accepted_selection')
            seen.add(key)
        row = (snapshot.identity, self.context_bytes, snapshot.history, snapshot.reviews, snapshot.ledger)
        existing = connection.execute('SELECT * FROM snapshots WHERE id=?', (snapshot.identity,)).fetchone()
        if existing is None:
            connection.execute('INSERT INTO snapshots VALUES(?,?,?,?,?)', row)
        elif existing != row:
            raise StorageCorruption('snapshot identity collision')

    def _snapshot(self, connection, identity):
        row = connection.execute('SELECT context,history,reviews,ledger FROM snapshots WHERE id=?', (identity,)).fetchone()
        if row is None or row[0] != self.context_bytes:
            raise StorageCorruption('missing or wrong-context snapshot')
        snapshot = TrustedSnapshot(self.ctx, *row[1:])
        if snapshot.identity != identity:
            raise StorageCorruption('snapshot digest mismatch')
        return snapshot

    def current_snapshot(self):
        with self._transaction() as connection:
            return connection.execute('SELECT current_snapshot FROM certification_state WHERE id=1').fetchone()[0]

    def install_snapshot(self, snapshot, *, expected_snapshot):
        """Trusted local CAS, preserving all previously finalized source ancestry.

        This imports a newly accepted offline checkpoint. It does not synchronize
        production history, promote v2 participation, or settle the v3 ledger.
        """
        with self._transaction(write=True) as connection:
            current = connection.execute('SELECT current_snapshot FROM certification_state WHERE id=1').fetchone()[0]
            if current != expected_snapshot:
                raise CertificationConflict('snapshot_compare_and_swap')
            require(type(snapshot) is TrustedSnapshot and snapshot.context == self.ctx, 'snapshot_context')
            old = self._snapshot(connection, current)
            with old.history_view(set()) as before, snapshot.history_view(set()) as after:
                if (not before.references <= after.references or after.finalized[0] < before.finalized[0] or
                        before.chain[:before.finalized[0] + 1] != after.chain[:before.finalized[0] + 1]):
                    raise ChainSelectionError('cannot replace finalized source history')
                boundary = max((height for height, _ in self._proofs(connection)), default=self.anchor_height)
                if any(height < len(after.chain) and after.chain[height]['hash'] != block_hash
                       for height, block_hash in self._selected(connection) if height <= boundary):
                    raise ChainSelectionError('source snapshot conflicts with retained v3 finality')
                ledger = self._ledger(snapshot)
                require((ledger['parent_index'], ledger['parent_hash']) == after.head, 'snapshot_ledger_parent')
                require(Decimal(ledger['parent_timestamp']) == Decimal(str(after.chain[-1]['timestamp'])),
                        'snapshot_ledger_time')
            self._put_snapshot(connection, snapshot)
            connection.execute('UPDATE certification_state SET current_snapshot=? WHERE id=1', (snapshot.identity,))
        return snapshot.identity

    def insert(self, raw):
        raise StorageUnavailable('use certify: unowned candidate insertion is disabled')

    def _quota(self, connection, history, certificate):
        # Existing finalized historical participation plus permanent accepted
        # v2 issuance reservations. Both dimensions count once per submission.
        rows = {}
        for vote in certificate['votes']:
            address, sid, height = vote['voter_wallet_address'], vote['submission_id'], vote['reviewer_status_effective_height']
            epoch = review_epoch(height)
            used = {v['submission_id'] for v in history.projection.votes if v['voter_address'] == address
                    and v['reviewer_status_effective_height'] <= height
                    and review_epoch(v['reviewer_status_effective_height']) == epoch}
            used.update(r[0] for r in connection.execute(
                'SELECT submission FROM certification_participation WHERE wallet=? AND epoch=? AND height<=?',
                (address, epoch, height)))
            limit = (ESTABLISHED_MAX_VOTES_PER_EPOCH if vote['reviewer_status'] == 'ESTABLISHED_REVIEWER'
                     else PROBATION_MAX_VOTES_PER_EPOCH)
            if sid not in used and len(used) >= limit:
                raise CertificationConflict('reviewer_epoch_quota')
            key = (address, sid, epoch)
            rows[key] = min(rows.get(key, height), height)
        return sorted((*key, height) for key, height in rows.items())

    def certify(self, adapter, prepared, *, operation, expected_snapshot, header,
                native_transactions=MISSING, proposal=None, fault=None):
        """Reverify admission/history/evidence and commit certificate+claims+R.

        fault(stage) is an explicit offline test seam; exceptions/death do not
        bypass rollback. No signature is created here. No fork choice occurs.
        """
        try:
            h64(operation); h64(expected_snapshot)
            require(type(adapter) is AdmissionAdapter and adapter.config == self.config, 'adapter_context')
            adapter.verify_prepared(prepared)
            closed(header, 'index previous_hash timestamp minted_at miner content_type', ('meme_text',))
            header = parse(canonical(header))
            if native_transactions is not MISSING:
                native_transactions = parse(canonical(native_transactions))
            with self._transaction(write=True) as connection:
                current = connection.execute('SELECT current_snapshot FROM certification_state WHERE id=1').fetchone()[0]
                if current != expected_snapshot:
                    return IncompleteEvidence(('stale_authoritative_snapshot',))
                snapshot = self._snapshot(connection, current)
                app = prepared.certificate
                selected = next((r for r in parse(snapshot.reviews, limit=16777216)
                    if r['submission'] == app['submission_id'] and r['original'] == app['content_hash']), None)
                if selected is None:
                    return IncompleteEvidence(('accepted_v2_review_snapshot',))
                require(Context(**selected['context']) == self.ctx, 'frozen_history_context')
                votes = parse(selected['votes'].encode(), limit=196608)
                attestation = parse(selected['attestation'].encode(), limit=16384)
                evidence.validate_votes(votes, self.ctx)
                evidence.validate_attestation(attestation, self.ctx)
                wallets = {v['voter_wallet_address'] for v in votes + app['votes']}
                with snapshot.history_view(wallets) as history:
                    stored = history.submissions.get(app['submission_id'])
                    if stored is None or stored.get('admission_certificate') is None:
                        return IncompleteEvidence(('application_submission_certificate',))
                    require(stored['content_hash'] == app['content_hash'] and stored['submitter'] == app['creator_wallet']
                        and canonical(stored['admission_certificate']) == prepared.application_certificate_bytes,
                        'application_submission_binding')
                    if any(b.get('content_hash') == app['content_hash'] or b.get('submission_id') == app['submission_id']
                           for b in history.chain):
                        raise CertificationConflict('previously_minted_original_or_submission')
                    validate_admission_certificate(app, media_bytes=prepared.original,
                                                   reviewer_status_resolver=history.status)
                    for vote in votes:
                        decision = history.decision(self.ctx, vote)
                        require(decision.eligible and decision.status == vote['reviewer_status'], 'history_reviewer_ineligible')
                    issuer = EvidenceIssuer(adapter, IssuanceDependencies(
                        lambda ctx, sid, original: selected['votes'].encode() if ctx == self.ctx and
                            (sid, original) == (app['submission_id'], app['content_hash']) else None, history.decision))
                    issued = issuer.issue(prepared, attestation=attestation, votes=votes)
                    if type(issued) is IncompleteEvidence:
                        return issued
                    cert = issued.certificate
                    if proposal is not None:
                        require(type(proposal) is CertificationProposal and proposal.evidence == issued
                                and proposal.replay.context == self.ctx
                                and proposal.replay.keys == replay_keys(self.ctx, cert), 'proposal_binding')
                        revision = digest(dict(application=history.fingerprint, votes=digest(votes), attestation=digest(attestation)))
                        if (proposal.replay.history_digest != revision or proposal.replay.canonical_head != history.head
                                or proposal.replay.finalized_head != history.finalized):
                            return IncompleteEvidence(('stale_history_proposal',))
                    ledger = self._ledger(snapshot)
                    # Only parents with a retained authoritative ledger snapshot
                    # can be constructed. Do not guess a descendant's balances.
                    if (header.get('previous_hash'), header.get('index')) != (ledger['parent_hash'], ledger['parent_index'] + 1):
                        return IncompleteConstruction(('authoritative_parent_ledger',))
                    state = ConstructionState(**ledger, reviewer_status_resolver=history.status)
                    if type(native_transactions) is list:
                        settled = {tx['tx_id'] for b in history.chain for tx in b.get('native_transactions', [])}
                        require(not any(tx.get('tx_id') in settled for tx in native_transactions),
                                'ancestry_transaction_replay')
                    candidate = BlockConstructionBridge(adapter).construct_issued(prepared, issuer=issuer, issued=issued,
                        header=header, state=state, native_transactions=native_transactions)
                    if type(candidate) is IncompleteConstruction:
                        return candidate
                    record = self._verify(candidate.canonical_record)
                    keys = replay_keys(self.ctx, cert)
                    existing = connection.execute('SELECT snapshot,certificate,application FROM certifications WHERE operation=?',
                                                  (operation,)).fetchone()
                    identity = (current, issued.certificate_bytes, prepared.application_certificate_bytes)
                    if existing is not None and existing[1:] != identity[1:]:
                        raise CertificationConflict('operation_identity')
                    if existing is None:
                        for column, value, code in (('original', cert['content_hash'], 'original_claim'),
                                ('submission', cert['submission_id'], 'submission_claim'),
                                ('certificate_id', cert['certificate_digest'], 'certificate_claim')):
                            if connection.execute(f'SELECT 1 FROM certifications WHERE {column}=?', (value,)).fetchone():
                                raise CertificationConflict(code)
                        for key in keys:
                            if connection.execute('SELECT 1 FROM replay_claims WHERE claim=?', (key,)).fetchone():
                                raise CertificationConflict('signed_evidence_claim')
                    participation = self._quota(connection, history, cert)
                    if fault:
                        fault('before_claims')
                    if existing is None:
                        connection.execute('INSERT INTO certifications VALUES(?,?,?,?,?,?,?)',
                            (operation, current, cert['certificate_digest'], cert['content_hash'], cert['submission_id'],
                             issued.certificate_bytes, prepared.application_certificate_bytes))
                        connection.executemany('INSERT INTO replay_claims VALUES(?,?)', [(k, operation) for k in keys])
                        connection.executemany('INSERT INTO certification_participation VALUES(?,?,?,?,?)',
                                               [(*r, operation) for r in participation])
                    if fault:
                        fault('after_claims')
                    loaded = self._load(connection, record['hash'])
                    if loaded is None:
                        connection.execute('INSERT INTO blocks VALUES(?,?)', (record['hash'], candidate.canonical_record))
                        self._put_indexes(connection, record)
                        connection.execute('INSERT INTO candidate_certifications VALUES(?,?,?)', (record['hash'], operation, current))
                    elif (loaded[0] != candidate.canonical_record or connection.execute(
                            'SELECT operation FROM candidate_certifications WHERE block_hash=?',
                            (record['hash'],)).fetchone() != (operation,)):
                        raise CertificationConflict('candidate_owner')
                    if fault:
                        fault('after_block')
                    result = PersistedCandidate(operation, record['hash'], candidate.canonical_record, current, loaded is not None)
            if fault:
                fault('after_commit')  # An interrupted acknowledgement can be retried.
            return result
        except IntegrationError as exc:
            if exc.classification == Failure.INCOMPLETE:
                return IncompleteEvidence((exc.code,))
            raise
        except CertificationConflict:
            raise
        except (V3Error, ValueError, TypeError, KeyError) as exc:
            raise IntegrationError(Failure.INVALID_CANONICAL, getattr(exc, 'code', 'invalid_certification')) from exc
        except Exception as exc:
            raise IntegrationError(Failure.LOCAL_FAILURE, 'atomic_storage_or_worker_unavailable') from exc

    def _selection_claims(self, connection, chain):
        claims = []
        for _, block_hash in chain:
            payload = self._load(connection, block_hash)[1]['envelope']['payload']
            claims.append(('original', payload['media']['original_sha256'], block_hash))
            claims.extend((kind, payload[field], block_hash) for kind, field in
                (('submission', 'submission_id'), ('certificate', 'certificate_id')))
            claims.extend(('transaction', tx['tx_id'], block_hash) for tx in payload['native_transactions'])
        if len({(kind, identity) for kind, identity, _ in claims}) != len(claims):
            raise ChainSelectionError('duplicate evidence or transaction on selected ancestry')
        return sorted(claims)

    def select_chain(self, tip, *, expected_tip):
        """Offline caller chooses winner; atomically swap selection+branch claims.

        No balance/reward settlement or production consensus authorization is
        implied by this storage projection.
        """
        if tip is not None:
            h64(tip)
        with self._transaction(write=True) as connection:
            old = self._selected(connection)
            if (old[-1][1] if old else None) != expected_tip:
                raise ChainSelectionError('stale selected tip')
            chain = self._lineage(connection, tip)
            if not set(self._proofs(connection)) <= set(chain):
                raise ChainSelectionError('cannot replace finalized history')
            claims = self._selection_claims(connection, chain)
            connection.execute('DELETE FROM selected_claims')
            connection.execute('DELETE FROM canonical_chain')
            connection.executemany('INSERT INTO canonical_chain VALUES(?,?)', chain)
            connection.executemany('INSERT INTO selected_claims VALUES(?,?,?)', claims)
            connection.execute('UPDATE settings SET selected_tip=? WHERE id=1', (tip,))

    def _integrity(self, connection):
        try:
            return self._certification_integrity(connection)
        except IntegrationError as exc:
            if exc.classification == Failure.LOCAL_FAILURE:
                raise StorageUnavailable('recovery verification unavailable', exc.outcome) from exc
            raise StorageCorruption('retained authenticated history is unusable') from exc
        except (V3Error, ValueError, TypeError, KeyError) as exc:
            raise StorageCorruption('stored certification evidence failed verification') from exc

    def _certification_integrity(self, connection):
        result = super()._integrity(connection)
        for (identity,) in connection.execute('SELECT id FROM snapshots').fetchall():
            snapshot = self._snapshot(connection, identity)
            self._ledger(snapshot)
        owners = {}
        expected_participation = []
        for operation, snapshot_id, cert_id, original, submission, raw, app_raw in connection.execute(
                'SELECT * FROM certifications').fetchall():
            snapshot = self._snapshot(connection, snapshot_id)
            cert = parse(raw, limit=196608)
            evidence.validate_certificate(cert, self.ctx)
            if (cert_id, original, submission) != (cert['certificate_digest'], cert['content_hash'], cert['submission_id']):
                raise StorageCorruption('certificate index mismatch')
            app = parse(app_raw, limit=196608)
            if (app['submission_id'], app['content_hash'], app['creator_wallet']) != (submission, original, cert['creator_wallet']):
                raise StorageCorruption('application certification mismatch')
            selected = [r for r in parse(snapshot.reviews, limit=16777216)
                if (r['submission'], r['original']) == (submission, original)]
            if (len(selected) != 1 or Context(**selected[0]['context']) != self.ctx or
                    selected[0]['votes'].encode() != canonical(cert['votes']) or
                    selected[0]['attestation'].encode() != canonical(cert['attestation'])):
                raise StorageCorruption('retained accepted selection mismatch')
            wallets = {v['voter_wallet_address'] for v in cert['votes'] + app['votes']}
            with snapshot.history_view(wallets) as history:
                stored = history.submissions.get(submission)
                if (stored is None or stored['content_hash'] != original or
                        stored['submitter'] != cert['creator_wallet'] or
                        canonical(stored['admission_certificate']) != app_raw):
                    raise StorageCorruption('retained submission ownership mismatch')
                linked = connection.execute('SELECT block_hash FROM candidate_certifications WHERE operation=? LIMIT 1',
                                            (operation,)).fetchone()
                if linked is None:
                    raise StorageCorruption('certificate has no persisted candidate')
                payload = self._load(connection, linked[0])[1]['envelope']['payload']
                outcome = media.reconstruct(payload['media'], decoder=self.decoder)
                if outcome.status == Status.INDETERMINATE_LOCAL_FAILURE:
                    raise StorageUnavailable('recovery decoder unavailable', outcome)
                if outcome.status != Status.VALID:
                    raise StorageCorruption('recovery media integrity')
                validate_admission_certificate(app, media_bytes=outcome.original, reviewer_status_resolver=history.status)
                for vote in cert['votes']:
                    decision = history.decision(self.ctx, vote)
                    if not decision.eligible or decision.status != vote['reviewer_status']:
                        raise StorageCorruption('retained reviewer eligibility mismatch')
            owners[operation] = raw
            actual = connection.execute('SELECT claim FROM replay_claims WHERE operation=? ORDER BY claim', (operation,)).fetchall()
            if actual != [(k,) for k in replay_keys(self.ctx, cert)]:
                raise StorageCorruption('replay claims mismatch')
            participation = {}
            for vote in cert['votes']:
                height = vote['reviewer_status_effective_height']
                key = (vote['voter_wallet_address'], submission, review_epoch(height))
                participation[key] = min(participation.get(key, height), height)
            expected_participation.extend((*key, height, operation) for key, height in participation.items())
        if sorted(expected_participation) != sorted(connection.execute('SELECT * FROM certification_participation').fetchall()):
            raise StorageCorruption('participation reservation mismatch')
        links = connection.execute('SELECT * FROM candidate_certifications').fetchall()
        if len(links) != result['blocks']:
            raise StorageCorruption('unowned candidate')
        for block_hash, operation, snapshot_id in links:
            self._snapshot(connection, snapshot_id)
            payload = self._load(connection, block_hash)[1]['envelope']['payload']
            if canonical(payload['admission_certificate']) != owners[operation]:
                raise StorageCorruption('candidate certificate ownership mismatch')
        expected = self._selection_claims(connection, self._selected(connection))
        if sorted(connection.execute('SELECT * FROM selected_claims').fetchall()) != expected:
            raise StorageCorruption('selected replay claims mismatch')
        result.update(certifications=len(owners), replay_claims=connection.execute('SELECT count(*) FROM replay_claims').fetchone()[0])
        return result

    def backup(self, target):
        # Base backup reopens a block-only schema; use this unified type instead.
        target = Path(target).resolve()
        with target.open('xb'):
            pass
        with self._transaction() as connection:
            self._integrity(connection)
            with closing(sqlite3.connect(target)) as destination:
                connection.backup(destination)
                destination.execute(f'PRAGMA journal_mode={self.journal_mode}')
        with type(self)(target, self.config, decoder=self.decoder, journal_mode=self.journal_mode) as restored:
            restored.check_integrity()
        return target
