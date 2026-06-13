"""Shared /skills command for TUI, Telegram, and CLI chat."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.skills.assignments import agents_for_skill
from core.skills.manager import SkillsManager


def _agent_slot(host: Any) -> str:
    return (
        getattr(host, "agent_slot", None)
        or getattr(getattr(host, "agent", None), "agent_slot", None)
        or "main"
    )


def _load_skills(host: Any) -> tuple[SkillsManager, str, Any]:
    config = getattr(host, "config", None)
    if config is None:
        from cli.core import init_profile

        profile = getattr(host, "profile", "default")
        config = init_profile(profile)

    from core.di import resolve_runtime_config

    runtime = resolve_runtime_config(config)
    mgr = SkillsManager(runtime)
    if getattr(host, "agent", None) and hasattr(host.agent, "skills"):
        mgr = host.agent.skills
        if not mgr.all_skills:
            mgr.load_all_skills()
    else:
        mgr.load_all_skills()

    return mgr, _agent_slot(host), config


def format_skills_message(
    host: Any,
    *,
    agent_slot: str | None = None,
    limit: int = 40,
    html: bool = False,
) -> str:
    mgr, default_slot, config = _load_skills(host)
    slot = agent_slot or default_slot
    skills_dir = Path(getattr(config, "skills_dir", "") or mgr.skills_dir)

    all_names = sorted(mgr.all_skills.keys())
    allowed_names = sorted(mgr.list_skill_names_for_agent(slot))
    assigns = getattr(config, "skill_assignments", None) or {}

    if html:
        from integrations.telegram.markdown import escape_html

        lines = [
            "<b>Skills</b>",
            f"dir: <code>{escape_html(str(skills_dir))}</code>",
            f"loaded: {len(all_names)} · agent <code>{escape_html(slot)}</code>: {len(allowed_names)}",
            "",
        ]
        if not all_names:
            lines.append("<i>No skills on disk. Use /hub or <code>holix hub install</code>.</i>")
            return "\n".join(lines)

        for name in allowed_names[:limit]:
            skill = mgr.all_skills.get(name, {})
            desc = escape_html((skill.get("description") or "")[:72])
            src = skill.get("_source", "")
            tag = f" [{src}]" if src else ""
            lines.append(f"• <code>{escape_html(name)}</code>{tag}")
            if desc:
                lines.append(f"  <i>{desc}</i>")

        if len(allowed_names) > limit:
            lines.append(f"<i>… +{len(allowed_names) - limit} more</i>")

        if slot != "main" and assigns.get(slot):
            lines.append("")
            lines.append(
                f"<i>Profile allowlist for '{escape_html(slot)}': "
                f"{len(assigns[slot])} skill(s). "
                f"<code>holix skills assign</code> to change.</i>"
            )
        elif slot == "main":
            lines.append("")
            lines.append(
                "<i>Main agent uses all profile skills. "
                "Sub-agents: <code>holix skills assign</code>.</i>"
            )

        return "\n".join(lines)

    lines = [
        f"[bold]Skills[/bold] · dir {skills_dir}",
        f"loaded {len(all_names)} · agent [cyan]{slot}[/cyan]: {len(allowed_names)} available",
        "",
    ]
    if not all_names:
        lines.append("[dim]No skills found. Try /hub or `holix hub install`.[/dim]")
        return "\n".join(lines)

    for name in allowed_names[:limit]:
        skill = mgr.all_skills.get(name, {})
        desc = (skill.get("description") or "")[:72]
        src = skill.get("_source", "")
        src_s = f" [{src}]" if src else ""
        assigned = ", ".join(agents_for_skill(assigns, name))
        extra = f" → {assigned}" if assigned else ""
        lines.append(f"  [cyan]{name}[/cyan]{src_s}{extra}")
        if desc:
            lines.append(f"    [dim]{desc}[/dim]")

    if len(allowed_names) > limit:
        lines.append(f"  [dim]… +{len(allowed_names) - limit} more[/dim]")

    if slot != "main" and assigns.get(slot):
        lines.append(
            f"[dim]Allowlist for '{slot}': {len(assigns[slot])} skill(s). "
            f"`holix skills assign` to change.[/dim]"
        )
    elif slot == "main":
        lines.append(
            "[dim]Main agent: all profile skills. "
            "Sub-agents: `holix skills assign`.[/dim]"
        )

    return "\n".join(lines)


async def _send_telegram_skills_html(host: Any, html: str) -> None:
    """Deliver skills HTML to Telegram, splitting when over message size limit."""
    if hasattr(host, "_send_html_split"):
        await host._send_html_split(html)
        return
    if hasattr(host, "_send_html"):
        from integrations.telegram.markdown import split_telegram_html

        chunks = split_telegram_html(html)
        for chunk in chunks:
            await host._send_html(chunk)
        return
    host.transcript_write(html)


async def run_skills_command(host: Any, command: str = "/skills") -> None:
    """Show loaded skills for the current profile and agent slot."""
    parts = command.strip().split(maxsplit=1)
    slot_arg = parts[1].strip() if len(parts) > 1 else None

    if hasattr(host, "_interactive") and not slot_arg:
        await host._interactive.show_skills_picker()
        return

    if hasattr(host, "_send_html"):
        html = format_skills_message(
            host,
            agent_slot=slot_arg,
            html=True,
            limit=20,
        )
        await _send_telegram_skills_html(host, html)
        return

    text = format_skills_message(host, agent_slot=slot_arg, html=False)
    if hasattr(host, "_send_split_plain"):
        await host._send_split_plain(text)
    else:
        host.transcript_write(text)