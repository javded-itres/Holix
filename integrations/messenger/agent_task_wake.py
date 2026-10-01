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
    pin_task: Callable[[Any], Any] | None = None,
    unpin_task: Callable[[Any], Any] | None = None,
) -> None:
    """Register once per chat session. ``start_run`` begins an agent turn.

    ``pin_task`` / ``unpin_task`` are async callables that keep the task
    visible in the chat until it finishes.
    """
    if getattr(session, "_agent_task_wake_bound", False):
        return

    from core.runtime.agent_tasks import (
        format_agent_task_wakeup,
        register_agent_task_listener,
        register_agent_task_start_listener,
    )

    def _same_chat(task: Any) -> bool:
        if (getattr(task, "conversation_id", "") or "") != (
            getattr(session, "conversation_id", "") or ""
        ):
            return False
        return (getattr(task, "profile", "") or "") == (getattr(session, "profile", "") or "")

    def _schedule(coro_factory: Callable[[], Any], task: Any) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("no loop for background task %s", getattr(task, "task_id", ""))
            return
        loop.create_task(coro_factory())

    def _on_start(task: Any) -> None:
        if pin_task is None or not _same_chat(task):
            return

        async def _go() -> None:
            try:
                await pin_task(task)
            except Exception:
                logger.exception("failed to pin task %s", getattr(task, "task_id", ""))

        _schedule(_go, task)

    def _on_task(task: Any) -> None:
        if not _same_chat(task):
            return
        if unpin_task is not None:

            async def _unpin() -> None:
                try:
                    await unpin_task(task)
                except Exception:
                    logger.exception("failed to unpin task %s", getattr(task, "task_id", ""))

            _schedule(_unpin, task)
        from integrations.messenger.generation_details import media_file_was_delivered

        if media_file_was_delivered(getattr(task, "output", "")) and task.exit_code == 0:
            return
        text = format_agent_task_wakeup(task)

        async def _go() -> None:
            try:
                start_run(text)
            except Exception:
                logger.exception("failed to wake agent for task %s", getattr(task, "task_id", ""))

        _schedule(_go, task)

    register_agent_task_start_listener(_on_start)
    register_agent_task_listener(_on_task)
    session._agent_task_wake_bound = True
    session._agent_task_wake_listener = _on_task
    session._agent_task_start_listener = _on_start
