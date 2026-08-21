from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import config
from wallet_auth import normalize_wallet_address


ACCESS_SESSION_TTL_SECONDS = 60 * 60


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def normalize_email(value: str | None) -> str:
    return str(value or "").strip().lower()


def normalize_text_field(value: str | None) -> str:
    return str(value or "").strip()


def normalize_handle(value: str | None) -> str:
    return normalize_text_field(value)


def hash_access_code(code: str) -> str:
    return hashlib.sha256(str(code or "").strip().encode("utf-8")).hexdigest()


def generate_access_code() -> str:
    token = secrets.token_hex(8).upper()
    return f"ZC-{token}"


def dev_bypass_effective() -> bool:
    return config.ENVIRONMENT == "development" and bool(config.ACCESS_DEV_BYPASS_ENABLED)


def access_mode_enforces_binding() -> bool:
    return config.ACCESS_CONTROL_MODE in {"invite_only", "allowlist"}


def access_feature_required(feature: str) -> bool:
    feature_flags = {
        "app": config.REQUIRE_ACCESS_FOR_APP,
        "submissions": config.REQUIRE_ACCESS_FOR_SUBMISSIONS,
        "votes": config.REQUIRE_ACCESS_FOR_VOTES,
        "rewards": config.REQUIRE_ACCESS_FOR_REWARDS,
        "transfers": config.REQUIRE_ACCESS_FOR_TRANSFERS,
    }
    return bool(feature_flags.get(str(feature or "").strip().lower(), False))


def public_access_status_payload() -> dict:
    return {
        "environment": config.ENVIRONMENT,
        "access_control_mode": config.ACCESS_CONTROL_MODE,
        "access_requests_enabled": config.ACCESS_REQUESTS_ENABLED,
        "access_public_label": config.ACCESS_PUBLIC_LABEL,
        "max_wallets_per_access_account": config.MAX_WALLETS_PER_ACCESS_ACCOUNT,
        "access_dev_bypass_enabled": dev_bypass_effective(),
        "require_access_for_app": config.REQUIRE_ACCESS_FOR_APP,
        "require_access_for_submissions": config.REQUIRE_ACCESS_FOR_SUBMISSIONS,
        "require_access_for_votes": config.REQUIRE_ACCESS_FOR_VOTES,
        "require_access_for_rewards": config.REQUIRE_ACCESS_FOR_REWARDS,
        "require_access_for_transfers": config.REQUIRE_ACCESS_FOR_TRANSFERS,
    }


@dataclass
class AccessSession:
    session_id: str
    access_account_id: str
    issued_at: datetime
    expires_at: datetime
    invite_authenticated: bool = True
    bound_wallet_address: str | None = None
    consumed_at: datetime | None = None


@dataclass
class AccessDecision:
    allowed: bool
    reason: str
    access_account: dict | None = None
    binding: dict | None = None
    bypassed: bool = False
    allowlist_override_applied: bool = False
    allowlist_scope: str | None = None


