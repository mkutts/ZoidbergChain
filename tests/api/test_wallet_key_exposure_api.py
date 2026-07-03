from fastapi.testclient import TestClient


SENSITIVE_FIELD_NAMES = {
    "privatekey",
    "signingkey",
    "seed",
    "secret",
    "rawsecret",
    "encryptedprivatekey",
}


def _client(blockchain):
    import api

    api.blockchain = blockchain
    return TestClient(api.app)


def _set_security_mode(
    monkeypatch,
    environment,
    allow_export=False,
    public_api_mode=False,
    allow_reset=None,
):
    import api

    reset_enabled = environment == "development" if allow_reset is None else allow_reset
    monkeypatch.setattr(api, "is_development", lambda: environment == "development")
    monkeypatch.setattr(api, "is_production", lambda: environment == "production")
    monkeypatch.setattr(api, "allow_private_key_export", lambda: allow_export)
    monkeypatch.setattr(api, "allow_dev_reset_endpoints", lambda: reset_enabled)
    monkeypatch.setattr(api, "public_api_mode_enabled", lambda: public_api_mode)


def _assert_no_sensitive_fields(payload):
    if isinstance(payload, dict):
        for key, value in payload.items():
            normalized_key = key.replace("_", "").replace("-", "").lower()
            assert normalized_key not in SENSITIVE_FIELD_NAMES
            _assert_no_sensitive_fields(value)
    elif isinstance(payload, list):
        for item in payload:
            _assert_no_sensitive_fields(item)


def test_get_wallets_does_not_expose_private_key_in_development(blockchain, monkeypatch):
    _set_security_mode(monkeypatch, "development", allow_export=True)
    client = _client(blockchain)

    response = client.get("/get_wallets")

    assert response.status_code == 200
    body = response.json()
    assert body["wallets"]
    _assert_no_sensitive_fields(body)
    assert set(body["wallets"][0].keys()) == {"public_key", "balance"}


def test_get_wallets_does_not_expose_private_key_in_testnet(blockchain, monkeypatch):
    _set_security_mode(monkeypatch, "testnet", allow_export=False, public_api_mode=True)
    client = _client(blockchain)

    response = client.get("/get_wallets")

    assert response.status_code == 200
    _assert_no_sensitive_fields(response.json())


def test_get_wallets_does_not_expose_private_key_in_production(blockchain, monkeypatch):
    _set_security_mode(monkeypatch, "production", allow_export=False, public_api_mode=True)
    client = _client(blockchain)

    response = client.get("/get_wallets")

    assert response.status_code == 200
    _assert_no_sensitive_fields(response.json())


def test_wallet_creation_does_not_expose_private_key_in_testnet(blockchain, monkeypatch):
    _set_security_mode(monkeypatch, "testnet", allow_export=False, public_api_mode=True)
    client = _client(blockchain)

    response = client.post("/generate_wallet")

    assert response.status_code == 200
    body = response.json()
    _assert_no_sensitive_fields(body)
    assert body["wallet"].keys() == {"public_key", "balance"}
    assert body["key_export"]["enabled"] is False


def test_wallet_creation_does_not_expose_private_key_in_production(blockchain, monkeypatch):
    _set_security_mode(monkeypatch, "production", allow_export=False, public_api_mode=True)
    client = _client(blockchain)

    response = client.post("/generate_wallet")

    assert response.status_code == 200
    body = response.json()
    _assert_no_sensitive_fields(body)
    assert body["wallet"].keys() == {"public_key", "balance"}
    assert body["key_export"]["enabled"] is False


def test_dev_private_key_export_works_in_development_when_enabled(blockchain, monkeypatch):
    _set_security_mode(monkeypatch, "development", allow_export=True, public_api_mode=False)
    client = _client(blockchain)

    response = client.get("/dev/wallets")

    assert response.status_code == 200
    body = response.json()
    assert body["warning"] == "Development-only endpoint. Never expose this publicly."
    assert body["wallets"]
    assert all("private_key" in wallet for wallet in body["wallets"])
    assert {
        wallet["private_key"] for wallet in body["wallets"]
    } == {
        wallet.private_key for wallet in blockchain.wallets.values()
    }


def test_dev_private_key_export_is_blocked_in_development_when_flag_disabled(blockchain, monkeypatch):
    _set_security_mode(monkeypatch, "development", allow_export=False, public_api_mode=False)
    client = _client(blockchain)

    response = client.get("/dev/wallets")

    assert response.status_code == 403
    _assert_no_sensitive_fields(response.json())


def test_dev_private_key_export_is_blocked_in_testnet(blockchain, monkeypatch):
    _set_security_mode(monkeypatch, "testnet", allow_export=False, public_api_mode=True)
    client = _client(blockchain)

    response = client.get("/dev/wallets")

    assert response.status_code == 403
    assert "disabled" in response.json()["detail"]


def test_dev_private_key_export_is_blocked_in_production(blockchain, monkeypatch):
    _set_security_mode(monkeypatch, "production", allow_export=False, public_api_mode=True)
    client = _client(blockchain)

    response = client.get("/dev/wallets")

    assert response.status_code == 403
    assert "disabled" in response.json()["detail"]


def test_dev_private_key_export_is_blocked_when_public_api_mode_is_true(blockchain, monkeypatch):
    _set_security_mode(monkeypatch, "development", allow_export=True, public_api_mode=True)
    client = _client(blockchain)

    response = client.get("/dev/wallets")

    assert response.status_code == 403
    assert "disabled" in response.json()["detail"]


