from fastapi.testclient import TestClient

from peers import PeerStore


def _client(blockchain):
    import api

    api.blockchain = blockchain
    api.peer_store = PeerStore()
    return TestClient(api.app)


def test_public_endpoint_error_responses_do_not_leak_internal_details(blockchain, wallets, monkeypatch):
    client = _client(blockchain)

    def boom(_public_key):
        raise RuntimeError("leaked path /tmp/zoidberg/private.key")

    monkeypatch.setattr(blockchain, "get_balance", boom)

    response = client.get(
        "/get_balance",
        params={"public_key": wallets["owner"].public_key},
    )

    assert response.status_code == 500
    assert response.json() == {"error": "Internal Server Error"}


def test_request_logging_does_not_include_query_string_secrets(blockchain, wallets, monkeypatch):
    import api

    client = _client(blockchain)
    private_key = wallets["owner"].private_key
    logged_messages = []

    monkeypatch.setattr(api.logging, "info", lambda message: logged_messages.append(message))

    response = client.post(
        "/add_transaction",
        params={
            "sender": wallets["owner"].public_key,
            "recipient": wallets["contributor_one"].public_key,
            "amount": "1",
            "private_key": private_key,
        },
    )

    assert response.status_code == 200
    assert logged_messages
    assert any("/add_transaction" in message for message in logged_messages)
    assert all(private_key not in message for message in logged_messages)
    assert all("private_key=" not in message for message in logged_messages)
