"""Focused analytical tests; historical/active assertions remain untouched."""
import json
import pytest
from run import HERE, budgets, candidate, dist, encoded_bound, load
check=load('meme723_independent_check','benchmarks/task723_v1/crosscheck.py').check


def test_independent_evidence_and_decimal_costs():
    assert check(HERE)['status']=='PASS'


@pytest.mark.parametrize('cap',[131072,262144,524288,1048576,2097152])
def test_all_candidates_reserve_full_security_and_transaction_budgets(cap):
    b=budgets(encoded_bound(cap))
    assert b['proposed_block_cap']>=4*((b['encoded_cap']+2)//3)+327680
    assert b['proposed_block_cap']<=3145728
    assert b['encoded_cap']>=cap


def test_nearest_rank_small_population_and_tiny_media_metadata_failure():
    assert dist([1,2,3,4])['p50']==2
    records=json.loads((HERE/'records.json').read_bytes())
    tiny=next(r for r in records['rows'] if r['id']=='text-8')
    assert tiny['metadata_percent']>99 and tiny['certificate_value_bytes']>15000


def test_admission_inclusive_at_boundary_and_separate_by_mime():
    rows=json.loads((HERE/'records.json').read_bytes())['rows']
    exact=next(r for r in rows if r['id']=='text-16384')
    c=candidate(rows,'boundary',131072,262144,16384)
    d=candidate(rows,'below-boundary',131072,262144,16383)
    assert exact['id'] in c['admitted_ids'] and exact['id'] not in d['admitted_ids']
    assert next(r for r in rows if r['id']=='gif-boundary-262144')['id'] in c['admitted_ids']


def test_diagnostic_does_not_reweight_primary_population():
    rec=json.loads((HERE/'records.json').read_bytes())
    assert len(rec['rows'])==58
    assert all(r['id']!='text-expansion-control' for r in rec['rows'])
    assert rec['diagnostic_controls'][0]['encoded_bytes']==105


def test_overflow_controls_stay_in_denominators_without_fabricated_records():
    rec=json.loads((HERE/'records.json').read_bytes())
    over=[r for r in rec['rows'] if r['record_bytes'] is None]
    assert {r['id'] for r in over}=={'jpeg-texture-1280','png-texture-1280'}
    candidates=json.loads((HERE/'candidates.json').read_bytes())
    for c in candidates['common_ceiling']+candidates['profiles']:
        assert c['population']==58
        assert all(r['id'] not in c['admitted_ids'] for r in over)


def test_encoded_headroom_preserves_real_raw_expansion_control():
    rec=json.loads((HERE/'records.json').read_bytes())
    control=rec['diagnostic_controls'][0]
    assert control['encoded_bytes']>control['original_bytes']
    assert control['descriptor_bytes']<control['identity_descriptor_bytes']
    # Strict serialized shrink: a 4-byte codec label saving cannot pay for an
    # extra 4-byte base64 group when stored-size digit width cannot decrease.
    for m in list(range(1,35))+[104,105,131072,262144,524288,1048576,2097152]:
        for e in range(m+3,m+7):
            delta=4*((e+2)//3)-4*((m+2)//3)-4+len(str(e))-len(str(m))
            assert delta>=0


def test_native_success_is_distinct_from_strict_profile_acceptance():
    trials=json.loads((HERE/'codecs.json').read_bytes())['rows']
    for t in trials:
        assert t['exact_sha256']
        if t.get('strict_status')=='INVALID':
            assert not t['strict_exact_original']
            assert 'INVALID' in t['complete_record_status']


def test_lower_ceiling_with_fixed_accepted_average_does_not_reduce_cost():
    e=json.loads((HERE/'economics.json').read_bytes())
    shared=next(w for w in e['workloads'] if w['name']=='fixed_small_average_all_caps')
    rec=json.loads((HERE/'records.json').read_bytes())['rows']
    profiles=json.loads((HERE/'candidates.json').read_bytes())['profiles']
    assert shared['n']>0
    for p in profiles:
        assert all(sid in p['admitted_ids'] for sid in shared['object_ids'])
    assert shared['canonical_bytes']==sum(r['record_bytes'] for r in rec if r['id'] in shared['object_ids'])/shared['n']


def test_near_limit_gif_block_count_rejection_keeps_existing_identity_fallback():
    trials=json.loads((HERE/'codecs.json').read_bytes())['rows']
    t=next(t for t in trials if t['id']=='gif-boundary-2097152' and t['candidate']=='zstd-3')
    assert t['exact_sha256'] and t['strict_status']=='INVALID'
    assert (t['strict_stage'],t['strict_code'])==('frame','block_count')
    records=json.loads((HERE/'records.json').read_bytes())['rows']
    r=next(r for r in records if r['id']==t['id'])
    assert r['codec']=='identity' and r['exact_roundtrip']
