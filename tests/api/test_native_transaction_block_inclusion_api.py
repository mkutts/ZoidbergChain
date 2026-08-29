import importlib

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

import blockchain as blockchain_module
from block import Block
from native_transfer import (
    NativeTransferMessage,
    build_native_transaction,
    build_transfer_signing_message,
    hash_transfer_signing_message,
)
from peers import PeerStore
from protocol_v1 import PUBLIC_TESTNET_V1_NETWORK_ID
from submission import APPROVED, VOTE_NOT_ORIGINAL, VOTE_ORIGINAL
from test_support import fund_native_wallet_with_block
from transaction import Transaction
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
    return TestClient(api.app), api


def _create_account():
    return Account.create()


def _sign_message(message, account):
    signed = Account.sign_message(encode_defunct(text=message), account.key)
    return signed.signature.hex()


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


def _fund_native_wallet(blockchain, wallet_address, amount="25"):
    fund_native_wallet_with_block(blockchain, wallet_address, amount=amount)


def _build_legacy_signed_transaction(account, *, to_address=None, amount="4", fee="0", nonce="1", memo="legacy block tx"):
    recipient_address = (to_address or _create_account().address).lower()
    transfer_message = NativeTransferMessage(
        action="transfer_zoid",
        network="zoidberg-testnet",
        from_address=account.address.lower(),
        to_address=recipient_address,
        amount=amount,
        nonce=str(nonce),
        fee=fee,
        timestamp="2026-07-26T00:00:00+00:00",
        memo=memo,
        status="signed_pending",
    )
    signed_message = build_transfer_signing_message(transfer_message)
    signature = _sign_message(signed_message, account)
    return build_native_transaction(
        network="zoidberg-testnet",
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
    ).to_dict()


def _submit_transfer_intent(client, account, headers, **overrides):
    challenge_payload = {
        "from_address": account.address,
        "to_address": overrides.get("to_address", _create_account().address),
        "amount": overrides.get("amount", "4"),
        "fee": overrides.get("fee", "0"),
        "memo": overrides.get("memo", "block inclusion"),
    }
    challenge_response = client.post("/auth/wallet/transfer-challenge", json=challenge_payload, headers=headers)
    challenge = challenge_response.json()
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


def _submission(blockchain, submission_image, submitter):
    return blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Task 8.6 block inclusion",
        submitter=submitter,
    )


def _certify_submission(blockchain, submission):
    for index, vote_type in enumerate([
        VOTE_ORIGINAL,
        VOTE_ORIGINAL,
        VOTE_ORIGINAL,
        VOTE_ORIGINAL,
        VOTE_NOT_ORIGINAL,
    ]):
        blockchain.cast_submission_vote(
            submission_id=submission.submission_id,
            voter=f"task8-6-voter-{index}",
            vote_type=vote_type,
            created_at=1_000_100 + index,
        )
    submission.transition_to(APPROVED)
    return blockchain.create_originality_certificate(submission.submission_id, approved_at=1_000_200)


def _prepare_mintable_submission(blockchain, submission_image, submitter):
    submission = _submission(blockchain, submission_image, submitter)
    _certify_submission(blockchain, submission)
    blockchain.add_to_mint_queue(submission.submission_id)
    return submission


def _register_peer(api_module, node_id="peer-node-1", url="http://peer-one.test:8000"):
    return api_module.peer_store.register_peer(
        node_id=node_id,
        url=url,
        network_name="zoidberg-testnet",
    )


def test_mint_with_empty_mempool_succeeds_and_reports_zero_transactions(blockchain, submission_image, wallets):
    client, _api = _client(blockchain)
    submission = _prepare_mintable_submission(blockchain, submission_image, wallets["owner"].public_key)

    response = client.post(f"/mint-queue/{submission.submission_id}/mint", data={"miner": wallets["contributor_one"].public_key})

    assert response.status_code == 200
    body = response.json()
    assert body["minted"] is True
    assert body["transactions_included"] == 0
    assert body["transaction_ids"] == []
    assert body["block"]["transaction_count"] == 0
    assert body["block"]["transaction_ids"] == []


