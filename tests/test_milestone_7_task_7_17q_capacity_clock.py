"""Inert Q size/clock/queue probes plus unchanged P safety scenarios."""
from dataclasses import replace
import json
from pathlib import Path

import pytest

from verification.review717q.capacity import (
    INPUT, canonical, encode, ledger, maximum_vote, sized_control,
    structural_bounds, structural_vote, vote_event,
)
from verification.review717q.clock import ClockState, clock_step
from verification.review717q.workload import archive, economics, queue_trace, report, reproduce_p, workload
from verification.review717p import check as p
from verification.review717p.model import (
    Rejected, apply, batch_for, certificate_for, media_candidate, sources, step,
    validate_media, vote_event as pvote, open_event,
)
from verification.review717p.workload import calculate

ROOT = Path(__file__).resolve().parents[1]


def test_retained_results_reproduce():
    assert report() == json.loads((ROOT/'verification/review717q/results.json').read_text())


def test_size_ledger_has_independent_literal_expectations():
    sample, maximum = ledger()['rows']
    assert (sample['payload'], sample['signed'], sample['event']) == (1507, 1701, 1743)
    assert (maximum['payload'], maximum['signed'], maximum['event']) == (1545, 1739, 1781)
    assert sample['byte_slots_with_16_close_reserve'] == 130
    assert maximum['byte_slots_with_16_close_reserve'] == 127
    assert ledger()['loose_event_8192_slots'] == 27
    assert ledger()['P_24_unallocated_bytes'] == 186496


@pytest.mark.parametrize('delta,valid', [(-1, True), (0, True), (1, False)])
def test_exact_batch_boundary(delta, valid):
    # 31 max events = 254076 framed bytes; remainder fills exactly 262144.
    events = [sized_control(8192) for _ in range(31)]
    remaining = 262144-1024-31*8196-4
    events.append(sized_control(remaining+delta))
    if valid:
        assert len(encode(events)) == 262144+delta
    else:
        with pytest.raises(ValueError, match='batch bytes'):
            encode(events)


@pytest.mark.parametrize('field,value', [
    ('network_id', 'n'*65), ('reviewer_public_key', '02'+'a'*128),
    ('review_session_id', 'a'*65), ('vote_nonce', 'n'*8192),
    ('eligibility_media_height', True), ('eligibility_journal_height', 9007199254740992),
])
def test_oversized_or_malformed_vote(field, value):
    v = maximum_vote()
    v['payload'][field] = value
    with pytest.raises(ValueError):
        encode([vote_event(v)])


def test_large_signature_rejected_before_symbolic_agreement():
    v = maximum_vote()
    v['signature'] += '00'
    with pytest.raises(ValueError, match='signature bound'):
        structural_bounds(v)


def test_24_is_independent_of_bytes_and_cpu():
    events = [vote_event() for _ in range(25)]
    assert len(encode(events)) == 1024+25*1747
    with pytest.raises(ValueError, match='fixed24'):
        encode(events, fixed24=True)
    assert len(encode([vote_event() for _ in range(130)], cpu=False)) == 228134
    with pytest.raises(ValueError, match='work budget'):
        encode([vote_event() for _ in range(97)])


def test_mixed_events_and_all_simultaneous_closes_fit_with_96_max_votes():
    closes = [sized_control(2044, 'CLOSE', sid=f'{i:02}') for i in range(16)]
    other = [sized_control(2044, 'OPEN', checks=1), sized_control(508, 'EPOCH', checks=3)]
    assert len(encode(closes+[vote_event(maximum_vote())]*96+other)) == 207712
    with pytest.raises(ValueError, match='close order'):
        encode([vote_event()]+closes)
    with pytest.raises(ValueError, match='reservations'):
        encode(closes+[sized_control(100, 'CLOSE', sid='99')])


