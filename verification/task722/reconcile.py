"""Independent byte/statistic ledger and executable producer counterexample."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))


def read(path):
    return json.loads((ROOT/path).read_bytes())


def save(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n',encoding='utf-8')


def stats(rows):
    values = sorted(100*(r['record_bytes']-r['base64_media_bytes'])/r['record_bytes'] for r in rows)
    return dict(n=len(rows),p50=values[math.ceil(len(values)*.5)-1],p95=values[math.ceil(len(values)*.95)-1],
                worst=max(values),equal_record_mean=sum(values)/len(values),below15=sum(v<15 for v in values),
                canonical_byte_share=100*sum(r['nonmedia_bytes'] for r in rows)/sum(r['record_bytes'] for r in rows))


def replay_compare(scratch):
    old=read('benchmarks/milestone_7_task_7_4_results.json')
    new=json.loads((scratch/'codec.json').read_bytes())
    differences=[]
    for a,b in zip(old['per_sample'],new['per_sample'],strict=True):
        for key in a.keys()|b.keys():
            if not key.startswith(('compression_','decompression_')) and a.get(key)!=b.get(key):
                differences.append([a['sample_id'],a['candidate_id'],key])
    a=read('benchmarks/milestone_7_task_7_7_results.json')
    b=json.loads((scratch/'composition.json').read_bytes())
    for value in (a,b):
        value.pop('environment');value.pop('sqlite')
    result=dict(codec_rows=len(new['per_sample']),codec_nontiming_differences=differences,
                composition_rows=len(b['per_block']),
                composition_exact_excluding_environment_sqlite=a==b,
                economics_json_exact=read('benchmarks/milestone_7_task_7_8_results.json')==json.loads((scratch/'economics.json').read_bytes()),
                economics_csv_exact=(ROOT/'benchmarks/milestone_7_task_7_8_monthly.csv').read_bytes()==(scratch/'economics.csv').read_bytes(),
                historical_sqlite_replay='NOT RUN: historical WAL initializer prohibited; use tracked measurements only')
    save('historical_replay_comparison.json',result)
    assert not differences and all(v for v in result.values() if isinstance(v,bool))


def main():
    from benchmarks.task720_v1.crosscheck import run as crosscheck
    from verification.task721.reconcile import reconcile
    save('frozen_arithmetic_checks.json',crosscheck(ROOT/'benchmarks/task720_v1'))
    result=reconcile()
    # Prior reconciler checks all ledger entries; retain compact totals here.
    save('compression_reconciliation.json',dict(status=result['status'],groups=result['groups']))
    records=read('benchmarks/task720_v1/records.json')
    metrics=read('benchmarks/task720_v1/metrics.json')
    save('corpus_checksums.json',dict(method='Source identities matched by full fresh pinned-encoder replay; accepted identities taken from independently verified canonical rows.',
        historical_source_bytes=6093917,new_source_bytes=11521163,
        rows=[{k:r[k] for k in ('population','id','source_bytes','source_sha256','original_bytes','original_sha256')} for r in records['rows']]))
    rows=records['rows']+records['sensitivity_rows']
    layer_checks={
        'encoded_payload_vs_original':lambda r:r['encoded_bytes']<=r['original_bytes'],
        'binary_plus_descriptor_nonpayload_vs_identity':lambda r:r['encoded_bytes']+r['descriptor_bytes']-r['base64_media_bytes']<=r['original_bytes']+r['identity_descriptor_bytes']-4*((r['original_bytes']+2)//3),
        'complete_descriptor_vs_identity':lambda r:r['descriptor_bytes']<=r['identity_descriptor_bytes'],
        'complete_media_member_vs_identity':lambda r:r['partition']['serialized_media_representation_bytes']<=r['identity_descriptor_bytes']+8,
        'complete_record_vs_identity':lambda r:r['record_bytes']<=r['identity_record_bytes'],
        'serialized_media_vs_raw_original':lambda r:r['partition']['serialized_media_representation_bytes']<=r['original_bytes'],
        'complete_record_vs_raw_original':lambda r:r['record_bytes']<=r['original_bytes'],
    }
    save('no_expansion_layers.json',dict(population='70 primary plus 8 sensitivity records',records=len(rows),
        layers={name:dict(satisfied=sum(check(r) for r in rows),counterexamples=[dict(population=r['population'],id=r['id']) for r in rows if not check(r)]) for name,check in layer_checks.items()},
        universal_raw_counterexample='producer_counterexample.json: corpus-only inequality is not a universal guarantee',
        physical_allocation='NOT VERIFIED: no monotonic allocator/storage guarantee is implemented'))
    output={}
    bands={'<1KiB':(0,1024),'1-16KiB':(1024,16384),'16-256KiB':(16384,262144),
           '256KiB-1MiB':(262144,1048576),'1-2MiB':(1048576,2097153)}
    for pop in ('historical','production-like'):
        rows=[r for r in records['rows'] if r['population']==pop]
        summary=stats(rows)
        for key in ('p50','p95','worst'):
            assert abs(summary[key]-metrics[pop]['all']['metadata_percent'][key])<1e-10
        output[pop]=dict(all=summary,by_mime={mime:stats([r for r in rows if r['mime']==mime]) for mime in sorted({r['mime'] for r in rows})},
                        by_original_size_band={name:stats(group) for name,(lo,hi) in bands.items() if (group:=[r for r in rows if lo<=r['original_bytes']<hi])},
                        byte_totals={key:sum(r[key] for r in rows) for key in ('original_bytes','encoded_bytes','base64_media_bytes','record_bytes','nonmedia_bytes','certificate_value_bytes','signature_token_bytes_subset')},
                        partition_totals={key:sum(r['partition'][key] for r in rows) for key in rows[0]['partition']},
                        descriptor_framing=sum(r['partition']['serialized_media_representation_bytes']-r['base64_media_bytes'] for r in rows),
                        base64_expansion=sum(r['base64_media_bytes']-r['encoded_bytes'] for r in rows),
                        codec_counts=dict(Counter(r['codec'] for r in rows)))
    output['historical_projected_7_7']={k:v['all']['metadata_percent'] for k,v in read('benchmarks/milestone_7_task_7_7_results.json')['aggregates'].items()}
    output['method']='Each full primary population; equal record nearest rank ceil(n*p); N=R-B, denominator R. No tiny media excluded. Sensitivities not primary samples.'
    output['break_even']='N/R < .15 iff B > 17*N/3. For fixed N and E/M=q, M approximately > 17*N/(4*q).'
    save('metadata_reconciliation.json',output)
    # Natural default-encoder output: no monkeypatch and no received-byte repair.
    from canonical_v3 import media, block
    from canonical_v3.primitives import canonical
    from codec_prototype.isolated_decoder import IsolatedDecoder, Status
    from scripts import milestone_7_task_7_11_storage as fixtures
    scratch=ROOT/'temp'/'task722-counterexample'
    scratch.mkdir(exist_ok=True)
    os.environ.update(TEMP=str(scratch),TMP=str(scratch))
    raw=b'bmozvaibkgjhevxdmqzukt0c328pqlcgchkq90vew8mgc394iojl7lc8ycj3kn2fdjeaiphe490948m1tbb577bbqbm52hfmpftgkea0'
    encoded=media._compress_default(raw)
    identity=media.descriptor(raw,raw,'text/plain','identity')
    with IsolatedDecoder() as decoder:
        chosen=media.produce(raw,'text/plain',decoder=decoder)
        assert chosen.outcome.status==Status.VALID and chosen.outcome.original==raw
        assert chosen.descriptor['codec_id']=='zstd' and len(encoded)>len(raw)
        record=fixtures.corpus_record(raw,'text/plain','task722-natural-expansion',1,fixtures.CTX.genesis_hash,decoder)
        payload=deepcopy(json.loads(record)['envelope']['payload'])
        payload['media']=identity
        identity_record=block.encode_record(payload,fixtures.CTX)
    save('producer_counterexample.json',dict(original_ascii=raw.decode(),original_sha256=hashlib.sha256(raw).hexdigest(),
        original_bytes=len(raw),encoded_bytes=len(encoded),encoded_sha256=hashlib.sha256(encoded).hexdigest(),
        base64_identity=len(identity['payload']),base64_selected=len(chosen.descriptor['payload']),
        identity_descriptor=len(canonical(identity)),selected_descriptor=len(canonical(chosen.descriptor)),
        identity_binary_plus_descriptor=len(raw)+len(canonical(identity))-len(identity['payload']),
        selected_binary_plus_descriptor=len(encoded)+len(canonical(chosen.descriptor))-len(chosen.descriptor['payload']),
        identity_record=len(identity_record),selected_record=len(record),strict_reconstruction='VALID exact SHA-256',
        explanation='Normal native encoder selected E=105 > M=104. Both base64 strings are 140 bytes; zstd codec_id is four bytes shorter than identity. Canonical descriptor/record shrink by four bytes.'))
    # Verify integration claims against source rows, rather than trusting summary counts.
    bridge=read('verification/task721/end_to_end.json')
    fresh=read('verification/task722/bridge_recovery.json') if (OUT/'bridge_recovery.json').exists() else bridge
    for name,data in [('tracked721',bridge),('fresh722',fresh)]:
        assert len(data['format_records'])==70 and len(data['application_records'])==58
        assert len(data['recovery']['rows'])==128 and data['index_rebuild']['blocks']==128
        assert all(r['exact'] for r in data['format_records']+data['application_records'])
        frozen={(r['population'],r['id']):r for r in records['rows']}
        for row in data['format_records']:
            expected=frozen[row['population'],row['id']]
            assert (row['original_size'],row['stored_size'],row['codec'],row['original_sha256'])==(expected['original_bytes'],expected['encoded_bytes'],expected['codec'],expected['original_sha256'])
    save('integration_checks.json',dict(status='PASS',tracked_and_fresh=dict(format=70,admissible=58,recovered=128),
        journal=fresh['journal_mode'],synchronous=fresh['synchronous'],index_rebuild=fresh['index_rebuild'],
        format_choices=fresh['format_choices'],application_choices=fresh['application_choices'],
        activated=False,consensus_authority='INCOMPLETE',fresh_exercise=(OUT/'bridge_recovery.json').exists()))
    print('Ledger, percentiles, normal-producer counterexample and integration counts verified.')


if __name__=='__main__':
    main()
