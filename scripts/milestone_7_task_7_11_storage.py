"""Reproducible offline Task 7.11 measurement; all DBs are temporary.

Uses existing frozen block vectors and regenerates the Task 7.3 corpus,
checking its original hashes. Fresh public test-key signatures bind media to
the closed v3 format. This is not an accepted ledger or admission certificate.
No active storage backend, config, genesis or database is opened.
"""
import argparse
from contextlib import closing
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import platform
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eth_account import Account
from eth_account.messages import encode_defunct
from PIL import Image
import zstandard

from canonical_v3 import block, evidence, media
from canonical_v3.primitives import Context, EDGE_SPACE, canonical, digest, envelope
from canonical_v3.storage import V3Store
from codec_prototype.isolated_decoder import IsolatedDecoder, Status
from scripts.milestone_7_task_7_3_corpus import build_samples

FIXTURES = ROOT / 'tests/fixtures/milestone_7_v3_v1'
MANIFEST = json.loads((FIXTURES / 'manifest.json').read_bytes())
CTX = Context(**MANIFEST['context'])
DEFAULT_OUTPUT = ROOT / 'benchmarks/milestone_7_task_7_11_results.json'
TEST_KEYS = {Account.from_key(bytes([n * 17]) * 32).address.lower(): bytes([n * 17]) * 32 for n in range(1, 9)}


def sign(raw, address):
    return '0x' + Account.sign_message(encode_defunct(primitive=raw), TEST_KEYS[address]).signature.hex()


def corpus_record(original, mime, sample_id, height, previous, decoder):
    """Fresh format/crypto fixture only, using the frozen symbolic context."""
    payload = deepcopy(json.loads((FIXTURES / 'block-identity.json').read_bytes())['envelope']['payload'])
    produced = media.produce(original, mime, decoder=decoder)
    if produced.outcome.status != Status.VALID:
        raise RuntimeError(f'isolated decoder withheld fixture: {produced.outcome}')
    payload.update(index=height, previous_hash=previous, submission_id=digest(sample_id)[:32],
                   media=produced.descriptor, content_type='text' if mime == 'text/plain' else 'image')
    certificate = payload['admission_certificate']
    certificate.update(content_hash=hashlib.sha256(original).hexdigest(), submission_id=payload['submission_id'])
    tech = certificate['technical_evidence']
    tech.update(raw_media_sha256=certificate['content_hash'], raw_media_byte_length=len(original),
                detected_mime_type=mime, detected_media_type=dict(zip(media.MIMES,
                ('plain_utf8_text', 'jpeg', 'png', 'gif', 'webp')))[mime])
    if mime != 'text/plain':
        with Image.open(io.BytesIO(original)) as image:
            width, height_pixels = image.size
            frames = getattr(image, 'n_frames', 1)
        tech.update(raw_media_semantics='exact_input_bytes', width_pixels=width, height_pixels=height_pixels,
                    frame_count=frames, aggregate_decoded_pixels=width * height_pixels * frames)
    tech['evidence_digest'] = digest({k: v for k, v in tech.items() if k != 'evidence_digest'})
    attestation = certificate['attestation']
    ap = attestation['canonical_payload']
    ap.update(raw_media_sha256=certificate['content_hash'], submission_id=payload['submission_id'],
              technical_evidence_digest=tech['evidence_digest'])
    message = canonical(envelope(ap, 'submitter-attestation', CTX))
    attestation.update(canonical_message=message.decode(), canonical_message_hash=hashlib.sha256(message).hexdigest(),
                       canonical_payload_digest=hashlib.sha256(message).hexdigest(),
                       signature=sign(message, certificate['creator_wallet']))
    for vote in certificate['votes']:
        vote.update(content_hash=certificate['content_hash'], submission_id=payload['submission_id'])
        vp = evidence.vote_payload(vote, CTX)
        message = canonical(vp)
        vote.update(vote_message=message.decode(), signed_message_hash=hashlib.sha256(message).hexdigest(),
                    vote_signature=sign(message, vote['voter_wallet_address']))
        vote['vote_identity'] = digest(dict(payload=vp, signature=vote['vote_signature']))
    certificate['votes'].sort(key=lambda v: (v['dimension'], v['voter_wallet_address'], v['vote_identity']))
    for dimension in ('originality', 'admissibility'):
        certificate[dimension] = evidence.derive_tally(certificate['votes'], dimension, CTX)
    certificate['certificate_digest'] = digest({k: v for k, v in certificate.items() if k != 'certificate_digest'})
    payload.update(certificate_id=certificate['certificate_digest'], vote_hash=certificate['originality']['vote_set_digest'])
    # No native transfers in this chain-shaped fixture: replaying the golden
    # nonce-one transfer across 36 blocks would imply false ledger validity.
    from canonical_v3.transactions import aggregate_hash
    payload.update(native_transactions=[], transactions_hash=aggregate_hash([], CTX))
    return block.encode_record(payload, CTX)


