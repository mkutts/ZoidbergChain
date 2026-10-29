"""Bounded Task 7.22 replay. Never writes prior evidence or enables WAL.

Run with .venv/Scripts/python.exe -B verification/task722/run.py replay|tests.
All subprocess logs are compacted to their last 30 lines; structured outcomes
retain every pytest ID through the existing observation-only evidence plugin.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def main(phase):
    scratch = ROOT/'temp'/('task722-'+uuid.uuid4().hex)
    scratch.mkdir(parents=True)
    env = dict(os.environ, TEMP=str(scratch), TMP=str(scratch), PYTHONDONTWRITEBYTECODE='1')
    if phase == 'replay':
        (OUT/'replay720').mkdir(exist_ok=True)
        jobs = {
            'historical_corpus': ['scripts/milestone_7_task_7_3_corpus.py', '--verify'],
            'historical_codec': ['scripts/milestone_7_task_7_4_benchmark.py', '--output', str(scratch/'codec.json')],
            'historical_composition': ['scripts/milestone_7_task_7_7_block_composition.py', '--skip-sqlite', '--output', str(scratch/'composition.json')],
            'historical_economics': ['scripts/milestone_7_task_7_8_node_economics.py', '--output', str(scratch/'economics.json'), '--csv', str(scratch/'economics.csv')],
            'production_like': ['benchmarks/task720_v1/measure.py', '--output', str(scratch/'replay720')],
            'bridge_recovery': ['verification/task721/exercise.py', str(OUT/'bridge_recovery.json')],
        }
    else:
        groups = {
            'measurements': ['tests/test_milestone_7_task_'+n+'.py' for n in ('7_3_corpus','7_4_benchmark','7_4a_image_evaluation','7_7_block_composition','7_8_node_economics')]+['verification/task719/test_reproduction_guards.py','benchmarks/task720_v1/test_acceptance.py'],
            'bridge': ['verification/task721/test_bridge.py'],
            'canonical': ['tests/test_milestone_7_task_'+n+'.py' for n in ('7_10c_v3','7_13_admission','7_14_issuance','7_15_history')],
            'codecs': ['tests/test_milestone_7_task_'+n+'.py' for n in ('7_6_decoder','7_6a_sequences','7_6b_performance','7_6c_isolation','7_6d_linux_isolation','7_6d_evidence')],
            'atomic': ['tests/test_milestone_7_task_7_16_atomic.py'],
            'active': ['tests/test_protocol_v1_golden_vectors.py','tests/test_protocol_v1_freeze_consistency.py','tests/blockchain/test_protocol_v1_block_format.py','tests/test_milestone_6_task_6_9_media_integrity.py','tests/test_milestone_7_task_7_17e_finality_durability.py','tests/storage/test_sqlite_storage_backend.py','tests/storage/test_storage_regression_pass.py','-k','not media_api and not settings_connection_ownership_and_nested_begin'],
        }
        jobs = {name: ['-m','pytest',*files,'-q','--tb=short','-p','no:cacheprovider','-p','verification.task719.pytest_evidence','--basetemp='+str(scratch/name)] for name, files in groups.items()}
    execution = []
    for name, args in jobs.items():
        env['TASK719_OUTCOMES'] = str(OUT/(name+'_outcomes.json'))
        argv = [sys.executable,'-B',*args]
        started = time.monotonic()
        log = scratch/(name+'.txt')
        with log.open('w',encoding='utf-8') as handle:
            child = subprocess.Popen(argv,cwd=ROOT,env=env,stdout=handle,stderr=subprocess.STDOUT)
            try:
                code = child.wait(timeout=600)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait(); code = 'TIMEOUT'
        tail = log.read_text(encoding='utf-8',errors='replace').splitlines()[-30:]
        execution.append(dict(name=name,argv=argv,cwd=str(ROOT),scratch=str(scratch),timeout_seconds=600,
                              exit=code,elapsed_seconds=time.monotonic()-started,log_tail=tail))
        (OUT/(phase+'_execution.json')).write_text(json.dumps(execution,indent=2)+'\n',encoding='utf-8')
        print(name,code,flush=True)
        if phase == 'replay' and code == 0:
            # Keep only comparisons and compact ledgers, not another 20 MB replay.
            if name == 'production_like':
                compare = subprocess.run([sys.executable,'-B','benchmarks/task720_v1/compare.py',str(scratch/'replay720')],cwd=ROOT,env=env,capture_output=True,text=True,timeout=60)
                (OUT/'replay720'/'comparison.json').write_bytes((scratch/'replay720'/'comparison.json').read_bytes())
                assert compare.returncode == 0, compare.stderr
    if phase == 'replay':
        from verification.task722.reconcile import replay_compare
        replay_compare(scratch)
    if any(row['exit'] != 0 for row in execution):
        raise SystemExit(1)


if __name__ == '__main__':
    sys.path.insert(0,str(ROOT))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=['replay','tests'])
    main(parser.parse_args().phase)
