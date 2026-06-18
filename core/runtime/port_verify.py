"""Verify which OS process listens on expected dev-server ports."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

from core.platform_compat import IS_WINDOWS
from core.runtime.port_utils import pids_listening_on_port


@dataclass(slots=True)
class PortListenerInfo:
    port: int
    pid: int
    command: str = ""


@dataclass(slots=True)
class PortCheckResult:
    port: int
    listener_pids: list[int] = field(default_factory=list)
    listener_commands: list[str] = field(default_factory=list)
    owned_by_process: bool = False
    issue: str = ""  # ok | foreign_listener | no_listener | dead_root


def process_command_line(pid: int) -> str:
    """Best-effort command line for a PID."""
    if pid <= 0:
        return ""
    try:
        if IS_WINDOWS:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"(Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\").CommandLine",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                return (result.stdout or "").strip()
        else:
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "command="],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                return (result.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return ""


def describe_port_listeners(port: int) -> list[PortListenerInfo]:
    """Return processes listening on ``port`` with command lines when available."""
    listeners: list[PortListenerInfo] = []
    seen: set[int] = set()
    for pid in pids_listening_on_port(port):
        if pid in seen:
            continue
        seen.add(pid)
        listeners.append(
            PortListenerInfo(
                port=port,
                pid=pid,
                command=process_command_line(pid),
            )
        )
    return listeners


def _pid_in_process_tree(descendant_pid: int, ancestor_pid: int) -> bool:
    if descendant_pid <= 0 or ancestor_pid <= 0:
        return False
    if descendant_pid == ancestor_pid:
        return True
    try:
        import psutil

        current = psutil.Process(descendant_pid)
        while True:
            if current.pid == ancestor_pid:
                return True
            parent = current.parent()
            if parent is None:
                return False
            current = parent
    except Exception:
        return descendant_pid == ancestor_pid


def _command_matches_expected(listener_cmd: str, expected_command: str) -> bool:
    listener = (listener_cmd or "").lower()
    expected = (expected_command or "").lower()
    if not listener or not expected:
        return False
    tokens = (
        "uvicorn",
        "gunicorn",
        "node",
        "npm",
        "vite",
        "next",
        "python",
        "manage.py",
        "runserver",
    )
    for token in tokens:
        if token in expected and token in listener:
            return True
    first = expected.split()[0:1]
    return bool(first and first[0] in listener)


def listener_owned_by_process(
    listener_pid: int,
    *,
    root_pid: int,
    root_running: bool,
    expected_command: str,
    listener_command: str,
) -> bool:
    if listener_pid <= 0:
        return False
    if not root_running:
        return False
    if _pid_in_process_tree(listener_pid, root_pid):
        return True
    if _command_matches_expected(listener_command, expected_command):
        return True
    return listener_pid == root_pid


def verify_expected_ports(
    *,
    expected_ports: list[int],
    root_pid: int,
    root_running: bool,
    expected_command: str,
) -> list[PortCheckResult]:
    """Check each expected port has our process (or child) listening."""
    results: list[PortCheckResult] = []
    for port in expected_ports:
        listeners = describe_port_listeners(port)
        if not listeners:
            results.append(
                PortCheckResult(
                    port=port,
                    owned_by_process=False,
                    issue="no_listener" if root_running else "dead_root",
                )
            )
            continue

        owned_any = False
        pids: list[int] = []
        commands: list[str] = []
        for item in listeners:
            pids.append(item.pid)
            commands.append(item.command or f"pid {item.pid}")
            if listener_owned_by_process(
                item.pid,
                root_pid=root_pid,
                root_running=root_running,
                expected_command=expected_command,
                listener_command=item.command,
            ):
                owned_any = True

        issue = "ok" if owned_any else "foreign_listener"
        results.append(
            PortCheckResult(
                port=port,
                listener_pids=pids,
                listener_commands=commands,
                owned_by_process=owned_any,
                issue=issue,
            )
        )
    return results


def format_port_checks(checks: list[PortCheckResult]) -> list[str]:
    lines: list[str] = []
    for check in checks:
        if not check.listener_pids:
            lines.append(f"  · port {check.port}: no listener ({check.issue})")
            continue
        for pid, cmd in zip(check.listener_pids, check.listener_commands, strict=False):
            owned = "ours" if check.owned_by_process else "foreign"
            short = cmd if len(cmd) <= 120 else cmd[:119] + "…"
            lines.append(f"  · port {check.port}: pid {pid} ({owned}) — {short}")
    return lines