def size(path):
    return path.stat().st_size if path.exists() else 0


def disk_sizes(path):
    return {name: size(Path(str(path) + suffix)) for name, suffix in
            (('main_bytes', ''), ('wal_bytes', '-wal'), ('shm_bytes', '-shm'))}


def dbstat(connection):
    try:
        objects = dict(connection.execute('SELECT name,sum(pgsize) FROM dbstat GROUP BY name'))
    except sqlite3.OperationalError:
        return dict(available=False, index_bytes=None)
    indexes = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    return dict(available=True, index_bytes=sum(value for key, value in objects.items() if key in indexes),
                objects=objects,
                note='WITHOUT ROWID primary keys are part of table B-trees, not additional index objects')


def observe_blobs(records, directory, label, decoder, *, select=False):
    path = directory / (label + '.sqlite')
    observations = []
    with V3Store(path, CTX, decoder=decoder) as store:
        connection = store.connection
        store.checkpoint()
        baseline = disk_sizes(path)
        checkpoints = {1, 5, 15, len(records)}
        for count, raw in enumerate(records, 1):
            store.insert(raw)
            if count in checkpoints:
                observations.append(dict(blocks=count, canonical_bytes=sum(map(len, records[:count])),
                                         allocated_page_bytes=connection.execute('PRAGMA page_count').fetchone()[0] * 4096,
                                         **disk_sizes(path)))
        if select:
            store.select_chain(json.loads(records[-1])['hash'], expected_tip=None)
        verification = store.check_integrity()
        before_checkpoint = disk_sizes(path)
        checkpoint = store.checkpoint()
        after_checkpoint = disk_sizes(path)
        stat = dbstat(connection)
        # BLOBs are kept exactly once in logical records, independent of
        # transient WAL/pages, backup copies, or intentional competing blocks.
        logical = connection.execute('SELECT sum(length(canonical)) FROM blocks').fetchone()[0]
        derived = connection.execute('SELECT sum(length(hash)+length(previous_hash)+length(original_hash)+8) FROM block_index').fetchone()[0]
        backup = store.backup(directory / (label + '-backup.sqlite'))
        backup_size = size(backup)
        connection.execute('VACUUM')
        vacuum_before_checkpoint = disk_sizes(path)
        store.checkpoint()
        after_vacuum = disk_sizes(path)
        return dict(blocks=len(records), canonical_serialized_bytes=sum(map(len, records)),
                    canonical_blob_bytes=logical, redundant_full_media_copies=0,
                    logical_block_index_value_bytes=derived, baseline=baseline, observations=observations,
                    before_checkpoint=before_checkpoint, checkpoint_result=checkpoint,
                    after_checkpoint=after_checkpoint, dbstat_after_checkpoint=stat,
                    backup_bytes=backup_size, vacuum_before_checkpoint=vacuum_before_checkpoint,
                    after_vacuum=after_vacuum, verification=verification,
                    temporary_headroom=dict(
                        measured_wal_peak_at_observation_bytes=max(before_checkpoint['wal_bytes'], vacuum_before_checkpoint['wal_bytes']),
                        measured_backup_copy_bytes=backup_size,
                        modeled_vacuum_working_copy_allowance_bytes=after_checkpoint['main_bytes'],
                        modeled_additional_bytes=backup_size + after_checkpoint['main_bytes'] + max(before_checkpoint['wal_bytes'], vacuum_before_checkpoint['wal_bytes']),
                        note='Observation-point WAL peak, not a filesystem high-water trace. VACUUM working copy is a planning allowance; filesystem temp peak was not measured. SHM is reported separately.'))


def observe_json_section(records, directory):
    """Controlled same-R comparison, not a recreation of the active full schema."""
    path = directory / 'same-records-json.sqlite'
    with closing(sqlite3.connect(path, isolation_level=None)) as connection:
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA synchronous=FULL')
        connection.execute('PRAGMA wal_autocheckpoint=0')
        connection.execute('CREATE TABLE storage_sections (section_name TEXT PRIMARY KEY,json_data TEXT NOT NULL)')
        connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        baseline = disk_sizes(path)
        observations = []
        for count in (1, 5, 15, len(records)):
            # JSON objects embedded as objects, not escaped string copies.
            raw = b'[' + b','.join(records[:count]) + b']'
            connection.execute('BEGIN IMMEDIATE')
            connection.execute("INSERT INTO storage_sections VALUES('chain',?) ON CONFLICT(section_name) DO UPDATE SET json_data=excluded.json_data",
                               (raw.decode('utf-8'),))
            connection.execute('COMMIT')
            observations.append(dict(blocks=count, logical_chain_json_bytes=len(raw), **disk_sizes(path)))
        connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        after_checkpoint = disk_sizes(path)
        connection.execute('VACUUM')
        connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        return dict(boundary='Minimal one-section table with identical R objects and four whole-section saves; excludes active schema/indexes and is not Task 7.7 remeasurement',
                    baseline=baseline, observations=observations, after_checkpoint=after_checkpoint,
                    after_vacuum=disk_sizes(path))


