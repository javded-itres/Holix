"""Background gateway lifecycle: start, stop, status, reload."""

from __future__ import annotations

import subprocess
import sys
import time

import httpx
from core.platform_compat import popen_background, port_check_hint, terminate_process

from cli.services.gateway_state import (
    LOG_PATH,
    GatewayState,
    clear_state,
    ensure_gateway_dir,
    health_url,
    is_process_alive,
    load_state,
)
from cli.utils.ports import resolve_listen_port
from cli.utils.rich_console import print_error, print_info, print_success, print_warning


def _running_state() -> GatewayState | None:
    state = load_state()
    if state is None:
        return None
    if is_process_alive(state.pid):
        return state
    clear_state()
    return None


def _wait_for_state(timeout: float = 15.0) -> GatewayState | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = load_state()
        if state is not None and is_process_alive(state.pid):
            return state
        time.sleep(0.2)
    return None


def _is_helix_health(state: GatewayState) -> bool:
    """True when Helix gateway responds on /health."""
    try:
        resp = httpx.get(health_url(state), timeout=2.0)
        if resp.status_code != 200:
            return False
        data = resp.json()
        return data.get("status") == "healthy" or "agent_ready" in data
    except Exception:
        return False


def _wait_for_healthy(state: GatewayState, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not is_process_alive(state.pid):
            return False
        if _is_helix_health(state):
            return True
        time.sleep(0.5)
    return False


def _print_log_tail(lines: int = 25) -> None:
    if not LOG_PATH.exists():
        return
    try:
        content = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = content[-lines:]
        if tail:
            print_warning("Recent gateway log:")
            for line in tail:
                print_info(line)
    except OSError:
        pass


def start_gateway_daemon(
    host: str,
    port: int,
    *,
    reload: bool = False,
    profile: str = "default",
    foreground: bool = False,
    with_docs: bool = False,
    docs_host: str = "127.0.0.1",
    docs_port: int = 8080,
) -> None:
    """Start gateway (+ companions) in background or foreground."""
    existing = _running_state()
    if existing is not None:
        print_error(
            f"Gateway already running (pid={existing.pid}, "
            f"http://{existing.host}:{existing.port})"
        )
        print_info("Stop it first: helix gateway stop")
        raise SystemExit(1)

    listen_port = resolve_listen_port(host, port)
    if listen_port != port:
        print_warning(f"Port {port} is in use; using {listen_port} instead")
        port = listen_port

    if foreground:
        from cli.services.supervisor import run_gateway_supervisor

        print_info(f"Starting gateway in foreground on {host}:{port}")
        run_gateway_supervisor(
            host,
            port,
            reload=reload,
            profile=profile,
            with_docs=with_docs,
            docs_host=docs_host,
            docs_port=docs_port,
        )
        return

    ensure_gateway_dir()
    log_handle = open(LOG_PATH, "a", encoding="utf-8")
    cmd = [
        sys.executable,
        "-m",
        "cli.services.gateway_worker",
        "--host",
        host,
        "--port",
        str(port),
        "--profile",
        profile,
    ]
    if reload:
        cmd.append("--reload")
    if with_docs:
        cmd.extend(["--with-docs", "--docs-host", docs_host, "--docs-port", str(docs_port)])

    try:
        popen_background(cmd, stdout=log_handle, stderr=subprocess.STDOUT)
    except OSError as e:
        log_handle.close()
        print_error(f"Failed to start gateway worker: {e}")
        raise SystemExit(1) from e

    log_handle.close()

    state = _wait_for_state()
    if state is None or not _wait_for_healthy(state):
        print_error("Gateway did not start or is not healthy.")
        print_info(f"Check logs and binding on port {port}: {port_check_hint(port)}")
        print_info(str(LOG_PATH))
        _print_log_tail()
        raise SystemExit(1)

    print_success(f"Gateway started in background (pid={state.pid})")
    print_info(f"Profile: {state.profile}")
    print_info(f"API: http://{state.host}:{state.port}")
    print_info(f"Health: {health_url(state)}")
    from cli.services.gateway_state import docs_url

    docs = docs_url(state)
    if docs:
        print_info(f"Docs: {docs}")
    print_info(f"Logs: {state.log_file}")
    print_info("Stop: helix gateway stop")


def stop_gateway_daemon() -> None:
    state = load_state()
    if state is None:
        print_warning("Gateway is not running (no state file)")
        return

    if state.telegram_pid and is_process_alive(state.telegram_pid):
        terminate_process(state.telegram_pid, grace=5.0)

    if state.docs_pid and is_process_alive(state.docs_pid):
        terminate_process(state.docs_pid, grace=5.0)

    if is_process_alive(state.pid):
        print_info(f"Stopping gateway (pid={state.pid})…")
        terminate_process(state.pid)
        print_success("Gateway stopped")
    else:
        print_warning(f"Gateway process {state.pid} is not running")

    clear_state()


def gateway_status() -> None:
    from cli.utils.rich_console import print_panel

    state = _running_state()
    if state is None:
        print_panel(
            "[yellow]Gateway is not running[/yellow]\n\n"
            "Start: [cyan]helix gateway start[/cyan]",
            title="Gateway Status",
            border_style="yellow",
        )
        return

    lines = [
        "[green]Status:[/green] running",
        f"[cyan]PID:[/cyan] {state.pid}",
        f"[cyan]Profile:[/cyan] {state.profile}",
        f"[cyan]Bind:[/cyan] {state.host}:{state.port}",
        f"[cyan]Reload:[/cyan] {'yes' if state.reload else 'no'}",
        f"[cyan]Started:[/cyan] {state.started_at}",
        f"[cyan]Logs:[/cyan] {state.log_file}",
    ]
    if state.telegram_pid:
        tg_alive = is_process_alive(state.telegram_pid)
        lines.append(
            f"[cyan]Telegram PID:[/cyan] {state.telegram_pid} "
            f"({'running' if tg_alive else 'stopped'})"
        )
    from cli.services.gateway_state import docs_url

    docs = docs_url(state)
    if docs:
        docs_alive = state.docs_pid is not None and is_process_alive(state.docs_pid)
        lines.append(
            f"[cyan]Docs:[/cyan] {docs} "
            f"({'running' if docs_alive else 'stopped'})"
        )

    try:
        resp = httpx.get(health_url(state), timeout=2.0)
        if resp.status_code == 200:
            lines.append(f"[cyan]Health:[/cyan] {resp.json().get('status', 'ok')}")
        else:
            lines.append(f"[yellow]Health:[/yellow] HTTP {resp.status_code}")
    except Exception as e:
        lines.append(f"[yellow]Health:[/yellow] unreachable ({e})")

    print_panel("\n".join(lines), title="Gateway Status", border_style="green")


def reload_gateway_daemon() -> None:
    state = _running_state()
    if state is None:
        print_warning("Gateway is not running. Starting with defaults…")
        from config import settings

        start_gateway_daemon(
            settings.gateway_host,
            settings.gateway_port,
            profile="default",
        )
        return

    host, port, profile, reload = state.host, state.port, state.profile, state.reload
    with_docs = state.docs_pid is not None
    docs_host = state.docs_host or "127.0.0.1"
    docs_port = state.docs_port or 8080
    print_info("Reloading gateway (stop → start)…")
    stop_gateway_daemon()
    time.sleep(0.5)
    start_gateway_daemon(
        host,
        port,
        reload=reload,
        profile=profile,
        with_docs=with_docs,
        docs_host=docs_host,
        docs_port=docs_port,
    )