"""Task 7.19 exact-source checks and separately versioned laboratory measurements."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from scripts import milestone_7_task_7_3_corpus as corpus


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def manifest():
    frozen = json.loads(corpus.MANIFEST_PATH.read_bytes())
    actual = corpus.make_manifest()
    differences = []
    for old, new in zip(frozen['samples'], actual['samples'], strict=True):
        assert old['id'] == new['id']
        for key in old.keys() | new.keys():
            if old.get(key) != new.get(key):
                differences.append(dict(sample_id=old['id'], field=key, frozen=old.get(key), current=new.get(key)))
    sources = corpus.build_samples()
    for sample, record in zip(sources, frozen['samples'], strict=True):
        assert sample['id'] == record['id']
        assert len(sample['bytes']) == record['original_byte_size']
        assert hashlib.sha256(sample['bytes']).hexdigest() == record['sha256']
    save('manifest_differences.json', dict(top_level_differences=[k for k in frozen if k != 'samples' and frozen[k] != actual[k]],
        differences=differences, sample_count=len(sources), original_bytes=sum(len(s['bytes']) for s in sources),
        source_hashes_sizes_order_exact=True, frozen_environment=frozen['environment'], current_environment=actual['environment']))
    print('Verified all 36 source hashes, sizes and order; observational field differences:', len(differences))


def media_checks():
    from scripts import milestone_7_task_7_11_storage as storage
    from scripts import milestone_7_task_7_7_block_composition as composition
    from canonical_v3 import block, media
    from canonical_v3.primitives import canonical, EDGE_SPACE
    from codec_prototype.isolated_decoder import IsolatedDecoder, Status
    frozen = json.loads(corpus.MANIFEST_PATH.read_bytes())
    corpus.verify_manifest(frozen)
    samples = corpus.build_samples()
    rows, strict = [], []
    previous = storage.CTX.genesis_hash
    with IsolatedDecoder() as worker:
        for index, (s, expected) in enumerate(zip(samples, frozen['samples'], strict=True), 1):
            raw = s['bytes']
            for codec, encoded in [('identity', raw), ('zstd', media._compress_default(raw))]:
                descriptor = media.descriptor(raw, encoded, s['mime_type'], codec)
                outcome = worker.validate(canonical(descriptor))
                assert outcome.status == Status.VALID and outcome.original == raw
                assert hashlib.sha256(outcome.original).hexdigest() == expected['sha256']
                strict.append(dict(sample_id=s['id'], codec=codec, exact_bytes_and_hash=True))
            accepted = raw
            if s['mime_type'] == 'text/plain':
                accepted = raw.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n').strip(EDGE_SPACE).encode('utf-8')
            record = storage.corpus_record(accepted, s['mime_type'], s['id'], index, previous, worker)
            parsed = block.parse_record(record, storage.CTX)
            previous = parsed['hash']
            descriptor = parsed['envelope']['payload']['media']
            identity = media.descriptor(accepted, accepted, s['mime_type'], 'identity')
            assert len(canonical(descriptor)) <= len(canonical(identity))
            reconstructed = block.reconstruct_record_media(record, storage.CTX, decoder=worker)
            assert reconstructed.original == accepted
            assert hashlib.sha256(accepted).hexdigest() == descriptor['original_sha256']
            metadata = len(record) - len(descriptor['payload'])
            rows.append(dict(sample_id=s['id'], source_sha256=expected['sha256'], accepted_sha256=descriptor['original_sha256'],
                source_bytes=len(raw), accepted_bytes=len(accepted), codec=descriptor['codec_id'], stored_bytes=descriptor['stored_size'],
                record_bytes=len(record), metadata_bytes=metadata, canonical_metadata_percent=100 * metadata / len(record),
                descriptor_bytes=len(canonical(descriptor)), identity_descriptor_bytes=len(canonical(identity)),
                exact_accepted_roundtrip=True, parts=composition.component_accounting(canonical(parsed['envelope']), 'media')))
    values = [r['canonical_metadata_percent'] for r in rows]
    result = dict(boundary='Existing inactive format laboratory; public fixture test keys only; original source and canonicalized accepted text explicitly distinguished.',
        rows=rows, strict_source_roundtrips=strict, selected=dict(Counter(r['codec'] for r in rows)),
        canonical_metadata_percent=dict(p50=corpus.percentile(values, 50), p95=corpus.percentile(values, 95), worst=max(values)),
        totals={k: sum(r[k] for r in rows) for k in ['source_bytes', 'accepted_bytes', 'stored_bytes', 'record_bytes', 'metadata_bytes']})
    baseline = json.loads((ROOT / 'verification/task718/supplemental.json').read_bytes())
    assert result['canonical_metadata_percent'] == baseline['frozen_metadata_summary']['canonical_metadata_percent']
    assert result['totals']['record_bytes'] == baseline['frozen_totals']['canonical_record']
    save('adaptive_roundtrip_metadata.json', result)
    print('72 exact source roundtrips; 36 adaptive accepted-byte roundtrips; metadata matches Task 7.18')


def compare():
    codec = json.loads((OUT / 'codec.json').read_bytes())
    historical = json.loads((ROOT / 'benchmarks/milestone_7_task_7_4_results.json').read_bytes())
    timing = lambda k: k.startswith(('compression_', 'decompression_'))
    codec_differences = []
    for old, new in zip(historical['per_sample'], codec['per_sample'], strict=True):
        for key in old.keys() | new.keys():
            if not timing(key) and old.get(key) != new.get(key):
                codec_differences.append(dict(sample=new['sample_id'], profile=new['candidate_id'], field=key))
    a = json.loads((OUT / 'composition_no_sqlite.json').read_bytes())
    b = json.loads((ROOT / 'benchmarks/milestone_7_task_7_7_results.json').read_bytes())
    a.pop('environment'); b.pop('environment')
    a.pop('sqlite'); b.pop('sqlite')
    storage = json.loads((OUT / 'storage.json').read_bytes())
    old_storage = json.loads((ROOT / 'benchmarks/milestone_7_task_7_11_results.json').read_bytes())
    storage.pop('environment'); old_storage.pop('environment')
    economics = json.loads((OUT / 'economics.json').read_bytes())
    old_economics = json.loads((ROOT / 'benchmarks/milestone_7_task_7_8_results.json').read_bytes())
    result = dict(codec_rows=len(codec['per_sample']), codec_nontiming_differences=codec_differences,
        composition_exact_excluding_environment_and_sqlite=a == b, storage_exact_excluding_environment=storage == old_storage,
        historical_composition_sqlite_replay='BLOCKED: historical WAL request conflicts with active DELETE-only safety gate; no bypass',
        economics_json_exact=economics == old_economics,
        economics_csv_byte_exact=(OUT / 'economics.csv').read_bytes() == (ROOT / 'benchmarks/milestone_7_task_7_8_monthly.csv').read_bytes())
    save('comparisons.json', result)
    assert not codec_differences and all(value for key, value in result.items() if isinstance(value, bool))
    print(json.dumps(result))


if __name__ == '__main__':
    {'manifest': manifest, 'media': media_checks, 'compare': compare}[sys.argv[1]]()
