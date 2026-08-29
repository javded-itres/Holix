"""Monitor / tail / wait / kill Holix background processes."""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from core.tools.base import BaseTool
from core.tools.execution_context import get_profile_name
from core.tools.result import tool_err, tool_ok


def _truncate(text: str, max_bytes: int) -> tuple[str, bool]:
    raw = text.encode("utf-8", errors="replace")
    if len(raw) <= max_bytes:
        return text, False
    clipped = raw[-max_bytes:]
    return clipped.decode("utf-8", errors="replace"), True


def _record_payload(rec: Any) -> dict[str, Any]:
    running = bool(rec.is_running()) if hasattr(rec, "is_running") else False
    return {
        "job_id": str(getattr(rec, "process_id", "") or ""),
        "cmd": str(getattr(rec, "command", "") or ""),
        "pid": int(getattr(rec, "pid", 0) or 0),
        "started_at": float(getattr(rec, "started_at", 0) or 0),
        "log_path": str(getattr(rec, "log_path", "") or ""),
        "status": "running" if running else "stopped",
        "label": str(getattr(rec, "label", "") or ""),
    }


class JobMonitorTool(BaseTool):
    """List / tail / wait / kill tracked background jobs."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "job_monitor"
        self.description = (
            "Inspect Holix background jobs (start_background_process registry). "
            "Actions: list, tail, wait, kill. job_id is required for tail/wait/kill."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "additionalProperties": False,
            "required": ["action"],
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "tail", "wait", "kill"],
                },
                "job_id": {"type": "string"},
                "timeout_s": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 300,
                    "default": 15,
                },
                "max_bytes": {
                    "type": "integer",
                    "minimum": 1024,
                    "maximum": 200000,
                    "default": 16000,
                },
                "grep": {"type": "string"},
            },
        }

    async def execute(
        self,
        action: str,
        job_id: str = "",
        timeout_s: int = 15,
        max_bytes: int = 16000,
        grep: str = "",
        **_: Any,
    ) -> str:
        from core.runtime.background_process import get_background_process_registry

        act = str(action or "").strip().lower()
        if act not in {"list", "tail", "wait", "kill"}:
            return tool_err("invalid_action", f"unknown action {action!r}")
        if act == "kill":
            self.risk_level = "medium"
        else:
            self.risk_level = "no"

        registry = get_background_process_registry()
        profile = get_profile_name()
        max_bytes = max(1024, min(int(max_bytes or 16000), 200000))
        timeout_s = max(1, min(int(timeout_s or 15), 300))

        if act == "list":
            recs = registry.list_for_profile(profile=profile)
            return tool_ok(jobs=[_record_payload(r) for r in recs])

        target = (job_id or "").strip()
        if not target:
            return tool_err("missing_job_id", "job_id is required for tail/wait/kill")
        rec = registry.get(target)
        if rec is None:
            return tool_err("not_found", f"job '{target}' not found", job_id=target)

        if act == "kill":
            stopped = await registry.stop(target)
            if stopped is None:
                return tool_err("not_found", f"job '{target}' not found", job_id=target)
            return tool_ok(job=_record_payload(stopped), killed=True)

        if act == "wait":
            deadline = time.monotonic() + timeout_s
            while rec.is_running() and time.monotonic() < deadline:
                await asyncio.sleep(0.4)
                rec = registry.get(target) or rec
            return tool_ok(job=_record_payload(rec), timed_out=bool(rec.is_running()))

        log_path = str(getattr(rec, "log_path", "") or "")
        body = ""
        if log_path:
            try:
                from pathlib import Path

                raw = Path(log_path).read_bytes()
                body = raw.decode("utf-8", errors="replace")
            except OSError as exc:
                return tool_err("io", f"could not read log: {exc}", job_id=target)
        if grep:
            try:
                compiled = re.compile(grep)
            except re.error as exc:
                return tool_err("invalid_grep", str(exc))
            body = "\n".join(line for line in body.splitlines() if compiled.search(line))
        clipped, truncated = _truncate(body, max_bytes)
        return tool_ok(
            job=_record_payload(rec),
            output=clipped,
            truncated=truncated,
        )
