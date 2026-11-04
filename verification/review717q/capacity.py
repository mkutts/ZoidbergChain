"""Exact diagnostic framing, not a proposed production wire protocol.

The 1024-byte header is an 80-byte diagnostic header and zero reservation.
Events are compact ASCII JSON with uint32 lengths. Certificates are external.
No cryptographic, parser-depth, BFT performance or durable-disk claim follows.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
import struct

from verification.review717p.model import canonical
from verification.review717p.workload import structural_vote

INPUT = json.loads(Path(__file__).with_name('inputs.json').read_text())
U = 9007199254740991


def maximum_vote():
    v = deepcopy(structural_vote())
    v['payload']['network_id'] = 'n' * 64
    v['payload']['eligibility_journal_height'] = U
    return v


def vote_event(v=None):
    return dict(kind='VOTE', payload=dict(signed_vote=v or structural_vote()))


def structural_bounds(v):
    """O/I closed shape/bounds only. Placeholder points/signatures are NOT verified."""
    example = structural_vote()
    if type(v) is not dict or set(v) != set(example):
        raise ValueError('signed shape')
    p = v['payload']
    if type(p) is not dict or set(p) != set(example['payload']):
        raise ValueError('payload shape')
    for k, x in p.items():
        if k == 'network_id':
            good = type(x) is str and re.fullmatch(r'[a-z0-9][a-z0-9-]{2,63}', x)
        elif k in ('eligibility_media_height', 'eligibility_journal_height', 'session_close_height'):
            good = type(x) is int and 0 <= x <= U
        elif k == 'dimension':
            good = x in ('originality', 'admissibility')
        elif k == 'choice':
            good = x in (('original', 'not_original', 'unsure') if p['dimension'] == 'originality'
                         else ('admissible', 'not_admissible', 'unsure'))
        elif k in ('creator_wallet', 'reviewer_wallet'):
            good = type(x) is str and re.fullmatch(r'0x[0-9a-f]{40}', x)
        elif k == 'reviewer_public_key':
            good = type(x) is str and re.fullmatch(r'0[23][0-9a-f]{64}', x)
        elif k in ('submission_id', 'vote_nonce'):
            good = type(x) is str and re.fullmatch(r'[0-9a-f]{32}', x)
        elif k.endswith('_hash') or k.endswith('_digest') or k in ('original_media_sha256', 'review_session_id'):
            good = type(x) is str and re.fullmatch(r'[0-9a-f]{64}', x)
        else:
            good = type(x) is type(example['payload'][k]) and x == example['payload'][k]
        if not good:
            raise ValueError('field bound: ' + k)
    if v['signature_scheme'] != 'personal_sign' or not isinstance(v['signature'], str) or not re.fullmatch(r'0x[0-9a-f]{130}', v['signature']):
        raise ValueError('signature bound')
    if len(canonical(p)) > 2048 or len(canonical(v)) > INPUT['signed_vote_max_bytes']:
        raise ValueError('vote bytes')


def encode(events, *, height=1, parent=bytes(32), cpu=True, fixed24=False, available=True):
    """Validate size/work/order before symbolic agreement. All sources must exist.

    Control events are opaque diagnostic payloads, with declared signature work.
    A production closed control grammar and derived due-close set remain gates.
    """
    if not available:
        raise ValueError('INCOMPLETE_EVIDENCE')
    rows, votes, control, close_ids, optional_seen = [], 0, 0, [], False
    for e in events:
        kind = e['kind']
        raw = canonical(e)
        if len(raw) > INPUT['event_max_bytes']:
            raise ValueError('event bytes')
        if kind == 'VOTE':
            structural_bounds(e['payload']['signed_vote'])
            votes += 1
        elif kind in ('OPEN', 'CLOSE', 'EPOCH', 'EVIDENCE'):
            checks = e.get('checks', 0)
            if type(checks) is not int or not 0 <= checks <= INPUT['control_signature_budget']:
                raise ValueError('control work')
            control += checks
        else:
            raise ValueError('unknown event')
        if kind == 'CLOSE':
            if optional_seen or len(raw)+4 > INPUT['close_frame_budget']:
                raise ValueError('close order/bytes')
            close_ids.append(e['sid'])
        else:
            optional_seen = True
        rows.append(struct.pack('>I', len(raw)) + raw)
    if close_ids != sorted(set(close_ids)) or len(close_ids) > INPUT['close_reservations']:
        raise ValueError('close reservations/order')
    if fixed24 and votes > 24:
        raise ValueError('fixed24')
    if cpu and (votes > INPUT['cpu_vote_budget'] or control > INPUT['control_signature_budget']):
        raise ValueError('work budget')
    root = sha256(b''.join(rows)).digest()  # diagnostic ordered root, NOT a Merkle tree
    header = b'Q717' + struct.pack('>Q', height) + parent + struct.pack('>I', len(rows)) + root
    assert len(header) == 80
    result = header + bytes(INPUT['header_bytes']-80) + b''.join(rows)
    if len(result) > INPUT['batch_bytes']:
        raise ValueError('batch bytes')
    return result


def sized_control(size, kind='EVIDENCE', **fields):
    e = dict(kind=kind, data='', **fields)
    e['data'] = 'x' * (size-len(canonical(e)))
    assert len(canonical(e)) == size
    return e


def ledger():
    rows = []
    for name, v in [('P_sample', structural_vote()), ('O_I_conditional_max', maximum_vote())]:
        structural_bounds(v)
        p, signed, event = map(lambda x: len(canonical(x)), (v['payload'], v, vote_event(v)))
        slots = (262144-33792)//(event+4)
        rows.append(dict(name=name, payload=p, signed=signed, wrapper=signed-p,
                         event=event, event_wrapper=event-signed, framing=4,
                         signature_text=132, decoded_signature=65,
                         byte_slots_with_16_close_reserve=slots,
                         batch_24=1024+24*(event+4),
                         batch_byte_full=33792+slots*(event+4),
                         remainder=262144-(33792+slots*(event+4))))
    return dict(rows=rows, P_sample_byte_slots=228352//1744,
                P_24_accounted_bytes=33792+24*1744,
                P_24_unallocated_bytes=262144-(33792+24*1744),
                loose_event_8192_slots=228352//8196,
                loose_signed_4096_event_slots=228352//(4096+42+4),
                header_actual=80, header_reservation=944,
                certificate_signature_text=4*132,
                certificate_mean_other=4096-4*132,
                certificate_max_other=16384-4*132)