class AccessSessionManager:
    def __init__(self, *, session_ttl_seconds: int = ACCESS_SESSION_TTL_SECONDS):
        self.session_ttl_seconds = session_ttl_seconds
        self._sessions_by_token_hash: dict[str, AccessSession] = {}

    def clear(self) -> None:
        self._sessions_by_token_hash.clear()

    def prune_expired(self) -> None:
        now = utc_now()
        self._sessions_by_token_hash = {
            token_hash: session
            for token_hash, session in self._sessions_by_token_hash.items()
            if session.expires_at > now
        }

    def issue_session(self, access_account_id: str) -> dict[str, str]:
        self.prune_expired()
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        issued_at = utc_now()
        expires_at = issued_at + timedelta(seconds=self.session_ttl_seconds)
        self._sessions_by_token_hash[token_hash] = AccessSession(
            session_id=token_hash,
            access_account_id=str(access_account_id or "").strip(),
            issued_at=issued_at,
            expires_at=expires_at,
        )
        return {
            "access_session_token": raw_token,
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }

    def _resolve_session(self, token: str) -> tuple[str, AccessSession]:
        self.prune_expired()
        candidate = str(token or "").strip()
        if not candidate:
            raise ValueError("Missing access session token.")
        token_hash = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
        session = self._sessions_by_token_hash.get(token_hash)
        if session is None:
            raise ValueError("No active access session found.")
        if session.expires_at <= utc_now():
            del self._sessions_by_token_hash[token_hash]
            raise ValueError("Access session has expired.")
        return token_hash, session

    def resolve_access_account_id(self, token: str) -> str:
        _token_hash, session = self._resolve_session(token)
        return session.access_account_id

    def get_session(self, token: str) -> AccessSession:
        _token_hash, session = self._resolve_session(token)
        return session

    def mark_wallet_bound(self, token: str, wallet_address: str) -> AccessSession:
        _token_hash, session = self._resolve_session(token)
        normalized_wallet = normalize_wallet_address(wallet_address or "")
        if normalized_wallet is None:
            raise ValueError("Invalid wallet address for access session binding.")
        if session.bound_wallet_address and session.bound_wallet_address != normalized_wallet:
            raise ValueError("Access session is already associated with a different verified wallet.")
        session.bound_wallet_address = normalized_wallet
        if session.consumed_at is None:
            session.consumed_at = utc_now()
        return session

    def count_active_sessions(self) -> int:
        self.prune_expired()
        return len(self._sessions_by_token_hash)

    @staticmethod
    def backend_description() -> str:
        return "memory_only_process_local"

    def revoke_session(self, token: str) -> bool:
        candidate = str(token or "").strip()
        if not candidate:
            return False
        token_hash = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
        return self._sessions_by_token_hash.pop(token_hash, None) is not None


def access_decision_for_wallet(blockchain, wallet_address: str | None, *, feature: str) -> AccessDecision:
    normalized_wallet = normalize_wallet_address(wallet_address or "")
    if not access_feature_required(feature):
        return AccessDecision(allowed=True, reason="feature_not_gated")
    if dev_bypass_effective():
        return AccessDecision(allowed=True, reason="development_bypass", bypassed=True)
    if not access_mode_enforces_binding():
        return AccessDecision(allowed=True, reason="access_mode_open")
    if normalized_wallet is None:
        return AccessDecision(allowed=False, reason="wallet_not_verified")
    binding = blockchain.get_wallet_binding(normalized_wallet)
    account = blockchain.get_access_account_for_wallet(normalized_wallet)
    if binding and str(binding.get("status") or "").strip().lower() == "revoked":
        return AccessDecision(
            allowed=False,
            reason="wallet_binding_revoked",
            access_account=account,
            binding=binding,
        )
    if account is not None:
        account_status = str(account.get("status") or "").strip().lower()
        if account_status != "active":
            return AccessDecision(
                allowed=False,
                reason=f"access_account_{account_status or 'inactive'}",
                access_account=account,
                binding=binding,
            )
    if not binding or str(binding.get("status") or "").strip().lower() != "active":
        override_entry = blockchain.find_matching_allowlist_entry(
            "access",
            wallet_address=normalized_wallet,
            access_account=account,
        )
        if override_entry:
            return AccessDecision(
                allowed=True,
                reason="allowlist_override",
                access_account=account,
                binding=binding,
                allowlist_override_applied=True,
                allowlist_scope=str(override_entry.get("scope") or "").strip().lower() or None,
            )
        return AccessDecision(allowed=False, reason="wallet_not_bound", access_account=account, binding=binding)
    account = blockchain.get_access_account(binding.get("access_account_id"))
    if not account:
        return AccessDecision(allowed=False, reason="access_account_missing", binding=binding)
    return AccessDecision(
        allowed=True,
        reason="access_granted",
        access_account=account,
        binding=binding,
    )
