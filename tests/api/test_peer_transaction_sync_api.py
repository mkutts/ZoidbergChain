import importlib

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

import peer_sync
from blockchain import Blockchain
from native_transfer import (
    NativeTransferMessage,
    build_native_transaction,
    build_transfer_signing_message,
    hash_transfer_signing_message,
)
from peers import PeerStore
from protocol_v1 import PROTOCOL_VERSION
from protocol_v1_native_transfer import resolve_protocol_v1_network_id
from protocol_v1_peer_message import (
    build_protocol_v1_peer_request_headers,
    clear_protocol_v1_peer_replay_store_cache,
)
from test_support import fund_native_wallet_with_block
from wallet_auth import WalletAuthManager


def _client(blockchain):
    import config
    import api

    importlib.reload(config)
    api = importlib.reload(api)
    api.NODE_ID = "local-node"
    api.PUBLIC_NODE_URL = "http://localhost:8000"
    api.NETWORK_NAME = "zoidberg-testnet"
    api.blockchain = blockchain
    api.peer_store = PeerStore()
    api.wallet_auth_manager = WalletAuthManager(
        network_name=api.NETWORK_NAME,
        environment=api.ENVIRONMENT,
    )
    clear_protocol_v1_peer_replay_store_cache(data_dir=api.peer_store.storage.data_dir)
    return TestClient(api.app), api


def _sign_message(message, account):
    signed = Account.sign_message(encode_defunct(text=message), account.key)
    return signed.signature.hex()


def _fund_native_wallet(blockchain, wallet_address, amount="25"):
    fund_native_wallet_with_block(blockchain, wallet_address, amount=amount)


def _verified_headers(client, account):
    challenge = client.post("/auth/wallet/challenge", json={"wallet_address": account.address})
    verify = client.post(
        "/auth/wallet/verify",
        json={
            "wallet_address": account.address,
            "message": challenge.json()["message"],
            "signature": _sign_message(challenge.json()["message"], account),
        },
    )
    return {"Authorization": f"Bearer {verify.json()['session_token']}"}


def _submit_transfer_intent(client, account, headers, **overrides):
    challenge_payload = {
        "from_address": account.address,
        "to_address": overrides.get("to_address", Account.create().address),
        "amount": overrides.get("amount", "4"),
        "fee": overrides.get("fee", "0"),
        "memo": overrides.get("memo", "peer sync"),
    }
    challenge = client.post("/auth/wallet/transfer-challenge", json=challenge_payload, headers=headers).json()
    payload = {
        "from_address": account.address,
        "to_address": challenge["transfer_preview"]["to_address"],
        "amount": challenge["transfer_preview"]["amount"],
        "fee": challenge["transfer_preview"]["fee"],
        "memo": challenge_payload["memo"],
        "message": challenge["message"],
        "signature": _sign_message(challenge["message"], account),
        "admit_to_mempool": overrides.get("admit_to_mempool", False),
    }
    return client.post("/transfers/submit", json=payload, headers=headers)


def _register_peer(api_module, node_id="peer-node-1", url="http://peer-one.test:8000"):
    return api_module.peer_store.register_peer(
        node_id=node_id,
        url=url,
        network_name="zoidberg-testnet",
    )


def _configure_peer_auth(monkeypatch, enabled, secret="super-secret-value"):
    import api

    monkeypatch.setattr(api, "peer_auth_required", lambda: enabled)
    monkeypatch.setattr(api, "peer_shared_secret", lambda: secret)
    monkeypatch.setattr(api, "peer_shared_secret_is_configured", lambda: bool(secret))
    monkeypatch.setattr(api, "signed_peer_messages_enabled", lambda: False)
    monkeypatch.setattr(api, "peer_replay_protection_enabled", lambda: False)
    monkeypatch.setattr(peer_sync, "peer_auth_required", lambda: enabled)
    monkeypatch.setattr(peer_sync, "peer_shared_secret", lambda: secret)
    monkeypatch.setattr(peer_sync, "peer_shared_secret_is_configured", lambda: bool(secret))
    monkeypatch.setattr(peer_sync, "signed_peer_messages_enabled", lambda: False)
    monkeypatch.setattr(peer_sync, "peer_replay_protection_enabled", lambda: False)


