"""Peer chain-summary retrieval and consensus-delegating sync coordination."""

from dataclasses import dataclass
import math
from typing import Callable

from protocol_v1 import PROTOCOL_VERSION
from protocol_v1_peer_message import resolve_protocol_v1_peer_network_id

from .peer_network_errors import ChainSyncError


@dataclass(frozen=True)
class ChainSyncState:
    local_height: int
    local_latest_hash: str
    local_genesis_hash: str
    local_score: float
    local_network_id: str


@dataclass(frozen=True)
class ChainSyncCollaborators:
    compare_summaries: Callable[..., dict]
    store_certificates: Callable[[list], None]
    validate_candidate: Callable[..., list]
    compare_candidate: Callable[[list], dict]
    adopt_candidate: Callable[[list], dict]


class PeerChainSyncService:
    def __init__(self, transport, build_headers, logger):
        self.transport = transport
        self.build_headers = build_headers
        self.logger = logger

    @staticmethod
    def normalize_summary(summary):
        if not isinstance(summary, dict):
            raise ChainSyncError("Peer chain summary must be an object.")
        required = [
            "network_name", "network_id", "protocol_version", "node_id",
            "chain_height", "latest_block_hash", "genesis_hash",
        ]
        for field_name in required:
            if field_name not in summary:
                raise ChainSyncError(f"Peer chain summary missing {field_name}.")
        if not isinstance(summary["network_name"], str) or not summary["network_name"].strip():
            raise ChainSyncError("Peer chain summary network_name is required.")
        if not isinstance(summary["network_id"], str) or not summary["network_id"].strip():
            raise ChainSyncError("Peer chain summary network_id is required.")
        try:
            network_id = resolve_protocol_v1_peer_network_id(network_id=summary["network_id"].strip())
        except ValueError as exc:
            raise ChainSyncError("Peer chain summary network_id is invalid.") from exc
        protocol_version = summary["protocol_version"]
        if isinstance(protocol_version, bool) or not isinstance(protocol_version, int) or protocol_version != PROTOCOL_VERSION:
            raise ChainSyncError("Peer chain summary protocol_version is unsupported.")
        if not isinstance(summary["node_id"], str) or not summary["node_id"].strip():
            raise ChainSyncError("Peer chain summary node_id is required.")
        if not isinstance(summary["chain_height"], int) or summary["chain_height"] < 0:
            raise ChainSyncError("Peer chain summary chain_height must be a non-negative integer.")
        if not isinstance(summary["latest_block_hash"], str) or not summary["latest_block_hash"].strip():
            raise ChainSyncError("Peer chain summary latest_block_hash is required.")
        if not isinstance(summary["genesis_hash"], str) or not summary["genesis_hash"].strip():
            raise ChainSyncError("Peer chain summary genesis_hash is required.")
        try:
            cumulative_score = float(summary.get("cumulative_originality_score", 0))
        except (TypeError, ValueError):
            raise ChainSyncError("Peer chain summary cumulative_originality_score must be numeric.")
        if not math.isfinite(cumulative_score) or cumulative_score < 0:
            raise ChainSyncError("Peer chain summary cumulative_originality_score must be non-negative.")
        return {
            **summary,
            "network_name": summary["network_name"].strip(),
            "network_id": network_id,
            "protocol_version": protocol_version,
            "node_id": summary["node_id"].strip(),
            "latest_block_hash": summary["latest_block_hash"].strip(),
            "genesis_hash": summary["genesis_hash"].strip(),
            "cumulative_originality_score": round(cumulative_score, 8),
        }

    def fetch_summary(self, peer, *, origin_node_id, network_name, timeout_seconds):
        path = "/peers/chain/summary"
        headers = self.build_headers(
            "GET", path, None, origin_node_id, network_name=network_name
        )
        kwargs = {"timeout": timeout_seconds}
        if headers:
            kwargs["headers"] = headers
        response = self.transport.get(f"{peer['url'].rstrip('/')}{path}", **kwargs)
        status_code = getattr(response, "status_code", None)
        if status_code is None or status_code >= 400:
            raise ChainSyncError(f"Peer summary returned status {status_code}.")
        return self.normalize_summary(response.json())

    def fetch_blocks(self, peer, from_height, *, origin_node_id, network_name, timeout_seconds):
        path = "/peers/chain/blocks"
        query_payload = {"from_height": from_height, "include_media_bytes": True}
        headers = self.build_headers(
            "GET", path, query_payload, origin_node_id, network_name=network_name
        )
        kwargs = {
            "params": {"from_height": from_height, "include_media_bytes": "true"},
            "timeout": timeout_seconds,
        }
        if headers:
            kwargs["headers"] = headers
        response = self.transport.get(f"{peer['url'].rstrip('/')}{path}", **kwargs)
        status_code = getattr(response, "status_code", None)
        if status_code is None or status_code >= 400:
            raise ChainSyncError(f"Peer blocks returned status {status_code}.")
        payload = response.json()
        certificates = []
        if isinstance(payload, dict):
            blocks = payload.get("blocks")
            certificates = payload.get("certificates", [])
        else:
            blocks = payload
        if not isinstance(blocks, list):
            raise ChainSyncError("Peer blocks response must include a blocks list.")
        if not isinstance(certificates, list):
            raise ChainSyncError("Peer blocks certificates must be a list when provided.")
        normalized_blocks = []
        normalized_certificates = list(certificates)
        for block_payload in blocks:
            if isinstance(block_payload, dict) and "block" in block_payload:
                normalized_blocks.append(block_payload["block"])
                if block_payload.get("certificate") is not None:
                    normalized_certificates.append(block_payload["certificate"])
            else:
                normalized_blocks.append(block_payload)
        return {"blocks": normalized_blocks, "certificates": normalized_certificates}

    @staticmethod
    def result(
        peer, status, reason, local_height=None, peer_height=None,
        candidate_height=None, appended=0, latest_block_hash=None,
        local_latest_hash=None, candidate_latest_hash=None, local_score=None,
        peer_score=None, candidate_score=None, decision=None,
    ):
        value = {
            "node_id": peer.get("node_id"), "url": peer.get("url"),
            "status": status, "reason": reason, "appended": appended,
        }
        for key, item in [
            ("local_height", local_height), ("peer_height", peer_height),
            ("candidate_height", candidate_height), ("latest_block_hash", latest_block_hash),
            ("local_latest_hash", local_latest_hash), ("candidate_latest_hash", candidate_latest_hash),
            ("local_score", local_score), ("peer_score", peer_score),
            ("candidate_score", candidate_score), ("decision", decision),
        ]:
            if item is not None:
                value[key] = item
        return value

    def sync_peer(
        self, peer, *, origin_node_id, network_name, timeout_seconds,
        state: ChainSyncState, collaborators: ChainSyncCollaborators,
    ):
        summary = self.fetch_summary(
            peer, origin_node_id=origin_node_id, network_name=network_name,
            timeout_seconds=timeout_seconds,
        )
        peer_score = summary["cumulative_originality_score"]
        peer_height = summary["chain_height"]
        peer_latest_hash = summary["latest_block_hash"]
        common = dict(
            local_height=state.local_height, peer_height=peer_height,
            candidate_height=peer_height, local_latest_hash=state.local_latest_hash,
            candidate_latest_hash=peer_latest_hash, local_score=state.local_score,
            peer_score=peer_score, candidate_score=peer_score,
        )
        if summary["network_name"] != network_name or summary["network_id"] != state.local_network_id:
            return self.result(peer, "skipped", "wrong_network", decision="invalid_candidate", **common)
        if summary["genesis_hash"] != state.local_genesis_hash:
            return self.result(peer, "skipped", "different_genesis_hash", decision="invalid_candidate", **common)

        preliminary = collaborators.compare_summaries(
            local_score=state.local_score, candidate_score=peer_score,
            local_height=state.local_height, candidate_height=peer_height,
            local_latest_hash=state.local_latest_hash,
            candidate_latest_hash=peer_latest_hash,
        )
        if preliminary["decision"] != "replace_with_candidate":
            return self.result(
                peer, "skipped", preliminary["reason"],
                decision=preliminary["decision"], **common,
            )

        candidate_payload = self.fetch_blocks(
            peer, 0, origin_node_id=origin_node_id, network_name=network_name,
            timeout_seconds=timeout_seconds,
        )
        collaborators.store_certificates(candidate_payload.get("certificates", []))
        candidate_chain = collaborators.validate_candidate(
            candidate_payload["blocks"],
            expected_latest_hash=peer_latest_hash,
            expected_genesis_hash=state.local_genesis_hash,
            expected_height=peer_height,
        )
        comparison = collaborators.compare_candidate(candidate_chain)
        if comparison["decision"] != "replace_with_candidate":
            return self.result(
                peer, "skipped", comparison["reason"],
                local_height=state.local_height, peer_height=peer_height,
                candidate_height=comparison["candidate_height"],
                local_latest_hash=comparison["local_latest_hash"],
                candidate_latest_hash=comparison["candidate_latest_hash"],
                local_score=comparison["local_score"], peer_score=peer_score,
                candidate_score=comparison["candidate_score"], decision=comparison["decision"],
            )
        adoption = collaborators.adopt_candidate(candidate_chain)
        return self.result(
            peer, "synced", comparison["reason"],
            local_height=state.local_height, peer_height=peer_height,
            candidate_height=comparison["candidate_height"],
            appended=adoption["appended"], latest_block_hash=adoption["latest_block_hash"],
            local_latest_hash=comparison["local_latest_hash"],
            candidate_latest_hash=comparison["candidate_latest_hash"],
            local_score=comparison["local_score"], peer_score=peer_score,
            candidate_score=comparison["candidate_score"], decision=comparison["decision"],
        )

    def sync_all(self, peers, sync_peer):
        results = []
        for peer in peers:
            try:
                result = sync_peer(peer)
            except Exception as exc:
                self.logger.warning(
                    "Failed to sync chain from peer %s at %s: %s",
                    peer.get("node_id"), peer.get("url"), exc,
                )
                result = {
                    "node_id": peer.get("node_id"), "url": peer.get("url"),
                    "status": "failed", "reason": str(exc),
                }
            results.append(result)
        return {
            "attempted": len(results),
            "synced": sum(1 for result in results if result["status"] == "synced"),
            "skipped": sum(1 for result in results if result["status"] == "skipped"),
            "failed": sum(1 for result in results if result["status"] == "failed"),
            "results": results,
        }
