from fastapi.testclient import TestClient

import api
from admin_auth import AdminSessionManager, hash_admin_password
from access_control import AccessSessionManager
from wallet_auth import WalletAuthManager


def _client(blockchain):
    api.limiter.reset()
    api.blockchain = blockchain
    api.wallet_auth_manager = WalletAuthManager(
        network_name=api.NETWORK_NAME,
        environment=api.ENVIRONMENT,
    )
    api.access_session_manager = AccessSessionManager()
    api.admin_session_manager = AdminSessionManager(session_ttl_seconds=api.ADMIN_SESSION_TTL_SECONDS)
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

    for name, value in defaults.items():
        monkeypatch.setattr(config, name, value)
        monkeypatch.setattr(api, name, value)

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

    for name, value in defaults.items():
        monkeypatch.setattr(config, name, value)
        monkeypatch.setattr(api, name, value)


def _login_admin(client, password="super-secret-admin"):
    response = client.post("/admin/login", json={"password": password})
    assert response.status_code == 200
    return response


def test_unauthenticated_admin_endpoints_return_401_and_invalid_login_fails(blockchain, monkeypatch):
    _configure_admin(monkeypatch)
    client = _client(blockchain)

    list_response = client.get("/admin/access/requests")
    allowlist_response = client.get("/admin/allowlist")
    override_response = client.get("/admin/override-requests")
    approve_response = client.post(
        "/admin/access/requests/example-request/approve",
        json={"reviewed_by": "operator", "operator_notes": "", "max_wallets": 1},
    )
    invalid_login = client.post("/admin/login", json={"password": "wrong-password"})

    assert list_response.status_code == 401
    assert allowlist_response.status_code == 401
    assert override_response.status_code == 401
    assert approve_response.status_code == 401
    assert invalid_login.status_code == 401


def test_admin_login_session_and_logout_flow(blockchain, monkeypatch):
    _configure_admin(monkeypatch)
    client = _client(blockchain)

    login = _login_admin(client)
    session_after_login = client.get("/admin/session")
    logout = client.post("/admin/logout")
    session_after_logout = client.get("/admin/session")

    assert login.json()["authenticated"] is True
    assert session_after_login.status_code == 200
    assert session_after_login.json()["authenticated"] is True
    assert logout.status_code == 200
    assert session_after_logout.json()["authenticated"] is False


def test_pending_requests_are_admin_only_and_approve_returns_one_time_invite_code(blockchain, monkeypatch):
    _configure_admin(monkeypatch)
    _configure_access(monkeypatch)
    client = _client(blockchain)

    request_record = blockchain.create_access_request(
        name="Pending Tester",
        email="pending@example.test",
        reason="Need access",
        notes="From browser",
    )
    blockchain.save_blockchain()

    assert client.get("/admin/access/requests").status_code == 401

    _login_admin(client)
    listed = client.get("/admin/access/requests?status=pending")
    approve = client.post(
        f"/admin/access/requests/{request_record['request_id']}/approve",
        json={"reviewed_by": "operator", "operator_notes": "Approved from UI", "max_wallets": 1},
    )

    assert listed.status_code == 200
    assert listed.json()["requests"][0]["request_id"] == request_record["request_id"]
    assert approve.status_code == 200
    payload = approve.json()
    assert payload["invite_code"].startswith("ZC-")
    assert payload["warning"]
    assert payload["access_account"]["status"] == "active"


def test_admin_reject_request_and_create_invite_work(blockchain, monkeypatch):
    _configure_admin(monkeypatch)
    _configure_access(monkeypatch)
    client = _client(blockchain)
    _login_admin(client)

    request_record = blockchain.create_access_request(
        name="Reject Tester",
        email="reject@example.test",
        reason="No thanks",
    )
    blockchain.save_blockchain()

    reject = client.post(
        f"/admin/access/requests/{request_record['request_id']}/reject",
        json={"reviewed_by": "operator", "operator_notes": "Not recognized"},
    )
    create_invite = client.post(
        "/admin/access/invites",
        json={
            "name": "Direct Invite",
            "email": "direct@example.test",
            "handle": "@direct",
            "notes": "Known tester",
            "reviewed_by": "operator",
            "operator_notes": "Invited directly",
            "max_wallets": 1,
        },
    )

    assert reject.status_code == 200
    assert reject.json()["request"]["status"] == "rejected"
    assert create_invite.status_code == 200
    invite_payload = create_invite.json()
    assert invite_payload["invite_code"].startswith("ZC-")
    assert invite_payload["access_account"]["email"] == "direct@example.test"


def test_admin_account_lists_do_not_expose_invite_hashes_or_admin_secrets(blockchain, monkeypatch):
    _configure_admin(monkeypatch, ADMIN_BOOTSTRAP_TOKEN="bootstrap-token-value")
    client = _client(blockchain)
    _login_admin(client)

    account, _invite_code = blockchain.create_access_invite(
        name="List Tester",
        email="list@example.test",
        reviewed_by="operator",
    )
    blockchain.save_blockchain()

    accounts = client.get("/admin/access/accounts")
    detail = client.get(f"/admin/access/accounts/{account['access_account_id']}")

    assert accounts.status_code == 200
    assert detail.status_code == 200
    serialized = f"{accounts.json()} {detail.json()}"
    assert "invite_code_hash" not in serialized
    assert "redeemed_invite_code_hash" not in serialized
    assert "super-secret-admin" not in serialized
    assert "bootstrap-token-value" not in serialized


