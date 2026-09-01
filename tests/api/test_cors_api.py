import importlib

from fastapi.testclient import TestClient
import pytest


def _client(monkeypatch, blockchain, data_dir, **env):
    from peers import PeerStore
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("NODE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("SQLITE_DB_PATH", str(data_dir / "zoidbergchain.db"))
    monkeypatch.setenv("STORAGE_BACKEND", "json")

    import config
    import api

    importlib.reload(config)
    api = importlib.reload(api)
    api.blockchain = blockchain
    # Reset peer_store to use the same isolated storage backend as the blockchain fixture
    api.peer_store = PeerStore(storage_backend=blockchain.storage)
    return TestClient(api.app)


def test_development_cors_allows_local_vue_origin(monkeypatch, blockchain, isolated_data_dir):
    client = _client(monkeypatch, blockchain, isolated_data_dir, ENVIRONMENT="development")

    response = client.get(
        "/chain/summary",
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_wallet_challenge_preflight_allows_local_vue_origin(monkeypatch, blockchain, isolated_data_dir):
    client = _client(monkeypatch, blockchain, isolated_data_dir, ENVIRONMENT="development")

    response = client.options(
        "/auth/wallet/challenge",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "POST" in response.headers["access-control-allow-methods"]
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed_headers
    assert "content-type" in allowed_headers
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_does_not_grant_random_origin(monkeypatch, blockchain, isolated_data_dir):
    client = _client(
        monkeypatch,
        blockchain,
        isolated_data_dir,
        ENVIRONMENT="production",
        PEER_SHARED_SECRET="test-cors-secret-with-enough-length",
    )

    response = client.options(
        "/auth/wallet/challenge",
        headers={
            "Origin": "https://random.example.test",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert "access-control-allow-origin" not in response.headers
    assert response.headers["access-control-allow-credentials"] == "true"
