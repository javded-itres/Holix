"""Per-request context for tool execution (conversation / sub-agent scoping)."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

_conversation_id: ContextVar[str] = ContextVar("holix_conversation_id", default="default")
_subagent_name: ContextVar[str] = ContextVar("holix_subagent_name", default="")
_interaction_bridge: ContextVar[Any] = ContextVar("holix_interaction_bridge", default=None)
_chat_delivery_bridge: ContextVar[Any] = ContextVar("holix_chat_delivery_bridge", default=None)
_memory_facade: ContextVar[Any] = ContextVar("holix_memory_facade", default=None)
_workspace_root: ContextVar[str | None] = ContextVar("holix_workspace_root", default=None)
_workspace_jail_enabled: ContextVar[bool] = ContextVar("holix_workspace_jail_enabled", default=False)
_full_paths_visible: ContextVar[bool] = ContextVar("holix_full_paths_visible", default=True)


def get_conversation_id() -> str:
    return _conversation_id.get()


def get_subagent_name() -> str:
    return _subagent_name.get()


def get_interaction_bridge() -> Any | None:
    return _interaction_bridge.get()


def get_chat_delivery_bridge() -> Any | None:
    return _chat_delivery_bridge.get()


def get_memory_facade() -> Any | None:
    return _memory_facade.get()


def get_workspace_root() -> str | None:
    return _workspace_root.get()


def is_workspace_jail_enabled() -> bool:
    return _workspace_jail_enabled.get()


def is_full_paths_visible() -> bool:
    return _full_paths_visible.get()


def paths_visibility_scope(*, full_paths_visible: bool):
    """Return token from ContextVar.set for use with reset_paths_visibility_scope."""
    return _full_paths_visible.set(full_paths_visible)


def reset_paths_visibility_scope(token) -> None:
    _full_paths_visible.reset(token)


def conversation_scope(conversation_id: str):
    """Return token from ContextVar.set for use with reset_conversation_scope."""
    return _conversation_id.set(conversation_id)


def reset_conversation_scope(token) -> None:
    _conversation_id.reset(token)


def chat_delivery_scope(bridge: Any):
    """Return token from ContextVar.set for use with reset_chat_delivery_scope."""
    return _chat_delivery_bridge.set(bridge)


def reset_chat_delivery_scope(token) -> None:
    _chat_delivery_bridge.reset(token)


def memory_facade_scope(facade: Any):
    """Return token from ContextVar.set for use with reset_memory_facade_scope."""
    return _memory_facade.set(facade)


def reset_memory_facade_scope(token) -> None:
    _memory_facade.reset(token)


def workspace_scope(
    *,
    workspace_root: str | None = None,
    workspace_jail_enabled: bool = False,
):
    """Return tokens for workspace jail context."""
    return [
        ("root", _workspace_root.set(workspace_root)),
        ("jail", _workspace_jail_enabled.set(workspace_jail_enabled)),
    ]


def reset_workspace_scope(tokens) -> None:
    for key, token in reversed(tokens):
        if key == "root":
            _workspace_root.reset(token)
        elif key == "jail":
            _workspace_jail_enabled.reset(token)


def subagent_scope(
    subagent_name: str,
    *,
    interaction_bridge: Any = None,
):
    """Context manager tokens for sub-agent tool execution."""
    tokens = []
    tokens.append(("subagent", _subagent_name.set(subagent_name)))
    if interaction_bridge is not None:
        tokens.append(("bridge", _interaction_bridge.set(interaction_bridge)))
    return tokens


def reset_subagent_scope(tokens) -> None:
    for key, token in reversed(tokens):
        if key == "subagent":
            _subagent_name.reset(token)
        elif key == "bridge":
            _interaction_bridge.reset(token)