import importlib

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

from blockchain import Blockchain
from storage import JSONStorageBackend, SQLiteStorageBackend
from transaction import Transaction
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


def _fund_native_wallet(blockchain, wallet_address, amount="5"):
    blockchain.chain[0].transactions.append(
        Transaction(sender="GENESIS", recipient=wallet_address.lower(), amount=float(amount), tip=0)
    )


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
    challenge_overrides = {
        key: overrides[key]
        for key in ("to_address", "amount", "fee", "memo")
        if key in overrides
    }
    challenge_response = _request_transfer_challenge(client, account, headers, **challenge_overrides)
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
    assert body["nonce"] == "1"
    assert body["expected_nonce"] == "1"
    assert body["nonce_policy"] == "strict_sequential"
    assert body["transfer_preview"]["nonce"] == "1"
    assert body["transfer_preview"]["network"] == manager.network_name
    assert "ZoidbergChain Native Transfer" in body["message"]
    assert "Nonce: 1" in body["message"]
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


def test_transfer_challenge_rejects_wrong_manual_nonce(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()
    headers = _verified_headers(client, account)

    response = _request_transfer_challenge(client, account, headers, nonce=2)

    assert response.status_code == 400
    assert "expected next nonce 1" in response.json()["detail"].lower()


def test_valid_signed_transfer_intent_succeeds_and_is_non_final(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()
    _fund_native_wallet(blockchain, account.address, "25")
    headers = _verified_headers(client, account)
    starting_balance = blockchain.get_native_balance(account.address.lower())

    response = _submit_transfer_intent(client, account, headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body["tx_id"]) == 64
    assert body["transfer_id"]
    assert body["nonce"] == "1"
    assert body["status"] == "signed_pending"
    assert body["settlement_state"] == "non_final"
    assert "not settled" in body["message"].lower()
    assert blockchain.get_native_balance(account.address.lower()) == starting_balance


def test_transfer_challenge_returns_balance_preview(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()
    _fund_native_wallet(blockchain, account.address, "5")
    headers = _verified_headers(client, account)

    response = _request_transfer_challenge(client, account, headers, amount="4")

    assert response.status_code == 200
    body = response.json()
    assert body["available_balance"] == "5"
    assert body["estimated_total"] == "4"
    assert body["would_be_sufficient_at_challenge_time"] is True


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
    assert "signed transfer message" in response.json()["detail"].lower()


def test_transfer_submit_returns_existing_record_for_exact_duplicate(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()
    _fund_native_wallet(blockchain, account.address, "25")
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
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["tx_id"] == first.json()["tx_id"]
    assert "already recorded" in second.json()["message"].lower()


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


def test_second_different_signed_transfer_with_same_nonce_is_rejected(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()
    _fund_native_wallet(blockchain, account.address, "25")
    headers = _verified_headers(client, account)

    first_challenge = _request_transfer_challenge(
        client,
        account,
        headers,
        to_address=_create_account().address,
        amount="10",
    )
    second_challenge = _request_transfer_challenge(
        client,
        account,
        headers,
        to_address=_create_account().address,
        amount="11",
    )

    first_payload = {
        "from_address": account.address,
        "to_address": first_challenge.json()["transfer_preview"]["to_address"],
        "amount": first_challenge.json()["transfer_preview"]["amount"],
        "fee": first_challenge.json()["transfer_preview"]["fee"],
        "memo": "preview",
        "message": first_challenge.json()["message"],
        "signature": _sign_message(first_challenge.json()["message"], account),
    }
    second_payload = {
        "from_address": account.address,
        "to_address": second_challenge.json()["transfer_preview"]["to_address"],
        "amount": second_challenge.json()["transfer_preview"]["amount"],
        "fee": second_challenge.json()["transfer_preview"]["fee"],
        "memo": "preview",
        "message": second_challenge.json()["message"],
        "signature": _sign_message(second_challenge.json()["message"], account),
    }

    first = client.post("/transfers/submit", json=first_payload, headers=headers)
    second = client.post("/transfers/submit", json=second_payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 400
    assert "nonce already used or reserved" in second.json()["detail"].lower()


def test_gap_nonce_is_rejected_under_strict_sequential_policy(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()
    headers = _verified_headers(client, account)

    response = _request_transfer_challenge(client, account, headers, nonce=3)

    assert response.status_code == 400
    assert "expected next nonce 1" in response.json()["detail"].lower()


def test_transfer_read_endpoints_return_safe_fields(blockchain):
    client, _ = _client(blockchain)
    sender = _create_account()
    _fund_native_wallet(blockchain, sender.address, "25")
    headers = _verified_headers(client, sender)

    submit_response = _submit_transfer_intent(client, sender, headers)
    transfer_id = submit_response.json()["transfer_id"]
    tx_id = submit_response.json()["tx_id"]

    by_id = client.get(f"/transfers/{transfer_id}")
    wallet_history = client.get(f"/wallets/{sender.address.lower()}/transfers")
    tx_by_id = client.get(f"/transactions/{tx_id}")
    account_history = client.get(f"/accounts/{sender.address.lower()}/transactions")

    assert by_id.status_code == 200
    assert wallet_history.status_code == 200
    assert tx_by_id.status_code == 200
    assert account_history.status_code == 200
    transfer = by_id.json()["transfer"]
    transaction = tx_by_id.json()["transaction"]
    assert "signature" not in transfer
    assert "message" not in transfer
    assert "session_token" not in transfer
    assert transfer["tx_id"] == tx_id
    assert transfer["nonce"] == "1"
    assert wallet_history.json()["transfers"][0]["transfer_id"] == transfer_id
    assert wallet_history.json()["transfers"][0]["tx_id"] == tx_id
    assert transaction["tx_id"] == tx_id
    assert transaction["status"] == "signed_pending"
    assert transaction["nonce"] == "1"
    assert "signature" not in transaction
    assert "signed_message" not in transaction
    assert account_history.json()["transactions"][0]["tx_id"] == tx_id
    assert account_history.json()["transactions"][0]["direction"] == "outgoing"


@pytest.mark.parametrize("backend_factory", [_json_backend, _sqlite_backend])
def test_transfer_intent_persists_across_storage_reload(backend_factory, isolated_data_dir):
    backend = backend_factory(isolated_data_dir, "transfers")
    blockchain = _create_blockchain_with_backend(backend)
    client, _ = _client(blockchain)
    account = _create_account()
    _fund_native_wallet(blockchain, account.address, "25")
    headers = _verified_headers(client, account)

    submit_response = _submit_transfer_intent(client, account, headers)
    assert submit_response.status_code == 200
    transfer_id = submit_response.json()["transfer_id"]
    tx_id = submit_response.json()["tx_id"]

    reloaded = Blockchain(
        project_owner_wallet=blockchain.project_owner_wallet,
        Contributor_one=blockchain.Contributor_one,
        Contributor_two=blockchain.Contributor_two,
        storage_backend=backend,
    )
    stored = reloaded.get_transfer_intent(transfer_id)
    stored_transaction = reloaded.get_native_transaction(tx_id)

    assert stored is not None
    assert stored_transaction is not None
    assert stored["status"] == "signed_pending"
    assert stored["from_address"] == account.address.lower()
    assert stored["tx_id"] == tx_id
    assert stored["transfer_nonce"] == "1"
    assert stored_transaction["status"] == "signed_pending"
    assert stored_transaction["from_address"] == account.address.lower()
    assert stored_transaction["nonce"] == "1"


def test_unknown_transaction_lookup_returns_404(blockchain):
    client, _ = _client(blockchain)

    response = client.get("/transactions/" + ("a" * 64))

    assert response.status_code == 404


def test_account_transaction_history_includes_incoming_and_outgoing(blockchain):
    client, _ = _client(blockchain)
    sender = _create_account()
    recipient = _create_account()
    _fund_native_wallet(blockchain, sender.address, "25")
    headers = _verified_headers(client, sender)

    submit_response = _submit_transfer_intent(
        client,
        sender,
        headers,
        to_address=recipient.address,
    )
    assert submit_response.status_code == 200
    tx_id = submit_response.json()["tx_id"]

    sender_history = client.get(f"/accounts/{sender.address.lower()}/transactions")
    recipient_history = client.get(f"/accounts/{recipient.address.lower()}/transactions")

    assert sender_history.status_code == 200
    assert recipient_history.status_code == 200
    assert sender_history.json()["transactions"][0]["tx_id"] == tx_id
    assert sender_history.json()["transactions"][0]["direction"] == "outgoing"
    assert recipient_history.json()["transactions"][0]["tx_id"] == tx_id
    assert recipient_history.json()["transactions"][0]["direction"] == "incoming"


def test_nonce_endpoint_returns_expected_state(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()
    _fund_native_wallet(blockchain, account.address, "25")
    headers = _verified_headers(client, account)

    before = client.get(f"/accounts/{account.address.lower()}/nonce")
    submit_response = _submit_transfer_intent(client, account, headers)
    after = client.get(f"/accounts/{account.address.lower()}/nonce")

    assert before.status_code == 200
    assert before.json()["next_nonce"] == 1
    assert before.json()["used_nonces"] == []
    assert before.json()["reserved_nonces"] == []
    assert before.json()["policy"] == "strict_sequential"

    assert submit_response.status_code == 200
    assert after.status_code == 200
    assert after.json()["next_nonce"] == 2
    assert after.json()["used_nonces"] == [1]
    assert after.json()["reserved_nonces"] == [1]


def test_invalid_wallet_nonce_endpoint_rejected(blockchain):
    client, _ = _client(blockchain)

    response = client.get("/accounts/not-a-wallet/nonce")

    assert response.status_code == 400


@pytest.mark.parametrize("backend_factory", [_json_backend, _sqlite_backend])
def test_nonce_state_survives_storage_reload(backend_factory, isolated_data_dir):
    backend = backend_factory(isolated_data_dir, "nonce-reload")
    blockchain = _create_blockchain_with_backend(backend)
    client, _ = _client(blockchain)
    account = _create_account()
    _fund_native_wallet(blockchain, account.address, "25")
    headers = _verified_headers(client, account)

    submit_response = _submit_transfer_intent(client, account, headers)
    assert submit_response.status_code == 200

    reloaded = Blockchain(
        project_owner_wallet=blockchain.project_owner_wallet,
        Contributor_one=blockchain.Contributor_one,
        Contributor_two=blockchain.Contributor_two,
        storage_backend=backend,
    )

    assert reloaded.get_next_nonce(account.address.lower()) == 2
    assert reloaded.get_used_nonces(account.address.lower()) == [1]
    assert reloaded.get_reserved_nonces(account.address.lower()) == [1]


def test_transfer_equal_to_available_balance_is_accepted(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()
    _fund_native_wallet(blockchain, account.address, "5")
    headers = _verified_headers(client, account)

    response = _submit_transfer_intent(client, account, headers, amount="5")

    assert response.status_code == 200
    balance_state = client.get(f"/accounts/{account.address.lower()}").json()
    assert balance_state["final_balance"] == "5"
    assert balance_state["pending_outgoing"] == "5"
    assert balance_state["available_balance"] == "0"


def test_transfer_above_available_balance_is_rejected_and_not_recorded(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()
    _fund_native_wallet(blockchain, account.address, "5")
    headers = _verified_headers(client, account)

    response = _submit_transfer_intent(client, account, headers, amount="6")
    nonce_state = client.get(f"/accounts/{account.address.lower()}/nonce").json()
    history = client.get(f"/accounts/{account.address.lower()}/transactions").json()["transactions"]

    assert response.status_code == 400
    assert "insufficient available balance" in response.json()["detail"].lower()
    assert nonce_state["next_nonce"] == 1
    assert history == []
    assert blockchain.get_native_balance(account.address.lower()) == 5


def test_multiple_pending_transfers_cannot_overcommit_funds(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()
    _fund_native_wallet(blockchain, account.address, "5")
    headers = _verified_headers(client, account)

    first = _submit_transfer_intent(client, account, headers, amount="4")
    second = _submit_transfer_intent(client, account, headers, amount="2")
    third = _submit_transfer_intent(client, account, headers, amount="1")
    balance_state = client.get(f"/accounts/{account.address.lower()}").json()
    nonce_state = client.get(f"/accounts/{account.address.lower()}/nonce").json()

    assert first.status_code == 200
    assert second.status_code == 400
    assert "insufficient available balance" in second.json()["detail"].lower()
    assert third.status_code == 200
    assert balance_state["final_balance"] == "5"
    assert balance_state["pending_outgoing"] == "5"
    assert balance_state["available_balance"] == "0"
    assert nonce_state["next_nonce"] == 3


def test_pending_incoming_does_not_increase_available_balance(blockchain):
    client, _ = _client(blockchain)
    sender = _create_account()
    recipient = _create_account()
    _fund_native_wallet(blockchain, sender.address, "5")
    headers = _verified_headers(client, sender)

    response = _submit_transfer_intent(client, sender, headers, to_address=recipient.address, amount="4")
    recipient_summary = client.get(f"/accounts/{recipient.address.lower()}").json()

    assert response.status_code == 200
    assert recipient_summary["final_balance"] == "0"
    assert recipient_summary["pending_incoming"] == "4"
    assert recipient_summary["available_balance"] == "0"


def test_wallet_balance_endpoint_returns_full_balance_snapshot(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()
    _fund_native_wallet(blockchain, account.address, "5")
    headers = _verified_headers(client, account)

    submit_response = _submit_transfer_intent(client, account, headers, amount="4")
    response = client.get(f"/wallets/{account.address.lower()}/balance")

    assert submit_response.status_code == 200
    assert response.status_code == 200
    body = response.json()
    assert body["final_balance"] == "5"
    assert body["native_balance"] == "5"
    assert body["pending_outgoing"] == "4"
    assert body["pending_incoming"] == "0"
    assert body["available_balance"] == "1"
    assert body["symbol"] == "ZOID"


def test_nonzero_fee_is_rejected_clearly(blockchain):
    client, _ = _client(blockchain)
    account = _create_account()
    _fund_native_wallet(blockchain, account.address, "5")
    headers = _verified_headers(client, account)

    response = _request_transfer_challenge(client, account, headers, fee="0.1")

    assert response.status_code == 200
    challenge = response.json()
    submit = client.post(
        "/transfers/submit",
        json={
            "from_address": account.address,
            "to_address": challenge["transfer_preview"]["to_address"],
            "amount": challenge["transfer_preview"]["amount"],
            "fee": challenge["transfer_preview"]["fee"],
            "memo": "preview",
            "message": challenge["message"],
            "signature": _sign_message(challenge["message"], account),
        },
        headers=headers,
    )

    assert submit.status_code == 400
    assert "nonzero fees are not enabled yet" in submit.json()["detail"].lower()


def test_invalid_wallet_transfer_history_rejected(blockchain):
    client, _ = _client(blockchain)

    response = client.get("/wallets/not-a-wallet/transfers")

    assert response.status_code == 400
