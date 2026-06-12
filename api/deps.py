"""FastAPI dependencies for Holix gateway."""

from __future__ import annotations

import re
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import settings

# Legacy re-export for tests patching api.deps.api_key_manager
api_key_manager = None
rate_limiter = None

_SESSION_KEY_MAX = 256
_CONTROL_CHARS = re.compile(r"[\r\n\x00]")

_bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="HolixApiKey",
    bearerFormat="API key",
    description="Holix gateway API key (hx_…). Also accepted via X-API-Key header.",
)


def _api_key_from_request(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> str | None:
    if credentials is not None:
        token = credentials.credentials.strip()
        return token or None
    header = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
    if header:
        return header.strip() or None
    return None


async def _validate_key(api_key: str, *, default_limit: int) -> dict:
    from api import state

    manager = state.api_key_manager
    limiter = state.rate_limiter
    if manager is None:
        raise HTTPException(status_code=503, detail="API key manager not initialized")

    key_info = await manager.validate_api_key(api_key)
    if not key_info:
        raise HTTPException(status_code=401, detail="Invalid API key")

    limit = int(key_info.get("rate_limit") or default_limit)
    key_hash = manager.hash_key(api_key)
    if limiter and not limiter.check_rate_limit(key_hash, limit):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    return key_info


async def verify_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict:
    """Require a valid API key on all protected routes."""
    api_key = _api_key_from_request(request, credentials)
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")
    return await _validate_key(api_key, default_limit=settings.rate_limit_rpm)


async def verify_optional_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict | None:
    """Health endpoints: validate key when provided, else None."""
    api_key = _api_key_from_request(request, credentials)
    if not api_key:
        return None
    return await _validate_key(api_key, default_limit=settings.rate_limit_rpm)


async def verify_admin_key(key_info: dict = Depends(verify_api_key)) -> dict:
    """Admin routes require a valid key with admin permission."""
    from core.security.permissions import PermissionChecker

    checker = PermissionChecker(key_info["permissions"])
    if not checker.is_admin():
        raise HTTPException(status_code=403, detail="Admin permission required")
    return key_info


def _header_alias(
    helix: str | None,
    hermes: str | None,
) -> str | None:
    value = (helix or hermes or "").strip()
    return value or None


def _validate_session_key(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) > _SESSION_KEY_MAX or _CONTROL_CHARS.search(value):
        raise HTTPException(status_code=400, detail="Invalid session key header")
    return value


@dataclass(frozen=True, slots=True)
class RequestContext:
    profile: str
    conversation_id: str
    session_key: str | None
    api_key_info: dict


def resolve_profile_name(
    *,
    header_profile: str | None,
    model: str | None,
    host_profile: str,
) -> str:
    """Profile routing: X-Holix-Profile > model field > gateway host profile."""
    if header_profile and header_profile.strip():
        return header_profile.strip()
    if model and model.strip() and model.strip() not in {"holix", "holix-agent", "hermes-agent"}:
        return model.strip()
    return host_profile


async def get_registry():
    from api import state

    if state.registry is None:
        raise HTTPException(status_code=503, detail="Gateway registry not initialized")
    return state.registry