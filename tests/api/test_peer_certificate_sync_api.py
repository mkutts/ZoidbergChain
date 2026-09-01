import requests
from fastapi.testclient import TestClient
from eth_account import Account

import peer_sync
from originality_certificate import OriginalityCertificate, calculate_certificate_id
from peers import PeerStore
from protocol_v1_peer_message import (
    build_protocol_v1_peer_request_headers,
    clear_protocol_v1_peer_replay_store_cache,
)
from submission import APPROVED, VOTE_NOT_ORIGINAL, VOTE_ORIGINAL


def _client(blockchain):
    import api

    api.NODE_ID = "local-node"
    api.PUBLIC_NODE_URL = "http://localhost:8000"
    api.NETWORK_NAME = "zoidberg-testnet"
    api.blockchain = blockchain
    # Reset peer_store to use the same isolated storage backend as the blockchain fixture
    api.peer_store = PeerStore(storage_backend=blockchain.storage)
    clear_protocol_v1_peer_replay_store_cache(data_dir=api.peer_store.storage.data_dir)
    return TestClient(api.app)


def _register_peer(node_id="peer-node-1", url="http://peer-one.test:8000"):
    import api

    return api.peer_store.register_peer(
        node_id=node_id,
        url=url,
        network_name="zoidberg-testnet",
    )


def _configure_signed_peer_messages(monkeypatch, secret="super-secret-value"):
    import api

    monkeypatch.setattr(api, "signed_peer_messages_enabled", lambda: True)
    monkeypatch.setattr(api, "peer_auth_required", lambda: False)
    monkeypatch.setattr(api, "peer_shared_secret", lambda: secret)
    monkeypatch.setattr(api, "peer_shared_secret_is_configured", lambda: True)
    monkeypatch.setattr(api, "peer_replay_protection_enabled", lambda: False)
    monkeypatch.setattr(api, "PEER_SIGNATURE_WINDOW_SECONDS", 300)
    monkeypatch.setattr(peer_sync, "signed_peer_messages_enabled", lambda: True)
    monkeypatch.setattr(peer_sync, "peer_auth_required", lambda: False)
    monkeypatch.setattr(peer_sync, "peer_shared_secret", lambda: secret)
    monkeypatch.setattr(peer_sync, "peer_shared_secret_is_configured", lambda: True)
    monkeypatch.setattr(peer_sync, "peer_replay_protection_enabled", lambda: False)
    monkeypatch.setattr(peer_sync, "peer_signature_window_seconds", lambda: 300)
    peer_sync._PEER_NONCE_CACHE.clear()
    clear_protocol_v1_peer_replay_store_cache()


def _freeze_peer_time(monkeypatch, now=1_700_000_000):
    import api

    monkeypatch.setattr(api.time, "time", lambda: now)
    monkeypatch.setattr(peer_sync.time, "time", lambda: now)


def _signed_headers(path, payload, *, secret="super-secret-value", timestamp=1_700_000_000, nonce="nonce-1"):
    return build_protocol_v1_peer_request_headers(
        "POST",
        path,
        payload,
        "peer-node-1",
        network_name="zoidberg-testnet",
        secret=secret,
        timestamp=timestamp,
        nonce=nonce,
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


def test_signed_peer_certificate_auth_does_not_bypass_certificate_validation(
    blockchain,
    submission_image,
    wallets,
    monkeypatch,
):
    client = _client(blockchain)
    _configure_signed_peer_messages(monkeypatch)
    _freeze_peer_time(monkeypatch)
    _register_peer()
    _submission, certificate = _certificate(blockchain, submission_image, wallets)
    blockchain.originality_certificates = []
    payload = _receive_payload(certificate)
    payload["certificate"]["vote_total"] = payload["certificate"]["vote_total"] + 1

    response = client.post(
        "/peers/certificates/receive",
        json=payload,
        headers=_signed_headers(
            "/peers/certificates/receive",
            payload,
            nonce="signed-certificate-invalid-vote-total-1",
        ),
    )

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


def test_receive_protocol_v1_certificate_accepts_ethereum_creator_wallet(blockchain, submission_image):
    client = _client(blockchain)
    _register_peer()
    submitter = Account.create()
    submission = _submission(blockchain, submission_image, submitter.address.lower(), text="ethereum creator certificate")
    _cast_votes(blockchain, submission.submission_id, "ethereum-creator-voter")
    submission.transition_to(APPROVED)
    certificate = blockchain.create_originality_certificate(submission.submission_id, approved_at=1_000_100)
    blockchain.originality_certificates = []

    response = client.post("/peers/certificates/receive", json=_receive_payload(certificate))

    assert response.status_code == 200
    stored_certificate = blockchain.get_originality_certificate(certificate.certificate_id)
    assert stored_certificate is not None
    assert stored_certificate.creator_wallet == submitter.address.lower()


def test_protocol_v1_certificate_rejects_wrong_inner_network_id(blockchain, submission_image, wallets):
    client = _client(blockchain)
    _register_peer()
    _submission, certificate = _certificate(blockchain, submission_image, wallets)
    blockchain.originality_certificates = []
    payload = _receive_payload(certificate)
    payload["certificate"]["network_id"] = "zoidberg-devnet-v1"

    response = client.post("/peers/certificates/receive", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "Originality certificate belongs to a different network."


def test_protocol_v1_certificate_rejects_vote_hash_mismatch_against_local_vote_set(
    blockchain,
    submission_image,
    wallets,
):
    client = _client(blockchain)
    _register_peer()
    _submission, certificate = _certificate(blockchain, submission_image, wallets)
    blockchain.originality_certificates = []
    payload = _receive_payload(certificate)
    payload["certificate"]["vote_hash"] = "a" * 64
    payload["certificate"]["certificate_id"] = calculate_certificate_id(
        payload["certificate"],
        certificate_version=payload["certificate"]["certificate_version"],
        network_id=payload["certificate"]["network_id"],
        network_name=payload["certificate"]["network_name"],
    )

    response = client.post("/peers/certificates/receive", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "Originality certificate vote_hash does not match local vote set."


def test_legacy_peer_certificate_is_not_silently_converted_to_protocol_v1(blockchain, submission_image, wallets):
    client = _client(blockchain)
    _register_peer()
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key, text="legacy certificate replay")
    _cast_votes(blockchain, submission.submission_id, "legacy-certificate-voter")
    submission.transition_to(APPROVED)
    legacy_certificate = OriginalityCertificate.from_approved_submission(
        submission=submission,
        votes=blockchain.get_submission_votes(submission.submission_id)["votes"],
        minimum_votes_required=5,
        approved_at=1_000_100,
        network_name="zoidberg-testnet",
        issuing_node_id="node-certifier",
        certificate_version=None,
    )
    blockchain.originality_certificates = []

    response = client.post("/peers/certificates/receive", json=_receive_payload(legacy_certificate))

    assert response.status_code == 200
    stored_certificate = blockchain.get_originality_certificate(legacy_certificate.certificate_id)
    assert stored_certificate is not None
    assert stored_certificate.certificate_version is None
    assert stored_certificate.protocol_version is None
    assert stored_certificate.network_id is None


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
