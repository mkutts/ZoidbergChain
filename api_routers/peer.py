"""Peer API HTTP adapters."""

from fastapi import APIRouter

import api_runtime as _runtime
from api_runtime import *  # noqa: F401,F403 - shared API wiring and schemas

_ROUTER_RUNTIME_GENERATION = _runtime._ROUTER_RUNTIME_GENERATION
router = APIRouter()


def _sync_runtime_globals():
    """Refresh compatibility globals without replacing module identity."""
    globals().update({name: value for name, value in vars(_runtime).items() if not name.startswith("__")})

@router.post('/peers/register')
@api_limit("peer_receive")
async def register_peer(request: Request, registration: PeerRegistration, _: None = Depends(require_peer_secret)):
    _sync_runtime_globals()
    if registration.network_name.strip() != NETWORK_NAME:
        raise HTTPException(status_code=400, detail="Peer belongs to a different network.")

    try:
        authenticated_peer = _require_protocol_v1_peer_claims_match_auth(
            request,
            claimed_node_id=registration.node_id,
            claimed_network_name=registration.network_name,
        )
        claimed_node_id = (
            authenticated_peer.sender_node_id
            if authenticated_peer is not None
            else registration.node_id
        )
        peer = register_peer_operation(
            peer_store,
            node_id=claimed_node_id,
            url=registration.url,
            network_name=registration.network_name,
            local_node_id=NODE_ID,
            public_node_url=PUBLIC_NODE_URL,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"message": "Peer registered successfully.", "peer": peer}


@router.get('/peers')
@api_limit("public_read")
async def get_peers(request: Request):
    _sync_runtime_globals()
    return {"peers": peer_store.list_peers()}


@router.post('/peers/transactions/receive')
@api_limit("peer_receive")
async def receive_transaction_from_peer(
    request: Request,
    receive_request: PeerTransactionReceive,
    _: None = Depends(require_peer_secret),
):
    _sync_runtime_globals()
    try:
        authenticated_peer = _require_protocol_v1_peer_claims_match_auth(
            request,
            claimed_node_id=receive_request.origin_node_id,
            claimed_network_name=receive_request.network_name,
        )
        return receive_peer_transaction(
            blockchain=blockchain,
            peer_store=peer_store,
            origin_node_id=(
                authenticated_peer.sender_node_id
                if authenticated_peer is not None
                else receive_request.origin_node_id
            ),
            network_name=receive_request.network_name,
            transaction_payload=receive_request.transaction,
            local_network_name=NETWORK_NAME,
        )
    except UnauthorizedPeerError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except WrongNetworkError as exc:
        return _peer_transaction_error_response(
            400,
            tx_id=(receive_request.transaction or {}).get("tx_id"),
            reason="wrong_network",
            message=str(exc),
        )
    except ConflictingTransactionError as exc:
        return _peer_transaction_error_response(
            409,
            tx_id=(receive_request.transaction or {}).get("tx_id"),
            reason="conflicting_nonce",
            message=str(exc),
        )
    except MalformedTransactionError as exc:
        message = str(exc)
        reason = "validation_failed"
        lowered = message.lower()
        if "tx_id does not match" in lowered:
            reason = "invalid_tx_id"
        elif "mempool admission" in lowered and ("transaction version is required" in lowered or "transaction_version" in lowered):
            reason = "unsupported_transaction_version"
        elif "signature" in lowered:
            reason = "invalid_signature"
        elif "insufficient available balance" in lowered:
            reason = "insufficient_available_balance"
        elif "nonzero fees are not enabled yet" in lowered:
            reason = "invalid_fee_policy"
        elif "nonce" in lowered:
            reason = "invalid_nonce"
        return _peer_transaction_error_response(
            400,
            tx_id=(receive_request.transaction or {}).get("tx_id"),
            reason=reason,
            message=message,
        )


@router.get('/peers/transactions/{tx_id}')
@api_limit("peer_receive")
async def get_peer_transaction(
    request: Request,
    tx_id: str,
    _: None = Depends(require_peer_secret),
):
    _sync_runtime_globals()
    _require_protocol_v1_active_peer(request)
    transaction = blockchain.get_native_transaction(tx_id)
    if not transaction:
        raise HTTPException(status_code=404, detail=f"Transaction not found: {tx_id}")
    return {
        "transaction": transaction,
        "network_name": NETWORK_NAME,
    }


