"""FastAPI dependencies for Helix gateway."""

from __future__ import annotations

from fastapi import Header, HTTPException

from config import settings

# Set by gateway lifespan
api_key_manager = None
rate_limiter = None


def _extract_api_key(
    authorization: str | None,
    x_api_key: str | None,
) -> str | None:
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:]
    if x_api_key:
        return x_api_key
    return None


async def _validate_key(api_key: str, *, default_limit: int) -> dict:
    if api_key_manager is None:
        raise HTTPException(status_code=503, detail="API key manager not initialized")

    key_info = await api_key_manager.validate_api_key(api_key)
    if not key_info:
        raise HTTPException(status_code=401, detail="Invalid API key")

    limit = int(key_info.get("rate_limit") or default_limit)
    key_hash = api_key_manager.hash_key(api_key)
    if rate_limiter and not rate_limiter.check_rate_limit(key_hash, limit):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    return key_info


async def verify_api_key(
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None),
) -> dict | None:
    """Optional auth for public /v1 routes when require_auth is disabled."""
    if not settings.effective_require_auth:
        api_key = _extract_api_key(authorization, x_api_key)
        if not api_key:
            return None
        return await _validate_key(api_key, default_limit=settings.rate_limit_rpm)

    api_key = _extract_api_key(authorization, x_api_key)
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")
    return await _validate_key(api_key, default_limit=settings.rate_limit_rpm)


async def verify_admin_key(
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None),
) -> dict:
    """Admin routes always require a valid admin API key."""
    from core.security.permissions import PermissionChecker

    api_key = _extract_api_key(authorization, x_api_key)
    if not api_key:
        raise HTTPException(status_code=401, detail="Admin API key required")

    key_info = await _validate_key(api_key, default_limit=settings.admin_rate_limit_rpm)
    checker = PermissionChecker(key_info["permissions"])
    if not checker.is_admin():
        raise HTTPException(status_code=403, detail="Admin permission required")
    return key_info