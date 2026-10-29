"""Independent stdlib arithmetic, evidence and cost checks; no simulator import."""
import argparse
from collections import Counter
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def read(folder,name):
    return json.loads((folder/name).read_bytes())


def percentile(v,p):
    v=sorted(v)
    return v[(len(v)*p+99)//100-1]


def close(a,b):
    assert abs(Decimal(str(a))-Decimal(str(b))) <= max(Decimal('0.0001'),abs(Decimal(str(b)))*Decimal('1e-12')),(a,b)


def check(out):
    manifest=read(out,'manifest.json');recs=read(out,'records.json'); cs=read(out,'candidates.json');co=read(out,'codecs.json')
    byid={r['id']:r for r in recs['rows']+recs['diagnostic_controls']}
    assert len(byid)==len(manifest['samples'])==59
    for sample in manifest['samples']:
        r=byid[sample['id']]
        assert r['original_sha256']==sample['sha256'] and r['original_bytes']==sample['original_bytes']
        assert sample['license']=='CC0-1.0' and sample['synthetic'] and not sample['production_traffic']
        if r['record_bytes'] is None:
            assert r['original_bytes']>2097152
            continue
        assert sum(r['field_ledger'].values())==sum(r['partition'].values())==r['record_bytes']
        assert r['base64_media_bytes']==4*((r['encoded_bytes']+2)//3)
        assert r['nonmedia_bytes']==r['record_bytes']-r['base64_media_bytes']
        close(r['metadata_percent'],100*r['nonmedia_bytes']/r['record_bytes'])
        assert r['record_bytes']<=r['identity_record_bytes'] and r['exact_roundtrip']
    for r in recs['sensitivities']:
        assert sum(r['field_ledger'].values())==sum(r['partition'].values())==r['record_bytes']
        assert r['exact_roundtrip']
    for r in co['rows']:
        base=byid[r['id']]
        if base['record_bytes'] is None:
            assert r['complete_record_bytes'] is None and r['complete_record_status'].startswith('Unavailable')
            continue
        assert r['exact_sha256'] and r['complete_record_bytes']==base['record_bytes']+r['descriptor_bytes']-base['descriptor_bytes']
        assert r['serialized_media_member_bytes']==r['descriptor_bytes']+8
        if r['candidate'].startswith('brotli'):
            assert r['complete_record_status'].startswith('Hypothetical')
        elif r['encoded_bytes']<=2097152:
            assert r['complete_record_status'].startswith('Actual') and len(r['complete_record_sha256'])==64
            assert r['strict_status'] in ('VALID','INVALID')
            assert r['strict_exact_original']==(r['strict_status']=='VALID')
    rows=recs['rows']
    for c in cs['common_ceiling']+cs['separate_cap_grid']+cs['profiles']:
        admitted=[];excluded=[]
        for r in rows:
            cap=c['text_cap'] if r['mime']=='text/plain' else c['gif_cap'] if r['mime']=='image/gif' else c['static_cap']
            (admitted if r['original_bytes']<=cap else excluded).append(r)
        assert c['admitted_ids']==[r['id'] for r in admitted]
        assert c['admitted']==len(admitted) and c['excluded_by_mime']==dict(Counter(r['mime'] for r in excluded))
        close(c['admitted_percent'],100*len(admitted)/len(rows))
        assert c['safe_complete_bound']==4*((c['encoded_cap']+2)//3)+196608+98304+32768
        assert c['proposed_block_cap']>=c['safe_complete_bound'] and c['proposed_block_cap']<=3145728
        for field,key in [('original_bytes','original_bytes'),('record_bytes','record_bytes'),('metadata_percent','metadata_percent'),('certificate_bytes','certificate_value_bytes')]:
            for p in (50,95,99):
                close(c['statistics'][field][f'p{p}'],percentile([r[key] for r in admitted],p))
            close(c['statistics'][field]['worst'],max(r[key] for r in admitted))
        assert all(r['encoded_bytes']<=c['encoded_cap'] and r['record_bytes']<=c['proposed_block_cap'] for r in admitted)
    control=recs['diagnostic_controls'][0]
    assert control['original_bytes']==104 and control['encoded_bytes']==105 and control['record_bytes']==control['identity_record_bytes']-4
    e=read(out,'economics.json');D=lambda x:Decimal(str(x));G=D(2**30);checked=0
    workloads={w['name']:w for w in e['workloads']};profiles=e['inputs']['profiles'];params=e['inputs']['default']
    for scenario in e['scenarios']+e['sensitivities']:
        w=workloads[scenario['workload']];rate=scenario['blocks_per_day'];host=profiles[scenario['profile']]
        total=D(0)
        monthly=scenario.get('monthly',[scenario['month36']])
        for m in monthly:
            month=m['month'];days=e['inputs']['month_days']
            n=D(rate*sum(days[:month]));new=D(rate*days[month-1]);r=D(w['canonical_bytes']);c=n*r
            primary=G+c*D('1.25');head=primary*D('.2')+new*r*D('1.25')*D('1.45')+5*G
            local=3*primary+head;backup=primary*D('3.8')
            close(m['canonical_bytes'],c);close(m['primary_database_bytes'],primary)
            close(m['local_capacity_bytes'],local);close(m['backup_retained_bytes'],backup)
            billed=max(D(0),local/G-D(host['included_primary_gib'])).to_integral_value(rounding=ROUND_CEILING)
            outbytes=new*r*D('11.52')+primary*4+c*D('1.2')/12+primary*D('.95')/12
            cost=D(host['monthly_compute'])+billed*D(host['primary_gib_month'])+backup/G*D(host['backup_gib_month'])+outbytes/G*D(host['egress_gib'])
            close(m['cost_usd']['total'],cost);total+=cost;checked+=1
        if 'monthly' in scenario: close(scenario['three_year_cumulative_usd'],total)
    assert len(e['scenarios'])==36 and len(e['sensitivities'])==54
    return dict(status='PASS',primary_records=len(rows),diagnostic_records=1,codec_trials=len(co['rows']),
        candidates=len(cs['common_ceiling'])+len(cs['separate_cap_grid'])+len(cs['profiles']),
        decimal_month_checks=checked,metadata_target='FAIL retained',
        checks='Original identities, exact ledgers, base64, coverage, percentile ranks, component-budget bounds, complete codec records and independent Decimal costs')


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('output',nargs='?',type=Path,default=HERE);args=ap.parse_args()
    result=check(args.output)
    (args.output/'crosscheck.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
