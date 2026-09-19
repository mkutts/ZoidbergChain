"""Framework-neutral Ethereum-style wallet identity signature primitives."""

from eth_account import Account
from eth_account.messages import encode_defunct


def canonicalize_wallet_message(message: str) -> str:
    return str(message or "").replace("\r\n", "\n").replace("\r", "\n")


def normalize_wallet_address(wallet_address: str) -> str | None:
    candidate = str(wallet_address or "").strip()
    if len(candidate) != 42 or candidate[:2].lower() != "0x":
        return None
    hex_part = candidate[2:]
    if not hex_part or any(ch not in "0123456789abcdefABCDEF" for ch in hex_part):
        return None
    return f"0x{hex_part.lower()}"


def recover_signed_wallet_address(message: str, signature: str) -> str:
    try:
        recovered = Account.recover_message(
            encode_defunct(text=canonicalize_wallet_message(message)),
            signature=signature,
        )
    except Exception as exc:
        raise ValueError("Malformed signature or unsupported signature payload.") from exc
    recovered_normalized = normalize_wallet_address(recovered)
    if not recovered_normalized:
        raise ValueError("Recovered signature address is invalid.")
    return recovered_normalized
