"""Exact R717 accounting plus reproducible same-boundary closure witnesses."""
from math import ceil
import json
from pathlib import Path

from . import model as m
from .vectors import example
from .wire import pack, frame, tagged
from verification.review717q.workload import economics


def resources(rate, *, active=True):
    votes=rate*1440
    sessions=ceil(votes/100)
    heights=17280 if active else 288
    # Arithmetic offered demand only. More heights would be required at 10k.
    sizes={k:len(pack(k,example(k,True))) for k in ('OPEN','START','CLOSE','ADMISSION',
          'PARTICIPATION','EPOCH','HEADER','PROOF','MEDIA')}
    height_bytes=12+sizes['HEADER']+sizes['PROOF']+64
    # Worst distinct-submission charge per signed dimension vote. Both dimensions
    # for one submission usually share a charge; no compression is assumed.
    vote_bytes=sizes['ADMISSION']+7+sizes['PARTICIPATION']+7+2*96
    session_bytes=sum(sizes[k]+7+96 for k in ('OPEN','START','CLOSE'))
    daily=dict(votes_and_charge_records=votes*vote_bytes, sessions=sessions*session_bytes,
               headers_proofs_height_index=heights*height_bytes,
               epochs=288*(sizes['EPOCH']+7+96))
    per_day=sum(daily.values())
    three=per_day*1095
    # Reuse Q's published historical 7.8 cost formula/input prices; same media
    # 1000/day baseline and eight-peer traffic proxy. This is NOT a new quote.
    return dict(rate=rate, classification='arithmetic offered demand; no throughput demonstration',
                active=active, vote_ceiling_per_minute=1152, sustainable_arithmetic=rate<1152,
                components_day=daily, logical_day=per_day, logical_three_year=three,
                four_validators=4*three, two_independent_archives=2*three,
                all_six_service_copies=6*three, physical_primary=three*1.25,
                backups_per_copy=three*1.25*3.8,
                restore_seconds_100Mbps=three*8/100000000,
                user_checks_per_second=rate/60,
                finality_and_clock_checks_per_second=heights*7/86400,
                media_binding=sizes['MEDIA']+7,
                historical_whole_node_economics=economics(per_day,heights))


def closure_witness(n=33):
    # Seed is an explicit already-finalized application snapshot, not a bootstrap.
    s=m.State(height=2,median=305,lower=304,epoch=1)
    for i in reversed(range(n)):
        sid=f'{i:064x}'
        sess=m.Session(sid,f'{i:032x}',f'{i+1:064x}','creator',1,0,'00'*32,
                       0,'11'*32,{'w':2},deadline=1506,started=2)
        sess.fold=tagged('empty-votes',bytes.fromhex(sid))
        s.sessions[sid]=sess
        s.expiry.append((1506,sid))
    s.expiry.sort()
    history=[(1,299),(2,304)]
    pages=[]
    while s.expiry:
        s,result=m.step(s,boundaries=history,readings=(max(1507,s.median+5),)*3)
        history.append(result['boundary'])
        raw=b''.join(frame('CLOSE',r) for r in result['closes'])
        pages.append(dict(height=s.height,sids=[r['sid'] for r in result['closes']],
                          rows=result['closes'],
                          frame_bytes=len(raw),hex=raw.hex(),sha256=__import__('hashlib').sha256(raw).hexdigest(),
                          freeze_heights=[r['freeze_height'] for r in result['closes']]))
    return dict(sessions=n,pages=pages,successful_heights=len(pages))


def main():
    result=dict(task='7.17R',authority='trusted finalized-prefix/authentication facts in application model',
                signing_performed=False,production_changed=False,
                parameters=dict(max_live=4096,open_per_batch=16,close_per_batch=16,
                                epsilon_seconds=1,window_seconds=1200,epoch_seconds=300,
                                vote_checks=96,control_signature_budget=64),
                closure=closure_witness(),
                closure_1000=dict(pages=ceil(1000/16),seconds_bound=None),
                closure_4096=dict(pages=ceil(4096/16),seconds_bound=None),
                resources=[resources(r) for r in (10,100,1000,10000)],idle=resources(0,active=False),
                blockers=['owner architecture/clock/policy approvals','trusted physical clock justification',
                          'G2 stream/policy registry amendment','new-domain crypto interoperability vectors',
                          'rights/technical/qualification/offense source policy semantics',
                          'complete combined media canonical hash/max-fit schema',
                          'independent two-stream BFT/signing refinement and custody',
                          'native-host availability/restore/throughput and operating budget'])
    Path(__file__).with_name('results.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps(dict(closure_pages=result['closure']['successful_heights'],
                         resources=[dict(rate=r['rate'],three_year=r['logical_three_year']) for r in result['resources']]),indent=2))


if __name__=='__main__':
    main()
