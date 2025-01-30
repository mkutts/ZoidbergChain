from fastapi import Security, HTTPException, Depends
from fastapi.security.api_key import APIKeyHeader

# Example API keys (In production, store securely in a database)
API_KEYS = {
    "admin_key_123": "admin",  # Admin-level access
    "user_key_456": "user",    # Regular user access
}

api_key_header = APIKeyHeader(name="X-API-Key")

async def validate_api_key(api_key: str = Security(api_key_header)):
    """Validate the API key from the request header."""
    if api_key not in API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return API_KEYS[api_key]  # Return the user role (admin/user)
