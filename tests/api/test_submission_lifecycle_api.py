from fastapi.testclient import TestClient
from eth_account import Account
from eth_account.messages import encode_defunct

from wallet_auth import WalletAuthManager
from submission import (
    APPROVED,
    HARD_REJECTED,
    MINTED,
    PENDING,
    QUEUED,
    REJECTED,
    VOTE_NOT_ORIGINAL,
    VOTE_ORIGINAL,
    VOTE_UNSURE,
)


def _client(blockchain):
    import api

    api.blockchain = blockchain
    api.wallet_auth_manager = WalletAuthManager(
        network_name=api.NETWORK_NAME,
        environment=api.ENVIRONMENT,
    )
    return TestClient(api.app)


def _submission(blockchain, submission_image, submitter, text="API lifecycle meme"):
    return blockchain.submit_content(
        image_path=str(submission_image),
        text_content=text,
        submitter=submitter,
    )


def _cast_votes(blockchain, submission_id, vote_types):
    for index, vote_type in enumerate(vote_types):
        blockchain.cast_submission_vote(
            submission_id=submission_id,
            voter=f"api-voter-{index}",
            vote_type=vote_type,
        )


def _certify_submission(blockchain, submission):
    _cast_votes(
        blockchain,
        submission.submission_id,
        [VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_NOT_ORIGINAL],
    )
    submission.transition_to(APPROVED)
    return blockchain.create_originality_certificate(submission.submission_id, approved_at=1_000_000)


def _generate_wallet_via_api(client):
    response = client.post("/generate_wallet")
    assert response.status_code == 200
    return response.json()["wallet"]["public_key"]


def _create_metamask_account():
    return Account.create()


def _sign_message(message, account):
    signed = Account.sign_message(encode_defunct(text=message), account.key)
    return signed.signature.hex()


def _verify_wallet_session(client, account):
    challenge = client.post("/auth/wallet/challenge", json={"wallet_address": account.address})
    assert challenge.status_code == 200
    message = challenge.json()["message"]
    verify = client.post(
        "/auth/wallet/verify",
        json={
            "wallet_address": account.address,
            "message": message,
            "signature": _sign_message(message, account),
        },
    )
    assert verify.status_code == 200
    return {"Authorization": f"Bearer {verify.json()['session_token']}"}


