import logging
import math

import requests

from block import Block
from config import ORIGINALITY_APPROVAL_THRESHOLD
from originality_certificate import (
    OriginalityCertificate,
    calculate_certificate_id,
    calculate_originality_score,
    validate_certificate_for_submission,
)
from submission import (
    APPROVED,
    HARD_REJECTED,
    MINTED,
    PENDING,
    QUEUED,
    REJECTED,
    SUBMISSION_STATUSES,
    Submission,
    VOTE_TYPES,
    calculate_submission_content_hash,
)
from transaction import Transaction


LATER_THAN_PENDING_STATUSES = {APPROVED, QUEUED, REJECTED, HARD_REJECTED, MINTED}


class PeerSyncError(ValueError):
    pass


class UnauthorizedPeerError(PeerSyncError):
    pass


class WrongNetworkError(PeerSyncError):
    pass


class MalformedSubmissionError(PeerSyncError):
    pass


class DuplicateSubmissionError(PeerSyncError):
    pass


class MalformedVoteError(PeerSyncError):
    pass


class MalformedCertificateError(PeerSyncError):
    pass


class ConflictingCertificateError(PeerSyncError):
    pass


class UnknownSubmissionError(PeerSyncError):
    pass


class ConflictingVoteError(PeerSyncError):
    pass


class MalformedBlockError(PeerSyncError):
    pass


class DuplicateBlockError(PeerSyncError):
    pass


class ChainExtensionError(PeerSyncError):
    pass


class ChainSyncError(PeerSyncError):
    pass


def should_update_submission_status(existing_status, incoming_status=PENDING):
    if existing_status is None:
        return True
    if incoming_status == PENDING and existing_status in LATER_THAN_PENDING_STATUSES:
        return False
    return existing_status != incoming_status


def is_duplicate_submission(blockchain, submission_payload):
    return _find_duplicate_submission(blockchain, submission_payload) is not None


