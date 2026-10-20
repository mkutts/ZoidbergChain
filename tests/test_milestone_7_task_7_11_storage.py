"""Disposable v3 stores only; no active storage/config/database is opened."""
from copy import deepcopy
from dataclasses import replace
import base64
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from canonical_v3 import block, media
from canonical_v3.primitives import Context, V3Error, canonical
from canonical_v3.storage import (
    ChainSelectionError, MediaRejected, RecordConflict, SCHEMA, StorageCorruption,
    StorageUnavailable, V3Store,
)
from codec_prototype.isolated_decoder import IsolatedDecoder, Outcome, Status

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/milestone_7_v3_v1'
CTX = Context(**json.loads((FIXTURES / 'manifest.json').read_bytes())['context'])
IDENTITY = (FIXTURES / 'block-identity.json').read_bytes()
ZSTD = (FIXTURES / 'block-zstd.json').read_bytes()
HIGH_S = (FIXTURES / 'block-high-s.json').read_bytes()
PROOF = (FIXTURES / 'finality-proof.json').read_bytes()
HASH = json.loads(IDENTITY)['hash']
ZSTD_HASH = json.loads(ZSTD)['hash']
VALIDATORS = tuple(json.loads(PROOF)['validator_set'])


@pytest.fixture
def store(tmp_path):
    with IsolatedDecoder() as decoder:
        with V3Store(tmp_path / 'isolated.sqlite', CTX, decoder=decoder) as result:
            yield result


def derived_payload(raw=IDENTITY, **changes):
    payload = deepcopy(json.loads(raw)['envelope']['payload'])
    payload.update(changes)
    return block.encode_record(payload, CTX)


def hash_of(raw):
    return json.loads(raw)['hash']


def finalize(store):
    return store.finalize(PROOF, trusted_validators=VALIDATORS, equivocators=frozenset())


def corrupt_blob(store, value):
    # Simulate out-of-band disk/tool damage, not an application write API.
    connection = store.connection
    connection.execute('DROP TRIGGER immutable_blocks_update')
    connection.execute('UPDATE blocks SET canonical=? WHERE hash=?', (value, HASH))
    connection.execute(next(s for s in SCHEMA if s.startswith('CREATE TRIGGER immutable_blocks_update')))


@pytest.mark.parametrize('raw', [IDENTITY, ZSTD, HIGH_S], ids=['identity', 'zstd', 'high-s'])
def test_exact_canonical_hash_and_original_survive_reopen(store, raw):
    assert store.insert(raw)
    expected = json.loads(raw)
    assert store.get(expected['hash']) == raw
    outcome = block.reconstruct_record_media(store.get(expected['hash']), CTX, decoder=store.decoder)
    assert outcome.status == Status.VALID and outcome.original == b'a'
    assert hashlib.sha256(outcome.original).hexdigest() == expected['envelope']['payload']['media']['original_sha256']
    store.select_chain(expected['hash'], expected_tip=None)
    assert store.get_by_height(1) == raw
    path, decoder = store.path, store.decoder
    store.close()
    with V3Store(path, CTX, decoder=decoder) as reopened:
        assert reopened.get(expected['hash']) == raw
        assert reopened.get_by_height(1) == raw
        assert reopened.check_integrity()['blocks'] == 1


def test_duplicates_branches_and_searches(store):
    for raw in (IDENTITY, ZSTD, HIGH_S):
        assert store.insert(raw)
        assert not store.insert(raw)
    assert len(store.candidates_at_height(1)) == 3
    payload = json.loads(IDENTITY)['envelope']['payload']
    assert len(store.by_original_hash(payload['media']['original_sha256'])) == 3
    assert len(store.by_previous_hash(CTX.genesis_hash)) == 3
    assert len(store.by_transaction(payload['native_transactions'][0]['tx_id'])) == 3
    assert store.get('0' * 64) is None
    assert store.get_by_height(1) is None
    assert store.get_by_height(99) is None
    assert store.check_integrity() == dict(blocks=3, native_transaction_references=3, selected_blocks=0, finality_proofs=0)
    assert store.connection.execute('SELECT sum(length(canonical)) FROM blocks').fetchone()[0] == sum(map(len, (IDENTITY, ZSTD, HIGH_S)))


def test_conflicting_record_is_preserved(store):
    store.insert(IDENTITY)
    corrupt_blob(store, b'{}')
    with pytest.raises(RecordConflict):
        store.insert(IDENTITY)
    assert store.connection.execute('SELECT canonical FROM blocks').fetchone()[0] == b'{}'


