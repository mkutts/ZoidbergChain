from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import Header, HTTPException


ETHEREUM_ADDRESS_PATTERN = r"^0x[a-fA-F0-9]{40}$"
DEFAULT_CHALLENGE_TTL_SECONDS = 300
DEFAULT_SESSION_TTL_SECONDS = 12 * 60 * 60


@dataclass
class WalletChallenge:
    wallet_address: str
    nonce: str
    message: str
    issued_at: datetime
    expires_at: datetime
    used: bool = False


@dataclass
class WalletSession:
    session_id: str
    wallet_address: str
    issued_at: datetime
    expires_at: datetime
    environment: str
    network_name: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def normalize_wallet_address(wallet_address: str) -> str | None:
    candidate = str(wallet_address or "").strip()
    if len(candidate) != 42 or not candidate.startswith("0x"):
        return None
    hex_part = candidate[2:]
    if not hex_part or any(ch not in "0123456789abcdefABCDEF" for ch in hex_part):
        return None
    return f"0x{hex_part.lower()}"


def build_wallet_login_message(
    *,
    wallet_address: str,
    network_name: str,
    nonce: str,
    issued_at: datetime,
    expires_at: datetime,
) -> str:
    return (
        "ZoidbergChain Login\n\n"
        f"Wallet: {wallet_address}\n"
        f"Network: {network_name}\n"
        f"Nonce: {nonce}\n"
        f"Issued At: {_isoformat(issued_at)}\n"
        f"Expires At: {_isoformat(expires_at)}\n\n"
        "This signature proves ownership of this wallet for ZoidbergChain login.\n"
        "It does not authorize a transaction."
    )


class WalletAuthManager:
    def __init__(
        self,
        *,
        network_name: str,
        environment: str,
        challenge_ttl_seconds: int = DEFAULT_CHALLENGE_TTL_SECONDS,
        session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
    ):
        self.network_name = network_name
        self.environment = environment
        self.challenge_ttl_seconds = challenge_ttl_seconds
        self.session_ttl_seconds = session_ttl_seconds
        self._challenges_by_wallet: dict[str, WalletChallenge] = {}
        self._sessions_by_token_hash: dict[str, WalletSession] = {}

    def clear(self) -> None:
        self._challenges_by_wallet.clear()
        self._sessions_by_token_hash.clear()

    def _clear_expired(self) -> None:
        now = _utc_now()
        self._challenges_by_wallet = {
            wallet: challenge
            for wallet, challenge in self._challenges_by_wallet.items()
            if challenge.expires_at > now
        }
        self._sessions_by_token_hash = {
            token_hash: session
            for token_hash, session in self._sessions_by_token_hash.items()
            if session.expires_at > now
        }

    def issue_challenge(self, wallet_address: str) -> dict[str, str]:
        self._clear_expired()
        normalized = normalize_wallet_address(wallet_address)
        if not normalized:
            raise ValueError("Invalid wallet address. Expected an Ethereum-style 0x address.")

        issued_at = _utc_now()
        expires_at = issued_at + timedelta(seconds=self.challenge_ttl_seconds)
        nonce = secrets.token_urlsafe(24)
        message = build_wallet_login_message(
            wallet_address=normalized,
            network_name=self.network_name,
            nonce=nonce,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        self._challenges_by_wallet[normalized] = WalletChallenge(
            wallet_address=normalized,
            nonce=nonce,
            message=message,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        return {
            "wallet_address": wallet_address,
            "normalized_wallet_address": normalized,
            "nonce": nonce,
            "message": message,
            "expires_at": _isoformat(expires_at),
        }

    def verify_signature(self, wallet_address: str, message: str, signature: str) -> dict[str, str | bool]:
        self._sessions_by_token_hash = {
            token_hash: session
            for token_hash, session in self._sessions_by_token_hash.items()
            if session.expires_at > _utc_now()
        }
        normalized = normalize_wallet_address(wallet_address)
        if not normalized:
            raise ValueError("Invalid wallet address. Expected an Ethereum-style 0x address.")
        if not isinstance(signature, str) or not signature.strip():
            raise ValueError("Missing signature.")

        challenge = self._challenges_by_wallet.get(normalized)
        if challenge is None:
            raise ValueError("No active wallet challenge found for this address.")
        if challenge.used:
            raise ValueError("Wallet challenge has already been used.")
        if challenge.expires_at <= _utc_now():
            raise ValueError("Wallet challenge has expired.")
        if message != challenge.message:
            raise ValueError("Wallet challenge message does not match the stored challenge.")

        try:
            recovered = Account.recover_message(
                encode_defunct(text=message),
                signature=signature,
            )
        except Exception as exc:
            raise ValueError("Malformed signature or unsupported signature payload.") from exc

        recovered_normalized = normalize_wallet_address(recovered)
        if recovered_normalized != normalized:
            raise ValueError("Signature does not match the submitted wallet address.")

        challenge.used = True
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        issued_at = _utc_now()
        expires_at = issued_at + timedelta(seconds=self.session_ttl_seconds)
        session = WalletSession(
            session_id=secrets.token_hex(16),
            wallet_address=normalized,
            issued_at=issued_at,
            expires_at=expires_at,
            environment=self.environment,
            network_name=self.network_name,
        )
        self._sessions_by_token_hash[token_hash] = session
        return {
            "verified": True,
            "wallet_address": normalized,
            "session_token": raw_token,
            "expires_at": _isoformat(expires_at),
            "message": "Wallet verified",
        }

    def resolve_session(self, token: str) -> WalletSession:
        self._clear_expired()
        if not isinstance(token, str) or not token.strip():
            raise ValueError("Missing session token.")
        token_hash = hashlib.sha256(token.strip().encode("utf-8")).hexdigest()
        session = self._sessions_by_token_hash.get(token_hash)
        if session is None:
            raise ValueError("Invalid or expired session token.")
        if session.expires_at <= _utc_now():
            self._sessions_by_token_hash.pop(token_hash, None)
            raise ValueError("Session token has expired.")
        return session


default_wallet_auth_manager = WalletAuthManager(
    network_name="zoidberg-testnet",
    environment="development",
)


def resolve_verified_wallet_from_authorization(
    authorization: str | None,
    *,
    manager: WalletAuthManager = default_wallet_auth_manager,
) -> str:
    if not authorization or not authorization.strip():
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        raise HTTPException(status_code=401, detail="Invalid authorization scheme.")
    token = authorization[len(prefix):].strip()
    try:
        session = manager.resolve_session(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return session.wallet_address


async def get_verified_wallet_from_request(
    authorization: str | None = Header(default=None),
    manager: WalletAuthManager = default_wallet_auth_manager,
) -> str:
    return resolve_verified_wallet_from_authorization(authorization, manager=manager)
