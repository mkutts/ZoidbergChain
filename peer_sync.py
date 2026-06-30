import logging
import math

import requests

from submission import (
    APPROVED,
    HARD_REJECTED,
    MINTED,
    PENDING,
    QUEUED,
    REJECTED,
    SUBMISSION_STATUSES,
    Submission,
    calculate_submission_content_hash,
)


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


def should_update_submission_status(existing_status, incoming_status=PENDING):
    if existing_status is None:
        return True
    if incoming_status == PENDING and existing_status in LATER_THAN_PENDING_STATUSES:
        return False
    return existing_status != incoming_status


def is_duplicate_submission(blockchain, submission_payload):
    return _find_duplicate_submission(blockchain, submission_payload) is not None


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


def _find_duplicate_submission(blockchain, submission_payload):
    submission_id = submission_payload.get("submission_id")
    content_hash = submission_payload.get("content_hash")

    for submission in blockchain.submissions:
        if submission.submission_id == submission_id:
            return submission
        if content_hash and getattr(submission, "content_hash", None) == content_hash:
            return submission

    return None


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
