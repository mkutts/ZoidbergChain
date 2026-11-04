"""Current 7.17E persistence contract, independently of frozen 7.17C witnesses.

Real canonical messages/signatures and real file-backed transactions. The small
facade stubs unrelated media/chain validation and reconstruction only; the real
Blockchain submission/cache/save methods, service and storage boundary execute.
Historical full-chain/API/reorg tests exercise the ordinary complete facade.
"""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from types import MethodType, SimpleNamespace
from threading import Event

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from blockchain import Blockchain
from protocol_v1 import PUBLIC_TESTNET_V1_NETWORK_ID as NETWORK
from protocol_v1_genesis import GenesisValidationError
from protocol_v1_finality import build_protocol_v1_finality_attestation, build_protocol_v1_finality_attestation_message
from services import FinalityAttestationError, FinalityService
from storage import FinalityStateConflictError, StorageCorruptionError, create_storage_backend


TARGET = 'a' * 64


def backend(root, kind='sqlite'):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    return create_storage_backend(kind, blockchain_file=str(root / 'chain.json'),
        peers_file=str(root / 'peers.json'), sqlite_db_path=str(root / 'chain.db'))


def initial_chain(count=1):
    return [dict(index=h, hash=chr(97 + h) * 64,
        previous_hash=chr(96 + h) * 64 if h else '0') for h in range(count)]


def node(store, validators, *, seed=True):
    if seed and not (store.load_blockchain_document() or {}).get('chain'):
        store.save_blockchain_document(dict(chain=initial_chain(), submissions=[], mint_queue=[],
            finality_attestations=[], finalized_blocks=[]))
    obj = Blockchain.__new__(Blockchain)
    obj.validator_set = tuple(validators)
    obj._finality_service = FinalityService()
    obj.finality_attestations, obj.finalized_blocks = [], []
    obj.chain = []
    obj.storage = store
    obj._report_reviewer_index = {}
    obj._set_report_reviewer_index = lambda *args, **kwargs: None
    obj.reconcile_canonical_reviewer_states = lambda: None
    obj.protocol_v1_network_id = lambda: NETWORK
    obj.is_chain_valid = lambda chain: True
    obj.calculate_hash_from_dict = lambda block: block['hash']

    def restore(self, document):
        self._check_finality_cache_transition(document)
        self.chain = [SimpleNamespace(index=b['index'], hash=b['hash'],
            to_dict=lambda b=b: deepcopy(b)) for b in document['chain']]
        self._publish_finality_cache(document)

    obj._restore_blockchain_state_document = MethodType(restore, obj)
    obj._serialize_blockchain_state = lambda: deepcopy(dict(chain=obj.chain_to_dicts(obj.chain),
        submissions=[], mint_queue=[], finality_attestations=obj.finality_attestations,
        finalized_blocks=obj.finalized_blocks))
    restore(obj, store.load_blockchain_document())
    return obj


@pytest.fixture
def votes():
    accounts = [Account.create() for _ in range(4)]
    validators = tuple(sorted(a.address.lower() for a in accounts))

    def sign(index, target=TARGET, height=0):
        account = accounts[index]
        message = build_protocol_v1_finality_attestation_message(validator_address=account.address,
            block_height=height, block_hash=target, network_id=NETWORK)
        signature = Account.sign_message(encode_defunct(text=message), account.key).signature.hex()
        return build_protocol_v1_finality_attestation(validator_address=account.address,
            block_height=height, block_hash=target, network_id=NETWORK, signature=signature)
    return validators, sign


def assert_state(store, count, finalized):
    durable = store.load_blockchain_document()
    assert len(durable['finality_attestations']) == count
    assert len(durable['finalized_blocks']) == finalized
    if finalized:
        proof = durable['finalized_blocks'][0]
        FinalityService().validate_finalization_evidence(proof, expected_network_id=NETWORK)
        assert len({v['validator_address'] for v in proof['attestations']}) >= 3
        assert proof['block_hash'] == TARGET
    return durable


