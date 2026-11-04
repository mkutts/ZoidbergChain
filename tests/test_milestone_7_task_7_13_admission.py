"""Deterministic offline admission integration; real validation and test signatures."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile

from eth_account import Account
from eth_account.messages import encode_defunct
from PIL import Image
import pytest

from admission_certificate import build_admission_certificate
import dual_review
import media_technical_validation as technical
from protocol_v1 import PUBLIC_TESTNET_V1_NETWORK_ID
import protocol_v1_submitter_attestation as rights
from canonical_v3 import block, evidence, media, transactions
from canonical_v3.admission import (
    AdmissionAdapter, AdmissionDependencies, Failure, IntegrationError,
    TestOnlyConfig, reserve_identity,
)
from canonical_v3.construction import (
    BlockConstructionBridge, CandidateRecord, ConstructionState, IncompleteConstruction,
)
from canonical_v3.primitives import Context, MAX_RECORD, V3Error, canonical, digest, envelope, parse
from codec_prototype.isolated_decoder import IsolatedDecoder, Limits, Outcome, Status

FIXTURES = Path(__file__).parent / 'fixtures/milestone_7_v3_v1'
CTX = Context(**json.loads((FIXTURES / 'manifest.json').read_bytes())['context'])
BASE = json.loads((FIXTURES / 'block-identity.json').read_bytes())['envelope']['payload']
SID = BASE['submission_id']
ISSUE, EXPIRE = '2026-10-19T00:00:00+00:00', '2026-10-20T00:00:00+00:00'


def account(number):
    return Account.from_key(bytes([number * 17]) * 32)


def sign(message, number):
    return '0x' + Account.sign_message(encode_defunct(primitive=message), account(number).key).signature.hex()


def image(fmt='PNG'):
    buf = io.BytesIO()
    Image.new('RGB', (3, 2), (12, 34, 56)).save(buf, format=fmt)
    return buf.getvalue()


def application_admission(raw=b'a', mime='text/plain', submission_id=SID, reference_hash=CTX.genesis_hash):
    """No mocked acceptance: current byte validator, rights/reviews and cert verifier."""
    validated = technical.validate_media_bytes(raw, declared_mime_type=mime)
    tech = validated.result
    creator = account(1).address.lower()
    ap = rights.build_submitter_attestation_payload(wallet_address=creator,
        submission_id=submission_id, raw_media_sha256=tech['raw_media_sha256'],
        policy_id=tech['policy_id'], policy_version=tech['policy_version'],
        policy_digest=tech['policy_digest'], technical_evidence_version=1,
        technical_evidence_digest=tech['evidence_digest'], nonce='offline-admission',
        issued_at=ISSUE, expires_at=EXPIRE, network_id=PUBLIC_TESTNET_V1_NETWORK_ID)
    message = rights.build_submitter_attestation_message(**ap).encode()
    attestation = rights.build_submitter_attestation_record(payload=ap, signature=sign(message, 1), verified_at=ISSUE)
    votes, statuses = [], {}
    for number in range(2, 7):
        wallet = account(number).address.lower()
        status = 'ESTABLISHED_REVIEWER' if number == 2 else 'PROBATIONARY_REVIEWER'
        statuses[wallet, 0, reference_hash] = status
        for dimension, choice in evidence.POSITIVE.items():
            values = dict(wallet_address=wallet, submission_id=submission_id,
                content_hash=tech['raw_media_sha256'], dimension=dimension, choice=choice,
                nonce=f'offline-{number}-{dimension}', issued_at=ISSUE, expires_at=EXPIRE,
                network_id=PUBLIC_TESTNET_V1_NETWORK_ID)
            message = dual_review.vote_message(**values).encode()
            signature = sign(message, number)
            votes.append(dict(submission_id=submission_id, content_hash=tech['raw_media_sha256'], voter=wallet,
                voter_wallet_address=wallet, vote_type=choice, dimension=dimension, vote_version=2,
                protocol_version=1, network_id=PUBLIC_TESTNET_V1_NETWORK_ID, signature_scheme='personal_sign',
                vote_signature=signature, vote_message=message.decode(), vote_nonce=values['nonce'],
                signed_message_hash=hashlib.sha256(message).hexdigest(), vote_issued_at=ISSUE,
                vote_expires_at=EXPIRE, vote_identity=dual_review.vote_identity(signature=signature, **values),
                reviewer_policy_version=1, reputation_rule_version=2, reviewer_status=status,
                reviewer_eligible=True, reviewer_status_effective_height=0,
                reviewer_status_reference_block_hash=reference_hash))
    resolver = lambda wallet, height, ref: statuses.get((wallet, height, ref))
    certificate = build_admission_certificate(submission_id=submission_id, content_hash=tech['raw_media_sha256'],
        creator_wallet=creator, media_bytes=validated.raw_media_bytes, technical_evidence=tech,
        attestation=attestation, votes=votes, reviewer_status_resolver=resolver)
    return validated, certificate, resolver


def v2_certificate(app):
    """New explicit test signatures, never relabel old signed evidence in runtime."""
    cert = deepcopy(BASE['admission_certificate'])
    cert['submission_id'] = app['submission_id']
    cert['content_hash'] = app['content_hash']
    tech = deepcopy(app['technical_evidence'])
    tech.update(evidence.policy_fields(CTX))
    tech.pop('evidence_digest')
    tech['evidence_digest'] = digest(tech)
    cert['technical_evidence'] = tech
    ap = cert['attestation']['canonical_payload']
    ap.update(submission_id=app['submission_id'], raw_media_sha256=app['content_hash'], technical_evidence_digest=tech['evidence_digest'])
    message = canonical(envelope(ap, 'submitter-attestation', CTX))
    cert['attestation'].update(signature=sign(message, 1), canonical_payload_digest=hashlib.sha256(message).hexdigest(),
        canonical_message=message.decode(), canonical_message_hash=hashlib.sha256(message).hexdigest())
    for vote in cert['votes']:
        vote['submission_id'] = app['submission_id']
        vote['content_hash'] = app['content_hash']
        vp = evidence.vote_payload(vote, CTX)
        message = canonical(vp)
        number = next(n for n in range(2, 9) if account(n).address.lower() == vote['voter_wallet_address'])
        signature = sign(message, number)
        vote.update(vote_message=message.decode(), vote_signature=signature,
            signed_message_hash=digest(vp), vote_identity=digest(dict(payload=vp, signature=signature)))
    for dimension in evidence.POSITIVE:
        cert[dimension] = evidence.derive_tally(cert['votes'], dimension, CTX)
    cert.pop('certificate_digest')
    cert['certificate_digest'] = digest(cert)
    evidence.validate_certificate(cert, CTX)
    return cert


def state_for(cert):
    statuses = {(v['voter_wallet_address'], v['reviewer_status_effective_height'],
                 v['reviewer_status_reference_block_hash']): v['reviewer_status'] for v in cert['votes']}
    native = BASE['native_transactions'][0]
    return ConstructionState(0, CTX.genesis_hash, '1792367999', 5000000,
        {native['from_address']: 2000000, native['to_address']: 0}, {native['from_address']: 1},
        lambda wallet, height, ref: statuses.get((wallet, height, ref)))


def header_for(mime='text/plain'):
    return {**{k: BASE[k] for k in ('index', 'previous_hash', 'timestamp', 'minted_at', 'miner')},
            'content_type': 'text' if mime == 'text/plain' else 'image'}


@pytest.fixture(autouse=True)
def worker_root(tmp_path, monkeypatch):
    root = tmp_path / 'private-worker-temp'
    root.mkdir()
    monkeypatch.setattr(tempfile, 'tempdir', str(root))


@pytest.fixture
def harness():
    validated, cert, resolver = application_admission()
    with IsolatedDecoder() as decoder:
        adapter = AdmissionAdapter(TestOnlyConfig(CTX, True), AdmissionDependencies(resolver, lambda h: False), decoder=decoder)
        yield adapter, validated, cert


@pytest.mark.parametrize('fmt,mime', [('JPEG', 'image/jpeg'), ('PNG', 'image/png'),
    ('WEBP', 'image/webp'), ('GIF', 'image/gif'), (None, 'text/plain')])
def test_real_admission_to_candidate(fmt, mime):
    raw = image(fmt) if fmt else b'a'
    validated, app, resolver = application_admission(raw, mime)
    with IsolatedDecoder() as decoder:
        adapter = AdmissionAdapter(TestOnlyConfig(CTX, True), AdmissionDependencies(resolver, lambda h: False), decoder=decoder)
        prepared = adapter.prepare(validated, app)
        cert = v2_certificate(app)
        candidate = BlockConstructionBridge(adapter).construct(prepared, header=header_for(mime),
            certificate=cert, state=state_for(cert), native_transactions=BASE['native_transactions'])
        assert type(candidate) is CandidateRecord and candidate.finalized is False
        record = block.parse_record(candidate.canonical_record, CTX)
        p = record['envelope']['payload']
        assert p['media']['original_sha256'] == hashlib.sha256(raw).hexdigest() == app['content_hash']
        assert media.reconstruct(p['media'], decoder=decoder).original == raw == prepared.original
        assert prepared.original is validated.raw_media_bytes
        assert prepared.certificate == app
        assert p['creator_wallet'] == app['creator_wallet']
        assert p['approval_percentage'] == dict(numerator=5, denominator=7)
        assert p['transactions'] == [transactions.reward(app['creator_wallet'])]
        assert candidate.sizes.complete == len(candidate.canonical_record) <= candidate.identity_reservation <= MAX_RECORD


def test_missing_certificate_is_incomplete_not_relabelled(harness):
    adapter, validated, app = harness
    prepared = adapter.prepare(validated, app)
    result = BlockConstructionBridge(adapter).construct(prepared, header=header_for())
    assert result.classification == Failure.INCOMPLETE and result.canonical_record is None
    assert result.missing == ('v2_admission_certificate', 'construction_state', 'native_transaction_selection')
    with pytest.raises(IntegrationError) as exc:
        BlockConstructionBridge(adapter).construct(prepared, header=header_for(), certificate=app)
    assert exc.value.classification == Failure.INVALID_CANONICAL


@pytest.mark.parametrize('raw,codec', [(b'a', 'identity'), (b'a' * 10000, 'zstd')])
def test_complete_descriptor_choice_and_original_identity(raw, codec):
    validated, cert, resolver = application_admission(raw)
    with IsolatedDecoder() as decoder:
        adapter = AdmissionAdapter(TestOnlyConfig(CTX, True), AdmissionDependencies(resolver, lambda h: False), decoder=decoder)
        prepared = adapter.prepare(validated, cert)
        desc = prepared.descriptor
        assert desc['codec_id'] == codec
        identity = media.descriptor(raw, raw, 'text/plain', 'identity')
        assert len(prepared.descriptor_bytes) <= len(canonical(identity))
        assert desc['original_sha256'] == identity['original_sha256']


def test_identity_fallback_and_duplicate_original_across_encodings(monkeypatch):
    validated, cert, resolver = application_admission(b'a' * 10000)
    claims = set()
    with IsolatedDecoder() as decoder:
        deps = AdmissionDependencies(resolver, lambda h: h in claims)
        first = AdmissionAdapter(TestOnlyConfig(CTX, True), deps, decoder=decoder)
        compressed = first.prepare(validated, cert)
        monkeypatch.setattr(media, '_compress_default', lambda raw: None)
        second = AdmissionAdapter(TestOnlyConfig(CTX, True), deps, decoder=decoder)
        identity = second.prepare(validated, cert)
        assert compressed.descriptor['codec_id'] == 'zstd' and identity.descriptor['codec_id'] == 'identity'
        v2 = v2_certificate(cert)
        args = dict(header=header_for(), certificate=v2, state=state_for(v2), native_transactions=[])
        records = [parse(BlockConstructionBridge(adapter).construct(prepared, **args).canonical_record)
                   for adapter, prepared in ((first, compressed), (second, identity))]
        assert records[0]['hash'] != records[1]['hash']
        for record in records:
            assert record['hash'] == digest(record['envelope'])
            assert record['envelope']['payload']['media']['original_sha256'] == cert['content_hash']
        claims.add(identity.descriptor['original_sha256'])
        for adapter, prepared in ((first, compressed), (second, identity)):
            with pytest.raises(IntegrationError, match='duplicate_original'):
                adapter.verify_prepared(prepared)
        with pytest.raises(IntegrationError, match='duplicate_original'):
            second.prepare(validated, cert)


@pytest.mark.parametrize('raw,mime', [(b'GIF89a broken', 'image/gif'), (image()[:-2], 'image/png'),
    (b'x' * (media.MAX_TEXT + 1), 'text/plain'), (b'x' * (media.MAX_IMAGE + 1), 'image/png'),
    (image(), 'image/jpeg'), (b'a', 'application/pdf')],
    ids=['malformed', 'truncated', 'oversize-text', 'oversize-image', 'mime-mismatch', 'unsupported'])
def test_handmade_validated_result_cannot_assert_admission(raw, mime, harness):
    adapter, valid, app = harness
    fake = technical.ValidatedMedia(raw, None, dict(valid.result, detected_mime_type=mime))
    with pytest.raises(IntegrationError) as exc:
        adapter.prepare(fake, app)
    assert exc.value.classification == Failure.INVALID_ADMISSION


@pytest.mark.parametrize('field', ['attestation', 'votes', 'technical_evidence', 'creator_wallet', 'content_hash'])
def test_tampered_application_admission_rejected(field, harness):
    adapter, valid, app = harness
    app[field] = None
    with pytest.raises(IntegrationError) as exc:
        adapter.prepare(valid, app)
    assert exc.value.classification == Failure.INVALID_ADMISSION


@pytest.mark.parametrize('reason', ['unavailable', 'crash', 'timeout'])
@pytest.mark.parametrize('stage', ['prepare', 'construct'])
def test_codec_local_failures_preserved(reason, stage, monkeypatch, harness):
    adapter, valid, app = harness
    cert = v2_certificate(app)
    prepared = adapter.prepare(valid, app) if stage == 'construct' else None
    outcome = Outcome(Status.INDETERMINATE_LOCAL_FAILURE, reason=reason)
    monkeypatch.setattr(adapter.decoder, 'validate', lambda raw: outcome)
    with pytest.raises(IntegrationError) as exc:
        if stage == 'prepare':
            adapter.prepare(valid, app)
        else:
            BlockConstructionBridge(adapter).construct(prepared, header=header_for(), certificate=cert,
                state=state_for(cert), native_transactions=[])
    assert exc.value.classification == Failure.LOCAL_FAILURE and exc.value.outcome is outcome


def test_closed_decoder_unavailable(harness):
    adapter, valid, cert = harness
    adapter.decoder.close()
    with pytest.raises(IntegrationError) as exc:
        adapter.prepare(valid, cert)
    assert exc.value.classification == Failure.LOCAL_FAILURE


@pytest.mark.parametrize('timeout', [False, True])
def test_technical_worker_failures_are_local(timeout, monkeypatch, harness):
    adapter, _, cert = harness
    valid, image_cert, _ = application_admission(image(), 'image/png')
    def failed(*a, **k):
        if timeout:
            raise TimeoutError()
        raise technical.MediaValidationUnavailable('worker unavailable')
    monkeypatch.setattr(technical, '_run_isolated_decoder', failed)
    with pytest.raises(IntegrationError) as exc:
        adapter.prepare(valid, image_cert)
    assert exc.value.classification == Failure.LOCAL_FAILURE


@pytest.mark.parametrize('mutation', ['hash', 'payload', 'null_image_field', 'missing_image_field', 'extra', 'attestation', 'votes'])
def test_bad_v2_evidence_is_invalid_canonical(mutation, harness):
    adapter, valid, app = harness
    prepared = adapter.prepare(valid, app)
    cert = v2_certificate(app)
    if mutation == 'hash':
        cert['content_hash'] = '0' * 64
    elif mutation == 'payload':
        cert['attestation']['canonical_payload']['raw_media_sha256'] = '0' * 64
    elif mutation == 'null_image_field':
        cert['technical_evidence']['width_pixels'] = 0
    elif mutation == 'missing_image_field':
        del cert['technical_evidence']['width_pixels']
    elif mutation == 'extra':
        cert['extra'] = None
    else:
        cert[mutation] = None
    with pytest.raises(IntegrationError) as exc:
        BlockConstructionBridge(adapter).construct(prepared, header=header_for(), certificate=cert,
            state=state_for(v2_certificate(app)), native_transactions=[])
    assert exc.value.classification == Failure.INVALID_CANONICAL


def test_unissued_and_mutated_prepared_inputs(harness):
    adapter, valid, app = harness
    prepared = adapter.prepare(valid, app)
    for forged in (True, replace(prepared), replace(prepared, descriptor_bytes=b'{}')):
        with pytest.raises(IntegrationError):
            BlockConstructionBridge(adapter).construct(forged, header=header_for())
    copy = prepared.descriptor
    copy['original_sha256'] = '0' * 64
    assert prepared.descriptor['original_sha256'] == app['content_hash']


def test_identity_reservation_at_approved_caps():
    image_budget = reserve_identity(media.MAX_IMAGE, 'image/png')
    assert image_budget.complete_bound == block.conservative_size_bound() == 3058797
    assert MAX_RECORD - image_budget.complete_bound == 86931
    assert image_budget.identity_payload == 2796204
    assert image_budget.descriptor_bound == 2796435
    assert reserve_identity(media.MAX_TEXT, 'text/plain').complete_bound == 612121
    for size, mime in ((media.MAX_IMAGE + 1, 'image/png'), (media.MAX_TEXT + 1, 'text/plain')):
        with pytest.raises(V3Error):
            reserve_identity(size, mime)


@pytest.mark.parametrize('case', ['null_certificate', 'null_state', 'null_transactions', 'too_many',
    'unsigned', 'oversize_transaction', 'insufficient_reward', 'wrong_reviewer', 'insufficient_balance',
    'nonce', 'header_extra', 'header_null', 'caption_on_text'])
def test_closed_construction_and_state_limits(case, harness):
    adapter, valid, app = harness
    prepared = adapter.prepare(valid, app)
    cert = v2_certificate(app)
    state = state_for(cert)
    args = dict(header=header_for(), certificate=cert, state=state, native_transactions=[])
    if case.startswith('null_'):
        args[{'null_certificate': 'certificate', 'null_state': 'state', 'null_transactions': 'native_transactions'}[case]] = None
    elif case == 'too_many':
        args['native_transactions'] = BASE['native_transactions'] * 11
    elif case in ('unsigned', 'oversize_transaction'):
        tx = deepcopy(BASE['native_transactions'][0])
        tx['signature' if case == 'unsigned' else 'memo'] = None if case == 'unsigned' else 'x' * 8193
        args['native_transactions'] = [tx]
    elif case == 'insufficient_reward':
        args['state'] = replace(state, reward_pool_units=4999999)
    elif case == 'wrong_reviewer':
        args['state'] = replace(state, reviewer_status_resolver=lambda *a: 'INELIGIBLE')
    elif case in ('insufficient_balance', 'nonce'):
        tx = BASE['native_transactions'][0]
        args['native_transactions'] = [tx]
        args['state'] = replace(state, **({'balances': {tx['from_address']: 0, tx['to_address']: 0}}
            if case == 'insufficient_balance' else {'next_nonces': {tx['from_address']: 2}}))
    elif case == 'header_extra':
        args['header']['transactions'] = []
    elif case == 'header_null':
        args['header']['index'] = None
    else:
        args['header']['meme_text'] = 'caption'
    with pytest.raises(IntegrationError) as exc:
        BlockConstructionBridge(adapter).construct(prepared, **args)
    assert exc.value.classification == Failure.INVALID_CANONICAL


@pytest.mark.parametrize('missing', ['reviewers', 'ledger'])
def test_missing_state_is_incomplete(missing, harness):
    adapter, valid, app = harness
    prepared = adapter.prepare(valid, app)
    cert = v2_certificate(app)
    state = state_for(cert)
    state = replace(state, **({'reviewer_status_resolver': lambda *a: None} if missing == 'reviewers' else {'balances': {}}))
    result = BlockConstructionBridge(adapter).construct(prepared, header=header_for(), certificate=cert,
        state=state, native_transactions=BASE['native_transactions'])
    assert isinstance(result, IncompleteConstruction) and result.classification == Failure.INCOMPLETE


def test_exact_final_byte_gate_and_optional_transaction_independence(monkeypatch, harness):
    adapter, valid, app = harness
    prepared = adapter.prepare(valid, app)
    cert = v2_certificate(app)
    bridge = BlockConstructionBridge(adapter)
    args = dict(header=header_for(), certificate=cert, state=state_for(cert))
    candidate = bridge.construct(prepared, native_transactions=[], **args)
    size = len(candidate.canonical_record)
    # Instrument the existing final gate at C-1/C/C+1. Artificial small cap,
    # not a claim that an approved record can reach 3 MiB under tighter caps.
    for limit in (size, size + 1):
        monkeypatch.setattr(block, 'MAX_RECORD', limit)
        assert bridge.construct(prepared, native_transactions=[], **args).sizes.complete == size
    monkeypatch.setattr(block, 'MAX_RECORD', size - 1)
    with pytest.raises(IntegrationError, match='block_size'):
        bridge.construct(prepared, native_transactions=[], **args)
    monkeypatch.setattr(block, 'MAX_RECORD', MAX_RECORD)
    with pytest.raises(IntegrationError):
        bridge.construct(prepared, native_transactions=BASE['native_transactions'] * 11, **args)
    assert bridge.construct(prepared, native_transactions=[], **args).sizes.complete == size


def test_test_only_configuration_and_no_active_imports():
    with pytest.raises(V3Error):
        TestOnlyConfig(CTX, False)
    root = Path(__file__).resolve().parents[1]
    for path in [root / 'blockchain.py', root / 'block.py', root / 'api_runtime.py', root / 'storage.py',
                 *list((root / 'services').glob('*.py')), *list((root / 'api_routers').glob('*.py'))]:
        assert 'canonical_v3' not in path.read_text(encoding='utf-8'), path


def test_actual_application_upload_attestation_review_to_offline_bridge(blockchain):
    from wallet_auth import WalletAuthManager
    raw = b'Actual application admission to offline candidate'
    owner = account(1)
    content = blockchain.upload_text_content_operation(text_content=raw.decode(), submitted_by=owner.address)
    tech = blockchain.technical_validation_evidence_for_content(content)
    auth = WalletAuthManager(network_name='zoidberg-testnet', environment='development')
    challenge = auth.issue_submission_challenge(wallet_address=owner.address,
        content_hash=content.content_hash, content_id=content.content_id, caption='', technical_validation=tech)
    submission = blockchain.submit_signed_content_operation(wallet_address=owner.address,
        message=challenge['message'], signature=sign(challenge['message'].encode(), 1),
        content_hash=content.content_hash, content_id=content.content_id, text_content=raw.decode(), auth_manager=auth)
    valid, signed, resolver = application_admission(raw, submission_id=submission.submission_id,
        reference_hash=blockchain.chain[0].hash)
    blockchain.get_reviewer_status_at_reference = resolver
    blockchain.votes.extend(signed['votes'])
    blockchain.evaluate_submission_operation(submission.submission_id)
    app = blockchain.validate_current_admission(submission)
    before = [b.hash for b in blockchain.chain]
    with IsolatedDecoder() as decoder:
        adapter = AdmissionAdapter(TestOnlyConfig(CTX, True), AdmissionDependencies(resolver,
            lambda h: any(b.content_hash == h for b in blockchain.chain)), decoder=decoder)
        prepared = adapter.prepare(valid, app)
        bridge = BlockConstructionBridge(adapter)
        assert isinstance(bridge.construct(prepared, header=header_for()), IncompleteConstruction)
        cert = v2_certificate(app)
        candidate = bridge.construct(prepared, header=header_for(), certificate=cert,
            state=state_for(cert), native_transactions=[])
        assert block.parse_record(candidate.canonical_record, CTX)['envelope']['payload']['submission_id'] == submission.submission_id
    assert [b.hash for b in blockchain.chain] == before


@pytest.mark.parametrize('dependency', ['claim', 'application_reviewer', 'v2_reviewer'])
def test_dependency_outage_stays_local(dependency, harness):
    adapter, valid, app = harness
    def unavailable(*args):
        raise OSError('local test dependency unavailable')
    if dependency == 'claim':
        adapter.dependencies = replace(adapter.dependencies, original_claimed=unavailable)
    elif dependency == 'application_reviewer':
        adapter.dependencies = replace(adapter.dependencies, reviewer_status_resolver=unavailable)
    with pytest.raises(IntegrationError) as exc:
        if dependency != 'v2_reviewer':
            adapter.prepare(valid, app)
        else:
            prepared = adapter.prepare(valid, app)
            cert = v2_certificate(app)
            BlockConstructionBridge(adapter).construct(prepared, header=header_for(), certificate=cert,
                state=replace(state_for(cert), reviewer_status_resolver=unavailable), native_transactions=[])
    assert exc.value.classification == Failure.LOCAL_FAILURE


def test_missing_application_evidence_is_incomplete(harness):
    adapter, valid, app = harness
    with pytest.raises(IntegrationError) as exc:
        adapter.prepare(valid, None)
    assert exc.value.classification == Failure.INCOMPLETE
    adapter.dependencies = replace(adapter.dependencies, reviewer_status_resolver=lambda *a: None)
    with pytest.raises(IntegrationError) as exc:
        adapter.prepare(valid, app)
    assert exc.value.classification == Failure.INCOMPLETE


@pytest.mark.parametrize('tamper', ['hash', 'payload'])
def test_tampered_descriptor_is_invalid_canonical(tamper, monkeypatch, harness):
    adapter, valid, app = harness
    desc = media.descriptor(b'a', b'a', 'text/plain', 'identity')
    desc['original_sha256' if tamper == 'hash' else 'payload'] = '0' * 64 if tamper == 'hash' else 'Yg=='
    # Simulate descriptor corruption at producer/worker boundary, preserving
    # the actual admission checks and the real isolated reconstruction path.
    def corrupted(original, mime, *, decoder):
        return media.ProducedMedia(None, media.reconstruct(desc, decoder=decoder))
    monkeypatch.setattr(media, 'produce', corrupted)
    with pytest.raises(IntegrationError) as exc:
        adapter.prepare(valid, app)
    assert exc.value.classification == Failure.INVALID_CANONICAL


def test_current_image_policy_is_not_relaxed(harness):
    adapter, valid, app = harness
    # Valid PNG with deterministic incompressible pixels, >current 256 KiB cap
    # but below the future v3 2 MiB cap. Existing technical policy still rejects.
    import random
    raw = io.BytesIO()
    Image.frombytes('RGB', (400, 400), random.Random(713).randbytes(480000)).save(raw, format='PNG')
    data = raw.getvalue()
    assert 262144 < len(data) < media.MAX_IMAGE
    fake = technical.ValidatedMedia(data, None, dict(valid.result, detected_mime_type='image/png'))
    with pytest.raises(IntegrationError) as exc:
        adapter.prepare(fake, app)
    assert exc.value.classification == Failure.INVALID_ADMISSION


def test_maximal_text_identity_and_ten_native_records(monkeypatch):
    raw = b'a' * media.MAX_TEXT
    valid, app, resolver = application_admission(raw)
    monkeypatch.setattr(media, '_compress_default', lambda original: None)
    cert = v2_certificate(app)
    selected = []
    for nonce in range(1, 11):
        tx = deepcopy(BASE['native_transactions'][0])
        tx['nonce'] = str(nonce)
        unsigned = {k: tx[k] for k in transactions.PAYLOAD_FIELDS}
        message = transactions.signing_bytes(unsigned, CTX)
        tx.update(signature=sign(message, 1), signed_message=message.decode(),
            signed_message_hash=hashlib.sha256(message).hexdigest(), tx_id=hashlib.sha256(message).hexdigest())
        selected.append(tx)
    state = state_for(cert)
    state = replace(state, balances={selected[0]['from_address']: 10000000, selected[0]['to_address']: 0})
    with IsolatedDecoder() as decoder:
        adapter = AdmissionAdapter(TestOnlyConfig(CTX, True), AdmissionDependencies(resolver, lambda h: False), decoder=decoder)
        prepared = adapter.prepare(valid, app)
        candidate = BlockConstructionBridge(adapter).construct(prepared, header=header_for(), certificate=cert,
            state=state, native_transactions=selected)
        p = block.parse_record(candidate.canonical_record, CTX)['envelope']['payload']
        assert p['media']['codec_id'] == 'identity' and len(p['native_transactions']) == 10
        assert media.reconstruct(p['media'], decoder=decoder).original == raw
        assert candidate.sizes.complete <= candidate.identity_reservation == 612121


def test_preserves_accepted_text_bytes_after_application_normalization():
    valid, app, resolver = application_admission(b'  accepted text\r\nline  ')
    assert valid.raw_media_bytes == b'accepted text\nline'
    with IsolatedDecoder() as decoder:
        adapter = AdmissionAdapter(TestOnlyConfig(CTX, True), AdmissionDependencies(resolver, lambda h: False), decoder=decoder)
        prepared = adapter.prepare(valid, app)
        assert prepared.original == valid.raw_media_bytes
        assert prepared.descriptor['original_sha256'] == hashlib.sha256(valid.raw_media_bytes).hexdigest()


class ControlledFailureDecoder(IsolatedDecoder):
    """Existing malicious-worker test fixture, still launched/reaped by the real coordinator."""
    def __init__(self, mode):
        super().__init__(limits=Limits(wall_seconds=0.2))
        self.mode = mode

    def _command(self):
        helper = Path(__file__).parent / 'helpers/decoder_worker_fixture.py'
        if self.mode == 'unavailable':
            return [str(helper.parent / 'nonexistent-decoder-executable')]
        site = Path(sys.prefix) / ('Lib/site-packages' if sys.platform == 'win32'
                                  else f'lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages')
        return [sys._base_executable, '-I', '-u', str(helper), str(site), self.mode]


@pytest.mark.parametrize('mode', ['unavailable', 'crash', 'hang'])
def test_real_codec_process_failures_reach_adapter_as_local(mode):
    valid, app, resolver = application_admission()
    with ControlledFailureDecoder(mode) as decoder:
        adapter = AdmissionAdapter(TestOnlyConfig(CTX, True), AdmissionDependencies(resolver, lambda h: False), decoder=decoder)
        with pytest.raises(IntegrationError) as exc:
            adapter.prepare(valid, app)
        assert exc.value.classification == Failure.LOCAL_FAILURE
        assert exc.value.outcome.original is None
        if mode != 'unavailable':
            assert exc.value.outcome.metrics['reaped'] is True
            assert exc.value.outcome.metrics['exit_code'] is not None
        if mode == 'hang':
            assert exc.value.outcome.reason == 'timeout'
