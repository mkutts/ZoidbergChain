"""Local repeated verification timings; no network throughput extrapolation."""
import json
import platform
from statistics import median
from time import perf_counter_ns

from verification.review717r import wire as w
from .fixtures import ROOT, load, pins, transcript
from .verify import verify_user, user_bindings, verify_proof, verify_clock, record


def main():
    d=load();p=pins(d);units=transcript(d)
    rows={r['name']:r for r in d['records']}
    vote=rows['vote-0-0']['object'];raw=bytes.fromhex(rows['vote-0-0']['hex'])
    binding=user_bindings('VOTE',vote)
    h,events=w.parse_body(units[2]['batch'])
    op=rows['open']['object']
    malformed=bytes.fromhex('00'*65)
    wrong=dict(vote,signature=rows['vote-1-1']['object']['signature'])
    wrong_raw=w.pack('VOTE',wrong)
    malformed_raw=raw[:-65]+malformed
    def rejected(f):
        try: f()
        except ValueError: return
        raise AssertionError('negative control accepted')
    def quorum():
        verify_proof(p,units[2]['proof'],batch_bytes=units[2]['batch'],height=3,parent=h['parent'],round=0)
    def mixed():
        # Verify a full actual laboratory batch: 10 votes +5 PARTICIPATION,
        # three time samples, four proposal/precommit signatures. Control
        # records are authenticated by the batch/proof, not separately signed.
        hh,ee=w.parse_body(units[2]['batch']);w.preflight_work(ee)
        for kind,obj in ee:
            if kind=='ADMISSION':
                v=obj['vote'];verify_user(p,'VOTE',w.pack('VOTE',v),expected=user_bindings('VOTE',v))
        verify_clock(p,hh);quorum()
    def bench(fn,n):
        fn()  # warm-up, excluded
        values=[]
        for _ in range(n):
            start=perf_counter_ns();fn();values.append((perf_counter_ns()-start)/1e6)
        ordered=sorted(values)
        return dict(samples=n,median_ms=median(values),p95_ms=ordered[min(n-1,(95*n+99)//100-1)],
                    min_ms=min(values),max_ms=max(values),samples_ms=values)
    cases={
        'user_vote':(lambda:verify_user(p,'VOTE',raw,expected=binding),30),
        'user_open':(lambda:verify_user(p,'OPEN',w.pack('OPEN',op),expected=user_bindings('OPEN',op)),20),
        'quorum_proof_with_body':(quorum,15),
        'mixed_batch_10_votes_5_controls_3_time_4_consensus':(mixed,10),
        'wrong_signature':(lambda:rejected(lambda:verify_user(p,'VOTE',wrong_raw,expected=binding)),30),
        'malformed_signature':(lambda:rejected(lambda:verify_user(p,'VOTE',malformed_raw,expected=binding)),30),
        'oversized_signed_object':(lambda:rejected(lambda:record('VOTE',b'x'*(w.CAP+1))),30)}
    result=dict(classification='TEST ONLY; local warm timings; no public-network throughput claim',
        environment=dict(python=platform.python_version(),platform=platform.platform(),processor=platform.processor()),
        timings={k:bench(fn,n) for k,(fn,n) in cases.items()},
        sizes=dict(vote=len(raw),open=len(w.pack('OPEN',op)),message=383,time_sample=74,pv=1150,proof=1533,
                   checkpoint=275,media_binding=862,header=544,
                   transcript_batches=[len(u['batch']) for u in units],mixed_batch=len(units[2]['batch']),
                   batch_limit=262144,media_block_limit=3145728,max_batch_plus_proof=263677),
        crypto_checks=dict(mixed_batch=dict(user=10,time=3,consensus=4,total=17),quorum=4),
        boundaries=dict(production_limits_adopted=False,physical_time_trusted=False,
                        complete_finalized_history=False,agreement_execution=False))
    (ROOT/'verification/review717s/resource-results.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps(dict(sizes=result['sizes'],medians_ms={k:v['median_ms'] for k,v in result['timings'].items()})))


if __name__=='__main__': main()
