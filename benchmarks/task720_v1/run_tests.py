"""Bounded reproducible regression selection; no storage/WAL replay or API tests."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent


def main():
    scratch=ROOT/'temp'/('task720-tests-'+uuid.uuid4().hex)
    scratch.mkdir(parents=True)
    env=dict(os.environ,TEMP=str(scratch),TMP=str(scratch),PYTHONDONTWRITEBYTECODE='1')
    groups={
        'acceptance':['benchmarks/task720_v1/test_acceptance.py','verification/task719/test_reproduction_guards.py'],
        'measurements':['tests/test_milestone_7_task_'+n+'.py' for n in
            ('7_3_corpus','7_4_benchmark','7_4a_image_evaluation','7_7_block_composition')],
        'codecs':['tests/test_milestone_7_task_'+n+'.py' for n in
            ('7_6_decoder','7_6a_sequences','7_6b_performance','7_6c_isolation','7_6d_linux_isolation','7_6d_evidence')],
        'format':['tests/test_milestone_7_task_7_10c_v3.py'],
    }
    outcomes=[]
    for name,files in groups.items():
        argv=[sys.executable,'-B','-m','pytest',*files,'-q','--tb=short','-p','no:cacheprovider',
              '-p','verification.task719.pytest_evidence','--basetemp='+str(scratch/name)]
        env['TASK719_OUTCOMES']=str(OUT/(name+'_outcomes.json'))
        started=time.monotonic()
        with (OUT/(name+'_tests.txt')).open('w',encoding='utf-8') as log:
            process=subprocess.Popen(argv,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            try:
                rc=process.wait(timeout=240)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(); rc='TIMEOUT'
        outcomes.append(dict(group=name,argv=argv,cwd=str(ROOT),timeout_seconds=240,exit=rc,elapsed=time.monotonic()-started))
        print(name,rc,flush=True)
    (OUT/'tests_execution.json').write_text(json.dumps(dict(scratch=str(scratch),groups=outcomes),indent=2)+'\n',encoding='utf-8')
    if any(r['exit']!=0 for r in outcomes):
        raise SystemExit(1)


if __name__=='__main__':
    main()
