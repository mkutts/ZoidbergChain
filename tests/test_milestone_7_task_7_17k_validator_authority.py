"""7.17K adversarial checks. No positive genesis/application-finality claim."""
from copy import deepcopy
from dataclasses import asdict
import itertools
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from canonical_v3.primitives import MAX_UINT
from isolated_bft717j.custody import TestKey
from isolated_bft717j.wire import Context, J, descriptor, identity, parse, sha, CURVE_ORDER
from isolated_bft717k.authority import (TrustedTestAnchor, StaticTestAuthority,
    resolve_authority, save_cache, load_cache)
from isolated_bft717k.manifest import Manifest, construct_manifest
from isolated_bft717k.outcomes import AuthorityFailure, Outcome
from isolated_bft717k.signer_fixture import open_test_signer
from isolated_bft717k.verifier import (verify_message, verify_quorum, verify_history,
    compare_quorums, compare_messages)
from verification.bft717k.fixtures import (ROOT, VECTORS, context, authority, sign,
    message, certificate, frozen_proof)
from verification.tendermint717h.model import Block


@pytest.fixture(scope='module')
def auth():
    return authority()


def assert_no_finality(result):
    assert not result.genesis_authenticated
    assert not result.block_parent_identity_authenticated
    assert not result.full_finalized_ancestry_verified
    assert not result.complete_consensus_execution_verified


def resolve(anchor, ctx, **changes):
    fields = dict(network_id=ctx.network, genesis_hash=ctx.genesis_hash,
        validator_set_commitment=ctx.C, agreement_profile_digest=ctx.A)
    fields.update(changes)
    return resolve_authority(anchor, ctx.manifest_bytes, ctx.agreement_bytes, **fields)


def test_manifest_frozen_commitment_and_all_authoring_orders():
    m = Manifest(J(VECTORS['manifest']))
    assert m.commitment == VECTORS['validator_set_commitment']
    assert len(m.members) == 4
    assert {pub: vid for vid, pub in m.members} == {
        k['public_key']: k['validator_id'] for k in VECTORS['keys'] if k['scalar'] <= 4}
    for order in itertools.permutations(VECTORS['manifest']['validator_public_keys']):
        assert construct_manifest('task717i-test', order) == m
    value = m.value
    value['validator_public_keys'].clear()
    assert len(m.members) == 4


@pytest.mark.parametrize('mutation', ['unknown', 'missing', 'bool', 'float', 'str-int', 'epoch',
    'version', 'membership-version', 'profile', 'protocol', 'domain', 'fault-budget',
    'quorum', 'count', 'order', 'duplicate-key', 'unicode', 'short-network', 'long-network',
    'bad-network', 'null-keys', 'duplicate-json', 'whitespace', 'exponent', 'negative-zero',
    'depth', 'oversize', 'bom', 'escape'])
