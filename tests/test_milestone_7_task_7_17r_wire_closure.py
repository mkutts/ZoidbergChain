"""R717 specification checks; trusted authentication facts are explicit."""
from copy import deepcopy
from dataclasses import asdict
from fractions import Fraction
import json
from pathlib import Path
import subprocess

import pytest

from verification.review717r import model as m
from verification.review717r import wire as w
from verification.review717r.vectors import build, example, fixture_objects

ROOT = Path(__file__).resolve().parents[1]


def run(s, history, **kw):
    out, result = m.step(s, boundaries=history, **kw)
    history.append(result['boundary'])
    return out, result


def started(eligibility=None):
    hist = []
    s, _ = run(m.State(), hist, readings=(300, 300, 300), opens=(m.open_fact(1, eligibility),))
    s, _ = run(s, hist, readings=(305, 305, 305))
    return s, hist


@pytest.mark.parametrize('kind', w.SCHEMAS)
def test_closed_grammar_roundtrip_and_fixed_maxima(kind):
    expected = json.loads((ROOT/'tests/fixtures/review717r_v1/schema.json').read_text())
    obj = example(kind, True)
    raw = w.pack(kind, obj)
    assert len(raw) == expected['maxima'][kind]
    assert w.unpack(kind, raw) == obj
    with pytest.raises(ValueError):
        w.pack(kind, dict(obj, unrecognized=0))
    with pytest.raises(ValueError):
        w.unpack(kind, raw+b'\x00')
    with pytest.raises(ValueError):
        w.unpack(kind, raw[:-1])


def test_retained_vectors_and_independent_node_hashes():
    retained = json.loads((ROOT/'tests/fixtures/review717r_v1/vectors.json').read_text())
    assert retained == build()
    result = json.loads(subprocess.check_output(['node', 'verification/review717r/oracle.cjs'], cwd=ROOT))
    assert result['vectors'] == 17 and result['independent_encoder'] and result['batch']
    assert result['signatures_generated'] == 0


@pytest.mark.parametrize('field,value', [('protocol', True), ('membership', 1), ('dimension', 2),
    ('choice', -1), ('sequence', 1), ('deadline', 9007199254740992), ('key', 'AA'*33),
    ('signature', '00'*66), ('network', 'N'*64), ('network', 'a'*65)])
def test_strict_fields(field, value):
    obj = example('VOTE')
    obj[field] = value
    with pytest.raises(ValueError):
        w.pack('VOTE', obj)


def test_network_padding_unknown_version_and_frame_tamper():
    vote = example('VOTE')
    raw = bytearray(w.pack('VOTE', vote))
    raw[64] = 1
    with pytest.raises(ValueError):
        w.unpack('VOTE', bytes(raw))
    framed = bytearray(w.frame('VOTE', vote))
    framed[2] = 2
    with pytest.raises(ValueError):
        w.unframe(bytes(framed))


def cap_batch(extra=0):
    _, h = fixture_objects()
    overhead = len(w.body(h, []))
    events = []
    remain = w.CAP - overhead + extra
    while remain:
        chunk = min(8140, remain-49)
        assert chunk > 0
        obj = dict(object_id='ab'*32, total=1048576, offset=len(events)*8140, chunk='aa'*chunk)
        encoded = len(w.frame('DATA', obj))
        events.append(('DATA', obj))
        remain -= encoded
    return h, events


@pytest.mark.parametrize('delta', [-1, 0, 1])
def test_exact_batch_cap_and_one_over(delta):
    h, events = cap_batch(delta)
    if delta > 0:
        with pytest.raises(ValueError, match='batch cap'):
            w.body(h, events)
    else:
        raw = w.body(h, events)
        assert len(raw) == w.CAP+delta
        assert w.parse_body(raw)[1] == events


def test_corrupt_or_missing_batch_bytes():
    h, events = cap_batch()
    raw = w.body(h, events)
    for bad in (raw[:-1], raw+b'0', raw[:-1]+bytes([raw[-1]^1])):
        with pytest.raises(ValueError):
            w.parse_body(bad)


def test_work_counts_rejected_votes_and_mandatory_lane():
    admission = example('ADMISSION')
    admission['result'] = 8
    assert w.preflight_work([('ADMISSION', admission)]*96)['vote_checks'] == 96
    with pytest.raises(ValueError, match='work budget'):
        w.preflight_work([('ADMISSION', admission)]*97)
    with pytest.raises(ValueError, match='mandatory lane'):
        w.preflight_work([('CLOSE', example('CLOSE'))]*17)


@pytest.mark.parametrize('counts,expected', [((7,3,0,1),1), ((6,3,0,1),2), ((1,0,4,1),1),
    ((0,0,5,1),0), ((0,0,0,0),0), ((4,0,0,1),0), ((5,0,0,0),0), ((2,3,0,1),2)])
