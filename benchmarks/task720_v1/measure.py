"""Task 7.20 offline acceptance measurement, no active integration or database I/O.

Newly authored corpus/source artifacts: CC0-1.0. Run with the repository venv.
All frozen evidence is read-only. Outputs default to this versioned directory;
use --output DIR for a fresh reproduction. Timing is observational, sizes exact.
"""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import corpus as profile
from canonical_v3 import block, evidence, media, transactions
from canonical_v3.primitives import canonical, digest, EDGE_SPACE, V3Error, MAX_RECORD, rational, envelope
from codec_prototype.isolated_decoder import IsolatedDecoder, Status, Limits
from scripts import milestone_7_task_7_3_corpus as historical
from scripts import milestone_7_task_7_4_benchmark as codecs
from scripts import milestone_7_task_7_7_block_composition as composition
from scripts import milestone_7_task_7_11_storage as fixtures
from media_technical_validation import validate_media_bytes, TechnicalMediaValidationError
from media_admission_policy import media_admission_policy
from PIL import Image


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(out, name, value):
    (out/name).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n',encoding='utf-8')


def percent(values, p):
    ordered = sorted(values)
    return ordered[(len(ordered)*p+99)//100-1]


def distribution(values, worst='max'):
    return dict(p50=percent(values,50),p95=percent(values,95),worst=(max if worst=='max' else min)(values),
                equal_record_mean=statistics.mean(values))


def ledger(value, path='$'):
    """Disjoint JSON byte charges at every field, with no signature double count.

    Each object owns braces/commas and its keys/colons. Every child owns its
    value only. Arrays own brackets/commas. Payload string content is media;
    its quotes are overhead. JSON escaped vote messages are charged as strings.
    """
    if isinstance(value,dict):
        rows = {path+'/@structure':2+max(0,len(value)-1)}
        for key, child in sorted(value.items()):
            rows[path+'/'+key+'/@key'] = len(canonical(key))+1
            rows.update(ledger(child,path+'/'+key))
        return rows
    if isinstance(value,list):
        rows = {path+'/@structure':2+max(0,len(value)-1)}
        for index,child in enumerate(value):
            rows.update(ledger(child,path+'/'+str(index)))
        return rows
    if path == '$/envelope/payload/media/payload':
        return {path+'/@content':len(value),path+'/@quotes':2}
    return {path:len(canonical(value))}


def admission(sample):
    try:
        result = validate_media_bytes(sample['raw'],declared_mime_type=sample['mime'])
        return dict(status='accepted',reasons=result.result['reason_codes'],
                    exact_input=result.raw_media_bytes==sample['raw'],detected_mime=result.result['detected_mime_type'])
    except TechnicalMediaValidationError as exc:
        return dict(status='rejected',reasons=exc.result['reason_codes'])


def codec_rows(samples, config):
    rows=[]
    for candidate in config['candidates']:
        encode,decode,_ = codecs._operations(candidate)
        for sample in samples:
            original=sample['raw']
            encoded,enc_times=codecs._timed(encode,original,9,2)
            restored,dec_times=codecs._timed(decode,encoded,9,2)
            assert restored==original and sha(restored)==sha(original)
            # Brotli/zlib are comparison candidates, never valid v3 codec IDs.
            descriptor=codecs._descriptor_size(encoded,{'bytes':original,'mime_type':sample['mime']},candidate['codec'])
            identity=codecs._descriptor_size(original,{'bytes':original,'mime_type':sample['mime']},'identity')
            rows.append(dict(id=sample['id'],category=sample['category'],mime=sample['mime'],candidate=candidate['id'],
                original_bytes=len(original),encoded_bytes=len(encoded),descriptor_bytes=descriptor,
                identity_descriptor_bytes=identity,savings_percent=100*(1-len(encoded)/len(original)),
                descriptor_savings_percent=100*(1-descriptor/identity),expands=len(encoded)>len(original),
                descriptor_expands=descriptor>identity,encode_ns=enc_times,decode_ns=dec_times,
                encode_ns_median=statistics.median(enc_times),decode_ns_median=statistics.median(dec_times),
                exact_roundtrip=True,original_sha256=sha(original),encoded_sha256=sha(encoded)))
        print('Codec completed:',candidate['id'],flush=True)
    groups={}
    for candidate in config['candidates']:
        groups[candidate['id']]={}
        for category in sorted({s['category'] for s in samples}):
            selected=[r for r in rows if r['candidate']==candidate['id'] and r['category']==category]
            groups[candidate['id']][category]=dict(objects=len(selected),
                original_bytes=sum(r['original_bytes'] for r in selected),encoded_bytes=sum(r['encoded_bytes'] for r in selected),
                byte_weighted_savings_percent=100*(1-sum(r['encoded_bytes'] for r in selected)/sum(r['original_bytes'] for r in selected)),
                raw_expansions=sum(r['expands'] for r in selected),descriptor_expansions=sum(r['descriptor_expands'] for r in selected),
                distributions={field:distribution([r[field] for r in selected], 'min' if 'savings' in field else 'max') for field in
                   ('savings_percent','descriptor_savings_percent','original_bytes','encoded_bytes','descriptor_bytes','encode_ns_median','decode_ns_median')})
    return dict(profiles=config['candidates'],timing=dict(warmups=2,repetitions=9,clock='perf_counter_ns',
        note='in-process native codec only, imports and fixture generation excluded; strict worker separately measured'),rows=rows,aggregates=groups)


def record_row(sample, raw, population, worker):
    rec=block.parse_record(raw,fixtures.CTX)
    p=rec['envelope']['payload']; desc=p['media']
    original=sample['raw']
    accepted=original.decode().replace('\r\n','\n').replace('\r','\n').strip(EDGE_SPACE).encode() if sample['mime']=='text/plain' else original
    outcome=block.reconstruct_record_media(raw,fixtures.CTX,decoder=worker)
    assert outcome.status==Status.VALID and outcome.original==accepted
    assert sha(accepted)==desc['original_sha256'] and desc['mime_type']==sample['mime']
    assert len(accepted)==desc['original_size']
    identity=media.descriptor(accepted,accepted,sample['mime'],'identity')
    identity_payload=deepcopy(p); identity_payload['media']=identity
    identity_record=block.encode_record(identity_payload,fixtures.CTX)
    assert len(raw)<=len(identity_record)
    field_bytes=ledger(rec)
    assert sum(field_bytes.values())==len(raw)
    assert field_bytes['$/envelope/payload/media/payload/@content']==len(desc['payload'])
    parts=composition.component_accounting(canonical(rec['envelope']),'media')
    partition={k:parts[k] for k in ('serialized_media_representation_bytes','certificate_bytes','transaction_record_bytes',
        'header_bytes','remaining_structural_metadata_bytes','envelope_bytes','delimiter_bytes')}
    partition['portable_wrapper_bytes']=len(raw)-len(canonical(rec['envelope']))
    assert sum(partition.values())==len(raw)
    metadata=len(raw)-len(desc['payload'])
    signatures=sum(v for k,v in field_bytes.items() if k.endswith(('/signature','/vote_signature')))
    return dict(id=sample['id'],population=population,category=sample['category'],mime=sample['mime'],
        source_bytes=len(original),original_bytes=len(accepted),source_sha256=sha(original),original_sha256=sha(accepted),
        encoded_bytes=desc['stored_size'],base64_media_bytes=len(desc['payload']),record_bytes=len(raw),nonmedia_bytes=metadata,
        metadata_percent=100*metadata/len(raw),metadata_over_original_percent=100*metadata/len(accepted),
        binary_nonmedia_percent=100*(len(raw)-desc['stored_size'])/len(raw),
        base64_expansion_bytes=len(desc['payload'])-desc['stored_size'],
        codec=desc['codec_id'],descriptor_bytes=len(canonical(desc)),identity_descriptor_bytes=len(canonical(identity)),
        identity_record_bytes=len(identity_record),exact_roundtrip=True,record_sha256=sha(raw),canonical_hash=rec['hash'],
        field_ledger=field_bytes,partition=partition,certificate_value_bytes=len(canonical(p['admission_certificate'])),
        reviewer_vote_value_bytes=len(canonical(p['admission_certificate']['votes'])),native_value_bytes=len(canonical(p['native_transactions'])),
        signature_token_bytes_subset=signatures,votes=len(p['admission_certificate']['votes']),worker_metrics=outcome.metrics)


def record_stats(rows):
    if not rows:
        return None
    total_original=sum(r['original_bytes'] for r in rows)
    total_record=sum(r['record_bytes'] for r in rows)
    return dict(objects=len(rows),metadata_percent=distribution([r['metadata_percent'] for r in rows]),
        metadata_over_original_percent=distribution([r['metadata_over_original_percent'] for r in rows]),
        canonical_byte_weighted_metadata_percent=100*sum(r['nonmedia_bytes'] for r in rows)/total_record,
        original_byte_weighted_mean_metadata_percent=sum(r['original_bytes']*r['metadata_percent'] for r in rows)/total_original,
        metadata_bytes_over_original_bytes_percent=100*sum(r['nonmedia_bytes'] for r in rows)/total_original,
        below_15_percent=sum(r['metadata_percent']<15 for r in rows),
        totals={k:sum(r[k] for r in rows) for k in ('source_bytes','original_bytes','encoded_bytes','base64_media_bytes','record_bytes','nonmedia_bytes')},
        partition={k:sum(r['partition'][k] for r in rows) for k in rows[0]['partition']})


def aggregate_records(rows):
    groups={'all':rows}
    for mime in media.MIMES:
        groups['mime:'+mime]=[r for r in rows if r['mime']==mime]
    for label,low,high in [('tiny',1,1023),('small',1024,16383),('medium',16384,262143),('large',262144,2097152)]:
        groups['band:'+label]=[r for r in rows if low<=r['original_bytes']<=high]
        for mime in media.MIMES:
            groups['mime_band:'+mime+':'+label]=[r for r in rows if r['mime']==mime and low<=r['original_bytes']<=high]
    return {name:record_stats(group) for name,group in groups.items() if group}


def modified_record(raw, mode):
    """Valid crypto fixtures using existing public test keys; no accepted history."""
    p=deepcopy(json.loads(raw)['envelope']['payload']); c=p['admission_certificate']
    if mode=='ten-votes':
        c['votes']=[v for d in evidence.POSITIVE for v in sorted(
            [v for v in c['votes'] if v['dimension']==d and v['vote_type']==evidence.POSITIVE[d]],
            key=lambda v:(v['reviewer_status']!='ESTABLISHED_REVIEWER',v['voter_wallet_address']))[:5]]
    elif mode=='long-metadata':
        a=c['attestation']; a['canonical_payload']['nonce']='n'*256; a['nonce']='n'*256
        msg=canonical(envelope(a['canonical_payload'],'submitter-attestation',fixtures.CTX))
        a.update(canonical_message=msg.decode(),canonical_message_hash=sha(msg),canonical_payload_digest=sha(msg),
                 signature=fixtures.sign(msg,c['creator_wallet']))
        for v in c['votes']:
            v['vote_nonce']='v'*256
            msg=canonical(evidence.vote_payload(v,fixtures.CTX))
            v.update(vote_message=msg.decode(),signed_message_hash=sha(msg),vote_signature=fixtures.sign(msg,v['voter_wallet_address']))
            v['vote_identity']=digest(dict(payload=evidence.vote_payload(v,fixtures.CTX),signature=v['vote_signature']))
        if p['content_type']!='text':
            p['meme_text']='Review observation: '+('📎'*980)
        golden=json.loads((fixtures.FIXTURES/'native.json').read_bytes())
        transfers=[]
        for i in range(1,11):
            transfer=deepcopy(golden); transfer.update(nonce=str(i),memo='Audit receipt '+str(i)+' '+('📎'*260))
            msg=transactions.signing_bytes({k:transfer[k] for k in transactions.PAYLOAD_FIELDS},fixtures.CTX)
            transfer.update(signed_message=msg.decode(),signed_message_hash=sha(msg),tx_id=sha(msg),
                            signature=fixtures.sign(msg,transfer['from_address']))
            transfers.append(transfer)
        p['native_transactions']=transfers
        p['transactions_hash']=transactions.aggregate_hash(transfers,fixtures.CTX)
    c['votes'].sort(key=lambda v:(v['dimension'],v['voter_wallet_address'],v['vote_identity']))
    for d in evidence.POSITIVE:
        c[d]=evidence.derive_tally(c['votes'],d,fixtures.CTX)
    c['certificate_digest']=digest({k:v for k,v in c.items() if k!='certificate_digest'})
    tally=c['originality']; score=rational(tally['positive_votes'],tally['approval_denominator'])
    p.update(certificate_id=c['certificate_digest'],vote_hash=tally['vote_set_digest'],approval_percentage=score,
             originality_score=score,decisive_vote_total=tally['approval_denominator'])
    return block.encode_record(p,fixtures.CTX)


def boundaries(worker):
    checks=[]
    original=b'Accept exact bytes.'
    identity=media.descriptor(original,original,'text/plain','identity')
    encoded=media._compress_default(original)
    alternate=media.descriptor(original,encoded,'text/plain','zstd')
    assert len(canonical(alternate))>len(canonical(identity))
    assert media.produce(original,'text/plain',decoder=worker).descriptor['codec_id']=='identity'
    assert media.reconstruct(alternate,decoder=worker).original==original
    p=deepcopy(json.loads(fixtures.corpus_record(original,'text/plain','alternate',1,fixtures.CTX.genesis_hash,worker))['envelope']['payload'])
    identity_raw=block.encode_record(p,fixtures.CTX)
    p['media']=alternate; larger=block.encode_record(p,fixtures.CTX)
    assert len(larger)>len(identity_raw) and block.reconstruct_record_media(larger,fixtures.CTX,decoder=worker).original==original
    checks.append(dict(case='framing_expansion_external_alternate',identity_descriptor=len(canonical(identity)),
        larger_descriptor=len(canonical(alternate)),identity_record=len(identity_raw),larger_record=len(larger),
        producer='identity',validator='VALID',same_original_sha256=True))
    for label,change in [('unknown-codec',dict(codec_id='brotli')),('bool-version',dict(codec_version=True)),
                         ('wrong-hash',dict(original_sha256='0'*64)),('oversized-encoded',dict(stored_size=media.MAX_ENCODED+1)),
                         ('oversized-text',dict(original_size=media.MAX_TEXT+1)),('wrong-mime',dict(mime_type='video/mp4'))]:
        bad=dict(alternate,**change); result=media.reconstruct(bad,decoder=worker)
        assert result.status==Status.INVALID
        checks.append(dict(case=label,status=result.status.value,stage=result.stage,code=result.code))
    import base64
    corrupt=bytearray(encoded); corrupt[-1]^=1
    result=media.reconstruct(dict(alternate,payload=base64.b64encode(corrupt).decode()),decoder=worker)
    assert result.status==Status.INVALID
    checks.append(dict(case='corrupt-checksum',status=result.status.value,stage=result.stage,code=result.code))
    for mime,cap in [('text/plain',media.MAX_TEXT),('image/png',media.MAX_IMAGE)]:
        raw=b'a'*cap
        desc=media.descriptor(raw,raw,mime,'identity')
        outcome=media.reconstruct(desc,decoder=worker)
        assert outcome.status==Status.VALID and outcome.original==raw
        try:
            media.produce(raw+b'a',mime,decoder=worker)
        except V3Error as exc:
            assert exc.code=='original_size'
        else:
            raise AssertionError('oversize accepted')
        checks.append(dict(case='exact-original-and-encoded-cap-'+mime,original=cap,stored=cap,
            status=outcome.status.value,note='descriptor/codec gate; a bytes is not an image container'))
    for n in (MAX_RECORD-1,MAX_RECORD):
        block.check_complete_size(b' '*n)
    try:
        block.check_complete_size(b' '*(MAX_RECORD+1))
    except V3Error as exc:
        assert exc.code=='block_size'
    else:
        raise AssertionError('oversize complete block accepted')
    checks.append(dict(case='complete-record-byte-gate',cap=MAX_RECORD,conservative_schema_bound=block.conservative_size_bound(),
        note='at-cap spaces pass byte gate only and are not valid records; actual valid records have tighter schema bounds'))
    return checks


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=profile.HERE)
    args=parser.parse_args(); out=args.output.resolve(); out.mkdir(parents=True,exist_ok=True)
    scratch=ROOT/'temp'/'task720-workers'; scratch.mkdir(parents=True,exist_ok=True)
    os.environ.update(TEMP=str(scratch),TMP=str(scratch),PYTHONDONTWRITEBYTECODE='1')
    samples=profile.build(); manifest=profile.manifest(samples)
    frozen_path=profile.HERE/'manifest.json'
    if frozen_path.exists():
        assert manifest==json.loads(frozen_path.read_bytes()), 'corpus source/encoder/identity drift'
    save(out,'manifest.json',manifest)
    print('Generated production-like corpus:',len(samples),sum(len(s['raw']) for s in samples),flush=True)
    config=json.loads((ROOT/'tests/fixtures/milestone_7_benchmark_v1_config.json').read_bytes())
    codec_result=codec_rows(samples,config); save(out,'codecs.json',codec_result)
    frozen=json.loads(historical.MANIFEST_PATH.read_bytes()); historical.verify_manifest(frozen)
    old=historical.build_samples()
    history=[dict(id=s['id'],mime=s['mime_type'],category=s['category'],raw=s['bytes'],origin=s['description'],seed=s['seed']) for s in old]
    audit=[]
    historical_codecs=json.loads((ROOT/'benchmarks/milestone_7_task_7_4_results.json').read_bytes())
    for s,expected in zip(history,frozen['samples'],strict=True):
        assert sha(s['raw'])==expected['sha256'] and len(s['raw'])==expected['original_byte_size']
        z=next(r for r in historical_codecs['per_sample'] if r['sample_id']==s['id'] and r['candidate_id']=='zstd-3')
        audit.append(dict(id=s['id'],mime=s['mime'],category=s['category'],original_bytes=len(s['raw']),sha256=sha(s['raw']),
            origin='Repository-authored synthetic; '+s['origin'],seed=s['seed'],equal_record_weight=1/36,
            original_byte_weight=len(s['raw'])/sum(len(t['raw']) for t in history),zstd_encoded_bytes=z['encoded_bytes'],
            historical_scoring=expected['benchmark_scoring'],historical_admission=expected['current_validator_status']))
    save(out,'historical_audit.json',dict(rows=audit,tiny_under_1024=sum(r['original_bytes']<1024 for r in audit),
        under_16384=sum(r['original_bytes']<16384 for r in audit),origin='36 synthetic objects, no production population'))
    rows=[]; admissions=[]; sensitivities=[]
    with IsolatedDecoder() as worker:
        for population,members in [('historical',history),('production-like',samples)]:
            for index,s in enumerate(members,1):
                source=s['raw']
                accepted=source.decode().replace('\r\n','\n').replace('\r','\n').strip(EDGE_SPACE).encode() if s['mime']=='text/plain' else source
                # Source-byte and accepted-byte domains are both independently checked.
                strict=[]
                for codec,encoded in [('identity',source),('zstd',media._compress_default(source))]:
                    outcome=worker.validate(canonical(media.descriptor(source,encoded,s['mime'],codec)))
                    assert outcome.status!=Status.INDETERMINATE_LOCAL_FAILURE, outcome
                    if codec=='identity' or outcome.status==Status.VALID:
                        assert outcome.status==Status.VALID and outcome.original==source
                    # Native encoder output need not satisfy the narrower frozen
                    # profile. Keep rejected trials and test actual fallback.
                    strict.append(dict(codec=codec,status=outcome.status.value,stage=outcome.stage,code=outcome.code,
                        exact_source_bytes=outcome.original==source,worker_metrics=outcome.metrics))
                raw=fixtures.corpus_record(accepted,s['mime'],s['id'],index,fixtures.CTX.genesis_hash,worker)
                row=record_row(s,raw,population,worker); row['strict_source_roundtrips']=strict
                rows.append(row)
                if population=='production-like':
                    observed=admission(s); admissions.append(dict(id=s['id'],**observed))
                    # Current rejection is evidence, never exclusion from v3 corpus statistics.
                    if observed['status']=='accepted':
                        assert observed['exact_input'] and observed['detected_mime']==s['mime']
                    if s['id'] in ('narrative-tiny','narrative-medium','png-small','png-near-v3'):
                        for mode in ('ten-votes','long-metadata'):
                            modified=modified_record(raw,mode)
                            sensitivities.append(record_row(s,modified,mode,worker))
                print('Record verified:',population,s['id'],flush=True)
        boundary=boundaries(worker)
    save(out,'admission.json',dict(active_policy=media_admission_policy(),observations=admissions,
        proposed_v3=dict(mimes=media.MIMES,max_text=media.MAX_TEXT,max_image=media.MAX_IMAGE,max_encoded=media.MAX_ENCODED,
                         max_record=MAX_RECORD),
        note='Active observations use current technical validator; isolated records validate frozen format/crypto/codec only, not live admission/history.'))
    save(out,'records.json',dict(rows=rows,sensitivity_rows=sensitivities,boundaries=boundary))
    metrics={pop:aggregate_records([r for r in rows if r['population']==pop]) for pop in ('historical','production-like')}
    active_ids={r['id'] for r in admissions if r['status']=='accepted'}
    metrics['production-like-current-accepted']=aggregate_records([r for r in rows if r['population']=='production-like' and r['id'] in active_ids])
    metrics['production-like-images']=aggregate_records([r for r in rows if r['population']=='production-like' and r['mime']!='text/plain'])
    metrics['selected_codecs']={pop:dict(Counter(r['codec'] for r in rows if r['population']==pop)) for pop in ('historical','production-like')}
    metrics['sensitivity']=[{k:r[k] for k in ('id','population','votes','original_bytes','encoded_bytes','record_bytes','nonmedia_bytes',
        'metadata_percent','certificate_value_bytes','native_value_bytes')} for r in sensitivities]
    metrics['definitions']=dict(percentile='nearest rank: sorted[ceil(n*p/100)-1], equal weight per record',
        canonical_metadata='(record - base64 media content characters) / record; descriptor, quotes, all security evidence included',
        binary_nonmedia='(record - encoded media bytes) / record; base64 expansion included',
        weights='No observed production weights. Equal-record mean, canonical-byte weighted share and original-byte weighted mean are distinct.',
        excluded='External finality proofs, SQLite/index/filesystem bytes and unapproved future journal commitments are outside canonical record, not zero.',
        resources=dict(decoder_limits=Limits().__dict__,codec_native_peak_memory='not measured; no reliable native peak instrumentation',
                       codec_parent='trusted self-created inputs only; no hostile codec benchmark execution',profiles='existing 7.4 settings unchanged'))
    save(out,'metrics.json',metrics)
    print('Completed:',len(rows),'canonical records;',len(sensitivities),'sensitivity records;',len(codec_result['rows']),'codec rows',flush=True)


if __name__=='__main__':
    main()
