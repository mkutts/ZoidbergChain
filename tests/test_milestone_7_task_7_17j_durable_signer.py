"""Isolated crypto/journal tests; all private keys random, memory/IPC only."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
import json
import multiprocessing as mp
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from isolated_bft717j.wire import (Context, J, parse, sha, descriptor, identity, envelope,
    signed, proof, prefix, signing_digest, slot_key, commitment, CURVE_ORDER, V3Error)
from isolated_bft717j.signer import Signer
from isolated_bft717j.custody import (TestKey, OwnershipConflict, Unavailable, CorruptState,
    StaleState, CryptoFailure, connection)
from verification.tendermint717h.model import Block

ROOT = Path(__file__).resolve().parents[1]
VECTORS = json.loads((ROOT / 'tests/fixtures/bft717j/vectors.json').read_text())


@pytest.fixture(scope='session')
def results():
    rows = []
    yield rows
    output = os.environ.get('BFT717J_RESULTS')
    if output:
        Path(output).write_text(json.dumps(dict(sqlite=sqlite3.sqlite_version,
            journal_mode='delete', synchronous=3, busy_timeout_ms=30000,
            scope='test-only bounded reducer; no power-loss or multi-host assurance',
            cases=rows), indent=2) + '\n', encoding='utf-8')


@pytest.fixture
def fixture(tmp_path):
    keys = sorted([TestKey() for _ in range(4)], key=lambda k: k.public_key)
    manifest = deepcopy(VECTORS['manifest'])
    manifest['network_id'] = 'task717j-test'
    manifest['validator_public_keys'] = [k.public_key for k in keys]
    ctx = Context(J(manifest), J(descriptor('55'*32)), '11'*32)
    blocks = J([asdict(Block('aa'*32, parent=ctx.genesis_hash)),
                asdict(Block('bb'*32, parent=ctx.genesis_hash)),
                asdict(Block('cc'*32, parent=ctx.genesis_hash, original=False))])
    return dict(root=tmp_path, keys=keys, ctx=ctx, blocks=blocks)


def message(f, step='prevote', value='aa'*32, index=1, height=1, round=0, vr=-1):
    ctx = f['ctx']
    p = dict(agreement_profile_digest=ctx.A, block_height=height, genesis_hash=ctx.genesis_hash,
        message_version=1, parent_hash=ctx.genesis_hash, round=round, validator_epoch=0,
        validator_id=identity(f['keys'][index].public_key), validator_set_commitment=ctx.C,
        block_hash=value, step=step)
    purpose = 'bft-proposal' if step == 'propose' else 'bft-vote'
    if step == 'propose':
        p['valid_round'] = vr
    return J(dict(domain='zoidbergchain/'+purpose+'/v1', network_id=ctx.network,
        object_type=purpose, payload=p, protocol='zoidbergchain', protocol_version=2))


def peer_signed(f, raw, index):
    # Disposable evidence producer, outside the honest signer under test.
    sig = Account.sign_message(encode_defunct(primitive=raw), f['keys'][index]._material).signature
    return J(dict(envelope=parse(raw), signature='0x'+bytes(sig).hex(), signature_scheme='personal_sign'))


def proposal(f, value='aa'*32):
    return peer_signed(f, message(f, 'propose', value, index=0), 0)


def polka(f, value='aa'*32):
    votes = [parse(peer_signed(f, message(f, value=value, index=i), i)) for i in (0, 2, 3)]
    votes.sort(key=lambda s: s['envelope']['payload']['validator_id'])
    return J(dict(certificate_version=1, commitment=commitment(votes[0]['envelope']), votes=votes))


def open_signer(f, *, bootstrap=False, index=1, **kwargs):
    return Signer(f['root']/f'{index}.db', f['root']/'custody', f['ctx'], f['keys'][index],
                  f['blocks'], bootstrap=bootstrap, **kwargs)


def ready(f, index=1, **kwargs):
    s = open_signer(f, bootstrap=True, index=index, **kwargs)
    if index != 0:
        s.start()
    return s


def sql_rows(f, index=1):
    with connection(f['root']/f'{index}.db') as c:
        return c.execute('SELECT * FROM slots').fetchall(), c.execute('SELECT * FROM outbox').fetchall()


@pytest.mark.parametrize('name', list(VECTORS['cases']))
def test_frozen_signing_vectors(name):
    v = VECTORS['cases'][name]
    e = v['envelope']
    ctx = Context(J(VECTORS['manifest']), J(VECTORS['agreement']), e['payload']['genesis_hash'])
    if name == 'network-b':
        m = deepcopy(VECTORS['manifest'])
        m['network_id'] = e['network_id']
        ctx = Context(J(m), ctx.agreement_bytes, ctx.genesis_hash)
    if name == 'set-b':
        m = deepcopy(VECTORS['manifest'])
        m['validator_public_keys'] = sorted(k['public_key'] for k in VECTORS['keys'] if k['scalar'] in (1,2,3,5))
        ctx = Context(J(m), ctx.agreement_bytes, ctx.genesis_hash)
    raw = v['preimage_ascii'].encode('ascii')
    assert envelope(raw, ctx) == e
    assert J(e) == raw and len(raw) == v['byte_length']
    assert sha(raw) == v['message_id']
    assert prefix(raw).hex() == v['prefix_hex']
    assert signing_digest(raw).hex() == v['signing_digest']
    assert signed(J(v['signed']), ctx) == v['signed']
    assert sha(J(v['signed'])) == v['signed_id']
    assert slot_key(e) == dict(height=1, round=e['payload']['round'], purpose=e['payload']['step'])
    # Frozen document tables, rather than a regenerated oracle alone, fix expectations.
    doc = (ROOT/'docs/milestone-7-bft-wire-and-signer-contract.md').read_text(encoding='utf-8')
    assert f"| {name} | {v['byte_length']} | `{v['message_id']}` | `{v['signing_digest']}` |" in doc
    assert f"| {name} | `{v['signed']['signature']}` | {v['signed_length']} | `{v['signed_id']}` |" in doc


@pytest.mark.parametrize('name', list(VECTORS['proofs']))
def test_five_frozen_proof_objects(name):
    ctx = Context(J(VECTORS['manifest']), J(VECTORS['agreement']), '11'*32)
    v = VECTORS['proofs'][name]
    raw = J(v['value'])
    assert proof(raw, ctx, 'q4' if name.startswith('q4') else name) == v['value']
    assert sha(raw) == v['digest'] and len(raw) == v['byte_length']
    assert '`' + v['digest'] + '`' in (ROOT/'docs/milestone-7-bft-wire-and-signer-contract.md').read_text(encoding='utf-8')


def test_independent_javascript_oracle_is_the_frozen_contract_source(tmp_path):
    doc = (ROOT/'docs/milestone-7-bft-wire-and-signer-contract.md').read_text(encoding='utf-8')
    source = re.search(r'```javascript task717i-independent-oracle\n(.*?)\n```', doc, re.S).group(1)
    oracle = ROOT/'verification/bft717j/oracle.cjs'
    assert oracle.read_text(encoding='utf-8') == source
    shutil.copyfile(oracle, tmp_path/'oracle.cjs')
    shutil.copyfile(ROOT/'tests/fixtures/bft717j/vectors.json', tmp_path/'vectors.json')
    run = subprocess.run(['node', str(tmp_path/'oracle.cjs')], capture_output=True, text=True, timeout=90)
    assert run.returncode == 0, run.stderr
    result = json.loads(run.stdout)
    assert result['cases'] == 21 and result['proofs'] == 5


@pytest.mark.parametrize('mutation', ['duplicate','whitespace','float','bool','missing','extra',
    'null','negative-zero','exponent','unicode','escape','bom','depth','oversize','version','purpose',
    'network','genesis','epoch','set','profile','identity','parent','integer-overflow'])
def test_closed_canonical_rejections(fixture, mutation):
    f = fixture
    raw = message(f)
    e = parse(raw)
    p = e['payload']
    if mutation == 'duplicate': raw = raw.replace(b'"round":0', b'"round":0,"round":0')
    elif mutation == 'whitespace': raw += b'\n'
    elif mutation == 'float': raw = raw.replace(b'"round":0', b'"round":0.0')
    elif mutation == 'bool': p['round'] = False; raw = J(e)
    elif mutation == 'missing': del p['block_hash']; raw = J(e)
    elif mutation == 'extra': p['request_id'] = 1; raw = J(e)
    elif mutation == 'null': p['round'] = None; raw = J(e)
    elif mutation == 'negative-zero': raw = raw.replace(b'"round":0', b'"round":-0')
    elif mutation == 'exponent': raw = raw.replace(b'"round":0', b'"round":0e0')
    elif mutation == 'unicode': raw = raw.replace(b'task717j-test', 't\u00e9st'.encode())
    elif mutation == 'escape': raw = raw.replace(b'task717j-test', b'\\u0074ask717j-test')
    elif mutation == 'bom': raw = b'\xef\xbb\xbf' + raw
    elif mutation == 'depth': raw = b'['*33+b'0'+b']'*33
    elif mutation == 'oversize': raw = b' '*2049
    elif mutation == 'version': e['protocol_version'] = 1; raw = J(e)
    elif mutation == 'purpose': e['domain'] = 'zoidbergchain/finality-attestation/v2'; raw = J(e)
    elif mutation == 'network': e['network_id'] = 'other-test'; raw = J(e)
    elif mutation == 'genesis': p['genesis_hash'] = '22'*32; raw = J(e)
    elif mutation == 'epoch': p['validator_epoch'] = 1; raw = J(e)
    elif mutation == 'set': p['validator_set_commitment'] = '22'*32; raw = J(e)
    elif mutation == 'profile': p['agreement_profile_digest'] = '22'*32; raw = J(e)
    elif mutation == 'identity': p['validator_id'] = '0x'+'00'*20; raw = J(e)
    elif mutation == 'parent': p['parent_hash'] = '22'*32; raw = J(e)
    elif mutation == 'integer-overflow': p['block_height'] = 9007199254740992; raw = json.dumps(e).encode()
    with pytest.raises(V3Error):
        envelope(raw, f['ctx'])


def test_high_s_and_no_fallback(fixture):
    f = fixture
    original = parse(proposal(f))
    sig = original['signature']
    original['signature'] = sig[:66] + f'{CURVE_ORDER-int(sig[66:130],16):064x}' + ('1c' if sig[-2:] == '1b' else '1b')
    signed(J(original), f['ctx'])
    original['envelope']['payload']['block_hash'] = 'bb'*32
    with pytest.raises(V3Error, match='signature_key'):
        signed(J(original), f['ctx'])
    original['signature_scheme'] = 'legacy'
    with pytest.raises(V3Error, match='signature_scheme'):
        signed(J(original), f['ctx'])


def test_proposal_and_durable_identical_retry(fixture):
    f = fixture
    m = message(f, 'propose', index=0)
    with ready(f, 0) as s:
        first = s.sign(m)
        assert first == s.sign(m)
        assert signed(first, f['ctx'])['envelope'] == parse(m)
        with pytest.raises(V3Error, match='CONFLICTING_SLOT'):
            s.sign(message(f, 'propose', 'bb'*32, 0))
    with open_signer(f, index=0) as s:
        assert s.sign(m) == first
        assert s.recover()['fence_generation'] == 2


def test_lock_pv_and_recovery(fixture):
    f = fixture
    with ready(f) as s:
        s.sign(message(f), proposal=proposal(f))
        with pytest.raises(V3Error):
            s.sign(message(f, 'precommit'), proposal=proposal(f))
        result = s.sign(message(f, 'precommit'), proposal=proposal(f), pv=polka(f))
        st = s.recover()
        assert st['locked'] == st['valid'] and st['locked']['block_hash'] == 'aa'*32
        assert st['locked']['round'] == 0 and st['phase'] == 'precommit'
        with pytest.raises(V3Error, match='CONFLICTING_SLOT'):
            s.sign(message(f, 'precommit', None))
        with pytest.raises(V3Error, match='INCOMPLETE_AGREEMENT_CONTEXT'):
            s.transition(locked=None, valid_round=0, height=2)
    with open_signer(f) as s:
        for _ in range(3):
            assert s.recover()['locked'] == st['locked']
        assert s.sign(message(f, 'precommit')) == result


def test_nil_vote_paths_and_missing_data(fixture):
    f = fixture
    with ready(f) as s:
        with pytest.raises(V3Error, match='prevote_guard'):
            s.sign(message(f, value=None), proposal=proposal(f))
        with pytest.raises(V3Error, match='INCOMPLETE_DATA'):
            s.sign(message(f, value=None), proposal=proposal(f, 'dd'*32))
        raw = s.sign(message(f, value=None), proposal=proposal(f, 'cc'*32))
        assert parse(raw)['envelope']['payload']['block_hash'] is None
        s.sign(message(f, 'precommit', None), pv=polka(f, None))
        st = s.recover()
        assert st['locked']['round'] == st['valid']['round'] == -1
        assert st['phase'] == 'precommit'


@pytest.mark.parametrize('bad', ['duplicate','signature','mixed','few','nil','other-value'])
def test_authenticated_evidence_required(fixture, bad):
    f = fixture
    with ready(f) as s:
        s.sign(message(f), proposal=proposal(f))
        pv = parse(polka(f))
        if bad == 'duplicate': pv['votes'][1] = pv['votes'][0]
        elif bad == 'signature': pv['votes'][0]['signature'] = '0x'+'00'*65
        elif bad == 'mixed': pv['votes'][0]['envelope']['payload']['round'] = 1
        elif bad == 'few': pv['votes'].pop()
        elif bad == 'nil': pv = parse(polka(f, None))
        elif bad == 'other-value': pv = parse(polka(f, 'bb'*32))
        with pytest.raises(V3Error):
            s.sign(message(f, 'precommit'), proposal=proposal(f), pv=J(pv))
        assert s.recover()['locked']['round'] == -1


@pytest.mark.parametrize('kind', ['round','height','unjustified','identity'])
def test_unavailable_agreement_context(fixture, kind):
    f = fixture
    with ready(f) as s:
        raw = message(f, round=1) if kind == 'round' else message(f, height=2) if kind == 'height' else (
            message(f, index=2) if kind == 'identity' else message(f, 'precommit'))
        with pytest.raises(V3Error):
            s.sign(raw)
        assert not sql_rows(f)[0]


def test_concurrent_identical_and_conflicting_connections(fixture):
    f = fixture
    with ready(f) as s:
        def call(value):
            try:
                return s.sign(message(f, value=value), proposal=proposal(f, value))
            except V3Error as exc:
                return exc.code
        with ThreadPoolExecutor(max_workers=8) as pool:
            identical = list(pool.map(call, ['aa'*32]*8))
            conflicts = list(pool.map(call, ['aa'*32, 'bb'*32]*8))
        assert len(set(identical)) == 1
        assert set(conflicts) == {identical[0], 'CONFLICTING_SLOT'}
        assert len(sql_rows(f)[0]) == len(sql_rows(f)[1]) == 1


def child_sign(f, index, action, boundary, pipe):
    def fault(name, c):
        if name == boundary:
            pipe.send(('boundary', name))
            pipe.recv()  # Parent really terminates the process at this exact window.
    try:
        with open_signer(f, index=index, fault=fault) as s:
            value = 'bb'*32 if action == 'conflicting' else 'aa'*32
            raw = message(f, 'precommit' if action == 'precommit' else 'prevote', value, index=index)
            result = s.sign(raw, proposal=proposal(f, value), pv=polka(f) if action == 'precommit' else None,
                            publish=lambda raw: pipe.send(('published', raw)))
            pipe.send(('result', result))
    except BaseException as exc:
        pipe.send(('error', type(exc).__name__, str(exc)))
    finally:
        pipe.close()


def spawn(f, action='prevote', boundary=None):
    context = mp.get_context('spawn')
    parent, child = context.Pipe()
    p = context.Process(target=child_sign, args=(f, 1, action, boundary, child))
    p.start()
    child.close()
    return p, parent


def receive(p, pipe):
    if not pipe.poll(35):
        p.terminate(); p.join(10)
        pytest.fail('child did not reach controlled boundary')
    return pipe.recv()


@pytest.mark.parametrize('boundary', ['before_reservation_commit','after_reservation_commit',
    'after_sign','before_signature_commit','after_signature_commit','before_release','after_publication',
    'during_lock_update'])
def test_real_process_crash_windows(fixture, boundary, results):
    f = fixture
    locking = boundary == 'during_lock_update'
    with ready(f) as s:
        if locking:
            s.sign(message(f), proposal=proposal(f))
    p, pipe = spawn(f, 'precommit' if locking else 'prevote', boundary)
    published = None
    try:
        event = receive(p, pipe)
        if boundary == 'after_publication':
            assert event[0] == 'published'
            published = event[1]
            event = receive(p, pipe)
        assert event == ('boundary', boundary)
        p.terminate(); p.join(15)
        assert p.exitcode is not None and p.exitcode != 0
    finally:
        if p.is_alive(): p.terminate(); p.join(10)
        pipe.close()
    rolled_back = boundary in ('before_reservation_commit','during_lock_update')
    with open_signer(f) as s:
        state = s.recover()
        if locking:
            assert state['locked']['round'] == -1  # Uncommitted paired update rolled back.
        rows, out = sql_rows(f)
        assert len(rows) == (1 if locking else 0 if rolled_back else 1)
        if not rolled_back:
            with pytest.raises(V3Error, match='CONFLICTING_SLOT'):
                s.sign(message(f, value='bb'*32), proposal=proposal(f, 'bb'*32))
        raw = message(f, 'precommit' if locking else 'prevote')
        result = s.sign(raw, proposal=proposal(f), pv=polka(f) if locking else None)
        assert s.sign(raw) == result
        if published is not None: assert result == published
        if locking: assert s.recover()['locked']['round'] == 0
        assert s.recover()['pending_slot'] is None
    results.append(dict(case=boundary, mechanism='parent terminated independent process',
        passed=True, precommit_rollback=rolled_back, exact_retry=True,
        publication_observed=published is not None))


@pytest.mark.parametrize('boundary', ['after_reservation_commit','after_sign','after_signature_commit'])
def test_crash_preserves_committed_lock_and_valid_pair(fixture, boundary, results):
    f = fixture
    with ready(f) as s:
        s.sign(message(f), proposal=proposal(f))
    p, pipe = spawn(f, 'precommit', boundary)
    try:
        assert receive(p, pipe) == ('boundary', boundary)
        p.terminate(); p.join(15)
    finally:
        if p.is_alive(): p.terminate(); p.join(10)
        pipe.close()
    with open_signer(f) as s:
        state = s.recover()
        assert state['locked'] == state['valid'] and state['locked']['block_hash'] == 'aa'*32
        assert state['locked']['round'] == 0 and state['phase'] == 'precommit'
        with pytest.raises(V3Error, match='CONFLICTING_SLOT'):
            s.sign(message(f, 'precommit', None))
        result = s.sign(message(f, 'precommit'))
        assert s.sign(message(f, 'precommit')) == result
    results.append(dict(case='lock_'+boundary, passed=True,
                        mechanism='real process termination', lock_and_valid_survived=True))


def test_exclusive_owner_processes_and_reacquisition(fixture, results):
    f = fixture
    with ready(f) as s:
        with pytest.raises(OwnershipConflict): open_signer(f)
        p, pipe = spawn(f)
        try:
            event = receive(p, pipe)
            assert event[0:2] == ('error', 'OwnershipConflict')
            p.join(10)
        finally:
            if p.is_alive(): p.terminate(); p.join(10)
            pipe.close()
    with open_signer(f) as s:
        assert s.recover()['fence_generation'] == 2
    with pytest.raises(Unavailable): s.sign(message(f), proposal=proposal(f))
    results.append(dict(case='process_owner_conflict_and_transfer', passed=True))


@pytest.mark.parametrize('conflicting', [False, True])
def test_two_process_signing_attempts(fixture, conflicting, results):
    f = fixture
    with ready(f): pass
    first, first_pipe = spawn(f, boundary='after_reservation_commit')
    second = second_pipe = None
    try:
        assert receive(first, first_pipe) == ('boundary', 'after_reservation_commit')
        second, second_pipe = spawn(f, 'conflicting' if conflicting else 'prevote')
        assert receive(second, second_pipe)[0:2] == ('error', 'OwnershipConflict')
        second.join(10)
        first_pipe.send('continue')
        published = receive(first, first_pipe)
        result = receive(first, first_pipe)
        assert published[0] == 'published' and result == ('result', published[1])
        first.join(10)
        assert first.exitcode == 0
    finally:
        for proc, channel in ((first, first_pipe), (second, second_pipe)):
            if proc is not None and proc.is_alive(): proc.terminate(); proc.join(10)
            if channel is not None: channel.close()
    with open_signer(f) as s:
        assert s.sign(message(f)) == published[1]
        with pytest.raises(V3Error, match='CONFLICTING_SLOT'):
            s.sign(message(f, value='bb'*32), proposal=proposal(f, 'bb'*32))
    results.append(dict(case='two_process_'+('conflict' if conflicting else 'duplicate'),
                        passed=True, successful_publishers=1))


@pytest.mark.parametrize('boundary', ['after_reservation_commit','after_signature_commit'])
def test_ambiguous_commit_acknowledgement(fixture, boundary, results):
    f = fixture
    def fail(name, c):
        if name == boundary: raise OSError('injected lost commit acknowledgement')
    with ready(f) as s:
        s.fault = fail
        with pytest.raises(OSError): s.sign(message(f), proposal=proposal(f))
        with pytest.raises(Unavailable): s.sign(message(f), proposal=proposal(f))
        s.fault = None
        state = s.recover()
        assert (state['pending_slot'] is None) == (boundary == 'after_signature_commit')
        first = s.sign(message(f), proposal=proposal(f))
        assert s.sign(message(f)) == first
    results.append(dict(case='ambiguous_'+boundary, passed=True, no_release_on_error=True))


def test_busy_and_unavailable_until_recovery(fixture, results):
    f = fixture
    with ready(f, busy_ms=1) as s:
        with connection(s.path) as c:
            c.execute('BEGIN IMMEDIATE')
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                s.sign(message(f), proposal=proposal(f))
        with pytest.raises(Unavailable): s.sign(message(f), proposal=proposal(f))
        s.recover()
        s.sign(message(f), proposal=proposal(f))
    results.append(dict(case='sqlite_busy', passed=True))


@pytest.mark.parametrize('boundary', ['before_reservation_commit','before_signature_commit'])
@pytest.mark.parametrize('mode', ['io','full','commit-denied','commit-busy'])
def test_storage_faults_before_commit(fixture, mode, boundary, results):
    f = fixture
    reader = None
    def fail(name, c):
        nonlocal reader
        if name != boundary: return
        if mode == 'io': raise sqlite3.OperationalError('injected disk I/O error')
        if mode == 'full':
            # Real SQLITE_FULL, after reservation rows were written but before commit.
            pages = c.execute('PRAGMA page_count').fetchone()[0]
            c.execute(f'PRAGMA max_page_count={pages}')
            c.execute('CREATE TABLE pressure(data BLOB)')
            c.execute('INSERT INTO pressure VALUES(zeroblob(1000000))')
        if mode == 'commit-denied':
            c.set_authorizer(lambda action, arg, *rest: sqlite3.SQLITE_DENY
                if action == sqlite3.SQLITE_TRANSACTION and arg == 'COMMIT' else sqlite3.SQLITE_OK)
        if mode == 'commit-busy':
            reader = sqlite3.connect(s.path, isolation_level=None)
            reader.execute('BEGIN')
            reader.execute('SELECT * FROM head').fetchall()
    with ready(f, busy_ms=1) as s:
        s.fault = fail
        try:
            with pytest.raises(sqlite3.Error) as error: s.sign(message(f), proposal=proposal(f))
            if mode != 'io':
                expected_code = {'full': sqlite3.SQLITE_FULL, 'commit-denied': sqlite3.SQLITE_AUTH,
                                 'commit-busy': sqlite3.SQLITE_BUSY}[mode]
                assert error.value.sqlite_errorcode == expected_code
        finally:
            if reader is not None: reader.close()
        rows, outbox = sql_rows(f)
        assert len(rows) == (0 if boundary == 'before_reservation_commit' else 1)
        assert not outbox
        s.fault = None
        s.recover()
        s.sign(message(f), proposal=proposal(f))
    results.append(dict(case=mode+'_'+boundary, passed=True,
                        reservation_rolled_back=boundary == 'before_reservation_commit',
                        real_sqlite_error=mode != 'io',
                        sqlite_errorcode=getattr(error.value, 'sqlite_errorcode', None)))


@pytest.mark.parametrize('corruption', ['blob','head','slot','outbox','event','state','missing-db','wrong-genesis','wal'])
def test_tamper_and_missing_store_refuse(fixture, corruption, results):
    f = fixture
    with ready(f) as s:
        s.sign(message(f), proposal=proposal(f))
        if corruption not in ('missing-db','wrong-genesis','wal'):
            with connection(s.path) as c:
                c.execute('BEGIN IMMEDIATE')
                if corruption == 'blob': c.execute("UPDATE blobs SET raw=x'7b7d' WHERE kind='receipt'")
                elif corruption == 'head': c.execute("UPDATE head SET record=x'7b7d'")
                elif corruption == 'slot':
                    c.execute("UPDATE slots SET slot_id=(SELECT digest FROM blobs WHERE kind='state' LIMIT 1)")
                elif corruption == 'outbox': c.execute('DELETE FROM outbox')
                elif corruption == 'event': c.execute('DELETE FROM events WHERE sequence=2')
                elif corruption == 'state': c.execute("UPDATE blobs SET raw=x'7b7d' WHERE kind='state'")
                c.commit()
            with pytest.raises((CorruptState, sqlite3.Error)): s.recover()
            with pytest.raises(Unavailable): s.sign(message(f))
    if corruption == 'missing-db': (f['root']/'1.db').unlink()
    elif corruption == 'wrong-genesis':
        f = dict(f, ctx=Context(f['ctx'].manifest_bytes, f['ctx'].agreement_bytes, '22'*32))
        # Keep the old catalogue deliberately: either pinned-context check must reject.
    elif corruption == 'wal':
        c = sqlite3.connect(f['root']/'1.db')
        c.execute('PRAGMA journal_mode=WAL'); c.close()
    with pytest.raises((Unavailable, sqlite3.Error, V3Error)): open_signer(f)
    if corruption == 'missing-db': assert not (f['root']/'1.db').exists()
    results.append(dict(case='corrupt_'+corruption, passed=True))


def test_stale_backup_and_joint_rollback_limit(fixture, results):
    f = fixture
    with ready(f): pass
    db = f['root']/'1.db'
    witness = f['root']/'custody'/(f['keys'][1].public_key+'.witness.db')
    backup, witness_backup = f['root']/'old.db', f['root']/'old-witness.db'
    shutil.copyfile(db, backup); shutil.copyfile(witness, witness_backup)
    with open_signer(f) as s:
        s.sign(message(f), proposal=proposal(f))
    shutil.copyfile(backup, db)
    with pytest.raises(StaleState): open_signer(f)
    # Deliberate impossibility witness: rolling BOTH files back is locally invisible.
    shutil.copyfile(witness_backup, witness)
    with open_signer(f) as s:
        s.sign(message(f, value='bb'*32), proposal=proposal(f, 'bb'*32))
    results.append(dict(case='signer_only_rollback', detected=True, passed=True))
    results.append(dict(case='joint_rollback', detected=False, expected_limitation=True,
                        scope='separate surviving nonrollbackable custody required', passed=True))


def test_crypto_failure_distinct_from_sqlite(fixture, monkeypatch, results):
    f = fixture
    with ready(f) as s:
        monkeypatch.setattr(s.key, '_sign_reserved', lambda *a: '0x'+'00'*65)
        with pytest.raises(CryptoFailure): s.sign(message(f), proposal=proposal(f))
        assert len(sql_rows(f)[0]) == 1 and not sql_rows(f)[1]
        with pytest.raises(Unavailable): s.sign(message(f), proposal=proposal(f))
    results.append(dict(case='crypto_failure', passed=True, classification='CryptoFailure'))


def test_semantic_tampering_even_with_recomputed_hashes(fixture, results):
    f = fixture
    with ready(f) as s:
        s.sign(message(f), proposal=proposal(f))
        with connection(s.path) as c:
            c.execute('BEGIN IMMEDIATE')
            seq, eid, sid = c.execute('SELECT * FROM events ORDER BY sequence DESC LIMIT 1').fetchone()
            state = parse(c.execute('SELECT raw FROM blobs WHERE digest=?', (sid,)).fetchone()[0])
            state['locked'] = dict(block_hash='bb'*32, round=0, proposal_id='00'*32,
                                   prevote_certificate_id='00'*32)
            new_sid = sha(J(state))
            c.execute('INSERT INTO blobs VALUES(?,?,?)', (new_sid, 'state', J(state)))
            event = parse(c.execute('SELECT raw FROM blobs WHERE digest=?', (eid,)).fetchone()[0])
            event['after_state'] = new_sid
            new_eid = sha(J(event))
            c.execute('INSERT INTO blobs VALUES(?,?,?)', (new_eid, 'event', J(event)))
            c.execute('UPDATE events SET event_id=?,state_id=? WHERE sequence=?', (new_eid,new_sid,seq))
            head = dict(record_version=1,namespace_id=s.ns,sequence=seq,event_id=new_eid,state_id=new_sid)
            c.execute('UPDATE head SET record=?', (J(head),))
            c.commit()
        with pytest.raises(CorruptState): s.recover()
    results.append(dict(case='semantic_state_tamper_rehashed', passed=True))


def test_missing_support_source_and_foreign_keys(fixture, results):
    f = fixture
    with ready(f) as s:
        s.sign(message(f), proposal=proposal(f))
        with connection(s.path) as c:
            with pytest.raises(sqlite3.IntegrityError): c.execute('DELETE FROM slots')
            c.execute('DELETE FROM blobs WHERE digest=?', (sha(proposal(f)),))
        with pytest.raises(CorruptState): s.recover()
    results.append(dict(case='missing_authenticated_source', passed=True))


def test_height_and_round_transitions_are_gated_without_writes(fixture, results):
    f = fixture
    with ready(f) as s:
        before = s.recover()
        for operation in ('height_advance','round_advance','unlock','late_valid','finalize','timeout'):
            with pytest.raises(V3Error, match='INCOMPLETE_AGREEMENT_CONTEXT'):
                s.transition(operation, evidence={})
            assert s.recover() == before
    results.append(dict(case='height_round_lock_adapters', passed=True,
        outcome='blocked before mutation; no height-transition crash claim'))


def test_witness_failure_and_generation_revocation(fixture, results):
    f = fixture
    with ready(f) as s:
        def fail(name, c):
            if name == 'after_witness_commit': raise OSError('injected lost witness acknowledgement')
        s.fault = fail
        with pytest.raises(OSError): s.sign(message(f), proposal=proposal(f))
        assert not sql_rows(f)[1]
        s.fault = None
        s.recover()
        s.sign(message(f), proposal=proposal(f))
        with s.witness.connect() as c:
            c.execute('UPDATE witness SET generation=generation+1')
        with pytest.raises(StaleState): s.sign(message(f))
        with pytest.raises(Unavailable): s.sign(message(f))
        with pytest.raises(StaleState): s.recover()
    # Explicit new owner records FENCE and can only return the old exact bytes.
    with open_signer(f) as s:
        s.sign(message(f))
    results.append(dict(case='witness_ack_and_revoked_generation', passed=True))


def test_same_key_namespace_switch_and_missing_witness_refused(fixture):
    f = fixture
    with ready(f): pass
    db = f['root']/'1.db'
    db.unlink()
    # A surviving witness forbids treating the identity as new even without its DB.
    with pytest.raises(V3Error, match='already_initialized'): open_signer(f, bootstrap=True)
    assert not db.exists()


def test_proposal_nil_and_boundaries(fixture):
    f = fixture
    with pytest.raises(V3Error, match='nil_proposal'):
        envelope(message(f, 'propose', None, index=0), f['ctx'])
    for raw in (message(f, round=2147483648), message(f, height=0),
                message(f, 'propose', index=0, vr=0)):
        with pytest.raises(V3Error): envelope(raw, f['ctx'])
    a, b = message(f, height=1), message(f, height=2)
    assert sha(a) != sha(b) and signing_digest(a) != signing_digest(b)


def test_local_witness_joint_rollback_cannot_downgrade_live_owner(fixture):
    f = fixture
    with ready(f): pass
    db = f['root']/'1.db'
    witness = f['root']/'custody'/(f['keys'][1].public_key+'.witness.db')
    old_db, old_witness = db.read_bytes(), witness.read_bytes()
    with open_signer(f) as s:
        s.sign(message(f), proposal=proposal(f))
        db.write_bytes(old_db); witness.write_bytes(old_witness)
        with pytest.raises(StaleState): s.recover()
        with pytest.raises(Unavailable): s.sign(message(f))


def test_pending_reservation_blocks_successor_and_uses_retained_evidence(fixture, results):
    f = fixture
    with ready(f) as s:
        def fail(name, c):
            if name == 'after_reservation_commit': raise OSError('injected stop before signing')
        s.fault = fail
        with pytest.raises(OSError): s.sign(message(f), proposal=proposal(f))
        s.fault = None
        state = s.recover()
        assert state['pending_slot'] == dict(height=1, round=0, purpose='prevote')
        with pytest.raises(V3Error, match='pending_or_fault'):
            s.sign(message(f, 'precommit'), proposal=proposal(f), pv=polka(f))
        assert s.recover() == state
        result = s.sign(message(f))  # Caller no longer supplies proposal/data/PV.
        assert result == s.sign(message(f))
    results.append(dict(case='pending_blocks_successors', passed=True, retained_sources_sufficient=True))


def test_signed_retry_never_invokes_key_and_does_not_mutate_history(fixture, monkeypatch):
    f = fixture
    with ready(f) as s:
        result = s.sign(message(f), proposal=proposal(f))
        state = s.recover()
        def forbidden(*args): raise AssertionError('stored retry reached key')
        monkeypatch.setattr(s.key, '_sign_reserved', forbidden)
        assert s.sign(message(f)) == result
        assert s.recover() == state


def test_mutated_parsed_fixture_cannot_authorize_validity(fixture):
    f = fixture
    with ready(f) as s:
        parsed = s.blocks
        parsed['cc'*32]['original'] = True
        with pytest.raises(V3Error, match='prevote_guard'):
            s.sign(message(f, value='cc'*32), proposal=proposal(f, 'cc'*32))
        result = s.sign(message(f, value=None), proposal=proposal(f, 'cc'*32))
        assert parse(result)['envelope']['payload']['block_hash'] is None


def test_rollback_failure_still_closes_connection_and_releases_writer(fixture, monkeypatch, results):
    f = fixture
    with ready(f) as s:
        original_connect = sqlite3.connect
        class RollbackFailure(sqlite3.Connection):
            def rollback(self):
                raise sqlite3.OperationalError('injected rollback I/O failure')
        monkeypatch.setattr(sqlite3, 'connect', lambda *args, **kwargs:
            original_connect(*args, **kwargs, factory=RollbackFailure))
        with pytest.raises(sqlite3.OperationalError, match='rollback I/O'):
            with connection(s.path) as c:
                c.execute('BEGIN IMMEDIATE')
                c.execute('UPDATE head SET record=record')
                raise RuntimeError('operation failed before commit')
        # Keep c referenced: garbage collection cannot hide a leaked connection.
        with pytest.raises(sqlite3.ProgrammingError, match='closed'):
            c.execute('SELECT 1')
        check = original_connect(s.path, isolation_level=None, timeout=0.001)
        try:
            check.execute('BEGIN IMMEDIATE')
            check.rollback()
        finally:
            check.close()
    results.append(dict(case='rollback_failure_cleanup', passed=True, connection_closed=True))


@pytest.mark.parametrize('changed', ['network','genesis','set','profile'])
def test_restored_authority_context_cannot_be_rebound(fixture, changed):
    f = fixture
    with ready(f): pass
    m, d, genesis = f['ctx'].manifest, parse(f['ctx'].agreement_bytes), f['ctx'].genesis_hash
    if changed == 'network': m['network_id'] = 'task717j-test-other'
    elif changed == 'genesis': genesis = '22'*32
    elif changed == 'set':
        m['validator_public_keys'][0] = TestKey().public_key
        m['validator_public_keys'].sort()
    elif changed == 'profile': d = descriptor('66'*32)
    ctx = Context(J(m), J(d), genesis)
    blocks = parse(f['blocks'], 65536)
    for b in blocks: b['parent'] = genesis
    changed_f = dict(f, ctx=ctx, blocks=J(blocks))
    with pytest.raises(CorruptState): open_signer(changed_f)


@pytest.mark.parametrize('changed', ['unsorted','duplicate','point','bool','extra'])
def test_manifest_requires_exact_static_authority(fixture, changed):
    f = fixture
    m = f['ctx'].manifest
    if changed == 'unsorted': m['validator_public_keys'].reverse()
    elif changed == 'duplicate': m['validator_public_keys'][1] = m['validator_public_keys'][0]
    elif changed == 'point': m['validator_public_keys'][0] = '02'+'ff'*32
    elif changed == 'bool': m['byzantine_fault_budget'] = True
    elif changed == 'extra': m['administrator'] = 'test'
    with pytest.raises(V3Error): Context(J(m), f['ctx'].agreement_bytes, f['ctx'].genesis_hash)


def test_missing_witness_and_physical_corruption_do_not_bootstrap(fixture, results):
    f = fixture
    with ready(f) as s:
        s.sign(message(f), proposal=proposal(f))
    witness = f['root']/'custody'/(f['keys'][1].public_key+'.witness.db')
    witness.unlink()
    with pytest.raises(sqlite3.OperationalError): open_signer(f)
    assert not witness.exists()
    with open(f['root']/'1.db', 'r+b') as stream:
        stream.write(b'not a sqlite header')
    with pytest.raises(sqlite3.DatabaseError): open_signer(f)
    results.append(dict(case='missing_witness_physical_corruption', passed=True))


def test_no_active_runtime_imports_or_model_fixture_changes():
    tracked = subprocess.run(['git','ls-files','*.py'], cwd=ROOT, capture_output=True,
                             text=True, check=True).stdout.splitlines()
    # 7.17K is another explicitly inert test package, not an active node caller.
    active = [ROOT/p for p in tracked if not p.startswith(('tests/','verification/','isolated_bft717k/','isolated_g2717m/'))]
    assert all('isolated_bft717j' not in p.read_text(encoding='utf-8') for p in active)
    paths = ['verification/tendermint717h', 'tests/test_milestone_7_task_7_17h_tendermint_model.py',
             'canonical_v3', 'wallet_signatures.py', 'storage.py', 'blockchain.py', 'services']
    unchanged = subprocess.run(['git','diff','HEAD','--',*paths], cwd=ROOT,
                               capture_output=True, text=True, check=True)
    assert unchanged.stdout == ''


def test_sqlite_configuration_and_initialization_refusal(fixture):
    f = fixture
    with ready(f) as s:
        with s.connect() as c:
            assert c.execute('PRAGMA journal_mode').fetchone()[0] == 'delete'
            assert c.execute('PRAGMA synchronous').fetchone()[0] == 3
            assert c.execute('PRAGMA foreign_keys').fetchone()[0] == 1
            assert c.execute('PRAGMA busy_timeout').fetchone()[0] == 30000
    with pytest.raises(V3Error, match='already_initialized'): open_signer(f, bootstrap=True)
