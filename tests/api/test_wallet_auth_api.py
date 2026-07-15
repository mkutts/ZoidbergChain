import importlib

from fastapi.testclient import TestClient
from datetime import timedelta

from eth_account import Account
from eth_account.messages import encode_defunct

from wallet_auth import WalletAuthManager, resolve_verified_wallet_from_authorization


def _client(blockchain):
    import config
    import api

    importlib.reload(config)
    api = importlib.reload(api)
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


def _verified_headers(client, account):
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
    assert verify.status_code == 200
    return {"Authorization": f"Bearer {verify.json()['session_token']}"}


def _upload_text_content(client, submitted_by, text="wallet auth content"):
    response = client.post(
        "/content/text",
        json={
            "text_content": text,
            "submitted_by": submitted_by,
            "caption": text,
        },
    )
    assert response.status_code == 200
    return response.json()


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

    assert response.status_code == 400
    assert "no active wallet challenge" in response.json()["detail"].lower()


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


def test_session_endpoint_returns_verified_wallet_session(blockchain):
    client, _ = _client(blockchain)
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

    response = client.get(
        "/auth/wallet/session",
        headers={"Authorization": f"Bearer {verify.json()['session_token']}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["wallet_address"] == account.address.lower()
    assert body["normalized_wallet_address"] == account.address.lower()
    assert body["issued_at"]
    assert body["expires_at"]


def test_verified_session_can_request_submission_challenge(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()
    headers = _verified_headers(client, account)
    uploaded = _upload_text_content(client, account.address, text="signed challenge")

    response = client.post(
        "/auth/wallet/submission-challenge",
        json={
            "wallet_address": account.address,
            "content_hash": uploaded["content_hash"],
            "content_id": uploaded["content_id"],
            "caption": "signed challenge",
        },
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["wallet_address"] == account.address.lower()
    assert body["content_hash"] == uploaded["content_hash"]
    assert body["content_id"] == uploaded["content_id"]
    assert "Action: submit_content" in body["message"]
    assert account.address.lower() in body["message"].lower()
    assert uploaded["content_hash"] in body["message"]
    assert body["nonce"]


def test_submission_challenge_requires_verified_session(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()

    response = client.post(
        "/auth/wallet/submission-challenge",
        json={
            "wallet_address": account.address,
            "content_hash": "a" * 64,
        },
    )

    assert response.status_code == 401
    assert "missing bearer token" in response.json()["detail"].lower()


def test_submission_challenge_rejects_wallet_mismatch(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()
    wrong_account = _create_account()
    headers = _verified_headers(client, account)
    uploaded = _upload_text_content(client, account.address, text="wallet mismatch")

    response = client.post(
        "/auth/wallet/submission-challenge",
        json={
            "wallet_address": wrong_account.address,
            "content_hash": uploaded["content_hash"],
            "content_id": uploaded["content_id"],
        },
        headers=headers,
    )

    assert response.status_code == 403
    assert "must match the verified wallet session" in response.json()["detail"].lower()


def test_submission_challenge_rejects_content_id_hash_mismatch(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()
    headers = _verified_headers(client, account)
    first = _upload_text_content(client, account.address, text="first content")
    second = _upload_text_content(client, account.address, text="second content")

    response = client.post(
        "/auth/wallet/submission-challenge",
        json={
            "wallet_address": account.address,
            "content_hash": first["content_hash"],
            "content_id": second["content_id"],
        },
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "content_id does not match content_hash."


def test_verified_session_can_request_vote_challenge(blockchain):
    client, _ = _client(blockchain)
    submitter = _create_account()
    voter = _create_account()
    submitter_headers = _verified_headers(client, submitter)
    voter_headers = _verified_headers(client, voter)
    uploaded = _upload_text_content(client, submitter.address, text="vote challenge content")

    submission_challenge = client.post(
        "/auth/wallet/submission-challenge",
        json={
            "wallet_address": submitter.address,
            "content_hash": uploaded["content_hash"],
            "content_id": uploaded["content_id"],
            "caption": "vote challenge content",
        },
        headers=submitter_headers,
    )
    signed_submission = client.post(
        "/submit_content",
        data={
            "wallet_address": submitter.address,
            "content_hash": uploaded["content_hash"],
            "content_id": uploaded["content_id"],
            "message": submission_challenge.json()["message"],
            "signature": _sign_message(submission_challenge.json()["message"], submitter),
        },
        headers=submitter_headers,
    )
    submission_id = signed_submission.json()["submission"]["submission_id"]

    response = client.post(
        "/auth/wallet/vote-challenge",
        json={
            "wallet_address": voter.address,
            "submission_id": submission_id,
            "vote": "original",
        },
        headers=voter_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["wallet_address"] == voter.address.lower()
    assert body["submission_id"] == submission_id
    assert body["content_hash"] == uploaded["content_hash"]
    assert body["vote"] == "original"
    assert "Action: vote_originality" in body["message"]


def test_vote_challenge_rejects_wallet_mismatch(blockchain):
    client, _ = _client(blockchain)
    submitter = _create_account()
    voter = _create_account()
    wrong_voter = _create_account()
    submitter_headers = _verified_headers(client, submitter)
    voter_headers = _verified_headers(client, voter)
    uploaded = _upload_text_content(client, submitter.address, text="vote mismatch content")
    submission_challenge = client.post(
        "/auth/wallet/submission-challenge",
        json={
            "wallet_address": submitter.address,
            "content_hash": uploaded["content_hash"],
            "content_id": uploaded["content_id"],
        },
        headers=submitter_headers,
    )
    signed_submission = client.post(
        "/submit_content",
        data={
            "wallet_address": submitter.address,
            "content_hash": uploaded["content_hash"],
            "content_id": uploaded["content_id"],
            "message": submission_challenge.json()["message"],
            "signature": _sign_message(submission_challenge.json()["message"], submitter),
        },
        headers=submitter_headers,
    )

    response = client.post(
        "/auth/wallet/vote-challenge",
        json={
            "wallet_address": wrong_voter.address,
            "submission_id": signed_submission.json()["submission"]["submission_id"],
            "vote": "original",
        },
        headers=voter_headers,
    )

    assert response.status_code == 403
    assert "must match the verified wallet session" in response.json()["detail"].lower()


def test_session_endpoint_rejects_missing_and_invalid_token(blockchain):
    client, _ = _client(blockchain)

    missing = client.get("/auth/wallet/session")
    invalid = client.get(
        "/auth/wallet/session",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert missing.status_code == 401
    assert "missing bearer token" in missing.json()["detail"].lower()
    assert invalid.status_code == 401
    assert "invalid or expired session token" in invalid.json()["detail"].lower()


def test_session_endpoint_rejects_expired_token(blockchain):
    import api

    api.blockchain = blockchain
    api.wallet_auth_manager = WalletAuthManager(
        network_name=api.NETWORK_NAME,
        environment=api.ENVIRONMENT,
        session_ttl_seconds=-1,
    )
    client = TestClient(api.app)
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

    response = client.get(
        "/auth/wallet/session",
        headers={"Authorization": f"Bearer {verify.json()['session_token']}"},
    )

    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


def test_logout_revokes_verified_wallet_session(blockchain):
    client, _ = _client(blockchain)
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
    token = verify.json()["session_token"]

    logout = client.post(
        "/auth/wallet/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    after_logout = client.get(
        "/auth/wallet/session",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert logout.status_code == 200
    assert logout.json()["logged_out"] is True
    assert logout.json()["revoked"] is True
    assert after_logout.status_code == 401


def test_logout_without_valid_token_is_idempotent(blockchain):
    client, _ = _client(blockchain)

    missing = client.post("/auth/wallet/logout")
    invalid = client.post(
        "/auth/wallet/logout",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert missing.status_code == 200
    assert missing.json()["logged_out"] is True
    assert missing.json()["revoked"] is False
    assert invalid.status_code == 200
    assert invalid.json()["revoked"] is False


def test_prune_expired_removes_old_challenges_and_sessions():
    manager = WalletAuthManager(
        network_name="zoidberg-testnet",
        environment="test",
        challenge_ttl_seconds=60,
        session_ttl_seconds=60,
    )
    account = _create_account()
    challenge = manager.issue_challenge(account.address)
    signature = _sign_message(challenge["message"], account)
    verify = manager.verify_signature(
        account.address,
        challenge["message"],
        signature,
    )

    assert manager._challenges_by_wallet
    assert manager._sessions_by_token_hash

    stored_challenge = manager._challenges_by_wallet[account.address.lower()]
    stored_challenge.expires_at = stored_challenge.issued_at - timedelta(seconds=1)
    session = manager.resolve_session(verify["session_token"])
    session.expires_at = session.issued_at - timedelta(seconds=1)

    manager.prune_expired()

    assert manager._challenges_by_wallet == {}
    assert manager._sessions_by_token_hash == {}