def test_admin_can_suspend_reactivate_revoke_accounts_and_revoke_wallet_binding(blockchain, monkeypatch):
    _configure_admin(monkeypatch)
    client = _client(blockchain)
    _login_admin(client)

    account, _invite_code = blockchain.create_access_invite(
        name="Status Tester",
        email="status@example.test",
        reviewed_by="operator",
    )
    binding = blockchain.bind_wallet_to_access_account(
        account["access_account_id"],
        "0x1111111111111111111111111111111111111111",
    )
    blockchain.save_blockchain()

    suspend = client.post(f"/admin/access/accounts/{account['access_account_id']}/suspend")
    reactivate = client.post(f"/admin/access/accounts/{account['access_account_id']}/reactivate")
    revoke_account = client.post(f"/admin/access/accounts/{account['access_account_id']}/revoke")
    revoke_wallet = client.post(f"/admin/access/wallet-bindings/{binding['wallet_address']}/revoke")

    assert suspend.status_code == 200
    assert suspend.json()["access_account"]["status"] == "suspended"
    assert reactivate.status_code == 200
    assert reactivate.json()["access_account"]["status"] == "active"
    assert revoke_account.status_code == 200
    assert revoke_account.json()["access_account"]["status"] == "revoked"
    assert revoke_wallet.status_code == 200
    assert revoke_wallet.json()["wallet_binding"]["status"] == "revoked"


def test_admin_can_create_revoke_and_reactivate_allowlist_entries(blockchain, monkeypatch):
    _configure_admin(monkeypatch)
    client = _client(blockchain)
    _login_admin(client)

    create_response = client.post(
        "/admin/allowlist",
        json={
            "scope": "access",
            "subject_type": "wallet",
            "subject_value": "0x1111111111111111111111111111111111111111",
            "reason": "Known beta wallet",
        },
    )
    assert create_response.status_code == 200
    entry = create_response.json()["allowlist_entry"]
    assert entry["status"] == "active"

    revoke_response = client.post(
        f"/admin/allowlist/{entry['allowlist_entry_id']}/revoke",
        json={"revoked_reason": "Temporary hold"},
    )
    reactivate_response = client.post(
        f"/admin/allowlist/{entry['allowlist_entry_id']}/reactivate",
        json={"reason": "Reapproved"},
    )
    list_response = client.get("/admin/allowlist", params={"scope": "access", "status": "active"})

    assert revoke_response.status_code == 200
    assert revoke_response.json()["allowlist_entry"]["status"] == "revoked"
    assert reactivate_response.status_code == 200
    assert reactivate_response.json()["allowlist_entry"]["status"] == "active"
    assert list_response.status_code == 200
    assert list_response.json()["allowlist_entries"]


def test_admin_can_approve_and_reject_override_requests(blockchain, monkeypatch):
    _configure_admin(monkeypatch)
    client = _client(blockchain)
    _login_admin(client)

    first_request = blockchain.create_override_request(
        requested_scope="review",
        email="override-approve@example.test",
        wallet_address="0x1111111111111111111111111111111111111111",
        reason="Need voting override",
    )
    second_request = blockchain.create_override_request(
        requested_scope="access",
        email="override-reject@example.test",
        reason="Need access override",
    )
    blockchain.save_blockchain()

    approve = client.post(
        f"/admin/override-requests/{first_request['override_request_id']}/approve",
        json={
            "reviewed_by": "operator",
            "admin_note": "Approved for early beta review testing",
            "resolved_scope": "voting",
        },
    )
    reject = client.post(
        f"/admin/override-requests/{second_request['override_request_id']}/reject",
        json={
            "reviewed_by": "operator",
            "admin_note": "Rejected pending identity confirmation",
            "resolved_scope": "access",
        },
    )

    assert approve.status_code == 200
    approve_payload = approve.json()
    assert approve_payload["override_request"]["status"] == "approved"
    assert approve_payload["allowlist_entry"]["scope"] == "voting"

    assert reject.status_code == 200
    reject_payload = reject.json()
    assert reject_payload["override_request"]["status"] == "rejected"

    audit_log = client.get("/admin/audit-log", params={"limit": 20})
    assert audit_log.status_code == 200
    actions = [entry["action"] for entry in audit_log.json()["audit_log"]]
    assert "override_request_approved" in actions
    assert "override_request_rejected" in actions
    assert "allowlist_entry_created" in actions


def test_public_access_endpoints_still_do_not_expose_admin_or_invite_secrets(blockchain, monkeypatch):
    _configure_admin(monkeypatch, ADMIN_BOOTSTRAP_TOKEN="bootstrap-token-value")
    _configure_access(monkeypatch)
    client = _client(blockchain)

    status_response = client.get("/access/status")
    me_response = client.get("/access/me")

    assert status_response.status_code == 200
    assert me_response.status_code == 200
    serialized = f"{status_response.json()} {me_response.json()}"
    assert "ADMIN_PASSWORD_HASH" not in serialized
    assert "bootstrap-token-value" not in serialized
    assert "invite_code_hash" not in serialized
