import json
import logging
import math
import secrets
import time

import requests

from blockchain import NativeBlockValidationError
from block import Block
from content import (
    CONTENT_TYPE_IMAGE,
    CONTENT_TYPE_MIXED,
    CONTENT_TYPE_TEXT,
    STORAGE_STATUS_VERIFIED,
    TEXT_MIME_TYPE,
)
from config import (
    MAX_CONTENT_FILE_SIZE_BYTES,
    NODE_ID,
    ORIGINALITY_APPROVAL_THRESHOLD,
    peer_auth_required,
    peer_replay_protection_enabled,
    peer_shared_secret,
    peer_shared_secret_is_configured,
    peer_signature_window_seconds,
    signed_peer_messages_enabled,
)
from originality_certificate import (
    OriginalityCertificate,
    calculate_certificate_id,
    calculate_vote_hash,
    calculate_originality_score,
    validate_certificate_for_submission,
)
from protocol_v1 import OBJECT_TYPE_VOTE, PROTOCOL_VERSION
from protocol_v1_genesis import GenesisValidationError
from protocol_v1_originality import (
    PROTOCOL_V1_CERTIFICATE_VERSION,
    PROTOCOL_V1_VOTE_VERSION,
    build_protocol_v1_vote_message,
    resolve_protocol_v1_network_id,
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
    VOTE_NOT_ORIGINAL,
    VOTE_ORIGINAL,
    VOTE_TYPES,
    VOTE_UNSURE,
    calculate_submission_content_hash,
)
from transaction import Transaction
from wallet_auth import hash_wallet_message, normalize_wallet_address, recover_signed_wallet_address
from validators import (
    is_valid_content_hash,
    is_valid_network_name,
    is_valid_node_id,
    is_valid_user_wallet_identity,
    is_valid_wallet_public_key,
)
from services.peer_authentication_service import (
    PeerAuthenticationConfig,
    PeerAuthenticationService,
)
from services.peer_content_sync_service import (
    ContentDiscoveryCollaborators,
    ContentFetchCollaborators,
    PeerContentSyncService,
)
from services.peer_chain_sync_service import (
    ChainSyncCollaborators,
    ChainSyncState,
    PeerChainSyncService,
)
from services.peer_network_errors import (
    ChainExtensionError,
    ChainSyncError,
    ConflictingCertificateError,
    ConflictingTransactionError,
    ConflictingVoteError,
    ContentSyncError,
    DuplicateBlockError,
    DuplicateSubmissionError,
    ExpiredPeerSignatureError,
    InvalidPeerSignatureError,
    InvalidPeerTimestampError,
    MalformedBlockError,
    MalformedCertificateError,
    MalformedSubmissionError,
    MalformedTransactionError,
    MalformedVoteError,
    MissingSignedPeerHeadersError,
    PeerSyncError,
    ReplayedPeerNonceError,
    UnauthorizedPeerError,
    UnknownSubmissionError,
    WrongNetworkError,
)
from services.peer_transport_service import PeerBroadcastService, PeerHttpTransport


LATER_THAN_PENDING_STATUSES = {APPROVED, QUEUED, REJECTED, HARD_REJECTED, MINTED}
_PEER_NONCE_CACHE: dict[str, dict[str, int]] = {}


def _peer_authentication_service():
    return PeerAuthenticationService(
        PeerAuthenticationConfig(
            auth_required=peer_auth_required,
            replay_protection_enabled=peer_replay_protection_enabled,
            shared_secret=peer_shared_secret,
            shared_secret_is_configured=peer_shared_secret_is_configured,
            signature_window_seconds=peer_signature_window_seconds,
            signed_messages_enabled=signed_peer_messages_enabled,
            now=time.time,
            nonce=secrets.token_hex,
        ),
        _PEER_NONCE_CACHE,
    )


def _peer_http_transport():
    return PeerHttpTransport(requests)


def _peer_broadcast_service():
    return PeerBroadcastService(_peer_http_transport(), build_peer_request_headers, logging)


def _peer_content_sync_service():
    return PeerContentSyncService(
        _peer_http_transport(),
        build_peer_request_headers,
        logging,
        MAX_CONTENT_FILE_SIZE_BYTES,
    )


def _peer_chain_sync_service():
    return PeerChainSyncService(_peer_http_transport(), build_peer_request_headers, logging)


def hash_body(body_bytes):
    return PeerAuthenticationService.hash_body(body_bytes)


def build_peer_signature_payload(method, path, timestamp, nonce, body_hash):
    return PeerAuthenticationService.build_signature_payload(
        method, path, timestamp, nonce, body_hash
    )


def sign_peer_request(method, path, timestamp, nonce, body_bytes, secret=None):
    return _peer_authentication_service().sign_request(
        method, path, timestamp, nonce, body_bytes, secret
    )


def _serialize_peer_body(payload):
    return PeerAuthenticationService.serialize_body(payload)


def _peer_request_headers(method, path, payload, origin_node_id, *, network_name=None):
    return _peer_authentication_service().build_request_headers(
        method, path, payload, origin_node_id, network_name=network_name
    )


def _cleanup_peer_nonce_cache(now=None, window_seconds=None):
    return _peer_authentication_service().cleanup_nonce_cache(now, window_seconds)


def _record_peer_nonce(node_id, nonce, timestamp):
    return _peer_authentication_service().record_nonce(node_id, nonce, timestamp)


def _is_replayed_peer_nonce(node_id, nonce):
    return _peer_authentication_service().is_replayed_nonce(node_id, nonce)


def verify_peer_signature(method, path, headers, body_bytes):
    return _peer_authentication_service().verify_signature(method, path, headers, body_bytes)


def build_peer_request_headers(method, path, payload, origin_node_id, *, network_name=None):
    return _peer_request_headers(method, path, payload, origin_node_id, network_name=network_name)


def fetch_content_from_peer(
    blockchain,
    peer,
    content_hash,
    *,
    origin_node_id,
    timeout_seconds=3,
):
    result = _peer_content_sync_service().fetch_and_register(
        ContentFetchCollaborators(
            data_dir=blockchain.storage.data_dir,
            register_uploaded_content=blockchain.register_uploaded_content,
        ),
        peer,
        content_hash,
        origin_node_id=origin_node_id,
        timeout_seconds=timeout_seconds,
    )
    if result.get("status") == "fetched_and_verified":
        blockchain.save_blockchain()
    return result


def sync_missing_content(
    blockchain,
    peer_store,
    content_hash,
    *,
    origin_node_id,
    network_name,
    timeout_seconds=3,
):
    return _peer_content_sync_service().sync_missing(
        ContentDiscoveryCollaborators(
            get_content_object_by_hash=blockchain.get_content_object_by_hash,
            list_active_peers=peer_store.list_active_peers,
            fetch_content=lambda peer, requested_hash, **kwargs: fetch_content_from_peer(
                blockchain, peer, requested_hash, **kwargs
            ),
        ),
        content_hash,
        origin_node_id=origin_node_id,
        network_name=network_name,
        timeout_seconds=timeout_seconds,
    )