@pytest.mark.parametrize('raw', [b'{}', b'null', b'\xff', b'{}\n', b'{"x":1,"x":1}', b'x' * 3145729],
                         ids=['object', 'null', 'utf8', 'newline', 'duplicate', 'oversize'])
def test_invalid_incoming_format_never_commits(store, raw):
    with pytest.raises(V3Error):
        store.insert(raw)
    assert store.check_integrity()['blocks'] == 0


@pytest.mark.parametrize('blob', [b'{}', b'\xff', IDENTITY.replace(b'"index":1', b'"index":2'), ZSTD],
                         ids=['object', 'utf8', 'hash-tamper', 'wrong-key'])
def test_corrupted_stored_bytes_are_local_errors(store, blob):
    store.insert(IDENTITY)
    corrupt_blob(store, blob)
    for operation in (lambda: store.get(HASH), store.check_integrity, store.rebuild_indexes):
        with pytest.raises(StorageCorruption):
            operation()


def test_sql_immutability_and_blob_constraints(store):
    store.insert(IDENTITY)
    for sql in ('DELETE FROM blocks', "UPDATE blocks SET canonical=x'7b7d'"):
        with pytest.raises(sqlite3.IntegrityError, match='immutable'):
            store.connection.execute(sql)
    for value in ('{}', b'', b'x' * 3145729):
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute('INSERT INTO blocks VALUES(?,?)', ('0' * 64, value))


@pytest.mark.parametrize('damage', [
    "UPDATE block_index SET height=77",
    "UPDATE block_index SET previous_hash='bad'",
    "UPDATE block_index SET original_hash='bad'",
    'DELETE FROM block_index',
    "UPDATE transaction_index SET tx_id='bad'",
    'DELETE FROM transaction_index',
    'DELETE FROM canonical_chain',
    'UPDATE canonical_chain SET height=77',
])
def test_index_damage_detected_and_rebuildable(store, damage):
    store.insert(IDENTITY)
    store.select_chain(HASH, expected_tip=None)
    finalize(store)
    store.connection.execute(damage)
    with pytest.raises(StorageCorruption):
        store.check_integrity()
    assert store.rebuild_indexes()['blocks'] == 1
    assert store.get_by_height(1) == IDENTITY
    assert store.is_finalized(HASH)


def test_atomic_block_and_index_rollback(store, monkeypatch):
    original = store._put_indexes

    def fail(connection, record):
        original(connection, record)
        raise RuntimeError('injected failure after all derived writes')

    monkeypatch.setattr(store, '_put_indexes', fail)
    with pytest.raises(RuntimeError, match='injected'):
        store.insert(IDENTITY)
    assert store.check_integrity()['blocks'] == 0


def test_failed_rebuild_rolls_back_all_indexes(store, monkeypatch):
    store.insert(IDENTITY)
    store.insert(ZSTD)
    before = store.connection.execute('SELECT * FROM block_index ORDER BY hash').fetchall()
    original = store._put_indexes

    def fail(connection, record):
        original(connection, record)
        raise RuntimeError('rebuild interrupted')

    monkeypatch.setattr(store, '_put_indexes', fail)
    with pytest.raises(RuntimeError):
        store.rebuild_indexes()
    assert store.connection.execute('SELECT * FROM block_index ORDER BY hash').fetchall() == before
    assert store.check_integrity()['blocks'] == 2


def test_selected_lineage_reorganization_cas_and_finality(store):
    child = derived_payload(index=2, previous_hash=HASH)
    alternative_child = derived_payload(ZSTD, index=2, previous_hash=ZSTD_HASH)
    for raw in (IDENTITY, ZSTD, child, alternative_child):
        store.insert(raw)
    store.select_chain(hash_of(child), expected_tip=None)
    with pytest.raises(ChainSelectionError, match='stale'):
        store.select_chain(ZSTD_HASH, expected_tip=None)
    store.select_chain(hash_of(alternative_child), expected_tip=hash_of(child))
    assert store.get_by_height(1) == ZSTD
    assert store.get_by_height(2) == alternative_child
    store.select_chain(hash_of(child), expected_tip=hash_of(alternative_child))
    assert finalize(store)
    assert not finalize(store)
    assert store.is_finalized(HASH) and not store.is_finalized(hash_of(child))
    with pytest.raises(ChainSelectionError, match='finalized'):
        store.select_chain(hash_of(alternative_child), expected_tip=hash_of(child))
    with pytest.raises(ChainSelectionError, match='finalized'):
        store.select_chain(None, expected_tip=hash_of(child))
    store.select_chain(HASH, expected_tip=hash_of(child))
    assert store.selected_tip() == HASH
    assert store.get(hash_of(alternative_child)) == alternative_child
    assert store.rebuild_indexes()['finality_proofs'] == 1
    with pytest.raises(sqlite3.IntegrityError, match='immutable'):
        store.connection.execute('DELETE FROM finality')


