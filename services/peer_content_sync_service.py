"""Content discovery and full Model A media synchronization."""

from dataclasses import dataclass
from typing import Callable

from content import (
    resolve_payload_hash,
    store_content_bytes,
    validate_content_size,
    validate_mime_type,
)
from validators import is_valid_content_hash
from media_admission_policy import media_admission_policy
from media_technical_validation import TechnicalMediaValidationError, validate_media_bytes

from .peer_network_errors import ContentSyncError


@dataclass(frozen=True)
class ContentFetchCollaborators:
    data_dir: object
    register_uploaded_content: Callable[..., object]


@dataclass(frozen=True)
class ContentDiscoveryCollaborators:
    get_content_object_by_hash: Callable[[str], object]
    list_active_peers: Callable[..., list]
    fetch_content: Callable[..., dict]


class PeerContentSyncService:
    def __init__(self, transport, build_headers, logger, max_content_file_size_bytes):
        self.transport = transport
        self.build_headers = build_headers
        self.logger = logger
        self.max_content_file_size_bytes = max_content_file_size_bytes

    def fetch_and_register(
        self, collaborators: ContentFetchCollaborators, peer, content_hash,
        *, origin_node_id, timeout_seconds=3
    ):
        if not is_valid_content_hash(content_hash):
            raise ContentSyncError(
                "content_hash must be a 64-character lowercase hexadecimal string."
            )

        metadata_path = f"/peers/content/{content_hash}/metadata"
        metadata_headers = self.build_headers(
            "GET", metadata_path, None, origin_node_id,
            network_name=peer.get("network_name"),
        )
        metadata_kwargs = {"timeout": timeout_seconds}
        if metadata_headers:
            metadata_kwargs["headers"] = metadata_headers
        metadata_response = self.transport.get(
            f"{peer['url'].rstrip('/')}{metadata_path}", **metadata_kwargs
        )
        metadata_status = getattr(metadata_response, "status_code", None)
        if metadata_status == 404:
            return {"status": "not_found", "peer": peer.get("node_id"), "content_hash": content_hash}
        if metadata_status is None or metadata_status >= 400:
            raise ContentSyncError(
                f"Peer content metadata returned status {metadata_status}: "
                f"{getattr(metadata_response, 'text', '')}"
            )

        metadata_payload = metadata_response.json()
        metadata = metadata_payload.get("content") if isinstance(metadata_payload, dict) else None
        if not isinstance(metadata, dict):
            raise ContentSyncError("Peer content metadata response is malformed.")

        policy = media_admission_policy()
        accepted_limit = policy["consensus_protocol"]["byte_limits"]["accepted_image_bytes"]
        allowed_mimes = {item["mime_type"] for item in policy["consensus_protocol"]["allowed_media_types"]}
        file_size_bytes = metadata.get("file_size_bytes")
        if isinstance(file_size_bytes, int) and (file_size_bytes <= 0 or file_size_bytes > accepted_limit):
            return {"status": "failed_verification", "reason": "oversized_metadata", "peer": peer.get("node_id")}
        if isinstance(metadata.get("mime_type"), str) and metadata.get("mime_type").lower() not in allowed_mimes:
            return {"status": "failed_verification", "reason": "unsupported_mime_type", "peer": peer.get("node_id")}

        binary_path = f"/peers/content/{content_hash}"
        binary_headers = self.build_headers(
            "GET", binary_path, None, origin_node_id,
            network_name=peer.get("network_name"),
        )
        binary_kwargs = {"timeout": timeout_seconds}
        if binary_headers:
            binary_kwargs["headers"] = binary_headers
        binary_kwargs["stream"] = True
        binary_response = self.transport.get(
            f"{peer['url'].rstrip('/')}{binary_path}", **binary_kwargs
        )
        binary_status = getattr(binary_response, "status_code", None)
        if binary_status == 404:
            return {"status": "not_found", "peer": peer.get("node_id"), "content_hash": content_hash}
        if binary_status is None or binary_status >= 400:
            raise ContentSyncError(
                f"Peer content returned status {binary_status}: {getattr(binary_response, 'text', '')}"
            )

        response_length = getattr(binary_response, "headers", {}).get("content-length")
        try:
            if response_length is not None and int(response_length) > accepted_limit:
                return {"status": "failed_verification", "reason": "oversized_payload", "peer": peer.get("node_id")}
        except (TypeError, ValueError):
            pass
        if callable(getattr(binary_response, "iter_content", None)):
            chunks, received = [], 0
            for chunk in binary_response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                received += len(chunk)
                if received > accepted_limit:
                    return {"status": "failed_verification", "reason": "oversized_payload", "peer": peer.get("node_id")}
                chunks.append(chunk)
            payload_bytes = b"".join(chunks)
        else:
            payload_bytes = binary_response.content
        if not payload_bytes:
            return {"status": "failed_verification", "reason": "empty_payload", "peer": peer.get("node_id")}
        try:
            validated_media = validate_media_bytes(
                payload_bytes,
                declared_mime_type=str(
                    metadata.get("mime_type")
                    or binary_response.headers.get("content-type")
                    or "application/octet-stream"
                ).split(";")[0].strip(),
            )
            resolved_payload = {
                "content_hash": validated_media.result["raw_media_sha256"],
                "stored_bytes": validated_media.raw_media_bytes,
                "mime_type": validated_media.result["detected_mime_type"],
                "text_content": validated_media.text_content,
                "hash_scheme": "sha256_text" if validated_media.result["detected_mime_type"] == "text/plain" else "sha256_bytes",
            }
        except (TechnicalMediaValidationError, UnicodeDecodeError, ValueError) as exc:
            raise ContentSyncError(str(exc)) from exc

        if resolved_payload["content_hash"] != content_hash:
            return {
                "status": "failed_verification",
                "reason": "hash_mismatch",
                "peer": peer.get("node_id"),
                "expected_content_hash": content_hash,
                "actual_content_hash": resolved_payload["content_hash"],
            }

        try:
            stored_content = store_content_bytes(
                content_hash,
                resolved_payload["stored_bytes"],
                mime_type=resolved_payload["mime_type"],
                data_dir=collaborators.data_dir,
                hash_scheme=resolved_payload["hash_scheme"],
                technical_validation=validated_media.result,
            )
            content_object = collaborators.register_uploaded_content(
                content_hash=content_hash,
                submitted_by=metadata.get("submitted_by") or "peer-content",
                mime_type=resolved_payload["mime_type"],
                file_size_bytes=stored_content["file_size_bytes"],
                storage_status=stored_content["storage_status"],
                local_path=stored_content["local_path"],
                file_name=stored_content["file_name"],
                caption=metadata.get("caption"),
                text_content=resolved_payload["text_content"],
                content_type_hint=metadata.get("content_type"),
                byte_hash=stored_content["byte_hash"],
                hash_scheme=stored_content["hash_scheme"],
                technical_validation=validated_media.result,
            )
        except (UnicodeDecodeError, ValueError) as exc:
            raise ContentSyncError(str(exc)) from exc
        return {
            "status": "fetched_and_verified",
            "peer": peer.get("node_id"),
            "content_hash": content_hash,
            "content": content_object.to_dict(),
        }

    def sync_missing(
        self, collaborators: ContentDiscoveryCollaborators, content_hash,
        *, origin_node_id, network_name, timeout_seconds,
    ):
        content_object = collaborators.get_content_object_by_hash(content_hash)
        if content_object is not None and content_object.storage_status == "verified":
            return {"status": "already_verified", "content_hash": content_hash}
        peers = collaborators.list_active_peers(network_name=network_name)
        if not peers:
            return {"status": "no_peers_available", "content_hash": content_hash}
        saw_verification_failure = False
        saw_not_found = False
        for peer in peers:
            try:
                result = collaborators.fetch_content(
                    peer, content_hash,
                    origin_node_id=origin_node_id, timeout_seconds=timeout_seconds,
                )
            except Exception as exc:
                self.logger.warning(
                    "Failed to fetch content %s from peer %s at %s: %s",
                    content_hash, peer.get("node_id"), peer.get("url"), exc,
                )
                continue
            if result["status"] == "fetched_and_verified":
                return result
            if result["status"] == "failed_verification":
                saw_verification_failure = True
            if result["status"] == "not_found":
                saw_not_found = True
        if saw_verification_failure:
            return {"status": "failed_verification", "content_hash": content_hash}
        if saw_not_found:
            return {"status": "not_found", "content_hash": content_hash}
        return {"status": "no_peers_available", "content_hash": content_hash}