def _configure_signed_peer_messages(monkeypatch, secret="super-secret-value"):
    import api

    monkeypatch.setattr(api, "signed_peer_messages_enabled", lambda: True)
    monkeypatch.setattr(api, "peer_auth_required", lambda: False)
    monkeypatch.setattr(api, "peer_shared_secret", lambda: secret)
    monkeypatch.setattr(api, "peer_shared_secret_is_configured", lambda: True)
    monkeypatch.setattr(api, "peer_replay_protection_enabled", lambda: False)
    monkeypatch.setattr(api, "PEER_SIGNATURE_WINDOW_SECONDS", 300)
    monkeypatch.setattr(peer_sync, "signed_peer_messages_enabled", lambda: True)
    monkeypatch.setattr(peer_sync, "peer_auth_required", lambda: False)
    monkeypatch.setattr(peer_sync, "peer_shared_secret", lambda: secret)
    monkeypatch.setattr(peer_sync, "peer_shared_secret_is_configured", lambda: True)
    monkeypatch.setattr(peer_sync, "peer_replay_protection_enabled", lambda: False)
    monkeypatch.setattr(peer_sync, "peer_signature_window_seconds", lambda: 300)
    peer_sync._PEER_NONCE_CACHE.clear()
    clear_protocol_v1_peer_replay_store_cache()


def _freeze_peer_time(monkeypatch, now=1_700_000_000):
    import api

    monkeypatch.setattr(api.time, "time", lambda: now)
    monkeypatch.setattr(peer_sync.time, "time", lambda: now)


def _signed_headers(path, payload, *, secret="super-secret-value", timestamp=1_700_000_000, nonce="nonce-1"):
    return build_protocol_v1_peer_request_headers(
        "POST",
        path,
        payload,
        "peer-node-1",
        network_name="zoidberg-testnet",
        secret=secret,
        timestamp=timestamp,
        nonce=nonce,
    )


def _build_signed_transaction(
    account,
    *,
    to_address=None,
    amount="4",
    fee="0",
    nonce="1",
    network="zoidberg-testnet",
    memo="peer tx",
    transaction_version=PROTOCOL_VERSION,
):
    to_address = (to_address or Account.create().address).lower()
    network_id = resolve_protocol_v1_network_id(network_name=network) if transaction_version == PROTOCOL_VERSION else None
    transfer_message = NativeTransferMessage(
        action="transfer_zoid",
        network=network,
        from_address=account.address.lower(),
        to_address=to_address,
        amount=amount,
        nonce=str(nonce),
        fee=fee,
        timestamp="2026-07-26T00:00:00+00:00",
        memo=memo,
        status="signed_pending",
        transaction_version=transaction_version,
        protocol_version=PROTOCOL_VERSION if transaction_version == PROTOCOL_VERSION else None,
        network_id=network_id,
    )
    signed_message = build_transfer_signing_message(transfer_message)
    signature = _sign_message(signed_message, account)
    transaction = build_native_transaction(
        network=network,
        transaction_version=transaction_version,
        protocol_version=PROTOCOL_VERSION if transaction_version == PROTOCOL_VERSION else None,
        network_id=network_id,
        from_address=transfer_message.from_address,
        to_address=transfer_message.to_address,
        amount=transfer_message.amount,
        fee=transfer_message.fee,
        nonce=transfer_message.nonce,
        memo=transfer_message.memo,
        timestamp=transfer_message.timestamp,
        signature=signature,
        signature_scheme="personal_sign",
        signed_message=signed_message,
        signed_message_hash=hash_transfer_signing_message(signed_message),
        status="signed_pending",
        created_at="2026-07-26T00:00:00+00:00",
        updated_at="2026-07-26T00:00:00+00:00",
    )
    return transaction.to_dict()


