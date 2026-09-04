"""Admin API HTTP adapters."""

from fastapi import APIRouter

import api_runtime as _runtime
from api_runtime import *  # noqa: F401,F403 - shared API wiring and schemas

_ROUTER_RUNTIME_GENERATION = _runtime._ROUTER_RUNTIME_GENERATION
router = APIRouter()


def _sync_runtime_globals():
    """Refresh compatibility globals so existing api monkeypatches remain effective."""
    globals().update({name: value for name, value in vars(_runtime).items() if not name.startswith("__")})

@router.post('/admin/login')
@api_limit("admin_login")
async def admin_login(request: Request, response: Response, payload: AdminLoginRequest):
    _sync_runtime_globals()
    _require_admin_ui_enabled()
    if _admin_auth_disabled_for_local_dev():
        return {
            "message": "Admin auth is disabled for local development.",
            **_admin_session_status_payload(authenticated=True, reason="development_admin_auth_disabled"),
        }
    if not _admin_auth_configured():
        raise HTTPException(status_code=503, detail="Admin auth is not configured on this node.")
    if not verify_admin_credential(
        payload.password,
        password_hash=ADMIN_PASSWORD_HASH,
        bootstrap_token=ADMIN_BOOTSTRAP_TOKEN,
    ):
        client_host = request.client.host if request.client else "unknown"
        logger.warning("Failed admin login attempt from %s", client_host)
        blockchain.record_admin_login_failure_operation(
            audit_context=_access_admin_audit_context(request),
        )
        raise HTTPException(status_code=401, detail="Invalid admin credential.")

    session_payload = admin_session_manager.issue_session()
    _set_admin_session_cookie(
        response,
        request=request,
        token=session_payload["admin_session_token"],
        expires_at=session_payload["expires_at"],
    )
    session = admin_session_manager.get_session(session_payload["admin_session_token"])
    blockchain.record_admin_login_success_operation(
        audit_context=_access_admin_audit_context(request, session),
    )
    return {
        "message": "Admin session started.",
        **_admin_session_status_payload(authenticated=True, session=session),
    }


@router.post('/admin/logout')
@api_limit("public_read")
async def admin_logout(
    request: Request,
    response: Response,
    x_zoid_admin_session: str | None = Header(default=None, alias="X-ZOID-Admin-Session"),
):
    _sync_runtime_globals()
    _require_admin_ui_enabled()
    token = _get_admin_session_token(request, x_zoid_admin_session)
    session = None
    if token:
        try:
            session = admin_session_manager.get_session(token)
        except ValueError:
            session = None
    if token:
        admin_session_manager.revoke_session(token)
    if session is not None:
        blockchain.record_admin_logout_operation(
            audit_context=_access_admin_audit_context(request, session),
        )
    _clear_admin_session_cookie(response, request=request)
    return {
        "message": "Admin session ended.",
        **_admin_session_status_payload(authenticated=False, reason="logged_out"),
    }


@router.get('/admin/session')
@api_limit("public_read")
async def admin_session_status(
    request: Request,
    x_zoid_admin_session: str | None = Header(default=None, alias="X-ZOID-Admin-Session"),
):
    _sync_runtime_globals()
    _require_admin_ui_enabled()
    if _admin_auth_disabled_for_local_dev():
        return _admin_session_status_payload(
            authenticated=True,
            reason="development_admin_auth_disabled",
        )
    if not _admin_auth_configured():
        return _admin_session_status_payload(
            authenticated=False,
            reason="admin_auth_not_configured",
        )

    token = _get_admin_session_token(request, x_zoid_admin_session)
    if not token:
        return _admin_session_status_payload(
            authenticated=False,
            reason="not_authenticated",
        )

    try:
        session = admin_session_manager.get_session(token)
    except ValueError:
        return _admin_session_status_payload(
            authenticated=False,
            reason="invalid_or_expired_session",
        )
    return _admin_session_status_payload(authenticated=True, session=session)


@router.get('/admin/access/requests')
@api_limit("public_read")
async def admin_list_access_requests(
    request: Request,
    status: str | None = Query(default=None),
    _admin_session=Depends(_require_admin_session),
):
    _sync_runtime_globals()
    _refresh_access_control_read_state()
    return {
        "requests": [
            _admin_access_request(item)
            for item in blockchain.list_access_requests(status=status.strip() if isinstance(status, str) and status.strip() else None)
        ],
    }


