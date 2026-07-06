"""DesktopHost adapter for shared slash commands (Studio)."""

from __future__ import annotations

from typing import Any


class StudioHost:
    """Minimal host bridge for Studio WebSocket sessions."""

    def __init__(self, session: Any) -> None:
        self._session = session

    @property
    def agent(self) -> Any:
        return self._session.agent

    @property
    def conversation_id(self) -> str:
        return self._session.conversation_id

    @property
    def profile(self) -> str:
        return self._session.profile

    @property
    def streaming_enabled(self) -> bool:
        return True

    def transcript_write(self, text: str) -> None:
        return None

    def transcript_scroll_bottom(self) -> None:
        return None

    def set_status_line(self, text: str) -> None:
        return None

    def set_thinking(self, message: str | None) -> None:
        return None