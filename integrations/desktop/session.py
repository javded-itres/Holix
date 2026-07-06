"""Holix Studio server session (one profile, agent, active runs)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from integrations.desktop.event_bridge import agent_event_to_studio_message

logger = logging.getLogger(__name__)

BroadcastFn = Callable[[dict[str, Any]], Awaitable[None]]


class StudioSession:
    """Holds agent state and runs user messages for Studio clients."""

    def __init__(self, profile: str, *, conversation_id: str = "studio") -> None:
        self.profile = profile
        self.conversation_id = conversation_id
        self.agent: Any | None = None
        self._init_lock = asyncio.Lock()
        self._run_task: asyncio.Task | None = None
        self._broadcast: BroadcastFn | None = None

    def set_broadcast(self, fn: BroadcastFn) -> None:
        self._broadcast = fn

    async def ensure_agent(self) -> Any:
        async with self._init_lock:
            if self.agent is not None:
                return self.agent
            from integrations.desktop.agent_setup import create_studio_agent

            self.agent = await create_studio_agent(self.profile)
            return self.agent

    async def handle_client_message(self, message: dict[str, Any]) -> None:
        msg_type = str(message.get("type") or "")
        if msg_type == "user_message":
            text = str(message.get("text") or "").strip()
            if not text:
                return
            conv = str(message.get("conversation_id") or self.conversation_id)
            await self._start_run(text, conv)
            return
        if msg_type == "slash":
            command = str(message.get("command") or "").strip()
            if command in {"/stop", "stop"}:
                await self.stop_run()
            return
        if msg_type == "ping":
            await self._emit({"type": "pong"})

    async def stop_run(self) -> None:
        task = self._run_task
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._run_task = None
        await self._emit({"type": "run_stopped"})

    async def _start_run(self, text: str, conversation_id: str) -> None:
        await self.stop_run()
        agent = await self.ensure_agent()
        self._run_task = asyncio.create_task(
            self._run_agent(agent, text, conversation_id),
            name=f"studio-run-{self.profile}",
        )

    async def _run_agent(self, agent: Any, text: str, conversation_id: str) -> None:
        from core.runtime.executor import run_holix

        await self._emit({"type": "run_started", "conversation_id": conversation_id})
        try:
            async for event in run_holix(agent, text, conversation_id, stream=True):
                await self._emit(agent_event_to_studio_message(event))
        except asyncio.CancelledError:
            await self._emit({"type": "run_cancelled"})
            raise
        except Exception as e:
            logger.exception("Studio agent run failed")
            await self._emit({"type": "error", "message": str(e)})
        finally:
            self._run_task = None

    async def _emit(self, payload: dict[str, Any]) -> None:
        if self._broadcast is None:
            return
        await self._broadcast(payload)

    async def shutdown(self) -> None:
        await self.stop_run()
        agent = self.agent
        self.agent = None
        if agent is not None:
            close = getattr(agent, "close", None)
            if callable(close):
                maybe = close()
                if asyncio.iscoroutine(maybe):
                    await maybe