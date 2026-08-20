import importlib

from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

import blockchain as blockchain_module
from access_control import AccessSessionManager
from wallet_auth import WalletAuthManager


def _client(blockchain):
    import api

    api.limiter.reset()
    api.blockchain = blockchain
    api.wallet_auth_manager = WalletAuthManager(
        network_name=api.NETWORK_NAME,
        environment=api.ENVIRONMENT,
    )
    api.access_session_manager = AccessSessionManager()
    return TestClient(api.app)


def _create_account():
    return Account.create()


def _sign_message(message, account):
    signed = Account.sign_message(encode_defunct(text=message), account.key)
    return signed.signature.hex()


def _verify_wallet_session(client, account):
    challenge = client.post("/auth/wallet/challenge", json={"wallet_address": account.address})
    assert challenge.status_code == 200
    verify = client.post(
        "/auth/wallet/verify",
        json={
            "wallet_address": account.address,
            "message": challenge.json()["message"],
            "signature": _sign_message(challenge.json()["message"], account),
        },
    )
    assert verify.status_code == 200
    return {"Authorization": f"Bearer {verify.json()['session_token']}"}


def _upload_text_content_via_api(client, submitter, text="access-controlled text content"):
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
    return response


def _submit_signed_content_via_api(client, account, headers, content_hash, content_id=None, caption=None):
    challenge = _request_submission_challenge(
        client,
        account,
        headers,
        content_hash=content_hash,
        content_id=content_id,
        caption=caption,
    )
    assert challenge.status_code == 200
    response = client.post(
        "/submit_content",
        data={
            "wallet_address": account.address,
            "content_hash": content_hash,
            "content_id": content_id,
            "caption": caption,
            "message": challenge.json()["message"],
            "signature": _sign_message(challenge.json()["message"], account),
        },
        headers=headers,
    )
    return response


def _vote_signed_via_api(client, submission_id, account, headers, vote_type="original"):
    challenge = client.post(
        "/auth/wallet/vote-challenge",
        json={
            "wallet_address": account.address,
            "submission_id": submission_id,
            "vote": vote_type,
        },
        headers=headers,
    )
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


def _create_access_invite(blockchain, *, name="Tester", email="tester@example.test", max_wallets=1):
    account, access_code = blockchain.create_access_invite(
        name=name,
        email=email,
        max_wallets=max_wallets,
        reviewed_by="test",
    )
    blockchain.save_blockchain()
    return account, access_code


def _login_access_code(client, access_code):
    response = client.post("/access/login", json={"access_code": access_code})
    assert response.status_code == 200
    return response.json()


def _bind_wallet(client, access_session_token, verified_headers):
    response = client.post(
        "/access/bind-wallet",
        headers={
            **verified_headers,
            "X-ZOID-Access-Session": access_session_token,
        },
    )
    return response


def _configure_access(monkeypatch, **overrides):
    defaults = {
        "ACCESS_CONTROL_MODE": "invite_only",
        "ACCESS_REQUESTS_ENABLED": True,
        "ACCESS_DEV_BYPASS_ENABLED": False,
        "REQUIRE_ACCESS_FOR_APP": True,
        "REQUIRE_ACCESS_FOR_SUBMISSIONS": True,
        "REQUIRE_ACCESS_FOR_VOTES": True,
        "REQUIRE_ACCESS_FOR_REWARDS": True,
        "REQUIRE_ACCESS_FOR_TRANSFERS": True,
        "MAX_WALLETS_PER_ACCESS_ACCOUNT": 1,
    }
    defaults.update(overrides)
    import config
    import api
    for name, value in defaults.items():
        monkeypatch.setattr(config, name, value)
        monkeypatch.setattr(api, name, value)
    if "REQUIRE_ACCESS_FOR_REWARDS" in defaults:
        monkeypatch.setattr(blockchain_module, "REQUIRE_ACCESS_FOR_REWARDS", defaults["REQUIRE_ACCESS_FOR_REWARDS"])


