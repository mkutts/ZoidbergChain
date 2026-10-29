"""Independent Decimal arithmetic, test outcome census and preservation checks.

Does not import the simulator. Re-derives all monthly bills from input values.
"""
from collections import Counter
from decimal import Decimal as D, ROUND_CEILING
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
G=D(1024**3)


def read(name):
    return json.loads((OUT/name).read_bytes())


def save(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n',encoding='utf-8')


def main():
    inputs=read('economic_inputs.json')
    workloads={w['name']:w for w in inputs['workloads']}
    groups=read('economic_scenarios.json')['scenarios']
    sensitivity=read('sensitivity_scenarios.json')
    groups+=sensitivity['one_at_a_time']+sensitivity['best_reference_stress']
    max_bill_error=D(0);max_sum_error=D(0);max_capacity_error=D(0)
    for scenario in groups:
        p={k:D(str(v)) for k,v in scenario['assumptions'].items()}
        profile=inputs['profiles'][scenario['profile']]
        w=workloads[scenario['workload']]
        R=D(str(w['canonical_bytes']))+p['extra_evidence_bytes']
        rate=D(scenario['blocks_per_day'])
        elapsed=D(0);cumulative=D(0)
        for days in inputs['month_days']:
            elapsed+=D(days)
            C=elapsed*rate*R
            primary=G*p['base_gib']+C*(1+p['index_page_fraction']+p['fragmentation_fraction'])
            H=primary*p['headroom_fraction']+D(days)*rate*R*(1+p['index_page_fraction']+p['fragmentation_fraction'])*p['write_reserve_multiplier']+G*p['headroom_fixed_gib']
            local=primary*(2+p['snapshot_copies'])+H
            billable=max(D(0),local/G-D(profile['included_primary_gib'])).to_integral_value(rounding=ROUND_CEILING)
            retained=primary*p['backup_copies']*p['backup_factor']
            egress=D(days)*rate*R*p['peers']*D('1.44')+primary*p['backup_frequency_per_month']+C*D('1.2')*p['bootstrap_serves_per_month']+primary*p['backup_factor']*p['restore_events_per_month']
            bill=D(str(profile['monthly_compute']))+billable*D(str(profile['primary_gib_month']))*p['disk_price_factor']+retained/G*D(str(profile['backup_gib_month']))+egress/G*D(str(profile['egress_gib']))
            cumulative+=bill
        m=scenario['month36']
        bill_error=abs(bill-D(str(m['cost_usd']['total'])))
        sum_error=abs(cumulative-D(str(scenario['three_year_cumulative_usd'])))
        capacity_error=abs(local-D(str(m['local_capacity_bytes'])))
        max_bill_error=max(max_bill_error,bill_error);max_sum_error=max(max_sum_error,sum_error);max_capacity_error=max(max_capacity_error,capacity_error)
        assert bill_error<D('.0000001') and sum_error<D('.000001')
        assert capacity_error<D('.1')
        assert billable==m['additional_billed_disk_gib']
        assert (bill<100)==scenario['under100']
        assert abs(sum(v for k,v in m['cost_usd'].items() if k!='total')-m['cost_usd']['total'])<1e-7
        assert abs(m['serialized_media_bytes']+m['other_canonical_bytes']-m['canonical_bytes'])<.1
        assert abs(m['canonical_bytes']+m['database_base_bytes']+m['index_and_page_overhead_bytes']+m['fragmentation_bytes']-m['primary_database_bytes'])<.1
    save('independent_economic_checks.json',dict(status='PASS',scenarios=len(groups),months_per_scenario=36,
        methodology='Decimal closed-form capacity/billing recomputed independently, no simulator imports',
        max_monthly_usd_error=str(max_bill_error),max_cumulative_usd_error=str(max_sum_error),max_capacity_byte_error=str(max_capacity_error),
        tolerance=dict(month_usd='1e-7',cumulative_usd='1e-6',capacity_bytes='.1')))
    counts=Counter();details={};ids=[]
    for name in ('measurements','bridge','canonical','codecs','atomic','active'):
        value=read(name+'_outcomes.json')
        group=Counter(r['outcome'] for r in value['reports'])
        group['deselected']=len(value['deselected'])
        counts.update(group)
        details[name]=dict(counts=dict(group),exitstatus=value['exitstatus'],
            nonpassing=[r for r in value['reports'] if r['outcome']!='passed'],deselected=value['deselected'])
        ids.extend(r['nodeid'] for r in value['reports'])
    assert len(ids)==len(set(ids)), 'overlapping groups are not disjoint'
    for key in ('passed','failed','skipped','deselected'):
        counts.setdefault(key,0)
    command_timeouts=sum(row['exit']=='TIMEOUT' for phase in ('tests','replay') for row in read(phase+'_execution.json'))
    save('test_summary.json',dict(counts=dict(counts),groups=details,disjoint_test_ids=True,
        final_command_timeouts=command_timeouts,
        failures=[r for group in details.values() for r in group['nonpassing'] if r['outcome']=='failed']))
    before=read('preflight.json')
    changed=[path for path,digest in before['tracked_sha256'].items() if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=digest]
    git=lambda *a:subprocess.check_output(['git',*a],cwd=ROOT,text=True).strip()
    assert not changed
    assert git('rev-parse','HEAD')==before['head']
    assert git('branch','--show-current')==before['branch']
    assert not git('diff','--cached','--name-only')
    status=git('status','--porcelain=v1','--untracked-files=all').splitlines()
    assert all(line.startswith('?? docs/milestone-7-final-economics-and-acceptance-review.md') or line.startswith('?? verification/task722/') for line in status)
    save('preservation.json',dict(status='PASS',preexisting_tracked_files_preserved=len(before['tracked_sha256']),changed_preexisting_files=changed,
                                index_clean=True,head=before['head'],branch=before['branch'],git_status=status))
    sources={path:digest for path,digest in before['tracked_sha256'].items() if path.startswith(('canonical_v3/','codec_prototype/','benchmarks/task720_v1/','verification/task721/')) or path in ('scripts/milestone_7_task_7_3_corpus.py','scripts/milestone_7_task_7_4_benchmark.py','scripts/milestone_7_task_7_7_block_composition.py','scripts/milestone_7_task_7_8_node_economics.py','tests/fixtures/milestone_7_corpus_v1_manifest.json','benchmarks/milestone_7_task_7_4_results.json','benchmarks/milestone_7_task_7_7_results.json','benchmarks/milestone_7_task_7_8_results.json','benchmarks/milestone_7_task_7_11_results.json')}
    save('source_checksums.json',dict(sha256=sources,complete_preexisting_inventory='preflight.json',
        corpus_identity='Historical 36 generated objects + new 34 generated objects exact frozen hash/size, verified by fresh replay; source manifests in this inventory.'))
    files=[ROOT/'docs/milestone-7-final-economics-and-acceptance-review.md']+sorted(OUT.rglob('*'))
    (OUT/'checksums.sha256').write_text(''.join(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.relative_to(ROOT).as_posix()+'\n' for path in files if path.is_file() and path.name!='checksums.sha256'),encoding='utf-8')
    print('Independent economics, disjoint test census and preexisting-file preservation PASS:',dict(counts))


if __name__=='__main__':
    main()
