"""Per-profile Telegram and cron companions (start/stop/reload without uvicorn restart)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class CompanionState:
    profile: str
    cron_task: asyncio.Task[Any] | None = None
    telegram_task: asyncio.Task[Any] | None = None


class CompanionManager:
    """Lifecycle for profile-scoped background companions."""

    def __init__(self) -> None:
        self._states: dict[str, CompanionState] = {}

    def status(self, profile: str) -> dict[str, Any]:
        state = self._states.get(profile)
        return {
            "profile": profile,
            "cron_running": bool(state and state.cron_task and not state.cron_task.done()),
            "telegram_running": bool(
                state and state.telegram_task and not state.telegram_task.done()
            ),
        }

    async def start_cron(self, profile: str) -> None:
        await self.stop_cron(profile)
        from core.cron.scheduler import CronScheduler

        state = self._states.setdefault(profile, CompanionState(profile=profile))

        async def _run() -> None:
            await CronScheduler(profile).run_forever()

        state.cron_task = asyncio.create_task(_run(), name=f"holix-cron-{profile}")

    async def stop_cron(self, profile: str) -> None:
        state = self._states.get(profile)
        if state is None or state.cron_task is None:
            return
        state.cron_task.cancel()
        try:
            await state.cron_task
        except asyncio.CancelledError:
            pass
        state.cron_task = None

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

    async def reload(self, profile: str) -> dict[str, Any]:
        await self.stop_cron(profile)
        await self.stop_telegram(profile)
        await self.start_cron(profile)
        await self.start_telegram(profile)
        return self.status(profile)

    async def shutdown_all(self) -> None:
        for profile in list(self._states):
            await self.stop_cron(profile)
            await self.stop_telegram(profile)