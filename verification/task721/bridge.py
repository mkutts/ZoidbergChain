"""Explicit offline Task 7.21 service boundary. Never imported by production.

Provisional format/media verification does not establish chain selection,
reviewer-history completeness, BFT finality, or network activation authority.
No environment variable, peer field, signer, HTTP route, or storage factory.
"""
from dataclasses import asdict, dataclass
from pathlib import Path
import sqlite3

from canonical_v3 import block, evidence, media
from canonical_v3.admission import AdmissionAdapter, Failure, IntegrationError, TestOnlyConfig
from canonical_v3.construction import BlockConstructionBridge, ConstructionState
from canonical_v3.primitives import V3Error, canonical, decimal_units, h64, require
from canonical_v3.storage import (
    APPLICATION_ID, SCHEMA_VERSION, SCHEMA, StorageCorruption, StorageUnavailable, V3Store,
)
from codec_prototype.isolated_decoder import IsolatedDecoder, Status
from media_technical_validation import (
    MediaValidationUnavailable, TechnicalMediaValidationError,
    technical_evidence_identity, validate_media_bytes,
)

REMAINING = ('complete_reviewer_history_authority', 'canonical_selection_authorization', 'finality_proof')


def _config(config, decoder):
    require(type(config) is TestOnlyConfig and config.test_only is True, 'test_only_configuration_required')
    require(isinstance(decoder, IsolatedDecoder), 'isolated_decoder_required')


@dataclass(frozen=True)
class RetrievedMedia:
    body: bytes
    mime_type: str
    original_size: int
    original_sha256: str
    block_hash: str
    # Integrity is verified; this is never a finalized/public response.
    integrity_verified: bool = True
    integration_status: str = 'INCOMPLETE'
    consensus_authorized: bool = False
    remaining: tuple[str, ...] = REMAINING


def canonical_media(raw, config, *, decoder):
    """Independent received-byte path. No producer, selection, or recompression.

    Image/container admission is checked separately by validate_candidate.
    Missing BFT/history authority never becomes an unconditional PASS.
    """
    _config(config, decoder)
    try:
        record = block.parse_record(raw, config.context)
        desc = record['envelope']['payload']['media']
        outcome = media.reconstruct(desc, decoder=decoder)
    except V3Error as exc:
        raise IntegrationError(Failure.INVALID_CANONICAL, exc.code) from exc
    except Exception as exc:
        raise IntegrationError(Failure.LOCAL_FAILURE, 'decoder_operation_unavailable') from exc
    if outcome.status != Status.VALID:
        category = Failure.LOCAL_FAILURE if outcome.status == Status.INDETERMINATE_LOCAL_FAILURE else Failure.INVALID_CANONICAL
        raise IntegrationError(category, outcome.reason or outcome.code, outcome=outcome)
    return RetrievedMedia(outcome.original, desc['mime_type'], desc['original_size'],
                          desc['original_sha256'], record['hash'])


def _technical(original, mime):
    try:
        fresh = validate_media_bytes(original, declared_mime_type=mime)
    except MediaValidationUnavailable as exc:
        raise IntegrationError(Failure.LOCAL_FAILURE, 'technical_worker_unavailable') from exc
    except TechnicalMediaValidationError as exc:
        if exc.result.get('local_resource_defense_failure'):
            category = Failure.LOCAL_FAILURE
        else:
            category = Failure.INVALID_ADMISSION
        raise IntegrationError(category, 'current_application_policy_rejected', outcome=exc.result) from exc
    require(fresh.raw_media_bytes == original, 'accepted_bytes_not_canonical')
    return fresh


def construct_candidate(original, mime, *, adapter, application_certificate,
                        canonical_certificate, header, state, native_transactions):
    """Exact accepted originals → existing admission/producer/constructor.

    All certificates and trusted state must be supplied explicitly by the test
    harness. This module contains no keys and creates no admission authority.
    """
    require(type(adapter) is AdmissionAdapter, 'admission_adapter_required')
    try:
        fresh = _technical(original, mime)
    except V3Error as exc:
        raise IntegrationError(Failure.INVALID_ADMISSION, exc.code) from exc
    prepared = adapter.prepare(fresh, application_certificate)
    return BlockConstructionBridge(adapter).construct(prepared, header=header,
        certificate=canonical_certificate, state=state, native_transactions=native_transactions)


