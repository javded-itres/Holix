"""Group a model step's tool calls so read-only ones can run together."""

from __future__ import annotations

from typing import Any

# Asks the user or changes the plan. Never overlap these with other calls.
_SERIAL_NAMES = frozenset({"ask_user", "exit_plan_mode", "enter_plan_mode"})


def is_parallel_read(agent: Any, name: str) -> bool:
    """True for a no-risk tool that only reads."""
    if not name or name in _SERIAL_NAMES:
        return False
    registry = getattr(agent, "tools", None)
    tools = getattr(registry, "tools", None)
    if not isinstance(tools, dict):
        return False
    tool = tools.get(name)
    if tool is None:
        return False
    return getattr(tool, "risk_level", "") == "no"


def group_tool_calls(agent: Any, tool_calls: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Consecutive read-only calls share a batch. Everything else stays alone.

    A confirmation guard makes overlapping prompts unsafe, so the caller runs
    every call alone when one is installed.
    """
    groups: list[list[dict[str, Any]]] = []
    index = 0
    while index < len(tool_calls):
        call = tool_calls[index]
        name = str((call.get("function") or {}).get("name") or "")
        if not is_parallel_read(agent, name):
            groups.append([call])
            index += 1
            continue
        batch = [call]
        index += 1
        while index < len(tool_calls):
            nxt = tool_calls[index]
            nxt_name = str((nxt.get("function") or {}).get("name") or "")
            if not is_parallel_read(agent, nxt_name):
                break
            batch.append(nxt)
            index += 1
        groups.append(batch)
    return groups
