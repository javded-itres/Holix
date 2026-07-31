"""Holix API Gateway — multi-profile Hermes-compatible HTTP API."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from core.di.container import create_async_container, resolve_gateway_runtime_config
from core.gateway.profile_registry import ProfileAgentRegistry
from core.gateway.types import HostProfileName
from dishka.integrations.fastapi import FromDishka, inject, setup_dishka
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from integrations.bootstrap import register_integration_hooks
from integrations.max.gateway_routes import (
    init_max_webhook,
    max_gateway_state,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from api import state
from api.deps import verify_admin_key
from api.docs_chat import router as docs_chat_router
from api.routers import (
    a2a,
    admin,
    health,
    hermes_jobs,
    hermes_sessions,
    hermes_v1,
    holix_config,
    holix_global,
    holix_launch,
    holix_max,
    holix_mcp,
    holix_models,
    holix_profiles,
    holix_skills,
    holix_telegram,
    legacy_v1,
)
from config import settings

register_integration_hooks()

_dishka_container = create_async_container(
    resolve_gateway_runtime_config(),
    gateway=True,
)


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
    from core.paths import ensure_profile_memory_dirs

    init_holix_home()

    if settings.is_production and not settings.api_key_pepper.strip():
        raise RuntimeError("HOLIX_API_KEY_PEPPER is required when HOLIX_ENV=production")

    container = app.state.dishka_container
    host_profile = (os.getenv("HOLIX_PROFILE") or "default").strip() or "default"

    # Bind process state to the same APP-scope instances Dishka owns.
    gw = await state.bind_from_container(container, host_profile_name=host_profile)
    await gw.api_key_manager.initialize_db()

    supervised = os.getenv("HOLIX_GATEWAY_SUPERVISOR", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    async def _warm_gateway() -> None:
        ensure_profile_memory_dirs(gw.host_profile)
        await gw.registry.get_agent(gw.host_profile)
        if not supervised:
            await gw.companions.start_cron(gw.host_profile)
            await gw.companions.start_telegram(gw.host_profile)
            await gw.companions.start_max(gw.host_profile)

    asyncio.create_task(_warm_gateway(), name="holix-gateway-warm")

    await init_max_webhook(os.getenv("HELIX_PROFILE", "default"))

    yield

    if gw.companions is not None:
        await gw.companions.shutdown_all()
    if gw.registry is not None:
        await gw.registry.shutdown()
    state.clear()
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
app.include_router(a2a.router)
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
app.include_router(holix_launch.router)
app.include_router(holix_telegram.router)
app.include_router(holix_max.router)
app.include_router(docs_chat_router)

from core.extensions.registry import mount_gateway_extensions  # noqa: E402

mount_gateway_extensions(app)


@app.get("/")
@inject
async def root(
    registry: FromDishka[ProfileAgentRegistry],
    host_profile: FromDishka[HostProfileName],
):
    loaded = registry.list_loaded_profiles() if registry else []
    return {
        "name": "Holix API",
        "version": "0.2.0",
        "status": "running",
        "host_profile": str(host_profile),
        "loaded_profiles": loaded,
        "require_auth": settings.effective_require_auth,
        "max_webhook": (
            (max_state := max_gateway_state()) is not None and max_state.subscribed
        ),
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
    gw = state.get()
    if name == "agent":
        reg = gw.registry
        if reg is None:
            return None
        entry = reg.entry(gw.host_profile)
        return entry.agent if entry else None
    if name == "api_key_manager":
        return gw.api_key_manager
    if name == "rate_limiter":
        return gw.rate_limiter
    raise AttributeError(name)


