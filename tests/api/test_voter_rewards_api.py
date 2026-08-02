import pytest

import blockchain as blockchain_module

from test_submission_lifecycle_api import (
    VOTE_NOT_ORIGINAL,
    VOTE_ORIGINAL,
    VOTE_UNSURE,
    _client,
    _create_metamask_account,
    _generate_wallet_via_api,
    _submit_signed_content_via_api,
    _upload_text_content_via_api,
    _verify_wallet_session,
    _vote_signed_via_api,
)


def _configure_voter_rewards(
    monkeypatch,
    *,
    enabled=True,
    pool="1",
    max_per_wallet="0",
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


def _mint_submission_via_api(client, submission_id):
    miner = _generate_wallet_via_api(client)
    response = client.post(f"/mint-queue/{submission_id}/mint", data={"miner": miner})
    assert response.status_code == 200
    return response.json()


def _submit_signed_text_submission(client, account, headers, *, text):
    uploaded = _upload_text_content_via_api(client, account.address, text=text)
    return _submit_signed_content_via_api(
        client,
        account,
        headers,
        content_hash=uploaded["content_hash"],
        content_id=uploaded["content_id"],
        caption=text,
    )


def _cast_signed_votes(client, submission_id, voters_and_votes):
    for account, headers, vote_type in voters_and_votes:
        vote = _vote_signed_via_api(client, submission_id, account, headers, vote_type)
        assert vote["vote_type"] == vote_type


def test_approved_submission_rewards_original_majority_voters(blockchain, monkeypatch):
    _configure_voter_rewards(monkeypatch, pool="0.9", require_review=False)
    _clear_review_policy_env(monkeypatch)
    monkeypatch.setenv("PEER_SHARED_SECRET", "super-secret-value")
    client = _client(blockchain)

    creator = _create_metamask_account()
    creator_headers = _verify_wallet_session(client, creator)
    majority_voters = [(_create_metamask_account(), None) for _ in range(3)]
    minority_voter = _create_metamask_account()
    unsure_voter = _create_metamask_account()

    majority_voters = [(account, _verify_wallet_session(client, account)) for account, _ in majority_voters]
    minority_headers = _verify_wallet_session(client, minority_voter)
    unsure_headers = _verify_wallet_session(client, unsure_voter)

    submission = _submit_signed_text_submission(
        client,
        creator,
        creator_headers,
        text="approved voter reward submission",
    )

    _cast_signed_votes(
        client,
        submission["submission_id"],
        [
            *[(account, headers, VOTE_ORIGINAL) for account, headers in majority_voters],
            (minority_voter, minority_headers, VOTE_NOT_ORIGINAL),
            (unsure_voter, unsure_headers, VOTE_UNSURE),
        ],
    )

    evaluate_response = client.post(
        f"/submissions/{submission['submission_id']}/evaluate",
        data={"automated_originality_passed": "true"},
    )
    assert evaluate_response.status_code == 200

    minted = _mint_submission_via_api(client, submission["submission_id"])
    summary_response = client.get(f"/submissions/{submission['submission_id']}/voter-rewards")
    assert summary_response.status_code == 200
    summary = summary_response.json()

    assert minted["block"]["voter_rewards"]
    assert len(minted["block"]["voter_rewards"]) == 3
    assert summary["reward_status"] == "finalized"
    assert summary["final_majority_side"] == "original"
    assert summary["rewarded_voter_count"] == 3
    assert float(summary["reward_amount_per_voter"]) == 0.3
    assert float(summary["total_distributed"]) == 0.9
    assert "super-secret-value" not in str(summary)

    creator_rewards = client.get(f"/accounts/{creator.address}/rewards").json()["rewards"]
    assert len(creator_rewards) == 1
    assert creator_rewards[0]["reward_type"] == "meme_mining_reward"
    assert creator_rewards[0]["reward_recipient"] == creator.address.lower()

    for account, _headers in majority_voters:
        rewards = client.get(f"/accounts/{account.address}/rewards").json()["rewards"]
        assert len(rewards) == 1
        assert rewards[0]["reward_type"] == "voter_majority_reward"
        assert rewards[0]["submission_id"] == submission["submission_id"]
        assert rewards[0]["final_decision"] == "original"
        assert rewards[0]["vote_choice"] == VOTE_ORIGINAL
        assert float(rewards[0]["reward_amount"]) == 0.3

    assert client.get(f"/accounts/{minority_voter.address}/rewards").json()["rewards"] == []
    assert client.get(f"/accounts/{unsure_voter.address}/rewards").json()["rewards"] == []


def test_rejected_submission_rewards_not_original_voters_after_next_mint(blockchain, monkeypatch):
    _configure_voter_rewards(monkeypatch, pool="1", require_review=False)
    _clear_review_policy_env(monkeypatch)
    client = _client(blockchain)

    rejected_creator = _create_metamask_account()
    rejected_creator_headers = _verify_wallet_session(client, rejected_creator)
    rejected_voters = [(_create_metamask_account(), None) for _ in range(3)]
    rejected_voters = [(account, _verify_wallet_session(client, account)) for account, _ in rejected_voters]
    rejected_minority = _create_metamask_account()
    rejected_unsure = _create_metamask_account()
    rejected_minority_headers = _verify_wallet_session(client, rejected_minority)
    rejected_unsure_headers = _verify_wallet_session(client, rejected_unsure)

    rejected_submission = _submit_signed_text_submission(
        client,
        rejected_creator,
        rejected_creator_headers,
        text="rejected voter reward submission",
    )

    _cast_signed_votes(
        client,
        rejected_submission["submission_id"],
        [
            *[(account, headers, VOTE_NOT_ORIGINAL) for account, headers in rejected_voters],
            (rejected_minority, rejected_minority_headers, VOTE_ORIGINAL),
            (rejected_unsure, rejected_unsure_headers, VOTE_UNSURE),
        ],
    )

    rejected_evaluate = client.post(
        f"/submissions/{rejected_submission['submission_id']}/evaluate",
        data={"automated_originality_passed": "true"},
    )
    assert rejected_evaluate.status_code == 200
    assert rejected_evaluate.json()["submission"]["status"] == "rejected"

    pending_summary = client.get(f"/submissions/{rejected_submission['submission_id']}/voter-rewards").json()
    assert pending_summary["reward_status"] == "pending"
    assert pending_summary["final_majority_side"] == "not_original"
    assert pending_summary["pending_voter_count"] == 3

    approved_creator = _create_metamask_account()
    approved_creator_headers = _verify_wallet_session(client, approved_creator)
    approved_submission = _submit_signed_text_submission(
        client,
        approved_creator,
        approved_creator_headers,
        text="approved block for rejected-side settlement",
    )
    approved_voters = [(_create_metamask_account(), None) for _ in range(5)]
    approved_voters = [(account, _verify_wallet_session(client, account)) for account, _ in approved_voters]
    _cast_signed_votes(
        client,
        approved_submission["submission_id"],
        [
            (approved_voters[0][0], approved_voters[0][1], VOTE_ORIGINAL),
            (approved_voters[1][0], approved_voters[1][1], VOTE_ORIGINAL),
            (approved_voters[2][0], approved_voters[2][1], VOTE_ORIGINAL),
            (approved_voters[3][0], approved_voters[3][1], VOTE_ORIGINAL),
            (approved_voters[4][0], approved_voters[4][1], VOTE_NOT_ORIGINAL),
        ],
    )
    approved_evaluate = client.post(
        f"/submissions/{approved_submission['submission_id']}/evaluate",
        data={"automated_originality_passed": "true"},
    )
    assert approved_evaluate.status_code == 200
    minted = _mint_submission_via_api(client, approved_submission["submission_id"])
    assert minted["block"]["voter_rewards"]

    rejected_summary = client.get(f"/submissions/{rejected_submission['submission_id']}/voter-rewards").json()
    assert rejected_summary["reward_status"] == "finalized"
    assert rejected_summary["final_majority_side"] == "not_original"
    assert rejected_summary["rewarded_voter_count"] == 3

    rejected_creator_rewards = client.get(f"/accounts/{rejected_creator.address}/rewards").json()["rewards"]
    assert rejected_creator_rewards == []

    for account, _headers in rejected_voters:
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

    assert client.get(f"/accounts/{rejected_minority.address}/rewards").json()["rewards"] == []
    assert client.get(f"/accounts/{rejected_unsure.address}/rewards").json()["rewards"] == []


def test_voter_reward_cap_and_remainder_are_deterministic_and_not_due_after_mint(blockchain, monkeypatch):
    _configure_voter_rewards(monkeypatch, pool="1", max_per_wallet="0.2", require_review=False)
    _clear_review_policy_env(monkeypatch)
    client = _client(blockchain)

    creator = _create_metamask_account()
    creator_headers = _verify_wallet_session(client, creator)
    voters = [(_create_metamask_account(), None) for _ in range(5)]
    voters = [(account, _verify_wallet_session(client, account)) for account, _ in voters]

    submission = _submit_signed_text_submission(
        client,
        creator,
        creator_headers,
        text="capped voter reward submission",
    )
    _cast_signed_votes(
        client,
        submission["submission_id"],
        [
            (voters[0][0], voters[0][1], VOTE_ORIGINAL),
            (voters[1][0], voters[1][1], VOTE_ORIGINAL),
            (voters[2][0], voters[2][1], VOTE_ORIGINAL),
            (voters[3][0], voters[3][1], VOTE_ORIGINAL),
            (voters[4][0], voters[4][1], VOTE_NOT_ORIGINAL),
        ],
    )

    evaluate_response = client.post(
        f"/submissions/{submission['submission_id']}/evaluate",
        data={"automated_originality_passed": "true"},
    )
    assert evaluate_response.status_code == 200

    pending_summary = client.get(f"/submissions/{submission['submission_id']}/voter-rewards").json()
    assert pending_summary["reward_status"] == "pending"
    assert float(pending_summary["reward_amount_per_voter"]) == 0.2
    assert pending_summary["pending_voter_count"] == 4
    assert float(pending_summary["undistributed_remainder"]) == 0.2

    _mint_submission_via_api(client, submission["submission_id"])
    final_summary = client.get(f"/submissions/{submission['submission_id']}/voter-rewards").json()
    assert final_summary["reward_status"] == "finalized"
    assert final_summary["rewarded_voter_count"] == 4
    assert float(final_summary["reward_amount_per_voter"]) == 0.2
    assert not any(
        record["submission_id"] == submission["submission_id"]
        for record in blockchain._due_voter_reward_records()
    )

    second_mint = client.post(f"/mint-queue/{submission['submission_id']}/mint", data={"miner": _generate_wallet_via_api(client)})
    assert second_mint.status_code == 400


def test_denylisted_majority_voter_is_excluded_when_review_eligibility_is_required(blockchain, monkeypatch):
    _configure_voter_rewards(monkeypatch, pool="1", require_review=True)
    _clear_review_policy_env(monkeypatch)
    monkeypatch.setenv("REVIEW_ELIGIBILITY_MODE", "open")
    client = _client(blockchain)

    creator = _create_metamask_account()
    creator_headers = _verify_wallet_session(client, creator)
    majority_voters = [(_create_metamask_account(), None) for _ in range(4)]
    majority_voters = [(account, _verify_wallet_session(client, account)) for account, _ in majority_voters]
    minority_voter = _create_metamask_account()
    minority_headers = _verify_wallet_session(client, minority_voter)

    submission = _submit_signed_text_submission(
        client,
        creator,
        creator_headers,
        text="denylisted majority voter reward submission",
    )
    _cast_signed_votes(
        client,
        submission["submission_id"],
        [
            *[(account, headers, VOTE_ORIGINAL) for account, headers in majority_voters],
            (minority_voter, minority_headers, VOTE_NOT_ORIGINAL),
        ],
    )

    monkeypatch.setenv("REVIEW_DENYLIST_WALLETS", majority_voters[0][0].address)
    evaluate_response = client.post(
        f"/submissions/{submission['submission_id']}/evaluate",
        data={"automated_originality_passed": "true"},
    )
    assert evaluate_response.status_code == 200

    _mint_submission_via_api(client, submission["submission_id"])
    summary = client.get(f"/submissions/{submission['submission_id']}/voter-rewards").json()
    assert summary["reward_status"] == "finalized"
    assert summary["rewarded_voter_count"] == 3
    assert float(summary["reward_amount_per_voter"]) == 0.333333

    denylisted_rewards = client.get(f"/accounts/{majority_voters[0][0].address}/rewards").json()["rewards"]
    assert denylisted_rewards == []

    for account, _headers in majority_voters[1:]:
        rewards = client.get(f"/accounts/{account.address}/rewards").json()["rewards"]
        assert len(rewards) == 1
        assert rewards[0]["submission_id"] == submission["submission_id"]


def test_block_validation_rejects_duplicate_voter_reward_ids_from_prior_chain(blockchain, monkeypatch):
    _configure_voter_rewards(monkeypatch, pool="1", require_review=False)
    _clear_review_policy_env(monkeypatch)
    client = _client(blockchain)

    creator_one = _create_metamask_account()
    creator_one_headers = _verify_wallet_session(client, creator_one)
    submission_one = _submit_signed_text_submission(
        client,
        creator_one,
        creator_one_headers,
        text="first validated voter reward submission",
    )
    voters_one = [(_create_metamask_account(), None) for _ in range(5)]
    voters_one = [(account, _verify_wallet_session(client, account)) for account, _ in voters_one]
    _cast_signed_votes(
        client,
        submission_one["submission_id"],
        [
            (voters_one[0][0], voters_one[0][1], VOTE_ORIGINAL),
            (voters_one[1][0], voters_one[1][1], VOTE_ORIGINAL),
            (voters_one[2][0], voters_one[2][1], VOTE_ORIGINAL),
            (voters_one[3][0], voters_one[3][1], VOTE_ORIGINAL),
            (voters_one[4][0], voters_one[4][1], VOTE_NOT_ORIGINAL),
        ],
    )
    assert client.post(
        f"/submissions/{submission_one['submission_id']}/evaluate",
        data={"automated_originality_passed": "true"},
    ).status_code == 200
    _mint_submission_via_api(client, submission_one["submission_id"])

    settled_rewards = client.get(f"/submissions/{submission_one['submission_id']}/voter-rewards").json()["reward_records"]
    assert settled_rewards

    creator_two = _create_metamask_account()
    creator_two_headers = _verify_wallet_session(client, creator_two)
    submission_two = _submit_signed_text_submission(
        client,
        creator_two,
        creator_two_headers,
        text="second validated voter reward submission",
    )
    voters_two = [(_create_metamask_account(), None) for _ in range(5)]
    voters_two = [(account, _verify_wallet_session(client, account)) for account, _ in voters_two]
    _cast_signed_votes(
        client,
        submission_two["submission_id"],
        [
            (voters_two[0][0], voters_two[0][1], VOTE_ORIGINAL),
            (voters_two[1][0], voters_two[1][1], VOTE_ORIGINAL),
            (voters_two[2][0], voters_two[2][1], VOTE_ORIGINAL),
            (voters_two[3][0], voters_two[3][1], VOTE_ORIGINAL),
            (voters_two[4][0], voters_two[4][1], VOTE_NOT_ORIGINAL),
        ],
    )
    assert client.post(
        f"/submissions/{submission_two['submission_id']}/evaluate",
        data={"automated_originality_passed": "true"},
    ).status_code == 200

    submission_two_record = blockchain.get_submission(submission_two["submission_id"])
    certificate_two = blockchain.get_originality_certificate_for_submission(submission_two["submission_id"])
    minted_at = 1_786_000_000.0
    reward_metadata = blockchain.build_meme_reward_metadata(
        submission_two_record,
        certificate_two,
        minted_at=minted_at,
    )
    certificate_metadata = blockchain.certificate_block_metadata(certificate_two)
    reward_transactions = [
        {
            "sender": "REWARD_POOL",
            "recipient": reward_metadata["reward_recipient"],
            "amount": reward_metadata["reward_amount"],
            "tip": 0,
            "payload_size_kb": 0,
        },
        *[
            {
                "sender": "REWARD_POOL",
                "recipient": reward["reward_recipient"],
                "amount": reward["reward_amount"],
                "tip": 0,
                "payload_size_kb": 0,
            }
            for reward in settled_rewards
        ],
    ]
    candidate_block = {
        "index": blockchain.get_latest_block().index + 1,
        "previous_hash": blockchain.get_latest_block().hash,
        "timestamp": minted_at,
        "transactions": reward_transactions,
        "miner": _generate_wallet_via_api(client),
        "meme": {"encoded_image": "candidate-image", "text": "candidate block"},
        **certificate_metadata,
        **reward_metadata,
        "voter_rewards": settled_rewards,
    }

    with pytest.raises(blockchain_module.NativeBlockValidationError) as exc_info:
        blockchain.validate_block_certificate_metadata(
            candidate_block,
            prior_chain=blockchain.chain_to_dicts(blockchain.chain),
        )

    assert exc_info.value.code == "duplicate_reward"
