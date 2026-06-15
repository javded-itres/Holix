"""Shared /launch commands for TUI."""

from __future__ import annotations

from typing import Any

from core.external_cli.assignment import list_cli_assignment_rows
from core.external_cli.platform import launch_supported
from core.i18n import host_locale, t


def _resolve_binary(spec) -> str | None:
    from cli.launch.setup_wizard import _binary_installed

    return _binary_installed(spec)


async def run_launch_command(host: Any, command: str) -> None:
    """Handle ``/launch`` — open TUI manager or print assignment summary."""
    lang = host_locale(host)
    if not launch_supported():
        host.transcript_write(f"[yellow]{t('tui.launch.unsupported', lang)}[/yellow]")
        return

    parts = command.strip().split()
    sub = parts[1].lower() if len(parts) > 1 else ""

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
        profile = str(getattr(host, "profile", None) or "default")
        rows = list_cli_assignment_rows(profile, resolve_binary=_resolve_binary)
        if not rows:
            host.transcript_write(f"[dim]{t('tui.launch.empty', lang)}[/dim]")
            return
        host.transcript_write(f"[bold]{t('tui.launch.title', lang)}[/bold] ({profile})")
        for row in rows:
            subagent = (
                row.agent_slot
                if row.assigned
                else t("tui.launch.not_assigned", lang)
            )
            host.transcript_write(
                f"  [cyan]{row.cli_id}[/cyan] — {subagent} · "
                f"{t('tui.launch.col_model', lang)}={row.model_slot}"
            )
        host.transcript_write(f"[dim]{t('tui.launch.list_footer', lang)}[/dim]")
        return

    host.transcript_write(f"[yellow]{t('tui.launch.usage', lang)}[/yellow]")