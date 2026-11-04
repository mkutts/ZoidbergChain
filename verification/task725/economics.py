"""Measured small-sample coefficients, explicit extrapolation, historical prices.

No price discovery or changes to any prior model. Month = historical fixed
calendar; all quantity/cost series are retained for the full 36 months.
"""
import argparse
import csv
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from verification.task725.measure import read, save, load

GIB = 1024**3
DAYS = [31,28,31,30,31,30,31,31,30,31,30,31]*3
OLD = load('task725_old_econ', 'verification/task722/economics.py')


def coefficients(storage, backup, transfer, name):
    full = storage['populations'][name]['full']['observations']
    cycle = next(r['blocks'] for r in full if r['blocks'] > 5)
    # Exclude all prefix/init intervals; compare complete equal-composition cycles.
    slopes = []
    for a,b in zip(full, full[1:]):
        if a['blocks'] >= cycle:
            slopes.append(dict(from_blocks=a['blocks'], to_blocks=b['blocks'],
                overhead_per_block=((b['logical_bytes']-a['logical_bytes'])-(b['canonical_bytes']-a['canonical_bytes']))/(b['blocks']-a['blocks'])))
    assert slopes
    n = full[-1]['blocks']
    secondary = storage['populations'][name]['secondary_pages']['secondary_allocation_bytes']
    net = transfer['populations'][name]
    fresh = next(r for r in transfer['exchanges'] if r['label'] == name+':fresh_history')
    # Remove one collection/start-line/header cost, rather than copying it N/n times.
    # JSON arrays add 2(n-1) comma bytes across blocks and certificates.
    hist_per_block = (fresh['canonical_payload_bytes']+fresh['duplicated_certificate_value_bytes'])/fresh['blocks']+2
    hist_fixed = fresh['response_body_bytes']-fresh['canonical_payload_bytes']-fresh['duplicated_certificate_value_bytes']-2*fresh['blocks']+fresh['response_http_framing_bytes']
    return dict(initial_db_bytes=full[0]['logical_bytes'], measured_blocks=n,
        overhead_per_block=slopes[-1]['overhead_per_block'], overhead_range=[min(s['overhead_per_block'] for s in slopes), max(s['overhead_per_block'] for s in slopes)],
        marginal_intervals=slopes, secondary_index_bytes_at_measured_n=secondary,
        secondary_bytes_per_block_including_fixed=secondary/n,
        snapshot_ratio=backup['populations'][name]['snapshot_ratio'], backup_ratio=backup['populations'][name]['backup_ratio'],
        # Keep both the staged full backup and restored destination at recovery
        # peak, in addition to the normally retained source and snapshot.
        recovery_ratio=(backup['populations'][name]['recovery']['peak_directory_bytes']-backup['populations'][name]['snapshot']['logical_bytes'])/full[-1]['logical_bytes'],
        propagation_sender_bytes_per_block=net['propagation_sender_bytes']/net['n'],
        acknowledgment_bytes_per_block=net['propagation_acknowledgment_bytes']/net['n'],
        historical_response_bytes_per_block=hist_per_block, historical_response_fixed_bytes=hist_fixed,
        historical_request_fixed_bytes=fresh['request_http_framing_bytes'])