@router.get('/peers/mempool/summary')
@api_limit("peer_receive")
async def get_peer_mempool_summary(
    request: Request,
    _: None = Depends(require_peer_secret),
):
    _sync_runtime_globals()
    _require_protocol_v1_active_peer(request)
    transactions = blockchain.list_mempool_transactions()
    return {
        "tx_ids": [transaction.get("tx_id") for transaction in transactions if transaction.get("tx_id")],
        "count": len(transactions),
        "network_name": NETWORK_NAME,
    }


@router.post('/peers/submissions/receive')
@api_limit("peer_receive")
async def receive_submission_from_peer(request: Request, receive_request: PeerSubmissionReceive, _: None = Depends(require_peer_secret)):
    _sync_runtime_globals()
    try:
        authenticated_peer = _require_protocol_v1_peer_claims_match_auth(
            request,
            claimed_node_id=receive_request.origin_node_id,
            claimed_network_name=receive_request.network_name,
        )
        origin_node_id = (
            authenticated_peer.sender_node_id
            if authenticated_peer is not None
            else receive_request.origin_node_id
        )
        if not peer_store.get_active_peer(origin_node_id):
            _validate_unregistered_peer_submission_shape(receive_request)
        return receive_peer_submission(
            blockchain=blockchain,
            peer_store=peer_store,
            origin_node_id=origin_node_id,
            network_name=receive_request.network_name,
            submission_payload=receive_request.submission.model_dump(),
            local_network_name=NETWORK_NAME,
        )
    except UnauthorizedPeerError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except WrongNetworkError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except MalformedSubmissionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DuplicateSubmissionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post('/peers/votes/receive')
@api_limit("peer_receive")
async def receive_vote_from_peer(request: Request, receive_request: PeerVoteReceive, _: None = Depends(require_peer_secret)):
    _sync_runtime_globals()
    try:
        authenticated_peer = _require_protocol_v1_peer_claims_match_auth(
            request,
            claimed_node_id=receive_request.origin_node_id,
            claimed_network_name=receive_request.network_name,
        )
        origin_node_id = (
            authenticated_peer.sender_node_id
            if authenticated_peer is not None
            else receive_request.origin_node_id
        )
        if not peer_store.get_active_peer(origin_node_id):
            _validate_unregistered_peer_vote_shape(receive_request)
        return receive_peer_vote(
            blockchain=blockchain,
            peer_store=peer_store,
            origin_node_id=origin_node_id,
            network_name=receive_request.network_name,
            vote_payload={
                "vote_version": receive_request.vote_version,
                "protocol_version": receive_request.protocol_version,
                "network_id": receive_request.network_id,
                "submission_id": receive_request.submission_id,
                "voter": receive_request.voter,
                "vote_type": receive_request.vote_type,
                "vote_value": receive_request.vote_value,
                "content_hash": receive_request.content_hash,
                "voter_wallet_address": receive_request.voter_wallet_address,
                "signature_scheme": receive_request.signature_scheme,
                "vote_signature": receive_request.vote_signature,
                "vote_message": receive_request.vote_message,
                "signed_message_hash": receive_request.signed_message_hash,
                "vote_nonce": receive_request.vote_nonce,
                "vote_issued_at": receive_request.vote_issued_at,
                "vote_expires_at": receive_request.vote_expires_at,
                "signed_at": receive_request.signed_at,
                "identity_source": receive_request.identity_source,
                "created_at": receive_request.created_at,
                "vote_timestamp": receive_request.vote_timestamp,
            },
            local_network_name=NETWORK_NAME,
        )
    except UnauthorizedPeerError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except WrongNetworkError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except MalformedVoteError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except UnknownSubmissionError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictingVoteError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post('/peers/certificates/receive')
