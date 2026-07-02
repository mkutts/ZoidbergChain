from block import Block
from blockchain import Blockchain
from originality_certificate import OriginalityCertificate
from peers import PeerStore
from peer_sync import receive_peer_block, sync_chain_from_peers
from submission import Submission, VOTE_NOT_ORIGINAL, VOTE_ORIGINAL
from transaction import Transaction


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


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


def _matching_genesis_node(node_a, wallets):
    node_b = Blockchain(
        project_owner_wallet=wallets["owner"],
        Contributor_one=wallets["contributor_one"],
        Contributor_two=wallets["contributor_two"],
    )
    node_b.chain = [_clone_block(node_a.chain[0])]
    node_b.pending_transactions = []
    node_b.submissions = []
    node_b.mint_queue = []
    node_b.votes = []
    node_b.originality_certificates = []
    return node_b


def _copy_supporting_originality_data(source, target):
    target.submissions = [
        Submission.from_dict(submission.to_dict())
        for submission in source.submissions
    ]
    target.votes = [dict(vote) for vote in source.votes]
    target.originality_certificates = [
        OriginalityCertificate.from_dict(certificate.to_dict())
        for certificate in source.originality_certificates
    ]


def _chain_score(chain):
    return round(
        sum(
            getattr(block, "originality_score", 0) or 0
            for block in chain
            if getattr(block, "index", None) != 0
        ),
        8,
    )


def _chain_summary(node, node_id):
    latest_block = node.get_latest_block()
    return {
        "network_name": "zoidberg-testnet",
        "node_id": node_id,
        "chain_height": latest_block.index,
        "latest_block_hash": latest_block.hash,
        "genesis_hash": node.chain[0].hash,
        "cumulative_originality_score": node.get_cumulative_originality_score(),
        "cumulative_work": None,
    }


def _mock_peer_nodes(monkeypatch, peer_nodes_by_url):
    def fake_get(url, params=None, timeout=None):
        for peer_url, peer in peer_nodes_by_url.items():
            if not url.startswith(peer_url.rstrip("/") + "/"):
                continue
            node_id, node = peer
            if url.endswith("/chain/summary"):
                return FakeResponse(_chain_summary(node, node_id))
            if url.endswith("/chain/blocks"):
                from_height = params["from_height"]
                return FakeResponse({
                    "blocks": [
                        block.to_dict()
                        for block in node.chain
                        if block.index >= from_height
                    ]
                })
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("peer_sync.requests.get", fake_get)


def _peer_store(isolated_data_dir, filename="peers.json"):
    peer_store = PeerStore(file_path=str(isolated_data_dir / filename))
    peer_store.register_peer(
        node_id="node-a",
        url="http://node-a.test:8000",
        network_name="zoidberg-testnet",
    )
    return peer_store


def _sync_from_node_a(node_b, node_a, isolated_data_dir, monkeypatch, filename="peers.json"):
    _mock_peer_nodes(monkeypatch, {"http://node-a.test:8000": ("node-a", node_a)})
    return sync_chain_from_peers(
        blockchain=node_b,
        peer_store=_peer_store(isolated_data_dir, filename),
        network_name="zoidberg-testnet",
    )


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
    assert blockchain.mint_next_queued_submission(
        miner=wallets["contributor_one"].public_key,
        validate_meme=False,
    ) is True
    return blockchain.get_latest_block()


def _legacy_block(chain, miner, timestamp=1_000_000.0, text="Legacy verification block"):
    latest_block = chain[-1]
    return Block(
        index=latest_block.index + 1,
        previous_hash=latest_block.hash,
        timestamp=timestamp,
        transactions=[Transaction("REWARD_POOL", miner, 5, created_at=timestamp)],
        miner=miner,
        meme={"encoded_image": "legacy-image", "text": text},
    )


def _legacy_chain(base_chain, miner, count, start_timestamp=1_000_000.0):
    chain = [_clone_block(block) for block in base_chain]
    for offset in range(count):
        chain.append(
            _legacy_block(
                chain,
                miner,
                timestamp=start_timestamp + offset,
                text=f"Legacy verification block {offset}",
            )
        )
    return chain