def test_access_status_is_public_and_non_secret(blockchain, monkeypatch):
    _configure_access(monkeypatch)
    client = _client(blockchain)

    response = client.get("/access/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["access_control_mode"] == "invite_only"
    assert payload["require_access_for_app"] is True
    assert "invite_code_hash" not in str(payload)
    assert "PEER_SHARED_SECRET" not in str(payload)


def test_access_request_creates_pending_record(blockchain, monkeypatch):
    _configure_access(monkeypatch)
    client = _client(blockchain)

    response = client.post(
        "/access/request",
        json={
            "name": "Pending Tester",
            "email": "pending@example.test",
            "handle": "@pending",
            "reason": "Try the controlled testnet",
            "notes": "QA flow",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["request"]["status"] == "pending"
    assert blockchain.list_access_requests(status="pending")


def test_invite_code_binds_one_wallet_and_blocks_second_wallet(blockchain, monkeypatch):
    _configure_access(monkeypatch, MAX_WALLETS_PER_ACCESS_ACCOUNT=1)
    client = _client(blockchain)
    _, access_code = _create_access_invite(blockchain, email="bound@example.test", max_wallets=1)
    login = _login_access_code(client, access_code)

    first_wallet = _create_account()
    first_headers = _verify_wallet_session(client, first_wallet)
    bind_response = _bind_wallet(client, login["access_session_token"], first_headers)
    assert bind_response.status_code == 200

    second_wallet = _create_account()
    second_headers = _verify_wallet_session(client, second_wallet)
    second_bind = _bind_wallet(client, login["access_session_token"], second_headers)
    assert second_bind.status_code == 409
    assert "maximum number of bound wallets" in str(second_bind.json()).lower()


def test_access_me_stays_locked_after_invite_login_until_wallet_is_bound(blockchain, monkeypatch):
    _configure_access(monkeypatch, MAX_WALLETS_PER_ACCESS_ACCOUNT=1)
    client = _client(blockchain)
    _account, access_code = _create_access_invite(blockchain, email="lock-state@example.test", max_wallets=1)

    login = _login_access_code(client, access_code)
    me_before_bind = client.get(
        "/access/me",
        headers={"X-ZOID-Access-Session": login["access_session_token"]},
    )

    assert me_before_bind.status_code == 200
    before_payload = me_before_bind.json()
    assert before_payload["invite_authenticated"] is True
    assert before_payload["wallet_bound"] is False
    assert before_payload["access_granted"] is False
    assert before_payload["can_submit"] is False

    wallet = _create_account()
    wallet_headers = _verify_wallet_session(client, wallet)
    bind_response = _bind_wallet(client, login["access_session_token"], wallet_headers)
    assert bind_response.status_code == 200

    me_after_bind = client.get("/access/me", headers=wallet_headers)
    assert me_after_bind.status_code == 200
    after_payload = me_after_bind.json()
    assert after_payload["wallet_bound"] is True
    assert after_payload["access_granted"] is True
    assert after_payload["can_submit"] is True
    assert after_payload["wallet_binding"]["wallet_address"] == wallet.address.lower()


def test_redeemed_invite_code_cannot_be_reused(blockchain, monkeypatch):
    _configure_access(monkeypatch, MAX_WALLETS_PER_ACCESS_ACCOUNT=1)
    client = _client(blockchain)
    _account, access_code = _create_access_invite(blockchain, email="redeemed@example.test", max_wallets=1)

    login = _login_access_code(client, access_code)
    wallet_headers = _verify_wallet_session(client, _create_account())
    bind_response = _bind_wallet(client, login["access_session_token"], wallet_headers)
    assert bind_response.status_code == 200

    second_login = client.post("/access/login", json={"access_code": access_code})
    assert second_login.status_code == 409
    assert "redeemed" in str(second_login.json()).lower()


def test_access_login_sees_cli_approved_invite_without_api_restart(blockchain, monkeypatch):
    _configure_access(monkeypatch, MAX_WALLETS_PER_ACCESS_ACCOUNT=1)
    client = _client(blockchain)

    external_blockchain = blockchain_module.Blockchain(
        project_owner_wallet=blockchain_module.Wallet(),
        Contributor_one=blockchain_module.Wallet(),
        Contributor_two=blockchain_module.Wallet(),
    )
    external_account, access_code = external_blockchain.create_access_invite(
        name="CLI Approved Tester",
        email="cli-approved@example.test",
        max_wallets=1,
        reviewed_by="test",
    )
    external_blockchain.save_blockchain()

    login = client.post("/access/login", json={"access_code": access_code})

    assert login.status_code == 200
    payload = login.json()
    assert payload["access_account"]["access_account_id"] == external_account["access_account_id"]
    assert payload["access_session_token"]


def test_bind_requires_access_session_and_verified_wallet_session(blockchain, monkeypatch):
    _configure_access(monkeypatch)
    client = _client(blockchain)
    _account, access_code = _create_access_invite(blockchain, email="missing-sessions@example.test")
    login = _login_access_code(client, access_code)
    verified_wallet = _create_account()
    verified_headers = _verify_wallet_session(client, verified_wallet)

    missing_access_session = client.post("/access/bind-wallet", headers=verified_headers)
    assert missing_access_session.status_code == 401

    missing_wallet_session = client.post(
        "/access/bind-wallet",
        headers={"X-ZOID-Access-Session": login["access_session_token"]},
    )
    assert missing_wallet_session.status_code == 401


def test_bind_rejects_frontend_wallet_mismatch_claim(blockchain, monkeypatch):
    _configure_access(monkeypatch)
    client = _client(blockchain)
    _account, access_code = _create_access_invite(blockchain, email="mismatch@example.test")
    login = _login_access_code(client, access_code)
    wallet = _create_account()
    wallet_headers = _verify_wallet_session(client, wallet)

    response = client.post(
        "/access/bind-wallet",
        json={"wallet_address": "0x1111111111111111111111111111111111111111"},
        headers={
            **wallet_headers,
            "X-ZOID-Access-Session": login["access_session_token"],
        },
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["detail"]["error"] == "verified_wallet_mismatch"


def test_bound_wallet_persists_across_blockchain_reload(blockchain, monkeypatch):
    _configure_access(monkeypatch)
    _account, access_code = _create_access_invite(blockchain, email="persist@example.test")
    account = blockchain.resolve_access_account_by_invite_code(access_code)
    binding = blockchain.bind_wallet_to_access_account(
        account["access_account_id"],
        "0x1111111111111111111111111111111111111111",
    )
    blockchain.save_blockchain()

    reloaded = blockchain_module.Blockchain(storage_backend=blockchain.storage)
    reloaded_account = reloaded.get_access_account(account["access_account_id"])
    reloaded_binding = reloaded.get_wallet_binding(binding["wallet_address"])

    assert reloaded_account is not None
    assert reloaded_account["invite_code_redeemed_at"]
    assert binding["wallet_address"] in reloaded_account["bound_wallets"]
    assert reloaded_binding["status"] == "active"


def test_wallet_switch_does_not_inherit_access(blockchain, monkeypatch):
    _configure_access(monkeypatch)
    client = _client(blockchain)
    _account, access_code = _create_access_invite(blockchain, email="switch@example.test")
    login = _login_access_code(client, access_code)

    wallet_a = _create_account()
    wallet_a_headers = _verify_wallet_session(client, wallet_a)
    assert _bind_wallet(client, login["access_session_token"], wallet_a_headers).status_code == 200

    wallet_b = _create_account()
    wallet_b_headers = _verify_wallet_session(client, wallet_b)
    response = client.get("/access/me", headers=wallet_b_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["wallet_bound"] is False
    assert payload["access_granted"] is False


def test_bound_wallet_can_recover_access_even_if_stale_access_session_header_is_sent(blockchain, monkeypatch):
    _configure_access(monkeypatch)
    client = _client(blockchain)
    _account, access_code = _create_access_invite(blockchain, email="stale-session@example.test")
    login = _login_access_code(client, access_code)

    wallet = _create_account()
    wallet_headers = _verify_wallet_session(client, wallet)
    assert _bind_wallet(client, login["access_session_token"], wallet_headers).status_code == 200

    response = client.get(
        "/access/me",
        headers={
            **wallet_headers,
            "X-ZOID-Access-Session": "stale-access-session-token",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["wallet_bound"] is True
    assert payload["access_granted"] is True


def test_access_required_submission_and_vote_paths_allow_bound_wallets_only(blockchain, monkeypatch):
    _configure_access(monkeypatch)
    client = _client(blockchain)

    creator = _create_account()
    creator_headers = _verify_wallet_session(client, creator)
    uploaded = _upload_text_content_via_api(client, creator.address, text="invite-only submission")

    creator_challenge = _request_submission_challenge(
        client,
        creator,
        creator_headers,
        uploaded["content_hash"],
        uploaded["content_id"],
        "invite-only submission",
    )
    assert creator_challenge.status_code == 403

    _, creator_code = _create_access_invite(blockchain, email="creator@example.test")
    creator_login = _login_access_code(client, creator_code)
    assert _bind_wallet(client, creator_login["access_session_token"], creator_headers).status_code == 200

    submit_response = _submit_signed_content_via_api(
        client,
        creator,
        creator_headers,
        uploaded["content_hash"],
        uploaded["content_id"],
        "invite-only submission",
    )
    assert submit_response.status_code == 200
    submission = submit_response.json()["submission"]

    unbound_voter = _create_account()
    unbound_headers = _verify_wallet_session(client, unbound_voter)
    vote_challenge = client.post(
        "/auth/wallet/vote-challenge",
        json={
            "wallet_address": unbound_voter.address,
            "submission_id": submission["submission_id"],
            "vote": "original",
        },
        headers=unbound_headers,
    )
    assert vote_challenge.status_code == 403

    bound_voter = _create_account()
    bound_headers = _verify_wallet_session(client, bound_voter)
    _, voter_code = _create_access_invite(blockchain, email="voter@example.test")
    voter_login = _login_access_code(client, voter_code)
    assert _bind_wallet(client, voter_login["access_session_token"], bound_headers).status_code == 200

    vote_response = _vote_signed_via_api(client, submission["submission_id"], bound_voter, bound_headers, vote_type="original")
    assert vote_response.status_code == 200


def test_access_required_rewards_only_pay_bound_active_wallets(blockchain, monkeypatch):
    _configure_access(monkeypatch)
    monkeypatch.setattr(blockchain_module, "VOTER_REWARDS_ENABLED", True)
    monkeypatch.setattr(blockchain_module, "VOTER_REWARD_REQUIRE_REVIEW_ELIGIBLE", False)
    client = _client(blockchain)

    creator = _create_account()
    creator_headers = _verify_wallet_session(client, creator)
    _, creator_code = _create_access_invite(blockchain, email="reward-creator@example.test")
    creator_login = _login_access_code(client, creator_code)
    assert _bind_wallet(client, creator_login["access_session_token"], creator_headers).status_code == 200

    uploaded = _upload_text_content_via_api(client, creator.address, text="reward access control")
    submission_response = _submit_signed_content_via_api(
        client,
        creator,
        creator_headers,
        uploaded["content_hash"],
        uploaded["content_id"],
        "reward access control",
    )
    assert submission_response.status_code == 200
    submission_id = submission_response.json()["submission"]["submission_id"]

    bound_majority = _create_account()
    bound_headers = _verify_wallet_session(client, bound_majority)
    _, bound_code = _create_access_invite(blockchain, email="bound-majority@example.test")
    bound_login = _login_access_code(client, bound_code)
    assert _bind_wallet(client, bound_login["access_session_token"], bound_headers).status_code == 200

    unbound_majority = _create_account()
    unbound_headers = _verify_wallet_session(client, unbound_majority)
    second_unbound_majority = _create_account()
    second_unbound_headers = _verify_wallet_session(client, second_unbound_majority)
    unsure_voter = _create_account()
    unsure_headers = _verify_wallet_session(client, unsure_voter)
    minority = _create_account()
    minority_headers = _verify_wallet_session(client, minority)
    _, minority_code = _create_access_invite(blockchain, email="minority@example.test")
    minority_login = _login_access_code(client, minority_code)
    assert _bind_wallet(client, minority_login["access_session_token"], minority_headers).status_code == 200

    # Temporarily allow unbound vote admission while still requiring access for rewards.
    import config
    monkeypatch.setattr(config, "REQUIRE_ACCESS_FOR_VOTES", False)
    import api
    monkeypatch.setattr(api, "REQUIRE_ACCESS_FOR_VOTES", False)

    assert _vote_signed_via_api(client, submission_id, bound_majority, bound_headers, vote_type="original").status_code == 200
    assert _vote_signed_via_api(client, submission_id, unbound_majority, unbound_headers, vote_type="original").status_code == 200
    assert _vote_signed_via_api(client, submission_id, second_unbound_majority, second_unbound_headers, vote_type="original").status_code == 200
    assert _vote_signed_via_api(client, submission_id, unsure_voter, unsure_headers, vote_type="unsure").status_code == 200
    assert _vote_signed_via_api(client, submission_id, minority, minority_headers, vote_type="not_original").status_code == 200

    evaluate_response = client.post(
        f"/submissions/{submission_id}/evaluate",
        data={"automated_originality_passed": "true"},
    )
    assert evaluate_response.status_code == 200

    mint_response = client.post(
        f"/mint-queue/{submission_id}/mint",
        data={"miner": client.post('/generate_wallet').json()["wallet"]["public_key"]},
    )
    assert mint_response.status_code == 200

    summary = client.get(f"/submissions/{submission_id}/voter-rewards").json()
    assert summary["rewarded_voter_count"] == 1
    assert summary["pending_voter_count"] == 0
    assert any(item["reason"] == "wallet_not_bound" for item in summary["excluded_voters"])

    bound_rewards = client.get(f"/accounts/{bound_majority.address}/rewards").json()["rewards"]
    assert len(bound_rewards) == 1
    unbound_rewards = client.get(f"/accounts/{unbound_majority.address}/rewards").json()["rewards"]
    assert unbound_rewards == []


def test_access_dev_bypass_keeps_local_development_open(blockchain, monkeypatch):
    _configure_access(
        monkeypatch,
        ACCESS_CONTROL_MODE="invite_only",
        ACCESS_DEV_BYPASS_ENABLED=True,
        REQUIRE_ACCESS_FOR_SUBMISSIONS=True,
        REQUIRE_ACCESS_FOR_VOTES=True,
    )
    client = _client(blockchain)

    creator = _create_account()
    creator_headers = _verify_wallet_session(client, creator)
    uploaded = _upload_text_content_via_api(client, creator.address, text="dev bypass submission")
    submit_response = _submit_signed_content_via_api(
        client,
        creator,
        creator_headers,
        uploaded["content_hash"],
        uploaded["content_id"],
        "dev bypass submission",
    )
    assert submit_response.status_code == 200


def test_access_me_does_not_expose_invite_hashes(blockchain, monkeypatch):
    _configure_access(monkeypatch)
    client = _client(blockchain)
    tester = _create_account()
    tester_headers = _verify_wallet_session(client, tester)
    _, access_code = _create_access_invite(blockchain, email="me@example.test")
    login = _login_access_code(client, access_code)
    assert _bind_wallet(client, login["access_session_token"], tester_headers).status_code == 200

    response = client.get("/access/me", headers=tester_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["access_account"]["status"] == "active"
    assert "invite_code_hash" not in str(payload)
    assert "access_session_token" not in str(payload)
