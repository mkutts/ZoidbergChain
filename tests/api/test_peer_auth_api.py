import hashlib
import hmac

import peer_sync
from fastapi.testclient import TestClient
import pytest

from peers import PeerStore
from protocol_v1 import canonical_json_bytes
from protocol_v1_peer_message import (
    HEADER_MESSAGE_ID,
    HEADER_MESSAGE_TYPE,
    HEADER_NETWORK_ID,
    HEADER_NONCE,
    HEADER_PEER_MESSAGE_VERSION,
    HEADER_PROTOCOL_VERSION,
    calculate_protocol_v1_peer_message_id,
    build_protocol_v1_peer_request_headers,
    clear_protocol_v1_peer_replay_store_cache,
    sign_protocol_v1_peer_message,
)
from submission import VOTE_ORIGINAL


def _client(blockchain):
    import api

    api.NODE_ID = "local-node"
    api.PUBLIC_NODE_URL = "http://localhost:8000"
    api.NETWORK_NAME = "zoidberg-testnet"
    api.blockchain = blockchain
    api.peer_store = PeerStore()
    clear_protocol_v1_peer_replay_store_cache(data_dir=api.peer_store.storage.data_dir)
    return TestClient(api.app)


def _configure_peer_auth(monkeypatch, enabled, secret="super-secret-value"):
    import api

    monkeypatch.setattr(api, "peer_auth_required", lambda: enabled)
    monkeypatch.setattr(api, "peer_shared_secret", lambda: secret)
    monkeypatch.setattr(api, "peer_shared_secret_is_configured", lambda: bool(secret))
    monkeypatch.setattr(api, "signed_peer_messages_enabled", lambda: False)
    monkeypatch.setattr(api, "peer_replay_protection_enabled", lambda: False)
    monkeypatch.setattr(api, "PEER_SIGNATURE_WINDOW_SECONDS", 300)
    monkeypatch.setattr(peer_sync, "peer_auth_required", lambda: enabled)
    monkeypatch.setattr(peer_sync, "peer_shared_secret", lambda: secret)
    monkeypatch.setattr(peer_sync, "peer_shared_secret_is_configured", lambda: bool(secret))
    monkeypatch.setattr(peer_sync, "signed_peer_messages_enabled", lambda: False)
    monkeypatch.setattr(peer_sync, "peer_replay_protection_enabled", lambda: False)
    monkeypatch.setattr(peer_sync, "peer_signature_window_seconds", lambda: 300)
    peer_sync._PEER_NONCE_CACHE.clear()
    clear_protocol_v1_peer_replay_store_cache()


def _safe_secret(secret):
    return bool(secret) and secret.lower() not in {
        "change-me",
        "replace-with-long-random-secret",
    }


def _configure_signed_peer_messages(
    monkeypatch,
    enabled=True,
    secret="super-secret-value",
    replay_protection=True,
    window_seconds=300,
):
    import api

    monkeypatch.setattr(api, "signed_peer_messages_enabled", lambda: enabled)
    monkeypatch.setattr(api, "peer_auth_required", lambda: False)
    monkeypatch.setattr(api, "peer_shared_secret", lambda: secret)
    monkeypatch.setattr(api, "peer_shared_secret_is_configured", lambda: _safe_secret(secret))
    monkeypatch.setattr(api, "peer_replay_protection_enabled", lambda: replay_protection)
    monkeypatch.setattr(api, "PEER_SIGNATURE_WINDOW_SECONDS", window_seconds)
    monkeypatch.setattr(peer_sync, "signed_peer_messages_enabled", lambda: enabled)
    monkeypatch.setattr(peer_sync, "peer_auth_required", lambda: False)
    monkeypatch.setattr(peer_sync, "peer_shared_secret", lambda: secret)
    monkeypatch.setattr(peer_sync, "peer_shared_secret_is_configured", lambda: _safe_secret(secret))
    monkeypatch.setattr(peer_sync, "peer_replay_protection_enabled", lambda: replay_protection)
    monkeypatch.setattr(peer_sync, "peer_signature_window_seconds", lambda: window_seconds)
    peer_sync._PEER_NONCE_CACHE.clear()
    clear_protocol_v1_peer_replay_store_cache()


def _freeze_peer_time(monkeypatch, now=1_700_000_000):
    import api

    monkeypatch.setattr(api.time, "time", lambda: now)
    monkeypatch.setattr(peer_sync.time, "time", lambda: now)