@pytest.mark.parametrize('kind', ['json', 'sqlite'])
@pytest.mark.parametrize('shared_facade', [False, True])
def test_concurrent_distinct_votes_and_exact_retries_are_a_durable_union(tmp_path, votes, kind, shared_facade):
    validators, sign = votes
    store = backend(tmp_path, kind)
    first = node(store, validators)
    nodes = [first] * 4 if shared_facade else [first] + [node(backend(tmp_path, kind), validators) for _ in range(3)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda i: nodes[i % 4].submit_validator_finality_attestation(sign(i % 4)), range(16)))
    assert sum(r['status'] == 'accepted' for r in results) == 4
    assert sum(r['status'] == 'duplicate' for r in results) == 12
    durable = assert_state(store, 4, 1)
    assert len(durable['finalized_blocks'][0]['attestations']) == 3
    current = node(backend(tmp_path, kind), validators)
    assert current.get_finality_evidence(TARGET) == durable['finalized_blocks'][0]


def test_alternate_valid_signature_is_one_logical_vote(tmp_path, votes):
    validators, sign = votes
    current = node(backend(tmp_path), validators)
    vote = sign(0)
    variant = deepcopy(vote)
    raw = bytes.fromhex(vote['signature'].removeprefix('0x'))
    order = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
    variant['signature'] = (raw[:32] + (order - int.from_bytes(raw[32:64], 'big')).to_bytes(32, 'big')
        + bytes([27 + (1 - ((raw[64] - 27) % 2))])).hex()
    current.submit_validator_finality_attestation(vote)
    assert current.submit_validator_finality_attestation(variant)['status'] == 'duplicate'
    assert_state(current.storage, 1, 0)


@pytest.mark.parametrize('kind', ['json', 'sqlite'])
def test_stale_facade_low_level_save_and_callback_cannot_erase_votes_or_proof(tmp_path, votes, kind):
    validators, sign = votes
    store = backend(tmp_path, kind)
    current, stale = node(store, validators), node(backend(tmp_path, kind), validators)
    stale_document = store.load_blockchain_document()
    current.submit_validator_finality_attestations([sign(i) for i in range(3)])
    stale.save_blockchain()
    assert stale.get_finalized_head()['block_hash'] == TARGET
    store.save_blockchain_document(stale_document)
    store.atomic_update_blockchain_document(lambda durable: deepcopy(stale_document))
    assert_state(store, 3, 1)


@pytest.mark.parametrize('kind', ['json', 'sqlite'])
@pytest.mark.parametrize('higher', [False, True])
def test_conflicting_equal_height_or_higher_ancestry_is_rejected(tmp_path, votes, kind, higher):
    validators, sign = votes
    store = backend(tmp_path, kind)
    current = node(store, validators)
    current.submit_validator_finality_attestations([sign(i) for i in range(3)])
    before = store.load_blockchain_document()
    wrong = deepcopy(before)
    wrong['chain'][0]['hash'] = 'f' * 64
    if higher:
        wrong['chain'].append(dict(index=1, hash='e' * 64, previous_hash='f' * 64))
        proof = deepcopy(before['finalized_blocks'][0])
        proof.update(block_height=1, block_hash='e' * 64,
            attestations=[sign(i, 'e' * 64, 1) for i in range(3)])
        wrong['finalized_blocks'] = [proof]
    else:
        wrong['finalized_blocks'][0]['block_hash'] = 'f' * 64
    with pytest.raises(FinalityStateConflictError):
        store.save_blockchain_document(wrong)
    assert store.load_blockchain_document() == before


def test_failed_write_and_duplicate_retry_never_publish_uncommitted_finality(tmp_path, votes):
    validators, sign = votes
    current = node(backend(tmp_path), validators)
    current.submit_validator_finality_attestations([sign(0), sign(1)])
    before = current.storage.load_blockchain_document()
    connect = current.storage._connect

    @contextmanager
    def fail_after_writes():
        with connect() as connection:
            yield connection
            if connection.in_transaction:
                assert current.finalized_blocks == []
                raise OSError('injected precommit I/O failure')

    current.storage._connect = fail_after_writes
    with pytest.raises(OSError, match='precommit'):
        current.submit_validator_finality_attestation(sign(2))
    assert current.finalized_blocks == []
    assert current.storage.load_blockchain_document() == before
    current.storage._connect = connect
    assert current.submit_validator_finality_attestation(sign(2))['status'] == 'accepted'
    assert current.submit_validator_finality_attestation(sign(2))['status'] == 'duplicate'
    assert_state(current.storage, 3, 1)


