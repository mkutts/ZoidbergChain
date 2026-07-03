from fastapi.testclient import TestClient

from peers import PeerStore
from submission import VOTE_ORIGINAL


def _client(blockchain):
    import api

    api.blockchain = blockchain
    api.peer_store = PeerStore()
    return TestClient(api.app)


def test_valid_submission_request_succeeds(blockchain, submission_image, wallets):
    client = _client(blockchain)
    with open(submission_image, "rb") as image_file:
        response = client.post(
            "/submit_content",
            data={
                "submitter": wallets["owner"].public_key,
                "text_content": "Validation hardening submission",
            },
            files={"image": ("validation.jpg", image_file, "image/jpeg")},
        )

    assert response.status_code == 200
    assert response.json()["submission"]["submitter"] == wallets["owner"].public_key


def test_missing_submission_required_field_fails_clearly(blockchain, submission_image):
    client = _client(blockchain)
    with open(submission_image, "rb") as image_file:
        response = client.post(
            "/submit_content",
            data={"text_content": "Missing submitter"},
            files={"image": ("validation.jpg", image_file, "image/jpeg")},
        )

    assert response.status_code == 422


def test_oversized_submission_text_fails_clearly(blockchain, submission_image, wallets):
    client = _client(blockchain)
    with open(submission_image, "rb") as image_file:
        response = client.post(
            "/submit_content",
            data={
                "submitter": wallets["owner"].public_key,
                "text_content": "x" * 5000,
            },
            files={"image": ("validation.jpg", image_file, "image/jpeg")},
        )

    assert response.status_code == 422


def test_invalid_vote_value_rejected(blockchain, submission_image, wallets):
    client = _client(blockchain)
    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Vote validation",
        submitter=wallets["owner"].public_key,
    )

    response = client.post(
        f"/submissions/{submission.submission_id}/vote",
        data={
            "voter": wallets["contributor_one"].public_key,
            "vote_type": "maybe",
        },
    )

    assert response.status_code == 422


def test_missing_voter_rejected(blockchain, submission_image, wallets):
    client = _client(blockchain)
    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Vote validation",
        submitter=wallets["owner"].public_key,
    )

    response = client.post(
        f"/submissions/{submission.submission_id}/vote",
        data={"vote_type": VOTE_ORIGINAL},
    )

    assert response.status_code == 422


def test_malformed_wallet_public_key_rejected(blockchain):
    client = _client(blockchain)

    response = client.post(
        "/add_transaction",
        params={
            "sender": "bad-public-key",
            "recipient": "also-bad",
            "amount": "1",
            "private_key": "too-short",
        },
    )

    assert response.status_code == 422


def test_malformed_peer_registration_rejected(blockchain):
    client = _client(blockchain)

    response = client.post(
        "/peers/register",
        json={
            "node_id": "bad node id",
            "url": "http://peer-one.test:8000",
            "network_name": "zoidberg-testnet",
        },
    )

    assert response.status_code == 422


def test_invalid_peer_url_rejected(blockchain):
    client = _client(blockchain)

    response = client.post(
        "/peers/register",
        json={
            "node_id": "peer-node-1",
            "url": "not-a-url",
            "network_name": "zoidberg-testnet",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Peer URL must be a valid http or https URL."


def test_malformed_peer_submission_rejected_and_state_not_mutated(blockchain):
    client = _client(blockchain)
    starting_count = len(blockchain.submissions)

    response = client.post(
        "/peers/submissions/receive",
        json={
            "origin_node_id": "peer-node-1",
            "network_name": "zoidberg-testnet",
            "submission": {
                "submission_id": "submission-1",
                "image_path": "peer-submissions/meme.jpg",
                "text_content": "Peer submission",
                "submitter": "bad-public-key",
                "private_key": "leak-me",
                "created_at": 1_000_000.0,
            },
        },
    )

    assert response.status_code == 422
    assert len(blockchain.submissions) == starting_count


def test_malformed_peer_vote_rejected_and_state_not_mutated(blockchain, submission_image, wallets):
    client = _client(blockchain)
    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Peer vote validation",
        submitter=wallets["owner"].public_key,
    )
    starting_votes = len(blockchain.votes)

    response = client.post(
        "/peers/votes/receive",
        json={
            "origin_node_id": "peer-node-1",
            "network_name": "zoidberg-testnet",
            "submission_id": submission.submission_id,
            "voter": wallets["contributor_one"].public_key,
            "vote_type": "maybe",
            "created_at": 1_000_000.0,
        },
    )

    assert response.status_code == 422
    assert len(blockchain.votes) == starting_votes


def test_malformed_peer_block_rejected_and_chain_not_mutated(blockchain, submission_image, wallets):
    client = _client(blockchain)
    starting_height = len(blockchain.chain)

    response = client.post(
        "/peers/blocks/receive",
        json={
            "origin_node_id": "peer-node-1",
            "network_name": "zoidberg-testnet",
            "block": {
                "index": 1,
                "previous_hash": "bad-hash",
                "timestamp": 1_000_000.0,
                "transactions": [],
                "miner": wallets["owner"].public_key,
                "meme": {"text": "bad block"},
                "hash": "also-bad",
            },
        },
    )

    assert response.status_code == 422
    assert len(blockchain.chain) == starting_height


def test_malformed_peer_certificate_rejected_and_state_not_mutated(blockchain, submission_image, wallets):
    client = _client(blockchain)
    starting_count = len(blockchain.originality_certificates)

    response = client.post(
        "/peers/certificates/receive",
        json={
            "origin_node_id": "peer-node-1",
            "network_name": "zoidberg-testnet",
            "certificate": {
                "certificate_id": "bad",
                "submission_id": "submission-1",
                "content_hash": "also-bad",
                "creator_wallet": wallets["owner"].public_key,
                "vote_total": 1,
                "decisive_vote_total": 1,
                "original_votes": 1,
                "not_original_votes": 0,
                "unsure_votes": 0,
                "approval_percentage": 1.0,
                "minimum_votes_required": 5,
                "approved_at": 1_000_000.0,
                "network_name": "zoidberg-testnet",
                "issuing_node_id": "peer-node-1",
                "vote_hash": "bad",
            },
        },
    )

    assert response.status_code == 422
    assert len(blockchain.originality_certificates) == starting_count
