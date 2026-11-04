"""Offline issuance with fresh fixture signatures; no production identities/keys."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile

import pytest

from canonical_v3 import block, evidence, media, transactions
from canonical_v3.admission import AdmissionAdapter, AdmissionDependencies, Failure, IntegrationError, TestOnlyConfig
from canonical_v3.construction import BlockConstructionBridge, CandidateRecord, IncompleteConstruction
from canonical_v3.issuance import (
    EvidenceIssuer, IncompleteEvidence, IssuanceDependencies, ReviewerDecision, VerifiedCertificate,
)
from canonical_v3.primitives import MAX_RECORD, V3Error, canonical, digest, parse
from codec_prototype.isolated_decoder import IsolatedDecoder
from test_milestone_7_task_7_13_admission import (
    BASE, CTX, account, application_admission, header_for, sign, state_for, v2_certificate,
)

FIXTURES = Path(__file__).parent / 'fixtures/milestone_7_v2_issuance_v1'


def issuer_for(adapter, certificate):
    selected = canonical(certificate['votes'])
    decisions = {(v['dimension'], v['voter_wallet_address'], v['reviewer_status_effective_height'],
                  v['reviewer_status_reference_block_hash']): ReviewerDecision(v['reviewer_status'], True)
                 for v in certificate['votes']}

    def snapshot(ctx, submission, original):
        if ctx != CTX or submission != certificate['submission_id'] or original != certificate['content_hash']:
            return None
        return selected

    def decision(ctx, vote):
        if ctx != CTX:
            return None
        return decisions.get((vote['dimension'], vote['voter_wallet_address'],
            vote['reviewer_status_effective_height'], vote['reviewer_status_reference_block_hash']))
    return EvidenceIssuer(adapter, IssuanceDependencies(snapshot, decision))


def issue(issuer, prepared, certificate):
    return issuer.issue(prepared, attestation=certificate['attestation'], votes=certificate['votes'])


def resign(vote):
    number = next(n for n in range(2, 9) if account(n).address.lower() == vote['voter_wallet_address'])
    payload = evidence.vote_payload(vote, CTX)
    message = canonical(payload)
    signature = sign(message, number)
    vote.update(vote_signature=signature, vote_message=message.decode(), signed_message_hash=digest(payload),
                vote_identity=digest(dict(payload=payload, signature=signature)))


@pytest.fixture(scope='module')
def source(tmp_path_factory):
    patch = pytest.MonkeyPatch()
    patch.setattr(tempfile, 'tempdir', str(tmp_path_factory.mktemp('task714-workers')))
    valid, app, resolver = application_admission()
    with IsolatedDecoder() as decoder:
        adapter = AdmissionAdapter(TestOnlyConfig(CTX, True), AdmissionDependencies(resolver, lambda h: False), decoder=decoder)
        prepared = adapter.prepare(valid, app)
        yield adapter, prepared
    patch.undo()


def test_golden_certificate_and_independent_preimages(source):
    adapter, prepared = source
    cert = deepcopy(BASE['admission_certificate'])
    issuer = issuer_for(adapter, cert)
    result = issue(issuer, prepared, cert)
    assert type(result) is VerifiedCertificate
    assert result.certificate_bytes == canonical(cert)
    assert result.originality_ratio == {'numerator': 5, 'denominator': 7}
    golden = json.loads((FIXTURES / 'manifest.json').read_bytes())
    assert hashlib.sha256((FIXTURES / golden['source']).read_bytes()).hexdigest() == golden['source_sha256']
    # Independent standard-library serialization/hash; no issuer serializer oracle.
    j = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    assert hashlib.sha256(result.certificate_bytes).hexdigest() == golden['certificate_sha256']
    assert len(result.certificate_bytes) == golden['certificate_bytes']
    body = {k: v for k, v in cert.items() if k != 'certificate_digest'}
    assert hashlib.sha256(j(body)).hexdigest() == cert['certificate_digest'] == golden['certificate_digest']
    assert hashlib.sha256(j(cert['technical_evidence'])).hexdigest() == golden['technical_sha256']
    technical = cert['technical_evidence']
    assert hashlib.sha256(j({k: v for k, v in technical.items() if k != 'evidence_digest'})).hexdigest() == technical['evidence_digest']
    attestation = cert['attestation']
    message = j(dict(domain='zoidbergchain/submitter-attestation/v2', network_id=CTX.network_id,
        object_type='submitter-attestation', payload=attestation['canonical_payload'],
        protocol='zoidbergchain', protocol_version=2))
    assert message == attestation['canonical_message'].encode()
    assert hashlib.sha256(message).hexdigest() == attestation['canonical_payload_digest'] == attestation['canonical_message_hash']
    assert issuer.verify(prepared, result.certificate_bytes) == result
    for dimension in evidence.POSITIVE:
        votes = sorted((v for v in cert['votes'] if v['dimension'] == dimension), key=lambda v: v['voter_wallet_address'])
        projection = [dict(wallet=v['voter_wallet_address'], choice=v['vote_type'], identity=v['vote_identity'],
                           status=v['reviewer_status']) for v in votes]
        assert hashlib.sha256(j(projection)).hexdigest() == cert[dimension]['vote_set_digest']
    # Separate OpenSSL ECDSA verification of manual EIP-191 Keccak preimages.
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, utils
    from eth_utils import keccak
    signed = [(cert['attestation']['canonical_message'].encode(), cert['attestation']['signature'], 1)]
    for vote in cert['votes']:
        number = next(n for n in range(2, 9) if account(n).address.lower() == vote['voter_wallet_address'])
        signed.append((vote['vote_message'].encode(), vote['vote_signature'], number))
    assert len(signed) == len(golden['signing_digests'])
    for (message, signature, number), expected in zip(signed, golden['signing_digests']):
        signing_digest = keccak(b'\x19Ethereum Signed Message:\n' + str(len(message)).encode('ascii') + message)
        assert signing_digest.hex() == expected
        raw = bytes.fromhex(signature[2:])
        public = ec.derive_private_key(int.from_bytes(account(number).key), ec.SECP256K1()).public_key()
        public.verify(utils.encode_dss_signature(int.from_bytes(raw[:32]), int.from_bytes(raw[32:64])),
                      signing_digest, ec.ECDSA(utils.Prehashed(hashes.SHA256())))


def test_input_order_determinism_and_detached_results(source):
    adapter, prepared = source
    cert = deepcopy(BASE['admission_certificate'])
    issuer = issuer_for(adapter, cert)
    first = issue(issuer, prepared, cert)
    cert['votes'].reverse()
    second = issue(issuer, prepared, cert)
    assert first == second
    detached = first.certificate
    detached['votes'].clear()
    assert first.certificate['votes']


def test_assemble_closed_evidence_from_real_signed_inputs(source):
    adapter, prepared = source
    cert = deepcopy(BASE['admission_certificate'])
    issuer = issuer_for(adapter, cert)
    attestation = issuer.attestation_from_signature(prepared,
        payload=cert['attestation']['canonical_payload'], signature=cert['attestation']['signature'])
    votes = [issuer.vote_from_signature(prepared, message=v['vote_message'].encode(), signature=v['vote_signature'],
        reviewer_status=v['reviewer_status'], reference_height=v['reviewer_status_effective_height'],
        reference_hash=v['reviewer_status_reference_block_hash']) for v in cert['votes']]
    assert attestation == cert['attestation'] and votes == cert['votes']
    result = issuer.issue(prepared, attestation=attestation, votes=votes)
    assert result.certificate_bytes == canonical(cert)


@pytest.mark.parametrize('case', ['legacy', 'extra-key', 'signature', 'wrong-dimension', 'missing-key', 'oversize'])
def test_vote_assembly_cannot_upgrade_or_repair_invalid_signed_bytes(source, case):
    adapter, prepared = source
    cert = deepcopy(BASE['admission_certificate'])
    issuer = issuer_for(adapter, cert)
    vote = cert['votes'][0]
    payload = parse(vote['vote_message'].encode())
    signature = vote['vote_signature']
    if case == 'legacy':
        message = prepared.certificate['votes'][0]['vote_message'].encode()
        signature = prepared.certificate['votes'][0]['vote_signature']
    else:
        if case == 'extra-key':
            payload['protocol_version'] = 2
        elif case == 'signature':
            signature = '0x' + '01' + signature[4:]
        elif case == 'wrong-dimension':
            payload['dimension'] = 'originality'
        elif case == 'missing-key':
            del payload['nonce']
        elif case == 'oversize':
            payload['nonce'] = 'a' * 2049
        message = canonical(payload)
    with pytest.raises(IntegrationError) as exc:
        issuer.vote_from_signature(prepared, message=message, signature=signature,
            reviewer_status=vote['reviewer_status'], reference_height=vote['reviewer_status_effective_height'],
            reference_hash=vote['reviewer_status_reference_block_hash'])
    assert exc.value.classification == Failure.INVALID_CANONICAL


@pytest.mark.parametrize('dimension', ['originality', 'admissibility'])
@pytest.mark.parametrize('case', ['quorum', 'established', 'all-unsure', 'zero'])
def test_independent_incomplete_reviews(source, dimension, case):
    adapter, prepared = source
    cert = deepcopy(BASE['admission_certificate'])
    if case in ('quorum', 'zero'):
        selected = [v for v in cert['votes'] if v['dimension'] == dimension]
        cert['votes'] = [v for v in cert['votes'] if v['dimension'] != dimension] + selected[:(4 if case == 'quorum' else 0)]
    else:
        for vote in cert['votes']:
            if vote['dimension'] == dimension:
                if case == 'established':
                    vote['reviewer_status'] = 'PROBATIONARY_REVIEWER'
                else:
                    vote['vote_type'] = 'unsure'
                    resign(vote)
    cert['votes'].sort(key=lambda v: (v['dimension'], v['voter_wallet_address'], v['vote_identity']))
    issuer = issuer_for(adapter, cert)
    result = issue(issuer, prepared, cert)
    assert type(result) is IncompleteEvidence
    assert result.missing == (dimension + '_review',) and result.certificate_bytes is None


def test_unsure_counts_in_quorum_but_not_denominator(source):
    adapter, prepared = source
    cert = deepcopy(BASE['admission_certificate'])
    for dimension in evidence.POSITIVE:
        selected = [v for v in cert['votes'] if v['dimension'] == dimension][:5]
        for index, vote in enumerate(selected):
            vote['vote_type'] = evidence.POSITIVE[dimension] if index < 2 else 'unsure'
            resign(vote)
        cert['votes'] = [v for v in cert['votes'] if v['dimension'] != dimension] + selected
    cert['votes'].sort(key=lambda v: (v['dimension'], v['voter_wallet_address'], v['vote_identity']))
    result = issue(issuer_for(adapter, cert), prepared, cert)
    assert result.originality_ratio == {'numerator': 1, 'denominator': 1}
    for dimension in evidence.POSITIVE:
        tally = result.certificate[dimension]
        assert tally['eligible_valid_votes'] == 5 and tally['unsure_votes'] == 3
        assert tally['approval_denominator'] == 2 and tally['quorum_reached'] is True


@pytest.mark.parametrize('case', ['duplicate', 'contradictory', 'dimension', 'hash', 'submission', 'signature',
    'attestation-signature', 'network', 'protocol', 'nonce', 'malformed', 'oversize', 'legacy-vote', 'legacy-attestation'])
def test_invalid_sources_rejected(source, case):
    adapter, prepared = source
    cert = deepcopy(BASE['admission_certificate'])
    issuer = issuer_for(adapter, cert)
    vote = cert['votes'][0]
    if case in ('duplicate', 'contradictory'):
        other = deepcopy(vote)
        if case == 'contradictory':
            other['vote_type'] = 'not_admissible'
            resign(other)
        cert['votes'].append(other)
    elif case == 'dimension':
        vote['dimension'] = 'originality'
    elif case == 'hash':
        vote['content_hash'] = 'e' * 64
        resign(vote)
    elif case == 'submission':
        vote['submission_id'] = 'e' * 32
        resign(vote)
    elif case == 'signature':
        vote['vote_signature'] = '0x' + '01' + vote['vote_signature'][4:]
        vote['vote_identity'] = digest(dict(payload=evidence.vote_payload(vote, CTX), signature=vote['vote_signature']))
    elif case == 'attestation-signature':
        cert['attestation']['signature'] = '0x' + '01' + cert['attestation']['signature'][4:]
    elif case == 'network':
        vote['network_id'] = 'other-test-network'
    elif case == 'protocol':
        vote['protocol_version'] = 1
    elif case == 'nonce':
        vote['vote_nonce'] = 'changed-nonce'
    elif case == 'malformed':
        vote['reviewer_eligible'] = 1
    elif case == 'oversize':
        vote['vote_message'] = 'a' * 4097
    elif case == 'legacy-vote':
        cert['votes'][0] = deepcopy(prepared.certificate['votes'][0])
    else:
        cert['attestation'] = prepared.certificate['attestation']
    with pytest.raises(IntegrationError) as exc:
        issue(issuer, prepared, cert)
    assert exc.value.classification == Failure.INVALID_CANONICAL


@pytest.mark.parametrize('case', ['missing-vote', 'status', 'ineligible', 'negative', 'self-vote'])
def test_frozen_selection_and_authority_cannot_be_forged(source, case):
    adapter, prepared = source
    cert = deepcopy(BASE['admission_certificate'])
    issuer = issuer_for(adapter, cert)
    if case == 'missing-vote':
        cert['votes'].pop()  # Remaining set still qualifies; favorable omission must fail.
    elif case == 'status':
        cert['votes'][1]['reviewer_status'] = 'ESTABLISHED_REVIEWER'
        issuer.dependencies = replace(issuer.dependencies, frozen_votes=lambda *a: canonical(cert['votes']))
    elif case == 'ineligible':
        issuer.dependencies = replace(issuer.dependencies,
            reviewer_decision=lambda ctx, v: ReviewerDecision(v['reviewer_status'], False))
    elif case == 'negative':
        for vote in cert['votes']:
            if vote['dimension'] == 'admissibility':
                vote['vote_type'] = 'not_admissible'
                resign(vote)
        issuer = issuer_for(adapter, cert)
    else:
        vote = cert['votes'][0]
        vote['voter'] = vote['voter_wallet_address'] = cert['creator_wallet']
        payload = evidence.vote_payload(vote, CTX)
        signature = sign(canonical(payload), 1)
        vote.update(vote_signature=signature, vote_message=canonical(payload).decode(),
                    signed_message_hash=digest(payload), vote_identity=digest(dict(payload=payload, signature=signature)))
    with pytest.raises(IntegrationError) as exc:
        issue(issuer, prepared, cert)
    assert exc.value.classification == Failure.INVALID_CANONICAL


@pytest.mark.parametrize('case', ['order', 'tally', 'digest', 'legacy', 'whitespace', 'duplicate-key', 'oversize', 'ratio-field'])
def test_certificate_verification_is_strict(source, case):
    adapter, prepared = source
    cert = deepcopy(BASE['admission_certificate'])
    issuer = issuer_for(adapter, cert)
    if case == 'order':
        cert['votes'].reverse()
    elif case == 'tally':
        cert['originality']['positive_votes'] = 6
    elif case == 'digest':
        cert['certificate_digest'] = 'e' * 64
    elif case == 'legacy':
        cert = prepared.certificate
    elif case == 'ratio-field':
        cert['originality']['ratio'] = {'numerator': 10, 'denominator': 14}
    if case in ('order', 'tally', 'ratio-field'):
        cert.pop('certificate_digest')
        cert['certificate_digest'] = digest(cert)
    raw = canonical(cert)
    if case == 'whitespace':
        raw += b'\n'
    elif case == 'duplicate-key':
        raw = b'{"certificate_version":2,' + raw[1:]
    elif case == 'oversize':
        raw = b' ' * 196609
    with pytest.raises(IntegrationError) as exc:
        issuer.verify(prepared, raw)
    assert exc.value.classification == Failure.INVALID_CANONICAL


@pytest.mark.parametrize('dependency', ['frozen_votes', 'reviewer_decision'])
@pytest.mark.parametrize('behavior', ['missing', 'raises', 'bad-contract'])
def test_missing_and_operational_authority_are_distinct(source, dependency, behavior):
    adapter, prepared = source
    cert = deepcopy(BASE['admission_certificate'])
    issuer = issuer_for(adapter, cert)
    def lookup(*args):
        if behavior == 'raises':
            raise OSError('fixture lookup unavailable')
        return None if behavior == 'missing' else False
    issuer.dependencies = replace(issuer.dependencies, **{dependency: lookup})
    if behavior == 'missing':
        for result in (issue(issuer, prepared, cert), issuer.verify(prepared, canonical(cert))):
            assert type(result) is IncompleteEvidence
    else:
        for operation in (lambda: issue(issuer, prepared, cert), lambda: issuer.verify(prepared, canonical(cert))):
            with pytest.raises(IntegrationError) as exc:
                operation()
            assert exc.value.classification == Failure.LOCAL_FAILURE


def test_missing_inputs_are_not_null_or_legacy_substitution(source):
    adapter, prepared = source
    cert = deepcopy(BASE['admission_certificate'])
    issuer = issuer_for(adapter, cert)
    assert issuer.issue(prepared).missing == ('v2_attestation', 'v2_votes')
    assert issuer.issue(prepared, attestation=cert['attestation']).missing == ('v2_votes',)
    with pytest.raises(IntegrationError):
        issuer.issue(prepared, attestation=None)
    bad = deepcopy(cert['votes'])
    bad[0]['content_hash'] = 'e' * 64
    resign(bad[0])
    with pytest.raises(IntegrationError):
        issuer.issue(prepared, votes=bad)  # Missing attestation cannot mask a wrong binding.
    assert BlockConstructionBridge(adapter).construct_issued(prepared, issuer=issuer, header=header_for()).classification == Failure.INCOMPLETE


def test_issued_bridge_and_context_reverification(source):
    adapter, prepared = source
    cert = deepcopy(BASE['admission_certificate'])
    issuer = issuer_for(adapter, cert)
    issued = issue(issuer, prepared, cert)
    bridge = BlockConstructionBridge(adapter)
    args = dict(issuer=issuer, issued=issued, header=header_for(), state=state_for(cert), native_transactions=[])
    candidate = bridge.construct_issued(prepared, **args)
    assert type(candidate) is CandidateRecord and not candidate.finalized
    payload = block.parse_record(candidate.canonical_record, CTX)['envelope']['payload']
    assert payload['admission_certificate'] == cert
    assert payload['media']['original_sha256'] == hashlib.sha256(prepared.original).hexdigest()
    for changes in (dict(genesis_hash='e' * 64), dict(network_id='other-test-network')):
        with pytest.raises(IntegrationError, match='issued_evidence_context'):
            bridge.construct_issued(prepared, **dict(args, issued=replace(issued, context=replace(CTX, **changes))))
    forged = replace(issued, certificate_bytes=canonical(prepared.certificate))
    with pytest.raises(IntegrationError):
        bridge.construct_issued(prepared, **dict(args, issued=forged))
    issuer.dependencies = replace(issuer.dependencies, reviewer_decision=lambda *a: None)
    incomplete = bridge.construct_issued(prepared, **args)
    assert type(incomplete) is IncompleteConstruction and incomplete.canonical_record is None


def test_issued_bridge_byte_budget_and_optional_selection(source, monkeypatch):
    adapter, prepared = source
    cert = deepcopy(BASE['admission_certificate'])
    issuer = issuer_for(adapter, cert)
    issued = issue(issuer, prepared, cert)
    bridge = BlockConstructionBridge(adapter)
    args = dict(issuer=issuer, issued=issued, header=header_for(), state=state_for(cert))
    candidate = bridge.construct_issued(prepared, native_transactions=[], **args)
    size = len(candidate.canonical_record)
    assert candidate.sizes.certificate == len(issued.certificate_bytes) <= 196608
    assert size <= candidate.identity_reservation < MAX_RECORD
    for cap in (size + 1, size):
        monkeypatch.setattr(block, 'MAX_RECORD', cap)
        assert bridge.construct_issued(prepared, native_transactions=[], **args).sizes.complete == size
    monkeypatch.setattr(block, 'MAX_RECORD', size - 1)
    with pytest.raises(IntegrationError, match='block_size'):
        bridge.construct_issued(prepared, native_transactions=[], **args)
    monkeypatch.setattr(block, 'MAX_RECORD', MAX_RECORD)
    with pytest.raises(IntegrationError):
        bridge.construct_issued(prepared, native_transactions=BASE['native_transactions'] * 11, **args)
    assert bridge.construct_issued(prepared, native_transactions=[], **args) == candidate


def test_same_certification_across_identity_and_zstd(monkeypatch, tmp_path):
    monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path))
    valid, app, resolver = application_admission(b'a' * 10000)
    cert = v2_certificate(app)  # Only fixture code collects fresh test signatures.
    candidates = []
    with IsolatedDecoder() as decoder:
        for identity in (False, True):
            if identity:
                monkeypatch.setattr(media, '_compress_default', lambda raw: None)
            adapter = AdmissionAdapter(TestOnlyConfig(CTX, True), AdmissionDependencies(resolver, lambda h: False), decoder=decoder)
            prepared = adapter.prepare(valid, app)
            issuer = issuer_for(adapter, cert)
            issued = issue(issuer, prepared, cert)
            assert issued.certificate_bytes == canonical(cert)
            candidate = BlockConstructionBridge(adapter).construct_issued(prepared, issuer=issuer, issued=issued,
                header=header_for(), state=state_for(cert), native_transactions=[])
            record = block.parse_record(candidate.canonical_record, CTX)
            payload = record['envelope']['payload']
            assert payload['media']['codec_id'] == ('identity' if identity else 'zstd')
            assert media.reconstruct(payload['media'], decoder=decoder).original == valid.raw_media_bytes
            assert payload['media']['original_sha256'] == app['content_hash']
            candidates.append(record)
    assert candidates[0]['hash'] != candidates[1]['hash']
    assert candidates[0]['envelope']['payload']['certificate_id'] == candidates[1]['envelope']['payload']['certificate_id']


@pytest.mark.parametrize('ratio', [dict(numerator=10, denominator=14), dict(numerator=4, denominator=7),
                                   dict(numerator=True, denominator=1)])
def test_incorrect_or_noncanonical_block_summaries_reject(ratio):
    payload = deepcopy(BASE)
    payload['approval_percentage'] = ratio
    with pytest.raises(V3Error):
        block.encode_record(payload, CTX)


def test_max_text_and_ten_transactions_preserve_issued_evidence(monkeypatch, tmp_path):
    monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path))
    raw = b'a' * media.MAX_TEXT
    valid, app, resolver = application_admission(raw)
    monkeypatch.setattr(media, '_compress_default', lambda original: None)
    cert = v2_certificate(app)
    selected = []
    for nonce in range(1, 11):
        tx = deepcopy(BASE['native_transactions'][0])
        tx['nonce'] = str(nonce)
        message = transactions.signing_bytes({k: tx[k] for k in transactions.PAYLOAD_FIELDS}, CTX)
        tx.update(signature=sign(message, 1), signed_message=message.decode(),
                  signed_message_hash=hashlib.sha256(message).hexdigest(), tx_id=hashlib.sha256(message).hexdigest())
        selected.append(tx)
    state = replace(state_for(cert), balances={selected[0]['from_address']: 10000000, selected[0]['to_address']: 0})
    with IsolatedDecoder() as decoder:
        adapter = AdmissionAdapter(TestOnlyConfig(CTX, True), AdmissionDependencies(resolver, lambda h: False), decoder=decoder)
        prepared = adapter.prepare(valid, app)
        issuer = issuer_for(adapter, cert)
        issued = issue(issuer, prepared, cert)
        candidate = BlockConstructionBridge(adapter).construct_issued(prepared, issuer=issuer, issued=issued,
            header=header_for(), state=state, native_transactions=selected)
        payload = block.parse_record(candidate.canonical_record, CTX)['envelope']['payload']
        assert payload['media']['codec_id'] == 'identity' and len(payload['native_transactions']) == 10
        assert media.reconstruct(payload['media'], decoder=decoder).original == raw
        assert canonical(payload['admission_certificate']) == issued.certificate_bytes
        assert candidate.sizes.complete <= candidate.identity_reservation == 612121


def test_test_only_and_nonactivation():
    with pytest.raises(V3Error):
        EvidenceIssuer(None, IssuanceDependencies(lambda *a: None, lambda *a: None))
    root = Path(__file__).resolve().parents[1]
    for path in [root / 'blockchain.py', root / 'block.py', root / 'storage.py', root / 'peer_sync.py',
                 *list((root / 'api_routers').glob('*.py')), *list((root / 'services').glob('*.py'))]:
        assert 'canonical_v3' not in path.read_text(encoding='utf-8'), path
