"""Bounded documentation/evidence verification; no active application or DB calls.

Writes only new Task 7.24 evidence. Never rewrites historical result files.
"""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DOCS = [
    ROOT / 'docs/milestone-7-final-closeout-and-owner-decisions.md',
    ROOT / 'docs/zoidbergchain-distributed-complete-block-archiving-proposal.md',
]


def read(path):
    return json.loads((ROOT / path).read_bytes())


def save(name, value):
    (HERE / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def preservation():
    before = read('verification/task724/preflight.json')
    tracked = git('ls-files').splitlines()
    assert tracked == sorted(before['tracked_sha256']), 'Tracked inventory changed'
    changed = [p for p, h in before['tracked_sha256'].items() if sha(ROOT / p) != h]
    assert not changed, changed
    assert git('branch', '--show-current') == before['branch']
    assert git('rev-parse', 'HEAD') == before['head']
    index_sha = hashlib.sha256(git('ls-files', '--stage').encode()).hexdigest()
    assert index_sha == before['initial_index_sha256'], 'Index changed'
    assert not git('diff', '--name-only') and not git('diff', '--cached', '--name-only')
    allowed_docs = {p.relative_to(ROOT).as_posix() for p in DOCS}
    status = git('status', '--porcelain=v1', '--untracked-files=all').splitlines()
    for line in status:
        assert line.startswith('?? '), line
        path = line[3:].replace('\\', '/')
        assert path in allowed_docs or path.startswith('verification/task724/'), line
    return dict(
        status='PASS', branch=before['branch'], head=before['head'],
        tracked_files_checked=len(tracked), changed_preexisting_files=changed,
        index_unchanged=True, initial_status=before['initial_status'], final_status=status,
        production_changes=False, historical_evidence_changes=False,
        staged=False, commit_or_push=False,
    )


def historical_manifests():
    results = []
    for rel in [
        'verification/task719/checksums.sha256',
        'benchmarks/task720_v1/checksums.sha256',
        'verification/task721/checksums.sha256',
        'verification/task722/checksums.sha256',
        'benchmarks/task723_v1/checksums.sha256',
    ]:
        manifest = ROOT / rel
        count = 0
        for line in manifest.read_text().splitlines():
            if not line.strip():
                continue
            expected, name = line.split(maxsplit=1)
            # Task 7.21's manifest explicitly uses package-relative names.
            base = manifest.parent if rel.startswith('verification/task721/') else ROOT
            target = base / name.strip().lstrip('*')
            assert target.is_file(), str(target)
            assert sha(target) == expected, str(target)
            count += 1
        results.append(dict(manifest=rel, entries_verified=count, status='PASS'))
    return results


def percentile(values, p):
    values = sorted(values)
    return values[math.ceil(len(values) * p / 100) - 1]


def metadata(rows):
    percentages = [100 * r['nonmedia_bytes'] / r['record_bytes'] for r in rows]
    return dict(n=len(rows), p50=percentile(percentages, 50), p95=percentile(percentages, 95),
                worst=max(percentages), mean=sum(percentages) / len(rows),
                below15=sum(p < 15 for p in percentages), measurement_status='FAIL',
                owner_exception=True)


def local_links():
    checked = []
    for path in [*DOCS, HERE / 'README.md']:
        text = path.read_text(encoding='utf-8')
        for link in re.findall(r'\[[^\]]*\]\(([^)]+)\)', text):
            if '://' in link or link.startswith('#'):
                continue
            target = unquote(link.split('#')[0]).strip('<>')
            resolved = (path.parent / target).resolve()
            assert resolved.is_file(), (str(path), link)
            assert resolved.is_relative_to(ROOT), (str(path), link)
            checked.append(dict(source=path.relative_to(ROOT).as_posix(), target=link))
    proposal = DOCS[1].read_text(encoding='utf-8')
    for path in [*DOCS, HERE / 'README.md', HERE / 'verify.py']:
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            assert line == line.rstrip(), (str(path), number, 'trailing whitespace')
            assert not re.match(r'^(<<<<<<<|=======|>>>>>>>)', line), (str(path), number, 'conflict marker')
    packages = re.findall(r'^### ([A-K])\. ', proposal, re.M)
    assert packages == list('ABCDEFGHIJK'), packages
    for field in ['Purpose', 'Dependencies', 'Security boundary', 'Acceptance',
                  'Deliverables', 'Consensus/protocol changes']:
        assert proposal.count(f'**{field}:**') == 11, field
    tests = re.findall(r'^\| (\d+)\. ', proposal, re.M)
    assert tests == [str(i) for i in range(1, 13)], tests
    return dict(status='PASS', local_links=len(checked), checked=checked,
                work_packages=packages, future_acceptance_tests=12,
                distributed_tests_executed=0,
                limitation='Local file targets and document inventory checked; architectural correctness requires future review/testing.')


def reconcile():
    candidates = read('benchmarks/task723_v1/candidates.json')
    records = read('benchmarks/task723_v1/records.json')
    manifest = read('benchmarks/task723_v1/manifest.json')
    trials = read('benchmarks/task723_v1/codecs.json')['rows']
    rows = records['rows']
    legal = [r for r in rows if r['record_bytes'] is not None]
    over = [dict(id=r['id'], original_bytes=r['original_bytes'])
            for r in rows if r['record_bytes'] is None]
    assert len(rows) == 58 and len(legal) == 56 and len(manifest['samples']) == 59
    assert {r['id']: r['original_bytes'] for r in over} == {
        'jpeg-texture-1280': 2242286, 'png-texture-1280': 3594660,
    }
    assert sum(r['codec'] == 'zstd' for r in legal) == 31
    assert sum(r['codec'] == 'identity' for r in legal) == 25
    assert len(trials) == 413
    primary_ids = {r['id'] for r in rows}
    assert sum(t['id'] in primary_ids for t in trials) == 406
    for r in legal:
        assert sum(r['field_ledger'].values()) == sum(r['partition'].values()) == r['record_bytes']
        assert r['base64_media_bytes'] == 4 * ((r['encoded_bytes'] + 2) // 3)
        assert r['nonmedia_bytes'] == r['record_bytes'] - r['base64_media_bytes']
        assert r['record_bytes'] <= r['identity_record_bytes'] and r['exact_roundtrip']
    b = next(p for p in candidates['profiles'] if p['name'] == 'B_balanced')
    assert (b['static_cap'], b['gif_cap'], b['text_cap'], b['encoded_cap'], b['proposed_block_cap']) == (
        262144, 524288, 16384, 525312, 1048576,
    )
    assert b['encoded_cap'] - b['gif_cap'] == 1024
    base64 = 4 * ((b['encoded_cap'] + 2) // 3)
    bound = base64 + 196608 + 98304 + 32768
    assert base64 == 700416 and bound == b['safe_complete_bound'] == 1028096
    assert b['proposed_block_cap'] - bound == 20480
    admitted = [r for r in legal if r['id'] in b['admitted_ids']]
    assert len(admitted) == b['admitted'] == 41 and b['population'] == 58
    assert abs(sum(r['record_bytes'] for r in admitted) / 41 - 118935.53658536586) < 1e-8
    control = records['diagnostic_controls'][0]
    assert (control['original_bytes'], control['encoded_bytes'], control['base64_media_bytes']) == (104, 105, 140)
    assert (control['identity_descriptor_bytes'], control['descriptor_bytes']) == (363, 359)
    assert (control['identity_record_bytes'], control['record_bytes']) == (33331, 33327)
    previous = read('verification/task722/producer_counterexample.json')
    assert (previous['identity_record'], previous['selected_record']) == (33330, 33326)
    primary_metadata = metadata(legal)
    balanced_metadata = metadata(admitted)
    for key in ('p50', 'p95', 'worst', 'mean'):
        assert abs(primary_metadata[key] - candidates['primary']['metadata_percent'][key]) < 1e-10
        assert abs(balanced_metadata[key] - b['statistics']['metadata_percent'][key]) < 1e-10
    e = read('benchmarks/task723_v1/economics.json')
    assert len(e['inputs']['month_days']) == 36 and sum(e['inputs']['month_days']) == 1095
    assert len(e['scenarios']) == 36 and len(e['sensitivities']) == 54
    economics = []
    for s in e['scenarios']:
        if s['workload'] != 'B_balanced':
            continue
        m = s['month36']
        assert len(s['monthly']) == 36 and m['blocks'] == 1095 * s['blocks_per_day']
        assert abs(sum(x['cost_usd']['total'] for x in s['monthly']) - m['cumulative_cost_usd']) < 1e-6
        economics.append(dict(
            blocks_per_day=s['blocks_per_day'], host=s['profile'],
            canonical_gib=m['canonical_bytes'] / 2**30,
            local_capacity_gib=m['local_capacity_bytes'] / 2**30,
            month36_usd=m['cost_usd']['total'], full_three_year_usd=m['cumulative_cost_usd'],
            under100=m['cost_usd']['total'] < 100,
        ))
    spec = importlib.util.spec_from_file_location('task724_readonly_723_check', ROOT / 'benchmarks/task723_v1/crosscheck.py')
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    independent = checker.check(ROOT / 'benchmarks/task723_v1')
    assert independent['status'] == 'PASS' and independent['decimal_month_checks'] == 1350
    return dict(
        status='PASS', scope='Documentation and bounded read-only evidence verification; no archive implementation',
        counts=dict(primary_originals=58, legal_selected_records=56, zstd=31, identity=25,
                    diagnostic_originals=1, primary_native_trials=406, total_native_trials=413,
                    above_cap_originals=over, balanced_size_only_admitted=41),
        balanced=dict(static_original_bytes=262144, gif_original_bytes=524288,
                      text_original_bytes=16384, encoded_bytes=525312, complete_bytes=1048576,
                      base64_bound=base64, analytic_complete_bound=bound, complete_headroom=20480,
                      status='PROVISIONAL; production activation unapproved'),
        metadata=dict(primary_legal56=primary_metadata, balanced41=balanced_metadata),
        no_expansion=dict(interpretation='complete canonical record vs same original, same-context identity',
                          measured_selected_status='PASS in isolation', raw_universal_status='FAIL retained',
                          task723_counterexample=dict(M=104, E=105, D_identity=363, D_selected=359,
                                                      R_identity=33331, R_selected=33327),
                          physical_monotonicity='NOT VERIFIED'),
        three_year_economics=dict(days=1095, retention='Full historical retention per modeled node',
                                 balanced=economics, distributed_savings_measured=False,
                                 journal_costs_included=False, current_price_refresh=False),
        independent_723_checker=independent,
        decisions=dict(metadata_target='FAIL; explicit owner-approved exception',
                       model_a='Block-local complete lossless media reconstruction; node retention may differ',
                       canonical_finality='Separate authenticated chain anchor and historical proof requirements',
                       resolved=['R1 metadata exception', 'R5 canonical no-expansion interpretation'],
                       unresolved=['R2 representative-content evidence', 'R3 disabled application acceptance boundary',
                                   'R4 separate physical storage/real-transfer measurements']),
        verdicts=dict(task724_documentation='COMPLETE', original_milestone7='INCOMPLETE',
                      production_network='BLOCKED'),
        future_archive=dict(status='INACTIVE NOT IMPLEMENTED', provisional_independent_copies=3,
                            node_ids_equal_operators=False, post_delete_custody_required=True,
                            underreplication_stops_pruning=True, executed_distributed_tests=0),
    )


def main():
    preservation()
    result = reconcile()
    tests = read('verification/task724/tests.json')
    assert tests['status'] == 'PASS' and tests['exit_code'] == 0 and not tests['timed_out']
    assert tests['counts'] == {'passed': 14} and not tests['excluded_by_this_run']
    assert '14 passed' in (HERE / 'tests.txt').read_text(encoding='utf-8')
    result['fresh_analytical_tests'] = dict(status='PASS', passed=14, failed=0, skipped=0,
                                          deselected=0, archive_implementation_tests=0)
    result['historical_checksum_manifests'] = historical_manifests()
    save('findings.json', result)
    save('preservation.json', preservation())
    # Materialize generated link targets before checking the documentation.
    # Recompute the manifest after adding final documentation-check results.
    write_checksums()
    result['documentation_checks'] = local_links()
    save('findings.json', result)
    write_checksums()
    print(json.dumps(dict(status=result['status'], original_milestone7='INCOMPLETE',
                          production_network='BLOCKED', tracked_unchanged=1172,
                          historical_checksum_entries=sum(x['entries_verified'] for x in result['historical_checksum_manifests']),
                          decimal_month_checks=1350, local_links=result['documentation_checks']['local_links'],
                          distributed_tests_executed=0)))


def write_checksums():
    files = [*DOCS, *(p for p in HERE.iterdir() if p.is_file() and p.name != 'checksums.sha256')]
    lines = [f'{sha(p)}  {p.relative_to(ROOT).as_posix()}' for p in sorted(files)]
    (HERE / 'checksums.sha256').write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
