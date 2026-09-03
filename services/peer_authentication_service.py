"""Canonical peer request signing and inbound signature verification."""

from dataclasses import dataclass
import hashlib
import hmac
import json
from typing import Callable

from protocol_v1_peer_message import (
    HEADER_NETWORK_ID,
    MissingProtocolV1PeerHeadersError,
    ProtocolV1PeerMessageError,
    ReplayedPeerMessageError,
    build_protocol_v1_peer_request_headers,
    build_protocol_v1_peer_request_payload,
    normalize_protocol_v1_peer_timestamp,
    resolve_protocol_v1_peer_network_id,
    verify_protocol_v1_peer_request,
)

from .peer_network_errors import (
    ExpiredPeerSignatureError,
    InvalidPeerSignatureError,
    InvalidPeerTimestampError,
    MissingSignedPeerHeadersError,
    ReplayedPeerNonceError,
)


@dataclass(frozen=True)
class PeerAuthenticationConfig:
    auth_required: Callable[[], bool]
    replay_protection_enabled: Callable[[], bool]
    shared_secret: Callable[[], str]
    shared_secret_is_configured: Callable[[], bool]
    signature_window_seconds: Callable[[], int]
    signed_messages_enabled: Callable[[], bool]
    now: Callable[[], float]
    nonce: Callable[[int], str]


class PeerAuthenticationService:
    """Owns peer signature bytes, headers, timestamps, and nonce bookkeeping."""

    def __init__(self, config: PeerAuthenticationConfig, nonce_cache: dict[str, dict[str, int]]):
        self.config = config
        self.nonce_cache = nonce_cache

    @staticmethod
    def hash_body(body_bytes):
        if body_bytes is None:
            body_bytes = b""
        if isinstance(body_bytes, str):
            body_bytes = body_bytes.encode("utf-8")
        return hashlib.sha256(body_bytes).hexdigest()

    @staticmethod
    def build_signature_payload(method, path, timestamp, nonce, body_hash):
        return "\n".join(
            [str(method).upper(), str(path), str(timestamp), str(nonce), str(body_hash)]
        )

    def sign_request(self, method, path, timestamp, nonce, body_bytes, secret=None):
        secret = self.config.shared_secret() if secret is None else secret
        canonical_payload = self.build_signature_payload(
            method, path, timestamp, nonce, self.hash_body(body_bytes)
        )
        return hmac.new(
            secret.encode("utf-8"),
            canonical_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def serialize_body(payload):
        if payload is None:
            return b""
        return json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")

    def build_request_headers(self, method, path, payload, origin_node_id, *, network_name=None):
        if network_name is not None and payload is None and str(method).upper() == "GET":
            payload = {"network_name": network_name}
        if self.config.signed_messages_enabled():
            if not self.config.shared_secret_is_configured():
                raise ValueError("PEER_SHARED_SECRET must be configured for signed peer messages.")
            if not isinstance(origin_node_id, str) or not origin_node_id.strip():
                raise ValueError("origin_node_id is required for signed peer messages.")
            timestamp = normalize_protocol_v1_peer_timestamp(int(self.config.now()))
            nonce = self.config.nonce(16)
            payload_network_name = (
                payload.get("network_name")
                if isinstance(payload, dict) and isinstance(payload.get("network_name"), str)
                else None
            )
            return build_protocol_v1_peer_request_headers(
                method,
                path,
                payload if isinstance(payload, dict) else None,
                origin_node_id,
                network_name=network_name or payload_network_name,
                secret=self.config.shared_secret(),
                timestamp=timestamp,
                nonce=nonce,
                query_params=payload if str(method).upper() == "GET" and isinstance(payload, dict) else None,
            )
        if self.config.auth_required() and self.config.shared_secret_is_configured():
            return {"X-ZOID-Peer-Secret": self.config.shared_secret()}
        return {}

    def cleanup_nonce_cache(self, now=None, window_seconds=None):
        if not self.nonce_cache:
            return
        now = int(self.config.now()) if now is None else int(now)
        window_seconds = (
            self.config.signature_window_seconds()
            if window_seconds is None
            else int(window_seconds)
        )
        cutoff = now - window_seconds
        stale_node_ids = []
        for node_id, nonces in list(self.nonce_cache.items()):
            for nonce in [key for key, timestamp in nonces.items() if timestamp < cutoff]:
                nonces.pop(nonce, None)
            if not nonces:
                stale_node_ids.append(node_id)
        for node_id in stale_node_ids:
            self.nonce_cache.pop(node_id, None)

    def record_nonce(self, node_id, nonce, timestamp):
        self.cleanup_nonce_cache(int(self.config.now()), self.config.signature_window_seconds())
        self.nonce_cache.setdefault(node_id, {})[nonce] = int(timestamp)

    def is_replayed_nonce(self, node_id, nonce):
        self.cleanup_nonce_cache(int(self.config.now()), self.config.signature_window_seconds())
        return nonce in self.nonce_cache.get(node_id, {})

    def verify_signature(self, method, path, headers, body_bytes):
        if not self.config.signed_messages_enabled():
            return None
        try:
            body_payload = None
            if body_bytes not in (None, b"", ""):
                decoded_bytes = body_bytes if isinstance(body_bytes, bytes) else str(body_bytes).encode("utf-8")
                body_payload = json.loads(decoded_bytes)
                if not isinstance(body_payload, dict):
                    raise ProtocolV1PeerMessageError(
                        "Protocol v1 peer request payload must be a JSON object."
                    )
            payload = build_protocol_v1_peer_request_payload(
                method, path, body_payload=body_payload
            )
            expected_network_id = headers.get(HEADER_NETWORK_ID)
            if expected_network_id in (None, ""):
                raise MissingProtocolV1PeerHeadersError("Missing Protocol v1 peer headers.")
            context = verify_protocol_v1_peer_request(
                method=method,
                path=path,
                headers=headers,
                payload=payload,
                expected_network_id=resolve_protocol_v1_peer_network_id(
                    network_id=expected_network_id
                ),
                secret=self.config.shared_secret(),
                timestamp_window_seconds=self.config.signature_window_seconds(),
                replay_store=None,
                now=int(self.config.now()),
            )
        except MissingProtocolV1PeerHeadersError as exc:
            raise MissingSignedPeerHeadersError(str(exc)) from exc
        except ReplayedPeerMessageError as exc:
            raise ReplayedPeerNonceError(str(exc)) from exc
        except ProtocolV1PeerMessageError as exc:
            message = str(exc)
            if "timestamp outside the allowed window" in message.lower():
                raise ExpiredPeerSignatureError(message) from exc
            if "timestamp" in message.lower():
                raise InvalidPeerTimestampError(message) from exc
            raise InvalidPeerSignatureError(message) from exc
        return str(context.sender_node_id)
