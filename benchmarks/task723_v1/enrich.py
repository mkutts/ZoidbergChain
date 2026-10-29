"""Measure actual complete records for every legal identity/Zstd trial.

Brotli size substitutions are explicitly hypothetical: frozen v3 rejects them.
Uses only generated originals and existing public fixture context, no databases.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
from run import ROOT, HERE, corpus, fixtures, native, block, media, canonical, save, IsolatedDecoder, Status


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=HERE);args=ap.parse_args()
    out=args.output.resolve()
    assert out==HERE or ROOT/'temp' in out.parents
    samples={s['id']:s for s in corpus.build()}
    assert corpus.manifest(list(samples.values()))==json.loads((out/'manifest.json').read_bytes())
    codecs=json.loads((out/'codecs.json').read_bytes())
    records=json.loads((out/'records.json').read_bytes())
    measured={r['id']:r for r in records['rows']+records['diagnostic_controls']}
    profiles={p['id']:p for p in codecs['profiles']}
    with IsolatedDecoder() as worker:
        for sid,sample in samples.items():
            baseline=measured[sid]
            if baseline['record_bytes'] is None:
                for trial in [r for r in codecs['rows'] if r['id']==sid]:
                    trial.update(serialized_media_member_bytes=trial['descriptor_bytes']+8,
                        complete_record_bytes=None,complete_record_status='Unavailable: original exceeds frozen original ceiling; native lossless trial only')
                continue
            idx=list(samples).index(sid)+1
            raw=fixtures.corpus_record(sample['raw'],sample['mime'],sid,idx,fixtures.CTX.genesis_hash,worker)
            assert hashlib.sha256(raw).hexdigest()==baseline['record_sha256']
            payload=json.loads(raw)['envelope']['payload']
            for trial in [r for r in codecs['rows'] if r['id']==sid]:
                trial['serialized_media_member_bytes']=trial['descriptor_bytes']+8
                trial['complete_record_bytes']=len(raw)+trial['descriptor_bytes']-baseline['descriptor_bytes']
                profile=profiles[trial['candidate']]
                if profile['codec']=='brotli':
                    trial['complete_record_status']='Hypothetical byte-length substitution ONLY; schema rejects Brotli'
                    continue
                if trial['encoded_bytes']>media.MAX_ENCODED:
                    trial['complete_record_status']='Hypothetical size ONLY; encoded bytes exceed frozen limit'
                    continue
                encoded=native._operations(profile)[0](sample['raw'])
                assert hashlib.sha256(encoded).hexdigest()==trial['encoded_sha256']
                p=deepcopy(payload)
                p['media']=media.descriptor(sample['raw'],encoded,sample['mime'],profile['codec'])
                encoded_record=block.encode_record(p,fixtures.CTX)
                assert len(encoded_record)==trial['complete_record_bytes']
                start=time.perf_counter_ns()
                recovered=block.reconstruct_record_media(encoded_record,fixtures.CTX,decoder=worker)
                trial['strict_verification_wall_ns']=time.perf_counter_ns()-start
                if recovered.status==Status.INDETERMINATE_LOCAL_FAILURE:
                    raise RuntimeError(f'Unresolved local worker failure: {sid} {profile}: {recovered.reason}')
                trial['strict_status']=recovered.status.value
                trial['strict_stage']=recovered.stage
                trial['strict_code']=recovered.code
                trial['strict_exact_original']=recovered.original==sample['raw']
                if recovered.status==Status.VALID:
                    assert recovered.original==sample['raw']
                trial['strict_worker_metrics']=recovered.metrics
                trial['complete_record_sha256']=hashlib.sha256(encoded_record).hexdigest()
                trial['complete_record_status']=('Actual encoded record, parsed signatures and strict exact-byte reconstruction VALID'
                    if recovered.status==Status.VALID else 'Actual serialized record; strict decoder INVALID; native lossless trial is not an accepted canonical encoding')
            print('Full profiles verified',sid,flush=True)
    save(out,'codecs.json',codecs)


if __name__=='__main__':
    main()
