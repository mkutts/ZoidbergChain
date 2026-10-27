"""Record executed JUnit evidence and enforce delivery isolation; no mutations
outside the named validation report. Run after the checker and test suites.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
HEAD = 'a3ea45556308baa3331f5cda724139abb1f993eb'
BRANCH = 'Compression-State-Bloat-and-Node-Economics'
OLD = 'docs/milestone-7-network-wide-review-voting-protocol-decision.md'
REPORT = 'docs/milestone-7-network-wide-review-journal-feasibility.md'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--junit', action='append', required=True)
    args = parser.parse_args()
    assert git('rev-parse', 'HEAD') == HEAD
    assert git('branch', '--show-current') == BRANCH
    assert not git('diff', '--cached', '--name-only'), 'index changed'
    assert git('diff', '--name-only').splitlines() == [OLD], 'unexpected tracked modifications'
    paths = [ROOT/REPORT, ROOT/OLD, ROOT/'tests/test_milestone_7_task_7_17p_review_journal.py']
    paths += sorted((ROOT/'verification/review717p').glob('*.py'))
    paths += sorted((ROOT/'tests/fixtures/review717p_v1').glob('*.json'))
    paths += [ROOT/'verification/review717p/results.json', ROOT/'verification/review717p/negative-control-traces.json']
    suites = []
    for name in args.junit:
        root = ET.parse(ROOT/name).getroot()
        tests = []
        for case in root.iter('testcase'):
            outcome = next((t for t in ('failure', 'error', 'skipped') if case.find(t) is not None), 'passed')
            tests.append(dict(name=case.attrib['name'], classname=case.attrib.get('classname'), outcome=outcome))
        assert all(t['outcome'] == 'passed' for t in tests), 'test run not completely passing'
        suites.append(dict(junit=name, total=len(tests), passed=len(tests), tests=tests,
                           seconds=sum(float(s.attrib.get('time', 0)) for s in root.iter('testsuite'))))
    output = ROOT/'verification/review717p/validation.json'
    result = dict(task='7.17P', python=sys.version.split()[0], initial_head=HEAD, final_head=HEAD,
                  branch=BRANCH, initial_git_state='clean including untracked files',
                  final_git_state='only named unstaged Task 7.17P artifacts; index unchanged',
                  suites=suites, total_passed=sum(s['total'] for s in suites),
                  existing_tracked_code_and_fixtures_unchanged=True,
                  artifacts={str(p.relative_to(ROOT)).replace('\\', '/'): sha256(p.read_bytes()).hexdigest()
                             for p in paths},
                  checks=['branch/HEAD unchanged', 'index empty', 'only O tracked file modified',
                          'all named JUnit cases passing', 'local Markdown links',
                          'UTF-8 without BOM, final newline, no trailing spaces', 'git diff --check'])
    # Create target so the report's link can be validated on the first audit.
    output.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    for p in paths+[output]:
        raw = p.read_bytes()
        assert not raw.startswith(b'\xef\xbb\xbf'), p
        raw.decode('utf-8')
        assert raw.endswith(b'\n'), p
        assert all(line.rstrip(b' \t') == line for line in raw.splitlines()), p
    for p in [ROOT/REPORT, ROOT/OLD]:
        content = p.read_text(encoding='utf-8')
        assert content.count('```') % 2 == 0, p
        for target in re.findall(r'\]\(([^)]+)\)', content):
            if '://' not in target:
                assert (p.parent/target.split('#')[0]).exists(), (p, target)
    subprocess.check_call(['git', 'diff', '--check'], cwd=ROOT)
    # Constrain every newly created artifact, including untracked files.
    new_paths = git('ls-files', '--others', '--exclude-standard').splitlines()
    allowed = {str(p.relative_to(ROOT)).replace('\\', '/') for p in paths+[output]}
    assert set(new_paths) <= allowed, set(new_paths)-allowed
    print(json.dumps(dict(total_passed=result['total_passed'], suites=[
        {k: s[k] for k in ('junit', 'total', 'seconds')} for s in suites],
        files=len(paths)+1, isolation='PASS', output=str(output)), indent=2))


if __name__ == '__main__':
    main()
