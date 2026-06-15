"""Shared /subagent-types commands for TUI."""

from __future__ import annotations

from typing import Any

from core.i18n import host_locale, t
from core.subagents.registry import list_available_subagents


async def run_subagent_types_command(host: Any, command: str) -> None:
    """Open TUI manager or print sub-agent type catalog."""
    lang = host_locale(host)
    parts = command.strip().split()
    sub = parts[1].lower() if len(parts) > 1 else ""

    if sub in {"", "manage", "create"}:
        if hasattr(host, "push_screen"):
            try:
                from cli.tui.modals.subagent_types_manager import open_subagent_types_manager

                open_subagent_types_manager(host)
            except Exception as exc:
                host.transcript_write(
                    f"[red]{t('tui.subagent_types.error', lang, error=exc)}[/red]"
                )
        else:
            host.transcript_write(f"[dim]{t('tui.subagent_types.cli_hint', lang)}[/dim]")
        return

    if sub == "list":
        profile = str(getattr(host, "profile", None) or "default")
        items = list_available_subagents(profile=profile)
        if not items:
            host.transcript_write(f"[dim]{t('tui.subagent_types.empty', lang)}[/dim]")
            return
        host.transcript_write(f"[bold]{t('tui.subagent_types.title', lang)}[/bold] ({profile})")
        for item in items:
            kind = (
                t("tui.subagent_types.builtin", lang)
                if item.get("builtin")
                else t("tui.subagent_types.custom", lang)
            )
            host.transcript_write(
                f"  [cyan]{item['name']}[/cyan] [{kind}] — {item.get('description') or '—'}"
            )
        host.transcript_write(f"[dim]{t('tui.subagent_types.list_footer', lang)}[/dim]")
        return

    host.transcript_write(f"[yellow]{t('tui.subagent_types.usage', lang)}[/yellow]")