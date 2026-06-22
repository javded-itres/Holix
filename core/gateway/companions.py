"""Per-profile Telegram and cron companions (start/stop/reload without uvicorn restart)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class CompanionState:
    profile: str
    telegram_task: asyncio.Task[Any] | None = None
    max_task: asyncio.Task[Any] | None = None


class CompanionManager:
    """Lifecycle for profile-scoped background companions."""

    def __init__(self) -> None:
        self._states: dict[str, CompanionState] = {}
        self._global_cron_task: asyncio.Task[Any] | None = None

    def _cron_running(self) -> bool:
        return bool(self._global_cron_task and not self._global_cron_task.done())

    def status(self, profile: str) -> dict[str, Any]:
        state = self._states.get(profile)
        return {
            "profile": profile,
            "cron_running": self._cron_running(),
            "telegram_running": bool(
                state and state.telegram_task and not state.telegram_task.done()
            ),
            "max_polling_running": bool(
                state and state.max_task and not state.max_task.done()
            ),
        }

    async def start_cron(self, profile: str) -> None:
        await self.ensure_global_cron()

    async def ensure_global_cron(self) -> None:
        if self._cron_running():
            return
        from core.cron.scheduler import GlobalCronScheduler

        async def _run() -> None:
            await GlobalCronScheduler().run_forever()

        self._global_cron_task = asyncio.create_task(_run(), name="holix-cron-global")

    async def stop_cron(self, profile: str) -> None:
        from core.cron.discovery import invalidate_profile

        invalidate_profile(profile)

    async def stop_global_cron(self) -> None:
        if self._global_cron_task is None:
            return
        self._global_cron_task.cancel()
        try:
            await self._global_cron_task
        except asyncio.CancelledError:
            pass
        self._global_cron_task = None

    async def start_telegram(self, profile: str) -> None:
        await self.stop_telegram(profile)
        from cli.services.supervisor import telegram_should_start

        if not telegram_should_start(profile):
            return
        from integrations.telegram.bot import HolixTelegramBot

        state = self._states.setdefault(profile, CompanionState(profile=profile))

        async def _run() -> None:
            bot = HolixTelegramBot(profile=profile)
            await bot.run_polling()

        state.telegram_task = asyncio.create_task(
            _run(),
            name=f"holix-telegram-{profile}",
        )

    async def stop_telegram(self, profile: str) -> None:
        state = self._states.get(profile)
        if state is None or state.telegram_task is None:
            return
        state.telegram_task.cancel()
        try:
            await state.telegram_task
        except asyncio.CancelledError:
            pass
        state.telegram_task = None

    async def start_max(self, profile: str) -> None:
        await self.stop_max(profile)
        from integrations.max.gateway_routes import max_should_poll

        if not max_should_poll(profile):
            return
        from integrations.max.config import load_max_settings
        from integrations.max.polling import run_polling

        state = self._states.setdefault(profile, CompanionState(profile=profile))

        async def _run() -> None:
            await run_polling(load_max_settings(profile), profile=profile)

        state.max_task = asyncio.create_task(_run(), name=f"holix-max-{profile}")

    async def stop_max(self, profile: str) -> None:
        state = self._states.get(profile)
        if state is None or state.max_task is None:
            return
        state.max_task.cancel()
        try:
            await state.max_task
        except asyncio.CancelledError:
            pass
        state.max_task = None

    async def reload(self, profile: str) -> dict[str, Any]:
        await self.stop_cron(profile)
        await self.stop_telegram(profile)
        await self.stop_max(profile)
        await self.start_cron(profile)
        await self.start_telegram(profile)
        await self.start_max(profile)
        return self.status(profile)

    async def shutdown_all(self) -> None:
        await self.stop_global_cron()
        for profile in list(self._states):
            await self.stop_telegram(profile)
            await self.stop_max(profile)