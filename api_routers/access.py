"""Access API HTTP adapters."""

from fastapi import APIRouter

import api_runtime as _runtime
from api_runtime import *  # noqa: F401,F403 - shared API wiring and schemas

_ROUTER_RUNTIME_GENERATION = _runtime._ROUTER_RUNTIME_GENERATION
router = APIRouter()


def _sync_runtime_globals():
    """Refresh compatibility globals so existing api monkeypatches remain effective."""
    globals().update({name: value for name, value in vars(_runtime).items() if not name.startswith("__")})

@router.post('/feedback')
@api_limit("submission_create")
async def create_feedback(
    request: Request,
    payload: FeedbackCreateRequest,
    authorization: str | None = Header(default=None),
    x_zoid_access_session: str | None = Header(default=None, alias="X-ZOID-Access-Session"),
):
    _sync_runtime_globals()
    verified_wallet_address = None
    access_account = None

    if authorization:
        try:
            verified_wallet_address = resolve_verified_wallet_from_authorization(
                authorization,
                manager=wallet_auth_manager,
            )
            access_account = blockchain.get_access_account_for_wallet(verified_wallet_address)
        except HTTPException:
            verified_wallet_address = None

    if access_account is None and x_zoid_access_session:
        try:
            access_account = _resolve_access_account_from_session(x_zoid_access_session)
        except ValueError:
            access_account = None

    request_metadata = _safe_request_metadata(request)
    try:
        feedback = blockchain.submit_feedback_operation(
            feedback_type=payload.type,
            title=payload.title,
            description=payload.description,
            name=payload.name or (access_account.get("name") if access_account else None),
            email=payload.email or (access_account.get("email") if access_account else None),
            handle=payload.handle or (access_account.get("handle") if access_account else None),
            wallet_address=verified_wallet_address or payload.wallet_address,
            access_account_id=payload.access_account_id or (access_account.get("access_account_id") if access_account else None),
            current_page=payload.current_page,
            current_flow=payload.current_flow,
            user_agent=request_metadata["user_agent"],
            remote_ip=request_metadata["remote_ip"],
            browser_metadata=_sanitize_feedback_browser_metadata(payload.browser_metadata),
            eligibility_snapshot=_sanitize_feedback_eligibility_snapshot(payload.eligibility_snapshot),
            viewport_width=payload.viewport_width,
            viewport_height=payload.viewport_height,
            is_mobile=payload.is_mobile,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "message": "Feedback submitted. Thanks for helping test the controlled beta.",
        "feedback": _public_feedback(feedback),
    }


@router.get('/access/status')
@api_limit("public_read")
async def get_access_status(request: Request):
    _sync_runtime_globals()
    return public_access_status_payload()


@router.post('/access/request')
@api_limit("submission_create")
async def create_access_request(request: Request, payload: AccessRequestCreate):
    _sync_runtime_globals()
    if not ACCESS_REQUESTS_ENABLED:
        raise HTTPException(status_code=403, detail="Access requests are disabled on this node.")
    if ACCESS_CONTROL_MODE == "disabled":
        raise HTTPException(status_code=403, detail="Access control is disabled on this node.")
    try:
        access_request = blockchain.submit_access_request_operation(
            name=payload.name,
            email=payload.email,
            handle=payload.handle,
            reason=payload.reason,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": "Access request submitted.",
        "request": _public_access_request(access_request),
    }


