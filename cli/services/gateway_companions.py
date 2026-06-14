"""Reload OS-process gateway companions (docs, Telegram subprocess)."""

from __future__ import annotations

from typing import Any

from cli.utils.ports import wait_for_port_available


def reload_os_companions(profile: str) -> dict[str, Any]:
    """Restart docs/Telegram subprocess companions without stopping gateway."""
    from core.platform_compat import is_process_alive, terminate_process

    from cli.services.gateway_state import load_state

    state = load_state(profile)
    if state is None:
        return {
            "docs": "not_running",
            "telegram_subprocess": "not_running",
            "max_subprocess": "not_running",
        }

    result: dict[str, Any] = {}

    if state.docs_host and state.docs_port:
        if state.docs_pid and is_process_alive(state.docs_pid):
            terminate_process(state.docs_pid, grace=5.0)
        bind_host = (
            "127.0.0.1" if state.docs_host in ("0.0.0.0", "::") else state.docs_host
        )
        wait_for_port_available(bind_host, state.docs_port, timeout=8.0)

        from cli.services.supervisor import _docs_subprocess

        proc = _docs_subprocess(
            state.docs_host,
            state.docs_port,
            profile,
            gateway_host=state.host,
            gateway_port=state.port,
        )
        result["docs"] = "restarted" if proc is not None else "skipped"
    else:
        result["docs"] = "not_configured"

    if state.telegram_pid:
        if is_process_alive(state.telegram_pid):
            terminate_process(state.telegram_pid, grace=5.0)
        from cli.services.supervisor import _telegram_subprocess

        proc = _telegram_subprocess(profile)
        result["telegram_subprocess"] = "restarted" if proc is not None else "stopped"
    else:
        result["telegram_subprocess"] = "in_process"

    if state.max_pid:
        if is_process_alive(state.max_pid):
            terminate_process(state.max_pid, grace=5.0)
        from cli.services.supervisor import _max_subprocess

        proc = _max_subprocess(profile)
        result["max_subprocess"] = "restarted" if proc is not None else "stopped"
    else:
        result["max_subprocess"] = "in_process"

    return result