def _receive_payload(transaction, *, origin_node_id="peer-node-1", network_name="zoidberg-testnet"):
    return {
        "origin_node_id": origin_node_id,
        "network_name": network_name,
        "transaction": transaction,
    }


def test_receive_peer_transaction_accepts_valid_transaction_without_wallet_session(blockchain):
    client, api = _client(blockchain)
    _register_peer(api)
    account = Account.create()
    _fund_native_wallet(blockchain, account.address, "10")
    transaction = _build_signed_transaction(account, amount="4")

    response = client.post("/peers/transactions/receive", json=_receive_payload(transaction))

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert response.json()["status"] == "mempool"
    assert response.json()["duplicate"] is False
    stored = blockchain.get_mempool_transaction(transaction["tx_id"])
    assert stored is not None
    assert stored["transaction_version"] == 1
    assert stored["protocol_version"] == 1
    assert stored["network_id"] == resolve_protocol_v1_network_id(network_name="zoidberg-testnet")


def test_receive_peer_transaction_requires_peer_auth_when_enabled(blockchain, monkeypatch):
    client, api = _client(blockchain)
    _configure_peer_auth(monkeypatch, enabled=True)
    _register_peer(api)
    account = Account.create()
    _fund_native_wallet(blockchain, account.address, "10")
    transaction = _build_signed_transaction(account, amount="4")

    response = client.post("/peers/transactions/receive", json=_receive_payload(transaction))

    assert response.status_code == 401
    assert response.json()["detail"] == "Peer auth required. Missing shared secret."


def test_receive_peer_transaction_rejects_invalid_tx_id(blockchain):
    client, api = _client(blockchain)
    _register_peer(api)
    account = Account.create()
    _fund_native_wallet(blockchain, account.address, "10")
    transaction = _build_signed_transaction(account, amount="4")
    transaction["tx_id"] = "0" * 64

    response = client.post("/peers/transactions/receive", json=_receive_payload(transaction))

    assert response.status_code == 400
    assert response.json()["reason"] == "invalid_tx_id"


def test_receive_peer_transaction_rejects_wrong_network(blockchain):
    client, api = _client(blockchain)
    _register_peer(api)
    account = Account.create()
    _fund_native_wallet(blockchain, account.address, "10")
    transaction = _build_signed_transaction(account, amount="4", network="zoidberg-mainnet")

    response = client.post("/peers/transactions/receive", json=_receive_payload(transaction, network_name="zoidberg-mainnet"))

    assert response.status_code == 400
    assert response.json()["reason"] == "wrong_network"


def test_receive_peer_transaction_rejects_legacy_transaction_on_protocol_v1_network(blockchain):
    client, api = _client(blockchain)
    _register_peer(api)
    account = Account.create()
    _fund_native_wallet(blockchain, account.address, "10")
    transaction = _build_signed_transaction(account, amount="4", transaction_version=None)

    response = client.post("/peers/transactions/receive", json=_receive_payload(transaction))

    assert response.status_code == 400
    assert response.json()["reason"] == "unsupported_transaction_version"


def test_receive_peer_transaction_is_idempotent_for_duplicate_tx_id(blockchain):
    client, api = _client(blockchain)
    _register_peer(api)
    account = Account.create()
    _fund_native_wallet(blockchain, account.address, "10")
    transaction = _build_signed_transaction(account, amount="4")

    first = client.post("/peers/transactions/receive", json=_receive_payload(transaction))
    second = client.post("/peers/transactions/receive", json=_receive_payload(transaction))

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["accepted"] is True
    assert second.json()["duplicate"] is True