def test_manifest_adversarial_schema(mutation):
    m = deepcopy(VECTORS['manifest'])
    edits = dict(unknown=('extra', 1), bool=('validator_epoch', False),
        float=('validator_epoch', 0.0), **{'str-int': ('required_quorum', '3'),
        'epoch': ('validator_epoch', 1), 'version': ('protocol_version', 1),
        'membership-version': ('membership_version', 2), 'profile': ('authority_profile', 'dynamic'),
        'protocol': ('protocol', 'other'), 'domain': ('domain', 'other'),
        'fault-budget': ('byzantine_fault_budget', 0), 'quorum': ('required_quorum', 2),
        'unicode': ('network_id', 'tést'), 'short-network': ('network_id', 'ab'),
        'long-network': ('network_id', 'a'*65), 'bad-network': ('network_id', 'abc\n'),
        'null-keys': ('validator_public_keys', None)})
    if mutation in edits:
        k, v = edits[mutation]
        m[k] = v
    if mutation == 'missing': del m['validator_epoch']
    if mutation == 'count': m['validator_public_keys'].pop()
    if mutation == 'order': m['validator_public_keys'].reverse()
    if mutation == 'duplicate-key': m['validator_public_keys'][1] = m['validator_public_keys'][0]
    # stdlib encoding deliberately permits a float to reach the strict parser.
    raw = json.dumps(m, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    if mutation == 'duplicate-json': raw = raw.replace(b'"validator_epoch":0', b'"validator_epoch":0,"validator_epoch":0')
    if mutation == 'whitespace': raw += b'\n'
    if mutation == 'exponent': raw = raw.replace(b'"validator_epoch":0', b'"validator_epoch":0e0')
    if mutation == 'negative-zero': raw = raw.replace(b'"validator_epoch":0', b'"validator_epoch":-0')
    if mutation == 'depth': raw = b'['*33 + b'0' + b']'*33
    if mutation == 'oversize': raw = b' '*8193
    if mutation == 'bom': raw = b'\xef\xbb\xbf' + raw
    if mutation == 'escape': raw = raw.replace(b'task717i', b'task717\\u0069')
    with pytest.raises(AuthorityFailure) as e:
        Manifest(raw)
    assert e.value.outcome == Outcome.INVALID_MANIFEST


@pytest.mark.parametrize('bad', ['04'+'11'*32, '0x'+'02'+'11'*32, '02'+'ff'*32,
    '02'+'00'*32, '00'+'11'*32, '', None, 123,
    VECTORS['manifest']['validator_public_keys'][0].upper()])
def test_bad_public_key_representations(bad):
    m = deepcopy(VECTORS['manifest'])
    m['validator_public_keys'][0] = bad
    with pytest.raises(AuthorityFailure): Manifest(J(m))


def test_duplicate_identity_collision_defense(monkeypatch):
    # A real Keccak160 collision is not available; inject one ONLY at ID derivation.
    monkeypatch.setattr('isolated_bft717k.manifest.identity', lambda _: '0x'+'11'*20)
    with pytest.raises(AuthorityFailure, match='duplicate_validator_identity'):
        Manifest(J(VECTORS['manifest']))


@pytest.mark.parametrize('field,value', [('network_id','peer-test'), ('genesis_hash','22'*32),
    ('validator_set_commitment','22'*32), ('agreement_profile_digest','22'*32)])
def test_wrong_claimed_context(auth, field, value):
    with pytest.raises(AuthorityFailure) as e:
        resolve(auth.anchor, auth.context, **{field:value})
    assert e.value.outcome == Outcome.WRONG_CONTEXT


def test_self_declared_peer_genesis_and_roster_cannot_authorize(auth):
    ctx = context('task717i-test-peer')
    with pytest.raises(AuthorityFailure): resolve(auth.anchor, ctx)
    m = deepcopy(VECTORS['manifest'])
    m['validator_public_keys'] = sorted(k['public_key'] for k in VECTORS['keys'] if k['scalar'] in (1,2,3,5))
    alternate = Context(J(m), auth.context.agreement_bytes, auth.context.genesis_hash)
    with pytest.raises(AuthorityFailure): resolve(auth.anchor, alternate)
    with pytest.raises(AuthorityFailure): resolve(None, alternate)
    with pytest.raises(TypeError): TrustedTestAnchor(ctx.manifest_bytes, ctx.agreement_bytes, ctx.genesis_hash, genesis_verified=True)
    assert auth.genesis_authentication.outcome == Outcome.INCOMPLETE_AUTHORITY
    assert auth.genesis_authentication.fixture_membership_authenticated
    assert_no_finality(auth.genesis_authentication)


def test_only_test_networks_and_static_epoch(auth):
    with pytest.raises(AuthorityFailure): authority(context('launch-network'))
    vid, pub = next(iter(auth.context.members.items()))
    assert auth.resolve_member(vid, pub)['validator_epoch'] == 0
    for epoch in (1, False, '0'):
        with pytest.raises(AuthorityFailure): auth.resolve_member(vid, pub, epoch)
    with pytest.raises(AuthorityFailure): auth.resolve_member('0x'+'00'*20, pub)
    with pytest.raises(AuthorityFailure): auth.resolve_member(vid, VECTORS['keys'][-1]['public_key'])
    with pytest.raises(TypeError): bool(auth.genesis_authentication)


@pytest.mark.parametrize('name', ['proposal','prevote','precommit','nil-prevote','nil-precommit',
                                'round-one-prevote','justified-proposal'])
def test_frozen_authenticated_messages(auth, name):
    r = verify_message(auth, J(VECTORS['cases'][name]['signed']))
    assert r.outcome == Outcome.VALID_MESSAGE and r.signatures_valid
    assert_no_finality(r)


@pytest.mark.parametrize('name', ['pv', 'q4-x', 'q4-y', 'q4-x-four'])
def test_frozen_quorum_proofs(auth, name):
    raw = frozen_proof(name)
    r = verify_quorum(auth, raw, 'pv' if name == 'pv' else 'q4')
    assert r.outcome == Outcome.VALID_QUORUM
    assert r.quorum_structure_valid and r.signatures_valid
    assert r.proof_id == VECTORS['proofs'][name]['digest']
    assert r.signature_checks == (3 if name == 'pv' else 5 if name.endswith('four') else 4)
    assert r.distinct_signers == (4 if name.endswith('four') else 3)
    assert_no_finality(r)


@pytest.mark.parametrize('count', [0,1,2])
def test_insufficient_quorum_even_with_valid_signatures(auth, count):
    obj = parse(frozen_proof())
    obj['precommits'] = obj['precommits'][:count]
    r = verify_quorum(auth, J(obj))
    assert r.outcome == Outcome.INSUFFICIENT_QUORUM and not r.quorum_structure_valid
    assert r.signatures_valid and r.distinct_signers == count


@pytest.mark.parametrize('mutation', ['duplicate', 'high-s-duplicate', 'contradictory', 'unordered',
    'unauthorized', 'mixed-round', 'mixed-epoch', 'wrong-phase', 'nil', 'tamper', 'bad-v',
    'network', 'genesis', 'protocol', 'profile', 'set', 'parent', 'height', 'hash',
    'wrong-proposer', 'proposal-round', 'extra-roster', 'unknown', 'oversize', 'depth',
    'too-many', 'bad-commitment', 'bool-commitment', 'wrong-proof-version', 'duplicate-json'])
def test_adversarial_quorum(auth, mutation):
    obj = parse(frozen_proof())
    v = obj['precommits'][0]
    vid = v['envelope']['payload']['validator_id']
    scalar = next(k['scalar'] for k in VECTORS['keys'] if k['validator_id'] == vid)
    fields = {'mixed-round':('round',1), 'mixed-epoch':('validator_epoch',1),
        'wrong-phase':('step','prevote'), 'nil':('block_hash',None),
        'genesis':('genesis_hash','22'*32), 'profile':('agreement_profile_digest','22'*32),
        'set':('validator_set_commitment','22'*32), 'parent':('parent_hash','22'*32),
        'height':('block_height',2), 'hash':('block_hash','bb'*32)}
    if mutation in fields:
        field, value = fields[mutation]
        v['envelope']['payload'][field] = value
        obj['precommits'][0] = sign(v['envelope'], scalar)
    if mutation == 'duplicate': obj['precommits'][1] = deepcopy(v)
    if mutation == 'high-s-duplicate':
        duplicate = deepcopy(v)
        sig = bytes.fromhex(v['signature'][2:])
        duplicate['signature'] = '0x'+(sig[:32]+(CURVE_ORDER-int.from_bytes(sig[32:64])).to_bytes(32)+bytes([55-sig[64]])).hex()
        obj['precommits'][1] = duplicate
    if mutation == 'contradictory':
        other = deepcopy(v['envelope']); other['payload']['block_hash'] = 'bb'*32
        obj['precommits'][1] = sign(other, scalar)
    if mutation == 'unordered': obj['precommits'].reverse()
    if mutation == 'unauthorized': obj['precommits'][0] = sign(message(auth.context,5),5)
    if mutation == 'tamper': v['envelope']['payload']['validator_id'] = obj['precommits'][1]['envelope']['payload']['validator_id']
    if mutation == 'bad-v': v['signature'] = v['signature'][:-2]+'00'
    if mutation in ('network','protocol'):
        v['envelope']['network_id' if mutation == 'network' else 'protocol_version'] = 'peer-test' if mutation == 'network' else 1
        obj['precommits'][0] = sign(v['envelope'],scalar)
    if mutation == 'wrong-proposer': obj['proposal'] = sign(message(auth.context,2,'propose'),2)
    if mutation == 'proposal-round': obj['proposal'] = sign(message(auth.context,2,'propose',round=1),2)
    if mutation == 'extra-roster': obj['validator_set'] = list(auth.context.members)
    if mutation == 'unknown': obj['extra'] = 1
    if mutation == 'too-many': obj['precommits'] *= 2
    if mutation == 'bad-commitment': obj['commitment']['block_hash'] = 'bb'*32
    if mutation == 'bool-commitment': obj['commitment']['validator_epoch'] = False
    if mutation == 'wrong-proof-version': obj['proof_version'] = 3
    raw = J(obj)
    if mutation == 'oversize': raw = b' '*16385
    if mutation == 'depth': raw = b'['*33+b'0'+b']'*33
    if mutation == 'duplicate-json': raw = raw.replace(b'"proof_version":4', b'"proof_version":4,"proof_version":4')
    r = verify_quorum(auth, raw)
    expected = Outcome.WRONG_CONTEXT if mutation in ('network','genesis','profile','set') else Outcome.INVALID_PROOF
    assert r.outcome == expected, (mutation, r)
    assert not r.quorum_structure_valid
    assert_no_finality(r)


def test_nil_and_phase_semantics(auth):
    ctx = auth.context
    nil_pv = J(certificate(ctx, 'pv', value=None))
    assert verify_quorum(auth, nil_pv, 'pv').outcome == Outcome.VALID_QUORUM
    nil_q4 = certificate(ctx, value=None)
    assert verify_quorum(auth, J(nil_q4)).outcome == Outcome.INVALID_PROOF
    assert verify_quorum(auth, frozen_proof('pv')).outcome == Outcome.INVALID_PROOF
    assert verify_message(auth, J(VECTORS['cases']['nil-precommit']['signed']), expected_step='prevote').outcome == Outcome.INVALID_PROOF
    # A zero hash is non-nil metadata, not proof a block exists.
    zero = J(certificate(ctx, value='00'*32))
    assert verify_quorum(auth, zero).outcome == Outcome.VALID_QUORUM
    assert verify_history(auth, zero).outcome == Outcome.INCOMPLETE_DATA


@pytest.mark.parametrize('missing', ['absent','null'])
def test_missing_signed_proposal_is_incomplete(auth, missing):
    obj = parse(frozen_proof())
    if missing == 'absent': del obj['proposal']
    else: obj['proposal'] = None
    r = verify_quorum(auth, J(obj))
    assert r.outcome == Outcome.INCOMPLETE_DATA and not r.quorum_structure_valid


def test_equivocation_does_not_rewrite_authority_or_existing_qc(auth):
    a = J(VECTORS['cases']['prevote']['signed'])
    b = J(VECTORS['cases']['conflicting-prevote']['signed'])
    assert compare_messages(auth,a,b).outcome == Outcome.EQUIVOCATION
    assert compare_messages(auth,a,a).outcome == Outcome.RETRANSMISSION
    bad = parse(b); bad['signature'] = bad['signature'][:-2]+'00'
    assert compare_messages(auth,a,J(bad)).outcome == Outcome.INVALID_PROOF
    assert compare_messages(auth,a,J(VECTORS['cases']['round-one-prevote']['signed'])).outcome == Outcome.INVALID_PROOF
    assert len(auth.context.members) == 4
    assert verify_quorum(auth,frozen_proof()).outcome == Outcome.VALID_QUORUM


def test_registered_id_requires_exact_full_key_and_high_s_has_no_extra_weight(auth):
    e = message(auth.context)
    forged = J(sign(e,5))  # authorized ID, but a different recovered full point
    r = verify_message(auth,forged)
    assert r.outcome == Outcome.INVALID_PROOF and r.detail == 'signature_key'
    obj = parse(frozen_proof())
    v = obj['precommits'][0]
    sig = bytes.fromhex(v['signature'][2:])
    v['signature'] = '0x'+(sig[:32]+(CURVE_ORDER-int.from_bytes(sig[32:64])).to_bytes(32)+bytes([55-sig[64]])).hex()
    r = verify_quorum(auth,J(obj))
    assert r.outcome == Outcome.VALID_QUORUM and r.distinct_signers == 3


def test_conflicting_apparent_certificates_require_both_authentic_proofs(auth):
    x, y = frozen_proof(), frozen_proof('q4-y')
    r = compare_quorums(auth,x,y)
    assert r.outcome == Outcome.CONFLICT and r.signature_checks == 8
    assert_no_finality(r)
    assert compare_quorums(auth,x,frozen_proof('q4-x-four')).outcome == Outcome.COMPATIBLE
    bad = parse(y); bad['proposal']['signature'] = '0x'+'00'*65
    assert compare_quorums(auth,x,J(bad)).outcome == Outcome.INVALID_PROOF
    other_round = J(certificate(auth.context,round=1))
    assert compare_quorums(auth,x,other_round).outcome == Outcome.COMPATIBLE
    h2 = J(certificate(auth.context,height=2,parent='aa'*32))
    assert compare_quorums(auth,x,h2).outcome == Outcome.INCOMPLETE_DATA


def test_history_and_parent_boundary(auth):
    raw = frozen_proof()
    parent = J(dict(block_height=0,block_hash=auth.context.genesis_hash))
    r = verify_history(auth,raw,parent_reference=parent,block_bytes=b'{}')
    assert r.outcome == Outcome.INCOMPLETE_DATA and r.quorum_structure_valid
    assert_no_finality(r)
    assert 'unfrozen' in r.detail
    r = verify_history(auth,raw)
    assert 'missing_canonical_application_block' in r.detail and 'missing_parent' in r.detail
    for ref in (dict(block_height=0,block_hash='22'*32),dict(block_height=1,block_hash=auth.context.genesis_hash)):
        assert verify_history(auth,raw,parent_reference=J(ref)).outcome == Outcome.INVALID_PROOF
    assert verify_history(auth,raw,block_bytes=b' '*3145729).outcome == Outcome.INVALID_PROOF


def test_cache_reopen_in_fresh_process_and_independent_pins(auth,tmp_path):
    path = tmp_path/'authority.json'
    save_cache(path,auth)
    loaded = load_cache(path,auth.anchor)
    assert loaded == auth
    code = ('from verification.bft717k.fixtures import authority, frozen_proof; '
        'from isolated_bft717k.authority import load_cache; '
        'from isolated_bft717k.verifier import verify_quorum; '
        'import sys; a=load_cache(sys.argv[1],authority().anchor); '
        'r=verify_quorum(a,frozen_proof()); print(r.outcome.value); '
        'assert not r.genesis_authenticated and r.quorum_structure_valid')
    run = subprocess.run([sys.executable,'-B','-c',code,str(path)],cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert run.returncode == 0,run.stderr
    assert Outcome.VALID_QUORUM.value in run.stdout
    with pytest.raises(AuthorityFailure): load_cache(path,authority(context('task717i-test-changed')).anchor)


@pytest.mark.parametrize('damage', ['truncated','oversize','missing','genesis','roster','commitment','unknown','epoch','duplicate'])
def test_corrupt_local_cache_fails_closed(auth,tmp_path,damage):
    path = tmp_path/'authority.json'
    save_cache(path,auth)
    raw = path.read_bytes(); c = parse(raw)
    if damage == 'truncated': raw = raw[:40]
    if damage == 'oversize': raw = b' '*16385
    if damage == 'genesis': c['genesis_hash'] = '22'*32
    if damage == 'roster': c['manifest']['validator_public_keys'].reverse()
    if damage == 'commitment': c['validator_set_commitment'] = '22'*32
    if damage == 'unknown': c['genesis_verified'] = True
    if damage == 'epoch': c['validator_epoch'] = 1
    if damage in ('genesis','roster','commitment','unknown','epoch'): raw = J(c)
    if damage == 'duplicate': raw = raw.replace(b'"cache_version":1',b'"cache_version":1,"cache_version":1')
    path.write_bytes(raw)
    if damage == 'missing': path.unlink()
    with pytest.raises(AuthorityFailure) as e: load_cache(path,auth.anchor)
    assert e.value.outcome == Outcome.STORAGE_FAILURE
    if damage == 'missing': assert not path.exists()
    else: assert path.read_bytes() == raw


def test_storage_and_resource_failures_are_not_invalidity(auth,tmp_path,monkeypatch):
    with pytest.raises(AuthorityFailure) as e: save_cache(tmp_path/'absent'/'file',auth)
    assert e.value.outcome == Outcome.STORAGE_FAILURE
    def unavailable(*a,**k): raise MemoryError('test worker unavailable')
    monkeypatch.setattr('isolated_bft717k.verifier.signed',unavailable)
    assert verify_quorum(auth,frozen_proof()).outcome == Outcome.RESOURCE_FAILURE
    assert verify_quorum(None,frozen_proof()).outcome == Outcome.WRONG_CONTEXT


def test_cache_recomputed_self_consistency_cannot_replace_independent_membership(auth,tmp_path):
    path = tmp_path/'authority.json'
    # This is an internally valid alternate fixture, with correct C and same G.
    m = deepcopy(VECTORS['manifest'])
    m['validator_public_keys'] = sorted(k['public_key'] for k in VECTORS['keys'] if k['scalar'] in (1,2,3,5))
    changed = authority(Context(J(m),auth.context.agreement_bytes,auth.context.genesis_hash))
    save_cache(path,changed)
    with pytest.raises(AuthorityFailure) as e: load_cache(path,auth.anchor)
    assert e.value.outcome == Outcome.STORAGE_FAILURE


def test_cache_replace_failure_preserves_previous_file(auth,tmp_path,monkeypatch):
    path = tmp_path/'authority.json'
    save_cache(path,auth)
    before = path.read_bytes()
    def failed(*a): raise OSError('test replace failure')
    monkeypatch.setattr('isolated_bft717k.authority.os.replace',failed)
    with pytest.raises(AuthorityFailure) as e: save_cache(path,auth)
    assert e.value.outcome == Outcome.STORAGE_FAILURE
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_signer_gate_replay_and_h1_r0_nonregression(tmp_path,monkeypatch):
    keys = sorted([TestKey() for _ in range(4)],key=lambda k:k.public_key)
    m = construct_manifest('task717j-test-k', [k.public_key for k in keys])
    ctx = Context(m.raw,J(descriptor('55'*32)),'11'*32)
    auth = authority(ctx)
    blocks = J([asdict(Block('aa'*32,parent=ctx.genesis_hash))])
    path, custody = tmp_path/'signer.db',tmp_path/'custody'
    # Rejection precedes file creation or custody acquisition.
    with pytest.raises(AuthorityFailure): open_test_signer(auth,path,custody,TestKey(),blocks,bootstrap=True)
    assert not path.exists() and not custody.exists()
    e = deepcopy(VECTORS['cases']['proposal']['envelope'])
    e['network_id'] = ctx.network
    e['payload'].update(validator_id=identity(keys[0].public_key),validator_set_commitment=ctx.C)
    raw = J(e)
    with open_test_signer(auth,path,custody,keys[0],blocks,bootstrap=True) as s:
        original = s.sign(raw)
        changed = deepcopy(e); changed['payload']['block_hash'] = 'bb'*32
        with pytest.raises(ValueError,match='CONFLICTING_SLOT'): s.sign(J(changed))
    with open_test_signer(auth,path,custody,keys[0],blocks) as s:
        def forbidden(*a): raise AssertionError('retry called key')
        monkeypatch.setattr(keys[0],'_sign_reserved',forbidden)
        assert s.sign(raw) == original
        changed = deepcopy(e); changed['payload']['validator_set_commitment'] = '22'*32
        with pytest.raises(ValueError,match='context'): s.sign(J(changed))
        # Unchanged 7.17J refuses unsupported transitions, including new coordinates.
        for h,r in ((1,4),(5,0)):
            changed = deepcopy(e); changed['payload'].update(block_height=h,round=r)
            with pytest.raises(ValueError,match='INCOMPLETE_AGREEMENT_CONTEXT'): s.sign(J(changed))
    assert verify_message(auth,original).outcome == Outcome.VALID_MESSAGE


def test_max_width_valid_signed_quorums(auth):
    ctx = context('task717i-test-'+'a'*50)
    a = authority(ctx)
    assert len(ctx.network) == 64 and len(ctx.manifest_bytes) == 603
    for kind,scalars,width in [('pv',(1,2,3),3583),('pv',(1,2,3,4),4581),
                               ('q4',(1,2,3),4632),('q4',(1,2,3,4),5632)]:
        raw = J(certificate(ctx,kind,scalars,height=MAX_UINT,round=2147483647,vr=2147483646))
        assert len(raw) == width
        assert verify_quorum(a,raw,kind).outcome == Outcome.VALID_QUORUM


def test_isolation_and_frozen_contract_files_unchanged():
    tracked = subprocess.run(['git','ls-files','*.py'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.splitlines()
    active = [ROOT/p for p in tracked if not p.startswith(('tests/','verification/','isolated_bft717j/','isolated_bft717k/'))]
    assert all('isolated_bft717k' not in p.read_text(encoding='utf-8') for p in active)
    paths = ['isolated_bft717j','verification/tendermint717h','tests/fixtures/bft717j',
             'canonical_v3','services','blockchain.py','storage.py','protocol_v1_genesis.py',
             'protocol_v1_finality.py','wallet_signatures.py','config.py','validators.py']
    unchanged = subprocess.run(['git','diff','HEAD','--',*paths],cwd=ROOT,capture_output=True,text=True,check=True)
    assert unchanged.stdout == ''
