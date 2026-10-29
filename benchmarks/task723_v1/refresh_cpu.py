"""Refresh observational CPU only; verify sizes/hashes, preserve all byte data."""
import hashlib
import json
import statistics
from run import HERE, corpus, native, cpu_times, dist, save


def main():
    samples={s['id']:s for s in corpus.build()}
    assert corpus.manifest(list(samples.values()))==json.loads((HERE/'manifest.json').read_bytes())
    data=json.loads((HERE/'codecs.json').read_bytes())
    for p in data['profiles']:
        enc,dec,_=native._operations(p)
        for r in [r for r in data['rows'] if r['candidate']==p['id']]:
            raw=samples[r['id']]['raw'];encoded=enc(raw)
            assert hashlib.sha256(encoded).hexdigest()==r['encoded_sha256'] and dec(encoded)==raw
            r['encode_cpu_ns'],ei=cpu_times(enc,raw,r['encode_wall_ns'])
            r['decode_cpu_ns'],di=cpu_times(dec,encoded,r['decode_wall_ns'])
            r['cpu_batch_iterations']=dict(encode=ei,decode=di)
        rows=[r for r in data['rows'] if r['candidate']==p['id']]
        for k in ('encode_cpu_ns','decode_cpu_ns'):
            data['aggregates'][p['id']][k]=dist([statistics.median(r[k]) for r in rows])
        print('Batched CPU',p['id'],'done',flush=True)
    data['clock']='perf_counter_ns wall; process_time_ns CPU, amortized ~20ms batches including loop/call overhead; capped at 200000 iterations'
    save(HERE,'codecs.json',data)


if __name__=='__main__':main()
