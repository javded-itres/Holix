"""Per-turn custom-command overrides (allowed tools / model)."""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar, Token
from typing import Any

from core.commands.models import CommandInvocation
from core.subagents.react_agent import FilteredToolRegistry

_STASH_ATTR = "_pending_custom_command"

_current: ContextVar[CommandInvocation | None] = ContextVar(
    "holix_custom_command_run",
    default=None,
)


def set_custom_command_run(invocation: CommandInvocation | None) -> Token:
    return _current.set(invocation)


def reset_custom_command_run(token: Token) -> None:
    _current.reset(token)


def peek_custom_command_run() -> CommandInvocation | None:
    return _current.get()


def stash_custom_command(agent: Any, invocation: CommandInvocation) -> None:
    """Remember invocation for a later ``agent.run`` (TUI/Studio start a worker)."""
    if agent is None:
        return
    setattr(agent, _STASH_ATTR, invocation)


def take_stashed_custom_command(agent: Any, user_input: str) -> CommandInvocation | None:
    pending = getattr(agent, _STASH_ATTR, None) if agent is not None else None
    if pending is None:
        return None
    if pending.prompt != user_input:
        return None
    setattr(agent, _STASH_ATTR, None)
    return pending


def apply_command_overrides(agent: Any, invocation: CommandInvocation) -> Callable[[], None]:
    """Temporarily restrict tools / model for this agent run. Returns undo."""
    restores: list[Callable[[], None]] = []
    if invocation.model:
        previous_model = getattr(agent, "model", None)
        agent.model = invocation.model
        restores.append(lambda: setattr(agent, "model", previous_model))
    if invocation.allowed_tools and getattr(agent, "tools", None) is not None:
        previous_tools = agent.tools
        agent.tools = FilteredToolRegistry(
            previous_tools,
            allowed=set(invocation.allowed_tools),
            inherit_mcp=False,
            mcp_servers=[],
        )
        restores.append(lambda: setattr(agent, "tools", previous_tools))

    def _undo() -> None:
        for restore in reversed(restores):
            restore()

    return _undo
