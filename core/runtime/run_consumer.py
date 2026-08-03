"""Helpers for consuming agent run event streams in messenger hosts."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from core.agent_events import AgentEvent
from core.runtime.timeouts import agent_run_timeout_s


async def consume_run_holix(
    agent: Any,
    user_input: str,
    conversation_id: str,
    *,
    stream: bool,
    execution_mode: str | None,
    emit: Callable[[AgentEvent], None],
    timeout_s: float | None = None,
    state_overrides: dict | None = None,
) -> None:
    """Run Holix and forward events; raises TimeoutError if the run exceeds the cap."""
    from core.runtime.executor import run_holix

    effective_timeout = timeout_s if timeout_s is not None else agent_run_timeout_s(agent)

    async def _consume() -> None:
        try:
            async for event in run_holix(
                agent,
                user_input,
                conversation_id,
                stream=stream,
                execution_mode=execution_mode,
                state_overrides=state_overrides,
            ):
                emit(event)
        except asyncio.CancelledError:
            raise
        except RuntimeError as exc:
            if "generator didn't stop after athrow" in str(exc):
                raise asyncio.CancelledError() from exc
            raise

    try:
        await asyncio.wait_for(_consume(), timeout=effective_timeout)
    except asyncio.CancelledError:
        raise