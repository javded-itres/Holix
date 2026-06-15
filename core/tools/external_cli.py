"""Delegate coding tasks to external CLIs running in tmux (Linux/macOS)."""

from __future__ import annotations

from core.external_cli.access import external_cli_launch_error
from core.external_cli.platform import launch_supported
from core.tools.base import BaseTool
from core.tools.execution_context import get_profile_name, get_subagent_type


class ExternalCliTool(BaseTool):
    """Launch or message external coding CLIs (Claude Code, OpenCode, …) via tmux."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "external_cli"
        self.description = (
            "Launch or send tasks to external coding CLIs in tmux (claude, opencode, grok-build, …). "
            "Only available to sub-agents explicitly assigned in holix launch setup. "
            "Uses LLM credentials from the active Holix profile. Linux/macOS only."
        )
        self.risk_level = "medium"
        self.parameters = {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["launch", "restart", "send", "output", "list_sessions"],
                    "description": (
                        "launch: start CLI in tmux; restart: kill old sessions and start fresh; "
                        "send: prompt running session; output: read pane; list_sessions"
                    ),
                },
                "cli_id": {
                    "type": "string",
                    "description": "CLI id: claude, opencode, grok-build, gigacode, aider",
                },
                "task": {
                    "type": "string",
                    "description": "Initial or follow-up prompt for the external CLI",
                },
                "session": {
                    "type": "string",
                    "description": "Holix session id or tmux session name (for send/output)",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory for launch",
                },
                "model_slot": {
                    "type": "string",
                    "description": "Profile model slot (main, coder, …)",
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs) -> str:
        if not launch_supported():
            return "Error: external_cli is available only on Linux and macOS."

        action = (kwargs.get("action") or "").strip().lower()
        profile = get_profile_name() or "default"

        try:
            from core.external_cli.launch_service import (
                LaunchServiceError,
                capture_session_output,
                launch_external_cli,
                list_sessions,
                send_session_message,
            )
            from core.external_cli.registry import get_cli_spec
        except ImportError as exc:
            return f"Error: external_cli unavailable ({exc})"

        if action == "list_sessions":
            sessions = list_sessions(profile)
            if not sessions:
                return "No active external CLI sessions. Use action=launch to start one."
            lines = []
            for s in sessions:
                lines.append(
                    f"- {s.session_id}: {s.cli_id} @ {s.tmux_session}:{s.window_index} "
                    f"model={s.model_name} cwd={s.cwd}"
                )
            return "\n".join(lines)

        if action in {"launch", "restart"}:
            cli_id = (kwargs.get("cli_id") or "").strip().lower()
            if not cli_id or not get_cli_spec(cli_id):
                return "Error: cli_id required (claude, opencode, grok-build, gigacode, aider)."
            denied = external_cli_launch_error(
                profile,
                cli_id,
                caller_agent_type=get_subagent_type(),
            )
            if denied:
                return denied
            cwd_raw = (kwargs.get("cwd") or "").strip()
            cwd = cwd_raw or None
            task = (kwargs.get("task") or "").strip()
            model_slot = (kwargs.get("model_slot") or "").strip() or None
            try:
                launched = launch_external_cli(
                    profile,
                    cli_id,
                    task=task,
                    cwd=cwd,
                    model_slot=model_slot,
                    restart=action == "restart",
                )
            except LaunchServiceError as exc:
                return f"Error: {exc}"
            verb = "Restarted" if action == "restart" else "Launched"
            return (
                f"{verb} {cli_id} in tmux session {launched['tmux_session']} "
                f"(id={launched['session_id']}, model={launched['model_name']}, "
                f"cwd={launched['cwd']}). "
                f"Use action=send with session={launched['session_id']} for follow-ups."
            )

        if action in {"send", "output"}:
            session_ref = (kwargs.get("session") or "").strip()
            if not session_ref:
                return "Error: session required for send/output."
            from cli.services.tmux_launcher import find_launched_session

            found = find_launched_session(profile, session_ref)
            if found:
                denied = external_cli_launch_error(
                    profile,
                    found.cli_id,
                    caller_agent_type=get_subagent_type(),
                )
                if denied:
                    return denied
            if action == "send":
                task = (kwargs.get("task") or "").strip()
                if not task:
                    return "Error: task required for send."
                try:
                    result = send_session_message(profile, session_ref, task)
                except LaunchServiceError as exc:
                    return f"Error: {exc}"
                return f"Sent prompt to {result['tmux_session']}:{result['window_index']}"
            try:
                result = capture_session_output(profile, session_ref, lines=50)
            except LaunchServiceError as exc:
                return f"Error: {exc}"
            return result.get("output") or "(empty pane)"

        return f"Error: unknown action '{action}'"