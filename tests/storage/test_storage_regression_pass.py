from __future__ import annotations

from pathlib import Path

import pytest

import storage
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


def _seed_backend(backend, submission_image):
    owner = Wallet()
    contributor_one = Wallet()
    contributor_two = Wallet()
    blockchain = Blockchain(
        project_owner_wallet=owner,
        Contributor_one=contributor_one,
        Contributor_two=contributor_two,
        storage_backend=backend,
    )
    peer_store = PeerStore(storage_backend=backend)

    extra_wallets = [Wallet() for _ in range(3)]
    for wallet in extra_wallets:
        blockchain.wallets[wallet.public_key] = wallet

    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="storage regression meme",
        submitter=owner.public_key,
    )
    for index, wallet in enumerate([contributor_one, contributor_two, *extra_wallets], start=1):
        blockchain.cast_submission_vote(
            submission_id=submission.submission_id,
            voter=wallet.public_key,
            vote_type=VOTE_ORIGINAL,
            created_at=1_000.0 + index,
        )
    blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=2_000.0,
    )
    certificate = blockchain.get_originality_certificate_for_submission(submission.submission_id)
    blockchain.add_to_mint_queue(submission.submission_id)
    blockchain.mint_next_queued_submission(miner=owner.public_key, validate_meme=False)
    peer_store.register_peer(
        node_id="peer-a",
        url="http://peer-a.test:8000",
        network_name="zoidberg-testnet",
        now=3_000.0,
    )
    blockchain.save_blockchain()
    return {
        "backend": backend,
        "blockchain": blockchain,
        "peer_store": peer_store,
        "owner": owner,
        "contributor_one": contributor_one,
        "contributor_two": contributor_two,
        "submission": submission,
        "certificate": certificate,
        "extra_wallets": extra_wallets,
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


@pytest.mark.parametrize("backend_factory", [_json_backend, _sqlite_backend])
def test_cross_backend_parity_for_query_helpers_and_active_users(backend_factory, isolated_data_dir):
    backend = backend_factory(isolated_data_dir, "parity")
    state = {
        "chain": [
            {
                "index": 0,
                "previous_hash": "0",
                "timestamp": 100.0,
                "transactions": [],
                "miner": "GENESIS",
                "meme": {"text": "genesis"},
                "hash": "a" * 64,
            },
            {
                "index": 1,
                "previous_hash": "a" * 64,
                "timestamp": 200.0,
                "transactions": [
                    {
                        "sender": "wallet-tx",
                        "recipient": "wallet-rx",
                        "amount": 1,
                        "tip": 0,
                        "signature": "sig",
                        "payload_size_kb": 0,
                        "created_at": 900.0,
                    }
                ],
                "miner": "wallet-miner",
                "meme": {"text": "parity"},
                "hash": "b" * 64,
                "submission_id": "submission-a",
                "certificate_id": "c" * 64,
                "content_hash": "d" * 64,
                "creator_wallet": "wallet-submitter",
                "vote_hash": "e" * 64,
                "approval_percentage": 1.0,
                "decisive_vote_total": 1,
                "minimum_votes_required": 1,
                "approved_at": 910.0,
                "originality_score": 2.1,
            },
        ],
        "wallets": {
            "wallet-submitter": {"public_key": "wallet-submitter"},
        },
        "submissions": [
            {
                "submission_id": "submission-a",
                "image_path": "meme.jpg",
                "text_content": "parity",
                "submitter": "wallet-submitter",
                "status": "queued",
                "created_at": 850.0,
                "hard_reject_reason": None,
                "content_hash": "d" * 64,
                "certificate_id": "c" * 64,
            }
        ],
        "mint_queue": ["submission-a"],
        "votes": [
            {
                "submission_id": "submission-a",
                "voter": "wallet-voter",
                "vote_type": VOTE_ORIGINAL,
                "created_at": 860.0,
            }
        ],
        "originality_certificates": [
            {
                "certificate_id": "c" * 64,
                "submission_id": "submission-a",
                "content_hash": "d" * 64,
                "creator_wallet": "wallet-submitter",
                "vote_total": 1,
                "decisive_vote_total": 1,
                "original_votes": 1,
                "not_original_votes": 0,
                "unsure_votes": 0,
                "approval_percentage": 1.0,
                "minimum_votes_required": 1,
                "approved_at": 910.0,
                "network_name": "zoidberg-testnet",
                "issuing_node_id": "node-a",
                "vote_hash": "e" * 64,
                "originality_score": 2.1,
            }
        ],
        "peers": [
            {
                "node_id": "peer-a",
                "url": "http://peer-a.test:8000",
                "network_name": "zoidberg-testnet",
                "last_seen": 1000.0,
                "status": "active",
            }
        ],
    }
    backend.save_blockchain_state(state)
    backend.save_peers(state["peers"])

    assert backend.get_submission("submission-a") == state["submissions"][0]
    assert backend.get_submission_by_content_hash("d" * 64) == state["submissions"][0]
    assert backend.get_vote("submission-a", "wallet-voter") == state["votes"][0]
    assert backend.get_certificate_for_submission("submission-a") == state["originality_certificates"][0]
    assert backend.get_block_by_hash("b" * 64) == state["chain"][1]
    assert backend.get_block_by_height(1) == state["chain"][1]
    assert backend.mint_queue_contains("submission-a") is True
    assert backend.get_peer("peer-a") == state["peers"][0]
    assert backend.count_active_users(lookback_days=1, now=1000.0) == 3
    assert storage.check_storage_integrity(backend)["healthy"] is True


@pytest.mark.parametrize("backend_factory", [_json_backend, _sqlite_backend])
def test_peer_synced_state_persists_after_reload(backend_factory, isolated_data_dir, submission_image):
    source_backend = backend_factory(isolated_data_dir, "peer-source")
    source = _seed_backend(source_backend, submission_image)
    target_backend = backend_factory(isolated_data_dir, "peer-target")
    target = _matching_genesis_blockchain(
        source["blockchain"],
        target_backend,
        {
            "owner": source["owner"],
            "contributor_one": source["contributor_one"],
            "contributor_two": source["contributor_two"],
        },
    )
    target_peer_store = PeerStore(storage_backend=target_backend)
    target_peer_store.register_peer(
        node_id="peer-a",
        url="http://peer-a.test:8000",
        network_name="zoidberg-testnet",
        now=4_000.0,
    )

    receive_peer_submission(
        blockchain=target,
        peer_store=target_peer_store,
        origin_node_id="peer-a",
        network_name="zoidberg-testnet",
        submission_payload=source["submission"].to_dict(),
        local_network_name="zoidberg-testnet",
    )
    for vote in source["blockchain"].votes:
        receive_peer_vote(
            blockchain=target,
            peer_store=target_peer_store,
            origin_node_id="peer-a",
            network_name="zoidberg-testnet",
            vote_payload=vote,
            local_network_name="zoidberg-testnet",
        )
    receive_peer_certificate(
        blockchain=target,
        peer_store=target_peer_store,
        origin_node_id="peer-a",
        network_name="zoidberg-testnet",
        certificate_payload=source["certificate"].to_dict(),
        local_network_name="zoidberg-testnet",
    )
    receive_peer_block(
        blockchain=target,
        peer_store=target_peer_store,
        origin_node_id="peer-a",
        network_name="zoidberg-testnet",
        block_payload=source["blockchain"].get_latest_block().to_dict(),
        related_submission_id=source["submission"].submission_id,
        local_network_name="zoidberg-testnet",
    )
    target.save_blockchain()

    reloaded = Blockchain(storage_backend=target_backend)
    reloaded_peers = PeerStore(storage_backend=target_backend)
    assert reloaded.get_submission(source["submission"].submission_id) is not None
    assert len(reloaded.get_submission_votes(source["submission"].submission_id)["votes"]) == len(source["blockchain"].votes)
    assert reloaded.get_originality_certificate(source["certificate"].certificate_id) is not None
    assert reloaded.get_latest_block().hash == source["blockchain"].get_latest_block().hash
    assert reloaded_peers.get_active_peer("peer-a") is not None


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


@pytest.mark.parametrize("backend_factory", [_json_backend, _sqlite_backend])
def test_chain_sync_persists_cumulative_originality_score_after_reload(
    backend_factory,
    isolated_data_dir,
    submission_image,
    monkeypatch,
):
    source_backend = backend_factory(isolated_data_dir, "sync-source")
    source = _seed_backend(source_backend, submission_image)
    target_backend = backend_factory(isolated_data_dir, "sync-target")
    target = _matching_genesis_blockchain(
        source["blockchain"],
        target_backend,
        {
            "owner": source["owner"],
            "contributor_one": source["contributor_one"],
            "contributor_two": source["contributor_two"],
        },
    )
    target.submissions = [
        Submission.from_dict(submission.to_dict())
        for submission in source["blockchain"].submissions
    ]
    target.votes = [dict(vote) for vote in source["blockchain"].votes]
    target.save_blockchain()
    target_peer_store = PeerStore(storage_backend=target_backend)
    target_peer_store.register_peer(
        node_id="peer-a",
        url="http://peer-a.test:8000",
        network_name="zoidberg-testnet",
        now=5_000.0,
    )

    def fake_get(url, params=None, timeout=None):
        if url.endswith("/chain/summary"):
            latest_block = source["blockchain"].get_latest_block()
            return _FakeResponse(
                {
                    "network_name": "zoidberg-testnet",
                    "node_id": "peer-a",
                    "chain_height": latest_block.index,
                    "latest_block_hash": latest_block.hash,
                    "genesis_hash": source["blockchain"].chain[0].hash,
                    "cumulative_originality_score": source["blockchain"].get_cumulative_originality_score(),
                    "cumulative_work": None,
                }
            )
        if url.endswith("/chain/blocks"):
            from_height = params["from_height"]
            blocks = [
                block
                for block in source["blockchain"].chain
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
                        for certificate in source["blockchain"].originality_certificates
                        if certificate.certificate_id in certificate_ids
                    ],
                }
            )
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("peer_sync.requests.get", fake_get)

    result = sync_chain_from_peers(
        blockchain=target,
        peer_store=target_peer_store,
        network_name="zoidberg-testnet",
    )

    reloaded = Blockchain(storage_backend=target_backend)
    assert result["synced"] == 1
    assert reloaded.get_latest_block().hash == source["blockchain"].get_latest_block().hash
    assert reloaded.get_cumulative_originality_score() == source["blockchain"].get_cumulative_originality_score()


def test_two_node_scripts_point_to_separate_data_dirs():
    init_script = Path("scripts/init_two_node_data.ps1").read_text(encoding="utf-8")
    start_node_a = Path("scripts/start_node_a.ps1").read_text(encoding="utf-8")
    start_node_b = Path("scripts/start_node_b.ps1").read_text(encoding="utf-8")

    assert 'data\\node-a' in init_script
    assert 'data\\node-b' in init_script
    assert "$env:DATA_DIR" in init_script
    assert "$env:NODE_DATA_DIR" in init_script
    assert '$env:DATA_DIR = "data/node-a"' in start_node_a
    assert '$env:DATA_DIR = "data/node-b"' in start_node_b
    assert '$env:NODE_DATA_DIR = "data/node-a"' in start_node_a
    assert '$env:NODE_DATA_DIR = "data/node-b"' in start_node_b
