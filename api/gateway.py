"""Holix API Gateway — multi-profile Hermes-compatible HTTP API."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from core.di.container import create_async_container, resolve_gateway_runtime_config
from core.gateway.companions import CompanionManager
from core.gateway.profile_registry import ProfileAgentRegistry
from core.gateway.responses_store import ResponsesStore
from core.gateway.runs_store import RunsStore
from core.gateway.sessions_store import SessionsStore
from core.security.auth import APIKeyManager, RateLimiter
from dishka.integrations.fastapi import setup_dishka
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from api import state
from api.deps import verify_admin_key
from api.docs_chat import router as docs_chat_router
from api.routers import (
    admin,
    health,
    hermes_jobs,
    hermes_sessions,
    hermes_v1,
    holix_config,
    holix_global,
    holix_mcp,
    holix_models,
    holix_profiles,
    holix_skills,
    holix_telegram,
    legacy_v1,
)
from config import settings

_dishka_container = create_async_container(resolve_gateway_runtime_config())


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize multi-profile registry, stores, and API key DB."""
    from core.env_loader import init_holix_home
    from core.paths import ensure_profile_memory_dirs, resolve_api_keys_db_path

    init_holix_home()

    if settings.is_production and not settings.api_key_pepper.strip():
        raise RuntimeError("HOLIX_API_KEY_PEPPER is required when HOLIX_ENV=production")

    host_profile = (os.getenv("HOLIX_PROFILE") or "default").strip() or "default"
    state.host_profile = host_profile
    state.registry = ProfileAgentRegistry(host_profile)
    state.companions = CompanionManager()
    state.responses_store = ResponsesStore()
    state.runs_store = RunsStore()
    state.sessions_store = SessionsStore()
    state.rate_limiter = RateLimiter()
    state._agent_request_lock = asyncio.Lock()

    import api.deps as gateway_deps

    state.api_key_manager = APIKeyManager(str(resolve_api_keys_db_path()))
    await state.api_key_manager.initialize_db()
    gateway_deps.api_key_manager = state.api_key_manager
    gateway_deps.rate_limiter = state.rate_limiter

    ensure_profile_memory_dirs(host_profile)
    await state.registry.get_agent(host_profile)
    await state.companions.start_cron(host_profile)
    await state.companions.start_telegram(host_profile)

    yield

    if state.companions is not None:
        await state.companions.shutdown_all()
    if state.registry is not None:
        await state.registry.shutdown()
    await app.state.dishka_container.close()


app = FastAPI(
    title="Holix API",
    description="Multi-profile AI agent gateway (Hermes-compatible + Holix management)",
    version="0.2.0",
    lifespan=lifespan,
)

app.state.dishka_container = _dishka_container
setup_dishka(container=_dishka_container, app=app)

_origins = settings.cors_origin_list()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(health.router)
app.include_router(hermes_v1.router)
app.include_router(legacy_v1.router)
app.include_router(hermes_jobs.router)
app.include_router(hermes_sessions.router)
app.include_router(admin.router)
app.include_router(holix_profiles.router)
app.include_router(holix_models.router)
app.include_router(holix_skills.router)
app.include_router(holix_mcp.router)
app.include_router(holix_config.router)
app.include_router(holix_global.router)
app.include_router(holix_telegram.router)
app.include_router(docs_chat_router)


@app.get("/")
async def root():
    registry = state.registry
    loaded = registry.list_loaded_profiles() if registry else []
    return {
        "name": "Holix API",
        "version": "0.2.0",
        "status": "running",
        "host_profile": state.host_profile,
        "loaded_profiles": loaded,
        "require_auth": True,
    }


@app.get("/metrics")
async def prometheus_metrics_public(
    _admin: dict = Depends(verify_admin_key),
):
    if not settings.enable_prometheus_metrics:
        raise HTTPException(status_code=404, detail="Metrics disabled")
    from core.monitoring import metrics as global_metrics

    from api.prometheus import format_prometheus

    return PlainTextResponse(
        format_prometheus(global_metrics),
        media_type="text/plain; version=0.0.4",
    )


def __getattr__(name: str):
    """Backward compatibility for ``api.gateway.agent`` in tests."""
    if name == "agent":
        reg = state.registry
        if reg is None:
            return None
        entry = reg.entry(state.host_profile)
        return entry.agent if entry else None
    if name == "api_key_manager":
        return state.api_key_manager
    if name == "rate_limiter":
        return state.rate_limiter
    raise AttributeError(name)