@api_limit("peer_receive")
async def receive_certificate_from_peer(request: Request, receive_request: PeerCertificateReceive, _: None = Depends(require_peer_secret)):
    _sync_runtime_globals()
    try:
        if receive_request.certificate is None:
            raise HTTPException(status_code=400, detail="Certificate payload is required.")
        authenticated_peer = _require_protocol_v1_peer_claims_match_auth(
            request,
            claimed_node_id=receive_request.origin_node_id,
            claimed_network_name=receive_request.network_name,
        )
        origin_node_id = (
            authenticated_peer.sender_node_id
            if authenticated_peer is not None
            else receive_request.origin_node_id
        )
        if not peer_store.get_active_peer(origin_node_id):
            _validate_unregistered_peer_certificate_shape(receive_request)
        return receive_peer_certificate(
            blockchain=blockchain,
            peer_store=peer_store,
            origin_node_id=origin_node_id,
            network_name=receive_request.network_name,
            certificate_payload=receive_request.certificate.model_dump(),
            local_network_name=NETWORK_NAME,
        )
    except UnauthorizedPeerError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except WrongNetworkError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except MalformedCertificateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ConflictingCertificateError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post('/peers/blocks/receive')
@api_limit("peer_receive")
async def receive_block_from_peer(request: Request, receive_request: PeerBlockReceive, _: None = Depends(require_peer_secret)):
    _sync_runtime_globals()
    try:
        raw_payload = await request.json()
        if receive_request.block is None:
            raise HTTPException(status_code=400, detail="Block payload is required.")
        authenticated_peer = _require_protocol_v1_peer_claims_match_auth(
            request,
            claimed_node_id=receive_request.origin_node_id,
            claimed_network_name=receive_request.network_name,
        )
        origin_node_id = (
            authenticated_peer.sender_node_id
            if authenticated_peer is not None
            else receive_request.origin_node_id
        )
        if not peer_store.get_active_peer(origin_node_id):
            _validate_unregistered_peer_block_shape(receive_request)
        return receive_peer_block(
            blockchain=blockchain,
            peer_store=peer_store,
            origin_node_id=origin_node_id,
            network_name=receive_request.network_name,
            block_payload=(
                raw_payload.get("block")
                if isinstance(raw_payload, dict) and isinstance(raw_payload.get("block"), dict)
                else receive_request.block.model_dump(exclude_none=True)
            ),
            related_submission_id=receive_request.related_submission_id,
            local_network_name=NETWORK_NAME,
            certificate_payload=(
                raw_payload.get("certificate")
                if receive_request.certificate
                and isinstance(raw_payload, dict)
                and isinstance(raw_payload.get("certificate"), dict)
                else (
                    receive_request.certificate.model_dump(exclude_none=True)
                    if receive_request.certificate
                    else None
                )
            ),
        )
    except UnauthorizedPeerError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except WrongNetworkError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except MalformedCertificateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ConflictingCertificateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except MalformedBlockError as e:
        raise HTTPException(
            status_code=400,
            detail=e.to_detail() if hasattr(e, "to_detail") else str(e),
        )
    except DuplicateBlockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ChainExtensionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get('/peers/chain/summary')
@api_limit("peer_receive")
async def peer_chain_summary(
    request: Request,
    _: None = Depends(require_peer_secret),
):
    _sync_runtime_globals()
    _require_protocol_v1_active_peer(request)
    return _chain_summary_payload()


@router.get('/peers/chain/blocks')
@api_limit("peer_receive")
async def peer_chain_blocks(
    request: Request,
    from_height: int = 0,
    include_media_bytes: bool = False,
    _: None = Depends(require_peer_secret),
):
    _sync_runtime_globals()
    _require_protocol_v1_active_peer(request)
    if from_height < 0:
        raise HTTPException(status_code=400, detail="from_height must be non-negative.")

    blocks = [
        block
        for block in blockchain.chain
        if block.index >= from_height
    ]
    certificate_ids = {
        block.certificate_id
        for block in blocks
        if block.certificate_id
    }
    return {
        "blocks": [
            block.to_dict(include_media_bytes=include_media_bytes)
            for block in blocks
        ],
        "certificates": [
            certificate.to_dict()
            for certificate in blockchain.originality_certificates
            if certificate.certificate_id in certificate_ids
        ],
    }


@router.post('/chain/sync')
@api_limit("chain_sync")
async def sync_chain(request: Request):
    _sync_runtime_globals()
    return sync_chain_from_peers(
        blockchain=blockchain,
        peer_store=peer_store,
        network_name=NETWORK_NAME,
        origin_node_id=NODE_ID,
    )


