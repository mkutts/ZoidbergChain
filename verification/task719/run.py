"""Bounded Task 7.19 evidence runner; all outputs stay in this evidence version.

Run baseline before changing wrappers. Never emits historical manifests/results.
"""
from pathlib import Path
import argparse
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
sys.path.insert(0, str(ROOT))


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode().strip()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot():
    from scripts import milestone_7_task_7_3_corpus as corpus
    paths = git('ls-files', '-z').split('\0')
    tracked = {p: sha(ROOT / p) for p in paths if p}
    samples = corpus.build_samples()
    save('before.json', dict(branch=git('branch', '--show-current'), head=git('rev-parse', 'HEAD'),
        initial_status='clean including untracked; checked before creating task719 files',
        task718_commit=git('log', '-1', '--format=%H %s', '--', 'verification/task718/summary.json'),
        tracked_sha256=tracked, corpus=[dict(id=s['id'], size=len(s['bytes']),
            sha256=hashlib.sha256(s['bytes']).hexdigest()) for s in samples],
        environment=dict(python=sys.version, platform=platform.platform(), sqlite=sqlite3.sqlite_version,
            libraries={p: importlib.metadata.version(p) for p in
                       ['zstandard', 'Brotli', 'Pillow', 'cffi', 'pytest', 'cryptography', 'eth-account', 'fastapi', 'starlette', 'anyio', 'httpx2']})))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['baseline', 'reproduce', 'composition_followup', 'tests', 'inventory', 'api', 'api_control', 'finalize'])
    args = parser.parse_args()
    if args.phase == 'finalize':
        from scripts import milestone_7_task_7_3_corpus as corpus
        before = json.loads((OUT / 'before.json').read_bytes())
        current = {p: sha(ROOT / p) if (ROOT / p).exists() else None for p in before['tracked_sha256']}
        generated = [dict(id=s['id'], size=len(s['bytes']), sha256=hashlib.sha256(s['bytes']).hexdigest()) for s in corpus.build_samples()]
        changes = {p: dict(before=h, after=current[p]) for p, h in before['tracked_sha256'].items() if h != current[p]}
        save('preservation.json', dict(branch=git('branch', '--show-current'), head=git('rev-parse', 'HEAD'),
            tracked_changes=changes, corpus_before_after_equal=generated == before['corpus'],
            final_status=subprocess.check_output(['git', 'status', '--porcelain=v1', '--untracked-files=all'], cwd=ROOT).decode(),
            index_diff=git('diff', '--cached', '--name-only')))
        return
    if args.phase == 'baseline':
        if (OUT / 'before.json').exists():
            raise SystemExit('Refusing to replace the before snapshot')
        snapshot()
    scratch = ROOT / 'temp' / ('task719-' + args.phase + '-' + uuid.uuid4().hex)
    scratch.mkdir(parents=True)
    env = dict(os.environ, TEMP=str(scratch), TMP=str(scratch), PYTHONDONTWRITEBYTECODE='1')
    measurement_tests = ['tests/test_milestone_7_task_' + n + '.py' for n in
                         ['7_3_corpus', '7_4_benchmark', '7_4a_image_evaluation', '7_7_block_composition', '7_8_node_economics']]
    measurement_jobs = [
        ('corpus', ['scripts/milestone_7_task_7_3_corpus.py', '--verify'], 100),
        ('codec', ['scripts/milestone_7_task_7_4_benchmark.py', '--output', str(OUT / 'codec.json')], 180),
        ('composition', ['scripts/milestone_7_task_7_7_block_composition.py', '--output', str(OUT / 'composition.json')], 180)]
    jobs = {
        'baseline': measurement_jobs + [('measurements', ['-m', 'pytest', *measurement_tests, '-q', '--tb=short'], 150),
                    ('manifest_differences', ['verification/task719/checks.py', 'manifest'], 100)],
        'reproduce': measurement_jobs + [
            ('composition_no_sqlite', ['scripts/milestone_7_task_7_7_block_composition.py', '--skip-sqlite', '--output', str(OUT / 'composition_no_sqlite.json')], 120),
            ('economics', ['scripts/milestone_7_task_7_8_node_economics.py', '--output', str(OUT / 'economics.json'), '--csv', str(OUT / 'economics.csv')], 60),
            ('storage', ['scripts/milestone_7_task_7_11_storage.py', '--output', str(OUT / 'storage.json')], 180),
            ('adaptive_roundtrip_metadata', ['verification/task719/checks.py', 'media'], 180),
            ('comparisons', ['verification/task719/checks.py', 'compare'], 60)],
        'tests': [('measurements', ['-m', 'pytest', *measurement_tests, '-q', '--tb=short'], 150),
            ('codec', ['-m', 'pytest', *['tests/test_milestone_7_task_' + n + '.py' for n in
                ['7_6_decoder', '7_6a_sequences', '7_6b_performance', '7_6c_isolation', '7_6d_linux_isolation', '7_6d_evidence']], '-q', '--tb=short'], 150),
            ('format_storage', ['-m', 'pytest', 'tests/test_milestone_7_task_7_10c_v3.py', 'tests/test_milestone_7_task_7_11_storage.py', '-q', '--tb=short'], 180),
            ('wrapper_guards', ['-m', 'pytest', 'verification/task719/test_reproduction_guards.py', '-q', '--tb=short'], 100)],
        'inventory': [('collect_original_skips', ['-m', 'pytest', 'tests/test_milestone_7_task_7_16_atomic.py', '--collect-only', '-q'], 60),
            ('collect_deselection', ['-m', 'pytest', 'tests/test_milestone_7_task_7_12_image_admission.py', '-k', 'not public_upload', '--collect-only', '-q'], 60)],
        'api': [('loopback', ['verification/task719/api_probe.py', 'loopback'], 15),
            ('api_case', ['-m', 'pytest', 'tests/test_milestone_7_task_7_12_image_admission.py::test_public_upload_local_failure_is_503_and_persists_nothing', '-vv', '-s', '-o', 'faulthandler_timeout=10'], 35)],
    }
    jobs['api_control'] = jobs['api']
    jobs['composition_followup'] = [
        ('composition_no_sqlite', ['scripts/milestone_7_task_7_7_block_composition.py', '--skip-sqlite', '--output', str(OUT / 'composition_no_sqlite.json')], 120),
        ('comparisons', ['verification/task719/checks.py', 'compare'], 60)]
    jobs = jobs[args.phase]
    report = dict(phase=args.phase, cwd=str(ROOT), scratch=str(scratch),
                  environment_overrides={k: env[k] for k in ['TEMP', 'TMP', 'PYTHONDONTWRITEBYTECODE']}, commands=[])
    for name, argv, limit in jobs:
        log_name = args.phase + '_' + name + '.txt'
        if argv[:2] == ['-m', 'pytest']:
            outcome_path = OUT / (args.phase + '_' + name + '_outcomes.json')
            argv += ['-p', 'verification.task719.pytest_evidence', '-p', 'no:cacheprovider', '--basetemp=' + str(scratch / name)]
            env['TASK719_OUTCOMES'] = str(outcome_path)
        command = [str(PY), '-B', *argv]
        print('START', args.phase, name, flush=True)
        start = time.monotonic()
        with (OUT / log_name).open('w', encoding='utf-8') as log:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            print('PID', process.pid, flush=True)
            timed_out = False
            try:
                code = process.wait(timeout=limit)
            except subprocess.TimeoutExpired:
                timed_out = True
                # End the entire test worker tree on Windows, with a second bound.
                killed = subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], stdout=log, stderr=subprocess.STDOUT, timeout=15)
                if killed.returncode:
                    process.kill()
                process.wait(timeout=10)
                code = None
        report['commands'].append(dict(name=name, argv=command, log=log_name, exit_code=code,
            pid=process.pid, timed_out=timed_out or code == 124, timeout_seconds=limit, elapsed_seconds=round(time.monotonic() - start, 3)))
        save(args.phase + '_execution.json', report)
        print('END', name, code, 'timeout=' + str(timed_out), flush=True)


if __name__ == '__main__':
    main()
