"""Bounded, offline Task 7.18 evidence collection. Never writes historical results."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import os
import platform
import sqlite3
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PY = ROOT / '.venv/Scripts/python.exe'


def main():
    scratch = ROOT / 'temp' / ('task718-' + uuid.uuid4().hex)
    scratch.mkdir(parents=True)
    env = dict(os.environ, TEMP=str(scratch), TMP=str(scratch), PYTHONDONTWRITEBYTECODE='1')
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    tracked = [p for p in tracked if p]
    before = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in tracked}
    report = dict(head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
                  branch=subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT).decode().strip(),
                  initial_preflight_status='clean, independently observed before creation of audit files',
                  python=sys.version, platform=platform.platform(), sqlite=sqlite3.sqlite_version,
                  libraries={p: importlib.metadata.version(p) for p in
                             ['zstandard', 'Brotli', 'Pillow', 'cffi', 'pytest', 'cryptography', 'eth-account']},
                  scratch=str(scratch), environment_overrides={k: env[k] for k in ['TEMP', 'TMP', 'PYTHONDONTWRITEBYTECODE']},
                  tracked_sha256=before, commands=[])
    jobs = [
        ('corpus', ['scripts/milestone_7_task_7_3_corpus.py', '--verify'], 120),
        ('codec', ['scripts/milestone_7_task_7_4_benchmark.py', '--output', str(OUT / 'codec.json')], 180),
        ('composition', ['scripts/milestone_7_task_7_7_block_composition.py', '--output', str(OUT / 'composition.json')], 180),
        ('economics', ['scripts/milestone_7_task_7_8_node_economics.py', '--output', str(OUT / 'economics.json'), '--csv', str(OUT / 'economics.csv')], 120),
        ('storage', ['scripts/milestone_7_task_7_11_storage.py', '--output', str(OUT / 'storage.json')], 180),
    ]
    groups = {
        'tests_measurements': ['7_3_corpus', '7_4_benchmark', '7_4a_image_evaluation', '7_7_block_composition', '7_8_node_economics'],
        'tests_codec': ['7_6_decoder', '7_6a_sequences', '7_6b_performance', '7_6c_isolation', '7_6d_linux_isolation', '7_6d_evidence'],
        'tests_v3': ['7_10c_v3', '7_11_storage', '7_12_image_admission', '7_13_admission', '7_14_issuance', '7_15_history', '7_16_atomic'],
        'tests_717s': ['7_17s_crypto'],
    }
    for name, suffixes in groups.items():
        jobs.append((name, ['-m', 'pytest', *['tests/test_milestone_7_task_' + s + '.py' for s in suffixes],
                            '-q', '--tb=short', '-p', 'no:cacheprovider', '--basetemp=' + str(scratch / name)], 480))
    jobs.append(('tests_legacy', ['-m', 'pytest', 'tests/test_protocol_v1.py', 'tests/test_protocol_v1_golden_vectors.py',
                 'tests/test_protocol_v1_native_transfers.py', 'tests/blockchain/test_task_3_5_validator_quorum_finality.py::test_validator_quorum_is_ceiling_of_two_thirds',
                 'tests/storage/test_sqlite_storage_backend.py', 'tests/storage/test_storage_tools.py',
                 '-q', '--tb=short', '-p', 'no:cacheprovider', '--basetemp=' + str(scratch / 'legacy')], 300))
    for name, args, limit in jobs:
        cmd = [str(PY), '-B', *args]
        start = time.monotonic()
        log = OUT / (name + '.txt')
        print('START', name, flush=True)
        with log.open('w', encoding='utf-8') as stream:
            try:
                p = subprocess.run(cmd, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=limit)
                code, timeout = p.returncode, False
            except subprocess.TimeoutExpired:
                code, timeout = None, True
        report['commands'].append(dict(name=name, argv=cmd, timeout_seconds=limit, timed_out=timeout,
                                      exit_code=code, elapsed_seconds=round(time.monotonic() - start, 3), log=log.name))
        (OUT / 'execution.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print('END', name, code, log.read_text(encoding='utf-8')[-180:].replace('\n', ' '), flush=True)
    report['tracked_changes'] = [p for p in tracked if not (ROOT / p).exists() or
                                 hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != before[p]]
    (OUT / 'execution.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
