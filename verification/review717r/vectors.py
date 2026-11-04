"""Reproducible byte fixtures. Zero signatures are deliberate INVALID placeholders.

No signatures or keys are generated. Positive/negative refer to user choices,
not successful signature authentication. Application tests supply explicit facts.
"""
from copy import deepcopy
import json
from pathlib import Path

from .model import CONTEXT, tally, wire_fold
from .wire import SCHEMAS, ENUM, KINDS, pack, frame, body, tagged, hash_bytes, user_preimage, time_preimage

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'tests/fixtures/review717r_v1'


def default_type(t, maximum=False):
    if isinstance(t, int):
        return '55'*t
    if isinstance(t, tuple):
        return [example(t[1], maximum) for _ in range(t[3])]
    if t in SCHEMAS:
        return example(t, maximum)
    if t == 'nid':
        return 'n'*64 if maximum else CONTEXT['network']
    if t == 'chunk':
        return 'ab'*(8140 if maximum else 8)
    _, lo, hi = ENUM[t]
    return hi if maximum else lo


def example(name, maximum=False):
    obj = {k: default_type(t, maximum) for k, t in SCHEMAS[name]}
    if all(k in obj for k in CONTEXT):
        obj.update(CONTEXT)
        if maximum:
            obj['network'] = 'n'*64
    if 'signature' in obj:
        obj['signature'] = '00'*65  # Invalid by definition; never signed.
    return obj


def fixture_objects():
    o = example('OPEN')
    v = example('VOTE')
    sid = tagged('session', pack('OPEN', o)[:-65])
    o.update(media_hash=CONTEXT['genesis'], key='02'+'66'*32)
    # Recompute SID after immutable OPEN payload is finalized.
    sid = tagged('session', pack('OPEN', o)[:-65])
    v.update(sid=sid, key='03'+'77'*32, deadline=1502, base_height=0,
             base_hash='00'*32, media_height=0, media_hash=CONTEXT['genesis'])
    positive = deepcopy(v)
    negative = dict(v, choice=1)
    unsure = dict(v, choice=2)
    clock = example('CLOCK')
    clock['sequence'] = 1
    clock['samples'] = [dict(validator=i, reading=300, signature='00'*65) for i in range(3)]
    header = example('HEADER')
    header.update(height=1, parent='00'*32, previous_state='88'*32, clock=clock)
    t = tally((7, 3, 1, 1))
    empty = tagged('empty-votes', bytes.fromhex(sid))
    close = dict(sid=sid, deadline=1502, freeze_height=4, count=1,
                 fold=wire_fold(empty, 1, 3, 0, v, 2), originality=t,
                 admissibility=tally((0, 0, 5, 1)), outcome=0)
    admission = dict(vote=v, result=0, first_height=3, first_index=0, status=2, charged_epoch=1)
    cp = example('CHECKPOINT')
    cp.update(height=4, batch='99'*32, proof='aa'*32)
    media = example('MEDIA')
    media.update(checkpoint=cp, sid=sid, close_height=4, close_batch='99'*32,
                 close_index=0, close_id=tagged('event', frame('CLOSE', close)),
                 originality=t, admissibility=tally((5, 0, 0, 1)), count=10, fold=close['fold'])
    message = example('MESSAGE')
    message.update(height=4, round=0, value='99'*32, parent='98'*32, nil=0,
                   valid_round=-1, justification='00'*32, step=0, validator=3)
    proof = dict(proposal=message, precommits=[dict(message, step=2, validator=i) for i in range(3)])
    rows = [('open', 'OPEN', o, 'STRUCTURAL_ONLY'),
            ('positive', 'VOTE', positive, 'STRUCTURAL_ONLY'),
            ('negative', 'VOTE', negative, 'STRUCTURAL_ONLY'),
            ('unsure', 'VOTE', unsure, 'STRUCTURAL_ONLY'),
            ('duplicate', 'ADMISSION', dict(admission, result=1), 'DUPLICATE_IF_AUTHENTICATED'),
            ('invalid_signature', 'VOTE', v, 'INVALID_SIGNATURE'),
            ('admission', 'ADMISSION', admission, 'ADMIT_IF_AUTHENTICATED'),
            ('mandatory_close', 'CLOSE', close, 'STRUCTURAL_ONLY'),
            ('tally', 'TALLY', t, 'PASS'),
            ('quota_exhaustion', 'ADMISSION', dict(admission, result=8, status=0,
                                                  first_height=0, first_index=0, charged_epoch=0), 'QUOTA_EXHAUSTED'),
            ('epoch', 'EPOCH', dict(previous=0, current=5, lower=1502, time_id='bb'*32), 'STRUCTURAL_ONLY'),
            ('checkpoint', 'CHECKPOINT', cp, 'STRUCTURAL_ONLY'),
            ('media_binding', 'MEDIA', media, 'STRUCTURAL_ONLY_INDEPENDENT_EXAMPLE'),
            ('wrong_network', 'VOTE', dict(v, network='foreign-network'), 'WRONG_NETWORK'),
            ('missing_evidence', 'REFERENCE', dict(kind=0, object_id='cc'*32, length=100,
                 height=3, batch='dd'*32, index=0), 'INCOMPLETE_EVIDENCE'),
            ('conflicting_proof', 'PROOF', proof, 'STRUCTURAL_ONLY_INVALID_SIGNATURES'),
            ('unsupported_policy', 'POLICY', dict(old='44'*32, new='ff'*32, result=255), 'UNSUPPORTED_POLICY')]
    return rows, header


def build():
    rows, header = fixture_objects()
    vectors = []
    for label, kind, obj, expected in rows:
        raw = pack(kind, obj)
        row = dict(name=label, kind=kind, object=obj, hex=raw.hex(), length=len(raw),
                   sha256=hash_bytes(raw), object_id=tagged(kind.lower(), raw), expected=expected)
        if kind in ('OPEN', 'VOTE'):
            pre = user_preimage(kind, obj)
            row.update(signing_preimage_hex=pre.hex(), signing_preimage_sha256=hash_bytes(pre))
        vectors.append(row)
    sample = header['clock']['samples'][0]
    pre = time_preimage(CONTEXT, 1, header['parent'], 1, sample)
    batch = body(header, [('OPEN', rows[0][2])])
    return dict(classification='INERT; no new signatures; source/policy/BFT authentication not implemented',
                vectors=vectors, batch=dict(header=header, events=[['OPEN', rows[0][2]]],
                hex=batch.hex(), length=len(batch), sha256=hash_bytes(batch)),
                time_preimage=dict(hex=pre.hex(), sha256=hash_bytes(pre)))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data = build()
    schema = dict(schemas=SCHEMAS, enums=ENUM, kinds=KINDS,
                  maxima={k: len(pack(k, example(k, True))) for k in SCHEMAS})
    (OUT/'vectors.json').write_text(json.dumps(data, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    (OUT/'schema.json').write_text(json.dumps(schema, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    print(json.dumps(dict(vectors=len(data['vectors']), maxima=schema['maxima']), indent=2))


if __name__ == '__main__':
    main()