@router.post('/access/login')
@api_limit("wallet_create")
async def login_with_access_code(request: Request, payload: AccessLoginRequest):
    _sync_runtime_globals()
    try:
        account, session = blockchain.complete_access_login_operation(
            payload.access_code,
            issue_session=access_session_manager.issue_session,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {
        "message": "Invite accepted. Connect and verify MetaMask to bind the wallet.",
        "access_account": _public_access_account(account),
        **session,
    }


@router.post('/access/bind-wallet')
@api_limit("wallet_create")
async def bind_access_wallet(
    request: Request,
    payload: AccessBindWalletRequest | None = None,
    access_session_token: str = Depends(_access_session_dependency),
    wallet_address: str = Depends(_verified_wallet_dependency),
):
    _sync_runtime_globals()
    try:
        access_account = _resolve_access_account_from_session(access_session_token)
        normalized_payload_wallet = normalize_wallet_address(payload.wallet_address) if payload and payload.wallet_address else None
        normalized_verified_wallet = normalize_wallet_address(wallet_address)
        if normalized_payload_wallet and normalized_payload_wallet != normalized_verified_wallet:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "verified_wallet_mismatch",
                    "reason": "verified_wallet_session_does_not_match_requested_wallet",
                    "message": "The verified MetaMask wallet session does not match the requested wallet binding.",
                },
            )
        binding, access_account = blockchain.bind_access_wallet_operation(
            access_account["access_account_id"],
            wallet_address,
            mark_wallet_bound=lambda address: access_session_manager.mark_wallet_bound(access_session_token, address),
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 400
        if "missing access session" in detail.lower() or "no active access session" in detail.lower() or "expired" in detail.lower():
            status_code = 401
        elif "already associated with a different verified wallet" in detail.lower():
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "access_session_wallet_mismatch",
                    "reason": "access_session_already_bound_to_different_wallet",
                    "message": detail,
                },
            ) from exc
        elif "already bound to a different access account" in detail.lower():
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "wallet_already_bound_elsewhere",
                    "reason": "wallet_is_already_bound_to_different_access_account",
                    "message": detail,
                },
            ) from exc
        elif "maximum number of bound wallets" in detail.lower():
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "wallet_limit_reached",
                    "reason": "access_account_already_has_maximum_wallets",
                    "message": detail,
                },
            ) from exc
        elif "not found" in detail.lower() or "not active" in detail.lower():
            status_code = 403
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return {
        "message": "Wallet bound to controlled-testnet access account.",
        "access_account": _public_access_account(access_account),
        "wallet_binding": _public_wallet_binding(binding),
        "access": _access_status_payload(
            wallet_address=wallet_address,
            access_account=access_account,
            binding=binding,
            session_access_account=access_account,
            invite_authenticated=True,
            wallet_session_authenticated=True,
        ),
    }


@router.get('/access/me')
@api_limit("public_read")
async def get_access_me(
    request: Request,
    authorization: str | None = Header(default=None),
    x_zoid_access_session: str | None = Header(default=None, alias="X-ZOID-Access-Session"),
):
    _sync_runtime_globals()
    _refresh_access_control_read_state()
    wallet_address = None
    access_account = None
    binding = None
    session_access_account = None
    wallet_session_authenticated = False
    invite_authenticated = False
    access_decision = None

    if authorization:
        try:
            wallet_address = resolve_verified_wallet_from_authorization(
                authorization,
                manager=wallet_auth_manager,
            )
            wallet_session_authenticated = True
            binding = blockchain.get_wallet_binding(wallet_address)
            access_account = blockchain.get_access_account_for_wallet(wallet_address)
            access_decision = access_decision_for_wallet(blockchain, wallet_address, feature="app")
        except HTTPException as exc:
            raise HTTPException(status_code=401, detail=exc.detail) from exc

    if x_zoid_access_session:
        try:
            session_access_account = _resolve_access_account_from_session(x_zoid_access_session)
            invite_authenticated = True
        except ValueError as exc:
            if not wallet_session_authenticated or access_account is None:
                raise HTTPException(status_code=401, detail=str(exc)) from exc

    return _access_status_payload(
        wallet_address=wallet_address,
        access_account=access_account,
        binding=binding,
        session_access_account=session_access_account,
        invite_authenticated=invite_authenticated,
        wallet_session_authenticated=wallet_session_authenticated,
        access_decision=access_decision,
    )


