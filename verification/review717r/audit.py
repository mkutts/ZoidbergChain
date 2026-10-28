"""Constrained-delivery audit; no signing, network, staging or commits."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
HEAD='768f0d460eab1def068a14ba5666e9e7aa625ba0'
BRANCH='Compression-State-Bloat-and-Node-Economics'
Q='docs/milestone-7-review-journal-capacity-and-clock-decision.md'
REPORT='docs/milestone-7-review-journal-wire-and-closure-contract.md'
TEST='tests/test_milestone_7_task_7_17r_wire_closure.py'


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--junit',required=True)
    args=parser.parse_args()
    assert git('rev-parse','HEAD')==HEAD
    assert git('branch','--show-current')==BRANCH
    assert not git('diff','--cached','--name-only')
    assert git('diff','--name-only').splitlines()==[Q]
    before=subprocess.check_output(['git','show','HEAD:'+Q],cwd=ROOT)
    now=(ROOT/Q).read_bytes()
    assert now.split(b'\n\nDate:',1)[1]==before.split(b'\n\nDate:',1)[1]
    assert now.splitlines()[0]==before.splitlines()[0]
    allowed={Q,REPORT,TEST}
    allowed.update('verification/review717r/'+name for name in (
        '__init__.py','wire.py','model.py','vectors.py','report.py','evidence.py','audit.py',
        'oracle.cjs','results.json','validation.json'))
    allowed.update('tests/fixtures/review717r_v1/'+name for name in ('vectors.json','schema.json'))
    untracked=git('ls-files','--others','--exclude-standard').splitlines()
    assert set(untracked)<=allowed
    # Capture all tracked P/Q evidence, tests and fixtures unchanged except Q notice.
    preserved=git('ls-files','verification/review717p','verification/review717q',
                  'tests/fixtures/review717p_v1','tests/test_milestone_7_task_7_17p_review_journal.py',
                  'tests/test_milestone_7_task_7_17q_capacity_clock.py').splitlines()
    assert not git('diff','HEAD','--',*preserved)
    doc=ET.parse(ROOT/args.junit).getroot()
    counts,modules=Counter(),Counter()
    names=[]
    for case in doc.iter('testcase'):
        outcome=next((x for x in ('failure','error','skipped') if case.find(x) is not None),'passed')
        counts[outcome]+=1
        modules[case.attrib['classname']]+=1
        names.append(case.attrib['classname']+'::'+case.attrib['name'])
    assert counts['passed']==len(names) and len(names)>199
    oracle=json.loads(subprocess.check_output(['node','verification/review717r/oracle.cjs'],cwd=ROOT))
    assert oracle['vectors']==17 and oracle['closure_pages']==3 and oracle['vote_fold']
    output=ROOT/'verification/review717r/validation.json'
    if not output.exists():
        output.write_text('{}\n',encoding='utf-8')
    paths=[ROOT/p for p in sorted(allowed) if p!='verification/review717r/validation.json']
    # Validate local documentation, whitespace and package isolation.
    for p in paths:
        raw=p.read_bytes()
        assert not raw.startswith(b'\xef\xbb\xbf') and raw.endswith(b'\n')
        raw.decode('utf-8')
        assert all(x==x.rstrip(b' \t') for x in raw.splitlines()),p
    for name in (REPORT,Q):
        content=(ROOT/name).read_text(encoding='utf-8')
        assert content.count('```')%2==0
        for target in re.findall(r'\]\(([^)]+)\)',content):
            if '://' not in target:
                assert ((ROOT/name).parent/target.split('#')[0]).exists(),target
    prod=git('ls-files','*.py').splitlines()
    for name in prod:
        if not name.startswith(('verification/','tests/')):
            assert 'review717r' not in (ROOT/name).read_text(encoding='utf-8'),name
    result=dict(task='7.17R',branch=BRANCH,initial_head=HEAD,final_head=HEAD,
                initial_git_state='clean index and complete worktree including untracked files',
                final_git_state='index unchanged/empty; only named unstaged R files and Q notice',
                final_status=git('status','--porcelain=v1','--untracked-files=all').splitlines(),
                python=sys.version.split()[0],node= subprocess.check_output(['node','--version'],text=True).strip(),
                suites=[dict(junit=args.junit,total=len(names),outcomes=dict(counts),modules=dict(modules),
                             inventory_sha256=sha256('\n'.join(names).encode()).hexdigest(),
                             junit_sha256=sha256((ROOT/args.junit).read_bytes()).hexdigest())],
                independent_oracle=oracle,total_passed=counts['passed'],failed=0,errors=0,skipped=0,timed_out=0,
                signing_performed=False,scope='specification and trusted-fact isolated experiments only',
                readiness=dict(isolated_byte_closure='READY_FOR_REVIEW',crypto_prototype='BLOCKED',
                               production_journal='BLOCKED',public_testnet='BLOCKED',reviewer_history_717='BLOCKED'),
                artifacts={p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in paths},
                preserved_P_Q={p:sha256((ROOT/p).read_bytes()).hexdigest() for p in preserved},
                exclusions=['new-domain real signatures','full application source-policy validation',
                            'physical time trust','two-stream BFT/custody refinement','whole repository tests',
                            'live networking','native-host performance','physical archive restore'])
    output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    subprocess.check_call(['git','diff','--check'],cwd=ROOT)
    print(json.dumps(dict(passed=result['total_passed'],modules=dict(modules),oracle=oracle,
                         files=len(allowed),isolation='PASS'),indent=2))


if __name__=='__main__':
    main()
