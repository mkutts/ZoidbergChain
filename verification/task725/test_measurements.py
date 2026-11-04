"""Independent accounting checks and real backup/corruption recovery controls."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from canonical_v3.primitives import canonical
from canonical_v3.storage import SCHEMA, StorageCorruption
from codec_prototype.isolated_decoder import IsolatedDecoder
from verification.task721.bridge import DisposableStore
from verification.task725.measure import CONFIG, read, sha, connect, copy_observed, balanced

HERE = Path(os.environ.get('TASK725_EVIDENCE',str(Path(__file__).resolve().parent)))
GIB = 1024**3


def result(name):
    return json.loads((HERE/name).read_bytes())


def test_frozen_records_hashes_and_coverage():
    data=result('workloads.json');rows=data['rows']
    assert [len(rows[n]) for n in ('historical36','production34','meme58','balanced41')] == [36,34,58,41]
    for p,h in result('corpus_hashes.json').items():
        assert sha((ROOT/p).read_bytes()) == h
    expected=read('benchmarks/task720_v1/records.json')['rows']+read('benchmarks/task723_v1/records.json')['rows']
    by_hash={r['record_sha256']:r for r in expected if r.get('record_bytes') is not None}
    for name,members in rows.items():
        total=data['totals'][name]
        assert sum(r['record_bytes'] or 0 for r in members)==total['canonical_bytes']
        for r in members:
            if r['record_bytes'] is None:
                assert r['id'] in ('jpeg-texture-1280','png-texture-1280')
                assert not r['balanced']['eligible']
                continue
            old=by_hash[r['record_sha256']]
            assert (r['block_hash'],r['record_bytes'],r['encoded_bytes'],r['original_sha256']) == (old['canonical_hash'],old['record_bytes'],old['encoded_bytes'],old['original_sha256'])
    assert data['totals']['historical36']['source_bytes']-data['totals']['historical36']['original_bytes']==7
    assert set(r['id'] for r in rows['balanced41']) == set(next(p for p in read('benchmarks/task723_v1/candidates.json')['profiles'] if p['name']=='B_balanced')['admitted_ids'])


@pytest.mark.parametrize('name',['historical36','production34','meme58','balanced41','native_index_control'])
def test_page_and_index_accounting(name):
    data=result('sqlite.json')['populations'][name]
    for variant in ('full','no_secondary','minimal'):
        observations=data[variant]['observations']
        for r in observations:
            assert r['logical_bytes']==r['page_count']*r['page_size']
            assert r['live_allocated_page_bytes']==(r['page_count']-r['free_pages'])*r['page_size']
            assert r['database_overhead_bytes']==r['logical_bytes']-r['canonical_bytes']
            assert r['journal_mode']=='delete' and r['synchronous']==3
        assert all(data[variant]['constraints'].values())
    full=data['full']['observations'][-1]
    assert data['secondary_pages']['secondary_allocation_bytes']==sum(r['bytes'] for r in data['secondary_pages']['rows'])
    assert data['file_differences']['full_minus_no_secondary']==full['logical_bytes']-data['no_secondary']['observations'][-1]['logical_bytes']
    assert data['file_differences']['full_minus_minimal']==full['logical_bytes']-data['minimal']['observations'][-1]['logical_bytes']
    assert data['full']['index_entries']['transaction_id_idx']==(full['blocks'] if name=='native_index_control' else 0)
    growth=result('index_growth.json')['populations'][name]
    assert [r['blocks'] for r in growth]==[r['blocks'] for r in data['full']['observations']]
    assert growth[-1]['full_minus_no_secondary_file_bytes']==data['file_differences']['full_minus_no_secondary']


def test_backup_workspace_and_process_recovery():
    populations=result('backup_recovery.json')['populations']
    assert len(populations)==4
    for name,r in populations.items():
        n=result('sqlite.json')['populations'][name]['full']['observations'][-1]['blocks']
        size=r['source']['logical_bytes']
        assert r['snapshot']['logical_bytes']==r['backup']['bytes']==r['recovery']['bytes']==size
        assert r['recovery']['additional_workspace_bytes']==size
        assert r['retained_four_backups_bytes']==4*size
        assert r['verification']['blocks']==n and r['verification']['fresh_process']
        assert r['verification']['canonical_identity'] and r['verification']['original_commitments']
        assert r['snapshot_ratio']==r['backup_ratio']==1


def test_transfer_octets_add_up_and_unknown_packets_remain_unknown():
    data=result('transfer.json')
    assert data['packet_overhead_bytes'] is None and data['tcp_retransmissions'] is None
    assert data['verdict'].startswith('SIMULATED')
    for r in data['exchanges']:
        assert r['http_stream_bytes']==sum(r[k] for k in ('request_body_bytes','response_body_bytes','request_http_framing_bytes','response_http_framing_bytes'))
        assert r['application_framing_bytes']==r['request_body_bytes']+r['response_body_bytes']-r['canonical_payload_bytes']
        assert r['peer_auth_header_bytes'] < r['request_http_framing_bytes']
        assert r['authenticated_fixture_headers']
        assert r['content_encoding'] is None and r['transfer_encoding'] is None
    for name,p in data['populations'].items():
        rows=[r for r in data['exchanges'] if r['label']==name+':propagation']
        assert len(rows)==p['n']*2  # Existing broadcast sends certificate separately.
        assert sum(r['canonical_payload_bytes'] for r in rows)==p['canonical_bytes']
        assert p['propagation_sender_bytes']==sum(r['request_body_bytes']+r['request_http_framing_bytes'] for r in rows)


def test_economics_independent_arithmetic_and_delta_attribution():
    data=result('projections.json');assert len(data['scenarios'])==36
    for s,comparison in zip(data['scenarios'],data['comparisons'],strict=True):
        assert len(s['monthly'])==36 and sum(r['days'] for r in s['monthly'])==1095
        assert s['month36']['blocks']==s['blocks_per_day']*1095
        p=data['pricing'][s['profile']];cumulative=0
        assert s['whole_history_json_capacity']['canonical_history_alone_exceeds_ram'] == (s['month36']['canonical_bytes']>p['memory_gib']*GIB)
        assert s['whole_history_json_capacity']['status'].startswith('BLOCKED')
        for r in s['monthly']:
            local=sum(r[k] for k in ('primary_database_bytes','snapshot_bytes','recovery_workspace_bytes','operational_headroom_bytes'))
            assert local==pytest.approx(r['local_capacity_bytes'])
            disk=max(0,local/GIB-p['included_primary_gib'])
            import math
            egress=sum(r[k] for k in ('peer_outgoing_bytes','backup_upload_bytes','expected_bootstrap_serve_bytes','expected_restore_transfer_bytes'))
            bill=p['monthly_compute']+math.ceil(disk)*p['primary_gib_month']+r['backup_retained_bytes']/GIB*p['backup_gib_month']+egress/GIB*p['egress_gib']
            assert bill==pytest.approx(r['cost_usd']['total'],rel=1e-12)
            cumulative+=bill
        assert cumulative==pytest.approx(s['three_year_cumulative_usd'],rel=1e-12)
        assert s['under100']==(bill<100)
        assert comparison['updated_usd']-comparison['prior_same_population_usd']==pytest.approx(sum(comparison[k] for k in
            ('measured_storage_and_recovery_basis_delta','measured_backup_ratio_delta','measured_simulated_transfer_basis_delta')))


@pytest.mark.parametrize('fixture',['block-identity.json','block-zstd.json'])
def test_real_streaming_backup_restore_and_corrupt_commitment(tmp_path,monkeypatch,fixture):
    monkeypatch.setattr(tempfile,'tempdir',str(tmp_path))
    raw=(ROOT/'tests/fixtures/milestone_7_v3_v1'/fixture).read_bytes()
    h=json.loads(raw)['hash'];source=tmp_path/'source.sqlite';snapshot=tmp_path/'snapshot.sqlite';restored=tmp_path/'restored.sqlite'
    with IsolatedDecoder() as decoder:
        with DisposableStore(source,CONFIG,decoder=decoder,create=True) as store:
            assert store.insert(raw)
            dst=connect(snapshot);store.connection.backup(dst);dst.close()
        observation=copy_observed(snapshot,restored,tmp_path)
        assert observation['additional_workspace_bytes']==snapshot.stat().st_size
        with DisposableStore(restored,CONFIG,decoder=decoder) as store:
            assert store.get(h)==raw
            assert store.check_integrity()['blocks']==1
        # Retain exact schema while corrupting only a stored commitment in a test copy.
        damaged=raw.replace(h.encode(),b'0'*64,1)
        c=connect(restored)
        c.execute('DROP TRIGGER immutable_blocks_update')
        c.execute('UPDATE blocks SET canonical=? WHERE hash=?',(damaged,h))
        c.execute(next(s for s in SCHEMA if s.startswith('CREATE TRIGGER immutable_blocks_update ')))
        c.close()
        with DisposableStore(restored,CONFIG,decoder=decoder) as store:
            with pytest.raises(StorageCorruption):
                store.get(h)


def test_model_a_recovery_does_not_claim_finality():
    for r in result('backup_recovery.json')['populations'].values():
        assert r['verification']['integrity']['selected_blocks']==0
        assert r['verification']['integrity']['finality_proofs']==0


def test_real_loopback_transfer_and_invalid_block_control(tmp_path,monkeypatch):
    from verification.task725 import transfer
    from canonical_v3.admission import IntegrationError
    monkeypatch.setattr(tempfile,'tempdir',str(tmp_path))
    raws=[(ROOT/'tests/fixtures/milestone_7_v3_v1'/name).read_bytes() for name in ('block-identity.json','block-zstd.json')]
    with IsolatedDecoder() as decoder:
        transfer.run(tmp_path,tmp_path,dict(control=raws),decoder)
        observed=json.loads((tmp_path/'transfer.json').read_bytes())
        assert len(observed['exchanges'])==7  # two separate certificate/block sends, three GETs
        assert observed['populations']['control']['n']==2
        damaged=json.loads(raws[0]);damaged['hash']='0'*64
        with pytest.raises(IntegrationError):
            transfer.Harness(decoder).validate(damaged)
