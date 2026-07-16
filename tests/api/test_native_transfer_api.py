import importlib

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

from blockchain import Blockchain
from storage import JSONStorageBackend, SQLiteStorageBackend
from wallet import Wallet
from wallet_auth import WalletAuthManager


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


def _json_backend(base_dir, name="node"):
    node_dir = base_dir / name
    return JSONStorageBackend(
        blockchain_file=str(node_dir / "blockchain.json"),
        peers_file=str(node_dir / "peers.json"),
    )


def _sqlite_backend(base_dir, name="node"):
    node_dir = base_dir / name
    return SQLiteStorageBackend(sqlite_db_path=str(node_dir / "zoidbergchain.db"))


def _create_blockchain_with_backend(backend):
    owner = Wallet()
    contributor_one = Wallet()
    contributor_two = Wallet()
    return Blockchain(
        project_owner_wallet=owner,
        Contributor_one=contributor_one,
        Contributor_two=contributor_two,
        storage_backend=backend,
    )


def _create_account():
    return Account.create()


def _sign_message(message, account):
    signed = Account.sign_message(encode_defunct(text=message), account.key)
    return signed.signature.hex()


def _verified_headers(client, account):
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


def _request_transfer_challenge(client, account, headers, **overrides):
    payload = {
        "from_address": account.address,
        "to_address": _create_account().address,
        "amount": "10",
        "fee": "0",
        "memo": "preview",
    }
    payload.update(overrides)
    response = client.post("/auth/wallet/transfer-challenge", json=payload, headers=headers)
    return response


def _submit_transfer_intent(client, account, headers, **overrides):
    challenge_response = _request_transfer_challenge(client, account, headers)
    assert challenge_response.status_code == 200
    challenge = challenge_response.json()
    payload = {
        "from_address": account.address,
        "to_address": challenge["transfer_preview"]["to_address"],
        "amount": challenge["transfer_preview"]["amount"],
        "fee": challenge["transfer_preview"]["fee"],
        "memo": "preview",
        "message": challenge["message"],
        "signature": _sign_message(challenge["message"], account),
    }
    payload.update(overrides)
    response = client.post("/transfers/submit", json=payload, headers=headers)
    return response


def test_verified_session_can_request_transfer_challenge(blockchain):
    client, manager = _client(blockchain)
    account = _create_account()
    headers = _verified_headers(client, account)

    response = _request_transfer_challenge(client, account, headers)

    assert response.status_code == 200
    body = response.json()
    assert body["from_address"] == account.address.lower()
    assert body["transfer_preview"]["network"] == manager.network_name
    assert "ZoidbergChain Native Transfer" in body["message"]
    assert "not an Ethereum/ERC-20 transfer" in body["message"]


