"""Freeze/check Task 7.25 evidence; preserve every preexisting tracked byte."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
REPORT=ROOT/'docs/milestone-7-physical-storage-and-network-economics-verification.md'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()


def save(name,value):
    (HERE/name).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n',encoding='utf-8')


def historical_checksums():
    results=[]
    for rel in ('verification/task719/checksums.sha256','benchmarks/task720_v1/checksums.sha256',
                'verification/task721/checksums.sha256','verification/task722/checksums.sha256',
                'benchmarks/task723_v1/checksums.sha256','verification/task724/checksums.sha256'):
        path=ROOT/rel; count=0
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            expected,target=line.split(None,1);target=target.strip().lstrip('*')
            base=path.parent if 'task721/' in rel else ROOT
            assert sha((base/target).read_bytes())==expected,(rel,target)
            count+=1
        results.append(dict(manifest=rel,entries=count,status='PASS'))
    return results


def preservation():
    before=json.loads((HERE/'preflight.json').read_bytes())
    missing_or_changed=[p for p,h in before['tracked_sha256'].items() if not (ROOT/p).is_file() or sha((ROOT/p).read_bytes())!=h]
    assert not missing_or_changed,missing_or_changed
    assert git('rev-parse','HEAD')==before['head']
    assert git('branch','--show-current')==before['branch']
    assert sha(git('ls-files','--stage').encode())==before['index_sha256']
    assert set(git('ls-files').splitlines())==set(before['tracked_sha256'])
    # Include this generated evidence in the final untracked inventory.
    for p in (HERE/'preservation.json',HERE/'checksums.sha256'):
        if not p.exists():
            p.write_text('',encoding='utf-8')
    status=git('status','--porcelain=v1','--untracked-files=all').splitlines()
    for line in status:
        assert line.startswith('?? '),line
        p=line[3:]
        assert p.startswith('verification/task725/') or p==REPORT.relative_to(ROOT).as_posix(),line
    save('preservation.json',dict(status='PASS',branch=before['branch'],head=before['head'],
        initial_status=before['initial_status'],final_status=status,preexisting_tracked_files=len(before['tracked_sha256']),
        changed_preexisting_files=[],index_unchanged=True,stage_commit_push_merge=False))


def acceptance():
    tests=json.loads((HERE/'tests_execution.json').read_bytes())
    assert all(g['exit']==0 for g in tests['groups']) and not tests['timeouts']
    assert set(g['group'] for g in tests['groups'])=={'canonical','codecs','persistence','historical_arithmetic','physical'}
    probes=json.loads((HERE/'development_notes.json').read_bytes())['initial_checks']
    supplemental=[p for p in probes if 'passed' in p]
    totals={k:tests['counts'].get(k,0)+sum(p.get(k,0) for p in supplemental) for k in ('passed','failed','skipped')}
    totals.update(deselected=tests['deselected']+sum(p.get('deselected',0) for p in supplemental),
                  timeouts=tests['timeouts']+sum(bool(p.get('timeout')) for p in supplemental))
    save('all_test_attempts.json',dict(version=1,final_suite=dict(counts=tests['counts'],deselected=tests['deselected'],timeouts=tests['timeouts']),
        supplemental=supplemental,all_attempt_counts=totals,
        note='All-attempt counts include repeated node executions. The one initial loopback environment failure is preserved and resolved by permitted reruns; final selected suite counts are separate.'))
    for path in ('workloads.json','sqlite.json','backup_recovery.json','transfer.json','projections.json'):
        assert json.loads((HERE/path).read_bytes())['version']==1
    save('acceptance.json',dict(version=1,
        original_milestone='COMPLETE WITH OWNER-APPROVED LIMITATIONS',production_network='BLOCKED',
        task725_ready_for_owner_review_and_commit=True,milestone7_development_can_close_with_documented_limitations=True,
        authority='Current Task 7.25 Step 10 explicitly accepts disabled integration for development completion and retains real-world qualification as a public-launch requirement; Task 7.24 approves metadata exception and complete-canonical comparison.',
        findings=[dict(id='R1',status='FAIL WITH OWNER-APPROVED EXCEPTION',finding='Below-15% metadata target stays measured FAIL; no evidence removed.'),
            dict(id='R2',status='DEVELOPMENT LIMITATION ACCEPTED; LAUNCH REQUIREMENT OPEN',finding='Synthetic coverage only; real-world content qualification remains required before public launch.'),
            dict(id='R3',status='ACCEPTED DEVELOPMENT BOUNDARY',finding='Disabled adaptive integration accepted by current instruction; no active v3 protocol.'),
            dict(id='R4',status='RESOLVED FOR BOUNDED DEVELOPMENT EVIDENCE',finding='Actual isolated SQLite/schema/index allocation, full-copy snapshot/backup/recovery, byte-exact records/original commitments and real-framed simulated loopback transfer measured. No production P2P qualification.'),
            dict(id='R5',status='OWNER-APPROVED INTERPRETATION',finding='Complete canonical selected-vs-identity comparison; no raw or disk monotonic guarantee.'),
            dict(id='cost',status='CONDITIONAL; MISSES DISCLOSED',finding='Updated costs include measured two-copy recovery workspace. Some scenarios exceed $100, permitted by original acceptance contract. Prices, traffic mix and service tiers remain assumptions.')],
        owner_decisions=dict(balanced_caps='PROVISIONAL INACTIVE: static 262144; animated GIF 524288; text 16384; encoded 525312; complete 1048576',
            metadata='FAIL, approved exception',no_expansion='Complete canonical representation vs same identity context',
            disabled_integration='Accepted for development completion by current Task 7.25 request',real_world='Required for public launch',
            distributed_archiving='Future, unstarted',protocol_activation='BLOCKED'),
        unresolved_production=['Independent security and supported-platform historical decoder qualification',
            'Real-world provenance-cleared content/traffic pilot and operational throughput/restore SLA',
            'Approved v3 protocol limits/version/height and authenticated history/finality/reviewer interfaces',
            'Actual regional host, disk/IOPS, backup/transfer tier and capacity quotation',
            'Existing whole-history JSON/response.json boundary exceeds the assumed 8-GiB memory at projected history sizes; bounded retrieval needs separate implementation and qualification',
            'Production P2P protocol qualification; TCP/TLS/packet overhead and loss remain unmeasured'],
        new_failures_waived=False,tests=tests['counts'],timeouts=tests['timeouts']))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args()
    if args.check:
        path=HERE/'checksums.sha256'
        for line in path.read_text().splitlines():
            expected,target=line.split(None,1)
            assert sha((ROOT/target.strip()).read_bytes())==expected,target
        historical_checksums()
        print('Task 7.25 and six historical manifests PASS');return
    assert REPORT.exists()
    save('manifest_checks.json',dict(status='PASS',historical=historical_checksums()))
    acceptance()
    sources=['canonical_v3/block.py','canonical_v3/media.py','canonical_v3/storage.py','canonical_v3/primitives.py',
        'verification/task721/bridge.py','services/peer_transport_service.py','services/peer_chain_sync_service.py',
        'protocol_v1_peer_message.py','api_routers/peer.py','storage.py','storage_tools.py','scripts/storage_backup.py',
        'scripts/milestone_7_task_7_8_node_economics.py','verification/task722/economics.py','verification/task722/economic_inputs.json']
    sources += ['docs/'+name for name in ('milestone-7-original-scope-completion-audit.md',
        'milestone-7-production-like-compression-and-metadata-acceptance.md','milestone-7-disabled-compression-integration.md',
        'milestone-7-final-economics-and-acceptance-review.md','milestone-7-meme-first-launch-sizing-recommendation.md',
        'milestone-7-final-closeout-and-owner-decisions.md','zoidbergchain-distributed-complete-block-archiving-proposal.md')]
    save('source_versions.json',{p:sha((ROOT/p).read_bytes()) for p in sources})
    preservation()
    paths=sorted([REPORT,*[p for p in HERE.iterdir() if p.is_file() and p.name!='checksums.sha256']])
    (HERE/'checksums.sha256').write_text(''.join(sha(p.read_bytes())+'  '+p.relative_to(ROOT).as_posix()+'\n' for p in paths),encoding='utf-8')
    print('Preservation, acceptance, checksums PASS;',len(paths),'new files frozen')


if __name__=='__main__':
    main()
