"""Trusted, deliberately bounded reducer: initial round only, no agreement engine.

Only START, fresh-proposal L22, non-nil L36 and nil-polka L44 are enabled.
No public method accepts caller-written State, Event, lock or valid-value data.
"""
from copy import deepcopy
from dataclasses import asdict

from canonical_v3.primitives import closed, require, uint, h64
from verification.tendermint717h.model import Block
from .wire import J, parse, sha, signed, proof, commitment, slot_key

FLAGS = ('protocol', 'canonical', 'original', 'admission', 'transactions', 'resources')


def ref(kind, raw):
    return dict(kind=kind, digest=sha(raw))


def unset():
    return dict(block_hash=None, round=-1, proposal_id=None, prevote_certificate_id=None)


def initial(ns, genesis, generation):
    return dict(state_version=1, namespace_id=ns, revision=0, fence_generation=generation,
        height=1, round=0, phase='propose', started=False, locked=unset(), valid=unset(),
        finalized=dict(height=0, block_hash=genesis, proof_id=None),
        applied=dict(height=0, block_hash=genesis), inbox_tip=None, markers_tip=None,
        pending_slot=None, fault=None)


def catalogue(raw, ctx):
    entries = parse(raw, 65536)
    require(type(entries) is list and 1 <= len(entries) <= 32, 'test_catalogue')
    ids = []
    for b in entries:
        closed(b, 'id height parent ' + ' '.join(FLAGS))
        h64(b['id'])
        require(uint(b['height'], 1) == 1 and b['parent'] == ctx.genesis_hash, 'test_block_context')
        require(all(type(b[k]) is bool for k in FLAGS), 'test_block_flags')
        # Exact 7.17H Block fields; the pinned fixture, never a request, selects them.
        require(asdict(Block(**b)) == b, 'test_block')
        ids.append(b['id'])
    require(ids == sorted(set(ids)), 'test_catalogue_order')
    return {b['id']: b for b in entries}


def validation(b, ns):
    return dict(record_version=1, profile='task717h-symbolic-v1', namespace_id=ns,
        height=b['height'], parent_hash=b['parent'], block_hash=b['id'],
        block_record_id=sha(J(b)), source_revision=0,
        **{k: b[k] for k in FLAGS}, result='VALID' if all(b[k] for k in FLAGS) else 'INVALID')


def plan(state, e, ctx, pub, blocks, proposal_raw=None, pv_raw=None):
    """Compute an enabled reservation and immutable dependencies, without key use."""
    s = deepcopy(state)
    p, slot = e['payload'], slot_key(e)
    require(p['validator_id'] == ctx.namespace(pub)['validator_id'], 'signer_identity')
    require(s['pending_slot'] is None and s['fault'] is None, 'pending_or_fault')
    require(p['block_height'] == s['height'] == 1 and p['round'] == s['round'] == 0,
            'INCOMPLETE_AGREEMENT_CONTEXT')
    require(p['parent_hash'] == s['finalized']['block_hash'] == s['applied']['block_hash'], 'parent_anchor')
    deps = []
    messages = []

    def put(kind, value):
        raw = J(value)
        item = (kind, raw)
        if item not in deps:
            deps.append(item)
        return sha(raw)

    def mark(kind, status):
        s['markers_tip'] = put('marker', dict(record_version=1, previous=s['markers_tip'],
            height=s['height'], round=s['round'], kind=kind, status=status))

    def block(value):
        require(value in blocks, 'INCOMPLETE_DATA')
        b = blocks[value]
        bid = put('block', b)
        v = validation(b, s['namespace_id'])
        vid = put('validation', v)
        return bid, vid, v['result'] == 'VALID'

    block_id = validation_id = None
    if p['step'] == 'propose':
        require(not s['started'] and s['phase'] == 'propose' and p['valid_round'] == -1,
                'INCOMPLETE_AGREEMENT_CONTEXT')
        require(proposal_raw is None and pv_raw is None, 'unused_evidence')
        block_id, validation_id, valid = block(p['block_hash'])
        require(valid, 'invalid_get_value')
        s['started'] = True
        rule = 'START'
    else:
        require(s['started'], 'not_started')
        if p['step'] == 'precommit' and p['block_hash'] is None:
            require(s['phase'] == 'prevote' and proposal_raw is None and pv_raw is not None,
                    'INCOMPLETE_AGREEMENT_CONTEXT')
            pv = proof(pv_raw, ctx, 'pv')
            require(pv['commitment'] == {**commitment(e), 'step': 'prevote'}, 'nil_polka')
            put('pv', pv)
            messages.extend(pv['votes'])
            s['phase'], rule = 'precommit', 'L44'
            mark('precommit', 'once')
        else:
            require(proposal_raw is not None, 'MISSING_PROPOSAL')
            prop = signed(proposal_raw, ctx)
            pe = prop['envelope']
            pp = pe['payload']
            require(pp['step'] == 'propose' and pp['valid_round'] == -1, 'INCOMPLETE_AGREEMENT_CONTEXT')
            target = {k: v for k, v in commitment(e).items() if k not in ('block_hash', 'step')}
            require({k: v for k, v in commitment(pe).items()
                     if k not in ('block_hash', 'step', 'valid_round')} == target, 'proposal_context')
            pid = put('signed', prop)
            messages.append(prop)
            block_id, validation_id, valid = block(pp['block_hash'])
            if p['step'] == 'prevote':
                require(s['phase'] == 'propose' and pv_raw is None, 'phase_or_evidence')
                lock_ok = s['locked']['round'] == -1 or s['locked']['block_hash'] == pp['block_hash']
                require(p['block_hash'] == (pp['block_hash'] if valid and lock_ok else None), 'prevote_guard')
                s['phase'], rule = 'prevote', 'L22'
                mark('prevote', 'once')
            else:
                require(s['phase'] == 'prevote' and valid and p['block_hash'] == pp['block_hash'] and
                        pv_raw is not None, 'INCOMPLETE_AGREEMENT_CONTEXT')
                pv = proof(pv_raw, ctx, 'pv')
                require(pv['commitment'] == {**commitment(e), 'step': 'prevote'}, 'polka')
                pvid = put('pv', pv)
                messages.extend(pv['votes'])
                # Lock, valid state and precommit reservation share one transaction.
                lv = dict(block_hash=p['block_hash'], round=p['round'], proposal_id=pid,
                          prevote_certificate_id=pvid)
                s['locked'], s['valid'] = deepcopy(lv), deepcopy(lv)
                s['phase'], rule = 'precommit', 'L36'
                mark('polka', 'once')
                mark('precommit', 'once')
    for m in sorted({J(m): m for m in messages}.values(), key=lambda m: sha(J(m))):
        sid = put('signed', m)
        s['inbox_tip'] = put('receipt', dict(record_version=1, previous=s['inbox_tip'], signed_id=sid))
    s['pending_slot'] = slot
    return rule, s, deps, block_id, validation_id


def start_nonproposer(state, ctx, pub):
    require(not state['started'] and state['pending_slot'] is None and state['fault'] is None and
            state['height'] == 1 and state['round'] == 0 and
            pub != ctx.proposer(1, 0), 'INCOMPLETE_AGREEMENT_CONTEXT')
    s = deepcopy(state)
    s['started'] = True
    raw = J(dict(record_version=1, previous=s['markers_tip'], height=1, round=0,
                 kind='propose', status='armed'))
    s['markers_tip'] = sha(raw)
    return s, [('marker', raw)]
