import requests
from fastapi.testclient import TestClient

from block import Block
from peers import PeerStore
from submission import APPROVED, MINTED, VOTE_NOT_ORIGINAL, VOTE_ORIGINAL
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


def _receive_payload_with_certificate(
    block,
    certificate,
    origin_node_id="peer-node-1",
    network_name="zoidberg-testnet",
    related_submission_id=None,
):
    payload = _receive_payload(
        block,
        origin_node_id=origin_node_id,
        network_name=network_name,
        related_submission_id=related_submission_id,
    )
    payload["certificate"] = certificate.to_dict()
    return payload


def _submission(blockchain, submission_image, submitter):
    return blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Peer block submission",
        submitter=submitter,
    )


def _certify_submission(blockchain, submission):
    for index, vote_type in enumerate([
        VOTE_ORIGINAL,
        VOTE_ORIGINAL,
        VOTE_ORIGINAL,
        VOTE_ORIGINAL,
        VOTE_NOT_ORIGINAL,
    ]):
        blockchain.cast_submission_vote(
            submission_id=submission.submission_id,
            voter=f"peer-block-voter-{index}",
            vote_type=vote_type,
            created_at=1_000_000 + index,
        )
    submission.transition_to(APPROVED)
    return blockchain.create_originality_certificate(submission.submission_id, approved_at=1_000_100)


def _certified_peer_block(blockchain, submission_image, wallets):
    original_chain = list(blockchain.chain)
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    _certify_submission(blockchain, submission)
    blockchain.add_to_mint_queue(submission.submission_id)
    minted_block = blockchain.mint_next_queued_submission(
        miner=wallets["contributor_one"].public_key,
        validate_meme=False,
    )
    assert minted_block is not False
    block = blockchain.get_latest_block()
    blockchain.chain = original_chain
    return submission, block


def _rehash(blockchain, block_dict):
    block_dict["hash"] = blockchain.calculate_hash_from_dict(block_dict)
    return block_dict


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


