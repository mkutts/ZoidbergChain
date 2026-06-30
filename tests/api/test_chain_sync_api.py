from fastapi.testclient import TestClient

from block import Block
from peers import PeerStore
from submission import VOTE_ORIGINAL
from transaction import Transaction


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


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


def _next_block(chain, miner, timestamp=1_000_000.0, text="Synced peer block"):
    latest_block = chain[-1]
    return Block(
        index=latest_block.index + 1,
        previous_hash=latest_block.hash,
        timestamp=timestamp,
        transactions=[Transaction("REWARD_POOL", miner, 5, created_at=timestamp)],
        miner=miner,
        meme={"encoded_image": "peer-image", "text": text},
    )


def _summary(chain, network_name="zoidberg-testnet", node_id="peer-node-1"):
    return {
        "network_name": network_name,
        "node_id": node_id,
        "chain_height": chain[-1].index,
        "latest_block_hash": chain[-1].hash,
        "genesis_hash": chain[0].hash,
        "cumulative_work": None,
    }


def _mock_peer_chain(monkeypatch, peer_chain):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append({"url": url, "params": params, "timeout": timeout})
        if url.endswith("/chain/summary"):
            return FakeResponse(_summary(peer_chain))
        if url.endswith("/chain/blocks"):
            from_height = params["from_height"]
            return FakeResponse({
                "blocks": [
                    block.to_dict()
                    for block in peer_chain
                    if block.index >= from_height
                ]
            })
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("peer_sync.requests.get", fake_get)
    return calls


def test_chain_summary_endpoint(blockchain):
    client = _client(blockchain)
    latest_block = blockchain.get_latest_block()

    response = client.get("/chain/summary")

    assert response.status_code == 200
    assert response.json() == {
        "network_name": "zoidberg-testnet",
        "node_id": "local-node",
        "chain_height": latest_block.index,
        "latest_block_hash": latest_block.hash,
        "genesis_hash": blockchain.chain[0].hash,
        "cumulative_work": None,
    }


def test_fetching_blocks_from_height(blockchain, wallets):
    client = _client(blockchain)
    first_block = _next_block(blockchain.chain, wallets["contributor_one"].public_key, timestamp=1_000_001.0)
    second_block = _next_block(blockchain.chain + [first_block], wallets["contributor_two"].public_key, timestamp=1_000_002.0)
    blockchain.chain.extend([first_block, second_block])

    response = client.get("/chain/blocks", params={"from_height": 1})

    assert response.status_code == 200
    assert [block["hash"] for block in response.json()["blocks"]] == [
        first_block.hash,
        second_block.hash,
    ]


def test_sync_from_longer_valid_peer_chain(blockchain, wallets, monkeypatch):
    client = _client(blockchain)
    _register_peer()
    peer_block = _next_block(blockchain.chain, wallets["contributor_one"].public_key)
    peer_chain = list(blockchain.chain) + [peer_block]
    _mock_peer_chain(monkeypatch, peer_chain)

    response = client.post("/chain/sync")

    assert response.status_code == 200
    assert response.json()["synced"] == 1
    assert response.json()["results"][0]["appended"] == 1
    assert blockchain.get_latest_block().hash == peer_block.hash


def test_sync_rejects_peer_with_different_genesis_hash(blockchain, wallets, monkeypatch):
    client = _client(blockchain)
    _register_peer()
    peer_block = _next_block(blockchain.chain, wallets["contributor_one"].public_key)
    peer_chain = list(blockchain.chain) + [peer_block]
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        peer_summary = _summary(peer_chain)
        peer_summary["genesis_hash"] = "different-genesis"
        return FakeResponse(peer_summary)

    monkeypatch.setattr("peer_sync.requests.get", fake_get)

    response = client.post("/chain/sync")

    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "skipped"
    assert response.json()["results"][0]["reason"] == "different_genesis_hash"
    assert all(not url.endswith("/chain/blocks") for url in calls)
    assert blockchain.get_latest_block().hash == blockchain.chain[0].hash


def test_sync_rejects_shorter_peer_chain(blockchain, wallets, monkeypatch):
    local_block = _next_block(blockchain.chain, wallets["contributor_one"].public_key)
    blockchain.chain.append(local_block)
    client = _client(blockchain)
    _register_peer()
    peer_chain = blockchain.chain[:1]
    _mock_peer_chain(monkeypatch, peer_chain)

    response = client.post("/chain/sync")

    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "skipped"
    assert response.json()["results"][0]["reason"] == "peer_chain_shorter"
    assert blockchain.get_latest_block().hash == local_block.hash


def test_sync_rejects_invalid_fetched_block(blockchain, wallets, monkeypatch):
    client = _client(blockchain)
    _register_peer()
    peer_block = _next_block(blockchain.chain, wallets["contributor_one"].public_key)
    invalid_block = peer_block.to_dict()
    invalid_block["hash"] = "invalid-hash"

    def fake_get(url, params=None, timeout=None):
        if url.endswith("/chain/summary"):
            peer_summary = _summary(list(blockchain.chain) + [peer_block])
            peer_summary["latest_block_hash"] = "invalid-hash"
            return FakeResponse(peer_summary)
        if url.endswith("/chain/blocks"):
            return FakeResponse({"blocks": [invalid_block]})
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("peer_sync.requests.get", fake_get)

    response = client.post("/chain/sync")

    assert response.status_code == 200
    assert response.json()["failed"] == 1
    assert response.json()["results"][0]["status"] == "failed"
    assert "Block hash does not match block contents." in response.json()["results"][0]["reason"]
    assert blockchain.get_latest_block().index == 0


def test_sync_does_not_resolve_equal_height_fork(blockchain, wallets, monkeypatch):
    local_block = _next_block(blockchain.chain, wallets["contributor_one"].public_key, timestamp=1_000_001.0)
    peer_block = _next_block(blockchain.chain, wallets["contributor_two"].public_key, timestamp=1_000_002.0)
    blockchain.chain.append(local_block)
    client = _client(blockchain)
    _register_peer()
    peer_chain = blockchain.chain[:1] + [peer_block]
    _mock_peer_chain(monkeypatch, peer_chain)

    response = client.post("/chain/sync")

    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "skipped"
    assert response.json()["results"][0]["reason"] == "equal_height_fork_not_resolved"
    assert blockchain.get_latest_block().hash == local_block.hash


def test_successful_sync_preserves_existing_submissions_and_votes(
    blockchain,
    submission_image,
    wallets,
    monkeypatch,
):
    client = _client(blockchain)
    _register_peer()
    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Preserve local state",
        submitter=wallets["owner"].public_key,
    )
    vote = blockchain.cast_submission_vote(
        submission_id=submission.submission_id,
        voter=wallets["contributor_one"].public_key,
        vote_type=VOTE_ORIGINAL,
        created_at=1_000_000.0,
    )
    peer_block = _next_block(blockchain.chain, wallets["contributor_two"].public_key)
    peer_chain = list(blockchain.chain) + [peer_block]
    _mock_peer_chain(monkeypatch, peer_chain)

    response = client.post("/chain/sync")

    assert response.status_code == 200
    assert response.json()["synced"] == 1
    assert blockchain.get_submission(submission.submission_id) is submission
    assert blockchain.votes == [vote]
    assert blockchain.get_latest_block().hash == peer_block.hash
