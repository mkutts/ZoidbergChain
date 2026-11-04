"""Verify unchanged historical tracked bytes, HEAD/index, and new-only scope."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
REPORT=ROOT/'docs/milestone-7-meme-first-launch-sizing-recommendation.md'


def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT).decode().strip()


def main():
    before=json.loads((HERE/'preflight.json').read_bytes())
    changed=[f for f,h in before['tracked_sha256'].items() if hashlib.sha256((ROOT/f).read_bytes()).hexdigest()!=h]
    assert not changed,changed
    assert git('rev-parse','HEAD')==before['head']
    assert git('branch','--show-current')==before['branch']
    assert not git('diff','--cached')
    checks={name:json.loads((HERE/name).read_bytes())['status'] for name in ('crosscheck.json','test_results.json','replay_comparison.json')}
    assert all(v=='PASS' for v in checks.values()),checks
    (HERE/'preservation.json').touch(exist_ok=True)
    (HERE/'checksums.sha256').touch(exist_ok=True)
    status=git('status','--porcelain=v1','--untracked-files=all').splitlines()
    assert all(line.startswith('?? benchmarks/task723_v1/') or line=='?? docs/milestone-7-meme-first-launch-sizing-recommendation.md' for line in status),status
    preservation=dict(status='PASS',head=before['head'],branch=before['branch'],changed_preexisting_tracked_files=changed,
        tracked_files_checked=len(before['tracked_sha256']),index_unchanged=True,git_porcelain=status,
        validations=checks,commit_or_push_performed=False,activation_performed=False)
    (HERE/'preservation.json').write_text(json.dumps(preservation,indent=2)+'\n',encoding='utf-8')
    files=[REPORT]+sorted(p for p in HERE.rglob('*') if p.is_file() and p.name!='checksums.sha256' and '__pycache__' not in p.parts)
    (HERE/'checksums.sha256').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(ROOT).as_posix()+'\n' for p in files),encoding='utf-8')
    print('PASS:',len(before['tracked_sha256']),'preexisting tracked files unchanged;',len(files),'deliverable checksums; index/HEAD unchanged')


if __name__=='__main__':main()
