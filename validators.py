import re
from fastapi import UploadFile

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}

def is_valid_public_key(public_key: str, wallets: dict) -> bool:
    """Validate that the public key is a hexadecimal string and exists in the wallets."""
    is_format_valid = bool(re.match(r"^[a-f0-9]{66}$", public_key))  # Compressed key length
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
