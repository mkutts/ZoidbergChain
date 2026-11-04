"""CLI ONLY, offline public evidence producer, not a signer API.

Random disposable keys exist only in process memory. No private keys/seeds are
written or printed. Running again REPLACES public identities, so frozen vectors
are reproduced by verification, not by regenerating secret identities.
"""
if __name__ != '__main__':
    raise ImportError('Standalone test evidence generator cannot be imported as a signer')

from copy import deepcopy
import json
import secrets

from eth_keys import keys
from eth_utils import keccak

from isolated_bft717j.wire import J, descriptor, identity, sha
from isolated_bft717k.manifest import construct_manifest
from verification.review717r import wire as w
from verification.review717r.model import tally, wire_fold
from verification.review717r.vectors import example
from verification.review717s.verify import preimage, user_bindings
from verification.review717s.fixtures import ROOT


def new_key():
    while True:
        try:
            return keys.PrivateKey(secrets.token_bytes(32))
        except ValueError:
            pass


validators = sorted([new_key() for _ in range(4)], key=lambda k: k.public_key.to_compressed_bytes())
creator, *reviewers = [new_key() for _ in range(7)]
outsider = new_key()
pub = lambda k: k.public_key.to_compressed_bytes().hex()
wallet = lambda k: identity(pub(k))[2:]
manifest = construct_manifest('task717k-test-journal', [pub(k) for k in validators])
agreement = descriptor('55' * 32)
context = dict(network='task717k-test-journal', genesis='11'*32, protocol=1,
               instance='22'*32, validators=manifest.commitment, membership=0, policy='44'*32)
bootstrap = '55'*32
ctx_bytes = b''.join(w.encode_type(t, context[k]) for k, t in w.CTX)
origin = w.tagged('origin', ctx_bytes + bytes.fromhex(bootstrap))
initial = w.tagged('initial-state', bytes.fromhex(origin + bootstrap))
rows = []


def sign(kind, obj, key, *, label, expected='ACCEPT_SIGNATURE_ONLY', override=None, **time):
    obj = deepcopy(obj)
    obj['signature'] = '00'*65
    pre = preimage(kind, obj, **time)
    digest = keccak(pre if override is None else override(pre))
    sig = key.sign_msg_hash(digest).to_bytes()
    obj['signature'] = (sig[:64] + bytes([sig[64]+27])).hex()
    raw = w.pack(kind, obj)
    row = dict(name=label, kind=kind, object=obj, hex=raw.hex(), length=len(raw), sha256=sha(raw),
               preimage_hex=pre.hex(), preimage_sha256=sha(pre), keccak256=keccak(pre).hex(),
               public_key=pub(key), wallet=wallet(key), expected=expected)
    if time:
        row['time_context'] = time
    rows.append(row)
    return obj


def message(height, parent, round, step, value, index, label, *, nil=0, vr=-1, justification='00'*32,
            key=None, override=None, expected='ACCEPT_SIGNATURE_ONLY'):
    obj = dict(context, height=height, parent=parent, round=round, value=value, nil=nil,
               step=step, validator=index, valid_round=vr, justification=justification, signature='00'*65)
    return sign('MESSAGE', obj, key or validators[index], label=label, override=override, expected=expected)


def unit(height, parent, previous, reading, events):
    samples = [sign('TIME_SAMPLE', dict(validator=i, reading=reading, signature='00'*65), validators[i],
        label=f'time-{height}-{i}', context=context, height=height, parent=parent, sequence=height)
        for i in range(3)]
    header = dict(context, height=height, parent=parent, previous_state=previous,
        events_root='00'*32, event_count=0, event_bytes=0, clock=dict(sequence=height, samples=samples))
    batch = w.body(header, events)
    value = w.tagged('batch', batch)
    proposal = message(height, parent, 0, 0, value, (height-1)%4, f'proposal-{height}')
    votes = [message(height, parent, 0, 2, value, i, f'precommit-{height}-{i}') for i in range(3)]
    proof = w.pack('PROOF', dict(proposal=proposal, precommits=votes))
    return dict(batch_hex=batch.hex(), batch_sha256=sha(batch), batch_id=value,
                proof_hex=proof.hex(), proof_sha256=sha(proof), proof_id=w.tagged('proof', proof)), value


op = example('OPEN') | context
op.update(submission='66'*16, original='77'*32, creator=wallet(creator), key=pub(creator),
          media_height=0, media_hash=context['genesis'], base_height=0, base_hash=origin,
          eligibility_root=initial, inventory='88'*32, nonce='99'*16)
