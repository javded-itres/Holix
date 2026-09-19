"""Tool: send a user-confirmed support ticket to Telegram admin(s)."""

from __future__ import annotations

import json
from typing import Any

from core.runtime.admin_support import REQUEST_ADMIN_SUPPORT_TOOL
from core.tools.base import BaseTool
from core.tools.execution_context import get_profile_name, get_subagent_type
from core.tools.result import tool_err, tool_ok


class RequestAdminSupportTool(BaseTool):
    """Offer a Telegram admin ticket. Execute runs only after the user confirms."""

    def __init__(self) -> None:
        super().__init__()
        self.name = REQUEST_ADMIN_SUPPORT_TOOL
        self.description = (
            "Send a support request to the Holix Telegram admin(s) with session "
            "analysis, model, settings snapshot (no secrets), where it happened, "
            "and logs. The user MUST confirm in the confirmation UI; Deny sends "
            "nothing. Use when the session_doctor cannot fix the issue without "
            "operator help (model, jail, tokens, extensions). Never change "
            "system settings yourself."
        )
        self.risk_level = "high"
        self.require_user_confirmation = True
        self.parameters = {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Short problem title for the admin",
                },
                "analysis": {
                    "type": "string",
                    "description": "What went wrong and what was already tried",
                },
                "needed_settings": {
                    "type": "string",
                    "description": (
                        "System settings the admin may need to change "
                        "(model, jail, extensions, tokens) — do not include secrets"
                    ),
                },
                "conversation_id": {
                    "type": "string",
                    "description": "Parent session id (default: autodetect)",
                },
                "diagnose_report": {
                    "type": "string",
                    "description": "JSON string of the self_diagnose report (optional)",
                },
            },
            "required": ["summary", "analysis"],
        }

    async def execute(
        self,
        summary: str = "",
        analysis: str = "",
        needed_settings: str = "",
        conversation_id: str = "",
        diagnose_report: str = "",
        **_: Any,
    ) -> str:
        from core.runtime.admin_support import (
            build_ticket_payload,
            deliver_admin_support_ticket,
            infer_surface,
        )
        from core.runtime.self_diagnose import resolve_diagnose_conversation_id
        from core.runtime.trajectory import TrajectoryLog

        want_summary = (summary or "").strip()
        want_analysis = (analysis or "").strip()
        if not want_summary or not want_analysis:
            return tool_err(
                "missing_fields",
                "summary and analysis are required before sending a support ticket.",
            )

        cid = resolve_diagnose_conversation_id(conversation_id)
        profile = get_profile_name() or "default"
        report: dict[str, Any] = {}
        raw_report = (diagnose_report or "").strip()
        if raw_report:
            try:
                parsed = json.loads(raw_report)
                if isinstance(parsed, dict):
                    report = parsed
            except json.JSONDecodeError:
                report = {}

        logs: list[dict[str, Any]] = []
        try:
            logs = TrajectoryLog(profile).load(cid, limit=80)
        except Exception:
            logs = []

        model = ""
        if isinstance(report.get("llm"), dict):
            models = report["llm"].get("models") or {}
            if isinstance(models, dict) and models:
                model = str(next(iter(models.keys())))

        payload = build_ticket_payload(
            summary=want_summary,
            analysis=want_analysis,
            needed_settings=needed_settings,
            conversation_id=cid,
            profile=profile,
            model=model,
            surface=infer_surface(cid),
            diagnose_report=report,
            logs=logs,
            user={
                "conversation_id": cid,
                "subagent_type": get_subagent_type() or "",
            },
        )
        result = await deliver_admin_support_ticket(payload)
        if not result.get("ok"):
            return tool_err(
                str(result.get("code") or "send_failed"),
                str(result.get("error") or "Failed to send support ticket."),
                **{k: v for k, v in result.items() if k not in {"ok", "code", "error"}},
            )
        return tool_ok(
            message=(
                f"Support ticket sent to {result.get('sent', 0)} Telegram admin(s). "
                "Nothing else was changed."
            ),
            conversation_id=cid,
            profile=profile,
            surface=payload.get("surface"),
            model=payload.get("model"),
            **{k: v for k, v in result.items() if k != "ok"},
        )
