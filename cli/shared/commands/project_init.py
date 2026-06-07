"""`/init` — deep project scan and `.helix/HELIX.md` generation."""

from __future__ import annotations

import asyncio
from typing import Any

from core.project.helix_md import HELIX_MD_REL_PATH
from core.project.init_prompt import build_init_user_message


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


def prefer_plan_mode(host: Any) -> None:
    """Switch host to plan_and_execute for structured onboarding."""
    modes = getattr(host, "_execution_modes", None)
    if not modes or "plan_and_execute" not in modes:
        return
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


async def run_project_init(host: Any) -> None:
    """Execute /init: analyze repo and write HELIX.md."""
    if not getattr(host, "agent", None):
        host.transcript_write(
            "[yellow]Agent not ready. Configure a model first (helix models add).[/yellow]"
        )
        return

    prefer_plan_mode(host)
    host.transcript_write(
        f"[dim]▸ /init — analyzing project → {HELIX_MD_REL_PATH} "
        f"(mode: plan_and_execute)[/dim]"
    )
    await dispatch_agent_message(host, build_init_user_message())