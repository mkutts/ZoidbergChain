from test_submission_lifecycle_api import (
    VOTE_ORIGINAL,
    _client,
    _create_metamask_account,
    _generate_wallet_via_api,
    _submit_signed_content_via_api,
    _upload_text_content_via_api,
    _verify_wallet_session,
    _vote_signed_via_api,
)


def test_native_account_summary_returns_zero_state_for_unknown_wallet(blockchain):
    client = _client(blockchain)
    unknown_account = _create_metamask_account()

    response = client.get(f"/accounts/{unknown_account.address}")

    assert response.status_code == 200
    body = response.json()
    assert body["wallet_address"] == unknown_account.address.lower()
    assert body["normalized_wallet_address"] == unknown_account.address.lower()
    assert body["account_type"] == "metamask_native"
    assert body["final_balance"] == "0"
    assert body["native_balance"] == "0"
    assert body["pending_outgoing"] == "0"
    assert body["pending_incoming"] == "0"
    assert body["available_balance"] == "0"
    assert body["submission_count"] == 0
    assert body["vote_count"] == 0
    assert body["reward_count"] == 0
    assert body["pending_transfer_count"] == 0
    assert body["symbol"] == "ZOID"
    assert "do not need to be pre-registered" in body["note"].lower()


def test_native_account_endpoints_return_activity_without_dev_wallet_registration(blockchain):
    client = _client(blockchain)
    creator = _create_metamask_account()
    creator_headers = _verify_wallet_session(client, creator)

    uploaded = _upload_text_content_via_api(client, creator.address, text="native account summary submission")
    submission = _submit_signed_content_via_api(
        client,
        creator,
        creator_headers,
        content_hash=uploaded["content_hash"],
        content_id=uploaded["content_id"],
        caption="native account summary submission",
    )

    other_submitter = _create_metamask_account()
    other_headers = _verify_wallet_session(client, other_submitter)
    other_uploaded = _upload_text_content_via_api(client, other_submitter.address, text="native account summary vote target")
    other_submission = _submit_signed_content_via_api(
        client,
        other_submitter,
        other_headers,
        content_hash=other_uploaded["content_hash"],
        content_id=other_uploaded["content_id"],
        caption="native account summary vote target",
    )

    _vote_signed_via_api(
        client,
        other_submission["submission_id"],
        creator,
        creator_headers,
        VOTE_ORIGINAL,
    )

    for _ in range(5):
        voter = _create_metamask_account()
        voter_headers = _verify_wallet_session(client, voter)
        _vote_signed_via_api(client, submission["submission_id"], voter, voter_headers, VOTE_ORIGINAL)

    evaluate_response = client.post(
        f"/submissions/{submission['submission_id']}/evaluate",
        data={"automated_originality_passed": "true"},
    )
    assert evaluate_response.status_code == 200

    minter = _generate_wallet_via_api(client)
    mint_response = client.post(f"/mint-queue/{submission['submission_id']}/mint", data={"miner": minter})
    assert mint_response.status_code == 200

    recipient = _create_metamask_account()
    blockchain.create_signed_transfer_intent(
        from_address=creator.address,
        to_address=recipient.address,
        amount="3",
        fee="0",
        memo="native account test intent",
        network="zoidberg-testnet",
        signature_scheme="personal_sign",
        signature="0xdeadbeef",
        signed_message="native account test signed message",
        signed_message_hash="a" * 64,
        transfer_nonce="1",
        signed_at="2026-07-23T12:00:00+00:00",
    )

    summary_response = client.get(f"/accounts/{creator.address}")
    submissions_response = client.get(f"/accounts/{creator.address}/submissions")
    votes_response = client.get(f"/accounts/{creator.address}/votes")
    rewards_response = client.get(f"/accounts/{creator.address}/rewards")
    transfers_response = client.get(f"/accounts/{creator.address}/transfers")

    assert summary_response.status_code == 200
    assert submissions_response.status_code == 200
    assert votes_response.status_code == 200
    assert rewards_response.status_code == 200
    assert transfers_response.status_code == 200

    summary = summary_response.json()
    assert summary["wallet_address"] == creator.address.lower()
    assert summary["submission_count"] == 1
    assert summary["vote_count"] == 1
    assert summary["reward_count"] == 1
    assert summary["pending_transfer_count"] == 1
    assert summary["final_balance"] == summary["native_balance"]
    assert float(summary["native_balance"]) >= 5.0
    assert summary["pending_outgoing"] == "3"
    assert summary["pending_incoming"] == "0"

    submissions = submissions_response.json()["submissions"]
    assert len(submissions) == 1
    assert submissions[0]["submission_id"] == submission["submission_id"]
    assert submissions[0]["creator_wallet_address"] == creator.address.lower()
    assert submissions[0]["signed"] is True
    assert submissions[0]["signature_scheme"] == "personal_sign"
    assert "submission_signature" not in submissions[0]

    votes = votes_response.json()["votes"]
    assert len(votes) == 1
    assert votes[0]["submission_id"] == other_submission["submission_id"]
    assert votes[0]["voter_wallet_address"] == creator.address.lower()
    assert votes[0]["signed"] is True
    assert votes[0]["identity_source"] == "metamask_signed"
    assert "vote_signature" not in votes[0]
    assert "vote_message" not in votes[0]

    rewards = rewards_response.json()["rewards"]
    assert len(rewards) == 1
    assert rewards[0]["reward_recipient"] == creator.address.lower()
    assert float(rewards[0]["reward_amount"]) == 5.0

    transfers = transfers_response.json()["transfers"]
    assert len(transfers) == 1
    assert transfers[0]["from_address"] == creator.address.lower()
    assert transfers[0]["to_address"] == recipient.address.lower()
    assert transfers[0]["memo"] == "native account test intent"
    assert transfers[0]["status"] == "signed_pending"
    assert "signature" not in transfers[0]
    assert "message" not in transfers[0]
    assert "session_token" not in transfers[0]


def test_native_account_endpoints_reject_invalid_address(blockchain):
    client = _client(blockchain)

    response = client.get("/accounts/not-a-wallet")

    assert response.status_code == 400
    assert "ethereum-style 0x address" in response.json()["detail"].lower()
