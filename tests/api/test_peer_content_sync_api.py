import hashlib

import pytest
from fastapi.testclient import TestClient

import peer_sync
from blockchain import Blockchain
from content import compute_text_content_hash
from peers import PeerStore
from storage import JSONStorageBackend, SQLiteStorageBackend
from submission import APPROVED, PENDING, Submission, VOTE_NOT_ORIGINAL, VOTE_ORIGINAL
from wallet import Wallet


TEXT_BYTES = b"Peer content body"


def _client(blockchain):
    import api

    api.NODE_ID = "local-node"
    api.PUBLIC_NODE_URL = "http://localhost:8000"
    api.NETWORK_NAME = "zoidberg-testnet"
    api.blockchain = blockchain
    api.peer_store = PeerStore(storage_backend=blockchain.storage)
    return TestClient(api.app)


def _register_peer(node_id="peer-node-1", url="http://peer-one.test:8000", *, client=None, blockchain=None):
    import api

    peer_store = api.peer_store if client is not None else PeerStore(storage_backend=blockchain.storage)
    return peer_store.register_peer(
        node_id=node_id,
        url=url,
        network_name="zoidberg-testnet",
    )


def _configure_peer_auth(monkeypatch, enabled, secret="super-secret-value"):
    import api

    monkeypatch.setattr(api, "peer_auth_required", lambda: enabled)
    monkeypatch.setattr(api, "peer_shared_secret", lambda: secret)
    monkeypatch.setattr(api, "peer_shared_secret_is_configured", lambda: bool(secret))
    monkeypatch.setattr(api, "signed_peer_messages_enabled", lambda: False)
    monkeypatch.setattr(api, "peer_replay_protection_enabled", lambda: False)
    monkeypatch.setattr(peer_sync, "peer_auth_required", lambda: enabled)
    monkeypatch.setattr(peer_sync, "peer_shared_secret", lambda: secret)
    monkeypatch.setattr(peer_sync, "peer_shared_secret_is_configured", lambda: bool(secret))
    monkeypatch.setattr(peer_sync, "signed_peer_messages_enabled", lambda: False)
    monkeypatch.setattr(peer_sync, "peer_replay_protection_enabled", lambda: False)
    peer_sync._PEER_NONCE_CACHE.clear()


def _configure_signed_peer_messages(monkeypatch, secret="super-secret-value"):
    import api

    monkeypatch.setattr(api, "signed_peer_messages_enabled", lambda: True)
    monkeypatch.setattr(api, "peer_auth_required", lambda: False)
    monkeypatch.setattr(api, "peer_shared_secret", lambda: secret)
    monkeypatch.setattr(api, "peer_shared_secret_is_configured", lambda: True)
    monkeypatch.setattr(api, "peer_replay_protection_enabled", lambda: False)
    monkeypatch.setattr(peer_sync, "signed_peer_messages_enabled", lambda: True)
    monkeypatch.setattr(peer_sync, "peer_auth_required", lambda: False)
    monkeypatch.setattr(peer_sync, "peer_shared_secret", lambda: secret)
    monkeypatch.setattr(peer_sync, "peer_shared_secret_is_configured", lambda: True)
    monkeypatch.setattr(peer_sync, "peer_replay_protection_enabled", lambda: False)
    peer_sync._PEER_NONCE_CACHE.clear()


def _signed_get_headers(path, *, secret="super-secret-value", timestamp=1_700_000_000, nonce="nonce-1"):
    signature = peer_sync.sign_peer_request(
        method="GET",
        path=path,
        timestamp=timestamp,
        nonce=nonce,
        body_bytes=b"",
        secret=secret,
    )
    return {
        "X-ZOID-Node-Id": "peer-node-1",
        "X-ZOID-Timestamp": str(timestamp),
        "X-ZOID-Nonce": nonce,
        "X-ZOID-Signature": signature,
    }


def _fake_response(status_code, *, json_body=None, content=b"", text="", headers=None):
    class _Response:
        def __init__(self):
            self.status_code = status_code
            self.content = content
            self.text = text
            self.headers = headers or {}

        def json(self):
            return json_body

    return _Response()