def test_mint_includes_and_settles_one_mempool_transaction(blockchain, submission_image, wallets):
    client, _api = _client(blockchain)
    sender = _create_account()
    recipient = _create_account()
    _fund_native_wallet(blockchain, sender.address, "10")
    headers = _verified_headers(client, sender)

    submit_response = _submit_transfer_intent(
        client,
        sender,
        headers,
        to_address=recipient.address,
        amount="4",
        admit_to_mempool=True,
    )
    tx_id = submit_response.json()["tx_id"]
    submission = _prepare_mintable_submission(blockchain, submission_image, wallets["owner"].public_key)

    mint_response = client.post(f"/mint-queue/{submission.submission_id}/mint", data={"miner": wallets["contributor_one"].public_key})

    assert mint_response.status_code == 200
    body = mint_response.json()
    assert body["transactions_included"] == 1
    assert body["transaction_ids"] == [tx_id]
    assert body["block"]["transaction_count"] == 1
    assert body["block"]["transaction_ids"] == [tx_id]
    assert body["block"]["native_transactions"][0]["tx_id"] == tx_id
    assert body["block"]["native_transactions"][0]["transaction_version"] == 1
    assert body["block"]["native_transactions"][0]["protocol_version"] == 1
    assert body["block"]["native_transactions"][0]["network_id"] == PUBLIC_TESTNET_V1_NETWORK_ID

    transaction_response = client.get(f"/transactions/{tx_id}")
    sender_history = client.get(f"/accounts/{sender.address.lower()}/transactions").json()
    recipient_history = client.get(f"/accounts/{recipient.address.lower()}/transactions").json()
    sender_balance = client.get(f"/wallets/{sender.address.lower()}/balance").json()
    recipient_balance = client.get(f"/wallets/{recipient.address.lower()}/balance").json()
    mempool = client.get("/mempool").json()

    assert transaction_response.status_code == 200
    transaction = transaction_response.json()["transaction"]
    assert transaction["status"] == "settled"
    assert transaction["included_block_hash"] == body["block_hash"]
    assert transaction["included_block_height"] == body["block_height"]
    assert transaction["settled_at"] is not None
    assert sender_history["transactions"][0]["status"] == "settled"
    assert sender_history["transactions"][0]["included_block_hash"] == body["block_hash"]
    assert sender_history["transactions"][0]["included_block_height"] == body["block_height"]
    assert sender_history["transactions"][0]["direction"] == "outgoing"
    assert recipient_history["transactions"][0]["status"] == "settled"
    assert recipient_history["transactions"][0]["included_block_hash"] == body["block_hash"]
    assert recipient_history["transactions"][0]["direction"] == "incoming"
    assert sender_balance["final_balance"] == "6"
    assert sender_balance["pending_outgoing"] == "0"
    assert sender_balance["available_balance"] == "6"
    assert recipient_balance["final_balance"] == "4"
    assert recipient_balance["pending_incoming"] == "0"
    assert recipient_balance["available_balance"] == "4"
    assert mempool["count"] == 0


def test_mint_includes_up_to_max_transactions_per_block(blockchain, submission_image, wallets, monkeypatch):
    client, _api = _client(blockchain)
    monkeypatch.setattr(blockchain_module, "MAX_TRANSACTIONS_PER_BLOCK", 1)

    sender_one = _create_account()
    sender_two = _create_account()
    _fund_native_wallet(blockchain, sender_one.address, "10")
    _fund_native_wallet(blockchain, sender_two.address, "10")

    headers_one = _verified_headers(client, sender_one)
    headers_two = _verified_headers(client, sender_two)

    tx_one = _submit_transfer_intent(client, sender_one, headers_one, amount="3", admit_to_mempool=True).json()["tx_id"]
    tx_two = _submit_transfer_intent(client, sender_two, headers_two, amount="2", admit_to_mempool=True).json()["tx_id"]
    submission = _prepare_mintable_submission(blockchain, submission_image, wallets["owner"].public_key)

    response = client.post(f"/mint-queue/{submission.submission_id}/mint", data={"miner": wallets["contributor_one"].public_key})

    assert response.status_code == 200
    assert response.json()["transactions_included"] == 1
    included_tx_id = response.json()["transaction_ids"][0]
    remaining_tx_id = tx_two if included_tx_id == tx_one else tx_one
    assert client.get(f"/transactions/{included_tx_id}").json()["transaction"]["status"] == "settled"
    assert client.get(f"/transactions/{remaining_tx_id}").json()["transaction"]["status"] == "mempool"