def test_threshold_quorum_and_unsure(counts, expected):
    t = m.tally(counts)
    assert t['outcome'] == expected
    if counts[0]+counts[1]:
        assert Fraction(t['numerator'],t['denominator']) == Fraction(counts[0],counts[0]+counts[1])
    else:
        assert t['numerator'] == t['denominator'] == 0


def test_full_tally_duplicate_conflict_quota_and_frozen_status():
    elig = {f'w{i}': 2 if i == 0 else 1 for i in range(5)}
    s, hist = started(elig)
    votes = [m.vote_fact(s.sessions[m.open_fact(1)['sid']], f'w{i}', d, 2 if i == 4 else 0)
             for d in (0,1) for i in range(5)]
    s, obs = run(s, hist, readings=(310,310,310), votes=votes)
    assert obs['observations'] == ['ADMIT']*10 and len(s.charges) == 5
    s, obs = run(s, hist, readings=(315,315,315), votes=[votes[0], dict(votes[0], choice=1)])
    assert obs['observations'] == ['DUPLICATE','CONFLICT']
    sess = next(iter(s.sessions.values()))
    assert sess.count == 10 and len(sess.conflicts) == 1
    before = deepcopy(sess.counts)
    s, obs = run(s, hist, readings=(1507,1507,1507), votes=[votes[0]])
    assert obs['observations'] == ['LATE'] and len(s.charges) == 5
    assert next(iter(s.sessions.values())).counts == before
    assert obs['closes'][0]['outcome'] == 1


@pytest.mark.parametrize('kwargs', [dict(signers=(0,0,1)),dict(signers=(0,1)),
    dict(signers=(0,True,2)),dict(authenticated=False),dict(available=False),
    dict(parent='ff'*32),dict(context={'network':'wrong'}),dict(finalized=False),
    dict(proof_value='ff'*32),dict(height=99)])
def test_finality_clock_context_and_availability_fail_closed(kwargs):
    s, hist = started()
    original = deepcopy(s)
    with pytest.raises(ValueError):
        m.step(s, boundaries=hist, readings=(310,310,310), **kwargs)
    assert s == original


def test_clock_byzantine_extreme_cannot_force_early_freeze_and_partition_catchup():
    s, hist = started()
    s, _ = run(s,hist,readings=(310,310,999999999))
    sess = next(iter(s.sessions.values()))
    assert s.lower == 309 and not m.closed(sess,s.lower)
    with pytest.raises(ValueError,match='cadence'):
        m.step(s,readings=(309,309,309))
    # No state transitions during outage. First recovered proof freezes before votes.
    s, result = run(s,hist,readings=(10000,10000,10000),votes=[m.vote_fact(sess)])
    assert result['observations'] == ['LATE'] and result['closes'][0]['count'] == 0


def seed_due(n):
    s = m.State(height=2, median=305, lower=304, epoch=1)
    for i in reversed(range(n)):
        o = m.open_fact(i)
        sess = m.Session(o['sid'],o['submission'],o['original'],o['creator'],1,0,'00'*32,
                         0,'11'*32,{'w':2},deadline=1506,started=2)
        s.sessions[sess.sid] = sess
        s.expiry.append((1506,sess.sid))
    s.expiry.sort()
    return s


@pytest.mark.parametrize('n', [0,1,16,17,33,1000])
def test_simultaneous_closure_pages_no_omission_late_votes_or_local_order(n):
    s, hist = seed_due(n), [(1,299),(2,304)]
    expected = sorted(s.sessions)
    seen = []
    while s.expiry:
        ids = m.page(s,1506)
        for bad in ([], list(reversed(ids)), ids[:-1], ids+ids[:1]):
            if bad == ids:
                continue
            with pytest.raises(ValueError,match='mandatory close page'):
                m.step(s,boundaries=hist,readings=(max(1507,s.median+5),)*3,supplied_page=bad)
        pending = s.sessions[expected[-1]]
        s, result = run(s,hist,readings=(max(1507,s.median+5),)*3,votes=[m.vote_fact(pending)])
        seen.extend(r['sid'] for r in result['closes'])
        assert result['observations'] == ['LATE']
        assert all(r['freeze_height'] == 3 for r in result['closes'])
        assert len(result['closes']) <= 16
    assert seen == expected
    assert s.height-2 == (n+15)//16


def test_closure_order_uses_deadline_then_sid_and_bounded_live_capacity():
    s=seed_due(4096)
    assert len(s.expiry)==4096 and len(m.page(s,1506))==16
    # Later new deadlines cannot sort ahead of the due backlog.
    s.expiry[0]=(1505,s.expiry[0][1])
    assert m.page(s,1505)==[s.expiry[0][1]]
    with pytest.raises(ValueError,match='live session cap'):
        m.step(s,readings=(310,310,310),opens=[m.open_fact(5000)])


