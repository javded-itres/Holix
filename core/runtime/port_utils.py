"""Parse listen ports from shell commands and check availability."""

from __future__ import annotations

import re
import socket
import subprocess

from core.platform_compat import IS_WINDOWS, port_check_hint, terminate_process

_PORT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r":(\d{2,5})\b"),
    re.compile(r"--port[=\s]+(\d{2,5})\b", re.I),
    re.compile(r"-p\s+(\d{2,5})\b"),
    re.compile(r"\bPORT=(\d{2,5})\b"),
    re.compile(r"--listen[=\s]+[^\s]*:(\d{2,5})\b", re.I),
    re.compile(r"\blisten[=\s]+[^\s]*:(\d{2,5})\b", re.I),
)


def parse_listen_ports(command: str) -> list[int]:
    """Extract likely TCP listen ports from a dev-server command."""
    text = (command or "").strip()
    if not text:
        return []

    found: list[int] = []
    seen: set[int] = set()
    for pattern in _PORT_PATTERNS:
        for match in pattern.finditer(text):
            try:
                port = int(match.group(1))
            except (TypeError, ValueError):
                continue
            if 1 <= port <= 65535 and port not in seen:
                seen.add(port)
                found.append(port)
    return found


def is_port_available(host: str, port: int) -> bool:
    """Return True if host:port can be bound for listening."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def find_busy_ports(command: str, *, host: str = "127.0.0.1") -> list[int]:
    """Ports referenced in command that are already in use on host."""
    busy: list[int] = []
    for port in parse_listen_ports(command):
        if not is_port_available(host, port):
            busy.append(port)
    return busy


def ports_in_use(ports: list[int], *, host: str = "127.0.0.1") -> list[int]:
    """Return subset of ports that cannot be bound on host."""
    return [port for port in ports if not is_port_available(host, port)]


def pids_listening_on_port(port: int) -> list[int]:
    """Return PIDs listening on a TCP port (best effort, platform-specific)."""
    if port < 1 or port > 65535:
        return []

    pids: list[int] = []
    seen: set[int] = set()

    def _add(raw: str) -> None:
        for token in raw.split():
            if token.isdigit():
                pid = int(token)
                if pid > 0 and pid not in seen:
                    seen.add(pid)
                    pids.append(pid)

    try:
        if IS_WINDOWS:
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                needle = f":{port}"
                for line in result.stdout.splitlines():
                    if "LISTENING" in line and needle in line:
                        parts = line.split()
                        if parts:
                            _add(parts[-1])
        else:
            result = subprocess.run(
                ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                _add(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return pids


def extract_listen_ports_from_log(log_text: str) -> list[int]:
    """Infer listen ports from typical dev-server log lines."""
    if not (log_text or "").strip():
        return []
    patterns = (
        re.compile(r"https?://(?:127\.0\.0\.1|localhost|0\.0\.0\.0|\[::\]):(\d{2,5})\b", re.I),
        re.compile(r"\b(?:listening|ready|running)\s+(?:on\s+)?[^\s]*:(\d{2,5})\b", re.I),
        re.compile(r"\bUvicorn running on[^\n]*:(\d{2,5})\b", re.I),
    )
    found: list[int] = []
    seen: set[int] = set()
    for pattern in patterns:
        for match in pattern.finditer(log_text):
            try:
                port = int(match.group(1))
            except (TypeError, ValueError):
                continue
            if 1 <= port <= 65535 and port not in seen:
                seen.add(port)
                found.append(port)
    return found


def kill_listeners_on_ports(ports: list[int], *, retries: int = 2) -> list[int]:
    """Terminate processes listening on the given ports. Returns killed PIDs."""
    if not ports:
        return []

    killed: list[int] = []
    seen: set[int] = set()
    for _ in range(max(1, retries)):
        round_killed: list[int] = []
        for port in ports:
            for pid in pids_listening_on_port(port):
                if pid in seen:
                    continue
                seen.add(pid)
                try:
                    terminate_process(pid, grace=1.5)
                    round_killed.append(pid)
                except OSError:
                    pass
        killed.extend(round_killed)
        if not ports_in_use(ports):
            break
    return killed


def force_free_ports(ports: list[int], *, wait_s: float = 0.35) -> list[int]:
    """Kill listeners and wait until ports are bindable (best effort)."""
    import time

    unique = list(dict.fromkeys(ports))
    if not unique:
        return []
    killed = kill_listeners_on_ports(unique, retries=3)
    if wait_s > 0:
        time.sleep(wait_s)
    still_busy = ports_in_use(unique)
    if still_busy:
        killed.extend(kill_listeners_on_ports(still_busy, retries=2))
    return killed


def format_port_conflict_message(busy_ports: list[int], *, host: str = "127.0.0.1") -> str:
    """Human-readable guidance when listen ports are already taken."""
    ports = ", ".join(str(p) for p in busy_ports)
    hints = "; ".join(port_check_hint(p) for p in busy_ports[:3])
    return (
        f"Port(s) {ports} on {host} are already in use. "
        f"Do not start the server until the port is free.\n"
        f"- Inspect what holds the port: {hints}\n"
        f"- Or stop the Holix background process: stop_background_process\n"
        f"- Or restart on another port (e.g. PORT=8001 or --port 8001 in the command)\n"
        f"Fix the port conflict, then call start_background_process again."
    )