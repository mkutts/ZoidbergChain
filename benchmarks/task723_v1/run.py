"""Isolated Task 7.23 measurement; no DB, active protocol or historical writes."""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name,ROOT/path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


corpus = load('meme723_corpus','benchmarks/task723_v1/corpus.py')
old = load('meme723_ledger','benchmarks/task720_v1/measure.py')
econ = load('meme723_econ','verification/task722/economics.py')
from canonical_v3 import block, media
from canonical_v3.primitives import canonical, MAX_RECORD
from codec_prototype.isolated_decoder import IsolatedDecoder, Status, Limits
from scripts import milestone_7_task_7_11_storage as fixtures
from scripts import milestone_7_task_7_4_benchmark as native
from media_admission_policy import media_admission_policy


def save(out, name, value):
    (out/name).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n',encoding='utf-8')


def dist(values):
    v=sorted(values)
    return {**{f'p{p}':v[math.ceil(len(v)*p/100)-1] for p in (50,95,99)},
            'worst':max(v),'mean':statistics.mean(v)}


def cpu_times(operation, value, wall_ns):
    # Windows process CPU counters have coarse ticks. Amortize ~20 ms of work
    # rather than misreporting single-call sub-tick observations as zero work.
    iterations=max(1,min(200000,math.ceil(20000000/max(1,statistics.median(wall_ns)))))
    timings=[]
    for _ in range(5):
        start=time.process_time_ns()
        for _ in range(iterations):
            operation(value)
        timings.append((time.process_time_ns()-start)/iterations)
    return timings,iterations


def encoded_bound(original_cap):
    # Generous 1 KiB above identity; covers selector label/base64 rounding gains.
    # Also independently caps alternate externally supplied valid encodings.
    return min(media.MAX_ENCODED,original_cap+1024)


