"""Paths a background sub-agent owns until its result is injected.

The parent must not write those paths, and must not poll the job. The
result is written into the parent conversation when the child finishes.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

_CLAIMS: dict[str, dict[str, set[str]]] = {}
_TASKS: set[asyncio.Task] = set()


def _key(profile: str, conversation_id: str) -> str:
    return f"{profile or 'default'}:{conversation_id or 'default'}"


def claim(
    profile: str,
    conversation_id: str,
    job_id: str,
    paths: list[str] | None,
) -> None:
    owned = {
        str(path).replace("\\", "/").lstrip("./") for path in (paths or []) if str(path).strip()
    }
    _CLAIMS.setdefault(_key(profile, conversation_id), {})[job_id] = owned


def release(profile: str, conversation_id: str, job_id: str) -> None:
    jobs = _CLAIMS.get(_key(profile, conversation_id))
    if not jobs:
        return
    jobs.pop(job_id, None)


def conflicting_job(
    profile: str,
    conversation_id: str,
    path: str,
) -> str | None:
    jobs = _CLAIMS.get(_key(profile, conversation_id)) or {}
    wanted = str(path or "").replace("\\", "/").lstrip("./")
    if not wanted:
        return None
    for job_id, paths in jobs.items():
        for owned in paths:
            if wanted == owned or wanted.startswith(owned.rstrip("/") + "/"):
                return job_id
    return None


def watch(
    agent: Any,
    *,
    job_id: str,
    profile: str,
    conversation_id: str,
    timeout: float | None = None,
) -> None:
    """Wait for *job_id* and append its result to the parent conversation."""

    async def _run() -> None:
        try:
            result = await agent.subagents.wait_for(job_id, timeout=timeout or 3600)
            body = (
                getattr(result, "response", None) or getattr(result, "error", None) or ""
            ).strip()
            text = (
                f"[background sub-agent {job_id} finished]\n"
                f"success={getattr(result, 'success', False)}\n{body}"
            )
            memory = getattr(agent, "memory", None)
            if memory is not None and hasattr(memory, "save_message"):
                await memory.save_message(conversation_id, "user", text)
            emit = getattr(agent, "emit", None)
            if callable(emit):
                try:
                    from core.agent_events import ThinkingEvent

                    emit(ThinkingEvent(message=f"Background sub-agent {job_id} finished"))
                except Exception:
                    logger.debug("background inject emit failed", exc_info=True)
        except Exception:
            logger.debug("background sub-agent watch failed", exc_info=True)
        finally:
            release(profile, conversation_id, job_id)

    task = asyncio.create_task(_run())
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
