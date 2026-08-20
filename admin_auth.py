from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


ADMIN_PASSWORD_HASH_PREFIX = "pbkdf2_sha256"
ADMIN_PASSWORD_HASH_ITERATIONS = 390000


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def admin_auth_is_configured(password_hash: str | None, bootstrap_token: str | None) -> bool:
    return bool(str(password_hash or "").strip() or str(bootstrap_token or "").strip())


def hash_admin_password(password: str, *, salt: str | None = None, iterations: int = ADMIN_PASSWORD_HASH_ITERATIONS) -> str:
    normalized_password = str(password or "")
    if not normalized_password:
        raise ValueError("Admin password cannot be empty.")
    if iterations <= 0:
        raise ValueError("iterations must be positive.")

    salt_hex = salt.strip().lower() if isinstance(salt, str) and salt.strip() else secrets.token_hex(16)
    try:
        salt_bytes = bytes.fromhex(salt_hex)
    except ValueError as exc:
        raise ValueError("salt must be a valid hex string.") from exc

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        normalized_password.encode("utf-8"),
        salt_bytes,
        iterations,
    ).hex()
    return f"{ADMIN_PASSWORD_HASH_PREFIX}${iterations}${salt_hex}${digest}"


def verify_admin_password(password: str, stored_hash: str | None) -> bool:
    normalized_hash = str(stored_hash or "").strip()
    if not normalized_hash:
        return False

    try:
        algorithm, iterations_raw, salt_hex, expected_digest = normalized_hash.split("$", 3)
    except ValueError:
        return False

    if algorithm != ADMIN_PASSWORD_HASH_PREFIX:
        return False

    try:
        iterations = int(iterations_raw)
    except ValueError:
        return False

    try:
        candidate_hash = hash_admin_password(password, salt=salt_hex, iterations=iterations)
    except ValueError:
        return False

    candidate_digest = candidate_hash.rsplit("$", 1)[-1]
    return secrets.compare_digest(candidate_digest, expected_digest)


def verify_admin_credential(
    submitted_secret: str,
    *,
    password_hash: str | None = None,
    bootstrap_token: str | None = None,
) -> bool:
    candidate = str(submitted_secret or "")
    if not candidate:
        return False

    normalized_bootstrap = str(bootstrap_token or "").strip()
    if normalized_bootstrap and secrets.compare_digest(candidate, normalized_bootstrap):
        return True

    return verify_admin_password(candidate, password_hash)


@dataclass
class AdminSession:
    session_id: str
    issued_at: datetime
    expires_at: datetime


class AdminSessionManager:
    def __init__(self, *, session_ttl_seconds: int = 3600):
        self.session_ttl_seconds = int(session_ttl_seconds)
        self._sessions_by_token_hash: dict[str, AdminSession] = {}

    def clear(self) -> None:
        self._sessions_by_token_hash.clear()

    def prune_expired(self) -> None:
        now = utc_now()
        self._sessions_by_token_hash = {
            token_hash: session
            for token_hash, session in self._sessions_by_token_hash.items()
            if session.expires_at > now
        }

    def issue_session(self) -> dict[str, str]:
        self.prune_expired()
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        issued_at = utc_now()
        expires_at = issued_at + timedelta(seconds=self.session_ttl_seconds)
        self._sessions_by_token_hash[token_hash] = AdminSession(
            session_id=token_hash,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        return {
            "admin_session_token": raw_token,
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }

    def _resolve_session(self, token: str) -> tuple[str, AdminSession]:
        self.prune_expired()
        candidate = str(token or "").strip()
        if not candidate:
            raise ValueError("Missing admin session token.")
        token_hash = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
        session = self._sessions_by_token_hash.get(token_hash)
        if session is None:
            raise ValueError("No active admin session found.")
        if session.expires_at <= utc_now():
            del self._sessions_by_token_hash[token_hash]
            raise ValueError("Admin session has expired.")
        return token_hash, session

    def get_session(self, token: str) -> AdminSession:
        _token_hash, session = self._resolve_session(token)
        return session

    def revoke_session(self, token: str) -> bool:
        candidate = str(token or "").strip()
        if not candidate:
            return False
        token_hash = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
        return self._sessions_by_token_hash.pop(token_hash, None) is not None

    def count_active_sessions(self) -> int:
        self.prune_expired()
        return len(self._sessions_by_token_hash)

    @staticmethod
    def backend_description() -> str:
        return "memory_only_process_local"