def test_control_cpu_budget_and_evidence_persistence():
    with pytest.raises(ValueError, match='work budget'):
        encode([sized_control(100, 'EVIDENCE', checks=64)]*2)
    with pytest.raises(ValueError, match='INCOMPLETE_EVIDENCE'):
        encode([vote_event()], available=False)


@pytest.mark.parametrize('rate,expected', [(10, 124377984000), (100, 371872512000),
                                         (1000, 2846817792000), (10000, 27596270592000)])
def test_independent_p_reconciliation(rate, expected):
    actual = reproduce_p(rate)
    assert actual['three_year'] == expected == calculate(votes_per_minute=rate)['archive_three_year_bytes']


def test_idle_growth_and_no_media_epoch_progress():
    assert archive(0, cadence=5, policy='continuous')['three_year_bytes'] == 117657031680
    assert archive(0, cadence=5, policy='hybrid')['three_year_bytes'] == 2149493760
    s, _ = clock_step(ClockState(), readings=(1, 1, 1), opens=('s',))
    s.penalties['w'] = 1
    s, _ = clock_step(s, readings=(2, 2, 2), starts=(('s', 10),))
    s, obs = clock_step(s, readings=(3, 3, 3), votes=(('s', 'w', 'sub', 'probationary'),))
    assert obs == ['PENALIZED']
    # No media ledger input exists here. Clock epochs still advance after months.
    s, _ = clock_step(s, readings=(10001, 10001, 10001))
    assert s.epoch == 100 and s.sessions['s']['closed']


def started():
    s, _ = clock_step(ClockState(), readings=(1, 1, 1), opens=('a', 'b'))
    return clock_step(s, readings=(2, 2, 2), starts=(('a', 10), ('b', 10)))[0]


def test_idle_closure_partition_recovery_and_late_boundary():
    s = started()  # deadline=13; lower=median-1
    s, obs = clock_step(s, readings=(13, 13, 13), votes=(('a', 'w', 'x', 'probationary'),))
    assert obs == ['ADMIT'] and not s.sessions['a']['closed']
    with pytest.raises(ValueError, match='mandatory close'):
        clock_step(s, readings=(14, 14, 14), due=[])
    # Partition: no quorum calls and therefore no state progress until recovery.
    recovered, obs = clock_step(s, readings=(1000, 1000, 1000), due=['a', 'b'],
                               votes=(('a', 'w2', 'x', 'probationary'),))
    assert obs == ['LATE'] and recovered.sessions['a']['votes'] == [('w', 'x')]
    assert len(recovered.charges) == 1


@pytest.mark.parametrize('changes', [dict(context=('foreign',)), dict(signers=(0, 0, 1)),
                                    dict(signers=(0, 1)), dict(authenticated=False), dict(available=False),
                                    dict(parent='wrong-checkpoint'), dict(signers=(0, True, 2))])
def test_clock_needs_full_authoritative_input(changes):
    with pytest.raises(ValueError):
        clock_step(started(), readings=(14, 14, 14), **changes)


def test_clock_no_fast_forward_from_one_byzantine_and_no_rollback():
    s = started()
    s, _ = clock_step(s, readings=(3, 3, 9999999))
    assert s.lower == 2 and not s.sessions['a']['closed']
    with pytest.raises(ValueError, match='rollback'):
        clock_step(s, readings=(1, 1, 1))


def test_concurrent_quota_exhaustion_and_next_epoch_without_refund():
    s = started()
    s.charges.update({('w', f'old{i}'): 0 for i in range(4)})
    s, obs = clock_step(s, readings=(3, 3, 3), votes=(
        ('a', 'w', 'sub-a', 'probationary'), ('b', 'w', 'sub-b', 'probationary')))
    assert obs == ['ADMIT', 'QUOTA_EXHAUSTED']
    s, _ = clock_step(s, readings=(101, 101, 101), opens=('c',))
    s, _ = clock_step(s, readings=(102, 102, 102), starts=(('c', 10),))
    s, obs = clock_step(s, readings=(103, 103, 103), votes=(('c', 'w', 'sub-c', 'probationary'),))
    assert obs == ['ADMIT'] and len(s.charges) == 6 and s.charges[('w', 'sub-a')] == 0


