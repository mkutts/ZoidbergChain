"""Inert format/crypto/worker tests. No live chain, DB, keys or policy activation."""
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
import hashlib
import json
from pathlib import Path

import pytest

from canonical_v3 import block, evidence, finality, media, transactions
from canonical_v3.primitives import (
    Context, CURVE_ORDER, MAX_RECORD, MAX_UINT, V3Error, canonical, compare_ratios,
    decimal_units, digest, envelope, parse, rational, seconds, signature, time_utc,
    validate_rational, verify_signature,
)
from codec_prototype.isolated_decoder import IsolatedDecoder, Outcome, Status

FIXTURES = Path(__file__).parent / 'fixtures/milestone_7_v3_v1'
MANIFEST = json.loads((FIXTURES / 'manifest.json').read_bytes())
CTX = Context(**MANIFEST['context'])


def fixture(name):
    return json.loads((FIXTURES / (name + '.json')).read_bytes())


def payload():
    return fixture('block-identity')['envelope']['payload']


def test_frozen_inventory_and_published_oracles():
    assert hashlib.sha256((FIXTURES / 'manifest.json').read_bytes()).hexdigest() == 'cbef5b6d267331cbf8ab62ff75f8ee47a9ab6f10a017bedd7df6ec2169282595'
    assert len(MANIFEST['vectors']) == 65
    assert len({v['id'] for v in MANIFEST['vectors']}) == 65
    for v in MANIFEST['vectors']:
        raw = (FIXTURES / v['file']).read_bytes()
        assert len(raw) == v['bytes']
        assert hashlib.sha256(raw).hexdigest() == v['sha256']
    assert fixture('native')['tx_id'] == 'e68931c52c88865a0ad5f73edee11b36d57887c1f953898ab0f052d86ac4f425'
    assert transactions.aggregate_hash([fixture('native')], CTX) == 'c49dfa7b2ff2ac4c42d799a02589da551d12dc0c89588d019cba6c3f0ea5b70a'
    assert digest(fixture('identity')) == '7ee377e5bb1c7aa281895f2452de3f8c2e628e15140d7eed0c11fc15e08640ea'
    assert digest(dict(numerator=5, denominator=7)) == 'dc8dc4b48ae383b7b5077c7a78b3de8822afc8e16b675d35e9a98accb9b9f678'


def dispatch(vector, raw):
    kind = vector['kind']
    if kind == 'record':
        return block.parse_record(raw, CTX)
    if kind == 'reconstruction':
        result = media.reconstruct(parse(raw))
        assert result.status == Status(vector['expected'].upper())
        return result
    if kind == 'aggregate':
        # A is a computed preimage, never accepted as alternate wire J.
        value = json.loads(raw)
        assert transactions.aggregate_bytes(value, CTX) == raw
        return value
    value = parse(raw)
    if kind == 'descriptor':
        media.validate_descriptor(value)
    elif kind == 'transaction':
        transactions.validate_transaction(value, CTX)
    elif kind == 'ratio':
        validate_rational(value)
    elif kind == 'finality':
        finality.validate_attestation(value, CTX)
    elif kind == 'proof':
        finality.validate_proof(value, CTX, trusted_validators=tuple(value['validator_set']),
            equivocators=frozenset(), block_height=1, block_hash=fixture('block-identity')['hash'])
    elif kind == 'tally-case':
        result = evidence.derive_tally(value['votes'], 'originality', CTX)
        assert result == value['tally']
        if value['ratio'] is None:
            assert result['approval_denominator'] == 0 and result['resolved'] is False
            with pytest.raises(V3Error, match='undefined_ratio'):
                rational(result['positive_votes'], result['approval_denominator'])
        else:
            assert rational(result['positive_votes'], result['approval_denominator']) == value['ratio']
    else:
        assert kind in ('json', 'preimage')
    return value


@pytest.mark.parametrize('vector', MANIFEST['vectors'], ids=lambda v: v['id'])
def test_versioned_golden_vectors(vector):
    raw = (FIXTURES / vector['file']).read_bytes()
    if vector['expected'] == 'invalid' and vector['kind'] != 'reconstruction':
        with pytest.raises(V3Error):
            dispatch(vector, raw)
    else:
        dispatch(vector, raw)


