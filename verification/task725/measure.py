"""Task 7.25 v1: disposable physical measurements; no active node imports.

Run with -B in the pinned repository venv. All databases are under a new temp
directory. The legacy V3Store initializer, backup and restore are never called.
"""
import argparse
from collections import Counter
from contextlib import closing
from copy import deepcopy
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from canonical_v3 import block, media
from canonical_v3.admission import TestOnlyConfig
from canonical_v3.primitives import canonical, EDGE_SPACE
from canonical_v3.storage import SCHEMA, V3Store
from codec_prototype.isolated_decoder import IsolatedDecoder, Status
from scripts import milestone_7_task_7_3_corpus as historical
from scripts import milestone_7_task_7_11_storage as fixtures
from verification.task721.bridge import DisposableStore

CONFIG = TestOnlyConfig(fixtures.CTX, True)
SECONDARY = [s.split()[2] for s in SCHEMA if s.startswith('CREATE INDEX ')]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads((ROOT / path).read_bytes())


def save(out, name, value):
    (out / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def domain(source, mime):
    return source.decode().replace('\r\n', '\n').replace('\r', '\n').strip(EDGE_SPACE).encode() if mime == 'text/plain' else source


def balanced(original, mime, raw=None):
    # Same 7.23 GIF rule for its animated samples; static GIFs use static cap.
    frames = 1
    if mime == 'image/gif':
        from PIL import Image
        import io
        with Image.open(io.BytesIO(original)) as image:
            frames = getattr(image, 'n_frames', 1)
    ceiling = 16384 if mime == 'text/plain' else 524288 if mime == 'image/gif' and frames > 1 else 262144
    reasons = []
    if len(original) > ceiling:
        reasons.append('original_cap')
    if raw is None:
        reasons.append('no_legal_frozen_record')
    else:
        desc = json.loads(raw)['envelope']['payload']['media']
        if desc['stored_size'] > 525312:
            reasons.append('encoded_cap')
        if len(raw) > 1048576:
            reasons.append('complete_cap')
    return dict(eligible=not reasons, reasons=reasons, original_cap=ceiling, frames=frames)


def corpora(out, scratch, decoder):
    c720 = load('corpus725_720', 'benchmarks/task720_v1/corpus.py')
    c723 = load('corpus725_723', 'benchmarks/task723_v1/corpus.py')
    new = c720.build()
    assert c720.manifest(new) == read('benchmarks/task720_v1/manifest.json')
    print('Task 7.20 manifest exact', flush=True)
    memes = c723.build()
    assert c723.manifest(memes) == read('benchmarks/task723_v1/manifest.json')
    history = [dict(id=s['id'], raw=s['bytes'], mime=s['mime_type']) for s in historical.build_samples()]
    for s, frozen in zip(history, read('tests/fixtures/milestone_7_corpus_v1_manifest.json')['samples'], strict=True):
        assert s['id'] == frozen['id'] and sha(s['raw']) == frozen['sha256'] and len(s['raw']) == frozen['original_byte_size']
    frozen720 = read('benchmarks/task720_v1/records.json')['rows']
    frozen723 = read('benchmarks/task723_v1/records.json')['rows']
    groups = {}; inventories = {}; oracle = {}
    for name, samples, frozen in [('historical36', history, [r for r in frozen720 if r['population'] == 'historical']),
                                  ('production34', new, [r for r in frozen720 if r['population'] == 'production-like']),
                                  ('meme58', memes, frozen723)]:
        records = []; rows = []; expected = {r['id']: r for r in frozen}
        for index, sample in enumerate(samples, 1):
            if sample.get('category') == 'diagnostic-control':
                continue
            sid, mime, source = sample['id'], sample['mime'], sample['raw']
            original = domain(source, mime)
            row = dict(id=sid, mime=mime, source_bytes=len(source), source_sha256=sha(source),
                       original_bytes=len(original), original_sha256=sha(original), synthetic=True)
            if len(original) > (media.MAX_TEXT if mime == 'text/plain' else media.MAX_IMAGE):
                assert expected[sid]['record_bytes'] is None
                row.update(record_bytes=None, encoded_bytes=None, codec=None, block_hash=None,
                           status='Excluded: original exceeds frozen v3 cap; no complete canonical block')
                raw = None
            else:
                raw = fixtures.corpus_record(original, mime, sid, index, fixtures.CTX.genesis_hash, decoder)
                rec = block.parse_record(raw, fixtures.CTX); desc = rec['envelope']['payload']['media']
                # Exact historical context, not just a length match.
                assert sha(raw) == expected[sid]['record_sha256']
                assert len(raw) == expected[sid]['record_bytes']
                assert desc['stored_size'] == expected[sid]['encoded_bytes']
                identity = deepcopy(rec['envelope']['payload'])
                identity['media'] = media.descriptor(original, original, mime, 'identity')
                assert len(raw) <= len(block.encode_record(identity, fixtures.CTX))
                result = block.reconstruct_record_media(raw, fixtures.CTX, decoder=decoder)
                assert result.status == Status.VALID and result.original == original
                row.update(record_bytes=len(raw), encoded_bytes=desc['stored_size'], codec=desc['codec_id'],
                           block_hash=rec['hash'], record_sha256=sha(raw), status='Exact frozen record replay')
                records.append(raw)
                oracle[rec['hash']] = dict(original_sha256=sha(original), original_bytes=len(original), canonical_sha256=sha(raw))
            row['balanced'] = balanced(original, mime, raw)
            rows.append(row)
        groups[name] = records; inventories[name] = rows
        print(name, len(rows), 'originals,', len(records), 'exact frozen records', flush=True)
    admitted = {r['id'] for r in inventories['meme58'] if r['balanced']['eligible']}
    frozen_balanced = next(p for p in read('benchmarks/task723_v1/candidates.json')['profiles'] if p['name'] == 'B_balanced')
    assert admitted == set(frozen_balanced['admitted_ids']) and len(admitted) == 41
    groups['balanced41'] = [raw for raw in groups['meme58'] if json.loads(raw)['hash'] in
                            {r['block_hash'] for r in inventories['meme58'] if r['id'] in admitted}]
    inventories['balanced41'] = [r for r in inventories['meme58'] if r['id'] in admitted]
    # A separate non-economic transaction-index diagnostic. Main corpora have none.
    base = json.loads((fixtures.FIXTURES / 'block-identity.json').read_bytes())
    assert len(base['envelope']['payload']['native_transactions']) > 0
    groups['native_index_control'] = [canonical(base)]
    save(out, 'workloads.json', dict(version=1, weighting='Equal records, synthetic coverage; no production traffic distribution',
        context='Exact frozen public test signatures; independent candidates, not authenticated selected/finalized history',
        rows=inventories, totals={name:dict(originals=len(rows), legal_records=sum(r['record_bytes'] is not None for r in rows),
            source_bytes=sum(r['source_bytes'] for r in rows), original_bytes=sum(r['original_bytes'] for r in rows),
            canonical_bytes=sum(r['record_bytes'] or 0 for r in rows), encoded_bytes=sum(r['encoded_bytes'] or 0 for r in rows),
            choices=dict(Counter(r['codec'] for r in rows if r['codec']))) for name, rows in inventories.items()}))
    save(out, 'corpus_hashes.json', {p:sha((ROOT/p).read_bytes()) for p in
        ('tests/fixtures/milestone_7_corpus_v1_manifest.json', 'benchmarks/task720_v1/manifest.json',
         'benchmarks/task720_v1/records.json', 'benchmarks/task723_v1/manifest.json',
         'benchmarks/task723_v1/records.json', 'benchmarks/task723_v1/candidates.json')})
    return groups, oracle


def filesystem(path):
    result = dict(logical_bytes=path.stat().st_size)
    if os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCompressedFileSizeW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)]
        kernel.GetCompressedFileSizeW.restype = ctypes.c_uint32
        high = ctypes.c_uint32()
        ctypes.set_last_error(0)
        low = kernel.GetCompressedFileSizeW(str(path), ctypes.byref(high))
        if low == 0xffffffff and ctypes.get_last_error():
            raise ctypes.WinError(ctypes.get_last_error())
        kernel.GetFileAttributesW.argtypes = [ctypes.c_wchar_p]
        kernel.GetFileAttributesW.restype = ctypes.c_uint32
        attr = kernel.GetFileAttributesW(str(path))
        assert attr != 0xffffffff
        result.update(allocated_bytes=(high.value << 32) + low, sparse=bool(attr & 0x200),
                      compressed=bool(attr & 0x800), reparse_point=bool(attr & 0x400))
    elif hasattr(path.stat(), 'st_blocks'):
        result['allocated_bytes'] = path.stat().st_blocks * 512
    else:
        result['allocated_bytes'] = None
    return result


