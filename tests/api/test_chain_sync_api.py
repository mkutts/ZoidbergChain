from fastapi.testclient import TestClient

from block import Block
from peers import PeerStore
from submission import VOTE_NOT_ORIGINAL, VOTE_ORIGINAL
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


def _chain_score(chain):
    return round(
        sum(
            getattr(block, "originality_score", 0) or 0
            for block in chain
            if getattr(block, "index", None) != 0
        ),
        8,
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


def _legacy_chain(base_chain, miner, count, start_timestamp=1_000_000.0):
    chain = list(base_chain)
    for offset in range(count):
        chain.append(
            _next_block(
                chain,
                miner,
                timestamp=start_timestamp + offset,
                text=f"Legacy peer block {offset}",
            )
        )
    return chain


def _same_height_equal_score_chains(blockchain, wallets):
    first_chain = _legacy_chain(
        blockchain.chain,
        wallets["contributor_one"].public_key,
        count=1,
        start_timestamp=1_000_001.0,
    )
    second_chain = _legacy_chain(
        blockchain.chain,
        wallets["contributor_two"].public_key,
        count=1,
        start_timestamp=1_000_002.0,
    )
    lower_hash_chain, higher_hash_chain = sorted(
        [first_chain, second_chain],
        key=lambda chain: chain[-1].hash,
    )
    assert lower_hash_chain[-1].hash < higher_hash_chain[-1].hash
    return lower_hash_chain, higher_hash_chain


def _mint_certified_block(blockchain, submission_image, wallets, text, voter_prefix):
    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content=text,
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
            voter=f"{voter_prefix}-{index}",
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
    return blockchain.get_latest_block()


def _certified_chain_from_base(
    blockchain,
    base_chain,
    submission_image,
    wallets,
    text="Peer certified meme",
    voter_prefix="peer-certified-voter",
):
    saved_chain = list(blockchain.chain)
    blockchain.chain = list(base_chain)
    block = _mint_certified_block(blockchain, submission_image, wallets, text, voter_prefix)
    peer_chain = list(blockchain.chain)
    blockchain.chain = saved_chain
    return peer_chain, block


def _summary(
    chain,
    network_name="zoidberg-testnet",
    node_id="peer-node-1",
    cumulative_originality_score=None,
):
    return {
        "network_name": network_name,
        "node_id": node_id,
        "chain_height": chain[-1].index,
        "latest_block_hash": chain[-1].hash,
        "genesis_hash": chain[0].hash,
        "cumulative_originality_score": (
            _chain_score(chain)
            if cumulative_originality_score is None
            else cumulative_originality_score
        ),
        "cumulative_work": None,
    }


def _mock_peer_chain(monkeypatch, peer_chain, summary_overrides=None, blocks_override=None):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append({"url": url, "params": params, "timeout": timeout})
        if url.endswith("/chain/summary"):
            peer_summary = _summary(peer_chain)
            if summary_overrides:
                peer_summary.update(summary_overrides)
            return FakeResponse(peer_summary)
        if url.endswith("/chain/blocks"):
            if blocks_override is not None:
                return FakeResponse({"blocks": blocks_override})
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


def _mock_peer_chains(monkeypatch, peer_chains_by_url):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append({"url": url, "params": params, "timeout": timeout})
        for peer_url, peer_chain in peer_chains_by_url.items():
            if not url.startswith(peer_url.rstrip("/") + "/"):
                continue
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
        "cumulative_originality_score": 0,
        "cumulative_work": None,
    }


def test_chain_summary_reports_cumulative_originality_score(
    blockchain,
    submission_image,
    wallets,
):
    client = _client(blockchain)
    latest_block = _mint_certified_block(
        blockchain,
        submission_image,
        wallets,
        "Summary scored meme",
        "summary-voter",
    )

    response = client.get("/chain/summary")

    assert response.status_code == 200
    assert response.json()["latest_block_hash"] == latest_block.hash
    assert response.json()["cumulative_originality_score"] == latest_block.originality_score


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


def test_sync_uses_cumulative_originality_score_instead_of_height(
    blockchain,
    submission_image,
    wallets,
    monkeypatch,
):
    peer_chain, _peer_block = _certified_chain_from_base(
        blockchain,
        blockchain.chain,
        submission_image,
        wallets,
        "Local certified meme",
        "local-score-voter",
    )
    blockchain.chain = peer_chain
    local_tip = blockchain.get_latest_block()
    longer_lower_score_peer = _legacy_chain(
        blockchain.chain[:1],
        wallets["contributor_two"].public_key,
        count=2,
        start_timestamp=1_000_300.0,
    )
    client = _client(blockchain)
    _register_peer()
    calls = _mock_peer_chain(monkeypatch, longer_lower_score_peer)

    response = client.post("/chain/sync")

    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "skipped"
    assert response.json()["results"][0]["decision"] == "keep_local"
    assert response.json()["results"][0]["reason"] == "lower_originality_score"
    assert all(not call["url"].endswith("/chain/blocks") for call in calls)
    assert blockchain.get_latest_block().hash == local_tip.hash


