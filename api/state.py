"""Process-wide gateway state — mirror of Dishka APP-scope services.

Routers should prefer ``FromDishka[...]``. This module remains the
compatibility surface for:

* FastAPI lifespan bind/unbind
* non-request code (telegram_ops, gateway ``__getattr__``)
* tests that monkeypatch ``api.state.*``

**Lifecycle**

1. ``bind_from_container(container)`` — called once in gateway lifespan
2. services are the *same instances* Dishka returns (APP scope)
3. ``clear()`` — shutdown / test teardown
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dishka import AsyncContainer

    from core.gateway.companions import CompanionManager
    from core.gateway.locks import GatewayLocks
    from core.gateway.profile_registry import ProfileAgentRegistry
    from core.gateway.responses_store import ResponsesStore
    from core.gateway.runs_store import RunsStore
    from core.gateway.sessions_store import SessionsStore
    from core.security.auth import APIKeyManager, RateLimiter


class GatewayStateError(RuntimeError):
    """Gateway process state is missing a required service."""


@dataclass(slots=True)
class GatewayProcessState:
    """Typed process snapshot of gateway APP services."""

    host_profile: str = "default"
    registry: Any | None = None  # ProfileAgentRegistry
    companions: Any | None = None  # CompanionManager
    responses_store: Any | None = None
    runs_store: Any | None = None
    sessions_store: Any | None = None
    api_key_manager: Any | None = None
    rate_limiter: Any | None = None
    gateway_locks: Any | None = None
    # Kept for older tests / code that touch the lock directly
    _agent_request_lock: asyncio.Lock | None = None
    ready: bool = False

    @property
    def agent_request_lock(self) -> asyncio.Lock | None:
        if self.gateway_locks is not None:
            return self.gateway_locks.agent_request
        return self._agent_request_lock

    def require(self, name: str) -> Any:
        value = getattr(self, name, None)
        if value is None:
            raise GatewayStateError(
                f"Gateway state.{name} is not initialized "
                "(call bind_from_container in lifespan)"
            )
        return value

    def snapshot(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "host_profile": self.host_profile,
            "registry": self.registry is not None,
            "companions": self.companions is not None,
            "responses_store": self.responses_store is not None,
            "runs_store": self.runs_store is not None,
            "sessions_store": self.sessions_store is not None,
            "api_key_manager": self.api_key_manager is not None,
            "rate_limiter": self.rate_limiter is not None,
            "gateway_locks": self.gateway_locks is not None,
            "loaded_profiles": (
                list(self.registry.list_loaded_profiles())
                if self.registry is not None
                else []
            ),
        }


# Typed singleton (preferred for new non-request code)
process = GatewayProcessState()

# ---------------------------------------------------------------------------
# Module-level aliases — monkeypatch.setattr(api.state, "registry", …) works
# ---------------------------------------------------------------------------
host_profile: str = "default"
registry: ProfileAgentRegistry | None = None
companions: CompanionManager | None = None
responses_store: ResponsesStore | None = None
runs_store: RunsStore | None = None
sessions_store: SessionsStore | None = None
api_key_manager: APIKeyManager | None = None
rate_limiter: RateLimiter | None = None
gateway_locks: GatewayLocks | None = None
_agent_request_lock: asyncio.Lock | None = None


def _publish_module_aliases() -> None:
    """Copy ``process`` fields onto module globals for BC + monkeypatch surface."""
    g = globals()
    g["host_profile"] = process.host_profile
    g["registry"] = process.registry
    g["companions"] = process.companions
    g["responses_store"] = process.responses_store
    g["runs_store"] = process.runs_store
    g["sessions_store"] = process.sessions_store
    g["api_key_manager"] = process.api_key_manager
    g["rate_limiter"] = process.rate_limiter
    g["gateway_locks"] = process.gateway_locks
    g["_agent_request_lock"] = process.agent_request_lock


def _ingest_module_aliases() -> None:
    """Pull monkeypatched module globals back into ``process`` (tests)."""
    g = globals()
    process.host_profile = g.get("host_profile") or "default"
    process.registry = g.get("registry")
    process.companions = g.get("companions")
    process.responses_store = g.get("responses_store")
    process.runs_store = g.get("runs_store")
    process.sessions_store = g.get("sessions_store")
    process.api_key_manager = g.get("api_key_manager")
    process.rate_limiter = g.get("rate_limiter")
    process.gateway_locks = g.get("gateway_locks")
    process._agent_request_lock = g.get("_agent_request_lock")
    process.ready = process.registry is not None


def _sync_deps_module() -> None:
    """Keep legacy ``api.deps.api_key_manager`` / ``rate_limiter`` in sync."""
    try:
        import api.deps as gateway_deps

        gateway_deps.api_key_manager = process.api_key_manager
        gateway_deps.rate_limiter = process.rate_limiter
    except Exception:
        pass


async def bind_from_container(
    container: AsyncContainer,
    *,
    host_profile_name: str | None = None,
) -> GatewayProcessState:
    """Bind process state from Dishka APP container (gateway lifespan)."""
    from core.gateway.companions import CompanionManager
    from core.gateway.locks import GatewayLocks
    from core.gateway.profile_registry import ProfileAgentRegistry
    from core.gateway.responses_store import ResponsesStore
    from core.gateway.runs_store import RunsStore
    from core.gateway.sessions_store import SessionsStore
    from core.gateway.types import HostProfileName
    from core.security.auth import APIKeyManager, RateLimiter

    # Prefer typed host token when available
    host: str
    try:
        host = str(await container.get(HostProfileName))
    except Exception:
        host = (host_profile_name or "default").strip() or "default"

    process.host_profile = host
    process.registry = await container.get(ProfileAgentRegistry)
    process.companions = await container.get(CompanionManager)
    process.responses_store = await container.get(ResponsesStore)
    process.runs_store = await container.get(RunsStore)
    process.sessions_store = await container.get(SessionsStore)
    process.rate_limiter = await container.get(RateLimiter)
    process.api_key_manager = await container.get(APIKeyManager)
    process.gateway_locks = await container.get(GatewayLocks)
    process._agent_request_lock = process.gateway_locks.agent_request
    process.ready = True

    _publish_module_aliases()
    _sync_deps_module()
    return process


def clear() -> None:
    """Drop process bindings (shutdown / test isolation)."""
    process.host_profile = "default"
    process.registry = None
    process.companions = None
    process.responses_store = None
    process.runs_store = None
    process.sessions_store = None
    process.api_key_manager = None
    process.rate_limiter = None
    process.gateway_locks = None
    process._agent_request_lock = None
    process.ready = False
    _publish_module_aliases()
    _sync_deps_module()


def get() -> GatewayProcessState:
    """Return the process state singleton (re-syncs monkeypatched module attrs)."""
    _ingest_module_aliases()
    return process


def is_ready() -> bool:
    _ingest_module_aliases()
    return bool(process.ready and process.registry is not None)


# --- Require helpers (non-request code) ------------------------------------


def require_registry() -> Any:
    _ingest_module_aliases()
    return process.require("registry")


def require_companions() -> Any:
    _ingest_module_aliases()
    return process.require("companions")


def require_runs_store() -> Any:
    _ingest_module_aliases()
    return process.require("runs_store")


def require_sessions_store() -> Any:
    _ingest_module_aliases()
    return process.require("sessions_store")


def require_responses_store() -> Any:
    _ingest_module_aliases()
    return process.require("responses_store")


def require_api_key_manager() -> Any:
    _ingest_module_aliases()
    return process.require("api_key_manager")


def require_gateway_locks() -> Any:
    _ingest_module_aliases()
    locks = process.gateway_locks
    if locks is not None:
        return locks
    lock = process._agent_request_lock or globals().get("_agent_request_lock")
    if lock is None:
        raise GatewayStateError("Gateway locks are not initialized")
    from core.gateway.locks import GatewayLocks

    return GatewayLocks(agent_request=lock)


def get_host_profile() -> str:
    _ingest_module_aliases()
    if process.registry is not None:
        return getattr(process.registry, "host_profile", None) or process.host_profile or "default"
    return process.host_profile or "default"


__all__ = [
    "GatewayProcessState",
    "GatewayStateError",
    "bind_from_container",
    "clear",
    "get",
    "get_host_profile",
    "is_ready",
    "process",
    "require_api_key_manager",
    "require_companions",
    "require_gateway_locks",
    "require_registry",
    "require_responses_store",
    "require_runs_store",
    "require_sessions_store",
    # module aliases
    "host_profile",
    "registry",
    "companions",
    "responses_store",
    "runs_store",
    "sessions_store",
    "api_key_manager",
    "rate_limiter",
    "gateway_locks",
    "_agent_request_lock",
]
