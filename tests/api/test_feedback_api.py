import sys

from fastapi.testclient import TestClient
from eth_account import Account
from eth_account.messages import encode_defunct

from access_control import AccessSessionManager
from admin_auth import AdminSessionManager, hash_admin_password
from wallet_auth import WalletAuthManager


def _api_module():
    import api

    return api


def _client(blockchain):
    api = _api_module()
    from peers import PeerStore
    api.limiter.reset()
    api.blockchain = blockchain
    api.wallet_auth_manager = WalletAuthManager(
        network_name=api.NETWORK_NAME,
        environment=api.ENVIRONMENT,
    )
    api.access_session_manager = AccessSessionManager()
    api.admin_session_manager = AdminSessionManager(session_ttl_seconds=api.ADMIN_SESSION_TTL_SECONDS)
    # Reset peer_store to use the same isolated storage backend as the blockchain fixture
    api.peer_store = PeerStore(storage_backend=blockchain.storage)
    return TestClient(api.app)


def _configure_admin(monkeypatch, **overrides):
    defaults = {
        "ADMIN_UI_ENABLED": True,
        "ADMIN_AUTH_ENABLED": True,
        "ADMIN_SESSION_TTL_SECONDS": 3600,
        "ADMIN_PASSWORD_HASH": hash_admin_password("super-secret-admin"),
        "ADMIN_BOOTSTRAP_TOKEN": "",
    }
    defaults.update(overrides)

    import config
    api = sys.modules.get("api")

    for name, value in defaults.items():
        monkeypatch.setattr(config, name, value)
        if api is not None:
            monkeypatch.setattr(api, name, value)

    if api is not None:
        api.admin_session_manager = AdminSessionManager(session_ttl_seconds=api.ADMIN_SESSION_TTL_SECONDS)


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
    api = sys.modules.get("api")

    for name, value in defaults.items():
        monkeypatch.setattr(config, name, value)
        if api is not None:
            monkeypatch.setattr(api, name, value)


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
    return client.post(
        "/access/bind-wallet",
        headers={
            **verified_headers,
            "X-ZOID-Access-Session": access_session_token,
        },
    )


def _login_admin(client, password="super-secret-admin"):
    response = client.post("/admin/login", json={"password": password})
    import api
    print("DEBUG_ADMIN_LOGIN", api.ADMIN_AUTH_ENABLED, bool(api.ADMIN_PASSWORD_HASH), response.status_code, response.text)
    assert response.status_code == 200
    return response


