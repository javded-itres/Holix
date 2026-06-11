"""Lazy in-memory Helix agents keyed by profile name."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dishka import AsyncContainer

    from core.agent import HelixAgent


@dataclass(slots=True)
class ProfileEntry:
    profile: str
    agent: HelixAgent
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

    async def get_agent(self, profile: str | None = None) -> HelixAgent:
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

    async def shutdown(self) -> None:
        async with self._init_lock:
            for name in list(self._entries):
                await self._dispose_entry(self._entries.pop(name))

    async def _create_entry(self, profile: str) -> ProfileEntry:
        from cli.core import init_profile

        from core.agent_events import create_compatibility_print_handler
        from core.di.container import create_agent, resolve_runtime_config
        from core.env_loader import bootstrap_profile_env

        bootstrap_profile_env(profile)
        runtime = resolve_runtime_config(init_profile(profile))
        compat = create_compatibility_print_handler()
        agent, container = await create_agent(
            runtime,
            event_listeners=[compat],
            enable_monitoring=True,
        )
        return ProfileEntry(profile=profile, agent=agent, container=container)

    async def _dispose_entry(self, entry: ProfileEntry) -> None:
        try:
            await entry.container.close()
        except Exception:
            pass