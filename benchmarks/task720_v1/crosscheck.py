"""Independent stdlib arithmetic checks over recorded rows (no measurement imports)."""
import hashlib
import json
import math
from pathlib import Path
import sys


def run(directory):
    directory=Path(directory)
    read=lambda name:json.loads((directory/name).read_bytes())
    records=read('records.json'); metrics=read('metrics.json'); codecs=read('codecs.json'); manifest=read('manifest.json')
    rows=records['rows']
    def nearest(values,p):
        return sorted(values)[math.ceil(len(values)*p/100)-1]
    for row in rows+records['sensitivity_rows']:
        assert sum(row['field_ledger'].values())==sum(row['partition'].values())==row['record_bytes']
        assert row['base64_media_bytes']==4*math.ceil(row['encoded_bytes']/3)
        assert row['nonmedia_bytes']+row['base64_media_bytes']==row['record_bytes']
        assert row['metadata_percent']==100*row['nonmedia_bytes']/row['record_bytes']
        assert row['metadata_over_original_percent']==100*row['nonmedia_bytes']/row['original_bytes']
        assert row['record_bytes']<=row['identity_record_bytes']
        assert row['descriptor_bytes']<=row['identity_descriptor_bytes']
        assert row['exact_roundtrip']
    for pop in ('historical','production-like'):
        group=[r for r in rows if r['population']==pop]
        summary=metrics[pop]['all']
        for field,total in summary['totals'].items():
            assert total==sum(r[field] for r in group)
        values=[r['metadata_percent'] for r in group]
        assert summary['metadata_percent']['p50']==nearest(values,50)
        assert summary['metadata_percent']['p95']==nearest(values,95)
        assert summary['metadata_percent']['worst']==max(values)
        assert summary['canonical_byte_weighted_metadata_percent']==100*sum(r['nonmedia_bytes'] for r in group)/sum(r['record_bytes'] for r in group)
        assert summary['original_byte_weighted_mean_metadata_percent']==sum(r['metadata_percent']*r['original_bytes'] for r in group)/sum(r['original_bytes'] for r in group)
    ids={s['id'] for s in manifest['samples']}
    current=[r for r in rows if r['population']=='production-like']
    assert {r['id'] for r in current}==ids and len(ids)==len(current)
    assert {r['mime'] for r in current}=={'text/plain','image/png','image/jpeg','image/gif','image/webp'}
    assert len(codecs['rows'])==7*len(ids)
    zstd={r['id']:r for r in codecs['rows'] if r['candidate']=='zstd-3'}
    for row in current:
        trial=zstd[row['id']]
        assert row['source_bytes']==row['original_bytes']
        valid=next(t for t in row['strict_source_roundtrips'] if t['codec']=='zstd')['status']=='VALID'
        expected='zstd' if valid and trial['descriptor_bytes']<trial['identity_descriptor_bytes'] else 'identity'
        assert row['descriptor_bytes']==(trial['descriptor_bytes'] if expected=='zstd' else trial['identity_descriptor_bytes'])
        assert row['codec']==expected
    for c in codecs['rows']:
        assert c['exact_roundtrip']
        assert c['expands']==(c['encoded_bytes']>c['original_bytes'])
        assert c['savings_percent']==100*(1-c['encoded_bytes']/c['original_bytes'])
    for candidate,categories in codecs['aggregates'].items():
        for category,summary in categories.items():
            group=[r for r in codecs['rows'] if r['candidate']==candidate and r['category']==category]
            assert summary['original_bytes']==sum(r['original_bytes'] for r in group)
            assert summary['encoded_bytes']==sum(r['encoded_bytes'] for r in group)
            assert summary['byte_weighted_savings_percent']==100*(1-summary['encoded_bytes']/summary['original_bytes'])
    return dict(status='PASS',canonical_rows=len(rows),sensitivity_rows=len(records['sensitivity_rows']),codec_rows=len(codecs['rows']),
        exact_ledger_rows=len(rows)+len(records['sensitivity_rows']),percentile='independent math.ceil nearest rank',
        input_sha256={n:hashlib.sha256((directory/n).read_bytes()).hexdigest() for n in ('manifest.json','records.json','metrics.json','codecs.json')})


if __name__=='__main__':
    directory=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent
    result=run(directory)
    (directory/'crosscheck.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps(result))
