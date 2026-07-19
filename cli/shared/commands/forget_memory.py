"""Wipe agent conversation memory for the active session (/forget)."""

from __future__ import annotations

import logging
from typing import Any

from core.i18n import host_locale, t

logger = logging.getLogger(__name__)


async def _resolve_agent(host: Any) -> Any | None:
    agent = getattr(host, "agent", None)
    if agent is not None:
        return agent
    session = getattr(host, "_session", None)
    ensure = getattr(session, "ensure_agent", None) if session is not None else None
    if callable(ensure):
        try:
            return await ensure()
        except Exception:
            logger.debug("ensure_agent failed during forget", exc_info=True)
    return None


async def wipe_conversation_memory_for_host(host: Any) -> bool:
    """Delete SQLite + Chroma history for the host's conversation_id."""
    conversation_id = str(getattr(host, "conversation_id", None) or "").strip()
    if not conversation_id:
        return False

    agent = await _resolve_agent(host)
    if agent is None:
        return False

    memory = getattr(agent, "memory", None)
    if memory is None or not hasattr(memory, "delete_conversation"):
        return False

    try:
        deleted = await memory.delete_conversation(conversation_id)
    except Exception:
        logger.warning("delete_conversation failed for %s", conversation_id, exc_info=True)
        return False

    cm = getattr(agent, "context_manager", None)
    if cm is not None:
        cm.invalidate_usage_cache(conversation_id)

    return bool(deleted)


def clear_memory_search_ui(host: Any) -> None:
    if hasattr(host, "_memory_search_query"):
        host._memory_search_query = ""
    if hasattr(host, "_memory_search_results"):
        host._memory_search_results = []


def _clear_studio_chat_ui(host: Any) -> None:
    session = getattr(host, "_session", None)
    if session is None:
        return
    mod = getattr(type(session), "__module__", "") or ""
    if not (mod.startswith("holix_studio.") or type(session).__name__ == "StudioSession"):
        return

    ts = getattr(host, "_transcript_store", None) or getattr(session, "_transcript_store", None)
    if ts is not None and hasattr(ts, "clear"):
        ts.clear()
    recent = getattr(host, "_recent_tool_results", None) or getattr(
        session, "_recent_tool_results", None
    )
    if recent is not None and hasattr(recent, "clear"):
        recent.clear()
    if hasattr(session, "clear_chat_history"):
        session.clear_chat_history()
    schedule = getattr(host, "_schedule_emit", None)
    if callable(schedule):
        schedule({"type": "chat_clear"})


def _clear_messenger_chat_ui(host: Any) -> None:
    session = getattr(host, "_session", None)
    if session is None:
        return
    from integrations.max.session import MaxChatSession
    from integrations.telegram.session import ChatSession

    if not isinstance(session, (ChatSession, MaxChatSession)):
        return
    ts = getattr(host, "_transcript_store", None) or getattr(session, "_transcript_store", None)
    if ts is not None and hasattr(ts, "clear"):
        ts.clear()
    recent = getattr(host, "_recent_tool_results", None) or getattr(
        session, "_recent_tool_results", None
    )
    if recent is not None and hasattr(recent, "clear"):
        recent.clear()


def clear_chat_surface(host: Any) -> None:
    """Clear visible chat/transcript without touching agent memory."""
    _clear_studio_chat_ui(host)
    _clear_messenger_chat_ui(host)


async def _refresh_context_displays(host: Any) -> None:
    for attr in ("_update_context_display_async", "push_context_usage"):
        refresh = getattr(host, attr, None)
        if not callable(refresh):
            session = getattr(host, "_session", None)
            refresh = getattr(session, attr, None) if session is not None else None
        if not callable(refresh):
            continue
        try:
            result = refresh()
            if hasattr(result, "__await__"):
                await result
        except Exception:
            logger.debug("context refresh after forget failed", exc_info=True)
        break

    for attr in ("_refresh_status_bar", "_refresh_header_subtitle"):
        fn = getattr(host, attr, None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass


async def run_forget_memory(host: Any, *, clear_ui: bool = False) -> None:
    """Wipe DB memory for the current session; optionally clear chat UI."""
    write = getattr(host, "transcript_write", None)
    lang = host_locale(host)
    conversation_id = str(getattr(host, "conversation_id", None) or "").strip()

    if not conversation_id:
        if write:
            write(t("forget.no_session", lang))
        return

    if clear_ui:
        clear_chat_surface(host)

    deleted = await wipe_conversation_memory_for_host(host)
    clear_memory_search_ui(host)
    await _refresh_context_displays(host)

    if not write:
        return
    if deleted:
        short_id = conversation_id if len(conversation_id) <= 28 else f"{conversation_id[:25]}…"
        write(t("forget.done", lang, id=short_id))
    else:
        write(t("forget.failed", lang))