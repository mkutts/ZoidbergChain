import re
from pathlib import PurePosixPath
from fastapi import UploadFile

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_SUBMISSION_TEXT_LENGTH = 4096
MAX_METADATA_FIELD_LENGTH = 256
MAX_URL_LENGTH = 2048
PUBLIC_KEY_PATTERN = r"^[a-f0-9]{66}$"
NODE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
NETWORK_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,63}$"
HEX_32_PATTERN = r"^[a-f0-9]{32}$"
HEX_64_PATTERN = r"^[a-f0-9]{64}$"


def is_valid_http_url(url: str) -> bool:
    if not isinstance(url, str):
        return False
    normalized = url.strip()
    return bool(re.match(r"^https?://[^\s/$.?#].[^\s]*$", normalized))


def is_valid_node_id(node_id: str) -> bool:
    return bool(isinstance(node_id, str) and re.match(NODE_ID_PATTERN, node_id.strip()))


def is_valid_network_name(network_name: str) -> bool:
    return bool(isinstance(network_name, str) and re.match(NETWORK_NAME_PATTERN, network_name.strip()))


def is_valid_wallet_public_key(public_key: str) -> bool:
    return bool(isinstance(public_key, str) and re.match(PUBLIC_KEY_PATTERN, public_key.strip()))


def is_valid_submission_id(submission_id: str) -> bool:
    return bool(isinstance(submission_id, str) and re.match(HEX_32_PATTERN, submission_id.strip()))


def is_valid_certificate_id(certificate_id: str) -> bool:
    return bool(isinstance(certificate_id, str) and re.match(HEX_64_PATTERN, certificate_id.strip()))


def is_valid_block_hash(block_hash: str) -> bool:
    return bool(isinstance(block_hash, str) and re.match(HEX_64_PATTERN, block_hash.strip()))


def is_valid_content_hash(content_hash: str) -> bool:
    return bool(isinstance(content_hash, str) and re.match(HEX_64_PATTERN, content_hash.strip()))


def is_safe_filename(filename: str) -> bool:
    if not isinstance(filename, str) or not filename.strip():
        return False
    candidate = PurePosixPath(filename).name
    return candidate == filename and candidate not in {".", ".."} and "/" not in filename and "\\" not in filename

def is_valid_public_key(public_key: str, wallets: dict) -> bool:
    """Validate that the public key is a hexadecimal string and exists in the wallets."""
    is_format_valid = is_valid_wallet_public_key(public_key)
    is_registered = public_key in wallets
    print(f"Debug: Public key {public_key} format valid: {is_format_valid}, registered: {is_registered}")
    return is_format_valid and is_registered

def is_valid_amount(amount: float) -> bool:
    """Validate that the amount is a positive number."""
    return amount > 0

def is_valid_image(file: UploadFile) -> bool:
    """Validate the image file format based on its extension."""
    extension = file.filename.split(".")[-1].lower()
    return extension in ALLOWED_EXTENSIONS
