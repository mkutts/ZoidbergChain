from fastapi.testclient import TestClient
from eth_account import Account
from eth_account.messages import encode_defunct

import blockchain as blockchain_module

from submission import VOTE_NOT_ORIGINAL, VOTE_ORIGINAL, VOTE_UNSURE
from wallet_auth import WalletAuthManager


def _client(blockchain):
    import api

    api.limiter.reset()
    api.blockchain = blockchain
    api.wallet_auth_manager = WalletAuthManager(
        network_name=api.NETWORK_NAME,
        environment=api.ENVIRONMENT,
    )
    return TestClient(api.app)


def _configure_voter_rewards(
    monkeypatch,
    *,
    enabled=True,
    pool="1",
    max_per_wallet="1",
    min_decisive_votes=1,
    require_review=False,
):
    monkeypatch.setattr(blockchain_module, "VOTER_REWARDS_ENABLED", enabled)
    monkeypatch.setattr(blockchain_module, "VOTER_REWARD_POOL_PER_DECISION_ZOID", pool)
    monkeypatch.setattr(blockchain_module, "VOTER_REWARD_MAX_PER_WALLET_ZOID", max_per_wallet)
    monkeypatch.setattr(blockchain_module, "VOTER_REWARD_MIN_DECISIVE_VOTES", min_decisive_votes)
    monkeypatch.setattr(blockchain_module, "VOTER_REWARD_REQUIRE_REVIEW_ELIGIBLE", require_review)


def _clear_review_policy_env(monkeypatch):
    for name in [
        "REVIEW_ELIGIBILITY_MODE",
        "REVIEW_ALLOWLIST_WALLETS",
        "REVIEW_DENYLIST_WALLETS",
        "MIN_REVIEWER_ACCOUNT_AGE_SECONDS",
        "MIN_REVIEWER_SUBMISSION_COUNT",
        "MIN_REVIEWER_VOTE_COUNT",
        "MIN_REVIEWER_REWARD_COUNT",
        "MIN_REVIEWER_SETTLED_BALANCE_ZOID",
        "MIN_REVIEWER_SETTLED_TRANSFER_COUNT",
        "MAX_REVIEW_VOTES_PER_WALLET_PER_DAY",
        "REVIEW_POLICY_PUBLIC_LABEL",
        "PEER_SHARED_SECRET",
    ]:
        monkeypatch.delenv(name, raising=False)


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


def _upload_text_content_via_api(client, submitter, text):
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