def test_penalty_expiry_without_media_and_no_quota_refund_on_close():
    s = started()
    s.penalties['w'] = 1
    s, _ = clock_step(s, readings=(101, 101, 101), opens=('c',))
    s, _ = clock_step(s, readings=(102, 102, 102), starts=(('c', 10),))
    s, obs = clock_step(s, readings=(103, 103, 103), votes=(('c', 'w', 'sub', 'probationary'),))
    assert obs == ['ADMIT']
    s, _ = clock_step(s, readings=(200, 200, 200))
    assert s.sessions['c']['closed'] and s.charges[('w', 'sub')] == 1


def test_burst_stall_recovery_and_close_first_queue():
    trace = queue_trace([10000]+[0]*110)
    assert trace[103]['queued'] == 16 and trace[104]['queued'] == 0
    stalled = queue_trace([96]*10+[0]*10, stalls={1, 2, 3})
    assert stalled[9]['queued'] == 288 and stalled[12]['queued'] == 0
    expired = queue_trace([10000]+[0]*9, expiry=4)
    assert expired[-1]['admitted'] == 288 and expired[-1]['late'] == 9712


@pytest.mark.parametrize('rate', [10, 100, 1000, 10000])
def test_all_loads_have_explicit_capacity_and_cost_classification(rate):
    r = workload(rate, kind='byte_cpu', event=1743, cadence=5, policy='hybrid')
    assert r['sustainable_vote_lane_ceiling_minute'] == 1152
    assert r['stable_vote_lane'] == (rate < 1152)
    assert (r['outage_clear_minutes'] is None) == (rate >= 1152)
    assert r['actual_close_delay_bound'] is None
    assert r['economics']['budget_vps']['three_year_usd'] > 720


def test_malformed_flood_cannot_change_agreed_inputs():
    before = encode([vote_event()])
    for size in (8193, 65536):
        with pytest.raises(ValueError, match='event bytes'):
            encode([sized_control(size)])
    assert encode([vote_event()]) == before


def test_p_producer_omission_withholding_and_cross_ledger_replay_still_refuse():
    s = p.opened()
    s = step(s, pvote(s, choice='not_original'))
    s = step(s)
    b = batch_for(s)
    bad = replace(b, events=())
    with pytest.raises(Rejected, match='mandatory'):
        apply(s, bad, certificate_for(bad), sources(bad))
    with pytest.raises(Rejected, match='INCOMPLETE_HISTORY'):
        apply(s, b, certificate_for(b), frozenset())
    with pytest.raises(Rejected):
        apply(s, b, replace(certificate_for(b), context=('wrong-genesis',)), sources(b))
    passed = p.passing()
    candidate = media_candidate(passed)
    with pytest.raises(Rejected):
        validate_media(passed, {**candidate, 'context': ('review-journal',)}, local_media=passed.media)
    with pytest.raises(Rejected):
        validate_media(passed, {**candidate, 'close_source': (0, 'wrong-checkpoint', 0)}, local_media=passed.media)


def test_p_eight_negative_controls_unchanged():
    retained = json.loads((ROOT/'verification/review717p/negative-control-traces.json').read_text())
    assert len(p.negative_controls()) == 8
    assert all(x['detected'] for x in p.negative_controls())
    assert p.negative_controls() == retained


def test_economics_independently_reproduces_media_only_baseline():
    from scripts.milestone_7_task_7_8_node_economics import simulate
    cfg = json.loads((ROOT/'benchmarks/milestone_7_task_7_8_config.json').read_text())
    for name, actual in economics(0, 0).items():
        original = simulate(cfg, 1000, 'representative_corpus', name)
        assert actual['three_year_usd'] == pytest.approx(original['three_year']['cumulative_cost'])
        assert actual['month36_usd'] == pytest.approx(original['month_36']['monthly_cost']['total'])
