from fastapi.testclient import TestClient

from submission import APPROVED, HARD_REJECTED, MINTED, PENDING, REJECTED, VOTE_NOT_ORIGINAL, VOTE_ORIGINAL


def _client(blockchain):
    import api

    api.blockchain = blockchain
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
    assert blockchain.get_originality_certificate_for_submission(submission.submission_id) is not None
    assert client.get("/mint-queue").json()["mint_queue"][0]["submission_id"] == submission.submission_id


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
    submission.transition_to(APPROVED)

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
    submission.transition_to(APPROVED)
    blockchain.add_to_mint_queue(submission.submission_id)
    starting_chain_length = len(blockchain.chain)

    response = client.post(f"/mint-queue/{submission.submission_id}/mint")

    assert response.status_code == 200
    body = response.json()
    assert body["minted"] is True
    assert body["submission"]["status"] == MINTED
    assert len(blockchain.chain) == starting_chain_length + 1
    assert body["block"]["meme"]["text"] == submission.text_content
    assert client.get("/mint-queue").json() == {"mint_queue": []}


def test_mint_rejects_pending_rejected_and_already_minted_submissions(blockchain, submission_image, wallets):
    client = _client(blockchain)
    pending = _submission(blockchain, submission_image, wallets["owner"].public_key, "Pending")
    rejected = _submission(blockchain, submission_image, wallets["owner"].public_key, "Rejected")
    rejected.transition_to(REJECTED)
    minted = _submission(blockchain, submission_image, wallets["owner"].public_key, "Minted")
    minted.transition_to(APPROVED)
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