def connect(path):
    c = sqlite3.connect(path, isolation_level=None)
    assert c.execute('PRAGMA journal_mode').fetchone() == ('delete',)
    c.execute('PRAGMA synchronous=EXTRA')
    c.execute('PRAGMA foreign_keys=ON')
    return c


def observe(c, path, count, logical):
    page_size = c.execute('PRAGMA page_size').fetchone()[0]
    pages = c.execute('PRAGMA page_count').fetchone()[0]
    free = c.execute('PRAGMA freelist_count').fetchone()[0]
    assert not c.in_transaction
    assert not Path(str(path)+'-wal').exists() and not Path(str(path)+'-shm').exists()
    return dict(blocks=count, canonical_bytes=logical, **filesystem(path), page_size=page_size, page_count=pages,
        free_pages=free, live_allocated_page_bytes=(pages-free)*page_size,
        database_overhead_bytes=path.stat().st_size-logical, journal_mode=c.execute('PRAGMA journal_mode').fetchone()[0],
        synchronous=c.execute('PRAGMA synchronous').fetchone()[0], sqlite_version=sqlite3.sqlite_version)


def retrieval(c, hashes, indexed):
    # Warm caches; query+fetch only, no crypto/codec cost. Same SQL for both schemas.
    ids = sorted(hashes)[:32]
    durations = []
    for repetition in range(6):
        started = time.perf_counter_ns()
        for h in ids:
            assert c.execute('SELECT canonical FROM blocks WHERE hash=?', (h,)).fetchone()
        elapsed = (time.perf_counter_ns()-started)/len(ids)
        if repetition:
            durations.append(elapsed)
    output = dict(primary_key_ns_per_get=durations, cache='warm, five batches, up to 32 hashes; includes BLOB fetch; observational only')
    if indexed:
        h = ids[0]
        height = c.execute('SELECT height FROM block_index WHERE hash=?', (h,)).fetchone()[0]
        durations = []
        for _ in range(5):
            started = time.perf_counter_ns()
            for _ in range(100):
                assert c.execute('SELECT hash FROM block_index WHERE height=?', (height,)).fetchone()
            durations.append((time.perf_counter_ns()-started)/100)
        output.update(height_ns_per_get=durations, height_query_plan=c.execute(
            'EXPLAIN QUERY PLAN SELECT hash FROM block_index WHERE height=?', (height,)).fetchall())
    return output


