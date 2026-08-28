import requests
from fastapi.testclient import TestClient
from eth_account import Account
from eth_account.messages import encode_defunct

import peer_sync
from peers import PeerStore
from protocol_v1 import PROTOCOL_VERSION, PUBLIC_TESTNET_V1_NETWORK_ID
from protocol_v1_originality import PROTOCOL_V1_VOTE_VERSION, build_protocol_v1_vote_message
from protocol_v1_peer_message import (
    build_protocol_v1_peer_request_headers,
    clear_protocol_v1_peer_replay_store_cache,
)
from submission import APPROVED, VOTE_NOT_ORIGINAL, VOTE_ORIGINAL, VOTE_UNSURE
from wallet_auth import hash_wallet_message


def _client(blockchain):
    import api

    api.NODE_ID = "local-node"
    api.PUBLIC_NODE_URL = "http://localhost:8000"
    api.NETWORK_NAME = "zoidberg-testnet"
    api.blockchain = blockchain
    api.peer_store = PeerStore()
    clear_protocol_v1_peer_replay_store_cache(data_dir=api.peer_store.storage.data_dir)
    return TestClient(api.app)


def _register_peer(node_id="peer-node-1", url="http://peer-one.test:8000"):
    import api

    return api.peer_store.register_peer(
        node_id=node_id,
        url=url,
        network_name="zoidberg-testnet",
    )


def _configure_signed_peer_messages(monkeypatch, secret="super-secret-value"):
    import api

    monkeypatch.setattr(api, "signed_peer_messages_enabled", lambda: True)
    monkeypatch.setattr(api, "peer_auth_required", lambda: False)
    monkeypatch.setattr(api, "peer_shared_secret", lambda: secret)
    monkeypatch.setattr(api, "peer_shared_secret_is_configured", lambda: True)
    monkeypatch.setattr(api, "peer_replay_protection_enabled", lambda: False)
    monkeypatch.setattr(api, "PEER_SIGNATURE_WINDOW_SECONDS", 300)
    monkeypatch.setattr(peer_sync, "signed_peer_messages_enabled", lambda: True)
    monkeypatch.setattr(peer_sync, "peer_auth_required", lambda: False)
    monkeypatch.setattr(peer_sync, "peer_shared_secret", lambda: secret)
    monkeypatch.setattr(peer_sync, "peer_shared_secret_is_configured", lambda: True)
    monkeypatch.setattr(peer_sync, "peer_replay_protection_enabled", lambda: False)
    monkeypatch.setattr(peer_sync, "peer_signature_window_seconds", lambda: 300)
    peer_sync._PEER_NONCE_CACHE.clear()
    clear_protocol_v1_peer_replay_store_cache()


def _freeze_peer_time(monkeypatch, now=1_700_000_000):
    import api

    monkeypatch.setattr(api.time, "time", lambda: now)
    monkeypatch.setattr(peer_sync.time, "time", lambda: now)


def _signed_headers(path, payload, *, secret="super-secret-value", timestamp=1_700_000_000, nonce="nonce-1"):
    return build_protocol_v1_peer_request_headers(
        "POST",
        path,
        payload,
        "peer-node-1",
        network_name="zoidberg-testnet",
        secret=secret,
        timestamp=timestamp,
        nonce=nonce,
    )


def _submission(blockchain, submission_image, submitter, text="Peer vote submission"):
    return blockchain.submit_content(
        image_path=str(submission_image),
        text_content=text,
        submitter=submitter,
    )


def _vote_payload(
    submission_id,
    voter,
    vote_type=VOTE_ORIGINAL,
    origin_node_id="peer-node-1",
    network_name="zoidberg-testnet",
    created_at=1_000_000.0,
):
    return {
        "origin_node_id": origin_node_id,
        "network_name": network_name,
        "submission_id": submission_id,
        "voter": voter,
        "vote_type": vote_type,
        "created_at": created_at,
    }


def _sign_message(message, account):
    signed = Account.sign_message(encode_defunct(text=message), account.key)
    return signed.signature.hex()


