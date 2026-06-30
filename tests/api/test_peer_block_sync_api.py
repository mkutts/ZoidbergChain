import requests
from fastapi.testclient import TestClient

from block import Block
from peers import PeerStore
from submission import APPROVED, MINTED
from transaction import Transaction


def _client(blockchain):
    import api

    api.NODE_ID = "local-node"
    api.PUBLIC_NODE_URL = "http://localhost:8000"
    api.NETWORK_NAME = "zoidberg-testnet"
    api.blockchain = blockchain
    api.peer_store = PeerStore()
    return TestClient(api.app)


def _register_peer(node_id="peer-node-1", url="http://peer-one.test:8000"):
    import api

    return api.peer_store.register_peer(
        node_id=node_id,
        url=url,
        network_name="zoidberg-testnet",
    )


def _peer_block(blockchain, miner):
    latest_block = blockchain.get_latest_block()
    return Block(
        index=latest_block.index + 1,
        previous_hash=latest_block.hash,
        timestamp=1_000_000.0,
        transactions=[Transaction("REWARD_POOL", miner, 5, created_at=1_000_000.0)],
        miner=miner,
        meme={"encoded_image": "peer-image", "text": "Peer minted block"},
    )


def _receive_payload(block, origin_node_id="peer-node-1", network_name="zoidberg-testnet", related_submission_id=None):
    return {
        "origin_node_id": origin_node_id,
        "network_name": network_name,
        "block": block.to_dict(),
        "related_submission_id": related_submission_id,
    }


def _submission(blockchain, submission_image, submitter):
    return blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Peer block submission",
        submitter=submitter,
    )


def test_receiving_valid_peer_block_extends_chain(blockchain, wallets):
    client = _client(blockchain)
    _register_peer()
    block = _peer_block(blockchain, wallets["contributor_one"].public_key)
    starting_height = len(blockchain.chain)

    response = client.post("/peers/blocks/receive", json=_receive_payload(block))

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert response.json()["action"] == "appended"
    assert len(blockchain.chain) == starting_height + 1
    assert blockchain.get_latest_block().hash == block.hash


def test_receive_peer_block_rejects_unregistered_peer(blockchain, wallets):
    client = _client(blockchain)
    block = _peer_block(blockchain, wallets["contributor_one"].public_key)

    response = client.post("/peers/blocks/receive", json=_receive_payload(block))

    assert response.status_code == 403
    assert response.json()["detail"] == "Peer is not registered or active."
    assert blockchain.get_latest_block().hash != block.hash


def test_receive_peer_block_rejects_wrong_network(blockchain, wallets):
    client = _client(blockchain)
    _register_peer()
    block = _peer_block(blockchain, wallets["contributor_one"].public_key)

    response = client.post(
        "/peers/blocks/receive",
        json=_receive_payload(block, network_name="zoidberg-mainnet"),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Peer block belongs to a different network."
    assert blockchain.get_latest_block().hash != block.hash


def test_receive_peer_block_rejects_malformed_block(blockchain):
    client = _client(blockchain)
    _register_peer()

    response = client.post(
        "/peers/blocks/receive",
        json={
            "origin_node_id": "peer-node-1",
            "network_name": "zoidberg-testnet",
            "block": {"index": 1},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Block previous_hash is required."
    assert len(blockchain.chain) == 1


def test_receive_peer_block_rejects_duplicate_block(blockchain, wallets):
    client = _client(blockchain)
    _register_peer()
    block = _peer_block(blockchain, wallets["contributor_one"].public_key)

    assert client.post("/peers/blocks/receive", json=_receive_payload(block)).status_code == 200
    duplicate_response = client.post("/peers/blocks/receive", json=_receive_payload(block))

    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["detail"] == "Block already exists."
    assert len(blockchain.chain) == 2


def test_receive_peer_block_rejects_mismatched_previous_hash(blockchain, wallets):
    client = _client(blockchain)
    _register_peer()
    latest_block = blockchain.get_latest_block()
    block = Block(
        index=latest_block.index + 1,
        previous_hash="not-the-local-tip",
        timestamp=1_000_000.0,
        transactions=[Transaction("REWARD_POOL", wallets["contributor_one"].public_key, 5)],
        miner=wallets["contributor_one"].public_key,
        meme={"encoded_image": "peer-image", "text": "Forked block"},
    )

    response = client.post("/peers/blocks/receive", json=_receive_payload(block))

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Block does not extend the local chain tip. Fork resolution is not implemented yet."
    )
    assert len(blockchain.chain) == 1


def test_known_submission_status_becomes_minted_when_peer_block_references_it(
    blockchain,
    submission_image,
    wallets,
):
    client = _client(blockchain)
    _register_peer()
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    block = _peer_block(blockchain, wallets["contributor_one"].public_key)

    response = client.post(
        "/peers/blocks/receive",
        json=_receive_payload(block, related_submission_id=submission.submission_id),
    )

    assert response.status_code == 200
    assert submission.status == MINTED


def test_local_mint_broadcasts_block_without_failing_if_one_peer_is_down(
    blockchain,
    submission_image,
    wallets,
    monkeypatch,
):
    client = _client(blockchain)
    _register_peer("peer-up", "http://peer-up.test")
    _register_peer("peer-down", "http://peer-down.test")
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    submission.transition_to(APPROVED)
    blockchain.add_to_mint_queue(submission.submission_id)
    calls = []

    def fake_post(url, json, timeout):
        calls.append({"url": url, "json": json, "timeout": timeout})
        if "peer-down" in url:
            raise requests.RequestException("connection refused")
        return type("Response", (), {"status_code": 200, "text": "ok"})()

    monkeypatch.setattr("peer_sync.requests.post", fake_post)

    response = client.post(f"/mint-queue/{submission.submission_id}/mint")

    assert response.status_code == 200
    assert response.json()["minted"] is True
    assert response.json()["broadcast"]["attempted"] == 2
    assert response.json()["broadcast"]["succeeded"] == 1
    assert response.json()["broadcast"]["failed"] == 1
    assert len(calls) == 2
    assert all(call["url"].endswith("/peers/blocks/receive") for call in calls)
    assert calls[0]["json"]["related_submission_id"] == submission.submission_id


def test_manual_block_rebroadcast_endpoint_works(blockchain, wallets, monkeypatch):
    client = _client(blockchain)
    _register_peer()
    block = _peer_block(blockchain, wallets["contributor_one"].public_key)
    blockchain.chain.append(block)
    calls = []

    def fake_post(url, json, timeout):
        calls.append({"url": url, "json": json, "timeout": timeout})
        return type("Response", (), {"status_code": 200, "text": "ok"})()

    monkeypatch.setattr("peer_sync.requests.post", fake_post)

    response = client.post(f"/blocks/{block.hash}/broadcast")

    assert response.status_code == 200
    assert response.json()["broadcast"]["attempted"] == 1
    assert response.json()["broadcast"]["succeeded"] == 1
    assert calls[0]["url"] == "http://peer-one.test:8000/peers/blocks/receive"
    assert calls[0]["json"]["origin_node_id"] == "local-node"
    assert calls[0]["json"]["network_name"] == "zoidberg-testnet"
    assert calls[0]["json"]["block"]["hash"] == block.hash