def simulate(w, rate, profile, coef, stage=3, override=None):
    if stage == 0:
        return OLD.simulate(w, rate, profile, monthly=True)
    assumptions = dict(base_gib=1, fragmentation_fraction=.15, operational_fraction=.20,
        operational_fixed_gib=5, monthly_write_reserve=1.45, peers=8, network_contingency=1.20,
        retained_backups=4, backup_uploads_per_month=4, retained_snapshots=1,
        bootstrap_serves_per_month=1/12, restore_events_per_month=1/12)
    assumptions.update(override or {})
    a = assumptions; rows = []; cumulative = 0
    overhead = a.get('overhead_per_block', coef['overhead_per_block'])
    for month, days in enumerate(DAYS, 1):
        n = rate*sum(DAYS[:month]); new = rate*days; r = w['canonical_bytes']; canonical_bytes = n*r
        physical = coef['initial_db_bytes']+n*(r+overhead)
        # Separate inherited non-media base reserve and aged-fragmentation allowance.
        primary = physical+GIB*a['base_gib']+canonical_bytes*a['fragmentation_fraction']
        headroom = primary*a['operational_fraction']+new*(r+overhead+r*a['fragmentation_fraction'])*a['monthly_write_reserve']+GIB*a['operational_fixed_gib']
        snapshot = primary*coef['snapshot_ratio']*a['retained_snapshots']
        recovery = primary*coef['recovery_ratio']
        ratio = coef['backup_ratio'] if stage >= 2 else .95
        retained = primary*ratio*a['retained_backups']
        local = primary+snapshot+recovery+headroom
        backup_out = primary*a['backup_uploads_per_month']  # No new upload protocol measured.
        restore_out = primary*ratio*a['restore_events_per_month']
        if stage >= 3:
            sender = coef['propagation_sender_bytes_per_block']; ack = coef['acknowledgment_bytes_per_block']
            # 8 outgoing propagations + one ACK to the supplying peer. One incoming
            # propagation + ACKs from 8 peers. Contingency is explicitly an assumption.
            peer_out = new*(a['peers']*sender+ack)*a['network_contingency']
            incoming = new*(sender+a['peers']*ack)*a['network_contingency']
            bootstrap = (n*coef['historical_response_bytes_per_block']+coef['historical_response_fixed_bytes'])*a['network_contingency']
        else:
            peer_out = new*r*a['peers']*1.20*1.20
            incoming = new*r*1.15*1.20
            bootstrap = canonical_bytes*1.20
        bootstrap_out = bootstrap*a['bootstrap_serves_per_month']
        billed = math.ceil(max(0, local/GIB-profile['included_primary_gib']))
        costs = dict(compute_ram=profile['monthly_compute'], local_disk=billed*profile['primary_gib_month'],
            retained_backups=retained/GIB*profile['backup_gib_month'],
            peer_egress=peer_out/GIB*profile['egress_gib'], backup_upload_egress=backup_out/GIB*profile['egress_gib'],
            bootstrap_serve_egress=bootstrap_out/GIB*profile['egress_gib'], backup_restore_egress=restore_out/GIB*profile['egress_gib'])
        costs['total'] = sum(costs.values()); cumulative += costs['total']
        rows.append(dict(month=month, days=days, blocks=n, canonical_bytes=canonical_bytes,
            measured_basis_database_bytes=physical, database_initialization_bytes=coef['initial_db_bytes'],
            projected_database_overhead_bytes=n*overhead, assumed_aged_fragmentation_bytes=canonical_bytes*a['fragmentation_fraction'],
            primary_database_bytes=primary, snapshot_bytes=snapshot, recovery_workspace_bytes=recovery,
            operational_headroom_bytes=headroom, local_capacity_bytes=local, backup_retained_bytes=retained,
            peer_incoming_bytes=incoming, peer_outgoing_bytes=peer_out, backup_upload_bytes=backup_out,
            bootstrap_once_bytes=bootstrap, expected_bootstrap_serve_bytes=bootstrap_out,
            expected_restore_transfer_bytes=restore_out, additional_billed_disk_gib=billed,
            cost_usd=costs, cumulative_cost_usd=cumulative))
    return dict(workload=w['name'], blocks_per_day=rate, profile=profile['id'], assumptions=a,
        coefficients=coef, monthly=rows, month36=rows[-1], three_year_cumulative_usd=cumulative,
        under100=rows[-1]['cost_usd']['total'] < 100,
        whole_history_json_capacity=dict(assumed_memory_gib=profile['memory_gib'],
            canonical_history_alone_exceeds_ram=rows[-1]['canonical_bytes']>profile['memory_gib']*GIB,
            status='BLOCKED at existing whole-history JSON boundary; bounded retrieval or separately priced memory qualification required',
            evidence='Source/size inference; no OOM test. Canonical bytes are a lower bound before separate certificates and JSON object expansion.'),
        capacity_crossings={str(t):next((r['month'] for r in rows if r['local_capacity_bytes'] >= t*GIB), None) for t in (160,500,1000,10000,16000)},
        affordability_scope='Conditional illustrative pool pricing, unquoted and service/CPU/IOPS capacity unqualified')