def _protocol_v1_signed_vote_payload(
    submission,
    voter_account,
    *,
    vote_type=VOTE_ORIGINAL,
    network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
    nonce="peer-v1-vote-nonce-1",
    issued_at="2026-08-27T12:00:00+00:00",
    expires_at="2026-08-27T12:05:00+00:00",
):
    vote_message = build_protocol_v1_vote_message(
        wallet_address=voter_account.address.lower(),
        network_id=network_id,
        submission_id=submission.submission_id,
        content_hash=submission.content_hash,
        vote_type=vote_type,
        nonce=nonce,
        issued_at=issued_at,
        expires_at=expires_at,
    )
    return {
        **_vote_payload(
            submission.submission_id,
            voter_account.address.lower(),
            vote_type=vote_type,
        ),
        "vote_version": PROTOCOL_V1_VOTE_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "network_id": network_id,
        "content_hash": submission.content_hash,
        "voter_wallet_address": voter_account.address.lower(),
        "signature_scheme": "personal_sign",
        "vote_signature": _sign_message(vote_message, voter_account),
        "vote_message": vote_message,
        "signed_message_hash": hash_wallet_message(vote_message),
        "vote_nonce": nonce,
        "vote_issued_at": issued_at,
        "vote_expires_at": expires_at,
        "signed_at": issued_at,
        "identity_source": "metamask_signed",
    }


def test_receiving_valid_peer_vote(blockchain, submission_image, wallets):
    client = _client(blockchain)
    _register_peer()
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)

    response = client.post(
        "/peers/votes/receive",
        json=_vote_payload(submission.submission_id, wallets["contributor_one"].public_key),
    )

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert response.json()["action"] == "created"
    assert blockchain.votes == [
        {
            "voter": wallets["contributor_one"].public_key,
            "submission_id": submission.submission_id,
            "vote_type": VOTE_ORIGINAL,
            "created_at": 1_000_000.0,
        }
    ]