@router.post('/admin/access/requests/{request_id}/approve')
@api_limit("wallet_create")
async def admin_approve_access_request(
    request: Request,
    request_id: str,
    payload: AdminApproveAccessRequest,
    _admin_session=Depends(_require_admin_session),
):
    _sync_runtime_globals()
    try:
        access_account, invite_code, request_record = blockchain.approve_access_request_operation(
            request_id,
            reviewed_by=payload.reviewed_by,
            operator_notes=payload.operator_notes,
            max_wallets=payload.max_wallets,
            audit_context=_access_admin_audit_context(request, _admin_session),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": "Access request approved.",
        "warning": "Invite codes are shown once. Copy before leaving this screen.",
        "invite_code": invite_code,
        "access_account": _admin_access_account(access_account),
        "request": _admin_access_request(request_record),
    }


@router.post('/admin/access/requests/{request_id}/reject')
@api_limit("wallet_create")
async def admin_reject_access_request(
    request: Request,
    request_id: str,
    payload: AdminRejectAccessRequest,
    _admin_session=Depends(_require_admin_session),
):
    _sync_runtime_globals()
    try:
        request_record = blockchain.reject_access_request_operation(
            request_id,
            reviewed_by=payload.reviewed_by,
            operator_notes=payload.operator_notes,
            audit_context=_access_admin_audit_context(request, _admin_session),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": "Access request rejected.",
        "request": _admin_access_request(request_record),
    }


@router.post('/admin/access/invites')
@api_limit("wallet_create")
async def admin_create_access_invite(
    request: Request,
    payload: AdminCreateInviteRequest,
    _admin_session=Depends(_require_admin_session),
):
    _sync_runtime_globals()
    try:
        access_account, invite_code = blockchain.create_access_invite_operation(
            name=payload.name,
            email=payload.email,
            handle=payload.handle,
            notes=payload.notes,
            reviewed_by=payload.reviewed_by,
            operator_notes=payload.operator_notes,
            max_wallets=payload.max_wallets,
            audit_context=_access_admin_audit_context(request, _admin_session),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": "Access invite created.",
        "warning": "Invite codes are shown once. Copy before leaving this screen.",
        "invite_code": invite_code,
        "access_account": _admin_access_account(access_account),
    }


@router.get('/admin/access/accounts')
@api_limit("public_read")
async def admin_list_access_accounts(
    request: Request,
    status: str | None = Query(default=None),
    _admin_session=Depends(_require_admin_session),
):
    _sync_runtime_globals()
    _refresh_access_control_read_state()
    return {
        "accounts": [
            _admin_access_account(item)
            for item in blockchain.list_access_accounts(status=status.strip() if isinstance(status, str) and status.strip() else None)
        ],
    }


@router.get('/admin/access/accounts/{access_account_id}')
@api_limit("public_read")
async def admin_get_access_account(
    request: Request,
    access_account_id: str,
    _admin_session=Depends(_require_admin_session),
):
    _sync_runtime_globals()
    _refresh_access_control_read_state()
    access_account = blockchain.get_access_account(access_account_id)
    if access_account is None:
        raise HTTPException(status_code=404, detail=f"Access account not found: {access_account_id}")
    return {
        "access_account": _admin_access_account(access_account),
        "wallet_bindings": [
            _admin_wallet_binding(binding)
            for binding in blockchain.list_wallet_bindings(access_account_id=access_account_id)
        ],
    }


@router.get('/admin/allowlist')
@api_limit("public_read")
async def admin_list_allowlist(
    request: Request,
    scope: str | None = Query(default=None),
    subject_type: str | None = Query(default=None),
    subject_value: str | None = Query(default=None),
    status: str | None = Query(default=None),
    _admin_session=Depends(_require_admin_session),
):
    _sync_runtime_globals()
    _refresh_access_control_read_state()
    return {
        "allowlist_entries": [
            _admin_allowlist_entry(entry)
            for entry in blockchain.list_allowlist_entries(
                scope=scope,
                subject_type=subject_type,
                subject_value=subject_value,
                status=status,
            )
        ],
    }