def clone_records(records, repeats):
    output = list(records)
    for cycle in range(1, repeats):
        for raw in records:
            p = deepcopy(json.loads(raw)['envelope']['payload'])
            p['index'] += cycle*len(records)
            output.append(block.encode_record(p, fixtures.CTX))
    assert len({json.loads(r)['hash'] for r in output}) == len(output)
    return output


def index_pages(source, target):
    # Drop only in a disposable byte-copy after the real store has closed.
    shutil.copyfile(source, target)
    c = connect(target); rows = []
    for name in SECONDARY:
        before = c.execute('PRAGMA freelist_count').fetchone()[0]
        page_count = c.execute('PRAGMA page_count').fetchone()[0]
        c.execute('DROP INDEX '+name)
        assert c.execute('PRAGMA page_count').fetchone()[0] == page_count
        freed = c.execute('PRAGMA freelist_count').fetchone()[0]-before
        rows.append(dict(name=name, freed_pages=freed, bytes=freed*c.execute('PRAGMA page_size').fetchone()[0]))
    assert c.execute('PRAGMA integrity_check').fetchone() == ('ok',)
    c.close()
    return dict(method='Direct marginal releasable pages on test copy; no dbstat; includes any sqlite_schema page release. WITHOUT ROWID primary trees remain inseparable from table bytes.',
                rows=rows, secondary_allocation_bytes=sum(r['bytes'] for r in rows))


