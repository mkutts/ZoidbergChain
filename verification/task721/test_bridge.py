"""Hostile canonical bytes, real service checks, crash/recovery and nonactivation."""
from copy import deepcopy
from dataclasses import replace
import base64
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'tests'))
from canonical_v3 import block, media
from canonical_v3.admission import AdmissionAdapter, AdmissionDependencies, Failure, IntegrationError, TestOnlyConfig
from canonical_v3.primitives import MAX_RECORD, V3Error, canonical, digest
from canonical_v3.storage import SCHEMA, StorageCorruption, StorageUnavailable
from codec_prototype.isolated_decoder import IsolatedDecoder, Outcome, Status
from test_milestone_7_task_7_13_admission import (
    CTX, BASE, FIXTURES, application_admission, v2_certificate, state_for, header_for, image,
)
from verification.task721.bridge import (
    DisposableStore, canonical_media, construct_candidate, validate_candidate, retrieve,
)
from verification.task721.reconcile import reconcile

CONFIG = TestOnlyConfig(CTX, True)
IDENTITY = (FIXTURES/'block-identity.json').read_bytes()
ZSTD = (FIXTURES/'block-zstd.json').read_bytes()


@pytest.fixture(autouse=True)
def worker_root(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path))


@pytest.fixture
def decoder():
    with IsolatedDecoder() as worker:
        yield worker


def received(change, raw=ZSTD):
    record = json.loads(raw)
    change(record)
    record['hash'] = digest(record['envelope'])
    return canonical(record)


@pytest.mark.parametrize('raw', [IDENTITY, ZSTD], ids=['identity','zstd'])
def test_retrieval_restart_and_no_recompression(raw, tmp_path, decoder, monkeypatch):
    monkeypatch.setattr(media, '_compress_default', lambda _: pytest.fail('received bytes recompressed'))
    expected = canonical_media(raw, CONFIG, decoder=decoder)
    path = tmp_path/'media.sqlite'
    with DisposableStore(path, CONFIG, decoder=decoder, create=True) as store:
        assert store.connection.execute('PRAGMA journal_mode').fetchone()[0] == 'delete'
        assert store.connection.execute('PRAGMA synchronous').fetchone()[0] == 3
        assert store.insert(raw)
        assert retrieve(store,expected.block_hash,CONFIG,decoder=decoder) == expected
    with DisposableStore(path, CONFIG, decoder=decoder) as store:
        assert store.get(expected.block_hash) == raw
        assert retrieve(store,expected.block_hash,CONFIG,decoder=decoder) == expected
        assert expected.remaining
        assert store.connection.execute('SELECT count(*) FROM canonical_chain').fetchone()[0] == 0
        assert store.connection.execute('SELECT count(*) FROM finality').fetchone()[0] == 0


@pytest.mark.parametrize('field,value', [
    ('codec_id','brotli'),('codec_version',2),('codec_version',True),('encoding_version',2),
    ('mime_type','video/mp4'),('original_sha256','0'*64),('original_size',2),('stored_size',1),
    ('original_size',media.MAX_TEXT+1),('stored_size',media.MAX_ENCODED+1),
])
def test_invalid_descriptor_is_not_local_failure(field,value,decoder):
    raw=received(lambda r:r['envelope']['payload']['media'].update({field:value}))
    with pytest.raises(IntegrationError) as exc:
        canonical_media(raw,CONFIG,decoder=decoder)
    assert exc.value.classification == Failure.INVALID_CANONICAL


@pytest.mark.parametrize('case',['corrupt','truncated','block-hash','noncanonical','signature','network','protocol'])
def test_invalid_actual_canonical_encoded_bytes(case,decoder):
    def change(r):
        d=r['envelope']['payload']['media']
        if case in ('corrupt','truncated'):
            encoded=bytearray(base64.b64decode(d['payload']))
            if case=='corrupt': encoded[-1]^=1
            else: encoded=encoded[:-1]
            d.update(payload=base64.b64encode(encoded).decode(),stored_size=len(encoded))
        elif case=='signature':
            r['envelope']['payload']['admission_certificate']['votes'][0]['vote_signature']='0x'+'11'*65
        elif case=='network': r['envelope']['network_id']='another-network'
        elif case=='protocol': r['envelope']['protocol_version']=3
    raw=received(change)
    if case=='block-hash': raw=raw.replace(json.loads(raw)['hash'].encode(),b'0'*64,1)
    if case=='noncanonical': raw=b' '+raw
    with pytest.raises(IntegrationError) as exc:
        canonical_media(raw,CONFIG,decoder=decoder)
    assert exc.value.classification == Failure.INVALID_CANONICAL