def _submission_payload(
    submitter,
    *,
    submission_id="peer-submission-1",
    text_content="Peer submission content",
    created_at=1_000_000.0,
):
    return Submission(
        submission_id=submission_id,
        image_path="peer-submissions/meme.jpg",
        text_content=text_content,
        submitter=submitter,
        status=PENDING,
        created_at=created_at,
    ).to_dict()


def _receive_submission_payload(submission, origin_node_id="peer-node-1", network_name="zoidberg-testnet"):
    return {
        "origin_node_id": origin_node_id,
        "network_name": network_name,
        "submission": submission,
    }


def _cast_votes(blockchain, submission_id, voter_prefix="peer-content-voter"):
    for index, vote_type in enumerate(
        [VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_ORIGINAL, VOTE_NOT_ORIGINAL]
    ):
        blockchain.cast_submission_vote(
            submission_id=submission_id,
            voter=f"{voter_prefix}-{index}",
            vote_type=vote_type,
            created_at=1_000_000 + index,
        )


def _certified_submission_and_certificate(blockchain, submission_image, submitter):
    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Peer-certified submission",
        submitter=submitter,
    )
    _cast_votes(blockchain, submission.submission_id)
    submission.transition_to(APPROVED)
    certificate = blockchain.create_originality_certificate(
        submission.submission_id,
        approved_at=1_000_100,
    )
    return submission, certificate


def _certified_peer_block(blockchain, submission_image, wallets):
    original_chain = list(blockchain.chain)
    submission, certificate = _certified_submission_and_certificate(
        blockchain,
        submission_image,
        wallets["owner"].public_key,
    )
    blockchain.add_to_mint_queue(submission.submission_id)
    assert blockchain.mint_next_queued_submission(
        miner=wallets["contributor_one"].public_key,
        validate_meme=False,
    ) is True
    block = blockchain.get_latest_block()
    blockchain.chain = original_chain
    return submission, certificate, block


def _backend_factory(kind, base_dir, name):
    node_dir = base_dir / name
    if kind == "json":
        return JSONStorageBackend(
            blockchain_file=str(node_dir / "blockchain.json"),
            peers_file=str(node_dir / "peers.json"),
        )
    return SQLiteStorageBackend(sqlite_db_path=str(node_dir / "zoidbergchain.db"))


def _make_blockchain(backend):
    owner = Wallet()
    contributor_one = Wallet()
    contributor_two = Wallet()
    blockchain = Blockchain(
        project_owner_wallet=owner,
        Contributor_one=contributor_one,
        Contributor_two=contributor_two,
        storage_backend=backend,
    )
    return blockchain, {
        "owner": owner,
        "contributor_one": contributor_one,
        "contributor_two": contributor_two,
    }


def test_peer_content_metadata_and_download_require_peer_auth(blockchain, wallets, monkeypatch):
    client = _client(blockchain)
    _configure_peer_auth(monkeypatch, enabled=True)
    content_object = blockchain.upload_text_content(
        text_content="peer metadata text",
        submitted_by=wallets["owner"].public_key,
    )
    blockchain.save_blockchain()

    metadata_response = client.get(f"/peers/content/{content_object.content_hash}/metadata")
    download_response = client.get(f"/peers/content/{content_object.content_hash}")

    assert metadata_response.status_code == 401
    assert download_response.status_code == 401

    headers = {"X-ZOID-Peer-Secret": "super-secret-value"}
    metadata_response = client.get(
        f"/peers/content/{content_object.content_hash}/metadata",
        headers=headers,
    )
    download_response = client.get(
        f"/peers/content/{content_object.content_hash}",
        headers=headers,
    )

    assert metadata_response.status_code == 200
    assert metadata_response.json()["content"]["byte_hash"] == content_object.metadata["byte_hash"]
    assert "local_path" not in metadata_response.json()["content"]
    assert download_response.status_code == 200
    assert download_response.text == "peer metadata text"


def test_signed_peer_get_content_metadata_accepts_empty_body_signature(blockchain, wallets, monkeypatch):
    client = _client(blockchain)
    _configure_signed_peer_messages(monkeypatch)
    monkeypatch.setattr(peer_sync.time, "time", lambda: 1_700_000_000)
    content_object = blockchain.upload_text_content(
        text_content="signed peer metadata text",
        submitted_by=wallets["owner"].public_key,
    )
    blockchain.save_blockchain()

    response = client.get(
        f"/peers/content/{content_object.content_hash}/metadata",
        headers=_signed_get_headers(f"/peers/content/{content_object.content_hash}/metadata"),
    )

    assert response.status_code == 200
    assert response.json()["content"]["content_hash"] == content_object.content_hash


