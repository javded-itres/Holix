"""Wake the same messenger agent when one of its background tasks exits."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def bind_messenger_agent_task_wake(
    session: Any,
    *,
    start_run: Callable[[str], None],
) -> None:
    """Register once per chat session. ``start_run`` begins an agent turn."""
    if getattr(session, "_agent_task_wake_bound", False):
        return

    from core.runtime.agent_tasks import format_agent_task_wakeup, register_agent_task_listener

    def _on_task(task: Any) -> None:
        if (getattr(task, "conversation_id", "") or "") != (
            getattr(session, "conversation_id", "") or ""
        ):
            return
        if (getattr(task, "profile", "") or "") != (getattr(session, "profile", "") or ""):
            return
        text = format_agent_task_wakeup(task)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("no loop to report background task %s", getattr(task, "task_id", ""))
            return

        async def _go() -> None:
            try:
                start_run(text)
            except Exception:
                logger.exception("failed to wake agent for task %s", getattr(task, "task_id", ""))

        loop.create_task(_go())

    register_agent_task_listener(_on_task)
    session._agent_task_wake_bound = True
    session._agent_task_wake_listener = _on_task