@router.get('/eligibility/status')
@api_limit("public_read")
async def get_eligibility_status(
    request: Request,
    authorization: str | None = Header(default=None),
    x_zoid_access_session: str | None = Header(default=None, alias="X-ZOID-Access-Session"),
):
    _sync_runtime_globals()
    wallet_address = None
    access_account = None
    binding = None
    session_access_account = None
    wallet_session_authenticated = False
    invite_authenticated = False
    access_decision = None

    if authorization:
        try:
            wallet_address = resolve_verified_wallet_from_authorization(
                authorization,
                manager=wallet_auth_manager,
            )
            wallet_session_authenticated = True
            binding = blockchain.get_wallet_binding(wallet_address)
            access_account = blockchain.get_access_account_for_wallet(wallet_address)
            access_decision = access_decision_for_wallet(blockchain, wallet_address, feature="app")
        except HTTPException as exc:
            raise HTTPException(status_code=401, detail=exc.detail) from exc

    if x_zoid_access_session:
        try:
            session_access_account = _resolve_access_account_from_session(x_zoid_access_session)
            invite_authenticated = True
        except ValueError as exc:
            if not wallet_session_authenticated or access_account is None:
                raise HTTPException(status_code=401, detail=str(exc)) from exc

    return _build_eligibility_status_payload(
        wallet_address=wallet_address,
        access_account=access_account,
        binding=binding,
        session_access_account=session_access_account,
        invite_authenticated=invite_authenticated,
        wallet_session_authenticated=wallet_session_authenticated,
        access_decision=access_decision,
    )


