import requests
from fastapi.testclient import TestClient

from peers import PeerStore
from submission import APPROVED, MINTED, PENDING, REJECTED, Submission


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


def _submission_payload(
    submitter,
    submission_id="peer-submission-1",
    text_content="Peer submission content",
    created_at=1_000_000.0,
):
    return Submission(
        submission_id=submission_id,
        image_path="peer-submissions/meme.jpg",
        text_content=text_content,
        submitter=submitter,
        status=PENDING,
        created_at=created_at,
    ).to_dict()


def _receive_payload(submission, origin_node_id="peer-node-1", network_name="zoidberg-testnet"):
    return {
        "origin_node_id": origin_node_id,
        "network_name": network_name,
        "submission": submission,
    }


def test_receiving_valid_peer_submission(blockchain, wallets):
    client = _client(blockchain)
    _register_peer()
    payload = _submission_payload(wallets["owner"].public_key)

    response = client.post("/peers/submissions/receive", json=_receive_payload(payload))

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["action"] == "created"
    assert len(blockchain.submissions) == 1
    assert blockchain.submissions[0].submission_id == "peer-submission-1"
    assert blockchain.submissions[0].submitter == wallets["owner"].public_key
    assert blockchain.submissions[0].created_at == 1_000_000.0
    assert blockchain.submissions[0].status == PENDING


def test_receive_peer_submission_rejects_unregistered_peer(blockchain, wallets):
    client = _client(blockchain)
    payload = _submission_payload(wallets["owner"].public_key)

    response = client.post("/peers/submissions/receive", json=_receive_payload(payload))

    assert response.status_code == 403
    assert response.json()["detail"] == "Peer is not registered or active."
    assert blockchain.submissions == []


def test_receive_peer_submission_rejects_wrong_network(blockchain, wallets):
    client = _client(blockchain)
    _register_peer()
    payload = _submission_payload(wallets["owner"].public_key)

    response = client.post(
        "/peers/submissions/receive",
        json=_receive_payload(payload, network_name="zoidberg-mainnet"),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Peer submission belongs to a different network."
    assert blockchain.submissions == []


def test_receive_peer_submission_rejects_malformed_submission(blockchain):
    client = _client(blockchain)
    _register_peer()

    response = client.post(
        "/peers/submissions/receive",
        json=_receive_payload({
            "submission_id": "missing-fields",
            "image_path": "peer-submissions/meme.jpg",
        }),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Submission text_content is required."
    assert blockchain.submissions == []


def test_receive_peer_submission_rejects_duplicate_content_hash(blockchain, wallets):
    client = _client(blockchain)
    _register_peer()
    original_payload = _submission_payload(wallets["owner"].public_key)
    existing_submission = Submission.from_dict(original_payload)
    blockchain.submissions.append(existing_submission)

    duplicate_payload = {
        **original_payload,
        "submission_id": "different-submission-id",
    }

    response = client.post("/peers/submissions/receive", json=_receive_payload(duplicate_payload))

    assert response.status_code == 409
    assert response.json()["detail"] == "Submission already exists."
    assert len(blockchain.submissions) == 1


def test_receive_peer_submission_does_not_downgrade_later_statuses(blockchain, wallets):
    client = _client(blockchain)
    _register_peer()

    for status in [APPROVED, REJECTED, MINTED]:
        existing_submission = Submission(
            submission_id=f"{status}-submission",
            image_path="peer-submissions/meme.jpg",
            text_content=f"{status} content",
            submitter=wallets["owner"].public_key,
            status=status,
            created_at=1_000_000.0,
        )
        blockchain.submissions = [existing_submission]
        incoming_payload = {
            **existing_submission.to_dict(),
            "status": PENDING,
        }

        response = client.post("/peers/submissions/receive", json=_receive_payload(incoming_payload))

        assert response.status_code == 200
        assert response.json()["action"] == "ignored"
        assert response.json()["reason"] == "known_submission_not_downgraded"
        assert blockchain.submissions[0].status == status


def test_broadcasting_local_submission_does_not_fail_if_one_peer_is_down(
    blockchain,
    submission_image,
    wallets,
    monkeypatch,
):
    client = _client(blockchain)
    _register_peer("peer-up", "http://peer-up.test")
    _register_peer("peer-down", "http://peer-down.test")
    calls = []

    def fake_post(url, json, timeout, headers=None):
        calls.append({"url": url, "json": json, "timeout": timeout, "headers": headers})
        if "peer-down" in url:
            raise requests.RequestException("connection refused")
        return type("Response", (), {"status_code": 200, "text": "ok"})()

    monkeypatch.setattr("peer_sync.requests.post", fake_post)

    with open(submission_image, "rb") as image_file:
        response = client.post(
            "/submit_content",
            data={
                "submitter": wallets["owner"].public_key,
                "text_content": "Local broadcast submission",
            },
            files={"image": ("broadcast.jpg", image_file, "image/jpeg")},
        )

    assert response.status_code == 200
    assert response.json()["broadcast"]["attempted"] == 2
    assert response.json()["broadcast"]["succeeded"] == 1
    assert response.json()["broadcast"]["failed"] == 1
    assert len(calls) == 2
    assert len(blockchain.submissions) == 1


def test_manual_rebroadcast_endpoint_works(blockchain, submission_image, wallets, monkeypatch):
    client = _client(blockchain)
    _register_peer()
    calls = []

    def fake_post(url, json, timeout, headers=None):
        calls.append({"url": url, "json": json, "timeout": timeout, "headers": headers})
        return type("Response", (), {"status_code": 200, "text": "ok"})()

    monkeypatch.setattr("peer_sync.requests.post", fake_post)
    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Manual rebroadcast submission",
        submitter=wallets["owner"].public_key,
    )

    response = client.post(f"/submissions/{submission.submission_id}/broadcast")

    assert response.status_code == 200
    assert response.json()["broadcast"]["attempted"] == 1
    assert response.json()["broadcast"]["succeeded"] == 1
    assert calls[0]["url"] == "http://peer-one.test:8000/peers/submissions/receive"
    assert calls[0]["json"]["origin_node_id"] == "local-node"
    assert calls[0]["json"]["network_name"] == "zoidberg-testnet"
    assert calls[0]["json"]["submission"]["submission_id"] == submission.submission_id
