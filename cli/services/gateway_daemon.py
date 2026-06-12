"""Background gateway lifecycle: start, stop, status, reload."""

from __future__ import annotations

import re
import subprocess
import sys
import time

import httpx
from core.platform_compat import popen_background, port_check_hint, terminate_process

from cli.services.gateway_state import (
    GatewayState,
    clear_state,
    health_url,
    is_process_alive,
    list_running_states,
    load_state,
    log_path,
)
from cli.utils.ports import resolve_listen_port
from cli.utils.profile import profile_cli_prefix
from cli.utils.rich_console import print_error, print_info, print_success, print_warning


def find_gateway_worker_pids(profile: str) -> list[int]:
    """Find gateway_worker processes for a profile (fallback when state.json is missing)."""
    try:
        proc = subprocess.run(
            ["ps", "-ax", "-o", "pid=,command="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except OSError:
        return []

    if proc.returncode != 0:
        return []

    pids: list[int] = []
    marker = f"--profile {profile}"
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if "gateway_worker" not in stripped or marker not in stripped:
            continue
        match = re.match(r"^(\d+)\s+", stripped)
        if match:
            pids.append(int(match.group(1)))
    return pids


def _running_state(profile: str) -> GatewayState | None:
    state = load_state(profile)
    if state is None:
        return None
    if is_process_alive(state.pid):
        return state
    clear_state(profile)
    return None


def _wait_for_state(profile: str, timeout: float = 15.0) -> GatewayState | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = load_state(profile)
        if state is not None and is_process_alive(state.pid):
            return state
        time.sleep(0.2)
    return None


def _is_holix_health(state: GatewayState) -> bool:
    """True when Holix gateway responds on /health."""
    try:
        resp = httpx.get(health_url(state), timeout=2.0)
        if resp.status_code != 200:
            return False
        data = resp.json()
        status = data.get("status")
        # /health returns {"status":"ok"} (Hermes); /health?detailed=true adds agent_ready.
        if status in {"healthy", "ok"}:
            return True
        return "agent_ready" in data
    except Exception:
        return False


def _wait_for_healthy(state: GatewayState, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not is_process_alive(state.pid):
            return False
        if _is_holix_health(state):
            return True
        time.sleep(0.5)
    return False


def _print_log_tail(profile: str, lines: int = 25) -> None:
    path = log_path(profile)
    if not path.exists():
        return
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
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
    from core.env_loader import bootstrap_profile_env

    bootstrap_profile_env(profile)
    existing = _running_state(profile)
    if existing is not None:
        print_error(
            f"Gateway already running for profile '{profile}' "
            f"(pid={existing.pid}, http://{existing.host}:{existing.port})"
        )
        print_info(f"Stop it first: {profile_cli_prefix(profile)} gateway stop")
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

    log_file = log_path(profile)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_handle = open(log_file, "a", encoding="utf-8")
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

    state = _wait_for_state(profile)
    if state is None or not _wait_for_healthy(state):
        print_error("Gateway did not start or is not healthy.")
        print_info(f"Check logs and binding on port {port}: {port_check_hint(port)}")
        print_info(str(log_file))
        _print_log_tail(profile)
        raise SystemExit(1)

    # Reload state: docs/Telegram PIDs are written after the initial save in gateway_worker.
    state = load_state(profile) or state

    print_success(f"Gateway started in background (pid={state.pid})")
    print_info(f"Profile: {state.profile}")
    print_info(f"API: http://{state.host}:{state.port}")
    print_info(f"Health: {health_url(state)}")
    from cli.services.gateway_state import docs_url

    docs = docs_url(state)
    if docs:
        docs_alive = state.docs_pid is not None and is_process_alive(state.docs_pid)
        print_info(f"Docs: {docs}" + ("" if docs_alive else " (process stopped — check gateway.log)"))
    elif with_docs:
        print_warning("Documentation site was not started (see gateway.log)")
        print_info("Try: holix docs  — or reinstall: uv tool install . --force")
    print_info(f"Logs: {state.log_file}")
    print_info("Stop: holix gateway stop")


def stop_gateway_daemon(profile: str = "default") -> None:
    state = load_state(profile)
    if state is None:
        orphans = find_gateway_worker_pids(profile)
        if not orphans:
            print_warning(f"Gateway is not running for profile '{profile}' (no state file)")
            return
        print_warning(
            f"No state file for profile '{profile}', but gateway worker process(es) found"
        )
        for pid in orphans:
            if is_process_alive(pid):
                print_info(f"Stopping orphan gateway (pid={pid})…")
                terminate_process(pid, grace=5.0)
        clear_state(profile)
        print_success("Gateway stopped")
        return

    if state.telegram_pid and is_process_alive(state.telegram_pid):
        terminate_process(state.telegram_pid, grace=5.0)

    if state.docs_pid and is_process_alive(state.docs_pid):
        terminate_process(state.docs_pid, grace=5.0)

    if state.docs_host and state.docs_port:
        from cli.utils.ports import wait_for_port_available

        bind_host = (
            "127.0.0.1" if state.docs_host in ("0.0.0.0", "::") else state.docs_host
        )
        wait_for_port_available(bind_host, state.docs_port, timeout=8.0)

    if is_process_alive(state.pid):
        print_info(f"Stopping gateway (pid={state.pid})…")
        terminate_process(state.pid)
        print_success("Gateway stopped")
    else:
        print_warning(f"Gateway process {state.pid} is not running")

    clear_state(profile)


def gateway_status(profile: str = "default") -> None:
    from cli.utils.rich_console import print_panel

    running = list_running_states()
    state = _running_state(profile)
    if state is None and not running:
        print_panel(
            f"[yellow]Gateway is not running for profile '{profile}'[/yellow]\n\n"
            f"Start: [cyan]{profile_cli_prefix(profile)} gateway start[/cyan]",
            title="Gateway Status",
            border_style="yellow",
        )
        return

    if state is None and running:
        lines = [f"[yellow]Profile '{profile}' has no running gateway.[/yellow]", ""]
        lines.append("[cyan]Other running gateways:[/cyan]")
        for other in running:
            lines.append(
                f"  • {other.profile}: http://{other.host}:{other.port} (pid={other.pid})"
            )
        print_panel("\n".join(lines), title="Gateway Status", border_style="yellow")
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


def reload_gateway_daemon(profile: str = "default") -> None:
    import os

    from core.env_loader import bootstrap_profile_env

    def _env_bool(name: str) -> bool:
        return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}

    bootstrap_profile_env(profile)
    state = _running_state(profile)
    if state is None:
        print_warning(f"Gateway is not running for profile '{profile}'. Starting…")
        from config import settings

        host = os.environ.get("HOLIX_GATEWAY_HOST", settings.gateway_host)
        port = int(os.environ.get("HOLIX_GATEWAY_PORT", str(settings.gateway_port)))
        with_docs = _env_bool("HOLIX_GATEWAY_WITH_DOCS") or _env_bool("HOLIX_GATEWAY_DOCS")
        docs_host = os.environ.get("HOLIX_DOCS_HOST", settings.docs_host)
        docs_port = int(os.environ.get("HOLIX_DOCS_PORT", str(settings.docs_port)))
        start_gateway_daemon(
            host,
            port,
            profile=profile,
            with_docs=with_docs,
            docs_host=docs_host,
            docs_port=docs_port,
        )
        return

    host, port, profile, reload = state.host, state.port, state.profile, state.reload
    with_docs = state.docs_pid is not None or _env_bool("HOLIX_GATEWAY_WITH_DOCS") or _env_bool(
        "HOLIX_GATEWAY_DOCS"
    )
    docs_host = state.docs_host or os.environ.get("HOLIX_DOCS_HOST", "127.0.0.1")
    docs_port = state.docs_port or int(os.environ.get("HOLIX_DOCS_PORT", "8080"))
    print_info(f"Reloading gateway for profile '{profile}' (stop → start)…")
    stop_gateway_daemon(profile)
    start_gateway_daemon(
        host,
        port,
        reload=reload,
        profile=profile,
        with_docs=with_docs,
        docs_host=docs_host,
        docs_port=docs_port,
    )