def test_commit_succeeded_but_response_failed_rereads_durable_outcome(tmp_path, votes):
    validators, sign = votes
    current = node(backend(tmp_path), validators)
    current.submit_validator_finality_attestations([sign(0), sign(1)])
    def fault(stage):
        if stage == 'after_commit_before_publish':
            raise OSError('lost acknowledgement')
    current._finality_fault_injector = fault
    with pytest.raises(OSError, match='acknowledgement'):
        current.submit_validator_finality_attestation(sign(2))
    assert current.get_finalized_head()['block_hash'] == TARGET
    assert_state(current.storage, 3, 1)
    current._finality_fault_injector = None
    assert current.submit_validator_finality_attestation(sign(2))['status'] == 'duplicate'


def test_unknown_outcome_and_failed_reload_withholds_finality_queries(tmp_path, votes, monkeypatch):
    validators, sign = votes
    current = node(backend(tmp_path), validators)
    current.submit_validator_finality_attestations([sign(0), sign(1)])
    load = current.storage.load_blockchain_document
    def fault(stage):
        if stage == 'after_commit_before_publish':
            monkeypatch.setattr(current.storage, 'load_blockchain_document', lambda: (_ for _ in ()).throw(OSError('offline')))
            raise OSError('unknown outcome')
    current._finality_fault_injector = fault
    with pytest.raises(OSError, match='unknown'):
        current.submit_validator_finality_attestation(sign(2))
    assert current.finalized_blocks == []
    for query in (lambda: current.get_finalized_head(), lambda: current.get_block_chain_state(TARGET),
                  lambda: current.get_finality_evidence(TARGET)):
        with pytest.raises(RuntimeError, match='unavailable'):
            query()
    monkeypatch.setattr(current.storage, 'load_blockchain_document', load)
    current._finality_fault_injector = None
    assert current.submit_validator_finality_attestation(sign(2))['status'] == 'duplicate'
    assert current.get_finalized_head()['block_hash'] == TARGET


def test_failed_chain_validation_cannot_republish_available_finality_during_recovery(tmp_path, votes):
    validators, sign = votes
    current = node(backend(tmp_path), validators)
    current.submit_validator_finality_attestations([sign(0), sign(1)])
    current.is_chain_valid = lambda chain: False
    with pytest.raises(FinalityAttestationError, match='chain validation'):
        current.submit_validator_finality_attestation(sign(2))
    with pytest.raises(RuntimeError, match='unavailable'):
        current.get_finalized_head()
    assert_state(current.storage, 2, 0)
    current.is_chain_valid = lambda chain: True
    current.submit_validator_finality_attestation(sign(2))
    assert_state(current.storage, 3, 1)


def test_busy_is_operational_and_leaves_no_partial_state(tmp_path, votes):
    validators, sign = votes
    current = node(backend(tmp_path), validators)
    connect = current.storage._connect
    @contextmanager
    def short_timeout():
        with connect() as connection:
            connection.execute('PRAGMA busy_timeout=1')
            yield connection
    current.storage._connect = short_timeout
    with sqlite3.connect(current.storage.sqlite_db_path) as blocker:
        blocker.execute('BEGIN IMMEDIATE')
        with pytest.raises(sqlite3.OperationalError, match='locked'):
            current.submit_validator_finality_attestation(sign(0))
    assert current.finalized_blocks == []
    assert_state(current.storage, 0, 0)


