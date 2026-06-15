"""Shared /subagents slash commands."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.subagents.registry import list_available_subagents

logger = logging.getLogger(__name__)


def _agent(host: Any) -> Any:
    return getattr(host, "agent", None)


async def _deliver_subagent_result_when_ready(host: Any, job_id: str) -> None:
    """Push background sub-agent output to the messenger when the job finishes."""
    agent = _agent(host)
    if not agent or not hasattr(agent, "subagents"):
        return
    mgr = agent.subagents
    handle = mgr.get_handle(job_id)
    if not handle:
        return
    try:
        timeout = handle.config.timeout
        result = await mgr.wait_for(job_id, timeout=timeout)
        text = (result.response or result.error or "").strip()
        if not text:
            return
        body = f"**Субагент `{job_id}` завершил работу:**\n\n{text}"
        if hasattr(host, "_send_text"):
            await host._send_text(body)
        elif hasattr(host, "_send_split_plain"):
            await host._send_split_plain(f"{job_id}:\n{text}")
        else:
            host.transcript_write(text[:4000])
    except Exception:
        logger.exception("Failed to deliver background sub-agent result for %s", job_id)


async def run_subagents_command(host: Any, command: str) -> None:
    """List, spawn, terminate, or show sub-agent results."""
    cmd = command.strip().lower()
    parts = cmd.split()
    agent = _agent(host)

    if not agent or not hasattr(agent, "subagents"):
        host.transcript_write("Agent not ready")
        return

    mgr = agent.subagents
    cfg = getattr(agent, "config", None)
    if cfg and not getattr(cfg, "enable_subagents", True):
        host.transcript_write(
            "Sub-agents disabled. Set enable_subagents: true in profile config."
        )
        return

    if cmd in ("/subagents", "/subagent-list", "/subagent list"):
        if hasattr(host, "_send_html"):
            await host._send_html(mgr.format_status_text(html=True))
        else:
            host.transcript_write(mgr.format_status_text())
        return

    if parts[0] in ("/subagent-spawn", "/subagent", "/subagent_spawn") and len(parts) >= 2:
        agent_type = parts[1]
        task = command.split(maxsplit=2)[2] if len(parts) >= 3 else ""
        if not task.strip():
            profile = str(getattr(host, "profile", None) or "default")
            types = ", ".join(
                item["name"] for item in list_available_subagents(profile=profile)
            )
            host.transcript_write(
                "Usage: /subagent-spawn <type> <task>\n"
                f"Types: {types}\n"
                "Custom types: /subagent-types"
            )
            return
        try:
            handle, _ = await mgr.spawn_typed(agent_type, task.strip(), wait=False)
            host.transcript_write(
                f"spawned {handle.name} ({handle.config.process_mode.value}) "
                f"pid={handle.process_id or '—'}"
            )
            try:
                asyncio.get_running_loop().create_task(
                    _deliver_subagent_result_when_ready(host, handle.name)
                )
            except RuntimeError:
                pass
        except Exception as e:
            host.transcript_write(f"spawn failed: {e}")
        return

    if parts[0] == "/subagent-terminate" and len(parts) >= 2:
        ok = await mgr.terminate(parts[1])
        host.transcript_write("terminated" if ok else f"not running: {parts[1]}")
        return

    if parts[0] in ("/subagent-reply", "/subagent_reply"):
        from core.subagents.interaction import try_route_subagent_reply

        handled, feedback = try_route_subagent_reply(agent, command.strip())
        host.transcript_write(feedback or "reply sent")
        return

    if parts[0] == "/subagent-result" and len(parts) >= 2:
        name = parts[1]
        handle = mgr.get_handle(name)
        if not handle:
            host.transcript_write(f"unknown job: {name}")
            return
        if not handle.is_done:
            host.transcript_write(f"{name} still running [{handle.status.value}]")
            return
        res = handle.result
        text = (res.response or res.error or "") if res else ""
        if hasattr(host, "_send_split_plain"):
            await host._send_split_plain(f"{name}:\n{text}")
        else:
            host.transcript_write(text[:4000])
        return

    host.transcript_write(
        "Sub-agents:\n"
        "  /subagents — list running\n"
        "  /subagent-types — manage custom types (TUI)\n"
        "  /subagent-types list — all types\n"
        "  /subagent-spawn <type> <task>\n"
        "  /subagent-result <job_id>\n"
        "  /subagent-reply <job_id> <answer>\n"
        "  /subagent-terminate <job_id>"
    )