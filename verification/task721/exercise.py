"""Bounded corpus exercise; public test signatures and disposable DELETE DB only."""
from collections import Counter
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'tests'))
from benchmarks.task720_v1 import corpus
from canonical_v3 import block, media
from canonical_v3.admission import AdmissionAdapter, AdmissionDependencies, TestOnlyConfig
from canonical_v3.primitives import EDGE_SPACE
from codec_prototype.isolated_decoder import IsolatedDecoder
from media_technical_validation import TechnicalMediaValidationError
from scripts import milestone_7_task_7_3_corpus as historical
from scripts import milestone_7_task_7_11_storage as fixtures
from test_milestone_7_task_7_13_admission import application_admission, v2_certificate, state_for, header_for
from verification.task721.bridge import DisposableStore, canonical_media, construct_candidate, validate_candidate, retrieve


def exercise():
    generated = corpus.build()
    assert corpus.manifest(generated) == json.loads((ROOT/'benchmarks/task720_v1/manifest.json').read_bytes())
    old = historical.build_samples()
    historical.verify_manifest(json.loads((ROOT/'tests/fixtures/milestone_7_corpus_v1_manifest.json').read_bytes()))
    samples = [dict(id=s['id'], raw=s['bytes'], mime=s['mime_type'], population='historical') for s in old]
    samples += [dict(s, population='production-like') for s in generated]
    config = TestOnlyConfig(fixtures.CTX, True)
    expected, rows, applications, excluded = {}, [], [], []
    with tempfile.TemporaryDirectory(prefix='task721-corpus-') as directory:
        path = Path(directory)/'provisional.sqlite'
        with IsolatedDecoder() as producer, IsolatedDecoder() as validator, DisposableStore(path, config, decoder=validator, create=True) as store:
            for index, sample in enumerate(samples, 1):
                source = sample['raw']
                original = source.decode().replace('\r\n','\n').replace('\r','\n').strip(EDGE_SPACE).encode() if sample['mime']=='text/plain' else source
                raw = fixtures.corpus_record(original, sample['mime'], sample['id'], index, fixtures.CTX.genesis_hash, producer)
                # Freeze the actual received bytes. Everything below must work
                # even when the producer compressor is unavailable/forbidden.
                compress = media._compress_default
                media._compress_default = lambda _: (_ for _ in ()).throw(AssertionError('validator recompressed'))
                try:
                    result = canonical_media(raw, config, decoder=validator)
                    assert result.body == original
                    assert store.insert(raw)
                    assert store.get(result.block_hash) == raw
                    assert retrieve(store, result.block_hash, config, decoder=validator) == result
                finally:
                    media._compress_default = compress
                expected[result.block_hash] = base64.b64encode(original).decode('ascii')
                desc = json.loads(raw)['envelope']['payload']['media']
                assert len(raw) <= 3*1024*1024
                assert len(json.dumps(desc,sort_keys=True,separators=(',',':'))) <= len(json.dumps(media.descriptor(original,original,sample['mime'],'identity'),sort_keys=True,separators=(',',':')))
                rows.append(dict(id=sample['id'], population=sample['population'], source_size=len(source), original_size=len(original),
                    codec=desc['codec_id'], stored_size=desc['stored_size'], canonical_size=len(raw), block_hash=result.block_hash,
                    original_sha256=result.original_sha256, exact=True, mime=result.mime_type))
                # Real current application admission, not the larger v3 format
                # policy. Rejected objects remain in the format exercise above.
                try:
                    validated, app, resolver = application_admission(original, sample['mime'], submission_id=hashlib.sha256(sample['id'].encode()).hexdigest()[:32])
                except TechnicalMediaValidationError as exc:
                    if exc.result.get('local_resource_defense_failure'):
                        raise
                    excluded.append(dict(id=sample['id'],population=sample['population'],reasons=exc.result['reason_codes']))
                    continue
                assert validated.raw_media_bytes == original
                certificate = v2_certificate(app)
                state = state_for(certificate)
                adapter = AdmissionAdapter(config, AdmissionDependencies(resolver, lambda _:False), decoder=producer)
                candidate = construct_candidate(original, sample['mime'], adapter=adapter, application_certificate=app,
                    canonical_certificate=certificate, header=header_for(sample['mime']), state=state, native_transactions=[])
                media._compress_default = lambda _: (_ for _ in ()).throw(AssertionError('validator recompressed'))
                try:
                    verified = validate_candidate(candidate.canonical_record, config, decoder=validator, state=state)
                    assert verified.body == original and verified.remaining
                    assert store.insert(candidate.canonical_record)
                    assert retrieve(store, verified.block_hash, config, decoder=validator) == verified
                finally:
                    media._compress_default = compress
                expected[verified.block_hash] = base64.b64encode(original).decode('ascii')
                applications.append(dict(id=sample['id'],population=sample['population'],block_hash=verified.block_hash,
                    codec=json.loads(candidate.canonical_record)['envelope']['payload']['media']['codec_id'],
                    original_sha256=verified.original_sha256,exact=True,remaining=verified.remaining))
                print('Application/format complete:',sample['id'],flush=True)
            assert store.connection.execute('PRAGMA journal_mode').fetchone()[0] == 'delete'
            assert store.connection.execute('PRAGMA synchronous').fetchone()[0] == 3
            # Indexes carry no media authority. Rebuild solely from validated R.
            store.connection.execute('DELETE FROM transaction_index')
            store.connection.execute('DELETE FROM block_index')
            rebuilt = store.rebuild_indexes()
            assert rebuilt['blocks'] == len(expected)
        recovered = subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('recover.py')),str(path)],
            input=json.dumps(expected),capture_output=True,text=True,timeout=120,cwd=ROOT)
        if recovered.returncode:
            raise RuntimeError(recovered.stderr)
        recovery = json.loads(recovered.stdout)
        assert len(recovery['rows']) == len(expected)
    return dict(status='PASS', scope='disabled provisional laboratory; no selected/finalized blocks',
        format_records=rows, application_records=applications, current_policy_excluded=excluded,
        format_choices=dict(Counter(r['codec'] for r in rows)), application_choices=dict(Counter(r['codec'] for r in applications)),
        recovery=recovery, journal_mode='DELETE',synchronous='EXTRA',index_rebuild=rebuilt,
        no_recompression=True,distinct_producer_validator_decoders=True)


if __name__ == '__main__':
    output=exercise()
    Path(sys.argv[1]).write_text(json.dumps(output,indent=2,sort_keys=True)+'\n',encoding='utf-8')