def storage(out, scratch, groups, decoder):
    results = {}; paths = {}; rawsets = {}
    for name, base in groups.items():
        repeats = 32 if name == 'balanced41' else 32 if name == 'native_index_control' else 4
        records = clone_records(base, repeats)
        counts = sorted({0, 1, 5, len(base), 2*len(base), 4*len(base), len(records)} & set(range(len(records)+1)))
        if name == 'balanced41':
            counts = sorted(set(counts) | {8*len(base), 16*len(base)})
        rawsets[name] = records
        variants = {}
        for variant in ('full', 'no_secondary', 'minimal'):
            path = scratch/f'{name}-{variant}.sqlite'
            store = None
            if variant == 'full':
                store = DisposableStore(path, CONFIG, decoder=decoder, create=True)
                c = store.connection
            else:
                c = connect(path)
                schema = [s for s in SCHEMA if not s.startswith('CREATE INDEX ')] if variant == 'no_secondary' else [
                    s for s in SCHEMA if s.startswith('CREATE TABLE blocks ') or s.startswith('CREATE TRIGGER immutable_blocks_')]
                for statement in schema:
                    c.execute(statement)
                if variant == 'no_secondary':
                    c.execute('INSERT INTO settings VALUES(1,?,?,?,NULL)', (canonical(vars(fixtures.CTX)), 0, fixtures.CTX.genesis_hash))
            observations = [observe(c, path, 0, 0)]; logical = 0; hashes = []
            for count, raw in enumerate(records, 1):
                rec = json.loads(raw); hashes.append(rec['hash']); logical += len(raw)
                if store is not None:
                    assert store.insert(raw)
                else:
                    c.execute('BEGIN IMMEDIATE')
                    c.execute('INSERT INTO blocks VALUES(?,?)', (rec['hash'], raw))
                    if variant == 'no_secondary':
                        c.execute('INSERT INTO block_index VALUES(?,?,?,?)', V3Store._derived(rec))
                        c.executemany('INSERT INTO transaction_index VALUES(?,?,?)', V3Store._transactions(rec))
                    c.execute('COMMIT')
                if count in counts:
                    observation = observe(c, path, count, logical)
                    prev = observations[-1]
                    observation['marginal_bytes_per_block'] = (observation['logical_bytes']-prev['logical_bytes'])/(count-prev['blocks'])
                    observation['marginal_overhead_bytes_per_block'] = ((observation['logical_bytes']-prev['logical_bytes'])-(logical-prev['canonical_bytes']))/(count-prev['blocks'])
                    observations.append(observation)
            assert c.execute('PRAGMA integrity_check').fetchone() == ('ok',)
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
            assert c.execute('SELECT sum(length(canonical)) FROM blocks').fetchone()[0] == logical
            timing = retrieval(c, hashes, variant != 'minimal')
            entries = {name:len(records) for name in SECONDARY}
            entries['transaction_id_idx'] = sum(len(json.loads(r)['envelope']['payload']['native_transactions']) for r in records)
            # Same immutable identity constraints on minimal and full; test rollback-only violations.
            checks = {}
            for label, sql, params in [('duplicate_hash', 'INSERT INTO blocks VALUES(?,?)', (hashes[0], records[0])),
                                       ('immutable_update', 'UPDATE blocks SET canonical=canonical WHERE hash=?', (hashes[0],)),
                                       ('immutable_delete', 'DELETE FROM blocks WHERE hash=?', (hashes[0],)),
                                       ('blob_type', 'INSERT INTO blocks VALUES(?,?)', ('f'*64, 'not bytes'))]:
                c.execute('BEGIN')
                try:
                    c.execute(sql, params)
                except sqlite3.IntegrityError:
                    checks[label] = True
                else:
                    checks[label] = False
                finally:
                    c.execute('ROLLBACK')
            assert all(checks.values())
            try:
                c.execute('SELECT sum(pgsize) FROM dbstat').fetchone()
                dbstat = True
            except sqlite3.OperationalError:
                dbstat = False
            c.close()
            variants[variant] = dict(observations=observations, retrieval=timing, constraints=checks,
                                     dbstat_available=dbstat, index_entries=entries if variant != 'minimal' else {})
            if variant == 'full':
                paths[name] = path
        full = variants['full']['observations'][-1]
        variants['secondary_pages'] = index_pages(paths[name], scratch/f'{name}-drop-probe.sqlite')
        variants['file_differences'] = dict(full_minus_minimal=full['logical_bytes']-variants['minimal']['observations'][-1]['logical_bytes'],
            full_minus_no_secondary=full['logical_bytes']-variants['no_secondary']['observations'][-1]['logical_bytes'],
            note='Full-minus-minimal includes settings, derived tables and fixed schema, not pure indexes. Full-minus-no_secondary preserves uniqueness/FK/immutability semantics; nonunique query indexes only are omitted.')
        results[name] = variants
        print('Storage', name, len(records), 'blocks;', full['logical_bytes'], 'bytes', flush=True)
    save(out, 'sqlite.json', dict(version=1, populations=results,
        occupancy='Live allocated pages = (page_count-freelist_count)*page_size; not exact filled-cell bytes. File length, filesystem allocation and live pages are separate.',
        layout='Actual inherited V3Store insert/get schema via existing Task 7.21 DELETE/EXTRA initializer. Candidate storage only; selected/finality tables empty. No WAL.',
        synthetic_growth='Additional cycles change only unsigned header index and canonical block hash; media/certificates are reused. Valid independent format records, not a selected chain or independent production originals.'))
    return paths, rawsets, results


