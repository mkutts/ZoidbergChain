from fastapi.testclient import TestClient
from eth_account import Account
from eth_account.messages import encode_defunct

from wallet_auth import WalletAuthManager


def _client(blockchain):
    import api

    api.limiter.reset()
    api.blockchain = blockchain
    api.wallet_auth_manager = WalletAuthManager(
        network_name=api.NETWORK_NAME,
        environment=api.ENVIRONMENT,
    )
    return TestClient(api.app)


def _create_metamask_account():
    return Account.create()


def _sign_message(message, account):
    signed = Account.sign_message(encode_defunct(text=message), account.key)
    return signed.signature.hex()


def _verify_wallet_session(client, account):
    challenge = client.post("/auth/wallet/challenge", json={"wallet_address": account.address})
    assert challenge.status_code == 200
    message = challenge.json()["message"]
    verify = client.post(
        "/auth/wallet/verify",
        json={
            "wallet_address": account.address,
            "message": message,
            "signature": _sign_message(message, account),
        },
    )
    assert verify.status_code == 200
    return {"Authorization": f"Bearer {verify.json()['session_token']}"}


def _upload_text_content_via_api(client, submitter, text="review policy text content"):
    response = client.post(
        "/content/text",
        json={
            "text_content": text,
            "submitted_by": submitter,
            "caption": text,
        },
    )
    assert response.status_code == 200
    return response.json()


