from fastapi.testclient import TestClient

from submission import (
    APPROVED,
    HARD_REJECTED,
    MINTED,
    PENDING,
    QUEUED,
    REJECTED,
    VOTE_NOT_ORIGINAL,
    VOTE_ORIGINAL,
)


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
    assert response.json() == {"mint_queue": []}
    assert blockchain.mint_queue == []
    assert submission.status == APPROVED
    assert submission.certificate_id is None


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
