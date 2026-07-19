"""Per-run execution context (conversation, workspace, bridges)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RunContext:
    """Scoped context for a single agent run (one user message / graph invocation)."""

    conversation_id: str = "default"
    profile_name: str = "default"
    workspace_root: str | None = None
    workspace_jail_enabled: bool = False
    full_paths_visible: bool = True
    subagent_name: str = ""
    subagent_type: str = ""
    memory_facade: Any | None = None
    interaction_bridge: Any | None = None
    chat_delivery_bridge: Any | None = None
    emit_fn: Callable[[Any], None] | None = None

    extra: dict[str, Any] = field(default_factory=dict)