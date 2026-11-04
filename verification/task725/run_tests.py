"""Bounded focused regressions with per-node machine-readable outcomes."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
GROUPS={
    'canonical':['tests/test_milestone_7_task_7_10c_v3.py'],
    'codecs':['tests/test_milestone_7_task_7_6_decoder.py','tests/test_milestone_7_task_7_6a_sequences.py','tests/test_milestone_7_task_7_6c_isolation.py'],
    'persistence':['verification/task721/test_bridge.py'],
    'historical_arithmetic':['tests/test_milestone_7_task_7_8_node_economics.py','verification/task719/test_reproduction_guards.py','benchmarks/task723_v1/test_study.py'],
    'physical':['verification/task725/test_measurements.py'],
}


def run(out, groups):
    out.mkdir(parents=True,exist_ok=True)
    scratch=Path(tempfile.mkdtemp(prefix='task725-tests-',dir=ROOT/'temp'))
    records=[]
    for name in groups:
        argv=[sys.executable,'-B','-m','pytest',*GROUPS[name],'-q','--tb=short','-p','no:cacheprovider',
            '-p','verification.task719.pytest_evidence','--basetemp='+str(scratch/name)]
        env=dict(os.environ,TEMP=str(scratch),TMP=str(scratch),PYTHONDONTWRITEBYTECODE='1',TASK719_OUTCOMES=str(out/(name+'_outcomes.json')))
        if (out/'projections.json').exists():
            env['TASK725_EVIDENCE']=str(out)
        start=time.monotonic()
        with (out/(name+'_tests.txt')).open('w',encoding='utf-8') as log:
            p=subprocess.Popen(argv,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            try: rc=p.wait(timeout=360)
            except subprocess.TimeoutExpired:
                p.kill();p.wait();rc='TIMEOUT'
        record=dict(group=name,argv=argv,cwd=str(ROOT),exit=rc,timeout_seconds=360,elapsed_seconds=time.monotonic()-start)
        path=out/(name+'_outcomes.json')
        if path.exists():
            outcomes=json.loads(path.read_bytes())
            counter=Counter(r['outcome'] for r in outcomes['reports'])
            record.update(counts={k:counter[k] for k in ('passed','failed','skipped')},deselected=len(outcomes['deselected']))
        records.append(record)
        print(name,rc,record.get('counts'),flush=True)
    path=out/'tests_execution.json'
    old=json.loads(path.read_bytes())['groups'] if path.exists() else []
    merged={r['group']:r for r in old};merged.update({r['group']:r for r in records})
    summary=dict(groups=list(merged.values()),timeouts=sum(r['exit']=='TIMEOUT' for r in merged.values()),
                 counts=dict(sum((Counter(r.get('counts',{})) for r in merged.values()),Counter())),
                 deselected=sum(r.get('deselected',0) for r in merged.values()),
                 unsupported_platform_cases='Windows reference only; Linux/macOS not exercised. Skipped node IDs, if any, are in outcome files; not passes.',
                 deliberately_not_selected=['Legacy 7.11 V3Store WAL initializer/storage tests', 'WAL crash tests', 'Live API/consensus/network activation or future archiving tests'])
    summary['counts']={k:summary['counts'].get(k,0) for k in ('passed','failed','skipped')}
    path.write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
    return all(r['exit']==0 for r in records)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--group',action='append',choices=list(GROUPS));ap.add_argument('--output',type=Path,default=HERE)
    args=ap.parse_args();out=args.output.resolve()
    assert out==HERE or ROOT/'temp' in out.parents
    raise SystemExit(0 if run(out,args.group or list(GROUPS)) else 1)
