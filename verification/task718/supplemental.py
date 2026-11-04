"""Explicit supplemental measurements, not a repair of the historical runners.

Verifies every source byte against the frozen manifest. Uses unchanged codec
profiles. Closed-v3 format measurements use Task 7.11's documented canonical
text conversion; source and accepted hashes/sizes are both reported.
"""
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import base64
import hashlib
import json
import math
import os
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import milestone_7_task_7_3_corpus as corpus
from scripts import milestone_7_task_7_4_benchmark as bench
from scripts import milestone_7_task_7_7_block_composition as composition
from scripts import milestone_7_task_7_11_storage as storage
from scripts import milestone_7_task_7_8_node_economics as economics
from canonical_v3 import block, media
from canonical_v3.primitives import canonical, EDGE_SPACE, V3Error, MAX_RECORD
from codec_prototype.isolated_decoder import IsolatedDecoder, Status

OUT = Path(__file__).resolve().parent


def stats(values):
    v = sorted(values)
    return dict(p50=v[math.ceil(len(v) * .5)-1], p95=v[math.ceil(len(v)*.95)-1], worst=v[-1])


def signature_content(value):
    """Count explicit signature fields; arbitrary list strings are not signatures."""
    if isinstance(value, dict):
        return sum(len(v) if k in ('signature','vote_signature') and isinstance(v,str)
                   else signature_content(v) for k,v in value.items())
    if isinstance(value, list):
        return sum(signature_content(v) for v in value)
    return 0


