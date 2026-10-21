"""Inject a user message into the turn that is already running.

The TUI holds the box. The graph task reads it through a context var so a
tool poll loop can stop without cancelling the whole run.
"""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
from typing import Any


class SteerInterrupt(Exception):
    """The current command should stop because a new instruction arrived."""


class SteerBox:
    def __init__(self) -> None:
        self.pending: list[str] = []
        self.interrupt = asyncio.Event()

    def push(self, text: str) -> None:
        cleaned = (text or "").strip()
        if not cleaned:
            return
        self.pending.append(cleaned)
        self.interrupt.set()

    def drain(self) -> list[str]:
        items = list(self.pending)
        self.pending.clear()
        self.interrupt.clear()
        return items


_box: ContextVar[SteerBox | None] = ContextVar("holix_turn_steer", default=None)


def steer_scope(box: SteerBox):
    return _box.set(box)


def reset_steer_scope(token) -> None:
    _box.reset(token)


def current_steer() -> SteerBox | None:
    return _box.get()


def steer_requested() -> bool:
    box = _box.get()
    return bool(box and box.pending)


async def absorb_steer(
    messages: list[dict[str, Any]],
    agent: Any,
    conversation_id: str,
) -> bool:
    """Append pending instructions as user messages. True when any were waiting."""
    box = _box.get()
    if box is None or not box.pending:
        return False
    texts = box.drain()
    memory = getattr(agent, "memory", None) if agent is not None else None
    for text in texts:
        messages.append({"role": "user", "content": text})
        if memory is not None and hasattr(memory, "save_message"):
            await memory.save_message(conversation_id, "user", text)
    return bool(texts)