def run(out):
    inputs = read('verification/task722/economic_inputs.json')
    data = {name:json.loads((out/name).read_bytes()) for name in ('workloads.json','sqlite.json','backup_recovery.json','transfer.json')}
    growth={}
    for name,pop in data['sqlite.json']['populations'].items():
        minimal={r['blocks']:r for r in pop['minimal']['observations']}
        no_secondary={r['blocks']:r for r in pop['no_secondary']['observations']}
        growth[name]=[dict(blocks=r['blocks'],secondary_entries_per_block_index=r['blocks'],
            transaction_entries=r['blocks'] if name=='native_index_control' else 0,
            full_minus_no_secondary_file_bytes=r['logical_bytes']-no_secondary[r['blocks']]['logical_bytes'],
            full_minus_no_secondary_live_page_bytes=r['live_allocated_page_bytes']-no_secondary[r['blocks']]['live_allocated_page_bytes'],
            full_minus_minimal_file_bytes=r['logical_bytes']-minimal[r['blocks']]['logical_bytes']) for r in pop['full']['observations']]
    save(out,'index_growth.json',dict(version=1,populations=growth,
        method='Exact arithmetic from equivalent per-count SQLite observations. Secondary aggregate file allocation is separate from full-minus-minimal schema footprint and endpoint per-index DROP-page accounting.',
        fixed_roots='Empty secondary index roots are fixed initialization, not linear per-block cost.'))
    cases = []; comparisons = []; workloads = []; coefficients_map = {}; sensitivities = []
    prior723 = read('benchmarks/task723_v1/economics.json')['scenarios']
    prior722 = read('verification/task722/economic_scenarios.json')['scenarios']
    original = read('benchmarks/milestone_7_task_7_8_results.json')['scenarios']
    for name, rows in data['workloads.json']['rows'].items():
        legal = [r for r in rows if r['record_bytes'] is not None]
        w = dict(name=name, n=len(legal), canonical_bytes=sum(r['record_bytes'] for r in legal)/len(legal),
            original_bytes=sum(r['original_bytes'] for r in legal)/len(legal), encoded_bytes=sum(r['encoded_bytes'] for r in legal)/len(legal),
            serialized_media_bytes=0, other_canonical_bytes=0)
        # Old simulator uses the partition only for descriptive outputs, not cost.
        w['other_canonical_bytes'] = w['canonical_bytes']
        workloads.append(w)
        coef = coefficients(data['sqlite.json'], data['backup_recovery.json'], data['transfer.json'], name)
        coefficients_map[name] = coef
        for rate in (100,1000,10000):
            for profile in inputs['profiles'].values():
                stages = [simulate(w,rate,profile,coef,stage) for stage in range(4)]
                s = stages[-1]; cases.append(s)
                prior_name = dict(balanced41='B_balanced', historical36='frozen_v3_historical36', production34='task720_reference34').get(name)
                priors = prior723 if name == 'balanced41' else prior722
                prior = next((r for r in priors if r['workload'] == prior_name and r['blocks_per_day'] == rate and r['profile'] == profile['id']), None)
                if prior:
                    assert abs(stages[0]['month36']['cost_usd']['total']-prior['month36']['cost_usd']['total']) < 1e-9
                costs = [r['month36']['cost_usd']['total'] for r in stages]
                o = next(r for r in original if r['scenario']['workload']=='representative_corpus' and r['scenario']['blocks_per_day']==rate and r['scenario']['profile']==profile['id'])
                comparisons.append(dict(workload=name, blocks_per_day=rate, profile=profile['id'],
                    prior_same_population_usd=costs[0], prior_evidence_available=prior is not None,
                    prior_source='Task 7.23' if name=='balanced41' else 'Task 7.22' if prior else 'Task 7.22 formula applied to Task 7.23 full legal corpus; new comparator',
                    updated_usd=costs[3], delta_usd=costs[3]-costs[0],
                    measured_storage_and_recovery_basis_delta=costs[1]-costs[0], measured_backup_ratio_delta=costs[2]-costs[1],
                    measured_simulated_transfer_basis_delta=costs[3]-costs[2],
                    original_task78_representative_usd=o['month_36']['monthly_cost']['total'],
                    delta_vs_original_task78=costs[3]-o['month_36']['monthly_cost']['total'],
                    original_comparison_limit='Different canonical context and workload for all except historical family; original 7.8 omitted snapshot/recovery capacity charges. Not a measured-data-only delta.'))
                if name == 'balanced41':
                    for label, override in [('marginal_low',dict(overhead_per_block=coef['overhead_range'][0])),
                        ('marginal_high',dict(overhead_per_block=coef['overhead_range'][1])),
                        ('no_aged_fragmentation',dict(fragmentation_fraction=0)),
                        ('network_contingency_50pct',dict(network_contingency=1.5)),
                        ('peers16',dict(peers=16)), ('backups12',dict(retained_backups=12))]:
                        value = simulate(w,rate,profile,coef,override=override)
                        sensitivities.append(dict(label=label, blocks_per_day=rate, profile=profile['id'],
                            cost_usd=value['month36']['cost_usd']['total'], local_gib=value['month36']['local_capacity_bytes']/GIB,
                            override=override, under100=value['under100']))
    save(out,'projections.json',dict(version=1,workloads=workloads,coefficients=coefficients_map,
        pricing=inputs['profiles'],pricing_source='Frozen Task 7.22 illustrative USD assumptions; no new quote or recommendation',
        scenarios=cases,comparisons=comparisons,sensitivities=sensitivities,
        formulas=dict(primary='P=1GiB+measured_init+N*(mean_R+measured_marginal_overhead)+.15*C assumed aged fragmentation',
            local='P + (.20*P+1.45*monthly*(R+overhead+.15R)+5GiB) + measured_snapshot_ratio*P + measured_additional_recovery_ratio*P',
            backups='4 measured_backup_ratio*P retained remotely; four full P uploads/month, excluding unmeasured upload protocol framing',
            propagation='1.20 assumed contingency * monthly_blocks * (8*measured_sender_per_block+measured_ack_per_block)',
            bootstrap='1.20 assumed contingency * (N*(mean_R+mean_certificate+2)+fixed_collection_HTTP); excludes authority/finality handshake',
            cost='compute+ceil(max(0,local_GiB-included))*disk_rate+backup_GiB*backup_rate+(propagation+4P+bootstrap/12+backup/12)/GiB*egress_rate'),
        limitations=['Small append-only repeated-content samples; no observation of multi-year churn, fork load, deeper B-trees, compaction, native transaction traffic or real-world MIME weights.',
            'Fixed initialization is charged once, never linearly multiplied. Marginal overhead interval range is sensitivity, not a confidence interval or asymptotic proof.',
            'Measured full copies are 1:1; base reserve, headroom, aged fragmentation, frequency, retention, peers, contingency and restore/bootstrap frequency remain assumptions.',
            'Media-only. No future journal/archive/proof traffic, backup upload protocol overhead, taxes, admin labor, tier premiums or restoration SLA qualification. No universal under-$100 claim.']))
    with (out/'month36.csv').open('w',encoding='utf-8',newline='') as handle:
        fields=['workload','blocks_per_day','profile','canonical_gib','primary_gib','local_gib','backup_gib','bootstrap_gib','updated_usd','prior_usd','delta_usd','under100','three_year_usd']
        writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader()
        for s,c in zip(cases,comparisons,strict=True):
            m=s['month36']
            writer.writerow(dict(workload=s['workload'],blocks_per_day=s['blocks_per_day'],profile=s['profile'],
                canonical_gib=m['canonical_bytes']/GIB,primary_gib=m['primary_database_bytes']/GIB,local_gib=m['local_capacity_bytes']/GIB,
                backup_gib=m['backup_retained_bytes']/GIB,bootstrap_gib=m['bootstrap_once_bytes']/GIB,
                updated_usd=c['updated_usd'],prior_usd=c['prior_same_population_usd'],delta_usd=c['delta_usd'],under100=s['under100'],three_year_usd=s['three_year_cumulative_usd']))
    print('Economics:',len(cases),'36-month scenarios;',len(sensitivities),'sensitivity cases',flush=True)


if __name__ == '__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=Path(__file__).resolve().parent)
    args=ap.parse_args();target=args.output.resolve()
    assert target==Path(__file__).resolve().parent or ROOT/'temp' in target.parents
    run(target)
