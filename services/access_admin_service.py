"""Access, allowlist, override, and audit record transitions.

This module deliberately owns plain persisted records only. Authorization policy
and HTTP/session handling remain in their existing modules.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from access_control import (
    generate_access_code,
    hash_access_code,
    normalize_email,
    normalize_handle,
    normalize_text_field,
    utc_now_iso,
)
from wallet_auth import normalize_wallet_address


ALLOWLIST_SCOPES = {"access", "review", "submission", "voting", "rewards", "all_beta"}
ALLOWLIST_SUBJECT_TYPES = {"wallet", "access_account", "email", "handle"}
ALLOWLIST_STATUSES = {"active", "inactive", "revoked"}
OVERRIDE_REQUEST_STATUSES = {"pending", "approved", "rejected", "duplicate", "spam"}


@dataclass
class AccessAdminState:
    access_requests: list
    access_accounts: list
    wallet_bindings: list
    allowlist_entries: list
    override_requests: list
    audit_logs: list


class AccessAdminService:
    """Stateless transitions over caller-owned persisted record collections."""

    @staticmethod
    def refresh_from_storage(load_state):
        try:
            loaded_data = load_state()
        except Exception as exc:
            print(f"Debug: Failed to refresh access control state from storage - {exc}")
            return None
        return loaded_data if isinstance(loaded_data, dict) else None

    @staticmethod
    def normalize_access_wallet(wallet_address):
        return normalize_wallet_address(wallet_address or "")

    @staticmethod
    def normalize_allowlist_scope(scope):
        normalized_scope = str(scope or "").strip().lower()
        if normalized_scope not in ALLOWLIST_SCOPES:
            raise ValueError("Allowlist scope must be access, review, submission, voting, rewards, or all_beta.")
        return normalized_scope

    @staticmethod
    def normalize_allowlist_status(status):
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in ALLOWLIST_STATUSES:
            raise ValueError("Allowlist status must be active, inactive, or revoked.")
        return normalized_status

    @staticmethod
    def normalize_override_request_status(status):
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in OVERRIDE_REQUEST_STATUSES:
            raise ValueError("Override request status must be pending, approved, rejected, duplicate, or spam.")
        return normalized_status

    @staticmethod
    def normalize_allowlist_subject(subject_type, subject_value):
        normalized_subject_type = str(subject_type or "").strip().lower()
        if normalized_subject_type not in ALLOWLIST_SUBJECT_TYPES:
            raise ValueError("Allowlist subject_type must be wallet, access_account, email, or handle.")
        if normalized_subject_type == "wallet":
            normalized_subject_value = normalize_wallet_address(subject_value or "")
            if normalized_subject_value is None:
                raise ValueError("Allowlist wallet subject_value must be a valid Ethereum-style 0x address.")
            return normalized_subject_type, normalized_subject_value
        if normalized_subject_type == "access_account":
            normalized_subject_value = normalize_text_field(subject_value)
        elif normalized_subject_type == "email":
            normalized_subject_value = normalize_email(subject_value)
        else:
            normalized_subject_value = normalize_handle(subject_value)
        if not normalized_subject_value:
            raise ValueError("Allowlist subject_value is required.")
        return normalized_subject_type, normalized_subject_value

    @staticmethod
    def allowlist_scope_matches(entry_scope, requested_scope):
        scope_map = {
            "access": {"access", "all_beta"},
            "review": {"review", "all_beta"},
            "submission": {"submission", "review", "all_beta"},
            "voting": {"voting", "review", "all_beta"},
            "rewards": {"rewards", "review", "all_beta"},
            "all_beta": {"all_beta"},
        }
        return str(entry_scope or "").strip().lower() in scope_map.get(str(requested_scope or "").strip().lower(), set())

    @staticmethod
    def allowlist_entry_active(entry, *, now_iso=None):
        if str(entry.get("status") or "").strip().lower() != "active":
            return False
        expires_at = str(entry.get("expires_at") or "").strip()
        return not expires_at or expires_at > str(now_iso or utc_now_iso())

    def allowlist_subject_candidates(self, *, wallet_address=None, access_account=None):
        candidates = []
        normalized_wallet = self.normalize_access_wallet(wallet_address)
        if normalized_wallet:
            candidates.append(("wallet", normalized_wallet))
        if access_account:
            for subject_type, value in (
                ("access_account", normalize_text_field(access_account.get("access_account_id"))),
                ("email", normalize_email(access_account.get("email"))),
                ("handle", normalize_handle(access_account.get("handle"))),
            ):
                if value:
                    candidates.append((subject_type, value))
        return candidates

    def get_allowlist_entry(self, state, allowlist_entry_id):
        candidate = str(allowlist_entry_id or "").strip()
        return next((entry for entry in state.allowlist_entries if candidate and str(entry.get("allowlist_entry_id") or "").strip() == candidate), None)

    def list_allowlist_entries(self, state, *, scope=None, subject_type=None, subject_value=None, status=None):
        entries = list(state.allowlist_entries)
        normalized_subject_type = str(subject_type or "").strip().lower() if subject_type is not None else None
        if scope is not None:
            entries = [entry for entry in entries if str(entry.get("scope") or "").strip().lower() == str(scope or "").strip().lower()]
        if subject_type is not None:
            entries = [entry for entry in entries if str(entry.get("subject_type") or "").strip().lower() == normalized_subject_type]
        if subject_value is not None:
            normalizers = {"wallet": self.normalize_access_wallet, "email": normalize_email, "handle": normalize_handle, "access_account": normalize_text_field}
            value = normalizers.get(normalized_subject_type, normalize_text_field)(subject_value)
            entries = [entry for entry in entries if str(entry.get("subject_value") or "").strip() == value]
        if status is not None:
            entries = [entry for entry in entries if str(entry.get("status") or "").strip().lower() == str(status or "").strip().lower()]
        return sorted(entries, key=lambda entry: str(entry.get("updated_at") or entry.get("created_at") or ""), reverse=True)

    def find_matching_allowlist_entry(self, state, scope, *, wallet_address=None, access_account=None):
        normalized_scope = self.normalize_allowlist_scope(scope)
        candidates = self.allowlist_subject_candidates(wallet_address=wallet_address, access_account=access_account)
        if not candidates:
            return None
        subject_priority = {subject_type: index for index, (subject_type, _value) in enumerate(candidates)}
        now_iso = utc_now_iso()
        for entry in sorted(state.allowlist_entries, key=lambda item: (subject_priority.get(str(item.get("subject_type") or "").strip().lower(), 999), str(item.get("updated_at") or item.get("created_at") or ""))):
            if not self.allowlist_entry_active(entry, now_iso=now_iso) or not self.allowlist_scope_matches(entry.get("scope"), normalized_scope):
                continue
            if any(str(entry.get("subject_type") or "").strip().lower() == kind and str(entry.get("subject_value") or "").strip() == value for kind, value in candidates):
                return entry
        return None

    def create_allowlist_entry(self, state, *, scope, subject_type, subject_value, reason=None, expires_at=None, created_by=None, status="active"):
        normalized_subject_type, normalized_subject_value = self.normalize_allowlist_subject(subject_type, subject_value)
        timestamp = utc_now_iso()
        entry = {"allowlist_entry_id": secrets.token_hex(16), "scope": self.normalize_allowlist_scope(scope), "subject_type": normalized_subject_type, "subject_value": normalized_subject_value, "status": self.normalize_allowlist_status(status), "reason": normalize_text_field(reason), "created_at": timestamp, "updated_at": timestamp, "expires_at": normalize_text_field(expires_at) or None, "created_by": normalize_text_field(created_by), "revoked_at": None, "revoked_reason": ""}
        state.allowlist_entries.append(entry)
        return entry

    def update_allowlist_entry(self, state, allowlist_entry_id, *, scope=None, subject_type=None, subject_value=None, reason=None, expires_at=None, status=None):
        entry = self.get_allowlist_entry(state, allowlist_entry_id)
        if entry is None:
            raise ValueError(f"Allowlist entry not found: {allowlist_entry_id}")
        if scope is not None:
            entry["scope"] = self.normalize_allowlist_scope(scope)
        if subject_type is not None or subject_value is not None:
            entry["subject_type"], entry["subject_value"] = self.normalize_allowlist_subject(subject_type if subject_type is not None else entry.get("subject_type"), subject_value if subject_value is not None else entry.get("subject_value"))
        if reason is not None:
            entry["reason"] = normalize_text_field(reason)
        if expires_at is not None:
            entry["expires_at"] = normalize_text_field(expires_at) or None
        if status is not None:
            normalized_status = self.normalize_allowlist_status(status)
            if normalized_status == "revoked":
                raise ValueError("Use revoke_allowlist_entry to revoke an allowlist entry.")
            entry["status"] = normalized_status
        entry["updated_at"] = utc_now_iso()
        return entry

    def revoke_allowlist_entry(self, state, allowlist_entry_id, *, revoked_reason=None):
        entry = self.get_allowlist_entry(state, allowlist_entry_id)
        if entry is None:
            raise ValueError(f"Allowlist entry not found: {allowlist_entry_id}")
        timestamp = utc_now_iso()
        entry.update(status="revoked", updated_at=timestamp, revoked_at=timestamp, revoked_reason=normalize_text_field(revoked_reason))
        return entry

    def reactivate_allowlist_entry(self, state, allowlist_entry_id, *, reason=None):
        entry = self.get_allowlist_entry(state, allowlist_entry_id)
        if entry is None:
            raise ValueError(f"Allowlist entry not found: {allowlist_entry_id}")
        entry.update(status="active", updated_at=utc_now_iso(), revoked_at=None, revoked_reason="")
        if reason is not None:
            entry["reason"] = normalize_text_field(reason)
        return entry

    def get_override_request(self, state, override_request_id):
        candidate = str(override_request_id or "").strip()
        return next((record for record in state.override_requests if candidate and str(record.get("override_request_id") or "").strip() == candidate), None)

    def list_override_requests(self, state, *, status=None, requested_scope=None):
        records = list(state.override_requests)
        if status is not None:
            records = [record for record in records if str(record.get("status") or "").strip().lower() == str(status or "").strip().lower()]
        if requested_scope is not None:
            records = [record for record in records if str(record.get("requested_scope") or "").strip().lower() == str(requested_scope or "").strip().lower()]
        return sorted(records, key=lambda record: str(record.get("updated_at") or record.get("created_at") or ""), reverse=True)

    def create_override_request(self, state, *, requested_scope, name=None, email=None, handle=None, wallet_address=None, access_account_id=None, reason=None, current_page=None, detected_blocked_reason=None, user_agent=None, remote_ip=None):
        timestamp = utc_now_iso()
        record = {"override_request_id": secrets.token_hex(16), "requested_scope": self.normalize_allowlist_scope(requested_scope), "name": normalize_text_field(name), "email": normalize_email(email), "handle": normalize_handle(handle), "wallet_address": self.normalize_access_wallet(wallet_address) if wallet_address else None, "access_account_id": normalize_text_field(access_account_id), "reason": normalize_text_field(reason), "current_page": normalize_text_field(current_page), "detected_blocked_reason": normalize_text_field(detected_blocked_reason), "user_agent": normalize_text_field(user_agent)[:240], "remote_ip": normalize_text_field(remote_ip)[:120], "status": "pending", "created_at": timestamp, "updated_at": timestamp, "reviewed_at": None, "reviewed_by": None, "admin_note": "", "resolved_scope": None, "approved_allowlist_entry_id": None}
        state.override_requests.append(record)
        return record

    def update_override_request_status(self, state, override_request_id, *, status, reviewed_by="operator", admin_note=None, resolved_scope=None, approved_allowlist_entry_id=None):
        record = self.get_override_request(state, override_request_id)
        if record is None:
            raise ValueError(f"Override request not found: {override_request_id}")
        record.update(status=self.normalize_override_request_status(status), updated_at=utc_now_iso(), reviewed_by=normalize_text_field(reviewed_by), admin_note=normalize_text_field(admin_note), approved_allowlist_entry_id=normalize_text_field(approved_allowlist_entry_id))
        record["reviewed_at"] = record["updated_at"]
        record["resolved_scope"] = self.normalize_allowlist_scope(resolved_scope) if resolved_scope is not None else record.get("resolved_scope")
        return record

    @staticmethod
    def _find(records, field, value):
        candidate = str(value or "").strip()
        return next((record for record in records if candidate and str(record.get(field) or "").strip() == candidate), None)

    def get_access_request(self, state, request_id):
        return self._find(state.access_requests, "request_id", request_id)

    def get_access_account(self, state, access_account_id):
        return self._find(state.access_accounts, "access_account_id", access_account_id)

    def get_wallet_binding(self, state, wallet_address):
        normalized_wallet = self.normalize_access_wallet(wallet_address)
        return next((binding for binding in state.wallet_bindings if normalized_wallet is not None and self.normalize_access_wallet(binding.get("wallet_address")) == normalized_wallet), None)

    def get_access_account_for_wallet(self, state, wallet_address):
        binding = self.get_wallet_binding(state, wallet_address)
        return self.get_access_account(state, binding.get("access_account_id")) if binding else None

    def list_access_requests(self, state, *, status=None):
        return list(state.access_requests) if status is None else [record for record in state.access_requests if str(record.get("status") or "").strip().lower() == str(status or "").strip().lower()]

    def list_access_accounts(self, state, *, status=None):
        return list(state.access_accounts) if status is None else [account for account in state.access_accounts if str(account.get("status") or "").strip().lower() == str(status or "").strip().lower()]

    def count_active_wallet_bindings(self, state):
        return sum(1 for binding in state.wallet_bindings if str(binding.get("status") or "").strip().lower() == "active")

    def list_wallet_bindings(self, state, *, access_account_id=None, status=None):
        records = list(state.wallet_bindings)
        if access_account_id is not None:
            records = [record for record in records if str(record.get("access_account_id") or "").strip() == str(access_account_id or "").strip()]
        if status is not None:
            records = [record for record in records if str(record.get("status") or "").strip().lower() == str(status or "").strip().lower()]
        return records

    def create_access_request(self, state, *, name, email, handle=None, reason=None, notes=None):
        normalized_email = normalize_email(email)
        if not normalized_email:
            raise ValueError("email is required.")
        record = {"request_id": secrets.token_hex(16), "name": normalize_text_field(name), "email": normalized_email, "handle": normalize_handle(handle), "reason": normalize_text_field(reason), "notes": normalize_text_field(notes), "status": "pending", "created_at": utc_now_iso(), "reviewed_at": None, "reviewed_by": None, "operator_notes": "", "approved_access_account_id": None}
        state.access_requests.append(record)
        return record

    def _create_access_account_record(self, state, *, name, email, handle=None, notes=None, reviewed_by="operator", operator_notes=None, max_wallets=1):
        access_code, approved_at = generate_access_code(), utc_now_iso()
        reviewed_by_value, operator_notes_value = normalize_text_field(reviewed_by), normalize_text_field(operator_notes)
        account = {"access_account_id": secrets.token_hex(16), "name": normalize_text_field(name), "email": normalize_email(email), "handle": normalize_handle(handle), "status": "active", "created_at": utc_now_iso(), "approved_at": approved_at, "invite_code_generated_at": approved_at, "invite_code_hash": hash_access_code(access_code), "redeemed_invite_code_hash": None, "invite_code_redeemed_at": None, "bound_wallets": [], "max_wallets": int(max_wallets), "notes": normalize_text_field(notes), "operator_notes": operator_notes_value, "reviewed_by": reviewed_by_value, "last_login_at": None, "status_updated_at": approved_at, "status_updated_by": reviewed_by_value, "status_reason": operator_notes_value}
        state.access_accounts.append(account)
        return account, access_code

    def create_access_invite(self, state, *, name, email, handle=None, notes=None, reviewed_by="operator", operator_notes=None, max_wallets=1):
        if not normalize_email(email):
            raise ValueError("email is required.")
        return self._create_access_account_record(state, name=name, email=email, handle=handle, notes=notes, reviewed_by=reviewed_by, operator_notes=operator_notes, max_wallets=max_wallets)

    def approve_access_request(self, state, request_id, *, reviewed_by="operator", operator_notes=None, max_wallets=1):
        request = self.get_access_request(state, request_id)
        if request is None:
            raise ValueError(f"Access request not found: {request_id}")
        status = str(request.get("status") or "").strip().lower()
        if status == "approved":
            account = self.get_access_account(state, request.get("approved_access_account_id"))
            if account is None:
                raise ValueError("Access request was approved but the access account is missing.")
            return account, None
        if status == "rejected":
            raise ValueError("Rejected access requests cannot be approved later.")
        account, code = self._create_access_account_record(state, name=request.get("name"), email=request.get("email"), handle=request.get("handle"), notes=request.get("notes"), reviewed_by=reviewed_by, operator_notes=operator_notes, max_wallets=max_wallets)
        request.update(status="approved", reviewed_at=utc_now_iso(), reviewed_by=normalize_text_field(reviewed_by), operator_notes=normalize_text_field(operator_notes), approved_access_account_id=account["access_account_id"])
        return account, code

    def reject_access_request(self, state, request_id, *, reviewed_by="operator", operator_notes=None):
        request = self.get_access_request(state, request_id)
        if request is None:
            raise ValueError(f"Access request not found: {request_id}")
        request.update(status="rejected", reviewed_at=utc_now_iso(), reviewed_by=normalize_text_field(reviewed_by), operator_notes=normalize_text_field(operator_notes))
        return request

    def resolve_access_account_by_invite_code(self, state, access_code, *, include_redeemed=False):
        code_hash = hash_access_code(access_code)
        return next((account for account in state.access_accounts if str(account.get("invite_code_hash") or "").strip() == code_hash or (include_redeemed and str(account.get("redeemed_invite_code_hash") or "").strip() == code_hash)), None)

    def mark_access_account_login(self, state, access_account_id):
        account = self.get_access_account(state, access_account_id)
        if account is None:
            raise ValueError(f"Access account not found: {access_account_id}")
        account["last_login_at"] = utc_now_iso()
        return account

    def bind_wallet_to_access_account(self, state, access_account_id, wallet_address, *, source="invite_code"):
        account = self.get_access_account(state, access_account_id)
        if account is None:
            raise ValueError(f"Access account not found: {access_account_id}")
        wallet = self.normalize_access_wallet(wallet_address)
        if wallet is None:
            raise ValueError("Invalid wallet address. Expected an Ethereum-style 0x address.")
        status = str(account.get("status") or "").strip().lower()
        if status != "active":
            raise ValueError(f"Access account is {status or 'inactive'}.")
        binding = self.get_wallet_binding(state, wallet)
        if binding:
            if str(binding.get("access_account_id") or "").strip() != account["access_account_id"]:
                raise ValueError("Wallet is already bound to a different access account.")
            if str(binding.get("status") or "").strip().lower() != "active":
                binding.update(status="active", bound_at=binding.get("bound_at") or utc_now_iso(), revoked_at=None, revoked_by="", revoke_reason="")
            if wallet not in account["bound_wallets"]:
                account["bound_wallets"].append(wallet)
            if account.get("invite_code_hash"):
                account["redeemed_invite_code_hash"], account["invite_code_hash"] = account.get("invite_code_hash"), None
            if account.get("redeemed_invite_code_hash") and not account.get("invite_code_redeemed_at"):
                account["invite_code_redeemed_at"] = utc_now_iso()
            return binding
        account["bound_wallets"] = [item for item in account.get("bound_wallets", []) if self.normalize_access_wallet(item) is not None]
        if len(account["bound_wallets"]) >= int(account.get("max_wallets") or 1):
            raise ValueError("Access account has reached the maximum number of bound wallets.")
        binding = {"wallet_address": wallet, "access_account_id": account["access_account_id"], "bound_at": utc_now_iso(), "status": "active", "source": normalize_text_field(source) or "invite_code", "revoked_at": None, "revoked_by": "", "revoke_reason": ""}
        state.wallet_bindings.append(binding)
        account["bound_wallets"].append(wallet)
        if account.get("invite_code_hash"):
            account["redeemed_invite_code_hash"], account["invite_code_hash"], account["invite_code_redeemed_at"] = account.get("invite_code_hash"), None, utc_now_iso()
        return binding

    def update_access_account_status(self, state, access_account_id, status, *, updated_by="operator", reason=None):
        account = self.get_access_account(state, access_account_id)
        if account is None:
            raise ValueError(f"Access account not found: {access_account_id}")
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in {"active", "suspended", "revoked"}:
            raise ValueError("Access account status must be active, suspended, or revoked.")
        account.update(status=normalized_status, status_updated_at=utc_now_iso(), status_updated_by=normalize_text_field(updated_by), status_reason=normalize_text_field(reason))
        return account

    def revoke_wallet_binding(self, state, wallet_address, *, revoked_by="operator", reason=None):
        binding = self.get_wallet_binding(state, wallet_address)
        if binding is None:
            raise ValueError(f"Wallet binding not found: {wallet_address}")
        binding.update(status="revoked", revoked_at=utc_now_iso(), revoked_by=normalize_text_field(revoked_by), revoke_reason=normalize_text_field(reason))
        account, wallet = self.get_access_account(state, binding.get("access_account_id")), self.normalize_access_wallet(binding.get("wallet_address"))
        if account is not None and wallet in account.get("bound_wallets", []):
            account["bound_wallets"] = [item for item in account.get("bound_wallets", []) if self.normalize_access_wallet(item) != wallet]
        return binding

    def append_audit_log_entry(self, state, entry):
        normalized = dict(entry or {})
        normalized.setdefault("audit_id", secrets.token_hex(16))
        normalized.setdefault("timestamp", utc_now_iso())
        normalized["action"] = normalize_text_field(normalized.get("action"))
        normalized["result"] = normalize_text_field(normalized.get("result")) or "ok"
        state.audit_logs.append(normalized)
        return normalized

    def list_audit_log_entries(self, state, *, action=None, since=None, before=None, limit=None):
        entries = list(state.audit_logs)
        if action:
            entries = [entry for entry in entries if str(entry.get("action") or "").strip().lower() == str(action or "").strip().lower()]
        if since:
            entries = [entry for entry in entries if str(entry.get("timestamp") or "").strip() >= str(since).strip()]
        if before:
            entries = [entry for entry in entries if str(entry.get("timestamp") or "").strip() <= str(before).strip()]
        entries.sort(key=lambda entry: str(entry.get("timestamp") or ""), reverse=True)
        if limit is not None:
            try:
                limit_value = max(0, int(limit))
            except (TypeError, ValueError):
                limit_value = 0
            if limit_value:
                entries = entries[:limit_value]
        return entries