def run():
    manifest_path = ROOT / 'tests/fixtures/milestone_7_corpus_v1_manifest.json'
    corpus_manifest = json.loads(manifest_path.read_bytes())
    samples = {sample['id']: sample for sample in build_samples()}
    rows, records = [], []
    previous = CTX.genesis_hash
    with tempfile.TemporaryDirectory(prefix='.task-7-11-', dir=ROOT / 'benchmarks') as directory:
        directory = Path(directory)
        with IsolatedDecoder() as decoder:
            for index, expected in enumerate(corpus_manifest['samples'], 1):
                sample = samples[expected['id']]
                original = sample['bytes']
                if (hashlib.sha256(original).hexdigest() != expected['sha256'] or
                        len(original) != expected['original_byte_size']):
                    raise ValueError('corpus regeneration disagrees with frozen manifest')
                if sample['mime_type'] == 'text/plain':
                    original = original.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n').strip(EDGE_SPACE).encode('utf-8')
                raw = corpus_record(original, sample['mime_type'], sample['id'], index, previous, decoder)
                parsed = json.loads(raw)
                previous = parsed['hash']
                descriptor = parsed['envelope']['payload']['media']
                rows.append(dict(sample_id=sample['id'], original_bytes=len(original),
                                 source_original_sha256=expected['sha256'], original_sha256=descriptor['original_sha256'],
                                 codec=descriptor['codec_id'], encoded_bytes=descriptor['stored_size'],
                                 base64_payload_bytes=len(descriptor['payload']), canonical_bytes=len(raw),
                                 block_hash=parsed['hash'], canonical_file_sha256=hashlib.sha256(raw).hexdigest()))
                records.append(raw)
            print(f'Built {len(records)} signed corpus records; measuring isolated SQLite', flush=True)
            corpus_result = observe_blobs(records, directory, 'corpus', decoder, select=True)
            golden_records = [(FIXTURES / (name + '.json')).read_bytes() for name in ('block-identity', 'block-zstd', 'block-high-s')]
            golden_result = observe_blobs(golden_records, directory, 'golden', decoder)
        section_result = observe_json_section(records, directory)
    historical = json.loads((ROOT / 'benchmarks/milestone_7_task_7_7_results.json').read_bytes())
    prior = historical['sqlite']['projected_v3:adaptive']
    return dict(measurement_id='milestone-7-task-7.11-v1',
                environment=dict(python=platform.python_version(), platform=platform.platform(), sqlite=sqlite3.sqlite_version, zstandard=zstandard.__version__),
                boundary='Inactive v3 format/crypto/media fixtures, symbolic policies/genesis/public test keys; not accepted history or a performance benchmark. BLOB stores canonical JSON including base64 expansion.',
                corpus_manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                golden_manifest_sha256=hashlib.sha256((FIXTURES / 'manifest.json').read_bytes()).hexdigest(),
                rows=rows, corpus=corpus_result, golden=golden_result, same_records_json_section=section_result,
                task_7_7_comparison=dict(
                    projected_envelope_bytes=historical['aggregates']['projected_v3:adaptive']['all']['component_totals']['complete_serialized_block_bytes'],
                    portable_wrapper_correction_bytes=87 * len(records),
                    projected_json_section_checkpoint_bytes=prior['database_bytes_after_checkpoint'],
                    projected_json_section_vacuum_bytes=prior['database_bytes_after_vacuum'],
                    projected_json_section_wal_bytes=prior['observations'][-1]['wal_bytes_before_checkpoint'],
                    measured_vacuum_difference_bytes=prior['database_bytes_after_vacuum'] - corpus_result['after_vacuum']['main_bytes'],
                    caveat='Same source media corpus, different closed signed evidence/transactions/context/text normalization and portable R. Difference is descriptive, not pure BLOB savings. Same-R controlled table comparison is separate. No million-block extrapolation or Task 7.8 assumption change.'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = run()
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    print(f'Wrote {args.output}; {len(result["rows"])} corpus records, exact bytes verified')


if __name__ == '__main__':
    main()
