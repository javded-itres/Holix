"""Shared /launch commands for TUI and other interactive hosts."""

from __future__ import annotations

import asyncio
import shlex
from typing import Any

from core.external_cli.launch_service import (
    LaunchServiceError,
    capture_session_output,
    kill_launch_session,
    launch_external_cli,
    list_clis,
    list_sessions,
    send_session_message,
)
from core.external_cli.platform import launch_supported
from core.external_cli.registry import list_cli_specs
from core.i18n import host_locale, t


def _known_cli_ids() -> frozenset[str]:
    return frozenset(spec.cli_id for spec in list_cli_specs())


async def run_launch_command(host: Any, command: str) -> None:
    """Handle ``/launch`` — manage assignments, start CLIs, sessions."""
    lang = host_locale(host)
    if not launch_supported():
        host.transcript_write(f"[yellow]{t('tui.launch.unsupported', lang)}[/yellow]")
        return

    profile = str(getattr(host, "profile", None) or "default")
    raw = (command or "").strip()
    try:
        parts = shlex.split(raw)
    except ValueError as exc:
        host.transcript_write(f"[red]{t('tui.launch.parse_error', lang, error=exc)}[/red]")
        return

    if not parts or parts[0].lower() not in {"/launch", "/launch_cli"}:
        host.transcript_write(f"[yellow]{t('tui.launch.usage', lang)}[/yellow]")
        return

    sub = parts[1].lower() if len(parts) > 1 else ""
    known = _known_cli_ids()

    if sub in {"", "manage", "setup"}:
        if hasattr(host, "push_screen"):
            try:
                from cli.tui.modals.launch_manager import open_launch_manager

                open_launch_manager(host)
            except Exception as exc:
                host.transcript_write(f"[red]{t('tui.launch.error', lang, error=exc)}[/red]")
        else:
            host.transcript_write(f"[dim]{t('tui.launch.cli_hint', lang)}[/dim]")
        return

    if sub == "list":
        rows = list_clis(profile)
        if not rows:
            host.transcript_write(f"[dim]{t('tui.launch.empty', lang)}[/dim]")
            return
        host.transcript_write(f"[bold]{t('tui.launch.title', lang)}[/bold] ({profile})")
        for row in rows:
            subagent = (
                row["agent_slot"]
                if row["assigned"]
                else t("tui.launch.not_assigned", lang)
            )
            host.transcript_write(
                f"  [cyan]{row['cli_id']}[/cyan] — {subagent} · "
                f"{t('tui.launch.col_model', lang)}={row['model_slot']}"
            )
        host.transcript_write(f"[dim]{t('tui.launch.list_footer', lang)}[/dim]")
        return

    if sub == "sessions":
        sessions = list_sessions(profile)
        if not sessions:
            host.transcript_write(f"[dim]{t('tui.launch.no_sessions', lang)}[/dim]")
            return
        host.transcript_write(f"[bold]{t('tui.launch.sessions_title', lang)}[/bold]")
        for session in sessions:
            host.transcript_write(
                f"  [cyan]{session['session_id']}[/cyan] · {session['cli_id']} · "
                f"{session['tmux_session']}:{session['window_index']} · "
                f"{session.get('model_name') or session.get('model_slot')}"
            )
        host.transcript_write(f"[dim]{t('tui.launch.sessions_footer', lang)}[/dim]")
        return

    if sub == "send" and len(parts) >= 4:
        session_ref = parts[2]
        message = " ".join(parts[3:])
        try:
            result = await asyncio.to_thread(
                send_session_message, profile, session_ref, message
            )
        except LaunchServiceError as exc:
            host.transcript_write(f"[red]{exc}[/red]")
            return
        host.transcript_write(
            t(
                "tui.launch.sent",
                lang,
                session=result.get("session_id") or result["tmux_session"],
            )
        )
        return

    if sub == "output" and len(parts) >= 3:
        session_ref = parts[2]
        try:
            result = await asyncio.to_thread(capture_session_output, profile, session_ref)
        except LaunchServiceError as exc:
            host.transcript_write(f"[red]{exc}[/red]")
            return
        text = (result.get("output") or "").strip() or t("tui.launch.output_empty", lang)
        host.transcript_write(f"[bold]{session_ref}[/bold]\n{text}")
        return

    if sub in {"kill", "stop"} and len(parts) >= 3:
        session_ref = parts[2]
        try:
            result = await asyncio.to_thread(kill_launch_session, profile, session_ref)
        except LaunchServiceError as exc:
            host.transcript_write(f"[red]{exc}[/red]")
            return
        host.transcript_write(
            t("tui.launch.killed", lang, session=result.get("session_id") or session_ref)
        )
        return

    if sub in known:
        cli_id = sub
        restart = False
        task = ""
        cwd = None
        model_slot = None
        rest = parts[2:]
        if rest and rest[0].lower() == "restart":
            restart = True
            rest = rest[1:]
        i = 0
        while i < len(rest):
            token = rest[i]
            if token in {"-t", "--task"} and i + 1 < len(rest):
                task = rest[i + 1]
                i += 2
                continue
            if token in {"-C", "--cwd"} and i + 1 < len(rest):
                cwd = rest[i + 1]
                i += 2
                continue
            if token in {"-m", "--model-slot"} and i + 1 < len(rest):
                model_slot = rest[i + 1]
                i += 2
                continue
            if not task:
                task = " ".join(rest[i:])
                break
            i += 1
        try:
            session = await asyncio.to_thread(
                launch_external_cli,
                profile,
                cli_id,
                task=task,
                cwd=cwd,
                model_slot=model_slot,
                restart=restart,
            )
        except LaunchServiceError as exc:
            host.transcript_write(f"[red]{exc}[/red]")
            return
        verb = t("tui.launch.restarted", lang) if restart else t("tui.launch.started", lang)
        host.transcript_write(
            f"[green]{verb}[/green] [cyan]{cli_id}[/cyan] → "
            f"{session['tmux_session']} (id={session['session_id']})"
        )
        if task:
            host.transcript_write(f"[dim]{t('tui.launch.task', lang)}: {task[:120]}[/dim]")
        host.transcript_write(
            f"[dim]{t('tui.launch.followup', lang, id=session['session_id'])}[/dim]"
        )
        return

    host.transcript_write(f"[yellow]{t('tui.launch.usage', lang)}[/yellow]")