def budgets(encoded):
    b64=4*((encoded+2)//3)
    overhead=196608+98304+32768  # Exact disjoint check_budgets ceilings.
    safe=b64+overhead
    cap=math.ceil(safe/65536)*65536
    assert cap <= MAX_RECORD
    return dict(encoded_cap=encoded,base64_bound=b64,certificate_reserve=196608,
        native_transactions_reserve=98304,rest_reserve=32768,
        safe_complete_bound=safe,proposed_block_cap=cap,rounding_headroom=cap-safe)


def summarize(rows):
    population=rows
    rows=[r for r in rows if r.get('record_bytes') is not None]
    return dict(n=len(population),valid_record_n=len(rows),mime_counts=dict(Counter(r['mime'] for r in population)),
        original_bytes=dist([r['original_bytes'] for r in population]),
        record_bytes=dist([r['record_bytes'] for r in rows]),
        metadata_percent=dist([r['metadata_percent'] for r in rows]),
        metadata_bytes=dist([r['nonmedia_bytes'] for r in rows]),
        certificate_bytes=dist([r['certificate_value_bytes'] for r in rows]),
        choices=dict(Counter(r['codec'] for r in rows)),
        below15=sum(r['metadata_percent']<15 for r in rows),
        metadata_target='FAIL' if any(r['metadata_percent']>=15 for r in rows) else 'PASS',
        worker_peak_commit_bytes=max(r['worker_metrics'].get('peak_job_commit_bytes',0) for r in rows),
        verification_wall_ns=dist([r['verification_wall_ns'] for r in rows]))


def candidate(rows, name, static, gif, text):
    selected=[]; excluded=[]
    for r in rows:
        ceiling=text if r['mime']=='text/plain' else gif if r['mime']=='image/gif' else static
        (selected if r['original_bytes']<=ceiling else excluded).append(r)
    b=budgets(encoded_bound(max(static,gif,text)))
    assert all(r['encoded_bytes']<=b['encoded_cap'] and r['record_bytes']<=b['proposed_block_cap'] for r in selected)
    return dict(name=name,status='PROPOSED UNAPPROVED INACTIVE',static_cap=static,gif_cap=gif,text_cap=text,
        **b,admitted_ids=[r['id'] for r in selected],admitted=len(selected),population=len(rows),
        admitted_percent=100*len(selected)/len(rows),statistics=summarize(selected),
        exclusions=[dict(id=r['id'],mime=r['mime'],original_bytes=r['original_bytes']) for r in excluded],
        excluded_by_mime=dict(Counter(r['mime'] for r in excluded)))


def codec_measure(samples, out):
    profiles=[dict(id='identity',codec='identity')]+[
        dict(id=f'{c}-{level}',codec=c,level=level) for c,levels in
        [('zstd',(1,3,9)),('brotli',(1,5,9))] for level in levels]
    rows=[]
    for profile in profiles:
        enc,dec,details=native._operations(profile)
        for s in samples:
            raw=s['raw']; encoded,enc_wall=native._timed(enc,raw,5,1)
            restored,dec_wall=native._timed(dec,encoded,5,1)
            assert restored==raw and hashlib.sha256(restored).hexdigest()==s['sha256']
            ecpu,enc_iterations=cpu_times(enc,raw,enc_wall)
            dcpu,dec_iterations=cpu_times(dec,encoded,dec_wall)
            tracemalloc.start()
            mem_encoded=enc(raw); mem_restored=dec(mem_encoded)
            _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
            assert mem_restored==raw
            descriptor=native._descriptor_size(encoded,dict(bytes=raw,mime_type=s['mime']),profile['codec'])
            rows.append(dict(id=s['id'],mime=s['mime'],candidate=profile['id'],
                original_bytes=len(raw),encoded_bytes=len(encoded),descriptor_bytes=descriptor,
                encoded_sha256=hashlib.sha256(encoded).hexdigest(),exact_sha256=True,
                canonical_compatibility='VALID codec ID; strict worker measured on selected profile only' if profile['codec'] in ('identity','zstd') else 'COMPARISON ONLY; invalid frozen v3 codec ID',
                raw_expansion=len(encoded)>len(raw),encode_wall_ns=enc_wall,decode_wall_ns=dec_wall,
                encode_cpu_ns=ecpu,decode_cpu_ns=dcpu,python_traced_peak_bytes=peak,
                cpu_batch_iterations=dict(encode=enc_iterations,decode=dec_iterations)))
        print('Codec',profile['id'],'done',flush=True)
    aggregates={}
    for p in profiles:
        sub=[r for r in rows if r['candidate']==p['id']]
        aggregates[p['id']]=dict(original=sum(r['original_bytes'] for r in sub),
            encoded=sum(r['encoded_bytes'] for r in sub),raw_expansions=sum(r['raw_expansion'] for r in sub),
            encode_cpu_ns=dist([statistics.median(r['encode_cpu_ns']) for r in sub]),
            decode_cpu_ns=dist([statistics.median(r['decode_cpu_ns']) for r in sub]))
    save(out,'codecs.json',dict(profiles=profiles,rows=rows,aggregates=aggregates,
        repetitions=5,warmups=1,clock='perf_counter_ns wall; process_time_ns CPU, amortized ~20ms batches including loop/call overhead; capped at 200000 iterations',
        memory='tracemalloc peak is Python allocations during separate untimed encode/decode only; excludes native arenas, NOT total RSS. Strict selected-worker job peaks separately available.'))


def simulations(rows, profiles, out):
    inputs=json.loads((ROOT/'verification/task722/economic_inputs.json').read_bytes())
    cases=[];scenarios=[]
    for p in profiles:
        sub=[r for r in rows if r['id'] in p['admitted_ids']]
        w=econ.workload(p['name'],sub)
        cases.append(w)
        for rate in (100,1000,10000):
            for host in inputs['profiles'].values():
                scenarios.append(econ.simulate(w,rate,host,monthly=True))
    # Equal average accepted bytes under every ceiling: cap alone changes no bill.
    common=[r for r in rows if r['original_bytes']<=8192]
    w=econ.workload('fixed_small_average_all_caps',common);cases.append(w)
    for rate in (100,1000,10000):
        for host in inputs['profiles'].values():
            scenarios.append(econ.simulate(w,rate,host,monthly=True))
    # Independent expected-size change: reweight unchanged accepted records.
    sensitivities=[]
    for p in profiles:
        for label,subset in [('small',[r for r in rows if r['id'] in p['admitted_ids'] and r['original_bytes']<=16384]),
                             ('largest_quartile',sorted([r for r in rows if r['id'] in p['admitted_ids']],key=lambda r:r['original_bytes'])[-max(1,p['admitted']//4):])]:
            w=econ.workload(p['name']+'_'+label,subset);cases.append(w)
            for rate in (100,1000,10000):
                for host in inputs['profiles'].values():
                    sensitivities.append(econ.simulate(w,rate,host))
    save(out,'economics.json',dict(source='Task 7.22 unchanged simulate() and prices; analytical, unquoted',
        inputs=inputs,workloads=cases,scenarios=scenarios,sensitivities=sensitivities,
        worst_case_canonical_bytes_3yr={p['name']:{str(rate):1095*rate*p['proposed_block_cap'] for rate in (100,1000,10000)} for p in profiles},
        review_journal='Excluded; future unapproved journal/authority/finality traffic is not zero and is not funded by these media-only bills'))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=HERE)
    ap.add_argument('--reuse-codecs',action='store_true',help='Development resume: verify existing original identities, skip native timings')
    args=ap.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    assert out==HERE or ROOT/'temp' in out.parents, 'Outputs confined to package or temp subtree'
    os.environ['TEMP']=os.environ['TMP']=str(ROOT/'temp')
    samples=corpus.build();manifest=corpus.manifest(samples)
    if (HERE/'manifest.json').exists():
        assert manifest==json.loads((HERE/'manifest.json').read_bytes()),'Corpus identity drift'
    save(out,'manifest.json',manifest)
    print('Corpus generated:',len(samples),flush=True)
    if args.reuse_codecs:
        prior=json.loads((out/'codecs.json').read_bytes())
        assert len(prior['rows'])==len(samples)*7
        assert all(r['original_bytes']==next(s['original_bytes'] for s in samples if s['id']==r['id']) for r in prior['rows'])
    else:
        codec_measure(samples,out)
    rows=[];controls=[];sensitivity=[]
    with IsolatedDecoder() as worker:
        for i,s in enumerate(samples,1):
            if len(s['raw'])>(media.MAX_TEXT if s['mime']=='text/plain' else media.MAX_IMAGE):
                rows.append(dict(id=s['id'],mime=s['mime'],category=s['category'],source_bytes=len(s['raw']),
                    original_bytes=len(s['raw']),original_sha256=s['sha256'],record_bytes=None,
                    record_status='Original exceeds frozen v3 ceiling; no valid complete record exists',
                    active_admission=old.admission(s)))
                print('Retained capacity exclusion',s['id'],len(s['raw']),flush=True)
                continue
            raw=fixtures.corpus_record(s['raw'],s['mime'],s['id'],i,fixtures.CTX.genesis_hash,worker)
            start=time.perf_counter_ns(); row=old.record_row(s,raw,'meme723',worker)
            row['verification_wall_ns']=time.perf_counter_ns()-start
            row['record_sha256']=hashlib.sha256(raw).hexdigest()
            row['active_admission']=old.admission(s)
            row['full_serialized_media_bytes']=row['partition']['serialized_media_representation_bytes']
            p=json.loads(raw)['envelope']['payload']
            row['certificate_value_bytes']=len(canonical(p['admission_certificate']))
            assert row['original_sha256']==s['sha256'] and row['source_bytes']==row['original_bytes']
            (controls if s['category']=='diagnostic-control' else rows).append(row)
            if s['id'] in ('text-8','jpeg-caption-320','gif-boundary-2097152'):
                for mode in ('ten-votes','long-metadata'):
                    modified=old.modified_record(raw,mode)
                    sr=old.record_row(s,modified,'sensitivity',worker)
                    sensitivity.append(dict(mode=mode,**sr))
            print('Record',i,s['id'],row['record_bytes'],flush=True)
    assert len(controls)==1 and controls[0]['encoded_bytes']>controls[0]['original_bytes']
    assert controls[0]['record_bytes']<controls[0]['identity_record_bytes']
    save(out,'records.json',dict(rows=rows,diagnostic_controls=controls,sensitivities=sensitivity,
        context='Frozen public fixture keys/context, fourteen votes, empty native transfers. Format/crypto evidence, not chain authority or live admission.'))
    candidates=[candidate(rows,f'common_{cap}',cap,cap,media.MAX_TEXT) for cap in corpus.CAPS]
    grid=[candidate(rows,f'{s}_{g}_{t}',s,g,t) for s in corpus.CAPS for g in corpus.CAPS for t in (8192,16384,65536,262144)]
    profiles=[candidate(rows,'A_lean',131072,262144,8192),
              candidate(rows,'B_balanced',262144,524288,16384),
              candidate(rows,'C_flexible',524288,1048576,65536)]
    save(out,'candidates.json',dict(common_ceiling=candidates,separate_cap_grid=grid,profiles=profiles,
        primary=summarize(rows),preferred='B_balanced',all_values='PROPOSED UNAPPROVED INACTIVE',
        method='Original-size gates only; WebP animation conservatively uses static MIME cap, separate dimensions/frame defenses remain required'))
    simulations(rows,profiles,out)
    save(out,'baseline.json',dict(inactive_v3=dict(original_image=media.MAX_IMAGE,original_text=media.MAX_TEXT,
        encoded=media.MAX_ENCODED,complete=MAX_RECORD,analytic_bound=block.conservative_size_bound()),
        active_policy=media_admission_policy(),worker_limits=vars(Limits()),
        strict_decoder=dict(max_original=2097152,max_window=262144,max_blocks=64,native_arena=1048576),
        primary_population='All semantic and boundary samples; text-expansion-control excluded ONLY as predeclared diagnostic'))
    print('Study complete',len(rows),'primary records;',len(grid),'separate-cap scenarios',flush=True)


if __name__=='__main__':
    main()
