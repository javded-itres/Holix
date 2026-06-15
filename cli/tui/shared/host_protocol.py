"""Protocol for TUI hosts (code UI)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TuiHost(Protocol):
    """Minimal surface for event/slash handlers."""

    agent: Any
    conversation_id: str
    profile: str
    streaming_enabled: bool

    def transcript_write(self, text: str) -> None: ...
    def transcript_scroll_bottom(self) -> None: ...
    def set_status_line(self, text: str) -> None: ...
    def set_thinking(self, message: str | None) -> None: ...