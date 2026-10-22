"""Task 7.16: disposable unified databases, real signatures and real process death.

The inherited Task 7.15 source is a trusted symbolic local history fixture,
not a consensus-authenticated chain import. No production state is opened.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, nullcontext
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from admission_certificate import build_admission_certificate
from canonical_v3 import evidence, media, transactions
from canonical_v3.admission import AdmissionAdapter, AdmissionDependencies, Failure, IntegrationError, TestOnlyConfig
from canonical_v3.atomic import AtomicV3Store, CertificationConflict, TrustedSnapshot, wal_is_fixed
from canonical_v3.construction import IncompleteConstruction
from canonical_v3.history import AuthenticatedHistoryAdapter, SQLiteHistoryReader, _History
from canonical_v3.issuance import IncompleteEvidence
from canonical_v3.primitives import canonical, digest, envelope, parse
from canonical_v3.storage import ChainSelectionError, StorageCorruption, StorageUnavailable
from codec_prototype.isolated_decoder import IsolatedDecoder, Outcome, Status
from media_technical_validation import validate_media_bytes
from storage import SQLiteStorageBackend
from test_milestone_7_task_7_13_admission import BASE, account, application_admission, header_for, sign
from test_milestone_7_task_7_15_history import (
    CTX, FixtureJournal, block_hash, contextual_certificate, penalty_for,
    read_section, resign, section, source,
)

ROOT = Path(__file__).resolve().parents[1]
OP = '1' * 64
TABLES = ('certifications', 'replay_claims', 'certification_participation', 'blocks',
          'block_index', 'transaction_index', 'candidate_certifications', 'canonical_chain', 'selected_claims', 'finality')


def ledger():
    native = BASE['native_transactions'][0]
    return dict(parent_index=45, parent_hash=block_hash(45), parent_timestamp='45', reward_pool_units=5000000,
        balances={native['from_address']: 2000000, native['to_address']: 0}, next_nonces={native['from_address']: 1})


def header(**changes):
    return {**header_for(), 'index': 46, 'previous_hash': block_hash(45), **changes}


def durable(store):
    return tuple(sorted(store.connection.execute(f'SELECT * FROM {table}').fetchall()) for table in TABLES)


def capture(local, adapter, apps, state=None):
    reader = SQLiteHistoryReader(adapter.config, local, FixtureJournal())
    return TrustedSnapshot.capture(reader, [(a['submission_id'], a['content_hash']) for a in apps], state or ledger())


def put_reviews(local, certs):
    with local._connect() as connection:
        connection.execute('DELETE FROM task715_frozen')
        for cert in certs:
            connection.execute('INSERT INTO task715_frozen VALUES(?,?,?,?,?)',
                (cert['submission_id'], cert['content_hash'], json.dumps(vars(CTX)),
                 canonical(cert['votes']), canonical(cert['attestation'])))


@pytest.fixture
def harness(source, tmp_path, monkeypatch):
    original, adapter, prepared, cert, valid, app, decoder = source
    worker = tmp_path / 'workers'
    worker.mkdir()
    monkeypatch.setattr(tempfile, 'tempdir', str(worker))
    local_path = tmp_path / 'history.sqlite3'
    with original._connect() as connection, closing(sqlite3.connect(local_path)) as target:
        connection.backup(target)
    local = SQLiteStorageBackend(sqlite_db_path=str(local_path))
    snapshot = capture(local, adapter, [app])
    with AtomicV3Store(tmp_path / 'unified.sqlite', adapter.config, decoder=decoder, initial=snapshot) as store:
        yield dict(store=store, local=local, adapter=adapter, prepared=prepared, cert=deepcopy(cert),
                   app=app, valid=valid, decoder=decoder, snapshot=snapshot, root=tmp_path)


def certify(h, **changes):
    arguments = dict(operation=OP, expected_snapshot=h['store'].current_snapshot(),
                     header=header(), native_transactions=[])
    arguments.update(changes)
    return h['store'].certify(h['adapter'], h['prepared'], **arguments)


def refresh(h, certs=None, apps=None, state=None):
    if certs is not None:
        put_reviews(h['local'], certs)
    old = h['store'].current_snapshot()
    snapshot = capture(h['local'], h['adapter'], apps or [h['app']], state)
    h['store'].install_snapshot(snapshot, expected_snapshot=old)
    return snapshot


def extra_admission(h, *, raw=b'independent original', sid='2' * 32, nonce_suffix=None):
    valid, old, _ = application_admission(raw, submission_id=sid)
    reader = SQLiteHistoryReader(h['adapter'].config, h['local'], FixtureJournal())
    with reader.read() as storage:
        history = _History(storage, CTX, {account(n).address.lower() for n in range(2, 9)})
    for vote in old['votes']:
        vote.update(reviewer_status_effective_height=45, reviewer_status_reference_block_hash=block_hash(45))
    app = build_admission_certificate(submission_id=sid, content_hash=old['content_hash'],
        creator_wallet=old['creator_wallet'], media_bytes=valid.raw_media_bytes,
        technical_evidence=old['technical_evidence'], attestation=old['attestation'], votes=old['votes'],
        reviewer_status_resolver=history.status)
    apps = read_section(h['local'], 'submissions')
    apps.append(dict(submission_id=sid, content_hash=app['content_hash'], submitter=app['creator_wallet'], admission_certificate=app))
    section(h['local'], 'submissions', apps)
    cert = contextual_certificate(app)
    suffix = nonce_suffix or sid
    att = cert['attestation']
    att['nonce'] += '-' + suffix
    att['canonical_payload']['nonce'] = att['nonce']
    message = canonical(envelope(att['canonical_payload'], 'submitter-attestation', CTX))
    att.update(signature=sign(message, 1), canonical_message=message.decode(),
        canonical_payload_digest=hashlib.sha256(message).hexdigest(), canonical_message_hash=hashlib.sha256(message).hexdigest())
    for vote in cert['votes']:
        vote['vote_nonce'] += '-' + suffix
        resign(vote)
    for dimension in evidence.POSITIVE:
        cert[dimension] = evidence.derive_tally(cert['votes'], dimension, CTX)
    cert.pop('certificate_digest')
    cert['certificate_digest'] = digest(cert)
    evidence.validate_certificate(cert, CTX)
    adapter = AdmissionAdapter(h['adapter'].config, AdmissionDependencies(history.status, lambda _: False), decoder=h['decoder'])
    return adapter, adapter.prepare(valid, app), cert, app


def native_transaction():
    tx = deepcopy(BASE['native_transactions'][0])
    tx.update(network_id=CTX.network_id, network=CTX.application)
    message = transactions.signing_bytes({k: tx[k] for k in transactions.PAYLOAD_FIELDS}, CTX)
    tx.update(signed_message=message.decode(), signature=sign(message, 1),
        tx_id=hashlib.sha256(message).hexdigest(), signed_message_hash=hashlib.sha256(message).hexdigest())
    transactions.validate_transaction(tx, CTX)
    return tx


def test_atomic_success_proposal_indexes_and_exact_recovery(harness):
    h = harness
    proposal = AuthenticatedHistoryAdapter(h['adapter'], SQLiteHistoryReader(
        h['adapter'].config, h['local'], FixtureJournal())).issue(h['prepared'])
    tx = native_transaction()
    result = certify(h, proposal=proposal, native_transactions=[tx])
    assert result.classification == 'persisted_provisional' and not result.idempotent
    store = h['store']
    assert store.connection.execute('PRAGMA journal_mode').fetchone() == ('delete',)
    assert store.connection.execute('PRAGMA synchronous').fetchone() == (3,)
    assert store.selected_tip() is None and not store.is_finalized(result.block_hash)
    assert store.by_transaction(tx['tx_id']) == [result.canonical_record]
    assert store.connection.execute('SELECT count(*) FROM certifications').fetchone() == (1,)
    assert store.connection.execute('SELECT count(*) FROM replay_claims').fetchone() == (62,)
    assert store.connection.execute('SELECT count(*) FROM certification_participation').fetchone() == (7,)
    expected = durable(store)
    for _ in range(2):
        with AtomicV3Store(store.path, h['adapter'].config, decoder=h['decoder']) as reopened:
            assert reopened.get(result.block_hash) == result.canonical_record
            assert reopened.check_integrity()['certifications'] == 1
            assert durable(reopened) == expected
            p = parse(result.canonical_record)['envelope']['payload']
            assert media.reconstruct(p['media'], decoder=h['decoder']).original == h['prepared'].original
            assert p['approval_percentage'] == p['originality_score'] == dict(numerator=5, denominator=7)


def test_idempotent_retry_and_competing_candidates_share_one_issuance(harness):
    first = certify(harness)
    before = durable(harness['store'])
    again = certify(harness)
    assert again.idempotent and again.canonical_record == first.canonical_record
    assert durable(harness['store']) == before
    sibling = certify(harness, header=header(timestamp='1792368001'))
    assert sibling.block_hash != first.block_hash and not sibling.idempotent
    state = harness['store'].check_integrity()
    assert state['blocks'] == 2 and state['certifications'] == 1 and state['replay_claims'] == 62
    with pytest.raises(CertificationConflict, match='original_claim'):
        certify(harness, operation='2' * 64)
    assert harness['store'].check_integrity() == state


@pytest.mark.parametrize('stage', ['before_claims', 'after_claims', 'after_block'])
@pytest.mark.parametrize('error', [RuntimeError, sqlite3.OperationalError, OSError])
def test_rollback_at_every_write_stage_and_retry(harness, stage, error):
    before = durable(harness['store'])
    def fault(point):
        if point == stage:
            raise error('simulated disk I/O error')
    with pytest.raises(IntegrationError) as exc:
        certify(harness, fault=fault)
    assert exc.value.classification == Failure.LOCAL_FAILURE
    assert durable(harness['store']) == before
    assert harness['store'].check_integrity()['blocks'] == 0
    assert certify(harness).classification == 'persisted_provisional'
    assert certify(harness).idempotent


def test_lost_acknowledgement_is_retryable(harness):
    def fault(stage):
        if stage == 'after_commit':
            raise OSError('acknowledgement lost')
    with pytest.raises(IntegrationError) as exc:
        certify(harness, fault=fault)
    assert exc.value.classification == Failure.LOCAL_FAILURE
    assert harness['store'].check_integrity()['certifications'] == 1
    assert certify(harness).idempotent


def test_busy_is_local_failure_and_leaves_no_claim(harness):
    h = harness
    with AtomicV3Store(h['store'].path, h['adapter'].config, decoder=h['decoder'], timeout=0) as other:
        with h['store']._transaction(write=True):
            with pytest.raises(IntegrationError) as exc:
                other.certify(h['adapter'], h['prepared'], operation=OP,
                    expected_snapshot=h['snapshot'].identity, header=header(), native_transactions=[])
            assert exc.value.classification == Failure.LOCAL_FAILURE
            assert other.connection.execute('SELECT count(*) FROM replay_claims').fetchone() == (0,)
        assert certify(h).classification == 'persisted_provisional'


def test_two_connections_have_one_certification_winner(harness):
    h = harness
    def attempt(op):
        with AtomicV3Store(h['store'].path, h['adapter'].config, decoder=h['decoder'], timeout=30) as store:
            try:
                return store.certify(h['adapter'], h['prepared'], operation=op,
                    expected_snapshot=h['snapshot'].identity, header=header(), native_transactions=[]).classification
            except CertificationConflict as exc:
                return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ['1' * 64, '2' * 64]))
    assert sorted(results) == ['original_claim', 'persisted_provisional']
    assert h['store'].check_integrity()['certifications'] == 1
    assert h['store'].connection.execute('SELECT count(*) FROM blocks').fetchone() == (1,)


@pytest.mark.parametrize('same_original', [False, True])
def test_independent_reviews_or_conflicting_submission(harness, same_original):
    h = harness
    adapter, prepared, cert, app = extra_admission(h, raw=h['prepared'].original if same_original else b'distinct accepted original')
    refresh(h, [h['cert'], cert], [h['app'], app])
    first = certify(h)
    before = durable(h['store'])
    call = lambda: h['store'].certify(adapter, prepared, operation='2' * 64,
        expected_snapshot=h['store'].current_snapshot(), header=header(), native_transactions=[])
    if same_original:
        with pytest.raises(CertificationConflict, match='original_claim'):
            call()
        assert durable(h['store']) == before
    else:
        second = call()
        assert second.block_hash != first.block_hash
        assert h['store'].check_integrity()['certifications'] == 2
        assert h['store'].connection.execute('SELECT count(*) FROM certification_participation').fetchone() == (14,)
        with pytest.raises(CertificationConflict, match='operation_identity'):
            h['store'].certify(adapter, prepared, operation=OP, expected_snapshot=h['store'].current_snapshot(),
                              header=header(), native_transactions=[])


def test_signed_nonce_reuse_across_distinct_media_is_durable_conflict(harness):
    h = harness
    adapter, prepared, cert, app = extra_admission(h)
    # The two valid signed records share only the creator nonce here.
    att = cert['attestation']
    att['nonce'] = att['canonical_payload']['nonce'] = h['cert']['attestation']['nonce']
    message = canonical(envelope(att['canonical_payload'], 'submitter-attestation', CTX))
    att.update(signature=sign(message, 1), canonical_message=message.decode(),
        canonical_payload_digest=hashlib.sha256(message).hexdigest(), canonical_message_hash=hashlib.sha256(message).hexdigest())
    cert.pop('certificate_digest'); cert['certificate_digest'] = digest(cert)
    refresh(h, [h['cert'], cert], [h['app'], app])
    certify(h)
    before = durable(h['store'])
    with pytest.raises(CertificationConflict, match='signed_evidence_claim'):
        h['store'].certify(adapter, prepared, operation='2' * 64, expected_snapshot=h['store'].current_snapshot(),
                          header=header(), native_transactions=[])
    assert durable(h['store']) == before


def test_concurrent_independent_certifications_serialize_epoch_quota(harness):
    h = harness
    admissions = [(h['adapter'], h['prepared'], h['cert'], h['app'])]
    admissions.extend(extra_admission(h, raw=f'quota original {n}'.encode(), sid=f'{n:032x}')
                      for n in range(10, 15))
    refresh(h, [a[2] for a in admissions], [a[3] for a in admissions])
    expected = h['store'].current_snapshot()
    def attempt(item):
        index, (adapter, prepared, _, _) = item
        with AtomicV3Store(h['store'].path, h['adapter'].config, decoder=h['decoder'], timeout=30) as store:
            try:
                return store.certify(adapter, prepared, operation=f'{index + 1:064x}',
                    expected_snapshot=expected, header=header(), native_transactions=[]).classification
            except CertificationConflict as exc:
                return exc.code
    for item in enumerate(admissions[:4]):
        assert attempt(item) == 'persisted_provisional'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, list(enumerate(admissions))[4:]))
    assert sorted(results) == ['persisted_provisional', 'reviewer_epoch_quota']
    assert h['store'].check_integrity()['certifications'] == 5
    assert h['store'].connection.execute('SELECT count(*) FROM certification_participation').fetchone() == (35,)


def test_old_read_only_proposal_cannot_authorize_new_snapshot(harness):
    h = harness
    proposal = AuthenticatedHistoryAdapter(h['adapter'], SQLiteHistoryReader(
        h['adapter'].config, h['local'], FixtureJournal())).issue(h['prepared'])
    apps = read_section(h['local'], 'submissions')
    apps[0]['local_history_revision'] = 'changed'
    section(h['local'], 'submissions', apps)
    refresh(h)
    result = certify(h, proposal=proposal)
    assert type(result) is IncompleteEvidence and result.missing == ('stale_history_proposal',)
    assert h['store'].check_integrity()['certifications'] == 0


@pytest.mark.parametrize('change', ['revision', 'penalty', 'established'])
def test_snapshot_cas_stale_history_and_changed_eligibility(harness, change):
    h = harness
    old = h['store'].current_snapshot()
    if change == 'penalty':
        penalty_for(h['local'], 45)
    elif change == 'established':
        # Remove historical accepted promotion participation; mutable labels
        # cannot preserve established status.
        with h['local']._connect() as connection:
            connection.execute("UPDATE durable_vote_records SET lifecycle_state='rejected'")
    else:
        apps = read_section(h['local'], 'submissions')
        apps[0]['local_revision'] = 'updated'
        section(h['local'], 'submissions', apps)
    new = refresh(h)
    before = durable(h['store'])
    stale = certify(h, expected_snapshot=old)
    assert type(stale) is IncompleteEvidence and stale.missing == ('stale_authoritative_snapshot',)
    assert durable(h['store']) == before
    if change == 'revision':
        assert certify(h).classification == 'persisted_provisional'
    else:
        with pytest.raises(IntegrationError) as exc:
            certify(h)
        assert exc.value.classification == Failure.INVALID_CANONICAL
        assert durable(h['store']) == before
    with pytest.raises(CertificationConflict, match='snapshot_compare_and_swap'):
        h['store'].install_snapshot(new, expected_snapshot=old)
    with h['snapshot'].history_view({account(2).address.lower()}) as history:
        assert history.status(account(2).address.lower(), 45, block_hash(45)) == 'ESTABLISHED_REVIEWER'


@pytest.mark.parametrize('case', ['network', 'genesis', 'media-policy', 'review-policy', 'signature',
                                  'replayed-dimension', 'missing', 'unresolved'])
def test_context_crypto_and_missing_evidence_never_write(harness, case):
    h = harness
    cert = deepcopy(h['cert'])
    if case in ('network', 'genesis', 'media-policy', 'review-policy'):
        field = dict(network='network_id', genesis='genesis_hash', **{'media-policy': 'media_policy_digest',
                     'review-policy': 'review_policy_digest'})[case]
        wrong = replace(CTX, **{field: 'other-network' if case == 'network' else 'e' * 64})
        foreign = replace(h['snapshot'], context=wrong)
        with pytest.raises(ValueError):
            h['store'].install_snapshot(foreign, expected_snapshot=h['store'].current_snapshot())
        assert h['store'].check_integrity()['certifications'] == 0
        return
    if case == 'signature':
        cert['votes'][0]['vote_signature'] = '0x' + '01' + cert['votes'][0]['vote_signature'][4:]
    elif case == 'replayed-dimension':
        cert['votes'][0]['dimension'] = 'originality'
    elif case == 'unresolved':
        cert['votes'] = cert['votes'][:1]
    refresh(h, [] if case == 'missing' else [cert])
    before = durable(h['store'])
    if case in ('missing', 'unresolved'):
        assert type(certify(h)) is IncompleteEvidence
    else:
        with pytest.raises(IntegrationError) as exc:
            certify(h)
        assert exc.value.classification == Failure.INVALID_CANONICAL
    assert durable(h['store']) == before


@pytest.mark.parametrize('missing', ['native', 'reward', 'parent'])
def test_incomplete_or_invalid_construction_is_atomic(harness, missing):
    h = harness
    before = durable(h['store'])
    if missing == 'native':
        from canonical_v3.construction import MISSING
        assert type(certify(h, native_transactions=MISSING)) is IncompleteConstruction
    elif missing == 'parent':
        assert type(certify(h, header=header(index=47))) is IncompleteConstruction
    else:
        state = ledger(); state['reward_pool_units'] = 4999999
        refresh(h, state=state)
        with pytest.raises(IntegrationError) as exc:
            certify(h)
        assert exc.value.classification == Failure.INVALID_CANONICAL
    assert durable(h['store']) == before


def finality_for(result):
    addresses = sorted(account(n).address.lower() for n in (1, 2, 3))
    attestations = []
    from canonical_v3.finality import finality_bytes
    for address in addresses[:2]:
        number = next(n for n in (1, 2, 3) if account(n).address.lower() == address)
        payload = dict(attestation_version=2, validator_address=address, block_height=46, block_hash=result.block_hash)
        message = finality_bytes(payload, CTX)
        attestations.append(dict(payload, network_id=CTX.network_id, domain='zoidbergchain/finality-attestation/v2',
            signature_scheme='personal_sign', signature=sign(message, number), message=message.decode()))
    return canonical(dict(block_height=46, block_hash=result.block_hash, network_id=CTX.network_id,
        domain='zoidbergchain/finality-attestation/v2', attestation_version=2, validator_set=addresses,
        required_quorum=2, attestations=attestations)), tuple(addresses)


def test_provisional_reorg_and_finalized_history_protection(harness):
    h = harness
    first = certify(h)
    second = certify(h, header=header(timestamp='1792368001'))
    store = h['store']
    store.select_chain(first.block_hash, expected_tip=None)
    permanent = store.connection.execute('SELECT * FROM replay_claims ORDER BY claim').fetchall()
    store.select_chain(second.block_hash, expected_tip=first.block_hash)
    assert store.connection.execute('SELECT DISTINCT block_hash FROM selected_claims').fetchall() == [(second.block_hash,)]
    store.select_chain(None, expected_tip=second.block_hash)
    assert store.connection.execute('SELECT * FROM selected_claims').fetchall() == []
    assert store.connection.execute('SELECT * FROM replay_claims ORDER BY claim').fetchall() == permanent
    store.select_chain(first.block_hash, expected_tip=None)
    proof, validators = finality_for(first)
    assert store.finalize(proof, trusted_validators=validators, equivocators=frozenset())
    assert not store.finalize(proof, trusted_validators=validators, equivocators=frozenset())
    before = durable(store)
    for tip in (None, second.block_hash):
        with pytest.raises(ChainSelectionError, match='finalized'):
            store.select_chain(tip, expected_tip=first.block_hash)
        assert durable(store) == before
    assert store.is_finalized(first.block_hash) and not store.is_finalized(second.block_hash)
    assert store.check_integrity()['finality_proofs'] == 1
    # A trusted source replacement cannot detach the historical anchor either.
    chain = read_section(h['local'], 'chain'); chain[45]['timestamp'] = 46.0
    section(h['local'], 'chain', chain)
    snapshot = capture(h['local'], h['adapter'], [h['app']])
    with pytest.raises(ChainSelectionError, match='finalized'):
        store.install_snapshot(snapshot, expected_snapshot=store.current_snapshot())
    assert durable(store) == before


def test_selection_failure_rolls_back_claims_and_tip(harness):
    first = certify(harness)
    second = certify(harness, header=header(timestamp='1792368001'))
    store = harness['store']
    store.select_chain(first.block_hash, expected_tip=None)
    before = durable(store)
    store.connection.execute("CREATE TEMP TRIGGER fail_selection BEFORE UPDATE ON settings BEGIN SELECT RAISE(ABORT,'disk I/O error'); END")
    with pytest.raises((StorageCorruption, StorageUnavailable)):
        store.select_chain(second.block_hash, expected_tip=first.block_hash)
    store.connection.execute('DROP TRIGGER fail_selection')
    assert durable(store) == before


def test_source_snapshot_cannot_conflict_with_retained_v3_finality(harness):
    h = harness
    result = certify(h)
    store = h['store']
    store.select_chain(result.block_hash, expected_tip=None)
    proof, validators = finality_for(result)
    store.finalize(proof, trusted_validators=validators, equivocators=frozenset())
    before = durable(store)
    old = store.current_snapshot()
    chain = read_section(h['local'], 'chain')
    chain.append(dict(index=46, hash='e' * 64, previous_hash=block_hash(45),
                      network_id=CTX.network_id, timestamp=46.0, native_transactions=[]))
    section(h['local'], 'chain', chain)
    state = ledger()
    state.update(parent_index=46, parent_hash='e' * 64, parent_timestamp='46')
    snapshot = capture(h['local'], h['adapter'], [h['app']], state)
    with pytest.raises(ChainSelectionError, match='retained v3 finality'):
        store.install_snapshot(snapshot, expected_snapshot=old)
    assert store.current_snapshot() == old and durable(store) == before


def test_identity_and_zstd_share_claim_owner_but_allow_candidate_variants(harness, monkeypatch):
    h = harness
    assert h['prepared'].descriptor['codec_id'] == 'zstd'
    first = certify(h)
    with h['snapshot'].history_view({account(n).address.lower() for n in range(2, 9)}) as history:
        adapter = AdmissionAdapter(h['adapter'].config, AdmissionDependencies(history.status, lambda _: False), decoder=h['decoder'])
        monkeypatch.setattr(media, '_compress_default', lambda _: None)
        prepared = adapter.prepare(h['valid'], h['app'])
    assert prepared.descriptor['codec_id'] == 'identity'
    second = h['store'].certify(adapter, prepared, operation=OP, expected_snapshot=h['store'].current_snapshot(),
                               header=header(), native_transactions=[])
    assert second.block_hash != first.block_hash
    assert h['store'].check_integrity()['certifications'] == 1
    assert h['store'].by_original_hash(h['cert']['content_hash']) == sorted(
        [first.canonical_record, second.canonical_record], key=lambda b: parse(b)['hash'])


def test_worker_unavailable_and_actual_disk_full_are_local(harness, monkeypatch):
    h = harness
    before = durable(h['store'])
    original = h['decoder'].validate
    monkeypatch.setattr(h['decoder'], 'validate', lambda *a, **k: Outcome(
        Status.INDETERMINATE_LOCAL_FAILURE, stage='worker', code='unavailable'))
    with pytest.raises(IntegrationError) as exc:
        certify(h)
    assert exc.value.classification == Failure.LOCAL_FAILURE
    assert durable(h['store']) == before
    monkeypatch.setattr(h['decoder'], 'validate', original)
    # Real SQLITE_FULL, rather than merely throwing an I/O-shaped exception.
    pages = h['store'].connection.execute('PRAGMA page_count').fetchone()[0]
    h['store'].connection.execute(f'PRAGMA max_page_count={pages}')
    with pytest.raises(IntegrationError) as exc:
        certify(h)
    assert exc.value.classification == Failure.LOCAL_FAILURE
    assert durable(h['store']) == before
    h['store'].connection.execute('PRAGMA max_page_count=1073741823')
    assert certify(h).classification == 'persisted_provisional'


def test_immutable_constraints_foreign_keys_backup_and_nonactivation(harness):
    result = certify(harness)
    store = harness['store']
    for table in ('snapshots', 'certifications', 'replay_claims', 'certification_participation', 'candidate_certifications'):
        with pytest.raises(sqlite3.IntegrityError, match='immutable'):
            store.connection.execute(f'DELETE FROM {table}')
    with pytest.raises(sqlite3.IntegrityError):
        store.connection.execute('INSERT INTO replay_claims VALUES(?,?)', ('f' * 64, 'f' * 64))
    backup = store.backup(harness['root'] / 'backup.sqlite')
    with AtomicV3Store(backup, harness['adapter'].config, decoder=harness['decoder']) as recovered:
        assert recovered.get(result.block_hash) == result.canonical_record
        assert recovered.check_integrity() == store.check_integrity()
    with pytest.raises(StorageUnavailable):
        store.insert(result.canonical_record)
    with pytest.raises(StorageCorruption):
        AtomicV3Store(harness['local'].sqlite_db_path, harness['adapter'].config, decoder=harness['decoder'])
    for path in [ROOT / 'storage.py', ROOT / 'blockchain.py', ROOT / 'api_runtime.py', *list((ROOT / 'services').glob('*.py'))]:
        assert 'canonical_v3' not in path.read_text(encoding='utf-8')


def worker_input(h):
    path = h['root'] / 'worker-input.json'
    path.write_text(json.dumps(dict(database=str(h['store'].path), context=vars(CTX),
        original=h['prepared'].original.hex(), application=h['app'],
        snapshot=h['store'].current_snapshot(), header=header(), journal_mode=h['store'].journal_mode,
        worker_temp=str(h['root'] / 'workers'))), encoding='utf-8')
    return path


def child_command(h, operation, mode):
    return [sys.executable, '-B', str(Path(__file__).resolve()), str(worker_input(h)), operation, mode]


def child_main(path, operation, mode):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    tempfile.tempdir = data['worker_temp']
    from canonical_v3.primitives import Context
    config = TestOnlyConfig(Context(**data['context']), True)
    with IsolatedDecoder() as decoder, AtomicV3Store(data['database'], config, decoder=decoder, timeout=30,
                                                  journal_mode=data['journal_mode']) as store:
        snapshot = store._snapshot(store.connection, data['snapshot'])
        with snapshot.history_view({account(n).address.lower() for n in range(2, 9)}) as history:
            adapter = AdmissionAdapter(config, AdmissionDependencies(history.status, lambda _: False), decoder=decoder)
            prepared = adapter.prepare(validate_media_bytes(bytes.fromhex(data['original']), declared_mime_type='text/plain'), data['application'])
        def fault(stage):
            if stage == mode:
                # Spill uncommitted dirty pages, then await external kill.
                store.connection.execute('PRAGMA cache_size=1')
                print('kill-ready', flush=True)
                sys.stdin.readline()
        print('ready', flush=True)
        sys.stdin.readline()  # Parent starts both certification attempts together.
        try:
            result = store.certify(adapter, prepared, operation=operation, expected_snapshot=data['snapshot'],
                header=data['header'], native_transactions=[], fault=fault)
            print(json.dumps(dict(status=result.classification, block_hash=result.block_hash)), flush=True)
        except CertificationConflict as exc:
            print(json.dumps(dict(status=exc.code)), flush=True)


def read_line(process):
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(process.stdout.readline)
        try:
            line = future.result(timeout=30)
        except BaseException:
            process.kill()
            raise
    assert line, process.stderr.read()
    return line.strip()


def test_two_processes_one_owner_and_idempotent_retry(harness):
    h = harness
    processes = [subprocess.Popen(child_command(h, op, 'none'), cwd=ROOT, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for op in ('1' * 64, '2' * 64)]
    try:
        for p in processes:
            assert read_line(p) == 'ready'
        for p in processes:
            p.stdin.write('\n'); p.stdin.flush()
        results = [json.loads(read_line(p)) for p in processes]
        for p in processes:
            p.wait(timeout=30)
            assert p.returncode == 0, p.stderr.read()
        assert sorted(r['status'] for r in results) == ['original_claim', 'persisted_provisional']
        assert h['store'].check_integrity()['certifications'] == 1
        winner = next(op for op, r in zip(('1' * 64, '2' * 64), results) if r['status'] == 'persisted_provisional')
        assert certify(h, operation=winner).idempotent
    finally:
        for p in processes:
            if p.poll() is None:
                p.kill(); p.wait(timeout=10)
            for stream in (p.stdin, p.stdout, p.stderr):
                stream.close()


def test_affected_wal_runtime_is_refused_before_touching_any_file(harness, monkeypatch):
    h = harness
    assert wal_is_fixed((3, 51, 3)) and wal_is_fixed((3, 50, 7)) and wal_is_fixed((3, 44, 6))
    assert not wal_is_fixed((3, 49, 1)) and not wal_is_fixed((3, 51, 2))
    monkeypatch.setattr(sqlite3, 'sqlite_version_info', (3, 49, 1))
    absent = h['root'] / 'unsafe-wal.sqlite'
    before = h['store'].path.read_bytes()
    for path, initial in ((absent, h['snapshot']), (h['store'].path, None)):
        with pytest.raises(StorageUnavailable, match='WAL-reset fix'):
            AtomicV3Store(path, h['adapter'].config, decoder=h['decoder'], initial=initial, journal_mode='WAL')
    assert not absent.exists() and h['store'].path.read_bytes() == before


@pytest.mark.parametrize('journal_mode', ['DELETE', 'WAL'])
@pytest.mark.parametrize('stage', ['before_claims', 'after_claims', 'after_block', 'after_commit'])
def test_external_process_termination_journal_recovery_and_retry(harness, stage, journal_mode):
    if journal_mode == 'WAL' and not wal_is_fixed(sqlite3.sqlite_version_info):
        pytest.skip('WAL crash verification requires a SQLite runtime with the WAL-reset fix')
    context = (AtomicV3Store(harness['root'] / 'wal.sqlite', harness['adapter'].config, decoder=harness['decoder'],
                            initial=harness['snapshot'], journal_mode='WAL') if journal_mode == 'WAL'
               else nullcontext(harness['store']))
    with context as store:
        _process_termination_probe({**harness, 'store': store}, stage)


def _process_termination_probe(h, stage):
    before = durable(h['store'])
    process = subprocess.Popen(child_command(h, OP, stage), cwd=ROOT, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert read_line(process) == 'ready'
        process.stdin.write('\n'); process.stdin.flush()
        assert read_line(process) == 'kill-ready'
        process.terminate()
        process.wait(timeout=15)
    finally:
        if process.poll() is None:
            process.kill(); process.wait(timeout=10)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()
    for _ in range(2):
        with AtomicV3Store(h['store'].path, h['adapter'].config, decoder=h['decoder']) as recovered:
            count = recovered.check_integrity()['certifications']
            assert count == (1 if stage == 'after_commit' else 0)
            if stage != 'after_commit':
                assert durable(recovered) == before
    result = certify(h)
    assert result.idempotent == (stage == 'after_commit')
    assert h['store'].check_integrity()['certifications'] == 1


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))
    child_main(*sys.argv[1:])
