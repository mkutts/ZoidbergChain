from fastapi.testclient import TestClient

import api
import config
from access_control import AccessSessionManager
from admin_auth import AdminSessionManager, hash_admin_password
from ops_support import safe_backup_status, safe_environment_validation, verify_backup_status
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

    for name, value in defaults.items():
        monkeypatch.setattr(config, name, value)
        monkeypatch.setattr(api, name, value)

    api.admin_session_manager = AdminSessionManager(session_ttl_seconds=api.ADMIN_SESSION_TTL_SECONDS)


def _configure_ops_mode(monkeypatch, **overrides):
    defaults = {
        "ENVIRONMENT": "testnet",
        "NETWORK_NAME": "zoidberg-testnet",
        "NODE_ID": "zoidberg-node-1",
        "PUBLIC_DEMO_MODE": True,
        "ACCESS_CONTROL_MODE": "invite_only",
        "ACCESS_DEV_BYPASS_ENABLED": False,
        "ADMIN_UI_ENABLED": True,
        "ADMIN_AUTH_ENABLED": True,
        "ADMIN_PASSWORD_HASH": hash_admin_password("super-secret-admin"),
        "ADMIN_BOOTSTRAP_TOKEN": "",
        "MAX_CONTENT_FILE_SIZE_BYTES": 5 * 1024 * 1024,
        "REQUIRE_PEER_AUTH": True,
        "ENABLE_SIGNED_PEER_MESSAGES": True,
        "CORS_ALLOWED_ORIGINS": ("https://zoidbergcoin.com",),
    }
    defaults.update(overrides)

    for name, value in defaults.items():
        monkeypatch.setattr(config, name, value)
        if hasattr(api, name):
            monkeypatch.setattr(api, name, value)

    monkeypatch.setattr(config, "public_demo_mode_enabled", lambda: bool(config.PUBLIC_DEMO_MODE))
    monkeypatch.setattr(api, "public_demo_mode_enabled", lambda: bool(config.PUBLIC_DEMO_MODE))
    monkeypatch.setattr(config, "cors_allowed_origins", lambda: list(config.CORS_ALLOWED_ORIGINS))
    monkeypatch.setattr(api, "cors_allowed_origins", lambda: list(config.CORS_ALLOWED_ORIGINS))
    monkeypatch.setattr(config, "require_peer_auth", lambda: bool(config.REQUIRE_PEER_AUTH))
    monkeypatch.setattr(config, "signed_peer_messages_enabled", lambda: bool(config.ENABLE_SIGNED_PEER_MESSAGES))
    monkeypatch.setattr(config, "peer_auth_required", lambda: bool(config.REQUIRE_PEER_AUTH))
    monkeypatch.setattr(api, "require_peer_auth", lambda: bool(config.REQUIRE_PEER_AUTH))
    monkeypatch.setattr(api, "signed_peer_messages_enabled", lambda: bool(config.ENABLE_SIGNED_PEER_MESSAGES))
    monkeypatch.setattr(api, "peer_auth_required", lambda: bool(config.REQUIRE_PEER_AUTH))


def _login_admin(client, password="super-secret-admin"):
    response = client.post("/admin/login", json={"password": password})
    assert response.status_code == 200
    return response


def test_public_status_endpoints_return_safe_operational_metadata(blockchain, monkeypatch):
    _configure_ops_mode(monkeypatch)
    _configure_admin(monkeypatch, ADMIN_BOOTSTRAP_TOKEN="super-secret-bootstrap")
    monkeypatch.setenv("PEER_SHARED_SECRET", "super-secret-peer")
    client = _client(blockchain)

    responses = [
        client.get("/health"),
        client.get("/status"),
        client.get("/ops/status"),
    ]

    for response in responses:
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["environment"] == "testnet"
        assert payload["network_name"] == "zoidberg-testnet"
        assert "storage_backend" in payload
        assert "chain_height" in payload
        serialized = str(payload)
        assert "super-secret-bootstrap" not in serialized
        assert "super-secret-peer" not in serialized
        assert "ADMIN_PASSWORD_HASH" not in serialized

    status_payload = responses[1].json()
    assert status_payload["environment_validation"]["warning_count"] >= 0
    assert "latest_block" in status_payload