def test_hash_mismatch_reaches_decoder_with_valid_signed_original_commitment(decoder):
    # Replace only the encoded representation with a same-size different
    # original; retain fully valid original certificate and block bindings.
    record=json.loads(IDENTITY)
    desc=record['envelope']['payload']['media']
    desc['payload']=base64.b64encode(b'X'*desc['stored_size']).decode()
    record['hash']=digest(record['envelope'])
    with pytest.raises(IntegrationError) as exc:
        canonical_media(canonical(record),CONFIG,decoder=decoder)
    assert exc.value.classification == Failure.INVALID_CANONICAL
    assert exc.value.outcome is not None


def test_larger_conforming_encoding_valid_without_recompression(decoder,monkeypatch):
    from scripts.milestone_7_task_7_11_storage import corpus_record
    original=b'Accept exact bytes.'
    raw=corpus_record(original,'text/plain','alternate',1,CTX.genesis_hash,decoder)
    r=json.loads(raw)
    d=media.descriptor(original,media._compress_default(original),'text/plain','zstd')
    assert len(canonical(d))>len(canonical(media.descriptor(original,original,'text/plain','identity')))
    r['envelope']['payload']['media']=d
    r['hash']=digest(r['envelope'])
    monkeypatch.setattr(media,'_compress_default',lambda _:pytest.fail('validator recompressed'))
    assert canonical_media(canonical(r),CONFIG,decoder=decoder).body==original


@pytest.mark.parametrize('size',[MAX_RECORD-1,MAX_RECORD,MAX_RECORD+1])
def test_complete_cap_without_fabricating_schema_valid_padding(size,decoder):
    raw=b' '*size
    if size<=MAX_RECORD: block.check_complete_size(raw)
    else:
        with pytest.raises(V3Error,match='block_size'): block.check_complete_size(raw)
    with pytest.raises(IntegrationError) as exc:
        canonical_media(raw,CONFIG,decoder=decoder)
    assert exc.value.classification==Failure.INVALID_CANONICAL


@pytest.mark.parametrize('raw,mime',[(b'x'* (media.MAX_TEXT+1),'text/plain'),
    (image(),'image/jpeg'),(b'x','application/pdf'),(b' a ','text/plain')],
    ids=['oversized-text','wrong-mime','unsupported','noncanonical-original'])
def test_producer_rejects_bad_mime_size_and_unaccepted_original(raw,mime,decoder):
    valid,app,resolver=application_admission()
    cert=v2_certificate(app)
    adapter=AdmissionAdapter(CONFIG,AdmissionDependencies(resolver,lambda _:False),decoder=decoder)
    with pytest.raises(IntegrationError):
        construct_candidate(raw,mime,adapter=adapter,application_certificate=app,canonical_certificate=cert,
                            header=header_for(),state=state_for(cert),native_transactions=[])


def test_independent_application_validation_and_missing_authority(decoder,monkeypatch):
    original=image()
    valid,app,resolver=application_admission(original,'image/png')
    cert=v2_certificate(app); state=state_for(cert)
    adapter=AdmissionAdapter(CONFIG,AdmissionDependencies(resolver,lambda _:False),decoder=decoder)
    candidate=construct_candidate(original,'image/png',adapter=adapter,application_certificate=app,
        canonical_certificate=cert,header=header_for('image/png'),state=state,native_transactions=[])
    assert validate_candidate(candidate.canonical_record,CONFIG,decoder=decoder,state=state).body==original
    for missing in (None,replace(state,reviewer_status_resolver=lambda *args:None)):
        with pytest.raises(IntegrationError) as exc:
            validate_candidate(candidate.canonical_record,CONFIG,decoder=decoder,state=missing)
        assert exc.value.classification==Failure.INCOMPLETE
    bad=received(lambda r:r['envelope']['payload']['media'].update(mime_type='image/jpeg'),candidate.canonical_record)
    with pytest.raises(IntegrationError) as exc:
        validate_candidate(bad,CONFIG,decoder=decoder,state=state)
    assert exc.value.classification==Failure.INVALID_CANONICAL
    # A fully signed fixture can also carry falsely labelled container bytes;
    # format crypto alone must not establish current MIME admission.
    from scripts.milestone_7_task_7_11_storage import corpus_record
    wrong=corpus_record(original,'image/jpeg','wrong-mime',1,CTX.genesis_hash,decoder)
    with pytest.raises(IntegrationError) as exc:
        validate_candidate(wrong,CONFIG,decoder=decoder,state=state)
    assert exc.value.classification==Failure.INVALID_ADMISSION
    monkeypatch.setattr(decoder,'validate',lambda _:Outcome(Status.INDETERMINATE_LOCAL_FAILURE,reason='timeout'))
    with pytest.raises(IntegrationError) as exc:
        validate_candidate(candidate.canonical_record,CONFIG,decoder=decoder,state=state)
    assert exc.value.classification==Failure.LOCAL_FAILURE


