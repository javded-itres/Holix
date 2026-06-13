"""Lazy in-memory Holix agents keyed by profile name."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dishka import AsyncContainer

    from core.agent import HolixAgent


@dataclass(slots=True)
class ProfileEntry:
    profile: str
    agent: HolixAgent
    container: AsyncContainer
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    initialized_at: float = field(default_factory=time.time)


class ProfileAgentRegistry:
    """One gateway process, many profile-scoped agents (lazy init)."""

    def __init__(self, host_profile: str = "default") -> None:
        self.host_profile = (host_profile or "default").strip() or "default"
        self._entries: dict[str, ProfileEntry] = {}
        self._init_lock = asyncio.Lock()

    def list_loaded_profiles(self) -> list[str]:
        return sorted(self._entries)

    def entry(self, profile: str) -> ProfileEntry | None:
        name = (profile or self.host_profile).strip() or self.host_profile
        return self._entries.get(name)

    async def get_agent(self, profile: str | None = None) -> HolixAgent:
        name = (profile or self.host_profile).strip() or self.host_profile
        existing = self._entries.get(name)
        if existing is not None and existing.agent._initialized:
            return existing.agent

        async with self._init_lock:
            existing = self._entries.get(name)
            if existing is not None and existing.agent._initialized:
                return existing.agent
            if existing is not None:
                await self._dispose_entry(existing)
                self._entries.pop(name, None)
            entry = await self._create_entry(name)
            self._entries[name] = entry
            return entry.agent

    async def reload(self, profile: str) -> dict[str, str]:
        """Drop and recreate in-memory agent for a profile."""
        name = profile.strip()
        async with self._init_lock:
            existing = self._entries.pop(name, None)
            if existing is not None:
                await self._dispose_entry(existing)
            entry = await self._create_entry(name)
            self._entries[name] = entry
        return {"profile": name, "status": "reloaded"}

    async def unload(self, profile: str) -> dict[str, str]:
        """Remove a profile agent from memory without recreating it."""
        name = profile.strip()
        async with self._init_lock:
            existing = self._entries.pop(name, None)
            if existing is not None:
                await self._dispose_entry(existing)
        return {"profile": name, "status": "unloaded"}

    async def shutdown(self) -> None:
        async with self._init_lock:
            for name in list(self._entries):
                await self._dispose_entry(self._entries.pop(name))

    async def _create_entry(self, profile: str) -> ProfileEntry:
        from cli.core import init_profile

        from core.agent_events import create_compatibility_print_handler
        from core.crypto.gateway_crypto import require_gateway_profile_unlock
        from core.di.container import create_agent, resolve_runtime_config
        from core.env_loader import bootstrap_profile_env
        from core.paths import ensure_profile_memory_dirs

        def _prepare_runtime() -> Any:
            bootstrap_profile_env(profile)
            require_gateway_profile_unlock(profile)
            ensure_profile_memory_dirs(profile)
            return resolve_runtime_config(init_profile(profile, prompt_key=False))

        runtime = await asyncio.to_thread(_prepare_runtime)
        compat = create_compatibility_print_handler()
        agent, container = await create_agent(
            runtime,
            event_listeners=[compat],
            enable_monitoring=True,
        )
        return ProfileEntry(profile=profile, agent=agent, container=container)

    async def _dispose_entry(self, entry: ProfileEntry) -> None:
        from core.crypto.gateway_crypto import release_gateway_profile_unlock

        try:
            await entry.container.close()
        except Exception:
            pass
        release_gateway_profile_unlock(entry.profile)