def test_finality_marks_ancestors_and_checks_external_trust(store):
    from canonical_v3.finality import finality_bytes
    from eth_account import Account
    from eth_account.messages import encode_defunct
    child = derived_payload(index=2, previous_hash=HASH)
    for raw in (IDENTITY, child):
        store.insert(raw)
    proof = json.loads(PROOF)
    proof.update(block_height=2, block_hash=hash_of(child))
    attestation = proof['attestations'][0]
    attestation.update(block_height=2, block_hash=hash_of(child))
    payload = {key: attestation[key] for key in ('attestation_version', 'validator_address', 'block_height', 'block_hash')}
    message = finality_bytes(payload, CTX)
    attestation.update(message=message.decode(), signature='0x' + Account.sign_message(
        encode_defunct(primitive=message), bytes([17]) * 32).signature.hex())
    raw_proof = canonical(proof)
    with pytest.raises(ChainSelectionError):
        store.finalize(raw_proof, trusted_validators=VALIDATORS, equivocators=frozenset())
    store.select_chain(hash_of(child), expected_tip=None)
    for kwargs in [dict(trusted_validators=('0x' + '2' * 40,), equivocators=frozenset()),
                   dict(trusted_validators=VALIDATORS, equivocators=frozenset(VALIDATORS))]:
        with pytest.raises(V3Error):
            store.finalize(raw_proof, **kwargs)
    store.finalize(raw_proof, trusted_validators=VALIDATORS, equivocators=frozenset())
    assert store.is_finalized(HASH) and store.is_finalized(hash_of(child))
    with pytest.raises(ChainSelectionError):
        store.select_chain(HASH, expected_tip=hash_of(child))


@pytest.mark.parametrize('changes', [dict(index=3, previous_hash=HASH), dict(index=2, previous_hash='e' * 64),
                                   dict(index=1, previous_hash='e' * 64)])
def test_disconnected_or_wrong_height_candidate_cannot_be_selected(store, changes):
    store.insert(IDENTITY)
    raw = derived_payload(**changes)
    store.insert(raw)
    with pytest.raises(ChainSelectionError):
        store.select_chain(hash_of(raw), expected_tip=None)
    assert store.selected_tip() is None


def test_atomic_reorg_rollback(store):
    store.insert(IDENTITY)
    store.insert(ZSTD)
    store.select_chain(HASH, expected_tip=None)

    def deny(action, arg1, arg2, *_):
        return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_UPDATE and arg1 == 'settings' else sqlite3.SQLITE_OK

    store.connection.set_authorizer(deny)
    with pytest.raises(StorageCorruption):
        store.select_chain(ZSTD_HASH, expected_tip=HASH)
    store.connection.set_authorizer(None)
    assert store.selected_tip() == HASH
    assert store.get_by_height(1) == IDENTITY


@pytest.mark.parametrize('committed', [False, True])
def test_process_death_rollback_and_committed_wal_recovery(tmp_path, committed):
    path = tmp_path / 'crash.sqlite'
    code = '''
import os, sys, json
from pathlib import Path
from canonical_v3.primitives import Context
from canonical_v3.storage import V3Store
root, path, committed = sys.argv[1:]
fixtures = Path(root) / 'tests/fixtures/milestone_7_v3_v1'
ctx = Context(**json.loads((fixtures / 'manifest.json').read_bytes())['context'])
class CrashStore(V3Store):
    def _put_indexes(self, connection, record):
        super()._put_indexes(connection, record)
        if committed == 'False':
            os._exit(17)
store = CrashStore(path, ctx)
store.connection.execute('PRAGMA cache_size=1')  # Force uncommitted page spill.
store.insert((fixtures / 'block-identity.json').read_bytes())
os._exit(17)
'''
    result = subprocess.run([sys.executable, '-B', '-c', code, str(ROOT), str(path), str(committed)],
                            cwd=ROOT, capture_output=True, timeout=45)
    assert result.returncode == 17, result.stderr.decode()
    assert Path(str(path) + '-wal').stat().st_size > 0
    with V3Store(path, CTX) as recovered:
        assert recovered.check_integrity()['blocks'] == int(committed)
        assert recovered.get(HASH) == (IDENTITY if committed else None)


