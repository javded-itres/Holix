"""`/init` — deep project scan and `.holix/HOLIX.md` generation."""

from __future__ import annotations

import asyncio
from typing import Any

from core.i18n import host_locale, host_profile_name, t
from core.project.holix_md import HOLIX_MD_REL_PATH
from core.project.init_prompt import _holix_md_rel_path, build_init_user_message
from core.project.init_scan import scan_project_for_init, write_init_skeleton


def _agent_busy(host: Any) -> bool:
    session = getattr(host, "_session", None)
    if session is None:
        return False
    is_run_active = getattr(session, "is_run_active", None)
    if callable(is_run_active) and is_run_active():
        return True
    for attr in ("run_lock", "_run_lock"):
        lock = getattr(session, attr, None)
        if lock is not None and lock.locked():
            return True
    return False


def prefer_react_mode(host: Any) -> str | None:
    """Switch host to react — /init writes HOLIX.md via tools, not a plan gate."""
    modes = getattr(host, "_execution_modes", None)
    if not modes or "react" not in modes:
        return None
    host._execution_mode_index = modes.index("react")
    refresh = getattr(host, "_refresh_status_bar", None)
    if refresh:
        try:
            refresh()
        except Exception:
            pass
    return "react"


def choose_init_execution_mode(host: Any) -> str:
    """``/init`` always runs in ReAct.

    Plan & Execute would open a plan-review gate before writing ``HOLIX.md``.
    The init prompt already has a fixed checklist (scan → fill sections).
    """
    return prefer_react_mode(host) or "react"


async def _ack_init_start(host: Any, mode_label: str, *, target_dir: str | None = None) -> None:
    lang = host_locale(host)
    rel = (target_dir or "").strip().strip("/")
    if rel:
        from core.project.init_prompt import _holix_md_rel_path

        text = t(
            "init.ack_scoped",
            lang,
            path=_holix_md_rel_path(rel),
            dir=rel,
            mode=mode_label,
        )
    else:
        text = t("init.ack", lang, path=HOLIX_MD_REL_PATH, mode=mode_label)
    emit_system = getattr(host, "emit_system", None)
    if emit_system is not None:
        await emit_system(f"[dim]{text}[/dim]")
        return
    send_plain = getattr(host, "_send_plain", None)
    if send_plain is not None:
        await send_plain(text)
        return
    host.transcript_write(f"[dim]{text}[/dim]")


async def dispatch_agent_message(host: Any, message: str) -> None:
    """Send a user message to the host agent loop (TUI / Telegram)."""
    if hasattr(host, "_send_message"):
        await host._send_message(message)
        return
    if hasattr(host, "_send_message_manually"):
        await host._send_message_manually(message)
        return
    run = getattr(host, "_run_agent", None)
    if run is None:
        host.transcript_write("[red]Agent not available for /init[/red]")
        return
    coro = run(message)
    if asyncio.iscoroutine(coro):
        if hasattr(host, "run_worker"):
            host.run_worker(coro)
        else:
            await coro


async def run_project_init(host: Any, *, target_dir: str | None = None) -> None:
    """Execute /init: analyze repo and write HOLIX.md."""
    lang = host_locale(host)
    profile = host_profile_name(host)

    if not getattr(host, "agent", None):
        host.transcript_write(f"[yellow]{t('init.not_ready', lang)}[/yellow]")
        return

    if _agent_busy(host):
        host.transcript_write(f"[yellow]{t('init.busy', lang)}[/yellow]")
        return

    scope_rel = (target_dir or "").strip().strip("/") or None
    mode_label = choose_init_execution_mode(host)
    await _ack_init_start(host, mode_label, target_dir=scope_rel)

    # Prefer Studio/agent workspace — not process CWD (often Holix install tree).
    from core.project.workspace_root import resolve_project_root

    agent = getattr(host, "agent", None)
    project_root = resolve_project_root(
        agent=agent,
        config=getattr(agent, "config", None) if agent else None,
        host=host,
    )

    scan = scan_project_for_init(cwd=project_root, target_dir=scope_rel)
    holix_path = _holix_md_rel_path(scope_rel)
    template = t("init.holix_template", lang)
    write_init_skeleton(scan, holix_rel_path=holix_path, template=template, locale=lang)

    await dispatch_agent_message(
        host,
        build_init_user_message(
            locale=lang,
            profile_name=profile,
            target_dir=scope_rel,
            scan=scan,
            cwd=project_root,
        ),
    )
