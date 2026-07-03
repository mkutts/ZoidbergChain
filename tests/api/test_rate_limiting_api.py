import importlib

from fastapi.testclient import TestClient

from peers import PeerStore
from submission import VOTE_ORIGINAL


RATE_LIMIT_ENV_KEYS = (
    "ENVIRONMENT",
    "APP_ENV",
    "ENABLE_RATE_LIMITING",
    "ENABLE_SIGNED_PEER_MESSAGES",
    "REQUIRE_PEER_AUTH",
    "PUBLIC_API_MODE",
    "ALLOW_DEV_WALLET_PRIVATE_KEY_EXPORT",
    "ALLOW_DEV_RESET_ENDPOINTS",
    "ALLOW_INSECURE_LOCAL_PEERS",
    "PEER_REPLAY_PROTECTION_ENABLED",
    "RATE_LIMIT_ENABLED",
    "RATE_LIMIT_TRANSACTION_CREATE",
    "RATE_LIMIT_WALLET_CREATE",
    "RATE_LIMIT_SUBMISSION_CREATE",
    "RATE_LIMIT_VOTE",
    "RATE_LIMIT_EVALUATE",
    "RATE_LIMIT_MINT",
    "RATE_LIMIT_CHAIN_SYNC",
    "RATE_LIMIT_PEER_RECEIVE",
    "RATE_LIMIT_PUBLIC_READ",
    "RATE_LIMIT_DEV_ENDPOINTS",
    "PEER_SHARED_SECRET",
    "NODE_ID",
    "NETWORK_NAME",
    "PUBLIC_NODE_URL",
)


def _reload_api(monkeypatch, environment="development", **extra_env):
    for key in RATE_LIMIT_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("ENVIRONMENT", environment)
    if environment in {"testnet", "production"}:
        monkeypatch.setenv("PEER_SHARED_SECRET", extra_env.pop("PEER_SHARED_SECRET", "super-secret-value"))

    for key, value in extra_env.items():
        monkeypatch.setenv(key, value)

    import config

    importlib.reload(config)

    import api

    api = importlib.reload(api)
    api.peer_store = PeerStore()
    return api


def _client(blockchain, monkeypatch, environment="development", **extra_env):
    api = _reload_api(monkeypatch, environment=environment, **extra_env)
    api.blockchain = blockchain
    return TestClient(api.app), api


def _create_submission(blockchain, submission_image, submitter, text="Rate limited submission"):
    return blockchain.submit_content(
        image_path=str(submission_image),
        text_content=text,
        submitter=submitter,
    )


def test_rate_limiting_is_disabled_in_development_by_default(blockchain, monkeypatch):
    client, _api = _client(blockchain, monkeypatch)

    responses = [client.post("/generate_wallet") for _ in range(4)]

    assert all(response.status_code == 200 for response in responses)


def test_wallet_creation_is_rate_limited_when_enabled(blockchain, monkeypatch):
    client, _api = _client(
        blockchain,
        monkeypatch,
        ENABLE_RATE_LIMITING="true",
        RATE_LIMIT_WALLET_CREATE="1/minute",
    )

    first_response = client.post("/generate_wallet")
    second_response = client.post("/generate_wallet")

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.json()["detail"] == "Rate limit exceeded. Try again later."


def test_submission_creation_is_rate_limited_when_enabled(blockchain, submission_image, wallets, monkeypatch):
    client, _api = _client(
        blockchain,
        monkeypatch,
        ENABLE_RATE_LIMITING="true",
        RATE_LIMIT_SUBMISSION_CREATE="1/minute",
    )

    with open(submission_image, "rb") as image_file:
        first_response = client.post(
            "/submit_content",
            data={
                "submitter": wallets["owner"].public_key,
                "text_content": "First submission",
            },
            files={"image": ("rate-limit-1.jpg", image_file, "image/jpeg")},
        )

    with open(submission_image, "rb") as image_file:
        second_response = client.post(
            "/submit_content",
            data={
                "submitter": wallets["owner"].public_key,
                "text_content": "Second submission",
            },
            files={"image": ("rate-limit-2.jpg", image_file, "image/jpeg")},
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 429


def test_voting_is_rate_limited_when_enabled(blockchain, submission_image, wallets, monkeypatch):
    client, _api = _client(
        blockchain,
        monkeypatch,
        ENABLE_RATE_LIMITING="true",
        RATE_LIMIT_VOTE="1/minute",
    )
    submission = _create_submission(blockchain, submission_image, wallets["owner"].public_key)

    first_response = client.post(
        f"/submissions/{submission.submission_id}/vote",
        data={
            "voter": wallets["contributor_one"].public_key,
            "vote_type": VOTE_ORIGINAL,
        },
    )
    second_response = client.post(
        f"/submissions/{submission.submission_id}/vote",
        data={
            "voter": wallets["contributor_two"].public_key,
            "vote_type": VOTE_ORIGINAL,
        },
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 429


def test_chain_sync_is_rate_limited_when_enabled(blockchain, monkeypatch):
    client, _api = _client(
        blockchain,
        monkeypatch,
        ENABLE_RATE_LIMITING="true",
        RATE_LIMIT_CHAIN_SYNC="1/minute",
    )

    first_response = client.post("/chain/sync")
    second_response = client.post("/chain/sync")

    assert first_response.status_code == 200
    assert second_response.status_code == 429


def test_public_read_endpoints_are_not_overly_restricted(blockchain, monkeypatch):
    client, _api = _client(
        blockchain,
        monkeypatch,
        ENABLE_RATE_LIMITING="true",
        RATE_LIMIT_PUBLIC_READ="5/minute",
    )

    responses = [
        client.get("/node-info"),
        client.get("/chain/summary"),
        client.get("/get_wallets"),
        client.get("/transaction_pool"),
    ]

    assert all(response.status_code == 200 for response in responses)


def test_peer_endpoints_still_work_under_normal_two_node_behavior(blockchain, monkeypatch):
    client, api = _client(
        blockchain,
        monkeypatch,
        ENABLE_RATE_LIMITING="true",
        RATE_LIMIT_PEER_RECEIVE="5/minute",
    )

    register_response = client.post(
        "/peers/register",
        json={
            "node_id": "peer-node-1",
            "url": "http://peer-one.test:8000",
            "network_name": api.NETWORK_NAME,
        },
    )
    assert register_response.status_code == 200

    second_register_response = client.post(
        "/peers/register",
        json={
            "node_id": "peer-node-2",
            "url": "http://peer-two.test:8000",
            "network_name": api.NETWORK_NAME,
        },
    )
    peers_response = client.get("/peers")

    assert register_response.status_code == 200
    assert second_register_response.status_code == 200
    assert peers_response.status_code == 200
    assert len(peers_response.json()["peers"]) == 2
