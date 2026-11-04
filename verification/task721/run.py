"""Bounded replay. Every output stays in Task 7.21; no frozen evidence writes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent


def run(groups):
    scratch=ROOT/'temp'/('task721-'+uuid.uuid4().hex)
    scratch.mkdir(parents=True)
    env=dict(os.environ,TEMP=str(scratch),TMP=str(scratch),PYTHONDONTWRITEBYTECODE='1')
    outcomes=[]
    for name,files in groups.items():
        argv=[sys.executable,'-B','-m','pytest',*files,'-q','--tb=short','-p','no:cacheprovider',
              '-p','verification.task719.pytest_evidence','--basetemp='+str(scratch/name)]
        env['TASK719_OUTCOMES']=str(OUT/(name+'_outcomes.json'))
        started=time.monotonic()
        with (OUT/(name+'_tests.txt')).open('w',encoding='utf-8') as log:
            process=subprocess.Popen(argv,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            try: rc=process.wait(timeout=360)
            except subprocess.TimeoutExpired:
                process.kill();process.wait();rc='TIMEOUT'
        outcomes.append(dict(group=name,argv=argv,cwd=str(ROOT),timeout_seconds=360,exit=rc,elapsed_seconds=time.monotonic()-started))
        print(name,rc,flush=True)
    previous=json.loads((OUT/'tests_execution.json').read_bytes())['groups'] if (OUT/'tests_execution.json').exists() else []
    keep={r['group']:r for r in previous if r['group'] in ('focused','canonical_admission','codecs','atomic','active_safe','active_storage')}
    keep.update({r['group']:r for r in outcomes})
    (OUT/'tests_execution.json').write_text(json.dumps(dict(scratch=str(scratch),groups=list(keep.values())),indent=2)+'\n',encoding='utf-8')
    if any(r['exit']!=0 for r in outcomes): raise SystemExit(1)


def corpus():
    scratch=ROOT/'temp'/('task721-corpus-'+uuid.uuid4().hex)
    scratch.mkdir(parents=True)
    started=time.monotonic()
    argv=[sys.executable,'-B',str(OUT/'exercise.py'),str(OUT/'end_to_end.json')]
    with (OUT/'exercise.txt').open('w',encoding='utf-8') as log:
        process=subprocess.Popen(argv,cwd=ROOT,env=dict(os.environ,TEMP=str(scratch),TMP=str(scratch)),stdout=log,stderr=subprocess.STDOUT)
        try: rc=process.wait(timeout=900)
        except subprocess.TimeoutExpired:
            process.kill();process.wait();rc='TIMEOUT'
    (OUT/'exercise_execution.json').write_text(json.dumps(dict(argv=argv,cwd=str(ROOT),timeout_seconds=900,
        exit=rc,elapsed_seconds=time.monotonic()-started),indent=2)+'\n',encoding='utf-8')
    if rc!=0: raise SystemExit(1)


def preserve():
    before=json.loads((OUT/'prerequisites.json').read_bytes())
    changed=[p for p,sha in before['tracked_sha256'].items() if not (ROOT/p).is_file() or hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=sha]
    assert not changed,changed
    git=lambda *args:subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
    assert git('rev-parse','HEAD')==before['head']
    assert git('branch','--show-current')==before['branch']
    assert not git('diff','--cached','--name-only')
    result=dict(status='PASS',preserved_tracked_files=len(before['tracked_sha256']),changed_preexisting_files=changed,
                head=before['head'],branch=before['branch'],index_clean=True,
                git_status=git('status','--porcelain=v1','--untracked-files=all').splitlines())
    (OUT/'preservation.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=['tests','corpus','preserve'])
    parser.add_argument('--group',action='append',help='Run only a named test group; repeat for multiple groups')
    args=parser.parse_args()
    phase=args.phase
    if phase=='preserve': preserve()
    elif phase=='corpus': corpus()
    else:
        groups={
            'focused':['verification/task721/test_bridge.py'],
            'canonical_admission':['tests/test_milestone_7_task_'+n+'.py' for n in ('7_10c_v3','7_13_admission','7_14_issuance','7_15_history')],
            'codecs':['tests/test_milestone_7_task_'+n+'.py' for n in ('7_6_decoder','7_6a_sequences','7_6b_performance','7_6c_isolation','7_6d_linux_isolation','7_6d_evidence')],
            'atomic':['tests/test_milestone_7_task_7_16_atomic.py'],
            'active_safe':['tests/test_protocol_v1_golden_vectors.py','tests/test_protocol_v1_freeze_consistency.py',
                'tests/blockchain/test_protocol_v1_block_format.py','tests/test_milestone_6_task_6_9_media_integrity.py',
                'tests/test_milestone_7_task_7_17e_finality_durability.py','-k','not media_api and not settings_connection_ownership_and_nested_begin'],
            'active_storage':['tests/storage/test_sqlite_storage_backend.py','tests/storage/test_storage_regression_pass.py'],
        }
        if args.group:
            unknown=set(args.group)-set(groups)
            if unknown: parser.error('unknown test groups: '+str(sorted(unknown)))
            groups={name:files for name,files in groups.items() if name in args.group}
        run(groups)
