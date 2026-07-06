"""Holix Studio server session (one profile, agent, active runs)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from core.agent_events import AgentEvent, EventType
from integrations.desktop.event_bridge import agent_event_to_studio_message

logger = logging.getLogger(__name__)

BroadcastFn = Callable[[dict[str, Any]], Awaitable[None]]

# Live tokens/tool output are emitted on the agent event bus (see react_node).
# The run_holix generator still yields bootstrap thinking, max-steps, and errors.
_GENERATOR_ONLY_TYPES = frozenset(
    {
        EventType.THINKING,
        EventType.MAX_STEPS_REACHED,
        EventType.ERROR,
    }
)


class StudioSession:
    """Holds agent state and runs user messages for Studio clients."""

    def __init__(self, profile: str, *, conversation_id: str = "studio") -> None:
        self.profile = profile
        self.conversation_id = conversation_id
        self.agent: Any | None = None
        self._init_lock = asyncio.Lock()
        self._run_lock = asyncio.Lock()
        self._run_task: asyncio.Task | None = None
        self._broadcast: BroadcastFn | None = None
        self._event_forwarder: Callable[[AgentEvent], Awaitable[None]] | None = None

    def set_broadcast(self, fn: BroadcastFn) -> None:
        self._broadcast = fn

    async def ensure_agent(self) -> Any:
        async with self._init_lock:
            if self.agent is not None:
                return self.agent
            from integrations.desktop.agent_setup import build_studio_agent

            agent = build_studio_agent(self.profile)
            self._attach_event_forwarder(agent)
            await agent.initialize(mcp_ready_timeout=5.0, defer_skill_index=True)
            self.agent = agent
            return self.agent

    def _attach_event_forwarder(self, agent: Any) -> None:
        if self._event_forwarder is not None:
            return

        async def forward_event(event: AgentEvent) -> None:
            await self._emit(agent_event_to_studio_message(event))

        self._event_forwarder = forward_event
        agent.events.subscribe(forward_event)

    def _detach_event_forwarder(self) -> None:
        agent = self.agent
        forwarder = self._event_forwarder
        if agent is not None and forwarder is not None:
            agent.events.unsubscribe(forwarder)
        self._event_forwarder = None

    async def handle_client_message(self, message: dict[str, Any]) -> None:
        try:
            await self._dispatch_client_message(message)
        except Exception as e:
            logger.exception("Studio client message failed")
            await self._emit({"type": "error", "message": str(e)})

    async def _dispatch_client_message(self, message: dict[str, Any]) -> None:
        msg_type = str(message.get("type") or "")
        if msg_type == "user_message":
            text = str(message.get("text") or "").strip()
            if not text:
                return
            if text.startswith("/"):
                await self._dispatch_client_message(
                    {"type": "slash", "command": text.split()[0]}
                )
                return
            conv = str(message.get("conversation_id") or self.conversation_id)
            await self._start_run(text, conv)
            return
        if msg_type == "slash":
            command = str(message.get("command") or "").strip()
            if command in {"/stop", "stop"}:
                await self.stop_run(notify=True)
            return
        if msg_type == "ping":
            await self._emit({"type": "pong"})

    async def stop_run(self, *, notify: bool = False) -> bool:
        """Cancel the active run. Returns True if a run was in progress."""
        task = self._run_task
        cancelled = bool(task and not task.done())
        if cancelled:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if self._run_task is task:
            self._run_task = None
        if notify and cancelled:
            await self._emit({"type": "run_stopped"})
        return cancelled

    async def _start_run(self, text: str, conversation_id: str) -> None:
        async with self._run_lock:
            if self._run_task and not self._run_task.done():
                await self._emit(
                    {
                        "type": "error",
                        "message": "Дождитесь ответа или нажмите Stop.",
                    }
                )
                return
            self._run_task = asyncio.create_task(
                self._run_agent_job(text, conversation_id),
                name=f"studio-run-{self.profile}",
            )

    async def _run_agent_job(self, text: str, conversation_id: str) -> None:
        this_task = asyncio.current_task()
        await self._emit({"type": "run_started", "conversation_id": conversation_id})
        try:
            agent = await self.ensure_agent()
            await self._run_agent(agent, text, conversation_id)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("Studio agent job failed")
            await self._emit({"type": "error", "message": str(e)})
        finally:
            if self._run_task is this_task:
                self._run_task = None

    async def _run_agent(self, agent: Any, text: str, conversation_id: str) -> None:
        from core.runtime.executor import run_holix

        completed = False
        try:
            async for event in run_holix(agent, text, conversation_id, stream=True):
                if event.type in _GENERATOR_ONLY_TYPES:
                    await self._emit(agent_event_to_studio_message(event))
            completed = True
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("Studio agent run failed")
            await self._emit({"type": "error", "message": str(e)})
        finally:
            if completed:
                await asyncio.sleep(0)
                await self._emit({"type": "run_finished", "conversation_id": conversation_id})

    async def _emit(self, payload: dict[str, Any]) -> None:
        if self._broadcast is None:
            return
        await self._broadcast(payload)

    async def shutdown(self) -> None:
        await self.stop_run(notify=False)
        self._detach_event_forwarder()
        agent = self.agent
        self.agent = None
        if agent is not None:
            close = getattr(agent, "close", None)
            if callable(close):
                maybe = close()
                if asyncio.iscoroutine(maybe):
                    await maybe