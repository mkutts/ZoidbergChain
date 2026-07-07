from __future__ import annotations

from pathlib import Path

import pytest

import storage
import storage_tools
from block import Block
from blockchain import Blockchain
from peers import PeerStore
from peer_sync import (
    receive_peer_block,
    receive_peer_certificate,
    receive_peer_submission,
    receive_peer_vote,
    sync_chain_from_peers,
)
from storage import JSONStorageBackend, SQLiteStorageBackend
from submission import Submission, VOTE_ORIGINAL
from transaction import Transaction
from wallet import Wallet


def _json_backend(base_dir, name="node"):
    node_dir = base_dir / name
    return JSONStorageBackend(
        blockchain_file=str(node_dir / "blockchain.json"),
        peers_file=str(node_dir / "peers.json"),
    )


def _sqlite_backend(base_dir, name="node"):
    node_dir = base_dir / name
    return SQLiteStorageBackend(sqlite_db_path=str(node_dir / "zoidbergchain.db"))


def _backend_label(backend_factory):
    return "sqlite" if backend_factory is _sqlite_backend else "json"


def _wallets():
    return {
        "owner": Wallet(),
        "contributor_one": Wallet(),
        "contributor_two": Wallet(),
    }


def _clone_block(block):
    block_data = block.to_dict()
    return Block(
        index=block_data["index"],
        previous_hash=block_data["previous_hash"],
        timestamp=block_data["timestamp"],
        transactions=[Transaction.from_dict(tx) for tx in block_data["transactions"]],
        miner=block_data["miner"],
        meme=block_data.get("meme", {}),
        hash=block_data["hash"],
        submission_id=block_data.get("submission_id"),
        certificate_id=block_data.get("certificate_id"),
        content_hash=block_data.get("content_hash"),
        creator_wallet=block_data.get("creator_wallet"),
        vote_hash=block_data.get("vote_hash"),
        approval_percentage=block_data.get("approval_percentage"),
        decisive_vote_total=block_data.get("decisive_vote_total"),
        minimum_votes_required=block_data.get("minimum_votes_required"),
        approved_at=block_data.get("approved_at"),
        originality_score=block_data.get("originality_score"),
    )


def _matching_genesis_blockchain(source_blockchain, backend, wallets):
    blockchain = Blockchain(
        project_owner_wallet=wallets["owner"],
        Contributor_one=wallets["contributor_one"],
        Contributor_two=wallets["contributor_two"],
        storage_backend=backend,
    )
    blockchain.chain = [_clone_block(source_blockchain.chain[0])]
    blockchain.pending_transactions = []
    blockchain.submissions = []
    blockchain.mint_queue = []
    blockchain.votes = []
    blockchain.originality_certificates = []
    blockchain.save_blockchain()
    return blockchain


def _register_peer(peer_store, node_id, url, now):
    peer_store.register_peer(
        node_id=node_id,
        url=url,
        network_name="zoidberg-testnet",
        now=now,
    )


def _create_node(backend, wallets):
    blockchain = Blockchain(
        project_owner_wallet=wallets["owner"],
        Contributor_one=wallets["contributor_one"],
        Contributor_two=wallets["contributor_two"],
        storage_backend=backend,
    )
    peer_store = PeerStore(storage_backend=backend)
    return blockchain, peer_store


def _create_submission_with_votes(blockchain, submission_image, wallets, *, text):
    extra_wallets = [Wallet() for _ in range(3)]
    for wallet in extra_wallets:
        blockchain.wallets[wallet.public_key] = wallet

    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content=text,
        submitter=wallets["owner"].public_key,
    )
    voters = [
        wallets["contributor_one"],
        wallets["contributor_two"],
        *extra_wallets,
    ]
    for index, voter in enumerate(voters, start=1):
        blockchain.cast_submission_vote(
            submission_id=submission.submission_id,
            voter=voter.public_key,
            vote_type=VOTE_ORIGINAL,
            created_at=1_000.0 + index,
        )
    blockchain.save_blockchain()
    return submission


def _evaluate_and_mint(blockchain, submission_id, wallets):
    blockchain.evaluate_submission(
        submission_id,
        automated_originality_passed=True,
        now=2_000.0,
    )
    certificate = blockchain.get_originality_certificate_for_submission(submission_id)
    blockchain.add_to_mint_queue(submission_id)
    assert blockchain.mint_next_queued_submission(
        miner=wallets["owner"].public_key,
        validate_meme=False,
    ) is True
    blockchain.save_blockchain()
    return certificate, blockchain.get_latest_block()


