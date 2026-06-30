import json
from pathlib import Path

from fastapi.testclient import TestClient


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
    }


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