def test_replay_restart_boundary_and_new_opens_cannot_starve_closes():
    initial=seed_due(33)
    s, hist=deepcopy(initial),[(1,299),(2,304)]
    trace=[]
    for i in range(3):
        kw=dict(readings=(1507+i*5,)*3, opens=[m.open_fact(100+i)])
        trace.append(kw)
        s, _=run(s,hist,**kw)
        if i==0:
            s=deepcopy(s)  # intact-state restart; no reconstructed pending pool
    other, hist2=deepcopy(initial),[(1,299),(2,304)]
    other.sessions=dict(reversed(list(other.sessions.items())))
    for kw in trace:
        other,_=run(other,hist2,**kw)
    assert s == other
    assert all(s.sessions[sid].close for sid in initial.sessions)


def test_concurrent_quota_service_epoch_expiry_and_no_refund():
    s,hist=started({'w':1})
    second=m.open_fact(2,{'w':1})
    s,_=run(s,hist,readings=(310,)*3,opens=[second])
    s,_=run(s,hist,readings=(315,)*3)
    s.used['w',1]=4
    s.charges.update({('w',f'previous-{i}'):1 for i in range(4)})
    a,b=list(s.sessions.values())
    s,result=run(s,hist,readings=(320,)*3,votes=[m.vote_fact(a),m.vote_fact(b)])
    assert result['observations']==['ADMIT','QUOTA_EXHAUSTED']
    s.penalties['w']=2
    s,result=run(s,hist,readings=(325,)*3,votes=[m.vote_fact(b)])
    assert result['observations']==['PENALIZED']
    s,result=run(s,hist,readings=(601,)*3,votes=[m.vote_fact(b)])
    assert s.epoch==2 and result['observations']==['ADMIT'] and s.media[0]==0
    s,_=run(s,hist,readings=(2000,)*3)
    assert len(s.charges)==6 and s.charges['w',a.submission]==1


def test_wrong_session_binding_network_and_invalid_signature():
    s,hist=started()
    v=m.vote_fact(next(iter(s.sessions.values())))
    for change, expected in [(dict(sid='ff'*32),'WRONG_SESSION'),(dict(deadline=1),'WRONG_BINDING')]:
        _,result=m.step(s,boundaries=hist,readings=(310,)*3,votes=[dict(v,**change)])
        assert result['observations']==[expected]
    for change in (dict(authenticated=False),dict(context=dict(m.CONTEXT,network='foreign'))):
        with pytest.raises(ValueError):
            m.step(s,boundaries=hist,readings=(310,)*3,votes=[dict(v,**change)])


def test_unsupported_retry_never_discards_failed_history():
    s,hist=started()
    s,_=run(s,hist,readings=(2000,)*3)
    with pytest.raises(ValueError,match='UNSUPPORTED_RETRY'):
        m.step(s,boundaries=hist,readings=(2300,)*3,opens=[m.open_fact(2)|{'original':m.open_fact(1)['original']}])


def test_preserved_eight_p_negative_controls():
    from verification.review717p.check import negative_controls
    retained=json.loads((ROOT/'verification/review717p/negative-control-traces.json').read_text())
    assert len(retained)==8 and negative_controls()==retained and all(r['detected'] for r in retained)


def passing():
    elig={f'w{i}':2 if i==0 else 1 for i in range(5)}
    s,hist=started(elig)
    sess=next(iter(s.sessions.values()))
    s,_=run(s,hist,readings=(310,)*3,votes=[m.vote_fact(sess,f'w{i}',d) for d in (0,1) for i in range(5)])
    s,_=run(s,hist,readings=(1507,)*3)
    return s,hist


@pytest.mark.parametrize('change', [dict(count=1),dict(fold='ff'*32),dict(close_index=1),
    dict(close_id='ff'*32),dict(checkpoint=(4,'ff'*32)),dict(original='ff'*32),
    dict(context=dict(m.CONTEXT,instance='ff'*32))])
def test_media_exact_reference_no_producer_subset_or_cross_history_replay(change):
    s,_=passing()
    ref=m.media_reference(s,next(iter(s.sessions)))
    with pytest.raises(ValueError,match='reference mismatch'):
        m.verify_media_reference(s,dict(ref,**change),actual_media_parent=s.media)


