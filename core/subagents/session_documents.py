"""Give a child the parent session's document cards and the tools to read them."""

from __future__ import annotations

from typing import Any

_DOCUMENT_TOOLS = ("search_document", "read_document")
_SKIP_TYPES = frozenset({"page_analyst"})


def attach_session_documents(
    config: Any,
    profile: str | None,
    *,
    conversation_id: str = "",
) -> str:
    """Append session document tools and return the prompt block.

    No-op when this session has no indexed documents, or for the one-page
    analyst that must not gain extra tools. Safe to call more than once.
    """
    slug = (
        str(getattr(config, "agent_type", None) or getattr(config, "name", None) or "")
        .strip()
        .lower()
    )
    if slug in _SKIP_TYPES:
        return ""
    task_id = (
        conversation_id or str(getattr(config, "parent_conversation_id", None) or "")
    ).strip()
    if not task_id:
        return ""
    from core.documents.index import format_session_documents_prompt

    block = format_session_documents_prompt(
        (profile or "default").strip() or "default",
        task_id,
    )
    if not block:
        return ""
    tools = [str(name) for name in (getattr(config, "tools", None) or []) if str(name).strip()]
    for name in _DOCUMENT_TOOLS:
        if name not in tools:
            tools.append(name)
    config.tools = tools
    return block