@pytest.mark.parametrize('original,mime',[(b'Original accepted upload. '*100,'text/plain'),(image(),'image/png')],ids=['text','png'])
def test_actual_upload_service_then_canonical_only_retrieval(original,mime,tmp_path,decoder):
    from content import load_content_bytes, resolve_local_path
    from services.content_coordination_service import ContentCoordinationService, ContentCoordinationState
    from storage import JSONStorageBackend
    cache=JSONStorageBackend(blockchain_file=str(tmp_path/'upload/chain.json'),peers_file=str(tmp_path/'upload/peers.json'))
    state=ContentCoordinationState([],[],{},{},[],set())
    # The text service canonicalizes uploads; the bridge receives precisely
    # those accepted bytes, never silently substitutes source bytes.
    obj=ContentCoordinationService().upload_binary_content(state,cache,'public_testnet_v1',
        file_bytes=original,submitted_by=BASE['creator_wallet'],mime_type=mime)
    accepted=load_content_bytes(obj.content_hash,obj.mime_type,data_dir=cache.data_dir)
    validated,app,resolver=application_admission(accepted,mime)
    cert=v2_certificate(app); snapshot=state_for(cert)
    adapter=AdmissionAdapter(CONFIG,AdmissionDependencies(resolver,lambda _:False),decoder=decoder)
    candidate=construct_candidate(accepted,mime,adapter=adapter,application_certificate=app,
        canonical_certificate=cert,header=header_for(mime),state=snapshot,native_transactions=[])
    verified=validate_candidate(candidate.canonical_record,CONFIG,decoder=decoder,state=snapshot)
    assert verified.body==accepted and verified.original_sha256==obj.content_hash
    Path(resolve_local_path(obj.local_path,data_dir=cache.data_dir)).unlink()
    with DisposableStore(tmp_path/'uploaded.sqlite',CONFIG,decoder=decoder,create=True) as store:
        store.insert(candidate.canonical_record)
        assert retrieve(store,verified.block_hash,CONFIG,decoder=decoder).body==accepted


@pytest.mark.parametrize('stage',['after-blob','after-index','after-commit'])
def test_actual_process_interruption_and_retry(stage,tmp_path,decoder):
    path=tmp_path/'crash.sqlite'
    with DisposableStore(path,CONFIG,decoder=decoder,create=True): pass
    child=subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('crash.py')),stage,str(path)],
                         capture_output=True,text=True,timeout=25,cwd=ROOT)
    assert child.returncode==83,child.stderr
    identity=json.loads(IDENTITY)['hash']
    with DisposableStore(path,CONFIG,decoder=decoder) as store:
        assert (store.get(identity) is not None)==(stage=='after-commit')
        assert store.insert(IDENTITY)==(stage!='after-commit')
        assert store.get(identity)==IDENTITY
        assert store.check_integrity()['blocks']==1


@pytest.mark.parametrize('damage',['index','corrupt','truncated','missing-record'])
def test_database_is_not_substitute_for_canonical_evidence(damage,tmp_path,decoder):
    path=tmp_path/'damage.sqlite'
    identity=json.loads(ZSTD)['hash']
    with DisposableStore(path,CONFIG,decoder=decoder,create=True) as store:
        store.insert(ZSTD)
        if damage=='index':
            store.connection.execute('DELETE FROM block_index')
            with pytest.raises(StorageCorruption): store.get(identity)
            store.rebuild_indexes()
            assert store.get(identity)==ZSTD
        else:
            store.connection.execute('DROP TRIGGER immutable_blocks_update')
            store.connection.execute('DROP TRIGGER immutable_blocks_delete')
            if damage=='missing-record':
                store.connection.execute('PRAGMA foreign_keys=OFF')
                store.connection.execute('DELETE FROM blocks')
                for sql in SCHEMA:
                    if sql.startswith(('CREATE TRIGGER immutable_blocks_update','CREATE TRIGGER immutable_blocks_delete')):
                        store.connection.execute(sql)
                with pytest.raises(StorageCorruption): store.check_integrity()
            else:
                bad=ZSTD[:-1] if damage=='truncated' else ZSTD.replace(b'"hash":"',b'"hash":"0',1)
                store.connection.execute('UPDATE blocks SET canonical=?',(bad,))
                for sql in SCHEMA:
                    if sql.startswith(('CREATE TRIGGER immutable_blocks_update','CREATE TRIGGER immutable_blocks_delete')):
                        store.connection.execute(sql)
                with pytest.raises(StorageCorruption): retrieve(store,identity,CONFIG,decoder=decoder)
                with pytest.raises(StorageCorruption,match='stored canonical record'): store.rebuild_indexes()


