"""Deny-lists and caps for Code mode programs."""

from __future__ import annotations

from typing import Any, Literal

from core.tools.aliases import resolve_tool_name

ToolsPresentation = Literal["native", "code", "both"]

RUN_CODE_NAME = "run_code"

# Inner program may not call these (escape hatches, interactive, nested runtime).
_FORBIDDEN_EXACT: frozenset[str] = frozenset(
    {
        RUN_CODE_NAME,
        "execute_python",
        "code_executor",
        "ask_user",
        "ask_human",
        "external_cli",
        "run_acp_agent",
        "delegate_to_subagent",
        "wait_subagent_result",
        "terminate_subagent",
        "research_site_pages",
        "schedule_cron",
    }
)

_FORBIDDEN_PREFIXES: tuple[str, ...] = ("browser_",)

DEFAULT_WALL_S = 120
MAX_INNER_CALLS = 40
KILL_GRACE_S = 1.0
DEFAULT_PARALLEL_READONLY = True


def normalize_presentation(value: str | None) -> ToolsPresentation:
    raw = str(value or "native").strip().lower()
    if raw in ("native", "code", "both"):
        return raw  # type: ignore[return-value]
    return "native"


def is_forbidden_in_program(name: str, *, tools: dict | None = None) -> bool:
    """True when a Code mode program must not call this tool."""
    key = str(name or "").strip()
    if not key:
        return True
    resolved = resolve_tool_name(key, tools) if tools else key
    if resolved in _FORBIDDEN_EXACT or key in _FORBIDDEN_EXACT:
        return True
    return any(resolved.startswith(p) or key.startswith(p) for p in _FORBIDDEN_PREFIXES)


def is_readonly_inner_tool(name: str, *, tools: dict | None = None) -> bool:
    """True when an inner call may run in parallel (risk_level == no)."""
    if is_forbidden_in_program(name, tools=tools):
        return False
    key = str(name or "").strip()
    resolved = resolve_tool_name(key, tools) if tools else key
    tool = None
    if tools:
        tool = tools.get(resolved) or tools.get(key)
    return str(getattr(tool, "risk_level", "") or "").lower() == "no"


def clamp_wall_timeout_s(value: Any, default: int = DEFAULT_WALL_S) -> int:
    try:
        raw = int(value)
    except (TypeError, ValueError):
        raw = int(default)
    return max(1, min(raw, 600))


def clamp_max_inner_calls(value: Any, default: int = MAX_INNER_CALLS) -> int:
    try:
        raw = int(value)
    except (TypeError, ValueError):
        raw = int(default)
    return max(1, min(raw, 200))