@router.post('/eligibility/override-requests')
@api_limit("submission_create")
async def create_override_request(
    request: Request,
    payload: OverrideRequestCreate,
    authorization: str | None = Header(default=None),
    x_zoid_access_session: str | None = Header(default=None, alias="X-ZOID-Access-Session"),
):
    _sync_runtime_globals()
    wallet_address = None
    access_account = None
    if authorization:
        try:
            wallet_address = resolve_verified_wallet_from_authorization(
                authorization,
                manager=wallet_auth_manager,
            )
            access_account = blockchain.get_access_account_for_wallet(wallet_address)
        except HTTPException:
            wallet_address = None
    if not access_account and x_zoid_access_session:
        try:
            access_account = _resolve_access_account_from_session(x_zoid_access_session)
        except ValueError:
            access_account = None

    try:
        override_request = blockchain.submit_override_request_operation(
            audit_context=_access_admin_audit_context(request),
            requested_scope=payload.requested_scope,
            name=payload.name,
            email=payload.email or (access_account.get("email") if access_account else None),
            handle=payload.handle or (access_account.get("handle") if access_account else None),
            wallet_address=payload.wallet_address or wallet_address,
            access_account_id=payload.access_account_id or (access_account.get("access_account_id") if access_account else None),
            reason=payload.reason,
            current_page=payload.current_page,
            detected_blocked_reason=payload.detected_blocked_reason,
            user_agent=(request.headers.get("user-agent") or ""),
            remote_ip=(request.client.host if request.client else ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "message": "Override request submitted.",
        "override_request": _public_override_request(override_request),
    }


@router.post('/auth/wallet/challenge')
@api_limit("wallet_create")
async def create_wallet_challenge(request: Request, payload: WalletChallengeRequest):
    _sync_runtime_globals()
    if not is_valid_ethereum_address(payload.wallet_address):
        raise HTTPException(status_code=400, detail="Invalid wallet address. Expected an Ethereum-style 0x address.")
    try:
        challenge = wallet_auth_manager.issue_challenge(payload.wallet_address)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return challenge


@router.post('/auth/wallet/verify')
@api_limit("wallet_create")
async def verify_wallet_challenge(request: Request, payload: WalletVerifyRequest):
    _sync_runtime_globals()
    if not is_valid_ethereum_address(payload.wallet_address):
        raise HTTPException(status_code=400, detail="Invalid wallet address. Expected an Ethereum-style 0x address.")
    normalized = normalize_wallet_address(payload.wallet_address)
    if normalized is None:
        raise HTTPException(status_code=400, detail="Invalid wallet address. Expected an Ethereum-style 0x address.")

    try:
        verification = wallet_auth_manager.verify_signature(
            payload.wallet_address,
            payload.message,
            payload.signature,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 400
        if "expired" in detail.lower() or "already been used" in detail.lower():
            status_code = 401
        raise HTTPException(status_code=status_code, detail=detail) from exc

    return verification


@router.post('/auth/wallet/submission-challenge')
@api_limit("submission_create")
async def create_wallet_submission_challenge(
    request: Request,
    payload: WalletSubmissionChallengeRequest,
    wallet_address: str = Depends(_verified_wallet_dependency),
):
    _sync_runtime_globals()
    normalized_wallet = normalize_wallet_address(payload.wallet_address)
    if normalized_wallet is None or normalized_wallet != wallet_address:
        raise HTTPException(status_code=403, detail="wallet_address must match the verified wallet session.")
    _enforce_submission_eligibility(wallet_address)

    content_object = _require_content_reference(payload.content_hash, payload.content_id)
    safe_caption = validate_caption(payload.caption)

    try:
        challenge = wallet_auth_manager.issue_submission_challenge(
            wallet_address=wallet_address,
            content_hash=content_object.content_hash,
            content_id=content_object.content_id,
            caption=safe_caption,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return challenge


@router.post('/auth/wallet/vote-challenge')
@api_limit("submission_create")
async def create_wallet_vote_challenge(
    request: Request,
    payload: WalletVoteChallengeRequest,
    wallet_address: str = Depends(_verified_wallet_dependency),
):
    _sync_runtime_globals()
    normalized_wallet = normalize_wallet_address(payload.wallet_address)
    if normalized_wallet is None or normalized_wallet != wallet_address:
        raise HTTPException(status_code=403, detail="wallet_address must match the verified wallet session.")
    _enforce_access_for_feature(wallet_address, feature="votes")

    submission = blockchain.get_submission(payload.submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail=f"Submission not found: {payload.submission_id}")
    if blockchain.is_submission_voting_locked(submission):
        raise HTTPException(status_code=400, detail="Finalized or certified submissions cannot receive votes.")
    if wallet_address == submission.submitter:
        raise HTTPException(status_code=400, detail="Submission creator cannot vote on their own submission.")
    if blockchain.storage.get_vote(payload.submission_id, wallet_address, blockchain.votes):
        raise HTTPException(status_code=400, detail="Wallet has already voted on this submission.")
    _enforce_review_policy(wallet_address, scope="voting")

    try:
        challenge = wallet_auth_manager.issue_vote_challenge(
            wallet_address=wallet_address,
            submission_id=payload.submission_id,
            content_hash=submission.content_hash or "",
            vote_type=payload.vote,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return challenge


@router.get('/review/policy')
@api_limit("public_read")
async def get_review_policy(
    request: Request,
    wallet_address: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
):
    _sync_runtime_globals()
    config = _current_review_policy_config()
    normalized_wallet = None

    if authorization:
        try:
            verified_wallet = resolve_verified_wallet_from_authorization(
                authorization,
                manager=wallet_auth_manager,
            )
        except HTTPException as exc:
            raise HTTPException(status_code=401, detail=exc.detail) from exc
        normalized_wallet = verified_wallet
        if wallet_address:
            requested_wallet = _normalize_native_account_address(wallet_address)
            if requested_wallet != verified_wallet:
                raise HTTPException(
                    status_code=403,
                    detail="wallet_address must match the verified wallet session.",
                )
    elif wallet_address:
        normalized_wallet = _normalize_native_account_address(wallet_address)

    eligibility = None
    if normalized_wallet:
        _, eligibility = _review_eligibility_for_wallet(normalized_wallet)
    return build_public_policy_summary(
        config,
        wallet_address=normalized_wallet,
        eligibility=eligibility,
    )


@router.post('/auth/wallet/transfer-challenge')
@api_limit("wallet_create")
async def create_wallet_transfer_challenge(
    request: Request,
    payload: WalletTransferChallengeRequest,
    wallet_address: str = Depends(_verified_wallet_dependency),
):
    _sync_runtime_globals()
    normalized_from = normalize_wallet_address(payload.from_address)
    if normalized_from is None or normalized_from != wallet_address:
        raise HTTPException(status_code=403, detail="from_address must match the verified wallet session.")
    _enforce_access_for_feature(wallet_address, feature="transfers")

    try:
        expected_nonce = blockchain.get_next_nonce(wallet_address)
        if payload.nonce is not None and int(payload.nonce) != expected_nonce:
            raise HTTPException(
                status_code=400,
                detail=f"nonce must match the expected next nonce {expected_nonce}.",
            )
        challenge = wallet_auth_manager.issue_transfer_challenge(
            from_address=wallet_address,
            to_address=payload.to_address,
            amount=payload.amount,
            fee=payload.fee,
            memo=payload.memo,
            nonce=str(expected_nonce),
        )
        balance_snapshot = blockchain.get_native_balance_snapshot(wallet_address)
        estimated_total = parse_native_zoid_amount(payload.amount, allow_zero=False)
        would_be_sufficient = Decimal(estimated_total) <= Decimal(balance_snapshot["available_balance"])
        challenge["available_balance"] = balance_snapshot["available_balance"]
        challenge["estimated_total"] = estimated_total
        challenge["would_be_sufficient_at_challenge_time"] = would_be_sufficient
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return challenge


@router.get('/auth/wallet/session')
@api_limit("public_read")
async def get_wallet_session(
    request: Request,
    authorization: str | None = Header(default=None),
    wallet_address: str = Depends(_verified_wallet_dependency),
):
    _sync_runtime_globals()
    token = (authorization or "")[len("Bearer "):].strip() if authorization else ""
    try:
        return wallet_auth_manager.session_payload(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post('/auth/wallet/logout')
@api_limit("public_read")
async def logout_wallet_session(request: Request, authorization: str | None = Header(default=None)):
    _sync_runtime_globals()
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer "):].strip()
    revoked = wallet_auth_manager.revoke_session(token)
    return {
        "logged_out": True,
        "revoked": revoked,
        "message": "Wallet session cleared.",
    }


EXPLICIT_ROUTER = True

_ROUTE_ORDER = {
    ('POST', '/feedback', 'create_feedback'): 11,
    ('GET', '/access/status', 'get_access_status'): 12,
    ('POST', '/access/request', 'create_access_request'): 13,
    ('POST', '/access/login', 'login_with_access_code'): 14,
    ('POST', '/access/bind-wallet', 'bind_access_wallet'): 15,
    ('GET', '/access/me', 'get_access_me'): 16,
    ('GET', '/eligibility/status', 'get_eligibility_status'): 17,
    ('POST', '/eligibility/override-requests', 'create_override_request'): 18,
    ('POST', '/auth/wallet/challenge', 'create_wallet_challenge'): 48,
    ('POST', '/auth/wallet/verify', 'verify_wallet_challenge'): 49,
    ('POST', '/auth/wallet/submission-challenge', 'create_wallet_submission_challenge'): 50,
    ('POST', '/auth/wallet/vote-challenge', 'create_wallet_vote_challenge'): 51,
    ('GET', '/review/policy', 'get_review_policy'): 52,
    ('POST', '/auth/wallet/transfer-challenge', 'create_wallet_transfer_challenge'): 53,
    ('GET', '/auth/wallet/session', 'get_wallet_session'): 54,
    ('POST', '/auth/wallet/logout', 'logout_wallet_session'): 55,
}

for _route in router.routes:
    _method = next(iter(_route.methods))
    _route.endpoint.__route_order__ = _ROUTE_ORDER[(_method, _route.path, _route.name)]