def _broadcast_submission_and_votes(source_blockchain, target_blockchain, target_peer_store, submission):
    receive_peer_submission(
        blockchain=target_blockchain,
        peer_store=target_peer_store,
        origin_node_id="node-a",
        network_name="zoidberg-testnet",
        submission_payload=submission.to_dict(),
        local_network_name="zoidberg-testnet",
    )
    for vote in source_blockchain.votes:
        receive_peer_vote(
            blockchain=target_blockchain,
            peer_store=target_peer_store,
            origin_node_id="node-a",
            network_name="zoidberg-testnet",
            vote_payload=vote,
            local_network_name="zoidberg-testnet",
        )


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


def _mock_chain_sync(monkeypatch, source_blockchain):
    def fake_get(url, params=None, timeout=None):
        if url.endswith("/chain/summary"):
            latest_block = source_blockchain.get_latest_block()
            return _FakeResponse(
                {
                    "network_name": "zoidberg-testnet",
                    "node_id": "node-a",
                    "chain_height": latest_block.index,
                    "latest_block_hash": latest_block.hash,
                    "genesis_hash": source_blockchain.chain[0].hash,
                    "cumulative_originality_score": source_blockchain.get_cumulative_originality_score(),
                    "cumulative_work": None,
                }
            )
        if url.endswith("/chain/blocks"):
            from_height = params["from_height"]
            blocks = [
                block
                for block in source_blockchain.chain
                if block.index >= from_height
            ]
            certificate_ids = {
                block.certificate_id
                for block in blocks
                if block.certificate_id
            }
            return _FakeResponse(
                {
                    "blocks": [block.to_dict() for block in blocks],
                    "certificates": [
                        certificate.to_dict()
                        for certificate in source_blockchain.originality_certificates
                        if certificate.certificate_id in certificate_ids
                    ],
                }
            )
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("peer_sync.requests.get", fake_get)


@pytest.mark.parametrize(
    ("source_backend_factory", "target_backend_factory"),
    [
        (_json_backend, _sqlite_backend),
        (_sqlite_backend, _json_backend),
    ],
)
def test_mixed_backends_support_direct_peer_broadcast_flow_after_restart(
    source_backend_factory,
    target_backend_factory,
    isolated_data_dir,
    submission_image,
):
    wallets = _wallets()
    source_backend = source_backend_factory(isolated_data_dir, "node-a")
    target_backend = target_backend_factory(isolated_data_dir, "node-b")
    source_blockchain, source_peer_store = _create_node(source_backend, wallets)
    _register_peer(source_peer_store, "node-b", "http://node-b.test:8001", 100.0)
    target_blockchain = _matching_genesis_blockchain(source_blockchain, target_backend, wallets)
    target_peer_store = PeerStore(storage_backend=target_backend)
    _register_peer(target_peer_store, "node-a", "http://node-a.test:8000", 200.0)

    submission = _create_submission_with_votes(
        source_blockchain,
        submission_image,
        wallets,
        text="mixed backend broadcast meme",
    )
    _broadcast_submission_and_votes(
        source_blockchain,
        target_blockchain,
        target_peer_store,
        submission,
    )
    certificate, latest_block = _evaluate_and_mint(
        source_blockchain,
        submission.submission_id,
        wallets,
    )
    receive_peer_certificate(
        blockchain=target_blockchain,
        peer_store=target_peer_store,
        origin_node_id="node-a",
        network_name="zoidberg-testnet",
        certificate_payload=certificate.to_dict(),
        local_network_name="zoidberg-testnet",
    )
    receive_peer_block(
        blockchain=target_blockchain,
        peer_store=target_peer_store,
        origin_node_id="node-a",
        network_name="zoidberg-testnet",
        block_payload=latest_block.to_dict(),
        related_submission_id=submission.submission_id,
        local_network_name="zoidberg-testnet",
    )

    reloaded_source = Blockchain(storage_backend=source_backend)
    reloaded_target = Blockchain(storage_backend=target_backend)
    reloaded_target_peers = PeerStore(storage_backend=target_backend)

    assert _backend_label(source_backend_factory) != _backend_label(target_backend_factory)
    assert reloaded_source.get_latest_block().hash == latest_block.hash
    assert reloaded_target.get_latest_block().hash == latest_block.hash
    assert reloaded_target.get_submission(submission.submission_id) is not None
    assert len(reloaded_target.get_submission_votes(submission.submission_id)["votes"]) == len(source_blockchain.votes)
    assert reloaded_target.get_originality_certificate(certificate.certificate_id) is not None
    assert reloaded_target.get_latest_block().certificate_id == certificate.certificate_id
    assert reloaded_target_peers.get_active_peer("node-a") is not None