def main():
    scratch = ROOT / 'temp' / 'task718-supplemental'
    scratch.mkdir(exist_ok=True, parents=True)
    os.environ['TEMP'] = os.environ['TMP'] = str(scratch)
    manifest_bytes = corpus.MANIFEST_PATH.read_bytes()
    manifest = json.loads(manifest_bytes)
    samples = {s['id']: s for s in corpus.build_samples()}
    for s in manifest['samples']:
        raw = samples[s['id']]['bytes']
        assert len(raw) == s['original_byte_size'] and hashlib.sha256(raw).hexdigest() == s['sha256']
    actual = corpus.make_manifest()
    differences = []
    for old, new in zip(manifest['samples'], actual['samples']):
        assert old['id'] == new['id']
        delta = {k: dict(frozen=old.get(k), current=new.get(k)) for k in old.keys() | new.keys() if old.get(k) != new.get(k)}
        if delta:
            differences.append(dict(sample_id=old['id'], fields=delta))
    config = json.loads(bench.CONFIG_PATH.read_bytes())
    codec_rows = []
    for profile in config['candidates']:
        enc, dec, details = bench._operations(profile)
        for expected in manifest['samples']:
            raw = samples[expected['id']]['bytes']
            compressed, enc_ns = bench._timed(enc, raw, config['timed_repetitions'], config['warmup_iterations'])
            decoded, dec_ns = bench._timed(dec, compressed, config['timed_repetitions'], config['warmup_iterations'])
            assert decoded == raw and hashlib.sha256(decoded).hexdigest() == expected['sha256']
            codec_rows.append(dict(profile=profile['id'], sample_id=expected['id'], mime=expected['mime_type'], category=expected['category'],
                original=len(raw), encoded=len(compressed), encode_ns_median=statistics.median(enc_ns), decode_ns_median=statistics.median(dec_ns),
                encode_ns_p95=bench._percentile(enc_ns,95), decode_ns_p95=bench._percentile(dec_ns,95),
                sha256_match=True, byte_equal=True, configuration=profile | details))
    print('Verified source hashes and 252 codec round trips', flush=True)
    strict = []
    frozen = []
    previous = storage.CTX.genesis_hash
    with IsolatedDecoder() as worker:
        for index, expected in enumerate(manifest['samples'], 1):
            raw = samples[expected['id']]['bytes']
            for codec, encoded in [('identity', raw), ('zstd', media._compress_default(raw))]:
                descriptor = media.descriptor(raw, encoded, expected['mime_type'], codec)
                outcome = worker.validate(canonical(descriptor))
                assert outcome.status == Status.VALID and outcome.original == raw
                strict.append(dict(sample_id=expected['id'], codec=codec, status=outcome.status.value,
                                   sha256=hashlib.sha256(outcome.original).hexdigest(), byte_equal=True))
            accepted = raw
            if expected['mime_type'] == 'text/plain':
                accepted = raw.decode('utf-8').replace('\r\n','\n').replace('\r','\n').strip(EDGE_SPACE).encode('utf-8')
            record = storage.corpus_record(accepted, expected['mime_type'], expected['id'], index, previous, worker)
            parsed = block.parse_record(record, storage.CTX)
            previous = parsed['hash']
            payload = parsed['envelope']['payload']
            descriptor = payload['media']
            parts = composition.component_accounting(canonical(parsed['envelope']), 'media')
            # Historical instrumentation accounts for the envelope. R has an
            # additional exact 87-byte wrapper. Keep both values explicit.
            wrapper = len(record) - len(canonical(parsed['envelope']))
            assert wrapper == 87
            media_field = parts['serialized_media_representation_bytes']
            nonmedia = len(record) - media_field
            protocol_metadata = len(record) - len(descriptor['payload'])
            frozen.append(dict(sample_id=expected['id'], mime=expected['mime_type'], category=expected['category'],
                source_original=len(raw), accepted_original=len(accepted), source_hash=expected['sha256'],
                accepted_hash=descriptor['original_sha256'], encoded=descriptor['stored_size'], codec=descriptor['codec_id'],
                canonical_record=len(record), wrapper=wrapper, base64_characters=len(descriptor['payload']),
                descriptor_and_media_field_framing=media_field-len(descriptor['payload']),
                nonmedia_metadata=nonmedia, protocol_metadata_including_descriptor=protocol_metadata,
                historical_definition_percent=100*nonmedia/len(record), canonical_metadata_percent=100*protocol_metadata/len(record),
                original_relative_metadata_percent=100*protocol_metadata/len(accepted),
                reviewer_evidence_bytes=len(canonical(payload['admission_certificate']['votes'])),
                native_array_bytes=len(canonical(payload['native_transactions'])),
                signature_characters_subset=signature_content(payload), parts=parts,
                finality_bytes=0, finality_note='Separate proof, absent from corpus fixtures; not treated as free production finality',
                reconstruction_byte_equal=block.reconstruct_record_media(record, storage.CTX, decoder=worker).original == accepted))
    historical = json.loads((ROOT/'benchmarks/milestone_7_task_7_4_results.json').read_bytes())
    hist_rows = {(r['candidate_id'], r['sample_id']): r for r in historical['per_sample']}
    mismatch = [r for r in codec_rows if r['encoded'] != hist_rows[r['profile'],r['sample_id']]['encoded_bytes']]
    codec_groups = []
    for profile in config['candidates']:
        for category in ['plain_text','structured_metadata_json','source_code','image/jpeg','image/png','image/webp','image/gif']:
            rows = [r for r in codec_rows if r['profile']==profile['id'] and category in (r['category'],r['mime'])]
            original, encoded = sum(r['original'] for r in rows), sum(r['encoded'] for r in rows)
            codec_groups.append(dict(profile=profile['id'], category=category, count=len(rows), original=original, encoded=encoded,
                ratio=encoded/original, reduction_percent=100*(1-encoded/original),
                encode_ms_sum_medians=sum(r['encode_ns_median'] for r in rows)/1e6,
                decode_ms_sum_medians=sum(r['decode_ns_median'] for r in rows)/1e6,
                expansions=sum(r['encoded']>r['original'] for r in rows)))
    boundary_gates = []
    for component, cap in [('certificate',196608),('native',98304),('rest',32768)]:
        probe = {'envelope':{'payload':{'media':{'payload':''},'native_transactions':[], 'admission_certificate':{}}}}
        if component=='certificate':
            probe['envelope']['payload']['admission_certificate']='x'*(cap-2)
            target = probe['envelope']['payload']
            key = 'admission_certificate'
        elif component=='native':
            probe['envelope']['payload']['native_transactions']='x'*(cap-2)
            target = probe['envelope']['payload']
            key = 'native_transactions'
        else:
            probe['padding']=''
            size = block.check_budgets(probe,canonical(probe)).rest
            probe['padding']='x'*(cap-size)
            target,key=probe,'padding'
        measured=getattr(block.check_budgets(probe,canonical(probe)),component)
        assert measured==cap
        target[key]+='x'
        try:
            block.check_budgets(probe,canonical(probe))
        except V3Error as e:
            assert e.code=='block_component_budget'
        else:
            raise AssertionError('component cap+1 accepted')
        boundary_gates.append(dict(component=component,cap=cap,at_cap=True,plus_one_rejected=True,
            scope='Analytic budget-gate probe only; deliberately not a schema/crypto-valid block'))
    block.check_complete_size(b' ' * MAX_RECORD)
    try:
        block.check_complete_size(b' '*(MAX_RECORD+1))
    except V3Error as e:
        assert e.code=='block_size'
    else:
        raise AssertionError('complete cap+1 accepted')
    final = dict(boundary='Supplemental exact-source-byte experiment. Original documented runners failed; no gate bypass or source edit. Closed-v3 text canonicalization separately labeled.',
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(), manifest_environment_frozen=manifest['environment'],
        manifest_environment_current=actual['environment'], manifest_differences=differences,
        corpus_count=len(samples), corpus_original_bytes=sum(len(s['bytes']) for s in samples.values()),
        codec_rows=codec_rows, codec_groups=codec_groups, codec_size_mismatches_with_frozen=mismatch,
        strict_worker_roundtrips=strict, frozen_format_rows=frozen,
        boundary_gate_probes=boundary_gates,
        frozen_metadata_summary={key:stats([r[key] for r in frozen]) for key in ['historical_definition_percent','canonical_metadata_percent','original_relative_metadata_percent']},
        frozen_original_size_distribution=stats([r['accepted_original'] for r in frozen]),
        frozen_totals={key:sum(r[key] for r in frozen) for key in ['accepted_original','encoded','canonical_record','base64_characters','nonmedia_metadata','protocol_metadata_including_descriptor','descriptor_and_media_field_framing','reviewer_evidence_bytes','native_array_bytes','signature_characters_subset']})
    cfg = json.loads(economics.DEFAULT_CONFIG.read_bytes())
    costs = []
    for basis in ['historical_projected', 'closed_v3_fixture_mean']:
        trial = deepcopy(cfg)
        if basis == 'closed_v3_fixture_mean':
            trial['workloads']['representative_corpus']['canonical_block_bytes'] = final['frozen_totals']['canonical_record']/36
            trial['workloads']['representative_corpus']['metadata_bytes'] = final['frozen_totals']['nonmedia_metadata']/36
        for rate in [100,1000,10000]:
            for profile, prices in trial['profiles'].items():
                scenario = economics.simulate(trial,rate,'representative_corpus',profile)
                r = scenario['month_36']
                # Illustrative capacity-provisioning adjustment only. Keep
                # backup/egress charges unchanged. Charge one local snapshot,
                # stated temporary margin and one full DB VACUUM workspace at
                # the same marginal disk rate, after the bundle allowance.
                allocated = 2*r['primary_physical_bytes'] + r['snapshot_bytes'] + r['temporary_headroom_bytes']
                capacity_cost = max(0, allocated/2**30-prices['included_primary_gib'])*prices['primary_gib_month']
                adjusted = r['monthly_cost']['total']-r['monthly_cost']['primary_storage']+capacity_cost
                costs.append(dict(basis=basis,rate=rate,profile=profile,canonical_gib=r['cumulative_canonical_bytes']/2**30,
                    primary_gib=r['primary_physical_bytes']/2**30, month_36=r, initial_sync_bytes=scenario['three_year']['initial_sync_bytes'],
                    allocation_including_snapshot_temporary_vacuum_gib=allocated/2**30,
                    illustrative_capacity_priced_total=adjusted,
                    caveat='Audit-only unchanged historical illustrative unit prices; no provider quote, production forecast or new benchmark baseline.'))
    final['economics_audit_sensitivity'] = costs
    (OUT/'supplemental.json').write_text(json.dumps(final,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print('Wrote supplemental.json; size mismatches',len(mismatch), 'strict roundtrips',len(strict),flush=True)


if __name__ == '__main__':
    main()
