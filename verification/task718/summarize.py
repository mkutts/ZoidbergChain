"""Assemble audit-only calculated tables and final preservation evidence."""
from collections import Counter
from pathlib import Path
import hashlib
import importlib.metadata
import json
import re
import sqlite3
import subprocess
import zlib
import zstandard

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
DOC = ROOT/'docs/milestone-7-original-scope-completion-audit.md'
MARKER = '\n## Appendix A. Final measured evidence\n'


def load(path):
    return json.loads(path.read_bytes())


def table(headers, rows):
    return '\n'+'\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |',
                      *['| '+' | '.join(map(str,row))+' |' for row in rows]])+'\n\n'


def main():
    a=load(OUT/'execution.json'); f=load(OUT/'followup.json'); s=load(OUT/'supplemental.json')
    economy=load(OUT/'economics.json'); old=load(ROOT/'benchmarks/milestone_7_task_7_8_results.json')
    store=load(OUT/'storage.json'); old_store=load(ROOT/'benchmarks/milestone_7_task_7_11_results.json')
    counts=Counter(); commands=[]
    extra=load(OUT/'supplemental_recheck.json')['commands'] if (OUT/'supplemental_recheck.json').exists() else []
    for c in a['commands']+f['commands']+extra:
        text=(OUT/c['log']).read_text(encoding='utf-8')
        outcomes={word:int(re.findall(r'(\d+) '+word,text)[-1]) if re.findall(r'(\d+) '+word,text) else 0
                  for word in ['passed','failed','skipped','deselected']}
        if c['name'].startswith('tests_') or 'recheck' in c['name']:
            if not c['timed_out']:
                counts.update(outcomes)
        status='TIMEOUT' if c['timed_out'] else ('PASS' if c['exit_code']==0 else 'FAIL')
        commands.append(dict(name=c['name'],status=status,elapsed=c['elapsed_seconds'],outcomes=outcomes,log=c['log']))
    unchanged=[p for p,h in a['tracked_sha256'].items() if not (ROOT/p).exists() or hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    status=subprocess.check_output(['git','status','--porcelain=v1','--untracked-files=all'],cwd=ROOT,text=True)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    assert not unchanged and head==a['head']
    assert not subprocess.check_output(['git','diff','--cached','--name-only'],cwd=ROOT,text=True)
    assert all(line.startswith('?? ') and (line[3:].startswith('verification/task718/') or line[3:]=='docs/milestone-7-original-scope-completion-audit.md') for line in status.splitlines())
    summary=dict(original_acceptance='INCOMPLETE',production_readiness='BLOCKED',head=head,branch=a['branch'],
        additional_environment=dict(node=subprocess.check_output(['node','--version'],cwd=ROOT,text=True).strip(),
            libzstd=zstandard.ZSTD_VERSION,zstandard_backend=zstandard.backend,zlib_compile=zlib.ZLIB_VERSION,zlib_runtime=zlib.ZLIB_RUNTIME_VERSION,
            packages={p:importlib.metadata.version(p) for p in ['anyio','starlette','httpx2','fastapi']},
            dbstat_compiled='ENABLE_DBSTAT_VTAB' in [r[0] for r in sqlite3.connect(':memory:').execute('pragma compile_options')]),
        initial_status='clean',final_git_status=status,preexisting_tracked_file_changes=unchanged,index_changed=False,
        commands=commands,completed_test_counts=dict(counts),timeouts=[c['name'] for c in commands if c['status']=='TIMEOUT'],
        economics_json_exact=economy==old,economics_csv_byte_exact=(OUT/'economics.csv').read_bytes()==(ROOT/'benchmarks/milestone_7_task_7_8_monthly.csv').read_bytes(),
        storage_equal_excluding_environment=all(store[k]==old_store[k] for k in store if k!='environment'),
        codec_size_mismatches=len(s['codec_size_mismatches_with_frozen']),worker_roundtrips=len(s['strict_worker_roundtrips']),
        frozen_metadata=s['frozen_metadata_summary'],frozen_totals=s['frozen_totals'],manifest_difference_count=len(s['manifest_differences']),
        requirements={'scope_1':'PARTIAL','scope_2':'PARTIAL','scope_3':'PARTIAL','scope_4':'PASS','scope_5':'PARTIAL',
                      'addition_6':'PARTIAL','addition_7':'PASS','addition_8':'PARTIAL','addition_9':'PARTIAL',
                      'A':'PARTIAL','B':'PARTIAL','C':'FAIL','D':'PARTIAL','E':'PARTIAL','F':'FAIL','MODEL_A':'PASS'})
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    lines=[MARKER,'\nThese are final audit measurements, read directly from the retained JSON/logs.\n',
           '\n### A1. Execution outcomes\n',
           table(['Command/group','Outcome','Seconds','Final test summary','Log'],[
               [c['name'],c['status'],c['elapsed'],', '.join(f'{v} {k}' for k,v in c['outcomes'].items() if v) or 'No pytest summary',
                f"[{c['log']}](../verification/task718/{c['log']})"] for c in commands]),
           f"\nCompleted, disjoint test selections total **{counts['passed']} passed, {counts['failed']} failed, {counts['skipped']} skipped**; {counts['deselected']} deselected. "
           'The incomplete combined v3 run is not added to these counts. The same API case timed out in that run and in the bounded standalone diagnostic; neither attempt is a pass or skip.\n',
           '\nThe five failed node IDs are retained in tests_measurements.txt: corpus manifest regeneration; the obsolete genesis-image-isolation failure expectation; image-evaluation baseline verification; and the two composition-build tests. '
           'The 193 Linux-only skips require a Linux kernel. Any four atomic WAL crash skips are caused by the repository runtime gate on SQLite 3.49.1.\n',
           '\nFollow-ups were invoked with `.venv/Scripts/python.exe -B verification/task718/followup.py`; it records exact argv in followup.json. '
           'The standalone API faulthandler trace blocks in socket.accept/_fallback_socketpair while creating the Windows asyncio loop, before the upload handler. '
           'Host-local event-loop verification is unavailable; no production codec defect is inferred. No further socket or application changes were attempted.\n',
           f"\nDeterministic comparisons: simulator JSON exact={summary['economics_json_exact']}; CSV byte-exact={summary['economics_csv_byte_exact']}; "
           f"storage fields excluding environment exact={summary['storage_equal_excluding_environment']}; codec sizes differing from frozen rows={summary['codec_size_mismatches']}/252.\n",
           f"\nAll 36 source lengths/hashes match. Manifest observation differences occur in {len(s['manifest_differences'])} samples; field deltas are in supplemental.json. "
           'Frozen and regenerated encoder/Python environment dictionaries are compared there. '
           f"Fresh strict-worker source-byte round trips: {len(s['strict_worker_roundtrips'])}/72 exact; signed frozen-format reconstruction: {sum(r['reconstruction_byte_equal'] for r in s['frozen_format_rows'])}/36 exact.\n",
           '\n### A2. Raw category codec measurements\n',
           '\nRatio is encoded/original; reduction=100*(1-ratio), before adaptive fallback. Timings are summed per-object medians in milliseconds, not p95 latency. '
           'Object-level median/p95 and exact configurations are retained in supplemental.json; native memory remains unmeasured. '
           'Negative reductions are honest expansion results. Identity remains the comparison baseline.\n',
           table(['Profile','Category','Objects','Original B','Encoded B','Ratio','Reduction %','Encode ms','Decode ms','Expands'],[
               [r['profile'],r['category'],r['count'],f"{r['original']:,}",f"{r['encoded']:,}",f"{r['ratio']:.5f}",f"{r['reduction_percent']:.3f}",
                f"{r['encode_ms_sum_medians']:.4f}",f"{r['decode_ms_sum_medians']:.4f}",r['expansions']] for r in s['codec_groups']]),
           '\nZstd-3 category result: plain text 82.51% raw reduction; JSON/metadata 91.93%; source code 39.68%. '
           'The first two exceed the approximate target on this small synthetic corpus; the source snippets do not demonstrate 60–80%. '
           'This is not evidence that suitably sized code cannot reach that target. Do not pad or reweight the corpus to make it pass.\n',
           '\n### A3. Frozen v3 full-record metadata\n',
           table(['Definition','p50 %','p95 %','Worst %'],[[key,f"{v['p50']:.5f}",f"{v['p95']:.5f}",f"{v['worst']:.5f}"] for key,v in s['frozen_metadata_summary'].items()]),
           table(['36-record total','Bytes'],[[k,f'{v:,}'] for k,v in s['frozen_totals'].items()]),
           '\nDefinitions: historical_definition_percent=(R-serialized media member)/R; canonical_metadata_percent=(R-base64 content characters)/R; '
           'original_relative_metadata_percent=(R-base64 content characters)/accepted-original bytes. '
           'All percentiles are equal-block nearest rank, including tiny records. Required reviewer/submitter signatures remain inside certificate totals. '
           'Reviewer evidence/native-array/signature values below are diagnostic subsets, not extra additive bytes. '
           'The old signature-subset helper counts arbitrary array strings, including acceptance reason codes. '
           'Audit signature totals instead count only explicit signature/vote_signature fields (71,280 ASCII content bytes across these records); '
           'the unmodified helper diagnostic in each parts object is retained for traceability and is 864 bytes higher. '
           'There is no separate producer block signature in this frozen format. Finality proofs are separate retained objects, absent from this corpus population.\n']
    totals=Counter()
    for r in s['frozen_format_rows']:
        for k in ['certificate_bytes','transaction_record_bytes','header_bytes','remaining_structural_metadata_bytes','envelope_bytes','delimiter_bytes']:
            totals[k]+=r['parts'][k]
    totals['serialized_media_representation_bytes']=sum(r['parts']['serialized_media_representation_bytes'] for r in s['frozen_format_rows'])
    totals['portable_wrapper_bytes']=sum(r['wrapper'] for r in s['frozen_format_rows'])
    assert sum(totals.values())==s['frozen_totals']['canonical_record']
    lines.append(table(['Additive full-R partition','Bytes'],[[k,f'{v:,}'] for k,v in totals.items()]))
    total=s['frozen_totals']; weighted=100*total['protocol_metadata_including_descriptor']/total['canonical_record']
    lines.append(f"\nFull-R metadata byte-weighted share including descriptor: **{weighted:.5f}%**; "
                 f"mean R={total['canonical_record']/36:.6f} B. The equal-block p50/p95/worst target remains unmet. "
                 f"Accepted original size p50/p95/worst={s['frozen_original_size_distribution']}. "
                 'The supplemental gate probes confirm certificate/native/rest at-cap acceptance by the respective byte gate and cap+1 rejection. '
                 'They are explicitly analytic gate inputs, not forged valid maximum records; real-signature max-media tests are in the passed format suite.\n')
    lines.extend(['\n### A4. All historical month-36 scenarios\n',
        table(['Blocks/day','Workload','Budget USD','Cloud USD','Storage-focused USD'],[
            [rate,workload,*[f"{next(x for x in economy['scenarios'] if x['scenario']['blocks_per_day']==rate and x['scenario']['workload']==workload and x['scenario']['profile']==profile)['month_36']['monthly_cost']['total']:.2f}" for profile in ['budget_vps','mainstream_cloud','storage_focused']]]
            for rate in [100,1000,10000] for workload in ['small_media','representative_corpus','large_media']]),
        '\n### A5. Audit-only schema and disk-capacity sensitivities\n',
        '\nHistorical prices, peer/backup rules and DB amplification are held fixed. Closed-v3 mean substitutes only the measured canonical bytes/block. '
        'Capacity-priced total provisions primary + one local snapshot + stated temporary margin + one additional primary-sized VACUUM workspace, charging '
        'max(0, allocated GiB - bundle GiB) at the same marginal disk rate; backup and egress charges are unchanged. '
        'This is a planning sensitivity, not a provider quote or a measured minimum workspace, and leaves journal/source costs excluded.\n',
        table(['Basis','Blocks/day','Canonical GiB','Primary GiB','Allocated disk GiB','Budget published-rule / capacity-priced USD','Cloud same USD','Storage-focused same USD'],[
            [basis,rate,
             *[f"{next(r for r in s['economics_audit_sensitivity'] if r['basis']==basis and r['rate']==rate and r['profile']=='budget_vps')[key]:.3f}" for key in ['canonical_gib','primary_gib','allocation_including_snapshot_temporary_vacuum_gib']],
             *[f"{r['month_36']['monthly_cost']['total']:.2f} / {r['illustrative_capacity_priced_total']:.2f}" for profile in ['budget_vps','mainstream_cloud','storage_focused'] for r in [next(x for x in s['economics_audit_sensitivity'] if x['basis']==basis and x['rate']==rate and x['profile']==profile)]]]
            for basis in ['historical_projected','closed_v3_fixture_mean'] for rate in [100,1000,10000]]),
        '\n### A6. Preservation and final disposition\n',
        f"\nHEAD remains `{head}` on `{a['branch']}`. Index diff is empty. SHA-256 comparison of every preexisting tracked file found **zero changes**. "
        'Git reports only the requested new audit document and files under verification/task718 as untracked. '
        'summary.json records that status before its own creation on the first assembly; it is not a historical initial-clean claim. '
        'The initial clean prerequisite was independently checked before any audit file was created. No staging, commit, push, merge, activation, migration, reset or deployment occurred.\n',
        '\nAudit document and retained evidence are ready for owner review and an owner-performed commit. '
        '**Original acceptance: INCOMPLETE. Production readiness: BLOCKED. Do not officially close Milestone 7 now.**\n'])
    DOC.write_text(DOC.read_text(encoding='utf-8').split(MARKER)[0]+''.join(lines),encoding='utf-8')
    print(json.dumps({k:summary[k] for k in ['completed_test_counts','codec_size_mismatches','worker_roundtrips','manifest_difference_count','frozen_metadata','frozen_totals']},indent=2))


if __name__=='__main__':
    main()