def test_receive_peer_transaction_rejects_conflicting_same_sender_nonce(blockchain):
    client, api = _client(blockchain)
    _register_peer(api)
    account = Account.create()
    _fund_native_wallet(blockchain, account.address, "10")
    first_transaction = _build_signed_transaction(account, amount="4", nonce="1", memo="first")
    second_transaction = _build_signed_transaction(account, amount="3", nonce="1", memo="second")

    first = client.post("/peers/transactions/receive", json=_receive_payload(first_transaction))
    second = client.post("/peers/transactions/receive", json=_receive_payload(second_transaction))

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["reason"] == "conflicting_nonce"
    assert client.get(f"/wallets/{account.address.lower()}/balance").json()["pending_outgoing"] == "4"
    assert client.get("/mempool").json()["count"] == 1


def test_receive_peer_transaction_rejects_invalid_signature_without_reserving_balance(blockchain):
    client, api = _client(blockchain)
    _register_peer(api)
    account = Account.create()
    _fund_native_wallet(blockchain, account.address, "10")
    transaction = _build_signed_transaction(account, amount="4")
    transaction["signature"] = _sign_message(transaction["signed_message"], Account.create())
    rebuilt = build_native_transaction(
        network=transaction["network"],
        transaction_version=transaction.get("transaction_version"),
        protocol_version=transaction.get("protocol_version"),
        network_id=transaction.get("network_id"),
        from_address=transaction["from_address"],
        to_address=transaction["to_address"],
        amount=transaction["amount"],
        fee=transaction["fee"],
        nonce=transaction["nonce"],
        memo=transaction["memo"],
        timestamp=transaction["timestamp"],
        signature=transaction["signature"],
        signature_scheme=transaction["signature_scheme"],
        signed_message=transaction["signed_message"],
        signed_message_hash=transaction["signed_message_hash"],
        status="signed_pending",
        created_at=transaction["created_at"],
        updated_at=transaction["updated_at"],
    ).to_dict()

    response = client.post("/peers/transactions/receive", json=_receive_payload(rebuilt))

    assert response.status_code == 400
    assert response.json()["reason"] == "invalid_signature"
    assert client.get(f"/wallets/{account.address.lower()}/balance").json()["pending_outgoing"] == "0"
    assert client.get("/mempool").json()["count"] == 0


def test_signed_peer_transaction_auth_does_not_bypass_inner_signature_validation(blockchain, monkeypatch):
    client, api = _client(blockchain)
    _configure_signed_peer_messages(monkeypatch)
    _freeze_peer_time(monkeypatch)
    _register_peer(api)
    account = Account.create()
    _fund_native_wallet(blockchain, account.address, "10")
    transaction = _build_signed_transaction(account, amount="4")
    transaction["signature"] = _sign_message(transaction["signed_message"], Account.create())
    rebuilt = build_native_transaction(
        network=transaction["network"],
        transaction_version=transaction.get("transaction_version"),
        protocol_version=transaction.get("protocol_version"),
        network_id=transaction.get("network_id"),
        from_address=transaction["from_address"],
        to_address=transaction["to_address"],
        amount=transaction["amount"],
        fee=transaction["fee"],
        nonce=transaction["nonce"],
        memo=transaction["memo"],
        timestamp=transaction["timestamp"],
        signature=transaction["signature"],
        signature_scheme=transaction["signature_scheme"],
        signed_message=transaction["signed_message"],
        signed_message_hash=transaction["signed_message_hash"],
        status="signed_pending",
        created_at=transaction["created_at"],
        updated_at=transaction["updated_at"],
    ).to_dict()
    payload = _receive_payload(rebuilt)

    response = client.post(
        "/peers/transactions/receive",
        json=payload,
        headers=_signed_headers(
            "/peers/transactions/receive",
            payload,
            nonce="signed-transaction-invalid-signature-1",
        ),
    )

    assert response.status_code == 400
    assert response.json()["reason"] == "invalid_signature"
    assert client.get(f"/wallets/{account.address.lower()}/balance").json()["pending_outgoing"] == "0"
    assert client.get("/mempool").json()["count"] == 0