def test_sync_replaces_local_chain_with_valid_higher_score_peer(
    blockchain,
    submission_image,
    wallets,
    monkeypatch,
):
    client = _client(blockchain)
    _register_peer()
    peer_chain, peer_block = _certified_chain_from_base(
        blockchain,
        blockchain.chain,
        submission_image,
        wallets,
        "Peer certified replacement",
        "peer-replace-voter",
    )
    _mock_peer_chain(monkeypatch, peer_chain)

    response = client.post("/chain/sync")

    assert response.status_code == 200
    assert response.json()["synced"] == 1
    assert response.json()["results"][0]["decision"] == "replace_with_candidate"
    assert response.json()["results"][0]["reason"] == "higher_originality_score"
    assert response.json()["results"][0]["candidate_score"] == peer_block.originality_score
    assert blockchain.get_latest_block().hash == peer_block.hash


def test_sync_accepts_shorter_higher_score_peer_chain(
    blockchain,
    submission_image,
    wallets,
    monkeypatch,
):
    local_chain = _legacy_chain(
        blockchain.chain,
        wallets["contributor_one"].public_key,
        count=2,
        start_timestamp=1_000_200.0,
    )
    blockchain.chain = local_chain
    peer_chain, peer_block = _certified_chain_from_base(
        blockchain,
        local_chain[:1],
        submission_image,
        wallets,
        "Shorter peer with stronger originality",
        "shorter-peer-voter",
    )
    client = _client(blockchain)
    _register_peer()
    _mock_peer_chain(monkeypatch, peer_chain)

    response = client.post("/chain/sync")

    assert response.status_code == 200
    assert response.json()["synced"] == 1
    assert response.json()["results"][0]["peer_height"] < local_chain[-1].index
    assert blockchain.get_latest_block().hash == peer_block.hash


def test_sync_accepts_equal_score_higher_height_peer_chain(blockchain, wallets, monkeypatch):
    client = _client(blockchain)
    _register_peer()
    peer_chain = _legacy_chain(
        blockchain.chain,
        wallets["contributor_one"].public_key,
        count=1,
        start_timestamp=1_000_001.0,
    )
    _mock_peer_chain(monkeypatch, peer_chain)

    response = client.post("/chain/sync")

    assert response.status_code == 200
    assert response.json()["synced"] == 1
    assert response.json()["results"][0]["decision"] == "replace_with_candidate"
    assert response.json()["results"][0]["reason"] == "higher_chain_height"
    assert blockchain.get_latest_block().hash == peer_chain[-1].hash


def test_sync_accepts_equal_score_and_height_lower_latest_hash_peer_chain(
    blockchain,
    wallets,
    monkeypatch,
):
    lower_hash_chain, higher_hash_chain = _same_height_equal_score_chains(blockchain, wallets)
    blockchain.chain = higher_hash_chain
    client = _client(blockchain)
    _register_peer()
    _mock_peer_chain(monkeypatch, lower_hash_chain)

    response = client.post("/chain/sync")

    assert response.status_code == 200
    assert response.json()["synced"] == 1
    assert response.json()["results"][0]["decision"] == "replace_with_candidate"
    assert response.json()["results"][0]["reason"] == "lower_latest_block_hash"
    assert response.json()["results"][0]["candidate_latest_hash"] < response.json()["results"][0]["local_latest_hash"]
    assert blockchain.get_latest_block().hash == lower_hash_chain[-1].hash


def test_sync_treats_same_latest_block_hash_as_equivalent(blockchain, monkeypatch):
    client = _client(blockchain)
    _register_peer()
    calls = _mock_peer_chain(monkeypatch, list(blockchain.chain))

    response = client.post("/chain/sync")

    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "skipped"
    assert response.json()["results"][0]["decision"] == "equivalent"
    assert response.json()["results"][0]["reason"] == "same_latest_block_hash"
    assert all(not call["url"].endswith("/chain/blocks") for call in calls)