def copy_observed(source, target, directory):
    # Exclusive streaming writes: no reflink/hardlink/dedup API; flush every chunk.
    baseline = sum(p.stat().st_size for p in directory.iterdir() if p.is_file())
    peak = baseline; points = 0
    with source.open('rb') as inp, target.open('xb') as dst:
        while chunk := inp.read(1024*1024):
            dst.write(chunk); dst.flush(); os.fsync(dst.fileno())
            peak = max(peak, sum(p.stat().st_size for p in directory.iterdir() if p.is_file()))
            points += 1
    assert sha(source.read_bytes()) == sha(target.read_bytes())
    assert not os.path.samefile(source, target)
    return dict(bytes=target.stat().st_size, baseline_directory_bytes=baseline,
                peak_directory_bytes=peak, additional_workspace_bytes=peak-baseline,
                observation_points=points, **filesystem(target))


def recover(path, expected_path, result_path):
    expected = json.loads(expected_path.read_bytes())
    class ObservedDecoder(IsolatedDecoder):
        # Observe the real decode already performed by V3Store.get; avoid a
        # redundant second decode and a duplicate whole-database crypto scan.
        def validate(self, raw):
            self.last = super().validate(raw)
            return self.last
    with ObservedDecoder() as decoder, DisposableStore(path, CONFIG, decoder=decoder) as store:
        identities = [r[0] for r in store.connection.execute('SELECT hash FROM blocks')]
        assert set(identities) == set(expected)
        native_count = 0
        for h in identities:
            raw = store.get(h)
            result = decoder.last
            oracle = expected[h]
            assert sha(raw) == oracle['canonical_sha256']
            assert result.status == Status.VALID and len(result.original) == oracle['original_bytes']
            assert sha(result.original) == oracle['original_sha256']
            native_count += len(json.loads(raw)['envelope']['payload']['native_transactions'])
        c = store.connection
        assert c.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert not c.execute('PRAGMA foreign_key_check').fetchall()
        assert c.execute('SELECT count(*) FROM block_index').fetchone()[0] == len(identities)
        assert c.execute('SELECT count(*) FROM transaction_index').fetchone()[0] == native_count
        assert c.execute('SELECT selected_tip FROM settings').fetchone() == (None,)
        assert c.execute('SELECT count(*) FROM canonical_chain').fetchone() == (0,)
        assert c.execute('SELECT count(*) FROM finality').fetchone() == (0,)
        integrity = dict(blocks=len(identities), native_transaction_references=native_count,
                         selected_blocks=0, finality_proofs=0)
    result_path.write_text(json.dumps(dict(blocks=len(identities), canonical_identity=True,
        canonical_bytes_sha256=True, original_commitments=True, integrity=integrity,
        oracle='Hashes/sizes only; no original media files or other DB paths supplied', fresh_process=True))+'\n')