def test_admin_ops_and_audit_log_require_admin_auth(blockchain, monkeypatch):
    _configure_admin(monkeypatch)
    client = _client(blockchain)

    ops_response = client.get("/admin/ops/status")
    audit_response = client.get("/admin/audit-log")

    assert ops_response.status_code == 401
    assert audit_response.status_code == 401


def test_admin_actions_write_audit_entries_without_logging_passwords(blockchain, monkeypatch):
    _configure_admin(monkeypatch)
    client = _client(blockchain)

    request_record = blockchain.create_access_request(
        name="Ops Tester",
        email="ops@example.test",
        reason="Need testnet access",
    )
    blockchain.save_blockchain()

    invalid_login = client.post("/admin/login", json={"password": "wrong-password"})
    assert invalid_login.status_code == 401

    _login_admin(client)
    approve = client.post(
        f"/admin/access/requests/{request_record['request_id']}/approve",
        json={"reviewed_by": "operator", "operator_notes": "Approved for ops QA", "max_wallets": 1},
    )
    ops_status = client.get("/admin/ops/status")
    audit_log = client.get("/admin/audit-log", params={"limit": 20})

    assert approve.status_code == 200
    assert ops_status.status_code == 200
    assert audit_log.status_code == 200

    actions = [entry["action"] for entry in audit_log.json()["audit_log"]]
    assert "admin_login_failure" in actions
    assert "admin_login_success" in actions
    assert "access_request_approved" in actions
    assert "admin_ops_viewed" in actions

    serialized = str(audit_log.json())
    assert "wrong-password" not in serialized
    assert "super-secret-admin" not in serialized


def test_admin_audit_log_supports_action_filter(blockchain, monkeypatch):
    _configure_admin(monkeypatch)
    client = _client(blockchain)

    _login_admin(client)
    client.get("/admin/ops/status")

    response = client.get("/admin/audit-log", params={"action": "admin_ops_viewed", "limit": 5})

    assert response.status_code == 200
    entries = response.json()["audit_log"]
    assert entries
    assert all(entry["action"] == "admin_ops_viewed" for entry in entries)


def test_environment_validation_flags_unsafe_testnet_settings(monkeypatch):
    _configure_ops_mode(
        monkeypatch,
        ACCESS_CONTROL_MODE="open",
        ACCESS_DEV_BYPASS_ENABLED=True,
        ADMIN_PASSWORD_HASH="",
        REQUIRE_PEER_AUTH=True,
        ENABLE_SIGNED_PEER_MESSAGES=True,
        PUBLIC_DEMO_MODE=False,
        MAX_CONTENT_FILE_SIZE_BYTES=30 * 1024 * 1024,
        CORS_ALLOWED_ORIGINS=("https://zoidbergcoin.com",),
    )
    monkeypatch.setenv("PEER_SHARED_SECRET", "change-me")
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://admin.example.test")

    validation = safe_environment_validation()
    failed_codes = {check["code"] for check in validation["checks"] if not check["ok"]}

    assert validation["healthy"] is False
    assert "restricted_access_mode" in failed_codes
    assert "dev_bypass_disabled" in failed_codes
    assert "admin_auth_configured" in failed_codes
    assert "peer_secret_configured" in failed_codes
    assert "frontend_origin_in_cors" in failed_codes
    assert "public_demo_mode" in failed_codes
    assert "upload_limit_reasonable" in failed_codes


def test_backup_helpers_report_safe_status_without_exposing_secrets(blockchain, monkeypatch):
    _configure_ops_mode(monkeypatch)
    _configure_admin(monkeypatch, ADMIN_BOOTSTRAP_TOKEN="super-secret-bootstrap")
    monkeypatch.setenv("PEER_SHARED_SECRET", "super-secret-peer")

    backup_status = safe_backup_status(blockchain.storage)
    verify_status = verify_backup_status(blockchain.storage)
    serialized = f"{backup_status} {verify_status}"

    assert backup_status["backup_count"] >= 0
    assert verify_status["verified"] is False
    assert "super-secret-bootstrap" not in serialized
    assert "super-secret-peer" not in serialized
