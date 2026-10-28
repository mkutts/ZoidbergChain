"""Independent P reconstruction and conditional Q resource arithmetic.

Decimal bytes, 365-day years. No network, clock, pricing lookup or benchmark.
"""
from math import ceil
import json
from pathlib import Path

from .capacity import INPUT as I, ledger

ROOT = Path(__file__).resolve().parents[2]


def reproduce_p(rate):
    # Intentionally does not call P.calculate. Its daily event comma convention
    # and 5120/tick are accounting allowances, not an actual serialized batch.
    daily = rate*1440
    parts = dict(payload=daily*1507, signature_text=daily*132,
                 signed_wrapper_other=daily*62, event_and_separator=daily*43,
                 header=17280*1024, certificate=17280*4096)
    return dict(rate=rate, votes_day=daily, daily=parts, daily_total=sum(parts.values()),
                annual=sum(parts.values())*365, three_year=sum(parts.values())*1095,
                excluded=['OPEN/CLOSE/evidence originals', 'indexes', 'backups', 'physical amplification'])


def slots(kind, event):
    n = (I['batch_bytes']-I['header_bytes']-I['close_frame_budget']*16)//(event+4)
    return min(n, 24) if kind == 'fixed24' else min(n, I['cpu_vote_budget']) if kind == 'byte_cpu' else n


def archive(rate, *, cadence, policy, signed=1701, event=1743, slots_per_height=96):
    """Steady offered demand; not achievable if the associated service is unstable.

    100 signed dimension votes/session, 2048B OPEN & CLOSE, 512B epoch event.
    Counts use daily worst rounding. Media anchors/evidence originals additional.
    """
    votes = rate*1440
    sessions = ceil(votes/I['votes_per_session'])
    epoch_events = ceil(86400/I['epoch_checkpoint_seconds'])
    control = sessions*(I['open_framed_bytes']+I['close_framed_bytes'])+epoch_events*I['epoch_framed_bytes']
    # Explicit scenario: OPENs in <=16-session cohorts; common window/deadline
    # grid; votes and bounded controls co-packed in separate byte reservations.
    # Two extra heights/cohort for START/CLOSE, checkpoints kept disjoint.
    # Arbitrarily staggered sessions/partition closure backlog cost more.
    vote_heights = ceil(votes/slots_per_height)
    control_heights = ceil(control/32768)
    sparse = max(vote_heights, control_heights)+epoch_events+2*ceil(sessions/16)
    active = ceil(86400/cadence)
    heights = active if policy == 'continuous' else sparse if policy == 'event' else epoch_events if policy == 'periodic_only' and rate == 0 else max(active, sparse) if rate else epoch_events
    # Hybrid: nominal five-second service ticks while any session active;
    # zero active sessions uses only epoch checkpoints. sparse is a conservative
    # packing/transition count, never exceeding active ticks for stable low loads.
    parts = dict(payload=votes*(signed-194), user_signature_text=votes*132,
                 signed_wrapper_other=votes*62, event_wrapper=votes*(event-signed),
                 framing=votes*4, open_close=sessions*4096,
                 epoch_events=epoch_events*512, headers=heights*1024,
                 certificate_signatures=heights*528,
                 certificate_other=heights*(4096-528),
                 clock_signatures=heights*396,
                 clock_certificate_other=heights*(I['clock_certificate_bytes']-396),
                 indexes=(votes+2*sessions+epoch_events)*96+heights*64)
    total = sum(parts.values())
    return dict(rate=rate, policy=policy, signed_bytes=signed, votes_day=votes,
                sessions_day=sessions, heights_day=heights,
                required_scenario_heights_day=sparse,
                idle_height_upper_bound=max(0, heights-vote_heights-control_heights),
                daily_parts=parts, daily_bytes=total, annual_bytes=total*365,
                three_year_bytes=total*1095, certificate_max_extra_three_year=heights*12288*1095,
                four_validator_logical_bytes=total*1095*4,
                two_extra_archive_logical_bytes=total*1095*2,
                backup_factor=3.8, primary_amplification=1.25,
                primary_three_year_bytes=total*1095*1.25,
                backup_three_year_bytes=total*1095*1.25*3.8)


