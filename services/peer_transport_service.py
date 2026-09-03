"""Raw peer HTTP transport and behavior-compatible broadcast aggregation."""


class PeerHttpTransport:
    """The only networking service that knows the concrete HTTP client library."""

    def __init__(self, request_client):
        self.request_client = request_client

    @property
    def request_error(self):
        return self.request_client.RequestException

    def get(self, url, **kwargs):
        return self.request_client.get(url, **kwargs)

    def post(self, url, **kwargs):
        return self.request_client.post(url, **kwargs)


class PeerBroadcastService:
    def __init__(self, transport, build_headers, logger):
        self.transport = transport
        self.build_headers = build_headers
        self.logger = logger

    @staticmethod
    def _report(results):
        return {
            "attempted": len(results),
            "succeeded": sum(1 for result in results if result["status"] == "sent"),
            "failed": sum(1 for result in results if result["status"] == "failed"),
            "results": results,
        }

    def _broadcast_standard(
        self,
        *,
        peer_store,
        network_name,
        origin_node_id,
        timeout_seconds,
        path,
        payload,
        object_kind,
        object_id,
    ):
        results = []
        for peer in peer_store.list_active_peers(network_name=network_name):
            receive_url = f"{peer['url'].rstrip('/')}{path}"
            try:
                response = self.transport.post(
                    receive_url,
                    json=payload,
                    headers=self.build_headers("POST", path, payload, origin_node_id),
                    timeout=timeout_seconds,
                )
                status_code = getattr(response, "status_code", None)
                if status_code is None or status_code >= 400:
                    raise self.transport.request_error(
                        f"Peer returned status {status_code}: {getattr(response, 'text', '')}"
                    )
                results.append({"node_id": peer["node_id"], "url": peer["url"], "status": "sent"})
            except self.transport.request_error as exc:
                if object_kind == "vote":
                    self.logger.warning(
                        "Failed to broadcast vote for submission %s to peer %s at %s: %s",
                        object_id, peer.get("node_id"), receive_url, exc,
                    )
                else:
                    self.logger.warning(
                        f"Failed to broadcast {object_kind} %s to peer %s at %s: %s",
                        object_id, peer.get("node_id"), receive_url, exc,
                    )
                results.append({
                    "node_id": peer.get("node_id"),
                    "url": peer.get("url"),
                    "status": "failed",
                    "error": str(exc),
                })
        return self._report(results)

    def broadcast_submission(self, submission, peer_store, origin_node_id, network_name, timeout_seconds):
        payload = {
            "origin_node_id": origin_node_id,
            "network_name": network_name,
            "submission": submission.to_dict(),
        }
        return self._broadcast_standard(
            peer_store=peer_store,
            network_name=network_name,
            origin_node_id=origin_node_id,
            timeout_seconds=timeout_seconds,
            path="/peers/submissions/receive",
            payload=payload,
            object_kind="submission",
            object_id=submission.submission_id,
        )

    def broadcast_vote(self, vote, peer_store, origin_node_id, network_name, timeout_seconds):
        payload = {
            "origin_node_id": origin_node_id,
            "network_name": network_name,
            "submission_id": vote.get("submission_id"),
            "voter": vote.get("voter"),
            "vote_type": vote.get("vote_type"),
            "created_at": vote.get("created_at"),
        }
        for key in [
            "vote_version", "protocol_version", "network_id", "content_hash",
            "voter_wallet_address", "signature_scheme", "vote_signature", "vote_message",
            "signed_message_hash", "vote_nonce", "vote_issued_at", "vote_expires_at",
            "signed_at", "identity_source",
        ]:
            if vote.get(key) is not None:
                payload[key] = vote.get(key)
        return self._broadcast_standard(
            peer_store=peer_store,
            network_name=network_name,
            origin_node_id=origin_node_id,
            timeout_seconds=timeout_seconds,
            path="/peers/votes/receive",
            payload=payload,
            object_kind="vote",
            object_id=vote.get("submission_id"),
        )

    def broadcast_certificate(self, certificate, peer_store, origin_node_id, network_name, timeout_seconds):
        payload = {
            "origin_node_id": origin_node_id,
            "network_name": network_name,
            "certificate": certificate.to_dict(),
        }
        return self._broadcast_standard(
            peer_store=peer_store,
            network_name=network_name,
            origin_node_id=origin_node_id,
            timeout_seconds=timeout_seconds,
            path="/peers/certificates/receive",
            payload=payload,
            object_kind="certificate",
            object_id=certificate.certificate_id,
        )

    def broadcast_block(
        self, block, peer_store, origin_node_id, network_name,
        related_submission_id, certificate, timeout_seconds,
    ):
        payload = {
            "origin_node_id": origin_node_id,
            "network_name": network_name,
            "block": block.to_dict(),
            "related_submission_id": related_submission_id,
            "certificate": certificate.to_dict() if certificate else None,
        }
        results = []
        for peer in peer_store.list_active_peers(network_name=network_name):
            receive_url = f"{peer['url'].rstrip('/')}/peers/blocks/receive"
            certificate_result = None
            try:
                if certificate:
                    certificate_url = f"{peer['url'].rstrip('/')}/peers/certificates/receive"
                    certificate_payload = {
                        "origin_node_id": origin_node_id,
                        "network_name": network_name,
                        "certificate": certificate.to_dict(),
                    }
                    certificate_response = self.transport.post(
                        certificate_url,
                        json=certificate_payload,
                        headers=self.build_headers(
                            "POST", "/peers/certificates/receive", certificate_payload, origin_node_id
                        ),
                        timeout=timeout_seconds,
                    )
                    certificate_status_code = getattr(certificate_response, "status_code", None)
                    if certificate_status_code is None or certificate_status_code >= 400:
                        raise self.transport.request_error(
                            "Certificate peer returned status "
                            f"{certificate_status_code}: {getattr(certificate_response, 'text', '')}"
                        )
                    certificate_result = {"status": "sent", "url": certificate_url}
                response = self.transport.post(
                    receive_url,
                    json=payload,
                    headers=self.build_headers(
                        "POST", "/peers/blocks/receive", payload, origin_node_id
                    ),
                    timeout=timeout_seconds,
                )
                status_code = getattr(response, "status_code", None)
                if status_code is None or status_code >= 400:
                    raise self.transport.request_error(
                        f"Peer returned status {status_code}: {getattr(response, 'text', '')}"
                    )
                results.append({
                    "node_id": peer["node_id"], "url": peer["url"], "status": "sent",
                    "certificate": certificate_result,
                })
            except self.transport.request_error as exc:
                self.logger.warning(
                    "Failed to broadcast block %s to peer %s at %s: %s",
                    block.hash, peer.get("node_id"), receive_url, exc,
                )
                results.append({
                    "node_id": peer.get("node_id"), "url": peer.get("url"),
                    "status": "failed", "error": str(exc), "certificate": certificate_result,
                })
        return self._report(results)

    def broadcast_transaction(
        self, transaction_payload, tx_id, peer_store, origin_node_id, network_name, timeout_seconds
    ):
        payload = {
            "origin_node_id": origin_node_id,
            "network_name": network_name,
            "transaction": transaction_payload,
        }
        results = []
        path = "/peers/transactions/receive"
        for peer in peer_store.list_active_peers(network_name=network_name):
            receive_url = f"{peer['url'].rstrip('/')}{path}"
            try:
                response = self.transport.post(
                    receive_url,
                    json=payload,
                    headers=self.build_headers("POST", path, payload, origin_node_id),
                    timeout=timeout_seconds,
                )
                status_code = getattr(response, "status_code", None)
                body = response.json() if hasattr(response, "json") else {}
                if status_code is None or status_code >= 400:
                    raise self.transport.request_error(
                        f"Peer returned status {status_code}: {getattr(response, 'text', '')}"
                    )
                results.append({
                    "node_id": peer["node_id"], "url": peer["url"], "status": "sent",
                    "accepted": bool(body.get("accepted", True)),
                    "duplicate": bool(body.get("duplicate", False)),
                    "peer_status": body.get("status"),
                })
            except self.transport.request_error as exc:
                self.logger.warning(
                    "Failed to broadcast transaction %s to peer %s at %s: %s",
                    tx_id, peer.get("node_id"), receive_url, exc,
                )
                results.append({
                    "node_id": peer.get("node_id"), "url": peer.get("url"),
                    "status": "failed", "accepted": False, "error": str(exc),
                })
        report = self._report(results)
        report["accepted"] = sum(
            1 for result in results if result["status"] == "sent" and result.get("accepted")
        )
        return {
            "attempted": report["attempted"],
            "succeeded": report["succeeded"],
            "accepted": report["accepted"],
            "failed": report["failed"],
            "results": report["results"],
        }