def test_real_sqlite_full_rolls_back_vote_and_certificate(tmp_path, votes):
    validators, sign = votes
    current = node(backend(tmp_path), validators)
    current.submit_validator_finality_attestations([sign(0), sign(1)])
    connect = current.storage._connect
    with connect() as connection:
        connection.execute('VACUUM')
    before = current.storage.load_blockchain_document()
    @contextmanager
    def full_disk():
        with connect() as connection:
            pages = connection.execute('PRAGMA page_count').fetchone()[0]
            connection.execute(f'PRAGMA max_page_count={pages}')
            yield connection
    current.storage._connect = full_disk
    with pytest.raises(sqlite3.OperationalError) as error:
        current.submit_validator_finality_attestation(sign(2))
    assert error.value.sqlite_errorcode == sqlite3.SQLITE_FULL
    assert current.finalized_blocks == []
    assert current.storage.load_blockchain_document() == before
    current.storage._connect = connect
    current.submit_validator_finality_attestation(sign(2))
    assert_state(current.storage, 3, 1)


@pytest.mark.parametrize('failure', ['commit-denied', 'commit-busy'])
def test_actual_sqlite_commit_failure_keeps_cache_and_database_unpromoted(tmp_path, votes, failure):
    validators, sign = votes
    current = node(backend(tmp_path), validators)
    current.submit_validator_finality_attestations([sign(0), sign(1)])
    before = current.storage.load_blockchain_document()
    connect = current.storage._connect
    @contextmanager
    def failing_commit():
        with connect() as connection:
            if failure == 'commit-denied':
                connection.set_authorizer(lambda action, arg1, *args:
                    sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_TRANSACTION and arg1 == 'COMMIT' else sqlite3.SQLITE_OK)
            else:
                connection.execute('PRAGMA busy_timeout=1')
            yield connection
    current.storage._connect = failing_commit
    reader = sqlite3.connect(current.storage.sqlite_db_path)
    try:
        if failure == 'commit-busy':
            reader.execute('BEGIN')
            reader.execute('SELECT * FROM storage_sections').fetchall()
        with pytest.raises(sqlite3.DatabaseError) as error:
            current.submit_validator_finality_attestation(sign(2))
        assert error.value.sqlite_errorcode == (sqlite3.SQLITE_AUTH if failure == 'commit-denied' else sqlite3.SQLITE_BUSY)
        assert current.storage.load_blockchain_document() == before
        assert current.finalized_blocks == []
    finally:
        reader.close()
    current.storage._connect = connect
    current.submit_validator_finality_attestation(sign(2))
    assert_state(current.storage, 3, 1)


def test_conflicting_vote_invalid_batch_and_forged_duplicate_do_not_overwrite(tmp_path, votes):
    validators, sign = votes
    current = node(backend(tmp_path), validators)
    current.submit_validator_finality_attestation(sign(0))
    before = current.storage.load_blockchain_document()
    with pytest.raises(FinalityAttestationError, match='exact canonical'):
        current.submit_validator_finality_attestation(sign(0, 'f' * 64))
    bad = sign(2)
    bad['signature'] = '0x00'
    with pytest.raises(FinalityAttestationError, match='signature'):
        current.submit_validator_finality_attestations([sign(1), bad])
    forged = deepcopy(before)
    forged['finality_attestations'][0]['block_hash'] = 'f' * 64
    with pytest.raises(FinalityStateConflictError):
        current.storage.save_blockchain_document(forged)
    assert current.storage.load_blockchain_document() == before
    assert len(current.finality_attestations) == 1


def test_settings_connection_ownership_and_nested_begin(tmp_path):
    store = backend(tmp_path)
    with store._connect() as connection:
        assert connection.execute('PRAGMA journal_mode').fetchone() == ('delete',)
        assert connection.execute('PRAGMA synchronous').fetchone() == (3,)
        assert connection.execute('PRAGMA busy_timeout').fetchone() == (30000,)
        connection.execute('BEGIN IMMEDIATE')
        with pytest.raises(sqlite3.OperationalError, match='transaction'):
            connection.execute('BEGIN IMMEDIATE')
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        connection.execute('SELECT 1')
    # No automatic WAL conversion, including on this affected runtime.
    with sqlite3.connect(store.sqlite_db_path) as connection:
        assert connection.execute('PRAGMA journal_mode=WAL').fetchone() == ('wal',)
    with pytest.raises(RuntimeError, match='DELETE'):
        backend(tmp_path)
    with sqlite3.connect(store.sqlite_db_path) as connection:
        assert connection.execute('PRAGMA journal_mode').fetchone() == ('wal',)