def test_encodings_commit_differently_and_reconstruct_without_encoder(monkeypatch):
    import zstandard
    monkeypatch.setattr(zstandard, 'ZstdCompressor', lambda **_: pytest.fail('validator recompressed'))
    records = []
    with IsolatedDecoder() as decoder:
        for name in ('block-identity', 'block-zstd'):
            raw = (FIXTURES / (name + '.json')).read_bytes()
            record = block.parse_record(raw, CTX)
            assert block.encode_record(record['envelope']['payload'], CTX) == raw
            outcome = block.reconstruct_record_media(raw, CTX, decoder=decoder)
            assert outcome.status == Status.VALID and outcome.original == b'a'
            records.append(record)
    assert records[0]['hash'] == '03e27961c4dd9571fc9766a4f490ebb93f46e440c7af82773bf9d1705d93617f'
    assert records[1]['hash'] == '6512498086d35b49d1da6fa1e5e4b28b0ecea24f9f7118332ec60cc0f4249bc9'
    assert records[0]['hash'] != records[1]['hash']
    assert records[0]['envelope']['payload']['media']['original_sha256'] == records[1]['envelope']['payload']['media']['original_sha256']


def test_producer_uses_full_descriptor_size_and_default_profile():
    with IsolatedDecoder() as decoder:
        small = media.produce(b'a', 'text/plain', decoder=decoder)
        large = media.produce(b'a' * 10000, 'text/plain', decoder=decoder)
        assert small.outcome.status == large.outcome.status == Status.VALID
        assert small.descriptor == fixture('identity')
        assert large.descriptor['codec_id'] == 'zstd'
        assert large.outcome.original == b'a' * 10000
        identity = media.descriptor(b'a' * 10000, b'a' * 10000, 'text/plain', 'identity')
        assert len(canonical(large.descriptor)) < len(canonical(identity))
        assert large.descriptor['original_sha256'] == identity['original_sha256']


@pytest.mark.parametrize('reason', ['timeout', 'oom', 'crash', 'cancelled', 'saturated', 'cleanup_failure', 'unsupported_platform'])
def test_local_failure_propagates_and_producer_withholds_descriptor(monkeypatch, reason):
    with IsolatedDecoder() as decoder:
        failure = Outcome(Status.INDETERMINATE_LOCAL_FAILURE, reason=reason)
        monkeypatch.setattr(decoder, 'validate', lambda raw: failure)
        assert media.reconstruct(fixture('identity'), decoder=decoder) is failure
        result = media.produce(b'a', 'text/plain', decoder=decoder)
        assert result.outcome is failure and result.descriptor is None


def test_closed_worker_and_no_decoder_injection():
    decoder = IsolatedDecoder()
    decoder.close()
    assert media.reconstruct(fixture('identity'), decoder=decoder).status == Status.INDETERMINATE_LOCAL_FAILURE
    with pytest.raises(V3Error, match='isolated_decoder_required'):
        media.reconstruct(fixture('identity'), decoder=object())


@pytest.mark.parametrize('encoded', [None, b'broken frame'])
def test_producer_falls_back_to_verified_identity_for_encoder_failure(monkeypatch, encoded):
    monkeypatch.setattr(media, '_compress_default', lambda original: encoded)
    result = media.produce(b'a' * 10000, 'text/plain')
    assert result.outcome.status == Status.VALID and result.descriptor['codec_id'] == 'identity'


def test_compressed_producer_local_failure_is_not_masked(monkeypatch):
    calls = []
    with IsolatedDecoder() as decoder:
        def failure(raw):
            calls.append(raw)
            return Outcome(Status.INDETERMINATE_LOCAL_FAILURE, reason='timeout')
        monkeypatch.setattr(decoder, 'validate', failure)
        result = media.produce(b'a' * 10000, 'text/plain', decoder=decoder)
    assert len(calls) == 1 and result.descriptor is None
    assert result.outcome.status == Status.INDETERMINATE_LOCAL_FAILURE


