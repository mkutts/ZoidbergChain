"""Offline raw SQLite history, real fixture signatures and retained services.

Chain/finality are a trusted symbolic fixture, as in reviewer service tests;
these tests do not purport to establish consensus/finality from an uploaded DB.
Only this test journal creates staging/claim tables, in disposable databases.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile

import pytest

from admission_certificate import build_admission_certificate
import dual_review
from canonical_v3 import evidence, media
from canonical_v3.admission import AdmissionAdapter, AdmissionDependencies, Failure, IntegrationError, TestOnlyConfig
from canonical_v3.history import (
    AuthenticatedHistoryAdapter, CertificationProposal, FrozenReview, SQLiteHistoryReader, _History, replay_keys,
)
from canonical_v3.issuance import IncompleteEvidence
from canonical_v3.primitives import canonical, digest, parse, envelope, CURVE_ORDER
from codec_prototype.isolated_decoder import IsolatedDecoder
from protocol_v1 import PUBLIC_TESTNET_V1_NETWORK_ID
from reviewer_reputation import ReviewerReputationService, SIGNED_VOTE_EQUIVOCATION, build_offense_evidence
from storage import SQLiteStorageBackend
from test_milestone_7_task_7_13_admission import CTX as VECTOR_CTX, account, application_admission, sign, v2_certificate

# Explicit same-root historical integration fixture. The genesis is symbolic,
# NOT the actual public-testnet root; this is no cross-launch history mapping.
CTX = replace(VECTOR_CTX, network_id=PUBLIC_TESTNET_V1_NETWORK_ID)


def resign(vote):
    number = next(n for n in range(2, 9) if account(n).address.lower() == vote['voter_wallet_address'])
    payload = evidence.vote_payload(vote, CTX)
    message = canonical(payload)
    signature = sign(message, number)
    vote.update(vote_message=message.decode(), vote_signature=signature,
        signed_message_hash=digest(payload), vote_identity=digest(dict(payload=payload, signature=signature)))


def contextual_certificate(app):
    cert = v2_certificate(app)
    cert.update(network_id=CTX.network_id, **evidence.policy_fields(CTX))
    tech = cert['technical_evidence']
    tech.update(evidence.policy_fields(CTX))
    tech.pop('evidence_digest')
    tech['evidence_digest'] = digest(tech)
    attestation = cert['attestation']
    payload = attestation['canonical_payload']
    payload.update(network_id=CTX.network_id, policy_id=CTX.media_policy_id,
                   technical_evidence_digest=tech['evidence_digest'])
    message = canonical(envelope(payload, 'submitter-attestation', CTX))
    attestation.update(network_id=CTX.network_id, signature=sign(message, 1),
        canonical_message=message.decode(), canonical_payload_digest=hashlib.sha256(message).hexdigest(),
        canonical_message_hash=hashlib.sha256(message).hexdigest())
    for vote in cert['votes']:
        vote.update(network_id=CTX.network_id, reviewer_status_effective_height=45,
                    reviewer_status_reference_block_hash=block_hash(45))
        resign(vote)
    for dimension in evidence.POSITIVE:
        cert[dimension] = evidence.derive_tally(cert['votes'], dimension, CTX)
    cert.pop('certificate_digest')
    cert['certificate_digest'] = digest(cert)
    return cert


def block_hash(height):
    return CTX.genesis_hash if height == 0 else digest(dict(history_height=height))


def section(storage, name, value):
    with storage._connect() as connection:
        connection.execute('UPDATE storage_sections SET json_data=? WHERE section_name=?', (json.dumps(value), name))


def read_section(storage, name):
    with storage._connect() as connection:
        return json.loads(connection.execute('SELECT json_data FROM storage_sections WHERE section_name=?', (name,)).fetchone()[0])


class FixtureJournal:
    """Stand-in for FUTURE locally accepted v2 history, not a new authority."""
    def load(self, connection, context, submission_id, original_hash):
        row = connection.execute('SELECT context,votes,attestation FROM task715_frozen WHERE submission=? AND original=?',
                                 (submission_id, original_hash)).fetchone()
        if row is None:
            return None
        return FrozenReview(type(context)(**json.loads(row[0])), row[1], row[2])

    def claimed(self, connection, keys):
        return tuple(r[0] for r in connection.execute('SELECT claim FROM task715_claims') if r[0] in keys)


def freeze(storage, cert, *, context=CTX):
    with storage._connect() as connection:
        connection.execute('DELETE FROM task715_frozen')
        connection.execute('INSERT INTO task715_frozen VALUES (?,?,?,?,?)', (cert['submission_id'], cert['content_hash'],
            json.dumps(asdict(context)), canonical(cert['votes']), canonical(cert['attestation'])))


def seed(storage):
    chain = [dict(index=h, hash=block_hash(h), network_id=CTX.network_id,
                  previous_hash=block_hash(h - 1) if h else '0' * 64,
                  timestamp=float(h), native_transactions=[]) for h in range(46)]
    for number in range(2, 9):
        for offset in range(2):
            height = (number - 2) * 2 + offset
            chain[height].update(creator_wallet=account(number).address.lower(), submission_id=f'earned-{height}',
                                 certificate_id=digest(dict(earned_certificate=height)))
    section(storage, 'chain', chain)
    section(storage, 'finalized_blocks', [dict(block_height=h, block_hash=block_hash(h)) for h in range(46)])
    submissions = []
    for index in range(10):
        height = 15 if index < 5 else 20
        sid = f'prior-participation-{index}'
        content_hash = digest(dict(prior=index))
        wallet = account(2).address.lower()
        payload = dict(wallet_address=wallet, submission_id=sid, content_hash=content_hash,
            dimension='originality', choice='unsure', nonce=f'history-{index}',
            issued_at='2026-10-01T00:00:00+00:00', expires_at='2026-10-02T00:00:00+00:00',
            network_id=PUBLIC_TESTNET_V1_NETWORK_ID)
        message = dual_review.vote_message(**payload).encode()
        signature = sign(message, 2)
        vote = dict(voter=wallet, voter_wallet_address=wallet, submission_id=sid, content_hash=content_hash,
            dimension='originality', vote_type='unsure', vote_version=2, protocol_version=1,
            network_id=PUBLIC_TESTNET_V1_NETWORK_ID, signature_scheme='personal_sign',
            vote_signature=signature, vote_message=message.decode(), signed_message_hash=hashlib.sha256(message).hexdigest(),
            vote_nonce=payload['nonce'], vote_issued_at=payload['issued_at'], vote_expires_at=payload['expires_at'],
            vote_identity=dual_review.vote_identity(signature=signature, **payload), reviewer_policy_version=1,
            reputation_rule_version=2, reviewer_status='PROBATIONARY_REVIEWER', reviewer_eligible=True,
            reviewer_status_effective_height=height, reviewer_status_reference_block_hash=block_hash(height),
            created_at=f'2026-10-01T00:00:{index:02}+00:00')
        storage.record_durable_vote(vote)
        submissions.append(dict(submission_id=sid, content_hash=content_hash, submitter=account(1).address.lower()))
    section(storage, 'submissions', submissions)
    with storage._connect() as connection:
        connection.execute('CREATE TABLE task715_frozen (submission TEXT, original TEXT, context TEXT, votes BLOB, attestation BLOB)')
        connection.execute('CREATE TABLE task715_claims (claim TEXT PRIMARY KEY)')


@pytest.fixture(scope='module')
def source(tmp_path_factory):
    root = tmp_path_factory.mktemp('task715-source')
    patch = pytest.MonkeyPatch()
    patch.setattr(tempfile, 'tempdir', str(root))
    storage = SQLiteStorageBackend(sqlite_db_path=str(root / 'application.sqlite3'))
    seed(storage)
    reader = SQLiteHistoryReader(TestOnlyConfig(CTX, True), storage, FixtureJournal())
    with reader.read() as bound:
        history = _History(bound, CTX, {account(n).address.lower() for n in range(2, 9)})
    valid, old, _ = application_admission(b'authenticated application history ' * 1000)
    for vote in old['votes']:
        vote.update(reviewer_status_effective_height=45, reviewer_status_reference_block_hash=block_hash(45))
    app = build_admission_certificate(submission_id=old['submission_id'], content_hash=old['content_hash'],
        creator_wallet=old['creator_wallet'], media_bytes=valid.raw_media_bytes,
        technical_evidence=old['technical_evidence'], attestation=old['attestation'], votes=old['votes'],
        reviewer_status_resolver=history.status)
    submissions = read_section(storage, 'submissions')
    submissions.append(dict(submission_id=app['submission_id'], content_hash=app['content_hash'],
                            submitter=app['creator_wallet'], admission_certificate=app))
    section(storage, 'submissions', submissions)
    cert = contextual_certificate(app)
    freeze(storage, cert)
    with IsolatedDecoder() as decoder:
        adapter = AdmissionAdapter(TestOnlyConfig(CTX, True), AdmissionDependencies(history.status, lambda h: False), decoder=decoder)
        prepared = adapter.prepare(valid, app)
        yield storage, adapter, prepared, cert, valid, app, decoder
    patch.undo()


@pytest.fixture
def harness(source, tmp_path):
    storage, adapter, prepared, cert, *_ = source
    copied = tmp_path / 'application.sqlite3'
    shutil.copyfile(storage.sqlite_db_path, copied)
    local = SQLiteStorageBackend(sqlite_db_path=str(copied))
    reader = SQLiteHistoryReader(adapter.config, local, FixtureJournal())
    return local, AuthenticatedHistoryAdapter(adapter, reader), prepared, deepcopy(cert)


def expect_invalid(operation, match=None):
    with pytest.raises(IntegrationError, match=match) as exc:
        operation()
    assert exc.value.classification == Failure.INVALID_CANONICAL


def test_authenticated_dual_review_and_read_only_snapshot(harness):
    storage, integration, prepared, cert = harness
    before = Path(storage.sqlite_db_path).read_bytes()
    result = integration.issue(prepared)
    assert type(result) is CertificationProposal
    assert result.evidence.certificate_bytes == canonical(cert)
    assert result.evidence.originality_ratio == dict(numerator=5, denominator=7)
    assert result.replay.canonical_head == result.replay.finalized_head == (45, block_hash(45))
    assert result.replay.keys == replay_keys(CTX, cert)
    assert Path(storage.sqlite_db_path).read_bytes() == before
    # Caller mutations cannot alter immutable accepted history/results.
    result.evidence.certificate['votes'].clear()
    assert integration.issue(prepared) == result


@pytest.mark.parametrize('case', ['eligible-flag', 'forged-status', 'unsigned', 'missing-submission',
    'signature', 'reference', 'quota', 'missing-reference', 'policy', 'identity'])
def test_bad_or_missing_historical_participation(harness, case):
    storage, integration, prepared, _ = harness
    with storage._connect() as connection:
        if case == 'eligible-flag':
            connection.execute('UPDATE durable_vote_records SET reviewer_eligible=0')
        elif case == 'forged-status':
            connection.execute("UPDATE durable_vote_records SET reviewer_status='ESTABLISHED_REVIEWER'")
        elif case == 'unsigned':
            connection.execute("UPDATE durable_vote_records SET identity_status='legacy_unverifiable'")
        elif case == 'signature':
            connection.execute("UPDATE durable_vote_records SET signature='bad'")
        elif case == 'reference':
            connection.execute("UPDATE durable_vote_records SET reviewer_status_reference_block_hash=?", ('f' * 64,))
        elif case == 'quota':
            connection.execute('UPDATE durable_vote_records SET reviewer_status_effective_height=15, reviewer_status_reference_block_hash=?', (block_hash(15),))
        elif case == 'missing-reference':
            connection.execute('UPDATE durable_vote_records SET reviewer_status_effective_height=NULL, reviewer_status_reference_block_hash=NULL')
        elif case == 'policy':
            connection.execute('UPDATE durable_vote_records SET reputation_rule_version=1')
        elif case == 'identity':
            connection.execute('UPDATE durable_vote_records SET vote_identity=lower(hex(randomblob(32)))')
        # Change BOTH representations for metadata cases: these must fail the
        # historical derivation, rather than merely the column/source check.
        changes = {'eligible-flag': dict(reviewer_eligible=False),
            'forged-status': dict(reviewer_status='ESTABLISHED_REVIEWER'),
            'reference': dict(reviewer_status_reference_block_hash='f' * 64),
            'quota': dict(reviewer_status_effective_height=15, reviewer_status_reference_block_hash=block_hash(15)),
            'missing-reference': dict(reviewer_status_effective_height=None, reviewer_status_reference_block_hash=None),
            'policy': dict(reputation_rule_version=1)}.get(case)
        if changes:
            for identity, raw in connection.execute('SELECT evidence_id,source_record_json FROM durable_vote_records').fetchall():
                original = json.loads(raw)
                original.update(changes)
                connection.execute('UPDATE durable_vote_records SET source_record_json=? WHERE evidence_id=?',
                                   (json.dumps(original), identity))
    if case == 'missing-submission':
        section(storage, 'submissions', [s for s in read_section(storage, 'submissions') if not s['submission_id'].startswith('prior-')])
    if case in ('unsigned', 'missing-submission', 'missing-reference'):
        assert type(integration.issue(prepared)) is IncompleteEvidence
    else:
        expect_invalid(lambda: integration.issue(prepared))


@pytest.mark.parametrize('case', ['eligibility', 'status', 'signature', 'dimension', 'submission', 'media',
    'network', 'protocol', 'signing-version', 'duplicate', 'malleated-duplicate', 'nonce-duplicate'])
def test_forged_selected_evidence(harness, case):
    storage, integration, prepared, cert = harness
    vote = cert['votes'][0]
    if case == 'eligibility':
        vote['reviewer_eligible'] = False
    elif case == 'status':
        cert['votes'][1]['reviewer_status'] = 'ESTABLISHED_REVIEWER'
    elif case == 'signature':
        vote['vote_signature'] = '0x' + '01' + vote['vote_signature'][4:]
    elif case == 'dimension':
        vote['dimension'] = 'originality'
    elif case == 'submission':
        vote['submission_id'] = 'f' * 32
        resign(vote)
    elif case == 'media':
        vote['content_hash'] = 'f' * 64
        resign(vote)
    elif case == 'network':
        vote['network_id'] = 'other-network'
    elif case == 'protocol':
        vote['protocol_version'] = 1
    elif case == 'signing-version':
        vote['vote_version'] = 2
    elif case in ('duplicate', 'malleated-duplicate'):
        other = deepcopy(vote)
        if case == 'malleated-duplicate':
            raw = bytes.fromhex(other['vote_signature'][2:])
            other['vote_signature'] = '0x' + (raw[:32] + (CURVE_ORDER - int.from_bytes(raw[32:64])).to_bytes(32) + bytes([55 - raw[64]])).hex()
            other['vote_identity'] = digest(dict(payload=evidence.vote_payload(other, CTX), signature=other['vote_signature']))
        cert['votes'].append(other)
    elif case == 'nonce-duplicate':
        same_wallet = next(v for v in cert['votes'] if v['dimension'] != vote['dimension']
                           and v['voter_wallet_address'] == vote['voter_wallet_address'])
        same_wallet['vote_nonce'] = vote['vote_nonce']
        resign(same_wallet)
    cert['votes'].sort(key=lambda v: (v['dimension'], v['voter_wallet_address'], v['vote_identity']))
    freeze(storage, cert)
    expect_invalid(lambda: integration.issue(prepared))


@pytest.mark.parametrize('dimension', ['originality', 'admissibility'])
@pytest.mark.parametrize('case', ['quorum', 'established', 'unsure-only'])
def test_quorum_and_qualification_remain_independent(harness, dimension, case):
    storage, integration, prepared, cert = harness
    if case == 'quorum':
        group = [v for v in cert['votes'] if v['dimension'] == dimension]
        cert['votes'] = [v for v in cert['votes'] if v['dimension'] != dimension] + group[:4]
    elif case == 'established':
        cert['votes'] = [v for v in cert['votes'] if v['dimension'] != dimension or v['reviewer_status'] != 'ESTABLISHED_REVIEWER']
    else:
        for vote in cert['votes']:
            if vote['dimension'] == dimension:
                vote['vote_type'] = 'unsure'
                resign(vote)
    cert['votes'].sort(key=lambda v: (v['dimension'], v['voter_wallet_address'], v['vote_identity']))
    freeze(storage, cert)
    result = integration.issue(prepared)
    assert type(result) is IncompleteEvidence and result.missing == (dimension + '_review',)


@pytest.mark.parametrize('case', ['no-journal', 'no-selection', 'no-finality', 'no-submission', 'no-certificate', 'no-network'])
def test_missing_authoritative_history_is_explicit(harness, case):
    storage, integration, prepared, _ = harness
    if case == 'no-journal':
        integration.reader.journal = None
    elif case == 'no-selection':
        with storage._connect() as connection:
            connection.execute('DELETE FROM task715_frozen')
    elif case == 'no-finality':
        section(storage, 'finalized_blocks', [])
    elif case == 'no-network':
        chain = read_section(storage, 'chain')
        chain[0].pop('network_id')
        section(storage, 'chain', chain)
    else:
        submissions = read_section(storage, 'submissions')
        if case == 'no-submission':
            submissions = [s for s in submissions if s['submission_id'] != prepared.certificate['submission_id']]
        else:
            next(s for s in submissions if s['submission_id'] == prepared.certificate['submission_id']).pop('admission_certificate')
        section(storage, 'submissions', submissions)
    assert type(integration.issue(prepared)) is IncompleteEvidence


@pytest.mark.parametrize('case', ['journal-genesis', 'journal-network', 'chain-genesis', 'chain-network', 'reorg', 'contradictory-finality',
                                  'stored-media', 'stored-creator', 'certificate-mutation', 'minted'])
def test_context_and_contradictory_history_reject(harness, case):
    storage, integration, prepared, cert = harness
    if case.startswith('journal-'):
        freeze(storage, cert, context=replace(CTX, **({'genesis_hash': 'e' * 64} if case == 'journal-genesis' else {'network_id': 'other-network'})))
    elif case in ('chain-genesis', 'chain-network', 'reorg', 'minted'):
        chain = read_section(storage, 'chain')
        if case == 'chain-genesis':
            chain[0]['hash'] = 'e' * 64
        elif case == 'chain-network':
            chain[0]['network_id'] = 'another-network'
        elif case == 'reorg':
            chain[45]['hash'] = 'e' * 64
        else:
            chain[45]['content_hash'] = cert['content_hash']
        section(storage, 'chain', chain)
    elif case == 'contradictory-finality':
        finalized = read_section(storage, 'finalized_blocks')
        finalized.append(dict(block_height=45, block_hash='e' * 64))
        section(storage, 'finalized_blocks', finalized)
    else:
        submissions = read_section(storage, 'submissions')
        app = next(s for s in submissions if s['submission_id'] == cert['submission_id'])
        if case == 'stored-media':
            app['content_hash'] = 'e' * 64
        elif case == 'stored-creator':
            app['submitter'] = account(2).address.lower()
        else:
            app['admission_certificate']['votes'][0]['reviewer_status'] = 'NEW'
        section(storage, 'submissions', submissions)
    expect_invalid(lambda: integration.issue(prepared))


@pytest.mark.parametrize('kind', ['original', 'submission', 'certificate', 'attestation_nonce',
    'attestation_message', 'attestation_signature', 'review', 'vote_nonce', 'vote_message', 'vote_signature'])
def test_persisted_replay_preflight_rejects_each_claim(harness, kind):
    storage, integration, prepared, cert = harness
    namespace = dict(network_id=CTX.network_id, genesis_hash=CTX.genesis_hash, protocol_version=2)
    att, vote = cert['attestation'], cert['votes'][0]
    identity = {'original': [cert['content_hash']], 'submission': [cert['submission_id']],
        'certificate': [cert['certificate_digest']], 'attestation_nonce': [att['signer_wallet'], att['nonce']],
        'attestation_message': [att['canonical_message_hash']], 'attestation_signature': [att['signature']],
        'review': [vote['submission_id'], vote['dimension'], vote['voter_wallet_address']],
        'vote_nonce': [vote['voter_wallet_address'], vote['vote_nonce']],
        'vote_message': [vote['signed_message_hash']], 'vote_signature': [vote['vote_signature']]}[kind]
    key = digest(dict(**namespace, kind=kind, identity=identity))
    with storage._connect() as connection:
        connection.execute('INSERT INTO task715_claims VALUES (?)', (key,))
    expect_invalid(lambda: integration.issue(prepared), 'evidence_replay_conflict')


def test_conflicting_certificates_for_original_share_a_claim(harness):
    _, _, _, cert = harness
    other = deepcopy(cert)
    other['submission_id'] = 'e' * 32
    attestation = other['attestation']
    attestation['nonce'] += '-other'
    payload = attestation['canonical_payload']
    payload.update(submission_id=other['submission_id'], nonce=attestation['nonce'])
    message = canonical(envelope(payload, 'submitter-attestation', CTX))
    attestation.update(signature=sign(message, 1), canonical_message=message.decode(),
        canonical_payload_digest=hashlib.sha256(message).hexdigest(), canonical_message_hash=hashlib.sha256(message).hexdigest())
    for vote in other['votes']:
        vote['submission_id'] = other['submission_id']
        vote['vote_nonce'] += '-other'
        resign(vote)
    for dimension in evidence.POSITIVE:
        other[dimension] = evidence.derive_tally(other['votes'], dimension, CTX)
    other.pop('certificate_digest')
    other['certificate_digest'] = digest(other)
    evidence.validate_certificate(other, CTX)
    original = digest(dict(network_id=CTX.network_id, genesis_hash=CTX.genesis_hash,
                           protocol_version=2, kind='original', identity=[cert['content_hash']]))
    assert set(replay_keys(CTX, cert)) & set(replay_keys(CTX, other)) == {original}


def test_current_reputation_label_is_not_historical_authority(harness):
    storage, integration, prepared, _ = harness
    for n in range(2, 9):
        storage.initialize_reviewer_state(account(n).address.lower())
    assert type(integration.issue(prepared)) is CertificationProposal  # All current labels are NEW.


def penalty_for(storage, height):
    with storage._connect() as connection:
        vote = json.loads(connection.execute('SELECT source_record_json FROM durable_vote_records ORDER BY observed_at LIMIT 1').fetchone()[0])
    conflict = deepcopy(vote)
    conflict['vote_type'] = 'not_original'
    payload = dict(wallet_address=conflict['voter_wallet_address'], submission_id=conflict['submission_id'],
        content_hash=conflict['content_hash'], dimension=conflict['dimension'], choice=conflict['vote_type'],
        nonce=conflict['vote_nonce'], issued_at=conflict['vote_issued_at'], expires_at=conflict['vote_expires_at'],
        network_id=conflict['network_id'])
    message = dual_review.vote_message(**payload).encode()
    signature = sign(message, 2)
    conflict.update(vote_message=message.decode(), vote_signature=signature,
        signed_message_hash=hashlib.sha256(message).hexdigest(), vote_identity=dual_review.vote_identity(signature=signature, **payload))
    offense = build_offense_evidence(offense_type=SIGNED_VOTE_EQUIVOCATION, votes=[vote, conflict],
        reference_finalized_height=height, reference_finalized_block_hash=block_hash(height), review_epoch=height // 5)
    return ReviewerReputationService(storage).apply_verified_offense(offense,
        state_before='ESTABLISHED_REVIEWER' if height == 45 else 'PROBATIONARY_REVIEWER')


@pytest.mark.parametrize('case', ['active', 'expired', 'forged-duration', 'forged-offense', 'missing-offense'])
def test_reputation_is_reproduced_from_signed_offenses(harness, case):
    storage, integration, prepared, _ = harness
    penalty_for(storage, 20 if case == 'expired' else 45)
    if case in ('forged-duration', 'forged-offense', 'missing-offense'):
        with storage._connect() as connection:
            if case == 'forged-duration':
                connection.execute('UPDATE reviewer_penalties SET penalty_end_epoch=penalty_end_epoch+1')
            elif case == 'forged-offense':
                connection.execute("UPDATE reviewer_offense_records SET evidence_digest=?", ('f' * 64,))
            else:
                connection.execute('DELETE FROM reviewer_offense_records')
    if case == 'expired':
        assert type(integration.issue(prepared)) is CertificationProposal
    else:
        expect_invalid(lambda: integration.issue(prepared))


def test_future_penalty_cannot_change_past_status(harness):
    storage, integration, _, _ = harness
    penalty_for(storage, 45)
    with integration.reader.read() as bound:
        history = _History(bound, CTX, {account(2).address.lower()})
    assert history.status(account(2).address.lower(), 20, block_hash(20)) == 'PROBATIONARY_REVIEWER'
    assert history.status(account(2).address.lower(), 45, block_hash(45)) == 'COOLDOWN'


@pytest.mark.parametrize('unrelated_penalty', [False, True])
def test_unbacked_negative_transition_is_incomplete(harness, unrelated_penalty):
    storage, integration, prepared, _ = harness
    if unrelated_penalty:
        penalty_for(storage, 20)  # Genuine penalty, expired before the transition.
    wallet = account(2).address.lower()
    storage.initialize_reviewer_state(wallet)
    storage.transition_reviewer_state(wallet, to_status='COOLDOWN', reviewer_policy_version=1,
        reputation_rule_version=2, status_effective_height=45, status_reference_block_hash=block_hash(45),
        reason='legacy unsupported penalty transition')
    result = integration.issue(prepared)
    assert type(result) is IncompleteEvidence and result.missing == ('unbacked_penalty_transition',)


def test_two_historical_dimensions_charge_one_participation(harness):
    storage, integration, prepared, _ = harness
    with storage._connect() as connection:
        vote = json.loads(connection.execute('SELECT source_record_json FROM durable_vote_records ORDER BY observed_at LIMIT 1').fetchone()[0])
    vote['dimension'] = 'admissibility'
    vote['vote_nonce'] += '-admissibility'
    payload = dict(wallet_address=vote['voter_wallet_address'], submission_id=vote['submission_id'],
        content_hash=vote['content_hash'], dimension=vote['dimension'], choice=vote['vote_type'],
        nonce=vote['vote_nonce'], issued_at=vote['vote_issued_at'], expires_at=vote['vote_expires_at'], network_id=vote['network_id'])
    message = dual_review.vote_message(**payload).encode()
    signature = sign(message, 2)
    vote.update(vote_message=message.decode(), vote_signature=signature,
        signed_message_hash=hashlib.sha256(message).hexdigest(), vote_identity=dual_review.vote_identity(signature=signature, **payload))
    storage.record_durable_vote(vote)
    assert type(integration.issue(prepared)) is CertificationProposal
    with integration.reader.read() as bound:
        history = _History(bound, CTX, {account(2).address.lower()})
    status = history.status(account(2).address.lower(), 15, block_hash(15))
    assert history.quota(account(2).address.lower(), vote['submission_id'], 15, status)
    assert not history.quota(account(2).address.lower(), 'new-participation', 15, status)


def test_history_snapshot_is_one_read_transaction(harness):
    storage, integration, _, _ = harness
    with integration.reader.read() as bound:
        before = bound.connection.execute('SELECT votes FROM task715_frozen').fetchone()[0]
        assert bound.connection.in_transaction
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            bound.connection.execute('DELETE FROM task715_frozen')
        assert before == bound.connection.execute('SELECT votes FROM task715_frozen').fetchone()[0]
        # Existing service methods do not commit the enclosing snapshot.
        bound.list_durable_votes()
        assert bound.connection.in_transaction
    assert read_section(storage, 'chain')[-1]['hash'] == block_hash(45)


def test_read_only_proposals_detect_changed_history_revision(harness):
    storage, integration, prepared, _ = harness
    first = integration.issue(prepared)
    submissions = read_section(storage, 'submissions')
    submissions[0]['local_history_revision'] = 'changed'
    section(storage, 'submissions', submissions)
    second = integration.issue(prepared)
    assert first.evidence == second.evidence
    assert first.replay.keys == second.replay.keys
    assert first.replay.history_digest != second.replay.history_digest


@pytest.mark.parametrize('case', ['unavailable', 'corrupt', 'bad-journal', 'journal-error', 'replay-error'])
def test_storage_failures_fail_closed(harness, monkeypatch, case):
    storage, integration, prepared, _ = harness
    if case == 'unavailable':
        integration.reader.path = Path(storage.sqlite_db_path).with_name('absent.sqlite3')
    elif case == 'corrupt':
        with storage._connect() as connection:
            connection.execute('DROP TABLE durable_vote_records')
    elif case == 'bad-journal':
        monkeypatch.setattr(integration.reader.journal, 'load', lambda *a: False)
    elif case == 'journal-error':
        def unavailable(*args):
            raise OSError('journal offline')
        monkeypatch.setattr(integration.reader.journal, 'load', unavailable)
    else:
        def unavailable(*args):
            raise sqlite3.OperationalError('replay state unavailable')
        monkeypatch.setattr(integration.reader.journal, 'claimed', unavailable)
    with pytest.raises(IntegrationError) as exc:
        integration.issue(prepared)
    assert exc.value.classification == Failure.LOCAL_FAILURE


def test_selection_is_complete_and_journal_not_caller_supplied(harness):
    _, integration, prepared, _ = harness
    with pytest.raises(TypeError):
        integration.issue(prepared, votes=[], reviewer_eligible=True)
    # This boundary accepts only the journal's complete immutable selection.
    assert len(integration.issue(prepared).evidence.certificate['votes']) == 14


def test_concurrent_preflight_does_not_claim_durable_replay_protection(harness):
    storage, integration, prepared, _ = harness
    with ThreadPoolExecutor(max_workers=2) as pool:
        proposals = list(pool.map(lambda _: integration.issue(prepared), range(2)))
    assert proposals[0] == proposals[1]
    with storage._connect() as connection:
        assert connection.execute('SELECT count(*) FROM task715_claims').fetchone()[0] == 0

    # Isolated SQLite contract probe ONLY. The production block/certificate
    # transaction is deliberately not implemented. Rollback must free ALL keys.
    def claim_probe(proposal, *, abort=False):
        try:
            with sqlite3.connect(storage.sqlite_db_path) as connection:
                connection.execute('BEGIN IMMEDIATE')
                connection.executemany('INSERT INTO task715_claims VALUES (?)', [(k,) for k in proposal.replay.keys])
                if abort:
                    raise RuntimeError('injected precommit failure')
            return True
        except sqlite3.IntegrityError:
            return False
    with pytest.raises(RuntimeError):
        claim_probe(proposals[0], abort=True)
    with storage._connect() as connection:
        assert connection.execute('SELECT count(*) FROM task715_claims').fetchone()[0] == 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(claim_probe, proposals)) == [False, True]
    expect_invalid(lambda: integration.issue(prepared), 'evidence_replay_conflict')


def test_identity_zstd_share_certificate_and_replay_claims(source, monkeypatch):
    storage, _, _, cert, valid, app, decoder = source
    reader = SQLiteHistoryReader(TestOnlyConfig(CTX, True), storage, FixtureJournal())
    with reader.read() as bound:
        history = _History(bound, CTX, {account(n).address.lower() for n in range(2, 9)})
    proposals, descriptors = [], []
    for identity in (False, True):
        if identity:
            monkeypatch.setattr(media, '_compress_default', lambda raw: None)
        adapter = AdmissionAdapter(TestOnlyConfig(CTX, True), AdmissionDependencies(history.status, lambda h: False), decoder=decoder)
        prepared = adapter.prepare(valid, app)
        proposals.append(AuthenticatedHistoryAdapter(adapter, reader).issue(prepared))
        descriptors.append(prepared.descriptor)
    assert proposals[0] == proposals[1]
    assert proposals[0].evidence.certificate_bytes == canonical(cert)
    assert [d['codec_id'] for d in descriptors] == ['zstd', 'identity']
    assert descriptors[0]['original_sha256'] == descriptors[1]['original_sha256'] == cert['content_hash']


def test_no_active_registration_or_schema_changes():
    root = Path(__file__).resolve().parents[1]
    for path in [root / 'blockchain.py', root / 'storage.py', root / 'api_runtime.py',
                 *list((root / 'services').glob('*.py')), *list((root / 'api_routers').glob('*.py'))]:
        assert 'canonical_v3' not in path.read_text(encoding='utf-8'), path