def backups(out, scratch, paths, rawsets, decoder):
    results = {}
    for name, source in paths.items():
        if name == 'native_index_control':
            continue
        directory = scratch/('recovery-'+name); directory.mkdir()
        snap = directory/'snapshot.sqlite'; backup = directory/'full-backup.sqlite'; restored = directory/'restored.sqlite'
        with DisposableStore(source, CONFIG, decoder=decoder) as store:
            dst = connect(snap)
            store.connection.backup(dst, pages=64)
            assert dst.execute('PRAGMA integrity_check').fetchone() == ('ok',)
            dst.close()
        assert not os.path.samefile(source, snap)
        backup_measure = copy_observed(snap, backup, directory)
        recovery_measure = copy_observed(backup, restored, directory)
        expected = {}
        # Expected commitments were independently verified against original bytes in corpora().
        for raw in rawsets[name]:
            rec = json.loads(raw); desc = rec['envelope']['payload']['media']
            expected[rec['hash']] = dict(canonical_sha256=sha(raw), original_sha256=desc['original_sha256'], original_bytes=desc['original_size'])
        expected_path = scratch/(name+'-restore-oracle.json'); save(scratch, expected_path.name, expected)
        result_path = scratch/(name+'-restored.json')
        argv = [sys.executable, '-B', str(Path(__file__).resolve()), '--recover', str(restored), str(expected_path), str(result_path)]
        started = time.monotonic()
        process = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=1200)
        assert process.returncode == 0, process.stdout+process.stderr
        verified = json.loads(result_path.read_bytes())
        # Fresh child already ran actual inherited get + strict decoder on every
        # record. This independent comparison needs bytes, not another decode.
        with closing(sqlite3.connect(restored.as_uri()+'?mode=ro',uri=True)) as comparison:
            for raw in rawsets[name]:
                stored = comparison.execute('SELECT canonical FROM blocks WHERE hash=?', (json.loads(raw)['hash'],)).fetchone()
                assert stored == (raw,)
        results[name] = dict(source=filesystem(source), snapshot=filesystem(snap), backup=backup_measure,
            recovery=recovery_measure, verification=verified, elapsed_seconds=time.monotonic()-started,
            snapshot_ratio=snap.stat().st_size/source.stat().st_size,
            backup_ratio=backup.stat().st_size/source.stat().st_size,
            retained_four_backups_bytes=4*backup.stat().st_size,
            peak_including_live_source_bytes=source.stat().st_size+recovery_measure['peak_directory_bytes'],
            backing='Independent file IDs and streaming full backup/restore writes. SQLite online backup snapshot is self-contained. Same-volume copies share device failure domain; no remote durability claim.',
            peak_scope='Exact monotone full-copy file-length high water after each fsynced chunk; excludes RAM/OS buffers. Restore writes one destination directly, no decompressor/temp stage. Snapshot+backup+restored coexist; live source separate.')
        print('Recovery', name, verified['blocks'], 'identities and originals verified in fresh process', flush=True)
    save(out, 'backup_recovery.json', dict(version=1, populations=results, settings='DELETE/EXTRA only',
        note='Backup/snapshot ratio is measured for uncompressed full copies. Frequency/retention and remote upload durability are modeled, not measured operator practice.'))
    return results