def economics(daily, heights):
    """Whole-node example: Q journal + independent 1000 representative media/day.

    Reuses versioned 7.8 INPUT assumptions, independently sums monthly charges.
    Same compute charge once; eight peers; full backup upload four times/month.
    Snapshot/headroom bytes are provisioning needs, not priced twice.
    """
    cfg = json.loads((ROOT/'benchmarks/milestone_7_task_7_8_config.json').read_text())
    result = {}
    for name, p in cfg['profiles'].items():
        days, cumulative, last = 0, 0, None
        for m in range(36):
            d = cfg['month_days'][m%12]
            days += d
            logical = (daily+1000*211172)*days
            primary = (1024**3+logical*1.25)/1024**3
            backups = primary*3.8
            # Phase bytes are transport only, not an extra archive copy.
            outgoing = ((daily+211172000)*d*8*1.44 + heights*d*24576*3)/1024**3
            backup_transfer = primary*4
            cost = (p['monthly_compute']+max(0, primary-p['included_primary_gib'])*p['primary_gib_month']
                    +backups*p['backup_gib_month']+(outgoing+backup_transfer)*p['egress_gib'])
            cumulative += cost
            last = cost
        result[name] = dict(three_year_usd=cumulative, month36_usd=last,
                            primary_gib=primary, backup_gib=backups,
                            local_snapshot_gib=primary, vacuum_working_gib=primary)
    return result


def workload(rate, *, kind, event, cadence, policy):
    n = slots(kind, event)
    # Control rate: one OPEN and CLOSE/100 signed votes; 512B/300s epochs.
    # Max simultaneous close reserve always excluded from vote lane.
    # Additional optional control must fit elsewhere/defer; this is a vote-lane
    # ceiling, with closed-shape and byte-work limits still applied to every batch.
    cap = n*60/cadence
    spare = cap-rate
    a = archive(rate, cadence=cadence, policy=policy, event=event,
                signed=4096 if event == 8192 else event-42, slots_per_height=n)
    required = ceil(rate*60/n)
    checks = rate/60 + a['heights_day']/86400*(4+3) + a['sessions_day']/86400*2
    phase_per_second = a['heights_day']*24576/86400
    bytes_second = a['daily_bytes']/86400
    return dict(rate=rate, kind=kind, event_bytes=event, cadence=cadence, policy=policy,
                maximum_votes_batch=n, maximum_heights_hour=3600/cadence,
                full_vote_lane_bytes=33792+n*(event+4),
                sustainable_vote_lane_ceiling_minute=cap, stable_vote_lane=rate<cap,
                scenario_fits_height_budget=rate<cap and a['required_scenario_heights_day']<=86400/cadence,
                required_full_vote_heights_hour=required,
                signature_checks_second=checks,
                vote_signature_checks_second=rate/60,
                single_core_percent_at_ms={str(ms): checks*ms/10 for ms in I['signature_ms_sensitivity']},
                ingress_bytes_second=bytes_second*1.38+phase_per_second*3,
                egress_bytes_second=bytes_second*8*1.44+phase_per_second*3,
                backlog_growth_votes_hour=max(0, rate-cap)*60,
                outage_backlog=rate*360,
                outage_clear_minutes=rate*360/spare if spare>0 else None,
                burst_clear_minutes=10000/spare if spare>0 else None,
                nominal_P_window_vote_ceiling=255*n,
                nominal_next_height_interval_seconds=cadence,
                actual_close_delay_bound=None,
                archive=a, economics=economics(a['daily_bytes'], a['heights_day']),
                evidence='arithmetic only; no demonstrated BFT throughput; unstable rows are offered demand')


def queue_trace(arrivals, *, service=96, stalls=(), expiry=None):
    """Discrete FIFO probe. Malformed counts use a separate bounded ingress lane.

    Expiry is close-first: remaining and newly arrived votes are late at K.
    No local queue receipt can backdate their admission.
    """
    queued = admitted = late = 0
    trace = []
    for h, count in enumerate(arrivals, 1):
        queued += count
        if expiry is not None and h >= expiry and h not in stalls:
            late += queued
            queued = 0
        served = min(service, queued) if h not in stalls else 0
        queued -= served
        admitted += served
        trace.append(dict(height=h, queued=queued, admitted=admitted, late=late))
    return trace


def report():
    return dict(task='7.17Q', assumptions=I, ledger=ledger(),
                p_reproduced=[reproduce_p(r) for r in I['rates']],
                idle=[archive(0, cadence=5, policy=p) for p in ('continuous', 'event', 'hybrid', 'periodic_only')],
                stress=dict(burst=queue_trace([10000]+[0]*110),
                            stall=queue_trace([96]*10+[0]*10, stalls={1, 2, 3}),
                            boundary=queue_trace([10000]+[0]*9, expiry=4)),
                workloads=[workload(r, kind=k, event=e, cadence=c, policy=p)
                           for r in I['rates'] for k in ('fixed24', 'byte', 'byte_cpu')
                           for e in (1743, 1781, 8192) for c in (1, 5, 10)
                           for p in ('continuous', 'event', 'hybrid')
                           if c == 5 or (k == 'byte_cpu' and e == 1743)])


if __name__ == '__main__':
    output = Path(__file__).with_name('results.json')
    output.write_text(json.dumps(report(), sort_keys=True, indent=2)+'\n', encoding='utf-8')
    print('wrote isolated Q results:', output)
