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


@dataclass
class SubmissionChallenge:
    wallet_address: str
    content_hash: str
    content_id: str | None
    caption: str | None
    nonce: str
    message: str
    issued_at: datetime
    expires_at: datetime
    used: bool = False


@dataclass
class VoteChallenge:
    wallet_address: str
    submission_id: str
    content_hash: str
    vote_type: str
    nonce: str
    message: str
    issued_at: datetime
    expires_at: datetime
    used: bool = False


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


def build_wallet_submission_message(
    *,
    wallet_address: str,
    network_name: str,
    content_hash: str,
    content_id: str | None,
    caption: str | None,
    nonce: str,
    issued_at: datetime,
    expires_at: datetime,
) -> str:
    return "\n".join(
        [
            "ZoidbergChain Submission Authorization",
            "",
            "Action: submit_content",
            f"Network: {network_name}",
            f"Wallet: {wallet_address}",
            f"Content Hash: {content_hash}",
            f"Content ID: {content_id or ''}",
            f"Caption: {caption or ''}",
            f"Nonce: {nonce}",
            f"Issued At: {_isoformat(issued_at)}",
            f"Expires At: {_isoformat(expires_at)}",
            "",
            "This signature proves the wallet is submitting this content to ZoidbergChain.",
            "It does not authorize a token transfer.",
        ]
    )


def build_wallet_vote_message(
    *,
    wallet_address: str,
    network_name: str,
    submission_id: str,
    content_hash: str,
    vote_type: str,
    nonce: str,
    issued_at: datetime,
    expires_at: datetime,
) -> str:
    return "\n".join(
        [
            "ZoidbergChain Vote Authorization",
            "",
            "Action: vote_originality",
            f"Network: {network_name}",
            f"Wallet: {wallet_address}",
            f"Submission ID: {submission_id}",
            f"Content Hash: {content_hash}",
            f"Vote: {vote_type}",
            f"Nonce: {nonce}",
            f"Issued At: {_isoformat(issued_at)}",
            f"Expires At: {_isoformat(expires_at)}",
            "",
            "This signature proves the wallet is casting this originality vote on ZoidbergChain.",
            "It does not authorize a token transfer.",
        ]
    )


def hash_wallet_message(message: str) -> str:
    return hashlib.sha256(str(message or "").encode("utf-8")).hexdigest()