def _signed_headers(method, path, payload, secret="super-secret-value", timestamp=1_700_000_000, nonce="nonce-1", node_id="peer-node-1"):
    return build_protocol_v1_peer_request_headers(
        method,
        path,
        payload,
        node_id,
        network_name="zoidberg-testnet",
        secret=secret,
        timestamp=timestamp,
        nonce=nonce,
    )


def _custom_signed_headers(
    payload,
    *,
    message_type,
    node_id="peer-node-1",
    network_id="zoidberg-public-testnet-v1",
    peer_message_version="1",
    protocol_version="1",
    timestamp=1_700_000_000,
    nonce="nonce-1",
    secret="super-secret-value",
    message_id=None,
    signature=None,
):
    if message_id is None and peer_message_version == "1" and protocol_version == "1":
        message_id = calculate_protocol_v1_peer_message_id(
            payload,
            network_id=network_id,
            message_type=message_type,
            sender_node_id=node_id,
            timestamp=timestamp,
            nonce=nonce,
        )
    if signature is None and peer_message_version == "1" and protocol_version == "1":
        signature = sign_protocol_v1_peer_message(
            payload,
            network_id=network_id,
            message_type=message_type,
            sender_node_id=node_id,
            timestamp=timestamp,
            nonce=nonce,
            secret=secret,
        )
    return {
        HEADER_PEER_MESSAGE_VERSION: str(peer_message_version),
        HEADER_PROTOCOL_VERSION: str(protocol_version),
        HEADER_NETWORK_ID: network_id,
        HEADER_MESSAGE_TYPE: message_type,
        "X-ZOID-Node-Id": node_id,
        "X-ZOID-Timestamp": str(timestamp),
        HEADER_NONCE: nonce,
        HEADER_MESSAGE_ID: message_id or ("0" * 64),
        "X-ZOID-Signature": signature or ("0" * 64),
    }


def _register_peer(client, secret=None):
    headers = {}
    if secret is not None:
        headers["X-ZOID-Peer-Secret"] = secret
    return client.post(
        "/peers/register",
        headers=headers,
        json={
            "node_id": "peer-node-1",
            "url": "http://peer-one.test:8000",
            "network_name": "zoidberg-testnet",
        },
    )


def test_peer_endpoint_allowed_in_development_when_peer_auth_disabled(blockchain, monkeypatch):
    _configure_peer_auth(monkeypatch, enabled=False)
    client = _client(blockchain)

    response = _register_peer(client)

    assert response.status_code == 200
    assert response.json()["peer"]["node_id"] == "peer-node-1"


def test_peer_endpoint_requires_header_when_peer_auth_enabled(blockchain, monkeypatch):
    _configure_peer_auth(monkeypatch, enabled=True)
    client = _client(blockchain)

    response = _register_peer(client)

    assert response.status_code == 401
    assert response.json()["detail"] == "Peer auth required. Missing shared secret."


