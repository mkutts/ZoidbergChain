"""Retain actual JUnit counts, input hashes and constrained-delivery evidence."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
HEAD = 'e15c71e0e31afd3cb9a3bb50bc114bcac5922c62'
BRANCH = 'Compression-State-Bloat-and-Node-Economics'
OLD = 'docs/milestone-7-network-wide-review-journal-feasibility.md'
REPORT = 'docs/milestone-7-review-journal-capacity-and-clock-decision.md'
TEST = 'tests/test_milestone_7_task_7_17q_capacity_clock.py'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--junit', action='append', required=True)
    args = parser.parse_args()
    assert git('rev-parse', 'HEAD') == HEAD
    assert git('branch', '--show-current') == BRANCH
    assert not git('diff', '--cached', '--name-only')
    assert git('diff', '--name-only').splitlines() == [OLD]
    preserved = git('ls-files', 'verification/review717p', 'tests/fixtures/review717p_v1',
                    'tests/test_milestone_7_task_7_17p_review_journal.py').splitlines()
    assert not git('diff', 'HEAD', '--', *preserved)
    # Only the 15-line notice may change P's historical report body.
    baseline = subprocess.check_output(['git', 'show', 'HEAD:'+OLD], cwd=ROOT)
    current = (ROOT/OLD).read_bytes()
    assert current.split(b'\n\nDate:', 1)[1] == baseline.split(b'\n\nDate:', 1)[1]
    paths = [ROOT/REPORT, ROOT/OLD, ROOT/TEST]
    paths += sorted((ROOT/'verification/review717q').glob('*.py'))
    paths += [ROOT/'verification/review717q/inputs.json', ROOT/'verification/review717q/results.json']
    output = ROOT/'verification/review717q/validation.json'
    allowed = {p.relative_to(ROOT).as_posix() for p in paths+[output]}
    assert set(git('ls-files', '--others', '--exclude-standard').splitlines()) <= allowed
    suites = []
    for name in args.junit:
        path = ROOT/name
        doc = ET.parse(path).getroot()
        outcomes, modules = Counter(), Counter()
        names = []
        for case in doc.iter('testcase'):
            outcome = next((x for x in ('failure', 'error', 'skipped') if case.find(x) is not None), 'passed')
            outcomes[outcome] += 1
            modules[case.attrib['classname']] += 1
            names.append(case.attrib['classname']+'::'+case.attrib['name'])
        assert outcomes['passed'] == len(names), outcomes
        suites.append(dict(junit=name, total=len(names), outcomes=dict(outcomes),
                           seconds=sum(float(s.attrib.get('time', 0)) for s in doc.iter('testsuite')),
                           modules=dict(sorted(modules.items())),
                           test_inventory_sha256=sha256('\n'.join(names).encode()).hexdigest(),
                           junit_sha256=sha256(path.read_bytes()).hexdigest()))
    result = dict(task='7.17Q', branch=BRANCH, initial_head=HEAD, final_head=HEAD,
                  initial_state='clean index/worktree including untracked files, observed before edits',
                  final_state='only named unstaged Q deliverables; index empty', python=sys.version.split()[0],
                  suites=suites, total_passed=sum(s['total'] for s in suites),
                  skipped=0, failed=0, errors=0, timed_out=0,
                  earlier_runs=[dict(junit='temp/task717q-focused-1.xml', passed=35, failed=1,
                                     cause='incorrect expected idle-storage literal corrected; not release evidence'),
                                dict(junit='temp/task717q-focused-final.xml', passed=116,
                                     cause='superseded by additional parent-binding/penalty tests; not added to total'),
                                dict(junit='temp/task717q-focused-release.xml', passed=118,
                                     cause='superseded by typed-signer and independent economics checks; not added to total')],
                  exclusions=['whole repository', 'live network/multi-host BFT throughput',
                              'new-profile actual signatures/time oracle', 'physical clock/crash tests',
                              'full close paging implementation', 'production source archive/restore benchmarks'],
                  preserved_P={p: sha256((ROOT/p).read_bytes()).hexdigest() for p in preserved},
                  artifacts={p.relative_to(ROOT).as_posix(): sha256(p.read_bytes()).hexdigest() for p in paths},
                  historical_economics_input_sha256=sha256((ROOT/'benchmarks/milestone_7_task_7_8_config.json').read_bytes()).hexdigest(),
                  checks=['HEAD/branch unchanged', 'index empty', 'only P notice tracked modification',
                          'P historical body/code/fixtures/negative controls unchanged',
                          'untracked inventory constrained', 'all recorded JUnit cases pass',
                          'UTF-8/newlines/whitespace', 'local Markdown links', 'git diff --check'])
    output.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    for path in paths+[output]:
        raw = path.read_bytes()
        assert not raw.startswith(b'\xef\xbb\xbf')
        raw.decode('utf-8')
        assert raw.endswith(b'\n')
        assert all(x == x.rstrip(b' \t') for x in raw.splitlines())
    for path in (ROOT/REPORT, ROOT/OLD):
        content = path.read_text(encoding='utf-8')
        assert content.count('```') % 2 == 0
        for target in re.findall(r'\]\(([^)]+)\)', content):
            if '://' not in target:
                assert (path.parent/target.split('#')[0]).exists(), target
    subprocess.check_call(['git', 'diff', '--check'], cwd=ROOT)
    print(json.dumps(dict(total_passed=result['total_passed'], suites=[
        dict(total=s['total'], seconds=s['seconds']) for s in suites], files=len(paths)+1,
        skipped=0, timed_out=0, isolation='PASS'), indent=2))


if __name__ == '__main__':
    main()