def _same_height_equal_score_chains(base_chain, wallets):
    first_chain = _legacy_chain(
        base_chain,
        wallets["contributor_one"].public_key,
        count=1,
        start_timestamp=1_000_001.0,
    )
    second_chain = _legacy_chain(
        base_chain,
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


def test_two_node_style_sync_preserves_score_and_validates_certificate_backed_blocks(
    blockchain,
    submission_image,
    wallets,
    isolated_data_dir,
    monkeypatch,
):
    node_a = blockchain
    node_b = _matching_genesis_node(node_a, wallets)
    block = _mint_certified_block(
        node_a,
        submission_image,
        wallets,
        "Two-node certified meme",
        "two-node-certified-voter",
    )
    _copy_supporting_originality_data(node_a, node_b)

    result = _sync_from_node_a(node_b, node_a, isolated_data_dir, monkeypatch)

    assert result["synced"] == 1
    assert node_b.get_latest_block().hash == block.hash
    assert node_b.get_cumulative_originality_score() == node_a.get_cumulative_originality_score()
    assert node_b.is_chain_valid([block.to_dict() for block in node_b.chain]) is True
    assert node_b.get_latest_block().certificate_id == block.certificate_id


def test_two_node_sync_higher_cumulative_originality_score_wins(
    blockchain,
    submission_image,
    wallets,
    isolated_data_dir,
    monkeypatch,
):
    node_a = blockchain
    node_b = _matching_genesis_node(node_a, wallets)
    _mint_certified_block(
        node_a,
        submission_image,
        wallets,
        "Higher score verification meme",
        "higher-score-verification-voter",
    )
    _copy_supporting_originality_data(node_a, node_b)

    result = _sync_from_node_a(node_b, node_a, isolated_data_dir, monkeypatch, "higher-score-peers.json")

    assert result["results"][0]["decision"] == "replace_with_candidate"
    assert result["results"][0]["reason"] == "higher_originality_score"
    assert node_b.get_latest_block().hash == node_a.get_latest_block().hash


def test_two_node_sync_longer_lower_score_chain_loses(
    blockchain,
    submission_image,
    wallets,
    isolated_data_dir,
    monkeypatch,
):
    node_a = blockchain
    node_b = _matching_genesis_node(node_a, wallets)
    _mint_certified_block(
        node_b,
        submission_image,
        wallets,
        "Local higher score verification meme",
        "local-higher-score-voter",
    )
    node_a.chain = _legacy_chain(
        node_b.chain[:1],
        wallets["contributor_two"].public_key,
        count=3,
        start_timestamp=1_000_300.0,
    )

    result = _sync_from_node_a(node_b, node_a, isolated_data_dir, monkeypatch, "lower-score-peers.json")

    assert result["results"][0]["decision"] == "keep_local"
    assert result["results"][0]["reason"] == "lower_originality_score"
    assert node_b.get_cumulative_originality_score() > _chain_score(node_a.chain)
    assert len(node_a.chain) > len(node_b.chain)


def test_two_node_sync_equal_score_higher_height_wins(
    blockchain,
    wallets,
    isolated_data_dir,
    monkeypatch,
):
    node_a = blockchain
    node_b = _matching_genesis_node(node_a, wallets)
    node_a.chain = _legacy_chain(
        node_b.chain,
        wallets["contributor_one"].public_key,
        count=1,
        start_timestamp=1_000_001.0,
    )

    result = _sync_from_node_a(node_b, node_a, isolated_data_dir, monkeypatch, "higher-height-peers.json")

    assert result["results"][0]["decision"] == "replace_with_candidate"
    assert result["results"][0]["reason"] == "higher_chain_height"
    assert node_b.get_latest_block().hash == node_a.get_latest_block().hash


def test_two_node_sync_equal_score_and_height_lower_latest_hash_wins(
    blockchain,
    wallets,
    isolated_data_dir,
    monkeypatch,
):
    node_a = blockchain
    node_b = _matching_genesis_node(node_a, wallets)
    lower_hash_chain, higher_hash_chain = _same_height_equal_score_chains(node_b.chain, wallets)
    node_a.chain = lower_hash_chain
    node_b.chain = higher_hash_chain

    result = _sync_from_node_a(node_b, node_a, isolated_data_dir, monkeypatch, "lower-hash-peers.json")

    assert result["results"][0]["decision"] == "replace_with_candidate"
    assert result["results"][0]["reason"] == "lower_latest_block_hash"
    assert node_b.get_latest_block().hash == lower_hash_chain[-1].hash


def test_two_node_peer_block_mismatch_returns_sync_needed_without_corrupting_chain(
    blockchain,
    wallets,
    isolated_data_dir,
):
    peer_store = _peer_store(isolated_data_dir, "receive-peers.json")
    original_latest_hash = blockchain.get_latest_block().hash
    forked_block = Block(
        index=blockchain.get_latest_block().index + 1,
        previous_hash="not-the-local-tip",
        timestamp=1_000_000.0,
        transactions=[
            Transaction("REWARD_POOL", wallets["contributor_one"].public_key, 5, created_at=1_000_000.0)
        ],
        miner=wallets["contributor_one"].public_key,
        meme={"encoded_image": "peer-image", "text": "Forked verification block"},
    )

    result = receive_peer_block(
        blockchain=blockchain,
        peer_store=peer_store,
        origin_node_id="node-a",
        network_name="zoidberg-testnet",
        block_payload=forked_block.to_dict(),
        related_submission_id=None,
        local_network_name="zoidberg-testnet",
    )

    assert result["status"] == "sync_needed"
    assert result["reason"] == "previous_hash_mismatch"
    assert result["recommended_action"] == "run_chain_sync"
    assert blockchain.get_latest_block().hash == original_latest_hash
    assert all(block.hash != forked_block.hash for block in blockchain.chain)