def test_receive_peer_transaction_rejects_insufficient_available_balance(blockchain):
    client, api = _client(blockchain)
    _register_peer(api)
    account = Account.create()
    _fund_native_wallet(blockchain, account.address, "3")
    transaction = _build_signed_transaction(account, amount="4")

    response = client.post("/peers/transactions/receive", json=_receive_payload(transaction))

    assert response.status_code == 400
    assert response.json()["reason"] == "insufficient_available_balance"


def test_receive_peer_transaction_ignores_peer_local_only_fields(blockchain):
    client, api = _client(blockchain)
    _register_peer(api)
    account = Account.create()
    _fund_native_wallet(blockchain, account.address, "10")
    transaction = _build_signed_transaction(account, amount="4")
    transaction["status"] = "settled"
    transaction["admitted_at"] = "2000-01-01T00:00:00+00:00"
    transaction["rejection_reason"] = "peer_said_no"

    response = client.post("/peers/transactions/receive", json=_receive_payload(transaction))

    stored = blockchain.get_mempool_transaction(transaction["tx_id"])
    assert response.status_code == 200
    assert stored is not None
    assert stored["status"] == "mempool"
    assert stored["admitted_at"] != "2000-01-01T00:00:00+00:00"
    assert stored["rejection_reason"] is None