def test_process_death_during_reorganization(store):
    store.insert(IDENTITY)
    store.insert(ZSTD)
    store.select_chain(HASH, expected_tip=None)
    path = store.path
    store.close()
    code = '''
import os, sys, json, sqlite3
from pathlib import Path
from canonical_v3.primitives import Context
from canonical_v3.storage import V3Store
fixtures = Path(sys.argv[1]) / 'tests/fixtures/milestone_7_v3_v1'
ctx = Context(**json.loads((fixtures / 'manifest.json').read_bytes())['context'])
store = V3Store(sys.argv[2], ctx)
def crash(action, arg1, arg2, *args):
    if action == sqlite3.SQLITE_UPDATE and arg1 == 'settings':
        os._exit(19)
    return sqlite3.SQLITE_OK
store.connection.set_authorizer(crash)
store.select_chain(sys.argv[3], expected_tip=sys.argv[4])
'''
    result = subprocess.run([sys.executable, '-B', '-c', code, str(ROOT), str(path), ZSTD_HASH, HASH],
                            cwd=ROOT, capture_output=True, timeout=45)
    assert result.returncode == 19, result.stderr.decode()
    with V3Store(path, CTX) as recovered:
        assert recovered.check_integrity()['selected_blocks'] == 1
        assert recovered.selected_tip() == HASH
        assert recovered.get_by_height(1) == IDENTITY


def test_backup_restore_uncheckpointed_wal_and_index_rebuild(store, tmp_path):
    store.insert(IDENTITY)
    store.select_chain(HASH, expected_tip=None)
    finalize(store)
    assert Path(str(store.path) + '-wal').stat().st_size > 0
    backup = store.backup(tmp_path / 'backup.sqlite')
    restored = V3Store.restore(backup, tmp_path / 'restore.sqlite', CTX, decoder=store.decoder)
    with V3Store(restored, CTX, decoder=store.decoder) as recovered:
        assert recovered.get(HASH) == IDENTITY
        assert recovered.is_finalized(HASH)
        recovered.connection.execute('DELETE FROM transaction_index')
        assert recovered.rebuild_indexes()['native_transaction_references'] == 1
    with pytest.raises(FileExistsError):
        store.backup(store.path)
    with pytest.raises(FileExistsError):
        V3Store.restore(backup, restored, CTX)
    with pytest.raises(FileNotFoundError):
        V3Store.restore(tmp_path / 'absent.sqlite', tmp_path / 'new.sqlite', CTX)
    assert store.checkpoint() == (0, 0, 0)
    assert Path(str(store.path) + '-wal').stat().st_size == 0
    assert store.get(HASH) == IDENTITY


def test_online_backup_uses_verified_snapshot(store, tmp_path, monkeypatch):
    store.insert(IDENTITY)
    original = store._integrity

    def verify_then_concurrent_commit(connection):
        result = original(connection)
        with V3Store(store.path, CTX, decoder=store.decoder) as writer:
            writer.insert(ZSTD)
        return result

    monkeypatch.setattr(store, '_integrity', verify_then_concurrent_commit)
    backup = store.backup(tmp_path / 'snapshot.sqlite')
    with V3Store(backup, CTX, decoder=store.decoder) as recovered:
        assert recovered.check_integrity()['blocks'] == 1
        assert recovered.get(HASH) == IDENTITY
        assert recovered.get(ZSTD_HASH) is None
    assert store.get(ZSTD_HASH) == ZSTD


def test_interrupted_sqlite_backup_does_not_damage_source(store, tmp_path):
    store.insert(IDENTITY)
    real = store.connection

    class InterruptedBackup:
        def __getattr__(self, name):
            return getattr(real, name)

        def backup(self, destination):
            def interrupt(status, remaining, total):
                assert remaining > 0  # Interrupt an incomplete page copy.
                raise RuntimeError('backup interrupted after first page')
            real.backup(destination, pages=1, progress=interrupt)

    target = tmp_path / 'interrupted.sqlite'
    store.connection = InterruptedBackup()
    try:
        with pytest.raises(RuntimeError, match='backup interrupted'):
            store.backup(target)
    finally:
        store.connection = real
    assert not real.in_transaction
    assert store.get(HASH) == IDENTITY
    assert store.check_integrity()['blocks'] == 1
    with pytest.raises(StorageCorruption):
        V3Store.restore(target, tmp_path / 'invalid-restore.sqlite', CTX)


