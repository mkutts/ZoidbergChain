"""Inactive G2 adversarial tests; no full semantic genesis-valid assertion."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from isolated_g2717m import Outcome, TrustedGenesisPin, verify_bytes, verify_file
from isolated_g2717m.authority_adapter import bind_test_authority
from isolated_g2717m.verifier import GENESIS_LIMIT, PAYLOAD
from isolated_bft717j.wire import identity
from isolated_bft717k.authority import save_cache, load_cache
from isolated_bft717k.outcomes import AuthorityFailure, Outcome as KOutcome
from isolated_bft717k.verifier import verify_quorum
from verification.bft717k.fixtures import certificate
from verification.g2717m.fixtures import ROOT, VECTORS, base, encode, digest, rebind, wide

G = '0b1b932a7d6cfb0fed6cec2019724b0b0bf6ab13b0516e8d60d63ddbfa25ee94'
PIN = TrustedGenesisPin(G, 'task717i-test', 'task717i-test')
RAW = VECTORS['objects']['G2']['preimage'].encode()


def verify(e, pin=PIN):
    return verify_bytes(encode(e), trusted_pin=pin)


def pin_for(e):
    return TrustedGenesisPin(digest(e), e['network_id'], e['payload']['application'])


def assert_incomplete(result):
    assert result.outcome == Outcome.INCOMPLETE_POLICY, result
    assert result.canonical_envelope_verified and result.component_commitments_verified
    assert result.pinned_test_identity_matched and result.incomplete_policies
    assert not result.complete_semantic_genesis_valid and not result.production_consensus_authorized
    with pytest.raises(TypeError):
        bool(result)


def test_frozen_L_golden_bytes_hashes_and_semantic_boundary():
    assert len(RAW) == 4318 and hashlib.sha256(RAW).hexdigest() == G
    assert len(base()['payload']) == 17
    for row in VECTORS['objects'].values():
        b = row['preimage'].encode()
        assert len(b) == row['bytes'] and hashlib.sha256(b).hexdigest() == row['sha256']
    result = verify_bytes(RAW, trusted_pin=PIN)
    assert_incomplete(result)
    assert result.genesis_hash == G
    assert all(bytes.fromhex(row['canonical_bytes']) == b'{}'
        for row in base()['payload']['policy_registry']['policies'])
    assert any('reviewer' in reason for reason in result.incomplete_policies)
    assert any('native' in reason for reason in result.incomplete_policies)


@pytest.mark.parametrize('name', VECTORS['mutations'])
def test_unchanged_L_negative_vectors(name):
    row = VECTORS['mutations'][name]
    e = base()
    if 'path' in row:
        at = e
        for key in row['path'][:-1]:
            at = at[key]
        at[row['path'][-1]] = row['value']
        raw = encode(e)
    else:
        raw = RAW + bytes.fromhex(row['suffix_hex'])
    assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
    result = verify_bytes(raw, trusted_pin=PIN)
    assert result.outcome not in (Outcome.INCOMPLETE_POLICY, Outcome.INCOMPLETE_AUTHORITY)


def test_explicit_pin_missing_wrong_or_peer_supplied():
    result = verify_bytes(RAW, trusted_pin=None)
    assert result.outcome == Outcome.INCOMPLETE_AUTHORITY
    assert result.component_commitments_verified and not result.pinned_test_identity_matched
    with pytest.raises(TypeError):
        verify_bytes(RAW)
    for pin in (G, {'genesis_hash': G}, replace(PIN, genesis_hash='ff'*32),
            replace(PIN, network_id='task717i-test-other'), replace(PIN, application='another')):
        assert verify_bytes(RAW, trusted_pin=pin).outcome == Outcome.WRONG_AUTHORITY
    assert bind_test_authority(RAW, trusted_pin=None).test_authority is None
    with pytest.raises(ValueError):
        TrustedGenesisPin(G, 'zoidberg-public-testnet-v2', 'test')


@pytest.mark.parametrize('field', PAYLOAD.split())
@pytest.mark.parametrize('mutation', ['missing', 'null'])
def test_all_17_fields_required_and_nonnull(field, mutation):
    e = base()
    if mutation == 'missing':
        del e['payload'][field]
    else:
        e['payload'][field] = None
    assert verify(e).outcome == Outcome.INVALID_STRUCTURE


@pytest.mark.parametrize('path', [[], ['payload'], ['payload','validator_manifest'],
    ['payload','agreement_descriptor'], ['payload','agreement_descriptor','limits'],
    ['payload','policy_registry'], ['payload','policy_registry','policies',0],
    ['payload','reviewer_bootstrap'], ['payload','native_bootstrap'],
    ['payload','history_bootstrap'], ['payload','history_bootstrap','initial_state']])
def test_closed_schema_at_every_G2_object(path):
    e = base()
    at = e
    for k in path:
        at = at[k]
    at['genesis_hash'] = G
    assert verify(e).outcome == Outcome.INVALID_STRUCTURE


@pytest.mark.parametrize('mutation', ['newline','bom','utf8','duplicate','nested-duplicate',
    'float','exponent','nan','infinity','negative-zero','escape','spaces','order',
    'trailing','surrogate','unicode','depth','huge-integer','wrong-input-type'])
def test_lexical_and_resource_rejections(mutation):
    raw = RAW
    if mutation == 'newline': raw += b'\n'
    elif mutation == 'bom': raw = b'\xef\xbb\xbf'+raw
    elif mutation == 'utf8': raw = raw.replace(b'task717i', b'task\xff17i')
    elif mutation == 'duplicate': raw = raw.replace(b'"protocol_version":2}', b'"protocol_version":2,"protocol_version":2}')
    elif mutation == 'nested-duplicate': raw = raw.replace(b'"index":0', b'"index":0,"index":0')
    elif mutation in ('float','exponent','nan','infinity','negative-zero','huge-integer'):
        token = dict(float=b'0.0',exponent=b'0e0',nan=b'NaN',infinity=b'Infinity',
            **{'negative-zero':b'-0','huge-integer':b'9'*10000})[mutation]
        raw = raw.replace(b'"index":0', b'"index":'+token)
    elif mutation == 'escape': raw = raw.replace(b'task717i', b'task717\\u0069')
    elif mutation == 'spaces': raw = raw.replace(b'"index":0', b'"index": 0')
    elif mutation == 'order':
        e = base(); e['domain'] = e.pop('domain')
        raw = json.dumps(e, separators=(',', ':')).encode()
    elif mutation == 'trailing': raw += b'{}'
    elif mutation == 'surrogate': raw = raw.replace(b'task717i', b'task\\ud800')
    elif mutation == 'unicode': raw = raw.replace(b'task717i', 't\u00e9st717i'.encode())
    elif mutation == 'depth': raw = b'['*33+b'0'+b']'*33
    elif mutation == 'wrong-input-type': raw = bytearray(raw)
    assert verify_bytes(raw, trusted_pin=PIN).outcome == Outcome.INVALID_STRUCTURE


@pytest.mark.parametrize('path', [['protocol_version'], ['payload','genesis_version'],
    ['payload','index'], ['payload','initial_block_version'], ['payload','consensus_message_version'],
    ['payload','validator_manifest','validator_epoch'], ['payload','agreement_descriptor','agreement_version'],
    ['payload','reviewer_bootstrap','bootstrap_version'], ['payload','native_bootstrap','native_state_version'],
    ['payload','history_bootstrap','history_version'], ['payload','history_bootstrap','initial_state','state_version']])
@pytest.mark.parametrize('value', [True, '1', 99])
def test_no_version_coercion_or_negotiation(path, value):
    e = base(); at = e
    for key in path[:-1]: at = at[key]
    at[path[-1]] = value
    assert verify(e).outcome == Outcome.INVALID_STRUCTURE


@pytest.mark.parametrize('field', ['validator_set_commitment','agreement_profile_digest',
    'policy_registry_digest','reviewer_bootstrap_digest','native_bootstrap_digest'])
def test_component_mismatch(field):
    e = base(); e['payload'][field] = 'ab'*32
    assert verify(e).outcome == Outcome.INVALID_COMMITMENT


@pytest.mark.parametrize('part', ['reviewer','native','policy','manifest','application','network'])
def test_changed_source_changes_G_even_after_internal_rebinding(part):
    e = base(); p = e['payload']
    if part == 'reviewer': p['reviewer_bootstrap']['reviewers'].pop()
    elif part == 'native': p['native_bootstrap'].update(total_supply='1',initial_reward_pool='1')
    elif part == 'policy': p['policy_registry']['policies'][0]['canonical_bytes'] = encode({'test':'source'}).hex()
    elif part == 'manifest':
        pubs = p['validator_manifest']['validator_public_keys']
        from verification.bft717k.fixtures import VECTORS as IV
        pubs[-1] = next(k['public_key'] for k in IV['keys'] if k['scalar'] == 5)
        pubs.sort()
    elif part == 'application': p['application'] = 'task717i-other'
    elif part == 'network': e['network_id'] = 'task717i-test-other'
    changed = rebind(e)
    assert digest(changed) != G
    assert verify(changed).outcome == Outcome.WRONG_AUTHORITY
    assert_incomplete(verify(changed, pin_for(changed)))


@pytest.mark.parametrize('part', ['manifest','reviewer','native','policy'])
def test_tampered_included_content_without_rehash(part):
    e = base(); p = e['payload']
    if part == 'manifest': p['validator_manifest']['network_id'] = 'task717i-test-other'
    elif part == 'reviewer': p['reviewer_bootstrap']['reviewers'].pop()
    elif part == 'native': p['native_bootstrap'].update(total_supply='1',initial_reward_pool='1')
    else: p['policy_registry']['policies'][0]['canonical_bytes'] = b'{"x":1}'.hex()
    assert verify(e).outcome in (Outcome.INVALID_STRUCTURE, Outcome.INVALID_COMMITMENT)


@pytest.mark.parametrize('bad', ['7B7D','0x7b7d','7b7','zz','',None,'20','5b5d',
    b'{"x":1,"x":1}'.hex(), b'{"x":1.0}'.hex(), b'{}\n'.hex(), b'\xff'.hex(),
    b'{"x":"\\ud800"}'.hex(), b'{"x":"\\u00e9"}'.hex(),
    (b'['*33+b'0'+b']'*33).hex(), (b'{"x":"'+b'a'*8185+b'"}').hex()])
def test_strict_embedded_policy_bytes(bad):
    e = base(); e['payload']['policy_registry']['policies'][0]['canonical_bytes'] = bad
    assert verify(e).outcome == Outcome.INVALID_STRUCTURE


def test_unicode_source_retains_exact_scalars_and_no_semantic_approval():
    hashes = []
    for text in ('\u00e9', 'e\u0301', '\U0001f980', '"\\\n'):
        e = base(); e['payload']['policy_registry']['policies'][0]['canonical_bytes'] = encode({'test':text}).hex()
        e = rebind(e)
        assert_incomplete(verify(e, pin_for(e)))
        hashes.append(digest(e))
    assert len(set(hashes)) == 4


@pytest.mark.parametrize('field', ['genesis_hash','agreement_profile_digest','initial_state_commitment',
    'policy_registry_digest','reviewer_bootstrap_digest','native_bootstrap_digest','bootstrap_history_commitment',
    'finalized_ref'])
def test_explicit_circular_dependencies_reject(field):
    e = base(); e['payload']['policy_registry']['policies'][0]['canonical_bytes'] = encode({'nested':{field:G}}).hex()
    assert verify(e).outcome == Outcome.INVALID_STRUCTURE


def test_opaque_policy_field_is_never_interpreted_as_signature_authority():
    # No inner signature schema is frozen. A field spelling alone does not
    # define a G-dependent signature, nor can it authorize anything here.
    e = base()
    e['payload']['policy_registry']['policies'][0]['canonical_bytes'] = encode({'signature':'opaque'}).hex()
    e = rebind(e)
    assert_incomplete(verify(e,pin_for(e)))


@pytest.mark.parametrize('mutation', ['duplicate','unsorted','malformed','uppercase','too-many','status','usage'])
def test_reviewer_bootstrap(mutation):
    e = base(); b = e['payload']['reviewer_bootstrap']; ws = b['reviewers']
    if mutation == 'duplicate': ws[1] = ws[0]
    elif mutation == 'unsorted': ws.reverse()
    elif mutation == 'malformed': ws[0] = '0xBAD'
    elif mutation == 'uppercase': ws[0] = ws[0].upper()
    elif mutation == 'too-many': b['reviewers'] = ['0x'+format(i,'040x') for i in range(129)]
    elif mutation == 'status': b['underlying_status'] = 'ESTABLISHED_REVIEWER'
    else: b['quota_used'] = 1
    assert verify(e).outcome == Outcome.INVALID_STRUCTURE


@pytest.mark.parametrize('mutation', ['duplicate','unsorted','zero','negative','trailing-zero','float',
    'nonce-int','nonce-zero','nonce-two','supply','over-supply','recipient-key','too-many','extra'])
def test_native_bootstrap(mutation):
    e = base(); nb = e['payload']['native_bootstrap']
    accounts = [dict(wallet_address='0x'+format(i,'040x'),balance='1',next_nonce='1') for i in (1,2)]
    nb.update(allocations=accounts,total_supply='2')
    if mutation == 'duplicate': accounts[1]['wallet_address'] = accounts[0]['wallet_address']
    elif mutation == 'unsorted': accounts.reverse()
    elif mutation in ('zero','negative','trailing-zero','float'):
        accounts[0]['balance'] = {'zero':'0','negative':'-1','trailing-zero':'1.0','float':1.0}[mutation]
    elif mutation.startswith('nonce-'): accounts[0]['next_nonce'] = {'nonce-int':1,'nonce-zero':'0','nonce-two':'2'}[mutation]
    elif mutation == 'supply': nb['total_supply'] = '3'
    elif mutation == 'over-supply': nb['total_supply'] = '1000000000.000001'
    elif mutation == 'recipient-key': accounts[0]['wallet_address'] = e['payload']['validator_manifest']['validator_public_keys'][0]
    elif mutation == 'too-many': nb['allocations'] = accounts*2049
    else: accounts[0]['role'] = 'validator'
    assert verify(e).outcome == Outcome.INVALID_STRUCTURE


def test_N1_exact_money_conservation_and_clean_history():
    e = base(); e['payload']['native_bootstrap'] = json.loads(VECTORS['objects']['N1']['preimage'])['payload']
    e = rebind(e)
    assert_incomplete(verify(e, pin_for(e)))
    for field in ('offenses','penalties','participation','quota_used','reputation'):
        bad = deepcopy(e); bad['payload']['reviewer_bootstrap'][field] = []
        assert verify(bad).outcome == Outcome.INVALID_STRUCTURE
    e['payload']['history_bootstrap']['bootstrap_events'] = [{}]
    assert verify(e).outcome == Outcome.INVALID_STRUCTURE


def test_static_manifest_rejects_large_duplicate_offcurve_and_duplicate_ID(monkeypatch):
    for keys in (base()['payload']['validator_manifest']['validator_public_keys']*1024,
            ['02'+'ff'*32]*4, [base()['payload']['validator_manifest']['validator_public_keys'][0]]*4):
        e = base(); e['payload']['validator_manifest']['validator_public_keys'] = keys
        assert verify(e).outcome == Outcome.INVALID_STRUCTURE
    monkeypatch.setattr('isolated_bft717k.manifest.identity', lambda _: '0x'+'11'*20)
    assert verify(base()).outcome == Outcome.INVALID_STRUCTURE


def test_maximum_list_source_and_global_size_boundaries():
    e = wide()
    assert_incomplete(verify(e, pin_for(e)))
    assert len(e['payload']['native_bootstrap']['allocations']) == 4096
    assert len(e['payload']['reviewer_bootstrap']['reviewers']) == 128
    raw = b'"'+b'a'*(GENESIS_LIMIT-2)+b'"'
    assert len(raw) == GENESIS_LIMIT
    assert verify_bytes(raw,trusted_pin=PIN).detail == 'outer_string_length'
    assert verify_bytes(raw+b' ',trusted_pin=PIN).detail == 'json_size'
    # A valid complete envelope cannot reach 1 MiB: simultaneous component caps
    # already sum to 888832; padding/unknown extension fields are forbidden.


def test_registry_exact_total_cap_and_one_over():
    e = base(); e['network_id'] = 'task717i-test-ab'
    e = rebind(e); entries = e['payload']['policy_registry']['policies']
    for row in entries[:3]: row['canonical_bytes'] = encode({'x':'a'*8184}).hex()
    remaining = 65536-len(encode(e['payload']['policy_registry']))
    assert remaining % 2 == 0
    entries[3]['canonical_bytes'] = encode({'x':'a'*(remaining//2-6)}).hex()
    e = rebind(e)
    assert len(encode(e['payload']['policy_registry'])) == 65536
    assert_incomplete(verify(e, pin_for(e)))
    # One extra ASCII byte in the registry network gives exact 65537, and is
    # rejected on size before a mismatching network could mask the boundary.
    e['payload']['policy_registry']['network_id'] += 'a'
    assert len(encode(e['payload']['policy_registry'])) == 65537
    assert verify(e).detail == 'policy_registry_size'


def test_component_cross_bindings_and_history_commitments():
    for part,field in [('reviewer_bootstrap','reviewer_policy_digest'),
            ('reviewer_bootstrap','reputation_rule_digest'),
            ('history_bootstrap','bootstrap_history_commitment'),
            ('history_bootstrap','initial_state_commitment'),
            ('agreement_descriptor','application_policy_digest')]:
        e = base(); e['payload'][part][field] = 'ac'*32
        assert verify(e).outcome == Outcome.INVALID_COMMITMENT
    for field in ('policy_registry_digest','reviewer_bootstrap_digest','native_bootstrap_digest','bootstrap_history_commitment'):
        e = base(); e['payload']['history_bootstrap']['initial_state'][field] = 'ac'*32
        assert verify(e).outcome == Outcome.INVALID_COMMITMENT


def test_adapter_exact_membership_quorum_and_cache_never_overrides_pin(tmp_path):
    binding = bind_test_authority(RAW, trusted_pin=PIN)
    assert_incomplete(binding.verification)
    authority = binding.test_authority
    ctx = authority.context
    assert ctx.genesis_hash == G and ctx.C == VECTORS['objects']['M']['sha256']
    for pub in base()['payload']['validator_manifest']['validator_public_keys']:
        assert authority.resolve_member(identity(pub),pub)['genesis_hash'] == G
    assert authority.genesis_authentication.outcome == KOutcome.INCOMPLETE_AUTHORITY
    result = verify_quorum(authority,encode(certificate(ctx)),kind='q4')
    assert result.outcome == KOutcome.VALID_QUORUM
    assert not result.genesis_authenticated
    cache = tmp_path/'authority.json'; save_cache(cache,authority)
    assert load_cache(cache,authority.anchor).context.C == ctx.C
    foreign = rebind({**base(), 'network_id':'task717i-test-other'})
    other = bind_test_authority(encode(foreign),trusted_pin=pin_for(foreign)).test_authority
    with pytest.raises(AuthorityFailure): load_cache(cache,other.anchor)
    wrong = bind_test_authority(encode(foreign),trusted_pin=PIN)
    assert wrong.test_authority is None and wrong.verification.outcome == Outcome.WRONG_AUTHORITY


def test_local_IO_and_resource_failure_distinct(tmp_path, monkeypatch):
    assert verify_file(tmp_path/'missing', trusted_pin=PIN).outcome == Outcome.IO_FAILURE
    f = tmp_path/'g2.json'; f.write_bytes(RAW)
    assert_incomplete(verify_file(f,trusted_pin=PIN))
    f.write_bytes(b'a'*(GENESIS_LIMIT+1))
    assert verify_file(f,trusted_pin=PIN).detail == 'json_size'
    def unavailable(*args,**kwargs): raise MemoryError()
    monkeypatch.setattr('isolated_g2717m.verifier.parse',unavailable)
    assert verify_bytes(RAW,trusted_pin=PIN).outcome == Outcome.RESOURCE_FAILURE


def test_bounded_read_and_permission_failure(monkeypatch):
    import io
    requests = []
    class Stream(io.BytesIO):
        def read(self, amount):
            requests.append(amount)
            return super().read(amount)
    monkeypatch.setattr('builtins.open', lambda *a,**k: Stream(RAW))
    assert_incomplete(verify_file('unused',trusted_pin=PIN))
    assert requests == [GENESIS_LIMIT+1]
    def denied(*a,**k): raise PermissionError()
    monkeypatch.setattr('builtins.open',denied)
    assert verify_file('unused',trusted_pin=PIN).outcome == Outcome.IO_FAILURE


def test_manifest_and_adapter_resource_failure_not_invalid_data(monkeypatch):
    from isolated_bft717k.outcomes import AuthorityFailure
    def unavailable(*a,**k): raise AuthorityFailure(KOutcome.RESOURCE_FAILURE,'provider_unavailable')
    with monkeypatch.context() as patch:
        patch.setattr('isolated_g2717m.verifier.Manifest',unavailable)
        assert verify_bytes(RAW,trusted_pin=PIN).outcome == Outcome.RESOURCE_FAILURE
    monkeypatch.setattr('isolated_g2717m.authority_adapter.TrustedTestAnchor',unavailable)
    binding = bind_test_authority(RAW,trusted_pin=PIN)
    assert binding.test_authority is None and binding.verification.outcome == Outcome.RESOURCE_FAILURE


def test_source_network_application_and_registry_order():
    for source in ({'network_id':'wrong-network'}, {'application':'wrong-app'}):
        e = base(); e['payload']['policy_registry']['policies'][0]['canonical_bytes'] = encode(source).hex()
        assert verify(e).outcome == Outcome.INVALID_STRUCTURE
    e = base(); e['payload']['policy_registry']['policies'].reverse()
    assert verify(e).outcome == Outcome.INVALID_STRUCTURE


def test_source_depth_exactly_32_and_over():
    for depth in (32,33):
        source = b'{"x":'*depth+b'0'+b'}'*depth
        e = base(); e['payload']['policy_registry']['policies'][0]['canonical_bytes'] = source.hex()
        e = rebind(e)
        if depth == 32:
            assert_incomplete(verify(e,pin_for(e)))
        else:
            assert verify(e).outcome == Outcome.INVALID_STRUCTURE


def test_independent_JS_construction_and_unchanged_literal_vectors():
    output = subprocess.run(['node',str(ROOT/'verification/g2717m/oracle.cjs'),
        str(ROOT/'tests/fixtures/g2717m_v1/vectors.json')],capture_output=True,text=True,check=True)
    assert '12 independently constructed' in output.stdout


def test_production_sources_and_historical_fixtures_unchanged():
    # Include new files too so this remains meaningful before and after commit.
    excluded = ('tests/','verification/','isolated_g2717m/','isolated_bft717j/','isolated_bft717k/','.venv/','temp/')
    paths = subprocess.run(['git','ls-files','--cached','--others','--exclude-standard','*.py'],
        cwd=ROOT,capture_output=True,text=True,check=True).stdout.splitlines()
    active = [ROOT/p for p in paths if not p.startswith(excluded)]
    assert all('isolated_g2717m' not in p.read_text(encoding='utf-8') for p in active)
    protected = ['canonical_v3','protocol_v1_genesis.py','blockchain.py','services',
        'isolated_bft717j','isolated_bft717k','tests/fixtures/bft717j','verification/tendermint717h']
    assert subprocess.run(['git','diff','HEAD','--',*protected],cwd=ROOT,
        capture_output=True,text=True,check=True).stdout == ''
