import ast
from pathlib import Path

import pytest

from content import resolve_payload_hash
from protocol_v1_peer_message import resolve_protocol_v1_peer_network_id
from services import (
    ChainSyncCollaborators,
    ChainSyncState,
    ContentFetchCollaborators,
    ForkChoiceService,
    PeerAuthenticationConfig,
    PeerAuthenticationService,
    PeerBroadcastService,
    PeerChainSyncService,
    PeerContentSyncService,
    PeerHttpTransport,
)
from services.peer_network_errors import InvalidPeerSignatureError


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class FakeResponse:
    def __init__(self, status_code=200, payload=None, *, content=b"", headers=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._payload


def _auth_service(*, now=1_800_000_000):
    return PeerAuthenticationService(
        PeerAuthenticationConfig(
            auth_required=lambda: False,
            replay_protection_enabled=lambda: True,
            shared_secret=lambda: "task-10-shared-secret",
            shared_secret_is_configured=lambda: True,
            signature_window_seconds=lambda: 300,
            signed_messages_enabled=lambda: True,
            now=lambda: now,
            nonce=lambda _: "task10-nonce",
        ),
        {},
    )


def test_authentication_service_preserves_canonical_signed_bytes_and_detects_tampering():
    service = _auth_service()
    payload = {
        "origin_node_id": "node-a",
        "network_name": "zoidberg-testnet",
        "submission": {"submission_id": "a" * 32},
    }
    path = "/peers/submissions/receive"
    body = service.serialize_body(payload)
    headers = service.build_request_headers("POST", path, payload, "node-a")

    assert service.verify_signature("POST", path, headers, body) == "node-a"
    with pytest.raises(InvalidPeerSignatureError):
        service.verify_signature("POST", path, headers, service.serialize_body({**payload, "network_name": "tampered"}))


def test_broadcast_service_preserves_partial_failure_aggregation():
    class RequestError(Exception):
        pass

    class Client:
        RequestException = RequestError

        @staticmethod
        def post(url, **kwargs):
            if "peer-b" in url:
                raise RequestError("connection refused")
            return FakeResponse()

    class PeerStore:
        @staticmethod
        def list_active_peers(network_name):
            return [
                {"node_id": "a", "url": "http://peer-a"},
                {"node_id": "b", "url": "http://peer-b"},
            ]

    class Submission:
        submission_id = "s" * 32

        @staticmethod
        def to_dict():
            return {"submission_id": Submission.submission_id}

    class Logger:
        @staticmethod
        def warning(*args):
            pass

    service = PeerBroadcastService(PeerHttpTransport(Client), lambda *args, **kwargs: {}, Logger())
    report = service.broadcast_submission(
        Submission(), PeerStore(), "node-a", "zoidberg-testnet", 3
    )

    assert (report["attempted"], report["succeeded"], report["failed"]) == (2, 1, 1)
    assert [item["status"] for item in report["results"]] == ["sent", "failed"]


def test_content_service_preserves_full_model_a_media_bytes(blockchain, submission_image):
    media_bytes = Path(submission_image).read_bytes()
    resolved = resolve_payload_hash(media_bytes, "image/jpeg")

    class Transport:
        def get(self, url, **kwargs):
            if url.endswith("/metadata"):
                return FakeResponse(payload={"content": {
                    "file_size_bytes": len(media_bytes),
                    "mime_type": "image/jpeg",
                    "submitted_by": "peer-content",
                    "content_type": "image",
                }})
            return FakeResponse(content=media_bytes, headers={"content-type": "image/jpeg"})

    service = PeerContentSyncService(Transport(), lambda *args, **kwargs: {}, object(), 10_000_000)
    result = service.fetch_and_register(
        ContentFetchCollaborators(
            data_dir=blockchain.storage.data_dir,
            register_uploaded_content=blockchain.register_uploaded_content,
        ),
        {"node_id": "peer-a", "url": "http://peer-a", "network_name": "zoidberg-testnet"},
        resolved["content_hash"],
        origin_node_id="node-a",
    )

    assert result["status"] == "fetched_and_verified"
    stored = blockchain.get_content_object_by_hash(resolved["content_hash"])
    assert Path(stored.local_path).read_bytes() == media_bytes


def test_chain_sync_service_delegates_ranking_validation_and_adoption():
    network_name = "zoidberg-testnet"
    network_id = resolve_protocol_v1_peer_network_id(network_name=network_name)
    summary = {
        "network_name": network_name,
        "network_id": network_id,
        "protocol_version": 1,
        "node_id": "peer-a",
        "chain_height": 1,
        "latest_block_hash": "b" * 64,
        "genesis_hash": "a" * 64,
        "cumulative_originality_score": 1.0,
    }

    class Transport:
        def get(self, url, **kwargs):
            if url.endswith("/summary"):
                return FakeResponse(payload=summary)
            return FakeResponse(payload={"blocks": [{"index": 0}, {"index": 1}], "certificates": []})

    adopted = []
    candidate = [object(), object()]
    comparison = {
        "decision": "replace_with_candidate", "reason": "higher_originality_score",
        "candidate_height": 1, "local_latest_hash": "c" * 64,
        "candidate_latest_hash": "b" * 64, "local_score": 0.0,
        "candidate_score": 1.0,
    }
    collaborators = ChainSyncCollaborators(
        compare_summaries=ForkChoiceService.compare_summary_metrics,
        store_certificates=lambda payloads: None,
        validate_candidate=lambda blocks, **kwargs: candidate,
        compare_candidate=lambda blocks: comparison,
        adopt_candidate=lambda blocks: adopted.append(blocks) or {
            "appended": 1, "latest_block_hash": "b" * 64
        },
    )
    service = PeerChainSyncService(Transport(), lambda *args, **kwargs: {}, object())
    result = service.sync_peer(
        {"node_id": "peer-a", "url": "http://peer-a"},
        origin_node_id="node-a",
        network_name=network_name,
        timeout_seconds=5,
        state=ChainSyncState(0, "c" * 64, "a" * 64, 0.0, network_id),
        collaborators=collaborators,
    )

    assert result["status"] == "synced"
    assert result["decision"] == "replace_with_candidate"
    assert adopted == [candidate]


def test_peer_services_are_framework_independent_and_do_not_import_blockchain():
    service_paths = sorted((PROJECT_ROOT / "services").glob("peer_*_service.py"))
    assert service_paths
    for path in service_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        assert not any(name == "api" or name.startswith("fastapi") for name in imported)
        assert "blockchain" not in imported

    chain_source = (PROJECT_ROOT / "services" / "peer_chain_sync_service.py").read_text(encoding="utf-8")
    assert "peer_score < local_score" not in chain_source
    assert "peer_score > local_score" not in chain_source