def test_stale_refresh_cannot_regress_committed_cache(tmp_path, votes):
    validators, sign = votes
    current = node(backend(tmp_path), validators)
    stale = current.storage.load_blockchain_document()
    current.submit_validator_finality_attestations([sign(i) for i in range(3)])
    with pytest.raises(FinalityStateConflictError, match='Stale refresh'):
        current._restore_blockchain_state_document(stale)
    assert current.get_finalized_head()['block_hash'] == TARGET
    for _ in range(3):
        recovered = node(backend(tmp_path), validators)
        assert recovered.get_finality_evidence(TARGET) == current.get_finality_evidence(TARGET)


def test_gapped_finality_and_guarded_unfinalized_reorg_preserve_existing_semantics(tmp_path, votes):
    validators, sign = votes
    store = backend(tmp_path)
    store.save_blockchain_document(dict(chain=initial_chain(3), finality_attestations=[], finalized_blocks=[]))
    current = node(store, validators)
    current.submit_validator_finality_attestations([sign(i, 'b' * 64, 1) for i in range(3)])
    assert [p['block_height'] for p in current.finalized_blocks] == [1]  # No new parent-QC gate.
    current.submit_validator_finality_attestation(sign(0, 'c' * 64, 2))
    proposed = store.load_blockchain_document()
    proposed['chain'][2] = dict(index=2, hash='e' * 64, previous_hash='b' * 64)
    proposed['finality_attestations'] = [v for v in proposed['finality_attestations'] if v['block_height'] != 2]
    with pytest.raises(FinalityStateConflictError, match='reorganization'):
        store.save_blockchain_document(proposed)
    committed = store.atomic_update_blockchain_document(lambda durable: deepcopy(proposed), allow_vote_reorg=True)
    assert committed['finalized_blocks'][0]['block_hash'] == 'b' * 64
    assert {v['block_height'] for v in committed['finality_attestations']} == {1}
    recovered = node(backend(tmp_path), validators)
    assert recovered.get_finalized_head()['block_height'] == 1
    recovered.submit_validator_finality_attestations([sign(i) for i in range(3)])
    assert [p['block_height'] for p in recovered.finalized_blocks] == [0, 1]
    assert recovered.get_finalized_head()['block_height'] == 1


@pytest.mark.parametrize('kind', ['json', 'sqlite'])
def test_corrupt_real_facade_recovery_fails_closed_and_repeated_reload_recovers(blockchain, tmp_path, votes, kind):
    validators, sign = votes
    blockchain = Blockchain(blockchain.project_owner_wallet, blockchain.Contributor_one, blockchain.Contributor_two,
        storage_backend=backend(tmp_path, kind), validator_set=validators)
    target = blockchain.chain[0].hash
    blockchain.submit_validator_finality_attestations([sign(i, target) for i in range(3)])
    original = blockchain.get_finality_evidence(target)
    exposed = blockchain.get_finality_evidence(target)
    exposed['attestations'].clear()
    assert blockchain.get_finality_evidence(target) == original
    store = blockchain.storage
    def corrupt_or_repair(proof):
        if kind == 'sqlite':
            with store._connect() as connection:
                connection.execute("UPDATE storage_sections SET json_data=? WHERE section_name='finalized_blocks'", (json.dumps([proof]),))
        else:
            path = Path(store.blockchain_file)
            document = json.loads(path.read_text(encoding='utf-8'))
            document['finalized_blocks'] = [proof]
            path.write_text(json.dumps(document), encoding='utf-8')
    forged = deepcopy(original)
    forged['attestations'][0]['signature'] = '0x00'
    corrupt_or_repair(forged)
    with pytest.raises(GenesisValidationError, match='failed to load safely'):
        blockchain.load_blockchain()
    with pytest.raises(RuntimeError, match='unavailable'):
        blockchain.get_finalized_head()
    corrupt_or_repair(original)
    for _ in range(2):
        blockchain.load_blockchain()
        assert blockchain.get_finality_evidence(target) == original