def test_beta_user_can_submit_feedback_with_wallet_and_access_context(blockchain, monkeypatch):
    _configure_access(monkeypatch)
    client = _client(blockchain)

    account, access_code = _create_access_invite(blockchain, email="feedback@example.test")
    wallet = _create_account()
    wallet_headers = _verify_wallet_session(client, wallet)
    login = _login_access_code(client, access_code)
    bind = _bind_wallet(client, login["access_session_token"], wallet_headers)
    assert bind.status_code == 200

    response = client.post(
        "/feedback",
        json={
            "type": "wallet_connection_issue",
            "title": "Wallet reconnect is confusing",
            "description": "Returning flow needed an extra refresh before the UI caught up.",
            "current_page": "/dashboard",
            "current_flow": "dashboard",
            "eligibility_snapshot": {
                "access_granted": True,
                "can_submit": True,
                "blocked_reasons": [],
            },
            "browser_metadata": {
                "platform": "Win32",
                "language": "en-US",
            },
            "viewport_width": 1440,
            "viewport_height": 900,
            "is_mobile": False,
        },
        headers={
            **wallet_headers,
            "X-ZOID-Access-Session": login["access_session_token"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["feedback"]["status"] == "new"
    record = blockchain.get_feedback(payload["feedback"]["feedback_id"])
    assert record["wallet_address"] == wallet.address.lower()
    assert record["access_account_id"] == account["access_account_id"]
    assert record["eligibility_snapshot"]["can_submit"] is True
    assert "session_token" not in str(record)


def test_blocked_user_can_submit_feedback_without_access_grant(blockchain, monkeypatch):
    _configure_access(monkeypatch)
    client = _client(blockchain)

    response = client.post(
        "/feedback",
        json={
            "type": "access_allowlist_issue",
            "title": "Still blocked on access screen",
            "description": "I was invited but the access gate still says my wallet is not approved.",
            "current_page": "/",
            "current_flow": "access_gate",
        },
    )

    assert response.status_code == 200
    assert blockchain.list_feedback()[0]["status"] == "new"

    eligibility = client.get("/eligibility/status")
    assert eligibility.status_code == 200
    assert eligibility.json()["access_granted"] is False


def test_invalid_feedback_payload_is_rejected(blockchain, monkeypatch):
    _configure_access(monkeypatch)
    client = _client(blockchain)

    response = client.post(
        "/feedback",
        json={
            "type": "bug",
            "title": "x" * 161,
            "description": "",
        },
    )

    assert response.status_code == 422


def test_admin_feedback_endpoints_require_auth(blockchain, monkeypatch):
    _configure_admin(monkeypatch)
    client = _client(blockchain)
    record = blockchain.create_feedback(
        feedback_type="bug",
        title="Admin auth required",
        description="Feedback detail should stay admin-only.",
    )
    blockchain.save_blockchain()

    list_response = client.get("/admin/feedback")
    detail_response = client.get(f"/admin/feedback/{record['feedback_id']}")
    patch_response = client.patch(
        f"/admin/feedback/{record['feedback_id']}",
        json={"status": "resolved", "reviewed_by": "operator"},
    )

    assert list_response.status_code == 401
    assert detail_response.status_code == 401
    assert patch_response.status_code == 401


def test_admin_can_update_feedback_status_priority_and_notes(blockchain, monkeypatch):
    _configure_admin(monkeypatch)
    client = _client(blockchain)
    _login_admin(client)

    record = blockchain.create_feedback(
        feedback_type="bug",
        title="Needs triage",
        description="Admin should be able to review this.",
    )
    blockchain.save_blockchain()

    patch_response = client.patch(
        f"/admin/feedback/{record['feedback_id']}",
        json={
            "status": "in_progress",
            "priority": "high",
            "reviewed_by": "operator",
        },
    )
    note_response = client.post(
        f"/admin/feedback/{record['feedback_id']}/note",
        json={
            "note": "Reproduced on MetaMask mobile.",
            "created_by": "operator",
        },
    )
    detail_response = client.get(f"/admin/feedback/{record['feedback_id']}")

    assert patch_response.status_code == 200
    assert patch_response.json()["feedback"]["status"] == "in_progress"
    assert patch_response.json()["feedback"]["priority"] == "high"
    assert note_response.status_code == 200
    assert len(note_response.json()["feedback"]["admin_notes"]) == 1
    assert detail_response.status_code == 200
    assert detail_response.json()["feedback"]["admin_notes"][0]["note"] == "Reproduced on MetaMask mobile."


def test_admin_feedback_actions_are_audited_and_ops_summary_updates(blockchain, monkeypatch):
    _configure_admin(monkeypatch)
    client = _client(blockchain)
    _login_admin(client)

    record = blockchain.create_feedback(
        feedback_type="mobile_issue",
        title="Phone layout issue",
        description="The page jumps when the keyboard opens.",
        priority="urgent",
    )
    blockchain.save_blockchain()

    status_response = client.post(
        f"/admin/feedback/{record['feedback_id']}/status",
        json={
            "status": "reviewed",
            "reviewed_by": "operator",
        },
    )
    ops_response = client.get("/admin/ops/status")
    audit_response = client.get("/admin/audit-log", params={"limit": 20})

    assert status_response.status_code == 200
    assert ops_response.status_code == 200
    ops_payload = ops_response.json()
    assert ops_payload["feedback_summary"]["open_feedback_count"] >= 1
    assert ops_payload["metrics"]["high_priority_feedback_count"] >= 1

    actions = [entry["action"] for entry in audit_response.json()["audit_log"]]
    assert "feedback_status_changed" in actions
    assert "feedback_viewed" not in actions  # detail endpoint was not called here


def test_cleared_feedback_is_excluded_from_active_list_and_remains_retrievable(blockchain, monkeypatch):
    _configure_admin(monkeypatch)
    client = _client(blockchain)
    _login_admin(client)

    active_record = blockchain.create_feedback(
        feedback_type="bug",
        title="Still active",
        description="Needs review",
    )
    resolved_record = blockchain.create_feedback(
        feedback_type="other",
        title="Already resolved",
        description="Should stay in history",
        priority="low",
    )
    blockchain.update_feedback(resolved_record["feedback_id"], status="resolved", reviewed_by="operator")
    blockchain.save_blockchain()

    active_list = client.get("/admin/feedback", params={"status": "active"})
    resolved_list = client.get("/admin/feedback", params={"status": "resolved"})
    all_feedback = client.get("/admin/feedback")

    assert active_list.status_code == 200
    assert [item["feedback_id"] for item in active_list.json()["feedback_items"]] == [active_record["feedback_id"]]
    assert resolved_list.status_code == 200
    assert [item["feedback_id"] for item in resolved_list.json()["feedback_items"]] == [resolved_record["feedback_id"]]
    assert all_feedback.status_code == 200
    assert {item["feedback_id"] for item in all_feedback.json()["feedback_items"]} == {
        active_record["feedback_id"],
        resolved_record["feedback_id"],
    }


def test_admin_can_resolve_feedback_and_audit_log_keeps_history(blockchain, monkeypatch):
    _configure_admin(monkeypatch)
    client = _client(blockchain)
    _login_admin(client)

    record = blockchain.create_feedback(
        feedback_type="submission_upload_issue",
        title="Submission wizard blocked",
        description="Resolve this without deleting it.",
    )
    blockchain.save_blockchain()

    resolve_response = client.patch(
        f"/admin/feedback/{record['feedback_id']}",
        json={
            "status": "resolved",
            "reviewed_by": "operator",
        },
    )
    active_list = client.get("/admin/feedback", params={"status": "active"})
    detail_response = client.get(f"/admin/feedback/{record['feedback_id']}")
    audit_response = client.get("/admin/audit-log", params={"limit": 20})

    assert resolve_response.status_code == 200
    assert resolve_response.json()["feedback"]["status"] == "resolved"
    assert detail_response.status_code == 200
    assert detail_response.json()["feedback"]["status"] == "resolved"
    assert [item["feedback_id"] for item in active_list.json()["feedback_items"]] == []
    matching_entries = [
        entry for entry in audit_response.json()["audit_log"]
        if entry.get("feedback_id") == record["feedback_id"] and entry.get("action") == "feedback_status_changed"
    ]
    assert matching_entries


def test_feedback_apis_do_not_expose_secrets(blockchain, monkeypatch):
    _configure_admin(monkeypatch, ADMIN_BOOTSTRAP_TOKEN="super-secret-bootstrap")
    _configure_access(monkeypatch)
    client = _client(blockchain)
    _login_admin(client)

    response = client.post(
        "/feedback",
        json={
            "type": "other",
            "title": "Secret safety check",
            "description": "Make sure tokens never leak back out.",
            "eligibility_snapshot": {
                "access_granted": False,
                "session_token": "should-not-survive",
            },
        },
    )
    feedback_id = response.json()["feedback"]["feedback_id"]
    admin_list = client.get("/admin/feedback")
    admin_detail = client.get(f"/admin/feedback/{feedback_id}")

    assert response.status_code == 200
    serialized = f"{response.json()} {admin_list.json()} {admin_detail.json()}"
    assert "super-secret-bootstrap" not in serialized
    assert "should-not-survive" not in serialized
    assert "invite_code_hash" not in serialized
    assert "session_token" not in serialized