def _request_submission_challenge(client, account, headers, content_hash, content_id=None, caption=None):
    response = client.post(
        "/auth/wallet/submission-challenge",
        json={
            "wallet_address": account.address,
            "content_hash": content_hash,
            "content_id": content_id,
            "caption": caption,
        },
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()


def _submit_signed_content_via_api(client, account, headers, content_hash, content_id=None, caption=None):
    challenge = _request_submission_challenge(
        client,
        account,
        headers,
        content_hash=content_hash,
        content_id=content_id,
        caption=caption,
    )
    response = client.post(
        "/submit_content",
        data={
            "wallet_address": account.address,
            "content_hash": content_hash,
            "content_id": content_id,
            "caption": caption,
            "message": challenge["message"],
            "signature": _sign_message(challenge["message"], account),
        },
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()["submission"]


def _request_vote_challenge(client, account, headers, submission_id, vote_type="original"):
    return client.post(
        "/auth/wallet/vote-challenge",
        json={
            "wallet_address": account.address,
            "submission_id": submission_id,
            "vote": vote_type,
        },
        headers=headers,
    )


def _vote_signed_via_api(client, submission_id, account, headers, vote_type="original"):
    challenge = _request_vote_challenge(client, account, headers, submission_id, vote_type=vote_type)
    assert challenge.status_code == 200
    response = client.post(
        f"/submissions/{submission_id}/vote",
        data={
            "wallet_address": account.address,
            "vote_type": vote_type,
            "message": challenge.json()["message"],
            "signature": _sign_message(challenge.json()["message"], account),
        },
        headers=headers,
    )
    return response


def _signed_submission(client):
    submitter = _create_metamask_account()
    submitter_headers = _verify_wallet_session(client, submitter)
    uploaded = _upload_text_content_via_api(client, submitter.address, text="review policy base")
    submission = _submit_signed_content_via_api(
        client,
        submitter,
        submitter_headers,
        content_hash=uploaded["content_hash"],
        content_id=uploaded["content_id"],
        caption="review policy base",
    )
    return submitter, submitter_headers, submission


def _clear_review_policy_env(monkeypatch):
    for name in [
        "REVIEW_ELIGIBILITY_MODE",
        "REVIEW_ALLOWLIST_WALLETS",
        "REVIEW_DENYLIST_WALLETS",
        "MIN_REVIEWER_ACCOUNT_AGE_SECONDS",
        "MIN_REVIEWER_SUBMISSION_COUNT",
        "MIN_REVIEWER_VOTE_COUNT",
        "MIN_REVIEWER_REWARD_COUNT",
        "MIN_REVIEWER_SETTLED_BALANCE_ZOID",
        "MIN_REVIEWER_SETTLED_TRANSFER_COUNT",
        "MAX_REVIEW_VOTES_PER_WALLET_PER_DAY",
        "REVIEW_POLICY_PUBLIC_LABEL",
    ]:
        monkeypatch.delenv(name, raising=False)


def test_open_mode_allows_otherwise_valid_signed_voters(blockchain, monkeypatch):
    _clear_review_policy_env(monkeypatch)
    monkeypatch.setenv("REVIEW_ELIGIBILITY_MODE", "open")
    client = _client(blockchain)
    _, _, submission = _signed_submission(client)

    voter = _create_metamask_account()
    voter_headers = _verify_wallet_session(client, voter)
    response = _vote_signed_via_api(client, submission["submission_id"], voter, voter_headers, vote_type="unsure")

    assert response.status_code == 200
    assert response.json()["vote"]["voter"] == voter.address.lower()


def test_denylisted_wallet_is_rejected(blockchain, monkeypatch):
    _clear_review_policy_env(monkeypatch)
    client = _client(blockchain)
    _, _, submission = _signed_submission(client)
    voter = _create_metamask_account()
    voter_headers = _verify_wallet_session(client, voter)
    monkeypatch.setenv("REVIEW_ELIGIBILITY_MODE", "open")
    monkeypatch.setenv("REVIEW_DENYLIST_WALLETS", voter.address)

    response = _request_vote_challenge(client, voter, voter_headers, submission["submission_id"])

    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "reviewer_not_eligible"
    assert response.json()["detail"]["reason"] == "wallet_denylisted"


def test_allowlist_mode_rejects_non_allowlisted_wallet(blockchain, monkeypatch):
    _clear_review_policy_env(monkeypatch)
    monkeypatch.setenv("REVIEW_ELIGIBILITY_MODE", "allowlist")
    client = _client(blockchain)
    _, _, submission = _signed_submission(client)
    voter = _create_metamask_account()
    voter_headers = _verify_wallet_session(client, voter)

    response = _request_vote_challenge(client, voter, voter_headers, submission["submission_id"])

    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "wallet_not_allowlisted"


def test_allowlist_mode_accepts_allowlisted_wallet(blockchain, monkeypatch):
    _clear_review_policy_env(monkeypatch)
    client = _client(blockchain)
    _, _, submission = _signed_submission(client)
    voter = _create_metamask_account()
    voter_headers = _verify_wallet_session(client, voter)
    monkeypatch.setenv("REVIEW_ELIGIBILITY_MODE", "allowlist")
    monkeypatch.setenv("REVIEW_ALLOWLIST_WALLETS", voter.address)

    response = _vote_signed_via_api(client, submission["submission_id"], voter, voter_headers)

    assert response.status_code == 200


def test_activity_mode_rejects_brand_new_zero_activity_wallet(blockchain, monkeypatch):
    _clear_review_policy_env(monkeypatch)
    monkeypatch.setenv("REVIEW_ELIGIBILITY_MODE", "activity")
    monkeypatch.setenv("MIN_REVIEWER_VOTE_COUNT", "1")
    client = _client(blockchain)
    _, _, submission = _signed_submission(client)
    voter = _create_metamask_account()
    voter_headers = _verify_wallet_session(client, voter)

    response = _request_vote_challenge(client, voter, voter_headers, submission["submission_id"])

    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "insufficient_reviewer_activity"


def test_hybrid_mode_accepts_allowlisted_wallet_even_if_activity_is_low(blockchain, monkeypatch):
    _clear_review_policy_env(monkeypatch)
    client = _client(blockchain)
    _, _, submission = _signed_submission(client)
    voter = _create_metamask_account()
    voter_headers = _verify_wallet_session(client, voter)
    monkeypatch.setenv("REVIEW_ELIGIBILITY_MODE", "hybrid")
    monkeypatch.setenv("MIN_REVIEWER_VOTE_COUNT", "1")
    monkeypatch.setenv("REVIEW_ALLOWLIST_WALLETS", voter.address)

    response = _vote_signed_via_api(client, submission["submission_id"], voter, voter_headers)

    assert response.status_code == 200


def test_admin_review_allowlist_override_applies_to_review_policy(blockchain, monkeypatch):
    _clear_review_policy_env(monkeypatch)
    monkeypatch.setenv("REVIEW_ELIGIBILITY_MODE", "allowlist")
    client = _client(blockchain)
    voter = _create_metamask_account()
    voter_headers = _verify_wallet_session(client, voter)

    blockchain.create_allowlist_entry(
        scope="review",
        subject_type="wallet",
        subject_value=voter.address,
        reason="Admin override for early tester",
    )
    blockchain.save_blockchain()

    response = client.get("/review/policy", headers=voter_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["eligibility"]["eligible"] is True
    assert body["eligibility"]["allowlist_override_applied"] is True
    assert body["eligibility"]["allowlist_scope"] == "review"
    assert body["eligibility"]["eligibility_status"] == "allowlist_override"


def test_creator_still_cannot_vote_on_own_submission(blockchain, monkeypatch):
    _clear_review_policy_env(monkeypatch)
    client = _client(blockchain)
    submitter, submitter_headers, submission = _signed_submission(client)
    monkeypatch.setenv("REVIEW_ELIGIBILITY_MODE", "allowlist")
    monkeypatch.setenv("REVIEW_ALLOWLIST_WALLETS", submitter.address)

    response = _request_vote_challenge(client, submitter, submitter_headers, submission["submission_id"])

    assert response.status_code == 400
    assert "cannot vote on their own submission" in response.json()["detail"].lower()


def test_duplicate_vote_rule_still_works(blockchain, monkeypatch):
    _clear_review_policy_env(monkeypatch)
    client = _client(blockchain)
    _, _, submission = _signed_submission(client)
    voter = _create_metamask_account()
    voter_headers = _verify_wallet_session(client, voter)
    monkeypatch.setenv("REVIEW_ELIGIBILITY_MODE", "allowlist")
    monkeypatch.setenv("REVIEW_ALLOWLIST_WALLETS", voter.address)

    first_vote = _vote_signed_via_api(client, submission["submission_id"], voter, voter_headers)
    assert first_vote.status_code == 200

    second_challenge = _request_vote_challenge(client, voter, voter_headers, submission["submission_id"])
    assert second_challenge.status_code == 400
    assert "already voted" in second_challenge.json()["detail"].lower()


def test_review_policy_endpoint_does_not_expose_secrets(blockchain, monkeypatch):
    _clear_review_policy_env(monkeypatch)
    monkeypatch.setenv("PEER_SHARED_SECRET", "super-secret-value")
    monkeypatch.setenv("REVIEW_ELIGIBILITY_MODE", "allowlist")
    client = _client(blockchain)
    voter = _create_metamask_account()

    response = client.get("/review/policy", params={"wallet_address": voter.address})

    assert response.status_code == 200
    body = response.json()
    assert body["eligibility_mode"] == "allowlist"
    assert "PEER_SHARED_SECRET" not in body
    assert "peer_shared_secret" not in body
    assert "super-secret-value" not in str(body)
