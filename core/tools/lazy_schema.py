"""Claude-style deferred tool schemas: core set on the API, the rest via tool_search.

Builtin tools stay registered and executable. Only the OpenAI ``tools`` list
is trimmed. ``tool_search(enable_matches=true)`` adds hits for this session.
Disable with HOLIX_LAZY_TOOLS=0.
"""

from __future__ import annotations

import os

# Always attached (discovery + everyday coding). Everything else is deferred.
CORE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "tool_search",
        "list_agent_tasks",
        "skill_view",
        "skill_manage",
        "ask_user",
        "review_memory",
        "search_document",
        "read_document",
        "todo_write",
        "read_file",
        "write_file",
        "patch_file",
        "apply_patch",
        "delete_file",
        "list_directory",
        "grep",
        "glob",
        "run_terminal_command",
        "web_search",
        "fetch_url",
        "send_chat_files",
        "self_diagnose",
        "delegate_to_subagent",
        "wait_subagent_result",
        "research_site_pages",
        "plan_mode",
        "lsp",
        # Media tools are registered only when holix-media is configured.
        # They must be on the LLM list; tool_search does not surface them.
        "describe_media_model",
        "generate_image",
        "generate_video",
    }
)

_FALSE = frozenset({"0", "false", "no", "off", "n"})

# Only useful when a Telegram or MAX chat is attached to this run.
_MESSENGER_ONLY_TOOLS = frozenset({"send_chat_files"})


def messenger_delivery_available() -> bool:
    try:
        from core.tools.execution_context import get_chat_delivery_bridge
    except Exception:
        return False
    return get_chat_delivery_bridge() is not None


def lazy_tools_enabled() -> bool:
    raw = (os.environ.get("HOLIX_LAZY_TOOLS") or "1").strip().lower()
    return raw not in _FALSE


def schema_tool_offered(
    name: str,
    *,
    session_extra: set[str] | frozenset[str] | None = None,
) -> bool:
    """Whether this canonical tool name belongs on the LLM tools list."""
    key = str(name or "").strip()
    if not key:
        return False
    if key in _MESSENGER_ONLY_TOOLS and not messenger_delivery_available():
        return False
    if not lazy_tools_enabled():
        return True
    if key in CORE_TOOL_NAMES:
        return True
    extra = session_extra or ()
    return key in extra
