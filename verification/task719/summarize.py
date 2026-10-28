"""Build inventories and review summaries from retained Task 7.19 evidence."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]


def read(name):
    return json.loads((OUT / name).read_bytes())


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def main():
    codec = read('tests_codec_outcomes.json')
    linux = [dict(nodeid=r['nodeid'], reason='requires an actual Linux kernel',
                  historical_source='verification/task718/tests_codec.txt', current_outcome='skipped')
             for r in codec['reports'] if r['outcome'] == 'skipped']
    assert len(linux) == 193 and all('7_6d_linux_isolation.py' in x['nodeid'] for x in linux)
    atomic = read('inventory_collect_original_skips_outcomes.json')
    wal = [dict(nodeid=r['nodeid'], reason='WAL crash verification requires a SQLite runtime with the WAL-reset fix',
                historical_source='verification/task718/admission_history_atomic_recheck.txt',
                current_outcome='not rerun; collected only; unchanged runtime gate')
           for r in atomic['collected'] if '::test_external_process_termination_journal_recovery_and_retry[' in r['nodeid'] and r['nodeid'].endswith('-WAL]')]
    assert len(wal) == 4
    deselected = read('inventory_collect_deselection_outcomes.json')['deselected']
    assert len(deselected) == 1
    save('original_skip_deselection_inventory.json', dict(total_historical_skipped=197,
        groups=dict(platform_linux=linux, sqlite_wal_safety=wal),
        absent_reasons=dict(optional_dependencies=0, expensive_manual=0, missing_credentials_services=0, other=0),
        deselected=[dict(nodeid=n, reason='explicit -k not public_upload in Task 7.18 image_recheck',
            necessary_original_compression_economics=False, current_control='passed unchanged outside restricted account') for n in deselected],
        acceptance=dict(linux='Includes exact-corpus reconstruction plus Linux containment/lifecycle tests. Windows equivalents and 72 source roundtrips pass; skipped Linux behavior is not established on this host.',
            wal='Atomic crash durability, not compression selection, exact-byte reconstruction, metadata measurement or economics. No safety-gate override.')))
    baseline = {r['nodeid']: r for r in read('baseline_measurements_outcomes.json')['reports'] if r['outcome'] == 'failed'}
    final = {r['nodeid']: r for r in read('tests_measurements_outcomes.json')['reports']}
    failures = []
    for nodeid, outcome in baseline.items():
        stale_assertion = any(n in nodeid for n in ['test_manifest_regenerates', 'test_frozen_genesis_jpeg'])
        failures.append(dict(nodeid=nodeid, baseline_detail=outcome['detail'], current_outcome=final[nodeid]['outcome'],
            current_detail=final[nodeid]['detail'], reproduced_before_repair=True,
            observed_before_task718='No retained earlier failed execution found; assertions/wrappers predate 7.18; underlying environment issue and repair documented by 7.3 and 7.12.',
            cause=('Obsolete whole-manifest equality assertion, including mutable historical validator observations' if 'test_manifest_regenerates' in nodeid else
                   'Obsolete expectation that valid frozen JPEG raises MALFORMED_MEDIA after the image-worker repair' if 'test_frozen_genesis_jpeg' in nodeid else
                   'Reproduction wrapper compared historical validator observations as corpus identity'),
            compression_correctness_defect=False, consensus_or_canonical_hash_defect=False,
            windows_environment_related=True, prior_documentation=['docs/milestone-7-corpus.md', 'docs/milestone-7-image-admission-regression.md'],
            action='Left assertions unchanged under task constraint; explicit outstanding test debt' if stale_assertion else 'Repaired measurement verification wrapper only',
            original_acceptance_effect='Blocks an all-green legacy measurement selection; does not contradict direct source/roundtrip/measurement checks' if stale_assertion else 'Resolved original-scope reproduction blocker'))
    assert len(failures) == 5
    save('five_failure_triage.json', failures)
    sources = [p for p in read('before.json')['tracked_sha256'] if p.startswith('scripts/milestone_7_task_') and
               any(p.endswith(n) for n in ['7_3_corpus.py','7_4_benchmark.py','7_4a_image_evaluation.py','7_7_block_composition.py','7_8_node_economics.py','7_11_storage.py'])]
    save('source_versions.json', [dict(path=p, before_sha256=read('before.json')['tracked_sha256'][p],
        after_sha256=hashlib.sha256((ROOT / p).read_bytes()).hexdigest(),
        last_committed_version=subprocess.check_output(['git', 'log', '-1', '--format=%H %s', '--', p], cwd=ROOT).decode().strip()) for p in sources])
    phases = ['tests_measurements', 'tests_codec', 'tests_format_storage', 'tests_wrapper_guards', 'api_control_api_case']
    counts = Counter()
    for phase in phases:
        counts.update(r['outcome'] for r in read(phase + '_outcomes.json')['reports'])
    preservation = read('preservation.json')
    immutable = [p for p in read('before.json')['tracked_sha256'] if p.startswith(('benchmarks/', 'tests/fixtures/', 'verification/task718/'))]
    changed = preservation['tracked_changes']
    save('summary.json', dict(branch=preservation['branch'], head=preservation['head'], initial_status='clean',
        final_status=preservation['final_status'], index_changed=bool(preservation['index_diff']),
        files_modified=list(changed), preexisting_tracked_files=len(read('before.json')['tracked_sha256']),
        immutable_tracked_files_checked=len(immutable), immutable_tracked_changes=[p for p in immutable if p in changed],
        corpus_source_hashes_unchanged=preservation['corpus_before_after_equal'],
        comparisons=read('comparisons.json'), focused_completed_disjoint_counts=dict(counts),
        collection_only_deselections=len(deselected), historical_inventory=dict(failed=5, skipped=197, deselected=1, timeout_attempts=2),
        unresolved_test_ids=[n for n,r in final.items() if r['outcome'] == 'failed'],
        original_documented_commands=dict(corpus='PASS', codec='PASS', composition='Manifest gate repaired; full historical SQLite replay BLOCKED; --skip-sqlite PASS'),
        timeout_findings=dict(original_combined_v3_480_seconds='190 completed progress dots, next node is public API test; no completed summary',
            original_standalone_45_seconds='Socket accept during event-loop self-pipe setup before API handler',
            new_restricted_api_35_seconds='TIMEOUT; same setup stack; writable TEMP/TMP did not resolve',
            new_restricted_stdlib_control='12-second self-watchdog timeout, no API/database',
            new_unrestricted_controls='Socketpair PASS; unchanged API test 1 PASS in 0.90 seconds'),
        reproduction_acceptance='PARTIAL', ready_for_owner_review_and_commit=True,
        remaining_blockers=['Historical 7.7 WAL SQLite replay conflicts with active DELETE-only storage safety gate',
                            'Two obsolete Task 7.3 assertions remain failed and unchanged',
                            'Linux execution not rerun; 193 platform skips and four gated WAL crash cases are not passes'],
        not_run=['No full suite', 'No 7.17 reviewer-journal or consensus sequence', 'No Linux runtime tests or atomic WAL crash executions'],
        milestone_completion_claim=False))


if __name__ == '__main__':
    main()