@router.post('/blocks/{block_hash}/broadcast')
@api_limit("mint")
async def broadcast_block(request: Request, block_hash: str):
    _sync_runtime_globals()
    block = blockchain.get_block_by_hash(block_hash)
    if not block:
        raise HTTPException(status_code=404, detail=f"Block not found: {block_hash}")

    broadcast_result = broadcast_block_to_peers(
        block=block,
        peer_store=peer_store,
        origin_node_id=NODE_ID,
        network_name=NETWORK_NAME,
        certificate=(
            blockchain.get_originality_certificate(block.certificate_id)
            if block.certificate_id
            else None
        ),
    )
    return {
        "message": "Block broadcast attempted.",
        "block": _serialize_block(block),
        "broadcast": broadcast_result,
    }


@router.get('/peers/content/{content_hash}/metadata')
@api_limit("peer_receive")
async def get_peer_content_metadata(
    request: Request,
    content_hash: str,
    _: None = Depends(require_peer_secret),
):
    _sync_runtime_globals()
    _require_protocol_v1_active_peer(request)
    content_object = _require_content_object(content_hash)
    return {"content": _peer_safe_content_metadata(content_object)}


@router.get('/peers/content/{content_hash}')
@api_limit("peer_receive")
async def download_peer_content(
    request: Request,
    content_hash: str,
    _: None = Depends(require_peer_secret),
):
    _sync_runtime_globals()
    _require_protocol_v1_active_peer(request)
    content_object = _require_content_object(content_hash)
    verification = blockchain.verify_content_download_operation(
        content_object,
        verifier=verify_content_object_payload,
        data_dir=blockchain.storage.data_dir,
    )
    if verification["error"] == "missing_file":
        raise HTTPException(status_code=404, detail=f"Content file not found for hash: {content_hash}")
    if not verification["verified"]:
        raise HTTPException(status_code=409, detail="Content file failed integrity verification.")
    if content_object.mime_type == TEXT_MIME_TYPE and content_object.text_content:
        return PlainTextResponse(content=content_object.text_content, media_type=TEXT_MIME_TYPE)

    file_path = resolve_local_path(content_object.local_path, data_dir=blockchain.storage.data_dir)
    if not file_path or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail=f"Content file not found for hash: {content_hash}")

    if content_object.mime_type == TEXT_MIME_TYPE:
        try:
            text_body = load_content_bytes(
                content_object.content_hash,
                content_object.mime_type,
                data_dir=blockchain.storage.data_dir,
            ).decode("utf-8")
        except (FileNotFoundError, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=409, detail="Stored text content could not be decoded safely.") from exc
        return PlainTextResponse(content=text_body, media_type=TEXT_MIME_TYPE)

    return FileResponse(
        path=file_path,
        media_type=content_object.mime_type,
        filename=content_object.file_name or os.path.basename(file_path),
    )


@router.post('/content/{content_hash}/sync')
@api_limit("dev_endpoint")
async def sync_content_from_peers_endpoint(request: Request, content_hash: str):
    _sync_runtime_globals()
    require_development_mode(True, "Manual content sync")
    if not is_valid_content_hash(content_hash):
        raise HTTPException(status_code=422, detail="content_hash must be a 64-character lowercase hexadecimal string.")

    result = sync_missing_content(
        blockchain=blockchain,
        peer_store=peer_store,
        content_hash=content_hash,
        origin_node_id=NODE_ID,
        network_name=NETWORK_NAME,
    )
    content_object = blockchain.get_content_object_by_hash(content_hash)
    return {
        "result": result,
        "content": _safe_content_metadata(content_object) if content_object else None,
    }


@router.post('/certificates/{certificate_id}/broadcast')
@api_limit("mint")
async def broadcast_certificate(request: Request, certificate_id: str):
    _sync_runtime_globals()
    certificate = blockchain.get_originality_certificate(certificate_id)
    if not certificate:
        raise HTTPException(
            status_code=404,
            detail=f"Originality certificate not found: {certificate_id}",
        )

    broadcast_result = broadcast_certificate_to_peers(
        certificate=certificate,
        peer_store=peer_store,
        origin_node_id=NODE_ID,
        network_name=NETWORK_NAME,
    )
    return {
        "message": "Originality certificate broadcast attempted.",
        "certificate": _serialize_certificate(certificate),
        "broadcast": broadcast_result,
    }