def test_stale_truncation_cannot_discard_a_nonfinalized_vote(tmp_path, votes):
    validators, sign = votes
    store = backend(tmp_path)
    current = node(store, validators)
    stale = store.load_blockchain_document()
    store.atomic_update_blockchain_document(lambda durable: {**durable, 'chain': initial_chain(2)})
    current = node(store, validators)
    current.submit_validator_finality_attestation(sign(0, 'b' * 64, 1))
    with pytest.raises(FinalityStateConflictError):
        store.save_blockchain_document(stale)
    assert store.load_blockchain_document()['finality_attestations'] == [sign(0, 'b' * 64, 1)]


def test_stale_real_facade_save_refreshes_derived_report_finality_head(blockchain, tmp_path, votes):
    validators, sign = votes
    store = backend(tmp_path)
    current = Blockchain(blockchain.project_owner_wallet, blockchain.Contributor_one, blockchain.Contributor_two,
        storage_backend=store, validator_set=validators)
    stale = Blockchain(blockchain.project_owner_wallet, blockchain.Contributor_one, blockchain.Contributor_two,
        storage_backend=backend(tmp_path), validator_set=validators)
    target = current.chain[0].hash
    assert stale._report_finalized_head is None
    current.submit_validator_finality_attestations([sign(i, target) for i in range(3)])
    stale.save_blockchain()
    expected = dict(block_height=0, block_hash=target)
    assert stale.get_finalized_head() == expected
    assert stale._report_finalized_head == expected
    assert stale.get_finality_evidence(target) == current.get_finality_evidence(target)


def test_missing_one_finality_section_is_not_reinitialized(tmp_path, votes):
    validators, sign = votes
    store = backend(tmp_path)
    current = node(store, validators)
    current.submit_validator_finality_attestations([sign(i) for i in range(3)])
    with store._connect() as connection:
        connection.execute("DELETE FROM storage_sections WHERE section_name='finalized_blocks'")
    with pytest.raises(StorageCorruptionError, match='Incomplete finality'):
        backend(tmp_path)
    with sqlite3.connect(store.sqlite_db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM storage_sections WHERE section_name='finalized_blocks'").fetchone() == (0,)


@pytest.mark.parametrize('failure', [OSError('I/O unavailable'), sqlite3.OperationalError('database is locked')])
def test_real_facade_load_outage_is_operational_not_invalid_evidence(blockchain, monkeypatch, failure):
    def unavailable():
        raise failure
    monkeypatch.setattr(blockchain.storage, 'load_blockchain_state', unavailable)
    with pytest.raises(type(failure), match=str(failure)):
        blockchain.load_blockchain()
    with pytest.raises(RuntimeError, match='unavailable'):
        blockchain.get_finalized_head()


@pytest.mark.parametrize('first', ['finality', 'reorg'])
def test_reorg_and_finality_race_in_both_commit_orders(tmp_path, votes, first):
    validators, sign = votes
    store = backend(tmp_path)
    store.save_blockchain_document(dict(chain=initial_chain(2), finality_attestations=[], finalized_blocks=[]))
    current = node(store, validators)
    current.submit_validator_finality_attestations([sign(i, 'b' * 64, 1) for i in range(2)])
    entered, release = Event(), Event()
    def hold():
        entered.set()
        assert release.wait(10)
    if first == 'finality':
        current._finality_fault_injector = lambda stage: hold() if stage == 'before_commit' else None
    def reorg():
        def mutate(document):
            if first == 'reorg':
                hold()
            document['chain'][1] = dict(index=1, hash='f' * 64, previous_hash=TARGET)
            document['finality_attestations'] = []
            return document
        return store.atomic_update_blockchain_document(mutate, allow_vote_reorg=True)
    def finalize():
        return current.submit_validator_finality_attestation(sign(2, 'b' * 64, 1))
    with ThreadPoolExecutor(max_workers=2) as pool:
        winner = pool.submit(finalize if first == 'finality' else reorg)
        assert entered.wait(10)
        loser = pool.submit(reorg if first == 'finality' else finalize)
        release.set()
        winner.result(timeout=15)
        with pytest.raises(FinalityStateConflictError if first == 'finality' else FinalityAttestationError):
            loser.result(timeout=15)
    durable = store.load_blockchain_document()
    assert durable['chain'][1]['hash'] == ('b' * 64 if first == 'finality' else 'f' * 64)
    assert len(durable['finalized_blocks']) == (1 if first == 'finality' else 0)
    assert len(durable['finality_attestations']) == (3 if first == 'finality' else 0)


def wait_for(path, process, timeout=20):
    deadline = time.monotonic() + timeout
    while not path.exists():
        assert process.poll() is None, f'worker exited {process.returncode}'
        assert time.monotonic() < deadline, 'worker readiness timed out'
        time.sleep(.02)


def start_worker(tmp_path, validators, vote, *, stage=None, gate=None, suffix='worker'):
    job = dict(root=str(tmp_path), validators=validators, vote=vote, stage=stage,
        ready=str(tmp_path / f'{suffix}.ready'), gate=str(gate) if gate else None)
    path = tmp_path / f'{suffix}.json'
    path.write_text(json.dumps(job), encoding='utf-8')
    log = (tmp_path / f'{suffix}.log').open('w', encoding='utf-8')
    process = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), '--worker', str(path)],
        stdout=log, stderr=subprocess.STDOUT)
    log.close()
    return process, Path(job['ready'])


