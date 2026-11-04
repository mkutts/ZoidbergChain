"""Cross-check new evidence against frozen media identities; summarize gates."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
OUT=Path(__file__).resolve().parent
from verification.task721.reconcile import reconcile
from verification.task721.run import preserve


def main():
    read=lambda name:json.loads((OUT/name).read_bytes())
    e2e=read('end_to_end.json')
    assert e2e['status']=='PASS' and e2e['recovery']['status']=='PASS'
    frozen=json.loads((ROOT/'benchmarks/task720_v1/records.json').read_bytes())['rows']
    prior={(r['population'],r['id']):r for r in frozen}
    assert len(e2e['format_records'])==len(prior)==70
    for row in e2e['format_records']:
        old=prior[row['population'],row['id']]
        for new,previous in [('original_size','original_bytes'),('stored_size','encoded_bytes'),
                             ('original_sha256','original_sha256'),('codec','codec')]:
            assert row[new]==old[previous],(row['id'],new)
        assert row['exact']
    assert len(e2e['application_records'])==58
    assert len(e2e['current_policy_excluded'])==12
    assert all(r['remaining'] for r in e2e['application_records'])
    recovered={r['block_hash']:r for r in e2e['recovery']['rows']}
    assert len(recovered)==128
    for row in e2e['format_records']+e2e['application_records']:
        after=recovered[row['block_hash']]
        assert after['exact'] and after['original_sha256']==row['original_sha256']
    groups={}
    final_reports={}
    skips=[];deselected=[]
    for group in ('focused','canonical_admission','codecs','atomic','active_safe','active_storage'):
        data=read(group+'_outcomes.json')
        assert data['exitstatus']==0
        counts=Counter(r['outcome'] for r in data['reports'])
        assert not counts['failed']
        groups[group]=dict(counts,deselected=len(data['deselected']))
        deselected+=data['deselected']
        for r in data['reports']:
            assert r['nodeid'] not in final_reports
            final_reports[r['nodeid']]=r['outcome']
            if r['outcome']=='skipped': skips.append(r)
    totals=dict(Counter(final_reports.values()),deselected=len(set(deselected)))
    reconciliation=reconcile()
    (OUT/'reconciliation.json').write_text(json.dumps(reconciliation,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    gates={
        'A_adaptive_producer':dict(status='PASS',scope='disabled lab',evidence='58 real-admission candidates; 40 Zstd / 18 identity; all 70 format choices match frozen evidence'),
        'B_independent_canonical_validation':dict(status='PASS',scope='canonical/codec/crypto + explicit test snapshots only',evidence='separate decoders, no recompression, hostile inputs; complete authority remains INCOMPLETE'),
        'C_exact_reconstruction':dict(status='PASS',evidence='70 format + 58 application records, exact bytes and original SHA-256'),
        'D_isolated_persistence_restart':dict(status='PASS',evidence='128 records recovered in fresh process; DELETE/EXTRA, index rebuild and actual interrupted-process tests'),
        'E_retrieval_compatibility':dict(status='PASS',scope='isolated underlying service only; no compressed HTTP route',evidence='identity/Zstd originals, MIME, sizes/hash; actual upload-service/cache-removal tests'),
        'F_active_v1_v2_nonregression':dict(status='PASS',scope='preserved active sources and selected regressions; two explicit deselections',evidence='active parser/hash/producer/validator/storage/media/finality tests and accidental activation rejection'),
        'G_active_protocol_v3':dict(status='BLOCKED',evidence='no approved policy/version transition, selection/BFT/reviewer-history authority or active import'),
        'H_public_network_activation':dict(status='BLOCKED',evidence='no activation approval/security audit; no deployment or public route'),
        'I_complete_original_milestone7':dict(status='BLOCKED',evidence='inactive application integration plus Task 7.20 metadata target failure and original audit gaps remain'),
    }
    summary=dict(status='PASS_DISABLED_SCOPE_ONLY',environment=dict(python=sys.version,platform=platform.platform(),sqlite=sqlite3.sqlite_version),
        branch=read('prerequisites.json')['branch'],head=read('prerequisites.json')['head'],
        format_records=70,application_records=58,recovered_records=128,current_policy_excluded=12,
        format_choices=e2e['format_choices'],application_choices=e2e['application_choices'],
        frozen_identity_size_codec_comparison='PASS all 70',tests=groups,totals=totals,skips=skips,deselected=sorted(set(deselected)),
        gates=gates,ready_for_review=True,ready_for_owner_commit=True,active_protocol_changed=False,
        security_qualification='Functional tests do not replace independent security/native-decoder audit',
        preliminary_wal_control='See initial_attempts.json; final selection excludes the inadvertent empty-database WAL-refusal control')
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    preserve()
    files=sorted(p for p in OUT.iterdir() if p.is_file() and p.name!='checksums.sha256')
    (OUT/'checksums.sha256').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in files),encoding='utf-8')
    print(json.dumps(dict(totals=totals,groups=groups,readiness='review and owner-made commit only')))


if __name__=='__main__': main()