def test_sync_result_is_deterministic_independent_of_peer_order(
    blockchain,
    wallets,
    monkeypatch,
):
    lower_hash_chain, higher_hash_chain = _same_height_equal_score_chains(blockchain, wallets)
    genesis_chain = list(blockchain.chain)
    lower_peer_url = "http://peer-low.test:8000"
    higher_peer_url = "http://peer-high.test:8000"
    peer_chains = {
        lower_peer_url: lower_hash_chain,
        higher_peer_url: higher_hash_chain,
    }

    def sync_with_order(peer_order):
        import api

        blockchain.chain = list(genesis_chain)
        client = _client(blockchain)
        api.peer_store._save_peers([])
        for node_id, peer_url in peer_order:
            _register_peer(node_id=node_id, url=peer_url)
        _mock_peer_chains(monkeypatch, peer_chains)
        response = client.post("/chain/sync")
        assert response.status_code == 200
        return blockchain.get_latest_block().hash

    first_order_hash = sync_with_order([
        ("peer-high", higher_peer_url),
        ("peer-low", lower_peer_url),
    ])
    second_order_hash = sync_with_order([
        ("peer-low", lower_peer_url),
        ("peer-high", higher_peer_url),
    ])

    assert first_order_hash == lower_hash_chain[-1].hash
    assert second_order_hash == lower_hash_chain[-1].hash


def test_sync_rejects_peer_with_different_genesis_hash(blockchain, wallets, monkeypatch):
    client = _client(blockchain)
    _register_peer()
    peer_chain = _legacy_chain(blockchain.chain, wallets["contributor_one"].public_key, count=1)
    calls = _mock_peer_chain(
        monkeypatch,
        peer_chain,
        summary_overrides={"genesis_hash": "different-genesis"},
    )

    response = client.post("/chain/sync")

    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "skipped"
    assert response.json()["results"][0]["decision"] == "invalid_candidate"
    assert response.json()["results"][0]["reason"] == "different_genesis_hash"
    assert all(not call["url"].endswith("/chain/blocks") for call in calls)
    assert blockchain.get_latest_block().hash == blockchain.chain[0].hash


def test_sync_rejects_invalid_higher_score_chain(
    blockchain,
    submission_image,
    wallets,
    monkeypatch,
):
    client = _client(blockchain)
    _register_peer()
    peer_chain, peer_block = _certified_chain_from_base(
        blockchain,
        blockchain.chain,
        submission_image,
        wallets,
        "Invalid higher score peer",
        "invalid-peer-voter",
    )
    invalid_block = peer_block.to_dict()
    invalid_block["hash"] = "invalid-hash"
    _mock_peer_chain(
        monkeypatch,
        peer_chain,
        summary_overrides={"latest_block_hash": "invalid-hash"},
        blocks_override=[peer_chain[0].to_dict(), invalid_block],
    )

    response = client.post("/chain/sync")

    assert response.status_code == 200
    assert response.json()["failed"] == 1
    assert response.json()["results"][0]["status"] == "failed"
    assert "Block hash does not match block contents." in response.json()["results"][0]["reason"]
    assert blockchain.get_latest_block().index == 0


def test_sync_keeps_equal_score_and_height_higher_latest_hash_peer_chain(
    blockchain,
    wallets,
    monkeypatch,
):
    lower_hash_chain, higher_hash_chain = _same_height_equal_score_chains(blockchain, wallets)
    blockchain.chain = lower_hash_chain
    client = _client(blockchain)
    _register_peer()
    calls = _mock_peer_chain(monkeypatch, higher_hash_chain)

    response = client.post("/chain/sync")

    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "skipped"
    assert response.json()["results"][0]["decision"] == "keep_local"
    assert response.json()["results"][0]["reason"] == "higher_latest_block_hash"
    assert all(not call["url"].endswith("/chain/blocks") for call in calls)
    assert blockchain.get_latest_block().hash == lower_hash_chain[-1].hash


def test_successful_sync_preserves_existing_submissions_and_votes(
    blockchain,
    submission_image,
    wallets,
    monkeypatch,
):
    peer_chain, peer_block = _certified_chain_from_base(
        blockchain,
        blockchain.chain,
        submission_image,
        wallets,
        "Peer preserves local metadata",
        "preserve-peer-voter",
    )
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
    client = _client(blockchain)
    _register_peer()
    _mock_peer_chain(monkeypatch, peer_chain)

    response = client.post("/chain/sync")

    assert response.status_code == 200
    assert response.json()["synced"] == 1
    assert blockchain.get_submission(submission.submission_id) is submission
    assert vote in blockchain.votes
    assert blockchain.get_latest_block().hash == peer_block.hash