op = sign('OPEN', op, creator, label='open')
sid = w.tagged('session', w.pack('OPEN', op)[:-65])
units = []
u, parent = unit(1, origin, initial, 300, [('OPEN', op)])
units.append(u)
previous = w.tagged('state', bytes.fromhex(initial + parent))
# Construct exact clock independently here, then unit() signs the same readings.
samples2 = [dict(validator=i, reading=305, signature='00'*65) for i in range(3)]
# Need actual signatures for the START time commitment; sign once, reusing bytes
# is deterministic RFC6979 for the same memory-only key and preimage.
samples2 = [sign('TIME_SAMPLE', s, validators[i], label=f'time-start-reference-{i}',
    context=context, height=2, parent=parent, sequence=2) for i, s in enumerate(samples2)]
time2 = w.tagged('clock', w.pack('CLOCK', dict(sequence=2, samples=samples2)))
start = dict(sid=sid, open_height=1, deadline=1506, time_id=time2)
epoch = dict(previous=0, current=1, lower=304, time_id=time2)
u, parent = unit(2, parent, previous, 305, [('START', start), ('EPOCH', epoch)])
units.append(u)
previous = w.tagged('state', bytes.fromhex(previous + parent))
votes, events, count = [], [], 0
fold = w.tagged('empty-votes', bytes.fromhex(sid))
counts = [[0,0,0,0], [0,0,0,0]]
eligibility = {wallet(k): 2 if i == 0 else 1 for i, k in enumerate(reviewers[:5])}
for dimension in (0,1):
    for i, key in enumerate(reviewers[:5]):
        v = example('VOTE') | context
        v.update(**{k: op[k] for k in ('submission','original','creator','media_height','media_hash',
                                      'base_height','base_hash')}, sid=sid, deadline=1506,
                 key=pub(key), dimension=dimension, choice=(0,0,0,1,2)[i], nonce=f'{i:032x}')
        v = sign('VOTE', v, key, label=f'vote-{dimension}-{i}')
        votes.append(v)
        index, status = len(events), eligibility[wallet(key)]
        admission = dict(vote=v, result=0, first_height=3, first_index=index, status=status, charged_epoch=1)
        events.append(('ADMISSION', admission))
        count += 1
        fold = wire_fold(fold, count, 3, index, v, status)
        counts[dimension][v['choice']] += 1
        counts[dimension][3] += status == 2
        if dimension == 0:
            events.append(('PARTICIPATION', dict(wallet=wallet(key), submission=op['submission'], epoch=1,
                status=status, first_height=3, first_index=index, used_after=1,
                cause=w.tagged('event', w.frame('ADMISSION', admission)))))
u, parent = unit(3, parent, previous, 310, events)
units.append(u)
previous = w.tagged('state', bytes.fromhex(previous + parent))
samples4 = [sign('TIME_SAMPLE', dict(validator=i, reading=1507, signature='00'*65), validators[i],
    label=f'time-close-reference-{i}', context=context, height=4, parent=parent, sequence=4) for i in range(3)]
time4 = w.tagged('clock', w.pack('CLOCK', dict(sequence=4, samples=samples4)))
close = dict(sid=sid, deadline=1506, freeze_height=4, count=count, fold=fold,
             originality=tally(counts[0]), admissibility=tally(counts[1]), outcome=1)
u, parent = unit(4, parent, previous, 1507, [('CLOSE', close),
    ('EPOCH', dict(previous=1,current=5,lower=1506,time_id=time4))])
units.append(u)
# A fresh, correctly signed quorum over a false CLOSE count is still not a
# valid application history. Do not expose the temporary signing helper.
row_count = len(rows)
bad_u, _ = unit(4, w.parse_body(bytes.fromhex(u['batch_hex']))[0]['parent'], previous, 1507,
    [('CLOSE', dict(close,count=9)), ('EPOCH', dict(previous=1,current=5,lower=1506,time_id=time4))])
del rows[row_count:]
cp = dict(context, height=4, batch=parent, proof=u['proof_id'])
media = dict(context, checkpoint=cp, sid=sid, close_height=4, close_batch=parent, close_index=0,
    close_id=w.tagged('event', w.frame('CLOSE', close)), submission=op['submission'], original=op['original'],
    creator=op['creator'], media_height=1, media_parent=op['media_hash'], count=count, fold=fold,
    originality=close['originality'], admissibility=close['admissibility'])

# All six dimension/choice combinations, independent pending vote and outsider.
for d in (0,1):
    for choice in (0,1,2):
        v = dict(votes[0], dimension=d, choice=choice)
        sign('VOTE', v, reviewers[0], label=f'choice-{d}-{choice}')
