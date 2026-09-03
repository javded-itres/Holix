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
        "skill_view",
        "skill_manage",
        "ask_user",
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
        "research_site_pages",
        "plan_mode",
        "lsp",
    }
)

_FALSE = frozenset({"0", "false", "no", "off", "n"})


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
    if not lazy_tools_enabled():
        return True
    if key in CORE_TOOL_NAMES:
        return True
    extra = session_extra or ()
    return key in extra
