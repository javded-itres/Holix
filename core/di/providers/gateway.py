"""Gateway process services (registry, stores, auth) — APP scope."""

from __future__ import annotations

import os

from dishka import Provider, Scope, provide

from core.gateway.companions import CompanionManager
from core.gateway.locks import GatewayLocks
from core.gateway.profile_registry import ProfileAgentRegistry
from core.gateway.responses_store import ResponsesStore
from core.gateway.runs_store import RunsStore
from core.gateway.sessions_store import SessionsStore
from core.gateway.types import HostProfileName
from core.profile.service import ProfileManager
from core.security.auth import APIKeyManager, RateLimiter


class GatewayServicesProvider(Provider):
    """FastAPI gateway singletons (one process, many profiles)."""

    scope = Scope.APP

    @provide(scope=Scope.APP)
    def host_profile_name(self) -> HostProfileName:
        return HostProfileName(
            (os.getenv("HOLIX_PROFILE") or "default").strip() or "default"
        )

    @provide(scope=Scope.APP)
    def profile_manager(self) -> ProfileManager:
        """Shared profile store for /api/holix management routes."""
        return ProfileManager()

    @provide(scope=Scope.APP)
    def profile_registry(self, host_profile_name: HostProfileName) -> ProfileAgentRegistry:
        return ProfileAgentRegistry(str(host_profile_name))

    @provide(scope=Scope.APP)
    def companions(self) -> CompanionManager:
        return CompanionManager()

    @provide(scope=Scope.APP)
    def responses_store(self) -> ResponsesStore:
        return ResponsesStore()

    @provide(scope=Scope.APP)
    def runs_store(self) -> RunsStore:
        return RunsStore()

    @provide(scope=Scope.APP)
    def sessions_store(self) -> SessionsStore:
        return SessionsStore()

    @provide(scope=Scope.APP)
    def rate_limiter(self) -> RateLimiter:
        return RateLimiter()

    @provide(scope=Scope.APP)
    def api_key_manager(self) -> APIKeyManager:
        from core.paths import resolve_api_keys_db_path

        return APIKeyManager(str(resolve_api_keys_db_path()))

    @provide(scope=Scope.APP)
    def gateway_locks(self) -> GatewayLocks:
        return GatewayLocks()