def test_signature_variant_same_id_different_aggregate_and_block_and_duplicate_rejected():
    normal, high = fixture('native'), fixture('native-high-s')
    assert normal['signature'] != high['signature']
    assert normal['tx_id'] == high['tx_id']
    assert transactions.aggregate_hash([normal], CTX) != transactions.aggregate_hash([high], CTX)
    assert fixture('block-identity')['hash'] != fixture('block-high-s')['hash']
    with pytest.raises(V3Error, match='native_duplicate'):
        transactions.validate_transactions([normal, high], CTX)


@pytest.mark.parametrize('changes', [dict(network_id='other-network-v2'), dict(genesis_hash='e' * 64), dict(application='other-app')])
def test_explicit_trusted_context(changes):
    with pytest.raises(V3Error):
        transactions.validate_transaction(fixture('native'), replace(CTX, **changes))


def test_unicode_j_vs_native_a_and_missing_null():
    t = fixture('native-unicode')
    m = transactions.signing_bytes({k: t[k] for k in transactions.PAYLOAD_FIELDS}, CTX)
    assert len(m) == 527 and len(m.decode()) == 526
    a = transactions.aggregate_bytes([t], CTX)
    assert len(a) == 1412 and len(canonical([t])) == 1404
    assert b'\\u00e9' in a and b'\xc3\xa9' in canonical([t])
    assert parse(canonical(t))['memo'] == 'é'
    assert b'"memo":null' in canonical(fixture('native'))
    t = fixture('native'); del t['memo']
    with pytest.raises(V3Error):
        transactions.validate_transaction(t, CTX)
    assert canonical({'x': 'é'}) != canonical({'x': 'e\u0301'})


def test_all_ratio_inputs_and_pairwise_comparisons():
    ratios = [(p, d, rational(p, d)) for d in range(1, 17) for p in range(d + 1)]
    assert len(ratios) == 152
    assert len({canonical(r) for _, _, r in ratios}) == 81
    for p, d, r in ratios:
        validate_rational(r)
        assert Fraction(r['numerator'], r['denominator']) == Fraction(p, d)
        for p2, d2, r2 in ratios:
            expected = (p * d2 > p2 * d) - (p * d2 < p2 * d)
            assert compare_ratios(r, r2) == expected
    assert rational(0, 7) == dict(numerator=0, denominator=1)
    for p, d in ((0, 0), (1, 0), (17, 16), (True, 1), (1, -1), (1.0, 3)):
        with pytest.raises(V3Error):
            rational(p, d)


@pytest.mark.parametrize('value', ['01', '+1', '-0', '1.0', '1e0', 'NaN', 'Infinity', '1.0000001', '', 1, True, 1.0])
def test_decimal_negatives(value):
    with pytest.raises(V3Error):
        decimal_units(value)


def test_decimal_time_and_signature_boundaries():
    assert decimal_units('0.000001', positive=True) == 1
    assert decimal_units('1000000000') == 1000000000000000
    seconds(str(MAX_UINT) + '.999999')
    for value in [str(MAX_UINT + 1), '1.0000000']:
        with pytest.raises(V3Error):
            seconds(value)
    time_utc('0001-01-01T00:00:00+00:00')
    time_utc('9999-12-31T23:59:59.999999+00:00')
    for value in ['2026-02-29T00:00:00+00:00', '2026-01-01T00:00:60+00:00',
                  '2026-01-01T00:00:00Z', '2026-01-01T00:00:00.0+00:00', '2026-01-01T00:00:00.100000+00:00']:
        with pytest.raises(V3Error):
            time_utc(value)
    sig = fixture('native')['signature']
    for raw in [bytes(32) + bytes.fromhex(sig[66:]),
                CURVE_ORDER.to_bytes(32) + bytes.fromhex(sig[66:]),
                bytes.fromhex(sig[2:-2]) + b'\x00']:
        with pytest.raises(V3Error):
            signature('0x' + raw.hex())
    # Scalar-shaped but unrecoverable curve point is a deterministic rejection.
    with pytest.raises(V3Error, match='signature_recovery'):
        verify_signature(b'a', '0x' + (5).to_bytes(32).hex() + (1).to_bytes(32).hex() + '1b', '0x' + '1' * 40)