@pytest.mark.parametrize(
    ("source_backend_factory", "target_backend_factory"),
    [
        (_json_backend, _json_backend),
        (_sqlite_backend, _sqlite_backend),
        (_json_backend, _sqlite_backend),
        (_sqlite_backend, _json_backend),
    ],
)
def test_two_node_restart_and_chain_sync_catch_up_certificate_block_across_backends(
    source_backend_factory,
    target_backend_factory,
    isolated_data_dir,
    submission_image,
    monkeypatch,
):
    wallets = _wallets()
    source_backend = source_backend_factory(isolated_data_dir, "node-a")
    target_backend = target_backend_factory(isolated_data_dir, "node-b")
    source_blockchain, source_peer_store = _create_node(source_backend, wallets)
    _register_peer(source_peer_store, "node-b", "http://node-b.test:8001", 100.0)
    target_blockchain = _matching_genesis_blockchain(source_blockchain, target_backend, wallets)
    target_peer_store = PeerStore(storage_backend=target_backend)
    _register_peer(target_peer_store, "node-a", "http://node-a.test:8000", 200.0)

    submission = _create_submission_with_votes(
        source_blockchain,
        submission_image,
        wallets,
        text="restart catch-up meme",
    )
    _broadcast_submission_and_votes(
        source_blockchain,
        target_blockchain,
        target_peer_store,
        submission,
    )
    target_blockchain.save_blockchain()

    reloaded_target = Blockchain(storage_backend=target_backend)
    reloaded_target_peers = PeerStore(storage_backend=target_backend)
    certificate, latest_block = _evaluate_and_mint(
        source_blockchain,
        submission.submission_id,
        wallets,
    )
    _mock_chain_sync(monkeypatch, source_blockchain)

    result = sync_chain_from_peers(
        blockchain=reloaded_target,
        peer_store=reloaded_target_peers,
        network_name="zoidberg-testnet",
    )

    final_source = Blockchain(storage_backend=source_backend)
    final_target = Blockchain(storage_backend=target_backend)

    assert result["synced"] == 1
    assert final_source.get_latest_block().hash == latest_block.hash
    assert final_target.get_latest_block().hash == latest_block.hash
    assert final_target.get_cumulative_originality_score() == source_blockchain.get_cumulative_originality_score()
    assert final_target.get_originality_certificate(certificate.certificate_id) is not None
    assert final_target.get_latest_block().certificate_id == certificate.certificate_id
    assert final_target.is_chain_valid([block.to_dict() for block in final_target.chain]) is True


@pytest.mark.parametrize("backend_factory", [_json_backend, _sqlite_backend])
def test_two_node_backup_and_integrity_helpers_work_in_node_specific_paths(
    backend_factory,
    isolated_data_dir,
    submission_image,
):
    wallets_a = _wallets()
    wallets_b = _wallets()
    backend_a = backend_factory(isolated_data_dir, "node-a")
    backend_b = backend_factory(isolated_data_dir, "node-b")
    blockchain_a, peer_store_a = _create_node(backend_a, wallets_a)
    blockchain_b, peer_store_b = _create_node(backend_b, wallets_b)

    _register_peer(peer_store_a, "node-b", "http://node-b.test:8001", 300.0)
    _register_peer(peer_store_b, "node-a", "http://node-a.test:8000", 400.0)
    submission_a = _create_submission_with_votes(
        blockchain_a,
        submission_image,
        wallets_a,
        text="node a backup meme",
    )
    submission_b = _create_submission_with_votes(
        blockchain_b,
        submission_image,
        wallets_b,
        text="node b backup meme",
    )
    _evaluate_and_mint(blockchain_a, submission_a.submission_id, wallets_a)
    _evaluate_and_mint(blockchain_b, submission_b.submission_id, wallets_b)

    report_a = storage.check_storage_integrity(backend_a)
    report_b = storage.check_storage_integrity(backend_b)
    backup_a = storage_tools.backup_storage(backend_a)
    backup_b = storage_tools.backup_storage(backend_b)

    assert report_a["healthy"] is True
    assert report_b["healthy"] is True
    assert backup_a["backup_path"] != backup_b["backup_path"]
    assert "node-a" in backup_a["backup_path"]
    assert "node-b" in backup_b["backup_path"]


def test_sqlite_two_node_start_scripts_use_separate_data_paths():
    start_node_a = Path("scripts/start_node_a_sqlite.ps1").read_text(encoding="utf-8")
    start_node_b = Path("scripts/start_node_b_sqlite.ps1").read_text(encoding="utf-8")

    assert '$env:DATA_DIR = "data/node-a"' in start_node_a
    assert '$env:NODE_DATA_DIR = "data/node-a"' in start_node_a
    assert '$env:STORAGE_BACKEND = "sqlite"' in start_node_a
    assert '$env:SQLITE_DB_PATH = "data/node-a/zoidbergchain.db"' in start_node_a

    assert '$env:DATA_DIR = "data/node-b"' in start_node_b
    assert '$env:NODE_DATA_DIR = "data/node-b"' in start_node_b
    assert '$env:STORAGE_BACKEND = "sqlite"' in start_node_b
    assert '$env:SQLITE_DB_PATH = "data/node-b/zoidbergchain.db"' in start_node_b