def validate_candidate(raw, config, *, decoder, state=None):
    """Canonical/codec/crypto + real MIME checks + explicit trusted snapshot.

    The result always retains REMAINING. Even a supplied snapshot is a test
    assumption, not proof of complete reviewer history or consensus authority.
    Local technical worker termination remains a local failure.
    """
    result = canonical_media(raw, config, decoder=decoder)
    try:
        p = block.parse_record(raw, config.context)['envelope']['payload']
        fresh = _technical(result.body, result.mime_type)
        observations = set(evidence.TECHNICAL_FIELDS) - {
            'policy_id', 'policy_version', 'policy_digest', 'evidence_digest'}
        actual = technical_evidence_identity(fresh.result)
        evidence.fields_equal(p['admission_certificate']['technical_evidence'],
                              {k: actual[k] for k in observations})
        if state is None:
            raise IntegrationError(Failure.INCOMPLETE, 'trusted_construction_snapshot_required')
        require(type(state) is ConstructionState, 'construction_state')
        require(p['index'] == state.parent_index + 1 and p['previous_hash'] == state.parent_hash,
                'parent_binding')
        require(decimal_units(p['timestamp']) > decimal_units(state.parent_timestamp), 'parent_time')
        require(state.reward_pool_units >= 5000000, 'reward_pool_insufficient')
        for vote in p['admission_certificate']['votes']:
            try:
                status = state.reviewer_status_resolver(vote['voter_wallet_address'],
                    vote['reviewer_status_effective_height'], vote['reviewer_status_reference_block_hash'])
            except Exception as exc:
                raise IntegrationError(Failure.LOCAL_FAILURE, 'reviewer_lookup_unavailable') from exc
            if status is None:
                raise IntegrationError(Failure.INCOMPLETE, 'historical_reviewer_state')
            require(status == vote['reviewer_status'], 'reviewer_snapshot_mismatch')
        balances, nonces = dict(state.balances), dict(state.next_nonces)
        for tx in p['native_transactions']:
            sender, recipient = tx['from_address'], tx['to_address']
            if sender not in balances or recipient not in balances or sender not in nonces:
                raise IntegrationError(Failure.INCOMPLETE, 'native_ledger_state')
            amount = decimal_units(tx['amount'], positive=True)
            require(int(tx['nonce']) == nonces[sender] and balances[sender] >= amount, 'native_ledger')
            balances[sender] -= amount
            balances[recipient] += amount
            nonces[sender] += 1
    except V3Error as exc:
        raise IntegrationError(Failure.INVALID_CANONICAL, exc.code) from exc
    return result


class DisposableStore(V3Store):
    """Narrow DELETE/EXTRA initializer, actual inherited V3Store operations.

    Bypasses only the legacy isolated initializer's unconditional WAL pragma.
    Reopening requires the exact schema/context and DELETE journal; no conversion.
    Caller must supply a disposable path. No default or active DB discovery.
    """
    def __init__(self, path, config, *, decoder, create=False):
        _config(config, decoder)
        self.path, self.ctx, self.decoder = Path(path).resolve(), config.context, decoder
        self.anchor_height, self.anchor_hash = 0, h64(config.context.genesis_hash)
        self.context_bytes = canonical(asdict(config.context))
        self.connection = None
        if create:
            with self.path.open('xb'):
                pass
        try:
            self.connection = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True,
                                             isolation_level=None, timeout=1)
            self.connection.execute('PRAGMA foreign_keys=ON')
            if not create:
                self._validate_schema()  # Refuse an arbitrary/active DB before write pragmas.
            if self.connection.execute('PRAGMA journal_mode').fetchone()[0] != 'delete':
                raise StorageCorruption('DELETE journal required; no conversion')
            self.connection.execute('PRAGMA synchronous=EXTRA')
            if create:
                with self._transaction(write=True) as connection:
                    for statement in SCHEMA:
                        connection.execute(statement)
                    connection.execute(f'PRAGMA application_id={APPLICATION_ID}')
                    connection.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
                    connection.execute('INSERT INTO settings VALUES(1,?,?,?,NULL)',
                        (self.context_bytes, 0, self.anchor_hash))
            self._validate_schema()
        except sqlite3.Error as exc:
            self.close()
            raise StorageUnavailable('disposable SQLite open unavailable') from exc
        except BaseException:
            self.close()
            raise

    # Keep the public surface narrower than the legacy laboratory store.
    # In particular its backup verifier opens V3Store (and would enable WAL).
    def backup(self, target):
        raise StorageUnavailable('backup is outside the Task 7.21 boundary')

    @classmethod
    def restore(cls, *args, **kwargs):
        raise StorageUnavailable('restore is outside the Task 7.21 boundary')

    def checkpoint(self):
        raise StorageUnavailable('WAL maintenance is outside the Task 7.21 boundary')

    def select_chain(self, *args, **kwargs):
        raise IntegrationError(Failure.INCOMPLETE, 'canonical_selection_authorization')

    def finalize(self, *args, **kwargs):
        raise IntegrationError(Failure.INCOMPLETE, 'finality_authority')


def retrieve(store, block_hash, config, *, decoder):
    """Closest underlying media-service boundary; no API or off-chain fallback."""
    require(type(store) is DisposableStore and store.ctx == config.context, 'disposable_store_required')
    raw = store.get(block_hash)  # Revalidates canonical bytes, hashes, media and indexes.
    if raw is None:
        raise IntegrationError(Failure.INCOMPLETE, 'block_unavailable')
    return canonical_media(raw, config, decoder=decoder)
