"""Dishka integration helpers for Holix API routers.

Use::

    from dishka.integrations.fastapi import FromDishka, DishkaRoute
    from api.di import HostProfileName, ...

    router = APIRouter(..., route_class=DishkaRoute)

    @router.get("/x")
    async def endpoint(
        registry: FromDishka[ProfileAgentRegistry],
        host: FromDishka[HostProfileName],
        key_info: dict = Depends(verify_api_key),
    ):
        ...
"""

from __future__ import annotations

from core.gateway.companions import CompanionManager
from core.gateway.locks import GatewayLocks
from core.gateway.profile_registry import ProfileAgentRegistry
from core.gateway.responses_store import ResponsesStore
from core.gateway.runs_store import RunsStore
from core.gateway.sessions_store import SessionsStore
from core.gateway.types import HostProfileName
from core.profile.service import ProfileManager
from core.security.auth import APIKeyManager, RateLimiter

__all__ = [
    "APIKeyManager",
    "CompanionManager",
    "GatewayLocks",
    "HostProfileName",
    "ProfileAgentRegistry",
    "ProfileManager",
    "RateLimiter",
    "ResponsesStore",
    "RunsStore",
    "SessionsStore",
]