def test_checkpoint_busy_reader_and_recovery(store):
    store.insert(IDENTITY)
    reader = sqlite3.connect(store.path, isolation_level=None)
    try:
        reader.execute('BEGIN')
        reader.execute('SELECT count(*) FROM blocks').fetchone()
        store.insert(ZSTD)
        store.connection.execute('PRAGMA busy_timeout=1')
        assert store.checkpoint()[0] == 1
        assert store.get(ZSTD_HASH) == ZSTD
    finally:
        reader.close()
    assert store.checkpoint() == (0, 0, 0)
    assert store.check_integrity()['blocks'] == 2


def test_missing_selected_record_damaged_finality_and_corrupt_database(store, tmp_path):
    store.insert(IDENTITY)
    store.select_chain(HASH, expected_tip=None)
    finalize(store)
    store.connection.execute('DROP TRIGGER immutable_finality_update')
    store.connection.execute("UPDATE finality SET proof=x'7b7d'")
    store.connection.execute(next(s for s in SCHEMA if s.startswith('CREATE TRIGGER immutable_finality_update')))
    with pytest.raises(StorageCorruption, match='finality'):
        store.check_integrity()
    with pytest.raises(StorageCorruption):
        store.backup(tmp_path / 'bad-backup.sqlite')
    path = tmp_path / 'damaged.sqlite'
    path.write_bytes(b'not a SQLite database' * 256)
    with pytest.raises(StorageCorruption):
        V3Store(path, CTX)


def test_missing_selected_ancestor_is_not_repairable_from_indexes(store):
    store.insert(IDENTITY)
    child = derived_payload(index=2, previous_hash=HASH)
    store.insert(child)
    store.select_chain(hash_of(child), expected_tip=None)
    store.connection.execute('PRAGMA foreign_keys=OFF')
    store.connection.execute('DROP TRIGGER immutable_blocks_delete')
    store.connection.execute('DELETE FROM blocks WHERE hash=?', (HASH,))
    store.connection.execute(next(s for s in SCHEMA if s.startswith('CREATE TRIGGER immutable_blocks_delete')))
    for operation in (store.check_integrity, store.rebuild_indexes, lambda: store.get_by_height(2)):
        with pytest.raises(StorageCorruption):
            operation()


@pytest.mark.parametrize('status', [Status.INDETERMINATE_LOCAL_FAILURE, Status.INVALID])
def test_worker_outcomes_are_preserved_for_incoming_and_local_storage(store, monkeypatch, status):
    store.insert(IDENTITY)
    outcome = Outcome(status, reason='test-local' if status == Status.INDETERMINATE_LOCAL_FAILURE else None,
                      stage='test', code='test')
    monkeypatch.setattr(IsolatedDecoder, 'validate', lambda *_: outcome)
    with pytest.raises(StorageUnavailable if status == Status.INDETERMINATE_LOCAL_FAILURE else MediaRejected) as error:
        store.insert(ZSTD)
    assert error.value.outcome is outcome
    with pytest.raises(StorageUnavailable if status == Status.INDETERMINATE_LOCAL_FAILURE else StorageCorruption):
        store.get(HASH)
    assert store.connection.execute('SELECT count(*) FROM blocks').fetchone()[0] == 1


def test_worker_cannot_be_bypassed(store):
    store.decoder = object()
    with pytest.raises(V3Error, match='isolated_decoder_required'):
        store.insert(IDENTITY)
    assert store.connection.execute('SELECT count(*) FROM blocks').fetchone()[0] == 0


def test_real_corrupted_compressed_media_incoming_vs_stored(store):
    payload = deepcopy(json.loads(ZSTD)['envelope']['payload'])
    encoded = bytearray(base64.b64decode(payload['media']['payload']))
    encoded[-1] ^= 1
    payload['media']['payload'] = base64.b64encode(encoded).decode('ascii')
    raw = block.encode_record(payload, CTX)  # Format/hash valid; codec checksum invalid.
    with pytest.raises(MediaRejected) as incoming:
        store.insert(raw)
    assert incoming.value.outcome.status == Status.INVALID
    assert store.check_integrity()['blocks'] == 0
    # Simulate a corrupt record with a matching local primary key: codec failure
    # is still a local corruption error when encountered in retained storage.
    store.connection.execute('INSERT INTO blocks VALUES(?,?)', (hash_of(raw), raw))
    with pytest.raises(StorageCorruption, match='media'):
        store.get(hash_of(raw))