def test_transfer_challenge_requires_verified_session(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()

    response = _request_transfer_challenge(client, account, headers={})

    assert response.status_code == 401


def test_transfer_challenge_rejects_from_address_mismatch(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()
    headers = _verified_headers(client, account)

    response = _request_transfer_challenge(
        client,
        account,
        headers,
        from_address=_create_account().address,
    )

    assert response.status_code == 403
    assert "from_address must match" in response.json()["detail"].lower()


@pytest.mark.parametrize(
    ("overrides", "expected_error"),
    [
        ({"to_address": "bad-wallet"}, "to_address"),
        ({"amount": "0"}, "greater than zero"),
        ({"amount": "-1"}, "negative"),
        ({"fee": "-1"}, "negative"),
        ({"memo": "x" * 281}, "string should have at most"),
    ],
)
def test_transfer_challenge_validation_errors(blockchain, overrides, expected_error):
    client, _ = _client(blockchain)
    account = _create_account()
    headers = _verified_headers(client, account)

    response = _request_transfer_challenge(client, account, headers, **overrides)

    assert response.status_code in {400, 422}
    assert expected_error.lower() in str(response.json()).lower()


def test_valid_signed_transfer_intent_succeeds_and_is_non_final(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()
    headers = _verified_headers(client, account)
    starting_balance = blockchain.get_native_balance(account.address.lower())

    response = _submit_transfer_intent(client, account, headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "signed_pending"
    assert body["settlement_state"] == "non_final"
    assert "not active" in body["message"].lower()
    assert blockchain.get_native_balance(account.address.lower()) == starting_balance


def test_transfer_submit_rejects_wrong_wallet_signature(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()
    wrong_account = _create_account()
    headers = _verified_headers(client, account)
    challenge_response = _request_transfer_challenge(client, account, headers)
    challenge = challenge_response.json()

    response = client.post(
        "/transfers/submit",
        json={
            "from_address": account.address,
            "to_address": challenge["transfer_preview"]["to_address"],
            "amount": challenge["transfer_preview"]["amount"],
            "fee": challenge["transfer_preview"]["fee"],
            "memo": "preview",
            "message": challenge["message"],
            "signature": _sign_message(challenge["message"], wrong_account),
        },
        headers=headers,
    )

    assert response.status_code == 400
    assert "does not match" in response.json()["detail"].lower()


def test_transfer_submit_rejects_modified_message(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()
    headers = _verified_headers(client, account)
    challenge_response = _request_transfer_challenge(client, account, headers)
    challenge = challenge_response.json()

    response = client.post(
        "/transfers/submit",
        json={
            "from_address": account.address,
            "to_address": challenge["transfer_preview"]["to_address"],
            "amount": challenge["transfer_preview"]["amount"],
            "fee": challenge["transfer_preview"]["fee"],
            "memo": "preview",
            "message": challenge["message"].replace("Amount: 10", "Amount: 11"),
            "signature": _sign_message(challenge["message"], account),
        },
        headers=headers,
    )

    assert response.status_code == 400
    assert "transfer challenge" in response.json()["detail"].lower()


def test_transfer_submit_rejects_replayed_nonce(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()
    headers = _verified_headers(client, account)
    challenge_response = _request_transfer_challenge(client, account, headers)
    challenge = challenge_response.json()
    payload = {
        "from_address": account.address,
        "to_address": challenge["transfer_preview"]["to_address"],
        "amount": challenge["transfer_preview"]["amount"],
        "fee": challenge["transfer_preview"]["fee"],
        "memo": "preview",
        "message": challenge["message"],
        "signature": _sign_message(challenge["message"], account),
    }

    first = client.post("/transfers/submit", json=payload, headers=headers)
    second = client.post("/transfers/submit", json=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 401
    assert "already been used" in second.json()["detail"].lower()


def test_transfer_submit_rejects_field_mismatch(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()
    headers = _verified_headers(client, account)
    challenge_response = _request_transfer_challenge(client, account, headers)
    challenge = challenge_response.json()

    response = client.post(
        "/transfers/submit",
        json={
            "from_address": account.address,
            "to_address": _create_account().address,
            "amount": challenge["transfer_preview"]["amount"],
            "fee": challenge["transfer_preview"]["fee"],
            "memo": "preview",
            "message": challenge["message"],
            "signature": _sign_message(challenge["message"], account),
        },
        headers=headers,
    )

    assert response.status_code == 400
    assert "to_address does not match" in response.json()["detail"].lower()


def test_transfer_read_endpoints_return_safe_fields(blockchain):
    client, _ = _client(blockchain)
    sender = _create_account()
    headers = _verified_headers(client, sender)

    submit_response = _submit_transfer_intent(client, sender, headers)
    transfer_id = submit_response.json()["transfer_id"]

    by_id = client.get(f"/transfers/{transfer_id}")
    wallet_history = client.get(f"/wallets/{sender.address.lower()}/transfers")

    assert by_id.status_code == 200
    assert wallet_history.status_code == 200
    transfer = by_id.json()["transfer"]
    assert "signature" not in transfer
    assert "message" not in transfer
    assert "session_token" not in transfer
    assert wallet_history.json()["transfers"][0]["transfer_id"] == transfer_id


@pytest.mark.parametrize("backend_factory", [_json_backend, _sqlite_backend])
def test_transfer_intent_persists_across_storage_reload(backend_factory, isolated_data_dir):
    backend = backend_factory(isolated_data_dir, "transfers")
    blockchain = _create_blockchain_with_backend(backend)
    client, _ = _client(blockchain)
    account = _create_account()
    headers = _verified_headers(client, account)

    submit_response = _submit_transfer_intent(client, account, headers)
    assert submit_response.status_code == 200
    transfer_id = submit_response.json()["transfer_id"]

    reloaded = Blockchain(
        project_owner_wallet=blockchain.project_owner_wallet,
        Contributor_one=blockchain.Contributor_one,
        Contributor_two=blockchain.Contributor_two,
        storage_backend=backend,
    )
    stored = reloaded.get_transfer_intent(transfer_id)

    assert stored is not None
    assert stored["status"] == "signed_pending"
    assert stored["from_address"] == account.address.lower()


def test_invalid_wallet_transfer_history_rejected(blockchain):
    client, _ = _client(blockchain)

    response = client.get("/wallets/not-a-wallet/transfers")

    assert response.status_code == 400
