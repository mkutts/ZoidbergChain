import requests
from fastapi.testclient import TestClient

from peers import PeerStore
from submission import APPROVED, VOTE_NOT_ORIGINAL, VOTE_ORIGINAL


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


def _submission(blockchain, submission_image, submitter, text="Peer certificate submission"):
    return blockchain.submit_content(
        image_path=str(submission_image),
        text_content=text,
        submitter=submitter,
    )


def _cast_votes(blockchain, submission_id, voter_prefix="peer-certificate-voter"):
    for index, vote_type in enumerate([
        VOTE_ORIGINAL,
        VOTE_ORIGINAL,
        VOTE_ORIGINAL,
        VOTE_ORIGINAL,
        VOTE_NOT_ORIGINAL,
    ]):
        blockchain.cast_submission_vote(
            submission_id=submission_id,
            voter=f"{voter_prefix}-{index}",
            vote_type=vote_type,
            created_at=1_000_000 + index,
        )


def _certificate(blockchain, submission_image, wallets):
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    _cast_votes(blockchain, submission.submission_id)
    submission.transition_to(APPROVED)
    certificate = blockchain.create_originality_certificate(
        submission.submission_id,
        approved_at=1_000_100,
    )
    return submission, certificate


def _receive_payload(certificate, origin_node_id="peer-node-1", network_name="zoidberg-testnet"):
    return {
        "origin_node_id": origin_node_id,
        "network_name": network_name,
        "certificate": certificate.to_dict(),
    }


def test_receive_valid_peer_certificate(blockchain, submission_image, wallets):
    client = _client(blockchain)
    _register_peer()
    _submission, certificate = _certificate(blockchain, submission_image, wallets)
    blockchain.originality_certificates = []

    response = client.post("/peers/certificates/receive", json=_receive_payload(certificate))

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert response.json()["action"] == "created"
    assert blockchain.get_originality_certificate(certificate.certificate_id) is not None


def test_reject_unregistered_peer_certificate(blockchain, submission_image, wallets):
    client = _client(blockchain)
    _submission, certificate = _certificate(blockchain, submission_image, wallets)

    response = client.post("/peers/certificates/receive", json=_receive_payload(certificate))

    assert response.status_code == 403
    assert response.json()["detail"] == "Peer is not registered or active."


def test_reject_wrong_network_peer_certificate(blockchain, submission_image, wallets):
    client = _client(blockchain)
    _register_peer()
    _submission, certificate = _certificate(blockchain, submission_image, wallets)

    response = client.post(
        "/peers/certificates/receive",
        json=_receive_payload(certificate, network_name="zoidberg-mainnet"),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Peer certificate belongs to a different network."


def test_duplicate_matching_certificate_is_idempotent(blockchain, submission_image, wallets):
    client = _client(blockchain)
    _register_peer()
    _submission, certificate = _certificate(blockchain, submission_image, wallets)

    response = client.post("/peers/certificates/receive", json=_receive_payload(certificate))

    assert response.status_code == 200
    assert response.json()["action"] == "duplicate"
    assert len(blockchain.originality_certificates) == 1


def test_duplicate_conflicting_certificate_is_rejected(blockchain, submission_image, wallets):
    client = _client(blockchain)
    _register_peer()
    _submission, certificate = _certificate(blockchain, submission_image, wallets)
    conflicting_payload = _receive_payload(certificate)
    conflicting_payload["certificate"]["vote_hash"] = "different-vote-hash"

    response = client.post("/peers/certificates/receive", json=conflicting_payload)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Originality certificate already exists with different contents."
    )


def test_certificate_with_invalid_vote_totals_is_rejected(
    blockchain,
    submission_image,
    wallets,
):
    client = _client(blockchain)
    _register_peer()
    _submission, certificate = _certificate(blockchain, submission_image, wallets)
    blockchain.originality_certificates = []
    payload = _receive_payload(certificate)
    payload["certificate"]["vote_total"] = payload["certificate"]["vote_total"] + 1

    response = client.post("/peers/certificates/receive", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "Originality certificate vote_total is inconsistent."


def test_certificate_with_wrong_originality_score_is_rejected(
    blockchain,
    submission_image,
    wallets,
):
    client = _client(blockchain)
    _register_peer()
    _submission, certificate = _certificate(blockchain, submission_image, wallets)
    blockchain.originality_certificates = []
    payload = _receive_payload(certificate)
    payload["certificate"]["originality_score"] = payload["certificate"]["originality_score"] + 1

    response = client.post("/peers/certificates/receive", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "Originality certificate originality_score is inconsistent."


def test_certificate_stores_even_if_related_submission_is_missing(
    blockchain,
    submission_image,
    wallets,
):
    client = _client(blockchain)
    _register_peer()
    _submission, certificate = _certificate(blockchain, submission_image, wallets)
    blockchain.submissions = []
    blockchain.originality_certificates = []

    response = client.post("/peers/certificates/receive", json=_receive_payload(certificate))

    assert response.status_code == 200
    assert response.json()["action"] == "created"
    assert blockchain.get_originality_certificate(certificate.certificate_id) is not None


def test_certificate_validates_against_submission_when_submission_exists(
    blockchain,
    submission_image,
    wallets,
):
    client = _client(blockchain)
    _register_peer()
    submission, certificate = _certificate(blockchain, submission_image, wallets)
    blockchain.originality_certificates = []
    submission.status = "pending"

    response = client.post("/peers/certificates/receive", json=_receive_payload(certificate))

    assert response.status_code == 200
    assert response.json()["action"] == "created"
    assert submission.status == APPROVED
    assert blockchain.get_originality_certificate(certificate.certificate_id) is not None


def test_certificate_broadcasts_after_creation(
    blockchain,
    submission_image,
    wallets,
    monkeypatch,
):
    client = _client(blockchain)
    _register_peer()
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    _cast_votes(blockchain, submission.submission_id, "broadcast-create-voter")
    calls = []

    def fake_post(url, json, timeout, headers=None):
        calls.append({"url": url, "json": json, "timeout": timeout, "headers": headers})
        return type("Response", (), {"status_code": 200, "text": "ok"})()

    monkeypatch.setattr("peer_sync.requests.post", fake_post)

    response = client.post(
        f"/submissions/{submission.submission_id}/evaluate",
        data={"automated_originality_passed": "true"},
    )

    assert response.status_code == 200
    assert calls[0]["url"] == "http://peer-one.test:8000/peers/certificates/receive"
    assert calls[0]["json"]["certificate"]["certificate_id"] == response.json()["certificate"]["certificate_id"]
    assert response.json()["certificate_broadcast"]["succeeded"] == 1


def test_manual_certificate_broadcast_endpoint_works(
    blockchain,
    submission_image,
    wallets,
    monkeypatch,
):
    client = _client(blockchain)
    _register_peer()
    _submission, certificate = _certificate(blockchain, submission_image, wallets)
    calls = []

    def fake_post(url, json, timeout, headers=None):
        calls.append({"url": url, "json": json, "timeout": timeout, "headers": headers})
        return type("Response", (), {"status_code": 200, "text": "ok"})()

    monkeypatch.setattr("peer_sync.requests.post", fake_post)

    response = client.post(f"/certificates/{certificate.certificate_id}/broadcast")

    assert response.status_code == 200
    assert response.json()["broadcast"]["succeeded"] == 1
    assert calls[0]["url"] == "http://peer-one.test:8000/peers/certificates/receive"
    assert calls[0]["json"]["certificate"] == certificate.to_dict()