def test_public_api_mode_blocks_all_dev_endpoints(blockchain, monkeypatch):
    _set_security_mode(monkeypatch, "development", allow_export=True, public_api_mode=True)
    client = _client(blockchain)

    responses = [
        client.get("/dev/wallets"),
        client.post("/dev/reset"),
        client.get("/dev/debug"),
        client.post("/dev/submissions/missing/repair-certificate"),
    ]

    for response in responses:
        assert response.status_code == 403
        _assert_no_sensitive_fields(response.json())


def test_dev_reset_and_debug_work_in_development_when_enabled(blockchain, monkeypatch):
    _set_security_mode(monkeypatch, "development", allow_export=True, public_api_mode=False)
    client = _client(blockchain)

    debug_response = client.get("/dev/debug")
    reset_response = client.post("/dev/reset")

    assert debug_response.status_code == 200
    assert debug_response.json()["warning"] == "Development-only endpoint. Never expose this publicly."
    assert "wallet_count" in debug_response.json()
    _assert_no_sensitive_fields(debug_response.json())
    assert reset_response.status_code == 200
    assert reset_response.json()["warning"] == "Development-only endpoint. Never expose this publicly."
    _assert_no_sensitive_fields(reset_response.json())


def test_legacy_reset_route_is_guarded_and_points_to_dev_reset(blockchain, monkeypatch):
    _set_security_mode(monkeypatch, "development", allow_export=True, public_api_mode=False)
    client = _client(blockchain)

    response = client.post("/reset_blockchain")

    assert response.status_code == 200
    assert response.json()["deprecated_route"] is True
    assert response.json()["replacement"] == "/dev/reset"
    assert response.json()["warning"] == "Development-only endpoint. Never expose this publicly."
    _assert_no_sensitive_fields(response.json())


def test_dev_reset_and_debug_endpoints_blocked_in_testnet(blockchain, monkeypatch):
    _set_security_mode(monkeypatch, "testnet", allow_export=False, public_api_mode=True)
    client = _client(blockchain)

    responses = [
        client.post("/dev/reset"),
        client.get("/dev/debug"),
        client.post("/dev/submissions/missing/repair-certificate"),
        client.post("/reset_blockchain"),
    ]

    for response in responses:
        assert response.status_code == 403
        _assert_no_sensitive_fields(response.json())


def test_dev_reset_and_debug_endpoints_blocked_in_development_when_flag_disabled(blockchain, monkeypatch):
    _set_security_mode(
        monkeypatch,
        "development",
        allow_export=True,
        public_api_mode=False,
        allow_reset=False,
    )
    client = _client(blockchain)

    responses = [
        client.post("/dev/reset"),
        client.get("/dev/debug"),
        client.post("/dev/submissions/missing/repair-certificate"),
        client.post("/reset_blockchain"),
    ]

    for response in responses:
        assert response.status_code == 403
        _assert_no_sensitive_fields(response.json())


def test_dev_reset_and_debug_endpoints_blocked_in_production(blockchain, monkeypatch):
    _set_security_mode(monkeypatch, "production", allow_export=False, public_api_mode=True)
    client = _client(blockchain)

    responses = [
        client.post("/dev/reset"),
        client.get("/dev/debug"),
        client.post("/dev/submissions/missing/repair-certificate"),
        client.post("/reset_blockchain"),
    ]

    for response in responses:
        assert response.status_code == 403
        _assert_no_sensitive_fields(response.json())


def test_reusable_dev_guard_allows_and_blocks_correctly(monkeypatch):
    import pytest
    from fastapi import HTTPException
    import api

    _set_security_mode(monkeypatch, "development", allow_export=True, public_api_mode=False)
    api.require_development_mode(True, "Development test tools")

    _set_security_mode(monkeypatch, "development", allow_export=True, public_api_mode=True)
    with pytest.raises(HTTPException) as public_mode_error:
        api.require_development_mode(True, "Development test tools")
    assert public_mode_error.value.status_code == 403

    _set_security_mode(monkeypatch, "production", allow_export=False, public_api_mode=True)
    with pytest.raises(HTTPException) as production_error:
        api.require_development_mode(True, "Development test tools")
    assert production_error.value.status_code == 403

    _set_security_mode(monkeypatch, "development", allow_export=True, public_api_mode=False)
    with pytest.raises(HTTPException) as disabled_flag_error:
        api.require_development_mode(False, "Development test tools")
    assert disabled_flag_error.value.status_code == 403


def test_blocked_dev_responses_do_not_expose_sensitive_fields(blockchain, monkeypatch):
    _set_security_mode(monkeypatch, "production", allow_export=False, public_api_mode=True)
    client = _client(blockchain)

    responses = [
        client.get("/dev/wallets"),
        client.post("/dev/reset"),
        client.get("/dev/debug"),
        client.post("/dev/submissions/missing/repair-certificate"),
        client.post("/reset_blockchain"),
    ]

    for response in responses:
        assert response.status_code == 403
        _assert_no_sensitive_fields(response.json())


def test_wallet_api_responses_do_not_contain_sensitive_fields(blockchain, monkeypatch):
    _set_security_mode(monkeypatch, "development", allow_export=True, public_api_mode=False)
    client = _client(blockchain)
    public_key = next(iter(blockchain.wallets.keys()))

    responses = [
        client.get("/get_wallets"),
        client.post("/generate_wallet"),
        client.get("/get_balance", params={"public_key": public_key}),
    ]

    for response in responses:
        assert response.status_code == 200
        _assert_no_sensitive_fields(response.json())
