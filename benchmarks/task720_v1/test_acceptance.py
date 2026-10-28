"""Focused independent assertions for the versioned acceptance evidence."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(HERE))
import crosscheck
import measure
from canonical_v3 import block, media
from canonical_v3.primitives import canonical, V3Error
from codec_prototype.isolated_decoder import IsolatedDecoder, Status


def test_independent_published_arithmetic_and_complete_membership():
    assert crosscheck.run(HERE)['status']=='PASS'


def test_all_generated_source_hashes_sizes_and_provenance_are_pinned():
    manifest=json.loads((HERE/'manifest.json').read_bytes())
    generated=measure.profile.build()
    assert measure.profile.manifest(generated)==manifest
    assert len(generated)==len({s['id'] for s in generated})
    for sample,frozen in zip(generated,manifest['samples'],strict=True):
        assert hashlib.sha256(sample['raw']).hexdigest()==frozen['sha256']
        assert len(sample['raw'])==frozen['size']
        assert frozen['origin'] and 'CC0' in manifest['license']


def test_complete_ledger_on_independently_serialized_crypto_record():
    value=json.loads((measure.fixtures.FIXTURES/'block-identity.json').read_bytes())
    # json.dumps is independent of the instrumented recursive ledger.
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    assert sum(measure.ledger(value).values())==len(raw)
    parsed=block.parse_record(raw,measure.fixtures.CTX)
    p=parsed['envelope']['payload']
    assert set(p)==set(block.PAYLOAD_FIELDS)
    assert set(p['media'])==set(media.FIELDS.split())
    assert len(raw)-len(p['media']['payload'])>0


@pytest.mark.parametrize('raw',[b'x',b'Accept exact bytes.',b'Natural language about the audit process. '*200])
def test_producer_selects_the_actual_full_descriptor_and_record_minimum(raw):
    raw=raw.strip()
    with IsolatedDecoder() as worker:
        produced=media.produce(raw,'text/plain',decoder=worker)
        assert produced.outcome.status==Status.VALID
        identity=media.descriptor(raw,raw,'text/plain','identity')
        encoded=media._compress_default(raw)
        candidate=media.descriptor(raw,encoded,'text/plain','zstd')
        expected=candidate if len(canonical(candidate))<len(canonical(identity)) else identity
        assert produced.descriptor==expected
        # Same certificate/identity, different representation; recompute hash.
        original=measure.fixtures.corpus_record(raw,'text/plain','independent-adaptive',1,measure.fixtures.CTX.genesis_hash,worker)
        payload=json.loads(original)['envelope']['payload']
        payload['media']=identity
        assert len(original)<=len(block.encode_record(payload,measure.fixtures.CTX))
        assert block.reconstruct_record_media(original,measure.fixtures.CTX,decoder=worker).original==raw


def test_external_expansion_is_valid_and_corruption_is_invalid():
    with IsolatedDecoder() as worker:
        result=measure.boundaries(worker)
    assert result[0]['validator']=='VALID' and result[0]['producer']=='identity'
    assert result[0]['larger_record']>result[0]['identity_record']
    assert any(r['case']=='wrong-hash' and r['status']=='INVALID' for r in result)
    assert any(r['case']=='corrupt-checksum' and r['status']=='INVALID' for r in result)


def test_original_source_hash_and_mime_fail_closed_on_each_missing_descriptor_field():
    descriptor=media.descriptor(b'x',b'x','text/plain','identity')
    for field in descriptor:
        bad=deepcopy(descriptor); del bad[field]
        with pytest.raises(V3Error):
            media.validate_descriptor(bad)


def test_metadata_target_is_evaluated_at_each_statistic_without_reweighting():
    metrics=json.loads((HERE/'metrics.json').read_bytes())
    rows=json.loads((HERE/'records.json').read_bytes())['rows']
    population=[r for r in rows if r['population']=='production-like']
    summary=metrics['production-like']['all']
    assert summary['objects']==len(population)
    assert summary['metadata_percent']['worst']>15
    assert summary['below_15_percent']==sum(r['metadata_percent']<15 for r in population)
    assert all(r['votes']>=10 and r['certificate_value_bytes']>0 for r in population)