def test_mint_uses_canonical_native_transaction_order(blockchain, submission_image, wallets):
    client, _api = _client(blockchain)
    first_sender = _create_account()
    second_sender = _create_account()
    ordered_senders = sorted([first_sender, second_sender], key=lambda account: account.address.lower())
    lower_sender, higher_sender = ordered_senders[0], ordered_senders[1]
    recipient = _create_account()

    _fund_native_wallet(blockchain, lower_sender.address, "10")
    _fund_native_wallet(blockchain, higher_sender.address, "10")

    higher_headers = _verified_headers(client, higher_sender)
    lower_headers = _verified_headers(client, lower_sender)

    higher_tx_id = _submit_transfer_intent(
        client,
        higher_sender,
        higher_headers,
        to_address=recipient.address,
        amount="2",
        admit_to_mempool=True,
    ).json()["tx_id"]
    lower_tx_id = _submit_transfer_intent(
        client,
        lower_sender,
        lower_headers,
        to_address=recipient.address,
        amount="3",
        admit_to_mempool=True,
    ).json()["tx_id"]
    submission = _prepare_mintable_submission(blockchain, submission_image, wallets["owner"].public_key)

    response = client.post(f"/mint-queue/{submission.submission_id}/mint", data={"miner": wallets["contributor_one"].public_key})

    assert response.status_code == 200
    assert response.json()["transaction_ids"] == [lower_tx_id, higher_tx_id]
    assert response.json()["block"]["transaction_ids"] == [lower_tx_id, higher_tx_id]


def test_invalid_mempool_transaction_is_not_included_and_becomes_rejected(blockchain, submission_image, wallets):
    client, _api = _client(blockchain)
    sender = _create_account()
    _fund_native_wallet(blockchain, sender.address, "10")
    headers = _verified_headers(client, sender)

    submit_response = _submit_transfer_intent(client, sender, headers, amount="4", admit_to_mempool=True)
    tx_id = submit_response.json()["tx_id"]
    blockchain.native_transactions[0]["signature"] = "0xdeadbeef"
    submission = _prepare_mintable_submission(blockchain, submission_image, wallets["owner"].public_key)

    response = client.post(f"/mint-queue/{submission.submission_id}/mint", data={"miner": wallets["contributor_one"].public_key})

    assert response.status_code == 200
    assert response.json()["transactions_included"] == 0
    transaction = client.get(f"/transactions/{tx_id}").json()["transaction"]
    assert transaction["status"] == "rejected"


