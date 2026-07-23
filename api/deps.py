"""FastAPI dependencies for Holix gateway (Dishka-backed where possible)."""

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


async def _dishka_get[T](request: Request, dep_type: type[T]) -> T | None:
    container = getattr(request.app.state, "dishka_container", None)
    if container is None:
        return None
    try:
        return await container.get(dep_type)
    except Exception:
        return None


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


async def _validate_key(
    api_key: str,
    *,
    default_limit: int,
    request: Request | None = None,
) -> dict:
    """Validate API key via Dishka APP scope; state only when container is absent.

    Request path: ``request.app.state.dishka_container`` (same instances as lifespan).
    Non-request / legacy tests without app: fall back to ``api.state`` mirror.
    """
    from core.security.auth import APIKeyManager, RateLimiter

    from api import state

    manager: APIKeyManager | None = None
    limiter: RateLimiter | None = None
    if request is not None:
        manager = await _dishka_get(request, APIKeyManager)
        limiter = await _dishka_get(request, RateLimiter)
    if manager is None:
        # Container missing (unit tests / non-HTTP) — use process mirror.
        gw = state.get()
        manager = gw.api_key_manager
        if limiter is None:
            limiter = gw.rate_limiter
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


_BOOTSTRAP_KEY_INFO: dict = {
    "permissions": ["read", "write", "execute", "admin"],
    "rate_limit": 0,
    "bootstrap": True,
}


async def verify_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict:
    """Require a valid API key when HOLIX_REQUIRE_AUTH is enabled."""
    api_key = _api_key_from_request(request, credentials)
    if not api_key:
        if not settings.effective_require_auth:
            return dict(_BOOTSTRAP_KEY_INFO)
        raise HTTPException(status_code=401, detail="API key required")
    return await _validate_key(api_key, default_limit=settings.rate_limit_rpm, request=request)


async def verify_optional_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict | None:
    """Health endpoints: validate key when provided, else None."""
    api_key = _api_key_from_request(request, credentials)
    if not api_key:
        return None
    return await _validate_key(api_key, default_limit=settings.rate_limit_rpm, request=request)


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


def _sanitize_profile_name(name: str) -> str:
    from core.profile import ProfileNotFoundError, validate_profile_name_for_env

    try:
        return validate_profile_name_for_env(name)
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def resolve_profile_name(
    *,
    header_profile: str | None,
    model: str | None,
    host_profile: str,
) -> str:
    """Profile routing: X-Holix-Profile > model field > gateway host profile."""
    if header_profile and header_profile.strip():
        return _sanitize_profile_name(header_profile.strip())
    if model and model.strip() and model.strip() not in {"holix", "holix-agent", "hermes-agent"}:
        return _sanitize_profile_name(model.strip())
    return _sanitize_profile_name(host_profile)


def ensure_resource_profile(resource_profile: str, expected_profile: str) -> None:
    """Reject cross-profile access (returns 404 to avoid resource enumeration)."""
    if resource_profile != expected_profile:
        raise HTTPException(status_code=404, detail="Not found")


def _state_fallback(name: str):
    from api import state

    return getattr(state.get(), name, None)


async def get_registry(request: Request):
    """Profile agent registry — Dishka first; state only if container has no binding."""
    from core.gateway.profile_registry import ProfileAgentRegistry

    reg = await _dishka_get(request, ProfileAgentRegistry)
    if reg is not None:
        return reg
    reg = _state_fallback("registry")
    if reg is None:
        raise HTTPException(status_code=503, detail="Gateway registry not initialized")
    return reg


async def get_registry_optional(request: Request):
    """Like get_registry but returns None when not ready (health endpoints)."""
    try:
        return await get_registry(request)
    except HTTPException:
        return _state_fallback("registry")


async def get_companions(request: Request):
    from core.gateway.companions import CompanionManager

    val = await _dishka_get(request, CompanionManager)
    if val is not None:
        return val
    val = _state_fallback("companions")
    if val is None:
        raise HTTPException(status_code=503, detail="Companions not initialized")
    return val


async def get_companions_optional(request: Request):
    try:
        return await get_companions(request)
    except HTTPException:
        return _state_fallback("companions")


async def get_runs_store(request: Request):
    from core.gateway.runs_store import RunsStore

    val = await _dishka_get(request, RunsStore)
    if val is not None:
        return val
    val = _state_fallback("runs_store")
    if val is None:
        raise HTTPException(status_code=503, detail="Runs store not initialized")
    return val


async def get_runs_store_optional(request: Request):
    try:
        return await get_runs_store(request)
    except HTTPException:
        return _state_fallback("runs_store")


async def get_sessions_store(request: Request):
    from core.gateway.sessions_store import SessionsStore

    val = await _dishka_get(request, SessionsStore)
    if val is not None:
        return val
    val = _state_fallback("sessions_store")
    if val is None:
        raise HTTPException(status_code=503, detail="Sessions store not initialized")
    return val


async def get_responses_store(request: Request):
    from core.gateway.responses_store import ResponsesStore

    val = await _dishka_get(request, ResponsesStore)
    if val is not None:
        return val
    val = _state_fallback("responses_store")
    if val is None:
        raise HTTPException(status_code=503, detail="Responses store not initialized")
    return val


async def get_api_key_manager(request: Request):
    from core.security.auth import APIKeyManager

    val = await _dishka_get(request, APIKeyManager)
    if val is not None:
        return val
    val = _state_fallback("api_key_manager")
    if val is None:
        raise HTTPException(status_code=503, detail="API key manager not initialized")
    return val


async def get_rate_limiter(request: Request):
    from core.security.auth import RateLimiter

    val = await _dishka_get(request, RateLimiter)
    if val is not None:
        return val
    return _state_fallback("rate_limiter")


async def get_gateway_locks(request: Request):
    from core.gateway.locks import GatewayLocks

    from api import state

    val = await _dishka_get(request, GatewayLocks)
    if val is not None:
        return val
    try:
        return state.require_gateway_locks()
    except state.GatewayStateError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


async def get_host_profile(request: Request) -> str:
    from core.gateway.types import HostProfileName

    from api import state

    host = await _dishka_get(request, HostProfileName)
    if host is not None:
        return str(host)
    try:
        registry = await get_registry(request)
        return getattr(registry, "host_profile", None) or state.get_host_profile()
    except HTTPException:
        return state.get_host_profile()
