"""Bounded follow-ups for the incomplete combined v3 run, then supplemental QA."""
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def main():
    scratch = ROOT / 'temp' / ('task718-followup-' + uuid.uuid4().hex)
    scratch.mkdir(parents=True)
    env = dict(os.environ, TEMP=str(scratch), TMP=str(scratch), PYTHONDONTWRITEBYTECODE='1')
    groups = [
        ('api_diagnostic', ['tests/test_milestone_7_task_7_12_image_admission.py::test_public_upload_local_failure_is_503_and_persists_nothing'], 45),
        ('format_storage_recheck', ['tests/test_milestone_7_task_7_10c_v3.py','tests/test_milestone_7_task_7_11_storage.py'], 240),
        ('image_recheck', ['tests/test_milestone_7_task_7_12_image_admission.py','-k','not public_upload'], 90),
        ('admission_history_atomic_recheck', ['tests/test_milestone_7_task_7_13_admission.py','tests/test_milestone_7_task_7_14_issuance.py','tests/test_milestone_7_task_7_15_history.py','tests/test_milestone_7_task_7_16_atomic.py'], 360),
    ]
    jobs = [(name,['-m','pytest',*args,'-q','--tb=short','-p','no:cacheprovider',
                   '-o','faulthandler_timeout=20','--basetemp='+str(scratch/name)],limit) for name,args,limit in groups]
    jobs.append(('supplemental',['verification/task718/supplemental.py'],240))
    report = dict(environment_overrides={k:env[k] for k in ['TEMP','TMP','PYTHONDONTWRITEBYTECODE']}, commands=[])
    for name,args,limit in jobs:
        cmd=[str(ROOT/'.venv/Scripts/python.exe'),'-B',*args]
        start=time.monotonic()
        print('START',name,flush=True)
        with (OUT/(name+'.txt')).open('w',encoding='utf-8') as log:
            try:
                p=subprocess.run(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=limit)
                code,timeout=p.returncode,False
            except subprocess.TimeoutExpired:
                code,timeout=None,True
        report['commands'].append(dict(name=name,argv=cmd,exit_code=code,timed_out=timeout,
            timeout_seconds=limit,elapsed_seconds=round(time.monotonic()-start,3),log=name+'.txt'))
        (OUT/'followup.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print('END',name,code,(OUT/(name+'.txt')).read_text(encoding='utf-8')[-200:].replace('\n',' '),flush=True)


if __name__=='__main__':
    main()
