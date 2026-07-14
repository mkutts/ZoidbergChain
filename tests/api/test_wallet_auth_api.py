from fastapi.testclient import TestClient
from eth_account import Account
from eth_account.messages import encode_defunct

from wallet_auth import WalletAuthManager, resolve_verified_wallet_from_authorization


def _client(blockchain):
    import api

    api.blockchain = blockchain
    api.wallet_auth_manager = WalletAuthManager(
        network_name=api.NETWORK_NAME,
        environment=api.ENVIRONMENT,
    )
    return TestClient(api.app), api.wallet_auth_manager


def _create_account():
    return Account.create()


def _issue_challenge(client, wallet_address):
    response = client.post("/auth/wallet/challenge", json={"wallet_address": wallet_address})
    assert response.status_code == 200
    return response.json()


def _sign_message(message, account):
    signed = Account.sign_message(encode_defunct(text=message), account.key)
    return signed.signature.hex()


def test_valid_wallet_gets_challenge(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()

    response = client.post("/auth/wallet/challenge", json={"wallet_address": account.address})

    assert response.status_code == 200
    body = response.json()
    assert body["wallet_address"] == account.address
    assert body["normalized_wallet_address"] == account.address.lower()
    assert body["nonce"]
    assert body["expires_at"]


def test_invalid_wallet_rejected(blockchain):
    client, _ = _client(blockchain)

    response = client.post("/auth/wallet/challenge", json={"wallet_address": "not-a-wallet"})

    assert response.status_code == 422


def test_nonce_is_random_and_challenge_expires(blockchain):
    client, manager = _client(blockchain)
    account = _create_account()

    first = _issue_challenge(client, account.address)
    second = _issue_challenge(client, account.address)

    assert first["nonce"] != second["nonce"]
    stored = manager._challenges_by_wallet[account.address.lower()]
    assert stored.expires_at.isoformat() == second["expires_at"]


def test_challenge_message_includes_wallet_network_and_nonce(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()

    challenge = _issue_challenge(client, account.address)

    assert account.address.lower() in challenge["message"].lower()
    assert "Network: zoidberg-testnet" in challenge["message"]
    assert challenge["nonce"] in challenge["message"]


def test_valid_personal_sign_signature_verifies(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()
    challenge = _issue_challenge(client, account.address)
    signature = _sign_message(challenge["message"], account)

    response = client.post(
        "/auth/wallet/verify",
        json={
            "wallet_address": account.address,
            "message": challenge["message"],
            "signature": signature,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["verified"] is True
    assert body["wallet_address"] == account.address.lower()
    assert body["session_token"]
    assert body["expires_at"]


def test_wrong_wallet_rejected(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()
    wrong_account = _create_account()
    challenge = _issue_challenge(client, account.address)
    signature = _sign_message(challenge["message"], wrong_account)

    response = client.post(
        "/auth/wallet/verify",
        json={
            "wallet_address": account.address,
            "message": challenge["message"],
            "signature": signature,
        },
    )

    assert response.status_code == 400
    assert "does not match" in response.json()["detail"]


def test_modified_message_rejected(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()
    challenge = _issue_challenge(client, account.address)
    signature = _sign_message(challenge["message"], account)

    response = client.post(
        "/auth/wallet/verify",
        json={
            "wallet_address": account.address,
            "message": challenge["message"] + "\nModified",
            "signature": signature,
        },
    )

    assert response.status_code == 400
    assert "does not match" in response.json()["detail"]


def test_reused_nonce_rejected(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()
    challenge = _issue_challenge(client, account.address)
    signature = _sign_message(challenge["message"], account)

    first = client.post(
        "/auth/wallet/verify",
        json={
            "wallet_address": account.address,
            "message": challenge["message"],
            "signature": signature,
        },
    )
    second = client.post(
        "/auth/wallet/verify",
        json={
            "wallet_address": account.address,
            "message": challenge["message"],
            "signature": signature,
        },
    )

    assert first.status_code == 200
    assert second.status_code == 401
    assert "already been used" in second.json()["detail"]


def test_expired_challenge_rejected(blockchain):
    import api

    api.blockchain = blockchain
    api.wallet_auth_manager = WalletAuthManager(
        network_name=api.NETWORK_NAME,
        environment=api.ENVIRONMENT,
        challenge_ttl_seconds=-1,
    )
    client = TestClient(api.app)
    account = _create_account()
    challenge = _issue_challenge(client, account.address)
    signature = _sign_message(challenge["message"], account)

    response = client.post(
        "/auth/wallet/verify",
        json={
            "wallet_address": account.address,
            "message": challenge["message"],
            "signature": signature,
        },
    )

    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


def test_malformed_signature_rejected(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()
    challenge = _issue_challenge(client, account.address)

    response = client.post(
        "/auth/wallet/verify",
        json={
            "wallet_address": account.address,
            "message": challenge["message"],
            "signature": "bad-signature",
        },
    )

    assert response.status_code == 400
    assert "malformed signature" in response.json()["detail"].lower()


def test_auth_helper_returns_wallet_for_valid_session(blockchain):
    client, manager = _client(blockchain)
    account = _create_account()
    challenge = _issue_challenge(client, account.address)
    signature = _sign_message(challenge["message"], account)
    verify = client.post(
        "/auth/wallet/verify",
        json={
            "wallet_address": account.address,
            "message": challenge["message"],
            "signature": signature,
        },
    )

    wallet_address = resolve_verified_wallet_from_authorization(
        f"Bearer {verify.json()['session_token']}",
        manager=manager,
    )

    assert wallet_address == account.address.lower()


def test_auth_helper_rejects_invalid_and_expired_session(blockchain):
    client, manager = _client(blockchain)
    account = _create_account()
    challenge = _issue_challenge(client, account.address)
    signature = _sign_message(challenge["message"], account)
    verify = client.post(
        "/auth/wallet/verify",
        json={
            "wallet_address": account.address,
            "message": challenge["message"],
            "signature": signature,
        },
    )

    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        resolve_verified_wallet_from_authorization("Bearer invalid-token", manager=manager)

    expired_manager = WalletAuthManager(
        network_name=manager.network_name,
        environment=manager.environment,
        session_ttl_seconds=-1,
    )
    expired_challenge = expired_manager.issue_challenge(account.address)
    expired_signature = _sign_message(expired_challenge["message"], account)
    expired_verify = expired_manager.verify_signature(
        account.address,
        expired_challenge["message"],
        expired_signature,
    )

    with pytest.raises(HTTPException):
        resolve_verified_wallet_from_authorization(
            f"Bearer {expired_verify['session_token']}",
            manager=expired_manager,
        )

    assert verify.json()["session_token"]