def test_closed_schemas_all_required_fields_and_unknown_fields():
    p = payload()
    t = fixture('native')
    c = p['admission_certificate']
    cases = [(p, lambda x: block.validate_payload(x, CTX)),
             (t, lambda x: transactions.validate_transaction(x, CTX)),
             (p['media'], media.validate_descriptor),
             (c, lambda x: evidence.validate_certificate(x, CTX)),
             (c['technical_evidence'], lambda x: evidence.validate_technical(x, CTX)),
             (c['attestation'], lambda x: evidence.validate_attestation(x, CTX)),
             (c['attestation']['canonical_payload'], lambda x: evidence.attestation_bytes(x, CTX)),
             (c['votes'][0], lambda x: evidence.validate_vote(x, CTX)),
             (c['originality'], lambda x: evidence.validate_tally(x, c['votes'], 'originality', CTX)),
             (fixture('finality'), lambda x: finality.validate_attestation(x, CTX))]
    for original, validate in cases:
        for key in original:
            bad = deepcopy(original); del bad[key]
            with pytest.raises(V3Error, match='object_keys'):
                validate(bad)
            if original[key] is not None:
                bad = deepcopy(original); bad[key] = None
                with pytest.raises(V3Error):
                    validate(bad)
        bad = dict(original, arbitrary_extension=1)
        with pytest.raises(V3Error, match='object_keys'):
            validate(bad)


def test_typed_booleans_and_vote_snapshot_restrictions():
    c = payload()['admission_certificate']
    for name in ['eligible_valid_votes', 'policy_version', 'approval_threshold_bps']:
        bad = deepcopy(c['originality']); bad[name] = True
        with pytest.raises(V3Error):
            evidence.validate_tally(bad, c['votes'], 'originality', CTX)
    for name in ['quorum_reached', 'resolved']:
        bad = deepcopy(c['originality']); bad[name] = 1
        with pytest.raises(V3Error):
            evidence.validate_tally(bad, c['votes'], 'originality', CTX)
    bad = deepcopy(c['votes']); bad.append(deepcopy(bad[-1]))
    with pytest.raises(V3Error, match='vote_duplicate'):
        evidence.validate_votes(bad, CTX)
    with pytest.raises(V3Error, match='vote_count'):
        evidence.validate_votes(c['votes'] * 3, CTX)


def test_size_formula_complete_limit_and_child_budgets():
    assert evidence.certificate_size_bound() == 172901
    assert block.conservative_size_bound() == 3058797
    assert MAX_RECORD - block.conservative_size_bound() == 86931
    # Byte-gate tests ONLY, not claimed valid padded blocks; tighter schema caps
    # make a valid R exactly at 3 MiB unreachable.
    block.check_complete_size(b' ' * (MAX_RECORD - 1))
    block.check_complete_size(b' ' * MAX_RECORD)
    with pytest.raises(V3Error, match='block_size'):
        block.check_complete_size(b' ' * (MAX_RECORD + 1))
    with pytest.raises(V3Error):
        block.parse_record(b' ' * MAX_RECORD, CTX)
    raw = (FIXTURES / 'block-identity.json').read_bytes()
    rec = block.parse_record(raw, CTX)
    sizes = block.check_budgets(rec, raw)
    assert sizes.complete == 34588 and sizes.base64 == 4
    assert sizes.rest + sizes.native + sizes.certificate + sizes.base64 == len(raw)
    assert len(raw) - len(canonical(rec['envelope'])) == 87
    # Explicit analytic parent-budget probes, not schema/crypto-valid records.
    probe = {'envelope': {'payload': {'media': {'payload': ''}, 'native_transactions': [], 'admission_certificate': 'x' * (196608 - 2)}}}
    probe_raw = canonical(probe)
    assert block.check_budgets(probe, probe_raw).certificate == 196608
    probe['envelope']['payload']['admission_certificate'] += 'x'
    with pytest.raises(V3Error, match='block_component_budget'):
        block.check_budgets(probe, canonical(probe))


