import logging
import os

from fastapi import Security, HTTPException, Depends
from fastapi.security.api_key import APIKeyHeader
from starlette.status import HTTP_403_FORBIDDEN

logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

logger.debug(
    "API key configuration loaded: admin_configured=%s user_configured=%s",
    bool(os.getenv("ADMIN_API_KEY")),
    bool(os.getenv("USER_API_KEY")),
)

API_KEYS = {
    os.getenv("ADMIN_API_KEY"): "admin",
    os.getenv("USER_API_KEY"): "user",
}

async def validate_api_key(api_key: str = Security(api_key_header)):
    """Validate API Key from request headers."""
    if not api_key or api_key not in API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return API_KEYS[api_key]  # Return user role (admin/user)
