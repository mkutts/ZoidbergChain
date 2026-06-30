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
    VOTE_TYPES,
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


class MalformedVoteError(PeerSyncError):
    pass


class UnknownSubmissionError(PeerSyncError):
    pass


class ConflictingVoteError(PeerSyncError):
    pass


def should_update_submission_status(existing_status, incoming_status=PENDING):
    if existing_status is None:
        return True
    if incoming_status == PENDING and existing_status in LATER_THAN_PENDING_STATUSES:
        return False
    return existing_status != incoming_status


def is_duplicate_submission(blockchain, submission_payload):
    return _find_duplicate_submission(blockchain, submission_payload) is not None


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


def _find_duplicate_submission(blockchain, submission_payload):
    submission_id = submission_payload.get("submission_id")
    content_hash = submission_payload.get("content_hash")

    for submission in blockchain.submissions:
        if submission.submission_id == submission_id:
            return submission
        if content_hash and getattr(submission, "content_hash", None) == content_hash:
            return submission

    return None


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