@router.post('/submissions/{submission_id}/broadcast')
@api_limit("submission_create")
async def broadcast_submission(request: Request, submission_id: str):
    _sync_runtime_globals()
    submission = blockchain.get_submission(submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail=f"Submission not found: {submission_id}")

    broadcast_result = broadcast_submission_to_peers(
        submission=submission,
        peer_store=peer_store,
        origin_node_id=NODE_ID,
        network_name=NETWORK_NAME,
    )
    return {
        "message": "Submission broadcast attempted.",
        "submission": _serialize_submission(submission),
        "broadcast": broadcast_result,
    }


@router.post('/submissions/{submission_id}/votes/broadcast')
@api_limit("vote")
async def broadcast_submission_votes(request: Request, submission_id: str):
    _sync_runtime_globals()
    try:
        vote_summary = blockchain.get_submission_votes(submission_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    broadcast_result = broadcast_votes_to_peers(
        votes=vote_summary["votes"],
        peer_store=peer_store,
        origin_node_id=NODE_ID,
        network_name=NETWORK_NAME,
    )
    return {
        "message": "Submission vote broadcast attempted.",
        "submission_id": submission_id,
        "broadcast": broadcast_result,
    }


@router.post('/transactions/{tx_id}/broadcast')
@api_limit("transaction_create")
async def broadcast_native_transaction(
    request: Request,
    tx_id: str,
    _: str = Depends(require_transaction_broadcast_access),
):
    _sync_runtime_globals()
    try:
        blockchain.admit_transaction_for_broadcast_operation(tx_id)
        report = broadcast_transaction_to_peers(
            blockchain=blockchain,
            tx_id=tx_id,
            peer_store=peer_store,
            origin_node_id=NODE_ID,
            network_name=NETWORK_NAME,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "tx_id": tx_id,
        "broadcasted": True,
        "peers_attempted": report["attempted"],
        "peers_accepted": report["accepted"],
        "results": report["results"],
    }


EXPLICIT_ROUTER = True

_ROUTE_ORDER = {
    ('POST', '/peers/register', 'register_peer'): 57,
    ('GET', '/peers', 'get_peers'): 58,
    ('POST', '/peers/transactions/receive', 'receive_transaction_from_peer'): 59,
    ('GET', '/peers/transactions/{tx_id}', 'get_peer_transaction'): 60,
    ('GET', '/peers/mempool/summary', 'get_peer_mempool_summary'): 61,
    ('POST', '/peers/submissions/receive', 'receive_submission_from_peer'): 62,
    ('POST', '/peers/votes/receive', 'receive_vote_from_peer'): 63,
    ('POST', '/peers/certificates/receive', 'receive_certificate_from_peer'): 64,
    ('POST', '/peers/blocks/receive', 'receive_block_from_peer'): 65,
    ('GET', '/peers/chain/summary', 'peer_chain_summary'): 68,
    ('GET', '/peers/chain/blocks', 'peer_chain_blocks'): 70,
    ('POST', '/chain/sync', 'sync_chain'): 71,
    ('POST', '/blocks/{block_hash}/broadcast', 'broadcast_block'): 73,
    ('GET', '/peers/content/{content_hash}/metadata', 'get_peer_content_metadata'): 81,
    ('GET', '/peers/content/{content_hash}', 'download_peer_content'): 83,
    ('POST', '/content/{content_hash}/sync', 'sync_content_from_peers_endpoint'): 84,
    ('POST', '/certificates/{certificate_id}/broadcast', 'broadcast_certificate'): 92,
    ('POST', '/submissions/{submission_id}/broadcast', 'broadcast_submission'): 93,
    ('POST', '/submissions/{submission_id}/votes/broadcast', 'broadcast_submission_votes'): 96,
    ('POST', '/transactions/{tx_id}/broadcast', 'broadcast_native_transaction'): 116,
}

for _route in router.routes:
    _method = next(iter(_route.methods))
    _route.endpoint.__route_order__ = _ROUTE_ORDER[(_method, _route.path, _route.name)]