def environment(out, scratch):
    import importlib.metadata
    c = sqlite3.connect(':memory:')
    value = dict(version=1, python=sys.version, executable=sys.executable, platform=platform.platform(),
        machine=platform.machine(), sqlite_version=sqlite3.sqlite_version, sqlite_compile_options=c.execute('PRAGMA compile_options').fetchall(),
        packages={p:importlib.metadata.version(p) for p in ('pillow','zstandard','brotli','requests','starlette','eth-account','pytest')},
        scratch=str(scratch), byteorder=sys.byteorder, client_date='2026-11-03 America/New_York',
        no_public_peers=True, no_wal=True)
    c.close(); save(out, 'environment.json', value)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, default=HERE)
    ap.add_argument('--recover', nargs=3, type=Path)
    ap.add_argument('--copies-only', action='store_true', help='Resume completed SQLite measurements without regenerating or rewriting sources')
    args = ap.parse_args()
    if args.recover:
        assert all(ROOT/'temp' in p.resolve().parents for p in args.recover)
        recover(*args.recover); return
    out = args.output.resolve()
    assert out == HERE or ROOT/'temp' in out.parents
    out.mkdir(parents=True, exist_ok=True)
    if args.copies_only:
        source_root=Path(json.loads((out/'environment.json').read_bytes())['scratch']).resolve()
        assert ROOT/'temp' in source_root.parents
        measurements=json.loads((out/'sqlite.json').read_bytes())['populations']
        paths={};rawsets={};fingerprints={}
        for name in ('historical36','production34','meme58','balanced41'):
            path=source_root/f'{name}-full.sqlite'
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as c:
                assert c.execute('PRAGMA journal_mode').fetchone()==('delete',)
                rawsets[name]=[r[0] for r in c.execute('SELECT canonical FROM blocks ORDER BY hash')]
            last=measurements[name]['full']['observations'][-1]
            assert len(rawsets[name])==last['blocks'] and sum(map(len,rawsets[name]))==last['canonical_bytes']
            assert path.stat().st_size==last['logical_bytes']
            paths[name]=path;fingerprints[name]=sha(path.read_bytes())
        scratch=Path(tempfile.mkdtemp(prefix='task725-copies-',dir=ROOT/'temp'))
        os.environ.update(TEMP=str(scratch),TMP=str(scratch),PYTHONDONTWRITEBYTECODE='1');tempfile.tempdir=str(scratch)
        started=time.monotonic()
        with IsolatedDecoder() as decoder:
            backups(out,scratch,paths,rawsets,decoder)
        assert fingerprints=={name:sha(path.read_bytes()) for name,path in paths.items()}
        save(out,'copy_execution.json',dict(version=1,status='PASS',scratch=str(scratch),source_scratch=str(source_root),
            source_database_sha256=fingerprints,source_databases_unchanged=True,elapsed_seconds=time.monotonic()-started,
            fresh_process_timeout_seconds=1200,mode='Copies-only continuation of completed physical measurement; no source DB writes'))
        return
    scratch = Path(tempfile.mkdtemp(prefix='task725-', dir=ROOT/'temp'))
    os.environ.update(TEMP=str(scratch), TMP=str(scratch), PYTHONDONTWRITEBYTECODE='1')
    tempfile.tempdir = str(scratch)
    environment(out, scratch)
    with IsolatedDecoder() as decoder:
        groups, oracle = corpora(out, scratch, decoder)
        paths, rawsets, measurements = storage(out, scratch, groups, decoder)
        backups(out, scratch, paths, rawsets, decoder)
        transfer = load('transfer725', 'verification/task725/transfer.py')
        transfer.run(out, scratch, groups, decoder)
    print('Measurement complete', flush=True)


if __name__ == '__main__':
    main()