def sync_chain_from_peers(
    blockchain,
    peer_store,
    network_name,
    timeout_seconds=5,
):
    results = []
    active_peers = peer_store.list_active_peers(network_name=network_name)

    for peer in active_peers:
        try:
            result = _sync_chain_from_peer(
                blockchain=blockchain,
                peer=peer,
                network_name=network_name,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            logging.warning(
                "Failed to sync chain from peer %s at %s: %s",
                peer.get("node_id"),
                peer.get("url"),
                exc,
            )
            result = {
                "node_id": peer.get("node_id"),
                "url": peer.get("url"),
                "status": "failed",
                "reason": str(exc),
            }
        results.append(result)

    return {
        "attempted": len(results),
        "synced": sum(1 for result in results if result["status"] == "synced"),
        "skipped": sum(1 for result in results if result["status"] == "skipped"),
        "failed": sum(1 for result in results if result["status"] == "failed"),
        "results": results,
    }


def receive_peer_block(
    blockchain,
    peer_store,
    origin_node_id,
    network_name,
    block_payload,
    related_submission_id,
    local_network_name,
    certificate_payload=None,
):
    if network_name != local_network_name:
        raise WrongNetworkError("Peer block belongs to a different network.")

    peer = peer_store.get_active_peer(origin_node_id)
    if not peer:
        raise UnauthorizedPeerError("Peer is not registered or active.")
    if peer.get("network_name") != local_network_name:
        raise WrongNetworkError("Registered peer belongs to a different network.")

    certificate = None
    if certificate_payload is not None:
        certificate, _action = _store_peer_certificate(
            blockchain=blockchain,
            certificate_payload=certificate_payload,
            local_network_name=local_network_name,
        )

    block = _normalize_block_payload(block_payload)
    existing_block = next(
        (local_block for local_block in blockchain.chain if local_block.hash == block.hash),
        None,
    )
    if existing_block:
        if existing_block.to_dict() != block.to_dict():
            raise DuplicateBlockError("Block hash already exists with different contents.")
        return {
            "accepted": True,
            "status": "duplicate",
            "action": "duplicate",
            "reason": "block_already_exists",
            "block": existing_block.to_dict(),
            "certificate": certificate.to_dict() if certificate else None,
            "submission": None,
        }

    local_latest_block = blockchain.get_latest_block()
    if block.previous_hash != local_latest_block.hash:
        return {
            "accepted": False,
            "status": "sync_needed",
            "reason": "previous_hash_mismatch",
            "local_latest_hash": local_latest_block.hash,
            "received_previous_hash": block.previous_hash,
            "received_block_hash": block.hash,
            "recommended_action": "run_chain_sync",
        }

    for existing_block in blockchain.chain:
        if existing_block.index == block.index:
            raise DuplicateBlockError("Block already exists.")

    _validate_block_extends_chain(blockchain, block, blockchain.chain)

    blockchain.chain.append(block)
    _remove_confirmed_pending_transactions(blockchain, block.transactions)
    minted_submission = _mark_related_submission_minted(blockchain, related_submission_id)
    blockchain.save_blockchain()

    return {
        "accepted": True,
        "status": "accepted",
        "action": "appended",
        "block": block.to_dict(),
        "certificate": certificate.to_dict() if certificate else None,
        "submission": minted_submission.to_dict() if minted_submission else None,
    }


def receive_peer_certificate(
    blockchain,
    peer_store,
    origin_node_id,
    network_name,
    certificate_payload,
    local_network_name,
):
    if network_name != local_network_name:
        raise WrongNetworkError("Peer certificate belongs to a different network.")

    peer = peer_store.get_active_peer(origin_node_id)
    if not peer:
        raise UnauthorizedPeerError("Peer is not registered or active.")
    if peer.get("network_name") != local_network_name:
        raise WrongNetworkError("Registered peer belongs to a different network.")

    certificate, action = _store_peer_certificate(
        blockchain=blockchain,
        certificate_payload=certificate_payload,
        local_network_name=local_network_name,
        save=True,
    )
    return {
        "accepted": True,
        "action": action,
        "certificate": certificate.to_dict(),
    }


def receive_peer_vote(
    blockchain,
    peer_store,
    origin_node_id,
    network_name,
    vote_payload,
    local_network_name,
):
    if network_name != local_network_name:
        raise WrongNetworkError("Peer vote belongs to a different network.")

    peer = peer_store.get_active_peer(origin_node_id)
    if not peer:
        raise UnauthorizedPeerError("Peer is not registered or active.")
    if peer.get("network_name") != local_network_name:
        raise WrongNetworkError("Registered peer belongs to a different network.")

    normalized_vote = _normalize_vote_payload(vote_payload)
    if not blockchain.get_submission(normalized_vote["submission_id"]):
        raise UnknownSubmissionError(f"Submission not found: {normalized_vote['submission_id']}")

    existing_vote = _find_existing_vote(
        blockchain,
        normalized_vote["submission_id"],
        normalized_vote["voter"],
    )
    if existing_vote:
        if existing_vote.get("vote_type") == normalized_vote["vote_type"]:
            return {
                "accepted": True,
                "action": "duplicate",
                "vote": existing_vote,
            }
        raise ConflictingVoteError("Wallet has already voted differently on this submission.")

    try:
        vote = blockchain.cast_submission_vote(
            submission_id=normalized_vote["submission_id"],
            voter=normalized_vote["voter"],
            vote_type=normalized_vote["vote_type"],
            created_at=normalized_vote["created_at"],
        )
    except ValueError as e:
        raise MalformedVoteError(str(e))

    blockchain.save_blockchain()
    return {
        "accepted": True,
        "action": "created",
        "vote": vote,
    }


def receive_peer_submission(
    blockchain,
    peer_store,
    origin_node_id,
    network_name,
    submission_payload,
    local_network_name,
):
    if network_name != local_network_name:
        raise WrongNetworkError("Peer submission belongs to a different network.")

    peer = peer_store.get_active_peer(origin_node_id)
    if not peer:
        raise UnauthorizedPeerError("Peer is not registered or active.")
    if peer.get("network_name") != local_network_name:
        raise WrongNetworkError("Registered peer belongs to a different network.")

    normalized_payload = _normalize_submission_payload(submission_payload)
    existing_submission = _find_duplicate_submission(blockchain, normalized_payload)
    if existing_submission:
        if not should_update_submission_status(existing_submission.status, PENDING):
            if existing_submission.status not in LATER_THAN_PENDING_STATUSES:
                raise DuplicateSubmissionError("Submission already exists.")
            return {
                "accepted": False,
                "action": "ignored",
                "reason": "known_submission_not_downgraded",
                "submission": existing_submission.to_dict(),
            }
        raise DuplicateSubmissionError("Submission already exists.")

    submission = Submission.from_dict({**normalized_payload, "status": PENDING})
    blockchain.submissions.append(submission)
    blockchain.save_blockchain()

    return {
        "accepted": True,
        "action": "created",
        "submission": submission.to_dict(),
    }


def broadcast_submission_to_peers(
    submission,
    peer_store,
    origin_node_id,
    network_name,
    timeout_seconds=3,
):
    payload = {
        "origin_node_id": origin_node_id,
        "network_name": network_name,
        "submission": submission.to_dict(),
    }
    results = []

    for peer in peer_store.list_active_peers(network_name=network_name):
        receive_url = f"{peer['url'].rstrip('/')}/peers/submissions/receive"
        try:
            response = requests.post(receive_url, json=payload, timeout=timeout_seconds)
            status_code = getattr(response, "status_code", None)
            if status_code is None or status_code >= 400:
                raise requests.RequestException(
                    f"Peer returned status {status_code}: {getattr(response, 'text', '')}"
                )

            results.append({
                "node_id": peer["node_id"],
                "url": peer["url"],
                "status": "sent",
            })
        except requests.RequestException as exc:
            logging.warning(
                "Failed to broadcast submission %s to peer %s at %s: %s",
                submission.submission_id,
                peer.get("node_id"),
                receive_url,
                exc,
            )
            results.append({
                "node_id": peer.get("node_id"),
                "url": peer.get("url"),
                "status": "failed",
                "error": str(exc),
            })

    succeeded = sum(1 for result in results if result["status"] == "sent")
    failed = sum(1 for result in results if result["status"] == "failed")
    return {
        "attempted": len(results),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }


def broadcast_vote_to_peers(
    vote,
    peer_store,
    origin_node_id,
    network_name,
    timeout_seconds=3,
):
    payload = {
        "origin_node_id": origin_node_id,
        "network_name": network_name,
        "submission_id": vote.get("submission_id"),
        "voter": vote.get("voter"),
        "vote_type": vote.get("vote_type"),
        "created_at": vote.get("created_at"),
    }
    results = []

    for peer in peer_store.list_active_peers(network_name=network_name):
        receive_url = f"{peer['url'].rstrip('/')}/peers/votes/receive"
        try:
            response = requests.post(receive_url, json=payload, timeout=timeout_seconds)
            status_code = getattr(response, "status_code", None)
            if status_code is None or status_code >= 400:
                raise requests.RequestException(
                    f"Peer returned status {status_code}: {getattr(response, 'text', '')}"
                )

            results.append({
                "node_id": peer["node_id"],
                "url": peer["url"],
                "status": "sent",
            })
        except requests.RequestException as exc:
            logging.warning(
                "Failed to broadcast vote for submission %s to peer %s at %s: %s",
                vote.get("submission_id"),
                peer.get("node_id"),
                receive_url,
                exc,
            )
            results.append({
                "node_id": peer.get("node_id"),
                "url": peer.get("url"),
                "status": "failed",
                "error": str(exc),
            })

    succeeded = sum(1 for result in results if result["status"] == "sent")
    failed = sum(1 for result in results if result["status"] == "failed")
    return {
        "attempted": len(results),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }


def broadcast_votes_to_peers(
    votes,
    peer_store,
    origin_node_id,
    network_name,
    timeout_seconds=3,
):
    vote_results = [
        {
            "vote": vote,
            "broadcast": broadcast_vote_to_peers(
                vote=vote,
                peer_store=peer_store,
                origin_node_id=origin_node_id,
                network_name=network_name,
                timeout_seconds=timeout_seconds,
            ),
        }
        for vote in votes
    ]

    return {
        "vote_count": len(votes),
        "attempted": sum(result["broadcast"]["attempted"] for result in vote_results),
        "succeeded": sum(result["broadcast"]["succeeded"] for result in vote_results),
        "failed": sum(result["broadcast"]["failed"] for result in vote_results),
        "results": vote_results,
    }


def broadcast_certificate_to_peers(
    certificate,
    peer_store,
    origin_node_id,
    network_name,
    timeout_seconds=3,
):
    payload = {
        "origin_node_id": origin_node_id,
        "network_name": network_name,
        "certificate": certificate.to_dict(),
    }
    results = []

    for peer in peer_store.list_active_peers(network_name=network_name):
        receive_url = f"{peer['url'].rstrip('/')}/peers/certificates/receive"
        try:
            response = requests.post(receive_url, json=payload, timeout=timeout_seconds)
            status_code = getattr(response, "status_code", None)
            if status_code is None or status_code >= 400:
                raise requests.RequestException(
                    f"Peer returned status {status_code}: {getattr(response, 'text', '')}"
                )

            results.append({
                "node_id": peer["node_id"],
                "url": peer["url"],
                "status": "sent",
            })
        except requests.RequestException as exc:
            logging.warning(
                "Failed to broadcast certificate %s to peer %s at %s: %s",
                certificate.certificate_id,
                peer.get("node_id"),
                receive_url,
                exc,
            )
            results.append({
                "node_id": peer.get("node_id"),
                "url": peer.get("url"),
                "status": "failed",
                "error": str(exc),
            })

    succeeded = sum(1 for result in results if result["status"] == "sent")
    failed = sum(1 for result in results if result["status"] == "failed")
    return {
        "attempted": len(results),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }


def broadcast_block_to_peers(
    block,
    peer_store,
    origin_node_id,
    network_name,
    related_submission_id=None,
    certificate=None,
    timeout_seconds=3,
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
                certificate_response = requests.post(
                    certificate_url,
                    json=certificate_payload,
                    timeout=timeout_seconds,
                )
                certificate_status_code = getattr(certificate_response, "status_code", None)
                if certificate_status_code is None or certificate_status_code >= 400:
                    raise requests.RequestException(
                        "Certificate peer returned status "
                        f"{certificate_status_code}: {getattr(certificate_response, 'text', '')}"
                    )
                certificate_result = {"status": "sent", "url": certificate_url}

            response = requests.post(receive_url, json=payload, timeout=timeout_seconds)
            status_code = getattr(response, "status_code", None)
            if status_code is None or status_code >= 400:
                raise requests.RequestException(
                    f"Peer returned status {status_code}: {getattr(response, 'text', '')}"
                )

            results.append({
                "node_id": peer["node_id"],
                "url": peer["url"],
                "status": "sent",
                "certificate": certificate_result,
            })
        except requests.RequestException as exc:
            logging.warning(
                "Failed to broadcast block %s to peer %s at %s: %s",
                block.hash,
                peer.get("node_id"),
                receive_url,
                exc,
            )
            results.append({
                "node_id": peer.get("node_id"),
                "url": peer.get("url"),
                "status": "failed",
                "error": str(exc),
                "certificate": certificate_result,
            })

    succeeded = sum(1 for result in results if result["status"] == "sent")
    failed = sum(1 for result in results if result["status"] == "failed")
    return {
        "attempted": len(results),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }


def _sync_chain_from_peer(blockchain, peer, network_name, timeout_seconds):
    local_height = blockchain.get_latest_block().index
    local_latest_hash = blockchain.get_latest_block().hash
    local_genesis_hash = blockchain.chain[0].hash
    local_score = blockchain.get_cumulative_originality_score()

    summary = _fetch_peer_chain_summary(peer, timeout_seconds)
    peer_score = summary["cumulative_originality_score"]
    peer_height = summary["chain_height"]
    peer_latest_hash = summary["latest_block_hash"]
    if summary["network_name"] != network_name:
        return _chain_sync_result(
            peer,
            "skipped",
            "wrong_network",
            local_height=local_height,
            peer_height=peer_height,
            candidate_height=peer_height,
            local_latest_hash=local_latest_hash,
            candidate_latest_hash=peer_latest_hash,
            local_score=local_score,
            peer_score=peer_score,
            candidate_score=peer_score,
            decision="invalid_candidate",
        )
    if summary["genesis_hash"] != local_genesis_hash:
        return _chain_sync_result(
            peer,
            "skipped",
            "different_genesis_hash",
            local_height=local_height,
            peer_height=peer_height,
            candidate_height=peer_height,
            local_latest_hash=local_latest_hash,
            candidate_latest_hash=peer_latest_hash,
            local_score=local_score,
            peer_score=peer_score,
            candidate_score=peer_score,
            decision="invalid_candidate",
        )

    if peer_score < local_score:
        return _chain_sync_result(
            peer,
            "skipped",
            "lower_originality_score",
            local_height=local_height,
            peer_height=peer_height,
            candidate_height=peer_height,
            local_latest_hash=local_latest_hash,
            candidate_latest_hash=peer_latest_hash,
            local_score=local_score,
            peer_score=peer_score,
            candidate_score=peer_score,
            decision="keep_local",
        )
    if peer_score == local_score:
        if peer_height < local_height:
            return _chain_sync_result(
                peer,
                "skipped",
                "lower_chain_height",
                local_height=local_height,
                peer_height=peer_height,
                candidate_height=peer_height,
                local_latest_hash=local_latest_hash,
                candidate_latest_hash=peer_latest_hash,
                local_score=local_score,
                peer_score=peer_score,
                candidate_score=peer_score,
                decision="keep_local",
            )
        if peer_height == local_height:
            if peer_latest_hash == local_latest_hash:
                return _chain_sync_result(
                    peer,
                    "skipped",
                    "same_latest_block_hash",
                    local_height=local_height,
                    peer_height=peer_height,
                    candidate_height=peer_height,
                    local_latest_hash=local_latest_hash,
                    candidate_latest_hash=peer_latest_hash,
                    local_score=local_score,
                    peer_score=peer_score,
                    candidate_score=peer_score,
                    decision="equivalent",
                )
            if peer_latest_hash > local_latest_hash:
                return _chain_sync_result(
                    peer,
                    "skipped",
                    "higher_latest_block_hash",
                    local_height=local_height,
                    peer_height=peer_height,
                    candidate_height=peer_height,
                    local_latest_hash=local_latest_hash,
                    candidate_latest_hash=peer_latest_hash,
                    local_score=local_score,
                    peer_score=peer_score,
                    candidate_score=peer_score,
                    decision="keep_local",
                )

    candidate_payload = _fetch_peer_blocks(
        peer,
        from_height=0,
        timeout_seconds=timeout_seconds,
    )
    _store_chain_sync_certificates(
        blockchain=blockchain,
        certificates_payload=candidate_payload.get("certificates", []),
        local_network_name=network_name,
    )
    candidate_chain = _validate_candidate_chain(
        blockchain,
        candidate_payload["blocks"],
        expected_latest_hash=peer_latest_hash,
        expected_genesis_hash=local_genesis_hash,
        expected_height=peer_height,
    )
    comparison = blockchain.compare_chains_by_originality(blockchain.chain, candidate_chain)
    if comparison["decision"] != "replace_with_candidate":
        return _chain_sync_result(
            peer,
            "skipped",
            comparison["reason"],
            local_height=local_height,
            peer_height=peer_height,
            candidate_height=comparison["candidate_height"],
            local_latest_hash=comparison["local_latest_hash"],
            candidate_latest_hash=comparison["candidate_latest_hash"],
            local_score=comparison["local_score"],
            peer_score=peer_score,
            candidate_score=comparison["candidate_score"],
            decision=comparison["decision"],
        )

    previous_chain_length = len(blockchain.chain)
    for block in candidate_chain:
        _remove_confirmed_pending_transactions(blockchain, block.transactions)
    blockchain.chain = candidate_chain
    blockchain.save_blockchain()

    return _chain_sync_result(
        peer,
        "synced",
        comparison["reason"],
        local_height=local_height,
        peer_height=peer_height,
        candidate_height=comparison["candidate_height"],
        appended=max(0, len(candidate_chain) - previous_chain_length),
        latest_block_hash=blockchain.get_latest_block().hash,
        local_latest_hash=comparison["local_latest_hash"],
        candidate_latest_hash=comparison["candidate_latest_hash"],
        local_score=comparison["local_score"],
        peer_score=peer_score,
        candidate_score=comparison["candidate_score"],
        decision=comparison["decision"],
    )


def _fetch_peer_chain_summary(peer, timeout_seconds):
    summary_url = f"{peer['url'].rstrip('/')}/chain/summary"
    response = requests.get(summary_url, timeout=timeout_seconds)
    status_code = getattr(response, "status_code", None)
    if status_code is None or status_code >= 400:
        raise ChainSyncError(f"Peer summary returned status {status_code}.")
    return _normalize_chain_summary(response.json())


def _fetch_peer_blocks(peer, from_height, timeout_seconds):
    blocks_url = f"{peer['url'].rstrip('/')}/chain/blocks"
    response = requests.get(
        blocks_url,
        params={"from_height": from_height},
        timeout=timeout_seconds,
    )
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

    return {
        "blocks": normalized_blocks,
        "certificates": normalized_certificates,
    }


def _store_chain_sync_certificates(blockchain, certificates_payload, local_network_name):
    for certificate_payload in certificates_payload:
        try:
            _store_peer_certificate(
                blockchain=blockchain,
                certificate_payload=certificate_payload,
                local_network_name=local_network_name,
            )
        except (MalformedCertificateError, ConflictingCertificateError) as exc:
            raise ChainSyncError(str(exc))


def _store_peer_certificate(
    blockchain,
    certificate_payload,
    local_network_name,
    save=False,
):
    if isinstance(certificate_payload, dict):
        raw_certificate_id = certificate_payload.get("certificate_id")
        if isinstance(raw_certificate_id, str) and raw_certificate_id.strip():
            existing_certificate = blockchain.get_originality_certificate(raw_certificate_id.strip())
            if existing_certificate:
                try:
                    incoming_certificate = _normalize_certificate_payload(
                        certificate_payload,
                        local_network_name,
                    )
                except MalformedCertificateError:
                    raise ConflictingCertificateError(
                        "Originality certificate already exists with different contents."
                    )
                if existing_certificate.to_dict() == incoming_certificate.to_dict():
                    return existing_certificate, "duplicate"
                raise ConflictingCertificateError(
                    "Originality certificate already exists with different contents."
                )

    certificate = _normalize_certificate_payload(certificate_payload, local_network_name)
    existing_certificate = blockchain.get_originality_certificate(certificate.certificate_id)
    if existing_certificate:
        if existing_certificate.to_dict() == certificate.to_dict():
            return existing_certificate, "duplicate"
        raise ConflictingCertificateError(
            "Originality certificate already exists with different contents."
        )

    submission = blockchain.get_submission(certificate.submission_id)
    if submission:
        if submission.content_hash != certificate.content_hash:
            raise MalformedCertificateError(
                "Originality certificate content_hash does not match submission."
            )
        if submission.submitter != certificate.creator_wallet:
            raise MalformedCertificateError(
                "Originality certificate creator_wallet does not match submission."
            )
        if submission.status == PENDING:
            submission.transition_to(APPROVED)
        try:
            validate_certificate_for_submission(
                certificate,
                submission,
                network_name=local_network_name,
            )
        except ValueError as exc:
            raise MalformedCertificateError(str(exc))

    blockchain.originality_certificates.append(certificate)
    if save:
        blockchain.save_blockchain()
    return certificate, "created"


def _normalize_certificate_payload(certificate_payload, local_network_name):
    if not isinstance(certificate_payload, dict):
        raise MalformedCertificateError("Certificate payload must be an object.")

    required_fields = [
        "certificate_id",
        "submission_id",
        "content_hash",
        "creator_wallet",
        "vote_total",
        "decisive_vote_total",
        "original_votes",
        "not_original_votes",
        "unsure_votes",
        "approval_percentage",
        "minimum_votes_required",
        "approved_at",
        "network_name",
        "issuing_node_id",
        "vote_hash",
    ]
    for field_name in required_fields:
        if field_name not in certificate_payload:
            raise MalformedCertificateError(f"Certificate {field_name} is required.")

    normalized = {}
    for field_name in [
        "certificate_id",
        "submission_id",
        "content_hash",
        "creator_wallet",
        "network_name",
        "issuing_node_id",
        "vote_hash",
    ]:
        value = certificate_payload.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise MalformedCertificateError(f"Certificate {field_name} is required.")
        normalized[field_name] = value.strip()

    for field_name in [
        "vote_total",
        "decisive_vote_total",
        "original_votes",
        "not_original_votes",
        "unsure_votes",
        "minimum_votes_required",
    ]:
        value = certificate_payload.get(field_name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise MalformedCertificateError(
                f"Certificate {field_name} must be a non-negative integer."
            )
        normalized[field_name] = value

    for field_name in ["approval_percentage", "approved_at"]:
        value = certificate_payload.get(field_name)
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise MalformedCertificateError(f"Certificate {field_name} must be numeric.")
        if not math.isfinite(value) or value < 0:
            raise MalformedCertificateError(
                f"Certificate {field_name} must be a non-negative number."
            )
        normalized[field_name] = value

    if "originality_score" in certificate_payload and certificate_payload.get("originality_score") is not None:
        try:
            originality_score = float(certificate_payload.get("originality_score"))
        except (TypeError, ValueError):
            raise MalformedCertificateError("Certificate originality_score must be numeric.")
        if not math.isfinite(originality_score) or originality_score < 0:
            raise MalformedCertificateError(
                "Certificate originality_score must be a non-negative number."
            )
        normalized["originality_score"] = originality_score

    certificate = OriginalityCertificate.from_dict(normalized)
    _validate_certificate_internal(certificate, local_network_name)
    return certificate


def _validate_certificate_internal(certificate, local_network_name):
    if certificate.network_name != local_network_name:
        raise MalformedCertificateError("Originality certificate belongs to a different network.")
    if not certificate.vote_hash:
        raise MalformedCertificateError("Originality certificate vote_hash is required.")
    if certificate.minimum_votes_required is None:
        raise MalformedCertificateError("Originality certificate minimum_votes_required is required.")
    if certificate.approval_percentage < ORIGINALITY_APPROVAL_THRESHOLD:
        raise MalformedCertificateError(
            "Originality certificate approval percentage is below the required threshold."
        )
    if certificate.originality_score is None:
        raise MalformedCertificateError("Originality certificate originality_score is required.")
    if certificate.originality_score != calculate_originality_score(certificate):
        raise MalformedCertificateError(
            "Originality certificate originality_score is inconsistent."
        )

    vote_counts = [
        certificate.original_votes,
        certificate.not_original_votes,
        certificate.unsure_votes,
        certificate.vote_total,
        certificate.decisive_vote_total,
        certificate.minimum_votes_required,
    ]
    if any(not isinstance(count, int) or count < 0 for count in vote_counts):
        raise MalformedCertificateError(
            "Originality certificate vote totals must be non-negative integers."
        )
    if certificate.vote_total != (
        certificate.original_votes
        + certificate.not_original_votes
        + certificate.unsure_votes
    ):
        raise MalformedCertificateError("Originality certificate vote_total is inconsistent.")
    if certificate.decisive_vote_total != certificate.original_votes + certificate.not_original_votes:
        raise MalformedCertificateError(
            "Originality certificate decisive_vote_total is inconsistent."
        )
    if certificate.decisive_vote_total <= 0:
        raise MalformedCertificateError("Originality certificate must include decisive votes.")

    expected_approval = certificate.original_votes / certificate.decisive_vote_total
    if not math.isclose(certificate.approval_percentage, expected_approval):
        raise MalformedCertificateError(
            "Originality certificate approval percentage is inconsistent."
        )
    if certificate.certificate_id != calculate_certificate_id(certificate.to_core_dict()):
        raise MalformedCertificateError(
            "Originality certificate_id does not match certificate contents."
        )


def _validate_candidate_chain(
    blockchain,
    blocks_payload,
    expected_latest_hash,
    expected_genesis_hash,
    expected_height,
):
    if not blocks_payload:
        raise ChainSyncError("Peer returned no blocks for candidate chain.")

    candidate_chain = [_normalize_block_payload(block_payload) for block_payload in blocks_payload]
    if candidate_chain[0].index != 0:
        raise ChainSyncError("Candidate chain must begin with genesis block.")
    if candidate_chain[0].hash != expected_genesis_hash:
        raise ChainSyncError("Candidate chain genesis hash does not match local genesis.")
    if candidate_chain[-1].index != expected_height:
        raise ChainSyncError("Candidate chain height does not match peer summary.")
    if candidate_chain[-1].hash != expected_latest_hash:
        raise ChainSyncError("Candidate chain did not reach peer latest block hash.")

    for block in candidate_chain:
        metadata = block.certificate_metadata()
        certificate_id = metadata.get("certificate_id")
        if certificate_id and not blockchain.get_originality_certificate(certificate_id):
            raise ChainSyncError(f"Missing originality certificate: {certificate_id}")

    for block in candidate_chain:
        _validate_block_hash(blockchain, block)
        _validate_block_transactions(blockchain, block)

    if not blockchain.is_chain_valid([block.to_dict() for block in candidate_chain]):
        raise ChainSyncError("Candidate chain failed validation.")

    return candidate_chain


def _normalize_chain_summary(summary):
    if not isinstance(summary, dict):
        raise ChainSyncError("Peer chain summary must be an object.")

    for field_name in ["network_name", "node_id", "chain_height", "latest_block_hash", "genesis_hash"]:
        if field_name not in summary:
            raise ChainSyncError(f"Peer chain summary missing {field_name}.")

    if not isinstance(summary["network_name"], str) or not summary["network_name"].strip():
        raise ChainSyncError("Peer chain summary network_name is required.")
    if not isinstance(summary["node_id"], str) or not summary["node_id"].strip():
        raise ChainSyncError("Peer chain summary node_id is required.")
    if not isinstance(summary["chain_height"], int) or summary["chain_height"] < 0:
        raise ChainSyncError("Peer chain summary chain_height must be a non-negative integer.")
    if not isinstance(summary["latest_block_hash"], str) or not summary["latest_block_hash"].strip():
        raise ChainSyncError("Peer chain summary latest_block_hash is required.")
    if not isinstance(summary["genesis_hash"], str) or not summary["genesis_hash"].strip():
        raise ChainSyncError("Peer chain summary genesis_hash is required.")

    cumulative_originality_score = summary.get("cumulative_originality_score", 0)
    try:
        cumulative_originality_score = float(cumulative_originality_score)
    except (TypeError, ValueError):
        raise ChainSyncError("Peer chain summary cumulative_originality_score must be numeric.")
    if not math.isfinite(cumulative_originality_score) or cumulative_originality_score < 0:
        raise ChainSyncError("Peer chain summary cumulative_originality_score must be non-negative.")

    return {
        **summary,
        "network_name": summary["network_name"].strip(),
        "node_id": summary["node_id"].strip(),
        "latest_block_hash": summary["latest_block_hash"].strip(),
        "genesis_hash": summary["genesis_hash"].strip(),
        "cumulative_originality_score": round(cumulative_originality_score, 8),
    }


def _validate_missing_blocks(blockchain, blocks_payload, expected_latest_hash):
    working_chain = list(blockchain.chain)
    validated_blocks = []

    for block_payload in blocks_payload:
        block = _normalize_block_payload(block_payload)
        if any(existing_block.hash == block.hash or existing_block.index == block.index for existing_block in working_chain):
            raise ChainSyncError("Fetched block already exists locally.")
        _validate_block_extends_chain(blockchain, block, working_chain)
        working_chain.append(block)
        validated_blocks.append(block)

    if not validated_blocks:
        raise ChainSyncError("Peer reported a longer chain but returned no missing blocks.")
    if working_chain[-1].hash != expected_latest_hash:
        raise ChainSyncError("Fetched blocks did not reach peer latest block hash.")

    return validated_blocks


def _chain_sync_result(
    peer,
    status,
    reason,
    local_height=None,
    peer_height=None,
    candidate_height=None,
    appended=0,
    latest_block_hash=None,
    local_latest_hash=None,
    candidate_latest_hash=None,
    local_score=None,
    peer_score=None,
    candidate_score=None,
    decision=None,
):
    result = {
        "node_id": peer.get("node_id"),
        "url": peer.get("url"),
        "status": status,
        "reason": reason,
        "appended": appended,
    }
    if local_height is not None:
        result["local_height"] = local_height
    if peer_height is not None:
        result["peer_height"] = peer_height
    if candidate_height is not None:
        result["candidate_height"] = candidate_height
    if latest_block_hash is not None:
        result["latest_block_hash"] = latest_block_hash
    if local_latest_hash is not None:
        result["local_latest_hash"] = local_latest_hash
    if candidate_latest_hash is not None:
        result["candidate_latest_hash"] = candidate_latest_hash
    if local_score is not None:
        result["local_score"] = local_score
    if peer_score is not None:
        result["peer_score"] = peer_score
    if candidate_score is not None:
        result["candidate_score"] = candidate_score
    if decision is not None:
        result["decision"] = decision
    return result


def _find_duplicate_submission(blockchain, submission_payload):
    submission_id = submission_payload.get("submission_id")
    content_hash = submission_payload.get("content_hash")

    for submission in blockchain.submissions:
        if submission.submission_id == submission_id:
            return submission
        if content_hash and getattr(submission, "content_hash", None) == content_hash:
            return submission

    return None


def _normalize_block_payload(block_payload):
    if not isinstance(block_payload, dict):
        raise MalformedBlockError("Block payload must be an object.")

    required_fields = ["index", "previous_hash", "timestamp", "transactions", "miner", "meme", "hash"]
    for field_name in required_fields:
        if field_name not in block_payload:
            raise MalformedBlockError(f"Block {field_name} is required.")

    index = block_payload["index"]
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise MalformedBlockError("Block index must be a non-negative integer.")

    previous_hash = block_payload["previous_hash"]
    if not isinstance(previous_hash, str) or not previous_hash.strip():
        raise MalformedBlockError("Block previous_hash is required.")

    miner = block_payload["miner"]
    if not isinstance(miner, str) or not miner.strip():
        raise MalformedBlockError("Block miner is required.")

    block_hash = block_payload["hash"]
    if not isinstance(block_hash, str) or not block_hash.strip():
        raise MalformedBlockError("Block hash is required.")

    timestamp_value = block_payload["timestamp"]
    try:
        timestamp = float(timestamp_value)
    except (TypeError, ValueError):
        raise MalformedBlockError("Block timestamp must be a valid timestamp.")
    if not math.isfinite(timestamp) or timestamp < 0:
        raise MalformedBlockError("Block timestamp must be a valid timestamp.")

    transactions_payload = block_payload["transactions"]
    if not isinstance(transactions_payload, list):
        raise MalformedBlockError("Block transactions must be a list.")

    transactions = [
        _normalize_transaction_payload(transaction_payload)
        for transaction_payload in transactions_payload
    ]

    return Block(
        index=index,
        previous_hash=previous_hash.strip(),
        timestamp=timestamp_value,
        transactions=transactions,
        miner=miner.strip(),
        meme=block_payload["meme"],
        hash=block_hash.strip(),
        submission_id=block_payload.get("submission_id"),
        certificate_id=block_payload.get("certificate_id"),
        content_hash=block_payload.get("content_hash"),
        creator_wallet=block_payload.get("creator_wallet"),
        vote_hash=block_payload.get("vote_hash"),
        approval_percentage=block_payload.get("approval_percentage"),
        decisive_vote_total=block_payload.get("decisive_vote_total"),
        minimum_votes_required=block_payload.get("minimum_votes_required"),
        approved_at=block_payload.get("approved_at"),
        originality_score=block_payload.get("originality_score"),
    )


def _normalize_transaction_payload(transaction_payload):
    if not isinstance(transaction_payload, dict):
        raise MalformedBlockError("Block transaction payload must be an object.")

    for field_name in ["sender", "recipient", "amount"]:
        if field_name not in transaction_payload:
            raise MalformedBlockError(f"Block transaction {field_name} is required.")

    if not isinstance(transaction_payload["sender"], str) or not transaction_payload["sender"].strip():
        raise MalformedBlockError("Block transaction sender is required.")
    if not isinstance(transaction_payload["recipient"], str) or not transaction_payload["recipient"].strip():
        raise MalformedBlockError("Block transaction recipient is required.")

    amount_value = transaction_payload["amount"]
    tip_value = transaction_payload.get("tip", 0)
    payload_size_kb_value = transaction_payload.get("payload_size_kb", 0)
    try:
        amount = float(amount_value)
        tip = float(tip_value)
        payload_size_kb = float(payload_size_kb_value)
    except (TypeError, ValueError):
        raise MalformedBlockError("Block transaction amount, tip, and payload size must be numeric.")

    if not math.isfinite(amount) or amount < 0:
        raise MalformedBlockError("Block transaction amount must be non-negative.")
    if not math.isfinite(tip) or tip < 0:
        raise MalformedBlockError("Block transaction tip must be non-negative.")
    if not math.isfinite(payload_size_kb) or payload_size_kb < 0:
        raise MalformedBlockError("Block transaction payload size must be non-negative.")

    return Transaction.from_dict({
        **transaction_payload,
        "sender": transaction_payload["sender"].strip(),
        "recipient": transaction_payload["recipient"].strip(),
        "amount": amount_value,
        "tip": tip_value,
        "payload_size_kb": payload_size_kb_value,
    })


def _validate_block_hash(blockchain, block):
    calculated_hash = block.calculate_hash()
    if block.hash != calculated_hash:
        raise MalformedBlockError("Block hash does not match block contents.")

    block_dict = block.to_dict()
    if block.hash != blockchain.calculate_hash_from_dict(block_dict):
        raise MalformedBlockError("Block hash does not match existing block validation.")


def _validate_block_extends_chain(blockchain, block, current_chain):
    latest_block = current_chain[-1]
    if block.previous_hash != latest_block.hash:
        raise ChainExtensionError(
            "Block does not extend the local chain tip. Fork resolution is not implemented yet."
        )
    if block.index != latest_block.index + 1:
        raise MalformedBlockError("Block index must extend the local chain by one.")

    _validate_block_hash(blockchain, block)
    _validate_block_transactions(blockchain, block)
    try:
        blockchain.validate_block_certificate_metadata(block.to_dict())
    except ValueError as exc:
        raise MalformedBlockError(str(exc))

    candidate_chain = [existing_block.to_dict() for existing_block in current_chain] + [block.to_dict()]
    if not blockchain.is_chain_valid(candidate_chain):
        raise MalformedBlockError("Block failed chain validation.")


def _validate_block_transactions(blockchain, block):
    for transaction in block.transactions:
        if not transaction.is_valid():
            raise MalformedBlockError("Block contains an invalid transaction.")
        if transaction.sender not in {"GENESIS", "REWARD_POOL"} and not blockchain.validate_transaction(transaction):
            raise MalformedBlockError("Block contains an invalid transaction.")


def _remove_confirmed_pending_transactions(blockchain, confirmed_transactions):
    blockchain.pending_transactions = [
        pending_transaction
        for pending_transaction in blockchain.pending_transactions
        if not any(
            pending_transaction.to_dict() == confirmed_transaction.to_dict()
            for confirmed_transaction in confirmed_transactions
        )
    ]


def _mark_related_submission_minted(blockchain, related_submission_id):
    if not related_submission_id:
        return None
    if not isinstance(related_submission_id, str) or not related_submission_id.strip():
        raise MalformedBlockError("Related submission_id must be a non-empty string when provided.")

    submission = blockchain.get_submission(related_submission_id.strip())
    if not submission:
        return None

    submission.status = MINTED
    blockchain.mint_queue = [
        queued_submission_id
        for queued_submission_id in blockchain.mint_queue
        if queued_submission_id != submission.submission_id
    ]
    return submission


def _find_existing_vote(blockchain, submission_id, voter):
    for vote in blockchain.votes:
        if vote.get("submission_id") == submission_id and vote.get("voter") == voter:
            return vote
    return None


def _normalize_vote_payload(vote_payload):
    if not isinstance(vote_payload, dict):
        raise MalformedVoteError("Vote payload must be an object.")

    normalized = {}
    for field_name in ["submission_id", "voter"]:
        value = vote_payload.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise MalformedVoteError(f"Vote {field_name} is required.")
        normalized[field_name] = value.strip()

    vote_type = vote_payload.get("vote_type", vote_payload.get("vote_value"))
    if not isinstance(vote_type, str) or not vote_type.strip():
        raise MalformedVoteError("Vote vote_type is required.")
    vote_type = vote_type.strip()
    if vote_type not in VOTE_TYPES:
        raise MalformedVoteError(f"Invalid vote type: {vote_type}")
    normalized["vote_type"] = vote_type

    created_at = vote_payload.get("created_at", vote_payload.get("vote_timestamp"))
    try:
        created_at = float(created_at)
    except (TypeError, ValueError):
        raise MalformedVoteError("Vote created_at must be a valid timestamp.")

    if not math.isfinite(created_at) or created_at < 0:
        raise MalformedVoteError("Vote created_at must be a valid timestamp.")
    normalized["created_at"] = created_at
    return normalized


def _normalize_submission_payload(submission_payload):
    if not isinstance(submission_payload, dict):
        raise MalformedSubmissionError("Submission payload must be an object.")

    normalized = {}
    for field_name in ["submission_id", "image_path", "text_content", "submitter"]:
        value = submission_payload.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise MalformedSubmissionError(f"Submission {field_name} is required.")
        normalized[field_name] = value.strip()

    status = submission_payload.get("status", PENDING)
    if status not in SUBMISSION_STATUSES:
        raise MalformedSubmissionError(f"Invalid submission status: {status}")

    try:
        created_at = float(submission_payload.get("created_at"))
    except (TypeError, ValueError):
        raise MalformedSubmissionError("Submission created_at must be a valid timestamp.")

    if not math.isfinite(created_at) or created_at < 0:
        raise MalformedSubmissionError("Submission created_at must be a valid timestamp.")
    normalized["created_at"] = created_at

    content_hash = submission_payload.get("content_hash")
    if content_hash is not None:
        if not isinstance(content_hash, str) or not content_hash.strip():
            raise MalformedSubmissionError("Submission content_hash must be a non-empty string.")
        normalized["content_hash"] = content_hash.strip()
    else:
        normalized["content_hash"] = calculate_submission_content_hash(
            normalized["image_path"],
            normalized["text_content"],
            normalized["submitter"],
        )

    normalized["status"] = PENDING
    normalized["hard_reject_reason"] = None
    return normalized