@pytest.mark.parametrize('value', ['{}', b'x' * 3145729], ids=['text-type', 'oversize'])
def test_corrupt_blob_bound_checked_before_fetch(store, value):
    store.insert(IDENTITY)
    store.connection.execute('PRAGMA ignore_check_constraints=ON')
    corrupt_blob(store, value)
    with pytest.raises(StorageCorruption, match='type/size'):
        store.get(HASH)


def test_finality_conflict_and_interrupted_write(store):
    store.insert(IDENTITY)
    store.select_chain(HASH, expected_tip=None)

    def deny(action, arg1, *_):
        return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_INSERT and arg1 == 'finality' else sqlite3.SQLITE_OK

    store.connection.set_authorizer(deny)
    with pytest.raises(StorageCorruption):
        finalize(store)
    store.connection.set_authorizer(None)
    assert not store.is_finalized(HASH)
    assert store.check_integrity()['finality_proofs'] == 0
    finalize(store)
    with pytest.raises(RecordConflict):
        store.finalize(PROOF, trusted_validators=VALIDATORS, equivocators=frozenset({'0x' + '2' * 40}))
    assert store.check_integrity()['finality_proofs'] == 1


def test_external_snapshot_anchor(tmp_path):
    with V3Store(tmp_path / 'snapshot-anchor.sqlite', CTX, anchor_height=100, anchor_hash='e' * 64) as snapshot:
        raw = derived_payload(index=101, previous_hash='e' * 64)
        snapshot.insert(raw)
        snapshot.select_chain(hash_of(raw), expected_tip=None)
        assert snapshot.get_by_height(101) == raw
        assert snapshot.get_by_height(1) is None
        assert not snapshot.is_finalized(hash_of(raw))
        assert snapshot.rebuild_indexes()['selected_blocks'] == 1


def test_physical_bit_flip_detected_even_when_sqlite_pages_are_valid(store):
    store.insert(IDENTITY)
    assert store.checkpoint() == (0, 0, 0)
    path, decoder = store.path, store.decoder
    store.close()
    contents = path.read_bytes()
    needle = b'"payload":"YQ=="'
    assert contents.count(needle) == 1
    path.write_bytes(contents.replace(needle, b'"payload":"Yg=="'))
    with V3Store(path, CTX, decoder=decoder) as damaged:
        assert damaged.connection.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        with pytest.raises(StorageCorruption, match='block_hash'):
            damaged.check_integrity()


def test_schema_context_anchor_and_active_database_refusal(tmp_path):
    path = tmp_path / 'unknown.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE storage_sections (name TEXT PRIMARY KEY,json_data TEXT)')
    before = path.read_bytes()
    with pytest.raises(StorageCorruption, match='schema'):
        V3Store(path, CTX)
    assert path.read_bytes() == before
    empty = tmp_path / 'existing-empty.sqlite'
    empty.touch()
    with pytest.raises(StorageCorruption):
        V3Store(empty, CTX)
    path = tmp_path / 'valid.sqlite'
    with V3Store(path, CTX):
        pass
    with pytest.raises(StorageCorruption, match='context'):
        V3Store(path, replace(CTX, application='other-vector'))
    with pytest.raises(ValueError, match='genesis'):
        V3Store(tmp_path / 'wrong-anchor.sqlite', CTX, anchor_hash='e' * 64)
    with V3Store(path, CTX) as valid:
        valid.connection.execute('PRAGMA user_version=99')
    with pytest.raises(StorageCorruption, match='version'):
        V3Store(path, CTX)


def test_multiple_connections_duplicate_and_stale_selection(store):
    with V3Store(store.path, CTX, decoder=store.decoder) as other:
        assert store.insert(IDENTITY)
        assert not other.insert(IDENTITY)
        store.select_chain(HASH, expected_tip=None)
        with pytest.raises(ChainSelectionError, match='stale'):
            other.select_chain(None, expected_tip=None)
        assert other.selected_tip() == HASH


def test_no_active_import_or_migration_connections():
    active = [ROOT / name for name in ('storage.py', 'storage_tools.py', 'storage_migration.py', 'config.py',
                                      'block.py', 'blockchain.py', 'peer_sync.py', 'sync.py')]
    active += list((ROOT / 'services').glob('*.py'))
    active += list((ROOT / 'api_routers').glob('*.py'))
    assert all('canonical_v3' not in path.read_text(encoding='utf-8') for path in active)
