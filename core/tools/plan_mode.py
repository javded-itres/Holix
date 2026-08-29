"""Enter / exit / status for session plan_mode (strips write tools)."""

from __future__ import annotations

from typing import Any

from core.tools.base import BaseTool
from core.tools.plan_mode_state import (
    enter_plan_mode,
    exit_plan_mode,
    get_plan_state,
    set_plan_text,
)
from core.tools.result import tool_err, tool_ok


class PlanModeTool(BaseTool):
    """Toggle read-only plan mode for this conversation."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "plan_mode"
        self.description = (
            "Enter, exit, or check plan mode. While on, only read-only tools are "
            "offered (read_file, grep, glob, web_search, web_fetch, session_search, "
            "tool_search, ask_user, lsp, plan_mode). Writes return plan_mode_blocked."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "additionalProperties": False,
            "required": ["action"],
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["enter", "exit", "status"],
                },
                "plan": {"type": "string"},
                "require_approval": {
                    "type": "boolean",
                    "default": True,
                },
            },
        }

    async def execute(
        self,
        action: str,
        plan: str = "",
        require_approval: bool = True,
        **_: Any,
    ) -> str:
        act = str(action or "").strip().lower()
        if act not in {"enter", "exit", "status"}:
            return tool_err("invalid_action", f"unknown action {action!r}")

        if act == "status":
            state = get_plan_state()
            return tool_ok(**state)

        if act == "enter":
            state = enter_plan_mode(plan)
            path = _persist_plan(plan)
            extra: dict[str, Any] = {}
            if path:
                extra["saved"] = path
            return tool_ok(**state, **extra)

        state = get_plan_state()
        body = (plan or state.get("plan") or "").strip()
        if require_approval and body:
            approved = await _ask_approve(body)
            if approved is None:
                return tool_err("timeout", "plan approval timed out")
            if not approved:
                set_plan_text(body)
                return tool_ok(
                    active=True,
                    plan=body,
                    approved=False,
                    message="Plan kept in plan_mode — revise, then exit again.",
                )
            _persist_plan(body)
        exit_plan_mode()
        return tool_ok(active=False, plan=body, approved=True)


async def _ask_approve(plan: str) -> bool | None:
    from core.tools.ask_user import AskUserTool

    tool = AskUserTool()
    raw = await tool.execute(
        questions=[
            {
                "id": "plan",
                "prompt": "Approve this plan and exit plan mode?",
                "header": "Plan mode",
                "allow_free_text": False,
                "multi_select": False,
                "options": [
                    {"id": "approve", "label": "Approve"},
                    {"id": "revise", "label": "Revise"},
                ],
            }
        ],
        reason="plan_mode exit",
    )
    try:
        import json

        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return False
    if not payload.get("ok"):
        if payload.get("code") == "timeout":
            return None
        return False
    answers = payload.get("answers") or {}
    picked = answers.get("plan") or []
    if isinstance(picked, str):
        picked = [picked]
    value = str(picked[0] if picked else "").strip().lower()
    return value in {"approve", "approved", "yes"}


def _persist_plan(plan: str) -> str | None:
    text = (plan or "").strip()
    if not text:
        return None
    try:
        from types import SimpleNamespace

        from core.plan_review.plan_storage import save_plan
        from core.tools.execution_context import get_conversation_id, get_workspace_root

        root = get_workspace_root()
        config = SimpleNamespace(workspace_root=root) if root else None
        path = save_plan(
            plan_steps=[{"title": "plan_mode", "description": text[:2000]}],
            conversation_id=get_conversation_id() or "default",
            rendered_markdown=text,
            plan_status="plan_mode",
            config=config,
        )
        return str(path)
    except Exception:
        return None