def _reject_forbidden_fields(payload, allowed_fields, error_cls, object_name):
    forbidden_fields = []
    for forbidden_field in ["private_key", "privateKey", "signing_key", "seed", "seed_phrase", "secret", "raw_secret"]:
        if forbidden_field in payload:
            forbidden_fields.append(forbidden_field)
    extra_fields = set(payload.keys()) - set(allowed_fields)
    if extra_fields:
        forbidden_fields.extend(sorted(extra_fields))
    if forbidden_fields:
        raise error_cls(f"{object_name} contains forbidden or unexpected fields.")


def _transaction_reason_from_error(message):
    normalized = str(message or "").strip().lower()
    if "tx_id does not match" in normalized:
        return "invalid_tx_id"
    if "mempool admission" in normalized and ("transaction version is required" in normalized or "transaction_version" in normalized):
        return "unsupported_transaction_version"
    if "signed_message does not match" in normalized:
        return "invalid_signed_message"
    if "signature" in normalized:
        return "invalid_signature"
    if (
        "different network" in normalized
        or "network does not match" in normalized
        or "network_id does not match" in normalized
        or "belongs to a different network" in normalized
    ):
        return "wrong_network"
    if "nonce already used or reserved" in normalized:
        return "conflicting_nonce"
    if "lower than the next expected nonce" in normalized or "ahead of the next expected nonce" in normalized:
        return "invalid_nonce"
    if "insufficient available balance" in normalized:
        return "insufficient_available_balance"
    if "nonzero fees are not enabled yet" in normalized:
        return "invalid_fee_policy"
    if "not eligible for mempool admission" in normalized:
        return "invalid_status"
    if "not found" in normalized:
        return "not_found"
    return "validation_failed"


def _serialize_peer_transaction_payload(transaction):
    payload = {
        "tx_id": transaction.get("tx_id"),
        "transaction_type": transaction.get("transaction_type"),
        "network": transaction.get("network"),
        "from_address": transaction.get("from_address"),
        "to_address": transaction.get("to_address"),
        "amount": transaction.get("amount"),
        "fee": transaction.get("fee"),
        "nonce": transaction.get("nonce"),
        "memo": transaction.get("memo"),
        "timestamp": transaction.get("timestamp"),
        "signature": transaction.get("signature"),
        "signature_scheme": transaction.get("signature_scheme"),
        "signed_message": transaction.get("signed_message"),
        "signed_message_hash": transaction.get("signed_message_hash"),
        "status": transaction.get("status"),
        "created_at": transaction.get("created_at"),
        "updated_at": transaction.get("updated_at"),
    }
    if transaction.get("transaction_version") is not None:
        payload["transaction_version"] = transaction.get("transaction_version")
    if transaction.get("protocol_version") is not None:
        payload["protocol_version"] = transaction.get("protocol_version")
    if transaction.get("network_id") is not None:
        payload["network_id"] = transaction.get("network_id")
    return payload


def _require_valid_peer_string(value, validator, error_cls, field_name):
    if not isinstance(value, str) or not value.strip() or not validator(value.strip()):
        raise error_cls(f"{field_name} is required.")
    return value.strip()