def recover_signed_wallet_address(message: str, signature: str) -> str:
    try:
        recovered = Account.recover_message(
            encode_defunct(text=message),
            signature=signature,
        )
    except Exception as exc:
        raise ValueError("Malformed signature or unsupported signature payload.") from exc

    recovered_normalized = normalize_wallet_address(recovered)
    if not recovered_normalized:
        raise ValueError("Recovered signature address is invalid.")
    return recovered_normalized


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
        self._submission_challenges_by_message_hash: dict[str, SubmissionChallenge] = {}
        self._vote_challenges_by_message_hash: dict[str, VoteChallenge] = {}

    def clear(self) -> None:
        self._challenges_by_wallet.clear()
        self._sessions_by_token_hash.clear()
        self._submission_challenges_by_message_hash.clear()
        self._vote_challenges_by_message_hash.clear()

    def prune_expired(self) -> None:
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
        self._submission_challenges_by_message_hash = {
            message_hash: challenge
            for message_hash, challenge in self._submission_challenges_by_message_hash.items()
            if challenge.expires_at > now
        }
        self._vote_challenges_by_message_hash = {
            message_hash: challenge
            for message_hash, challenge in self._vote_challenges_by_message_hash.items()
            if challenge.expires_at > now
        }

    def issue_challenge(self, wallet_address: str) -> dict[str, str]:
        self.prune_expired()
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
            "issued_at": _isoformat(issued_at),
            "expires_at": _isoformat(expires_at),
        }

    def verify_signature(self, wallet_address: str, message: str, signature: str) -> dict[str, str | bool]:
        self.prune_expired()
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

        recovered_normalized = recover_signed_wallet_address(message, signature)
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
            "normalized_wallet_address": normalized,
            "session_token": raw_token,
            "issued_at": _isoformat(issued_at),
            "expires_at": _isoformat(expires_at),
            "message": "Wallet verified",
        }

    def issue_submission_challenge(
        self,
        *,
        wallet_address: str,
        content_hash: str,
        content_id: str | None = None,
        caption: str | None = None,
    ) -> dict[str, str]:
        self.prune_expired()
        normalized = normalize_wallet_address(wallet_address)
        if not normalized:
            raise ValueError("Invalid wallet address. Expected an Ethereum-style 0x address.")
        if not isinstance(content_hash, str) or not content_hash.strip():
            raise ValueError("content_hash is required.")

        issued_at = _utc_now()
        expires_at = issued_at + timedelta(seconds=self.challenge_ttl_seconds)
        nonce = secrets.token_urlsafe(24)
        message = build_wallet_submission_message(
            wallet_address=normalized,
            network_name=self.network_name,
            content_hash=content_hash.strip(),
            content_id=(content_id or "").strip() or None,
            caption=(caption or "").strip() or None,
            nonce=nonce,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        challenge = SubmissionChallenge(
            wallet_address=normalized,
            content_hash=content_hash.strip(),
            content_id=(content_id or "").strip() or None,
            caption=(caption or "").strip() or None,
            nonce=nonce,
            message=message,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        self._submission_challenges_by_message_hash[hash_wallet_message(message)] = challenge
        return {
            "wallet_address": normalized,
            "normalized_wallet_address": normalized,
            "content_hash": challenge.content_hash,
            "content_id": challenge.content_id or "",
            "caption": challenge.caption or "",
            "nonce": nonce,
            "message": message,
            "issued_at": _isoformat(issued_at),
            "expires_at": _isoformat(expires_at),
        }

    def verify_submission_signature(
        self,
        *,
        wallet_address: str,
        message: str,
        signature: str,
        content_hash: str,
        content_id: str | None = None,
    ) -> dict[str, str | bool]:
        self.prune_expired()
        normalized = normalize_wallet_address(wallet_address)
        if not normalized:
            raise ValueError("Invalid wallet address. Expected an Ethereum-style 0x address.")
        if not isinstance(signature, str) or not signature.strip():
            raise ValueError("Missing signature.")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Missing signed submission message.")

        message_hash = hash_wallet_message(message)
        challenge = self._submission_challenges_by_message_hash.get(message_hash)
        if challenge is None:
            raise ValueError("No active submission challenge found for this message.")
        if challenge.used:
            raise ValueError("Submission challenge has already been used.")
        if challenge.expires_at <= _utc_now():
            raise ValueError("Submission challenge has expired.")
        if message != challenge.message:
            raise ValueError("Submission challenge message does not match the stored challenge.")
        if challenge.wallet_address != normalized:
            raise ValueError("Submission challenge wallet does not match the verified session wallet.")
        if content_hash.strip() != challenge.content_hash:
            raise ValueError("Submission content_hash does not match the signed challenge.")

        normalized_content_id = (content_id or "").strip() or None
        if challenge.content_id != normalized_content_id:
            raise ValueError("Submission content_id does not match the signed challenge.")

        recovered_normalized = recover_signed_wallet_address(message, signature)
        if recovered_normalized != normalized:
            raise ValueError("Signature does not match the verified session wallet.")

        challenge.used = True
        signed_at = _utc_now()
        return {
            "verified": True,
            "wallet_address": normalized,
            "normalized_wallet_address": normalized,
            "content_hash": challenge.content_hash,
            "content_id": challenge.content_id or "",
            "caption": challenge.caption or "",
            "nonce": challenge.nonce,
            "signature_scheme": "personal_sign",
            "submission_signature": signature.strip(),
            "submission_message": challenge.message,
            "signed_message_hash": message_hash,
            "issued_at": _isoformat(challenge.issued_at),
            "expires_at": _isoformat(challenge.expires_at),
            "signed_at": _isoformat(signed_at),
            "identity_source": "metamask_signed",
            "message": "Submission signature verified",
        }

    def issue_vote_challenge(
        self,
        *,
        wallet_address: str,
        submission_id: str,
        content_hash: str,
        vote_type: str,
    ) -> dict[str, str]:
        self.prune_expired()
        normalized = normalize_wallet_address(wallet_address)
        if not normalized:
            raise ValueError("Invalid wallet address. Expected an Ethereum-style 0x address.")
        if not isinstance(submission_id, str) or not submission_id.strip():
            raise ValueError("submission_id is required.")
        if not isinstance(content_hash, str) or not content_hash.strip():
            raise ValueError("content_hash is required.")
        if not isinstance(vote_type, str) or not vote_type.strip():
            raise ValueError("vote is required.")

        issued_at = _utc_now()
        expires_at = issued_at + timedelta(seconds=self.challenge_ttl_seconds)
        nonce = secrets.token_urlsafe(24)
        message = build_wallet_vote_message(
            wallet_address=normalized,
            network_name=self.network_name,
            submission_id=submission_id.strip(),
            content_hash=content_hash.strip(),
            vote_type=vote_type.strip(),
            nonce=nonce,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        challenge = VoteChallenge(
            wallet_address=normalized,
            submission_id=submission_id.strip(),
            content_hash=content_hash.strip(),
            vote_type=vote_type.strip(),
            nonce=nonce,
            message=message,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        self._vote_challenges_by_message_hash[hash_wallet_message(message)] = challenge
        return {
            "wallet_address": normalized,
            "normalized_wallet_address": normalized,
            "submission_id": challenge.submission_id,
            "content_hash": challenge.content_hash,
            "vote": challenge.vote_type,
            "nonce": nonce,
            "message": message,
            "issued_at": _isoformat(issued_at),
            "expires_at": _isoformat(expires_at),
        }

    def verify_vote_signature(
        self,
        *,
        wallet_address: str,
        message: str,
        signature: str,
        submission_id: str,
        content_hash: str,
        vote_type: str,
    ) -> dict[str, str | bool]:
        self.prune_expired()
        normalized = normalize_wallet_address(wallet_address)
        if not normalized:
            raise ValueError("Invalid wallet address. Expected an Ethereum-style 0x address.")
        if not isinstance(signature, str) or not signature.strip():
            raise ValueError("Missing signature.")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Missing signed vote message.")

        message_hash = hash_wallet_message(message)
        challenge = self._vote_challenges_by_message_hash.get(message_hash)
        if challenge is None:
            raise ValueError("No active vote challenge found for this message.")
        if challenge.used:
            raise ValueError("Vote challenge has already been used.")
        if challenge.expires_at <= _utc_now():
            raise ValueError("Vote challenge has expired.")
        if message != challenge.message:
            raise ValueError("Vote challenge message does not match the stored challenge.")
        if challenge.wallet_address != normalized:
            raise ValueError("Vote challenge wallet does not match the verified session wallet.")
        if submission_id.strip() != challenge.submission_id:
            raise ValueError("Vote submission_id does not match the signed challenge.")
        if content_hash.strip() != challenge.content_hash:
            raise ValueError("Vote content_hash does not match the signed challenge.")
        if vote_type.strip() != challenge.vote_type:
            raise ValueError("Vote type does not match the signed challenge.")

        recovered_normalized = recover_signed_wallet_address(message, signature)
        if recovered_normalized != normalized:
            raise ValueError("Signature does not match the verified session wallet.")

        challenge.used = True
        signed_at = _utc_now()
        return {
            "verified": True,
            "wallet_address": normalized,
            "normalized_wallet_address": normalized,
            "submission_id": challenge.submission_id,
            "content_hash": challenge.content_hash,
            "vote": challenge.vote_type,
            "nonce": challenge.nonce,
            "signature_scheme": "personal_sign",
            "vote_signature": signature.strip(),
            "vote_message": challenge.message,
            "signed_message_hash": message_hash,
            "issued_at": _isoformat(challenge.issued_at),
            "expires_at": _isoformat(challenge.expires_at),
            "signed_at": _isoformat(signed_at),
            "identity_source": "metamask_signed",
            "message": "Vote signature verified",
        }

    def resolve_session(self, token: str) -> WalletSession:
        self.prune_expired()
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

    def revoke_session(self, token: str | None) -> bool:
        self.prune_expired()
        if not isinstance(token, str) or not token.strip():
            return False
        token_hash = hashlib.sha256(token.strip().encode("utf-8")).hexdigest()
        return self._sessions_by_token_hash.pop(token_hash, None) is not None

    def session_payload(self, token: str) -> dict[str, str | bool]:
        session = self.resolve_session(token)
        return {
            "valid": True,
            "wallet_address": session.wallet_address,
            "normalized_wallet_address": session.wallet_address,
            "issued_at": _isoformat(session.issued_at),
            "expires_at": _isoformat(session.expires_at),
            "network_name": session.network_name,
        }


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
