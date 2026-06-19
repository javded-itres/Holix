"""Tools for searching and reading other conversation sessions."""

from __future__ import annotations

from typing import Any

from core.memory.session_search import (
    format_memory_search_results,
    format_session_transcript,
)
from core.tools.base import BaseTool
from core.tools.execution_context import (
    get_conversation_id,
    get_memory_facade,
    get_profile_name,
)


def _resolve_memory() -> Any:
    facade = get_memory_facade()
    if facade is not None:
        return facade

    from cli.core import ProfileManager

    from core.di import resolve_runtime_config
    from core.memory.facade import MemoryFacade

    profile_name = (get_profile_name() or "").strip()
    if profile_name:
        manager = ProfileManager()
        if manager.profile_exists(profile_name):
            profile_cfg = manager.load_profile(profile_name)
            return MemoryFacade(resolve_runtime_config(profile_cfg))

    return MemoryFacade(resolve_runtime_config())


class SearchSessionsTool(BaseTool):
    """Semantic search across all stored conversation sessions."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "search_sessions"
        self.description = (
            "Search message history across ALL conversation sessions in this profile "
            "(Telegram, TUI, cron, etc.). Returns excerpts with conversation_id so "
            "you can call read_session for full context. Excludes the current session "
            "by default."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Semantic search query",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Max results (default 8)",
                    "default": 8,
                },
                "include_current": {
                    "type": "boolean",
                    "description": "Include hits from the active session (default false)",
                    "default": False,
                },
            },
            "required": ["query"],
        }

    async def execute(
        self,
        query: str,
        top_k: int = 8,
        include_current: bool = False,
        **_: Any,
    ) -> str:
        q = (query or "").strip()
        if not q:
            return "Error: query is required"

        memory = _resolve_memory()
        top_k = max(1, min(int(top_k or 8), 20))
        results = await memory.search(q, top_k=top_k, conversation_id=None)
        current = get_conversation_id()
        return format_memory_search_results(
            results,
            current_conversation_id=current,
            include_current=bool(include_current),
        )


class ReadSessionTool(BaseTool):
    """Load recent messages from a specific conversation session."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "read_session"
        self.description = (
            "Read recent messages from a conversation session by conversation_id "
            "(from search_sessions, list_conversations, or /sessions). "
            "Use to recover full context from another chat."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Session id, e.g. tg_default_123 or tui_default_…",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max messages to load (default 30, max 80)",
                    "default": 30,
                },
            },
            "required": ["conversation_id"],
        }

    async def execute(
        self,
        conversation_id: str,
        limit: int = 30,
        **_: Any,
    ) -> str:
        cid = (conversation_id or "").strip()
        if not cid:
            return "Error: conversation_id is required"

        memory = _resolve_memory()
        limit = max(1, min(int(limit or 30), 80))
        messages = await memory.get_conversation(cid, limit=limit)
        return format_session_transcript(cid, messages)