def test_broadcast_endpoint_admits_then_broadcasts_transaction(blockchain, monkeypatch):
    client, api = _client(blockchain)
    _register_peer(api, "peer-a", "http://peer-a.test")
    _register_peer(api, "peer-b", "http://peer-b.test")
    account = Account.create()
    _fund_native_wallet(blockchain, account.address, "10")
    headers = _verified_headers(client, account)
    submit = _submit_transfer_intent(client, account, headers, admit_to_mempool=False)
    tx_id = submit.json()["tx_id"]
    calls = []

    class FakeResponse:
        status_code = 200
        text = "ok"

        @staticmethod
        def json():
            return {"accepted": True, "status": "mempool", "duplicate": False}

    def fake_post(url, json, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(peer_sync.requests, "post", fake_post)

    response = client.post(f"/transactions/{tx_id}/broadcast")

    assert response.status_code == 200
    assert response.json()["peers_attempted"] == 2
    assert response.json()["peers_accepted"] == 2
    assert blockchain.get_mempool_transaction(tx_id) is not None
    assert len(calls) == 2


def test_broadcast_endpoint_does_not_rollback_local_mempool_on_peer_failure(blockchain, monkeypatch):
    client, api = _client(blockchain)
    _register_peer(api, "peer-up", "http://peer-up.test")
    _register_peer(api, "peer-down", "http://peer-down.test")
    account = Account.create()
    _fund_native_wallet(blockchain, account.address, "10")
    headers = _verified_headers(client, account)
    submit = _submit_transfer_intent(client, account, headers, admit_to_mempool=True)
    tx_id = submit.json()["tx_id"]

    class FakeResponse:
        status_code = 200
        text = "ok"

        @staticmethod
        def json():
            return {"accepted": True, "status": "mempool", "duplicate": False}

    def fake_post(url, json, headers=None, timeout=None):
        if "peer-down" in url:
            raise peer_sync.requests.RequestException("connection refused")
        return FakeResponse()

    monkeypatch.setattr(peer_sync.requests, "post", fake_post)

    response = client.post(f"/transactions/{tx_id}/broadcast")

    assert response.status_code == 200
    assert response.json()["peers_attempted"] == 2
    assert response.json()["peers_accepted"] == 1
    assert blockchain.get_mempool_transaction(tx_id) is not None


def test_broadcast_endpoint_returns_404_for_missing_transaction(blockchain):
    client, _ = _client(blockchain)

    response = client.post("/transactions/" + ("a" * 64) + "/broadcast")

    assert response.status_code == 404


def test_peer_transaction_fetch_and_mempool_summary_return_expected_data(blockchain):
    client, api = _client(blockchain)
    _register_peer(api)
    account = Account.create()
    _fund_native_wallet(blockchain, account.address, "10")
    transaction = _build_signed_transaction(account, amount="4")
    client.post("/peers/transactions/receive", json=_receive_payload(transaction))

    fetch_response = client.get(f"/peers/transactions/{transaction['tx_id']}")
    summary_response = client.get("/peers/mempool/summary")

    assert fetch_response.status_code == 200
    assert fetch_response.json()["transaction"]["tx_id"] == transaction["tx_id"]
    assert "private_key" not in str(fetch_response.json())
    assert "session_token" not in str(fetch_response.json())
    assert summary_response.status_code == 200
    assert summary_response.json()["count"] == 1
    assert summary_response.json()["tx_ids"] == [transaction["tx_id"]]


def test_sync_transaction_from_peer_fetches_and_admits_valid_transaction(blockchain, monkeypatch):
    client, api = _client(blockchain)
    peer = _register_peer(api)
    account = Account.create()
    _fund_native_wallet(blockchain, account.address, "10")
    transaction = _build_signed_transaction(account, amount="4")

    class FakeResponse:
        status_code = 200
        text = "ok"

        def json(self):
            return {"transaction": transaction, "network_name": "zoidberg-testnet"}

    monkeypatch.setattr(peer_sync.requests, "get", lambda *args, **kwargs: FakeResponse())

    result = peer_sync.sync_transaction_from_peer(
        blockchain,
        api.peer_store,
        peer,
        transaction["tx_id"],
        origin_node_id="local-node",
        network_name="zoidberg-testnet",
    )

    assert result["accepted"] is True
    assert blockchain.get_mempool_transaction(transaction["tx_id"]) is not None


def test_sync_transaction_from_peer_rejects_tampered_transaction(blockchain, monkeypatch):
    client, api = _client(blockchain)
    peer = _register_peer(api)
    account = Account.create()
    _fund_native_wallet(blockchain, account.address, "10")
    transaction = _build_signed_transaction(account, amount="4")
    transaction["tx_id"] = "0" * 64

    class FakeResponse:
        status_code = 200
        text = "ok"

        def json(self):
            return {"transaction": transaction, "network_name": "zoidberg-testnet"}

    monkeypatch.setattr(peer_sync.requests, "get", lambda *args, **kwargs: FakeResponse())

    with pytest.raises(peer_sync.MalformedTransactionError):
        peer_sync.sync_transaction_from_peer(
            blockchain,
            api.peer_store,
            peer,
            transaction["tx_id"],
            origin_node_id="local-node",
            network_name="zoidberg-testnet",
        )


def test_sync_mempool_from_peer_fetches_missing_transactions(blockchain, monkeypatch):
    client, api = _client(blockchain)
    peer = _register_peer(api)
    account = Account.create()
    _fund_native_wallet(blockchain, account.address, "10")
    transaction = _build_signed_transaction(account, amount="4")

    class SummaryResponse:
        status_code = 200
        text = "ok"

        @staticmethod
        def json():
            return {"tx_ids": [transaction["tx_id"]], "count": 1, "network_name": "zoidberg-testnet"}

    class TransactionResponse:
        status_code = 200
        text = "ok"

        @staticmethod
        def json():
            return {"transaction": transaction, "network_name": "zoidberg-testnet"}

    def fake_get(url, headers=None, timeout=None):
        if url.endswith("/peers/mempool/summary"):
            return SummaryResponse()
        return TransactionResponse()

    monkeypatch.setattr(peer_sync.requests, "get", fake_get)

    result = peer_sync.sync_mempool_from_peer(
        blockchain,
        api.peer_store,
        peer,
        origin_node_id="local-node",
        network_name="zoidberg-testnet",
    )

    assert result["count"] == 1
    assert result["fetched"] == 1
    assert blockchain.get_mempool_transaction(transaction["tx_id"]) is not None