def test_fetch_content_from_peer_fetches_and_verifies_text_content(blockchain, monkeypatch):
    content_hash = compute_text_content_hash(TEXT_BYTES.decode("utf-8"))
    peer = {"node_id": "peer-node-1", "url": "http://peer-one.test:8000"}
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append({"url": url, "headers": headers, "timeout": timeout})
        if url.endswith("/metadata"):
            return _fake_response(
                200,
                json_body={
                    "content": {
                        "content_hash": content_hash,
                        "mime_type": "text/plain",
                        "content_type": "text",
                        "submitted_by": "peer-wallet",
                        "file_size_bytes": len(TEXT_BYTES),
                        "byte_hash": content_hash,
                    }
                },
            )
        return _fake_response(
            200,
            content=TEXT_BYTES,
            headers={"content-type": "text/plain"},
        )

    monkeypatch.setattr(peer_sync.requests, "get", fake_get)

    result = peer_sync.fetch_content_from_peer(
        blockchain,
        peer,
        content_hash,
        origin_node_id="local-node",
    )

    stored = blockchain.get_content_object_by_hash(content_hash)
    assert result["status"] == "fetched_and_verified"
    assert stored is not None
    assert stored.storage_status == "verified"
    assert stored.text_content == "Peer content body"
    assert stored.submitted_by == "peer-wallet"
    assert stored.local_path is not None
    assert len(calls) == 2
    assert calls[0]["url"].endswith(f"/peers/content/{content_hash}/metadata")
    assert calls[1]["url"].endswith(f"/peers/content/{content_hash}")


def test_fetch_content_from_peer_rejects_hash_mismatch_and_keeps_remote_reference(blockchain, monkeypatch):
    expected_hash = compute_text_content_hash(TEXT_BYTES.decode("utf-8"))
    blockchain.register_remote_content_reference(content_hash=expected_hash, submitted_by="peer-wallet")
    peer = {"node_id": "peer-node-1", "url": "http://peer-one.test:8000"}

    def fake_get(url, headers=None, timeout=None):
        if url.endswith("/metadata"):
            return _fake_response(
                200,
                json_body={
                    "content": {
                        "content_hash": expected_hash,
                        "mime_type": "text/plain",
                        "content_type": "text",
                        "submitted_by": "peer-wallet",
                        "file_size_bytes": len(TEXT_BYTES),
                        "byte_hash": expected_hash,
                    }
                },
            )
        return _fake_response(
            200,
            content=b"tampered payload",
            headers={"content-type": "text/plain"},
        )

    monkeypatch.setattr(peer_sync.requests, "get", fake_get)

    result = peer_sync.fetch_content_from_peer(
        blockchain,
        peer,
        expected_hash,
        origin_node_id="local-node",
    )

    content_object = blockchain.get_content_object_by_hash(expected_hash)
    assert result["status"] == "failed_verification"
    assert result["reason"] == "hash_mismatch"
    assert content_object.storage_status == "remote"
    assert content_object.local_path is None


def test_fetch_content_from_peer_rejects_mime_mismatch(blockchain, monkeypatch):
    content_hash = compute_text_content_hash(TEXT_BYTES.decode("utf-8"))
    peer = {"node_id": "peer-node-1", "url": "http://peer-one.test:8000"}

    def fake_get(url, headers=None, timeout=None):
        if url.endswith("/metadata"):
            return _fake_response(
                200,
                json_body={
                    "content": {
                        "content_hash": content_hash,
                        "mime_type": "image/png",
                        "content_type": "text",
                        "submitted_by": "peer-wallet",
                        "file_size_bytes": len(TEXT_BYTES),
                        "byte_hash": content_hash,
                    }
                },
            )
        return _fake_response(200, content=TEXT_BYTES, headers={"content-type": "image/png"})

    monkeypatch.setattr(peer_sync.requests, "get", fake_get)

    with pytest.raises(peer_sync.ContentSyncError, match="does not match detected mime_type"):
        peer_sync.fetch_content_from_peer(
            blockchain,
            peer,
            content_hash,
            origin_node_id="local-node",
        )


