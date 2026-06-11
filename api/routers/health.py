"""Public health endpoints (no API key required)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

from api import state
from config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    registry = state.registry
    agent_ready = False
    if registry is not None:
        entry = registry.entry(state.host_profile)
        if entry is not None:
            agent_ready = entry.agent._initialized
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "agent_ready": agent_ready,
        "require_auth": True,
    }


@router.get("/v1/health")
async def health_v1():
    return {"status": "ok"}


@router.get("/health/detailed")
async def health_detailed():
    registry = state.registry
    loaded = registry.list_loaded_profiles() if registry else []
    companion_status = {}
    if state.companions is not None:
        for name in loaded:
            companion_status[name] = state.companions.status(name)
    runs_count = 0
    if state.runs_store is not None:
        state.runs_store._gc()  # noqa: SLF001
        runs_count = len(state.runs_store._runs)  # noqa: SLF001
    return {
        "status": "ok",
        "host_profile": state.host_profile,
        "loaded_profiles": loaded,
        "active_runs": runs_count,
        "companions": companion_status,
        "require_auth": True,
        "gateway_host": settings.gateway_host,
        "gateway_port": settings.gateway_port,
    }