def test_old_finalized_checkpoint_survives_new_journal_progress_but_not_new_media_parent():
    s,hist=passing()
    ref=m.media_reference(s,next(iter(s.sessions)))
    s,_=run(s,hist,readings=(1807,)*3)
    assert m.verify_media_reference(s,ref,actual_media_parent=s.media)=='VALID_REFERENCE_ONLY'
    for kwargs in (dict(actual_media_parent=(1,'ff'*32)),
                   dict(actual_media_parent=s.media,consumed={ref['original']}),
                   dict(actual_media_parent=s.media,evidence_complete=False),
                   dict(actual_media_parent=s.media,genesis_policy_supported=False)):
        with pytest.raises(ValueError):
            m.verify_media_reference(s,ref,**kwargs)


def test_exact_logical_deadline_last_prior_vote_and_first_boundary_vote():
    s,hist=started({'a':2,'b':1})
    sess=next(iter(s.sessions.values()))
    s,result=run(s,hist,readings=(1502,)*3,votes=[m.vote_fact(sess,'a',choice=1)])
    assert s.lower==1501 and result['observations']==['ADMIT']
    s,result=run(s,hist,readings=(1507,)*3,votes=[m.vote_fact(sess,'b')])
    assert s.lower==sess.deadline==1506 and result['observations']==['LATE']
    assert result['closes'][0]['count']==1


def test_empty_idle_service_progress_and_closed_fail_never_approve():
    s,hist=m.State(),[]
    for n in range(1,5):
        s,result=run(s,hist,readings=(300*n,)*3)
        assert not result['closes'] and not s.sessions and s.media[0]==0
    assert s.epoch==3  # lower=1199, half-open epochs; no media dependence
    s,hist=started({f'w{i}':2 for i in range(5)})
    sess=next(iter(s.sessions.values()))
    s,_=run(s,hist,readings=(310,)*3,votes=[m.vote_fact(sess,f'w{i}',0,1) for i in range(5)])
    s,result=run(s,hist,readings=(1507,)*3)
    assert result['closes'][0]['outcome']==2
    with pytest.raises(ValueError,match='PASS'):
        m.media_reference(s,sess.sid)


def test_resource_components_and_historical_cost_units():
    from verification.review717r.report import resources
    from verification.review717q.workload import economics
    r=resources(100)
    assert r['logical_day']==sum(r['components_day'].values())
    assert r['logical_three_year']==r['logical_day']*1095
    assert r['all_six_service_copies']==r['four_validators']+r['two_independent_archives']
    assert r['historical_whole_node_economics']==economics(r['logical_day'],17280)
    assert not resources(10000)['sustainable_arithmetic']
    assert resources(0,active=False)['logical_three_year']==729112320


def test_evidence_complete_retrieval_hash_binding_and_corruption():
    from verification.review717r.evidence import assemble, inventory_bytes
    raw=b'complete retained evidence'
    oid=w.tagged('source-3',raw)
    ref=dict(kind=3,object_id=oid,length=len(raw),height=0,batch='00'*32,index=0)
    inv=dict(entries=[ref])
    assert inventory_bytes(inv,{oid:raw})=={oid:raw}
    pages=[dict(object_id=oid,total=len(raw),offset=0,chunk=raw[:8].hex()),
           dict(object_id=oid,total=len(raw),offset=8,chunk=raw[8:].hex())]
    assert assemble(ref,pages)==raw
    for objects in ({},{oid:raw[:-1]},{oid:bytes(len(raw))}):
        with pytest.raises(ValueError):
            inventory_bytes(inv,objects)
    for bad in (pages[:1],list(reversed(pages)),[pages[0],dict(pages[1],offset=7)]):
        with pytest.raises(ValueError):
            assemble(ref,bad)
    with pytest.raises(ValueError,match='INCOMPLETE_HISTORY'):
        inventory_bytes(dict(entries=[dict(ref,height=1,batch='ff'*32)]),{oid:raw})


def test_multiple_deadlines_use_earliest_crossing_and_deadline_before_sid():
    s,hist=seed_due(33),[(1,299),(2,304)]
    last=sorted(s.sessions)[-1]
    s.sessions[last].deadline=1000
    s.expiry=[(sess.deadline,sid) for sid,sess in s.sessions.items()]
    s.expiry.sort()
    s,result=run(s,hist,readings=(1001,)*3)
    assert [r['sid'] for r in result['closes']]==[last]
    assert result['closes'][0]['freeze_height']==3
    for median in (1507,1512):
        s,result=run(s,hist,readings=(median,)*3)
        assert len(result['closes'])==16
        assert all(r['freeze_height']==4 for r in result['closes'])
    assert not s.expiry


def test_submission_identity_cannot_switch_original_under_another_session():
    s,hist=started()
    new=m.open_fact(2)
    new['submission']=m.open_fact(1)['submission']
    with pytest.raises(ValueError,match='submission identity lock'):
        m.step(s,boundaries=hist,readings=(310,)*3,opens=[new])