def test_fetch_content_from_peer_rejects_oversized_payload(blockchain, monkeypatch):
    content_hash = compute_text_content_hash(TEXT_BYTES.decode("utf-8"))
    peer = {"node_id": "peer-node-1", "url": "http://peer-one.test:8000"}
    import content

    monkeypatch.setattr(content.config, "MAX_CONTENT_FILE_SIZE_BYTES", 4)

    def fake_get(url, headers=None, timeout=None):
        if url.endswith("/metadata"):
            return _fake_response(
                200,
                json_body={
                    "content": {
                        "content_hash": content_hash,
                        "mime_type": "text/plain",
                        "content_type": "text",
                        "submitted_by": "peer-wallet",
                        "file_size_bytes": len(TEXT_BYTES),
                        "byte_hash": content_hash,
                    }
                },
            )
        return _fake_response(200, content=TEXT_BYTES, headers={"content-type": "text/plain"})

    monkeypatch.setattr(peer_sync.requests, "get", fake_get)

    result = peer_sync.fetch_content_from_peer(
        blockchain,
        peer,
        content_hash,
        origin_node_id="local-node",
    )

    assert result["status"] == "failed_verification"
    assert result["reason"] == "oversized_metadata"


def test_peer_metadata_local_path_is_ignored(blockchain, monkeypatch):
    content_hash = compute_text_content_hash(TEXT_BYTES.decode("utf-8"))
    peer = {"node_id": "peer-node-1", "url": "http://peer-one.test:8000"}

    def fake_get(url, headers=None, timeout=None):
        if url.endswith("/metadata"):
            return _fake_response(
                200,
                json_body={
                    "content": {
                        "content_hash": content_hash,
                        "mime_type": "text/plain",
                        "content_type": "text",
                        "submitted_by": "peer-wallet",
                        "file_size_bytes": len(TEXT_BYTES),
                        "byte_hash": content_hash,
                        "local_path": "C:/malicious/path.txt",
                    }
                },
            )
        return _fake_response(200, content=TEXT_BYTES, headers={"content-type": "text/plain"})

    monkeypatch.setattr(peer_sync.requests, "get", fake_get)

    result = peer_sync.fetch_content_from_peer(
        blockchain,
        peer,
        content_hash,
        origin_node_id="local-node",
    )

    content_object = blockchain.get_content_object_by_hash(content_hash)
    assert result["status"] == "fetched_and_verified"
    assert content_object.local_path != "C:/malicious/path.txt"


def test_sync_missing_content_short_circuits_for_verified_or_missing_peers(blockchain, wallets):
    verified = blockchain.upload_text_content(
        text_content="already present",
        submitted_by=wallets["owner"].public_key,
    )
    peer_store = PeerStore(storage_backend=blockchain.storage)

    already_verified = peer_sync.sync_missing_content(
        blockchain=blockchain,
        peer_store=peer_store,
        content_hash=verified.content_hash,
        origin_node_id="local-node",
        network_name="zoidberg-testnet",
    )
    no_peers = peer_sync.sync_missing_content(
        blockchain=blockchain,
        peer_store=peer_store,
        content_hash="a" * 64,
        origin_node_id="local-node",
        network_name="zoidberg-testnet",
    )

    assert already_verified["status"] == "already_verified"
    assert no_peers["status"] == "no_peers_available"


