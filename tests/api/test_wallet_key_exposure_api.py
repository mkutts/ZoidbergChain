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


def _set_security_mode(monkeypatch, environment, allow_export=False, public_api_mode=False):
    import api

    monkeypatch.setattr(api, "is_development", lambda: environment == "development")
    monkeypatch.setattr(api, "is_production", lambda: environment == "production")
    monkeypatch.setattr(api, "allow_private_key_export", lambda: allow_export)
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
    assert "Development-only private key export" in body["warning"]
    assert body["wallets"]
    assert all("private_key" in wallet for wallet in body["wallets"])
    assert {
        wallet["private_key"] for wallet in body["wallets"]
    } == {
        wallet.private_key for wallet in blockchain.wallets.values()
    }


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
