"""Analytical capacity/cost scenarios; no database, protocol or pricing mutations.

Uses exact measured canonical rows; retains historical assumptions separately.
All prices are illustrative USD, not provider quotes. No measured traffic mix.
"""
from collections import Counter
from copy import deepcopy
import csv
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
GIB=1024**3
DAYS=[31,28,31,30,31,30,31,31,30,31,30,31]*3


def read(path):
    return json.loads((ROOT/path).read_bytes())


def save(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n',encoding='utf-8')


def workload(name,rows,identity=False):
    n=len(rows)
    original=sum(r['original_bytes'] for r in rows)/n
    encoded=original if identity else sum(r['encoded_bytes'] for r in rows)/n
    canonical=sum(r['identity_record_bytes'] if identity else r['record_bytes'] for r in rows)/n
    media=sum((r['identity_descriptor_bytes']+8) if identity else r['partition']['serialized_media_representation_bytes'] for r in rows)/n
    # `"media":` = 8 bytes; descriptor itself includes its braces and payload.
    if identity:
        assert abs((media-canonical)-(sum(r['partition']['serialized_media_representation_bytes']-r['record_bytes'] for r in rows)/n))<1e-8
    return dict(name=name,n=n,object_ids=[r['id'] for r in rows],weighting='equal record measured subset; not observed traffic',
                original_bytes=original,encoded_bytes=encoded,serialized_media_bytes=media,
                canonical_bytes=canonical,other_canonical_bytes=canonical-media,
                original_totals=sum(r['original_bytes'] for r in rows),
                mime_counts=dict(Counter(r['mime'] for r in rows)),
                choices={'identity':n} if identity else dict(Counter(r['codec'] for r in rows)))


DEFAULT=dict(index_page_fraction=.10,fragmentation_fraction=.15,headroom_fraction=.20,
             write_reserve_multiplier=1.45,headroom_fixed_gib=5,base_gib=1,
             snapshot_copies=1,snapshot_frequency_per_month=30,backup_copies=4,backup_factor=.95,
             backup_frequency_per_month=4,peers=8,bootstrap_serves_per_month=1/12,
             restore_events_per_month=1/12,disk_price_factor=1,extra_evidence_bytes=0)


def simulate(w,rate,profile,params=None,monthly=False):
    p=dict(DEFAULT,**(params or {}))
    rows=[]; cumulative=0
    for month,days in enumerate(DAYS,1):
        blocks=rate*sum(DAYS[:month]); new=rate*days
        r=w['canonical_bytes']+p['extra_evidence_bytes']
        c=blocks*r
        index=c*p['index_page_fraction']; frag=c*p['fragmentation_fraction']
        primary=GIB*p['base_gib']+c+index+frag
        headroom=primary*p['headroom_fraction']+new*r*(1+p['index_page_fraction']+p['fragmentation_fraction'])*p['write_reserve_multiplier']+GIB*p['headroom_fixed_gib']
        snapshots=primary*p['snapshot_copies']; recovery=primary
        backups=primary*p['backup_copies']*p['backup_factor']
        local=primary+headroom+snapshots+recovery
        incoming=new*r*1.15*1.20
        peer_out=new*r*p['peers']*1.20*1.20
        backup_out=primary*p['backup_frequency_per_month']
        bootstrap=c*1.20; bootstrap_out=bootstrap*p['bootstrap_serves_per_month']
        restore_egress=primary*p['backup_factor']*p['restore_events_per_month']
        disk_rate=profile['primary_gib_month']*p['disk_price_factor']
        used=0; cost={}
        for label,capacity in [('primary_disk',primary),('snapshots',snapshots),('operational_headroom',headroom),('recovery_workspace',recovery)]:
            before=max(0,used/GIB-profile['included_primary_gib'])
            used+=capacity
            after=max(0,used/GIB-profile['included_primary_gib'])
            cost[label]=(after-before)*disk_rate
        billed=math.ceil(max(0,local/GIB-profile['included_primary_gib']))
        cost.update(compute_ram=profile['monthly_compute'],disk_billing_rounding=(billed-max(0,local/GIB-profile['included_primary_gib']))*disk_rate,
                    retained_backups=backups/GIB*profile['backup_gib_month'],
                    peer_egress=peer_out/GIB*profile['egress_gib'],backup_upload_egress=backup_out/GIB*profile['egress_gib'],
                    bootstrap_serve_egress=bootstrap_out/GIB*profile['egress_gib'],
                    backup_restore_egress=restore_egress/GIB*profile['egress_gib'],
                    ingress=0,extra_archive_nodes=0)
        cost['total']=sum(cost.values()); cumulative+=cost['total']
        rows.append(dict(month=month,days=days,blocks=blocks,original_media_bytes=blocks*w['original_bytes'],
            encoded_payload_bytes=blocks*w['encoded_bytes'],serialized_media_bytes=blocks*w['serialized_media_bytes'],
            other_canonical_bytes=blocks*(w['other_canonical_bytes']+p['extra_evidence_bytes']),canonical_bytes=c,
            database_base_bytes=GIB*p['base_gib'],index_and_page_overhead_bytes=index,fragmentation_bytes=frag,
            primary_database_bytes=primary,operational_headroom_bytes=headroom,snapshot_bytes=snapshots,
            backup_retained_bytes=backups,recovery_workspace_bytes=recovery,local_capacity_bytes=local,
            additional_billed_disk_gib=billed,bootstrap_once_bytes=bootstrap,peer_incoming_bytes=incoming,
            peer_outgoing_bytes=peer_out,backup_upload_bytes=backup_out,expected_bootstrap_serve_bytes=bootstrap_out,
            expected_restore_transfer_bytes=restore_egress,charged_egress_bytes=peer_out+backup_out+bootstrap_out+restore_egress,
            cost_usd=cost,cumulative_cost_usd=cumulative))
    output=dict(workload=w['name'],blocks_per_day=rate,profile=profile['id'],assumptions=p,month36=rows[-1],
                three_year_cumulative_usd=cumulative,under100=rows[-1]['cost_usd']['total']<100,
                affordability_scope='CONDITIONAL illustrative storage-pool model; regional quote, tier feasibility and operational throughput unverified',
                capacity_crossings={str(t):next((r['month'] for r in rows if r['local_capacity_bytes']>=t*GIB),None) for t in (160,500,1000,10000,16000)})
    if monthly:
        output['monthly']=rows
    return output


def main():
    config=read('benchmarks/milestone_7_task_7_8_config.json')
    profiles={name:dict(value,id=name,region='UNSPECIFIED in historical source; no regional quote',
                         assumption_date='2026-10-18',review_date='2026-10-28',quoted=False)
              for name,value in config['profiles'].items()}
    records=read('benchmarks/task720_v1/records.json')
    new=[r for r in records['rows'] if r['population']=='production-like']
    old=[r for r in records['rows'] if r['population']=='historical']
    workloads=[workload('frozen_v3_historical36',old),workload('task720_reference34',new),
               workload('task720_identity34',new,True)]
    for name,subset in [('small_le16KiB',[r for r in new if r['original_bytes']<=16384]),
                        ('medium_16_256KiB',[r for r in new if 16384<r['original_bytes']<=262144]),
                        ('large_gt1MiB',[r for r in new if r['original_bytes']>1048576]),
                        ('text_only',[r for r in new if r['mime']=='text/plain']),
                        ('images_only',[r for r in new if r['mime']!='text/plain'])]:
        workloads.append(workload(name,subset))
    old_config=config['workloads']['representative_corpus']
    historical_basis=dict(workloads[0],name='historical_projection_corrected',
        weighting='Exact rounded historical 7.8 config averages; not new frozen-v3 record evidence',
        original_bytes=old_config['original_bytes'],encoded_bytes=old_config['encoded_bytes'],
        canonical_bytes=old_config['canonical_block_bytes'],
        serialized_media_bytes=old_config['canonical_block_bytes']-old_config['metadata_bytes'],
        other_canonical_bytes=old_config['metadata_bytes'])
    workloads.append(historical_basis)
    wmap={w['name']:w for w in workloads}
    main_scenarios=[simulate(w,rate,p) for w in [*workloads[:2],historical_basis] for rate in (100,1000,10000) for p in profiles.values()]
    hist=read('benchmarks/milestone_7_task_7_8_results.json')
    historical=[]
    for item in hist['scenarios']:
        s=item['scenario'];w=deepcopy(config['workloads'][s['workload']])
        # Historical canonical already contains text serialization; metadata is
        # not E+N. Preserve exactly; no invented base64 partition for assumptions.
        historical.append(dict(scenario=s,month36=item['month_36'],three_year=item['three_year']))
    sensitivities=[]
    axes={
        'default':{},'identity_only':{'workload':'task720_identity34'},
        'small_media':{'workload':'small_le16KiB'},'medium_media':{'workload':'medium_16_256KiB'},
        'large_media':{'workload':'large_gt1MiB'},'text_mix':{'workload':'text_only'},'image_mix':{'workload':'images_only'},
        'larger_evidence':{'extra_evidence_bytes':65536},'external_proof_example':{'extra_evidence_bytes':1194},
        'backup_minimal':{'backup_copies':2,'backup_frequency_per_month':1},
        'backup12':{'backup_copies':12,'backup_factor':.98},
        'snapshot_weekly_retain1':{'snapshot_frequency_per_month':4},
        'snapshot_daily_retain7':{'snapshot_copies':7},
        'no_bootstrap_or_restore':{'bootstrap_serves_per_month':0,'restore_events_per_month':0},
        'bootstrap_monthly':{'bootstrap_serves_per_month':1},'peers16':{'peers':16},
        'capacity_disk_half_rate':{'disk_price_factor':.5},'ssd_double_rate':{'disk_price_factor':2},
        'high_page_fragmentation':{'index_page_fraction':.20,'fragmentation_fraction':.30},
    }
    for label,changes in axes.items():
        changes=dict(changes);w=wmap[changes.pop('workload','task720_reference34')]
        for rate in (100,1000,10000):
            for p in profiles.values():
                item=simulate(w,rate,p,changes);item['sensitivity']=label;sensitivities.append(item)
    cases={
        'best':('small_le16KiB',dict(backup_copies=2,backup_frequency_per_month=1,snapshot_frequency_per_month=4,bootstrap_serves_per_month=0,restore_events_per_month=0,disk_price_factor=.5)),
        'reference':('task720_reference34',{}),
        'stress':('large_gt1MiB',dict(extra_evidence_bytes=65536,backup_copies=12,backup_factor=.98,snapshot_copies=7,peers=16,bootstrap_serves_per_month=1,index_page_fraction=.20,fragmentation_fraction=.30,disk_price_factor=2))}
    ranges=[]
    for label,(name,params) in cases.items():
        for rate in (100,1000,10000):
            for p in profiles.values():
                item=simulate(wmap[name],rate,p,params);item['case']=label;ranges.append(item)
    save('economic_inputs.json',dict(calendar='36 months, 365 days/year, no leap day; 1095 days',month_days=DAYS,bytes_per_gib=GIB,
        profiles=profiles,workloads=workloads,default=DEFAULT,source='Read-only historical 7.8 rates; exact Task 7.20 canonical ledgers',
        pricing_note='2026-10-28 official-page review did not establish complete same-region bundles. Historical USD-normalized rates are illustrative, not quotations. B2 current public starting rate differs; no silent price replacement.'))
    save('cost_formulas.json',dict(
        canonical='C = cumulative_blocks * (mean_R + extra_evidence)',primary='P = 1 GiB + C + 0.10 C index/pages + 0.15 C fragmentation (analytical split, not measured)',
        headroom='H = .20 P + 1.45 * monthly_R * 1.25 + 5 GiB; rollback/write workspace allowance; no WAL enabled or claimed measured',
        snapshots='S = retained_snapshot_count * P; reference daily refresh, retain one local full snapshot, no dedup credit',
        recovery='W = P, additional primary-sized restore/VACUUM working copy provisioned throughout each month; conservative simultaneous peak reserve',
        backups='K = retained_full_copies * .95 P; four uploads/month, retain four, all conservatively priced at current P; .95 compression assumption',
        local='L=P+H+S+W; extra disk=ceil(max(0,L/GiB-included_GiB)), 1 GiB illustrative increments, no assumed physical tier cap',
        bandwidth='in=1.38 monthly_R; peer_out=11.52 monthly_R (8 peers); backup_out=4 P; one bootstrap=1.2 C; reference serves 1 bootstrap/year and 1 backup restore/year as expected monthly fractions',
        total='compute + extra_disk * marginal_disk_rate + K/GiB * backup_rate + (peer_out+backup_out+bootstrap_out+restore_egress)/GiB * egress_rate',
        ingress='assumed uncharged; bytes retained; provider-specific ingress/allowances not quoted',
        cumulative='sum of each modeled monthly bill, 36 months; no discounts, taxes or inflation',
        limitations='No invoices, tier feasibility, IOPS/burst/restore throughput or separate dbstat measurements. 0 extra archive nodes means none required by this media-only one-node model, not free journal capacity. Snapshot frequency with unchanged retention changes write work, not full-copy capacity; CPU/IO cost unmeasured.'))
    save('historical_economics.json',dict(status='historical uncorrected: snapshot/headroom/workspace not fully billed',scenarios=historical))
    save('economic_scenarios.json',dict(scenarios=main_scenarios))
    save('sensitivity_scenarios.json',dict(one_at_a_time=sensitivities,best_reference_stress=ranges))
    with (OUT/'month36_costs.csv').open('w',newline='',encoding='utf-8') as handle:
        fields=['workload','blocks_per_day','profile','primary_gib','local_capacity_gib','backup_gib','monthly_usd','cumulative_3yr_usd','under100']
        writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader()
        for item in main_scenarios:
            m=item['month36'];writer.writerow(dict(workload=item['workload'],blocks_per_day=item['blocks_per_day'],profile=item['profile'],primary_gib=m['primary_database_bytes']/GIB,
                 local_capacity_gib=m['local_capacity_bytes']/GIB,backup_gib=m['backup_retained_bytes']/GIB,monthly_usd=m['cost_usd']['total'],cumulative_3yr_usd=item['three_year_cumulative_usd'],under100=item['under100']))
    print(len(main_scenarios),'complete scenarios;',len(sensitivities),'one-axis sensitivities;',len(ranges),'best/reference/stress cases.')


if __name__=='__main__':
    main()