def test_portable_canonical_preimages_without_crypto_dependencies():
    # Same frozen J/A and block preimages on Windows and Linux, with no signer
    # recovery dependency; this does not claim full Linux crypto validation.
    checked = 0
    for vector in MANIFEST['vectors']:
        if vector['expected'] != 'valid':
            continue
        raw = (FIXTURES / vector['file']).read_bytes()
        value = json.loads(raw) if vector['kind'] == 'aggregate' else parse(raw)
        assert canonical(value, ascii_only=vector['kind'] == 'aggregate') == raw
        assert hashlib.sha256(raw).hexdigest() == vector['sha256']
        if vector['kind'] == 'record':
            assert hashlib.sha256(canonical(value['envelope'])).hexdigest() == value['hash']
        checked += 1
    assert checked == 23


@pytest.mark.parametrize('mime,cap', [('text/plain', 262144), ('image/png', 2097152)])
def test_original_and_encoded_size_boundaries(mime, cap):
    original = b'a' * cap
    value = media.descriptor(original, original, mime, 'identity')
    assert value['original_size'] == cap
    for key in ('original_size', 'stored_size'):
        bad = dict(value); bad[key] = (cap if key == 'original_size' else 2097152) + 1
        with pytest.raises(V3Error):
            media.validate_descriptor(bad)
    assert len(value['payload']) == 4 * ((cap + 2) // 3)
    if mime == 'image/png':
        assert len(value['payload']) == 2796204 and value['payload'].endswith('=')


def test_text_canonicality_controls_and_no_silent_repair():
    for value in [b' a', b'a ', b'a\r\nb', b'a\rb', b'\xff', b'a\x00b', b'a\xc2\x85b']:
        with pytest.raises(V3Error):
            media.produce(value, 'text/plain')
    for value in [b'a\nb', b'a\tb', 'é e\u0301 😀'.encode()]:
        media.canonical_text(value)
    result = media.reconstruct(media.descriptor(b' a', b' a', 'text/plain', 'identity'))
    assert result.status == Status.INVALID and result.code == 'text_noncanonical'


def test_json_scalar_depth_and_wire_canonicality():
    assert parse(b'[' * 32 + b'0' + b']' * 32)
    for raw in [b'[' * 33 + b'0' + b']' * 33, b'{"x":1,"x":2}', b'{"x":{"y":1,"y":2}}',
                b'{"x":9007199254740992}', b'{"x":-0}', b'{"x":1e0}', b'{"x":Infinity}', b'{"x":"\xff"}', b'{}\n']:
        with pytest.raises(V3Error):
            parse(raw)
    for value in [float('nan'), float('inf'), 1.0, {1: 'value'}, '\ud800', b'binary']:
        with pytest.raises(V3Error):
            canonical(value)
    raw = (FIXTURES / 'block-identity.json').read_bytes()
    duplicate = raw.replace(b'"block_version":3', b'"block_version":3,"block_version":3')
    with pytest.raises(V3Error, match='duplicate_key'):
        block.parse_record(duplicate, CTX)


def test_finality_uses_trusted_external_context_and_cannot_rewrite_record():
    proof = fixture('finality-proof')
    target = fixture('block-identity')['hash']
    validators = tuple(proof['validator_set'])
    original = (FIXTURES / 'block-identity.json').read_bytes()
    kwargs = dict(trusted_validators=validators, equivocators=frozenset(), block_height=1, block_hash=target)
    finality.validate_proof(proof, CTX, **kwargs)
    for changes in [dict(block_hash='e' * 64), dict(equivocators=frozenset(validators)),
                    dict(trusted_validators=('0x' + '2' * 40,))]:
        with pytest.raises(V3Error):
            finality.validate_proof(proof, CTX, **dict(kwargs, **changes))
    bad = deepcopy(proof); bad['attestations'] *= 2
    with pytest.raises(V3Error):
        finality.validate_proof(bad, CTX, **kwargs)
    assert block.encode_record(payload(), CTX) == original


def test_active_runtime_does_not_import_isolated_package():
    root = Path(__file__).resolve().parents[1]
    active = [root / p for p in ['block.py', 'blockchain.py', 'native_transfer.py', 'protocol_v1.py']]
    active += list((root / 'services').glob('*.py'))
    assert all('canonical_v3' not in path.read_text(encoding='utf-8') for path in active)


@pytest.mark.parametrize('path,value,expected_hash', [
    (('network_id',), 'zoidberg-signing-other-v2', 'bb46f35d4d03946220e5427aa800d0947260b06c1093cfeeb405e9bc6711d4e7'),
    (('protocol_version',), 1, '8540d7ac175fdee3667841c07c33c506f7c3e4424e647dc0efdac71a11f9cf0e'),
    (('payload', 'transaction_version'), 1, 'e3642ab311b8e334120c35fd964700c6cf2da30b41a3826313feb331654a2999'),
    (('payload', 'genesis_hash'), 'b' * 64, 'cb35653050fa50bcbb4c7a8ffeaac0479a4cc6caac38b3fa21f88a23549f2a31'),
    (('payload', 'transaction_type'), 'meme_mining_reward', '12d023aed3372fe39a3b0bbcfb68314aa2342c7e57a18a9e88f060d4e849d609'),
    (('domain',), 'zoidbergchain/finality-attestation/v2', '73405126a94a1d6239017af1a5f40019577b0b300ccaa7ea039baced051ef396'),
    (('object_type',), 'finality-attestation', '721dd317f136a21d0ef38655616b8691099e9d625b706e52d2eac11a5e155795'),
])
def test_published_domain_mutation_preimages_reject_signature_replay(path, value, expected_hash):
    m = fixture('native-message')
    target = m
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert digest(m) == expected_hash
    t = fixture('native')
    with pytest.raises(V3Error):
        verify_signature(canonical(m), t['signature'], t['from_address'])


def test_nonce_memo_and_record_count_limits():
    t = fixture('native')
    u = {k: t[k] for k in transactions.PAYLOAD_FIELDS}
    for memo in ['\0' * 280, '😀' * 280]:
        transactions.signing_bytes(dict(u, memo=memo, nonce=str(MAX_UINT)), CTX)
    for changes in [dict(memo='\0' * 281), dict(memo='😀' * 281), dict(memo=''), dict(memo=' a'),
                    dict(nonce='0'), dict(nonce='01'), dict(nonce=str(MAX_UINT + 1)), dict(nonce=1),
                    dict(amount='1000000000.000001'), dict(fee='0.0'), dict(amount=True)]:
        with pytest.raises(V3Error):
            transactions.signing_bytes(dict(u, **changes), CTX)
    with pytest.raises(V3Error, match='native_count'):
        transactions.validate_transactions([t] * 11, CTX)


def _rebind_media(p, original, mime):
    """Fresh test signatures, using only the explicit public fixture scalars.

    Used for format-size probes; does not certify a live snapshot or image.
    """
    from eth_account import Account
    from eth_account.messages import encode_defunct
    keys = {Account.from_key(bytes([n * 17]) * 32).address.lower(): bytes([n * 17]) * 32 for n in range(1, 9)}

    def sign(message, address):
        return '0x' + Account.sign_message(encode_defunct(primitive=message), keys[address]).signature.hex()

    p['media'] = media.descriptor(original, original, mime, 'identity')
    p['content_type'] = 'text' if mime == 'text/plain' else 'image'
    c = p['admission_certificate']
    c['content_hash'] = hashlib.sha256(original).hexdigest()
    tech = c['technical_evidence']
    tech.update(raw_media_sha256=c['content_hash'], raw_media_byte_length=len(original), detected_mime_type=mime)
    if mime == 'image/png':
        tech.update(detected_media_type='png', raw_media_semantics='exact_input_bytes', width_pixels=1,
                    height_pixels=1, frame_count=1, aggregate_decoded_pixels=1)
    tech['evidence_digest'] = digest({k: v for k, v in tech.items() if k != 'evidence_digest'})
    a = c['attestation']; ap = a['canonical_payload']
    ap.update(raw_media_sha256=c['content_hash'], technical_evidence_digest=tech['evidence_digest'])
    am = canonical(envelope(ap, 'submitter-attestation', CTX))
    a.update(canonical_message=am.decode(), canonical_message_hash=hashlib.sha256(am).hexdigest(),
             canonical_payload_digest=hashlib.sha256(am).hexdigest(), signature=sign(am, c['creator_wallet']))
    for v in c['votes']:
        v['content_hash'] = c['content_hash']
        vp = evidence.vote_payload(v, CTX)
        vm = canonical(vp)
        v.update(vote_message=vm.decode(), signed_message_hash=hashlib.sha256(vm).hexdigest(),
                 vote_signature=sign(vm, v['voter_wallet_address']))
        v['vote_identity'] = digest(dict(payload=vp, signature=v['vote_signature']))
    c['votes'].sort(key=lambda v: (v['dimension'], v['voter_wallet_address'], v['vote_identity']))
    for dimension in ('originality', 'admissibility'):
        c[dimension] = evidence.derive_tally(c['votes'], dimension, CTX)
    c['certificate_digest'] = digest({k: v for k, v in c.items() if k != 'certificate_digest'})
    p.update(certificate_id=c['certificate_digest'], vote_hash=c['originality']['vote_set_digest'])
    return p


def test_complete_record_at_max_image_and_caption_size_with_real_signatures():
    import struct
    import zlib

    def chunk(name, content):
        return struct.pack('>I', len(content)) + name + content + struct.pack('>I', zlib.crc32(name + content))

    # A one-pixel PNG plus a private ancillary chunk. Format/codec test only;
    # deliberately no claim of passing the separately blocked image admission.
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(b'\0\0\0\0'))
    png += chunk(b'npAD', b'\0' * (2097152 - len(png) - 24)) + chunk(b'IEND', b'')
    assert len(png) == 2097152
    p = _rebind_media(payload(), png, 'image/png')
    p['meme_text'] = '\0' * 1000
    raw = block.encode_record(p, CTX)
    parsed = block.parse_record(raw, CTX)
    sizes = block.check_budgets(parsed, raw)
    assert sizes.base64 == 2796204 and len(raw) < 3058797
    assert sizes.rest < 7761
    assert block.reconstruct_record_media(raw, CTX).original == png
    p['meme_text'] += '\0'
    with pytest.raises(V3Error, match='string_length'):
        block.encode_record(p, CTX)


