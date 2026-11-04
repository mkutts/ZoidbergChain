"""Bounded focused tests; no live DB, server, WAL initializer or journal suites."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def main():
    test_temp=(ROOT/'temp'/('task723-tests-'+uuid.uuid4().hex)).resolve()
    assert ROOT/'temp' in test_temp.parents
    test_temp.mkdir()
    cmd=[sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider',
        '--basetemp',str(test_temp/'pytest'),
        '-k','not test_public_upload_local_failure_is_503_and_persists_nothing',
        'benchmarks/task723_v1/test_study.py',
        'tests/test_milestone_7_task_7_10c_v3.py',
        'tests/test_milestone_7_task_7_6_decoder.py',
        'tests/test_milestone_7_task_7_12_image_admission.py']
    start=time.perf_counter()
    env=dict(os.environ,TEMP=str(test_temp),TMP=str(test_temp),PYTHONDONTWRITEBYTECODE='1')
    with (HERE/'tests.txt').open('w',encoding='utf-8') as log:
        result=subprocess.run(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600)
    lines=(HERE/'tests.txt').read_text(encoding='utf-8')
    counts={k:int(re.search(r'(\d+) '+k.rstrip('s')+r's?\b',lines).group(1)) if re.search(r'(\d+) '+k.rstrip('s')+r's?\b',lines) else 0 for k in ('passed','failed','skipped','errors')}
    record=dict(argv=cmd,exit_code=result.returncode,elapsed_seconds=time.perf_counter()-start,
        counts=counts,status='PASS' if result.returncode==0 else 'FAIL',log_tail=lines.splitlines()[-15:],
        excluded_ids=['tests/test_milestone_7_task_7_12_image_admission.py::test_public_upload_local_failure_is_503_and_persists_nothing'],
        exclusion_reason='Live API module initialization/production-style networking is outside isolated benchmark scope; retain existing Task 7.22 classification. No historical assertion changed.')
    (HERE/'test_results.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(record),flush=True)
    assert result.returncode==0


if __name__=='__main__': main()
