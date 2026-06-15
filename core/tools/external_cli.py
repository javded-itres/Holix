"""Delegate coding tasks to external CLIs running in tmux (Linux/macOS)."""

from __future__ import annotations

from pathlib import Path

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
                    "enum": ["launch", "send", "output", "list_sessions"],
                    "description": "launch: start CLI in tmux; send: prompt running session; output: read pane; list_sessions",
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
            from cli.core import get_profile_manager
            from cli.services.tmux_launcher import (
                capture_pane,
                find_launched_session,
                launch_cli_by_id,
                prune_dead_sessions,
                send_text,
                tmux_session_alive,
            )

            from core.external_cli.registry import get_cli_spec
        except ImportError as exc:
            return f"Error: external_cli unavailable ({exc})"

        config = get_profile_manager().load_profile(profile)

        if action == "list_sessions":
            sessions = prune_dead_sessions(profile)
            if not sessions:
                return "No active external CLI sessions. Use action=launch to start one."
            lines = []
            for s in sessions:
                lines.append(
                    f"- {s.session_id}: {s.cli_id} @ {s.tmux_session}:{s.window_index} "
                    f"model={s.model_name} cwd={s.cwd}"
                )
            return "\n".join(lines)

        if action == "launch":
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
            cwd = Path(cwd_raw) if cwd_raw else None
            task = (kwargs.get("task") or "").strip()
            model_slot = (kwargs.get("model_slot") or "").strip() or None
            launched = launch_cli_by_id(
                profile=profile,
                cli_id=cli_id,
                profile_config=config,
                cwd=cwd,
                task=task,
                model_slot=model_slot,
            )
            return (
                f"Launched {cli_id} in tmux session {launched.tmux_session} "
                f"(id={launched.session_id}, model={launched.model_name}, cwd={launched.cwd}). "
                f"Use action=send with session={launched.session_id} for follow-ups."
            )

        if action in {"send", "output"}:
            session_ref = (kwargs.get("session") or "").strip()
            if not session_ref:
                return "Error: session required for send/output."
            found = find_launched_session(profile, session_ref)
            if found:
                denied = external_cli_launch_error(
                    profile,
                    found.cli_id,
                    caller_agent_type=get_subagent_type(),
                )
                if denied:
                    return denied
            target = found.tmux_session if found else session_ref
            if not tmux_session_alive(target):
                return f"Error: tmux session not found: {session_ref}"
            window = found.window_index if found else 0
            if action == "send":
                task = (kwargs.get("task") or "").strip()
                if not task:
                    return "Error: task required for send."
                send_text(target, task, window_index=window)
                return f"Sent prompt to {target}:{window}"
            text = capture_pane(target, window_index=window, lines=50)
            return text or "(empty pane)"

        return f"Error: unknown action '{action}'"