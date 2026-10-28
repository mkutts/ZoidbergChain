"""Preservation, observed resources and checksum inventory for owner review."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name,value):
    (HERE/name).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n',encoding='utf-8')


def main():
    before=json.loads((HERE/'before.json').read_bytes())
    changed={p:dict(before=old,after=sha(ROOT/p)) for p,old in before['tracked_sha256'].items() if sha(ROOT/p)!=old}
    assert set(changed)=={'tests/test_milestone_7_task_7_3_corpus.py'}
    git=lambda *a:subprocess.check_output(['git',*a],cwd=ROOT).decode().strip()
    assert git('rev-parse','HEAD')==before['head']
    assert git('branch','--show-current')==before['branch']
    assert not git('diff','--cached','--name-only')
    save('preservation.json',dict(head=before['head'],branch=before['branch'],tracked_inputs=len(before['tracked_sha256']),
        changed=changed,all_other_tracked_sha256_unchanged=True,index_diff=[],
        status=git('status','--porcelain=v1','--untracked-files=all').splitlines()))
    records=json.loads((HERE/'records.json').read_bytes())
    observed=[]
    for r in records['rows']:
        observed.append(r['worker_metrics'])
        observed.extend(t['worker_metrics'] for t in r['strict_source_roundtrips'])
    summary={}
    for key in ('peak_job_commit_bytes','peak_process_commit_bytes','process_user_ns','process_kernel_ns','total_ns'):
        values=sorted(m[key] for m in observed if key in m)
        if values:
            summary[key]=dict(observations=len(values),p50=values[(len(values)*50+99)//100-1],
                p95=values[(len(values)*95+99)//100-1],worst=max(values))
    rejected=[dict(id=r['id'],population=r['population'],**{k:v for k,v in t.items() if k!='worker_metrics'})
        for r in records['rows'] for t in r['strict_source_roundtrips'] if t['status']!='VALID']
    save('resource_summary.json',dict(worker=summary,rejected_source_candidates=rejected,
        exact_source_roundtrips=sum(t['exact_source_bytes'] for r in records['rows'] for t in r['strict_source_roundtrips']),
        native_codec_peak='unavailable, benchmark parent not instrumented; no tracemalloc/native equivalence claim',
        note='Windows job/process commit observations, not RSS or a cross-platform memory bound proof'))
    historical_storage=ROOT/'benchmarks/milestone_7_task_7_11_results.json'
    storage=json.loads(historical_storage.read_bytes())
    proofs={name:dict(bytes=(ROOT/'tests/fixtures/milestone_7_v3_v1'/name).stat().st_size,
        sha256=sha(ROOT/'tests/fixtures/milestone_7_v3_v1'/name)) for name in ('finality.json','finality-proof.json')}
    save('external_overhead.json',dict(finality=dict(frozen_examples=proofs,
        note='Separate canonical objects; examples, not measured finality distribution or universal per-block constant'),
        database=dict(new_measurement=False,historical_reference=historical_storage.relative_to(ROOT).as_posix(),
            sha256=sha(historical_storage),corpus=storage['corpus'],
            note='Historical 7.11 observations only; no WAL replay or fresh physical/index attribution. Not included in R.'),
        future_review_journal='Unapproved future commitments excluded; no implementation or invented byte allowance'))
    report=ROOT/'docs/milestone-7-production-like-compression-and-metadata-acceptance.md'
    paths=sorted(p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='checksums.sha256')
    paths.append(report)
    (HERE/'checksums.sha256').write_text(''.join(sha(p)+'  '+p.relative_to(ROOT).as_posix()+'\n' for p in paths),encoding='utf-8')
    print('Preserved',len(before['tracked_sha256'])-1,'tracked files; only authorized stale-test module changed; checksums:',len(paths))


if __name__=='__main__':
    main()
