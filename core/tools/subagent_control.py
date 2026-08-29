"""Control running sub-agents (list / send / interrupt / collect / status)."""

from __future__ import annotations

import asyncio
from typing import Any

from core.tools.base import BaseTool
from core.tools.execution_context import get_tools_registry
from core.tools.result import tool_err, tool_ok


def _manager_from(parent: Any) -> Any | None:
    if parent is None:
        return None
    sub = getattr(parent, "subagents", None)
    if sub is not None:
        return sub
    return parent if hasattr(parent, "list_all") else None


def _resolve_manager(explicit_parent: Any) -> Any | None:
    mgr = _manager_from(explicit_parent)
    if mgr is not None:
        return mgr
    registry = get_tools_registry()
    host = getattr(registry, "_host_agent", None) if registry is not None else None
    return _manager_from(host)


def _handle_payload(handle: Any) -> dict[str, Any]:
    status = getattr(handle, "status", None)
    status_val = status.value if hasattr(status, "value") else str(status or "")
    result = getattr(handle, "result", None)
    last = ""
    if result is not None:
        last = str(getattr(result, "response", "") or getattr(result, "error", "") or "")
    return {
        "agent_id": str(getattr(handle, "name", "") or ""),
        "type": str(getattr(handle, "agent_type", "") or ""),
        "state": status_val,
        "running": bool(getattr(handle, "is_running", False)),
        "last_event": str(getattr(handle, "current_activity", "") or "")[:240],
        "last_tool": str(getattr(handle, "last_tool", "") or ""),
        "preview": last[:400],
    }


class SubagentControlTool(BaseTool):
    """Control running sub-agents. Does not spawn."""

    def __init__(self, parent_agent: Any | None = None) -> None:
        super().__init__()
        self._parent = parent_agent
        self.name = "subagent_control"
        self.description = (
            "Control already-running sub-agents: list, status, send a follow-up "
            "message, interrupt, or collect the last report. Does not spawn — "
            "use delegate_to_subagent for that."
        )
        self.risk_level = "medium"
        self.parameters = {
            "type": "object",
            "additionalProperties": False,
            "required": ["action"],
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "send", "interrupt", "collect", "status"],
                },
                "agent_id": {"type": "string"},
                "message": {"type": "string"},
                "wait_s": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 120,
                    "default": 0,
                },
            },
        }

    async def execute(
        self,
        action: str,
        agent_id: str = "",
        message: str = "",
        wait_s: int = 0,
        **_: Any,
    ) -> str:
        act = str(action or "").strip().lower()
        if act not in {"list", "send", "interrupt", "collect", "status"}:
            return tool_err("invalid_action", f"unknown action {action!r}")
        if act in {"list", "status"}:
            self.risk_level = "no"
        else:
            self.risk_level = "medium"

        manager = _resolve_manager(self._parent)
        if manager is None:
            if act == "list":
                return tool_ok(agents=[])
            return tool_err("not_found", "no sub-agent manager")

        if act == "list":
            handles = list(manager.list_all() or [])
            return tool_ok(agents=[_handle_payload(h) for h in handles])

        target = (agent_id or "").strip()
        if not target:
            return tool_err("missing_agent_id", "agent_id is required")
        handle = manager.get_handle(target) if hasattr(manager, "get_handle") else None
        if handle is None:
            return tool_err("not_found", f"agent '{target}' not found", agent_id=target)

        if act == "status":
            return tool_ok(agent=_handle_payload(handle))

        if act == "interrupt":
            ok = await manager.terminate(target)
            return tool_ok(agent=_handle_payload(handle), interrupted=bool(ok))

        if act == "send":
            text = (message or "").strip()
            if not text:
                return tool_err("missing_message", "message is required for send")
            try:
                from core.subagents.communication import AgentMessage

                bus = getattr(manager, "_comm_bus", None)
                if bus is None:
                    return tool_err("no_bus", "sub-agent communication bus is unavailable")
                mode = getattr(getattr(handle, "config", None), "process_mode", None)
                mode_val = mode.value if hasattr(mode, "value") else str(mode or "async")
                msg = AgentMessage(
                    from_agent="main",
                    to_agent=handle.name,
                    msg_type="guidance",
                    content=text,
                )
                await bus.send(msg, process_mode=str(mode_val).lower())
            except Exception as exc:
                return tool_err("send_failed", str(exc), agent_id=target)
            return tool_ok(agent=_handle_payload(handle), sent=True)

        wait_s = max(0, min(int(wait_s or 0), 120))
        if wait_s > 0 and getattr(handle, "is_running", False):
            waiter = getattr(manager, "_wait_for_handle", None)
            if callable(waiter):
                try:
                    await asyncio.wait_for(waiter(handle), timeout=wait_s)
                except TimeoutError:
                    pass
        result = getattr(handle, "result", None)
        payload = _handle_payload(handle)
        if result is not None:
            payload["response"] = str(getattr(result, "response", "") or "")[:4000]
            payload["error"] = str(getattr(result, "error", "") or "")
            payload["success"] = bool(getattr(result, "success", False))
        return tool_ok(agent=payload)