def test_receive_peer_submission_creates_remote_content_object_and_manual_sync_verifies_it(
    blockchain,
    wallets,
    monkeypatch,
):
    client = _client(blockchain)
    _register_peer(client=client)
    monkeypatch.setattr("api.is_development", lambda: True)
    monkeypatch.setattr("api.public_api_mode_enabled", lambda: False)
    peer_text = "Peer submission content"
    content_hash = compute_text_content_hash(peer_text)
    payload = _submission_payload(wallets["owner"].public_key, text_content=peer_text)
    payload["content_hash"] = content_hash
    payload["content_id"] = hashlib.sha256(content_hash.encode("utf-8")).hexdigest()[:32]

    def fake_get(url, headers=None, timeout=None):
        if url.endswith("/metadata"):
            return _fake_response(
                200,
                json_body={
                    "content": {
                        "content_hash": content_hash,
                        "mime_type": "text/plain",
                        "content_type": "text",
                        "submitted_by": wallets["owner"].public_key,
                        "file_size_bytes": len(peer_text.encode("utf-8")),
                        "byte_hash": content_hash,
                    }
                },
            )
        return _fake_response(
            200,
            content=peer_text.encode("utf-8"),
            headers={"content-type": "text/plain"},
        )

    monkeypatch.setattr(peer_sync.requests, "get", fake_get)

    receive_response = client.post(
        "/peers/submissions/receive",
        json=_receive_submission_payload(payload),
    )

    submission = blockchain.get_submission(payload["submission_id"])
    content_object = blockchain.get_content_object_by_hash(content_hash)
    assert receive_response.status_code == 200
    assert submission is not None
    assert submission.content_id == content_object.content_id
    assert content_object.storage_status == "remote"
    assert content_object.local_path is None

    sync_response = client.post(f"/content/{content_hash}/sync")

    content_object = blockchain.get_content_object_by_hash(content_hash)
    assert sync_response.status_code == 200
    assert sync_response.json()["result"]["status"] == "fetched_and_verified"
    assert sync_response.json()["content"]["storage_status"] == "verified"
    assert content_object.storage_status == "verified"
    assert submission.content_id == content_object.content_id


@pytest.mark.parametrize("backend_kind", ["json", "sqlite"])
def test_remote_content_reference_persists_across_storage_backends(
    backend_kind,
    isolated_data_dir,
    wallets,
):
    backend = _backend_factory(backend_kind, isolated_data_dir, f"peer-content-{backend_kind}")
    blockchain, local_wallets = _make_blockchain(backend)
    peer_store = PeerStore(storage_backend=backend)
    peer_store.register_peer(
        node_id="peer-node-1",
        url="http://peer-one.test:8000",
        network_name="zoidberg-testnet",
    )
    submission_payload = _submission_payload(
        local_wallets["owner"].public_key,
        text_content="Persisted remote peer content",
    )

    result = peer_sync.receive_peer_submission(
        blockchain=blockchain,
        peer_store=peer_store,
        origin_node_id="peer-node-1",
        network_name="zoidberg-testnet",
        submission_payload=submission_payload,
        local_network_name="zoidberg-testnet",
    )

    reloaded, _ = _make_blockchain(backend)
    content_object = reloaded.get_content_object_by_hash(result["submission"]["content_hash"])
    submission = reloaded.get_submission(result["submission"]["submission_id"])
    assert content_object is not None
    assert content_object.storage_status == "remote"
    assert content_object.local_path is None
    assert submission is not None
    assert submission.content_id == content_object.content_id


def test_receiving_peer_certificate_creates_remote_content_reference(blockchain, submission_image, wallets):
    client = _client(blockchain)
    _register_peer(client=client)
    _submission, certificate = _certified_submission_and_certificate(
        blockchain,
        submission_image,
        wallets["owner"].public_key,
    )
    blockchain.submissions = []
    blockchain.content_objects = []
    blockchain.originality_certificates = []

    response = client.post(
        "/peers/certificates/receive",
        json={
            "origin_node_id": "peer-node-1",
            "network_name": "zoidberg-testnet",
            "certificate": certificate.to_dict(),
        },
    )

    content_object = blockchain.get_content_object_by_hash(certificate.content_hash)
    assert response.status_code == 200
    assert content_object is not None
    assert content_object.storage_status == "remote"
    assert content_object.local_path is None


def test_receiving_peer_block_creates_remote_content_reference(blockchain, submission_image, wallets):
    client = _client(blockchain)
    _register_peer(client=client)
    submission, certificate, block = _certified_peer_block(blockchain, submission_image, wallets)
    blockchain.content_objects = []
    blockchain.originality_certificates = []

    response = client.post(
        "/peers/blocks/receive",
        json={
            "origin_node_id": "peer-node-1",
            "network_name": "zoidberg-testnet",
            "block": block.to_dict(),
            "related_submission_id": submission.submission_id,
            "certificate": certificate.to_dict(),
        },
    )

    content_object = blockchain.get_content_object_by_hash(block.content_hash)
    assert response.status_code == 200
    assert content_object is not None
    assert content_object.storage_status == "remote"
    assert content_object.local_path is None