def test_complete_record_at_max_text_size():
    original = b'a' * 262144
    p = _rebind_media(payload(), original, 'text/plain')
    raw = block.encode_record(p, CTX)
    assert block.parse_record(raw, CTX)['envelope']['payload']['media']['original_size'] == 262144
    result = block.reconstruct_record_media(raw, CTX)
    assert result.status == Status.VALID and result.original == original


def test_ten_signed_transfers_and_intrinsic_nonce_order():
    from eth_account import Account
    from eth_account.messages import encode_defunct
    records = []
    for number in range(1, 11):
        t = fixture('native')
        t['nonce'] = str(number)
        message = transactions.signing_bytes({k: t[k] for k in transactions.PAYLOAD_FIELDS}, CTX)
        t.update(signed_message=message.decode(), signed_message_hash=hashlib.sha256(message).hexdigest(),
                 tx_id=hashlib.sha256(message).hexdigest(),
                 signature='0x' + Account.sign_message(encode_defunct(primitive=message), b'\x11' * 32).signature.hex())
        records.append(t)
    transactions.validate_transactions(records, CTX)
    p = payload(); p['native_transactions'] = records
    p['transactions_hash'] = transactions.aggregate_hash(records, CTX)
    assert len(block.parse_record(block.encode_record(p, CTX), CTX)['envelope']['payload']['native_transactions']) == 10
    with pytest.raises(V3Error, match='native_order'):
        transactions.validate_transactions(records[::-1], CTX)
    with pytest.raises(V3Error, match='native_nonce_gap'):
        transactions.validate_transactions([records[0], records[2]], CTX)
