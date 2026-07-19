"""`/init` — deep project scan and `.holix/HOLIX.md` generation."""

from __future__ import annotations

import asyncio
from typing import Any

from core.i18n import host_locale, host_profile_name, t
from core.project.holix_md import HOLIX_MD_REL_PATH
from core.project.init_prompt import _holix_md_rel_path, build_init_user_message
from core.project.init_scan import scan_project_for_init, write_init_skeleton


def _is_messenger_host(host: Any) -> bool:
    """Telegram / MAX hosts — not Studio/TUI (they also expose `_session`)."""
    session = getattr(host, "_session", None)
    if session is None:
        return False
    from integrations.max.session import MaxChatSession
    from integrations.telegram.session import ChatSession

    return isinstance(session, (ChatSession, MaxChatSession))


def _is_studio_host(host: Any) -> bool:
    """Holix Studio — structured init prompt, no plan-review gate."""
    session = getattr(host, "_session", None)
    if session is None:
        return False
    mod = getattr(type(session), "__module__", "") or ""
    return mod.startswith("holix_studio.") or type(session).__name__ == "StudioSession"


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


def prefer_plan_mode(host: Any) -> str | None:
    """Switch host to plan_and_execute for structured onboarding (TUI)."""
    modes = getattr(host, "_execution_modes", None)
    if not modes or "plan_and_execute" not in modes:
        return None
    host._execution_mode_index = modes.index("plan_and_execute")
    refresh = getattr(host, "_refresh_status_bar", None)
    if refresh:
        try:
            refresh()
        except Exception:
            pass
    cycle = getattr(host, "action_cycle_execution_mode", None)
    if cycle and hasattr(host, "config"):
        try:
            from config import settings

            settings.execution_mode = "plan_and_execute"
        except Exception:
            pass
    return "plan_and_execute"


def prefer_react_mode(host: Any) -> str | None:
    """Switch host to react — avoids plan-review blocking in messengers."""
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
    """Pick execution mode for /init based on host type."""
    if _is_messenger_host(host) or _is_studio_host(host):
        return prefer_react_mode(host) or "react"
    return prefer_plan_mode(host) or "plan_and_execute"


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

    scan = scan_project_for_init(target_dir=scope_rel)
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
        ),
    )