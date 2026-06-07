"""Shared /cron commands for TUI, Telegram, and CLI."""

from __future__ import annotations

import re
from typing import Any

from core.cron.schedule_parse import parse_schedule_to_cron
from core.cron.store import CronStore

_CRON_FIELDS = re.compile(r"^(\S+\s+\S+\s+\S+\s+\S+\s+\S+)(?:\s+(.*))?$", re.DOTALL)


def _profile(host_or_profile: Any) -> str:
    if isinstance(host_or_profile, str):
        return host_or_profile
    return getattr(host_or_profile, "profile", "default")


def format_job_line(job) -> str:
    on = "[green]on[/green]" if job.enabled else "[dim]off[/dim]"
    status = job.last_status or "—"
    nxt = (job.next_run_at or "—")[:19]
    name = job.name or job.task[:40]
    result_hint = ""
    if getattr(job, "last_result", None):
        flat = job.last_result.replace("\n", " ")
        preview = flat[:72]
        suffix = "…" if len(flat) > 72 else ""
        result_hint = f"\n    last: [dim]{preview}{suffix}[/dim]"
    session_hint = ""
    if getattr(job, "session_id", None):
        session_hint = f"\n    notify session: [dim]{job.session_id}[/dim]"
    return (
        f"  [cyan]{job.id}[/cyan] {on} · [bold]{name}[/bold]\n"
        f"    cron: [dim]{job.cron_expression}[/dim]\n"
        f"    next: {nxt} · last: {status} · runs: {job.run_count}"
        f"{session_hint}{result_hint}"
    )


def format_jobs_message(profile: str = "default", *, html: bool = False) -> str:
    store = CronStore(profile)
    jobs = store.list_jobs()
    if not jobs:
        empty = "No cron jobs. Add with /cron add …"
        return f"<i>{empty}</i>" if html else f"[dim]{empty}[/dim]"

    if html:
        from integrations.telegram.markdown import escape_html

        lines = ["<b>Cron jobs</b>", ""]
        for job in jobs:
            flag = "✓" if job.enabled else "○"
            name = escape_html(job.name or job.task[:48])
            lines.append(
                f"{flag} <code>{escape_html(job.id)}</code> — {name}\n"
                f"   <code>{escape_html(job.cron_expression)}</code> · "
                f"next {(job.next_run_at or '—')[:19]}"
            )
        lines.append("")
        lines.append(
            "<i>/cron add schedule :: task · /cron enable|disable|remove id</i>"
        )
        return "\n".join(lines)

    lines = ["[bold]Cron jobs[/bold] (gateway scheduler runs due jobs)"]
    for job in jobs:
        lines.append(format_job_line(job))
    lines.append(
        "[dim]/cron add &lt;schedule&gt; :: &lt;task&gt; · /cron enable|disable|remove &lt;id&gt;[/dim]"
    )
    return "\n".join(lines)


def parse_add_arguments(rest: str) -> tuple[str, str]:
    """Parse schedule and task from add command tail."""
    raw = (rest or "").strip()
    if not raw:
        raise ValueError("Usage: /cron add <schedule> :: <task>")

    if "::" in raw:
        schedule, task = raw.split("::", 1)
        schedule, task = schedule.strip(), task.strip()
        if not schedule or not task:
            raise ValueError("Both schedule and task are required around ::")
        return parse_schedule_to_cron(schedule), task

    m = _CRON_FIELDS.match(raw)
    if m and m.group(2):
        return parse_schedule_to_cron(m.group(1)), m.group(2).strip()

    raise ValueError(
        "Usage: /cron add <schedule> :: <task>\n"
        "Example: /cron add every day at 9 :: Check disk usage\n"
        "Or: /cron add 0 9 * * * :: Summarize logs"
    )


