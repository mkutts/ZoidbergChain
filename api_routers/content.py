"""Content API HTTP adapters."""

from fastapi import APIRouter

import api_runtime as _runtime
from api_runtime import *  # noqa: F401,F403 - shared API wiring and schemas

_ROUTER_RUNTIME_GENERATION = _runtime._ROUTER_RUNTIME_GENERATION
router = APIRouter()


def _sync_runtime_globals():
    """Refresh compatibility globals for api monkeypatches and isolated nodes."""
    globals().update({name: value for name, value in vars(_runtime).items() if not name.startswith("__")})

@router.post('/content/upload')
@api_limit("submission_create")
async def upload_content(
    request: Request,
    file: UploadFile,
    submitted_by: Annotated[str, Form(..., min_length=1, max_length=128)],
    caption: Annotated[str | None, Form(max_length=MAX_CAPTION_LENGTH)] = None,
    content_type_hint: Annotated[str | None, Form(max_length=32)] = None,
):
    _sync_runtime_globals()
    submitted_by = _normalize_supported_user_identity(submitted_by, field_name="submitted_by")

    file_bytes = await file.read()
    try:
        validate_content_size(len(file_bytes))
        safe_caption = validate_caption(caption)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    declared_mime_type = (file.content_type or "").strip().lower() or None
    if declared_mime_type == "application/octet-stream":
        declared_mime_type = None
    if declared_mime_type is not None and declared_mime_type not in SUPPORTED_CONTENT_MIME_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported mime_type for uploaded content.")

    try:
        safe_original_filename = sanitize_original_filename(file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        content_object = blockchain.upload_binary_content_operation(
            file_bytes=file_bytes,
            submitted_by=submitted_by,
            mime_type=declared_mime_type,
            original_filename=safe_original_filename,
            caption=safe_caption,
            content_type_hint=content_type_hint,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _public_content_upload_response(content_object)


@router.post('/content/text')
@api_limit("submission_create")
async def upload_text_content(request: Request, payload: TextContentUpload):
    _sync_runtime_globals()
    submitted_by = _normalize_supported_user_identity(payload.submitted_by, field_name="submitted_by")

    try:
        content_object = blockchain.upload_text_content_operation(
            text_content=validate_text_content(payload.text_content),
            submitted_by=submitted_by,
            caption=validate_caption(payload.caption),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _public_content_upload_response(content_object)


@router.get('/content/{content_hash}/metadata')
@api_limit("public_read")
async def get_content_metadata(request: Request, content_hash: str):
    _sync_runtime_globals()
    content_object = _require_content_object(content_hash)
    return {"content": _safe_content_metadata(content_object)}


@router.get('/content/{content_hash}')
@api_limit("public_read")
async def download_content(request: Request, content_hash: str):
    _sync_runtime_globals()
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


@router.post('/submit_content')
@api_limit("submission_create")
async def submit_content(
    request: Request,
    authorization: str | None = Header(default=None),
    submitter: Annotated[str | None, Form(min_length=1, max_length=128)] = None,
    wallet_address: Annotated[str | None, Form(min_length=42, max_length=42, pattern=ETHEREUM_ADDRESS_PATTERN)] = None,
    message: Annotated[str | None, Form(min_length=1, max_length=4096)] = None,
    signature: Annotated[str | None, Form(min_length=1, max_length=4096)] = None,
    image: UploadFile | None = None,
    text_content: Annotated[str | None, Form(max_length=MAX_SUBMISSION_TEXT_LENGTH)] = None,
    content_hash: Annotated[str | None, Form(min_length=64, max_length=64, pattern=HEX_64_PATTERN)] = None,
    content_id: Annotated[str | None, Form(min_length=32, max_length=32, pattern=HEX_32_PATTERN)] = None,
):
    """Submit meme content for review without minting a blockchain block."""
    _sync_runtime_globals()
    signed_submission_requested = any(
        value is not None and str(value).strip()
        for value in [authorization, wallet_address, message, signature, content_hash, content_id]
    ) and not (submitter and not authorization and not wallet_address and not message and not signature)

    if signed_submission_requested:
        try:
            verified_wallet = resolve_verified_wallet_from_authorization(
                authorization,
                manager=wallet_auth_manager,
            )
        except HTTPException as exc:
            raise HTTPException(status_code=401, detail=exc.detail) from exc

        if image is not None:
            raise HTTPException(
                status_code=400,
                detail="Direct file submission is no longer supported here. Upload content first, then create a signed submission.",
            )
        if not message:
            raise HTTPException(status_code=400, detail="signed submission message is required.")
        if not signature:
            raise HTTPException(status_code=400, detail="signature is required.")

        content_object = _require_content_reference(content_hash, content_id)
        normalized_wallet = normalize_wallet_address(wallet_address or verified_wallet)
        if normalized_wallet is None or normalized_wallet != verified_wallet:
            raise HTTPException(status_code=403, detail="wallet_address must match the verified wallet session.")
        _enforce_submission_eligibility(verified_wallet)

        try:
            submission = blockchain.submit_signed_content_operation(
                wallet_address=verified_wallet,
                message=message,
                signature=signature,
                content_hash=content_object.content_hash,
                content_id=content_object.content_id,
                text_content=text_content or "",
                auth_manager=wallet_auth_manager,
            )
        except ValueError as exc:
            detail = str(exc)
            status_code = 400
            if "expired" in detail.lower() or "already been used" in detail.lower():
                status_code = 401
            raise HTTPException(status_code=status_code, detail=detail) from exc

    else:
        if not is_development():
            raise HTTPException(
                status_code=401,
                detail="MetaMask-signed submissions are required outside development mode.",
            )
        if not submitter:
            raise HTTPException(status_code=422, detail="submitter is required for the development-only submission path.")

        submitter = _normalize_supported_user_identity(submitter, field_name="submitter")

        if image is not None and (content_hash is not None or content_id is not None):
            raise HTTPException(status_code=400, detail="Provide either image upload or content linkage, not both.")

        if content_hash is not None or content_id is not None:
            try:
                submission = blockchain.submit_content_operation(
                    content_hash=content_hash,
                    content_id=content_id,
                    text_content=text_content or "",
                    submitter=submitter,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        else:
            if image is None or not image.filename:
                raise HTTPException(status_code=400, detail="Invalid image format. Allowed formats: jpg, jpeg, png, webp")

            file_bytes = await image.read()
            try:
                validate_content_size(len(file_bytes))
                safe_original_filename, _detected_mime_type = _validate_uploaded_image_payload(image, file_bytes)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            os.makedirs(SUBMISSIONS_DIR, exist_ok=True)
            image_path = os.path.join(SUBMISSIONS_DIR, os.path.basename(safe_original_filename))
            with open(image_path, "wb") as buffer:
                buffer.write(file_bytes)

            try:
                if not os.path.isfile(image_path):
                    return JSONResponse(status_code=400, content={"error": "Failed to save the uploaded image."})

                if not text_content:
                    text_content = extract_text(image_path)
                if not text_content:
                    return JSONResponse(status_code=400, content={"error": "No text found in the image."})

                submission = blockchain.submit_content_operation(
                    image_path=image_path,
                    text_content=text_content,
                    submitter=submitter,
                )
            finally:
                if os.path.isfile(image_path):
                    os.remove(image_path)

    broadcast_result = broadcast_submission_to_peers(
        submission=submission,
        peer_store=peer_store,
        origin_node_id=NODE_ID,
        network_name=NETWORK_NAME,
    )

    return {
        "message": "Content submitted successfully.",
        "submission": _serialize_submission(submission),
        "broadcast": broadcast_result,
    }


@router.get('/submissions')
@api_limit("public_read")
async def get_submissions(request: Request, status: SubmissionStatusValue | None = None):
    _sync_runtime_globals()
    submissions = [_serialize_submission(submission) for submission in blockchain.submissions]
    if status:
        submissions = [
            submission
            for submission in submissions
            if submission.get("status") == status
        ]
    submissions.sort(key=lambda submission: submission.get("created_at", 0), reverse=True)
    return {"submissions": submissions}


@router.get('/submissions/{submission_id}')
@api_limit("public_read")
async def get_submission(request: Request, submission_id: str):
    _sync_runtime_globals()
    submission = blockchain.get_submission(submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail=f"Submission not found: {submission_id}")
    return {"submission": _serialize_submission(submission)}


@router.get('/submissions/{submission_id}/certificate')
@api_limit("public_read")
async def get_submission_certificate(request: Request, submission_id: str):
    _sync_runtime_globals()
    submission = blockchain.get_submission(submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail=f"Submission not found: {submission_id}")

    certificate = blockchain.get_originality_certificate_for_submission(submission_id)
    if not certificate:
        raise HTTPException(
            status_code=404,
            detail=f"Originality certificate not found for submission: {submission_id}",
        )
    return {"certificate": _serialize_certificate(certificate)}


@router.get('/submissions/{submission_id}/voter-rewards')
@api_limit("public_read")
async def get_submission_voter_rewards(request: Request, submission_id: str):
    _sync_runtime_globals()
    try:
        return blockchain.get_submission_voter_reward_summary(submission_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get('/certificates/{certificate_id}')
@api_limit("public_read")
async def get_certificate(request: Request, certificate_id: str):
    _sync_runtime_globals()
    certificate = blockchain.get_originality_certificate(certificate_id)
    if not certificate:
        raise HTTPException(
            status_code=404,
            detail=f"Originality certificate not found: {certificate_id}",
        )
    return {"certificate": _serialize_certificate(certificate)}


@router.post('/submissions/{submission_id}/vote')
@api_limit("vote")
async def vote_on_submission(
    request: Request,
    submission_id: str,
    vote_type: Annotated[VoteTypeValue, Form(...)],
    authorization: str | None = Header(default=None),
    voter: Annotated[str | None, Form(min_length=1, max_length=128)] = None,
    wallet_address: Annotated[str | None, Form(min_length=42, max_length=42, pattern=ETHEREUM_ADDRESS_PATTERN)] = None,
    message: Annotated[str | None, Form(min_length=1, max_length=4096)] = None,
    signature: Annotated[str | None, Form(min_length=1, max_length=4096)] = None,
):
    _sync_runtime_globals()
    signed_vote_requested = any(
        value is not None and str(value).strip()
        for value in [authorization, wallet_address, message, signature]
    ) and not (voter and not authorization and not wallet_address and not message and not signature)

    if signed_vote_requested:
        try:
            verified_wallet = resolve_verified_wallet_from_authorization(
                authorization,
                manager=wallet_auth_manager,
            )
        except HTTPException as exc:
            raise HTTPException(status_code=401, detail=exc.detail) from exc

        if not message:
            raise HTTPException(status_code=400, detail="signed vote message is required.")
        if not signature:
            raise HTTPException(status_code=400, detail="signature is required.")

        submission = blockchain.get_submission(submission_id)
        if not submission:
            raise HTTPException(status_code=404, detail=f"Submission not found: {submission_id}")

        normalized_wallet = normalize_wallet_address(wallet_address or verified_wallet)
        if normalized_wallet is None or normalized_wallet != verified_wallet:
            raise HTTPException(status_code=403, detail="wallet_address must match the verified wallet session.")
        _enforce_access_for_feature(verified_wallet, feature="votes")
        _enforce_review_policy(verified_wallet, scope="voting")

        try:
            vote = blockchain.cast_signed_submission_vote_operation(
                submission_id=submission_id,
                voter=verified_wallet,
                vote_type=vote_type,
                message=message,
                signature=signature,
                auth_manager=wallet_auth_manager,
            )
        except ValueError as e:
            detail = str(e)
            status_code = 400
            if detail.startswith("Submission not found"):
                status_code = 404
            elif "expired" in detail.lower() or "already been used" in detail.lower():
                status_code = 401
            raise HTTPException(status_code=status_code, detail=detail) from e

    else:
        if not is_development():
            raise HTTPException(
                status_code=401,
                detail="MetaMask-signed votes are required outside development mode.",
            )
        if not voter:
            raise HTTPException(status_code=422, detail="voter is required for the development-only vote path.")
        if not is_valid_public_key(voter, blockchain.wallets):
            raise HTTPException(status_code=400, detail="Invalid voter public key.")

        try:
            vote = blockchain.cast_development_submission_vote_operation(
                submission_id=submission_id,
                voter=voter,
                vote_type=vote_type,
            )
        except ValueError as e:
            message_text = str(e)
            if message_text.startswith("Submission not found"):
                raise HTTPException(status_code=404, detail=message_text)
            raise HTTPException(status_code=400, detail=message_text)

    broadcast_result = broadcast_vote_to_peers(
        vote=vote,
        peer_store=peer_store,
        origin_node_id=NODE_ID,
        network_name=NETWORK_NAME,
    )
    return {
        "message": "Vote recorded successfully.",
        "vote": vote,
        "broadcast": broadcast_result,
    }


@router.get('/submissions/{submission_id}/votes')
@api_limit("public_read")
async def get_submission_votes(request: Request, submission_id: str):
    _sync_runtime_globals()
    try:
        return blockchain.get_submission_votes(submission_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post('/submissions/{submission_id}/evaluate')
@api_limit("evaluate")
async def evaluate_submission(
    request: Request,
    submission_id: str,
    automated_originality_passed: bool | None = Form(None),
):
    _sync_runtime_globals()
    try:
        evaluation, evaluated_submission, certificate = blockchain.evaluate_submission_operation(
            submission_id,
            automated_originality_passed=automated_originality_passed,
        )
        logging.debug(
            "evaluate_submission certificate lifecycle: submission_id=%s votes_cast=%s "
            "approval_percentage=%s decision=%s certificate_creation_attempted=%s "
            "certificate_id=%s certificate_lookup_after_save=%s",
            submission_id,
            evaluation.get("votes_cast"),
            evaluation.get("approval_percentage"),
            evaluation.get("reason"),
            evaluation.get("reason") == "approved_by_vote",
            certificate.certificate_id if certificate else None,
            certificate is not None,
        )
        certificate_broadcast = (
            broadcast_certificate_to_peers(
                certificate=certificate,
                peer_store=peer_store,
                origin_node_id=NODE_ID,
                network_name=NETWORK_NAME,
            )
            if certificate
            else {"attempted": 0, "succeeded": 0, "failed": 0, "results": []}
        )
    except ValueError as e:
        message = str(e)
        if message.startswith("Submission not found"):
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=400, detail=message)

    return {
        "message": "Submission evaluated successfully.",
        "evaluation": evaluation,
        "submission": _serialize_submission(evaluated_submission),
        "certificate": _serialize_certificate(certificate) if certificate else None,
        "voter_reward_summary": blockchain.get_submission_voter_reward_summary(submission_id),
        "certificate_broadcast": certificate_broadcast,
    }


@router.get('/active-users')
@api_limit("public_read")
async def active_users(request: Request):
    _sync_runtime_globals()
    return {
        "active_users": blockchain.get_active_users(),
        "lookback_days": ACTIVE_USER_LOOKBACK_DAYS,
    }


@router.get('/voting-threshold')
@api_limit("public_read")
async def voting_threshold(request: Request):
    _sync_runtime_globals()
    return blockchain.get_voting_threshold()


@router.get('/mint-queue')
@api_limit("public_read")
async def mint_queue(
    request: Request,
    include_blocked: bool = Query(True),
    mintable_only: bool = Query(False),
):
    _sync_runtime_globals()
    return {"mint_queue": blockchain.get_mint_queue_operation(include_blocked=include_blocked, mintable_only=mintable_only)}


@router.post('/mint-queue/{submission_id}/mint')
@api_limit("mint")
async def mint_queued_submission(
    request: Request,
    submission_id: str,
    miner: str | None = Form(None),
):
    _sync_runtime_globals()
    try:
        minted, submission, latest_block, certificate = blockchain.mint_submission_operation(submission_id, miner=miner)
    except ValueError as e:
        message = str(e)
        if message.startswith("Submission not found"):
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=400, detail=message)

    broadcast_result = (
        broadcast_block_to_peers(
            block=latest_block,
            peer_store=peer_store,
            origin_node_id=NODE_ID,
            network_name=NETWORK_NAME,
            related_submission_id=submission_id,
            certificate=certificate,
        )
        if minted
        else {"attempted": 0, "succeeded": 0, "failed": 0, "results": []}
    )

    return {
        "message": "Meme block minted with native ZOID transactions.",
        "minted": minted,
        "submission": _serialize_submission(submission),
        "block": _serialize_block(latest_block),
        "block_hash": latest_block.hash,
        "block_height": latest_block.index,
        "reward_recipient": latest_block.reward_recipient,
        "reward_amount": latest_block.reward_amount,
        "reward_type": latest_block.reward_type,
        "voter_reward_summary": blockchain.get_submission_voter_reward_summary(submission_id),
        "transactions_included": getattr(latest_block, "transaction_count", 0) or 0,
        "transaction_ids": list(getattr(latest_block, "transaction_ids", []) or []),
        "broadcast": broadcast_result,
    }


@router.post('/mint/{submission_id}', name="mint_queued_submission")
@api_limit("mint")
async def _mint_queued_submission_legacy(
    request: Request,
    submission_id: str,
    miner: str | None = Form(None),
):
    _sync_runtime_globals()
    return await mint_queued_submission.__wrapped__(request=request, submission_id=submission_id, miner=miner)


@router.post('/submissions/{submission_id}/block-minting')
@api_limit("dev_endpoint")
async def block_submission_minting(
    request: Request,
    submission_id: str,
    payload: MintBlockRequest,
    role: str = Depends(require_mint_queue_management_access),
):
    _sync_runtime_globals()
    try:
        submission = blockchain.block_submission_minting_operation(
            submission_id,
            reason=payload.reason,
            notes=payload.notes,
            blocked_by=role,
        )
    except ValueError as exc:
        message = str(exc)
        if message.startswith("Submission not found"):
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc

    return {
        "message": "Submission minting blocked successfully.",
        "submission": _serialize_submission(submission),
    }


@router.post('/submissions/{submission_id}/unblock-minting')
@api_limit("dev_endpoint")
async def unblock_submission_minting(
    request: Request,
    submission_id: str,
    role: str = Depends(require_mint_queue_management_access),
):
    _sync_runtime_globals()
    try:
        submission = blockchain.unblock_submission_minting_operation(submission_id)
    except ValueError as exc:
        message = str(exc)
        if message.startswith("Submission not found"):
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc

    return {
        "message": "Submission minting unblocked successfully.",
        "submission": _serialize_submission(submission),
    }


ROUTES = (
    (78, 'post', '/content/upload', 'upload_content', {}),
    (79, 'post', '/content/text', 'upload_text_content', {}),
    (80, 'get', '/content/{content_hash}/metadata', 'get_content_metadata', {}),
    (82, 'get', '/content/{content_hash}', 'download_content', {}),
    (85, 'post', '/submit_content', 'submit_content', {}),
    (86, 'get', '/submissions', 'get_submissions', {}),
    (87, 'get', '/submissions/{submission_id}', 'get_submission', {}),
    (88, 'get', '/submissions/{submission_id}/certificate', 'get_submission_certificate', {}),
    (89, 'get', '/submissions/{submission_id}/voter-rewards', 'get_submission_voter_rewards', {}),
    (90, 'get', '/certificates/{certificate_id}', 'get_certificate', {}),
    (94, 'post', '/submissions/{submission_id}/vote', 'vote_on_submission', {}),
    (95, 'get', '/submissions/{submission_id}/votes', 'get_submission_votes', {}),
    (97, 'post', '/submissions/{submission_id}/evaluate', 'evaluate_submission', {}),
    (121, 'get', '/active-users', 'active_users', {}),
    (122, 'get', '/voting-threshold', 'voting_threshold', {}),
    (123, 'get', '/mint-queue', 'mint_queue', {}),
    (124, 'post', '/mint-queue/{submission_id}/mint', 'mint_queued_submission', {}),
    (125, 'post', '/mint/{submission_id}', 'mint_queued_submission', {}),
    (126, 'post', '/submissions/{submission_id}/block-minting', 'block_submission_minting', {}),
    (127, 'post', '/submissions/{submission_id}/unblock-minting', 'unblock_submission_minting', {}),
)

EXPLICIT_ROUTER = True

_ROUTE_ORDER = {
    ('POST', '/content/upload', 'upload_content'): 78,
    ('POST', '/content/text', 'upload_text_content'): 79,
    ('GET', '/content/{content_hash}/metadata', 'get_content_metadata'): 80,
    ('GET', '/content/{content_hash}', 'download_content'): 82,
    ('POST', '/submit_content', 'submit_content'): 85,
    ('GET', '/submissions', 'get_submissions'): 86,
    ('GET', '/submissions/{submission_id}', 'get_submission'): 87,
    ('GET', '/submissions/{submission_id}/certificate', 'get_submission_certificate'): 88,
    ('GET', '/submissions/{submission_id}/voter-rewards', 'get_submission_voter_rewards'): 89,
    ('GET', '/certificates/{certificate_id}', 'get_certificate'): 90,
    ('POST', '/submissions/{submission_id}/vote', 'vote_on_submission'): 94,
    ('GET', '/submissions/{submission_id}/votes', 'get_submission_votes'): 95,
    ('POST', '/submissions/{submission_id}/evaluate', 'evaluate_submission'): 97,
    ('GET', '/active-users', 'active_users'): 121,
    ('GET', '/voting-threshold', 'voting_threshold'): 122,
    ('GET', '/mint-queue', 'mint_queue'): 123,
    ('POST', '/mint-queue/{submission_id}/mint', 'mint_queued_submission'): 124,
    ('POST', '/mint/{submission_id}', 'mint_queued_submission'): 125,
    ('POST', '/submissions/{submission_id}/block-minting', 'block_submission_minting'): 126,
    ('POST', '/submissions/{submission_id}/unblock-minting', 'unblock_submission_minting'): 127,
}

for _route in router.routes:
    _method = next(iter(_route.methods))
    _route.endpoint.__route_order__ = _ROUTE_ORDER[(_method, _route.path, _route.name)]
