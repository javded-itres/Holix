"""Mutable gateway process state (set during FastAPI lifespan)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.gateway.companions import CompanionManager
    from core.gateway.link_relay import LinkRelay
    from core.gateway.links_store import LinksStore
    from core.gateway.profile_registry import ProfileAgentRegistry
    from core.gateway.responses_store import ResponsesStore
    from core.gateway.runs_store import RunsStore
    from core.gateway.sessions_store import SessionsStore
    from core.security.auth import APIKeyManager, RateLimiter

registry: ProfileAgentRegistry | None = None
companions: CompanionManager | None = None
responses_store: ResponsesStore | None = None
runs_store: RunsStore | None = None
sessions_store: SessionsStore | None = None
links_store: LinksStore | None = None
link_relay: LinkRelay | None = None
api_key_manager: APIKeyManager | None = None
rate_limiter: RateLimiter | None = None
host_profile: str = "default"
_agent_request_lock = None  # asyncio.Lock, created in lifespan