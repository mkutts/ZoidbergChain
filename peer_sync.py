import logging
import math

import requests

from block import Block
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


def should_update_submission_status(existing_status, incoming_status=PENDING):
    if existing_status is None:
        return True
    if incoming_status == PENDING and existing_status in LATER_THAN_PENDING_STATUSES:
        return False
    return existing_status != incoming_status


def is_duplicate_submission(blockchain, submission_payload):
    return _find_duplicate_submission(blockchain, submission_payload) is not None


def receive_peer_block(
    blockchain,
    peer_store,
    origin_node_id,
    network_name,
    block_payload,
    related_submission_id,
    local_network_name,
):
    if network_name != local_network_name:
        raise WrongNetworkError("Peer block belongs to a different network.")

    peer = peer_store.get_active_peer(origin_node_id)
    if not peer:
        raise UnauthorizedPeerError("Peer is not registered or active.")
    if peer.get("network_name") != local_network_name:
        raise WrongNetworkError("Registered peer belongs to a different network.")

    block = _normalize_block_payload(block_payload)
    for existing_block in blockchain.chain:
        if existing_block.hash == block.hash or existing_block.index == block.index:
            raise DuplicateBlockError("Block already exists.")

    latest_block = blockchain.get_latest_block()
    if block.previous_hash != latest_block.hash:
        raise ChainExtensionError(
            "Block does not extend the local chain tip. Fork resolution is not implemented yet."
        )
    if block.index != latest_block.index + 1:
        raise MalformedBlockError("Block index must extend the local chain by one.")

    _validate_block_hash(blockchain, block)
    _validate_block_transactions(blockchain, block)

    candidate_chain = [existing_block.to_dict() for existing_block in blockchain.chain] + [block.to_dict()]
    if not blockchain.is_chain_valid(candidate_chain):
        raise MalformedBlockError("Block failed chain validation.")

    blockchain.chain.append(block)
    _remove_confirmed_pending_transactions(blockchain, block.transactions)
    minted_submission = _mark_related_submission_minted(blockchain, related_submission_id)
    blockchain.save_blockchain()

    return {
        "accepted": True,
        "action": "appended",
        "block": block.to_dict(),
        "submission": minted_submission.to_dict() if minted_submission else None,
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


def broadcast_block_to_peers(
    block,
    peer_store,
    origin_node_id,
    network_name,
    related_submission_id=None,
    timeout_seconds=3,
):
    payload = {
        "origin_node_id": origin_node_id,
        "network_name": network_name,
        "block": block.to_dict(),
        "related_submission_id": related_submission_id,
    }
    results = []

    for peer in peer_store.list_active_peers(network_name=network_name):
        receive_url = f"{peer['url'].rstrip('/')}/peers/blocks/receive"
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

    try:
        timestamp = float(block_payload["timestamp"])
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
        timestamp=timestamp,
        transactions=transactions,
        miner=miner.strip(),
        meme=block_payload["meme"],
        hash=block_hash.strip(),
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
