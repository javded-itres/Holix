"""Public health endpoints (no API key required)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

from dishka.integrations.fastapi import DishkaRoute, FromDishka

from api.di import (
    APIKeyManager,
    CompanionManager,
    GatewayLocks,
    HostProfileName,
    ProfileAgentRegistry,
    RateLimiter,
    ResponsesStore,
    RunsStore,
    SessionsStore,
)

from config import settings

router = APIRouter(tags=["health"], route_class=DishkaRoute)


@router.get("/health")
async def health(
    registry: FromDishka[ProfileAgentRegistry],
    host_profile: FromDishka[HostProfileName],
    detailed: bool = False,
):
    agent_ready = False
    if registry is not None:
        entry = registry.entry(str(host_profile))
        if entry is not None:
            agent_ready = entry.agent._initialized
    if not detailed:
        return {"status": "ok"}
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "agent_ready": agent_ready,
        "require_auth": settings.effective_require_auth,
    }


@router.get("/v1/health")
async def health_v1():
    return {"status": "ok"}


@router.get("/health/detailed")
async def health_detailed(
    registry: FromDishka[ProfileAgentRegistry],
    companions: FromDishka[CompanionManager],
    runs_store: FromDishka[RunsStore],
    host_profile: FromDishka[HostProfileName],
):
    loaded = registry.list_loaded_profiles() if registry else []
    companion_status = {}
    if companions is not None:
        for name in loaded:
            companion_status[name] = companions.status(name)
    runs_count = 0
    if runs_store is not None:
        runs_store._gc()  # noqa: SLF001
        runs_count = len(runs_store._runs)  # noqa: SLF001
    return {
        "status": "ok",
        "host_profile": str(host_profile),
        "loaded_profiles": loaded,
        "active_runs": runs_count,
        "companions": companion_status,
        "require_auth": settings.effective_require_auth,
        "gateway_host": settings.gateway_host,
        "gateway_port": settings.gateway_port,
    }