def _request_submission_challenge(client, account, headers, content_hash, content_id=None, caption=None):
    response = client.post(
        "/auth/wallet/submission-challenge",
        json={
            "wallet_address": account.address,
            "content_hash": content_hash,
            "content_id": content_id,
            "caption": caption,
        },
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()


def _submit_signed_content_via_api(client, account, headers, content_hash, content_id=None, caption=None):
    challenge = _request_submission_challenge(
        client,
        account,
        headers,
        content_hash=content_hash,
        content_id=content_id,
        caption=caption,
    )
    data = {
        "wallet_address": account.address,
        "content_hash": content_hash,
        "message": challenge["message"],
        "signature": _sign_message(challenge["message"], account),
    }
    if content_id:
        data["content_id"] = content_id
    response = client.post("/submit_content", data=data, headers=headers)
    assert response.status_code == 200
    return response.json()["submission"]


def _submit_content_via_api(client, submission_image, submitter, text="Real API lifecycle meme"):
    with open(submission_image, "rb") as image_file:
        response = client.post(
            "/submit_content",
            files={"image": ("real-api-lifecycle.jpg", image_file, "image/jpeg")},
            data={
                "submitter": submitter,
                "text_content": text,
            },
        )
    assert response.status_code == 200
    return response.json()["submission"]


def _upload_text_content_via_api(client, submitter, text="Upload-first text content"):
    response = client.post(
        "/content/text",
        json={
            "text_content": text,
            "submitted_by": submitter,
            "caption": text,
        },
    )
    assert response.status_code == 200
    return response.json()


def _upload_image_content_via_api(client, submitter, image_path, filename="upload-first.jpg", mime_type="image/jpeg", caption=None):
    with open(image_path, "rb") as image_file:
        response = client.post(
            "/content/upload",
            data={
                "submitted_by": submitter,
                **({"caption": caption} if caption is not None else {}),
            },
            files={"file": (filename, image_file, mime_type)},
        )
    assert response.status_code == 200
    return response.json()


def test_signed_submission_accepts_uploaded_content_and_derives_creator_from_verified_wallet(blockchain):
    client = _client(blockchain)
    account = _create_metamask_account()
    headers = _verify_wallet_session(client, account)
    uploaded = _upload_text_content_via_api(client, account.address, text="signed text content")

    submission = _submit_signed_content_via_api(
        client,
        account,
        headers,
        content_hash=uploaded["content_hash"],
        content_id=uploaded["content_id"],
        caption="signed text content",
    )

    assert submission["submitter"] == account.address.lower()
    assert submission["creator_wallet_address"] == account.address.lower()
    assert submission["identity_source"] == "metamask_signed"
    assert submission["signature_scheme"] == "personal_sign"
    assert submission["signed_message_hash"]


def test_signed_submission_rejects_missing_signature(blockchain):
    client = _client(blockchain)
    account = _create_metamask_account()
    headers = _verify_wallet_session(client, account)
    uploaded = _upload_text_content_via_api(client, account.address, text="signed missing signature")
    challenge = _request_submission_challenge(
        client,
        account,
        headers,
        content_hash=uploaded["content_hash"],
        content_id=uploaded["content_id"],
        caption="signed missing signature",
    )

    response = client.post(
        "/submit_content",
        data={
            "wallet_address": account.address,
            "content_hash": uploaded["content_hash"],
            "content_id": uploaded["content_id"],
            "message": challenge["message"],
        },
        headers=headers,
    )

    assert response.status_code == 400
    assert "signature is required" in response.json()["detail"].lower()


def test_signed_submission_rejects_wrong_wallet_signature(blockchain):
    client = _client(blockchain)
    account = _create_metamask_account()
    wrong_account = _create_metamask_account()
    headers = _verify_wallet_session(client, account)
    uploaded = _upload_text_content_via_api(client, account.address, text="wrong wallet signature")
    challenge = _request_submission_challenge(
        client,
        account,
        headers,
        content_hash=uploaded["content_hash"],
        content_id=uploaded["content_id"],
        caption="wrong wallet signature",
    )

    response = client.post(
        "/submit_content",
        data={
            "wallet_address": account.address,
            "content_hash": uploaded["content_hash"],
            "content_id": uploaded["content_id"],
            "message": challenge["message"],
            "signature": _sign_message(challenge["message"], wrong_account),
        },
        headers=headers,
    )

    assert response.status_code == 400
    assert "does not match the verified session wallet" in response.json()["detail"].lower()


def test_signed_submission_rejects_replayed_nonce(blockchain):
    client = _client(blockchain)
    account = _create_metamask_account()
    headers = _verify_wallet_session(client, account)
    uploaded = _upload_text_content_via_api(client, account.address, text="replayed nonce")
    challenge = _request_submission_challenge(
        client,
        account,
        headers,
        content_hash=uploaded["content_hash"],
        content_id=uploaded["content_id"],
        caption="replayed nonce",
    )
    signature = _sign_message(challenge["message"], account)

    first = client.post(
        "/submit_content",
        data={
            "wallet_address": account.address,
            "content_hash": uploaded["content_hash"],
            "content_id": uploaded["content_id"],
            "message": challenge["message"],
            "signature": signature,
        },
        headers=headers,
    )
    second = client.post(
        "/submit_content",
        data={
            "wallet_address": account.address,
            "content_hash": uploaded["content_hash"],
            "content_id": uploaded["content_id"],
            "message": challenge["message"],
            "signature": signature,
        },
        headers=headers,
    )

    assert first.status_code == 200
    assert second.status_code == 401
    assert "already been used" in second.json()["detail"].lower()


def test_signed_submission_accepts_browser_normalized_newlines(blockchain):
    client = _client(blockchain)
    account = _create_metamask_account()
    headers = _verify_wallet_session(client, account)
    uploaded = _upload_text_content_via_api(client, account.address, text="newline normalization")
    challenge = _request_submission_challenge(
        client,
        account,
        headers,
        content_hash=uploaded["content_hash"],
        content_id=uploaded["content_id"],
        caption="newline normalization",
    )

    browser_message = challenge["message"].replace("\n", "\r\n")

    response = client.post(
        "/submit_content",
        data={
            "wallet_address": account.address,
            "content_hash": uploaded["content_hash"],
            "content_id": uploaded["content_id"],
            "message": browser_message,
            "signature": _sign_message(challenge["message"], account),
        },
        headers=headers,
    )

    assert response.status_code == 200
    submission = response.json()["submission"]
    assert submission["submitter"] == account.address.lower()
    assert submission["identity_source"] == "metamask_signed"


def _vote_via_api(client, submission_id, voter, vote_type=VOTE_ORIGINAL):
    response = client.post(
        f"/submissions/{submission_id}/vote",
        data={
            "voter": voter,
            "vote_type": vote_type,
        },
    )
    assert response.status_code == 200
    return response.json()["vote"]


def _request_vote_challenge(client, account, headers, submission_id, vote_type=VOTE_ORIGINAL):
    response = client.post(
        "/auth/wallet/vote-challenge",
        json={
            "wallet_address": account.address,
            "submission_id": submission_id,
            "vote": vote_type,
        },
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()


def _vote_signed_via_api(client, submission_id, account, headers, vote_type=VOTE_ORIGINAL):
    challenge = _request_vote_challenge(client, account, headers, submission_id, vote_type=vote_type)
    response = client.post(
        f"/submissions/{submission_id}/vote",
        data={
            "wallet_address": account.address,
            "vote_type": vote_type,
            "message": challenge["message"],
            "signature": _sign_message(challenge["message"], account),
        },
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()["vote"]


def test_submit_content_accepts_uploaded_content_id_and_returns_safe_metadata(blockchain, wallets):
    client = _client(blockchain)
    uploaded = _upload_text_content_via_api(client, wallets["owner"].public_key)

    response = client.post(
        "/submit_content",
        data={
            "submitter": wallets["owner"].public_key,
            "content_id": uploaded["content_id"],
        },
    )

    assert response.status_code == 200
    submission = response.json()["submission"]
    assert submission["content_id"] == uploaded["content_id"]
    assert submission["content_hash"] == uploaded["content_hash"]
    assert submission["content_type"] == "text"
    assert submission["storage_status"] == "verified"
    assert submission["download_url"] == f"/content/{uploaded['content_hash']}"
    assert "image_path" not in submission


def test_submit_content_rejects_mismatched_content_id_and_hash(blockchain, wallets):
    client = _client(blockchain)
    first = _upload_text_content_via_api(client, wallets["owner"].public_key, text="first")
    second = _upload_text_content_via_api(client, wallets["owner"].public_key, text="second")

    response = client.post(
        "/submit_content",
        data={
            "submitter": wallets["owner"].public_key,
            "content_id": first["content_id"],
            "content_hash": second["content_hash"],
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "content_id does not match content_hash."


def test_submit_content_accepts_uppercase_jpg_filename(blockchain, submission_image, wallets):
    client = _client(blockchain)

    with open(submission_image, "rb") as image_file:
        response = client.post(
            "/submit_content",
            files={"image": ("Uppercase.JPG", image_file, "image/jpeg")},
            data={
                "submitter": wallets["owner"].public_key,
                "text_content": "uppercase filename submission",
            },
        )

    assert response.status_code == 200
    submission = response.json()["submission"]
    assert submission["content_hash"]
    assert submission["content_id"]
    assert submission["storage_status"] in {"local", "verified"}


def test_text_content_submission_can_be_minted_from_content_reference(blockchain, wallets):
    client = _client(blockchain)
    uploaded = _upload_text_content_via_api(client, wallets["owner"].public_key, text="mintable text content")

    response = client.post(
        "/submit_content",
        data={
            "submitter": wallets["owner"].public_key,
            "content_id": uploaded["content_id"],
        },
    )

    assert response.status_code == 200
    submission = response.json()["submission"]
    submission_id = submission["submission_id"]

    for index in range(5):
        blockchain.cast_submission_vote(
            submission_id=submission_id,
            voter=f"text-content-voter-{index}",
            vote_type=VOTE_ORIGINAL,
        )

    evaluate_response = client.post(
        f"/submissions/{submission_id}/evaluate",
        data={"automated_originality_passed": "true"},
    )

    assert evaluate_response.status_code == 200
    assert evaluate_response.json()["certificate"]["content_id"] == uploaded["content_id"]

    mint_response = client.post(f"/mint-queue/{submission_id}/mint")

    assert mint_response.status_code == 200
    body = mint_response.json()
    assert body["minted"] is True
    assert body["block"]["content_id"] == uploaded["content_id"]
    assert body["block"]["content_hash"] == uploaded["content_hash"]
    assert body["block"]["meme"]["text"] == "mintable text content"


def test_mint_queue_response_hydrates_content_metadata(blockchain, wallets):
    client = _client(blockchain)
    uploaded = _upload_text_content_via_api(client, wallets["owner"].public_key, text="hydrated queue content")

    response = client.post(
        "/submit_content",
        data={
            "submitter": wallets["owner"].public_key,
            "content_id": uploaded["content_id"],
        },
    )

    assert response.status_code == 200
    submission_id = response.json()["submission"]["submission_id"]

    for index in range(5):
        blockchain.cast_submission_vote(
            submission_id=submission_id,
            voter=f"queue-hydration-voter-{index}",
            vote_type=VOTE_ORIGINAL,
        )

    evaluate_response = client.post(
        f"/submissions/{submission_id}/evaluate",
        data={"automated_originality_passed": "true"},
    )

    assert evaluate_response.status_code == 200

    mint_queue_response = client.get("/mint-queue")
    assert mint_queue_response.status_code == 200
    mint_queue_item = mint_queue_response.json()["mint_queue"][0]
    assert mint_queue_item["content_id"] == uploaded["content_id"]
    assert mint_queue_item["content_hash"] == uploaded["content_hash"]
    assert mint_queue_item["content_type"] == "text"
    assert mint_queue_item["mime_type"] == "text/plain"
    assert mint_queue_item["storage_status"] == "verified"
    assert mint_queue_item["mintable"] is True
    assert mint_queue_item["mint_block_reason"] is None
    assert mint_queue_item["content_metadata_missing"] is False
    assert mint_queue_item["download_url"] == f"/content/{uploaded['content_hash']}"
    assert mint_queue_item["originality_score"] is not None


def test_mint_queue_blocks_signed_image_without_extractable_text(blockchain, submission_image, monkeypatch):
    client = _client(blockchain)
    account = _create_metamask_account()
    headers = _verify_wallet_session(client, account)
    uploaded = _upload_image_content_via_api(client, account.address, submission_image)
    submission = _submit_signed_content_via_api(
        client,
        account,
        headers,
        content_hash=uploaded["content_hash"],
        content_id=uploaded["content_id"],
    )

    monkeypatch.setattr("blockchain.extract_text", lambda _path: "")

    for index in range(5):
        blockchain.cast_submission_vote(
            submission_id=submission["submission_id"],
            voter=f"queue-no-text-voter-{index}",
            vote_type=VOTE_ORIGINAL,
        )

    evaluate_response = client.post(
        f"/submissions/{submission['submission_id']}/evaluate",
        data={"automated_originality_passed": "true"},
    )

    assert evaluate_response.status_code == 200

    mint_queue_response = client.get("/mint-queue")
    assert mint_queue_response.status_code == 200
    mint_queue_item = mint_queue_response.json()["mint_queue"][0]
    assert mint_queue_item["mintable"] is False
    assert mint_queue_item["mint_block_reason"] == "no_text_content_extracted"


def test_real_api_submit_vote_evaluate_certificate_lookup_and_mint_flow(
    blockchain,
    submission_image,
):
    client = _client(blockchain)
    submitter = _generate_wallet_via_api(client)
    voters = [_generate_wallet_via_api(client) for _ in range(5)]
    submission = _submit_content_via_api(client, submission_image, submitter)
    submission_id = submission["submission_id"]

    pending_certificate = client.get(f"/submissions/{submission_id}/certificate")
    assert pending_certificate.status_code == 404

    for voter in voters:
        _vote_via_api(client, submission_id, voter, VOTE_ORIGINAL)

    evaluate_response = client.post(
        f"/submissions/{submission_id}/evaluate",
        data={"automated_originality_passed": "true"},
    )

    assert evaluate_response.status_code == 200
    body = evaluate_response.json()
    certificate = body["certificate"]
    certificate_id = certificate["certificate_id"]
    assert body["evaluation"]["status"] == APPROVED
    assert body["evaluation"]["certificate_id"] == certificate_id
    assert body["submission"]["status"] == QUEUED
    assert body["submission"]["certificate_id"] == certificate_id
    assert certificate["submission_id"] == submission_id
    assert certificate["approval_percentage"] == 1.0
    assert certificate["decisive_vote_total"] == 5
    assert certificate["vote_hash"]
    assert certificate["minimum_votes_required"] == 5
    assert certificate["originality_score"] > 0

    by_submission = client.get(f"/submissions/{submission_id}/certificate")
    by_certificate_id = client.get(f"/certificates/{certificate_id}")
    assert by_submission.status_code == 200
    assert by_certificate_id.status_code == 200
    assert by_submission.json()["certificate"] == certificate
    assert by_certificate_id.json()["certificate"] == certificate

    mint_queue = client.get("/mint-queue")
    assert mint_queue.status_code == 200
    assert mint_queue.json()["mint_queue"][0]["submission_id"] == submission_id
    assert mint_queue.json()["mint_queue"][0]["certificate_id"] == certificate_id

    mint_response = client.post(f"/mint-queue/{submission_id}/mint")
    assert mint_response.status_code == 200
    minted = mint_response.json()
    assert minted["minted"] is True
    assert minted["submission"]["status"] == MINTED
    assert minted["block"]["submission_id"] == submission_id
    assert minted["block"]["certificate_id"] == certificate_id
    assert minted["block"]["originality_score"] == certificate["originality_score"]


def test_signed_submission_vote_evaluate_certificate_lookup_and_mint_flow(blockchain):
    client = _client(blockchain)
    account = _create_metamask_account()
    headers = _verify_wallet_session(client, account)
    minter = _generate_wallet_via_api(client)
    voters = [_generate_wallet_via_api(client) for _ in range(5)]
    uploaded = _upload_text_content_via_api(client, account.address, text="signed full flow")
    submission = _submit_signed_content_via_api(
        client,
        account,
        headers,
        content_hash=uploaded["content_hash"],
        content_id=uploaded["content_id"],
        caption="signed full flow",
    )
    submission_id = submission["submission_id"]

    for _ in voters:
        voter_account = _create_metamask_account()
        voter_headers = _verify_wallet_session(client, voter_account)
        _vote_signed_via_api(client, submission_id, voter_account, voter_headers, VOTE_ORIGINAL)

    evaluate_response = client.post(
        f"/submissions/{submission_id}/evaluate",
        data={"automated_originality_passed": "true"},
    )

    assert evaluate_response.status_code == 200
    certificate = evaluate_response.json()["certificate"]
    assert certificate["creator_wallet"] == account.address.lower()

    mint_response = client.post(
        f"/mint-queue/{submission_id}/mint",
        data={"miner": minter},
    )
    assert mint_response.status_code == 200
    minted = mint_response.json()
    assert minted["minted"] is True
    assert minted["reward_type"] == "meme_mining_reward"
    assert minted["reward_recipient"] == account.address.lower()
    assert float(minted["reward_amount"]) == 5.0
    assert minted["block"]["reward_recipient"] == account.address.lower()
    assert float(minted["block"]["reward_amount"]) == 5.0
    assert minted["block"]["miner"] == minter

    balance_response = client.get(f"/wallets/{account.address.lower()}/balance")
    rewards_response = client.get(f"/wallets/{account.address.lower()}/rewards")
    assert balance_response.status_code == 200
    assert float(balance_response.json()["final_balance"]) >= 5.0
    assert float(balance_response.json()["native_balance"]) >= 5.0
    assert balance_response.json()["pending_outgoing"] == "0"
    assert balance_response.json()["pending_incoming"] == "0"
    assert balance_response.json()["available_balance"] == balance_response.json()["native_balance"]
    assert rewards_response.status_code == 200
    assert rewards_response.json()["rewards"][0]["reward_recipient"] == account.address.lower()
    assert float(rewards_response.json()["rewards"][0]["reward_amount"]) == 5.0


def test_native_wallet_balance_endpoint_returns_zero_for_unknown_wallet(blockchain):
    client = _client(blockchain)
    unknown_account = _create_metamask_account()

    response = client.get(f"/wallets/{unknown_account.address}/balance")

    assert response.status_code == 200
    assert response.json()["wallet_address"] == unknown_account.address.lower()
    assert response.json()["final_balance"] == "0"
    assert response.json()["native_balance"] == "0"
    assert response.json()["pending_outgoing"] == "0"
    assert response.json()["pending_incoming"] == "0"
    assert response.json()["available_balance"] == "0"
    assert response.json()["symbol"] == "ZOID"


def test_signed_vote_derives_voter_from_verified_wallet(blockchain):
    client = _client(blockchain)
    submitter = _create_metamask_account()
    submitter_headers = _verify_wallet_session(client, submitter)
    uploaded = _upload_text_content_via_api(client, submitter.address, text="signed vote base")
    submission = _submit_signed_content_via_api(
        client,
        submitter,
        submitter_headers,
        content_hash=uploaded["content_hash"],
        content_id=uploaded["content_id"],
        caption="signed vote base",
    )

    voter_account = _create_metamask_account()
    voter_headers = _verify_wallet_session(client, voter_account)
    vote = _vote_signed_via_api(client, submission["submission_id"], voter_account, voter_headers, VOTE_UNSURE)

    assert vote["voter"] == voter_account.address.lower()
    assert vote["voter_wallet_address"] == voter_account.address.lower()
    assert vote["identity_source"] == "metamask_signed"
    assert vote["signature_scheme"] == "personal_sign"
    assert vote["signed_message_hash"]


def test_signed_vote_rejects_duplicate_vote(blockchain):
    client = _client(blockchain)
    submitter = _create_metamask_account()
    submitter_headers = _verify_wallet_session(client, submitter)
    uploaded = _upload_text_content_via_api(client, submitter.address, text="duplicate vote base")
    submission = _submit_signed_content_via_api(
        client,
        submitter,
        submitter_headers,
        content_hash=uploaded["content_hash"],
        content_id=uploaded["content_id"],
        caption="duplicate vote base",
    )

    voter_account = _create_metamask_account()
    voter_headers = _verify_wallet_session(client, voter_account)
    first_vote = _vote_signed_via_api(client, submission["submission_id"], voter_account, voter_headers, VOTE_ORIGINAL)

    assert first_vote["vote_type"] == VOTE_ORIGINAL
    second_challenge = client.post(
        "/auth/wallet/vote-challenge",
        json={
            "wallet_address": voter_account.address,
            "submission_id": submission["submission_id"],
            "vote": VOTE_ORIGINAL,
        },
        headers=voter_headers,
    )
    assert second_challenge.status_code == 400
    assert "already voted" in second_challenge.json()["detail"].lower()


def test_signed_vote_rejects_creator_self_vote(blockchain):
    client = _client(blockchain)
    submitter = _create_metamask_account()
    submitter_headers = _verify_wallet_session(client, submitter)
    uploaded = _upload_text_content_via_api(client, submitter.address, text="self vote base")
    submission = _submit_signed_content_via_api(
        client,
        submitter,
        submitter_headers,
        content_hash=uploaded["content_hash"],
        content_id=uploaded["content_id"],
        caption="self vote base",
    )

    response = client.post(
        "/auth/wallet/vote-challenge",
        json={
            "wallet_address": submitter.address,
            "submission_id": submission["submission_id"],
            "vote": VOTE_ORIGINAL,
        },
        headers=submitter_headers,
    )

    assert response.status_code == 400
    assert "cannot vote on their own submission" in response.json()["detail"].lower()


def test_evaluate_approved_submission_enters_mint_queue(blockchain, submission_image, wallets):
    client = _client(blockchain)
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    _cast_votes(
        blockchain,
        submission.submission_id,
        [VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_NOT_ORIGINAL],
    )

    response = client.post(
        f"/submissions/{submission.submission_id}/evaluate",
        data={"automated_originality_passed": "true"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["evaluation"]["status"] == APPROVED
    assert body["submission"]["status"] == "queued"
    assert body["certificate"]["submission_id"] == submission.submission_id
    assert body["certificate"]["certificate_id"]
    assert body["certificate"]["vote_hash"]
    assert body["certificate"]["approval_percentage"] == 0.8
    assert body["certificate"]["decisive_vote_total"] == 5
    assert body["certificate"]["minimum_votes_required"] == 5
    assert body["certificate"]["originality_score"] > 0
    assert body["submission"]["certificate_id"] == body["certificate"]["certificate_id"]
    assert body["evaluation"]["certificate_id"] == body["certificate"]["certificate_id"]
    assert blockchain.get_originality_certificate_for_submission(submission.submission_id) is not None
    assert client.get("/mint-queue").json()["mint_queue"][0]["submission_id"] == submission.submission_id


def test_evaluate_100_percent_original_submission_creates_certificate(
    blockchain,
    submission_image,
    wallets,
):
    client = _client(blockchain)
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    _cast_votes(
        blockchain,
        submission.submission_id,
        [VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL],
    )

    response = client.post(
        f"/submissions/{submission.submission_id}/evaluate",
        data={"automated_originality_passed": "true"},
    )

    assert response.status_code == 200
    body = response.json()
    certificate = body["certificate"]
    assert body["submission"]["status"] == QUEUED
    assert body["submission"]["certificate_id"] == certificate["certificate_id"]
    assert certificate["submission_id"] == submission.submission_id
    assert certificate["approval_percentage"] == 1.0
    assert certificate["decisive_vote_total"] == 5
    assert certificate["vote_hash"]
    assert certificate["minimum_votes_required"] == 5
    assert certificate["originality_score"] > 0


def test_repeated_evaluation_does_not_create_duplicate_certificate(blockchain, submission_image, wallets):
    client = _client(blockchain)
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    _cast_votes(
        blockchain,
        submission.submission_id,
        [VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_NOT_ORIGINAL],
    )

    first_response = client.post(
        f"/submissions/{submission.submission_id}/evaluate",
        data={"automated_originality_passed": "true"},
    )
    second_response = client.post(
        f"/submissions/{submission.submission_id}/evaluate",
        data={"automated_originality_passed": "true"},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 400
    assert second_response.json()["detail"] == "Only pending submissions can be evaluated."
    assert len(blockchain.originality_certificates) == 1


def test_evaluate_rejected_submission_stays_out_of_mint_queue(blockchain, submission_image, wallets):
    client = _client(blockchain)
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    _cast_votes(
        blockchain,
        submission.submission_id,
        [VOTE_NOT_ORIGINAL, VOTE_NOT_ORIGINAL, VOTE_NOT_ORIGINAL, VOTE_NOT_ORIGINAL, VOTE_ORIGINAL],
    )

    response = client.post(
        f"/submissions/{submission.submission_id}/evaluate",
        data={"automated_originality_passed": "true"},
    )

    assert response.status_code == 200
    assert response.json()["submission"]["status"] == REJECTED
    assert response.json()["certificate"] is None
    assert blockchain.get_originality_certificate_for_submission(submission.submission_id) is None
    assert client.get("/mint-queue").json() == {"mint_queue": []}


def test_approved_unminted_submission_appears_in_mint_queue(blockchain, submission_image, wallets):
    client = _client(blockchain)
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    _certify_submission(blockchain, submission)

    response = client.get("/mint-queue")

    assert response.status_code == 200
    assert response.json()["mint_queue"][0]["submission_id"] == submission.submission_id
    assert response.json()["mint_queue"][0]["status"] == "queued"


def test_hard_rejected_submission_cannot_be_evaluated_or_minted(blockchain, submission_image, wallets):
    client = _client(blockchain)
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    blockchain.hard_reject_submission(submission.submission_id, "Duplicate confirmed.")

    evaluate_response = client.post(
        f"/submissions/{submission.submission_id}/evaluate",
        data={"automated_originality_passed": "true"},
    )
    mint_response = client.post(f"/mint-queue/{submission.submission_id}/mint")

    assert evaluate_response.status_code == 400
    assert evaluate_response.json()["detail"] == "Hard rejected submissions cannot be evaluated."
    assert mint_response.status_code == 400
    assert mint_response.json()["detail"] == "Hard rejected submissions cannot be minted."
    assert submission.status == HARD_REJECTED
    assert blockchain.get_originality_certificate_for_submission(submission.submission_id) is None


def test_certificate_lookup_by_submission_id_works(blockchain, submission_image, wallets):
    client = _client(blockchain)
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    _cast_votes(
        blockchain,
        submission.submission_id,
        [VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_NOT_ORIGINAL],
    )
    evaluate_response = client.post(
        f"/submissions/{submission.submission_id}/evaluate",
        data={"automated_originality_passed": "true"},
    )

    response = client.get(f"/submissions/{submission.submission_id}/certificate")

    assert response.status_code == 200
    assert response.json()["certificate"] == evaluate_response.json()["certificate"]
    assert response.json()["certificate"]["originality_score"] > 0


def test_certificate_lookup_by_certificate_id_works(blockchain, submission_image, wallets):
    client = _client(blockchain)
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    _cast_votes(
        blockchain,
        submission.submission_id,
        [VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_NOT_ORIGINAL],
    )
    evaluate_response = client.post(
        f"/submissions/{submission.submission_id}/evaluate",
        data={"automated_originality_passed": "true"},
    )
    certificate_id = evaluate_response.json()["certificate"]["certificate_id"]

    response = client.get(f"/certificates/{certificate_id}")

    assert response.status_code == 200
    assert response.json()["certificate"] == evaluate_response.json()["certificate"]
    assert response.json()["certificate"]["certificate_id"] == certificate_id


def test_pending_submission_certificate_lookup_returns_clear_404(
    blockchain,
    submission_image,
    wallets,
):
    client = _client(blockchain)
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)

    response = client.get(f"/submissions/{submission.submission_id}/certificate")

    assert response.status_code == 404
    assert response.json()["detail"] == (
        f"Originality certificate not found for submission: {submission.submission_id}"
    )


def test_missing_certificate_id_returns_clear_404(blockchain):
    client = _client(blockchain)

    response = client.get("/certificates/missing-certificate")

    assert response.status_code == 404
    assert response.json()["detail"] == "Originality certificate not found: missing-certificate"


def test_mint_queued_submission_creates_block_and_marks_minted(blockchain, submission_image, wallets):
    client = _client(blockchain)
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    certificate = _certify_submission(blockchain, submission)
    blockchain.add_to_mint_queue(submission.submission_id)
    starting_chain_length = len(blockchain.chain)

    response = client.post(f"/mint-queue/{submission.submission_id}/mint")

    assert response.status_code == 200
    body = response.json()
    assert body["minted"] is True
    assert body["submission"]["status"] == MINTED
    assert len(blockchain.chain) == starting_chain_length + 1
    assert body["block"]["meme"]["text"] == submission.text_content
    assert body["block"]["certificate_id"] == certificate.certificate_id
    assert body["block"]["submission_id"] == submission.submission_id
    assert body["block"]["content_hash"] == submission.content_hash
    assert body["block"]["originality_score"] == certificate.originality_score
    assert client.get("/mint-queue").json() == {"mint_queue": []}


def test_approved_submission_without_certificate_cannot_mint(blockchain, submission_image, wallets):
    client = _client(blockchain)
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    submission.transition_to(APPROVED)

    response = client.post(f"/mint-queue/{submission.submission_id}/mint")

    assert response.status_code == 400
    assert response.json()["detail"] == "Originality certificate is required before minting."
    assert submission.status == APPROVED
    assert len(blockchain.chain) == 1


def test_mint_queue_excludes_approved_submission_missing_certificate(
    blockchain,
    submission_image,
    wallets,
):
    client = _client(blockchain)
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    submission.transition_to(APPROVED)

    response = client.get("/mint-queue")

    assert response.status_code == 200
    assert response.json() == {"mint_queue": []}
    assert submission.status == APPROVED
    assert submission.certificate_id is None


def test_mint_queue_repairs_stale_queued_submission_missing_certificate(
    blockchain,
    submission_image,
    wallets,
):
    client = _client(blockchain)
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    submission.transition_to(APPROVED)
    submission.transition_to(QUEUED)
    blockchain.mint_queue.append(submission.submission_id)

    response = client.get("/mint-queue")

    assert response.status_code == 200
    body = response.json()["mint_queue"][0]
    assert body["mintable"] is False
    assert body["mint_block_reason"] == "certificate_missing"
    assert body["submission_id"] == submission.submission_id
    assert blockchain.mint_queue == [submission.submission_id]
    assert submission.status == APPROVED
    assert submission.certificate_id is None


def test_block_and_unblock_minting_updates_queue_state(blockchain, submission_image, wallets):
    client = _client(blockchain)
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    _certify_submission(blockchain, submission)
    blockchain.add_to_mint_queue(submission.submission_id)

    block_response = client.post(
        f"/submissions/{submission.submission_id}/block-minting",
        json={"reason": "legacy bad item", "notes": "quarantine test"},
    )
    assert block_response.status_code == 200
    queue_item = client.get("/mint-queue").json()["mint_queue"][0]
    assert queue_item["mintable"] is False
    assert queue_item["mint_block_reason"] == "legacy bad item"
    assert queue_item["mint_blocked"] is True

    unblock_response = client.post(f"/submissions/{submission.submission_id}/unblock-minting")
    assert unblock_response.status_code == 200
    queue_item = client.get("/mint-queue").json()["mint_queue"][0]
    assert queue_item["mintable"] is True
    assert queue_item["mint_block_reason"] is None
    assert queue_item["mint_blocked"] is False


def test_cleanup_bad_mint_queue_items_reports_and_blocks_when_requested(blockchain, submission_image, wallets):
    client = _client(blockchain)
    bad_submission = _submission(blockchain, submission_image, wallets["owner"].public_key, "Bad item")
    _certify_submission(blockchain, bad_submission)
    blockchain.add_to_mint_queue(bad_submission.submission_id)
    blockchain.content_objects = []

    dry_run_response = client.post(
        "/dev/mint-queue/cleanup-bad-items",
        json={"dry_run": True, "block_unmintable": False},
    )
    assert dry_run_response.status_code == 200
    dry_run_body = dry_run_response.json()
    assert dry_run_body["blocked"] >= 1
    assert dry_run_body["items"][0]["reason"] == "content_metadata_missing"
    assert bad_submission.mint_blocked is False

    block_response = client.post(
        "/dev/mint-queue/cleanup-bad-items",
        json={"dry_run": False, "block_unmintable": True},
    )
    assert block_response.status_code == 200
    assert bad_submission.mint_blocked is True
    assert bad_submission.mint_block_reason == "content_metadata_missing"


def test_good_item_can_mint_while_bad_item_remains_blocked(blockchain, submission_image, wallets):
    client = _client(blockchain)
    bad_submission = _submission(blockchain, submission_image, wallets["owner"].public_key, "Bad first item")
    _certify_submission(blockchain, bad_submission)
    blockchain.add_to_mint_queue(bad_submission.submission_id)
    blockchain.content_objects = []

    good_submission = _submission(blockchain, submission_image, wallets["owner"].public_key, "Good second item")
    _certify_submission(blockchain, good_submission)
    blockchain.add_to_mint_queue(good_submission.submission_id)

    response = client.post(f"/mint/{good_submission.submission_id}")
    assert response.status_code == 200
    assert response.json()["minted"] is True
    assert response.json()["submission"]["status"] == MINTED
    assert bad_submission.submission_id in blockchain.mint_queue
    assert good_submission.submission_id not in blockchain.mint_queue


def test_dev_repair_certificate_creates_certificate_for_old_approved_submission(
    blockchain,
    submission_image,
    wallets,
):
    client = _client(blockchain)
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    _cast_votes(
        blockchain,
        submission.submission_id,
        [VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL],
    )
    submission.transition_to(APPROVED)

    response = client.post(f"/dev/submissions/{submission.submission_id}/repair-certificate")

    assert response.status_code == 200
    body = response.json()
    certificate = body["certificate"]
    certificate_id = certificate["certificate_id"]
    assert body["submission"]["status"] == APPROVED
    assert body["submission"]["certificate_id"] == certificate_id
    assert certificate["submission_id"] == submission.submission_id
    assert certificate["vote_hash"]
    assert certificate["approval_percentage"] == 1.0
    assert certificate["decisive_vote_total"] == 5
    assert certificate["originality_score"] > 0
    assert client.get(f"/submissions/{submission.submission_id}/certificate").status_code == 200
    assert client.get(f"/certificates/{certificate_id}").status_code == 200

    mint_queue = client.get("/mint-queue")

    assert mint_queue.status_code == 200
    assert mint_queue.json()["mint_queue"][0]["submission_id"] == submission.submission_id
    assert mint_queue.json()["mint_queue"][0]["certificate_id"] == certificate_id


def test_dev_repair_certificate_rejects_old_approved_submission_without_votes(
    blockchain,
    submission_image,
    wallets,
):
    client = _client(blockchain)
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    submission.transition_to(APPROVED)

    response = client.post(f"/dev/submissions/{submission.submission_id}/repair-certificate")

    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot repair certificate: finalized vote data is missing."
    assert blockchain.get_originality_certificate_for_submission(submission.submission_id) is None
    assert client.get("/mint-queue").json() == {"mint_queue": []}


def test_evaluation_rolls_back_when_certificate_creation_fails(
    blockchain,
    submission_image,
    wallets,
    monkeypatch,
):
    client = _client(blockchain)
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    _cast_votes(
        blockchain,
        submission.submission_id,
        [VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL],
    )

    def fail_certificate_creation(*args, **kwargs):
        raise ValueError("certificate storage unavailable")

    monkeypatch.setattr(blockchain, "create_originality_certificate", fail_certificate_creation)

    response = client.post(
        f"/submissions/{submission.submission_id}/evaluate",
        data={"automated_originality_passed": "true"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Originality certificate creation failed: certificate storage unavailable"
    )
    assert submission.status == PENDING
    assert submission.certificate_id is None
    assert blockchain.originality_certificates == []
    assert blockchain.mint_queue == []
    assert client.get("/mint-queue").json() == {"mint_queue": []}


def test_mint_rejects_pending_rejected_and_already_minted_submissions(blockchain, submission_image, wallets):
    client = _client(blockchain)
    pending = _submission(blockchain, submission_image, wallets["owner"].public_key, "Pending")
    rejected = _submission(blockchain, submission_image, wallets["owner"].public_key, "Rejected")
    rejected.transition_to(REJECTED)
    minted = _submission(blockchain, submission_image, wallets["owner"].public_key, "Minted")
    _certify_submission(blockchain, minted)
    blockchain.add_to_mint_queue(minted.submission_id)
    assert client.post(f"/mint-queue/{minted.submission_id}/mint").status_code == 200

    pending_response = client.post(f"/mint-queue/{pending.submission_id}/mint")
    rejected_response = client.post(f"/mint-queue/{rejected.submission_id}/mint")
    minted_again_response = client.post(f"/mint-queue/{minted.submission_id}/mint")

    assert pending.status == PENDING
    assert pending_response.status_code == 400
    assert pending_response.json()["detail"] == "Only approved unminted submissions can be minted."
    assert rejected_response.status_code == 400
    assert rejected_response.json()["detail"] == "Only approved unminted submissions can be minted."
    assert minted_again_response.status_code == 400
    assert minted_again_response.json()["detail"] == "Submission has already been minted."


def test_http_exception_status_and_message_are_preserved(blockchain):
    client = _client(blockchain)

    response = client.get("/submissions/missing-submission")

    assert response.status_code == 404
    assert response.json()["detail"] == "Submission not found: missing-submission"
