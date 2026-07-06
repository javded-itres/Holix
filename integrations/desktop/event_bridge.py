"""Map AgentEvent stream to Studio WebSocket messages."""

from __future__ import annotations

import re
from typing import Any

from core.agent_events import (
    AgentEvent,
    AssistantDeltaEvent,
    ErrorEvent,
    EventType,
    FinalResponseEvent,
    ThinkingEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from core.tools.file_diff import DIFF_SEPARATOR

_WRITE_FILE_PATH_RE = re.compile(r"^(?:Created|Updated)\s+(\S+)", re.MULTILINE)


def agent_event_to_studio_message(event: AgentEvent) -> dict[str, Any]:
    """Serialize one agent event for the Studio UI."""
    payload = event.to_dict()
    payload["type"] = _studio_type(event)
    extras = _extra_studio_fields(event)
    if extras:
        payload.update(extras)
    return payload


def _studio_type(event: AgentEvent) -> str:
    if isinstance(event, ThinkingEvent):
        return "thinking"
    if isinstance(event, AssistantDeltaEvent):
        return "assistant_delta"
    if isinstance(event, FinalResponseEvent):
        return "final_response"
    if isinstance(event, ToolCallStartEvent):
        return "tool_call_start"
    if isinstance(event, ToolCallResultEvent):
        return "tool_call_result"
    if isinstance(event, ErrorEvent):
        return "error"
    return event.type.value if hasattr(event.type, "value") else str(event.type)


def _extra_studio_fields(event: AgentEvent) -> dict[str, Any]:
    if isinstance(event, ToolCallResultEvent) and event.tool_name == "write_file":
        diff_msg = _file_diff_from_write_result(event.result)
        if diff_msg:
            return {"file_diff": diff_msg}
    if event.type == EventType.ERROR:
        err = getattr(event, "error", "") or ""
        return {"message": err}
    return {}


def _file_diff_from_write_result(result: str) -> dict[str, Any] | None:
    if DIFF_SEPARATOR not in result:
        return None
    summary, _, diff_block = result.partition(DIFF_SEPARATOR)
    summary = summary.strip()
    path_match = _WRITE_FILE_PATH_RE.search(summary)
    if not path_match:
        return None
    path = path_match.group(1)
    unified = diff_block.strip()
    old_text, new_text = _split_unified_diff(unified)
    return {
        "path": path,
        "unified": unified,
        "old": old_text,
        "new": new_text,
        "summary": summary,
    }


def _split_unified_diff(unified: str) -> tuple[str, str]:
    """Best-effort reconstruction of old/new from unified diff lines."""
    old_lines: list[str] = []
    new_lines: list[str] = []
    for line in unified.splitlines():
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            new_lines.append(line[1:])
        elif line.startswith("-"):
            old_lines.append(line[1:])
        elif line.startswith(" "):
            old_lines.append(line[1:])
            new_lines.append(line[1:])
    return "\n".join(old_lines), "\n".join(new_lines)