def test_receive_peer_vote_rejects_unregistered_peer(blockchain, submission_image, wallets):
    client = _client(blockchain)
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)

    response = client.post(
        "/peers/votes/receive",
        json=_vote_payload(submission.submission_id, wallets["contributor_one"].public_key),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Peer is not registered or active."
    assert blockchain.votes == []


def test_receive_peer_vote_rejects_wrong_network(blockchain, submission_image, wallets):
    client = _client(blockchain)
    _register_peer()
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)

    response = client.post(
        "/peers/votes/receive",
        json=_vote_payload(
            submission.submission_id,
            wallets["contributor_one"].public_key,
            network_name="zoidberg-mainnet",
        ),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Peer vote belongs to a different network."
    assert blockchain.votes == []


def test_receive_peer_vote_rejects_unknown_submission(blockchain, wallets):
    client = _client(blockchain)
    _register_peer()

    response = client.post(
        "/peers/votes/receive",
        json=_vote_payload("missing-submission", wallets["contributor_one"].public_key),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Submission not found: missing-submission"
    assert blockchain.votes == []


def test_receive_peer_vote_rejects_invalid_vote_type(blockchain, submission_image, wallets):
    client = _client(blockchain)
    _register_peer()
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)

    response = client.post(
        "/peers/votes/receive",
        json=_vote_payload(
            submission.submission_id,
            wallets["contributor_one"].public_key,
            vote_type="maybe",
        ),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid vote type: maybe"
    assert blockchain.votes == []


def test_duplicate_matching_peer_vote_is_idempotent(blockchain, submission_image, wallets):
    client = _client(blockchain)
    _register_peer()
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    existing_vote = blockchain.cast_submission_vote(
        submission_id=submission.submission_id,
        voter=wallets["contributor_one"].public_key,
        vote_type=VOTE_UNSURE,
        created_at=100.0,
    )

    response = client.post(
        "/peers/votes/receive",
        json=_vote_payload(
            submission.submission_id,
            wallets["contributor_one"].public_key,
            vote_type=VOTE_UNSURE,
            created_at=200.0,
        ),
    )

    assert response.status_code == 200
    assert response.json()["action"] == "duplicate"
    assert blockchain.votes == [existing_vote]


def test_duplicate_matching_peer_vote_after_certificate_is_idempotent(
    blockchain,
    submission_image,
    wallets,
):
    client = _client(blockchain)
    _register_peer()
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    existing_vote = blockchain.cast_submission_vote(
        submission_id=submission.submission_id,
        voter=wallets["contributor_one"].public_key,
        vote_type=VOTE_ORIGINAL,
        created_at=100.0,
    )
    submission.transition_to(APPROVED)
    blockchain.create_originality_certificate(submission.submission_id, approved_at=1_000_000)

    response = client.post(
        "/peers/votes/receive",
        json=_vote_payload(
            submission.submission_id,
            wallets["contributor_one"].public_key,
            vote_type=VOTE_ORIGINAL,
            created_at=200.0,
        ),
    )

    assert response.status_code == 200
    assert response.json()["action"] == "duplicate"
    assert blockchain.votes == [existing_vote]


def test_duplicate_conflicting_peer_vote_is_rejected(blockchain, submission_image, wallets):
    client = _client(blockchain)
    _register_peer()
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    blockchain.cast_submission_vote(
        submission_id=submission.submission_id,
        voter=wallets["contributor_one"].public_key,
        vote_type=VOTE_ORIGINAL,
    )

    response = client.post(
        "/peers/votes/receive",
        json=_vote_payload(
            submission.submission_id,
            wallets["contributor_one"].public_key,
            vote_type=VOTE_NOT_ORIGINAL,
        ),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Wallet has already voted differently on this submission."
    assert len(blockchain.votes) == 1
    assert blockchain.votes[0]["vote_type"] == VOTE_ORIGINAL


def test_peer_vote_rejected_after_certificate_exists(blockchain, submission_image, wallets):
    client = _client(blockchain)
    _register_peer()
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    blockchain.cast_submission_vote(
        submission_id=submission.submission_id,
        voter=wallets["contributor_one"].public_key,
        vote_type=VOTE_ORIGINAL,
    )
    submission.transition_to(APPROVED)
    blockchain.create_originality_certificate(submission.submission_id, approved_at=1_000_000)

    response = client.post(
        "/peers/votes/receive",
        json=_vote_payload(
            submission.submission_id,
            wallets["contributor_two"].public_key,
            vote_type=VOTE_NOT_ORIGINAL,
        ),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Finalized or certified submissions cannot receive votes."
    assert len(blockchain.votes) == 1


def test_creator_cannot_vote_through_peer_endpoint(blockchain, submission_image, wallets):
    client = _client(blockchain)
    _register_peer()
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)

    response = client.post(
        "/peers/votes/receive",
        json=_vote_payload(submission.submission_id, wallets["owner"].public_key),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Submission creator cannot vote on their own submission."
    assert blockchain.votes == []


def test_receiving_signed_peer_vote_preserves_signature_metadata(blockchain, submission_image):
    client = _client(blockchain)
    _register_peer()
    submitter = Account.create()
    voter = Account.create()
    submission = _submission(blockchain, submission_image, submitter.address.lower())
    vote_message = "Peer vote signed message"
    vote_signature = _sign_message(vote_message, voter)

    response = client.post(
        "/peers/votes/receive",
        json={
            **_vote_payload(submission.submission_id, voter.address.lower(), vote_type=VOTE_NOT_ORIGINAL),
            "content_hash": submission.content_hash,
            "voter_wallet_address": voter.address.lower(),
            "signature_scheme": "personal_sign",
            "vote_signature": vote_signature,
            "vote_message": vote_message,
            "signed_message_hash": hash_wallet_message(vote_message),
            "vote_nonce": "peer-vote-nonce-1",
            "signed_at": "2026-07-14T00:00:00+00:00",
            "identity_source": "metamask_signed",
        },
    )

    assert response.status_code == 200
    stored_vote = blockchain.votes[0]
    assert stored_vote["voter"] == voter.address.lower()
    assert stored_vote["voter_wallet_address"] == voter.address.lower()
    assert stored_vote["signature_scheme"] == "personal_sign"
    assert stored_vote["identity_source"] == "metamask_signed"
    assert stored_vote.get("vote_version") is None
    assert stored_vote.get("protocol_version") is None
    assert stored_vote.get("network_id") is None


def test_receiving_protocol_v1_peer_vote_preserves_versioned_signature_metadata(blockchain, submission_image):
    client = _client(blockchain)
    _register_peer()
    submitter = Account.create()
    voter = Account.create()
    submission = _submission(blockchain, submission_image, submitter.address.lower())

    response = client.post(
        "/peers/votes/receive",
        json=_protocol_v1_signed_vote_payload(submission, voter, vote_type=VOTE_NOT_ORIGINAL),
    )

    assert response.status_code == 200
    stored_vote = blockchain.votes[0]
    assert stored_vote["voter"] == voter.address.lower()
    assert stored_vote["voter_wallet_address"] == voter.address.lower()
    assert stored_vote["vote_version"] == PROTOCOL_V1_VOTE_VERSION
    assert stored_vote["protocol_version"] == PROTOCOL_VERSION
    assert stored_vote["network_id"] == PUBLIC_TESTNET_V1_NETWORK_ID
    assert stored_vote["signature_scheme"] == "personal_sign"
    assert stored_vote["identity_source"] == "metamask_signed"


def test_protocol_v1_peer_vote_rejects_inner_wrong_network(blockchain, submission_image):
    client = _client(blockchain)
    _register_peer()
    submitter = Account.create()
    voter = Account.create()
    submission = _submission(blockchain, submission_image, submitter.address.lower())

    response = client.post(
        "/peers/votes/receive",
        json=_protocol_v1_signed_vote_payload(
            submission,
            voter,
            network_id="zoidberg-devnet-v1",
        ),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Vote belongs to a different network."
    assert blockchain.votes == []


def test_protocol_v1_peer_vote_rejects_modified_vote_choice(blockchain, submission_image):
    client = _client(blockchain)
    _register_peer()
    submitter = Account.create()
    voter = Account.create()
    submission = _submission(blockchain, submission_image, submitter.address.lower())
    payload = _protocol_v1_signed_vote_payload(submission, voter, vote_type=VOTE_ORIGINAL)
    payload["vote_type"] = VOTE_NOT_ORIGINAL

    response = client.post("/peers/votes/receive", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "Vote vote_message does not match the Protocol v1 vote payload."
    assert blockchain.votes == []


def test_signed_peer_vote_auth_does_not_bypass_inner_vote_validation(
    blockchain,
    submission_image,
    monkeypatch,
):
    client = _client(blockchain)
    _configure_signed_peer_messages(monkeypatch)
    _freeze_peer_time(monkeypatch)
    _register_peer()
    submitter = Account.create()
    voter = Account.create()
    submission = _submission(blockchain, submission_image, submitter.address.lower())
    payload = _protocol_v1_signed_vote_payload(submission, voter, vote_type=VOTE_ORIGINAL)
    payload["vote_type"] = VOTE_NOT_ORIGINAL

    response = client.post(
        "/peers/votes/receive",
        json=payload,
        headers=_signed_headers(
            "/peers/votes/receive",
            payload,
            nonce="signed-vote-invalid-choice-1",
        ),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Vote vote_message does not match the Protocol v1 vote payload."
    assert blockchain.votes == []


def test_protocol_v1_vote_envelope_without_version_is_not_accepted_through_legacy_path(blockchain, submission_image):
    client = _client(blockchain)
    _register_peer()
    submitter = Account.create()
    voter = Account.create()
    submission = _submission(blockchain, submission_image, submitter.address.lower())
    payload = _protocol_v1_signed_vote_payload(submission, voter)

    for field_name in ["vote_version", "protocol_version", "network_id", "vote_issued_at", "vote_expires_at"]:
        payload.pop(field_name)

    response = client.post("/peers/votes/receive", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "Vote vote_version is required for Protocol v1 vote messages."
    assert blockchain.votes == []


def test_local_vote_broadcasts_without_failing_if_one_peer_is_down(
    blockchain,
    submission_image,
    wallets,
    monkeypatch,
):
    client = _client(blockchain)
    _register_peer("peer-up", "http://peer-up.test")
    _register_peer("peer-down", "http://peer-down.test")
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    calls = []

    def fake_post(url, json, timeout, headers=None):
        calls.append({"url": url, "json": json, "timeout": timeout, "headers": headers})
        if "peer-down" in url:
            raise requests.RequestException("connection refused")
        return type("Response", (), {"status_code": 200, "text": "ok"})()

    monkeypatch.setattr("peer_sync.requests.post", fake_post)

    response = client.post(
        f"/submissions/{submission.submission_id}/vote",
        data={
            "voter": wallets["contributor_one"].public_key,
            "vote_type": VOTE_ORIGINAL,
        },
    )

    assert response.status_code == 200
    assert response.json()["broadcast"]["attempted"] == 2
    assert response.json()["broadcast"]["succeeded"] == 1
    assert response.json()["broadcast"]["failed"] == 1
    assert len(calls) == 2
    assert len(blockchain.votes) == 1


def test_manual_vote_rebroadcast_endpoint_works(blockchain, submission_image, wallets, monkeypatch):
    client = _client(blockchain)
    _register_peer()
    submission = _submission(blockchain, submission_image, wallets["owner"].public_key)
    vote = blockchain.cast_submission_vote(
        submission_id=submission.submission_id,
        voter=wallets["contributor_one"].public_key,
        vote_type=VOTE_NOT_ORIGINAL,
        created_at=1_000_000.0,
    )
    calls = []

    def fake_post(url, json, timeout, headers=None):
        calls.append({"url": url, "json": json, "timeout": timeout, "headers": headers})
        return type("Response", (), {"status_code": 200, "text": "ok"})()

    monkeypatch.setattr("peer_sync.requests.post", fake_post)

    response = client.post(f"/submissions/{submission.submission_id}/votes/broadcast")

    assert response.status_code == 200
    assert response.json()["broadcast"]["vote_count"] == 1
    assert response.json()["broadcast"]["attempted"] == 1
    assert response.json()["broadcast"]["succeeded"] == 1
    assert calls[0]["url"] == "http://peer-one.test:8000/peers/votes/receive"
    assert calls[0]["json"] == {
        "origin_node_id": "local-node",
        "network_name": "zoidberg-testnet",
        "submission_id": submission.submission_id,
        "voter": vote["voter"],
        "vote_type": vote["vote_type"],
        "created_at": vote["created_at"],
    }
