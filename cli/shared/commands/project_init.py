"""`/init` — deep project scan and `.holix/HOLIX.md` generation."""

from __future__ import annotations

import asyncio
from typing import Any

from core.project.holix_md import HOLIX_MD_REL_PATH
from core.project.init_prompt import build_init_user_message


def _is_messenger_host(host: Any) -> bool:
    """Telegram / MAX hosts carry a per-chat session object."""
    return getattr(host, "_session", None) is not None


def _agent_busy(host: Any) -> bool:
    session = getattr(host, "_session", None)
    if session is not None:
        lock = getattr(session, "run_lock", None)
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
    if _is_messenger_host(host):
        return prefer_react_mode(host) or "react"
    return prefer_plan_mode(host) or "plan_and_execute"


async def _ack_init_start(host: Any, mode_label: str) -> None:
    text = (
        f"▸ /init — анализ проекта → {HOLIX_MD_REL_PATH} (режим: {mode_label})"
    )
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


async def run_project_init(host: Any) -> None:
    """Execute /init: analyze repo and write HOLIX.md."""
    if not getattr(host, "agent", None):
        host.transcript_write(
            "[yellow]Agent not ready. Configure a model first (holix models add).[/yellow]"
        )
        return

    if _agent_busy(host):
        host.transcript_write(
            "[yellow]Агент занят предыдущим запросом. "
            "Дождитесь ответа или отправьте /stop.[/yellow]"
        )
        return

    mode_label = choose_init_execution_mode(host)
    await _ack_init_start(host, mode_label)
    await dispatch_agent_message(host, build_init_user_message())