def _submit_signed_content_via_api(client, account, headers, *, content_hash, content_id, caption):
    challenge = client.post(
        "/auth/wallet/submission-challenge",
        json={
            "wallet_address": account.address,
            "content_hash": content_hash,
            "content_id": content_id,
            "caption": caption,
        },
        headers=headers,
    )
    assert challenge.status_code == 200
    response = client.post(
        "/submit_content",
        data={
            "wallet_address": account.address,
            "content_hash": content_hash,
            "content_id": content_id,
            "caption": caption,
            "message": challenge.json()["message"],
            "signature": _sign_message(challenge.json()["message"], account),
        },
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()["submission"]


def _submit_signed_text_submission(client, account, headers, *, text):
    uploaded = _upload_text_content_via_api(client, account.address, text)
    return _submit_signed_content_via_api(
        client,
        account,
        headers,
        content_hash=uploaded["content_hash"],
        content_id=uploaded["content_id"],
        caption=text,
    )


def _request_vote_challenge(client, account, headers, submission_id, *, vote_type):
    return client.post(
        "/auth/wallet/vote-challenge",
        json={
            "wallet_address": account.address,
            "submission_id": submission_id,
            "vote": vote_type,
        },
        headers=headers,
    )


def _vote_signed_via_api(client, submission_id, account, headers, *, vote_type):
    challenge = _request_vote_challenge(
        client,
        account,
        headers,
        submission_id,
        vote_type=vote_type,
    )
    assert challenge.status_code == 200
    response = client.post(
        f"/submissions/{submission_id}/vote",
        data={
            "wallet_address": account.address,
            "vote_type": vote_type,
            "message": challenge.json()["message"],
            "signature": _sign_message(challenge.json()["message"], account),
        },
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()["vote"]


def _cast_signed_votes(client, submission_id, voters_and_votes):
    for account, headers, vote_type in voters_and_votes:
        vote = _vote_signed_via_api(
            client,
            submission_id,
            account,
            headers,
            vote_type=vote_type,
        )
        assert vote["vote_type"] == vote_type


def _generate_wallet_via_api(client):
    response = client.post("/generate_wallet")
    assert response.status_code == 200
    return response.json()["wallet"]["public_key"]


def _mint_submission_via_api(client, submission_id):
    response = client.post(
        f"/mint-queue/{submission_id}/mint",
        data={"miner": _generate_wallet_via_api(client)},
    )
    assert response.status_code == 200
    return response.json()


def test_task_10_3_reward_flows_cover_approved_rejected_and_idempotency(blockchain, monkeypatch):
    _configure_voter_rewards(monkeypatch, pool="1", max_per_wallet="1", require_review=False)
    _clear_review_policy_env(monkeypatch)
    monkeypatch.setenv("REVIEW_ELIGIBILITY_MODE", "open")
    client = _client(blockchain)

    approved_creator = _create_metamask_account()
    approved_creator_headers = _verify_wallet_session(client, approved_creator)
    approved_majority_voters = [(_create_metamask_account(), None) for _ in range(4)]
    approved_majority_voters = [
        (account, _verify_wallet_session(client, account))
        for account, _ in approved_majority_voters
    ]
    approved_unsure = _create_metamask_account()
    approved_unsure_headers = _verify_wallet_session(client, approved_unsure)
    approved_minority = _create_metamask_account()
    approved_minority_headers = _verify_wallet_session(client, approved_minority)

    approved_submission = _submit_signed_text_submission(
        client,
        approved_creator,
        approved_creator_headers,
        text="task 10.3 approved original reward flow",
    )
    _cast_signed_votes(
        client,
        approved_submission["submission_id"],
        [
            (approved_majority_voters[0][0], approved_majority_voters[0][1], VOTE_ORIGINAL),
            (approved_majority_voters[1][0], approved_majority_voters[1][1], VOTE_ORIGINAL),
            (approved_majority_voters[2][0], approved_majority_voters[2][1], VOTE_ORIGINAL),
            (approved_majority_voters[3][0], approved_majority_voters[3][1], VOTE_ORIGINAL),
            (approved_unsure, approved_unsure_headers, VOTE_UNSURE),
            (approved_minority, approved_minority_headers, VOTE_NOT_ORIGINAL),
        ],
    )

    approved_evaluate = client.post(
        f"/submissions/{approved_submission['submission_id']}/evaluate",
        data={"automated_originality_passed": "true"},
    )
    assert approved_evaluate.status_code == 200
    approved_pending = client.get(
        f"/submissions/{approved_submission['submission_id']}/voter-rewards"
    ).json()
    assert approved_pending["reward_status"] == "pending"
    assert approved_pending["final_majority_side"] == "original"
    assert approved_pending["rewarded_voter_count"] == 0
    assert approved_pending["pending_voter_count"] == 4

    approved_minted = _mint_submission_via_api(client, approved_submission["submission_id"])
    approved_summary = client.get(
        f"/submissions/{approved_submission['submission_id']}/voter-rewards"
    ).json()
    assert approved_summary["reward_status"] == "finalized"
    assert approved_summary["rewarded_voter_count"] == 4
    assert approved_summary["pending_voter_count"] == 0
    assert len(approved_summary["reward_records"]) == 4
    assert approved_summary["pending_reward_records"] == []

    approved_creator_rewards = client.get(f"/accounts/{approved_creator.address}/rewards").json()["rewards"]
    assert len(approved_creator_rewards) == 1
    assert approved_creator_rewards[0]["reward_type"] == "meme_mining_reward"

    for account, _headers in approved_majority_voters:
        rewards = client.get(f"/accounts/{account.address}/rewards").json()["rewards"]
        assert len(rewards) == 1
        assert rewards[0]["reward_type"] == "voter_majority_reward"
        assert rewards[0]["submission_id"] == approved_submission["submission_id"]
        assert rewards[0]["final_decision"] == "original"
        assert rewards[0]["vote_choice"] == VOTE_ORIGINAL
        assert rewards[0]["block_hash"] == approved_minted["block"]["hash"]
        assert rewards[0]["block_height"] == approved_minted["block"]["index"]

    assert client.get(f"/accounts/{approved_unsure.address}/rewards").json()["rewards"] == []
    assert client.get(f"/accounts/{approved_minority.address}/rewards").json()["rewards"] == []

    second_mint = client.post(
        f"/mint-queue/{approved_submission['submission_id']}/mint",
        data={"miner": _generate_wallet_via_api(client)},
    )
    assert second_mint.status_code == 400
    approved_summary_after_retry = client.get(
        f"/submissions/{approved_submission['submission_id']}/voter-rewards"
    ).json()
    assert approved_summary_after_retry["rewarded_voter_count"] == 4
    assert approved_summary_after_retry["pending_voter_count"] == 0
    for account, _headers in approved_majority_voters:
        rewards = client.get(f"/accounts/{account.address}/rewards").json()["rewards"]
        assert len(rewards) == 1

    rejected_creator = _create_metamask_account()
    rejected_creator_headers = _verify_wallet_session(client, rejected_creator)
    rejected_majority_voters = [(_create_metamask_account(), None) for _ in range(4)]
    rejected_majority_voters = [
        (account, _verify_wallet_session(client, account))
        for account, _ in rejected_majority_voters
    ]
    rejected_unsure = _create_metamask_account()
    rejected_unsure_headers = _verify_wallet_session(client, rejected_unsure)
    rejected_minority = _create_metamask_account()
    rejected_minority_headers = _verify_wallet_session(client, rejected_minority)

    rejected_submission = _submit_signed_text_submission(
        client,
        rejected_creator,
        rejected_creator_headers,
        text="task 10.3 rejected reward delay flow",
    )
    _cast_signed_votes(
        client,
        rejected_submission["submission_id"],
        [
            (rejected_majority_voters[0][0], rejected_majority_voters[0][1], VOTE_NOT_ORIGINAL),
            (rejected_majority_voters[1][0], rejected_majority_voters[1][1], VOTE_NOT_ORIGINAL),
            (rejected_majority_voters[2][0], rejected_majority_voters[2][1], VOTE_NOT_ORIGINAL),
            (rejected_majority_voters[3][0], rejected_majority_voters[3][1], VOTE_NOT_ORIGINAL),
            (rejected_unsure, rejected_unsure_headers, VOTE_UNSURE),
            (rejected_minority, rejected_minority_headers, VOTE_ORIGINAL),
        ],
    )

    rejected_evaluate = client.post(
        f"/submissions/{rejected_submission['submission_id']}/evaluate",
        data={"automated_originality_passed": "true"},
    )
    assert rejected_evaluate.status_code == 200
    rejected_pending = client.get(
        f"/submissions/{rejected_submission['submission_id']}/voter-rewards"
    ).json()
    assert rejected_pending["reward_status"] == "pending"
    assert rejected_pending["final_majority_side"] == "not_original"
    assert rejected_pending["rewarded_voter_count"] == 0
    assert rejected_pending["pending_voter_count"] == 4
    assert client.get(f"/accounts/{rejected_creator.address}/rewards").json()["rewards"] == []
    for account, _headers in rejected_majority_voters:
        assert client.get(f"/accounts/{account.address}/rewards").json()["rewards"] == []
    assert client.get(f"/accounts/{rejected_unsure.address}/rewards").json()["rewards"] == []
    assert client.get(f"/accounts/{rejected_minority.address}/rewards").json()["rewards"] == []

    settlement_creator = _create_metamask_account()
    settlement_creator_headers = _verify_wallet_session(client, settlement_creator)
    settlement_majority_voters = [(_create_metamask_account(), None) for _ in range(4)]
    settlement_majority_voters = [
        (account, _verify_wallet_session(client, account))
        for account, _ in settlement_majority_voters
    ]
    settlement_minority = _create_metamask_account()
    settlement_minority_headers = _verify_wallet_session(client, settlement_minority)

    settlement_submission = _submit_signed_text_submission(
        client,
        settlement_creator,
        settlement_creator_headers,
        text="task 10.3 delayed rejection settlement trigger",
    )
    _cast_signed_votes(
        client,
        settlement_submission["submission_id"],
        [
            (settlement_majority_voters[0][0], settlement_majority_voters[0][1], VOTE_ORIGINAL),
            (settlement_majority_voters[1][0], settlement_majority_voters[1][1], VOTE_ORIGINAL),
            (settlement_majority_voters[2][0], settlement_majority_voters[2][1], VOTE_ORIGINAL),
            (settlement_majority_voters[3][0], settlement_majority_voters[3][1], VOTE_ORIGINAL),
            (settlement_minority, settlement_minority_headers, VOTE_NOT_ORIGINAL),
        ],
    )
    settlement_evaluate = client.post(
        f"/submissions/{settlement_submission['submission_id']}/evaluate",
        data={"automated_originality_passed": "true"},
    )
    assert settlement_evaluate.status_code == 200
    blockchain.reward_pool = 20.0
    _mint_submission_via_api(client, settlement_submission["submission_id"])

    rejected_summary = client.get(
        f"/submissions/{rejected_submission['submission_id']}/voter-rewards"
    ).json()
    assert rejected_summary["reward_status"] == "finalized"
    assert rejected_summary["rewarded_voter_count"] == 4
    assert rejected_summary["pending_voter_count"] == 0
    assert len(rejected_summary["reward_records"]) == 4
    assert rejected_summary["pending_reward_records"] == []
    for account, _headers in rejected_majority_voters:
        rewards = client.get(f"/accounts/{account.address}/rewards").json()["rewards"]
        matching_rewards = [
            reward
            for reward in rewards
            if reward["submission_id"] == rejected_submission["submission_id"]
        ]
        assert len(matching_rewards) == 1
        assert matching_rewards[0]["reward_type"] == "voter_majority_reward"
        assert matching_rewards[0]["final_decision"] == "not_original"
        assert matching_rewards[0]["vote_choice"] == VOTE_NOT_ORIGINAL


def test_task_10_3_review_eligibility_still_gates_votes_and_rewards(blockchain, monkeypatch):
    _clear_review_policy_env(monkeypatch)
    _configure_voter_rewards(monkeypatch, pool="1", max_per_wallet="1", require_review=False)
    monkeypatch.setenv("REVIEW_ELIGIBILITY_MODE", "allowlist")
    client = _client(blockchain)

    allowlist_creator = _create_metamask_account()
    allowlist_creator_headers = _verify_wallet_session(client, allowlist_creator)
    allowlisted_voter = _create_metamask_account()
    allowlisted_headers = _verify_wallet_session(client, allowlisted_voter)
    blocked_voter = _create_metamask_account()
    blocked_headers = _verify_wallet_session(client, blocked_voter)

    allowlist_submission = _submit_signed_text_submission(
        client,
        allowlist_creator,
        allowlist_creator_headers,
        text="task 10.3 allowlist policy gating",
    )

    monkeypatch.setenv("REVIEW_ALLOWLIST_WALLETS", allowlisted_voter.address)
    allowed_vote = _vote_signed_via_api(
        client,
        allowlist_submission["submission_id"],
        allowlisted_voter,
        allowlisted_headers,
        vote_type=VOTE_ORIGINAL,
    )
    assert allowed_vote["vote_type"] == VOTE_ORIGINAL

    blocked_vote = _request_vote_challenge(
        client,
        blocked_voter,
        blocked_headers,
        allowlist_submission["submission_id"],
        vote_type=VOTE_ORIGINAL,
    )
    assert blocked_vote.status_code == 403
    assert blocked_vote.json()["detail"]["reason"] == "wallet_not_allowlisted"

    _clear_review_policy_env(monkeypatch)
    _configure_voter_rewards(monkeypatch, pool="1", max_per_wallet="1", require_review=True)
    monkeypatch.setenv("REVIEW_ELIGIBILITY_MODE", "open")

    reward_creator = _create_metamask_account()
    reward_creator_headers = _verify_wallet_session(client, reward_creator)
    majority_voters = [(_create_metamask_account(), None) for _ in range(4)]
    majority_voters = [
        (account, _verify_wallet_session(client, account))
        for account, _ in majority_voters
    ]
    minority_voter = _create_metamask_account()
    minority_headers = _verify_wallet_session(client, minority_voter)

    reward_submission = _submit_signed_text_submission(
        client,
        reward_creator,
        reward_creator_headers,
        text="task 10.3 review-eligible reward filter",
    )
    _cast_signed_votes(
        client,
        reward_submission["submission_id"],
        [
            (majority_voters[0][0], majority_voters[0][1], VOTE_ORIGINAL),
            (majority_voters[1][0], majority_voters[1][1], VOTE_ORIGINAL),
            (majority_voters[2][0], majority_voters[2][1], VOTE_ORIGINAL),
            (majority_voters[3][0], majority_voters[3][1], VOTE_ORIGINAL),
            (minority_voter, minority_headers, VOTE_NOT_ORIGINAL),
        ],
    )

    monkeypatch.setenv("REVIEW_DENYLIST_WALLETS", majority_voters[0][0].address)
    evaluate_response = client.post(
        f"/submissions/{reward_submission['submission_id']}/evaluate",
        data={"automated_originality_passed": "true"},
    )
    assert evaluate_response.status_code == 200

    _mint_submission_via_api(client, reward_submission["submission_id"])
    reward_summary = client.get(
        f"/submissions/{reward_submission['submission_id']}/voter-rewards"
    ).json()
    assert reward_summary["reward_status"] == "finalized"
    assert reward_summary["rewarded_voter_count"] == 3
    assert reward_summary["pending_voter_count"] == 0
    assert float(reward_summary["reward_amount_per_voter"]) == 0.333333

    denylisted_rewards = client.get(
        f"/accounts/{majority_voters[0][0].address}/rewards"
    ).json()["rewards"]
    assert denylisted_rewards == []
    for account, _headers in majority_voters[1:]:
        rewards = client.get(f"/accounts/{account.address}/rewards").json()["rewards"]
        assert len(rewards) == 1
        assert rewards[0]["reward_type"] == "voter_majority_reward"
        assert rewards[0]["submission_id"] == reward_submission["submission_id"]