@router.post('/admin/allowlist')
@api_limit("wallet_create")
async def admin_create_allowlist_entry(
    request: Request,
    payload: AdminAllowlistCreateRequest,
    _admin_session=Depends(_require_admin_session),
):
    _sync_runtime_globals()
    try:
        entry = blockchain.create_allowlist_entry_operation(
            scope=payload.scope,
            subject_type=payload.subject_type,
            subject_value=payload.subject_value,
            reason=payload.reason,
            expires_at=payload.expires_at,
            created_by=_safe_session_identifier(_admin_session),
            audit_context=_access_admin_audit_context(request, _admin_session),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": "Allowlist entry created.",
        "allowlist_entry": _admin_allowlist_entry(entry),
    }


@router.get('/admin/allowlist/{allowlist_entry_id}')
@api_limit("public_read")
async def admin_get_allowlist_entry(
    request: Request,
    allowlist_entry_id: str,
    _admin_session=Depends(_require_admin_session),
):
    _sync_runtime_globals()
    _refresh_access_control_read_state()
    entry = blockchain.get_allowlist_entry(allowlist_entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Allowlist entry not found: {allowlist_entry_id}")
    return {
        "allowlist_entry": _admin_allowlist_entry(entry),
    }


@router.patch('/admin/allowlist/{allowlist_entry_id}')
@api_limit("wallet_create")
async def admin_update_allowlist_entry(
    request: Request,
    allowlist_entry_id: str,
    payload: AdminAllowlistUpdateRequest,
    _admin_session=Depends(_require_admin_session),
):
    _sync_runtime_globals()
    try:
        entry = blockchain.update_allowlist_entry_operation(
            allowlist_entry_id,
            scope=payload.scope,
            subject_type=payload.subject_type,
            subject_value=payload.subject_value,
            reason=payload.reason,
            expires_at=payload.expires_at,
            status=payload.status,
            audit_context=_access_admin_audit_context(request, _admin_session),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": "Allowlist entry updated.",
        "allowlist_entry": _admin_allowlist_entry(entry),
    }


@router.post('/admin/allowlist/{allowlist_entry_id}/revoke')
@api_limit("wallet_create")
async def admin_revoke_allowlist_entry(
    request: Request,
    allowlist_entry_id: str,
    payload: AdminAllowlistRevokeRequest,
    _admin_session=Depends(_require_admin_session),
):
    _sync_runtime_globals()
    try:
        entry = blockchain.revoke_allowlist_entry_operation(
            allowlist_entry_id,
            revoked_reason=payload.revoked_reason,
            audit_context=_access_admin_audit_context(request, _admin_session),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": "Allowlist entry revoked.",
        "allowlist_entry": _admin_allowlist_entry(entry),
    }


@router.post('/admin/allowlist/{allowlist_entry_id}/reactivate')
@api_limit("wallet_create")
async def admin_reactivate_allowlist_entry(
    request: Request,
    allowlist_entry_id: str,
    payload: AdminAllowlistReactivateRequest,
    _admin_session=Depends(_require_admin_session),
):
    _sync_runtime_globals()
    try:
        entry = blockchain.reactivate_allowlist_entry_operation(
            allowlist_entry_id,
            reason=payload.reason,
            audit_context=_access_admin_audit_context(request, _admin_session),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": "Allowlist entry reactivated.",
        "allowlist_entry": _admin_allowlist_entry(entry),
    }


@router.get('/admin/override-requests')
@api_limit("public_read")
async def admin_list_override_requests(
    request: Request,
    status: str | None = Query(default=None),
    requested_scope: str | None = Query(default=None),
    _admin_session=Depends(_require_admin_session),
):
    _sync_runtime_globals()
    _refresh_access_control_read_state()
    return {
        "override_requests": [
            _admin_override_request(record)
            for record in blockchain.list_override_requests(
                status=status,
                requested_scope=requested_scope,
            )
        ],
    }


@router.post('/admin/override-requests/{override_request_id}/approve')
@api_limit("wallet_create")
async def admin_approve_override_request(
    request: Request,
    override_request_id: str,
    payload: AdminOverrideRequestDecision,
    _admin_session=Depends(_require_admin_session),
):
    _sync_runtime_globals()
    try:
        override_request, entry = blockchain.approve_override_request_operation(
            override_request_id,
            reviewed_by=payload.reviewed_by,
            admin_note=payload.admin_note,
            created_by=_safe_session_identifier(_admin_session),
            resolved_scope=payload.resolved_scope,
            audit_context=_access_admin_audit_context(request, _admin_session),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": "Override request approved and allowlist entry created.",
        "override_request": _admin_override_request(override_request),
        "allowlist_entry": _admin_allowlist_entry(entry),
    }


@router.post('/admin/override-requests/{override_request_id}/reject')
@api_limit("wallet_create")
async def admin_reject_override_request(
    request: Request,
    override_request_id: str,
    payload: AdminOverrideRequestDecision,
    _admin_session=Depends(_require_admin_session),
):
    _sync_runtime_globals()
    try:
        override_request = blockchain.reject_override_request_operation(
            override_request_id,
            reviewed_by=payload.reviewed_by,
            admin_note=payload.admin_note,
            resolved_scope=payload.resolved_scope,
            audit_context=_access_admin_audit_context(request, _admin_session),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": "Override request rejected.",
        "override_request": _admin_override_request(override_request),
    }


@router.get('/admin/feedback')
@api_limit("public_read")
async def admin_list_feedback(
    request: Request,
    status: str | None = Query(default=None),
    feedback_type: str | None = Query(default=None, alias="type"),
    priority: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _admin_session=Depends(_require_admin_session),
):
    _sync_runtime_globals()
    _refresh_access_control_read_state()
    try:
        records = blockchain.list_feedback(
            status=status,
            feedback_type=feedback_type,
            priority=priority,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "summary": blockchain.feedback_summary(),
        "feedback_items": [_admin_feedback(record) for record in records],
    }


@router.get('/admin/feedback/{feedback_id}')
@api_limit("public_read")
async def admin_get_feedback(
    request: Request,
    feedback_id: str,
    _admin_session=Depends(_require_admin_session),
):
    _sync_runtime_globals()
    try:
        record = blockchain.get_feedback_for_admin_operation(
            feedback_id,
            audit_context=_access_admin_audit_context(request, _admin_session),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "feedback": _admin_feedback(record),
    }


@router.patch('/admin/feedback/{feedback_id}')
@api_limit("wallet_create")
async def admin_update_feedback(
    request: Request,
    feedback_id: str,
    payload: AdminFeedbackUpdateRequest,
    _admin_session=Depends(_require_admin_session),
):
    _sync_runtime_globals()
    try:
        record, _note = blockchain.update_feedback_operation(
            feedback_id,
            status=payload.status,
            priority=payload.priority,
            reviewed_by=payload.reviewed_by,
            admin_note=payload.admin_note,
            audit_context=_access_admin_audit_context(request, _admin_session),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "message": "Feedback updated.",
        "feedback": _admin_feedback(record),
    }


@router.post('/admin/feedback/{feedback_id}/status')
@api_limit("wallet_create")
async def admin_update_feedback_status(
    request: Request,
    feedback_id: str,
    payload: AdminFeedbackStatusRequest,
    _admin_session=Depends(_require_admin_session),
):
    _sync_runtime_globals()
    try:
        record, _note = blockchain.update_feedback_status_operation(
            feedback_id,
            status=payload.status,
            reviewed_by=payload.reviewed_by,
            audit_context=_access_admin_audit_context(request, _admin_session),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": "Feedback status updated.",
        "feedback": _admin_feedback(record),
    }


@router.post('/admin/feedback/{feedback_id}/note')
@api_limit("wallet_create")
async def admin_add_feedback_note(
    request: Request,
    feedback_id: str,
    payload: AdminFeedbackNoteRequest,
    _admin_session=Depends(_require_admin_session),
):
    _sync_runtime_globals()
    try:
        record, note = blockchain.add_feedback_note_operation(
            feedback_id,
            note=payload.note,
            created_by=payload.created_by,
            audit_context=_access_admin_audit_context(request, _admin_session),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": "Feedback note added.",
        "feedback": _admin_feedback(record),
        "note": note,
    }


@router.get('/admin/ops/status')
@api_limit("public_read")
async def admin_ops_status(
    request: Request,
    _admin_session=Depends(_require_admin_session),
):
    _sync_runtime_globals()
    payload = _admin_ops_status_payload()
    blockchain.record_admin_ops_view_operation(
        audit_context=_access_admin_audit_context(request, _admin_session),
    )
    return payload


@router.get('/admin/audit-log')
@api_limit("public_read")
async def admin_audit_log(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    action: str | None = Query(default=None),
    since: str | None = Query(default=None),
    before: str | None = Query(default=None),
    _admin_session=Depends(_require_admin_session),
):
    _sync_runtime_globals()
    return {
        "audit_log": [
            _admin_audit_entry(entry)
            for entry in blockchain.list_audit_log_entries(
                limit=limit,
                action=action,
                since=since,
                before=before,
            )
        ],
    }


@router.post('/admin/access/accounts/{access_account_id}/suspend')
@api_limit("wallet_create")
async def admin_suspend_access_account(
    request: Request,
    access_account_id: str,
    _admin_session=Depends(_require_admin_session),
):
    _sync_runtime_globals()
    return await _admin_update_access_account_status(
        request=request,
        access_account_id=access_account_id,
        status="suspended",
        session=_admin_session,
    )


@router.post('/admin/access/accounts/{access_account_id}/reactivate')
@api_limit("wallet_create")
async def admin_reactivate_access_account(
    request: Request,
    access_account_id: str,
    _admin_session=Depends(_require_admin_session),
):
    _sync_runtime_globals()
    return await _admin_update_access_account_status(
        request=request,
        access_account_id=access_account_id,
        status="active",
        session=_admin_session,
    )


@router.post('/admin/access/accounts/{access_account_id}/revoke')
@api_limit("wallet_create")
async def admin_revoke_access_account(
    request: Request,
    access_account_id: str,
    _admin_session=Depends(_require_admin_session),
):
    _sync_runtime_globals()
    return await _admin_update_access_account_status(
        request=request,
        access_account_id=access_account_id,
        status="revoked",
        session=_admin_session,
    )


@router.post('/admin/access/wallet-bindings/{wallet_address}/revoke')
@api_limit("wallet_create")
async def admin_revoke_wallet_binding(
    request: Request,
    wallet_address: str,
    _admin_session=Depends(_require_admin_session),
):
    _sync_runtime_globals()
    try:
        binding = blockchain.revoke_wallet_binding_operation(
            wallet_address,
            revoked_by="admin",
            audit_context=_access_admin_audit_context(request, _admin_session),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": "Wallet binding revoked.",
        "wallet_binding": _admin_wallet_binding(binding),
    }


async def _admin_update_access_account_status(
    *,
    request: Request,
    access_account_id: str,
    status: str,
    session=None,
):
    _sync_runtime_globals()
    try:
        access_account = blockchain.update_access_account_status_operation(
            access_account_id,
            status,
            updated_by="admin",
            audit_context=_access_admin_audit_context(request, session),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": f"Access account {status}.",
        "access_account": _admin_access_account(access_account),
    }


ROUTES = (
    (19, 'post', '/admin/login', 'admin_login', {}),
    (20, 'post', '/admin/logout', 'admin_logout', {}),
    (21, 'get', '/admin/session', 'admin_session_status', {}),
    (22, 'get', '/admin/access/requests', 'admin_list_access_requests', {}),
    (23, 'post', '/admin/access/requests/{request_id}/approve', 'admin_approve_access_request', {}),
    (24, 'post', '/admin/access/requests/{request_id}/reject', 'admin_reject_access_request', {}),
    (25, 'post', '/admin/access/invites', 'admin_create_access_invite', {}),
    (26, 'get', '/admin/access/accounts', 'admin_list_access_accounts', {}),
    (27, 'get', '/admin/access/accounts/{access_account_id}', 'admin_get_access_account', {}),
    (28, 'get', '/admin/allowlist', 'admin_list_allowlist', {}),
    (29, 'post', '/admin/allowlist', 'admin_create_allowlist_entry', {}),
    (30, 'get', '/admin/allowlist/{allowlist_entry_id}', 'admin_get_allowlist_entry', {}),
    (31, 'patch', '/admin/allowlist/{allowlist_entry_id}', 'admin_update_allowlist_entry', {}),
    (32, 'post', '/admin/allowlist/{allowlist_entry_id}/revoke', 'admin_revoke_allowlist_entry', {}),
    (33, 'post', '/admin/allowlist/{allowlist_entry_id}/reactivate', 'admin_reactivate_allowlist_entry', {}),
    (34, 'get', '/admin/override-requests', 'admin_list_override_requests', {}),
    (35, 'post', '/admin/override-requests/{override_request_id}/approve', 'admin_approve_override_request', {}),
    (36, 'post', '/admin/override-requests/{override_request_id}/reject', 'admin_reject_override_request', {}),
    (37, 'get', '/admin/feedback', 'admin_list_feedback', {}),
    (38, 'get', '/admin/feedback/{feedback_id}', 'admin_get_feedback', {}),
    (39, 'patch', '/admin/feedback/{feedback_id}', 'admin_update_feedback', {}),
    (40, 'post', '/admin/feedback/{feedback_id}/status', 'admin_update_feedback_status', {}),
    (41, 'post', '/admin/feedback/{feedback_id}/note', 'admin_add_feedback_note', {}),
    (42, 'get', '/admin/ops/status', 'admin_ops_status', {}),
    (43, 'get', '/admin/audit-log', 'admin_audit_log', {}),
    (44, 'post', '/admin/access/accounts/{access_account_id}/suspend', 'admin_suspend_access_account', {}),
    (45, 'post', '/admin/access/accounts/{access_account_id}/reactivate', 'admin_reactivate_access_account', {}),
    (46, 'post', '/admin/access/accounts/{access_account_id}/revoke', 'admin_revoke_access_account', {}),
    (47, 'post', '/admin/access/wallet-bindings/{wallet_address}/revoke', 'admin_revoke_wallet_binding', {}),
)

EXPLICIT_ROUTER = True

_ROUTE_ORDER = {
    ('POST', '/admin/login', 'admin_login'): 19,
    ('POST', '/admin/logout', 'admin_logout'): 20,
    ('GET', '/admin/session', 'admin_session_status'): 21,
    ('GET', '/admin/access/requests', 'admin_list_access_requests'): 22,
    ('POST', '/admin/access/requests/{request_id}/approve', 'admin_approve_access_request'): 23,
    ('POST', '/admin/access/requests/{request_id}/reject', 'admin_reject_access_request'): 24,
    ('POST', '/admin/access/invites', 'admin_create_access_invite'): 25,
    ('GET', '/admin/access/accounts', 'admin_list_access_accounts'): 26,
    ('GET', '/admin/access/accounts/{access_account_id}', 'admin_get_access_account'): 27,
    ('GET', '/admin/allowlist', 'admin_list_allowlist'): 28,
    ('POST', '/admin/allowlist', 'admin_create_allowlist_entry'): 29,
    ('GET', '/admin/allowlist/{allowlist_entry_id}', 'admin_get_allowlist_entry'): 30,
    ('PATCH', '/admin/allowlist/{allowlist_entry_id}', 'admin_update_allowlist_entry'): 31,
    ('POST', '/admin/allowlist/{allowlist_entry_id}/revoke', 'admin_revoke_allowlist_entry'): 32,
    ('POST', '/admin/allowlist/{allowlist_entry_id}/reactivate', 'admin_reactivate_allowlist_entry'): 33,
    ('GET', '/admin/override-requests', 'admin_list_override_requests'): 34,
    ('POST', '/admin/override-requests/{override_request_id}/approve', 'admin_approve_override_request'): 35,
    ('POST', '/admin/override-requests/{override_request_id}/reject', 'admin_reject_override_request'): 36,
    ('GET', '/admin/feedback', 'admin_list_feedback'): 37,
    ('GET', '/admin/feedback/{feedback_id}', 'admin_get_feedback'): 38,
    ('PATCH', '/admin/feedback/{feedback_id}', 'admin_update_feedback'): 39,
    ('POST', '/admin/feedback/{feedback_id}/status', 'admin_update_feedback_status'): 40,
    ('POST', '/admin/feedback/{feedback_id}/note', 'admin_add_feedback_note'): 41,
    ('GET', '/admin/ops/status', 'admin_ops_status'): 42,
    ('GET', '/admin/audit-log', 'admin_audit_log'): 43,
    ('POST', '/admin/access/accounts/{access_account_id}/suspend', 'admin_suspend_access_account'): 44,
    ('POST', '/admin/access/accounts/{access_account_id}/reactivate', 'admin_reactivate_access_account'): 45,
    ('POST', '/admin/access/accounts/{access_account_id}/revoke', 'admin_revoke_access_account'): 46,
    ('POST', '/admin/access/wallet-bindings/{wallet_address}/revoke', 'admin_revoke_wallet_binding'): 47,
}

for _route in router.routes:
    _method = next(iter(_route.methods))
    _route.endpoint.__route_order__ = _ROUTE_ORDER[(_method, _route.path, _route.name)]