@pytest.mark.parametrize('identical', [False, True])
def test_separate_process_vote_writers(tmp_path, votes, identical):
    validators, sign = votes
    store = backend(tmp_path)
    current = node(store, validators)
    current.submit_validator_finality_attestation(sign(0))
    gate = tmp_path / 'start'
    workers = [start_worker(tmp_path, validators, sign(1 if identical else i + 1),
        gate=gate, suffix=f'worker{i}') for i in range(2)]
    try:
        for process, ready in workers:
            wait_for(ready, process)
        gate.touch()
        for process, _ in workers:
            assert process.wait(timeout=30) == 0
        assert_state(store, 2 if identical else 3, 0 if identical else 1)
    finally:
        for process, _ in workers:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)


@pytest.mark.parametrize('stage', ['before_commit', 'after_commit_before_publish'])
def test_actual_process_termination_before_and_after_commit(tmp_path, votes, stage):
    validators, sign = votes
    current = node(backend(tmp_path), validators)
    current.submit_validator_finality_attestations([sign(0), sign(1)])
    process, ready = start_worker(tmp_path, validators, sign(2), stage=stage)
    try:
        wait_for(ready, process)
        assert_state(current.storage, 2 if stage == 'before_commit' else 3,
            0 if stage == 'before_commit' else 1)
        process.kill()
        process.wait(timeout=10)
        recovered = node(backend(tmp_path), validators)
        result = recovered.submit_validator_finality_attestation(sign(2))
        assert result['status'] == ('accepted' if stage == 'before_commit' else 'duplicate')
        assert_state(recovered.storage, 3, 1)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)


def worker(job):
    current = node(backend(job['root']), job['validators'])
    def suspend():
        Path(job['ready']).touch()
        while True:
            time.sleep(.05)
    if job['stage'] == 'before_commit':
        connect = current.storage._connect
        @contextmanager
        def stop_after_sql_writes():
            with connect() as connection:
                yield connection
                if connection.in_transaction:
                    suspend()
        current.storage._connect = stop_after_sql_writes
    elif job['stage'] == 'after_commit_before_publish':
        current._finality_fault_injector = lambda stage: suspend() if stage == job['stage'] else None
    if job['gate']:
        Path(job['ready']).touch()
        deadline = time.monotonic() + 25
        while not Path(job['gate']).exists():
            if time.monotonic() > deadline:
                raise RuntimeError('start gate timeout')
            time.sleep(.02)
    current.submit_validator_finality_attestation(job['vote'])


if __name__ == '__main__':
    assert sys.argv[1] == '--worker'
    worker(json.loads(Path(sys.argv[2]).read_text(encoding='utf-8')))