def resolve_job_id(store: CronStore, token: str):
    token = (token or "").strip()
    if not token:
        raise ValueError("Job id required")
    job = store.get(token)
    if job:
        return job
    matches = [j for j in store.list_jobs() if j.id.startswith(token)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(f"Ambiguous id {token!r} ({len(matches)} matches)")
    raise KeyError(token)


async def run_cron_command(host: Any, command: str) -> None:
    """Handle /cron family; host must provide transcript_write and profile."""
    cmd = command.strip()
    lower = cmd.lower()
    parts = lower.split()
    profile = _profile(host)
    store = CronStore(profile)

    sub = parts[1] if len(parts) > 1 else ""

    if sub in ("", "list", "ls"):
        if hasattr(host, "push_screen"):
            from cli.tui.modals.cron_manager import open_cron_manager

            open_cron_manager(host, profile)
            return
        host.transcript_write(format_jobs_message(profile))
        return

    if sub == "add":
        rest = cmd.split(maxsplit=2)[2] if len(cmd.split()) > 2 else ""
        try:
            expr, task = parse_add_arguments(rest)
            
            notify_chat_id = None
            if hasattr(host, "_session") and hasattr(host._session, "chat_id"):
                notify_chat_id = host._session.chat_id

            session_id = getattr(host, "conversation_id", None)
            if not session_id and hasattr(host, "_session"):
                session_id = getattr(host._session, "conversation_id", None)

            job = store.add(
                task=task,
                cron_expression=expr,
                notify_chat_id=notify_chat_id,
                session_id=str(session_id) if session_id else None,
            )
            
            # Add notification hint if chat_id was captured
            notify_hint = ""
            if notify_chat_id:
                notify_hint = f"\n  📬 Уведомления в чат: {notify_chat_id}"
            
            session_hint = ""
            if job.session_id:
                session_hint = f"\n  session: [dim]{job.session_id}[/dim] (summaries here)"
            host.transcript_write(
                f"[green]Cron job added[/green] [cyan]{job.id}[/cyan]\n"
                f"  {job.cron_expression} → {job.name}\n"
                f"  next: {job.next_run_at or '—'}"
                f"{session_hint}{notify_hint}"
            )
        except Exception as e:
            host.transcript_write(f"[red]{e}[/red]")
        return

    if sub in ("enable", "on"):
        token = parts[2] if len(parts) > 2 else ""
        try:
            job = resolve_job_id(store, token)
            store.set_enabled(job.id, True)
            host.transcript_write(f"[green]Enabled[/green] {job.id} ({job.name})")
        except Exception as e:
            host.transcript_write(f"[red]{e}[/red]")
        return

    if sub in ("disable", "off"):
        token = parts[2] if len(parts) > 2 else ""
        try:
            job = resolve_job_id(store, token)
            store.set_enabled(job.id, False)
            host.transcript_write(f"[dim]Disabled[/dim] {job.id} ({job.name})")
        except Exception as e:
            host.transcript_write(f"[red]{e}[/red]")
        return

    if sub in ("bind", "session"):
        token = parts[2] if len(parts) > 2 else ""
        session_id = getattr(host, "conversation_id", None)
        if not session_id and hasattr(host, "_session"):
            session_id = getattr(host._session, "conversation_id", None)
        if not session_id:
            host.transcript_write("[red]No active session to bind[/red]")
            return
        try:
            job = resolve_job_id(store, token)
            job.session_id = str(session_id)
            store.update(job)
            host.transcript_write(
                f"[green]Cron {job.id}[/green] will post summaries to [cyan]{session_id}[/cyan]"
            )
        except Exception as e:
            host.transcript_write(f"[red]{e}[/red]")
        return

    if sub in ("remove", "rm", "delete", "del"):
        token = parts[2] if len(parts) > 2 else ""
        try:
            job = resolve_job_id(store, token)
            store.remove(job.id)
            host.transcript_write(f"[yellow]Removed[/yellow] {job.id}")
        except Exception as e:
            host.transcript_write(f"[red]{e}[/red]")
        return

    host.transcript_write(
        "[yellow]Cron:[/yellow] /cron list · /cron add … :: … · "
        "/cron enable|disable|remove &lt;id&gt;"
    )