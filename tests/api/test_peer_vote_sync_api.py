import requests
from fastapi.testclient import TestClient

from peers import PeerStore
from submission import APPROVED, VOTE_NOT_ORIGINAL, VOTE_ORIGINAL, VOTE_UNSURE


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


def _submission(blockchain, submission_image, submitter, text="Peer vote submission"):
    return blockchain.submit_content(
        image_path=str(submission_image),
        text_content=text,
        submitter=submitter,
    )


def _vote_payload(
    submission_id,
    voter,
    vote_type=VOTE_ORIGINAL,
    origin_node_id="peer-node-1",
    network_name="zoidberg-testnet",
    created_at=1_000_000.0,
):
    return {
        "origin_node_id": origin_node_id,
        "network_name": network_name,
        "submission_id": submission_id,
        "voter": voter,
        "vote_type": vote_type,
        "created_at": created_at,
    }


def test_receiving_valid_peer_vote(blockchain, submission_image, wallets):
    client = _client(blockchain)
    _register_peer()
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)

    response = client.post(
        "/peers/votes/receive",
        json=_vote_payload(submission.submission_id, wallets["contributor_one"].public_key),
    )

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert response.json()["action"] == "created"
    assert blockchain.votes == [
        {
            "voter": wallets["contributor_one"].public_key,
            "submission_id": submission.submission_id,
            "vote_type": VOTE_ORIGINAL,
            "created_at": 1_000_000.0,
        }
    ]