def test_peer_endpoint_rejects_wrong_secret(blockchain, monkeypatch):
    _configure_peer_auth(monkeypatch, enabled=True)
    client = _client(blockchain)

    response = client.post(
        "/peers/register",
        headers={"X-ZOID-Peer-Secret": "wrong-secret"},
        json={
            "node_id": "peer-node-1",
            "url": "http://peer-one.test:8000",
            "network_name": "zoidberg-testnet",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid peer shared secret."


def test_peer_endpoint_accepts_correct_secret(blockchain, monkeypatch):
    _configure_peer_auth(monkeypatch, enabled=True)
    client = _client(blockchain)

    response = client.post(
        "/peers/register",
        headers={"X-ZOID-Peer-Secret": "super-secret-value"},
        json={
            "node_id": "peer-node-1",
            "url": "http://peer-one.test:8000",
            "network_name": "zoidberg-testnet",
        },
    )

    assert response.status_code == 200


def test_constant_time_comparison_helper_is_used(blockchain, monkeypatch):
    import api

    compare_calls = []

    def fake_compare_digest(left, right):
        compare_calls.append((left, right))
        return True

    monkeypatch.setattr(api.hmac, "compare_digest", fake_compare_digest)
    _configure_peer_auth(monkeypatch, enabled=True)
    client = _client(blockchain)

    response = client.post(
        "/peers/register",
        headers={"X-ZOID-Peer-Secret": "super-secret-value"},
        json={
            "node_id": "peer-node-1",
            "url": "http://peer-one.test:8000",
            "network_name": "zoidberg-testnet",
        },
    )

    assert response.status_code == 200
    assert compare_calls == [("super-secret-value", "super-secret-value")]


def test_public_endpoint_does_not_require_peer_secret(blockchain, monkeypatch):
    _configure_peer_auth(monkeypatch, enabled=True)
    client = _client(blockchain)

    response = client.get("/chain/summary")

    assert response.status_code == 200


def test_outbound_peer_broadcast_includes_auth_header_when_enabled(
    blockchain,
    submission_image,
    wallets,
    monkeypatch,
):
    import peer_sync

    _configure_peer_auth(monkeypatch, enabled=True)
    client = _client(blockchain)
    _register_peer(client, secret="super-secret-value")
    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Peer auth broadcast",
        submitter=wallets["owner"].public_key,
    )
    calls = []

    def fake_post(url, json, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return type("Response", (), {"status_code": 200, "text": "ok"})()

    monkeypatch.setattr(peer_sync.requests, "post", fake_post)

    response = client.post(f"/submissions/{submission.submission_id}/broadcast")

    assert response.status_code == 200
    assert calls[0]["headers"]["X-ZOID-Peer-Secret"] == "super-secret-value"


def test_outbound_peer_broadcast_omits_auth_header_when_disabled(
    blockchain,
    submission_image,
    wallets,
    monkeypatch,
):
    import peer_sync

    _configure_peer_auth(monkeypatch, enabled=False)
    client = _client(blockchain)
    _register_peer(client)
    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Peer auth broadcast",
        submitter=wallets["owner"].public_key,
    )
    calls = []

    def fake_post(url, json, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return type("Response", (), {"status_code": 200, "text": "ok"})()

    monkeypatch.setattr(peer_sync.requests, "post", fake_post)

    response = client.post(f"/submissions/{submission.submission_id}/broadcast")

    assert response.status_code == 200
    assert calls[0]["headers"] == {}


def test_signed_peer_request_allowed_in_development_when_enabled(blockchain, monkeypatch):
    _configure_signed_peer_messages(monkeypatch, enabled=True)
    client = _client(blockchain)
    _freeze_peer_time(monkeypatch)

    payload = {
        "node_id": "peer-node-1",
        "url": "http://peer-one.test:8000",
        "network_name": "zoidberg-testnet",
    }
    response = client.post(
        "/peers/register",
        headers=_signed_headers("POST", "/peers/register", payload),
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["peer"]["node_id"] == "peer-node-1"


def test_signed_peer_request_missing_signature_rejected(blockchain, monkeypatch):
    _configure_signed_peer_messages(monkeypatch, enabled=True)
    client = _client(blockchain)
    _freeze_peer_time(monkeypatch)

    response = client.post(
        "/peers/register",
        json={
            "node_id": "peer-node-1",
            "url": "http://peer-one.test:8000",
            "network_name": "zoidberg-testnet",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing Protocol v1 peer headers."


def test_signed_peer_request_rejects_wrong_signature(blockchain, monkeypatch):
    _configure_signed_peer_messages(monkeypatch, enabled=True)
    client = _client(blockchain)
    _freeze_peer_time(monkeypatch)
    payload = {
        "node_id": "peer-node-1",
        "url": "http://peer-one.test:8000",
        "network_name": "zoidberg-testnet",
    }
    headers = _signed_headers("POST", "/peers/register", payload)
    headers["X-ZOID-Signature"] = "0" * 64

    response = client.post("/peers/register", headers=headers, json=payload)

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid peer signature."


def test_signed_peer_request_rejects_expired_timestamp(blockchain, monkeypatch):
    _configure_signed_peer_messages(monkeypatch, enabled=True)
    client = _client(blockchain)
    _freeze_peer_time(monkeypatch)
    payload = {
        "node_id": "peer-node-1",
        "url": "http://peer-one.test:8000",
        "network_name": "zoidberg-testnet",
    }
    headers = _signed_headers("POST", "/peers/register", payload, timestamp=1_699_999_000)

    response = client.post("/peers/register", headers=headers, json=payload)

    assert response.status_code == 401
    assert response.json()["detail"] == "Peer message timestamp outside the allowed window."


def test_signed_peer_request_rejects_future_timestamp(blockchain, monkeypatch):
    _configure_signed_peer_messages(monkeypatch, enabled=True)
    client = _client(blockchain)
    _freeze_peer_time(monkeypatch)
    payload = {
        "node_id": "peer-node-1",
        "url": "http://peer-one.test:8000",
        "network_name": "zoidberg-testnet",
    }
    headers = _signed_headers("POST", "/peers/register", payload, timestamp=1_700_001_000)

    response = client.post("/peers/register", headers=headers, json=payload)

    assert response.status_code == 401
    assert response.json()["detail"] == "Peer message timestamp outside the allowed window."


def test_signed_peer_request_rejects_malformed_timestamp(blockchain, monkeypatch):
    _configure_signed_peer_messages(monkeypatch, enabled=True)
    client = _client(blockchain)
    _freeze_peer_time(monkeypatch)
    payload = {
        "node_id": "peer-node-1",
        "url": "http://peer-one.test:8000",
        "network_name": "zoidberg-testnet",
    }
    headers = _signed_headers("POST", "/peers/register", payload)
    headers["X-ZOID-Timestamp"] = "not-a-number"

    response = client.post("/peers/register", headers=headers, json=payload)

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid peer timestamp."


def test_signed_peer_request_rejects_replayed_nonce_when_enabled(blockchain, monkeypatch):
    _configure_signed_peer_messages(monkeypatch, enabled=True, replay_protection=True)
    client = _client(blockchain)
    _freeze_peer_time(monkeypatch)
    payload = {
        "node_id": "peer-node-1",
        "url": "http://peer-one.test:8000",
        "network_name": "zoidberg-testnet",
    }
    headers = _signed_headers("POST", "/peers/register", payload, nonce="shared-nonce")

    first_response = client.post("/peers/register", headers=headers, json=payload)
    second_response = client.post("/peers/register", headers=headers, json=payload)

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    assert second_response.json()["detail"] in {"Replayed peer nonce.", "Replayed peer message."}


def test_signed_peer_request_allows_replayed_nonce_when_disabled(blockchain, monkeypatch):
    _configure_signed_peer_messages(monkeypatch, enabled=True, replay_protection=False)
    client = _client(blockchain)
    _freeze_peer_time(monkeypatch)
    payload = {
        "node_id": "peer-node-1",
        "url": "http://peer-one.test:8000",
        "network_name": "zoidberg-testnet",
    }
    headers = _signed_headers("POST", "/peers/register", payload, nonce="shared-nonce")

    first_response = client.post("/peers/register", headers=headers, json=payload)
    second_response = client.post("/peers/register", headers=headers, json=payload)

    assert first_response.status_code == 200
    assert second_response.status_code == 200


def test_signed_peer_request_body_tampering_rejected(blockchain, monkeypatch):
    _configure_signed_peer_messages(monkeypatch, enabled=True)
    client = _client(blockchain)
    _freeze_peer_time(monkeypatch)
    signed_payload = {
        "node_id": "peer-node-1",
        "url": "http://peer-one.test:8000",
        "network_name": "zoidberg-testnet",
    }
    tampered_payload = {
        "node_id": "peer-node-1",
        "url": "http://peer-two.test:8000",
        "network_name": "zoidberg-testnet",
    }
    headers = _signed_headers("POST", "/peers/register", signed_payload)

    response = client.post("/peers/register", headers=headers, json=tampered_payload)

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid peer message ID."


def test_signed_peer_request_path_tampering_rejected(monkeypatch):
    _configure_signed_peer_messages(monkeypatch, enabled=True)
    _freeze_peer_time(monkeypatch)
    payload = {
        "origin_node_id": "peer-node-1",
        "network_name": "zoidberg-testnet",
        "submission": {"submission_id": "submission-1"},
    }
    headers = _signed_headers("POST", "/peers/submissions/receive", payload)

    with pytest.raises(peer_sync.InvalidPeerSignatureError):
        peer_sync.verify_peer_signature(
            method="POST",
            path="/peers/votes/receive",
            headers=headers,
            body_bytes=peer_sync._serialize_peer_body(payload),
        )


def test_signed_peer_request_method_tampering_rejected(monkeypatch):
    _configure_signed_peer_messages(monkeypatch, enabled=True)
    _freeze_peer_time(monkeypatch)
    payload = {
        "origin_node_id": "peer-node-1",
        "network_name": "zoidberg-testnet",
        "submission": {"submission_id": "submission-1"},
    }
    headers = _signed_headers("POST", "/peers/submissions/receive", payload)

    with pytest.raises(peer_sync.InvalidPeerSignatureError):
        peer_sync.verify_peer_signature(
            method="GET",
            path="/peers/submissions/receive",
            headers=headers,
            body_bytes=peer_sync._serialize_peer_body(payload),
        )


def test_signed_peer_request_rejects_wrong_network_header(blockchain, monkeypatch):
    _configure_signed_peer_messages(monkeypatch, enabled=True)
    client = _client(blockchain)
    _freeze_peer_time(monkeypatch)
    payload = {
        "node_id": "peer-node-1",
        "url": "http://peer-one.test:8000",
        "network_name": "zoidberg-testnet",
    }

    response = client.post(
        "/peers/register",
        headers=_custom_signed_headers(
            payload,
            message_type="peer-registration",
            network_id="zoidberg-devnet-v1",
        ),
        json=payload,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Peer message belongs to a different network."


def test_signed_peer_request_rejects_wrong_message_type_for_route(blockchain, monkeypatch):
    _configure_signed_peer_messages(monkeypatch, enabled=True)
    client = _client(blockchain)
    _freeze_peer_time(monkeypatch)
    payload = {
        "node_id": "peer-node-1",
        "url": "http://peer-one.test:8000",
        "network_name": "zoidberg-testnet",
    }

    response = client.post(
        "/peers/register",
        headers=_custom_signed_headers(payload, message_type="vote"),
        json=payload,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Peer message type does not match the requested peer route."


def test_signed_peer_request_rejects_wrong_protocol_version(blockchain, monkeypatch):
    _configure_signed_peer_messages(monkeypatch, enabled=True)
    client = _client(blockchain)
    _freeze_peer_time(monkeypatch)
    payload = {
        "node_id": "peer-node-1",
        "url": "http://peer-one.test:8000",
        "network_name": "zoidberg-testnet",
    }

    response = client.post(
        "/peers/register",
        headers=_custom_signed_headers(
            payload,
            message_type="peer-registration",
            protocol_version="2",
        ),
        json=payload,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported peer protocol version: 2."


def test_signed_peer_request_rejects_sender_node_id_mismatch(blockchain, monkeypatch):
    _configure_signed_peer_messages(monkeypatch, enabled=True)
    client = _client(blockchain)
    _freeze_peer_time(monkeypatch)
    payload = {
        "node_id": "peer-node-2",
        "url": "http://peer-one.test:8000",
        "network_name": "zoidberg-testnet",
    }

    response = client.post(
        "/peers/register",
        headers=_signed_headers("POST", "/peers/register", payload, node_id="peer-node-1"),
        json=payload,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Peer sender node_id does not match authenticated sender."


def test_signed_peer_request_rejects_missing_nonce_header(blockchain, monkeypatch):
    _configure_signed_peer_messages(monkeypatch, enabled=True)
    client = _client(blockchain)
    _freeze_peer_time(monkeypatch)
    payload = {
        "node_id": "peer-node-1",
        "url": "http://peer-one.test:8000",
        "network_name": "zoidberg-testnet",
    }
    headers = _signed_headers("POST", "/peers/register", payload)
    headers.pop(HEADER_NONCE)

    response = client.post("/peers/register", headers=headers, json=payload)

    assert response.status_code == 401
    assert "X-ZOID-Nonce" in response.json()["detail"]


def test_signed_peer_request_rejects_malformed_nonce(blockchain, monkeypatch):
    _configure_signed_peer_messages(monkeypatch, enabled=True)
    client = _client(blockchain)
    _freeze_peer_time(monkeypatch)
    payload = {
        "node_id": "peer-node-1",
        "url": "http://peer-one.test:8000",
        "network_name": "zoidberg-testnet",
    }
    headers = _signed_headers("POST", "/peers/register", payload)
    headers[HEADER_NONCE] = "bad nonce"

    response = client.post("/peers/register", headers=headers, json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "Peer nonce must use only letters, digits, '.', '_', ':', or '-'."


def test_explicit_v1_request_does_not_fallback_to_legacy_shared_secret(blockchain, monkeypatch):
    import api

    _configure_signed_peer_messages(monkeypatch, enabled=True)
    monkeypatch.setattr(api, "peer_auth_required", lambda: True)
    monkeypatch.setattr(peer_sync, "peer_auth_required", lambda: True)
    client = _client(blockchain)
    _freeze_peer_time(monkeypatch)
    payload = {
        "node_id": "peer-node-1",
        "url": "http://peer-one.test:8000",
        "network_name": "zoidberg-testnet",
    }

    response = client.post(
        "/peers/register",
        headers={
            HEADER_PEER_MESSAGE_VERSION: "1",
            "X-ZOID-Peer-Secret": "super-secret-value",
        },
        json=payload,
    )

    assert response.status_code == 401
    assert "Missing Protocol v1 peer headers" in response.json()["detail"]


def test_signed_peer_request_rejects_wrong_domain_auth_material(blockchain, monkeypatch):
    _configure_signed_peer_messages(monkeypatch, enabled=True)
    client = _client(blockchain)
    _freeze_peer_time(monkeypatch)
    payload = {
        "node_id": "peer-node-1",
        "url": "http://peer-one.test:8000",
        "network_name": "zoidberg-testnet",
    }
    headers = _signed_headers("POST", "/peers/register", payload)
    mutated_envelope = {
        "domain": "zoidbergchain/vote/v1",
        "message_type": "peer-registration",
        "network_id": "zoidberg-public-testnet-v1",
        "nonce": "nonce-1",
        "object_type": "peer-message",
        "payload": payload,
        "peer_message_version": 1,
        "protocol": "zoidbergchain",
        "protocol_version": 1,
        "sender_node_id": "peer-node-1",
        "timestamp": 1_700_000_000,
    }
    mutated_bytes = canonical_json_bytes(mutated_envelope)
    headers[HEADER_MESSAGE_ID] = hashlib.sha256(mutated_bytes).hexdigest()
    headers["X-ZOID-Signature"] = hmac.new(
        b"super-secret-value",
        mutated_bytes,
        hashlib.sha256,
    ).hexdigest()

    response = client.post("/peers/register", headers=headers, json=payload)

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid peer message ID."


def test_public_endpoint_does_not_require_signed_peer_messages(blockchain, monkeypatch):
    _configure_signed_peer_messages(monkeypatch, enabled=True)
    client = _client(blockchain)

    response = client.get("/chain/summary")

    assert response.status_code == 200


def test_outbound_signed_peer_broadcast_includes_signed_headers_when_enabled(
    blockchain,
    submission_image,
    wallets,
    monkeypatch,
):
    _configure_signed_peer_messages(monkeypatch, enabled=True)
    client = _client(blockchain)
    _freeze_peer_time(monkeypatch)
    monkeypatch.setattr(peer_sync.secrets, "token_hex", lambda _: "nonce-1")
    import api

    api.peer_store.register_peer(
        node_id="peer-node-1",
        url="http://peer-one.test:8000",
        network_name="zoidberg-testnet",
    )
    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Signed peer broadcast",
        submitter=wallets["owner"].public_key,
    )
    calls = []

    def fake_post(url, json, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return type("Response", (), {"status_code": 200, "text": "ok"})()

    monkeypatch.setattr(peer_sync.requests, "post", fake_post)

    response = client.post(f"/submissions/{submission.submission_id}/broadcast")

    assert response.status_code == 200
    assert calls[0]["headers"][HEADER_PEER_MESSAGE_VERSION] == "1"
    assert calls[0]["headers"][HEADER_PROTOCOL_VERSION] == "1"
    assert calls[0]["headers"][HEADER_NETWORK_ID] == "zoidberg-public-testnet-v1"
    assert calls[0]["headers"][HEADER_MESSAGE_TYPE] == "submission"
    assert calls[0]["headers"]["X-ZOID-Node-Id"] == "local-node"
    assert calls[0]["headers"]["X-ZOID-Timestamp"] == "1700000000"
    assert calls[0]["headers"]["X-ZOID-Nonce"] == "nonce-1"
    assert HEADER_MESSAGE_ID in calls[0]["headers"]
    assert "X-ZOID-Signature" in calls[0]["headers"]
    assert "X-ZOID-Peer-Secret" not in calls[0]["headers"]
