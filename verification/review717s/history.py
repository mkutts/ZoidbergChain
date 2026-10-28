"""Audit commitments in ONE four-batch laboratory transcript, never finalize it.

This intentionally is not R's general application/reviewer-history engine.
Eligibility below is a separately supplied test pin, not verified policy state.
Even complete bytes/signatures yield INCOMPLETE_HISTORY, never media approval.
"""
from canonical_v3.primitives import require
from verification.review717r import wire as w
from verification.review717r.model import tally, wire_fold
from .verify import (Result, ZERO, check_context, record, user_bindings, verify_user,
                     verify_proof, verify_clock, verify_checkpoint)


def audit_fixture_history(pins, units, checkpoint_bytes, media_bytes, *,
                          fixture_eligibility, actual_media_parent, pending_votes=()):
    require(type(units) in (tuple, list) and len(units) == 4,
            'INCOMPLETE_HISTORY: laboratory_prefix_requires_four_batches')
    parent, previous = pins.origin, pins.initial_state
    parsed = []
    for height, unit in enumerate(units, 1):
        require(type(unit) is dict and set(unit) == {'batch', 'proof'}, 'history_unit_shape')
        raw, proof = unit['batch'], unit['proof']
        require(raw is not None and proof is not None, 'INCOMPLETE_HISTORY: missing_journal_evidence')
        header, events = w.parse_body(raw)
        check_context(pins, header)
        require(header['height'] == height and header['parent'] == parent and
                header['previous_state'] == previous, 'prefix_parent_state')
        verify_proof(pins, proof, batch_bytes=raw, height=height, parent=parent, round=0)
        verify_clock(pins, header)
        w.preflight_work(events)
        parsed.append((header, events))
        parent = w.tagged('batch', raw)
        previous = w.tagged('state', bytes.fromhex(previous + parent))

    # Narrow fixed transcript grammar: OPEN; START/EPOCH; admissions/charges;
    # CLOSE/EPOCH. Unsupported histories fail rather than becoming policy valid.
    kinds = [[k for k, _ in events] for _, events in parsed]
    require(kinds[0] == ['OPEN'] and kinds[1] == ['START', 'EPOCH'] and
            kinds[3] == ['CLOSE', 'EPOCH'], 'UNSUPPORTED_LAB_TRANSCRIPT')
    require(all(k in ('ADMISSION', 'PARTICIPATION') for k in kinds[2]), 'UNSUPPORTED_LAB_EVENTS')
    medians = [sorted(s['reading'] for s in h['clock']['samples'])[1] for h, _ in parsed]
    require(medians[0] >= 300 and all(b >= a + 5 for a, b in zip(medians, medians[1:])),
            'logical_clock_cadence')
    op = parsed[0][1][0][1]
    verify_user(pins, 'OPEN', w.pack('OPEN', op), expected=user_bindings('OPEN', op))
    require(op['base_height'] == 0 and op['base_hash'] == pins.origin and
            op['eligibility_root'] == pins.initial_state, 'open_parent_state')
    sid = w.tagged('session', w.pack('OPEN', op)[:-65])
    start = parsed[1][1][0][1]
    deadline = medians[1] + 1 + 1200
    require(start == dict(sid=sid, open_height=1, deadline=deadline,
                         time_id=w.tagged('clock', w.pack('CLOCK', parsed[1][0]['clock']))), 'start_binding')
    require(medians[2] - 1 < deadline <= medians[3] - 1, 'logical_close_boundary')
    for idx, old in ((1, (medians[0] - 1) // 300), (3, (medians[2] - 1) // 300)):
        h, events = parsed[idx]
        lower = medians[idx] - 1
        require(events[-1][1] == dict(previous=old, current=lower // 300, lower=lower,
                time_id=w.tagged('clock', w.pack('CLOCK', h['clock']))), 'epoch_binding')

    counts, slots, charges = [[0, 0, 0, 0], [0, 0, 0, 0]], set(), set()
    count, fold, pending_charge = 0, w.tagged('empty-votes', bytes.fromhex(sid)), None
    expected_base = {k: op[k] for k in ('submission', 'original', 'creator', 'media_height',
                                       'media_hash', 'base_height', 'base_hash')}
    for index, (kind, obj) in enumerate(parsed[2][1]):
        if pending_charge is not None:
            require(kind == 'PARTICIPATION' and obj == pending_charge, 'participation_binding')
            pending_charge = None
            continue
        require(kind == 'ADMISSION', 'unexpected_participation')
        vote = obj['vote']
        expected = dict(expected_base, sid=sid, deadline=deadline, dimension=vote['dimension'])
        auth = verify_user(pins, 'VOTE', w.pack('VOTE', vote), expected=expected)
        wallet, d, choice = auth.identity, vote['dimension'], vote['choice']
        status = fixture_eligibility.get(wallet)
        require(type(status) is int and status in (1, 2) and wallet != op['creator'],
                'test_eligibility_pin')
        require(obj == dict(vote=vote, result=0, first_height=3, first_index=index,
                           status=status, charged_epoch=(medians[2] - 1) // 300), 'admission_binding')
        require((wallet, d) not in slots, 'duplicate_counted_vote')
        slots.add((wallet, d))
        count += 1
        counts[d][choice] += 1
        counts[d][3] += status == 2
        fold = wire_fold(fold, count, 3, index, vote, status)
        if wallet not in charges:
            charges.add(wallet)
            pending_charge = dict(wallet=wallet, submission=op['submission'], epoch=obj['charged_epoch'],
                status=status, first_height=3, first_index=index, used_after=1,
                cause=w.tagged('event', w.frame('ADMISSION', obj)))
    require(pending_charge is None, 'missing_participation')
    a, b = (tally(c) for c in counts)
    outcome = 2 if 2 in (a['outcome'], b['outcome']) else 1 if a['outcome'] == b['outcome'] == 1 else 0
    close = dict(sid=sid, deadline=deadline, freeze_height=4, count=count, fold=fold,
                 originality=a, admissibility=b, outcome=outcome)
    require(parsed[3][1][0][1] == close, 'replaced_close_page_or_tally')
    verify_checkpoint(pins, checkpoint_bytes, batch_bytes=units[-1]['batch'], proof_bytes=units[-1]['proof'])
    cp = record('CHECKPOINT', checkpoint_bytes)
    media = record('MEDIA', media_bytes)
    check_context(pins, media)
    expected_media = dict(pins.context, checkpoint=cp, sid=sid, close_height=4, close_batch=cp['batch'],
        close_index=0, close_id=w.tagged('event', w.frame('CLOSE', close)), **expected_base,
        count=count, fold=fold, originality=a, admissibility=b)
    # MEDIA calls the anchored media hash 'media_parent', and names the NEXT height.
    expected_media.pop('base_height')
    expected_media.pop('base_hash')
    expected_media['media_parent'] = expected_media.pop('media_hash')
    expected_media['media_height'] += 1
    require(media == expected_media and (op['media_height'], op['media_hash']) == actual_media_parent,
            'media_reference_parent_or_close')
    # Pending signatures are authenticated but never enumerated in the fold/tally.
    for vote_bytes in pending_votes:
        v = record('VOTE', vote_bytes)
        verify_user(pins, 'VOTE', vote_bytes, expected=dict(expected_base, sid=sid,
                    deadline=deadline, dimension=v['dimension']))
    return dict(verification=Result('INCOMPLETE_HISTORY', True, True, True),
        fixture_count=count, fixture_fold=fold, fixture_originality=a, fixture_admissibility=b,
        pending_verified_not_counted=len(pending_votes),
        missing=('journal-aware_G2_amendment', 'source_and_eligibility_policy_validation',
                 'full_application_validity', 'physical_clock_trust', 'agreement_execution'))