def test_receive_peer_block_rejects_out_of_order_native_transactions_without_mutating_local_state(
    blockchain,
    submission_image,
    wallets,
):
    client, api = _client(blockchain)
    _register_peer(api)
    first_sender = _create_account()
    second_sender = _create_account()
    ordered_senders = sorted([first_sender, second_sender], key=lambda account: account.address.lower())
    lower_sender, higher_sender = ordered_senders[0], ordered_senders[1]
    recipient = _create_account()

    _fund_native_wallet(blockchain, lower_sender.address, "10")
    _fund_native_wallet(blockchain, higher_sender.address, "10")

    higher_headers = _verified_headers(client, higher_sender)
    lower_headers = _verified_headers(client, lower_sender)

    higher_tx_id = _submit_transfer_intent(
        client,
        higher_sender,
        higher_headers,
        to_address=recipient.address,
        amount="2",
        admit_to_mempool=True,
    ).json()["tx_id"]
    lower_tx_id = _submit_transfer_intent(
        client,
        lower_sender,
        lower_headers,
        to_address=recipient.address,
        amount="3",
        admit_to_mempool=True,
    ).json()["tx_id"]

    higher_snapshot = blockchain._serialize_native_transaction_for_block(blockchain.get_native_transaction(higher_tx_id))
    lower_snapshot = blockchain._serialize_native_transaction_for_block(blockchain.get_native_transaction(lower_tx_id))
    latest_block = blockchain.get_latest_block()
    submission = _submission(blockchain, "zoidberg.jpg", recipient.address.lower())
    certificate = _certify_submission(blockchain, submission)
    minted_at = 1_000_500.0
    out_of_order_snapshots = [higher_snapshot, lower_snapshot]
    block = Block(
        index=latest_block.index + 1,
        previous_hash=latest_block.hash,
        timestamp=minted_at,
        transactions=[Transaction("REWARD_POOL", recipient.address.lower(), 5, created_at=1_000_500.0)],
        miner=recipient.address.lower(),
        meme={"encoded_image": "peer-image", "text": "Peer settled block"},
        native_transactions=out_of_order_snapshots,
        transaction_ids=[higher_tx_id, lower_tx_id],
        transaction_count=2,
        transactions_hash=blockchain._compute_block_native_transactions_hash(out_of_order_snapshots),
        **blockchain.certificate_block_metadata(certificate),
        **blockchain.build_meme_reward_metadata(submission, certificate, minted_at=minted_at),
    )

    response = client.post(
        "/peers/blocks/receive",
        json={
            "origin_node_id": "peer-node-1",
            "network_name": "zoidberg-testnet",
            "block": block.to_dict(),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "transaction_order_invalid"
    assert client.get(f"/transactions/{lower_tx_id}").json()["transaction"]["status"] == "mempool"
    assert client.get(f"/transactions/{higher_tx_id}").json()["transaction"]["status"] == "mempool"
    assert client.get(f"/wallets/{lower_sender.address.lower()}/balance").json()["final_balance"] == "10"
    assert client.get(f"/wallets/{higher_sender.address.lower()}/balance").json()["final_balance"] == "10"
    assert client.get("/mempool").json()["count"] == 2


def test_receive_peer_block_with_native_transaction_settles_local_mempool_transaction(blockchain):
    client, api = _client(blockchain)
    _register_peer(api)
    sender = _create_account()
    recipient = _create_account()
    _fund_native_wallet(blockchain, sender.address, "10")
    headers = _verified_headers(client, sender)
    submit_response = _submit_transfer_intent(
        client,
        sender,
        headers,
        to_address=recipient.address,
        amount="4",
        admit_to_mempool=True,
    )
    tx_id = submit_response.json()["tx_id"]
    transaction_snapshot = blockchain._serialize_native_transaction_for_block(blockchain.get_native_transaction(tx_id))
    latest_block = blockchain.get_latest_block()
    submission = _submission(blockchain, "zoidberg.jpg", recipient.address.lower())
    certificate = _certify_submission(blockchain, submission)
    minted_at = 1_000_500.0
    block = Block(
        index=latest_block.index + 1,
        previous_hash=latest_block.hash,
        timestamp=minted_at,
        transactions=[Transaction("REWARD_POOL", recipient.address.lower(), 5, created_at=1_000_500.0)],
        miner=recipient.address.lower(),
        meme={"encoded_image": "peer-image", "text": "Peer settled block"},
        native_transactions=[transaction_snapshot],
        transaction_ids=[tx_id],
        transaction_count=1,
        transactions_hash=blockchain._compute_block_native_transactions_hash([transaction_snapshot]),
        **blockchain.certificate_block_metadata(certificate),
        **blockchain.build_meme_reward_metadata(submission, certificate, minted_at=minted_at),
    )

    response = client.post(
        "/peers/blocks/receive",
        json={
            "origin_node_id": "peer-node-1",
            "network_name": "zoidberg-testnet",
            "block": block.to_dict(),
        },
    )

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    transaction = client.get(f"/transactions/{tx_id}").json()["transaction"]
    assert transaction["status"] == "settled"
    assert client.get("/mempool").json()["count"] == 0


def test_receive_peer_block_rejects_legacy_native_transaction_on_protocol_v1_block(blockchain):
    client, _api = _client(blockchain)
    sender = _create_account()
    recipient = _create_account()
    _fund_native_wallet(blockchain, sender.address, "10")
    legacy_transaction = _build_legacy_signed_transaction(
        sender,
        to_address=recipient.address,
        amount="4",
    )
    legacy_snapshot = blockchain._serialize_native_transaction_for_block(legacy_transaction)
    submission = _prepare_mintable_submission(blockchain, "zoidberg.jpg", recipient.address.lower())
    mint_response = client.post(
        f"/mint-queue/{submission.submission_id}/mint",
        data={"miner": recipient.address.lower()},
    )
    assert mint_response.status_code == 200

    block = dict(mint_response.json()["block"])
    block["native_transactions"] = [legacy_snapshot]
    block["transaction_ids"] = [legacy_snapshot["tx_id"]]
    block["transaction_count"] = 1
    block["transactions_hash"] = blockchain._compute_block_native_transactions_hash([legacy_snapshot])

    with pytest.raises(ValueError, match="Protocol v1 blocks cannot include legacy native transactions."):
        blockchain.validate_block_native_transactions(
            block,
            prior_chain=blockchain.chain_to_dicts(blockchain.chain[:-1]),
        )
