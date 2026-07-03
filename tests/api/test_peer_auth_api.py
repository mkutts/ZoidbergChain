from fastapi.testclient import TestClient

from peers import PeerStore
from submission import VOTE_ORIGINAL


def _client(blockchain):
    import api

    api.NODE_ID = "local-node"
    api.PUBLIC_NODE_URL = "http://localhost:8000"
    api.NETWORK_NAME = "zoidberg-testnet"
    api.blockchain = blockchain
    api.peer_store = PeerStore()
    return TestClient(api.app)


def _configure_peer_auth(monkeypatch, enabled, secret="super-secret-value"):
    import api
    import peer_sync

    monkeypatch.setattr(api, "peer_auth_required", lambda: enabled)
    monkeypatch.setattr(api, "peer_shared_secret", lambda: secret)
    monkeypatch.setattr(peer_sync, "peer_auth_required", lambda: enabled)
    monkeypatch.setattr(peer_sync, "peer_shared_secret", lambda: secret)
    monkeypatch.setattr(peer_sync, "peer_shared_secret_is_configured", lambda: bool(secret))


def _register_peer(client, secret=None):
    headers = {}
    if secret is not None:
        headers["X-ZOID-Peer-Secret"] = secret
    return client.post(
        "/peers/register",
        headers=headers,
        json={
            "node_id": "peer-node-1",
            "url": "http://peer-one.test:8000",
            "network_name": "zoidberg-testnet",
        },
    )


def test_peer_endpoint_allowed_in_development_when_peer_auth_disabled(blockchain, monkeypatch):
    _configure_peer_auth(monkeypatch, enabled=False)
    client = _client(blockchain)

    response = _register_peer(client)

    assert response.status_code == 200
    assert response.json()["peer"]["node_id"] == "peer-node-1"


def test_peer_endpoint_requires_header_when_peer_auth_enabled(blockchain, monkeypatch):
    _configure_peer_auth(monkeypatch, enabled=True)
    client = _client(blockchain)

    response = _register_peer(client)

    assert response.status_code == 401
    assert response.json()["detail"] == "Peer auth required. Missing shared secret."


def test_peer_endpoint_rejects_wrong_secret(blockchain, monkeypatch):
    _configure_peer_auth(monkeypatch, enabled=True)
    client = _client(blockchain)

    response = client.post(
        "/peers/register",
        headers={"X-ZOID-Peer-Secret": "wrong-secret"},
        json={
            "node_id": "peer-node-1",
            "url": "http://peer-one.test:8000",
            "network_name": "zoidberg-testnet",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid peer shared secret."


def test_peer_endpoint_accepts_correct_secret(blockchain, monkeypatch):
    _configure_peer_auth(monkeypatch, enabled=True)
    client = _client(blockchain)

    response = client.post(
        "/peers/register",
        headers={"X-ZOID-Peer-Secret": "super-secret-value"},
        json={
            "node_id": "peer-node-1",
            "url": "http://peer-one.test:8000",
            "network_name": "zoidberg-testnet",
        },
    )

    assert response.status_code == 200


def test_constant_time_comparison_helper_is_used(blockchain, monkeypatch):
    import api

    compare_calls = []

    def fake_compare_digest(left, right):
        compare_calls.append((left, right))
        return True

    monkeypatch.setattr(api.hmac, "compare_digest", fake_compare_digest)
    _configure_peer_auth(monkeypatch, enabled=True)
    client = _client(blockchain)

    response = client.post(
        "/peers/register",
        headers={"X-ZOID-Peer-Secret": "super-secret-value"},
        json={
            "node_id": "peer-node-1",
            "url": "http://peer-one.test:8000",
            "network_name": "zoidberg-testnet",
        },
    )

    assert response.status_code == 200
    assert compare_calls == [("super-secret-value", "super-secret-value")]


def test_public_endpoint_does_not_require_peer_secret(blockchain, monkeypatch):
    _configure_peer_auth(monkeypatch, enabled=True)
    client = _client(blockchain)

    response = client.get("/chain/summary")

    assert response.status_code == 200


def test_outbound_peer_broadcast_includes_auth_header_when_enabled(
    blockchain,
    submission_image,
    wallets,
    monkeypatch,
):
    import peer_sync

    _configure_peer_auth(monkeypatch, enabled=True)
    client = _client(blockchain)
    _register_peer(client, secret="super-secret-value")
    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Peer auth broadcast",
        submitter=wallets["owner"].public_key,
    )
    calls = []

    def fake_post(url, json, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return type("Response", (), {"status_code": 200, "text": "ok"})()

    monkeypatch.setattr(peer_sync.requests, "post", fake_post)

    response = client.post(f"/submissions/{submission.submission_id}/broadcast")

    assert response.status_code == 200
    assert calls[0]["headers"]["X-ZOID-Peer-Secret"] == "super-secret-value"


def test_outbound_peer_broadcast_omits_auth_header_when_disabled(
    blockchain,
    submission_image,
    wallets,
    monkeypatch,
):
    import peer_sync

    _configure_peer_auth(monkeypatch, enabled=False)
    client = _client(blockchain)
    _register_peer(client)
    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Peer auth broadcast",
        submitter=wallets["owner"].public_key,
    )
    calls = []

    def fake_post(url, json, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return type("Response", (), {"status_code": 200, "text": "ok"})()

    monkeypatch.setattr(peer_sync.requests, "post", fake_post)

    response = client.post(f"/submissions/{submission.submission_id}/broadcast")

    assert response.status_code == 200
    assert calls[0]["headers"] == {}