def receive_peer_transaction(
    blockchain,
    peer_store,
    origin_node_id,
    network_name,
    transaction_payload,
    local_network_name,
):
    if network_name != local_network_name:
        raise WrongNetworkError("Peer transaction belongs to a different network.")

    peer = peer_store.get_active_peer(origin_node_id)
    if not peer:
        raise UnauthorizedPeerError("Peer is not registered or active.")
    if peer.get("network_name") != local_network_name:
        raise WrongNetworkError("Registered peer belongs to a different network.")

    if not isinstance(transaction_payload, dict):
        raise MalformedTransactionError("Transaction payload must be an object.")

    stored_transaction = None
    duplicate = False
    try:
        stored_transaction, duplicate = blockchain.record_native_transaction(
            transaction_payload,
            status="signed_pending",
        )
        admitted = blockchain.admit_transaction_to_mempool(stored_transaction["tx_id"])
    except ValueError as exc:
        if stored_transaction is not None and not duplicate:
            blockchain.discard_native_transaction(stored_transaction["tx_id"])
        reason = _transaction_reason_from_error(str(exc))
        if reason == "conflicting_nonce":
            raise ConflictingTransactionError(str(exc)) from exc
        raise MalformedTransactionError(str(exc)) from exc

    return {
        "accepted": True,
        "tx_id": admitted["tx_id"],
        "status": admitted["status"],
        "duplicate": bool(duplicate),
    }


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
    origin_node_id=None,
    timeout_seconds=5,
):
    if origin_node_id is None:
        origin_node_id = NODE_ID
    service = _peer_chain_sync_service()
    peers = peer_store.list_active_peers(network_name=network_name)
    return service.sync_all(
        peers,
        lambda peer: _sync_chain_from_peer(
            blockchain=blockchain,
            peer=peer,
            origin_node_id=origin_node_id,
            network_name=network_name,
            timeout_seconds=timeout_seconds,
        ),
    )


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
    existing_block = blockchain.get_block_by_hash(block.hash)
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

    _validate_block_extends_chain(
        blockchain,
        block,
        blockchain.chain,
        validate_hash=True,
        validate_chain=True,
    )

    if blockchain.is_protocol_v1_block_payload(block):
        try:
            blockchain.cache_protocol_v1_block_content(
                block,
                submission_id=related_submission_id or block.submission_id,
            )
        except ValueError as exc:
            raise MalformedBlockError(str(exc)) from exc
    elif block.content_hash:
        blockchain.register_remote_content_reference(
            content_hash=block.content_hash,
            content_id=block.content_id,
            submitted_by=block.creator_wallet,
            mime_type=block.mime_type or "application/octet-stream",
            content_type=block.content_type or CONTENT_TYPE_IMAGE,
            storage_status="remote",
            submission_id=related_submission_id or block.submission_id,
        )

    blockchain.chain.append(block)
    blockchain.settle_block_native_transactions(block)
    blockchain.recompute_reward_pool_balance(chain=blockchain.chain)
    _remove_confirmed_pending_transactions(blockchain, block.transactions)
    minted_submission = _mark_related_submission_minted(
        blockchain,
        related_submission_id or block.submission_id,
    )
    blockchain.reconcile_submission_canonical_state()
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
    blockchain.register_remote_content_reference(
        content_hash=certificate.content_hash,
        content_id=certificate.content_id,
        submitted_by=certificate.creator_wallet,
        submission_id=certificate.submission_id,
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

    normalized_vote = _normalize_vote_payload(vote_payload, local_network_name)
    submission = blockchain.get_submission(normalized_vote["submission_id"])
    if not submission:
        raise UnknownSubmissionError(f"Submission not found: {normalized_vote['submission_id']}")
    if normalized_vote.get("content_hash") and submission.content_hash != normalized_vote["content_hash"]:
        raise MalformedVoteError("Vote content_hash does not match submission.")

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
        for key in [
            "vote_version",
            "protocol_version",
            "network_id",
            "content_hash",
            "voter_wallet_address",
            "signature_scheme",
            "vote_signature",
            "vote_message",
            "signed_message_hash",
            "vote_nonce",
            "vote_issued_at",
            "vote_expires_at",
            "signed_at",
            "identity_source",
        ]:
            if normalized_vote.get(key) is not None:
                vote[key] = normalized_vote.get(key)
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

    submission = Submission.from_dict(
        {
            **normalized_payload,
            "status": PENDING,
            "image_path": "",
        }
    )
    blockchain.submissions.append(submission)
    blockchain.register_remote_content_reference(
        content_hash=submission.content_hash,
        content_id=submission.content_id,
        submitted_by=submission.submitter,
        mime_type=(
            TEXT_MIME_TYPE
            if not normalized_payload.get("image_path") and submission.text_content
            else "application/octet-stream"
        ),
        content_type=(
            CONTENT_TYPE_MIXED
            if normalized_payload.get("image_path") and submission.text_content
            else (CONTENT_TYPE_IMAGE if normalized_payload.get("image_path") else CONTENT_TYPE_TEXT)
        ),
        caption=submission.text_content or None,
        text_content=submission.text_content or None,
        storage_status="remote",
        submission_id=submission.submission_id,
    )
    blockchain.link_content_objects_to_submissions()
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
    return _peer_broadcast_service().broadcast_submission(
        submission, peer_store, origin_node_id, network_name, timeout_seconds
    )


def broadcast_vote_to_peers(
    vote,
    peer_store,
    origin_node_id,
    network_name,
    timeout_seconds=3,
):
    return _peer_broadcast_service().broadcast_vote(
        vote, peer_store, origin_node_id, network_name, timeout_seconds
    )


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
    return _peer_broadcast_service().broadcast_certificate(
        certificate, peer_store, origin_node_id, network_name, timeout_seconds
    )


def broadcast_block_to_peers(
    block,
    peer_store,
    origin_node_id,
    network_name,
    related_submission_id=None,
    certificate=None,
    timeout_seconds=3,
):
    return _peer_broadcast_service().broadcast_block(
        block, peer_store, origin_node_id, network_name,
        related_submission_id, certificate, timeout_seconds,
    )


def broadcast_transaction_to_peers(
    blockchain,
    tx_id,
    peer_store,
    origin_node_id,
    network_name,
    timeout_seconds=3,
):
    transaction = blockchain.get_native_transaction(tx_id)
    if transaction is None:
        raise ValueError(f"Transaction not found: {tx_id}")
    return _peer_broadcast_service().broadcast_transaction(
        _serialize_peer_transaction_payload(transaction), tx_id, peer_store,
        origin_node_id, network_name, timeout_seconds,
    )


def sync_transaction_from_peer(
    blockchain,
    peer_store,
    peer,
    tx_id,
    *,
    origin_node_id,
    network_name,
    timeout_seconds=3,
):
    transaction_path = f"/peers/transactions/{tx_id}"
    request_headers = build_peer_request_headers(
        "GET",
        transaction_path,
        None,
        origin_node_id,
        network_name=network_name,
    )
    request_kwargs = {"timeout": timeout_seconds}
    if request_headers:
        request_kwargs["headers"] = request_headers
    response = _peer_http_transport().get(
        f"{peer['url'].rstrip('/')}{transaction_path}",
        **request_kwargs,
    )
    status_code = getattr(response, "status_code", None)
    if status_code == 404:
        return {"accepted": False, "tx_id": tx_id, "reason": "not_found"}
    if status_code is None or status_code >= 400:
        raise PeerSyncError(
            f"Peer transaction fetch returned status {status_code}: {getattr(response, 'text', '')}"
        )

    payload = response.json()
    transaction_payload = payload.get("transaction") if isinstance(payload, dict) else None
    if not isinstance(transaction_payload, dict):
        raise MalformedTransactionError("Peer transaction response is malformed.")
    return receive_peer_transaction(
        blockchain=blockchain,
        peer_store=peer_store,
        origin_node_id=peer.get("node_id"),
        network_name=network_name,
        transaction_payload=transaction_payload,
        local_network_name=network_name,
    )


def sync_mempool_from_peer(
    blockchain,
    peer_store,
    peer,
    *,
    origin_node_id,
    network_name,
    timeout_seconds=3,
):
    summary_path = "/peers/mempool/summary"
    request_headers = build_peer_request_headers(
        "GET",
        summary_path,
        None,
        origin_node_id,
        network_name=network_name,
    )
    request_kwargs = {"timeout": timeout_seconds}
    if request_headers:
        request_kwargs["headers"] = request_headers
    response = _peer_http_transport().get(
        f"{peer['url'].rstrip('/')}{summary_path}",
        **request_kwargs,
    )
    status_code = getattr(response, "status_code", None)
    if status_code is None or status_code >= 400:
        raise PeerSyncError(
            f"Peer mempool summary returned status {status_code}: {getattr(response, 'text', '')}"
        )

    payload = response.json()
    tx_ids = payload.get("tx_ids") if isinstance(payload, dict) else None
    if not isinstance(tx_ids, list):
        raise MalformedTransactionError("Peer mempool summary is malformed.")

    results = []
    for tx_id in tx_ids:
        normalized_tx_id = str(tx_id or "").strip().lower()
        if not normalized_tx_id or blockchain.get_mempool_transaction(normalized_tx_id) is not None:
            continue
        results.append(
            sync_transaction_from_peer(
                blockchain,
                peer_store,
                peer,
                normalized_tx_id,
                origin_node_id=origin_node_id,
                network_name=network_name,
                timeout_seconds=timeout_seconds,
            )
        )
    return {
        "count": len(tx_ids),
        "fetched": len(results),
        "results": results,
    }


def _sync_chain_from_peer(blockchain, peer, origin_node_id, network_name, timeout_seconds):
    state = ChainSyncState(
        local_height=blockchain.get_latest_block().index,
        local_latest_hash=blockchain.get_latest_block().hash,
        local_genesis_hash=blockchain.public_testnet_v1_genesis_hash(),
        local_score=blockchain.get_cumulative_originality_score(),
        local_network_id=blockchain.protocol_v1_network_id(),
    )
    collaborators = ChainSyncCollaborators(
        compare_summaries=blockchain.compare_chain_summaries,
        store_certificates=lambda payloads: _store_chain_sync_certificates(
            blockchain, payloads, network_name
        ),
        validate_candidate=lambda blocks, **expected: _validate_candidate_chain(
            blockchain, blocks, **expected
        ),
        compare_candidate=lambda candidate: blockchain.compare_chains_by_originality(
            blockchain.chain, candidate
        ),
        adopt_candidate=lambda candidate: _adopt_candidate_chain(blockchain, candidate),
    )
    return _peer_chain_sync_service().sync_peer(
        peer,
        origin_node_id=origin_node_id,
        network_name=network_name,
        timeout_seconds=timeout_seconds,
        state=state,
        collaborators=collaborators,
    )


def _adopt_candidate_chain(blockchain, candidate_chain):
    previous_chain_length = len(blockchain.chain)
    for block in candidate_chain:
        _remove_confirmed_pending_transactions(blockchain, block.transactions)
    blockchain.chain = candidate_chain
    blockchain.recompute_reward_pool_balance(chain=blockchain.chain)
    blockchain.reconcile_submission_canonical_state()
    blockchain.reconcile_native_transactions_with_chain(chain=candidate_chain)
    blockchain.save_blockchain()
    return {
        "appended": max(0, len(candidate_chain) - previous_chain_length),
        "latest_block_hash": blockchain.get_latest_block().hash,
    }


def _fetch_peer_chain_summary(peer, *, origin_node_id, network_name, timeout_seconds):
    return _peer_chain_sync_service().fetch_summary(
        peer,
        origin_node_id=origin_node_id,
        network_name=network_name,
        timeout_seconds=timeout_seconds,
    )


def _fetch_peer_blocks(peer, from_height, *, origin_node_id, network_name, timeout_seconds):
    return _peer_chain_sync_service().fetch_blocks(
        peer,
        from_height,
        origin_node_id=origin_node_id,
        network_name=network_name,
        timeout_seconds=timeout_seconds,
    )


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


def _validate_certificate_vote_set_against_local_submission(blockchain, certificate, submission):
    vote_summary = blockchain.get_submission_votes(submission.submission_id)
    expected_counts = {
        "vote_total": len(vote_summary["votes"]),
        "decisive_vote_total": vote_summary["counts"][VOTE_ORIGINAL] + vote_summary["counts"][VOTE_NOT_ORIGINAL],
        "original_votes": vote_summary["counts"][VOTE_ORIGINAL],
        "not_original_votes": vote_summary["counts"][VOTE_NOT_ORIGINAL],
        "unsure_votes": vote_summary["counts"][VOTE_UNSURE],
    }
    for field_name, expected_value in expected_counts.items():
        if getattr(certificate, field_name) != expected_value:
            raise MalformedCertificateError(f"Originality certificate {field_name} does not match local vote set.")
    try:
        expected_vote_hash = calculate_vote_hash(
            vote_summary["votes"],
            vote_set_version=certificate.certificate_version,
            submission_id=submission.submission_id,
            content_hash=submission.content_hash,
            network_id=certificate.network_id,
            network_name=certificate.network_name,
        )
    except ValueError as exc:
        raise MalformedCertificateError(str(exc)) from exc
    if certificate.vote_hash != expected_vote_hash:
        raise MalformedCertificateError("Originality certificate vote_hash does not match local vote set.")


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
                    submission = blockchain.get_submission(existing_certificate.submission_id)
                    if submission:
                        submission.certificate_id = existing_certificate.certificate_id
                    return existing_certificate, "duplicate"
                raise ConflictingCertificateError(
                    "Originality certificate already exists with different contents."
                )

    certificate = _normalize_certificate_payload(certificate_payload, local_network_name)
    existing_certificate = blockchain.get_originality_certificate(certificate.certificate_id)
    if existing_certificate:
        if existing_certificate.to_dict() == certificate.to_dict():
            submission = blockchain.get_submission(existing_certificate.submission_id)
            if submission:
                submission.certificate_id = existing_certificate.certificate_id
            return existing_certificate, "duplicate"
        raise ConflictingCertificateError(
            "Originality certificate already exists with different contents."
        )

    submission = blockchain.get_submission(certificate.submission_id)
    if submission:
        if submission.content_hash != certificate.content_hash:
            try:
                blockchain.promote_submission_content_for_protocol_v1(submission)
            except ValueError:
                pass
            if submission.content_hash != certificate.content_hash:
                content_object = blockchain.get_content_object_by_hash(submission.content_hash)
                if content_object is None or getattr(content_object, "storage_status", None) != STORAGE_STATUS_VERIFIED:
                    submission.content_hash = certificate.content_hash
                    if certificate.content_id is not None:
                        submission.content_id = certificate.content_id
                if submission.content_hash != certificate.content_hash:
                    raise MalformedCertificateError(
                        "Originality certificate content_hash does not match submission."
                    )
        if submission.submitter != certificate.creator_wallet:
            raise MalformedCertificateError(
                "Originality certificate creator_wallet does not match submission."
            )
        _validate_certificate_vote_set_against_local_submission(blockchain, certificate, submission)
        try:
            validate_certificate_for_submission(
                certificate,
                submission,
                network_name=local_network_name,
                allowed_submission_statuses={PENDING, APPROVED, QUEUED, MINTED},
            )
        except ValueError as exc:
            raise MalformedCertificateError(str(exc))

    blockchain.originality_certificates.append(certificate)
    blockchain.register_remote_content_reference(
        content_hash=certificate.content_hash,
        content_id=certificate.content_id,
        submitted_by=certificate.creator_wallet,
        storage_status="remote",
    )
    if submission:
        previous_status = submission.status
        previous_certificate_id = submission.certificate_id
        submission.certificate_id = certificate.certificate_id
        if submission.status == PENDING:
            submission.transition_to(APPROVED)
        try:
            validate_certificate_for_submission(
                certificate,
                submission,
                network_name=local_network_name,
            )
        except ValueError as exc:
            submission.status = previous_status
            submission.certificate_id = previous_certificate_id
            blockchain.originality_certificates = [
                stored_certificate
                for stored_certificate in blockchain.originality_certificates
                if stored_certificate.certificate_id != certificate.certificate_id
            ]
            raise MalformedCertificateError(str(exc))
    if save:
        blockchain.save_blockchain()
    return certificate, "created"


def _normalize_certificate_payload(certificate_payload, local_network_name):
    if not isinstance(certificate_payload, dict):
        raise MalformedCertificateError("Certificate payload must be an object.")

    _reject_forbidden_fields(
        certificate_payload,
        [
            "certificate_version",
            "protocol_version",
            "network_id",
            "certificate_id",
            "submission_id",
            "content_hash",
            "content_id",
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
            "originality_score",
            "approval_threshold",
        ],
        MalformedCertificateError,
        "Certificate payload",
    )

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
    certificate_version = certificate_payload.get("certificate_version")
    if certificate_version is not None:
        if (
            isinstance(certificate_version, bool)
            or not isinstance(certificate_version, int)
            or certificate_version != PROTOCOL_V1_CERTIFICATE_VERSION
        ):
            raise MalformedCertificateError("Certificate certificate_version is unsupported.")
        normalized["certificate_version"] = certificate_version

    protocol_version = certificate_payload.get("protocol_version")
    if protocol_version is not None:
        if isinstance(protocol_version, bool) or not isinstance(protocol_version, int):
            raise MalformedCertificateError("Certificate protocol_version must be a positive integer.")
        if protocol_version != PROTOCOL_VERSION:
            raise MalformedCertificateError("Certificate protocol_version is unsupported.")
        normalized["protocol_version"] = protocol_version

    network_id = certificate_payload.get("network_id")
    if network_id is not None:
        if not isinstance(network_id, str) or not network_id.strip():
            raise MalformedCertificateError("Certificate network_id is required.")
        try:
            normalized["network_id"] = resolve_protocol_v1_network_id(network_id=network_id.strip())
        except ValueError as exc:
            raise MalformedCertificateError(str(exc)) from exc

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
        validator = {
            "certificate_id": lambda raw: isinstance(raw, str) and bool(raw.strip()),
            "submission_id": lambda raw: isinstance(raw, str) and bool(raw.strip()),
            "content_hash": lambda raw: isinstance(raw, str) and bool(raw.strip()),
            "creator_wallet": is_valid_user_wallet_identity,
            "network_name": is_valid_network_name,
            "issuing_node_id": is_valid_node_id,
            "vote_hash": lambda raw: isinstance(raw, str) and bool(raw.strip()),
        }[field_name]
        normalized[field_name] = _require_valid_peer_string(
            value,
            validator,
            MalformedCertificateError,
            f"Certificate {field_name}",
        )
        if field_name == "creator_wallet":
            normalized_wallet = normalize_wallet_address(normalized[field_name])
            if normalized_wallet is not None:
                normalized[field_name] = normalized_wallet

    content_id = certificate_payload.get("content_id")
    if content_id is not None:
        if not isinstance(content_id, str) or not content_id.strip():
            raise MalformedCertificateError("Certificate content_id must be a non-empty string.")
        normalized["content_id"] = content_id.strip()

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

    approval_threshold = certificate_payload.get("approval_threshold")
    if approval_threshold is not None:
        try:
            approval_threshold = float(approval_threshold)
        except (TypeError, ValueError):
            raise MalformedCertificateError("Certificate approval_threshold must be numeric.")
        if not math.isfinite(approval_threshold) or approval_threshold < 0:
            raise MalformedCertificateError(
                "Certificate approval_threshold must be a non-negative number."
            )
        normalized["approval_threshold"] = approval_threshold

    if normalized.get("certificate_version") is None and any(
        normalized.get(field_name) is not None
        for field_name in ["protocol_version", "network_id", "approval_threshold"]
    ):
        raise MalformedCertificateError(
            "Certificate certificate_version is required when Protocol v1 certificate fields are present."
        )

    if normalized.get("certificate_version") == PROTOCOL_V1_CERTIFICATE_VERSION:
        if normalized.get("protocol_version") != PROTOCOL_VERSION:
            raise MalformedCertificateError("Certificate protocol_version is required for Protocol v1 certificates.")
        if normalized.get("network_id") is None:
            raise MalformedCertificateError("Certificate network_id is required for Protocol v1 certificates.")
        if "approval_threshold" not in normalized:
            raise MalformedCertificateError("Certificate approval_threshold is required for Protocol v1 certificates.")

    certificate = OriginalityCertificate.from_dict(normalized)
    _validate_certificate_internal(certificate, local_network_name)
    return certificate


def _validate_certificate_internal(certificate, local_network_name):
    if certificate.is_protocol_v1_certificate():
        expected_network_id = resolve_protocol_v1_network_id(network_name=local_network_name)
        if certificate.protocol_version != PROTOCOL_VERSION:
            raise MalformedCertificateError("Originality certificate protocol_version is unsupported.")
        if certificate.network_id != expected_network_id:
            raise MalformedCertificateError("Originality certificate belongs to a different network.")
        if certificate.approval_threshold is None:
            raise MalformedCertificateError("Originality certificate approval_threshold is required.")
        if not math.isclose(float(certificate.approval_threshold), ORIGINALITY_APPROVAL_THRESHOLD):
            raise MalformedCertificateError("Originality certificate approval threshold is inconsistent.")
    elif certificate.network_name != local_network_name:
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
    try:
        expected_certificate_id = calculate_certificate_id(
            certificate.to_core_dict(),
            certificate_version=certificate.certificate_version,
            network_id=certificate.network_id,
            network_name=certificate.network_name,
        )
    except ValueError as exc:
        raise MalformedCertificateError(str(exc)) from exc
    if certificate.certificate_id != expected_certificate_id:
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
    try:
        blockchain.validate_canonical_public_testnet_v1_genesis(candidate_chain[0])
    except GenesisValidationError as exc:
        raise ChainSyncError(str(exc)) from exc
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

    working_chain = []
    for block in candidate_chain:
        _validate_block_hash(blockchain, block)
        _validate_block_transactions(blockchain, block, prior_chain=working_chain)
        working_chain.append(block)

    if not blockchain.is_chain_valid([block.to_dict() for block in candidate_chain]):
        raise ChainSyncError("Candidate chain failed validation.")

    return candidate_chain


def _normalize_chain_summary(summary):
    return PeerChainSyncService.normalize_summary(summary)


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
    return PeerChainSyncService.result(
        peer, status, reason, local_height, peer_height, candidate_height,
        appended, latest_block_hash, local_latest_hash, candidate_latest_hash,
        local_score, peer_score, candidate_score, decision,
    )


def _find_duplicate_submission(blockchain, submission_payload):
    submission_id = submission_payload.get("submission_id")
    content_hash = submission_payload.get("content_hash")

    submission = blockchain.get_submission(submission_id) if isinstance(submission_id, str) and submission_id.strip() else None
    if submission:
        return submission
    if content_hash:
        return blockchain.storage.get_submission_by_content_hash(content_hash, blockchain.submissions)
    return None


def _normalize_block_payload(block_payload):
    if not isinstance(block_payload, dict):
        raise MalformedBlockError("Block payload must be an object.")

    _reject_forbidden_fields(
        block_payload,
        [
            "block_version",
            "genesis_version",
            "protocol_version",
            "network_id",
            "media_hash",
            "media_bytes",
            "index",
            "previous_hash",
            "timestamp",
            "transactions",
            "miner",
            "meme",
            "hash",
            "submission_id",
            "certificate_id",
            "content_hash",
            "content_id",
            "content_type",
            "mime_type",
            "creator_wallet",
            "vote_hash",
            "approval_percentage",
            "decisive_vote_total",
            "minimum_votes_required",
            "approved_at",
            "originality_score",
            "reward_type",
            "reward_recipient",
            "reward_amount",
            "reward_source",
            "minted_at",
            "voter_rewards",
            "native_transactions",
            "transaction_ids",
            "transaction_count",
            "transactions_hash",
            "total_supply",
            "initial_reward_pool",
        ],
        MalformedBlockError,
        "Block payload",
    )

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
    miner_value = miner.strip() if isinstance(miner, str) else ""
    if not miner_value or (miner_value not in {"GENESIS", "REWARD_POOL"} and not is_valid_user_wallet_identity(miner_value)):
        raise MalformedBlockError("Block miner is required.")

    block_hash = block_payload["hash"]
    if not isinstance(block_hash, str) or not block_hash.strip():
        raise MalformedBlockError("Block hash is required.")
    block_hash = block_hash.strip()

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
    block_version = block_payload.get("block_version")
    if block_version is not None and (
        isinstance(block_version, bool) or not isinstance(block_version, int) or block_version <= 0
    ):
        raise MalformedBlockError("Block block_version must be a positive integer when provided.")

    genesis_version = block_payload.get("genesis_version")
    if genesis_version is not None and (
        isinstance(genesis_version, bool) or not isinstance(genesis_version, int) or genesis_version <= 0
    ):
        raise MalformedBlockError("Block genesis_version must be a positive integer when provided.")

    protocol_version = block_payload.get("protocol_version")
    if protocol_version is not None and (
        isinstance(protocol_version, bool) or not isinstance(protocol_version, int) or protocol_version <= 0
    ):
        raise MalformedBlockError("Block protocol_version must be a positive integer when provided.")

    network_id = block_payload.get("network_id")
    if network_id is not None and (not isinstance(network_id, str) or not network_id.strip()):
        raise MalformedBlockError("Block network_id must be a non-empty string when provided.")

    try:
        return Block.from_dict(
            {
                **block_payload,
                "index": index,
                "previous_hash": previous_hash.strip(),
                "timestamp": timestamp_value,
                "transactions": transactions,
                "miner": miner_value,
                "hash": block_hash.strip(),
            }
        )
    except ValueError as exc:
        raise MalformedBlockError(str(exc)) from exc


def _normalize_transaction_payload(transaction_payload):
    if not isinstance(transaction_payload, dict):
        raise MalformedBlockError("Block transaction payload must be an object.")

    _reject_forbidden_fields(
        transaction_payload,
        ["sender", "recipient", "amount", "tip", "payload_size_kb", "signature", "created_at"],
        MalformedBlockError,
        "Block transaction payload",
    )

    for field_name in ["sender", "recipient", "amount"]:
        if field_name not in transaction_payload:
            raise MalformedBlockError(f"Block transaction {field_name} is required.")

    if not isinstance(transaction_payload["sender"], str) or not transaction_payload["sender"].strip():
        raise MalformedBlockError("Block transaction sender is required.")
    if not isinstance(transaction_payload["recipient"], str) or not transaction_payload["recipient"].strip():
        raise MalformedBlockError("Block transaction recipient is required.")
    sender_value = transaction_payload["sender"].strip()
    recipient_value = transaction_payload["recipient"].strip()
    if sender_value not in {"GENESIS", "REWARD_POOL"} and not is_valid_user_wallet_identity(sender_value):
        raise MalformedBlockError("Block transaction sender is required.")
    if not is_valid_user_wallet_identity(recipient_value):
        raise MalformedBlockError("Block transaction recipient is required.")

    amount_value = transaction_payload["amount"]
    tip_value = transaction_payload.get("tip", 0)
    payload_size_kb_value = transaction_payload.get("payload_size_kb", 0)
    created_at_value = transaction_payload.get("created_at")
    try:
        amount = float(amount_value)
        tip = float(tip_value)
        payload_size_kb = float(payload_size_kb_value)
        if created_at_value is not None:
            created_at = float(created_at_value)
        else:
            created_at = None
    except (TypeError, ValueError):
        raise MalformedBlockError("Block transaction amount, tip, and payload size must be numeric.")

    if not math.isfinite(amount) or amount < 0:
        raise MalformedBlockError("Block transaction amount must be non-negative.")
    if not math.isfinite(tip) or tip < 0:
        raise MalformedBlockError("Block transaction tip must be non-negative.")
    if not math.isfinite(payload_size_kb) or payload_size_kb < 0:
        raise MalformedBlockError("Block transaction payload size must be non-negative.")
    if created_at is not None and (not math.isfinite(created_at) or created_at < 0):
        raise MalformedBlockError("Block transaction created_at must be a valid timestamp.")

    transaction_dict = {
        **transaction_payload,
        "sender": sender_value,
        "recipient": recipient_value,
        "amount": amount_value,
        "tip": tip_value,
        "payload_size_kb": payload_size_kb_value,
    }
    if created_at is not None:
        transaction_dict["created_at"] = created_at_value
    else:
        transaction_dict.pop("created_at", None)
    return Transaction.from_dict(transaction_dict)


def _validate_block_hash(blockchain, block):
    try:
        calculated_hash = block.calculate_hash()
    except ValueError as exc:
        raise MalformedBlockError(str(exc)) from exc
    if block.hash != calculated_hash:
        raise MalformedBlockError("Block hash does not match block contents.")

    block_dict = block.to_dict()
    try:
        expected_hash = blockchain.calculate_hash_from_dict(block_dict)
    except ValueError as exc:
        raise MalformedBlockError(str(exc)) from exc
    if block.hash != expected_hash:
        raise MalformedBlockError("Block hash does not match existing block validation.")


def _validate_block_extends_chain(blockchain, block, current_chain, validate_hash=True, validate_chain=True):
    latest_block = current_chain[-1]
    if block.previous_hash != latest_block.hash:
        raise ChainExtensionError(
            "Block does not extend the local chain tip. Fork resolution is not implemented yet."
        )
    if block.index != latest_block.index + 1:
        raise MalformedBlockError("Block index must extend the local chain by one.")

    try:
        blockchain.validate_protocol_v1_block_payload(block.to_dict())
        blockchain.validate_block_certificate_metadata(
            block.to_dict(),
            prior_chain=[
                existing_block.to_dict() if hasattr(existing_block, "to_dict") else existing_block
                for existing_block in current_chain
            ],
        )
    except ValueError as exc:
        if isinstance(exc, NativeBlockValidationError):
            raise MalformedBlockError(str(exc), code=exc.code, details=exc.details)
        raise MalformedBlockError(str(exc))
    if validate_hash:
        _validate_block_hash(blockchain, block)
    _validate_block_transactions(blockchain, block, prior_chain=current_chain)

    if validate_chain:
        candidate_chain = [existing_block.to_dict() for existing_block in current_chain] + [block.to_dict()]
        if not blockchain.is_chain_valid(candidate_chain):
            raise MalformedBlockError("Block failed chain validation.")


def _validate_block_transactions(blockchain, block, *, prior_chain=None):
    for transaction in block.transactions:
        if not transaction.is_valid():
            raise MalformedBlockError("Block contains an invalid transaction.")
        if transaction.sender not in {"GENESIS", "REWARD_POOL"} and not blockchain.validate_transaction(transaction):
            raise MalformedBlockError("Block contains an invalid transaction.")
    try:
        source_chain = blockchain.chain if prior_chain is None else prior_chain
        chain_prefix = [
            existing_block.to_dict() if hasattr(existing_block, "to_dict") else existing_block
            for existing_block in source_chain
        ]
        blockchain.validate_block_native_transactions(block.to_dict(), prior_chain=chain_prefix)
    except ValueError as exc:
        if isinstance(exc, NativeBlockValidationError):
            raise MalformedBlockError(str(exc), code=exc.code, details=exc.details) from exc
        raise MalformedBlockError(str(exc)) from exc


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
    return blockchain.storage.get_vote(submission_id, voter, blockchain.votes)


def _looks_like_protocol_v1_domain_message(message, *, object_type=None):
    if not isinstance(message, str) or not message.strip():
        return False
    try:
        payload = json.loads(message)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    if payload.get("protocol") != "zoidbergchain":
        return False
    if payload.get("protocol_version") != PROTOCOL_VERSION:
        return False
    if object_type is not None and payload.get("object_type") != object_type:
        return False
    return isinstance(payload.get("domain"), str) and isinstance(payload.get("network_id"), str) and "payload" in payload


def _normalize_vote_payload(vote_payload, local_network_name):
    if not isinstance(vote_payload, dict):
        raise MalformedVoteError("Vote payload must be an object.")

    _reject_forbidden_fields(
        vote_payload,
        [
            "vote_version",
            "protocol_version",
            "network_id",
            "submission_id",
            "voter",
            "vote_type",
            "vote_value",
            "content_hash",
            "voter_wallet_address",
            "signature_scheme",
            "vote_signature",
            "vote_message",
            "signed_message_hash",
            "vote_nonce",
            "vote_issued_at",
            "vote_expires_at",
            "signed_at",
            "identity_source",
            "created_at",
            "vote_timestamp",
        ],
        MalformedVoteError,
        "Vote payload",
    )

    normalized = {}
    for field_name in ["submission_id", "voter"]:
        value = vote_payload.get(field_name)
        validator = (
            (lambda raw: isinstance(raw, str) and bool(raw.strip()))
            if field_name == "submission_id"
            else is_valid_user_wallet_identity
        )
        if not isinstance(value, str) or not value.strip() or not validator(value.strip()):
            raise MalformedVoteError(f"Vote {field_name} is required.")
        if field_name == "voter":
            normalized_wallet = normalize_wallet_address(value.strip())
            normalized[field_name] = normalized_wallet or value.strip()
        else:
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

    content_hash = vote_payload.get("content_hash")
    if content_hash is not None:
        normalized_content_hash = content_hash.strip() if isinstance(content_hash, str) else ""
        if not is_valid_content_hash(normalized_content_hash):
            raise MalformedVoteError("Vote content_hash must be a 64-character lowercase hexadecimal string.")
        normalized["content_hash"] = normalized_content_hash

    vote_version = vote_payload.get("vote_version")
    if vote_version is not None:
        if isinstance(vote_version, bool) or not isinstance(vote_version, int) or vote_version != PROTOCOL_V1_VOTE_VERSION:
            raise MalformedVoteError("Vote vote_version is unsupported.")
        normalized["vote_version"] = vote_version

    protocol_version = vote_payload.get("protocol_version")
    if protocol_version is not None:
        if isinstance(protocol_version, bool) or not isinstance(protocol_version, int):
            raise MalformedVoteError("Vote protocol_version must be a positive integer.")
        if protocol_version != PROTOCOL_VERSION:
            raise MalformedVoteError("Vote protocol_version is unsupported.")
        normalized["protocol_version"] = protocol_version

    network_id = vote_payload.get("network_id")
    if network_id is not None:
        if not isinstance(network_id, str) or not network_id.strip():
            raise MalformedVoteError("Vote network_id is required.")
        try:
            normalized["network_id"] = resolve_protocol_v1_network_id(network_id=network_id.strip())
        except ValueError as exc:
            raise MalformedVoteError(str(exc)) from exc

    normalized["voter_wallet_address"] = vote_payload.get("voter_wallet_address")
    normalized["signature_scheme"] = vote_payload.get("signature_scheme")
    normalized["vote_signature"] = vote_payload.get("vote_signature")
    normalized["vote_message"] = vote_payload.get("vote_message")
    normalized["signed_message_hash"] = vote_payload.get("signed_message_hash")
    normalized["vote_nonce"] = vote_payload.get("vote_nonce")
    normalized["vote_issued_at"] = vote_payload.get("vote_issued_at")
    normalized["vote_expires_at"] = vote_payload.get("vote_expires_at")
    normalized["signed_at"] = vote_payload.get("signed_at")
    normalized["identity_source"] = vote_payload.get("identity_source")

    if normalized.get("vote_version") is None and any(
        normalized.get(field_name) is not None
        for field_name in ["protocol_version", "network_id", "vote_issued_at", "vote_expires_at"]
    ):
        raise MalformedVoteError("Vote vote_version is required when Protocol v1 vote fields are present.")

    voter_wallet_address = normalized["voter_wallet_address"]
    normalized_wallet_address = normalize_wallet_address(voter_wallet_address) if isinstance(voter_wallet_address, str) else None
    if normalized_wallet_address:
        normalized["voter_wallet_address"] = normalized_wallet_address

    if normalized["vote_signature"] or normalized["vote_message"]:
        if normalized["signature_scheme"] != "personal_sign":
            raise MalformedVoteError("Vote signature_scheme must be personal_sign.")
        if not isinstance(normalized["vote_message"], str) or not normalized["vote_message"].strip():
            raise MalformedVoteError("Vote vote_message is required when signature metadata is provided.")
        if not isinstance(normalized["vote_signature"], str) or not normalized["vote_signature"].strip():
            raise MalformedVoteError("Vote vote_signature is required when signature metadata is provided.")

        try:
            recovered_wallet = recover_signed_wallet_address(
                normalized["vote_message"],
                normalized["vote_signature"],
            )
        except ValueError as exc:
            raise MalformedVoteError(str(exc)) from exc

        if normalized.get("vote_version") == PROTOCOL_V1_VOTE_VERSION:
            if normalized.get("protocol_version") != PROTOCOL_VERSION:
                raise MalformedVoteError("Vote protocol_version is required for Protocol v1 votes.")
            if normalized.get("network_id") is None:
                raise MalformedVoteError("Vote network_id is required for Protocol v1 votes.")
            expected_network_id = resolve_protocol_v1_network_id(network_name=local_network_name)
            if normalized["network_id"] != expected_network_id:
                raise MalformedVoteError("Vote belongs to a different network.")
            if normalized.get("content_hash") is None:
                raise MalformedVoteError("Vote content_hash is required for Protocol v1 votes.")
            if not isinstance(normalized.get("vote_nonce"), str) or not normalized["vote_nonce"].strip():
                raise MalformedVoteError("Vote vote_nonce is required for Protocol v1 votes.")
            if not isinstance(normalized.get("vote_issued_at"), str) or not normalized["vote_issued_at"].strip():
                raise MalformedVoteError("Vote vote_issued_at is required for Protocol v1 votes.")
            if not isinstance(normalized.get("vote_expires_at"), str) or not normalized["vote_expires_at"].strip():
                raise MalformedVoteError("Vote vote_expires_at is required for Protocol v1 votes.")
            expected_voter = normalize_wallet_address(normalized["voter"])
            if expected_voter is None:
                raise MalformedVoteError("Protocol v1 signed votes require an Ethereum-style voter wallet.")
            expected_message = build_protocol_v1_vote_message(
                wallet_address=expected_voter,
                network_id=normalized["network_id"],
                submission_id=normalized["submission_id"],
                content_hash=normalized["content_hash"],
                vote_type=normalized["vote_type"],
                nonce=normalized["vote_nonce"],
                issued_at=normalized["vote_issued_at"],
                expires_at=normalized["vote_expires_at"],
            )
            if normalized["vote_message"].strip() != expected_message:
                raise MalformedVoteError("Vote vote_message does not match the Protocol v1 vote payload.")
            if recovered_wallet != expected_voter:
                raise MalformedVoteError("Vote signature does not match voter.")
            normalized["voter"] = expected_voter
            if normalized["voter_wallet_address"] is None:
                normalized["voter_wallet_address"] = expected_voter
            elif normalized["voter_wallet_address"] != expected_voter:
                raise MalformedVoteError("Vote voter_wallet_address does not match voter.")
            if normalized.get("signed_message_hash") and normalized["signed_message_hash"] != hash_wallet_message(expected_message):
                raise MalformedVoteError("Vote signed_message_hash does not match vote_message.")
        else:
            if normalized.get("vote_version") is not None:
                raise MalformedVoteError("Vote signature metadata is incompatible with the declared vote_version.")
            if _looks_like_protocol_v1_domain_message(normalized["vote_message"], object_type=OBJECT_TYPE_VOTE):
                raise MalformedVoteError("Vote vote_version is required for Protocol v1 vote messages.")
            if recovered_wallet != normalized["voter"]:
                raise MalformedVoteError("Vote signature does not match voter.")
            if normalized["voter_wallet_address"] is None:
                normalized["voter_wallet_address"] = recovered_wallet
            elif normalized["voter_wallet_address"] != recovered_wallet:
                raise MalformedVoteError("Vote voter_wallet_address does not match voter.")
            if normalized.get("signed_message_hash") and normalized["signed_message_hash"] != hash_wallet_message(normalized["vote_message"]):
                raise MalformedVoteError("Vote signed_message_hash does not match vote_message.")
    elif normalized.get("vote_version") == PROTOCOL_V1_VOTE_VERSION:
        raise MalformedVoteError("Protocol v1 votes must include signature metadata.")

    return normalized


def _normalize_submission_payload(submission_payload):
    if not isinstance(submission_payload, dict):
        raise MalformedSubmissionError("Submission payload must be an object.")

    _reject_forbidden_fields(
        submission_payload,
        [
            "submission_id",
            "image_path",
            "text_content",
            "submitter",
            "status",
            "created_at",
            "hard_reject_reason",
            "content_hash",
            "content_id",
            "certificate_id",
            "decision_reason",
            "decision_finalized_at",
            "mint_blocked",
            "mint_block_reason",
            "mint_blocked_at",
            "mint_blocked_by",
            "mint_block_notes",
            "creator_wallet_address",
            "signature_scheme",
            "submission_signature",
            "submission_message",
            "signed_message_hash",
            "submission_nonce",
            "signed_at",
            "identity_source",
        ],
        MalformedSubmissionError,
        "Submission payload",
    )

    normalized = {}
    submission_id = submission_payload.get("submission_id")
    if not isinstance(submission_id, str) or not submission_id.strip():
        raise MalformedSubmissionError("Submission submission_id is required.")
    normalized["submission_id"] = submission_id.strip()

    image_path = submission_payload.get("image_path") or ""
    text_content = submission_payload.get("text_content") or ""
    if not isinstance(image_path, str) or not isinstance(text_content, str):
        raise MalformedSubmissionError("Submission image_path and text_content must be strings when provided.")
    normalized["image_path"] = image_path.strip()
    normalized["text_content"] = text_content.strip()
    if normalized["image_path"] and not normalized["text_content"] and not submission_payload.get("content_hash"):
        raise MalformedSubmissionError("Submission text_content is required.")
    if not normalized["image_path"] and not normalized["text_content"] and not submission_payload.get("content_hash"):
        raise MalformedSubmissionError("Submission must include image_path, text_content, or content_hash.")

    submitter = submission_payload.get("submitter")
    submitter_value = submitter.strip() if isinstance(submitter, str) else ""
    normalized_submitter_wallet = normalize_wallet_address(submitter_value) if submitter_value else None
    if not submitter_value or not (is_valid_wallet_public_key(submitter_value) or normalized_submitter_wallet):
        raise MalformedSubmissionError("Submission submitter is required.")
    normalized["submitter"] = normalized_submitter_wallet or submitter_value

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
        normalized_content_hash = content_hash.strip() if isinstance(content_hash, str) else ""
        if not is_valid_content_hash(normalized_content_hash):
            raise MalformedSubmissionError(
                "Submission content_hash must be a 64-character lowercase hexadecimal string."
            )
        normalized["content_hash"] = normalized_content_hash
    else:
        normalized["content_hash"] = calculate_submission_content_hash(
            normalized["image_path"],
            normalized["text_content"],
            normalized["submitter"],
        )

    content_id = submission_payload.get("content_id")
    if content_id is not None:
        if not isinstance(content_id, str) or not content_id.strip():
            raise MalformedSubmissionError("Submission content_id must be a non-empty string.")
        normalized["content_id"] = content_id.strip()
        try:
            Submission(
                image_path="",
                text_content="",
                submitter=normalized["submitter"],
                content_hash=normalized["content_hash"],
                content_id=normalized["content_id"],
            )
        except ValueError as exc:
            raise MalformedSubmissionError(str(exc)) from exc

    normalized["status"] = PENDING
    normalized["hard_reject_reason"] = None
    normalized["decision_reason"] = submission_payload.get("decision_reason")
    decision_finalized_at = submission_payload.get("decision_finalized_at")
    if decision_finalized_at is not None:
        try:
            decision_finalized_at = float(decision_finalized_at)
        except (TypeError, ValueError):
            raise MalformedSubmissionError("Submission decision_finalized_at must be a valid timestamp.")
        if not math.isfinite(decision_finalized_at) or decision_finalized_at < 0:
            raise MalformedSubmissionError("Submission decision_finalized_at must be a valid timestamp.")
    normalized["decision_finalized_at"] = decision_finalized_at
    normalized["creator_wallet_address"] = submission_payload.get("creator_wallet_address") or normalized["submitter"]
    normalized["signature_scheme"] = submission_payload.get("signature_scheme")
    normalized["submission_signature"] = submission_payload.get("submission_signature")
    normalized["submission_message"] = submission_payload.get("submission_message")
    normalized["signed_message_hash"] = submission_payload.get("signed_message_hash")
    normalized["submission_nonce"] = submission_payload.get("submission_nonce")
    normalized["signed_at"] = submission_payload.get("signed_at")
    normalized["identity_source"] = submission_payload.get("identity_source")

    creator_wallet_address = normalized["creator_wallet_address"]
    creator_wallet_normalized = normalize_wallet_address(creator_wallet_address) if isinstance(creator_wallet_address, str) else None
    if creator_wallet_address and creator_wallet_normalized:
        normalized["creator_wallet_address"] = creator_wallet_normalized

    if normalized["submission_signature"] or normalized["submission_message"]:
        if normalized["signature_scheme"] != "personal_sign":
            raise MalformedSubmissionError("Submission signature_scheme must be personal_sign.")
        if not isinstance(normalized["submission_message"], str) or not normalized["submission_message"].strip():
            raise MalformedSubmissionError("Submission submission_message is required when signature metadata is provided.")
        if not isinstance(normalized["submission_signature"], str) or not normalized["submission_signature"].strip():
            raise MalformedSubmissionError("Submission submission_signature is required when signature metadata is provided.")

        try:
            recovered_wallet = recover_signed_wallet_address(
                normalized["submission_message"],
                normalized["submission_signature"],
            )
        except ValueError as exc:
            raise MalformedSubmissionError(str(exc)) from exc

        if recovered_wallet != normalized["submitter"]:
            raise MalformedSubmissionError("Submission signature does not match submitter.")
        if normalized["creator_wallet_address"] != recovered_wallet:
            raise MalformedSubmissionError("Submission creator_wallet_address does not match submitter.")

        signed_message_hash = normalized.get("signed_message_hash")
        if signed_message_hash and signed_message_hash != hash_wallet_message(normalized["submission_message"]):
            raise MalformedSubmissionError("Submission signed_message_hash does not match submission_message.")

    return normalized