def test_receiving_direct_extending_block_with_invalid_certificate_is_rejected(
    blockchain,
    submission_image,
    wallets,
):
    client = _client(blockchain)
    _register_peer()
    _submission, block = _certified_peer_block(blockchain, submission_image, wallets)
    block_dict = block.to_dict()
    block_dict["certificate_id"] = "unknown-certificate"
    _rehash(blockchain, block_dict)

    response = client.post(
        "/peers/blocks/receive",
        json={
            "origin_node_id": "peer-node-1",
            "network_name": "zoidberg-testnet",
            "block": block_dict,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Block references unknown originality certificate."
    assert len(blockchain.chain) == 1


def test_receiving_direct_extending_block_with_mismatched_originality_score_is_rejected(
    blockchain,
    submission_image,
    wallets,
):
    client = _client(blockchain)
    _register_peer()
    _submission, block = _certified_peer_block(blockchain, submission_image, wallets)
    block_dict = block.to_dict()
    block_dict["originality_score"] = block_dict["originality_score"] + 1
    _rehash(blockchain, block_dict)

    response = client.post(
        "/peers/blocks/receive",
        json={
            "origin_node_id": "peer-node-1",
            "network_name": "zoidberg-testnet",
            "block": block_dict,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Block certificate metadata originality_score does not match certificate."
    assert len(blockchain.chain) == 1


def test_receiving_direct_extending_block_with_mismatched_reward_recipient_is_rejected(
    blockchain,
    submission_image,
    wallets,
):
    client = _client(blockchain)
    _register_peer()
    _submission, block = _certified_peer_block(blockchain, submission_image, wallets)
    block_dict = block.to_dict()
    block_dict["reward_recipient"] = wallets["contributor_two"].public_key
    _rehash(blockchain, block_dict)

    response = client.post(
        "/peers/blocks/receive",
        json={
            "origin_node_id": "peer-node-1",
            "network_name": "zoidberg-testnet",
            "block": block_dict,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Block reward_recipient does not match submission creator wallet."
    assert len(blockchain.chain) == 1


def test_receive_peer_block_succeeds_with_included_certificate(
    blockchain,
    submission_image,
    wallets,
):
    client = _client(blockchain)
    _register_peer()
    submission, block = _certified_peer_block(blockchain, submission_image, wallets)
    certificate = blockchain.get_originality_certificate(block.certificate_id)
    blockchain.originality_certificates = []

    response = client.post(
        "/peers/blocks/receive",
        json=_receive_payload_with_certificate(
            block,
            certificate,
            related_submission_id=submission.submission_id,
        ),
    )

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert response.json()["certificate"]["certificate_id"] == certificate.certificate_id
    assert blockchain.get_latest_block().hash == block.hash


def test_receive_peer_block_succeeds_after_certificate_was_synced_first(
    blockchain,
    submission_image,
    wallets,
):
    client = _client(blockchain)
    _register_peer()
    submission, block = _certified_peer_block(blockchain, submission_image, wallets)
    certificate = blockchain.get_originality_certificate(block.certificate_id)
    blockchain.originality_certificates = []

    certificate_response = client.post(
        "/peers/certificates/receive",
        json={
            "origin_node_id": "peer-node-1",
            "network_name": "zoidberg-testnet",
            "certificate": certificate.to_dict(),
        },
    )
    block_response = client.post(
        "/peers/blocks/receive",
        json=_receive_payload(block, related_submission_id=submission.submission_id),
    )

    assert certificate_response.status_code == 200
    assert block_response.status_code == 200
    assert block_response.json()["accepted"] is True
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


def test_receive_peer_block_duplicate_is_idempotent(blockchain, wallets):
    client = _client(blockchain)
    _register_peer()
    block = _peer_block(blockchain, wallets["contributor_one"].public_key)

    assert client.post("/peers/blocks/receive", json=_receive_payload(block)).status_code == 200
    duplicate_response = client.post("/peers/blocks/receive", json=_receive_payload(block))

    assert duplicate_response.status_code == 200
    assert duplicate_response.json()["accepted"] is True
    assert duplicate_response.json()["status"] == "duplicate"
    assert duplicate_response.json()["action"] == "duplicate"
    assert duplicate_response.json()["reason"] == "block_already_exists"
    assert len(blockchain.chain) == 2


def test_receive_peer_block_mismatched_previous_hash_returns_sync_needed(blockchain, wallets):
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

    assert response.status_code == 200
    assert response.json()["accepted"] is False
    assert response.json()["status"] == "sync_needed"
    assert response.json()["reason"] == "previous_hash_mismatch"
    assert response.json()["local_latest_hash"] == latest_block.hash
    assert response.json()["received_previous_hash"] == "not-the-local-tip"
    assert response.json()["received_block_hash"] == block.hash
    assert response.json()["recommended_action"] == "run_chain_sync"
    assert len(blockchain.chain) == 1
    assert blockchain.get_latest_block().hash == latest_block.hash


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
    _certify_submission(blockchain, submission)
    blockchain.add_to_mint_queue(submission.submission_id)
    calls = []

    def fake_post(url, json, timeout, headers=None):
        calls.append({"url": url, "json": json, "timeout": timeout, "headers": headers})
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
    assert len(calls) == 3
    assert calls[0]["url"].endswith("/peers/certificates/receive")
    assert calls[1]["url"].endswith("/peers/blocks/receive")
    assert calls[2]["url"].endswith("/peers/certificates/receive")
    assert calls[1]["json"]["related_submission_id"] == submission.submission_id
    assert calls[1]["json"]["certificate"]["certificate_id"] == blockchain.get_latest_block().certificate_id


def test_manual_block_rebroadcast_endpoint_works(blockchain, wallets, monkeypatch):
    client = _client(blockchain)
    _register_peer()
    block = _peer_block(blockchain, wallets["contributor_one"].public_key)
    blockchain.chain.append(block)
    calls = []

    def fake_post(url, json, timeout, headers=None):
        calls.append({"url": url, "json": json, "timeout": timeout, "headers": headers})
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