def test_unavailable_decoder_storage_and_missing_block_distinct(tmp_path,decoder,monkeypatch):
    path=tmp_path/'failures.sqlite'
    with DisposableStore(path,CONFIG,decoder=decoder,create=True) as store:
        with pytest.raises(IntegrationError) as exc: retrieve(store,'0'*64,CONFIG,decoder=decoder)
        assert exc.value.classification==Failure.INCOMPLETE
        store.insert(ZSTD)
        monkeypatch.setattr(decoder,'validate',lambda _:Outcome(Status.INDETERMINATE_LOCAL_FAILURE,reason='unavailable'))
        with pytest.raises(StorageUnavailable): store.get(json.loads(ZSTD)['hash'])


def test_no_inherited_wal_maintenance_or_consensus_authority(tmp_path,decoder):
    with DisposableStore(tmp_path/'narrow.sqlite',CONFIG,decoder=decoder,create=True) as store:
        for operation in (lambda:store.backup(tmp_path/'backup.sqlite'),store.checkpoint,
                          lambda:store.restore('unused','unused',CONFIG)):
            with pytest.raises(StorageUnavailable): operation()
        for operation in (lambda:store.select_chain(None,expected_tip=None),lambda:store.finalize(b'')):
            with pytest.raises(IntegrationError) as exc: operation()
            assert exc.value.classification==Failure.INCOMPLETE
        assert store.connection.execute('PRAGMA journal_mode').fetchone()[0]=='delete'
        assert not (tmp_path/'backup.sqlite').exists()


def test_nonactivation_by_environment_or_peer_field(monkeypatch,decoder,tmp_path):
    from media_integrity import reconstruct_media_bytes, MediaIntegrityError
    from services.block_validation_service import BlockValidationService, NativeBlockValidationError
    from services.content_coordination_service import ContentCoordinationService
    for key in ('ZOIDBERG_ENABLE_V3','ENABLE_V3','TEST_ONLY','ZOIDBERG_COMPRESSION_ENABLED'):
        monkeypatch.setenv(key,'1')
    payload=deepcopy(BASE)
    payload.update(block_version=3,test_only=True,protocol_version=3,enable_v3=True)
    assert not ContentCoordinationService.is_protocol_v1_block_payload(payload)
    with pytest.raises(NativeBlockValidationError) as exc:
        BlockValidationService().validate_block(payload,SimpleNamespace())
    assert exc.value.code=='invalid_block_version'
    with pytest.raises(MediaIntegrityError): reconstruct_media_bytes(payload)
    with pytest.raises(V3Error): TestOnlyConfig(CTX,False)
    with pytest.raises(V3Error): canonical_media(ZSTD,None,decoder=decoder)
    # Opening an active/arbitrary DB never repairs or migrates it.
    path=tmp_path/'active.sqlite'
    with sqlite3.connect(path) as connection: connection.execute('CREATE TABLE active(value)')
    before=path.read_bytes()
    with pytest.raises(StorageCorruption): DisposableStore(path,CONFIG,decoder=decoder)
    assert path.read_bytes()==before


def test_active_sources_and_frozen_evidence_are_unchanged():
    import hashlib
    before=json.loads((Path(__file__).with_name('prerequisites.json')).read_bytes())['tracked_sha256']
    assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha for name,sha in before.items())
    # Transitive active source cannot import the new verification bridge.
    for name in before:
        if name.endswith('.py') and not name.startswith(('tests/','scripts/','verification/','benchmarks/')):
            source=(ROOT/name).read_text(encoding='utf-8')
            assert 'verification.task721' not in source


def test_reconciliation_has_comparable_populations_and_mandatory_fields():
    result=reconcile()
    assert result['primary_records']==70 and result['sensitivity_records']==8
    group=result['groups']['production-like']
    assert group['records']==group['unique_objects']==34
    assert group['per_record_totals']['certificate_member_bytes']==1073154