def test_receive_peer_vote_rejects_unregistered_peer(blockchain, submission_image, wallets):
    client = _client(blockchain)
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)

    response = client.post(
        "/peers/votes/receive",
        json=_vote_payload(submission.submission_id, wallets["contributor_one"].public_key),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Peer is not registered or active."
    assert blockchain.votes == []


def test_receive_peer_vote_rejects_wrong_network(blockchain, submission_image, wallets):
    client = _client(blockchain)
    _register_peer()
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)

    response = client.post(
        "/peers/votes/receive",
        json=_vote_payload(
            submission.submission_id,
            wallets["contributor_one"].public_key,
            network_name="zoidberg-mainnet",
        ),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Peer vote belongs to a different network."
    assert blockchain.votes == []


def test_receive_peer_vote_rejects_unknown_submission(blockchain, wallets):
    client = _client(blockchain)
    _register_peer()

    response = client.post(
        "/peers/votes/receive",
        json=_vote_payload("missing-submission", wallets["contributor_one"].public_key),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Submission not found: missing-submission"
    assert blockchain.votes == []


def test_receive_peer_vote_rejects_invalid_vote_type(blockchain, submission_image, wallets):
    client = _client(blockchain)
    _register_peer()
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)

    response = client.post(
        "/peers/votes/receive",
        json=_vote_payload(
            submission.submission_id,
            wallets["contributor_one"].public_key,
            vote_type="maybe",
        ),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid vote type: maybe"
    assert blockchain.votes == []


def test_duplicate_matching_peer_vote_is_idempotent(blockchain, submission_image, wallets):
    client = _client(blockchain)
    _register_peer()
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    existing_vote = blockchain.cast_submission_vote(
        submission_id=submission.submission_id,
        voter=wallets["contributor_one"].public_key,
        vote_type=VOTE_UNSURE,
        created_at=100.0,
    )

    response = client.post(
        "/peers/votes/receive",
        json=_vote_payload(
            submission.submission_id,
            wallets["contributor_one"].public_key,
            vote_type=VOTE_UNSURE,
            created_at=200.0,
        ),
    )

    assert response.status_code == 200
    assert response.json()["action"] == "duplicate"
    assert blockchain.votes == [existing_vote]


def test_duplicate_matching_peer_vote_after_certificate_is_idempotent(
    blockchain,
    submission_image,
    wallets,
):
    client = _client(blockchain)
    _register_peer()
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    existing_vote = blockchain.cast_submission_vote(
        submission_id=submission.submission_id,
        voter=wallets["contributor_one"].public_key,
        vote_type=VOTE_ORIGINAL,
        created_at=100.0,
    )
    submission.transition_to(APPROVED)
    blockchain.create_originality_certificate(submission.submission_id, approved_at=1_000_000)

    response = client.post(
        "/peers/votes/receive",
        json=_vote_payload(
            submission.submission_id,
            wallets["contributor_one"].public_key,
            vote_type=VOTE_ORIGINAL,
            created_at=200.0,
        ),
    )

    assert response.status_code == 200
    assert response.json()["action"] == "duplicate"
    assert blockchain.votes == [existing_vote]


def test_duplicate_conflicting_peer_vote_is_rejected(blockchain, submission_image, wallets):
    client = _client(blockchain)
    _register_peer()
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    blockchain.cast_submission_vote(
        submission_id=submission.submission_id,
        voter=wallets["contributor_one"].public_key,
        vote_type=VOTE_ORIGINAL,
    )

    response = client.post(
        "/peers/votes/receive",
        json=_vote_payload(
            submission.submission_id,
            wallets["contributor_one"].public_key,
            vote_type=VOTE_NOT_ORIGINAL,
        ),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Wallet has already voted differently on this submission."
    assert len(blockchain.votes) == 1
    assert blockchain.votes[0]["vote_type"] == VOTE_ORIGINAL


def test_peer_vote_rejected_after_certificate_exists(blockchain, submission_image, wallets):
    client = _client(blockchain)
    _register_peer()
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    blockchain.cast_submission_vote(
        submission_id=submission.submission_id,
        voter=wallets["contributor_one"].public_key,
        vote_type=VOTE_ORIGINAL,
    )
    submission.transition_to(APPROVED)
    blockchain.create_originality_certificate(submission.submission_id, approved_at=1_000_000)

    response = client.post(
        "/peers/votes/receive",
        json=_vote_payload(
            submission.submission_id,
            wallets["contributor_two"].public_key,
            vote_type=VOTE_NOT_ORIGINAL,
        ),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Finalized or certified submissions cannot receive votes."
    assert len(blockchain.votes) == 1


def test_creator_cannot_vote_through_peer_endpoint(blockchain, submission_image, wallets):
    client = _client(blockchain)
    _register_peer()
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)

    response = client.post(
        "/peers/votes/receive",
        json=_vote_payload(submission.submission_id, wallets["owner"].public_key),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Submission creator cannot vote on their own submission."
    assert blockchain.votes == []


def test_local_vote_broadcasts_without_failing_if_one_peer_is_down(
    blockchain,
    submission_image,
    wallets,
    monkeypatch,
):
    client = _client(blockchain)
    _register_peer("peer-up", "http://peer-up.test")
    _register_peer("peer-down", "http://peer-down.test")
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    calls = []

    def fake_post(url, json, timeout, headers=None):
        calls.append({"url": url, "json": json, "timeout": timeout, "headers": headers})
        if "peer-down" in url:
            raise requests.RequestException("connection refused")
        return type("Response", (), {"status_code": 200, "text": "ok"})()

    monkeypatch.setattr("peer_sync.requests.post", fake_post)

    response = client.post(
        f"/submissions/{submission.submission_id}/vote",
        data={
            "voter": wallets["contributor_one"].public_key,
            "vote_type": VOTE_ORIGINAL,
        },
    )

    assert response.status_code == 200
    assert response.json()["broadcast"]["attempted"] == 2
    assert response.json()["broadcast"]["succeeded"] == 1
    assert response.json()["broadcast"]["failed"] == 1
    assert len(calls) == 2
    assert len(blockchain.votes) == 1


def test_manual_vote_rebroadcast_endpoint_works(blockchain, submission_image, wallets, monkeypatch):
    client = _client(blockchain)
    _register_peer()
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    vote = blockchain.cast_submission_vote(
        submission_id=submission.submission_id,
        voter=wallets["contributor_one"].public_key,
        vote_type=VOTE_NOT_ORIGINAL,
        created_at=1_000_000.0,
    )
    calls = []

    def fake_post(url, json, timeout, headers=None):
        calls.append({"url": url, "json": json, "timeout": timeout, "headers": headers})
        return type("Response", (), {"status_code": 200, "text": "ok"})()

    monkeypatch.setattr("peer_sync.requests.post", fake_post)

    response = client.post(f"/submissions/{submission.submission_id}/votes/broadcast")

    assert response.status_code == 200
    assert response.json()["broadcast"]["vote_count"] == 1
    assert response.json()["broadcast"]["attempted"] == 1
    assert response.json()["broadcast"]["succeeded"] == 1
    assert calls[0]["url"] == "http://peer-one.test:8000/peers/votes/receive"
    assert calls[0]["json"] == {
        "origin_node_id": "local-node",
        "network_name": "zoidberg-testnet",
        "submission_id": submission.submission_id,
        "voter": vote["voter"],
        "vote_type": vote["vote_type"],
        "created_at": vote["created_at"],
    }