pending = sign('VOTE', dict(votes[0], key=pub(reviewers[5]), choice=1), reviewers[5], label='pending-not-finalized')

# Correctly signed foreign/bad-context messages and wrong-purpose signatures.
for field, value in [('network','foreign-network'), ('genesis','ab'*32), ('instance','cd'*32),
                     ('sid','ef'*32), ('submission','12'*16), ('dimension',1)]:
    sign('VOTE', dict(votes[0], **{field:value}), reviewers[0], label='signed-wrong-'+field, expected='REJECT')
sign('VOTE', votes[0], reviewers[0], label='wrong-user-purpose', expected='REJECT',
     override=lambda p: p.replace(b'user-VOTE', b'user-OPEN'))
h3 = w.parse_body(bytes.fromhex(units[2]['batch_hex']))[0]
value3, parent3 = units[2]['batch_id'], h3['parent']
pv = dict(votes=[message(3,parent3,0,1,value3,i,f'prevote-{i}') for i in range(3)])
pv_raw = w.pack('PV',pv)
nil_pv = dict(votes=[message(3,parent3,0,1,'00'*32,i,f'nil-prevote-{i}',nil=1) for i in range(3)])
for step in (1,2):
    message(3,parent3,0,step,'00'*32,0,f'nil-step-{step}',nil=1)
justified = message(3,parent3,1,0,value3,3,'justified-proposal',vr=0,justification=w.tagged('pv',pv_raw))
round1 = dict(proposal=justified,
    precommits=[message(3,parent3,1,2,value3,i,f'round-one-precommit-{i}') for i in range(3)])
message(3,parent3,0,2,value3,0,'unauthorized-validator',key=outsider,expected='REJECT')
message(3,parent3,0,2,'ff'*32,0,'contradictory-precommit')
message(3,parent3,0,2,value3,0,'personal-wrapped-validator',expected='REJECT',
        override=lambda p: b'\x19Ethereum Signed Message:\n'+str(len(p)).encode()+p)
message(3,parent3,0,2,value3,0,'media-domain-validator',expected='REJECT',
        override=lambda p: p.replace(b'ZCRJ717R\x00consensus\x00', b'zoidbergchain/bft-vote/v1'))

data = dict(classification='TEST ONLY; disposable public identities; no operational or private material',
    signature_algorithm='secp256k1 RFC6979 low-S r32||s32||v27/28; users EIP-191; validators raw Keccak256',
    reproduction='Frozen public verification is deterministic. CLI regeneration uses fresh memory-only keys.',
    manifest=manifest.value, agreement=agreement, agreement_sha256=sha(J(agreement)), context=context,
    bootstrap=bootstrap, origin=origin, initial_state=initial,
    public_identities=[dict(role=role,public_key=pub(k),wallet=wallet(k)) for role,k in
        [(f'validator-{i}',k) for i,k in enumerate(validators)]+[('creator',creator)]+
        [(f'reviewer-{i}',k) for i,k in enumerate(reviewers)]+[('unauthorized',outsider)]],
    records=rows, proofs=dict(pv_hex=pv_raw.hex(),nil_pv_hex=w.pack('PV',nil_pv).hex(),
                             round_one_hex=w.pack('PROOF',round1).hex()),
    negative_close=dict(unit=bad_u,header=w.parse_body(bytes.fromhex(bad_u['batch_hex']))[0],
        events=w.parse_body(bytes.fromhex(bad_u['batch_hex']))[1],
        proof=w.unpack('PROOF',bytes.fromhex(bad_u['proof_hex'])),expected='REJECT_APPLICATION_COMMITMENT'),
    history=dict(units=units,display_units=[dict(header=w.parse_body(bytes.fromhex(u['batch_hex']))[0],
        events=w.parse_body(bytes.fromhex(u['batch_hex']))[1], proof=w.unpack('PROOF',bytes.fromhex(u['proof_hex'])))
        for u in units],checkpoint=cp,checkpoint_hex=w.pack('CHECKPOINT',cp).hex(),
        media=media,media_hex=w.pack('MEDIA',media).hex(),fixture_eligibility=eligibility,
        actual_media_parent=[0,context['genesis']],pending_vote_hex=w.pack('VOTE',pending).hex(),
        expected='INCOMPLETE_HISTORY', fixture_count=10))
out = ROOT/'tests/fixtures/review717s_v1/vectors.json'
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n',encoding='utf-8')
print(json.dumps(dict(public_records=len(rows),batches=len(units),private_material_written=False)))
