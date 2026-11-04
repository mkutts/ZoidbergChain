"""Bounded fresh full replay; timings/resources never affect exact comparisons."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OBSERVED={'worker_metrics','verification_wall_ns','worker_peak_commit_bytes',
          'encode_wall_ns','decode_wall_ns','encode_cpu_ns','decode_cpu_ns',
          'python_traced_peak_bytes','strict_verification_wall_ns','strict_worker_metrics'}
OBSERVED.add('cpu_batch_iterations')


def stable(value):
    if isinstance(value,dict):return {k:stable(v) for k,v in value.items() if k not in OBSERVED}
    if isinstance(value,list):return [stable(v) for v in value]
    return value


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=ROOT/'temp/task723-fresh-replay');args=ap.parse_args()
    out=args.output.resolve()
    assert ROOT/'temp' in out.parents and not out.exists(),'Use a fresh output directory under temp/'
    out.mkdir(parents=True)
    executions=[]
    for script,argv in [('run.py',['--output',str(out)]),('enrich.py',['--output',str(out)]),('crosscheck.py',[str(out)])]:
        cmd=[sys.executable,'-B',str(HERE/script),*argv]
        start=time.perf_counter()
        print('Replay start',script,flush=True)
        with (out/(script+'.log')).open('w',encoding='utf-8') as log:
            result=subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=600)
        executions.append(dict(argv=cmd,exit_code=result.returncode,elapsed_seconds=time.perf_counter()-start,
            log_tail=(out/(script+'.log')).read_text(encoding='utf-8').splitlines()[-8:]))
        (HERE/'replay_execution.json').write_text(json.dumps(executions,indent=2)+'\n',encoding='utf-8')
        assert result.returncode==0,script
    comparisons=[]
    for name in ('manifest.json','codecs.json','records.json','candidates.json','economics.json','baseline.json','crosscheck.json'):
        a=json.loads((HERE/name).read_bytes());b=json.loads((out/name).read_bytes())
        same=stable(a)==stable(b)
        comparisons.append(dict(file=name,deterministic_fields_equal=same))
    result=dict(status='PASS' if all(c['deterministic_fields_equal'] for c in comparisons) else 'FAIL',
        fresh_output=str(out),comparisons=comparisons,excluded_observations=sorted(OBSERVED),
        source='Full fresh original generation, all native profiles, selected and alternate complete signed records, independent arithmetic')
    (HERE/'replay_comparison.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result),flush=True)
    assert result['status']=='PASS'


if __name__=='__main__': main()
