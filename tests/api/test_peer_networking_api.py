import json
from pathlib import Path

from fastapi.testclient import TestClient

from submission import VOTE_NOT_ORIGINAL, VOTE_ORIGINAL


def _client(blockchain):
    import api

    api.NODE_ID = "local-node"
    api.PUBLIC_NODE_URL = "http://localhost:8000"
    api.NETWORK_NAME = "zoidberg-testnet"
    api.blockchain = blockchain
    return TestClient(api.app)


def test_node_info_response(blockchain):
    client = _client(blockchain)
    latest_block = blockchain.get_latest_block()

    response = client.get("/node-info")

    assert response.status_code == 200
    assert response.json() == {
        "node_id": "local-node",
        "public_node_url": "http://localhost:8000",
        "network_name": "zoidberg-testnet",
        "chain_height": latest_block.index,
        "latest_block_hash": latest_block.hash,
        "cumulative_originality_score": 0,
    }


def test_node_info_includes_cumulative_originality_score_for_scored_chain(
    blockchain,
    submission_image,
    wallets,
):
    client = _client(blockchain)
    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Node info scored meme",
        submitter=wallets["owner"].public_key,
    )
    for index, vote_type in enumerate([
        VOTE_ORIGINAL,
        VOTE_ORIGINAL,
        VOTE_ORIGINAL,
        VOTE_ORIGINAL,
        VOTE_NOT_ORIGINAL,
    ]):
        blockchain.cast_submission_vote(
            submission_id=submission.submission_id,
            voter=f"node-info-voter-{index}",
            vote_type=vote_type,
            created_at=1_000_000 + index,
        )
    blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=1_000_100,
    )
    blockchain.add_to_mint_queue(submission.submission_id)
    blockchain.mint_next_queued_submission(
        miner=wallets["contributor_one"].public_key,
        validate_meme=False,
    )

    response = client.get("/node-info")

    assert response.status_code == 200
    assert response.json()["cumulative_originality_score"] == blockchain.get_latest_block().originality_score


def test_registering_valid_peer(blockchain, monkeypatch):
    client = _client(blockchain)
    monkeypatch.setattr("peers.time.time", lambda: 100.0)

    response = client.post(
        "/peers/register",
        json={
            "node_id": "peer-node-1",
            "url": "http://peer-one.test:8000/",
            "network_name": "zoidberg-testnet",
        },
    )

    assert response.status_code == 200
    assert response.json()["peer"] == {
        "node_id": "peer-node-1",
        "url": "http://peer-one.test:8000",
        "network_name": "zoidberg-testnet",
        "last_seen": 100.0,
        "status": "active",
    }
    assert json.loads(Path("peers.json").read_text())[0]["node_id"] == "peer-node-1"


def test_register_peer_rejects_wrong_network(blockchain):
    client = _client(blockchain)

    response = client.post(
        "/peers/register",
        json={
            "node_id": "peer-node-1",
            "url": "http://peer-one.test:8000",
            "network_name": "zoidberg-mainnet",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Peer belongs to a different network."
    assert client.get("/peers").json() == {"peers": []}


def test_register_peer_rejects_invalid_url(blockchain):
    client = _client(blockchain)

    response = client.post(
        "/peers/register",
        json={
            "node_id": "peer-node-1",
            "url": "not-a-url",
            "network_name": "zoidberg-testnet",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Peer URL must be a valid http or https URL."
    assert client.get("/peers").json() == {"peers": []}


def test_register_peer_rejects_self(blockchain):
    client = _client(blockchain)

    response = client.post(
        "/peers/register",
        json={
            "node_id": "local-node",
            "url": "http://peer-one.test:8000",
            "network_name": "zoidberg-testnet",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot register this node as a peer."
    assert client.get("/peers").json() == {"peers": []}


def test_register_existing_peer_updates_last_seen(blockchain, monkeypatch):
    client = _client(blockchain)
    peer_payload = {
        "node_id": "peer-node-1",
        "url": "http://peer-one.test:8000",
        "network_name": "zoidberg-testnet",
    }

    monkeypatch.setattr("peers.time.time", lambda: 100.0)
    first_response = client.post("/peers/register", json=peer_payload)

    monkeypatch.setattr("peers.time.time", lambda: 200.0)
    second_response = client.post("/peers/register", json=peer_payload)

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    peers = client.get("/peers").json()["peers"]
    assert len(peers) == 1
    assert peers[0]["last_seen"] == 200.0
    assert peers[0]["status"] == "active"


def test_listing_peers(blockchain, monkeypatch):
    client = _client(blockchain)
    monkeypatch.setattr("peers.time.time", lambda: 100.0)

    client.post(
        "/peers/register",
        json={
            "node_id": "peer-node-1",
            "url": "http://peer-one.test:8000",
            "network_name": "zoidberg-testnet",
        },
    )
    client.post(
        "/peers/register",
        json={
            "node_id": "peer-node-2",
            "url": "https://peer-two.test",
            "network_name": "zoidberg-testnet",
        },
    )

    response = client.get("/peers")

    assert response.status_code == 200
    assert response.json()["peers"] == [
        {
            "node_id": "peer-node-1",
            "url": "http://peer-one.test:8000",
            "network_name": "zoidberg-testnet",
            "last_seen": 100.0,
            "status": "active",
        },
        {
            "node_id": "peer-node-2",
            "url": "https://peer-two.test",
            "network_name": "zoidberg-testnet",
            "last_seen": 100.0,
            "status": "active",
        },
    ]
