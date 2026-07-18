"""Parse listen ports from shell commands and check availability."""

from __future__ import annotations

import re
import socket
import subprocess
from pathlib import Path

from core.platform_compat import IS_WINDOWS, port_check_hint, terminate_process

_PORT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r":(\d{2,5})\b"),
    re.compile(r"--port[=\s]+(\d{2,5})\b", re.I),
    re.compile(r"-p\s+(\d{2,5})\b"),
    re.compile(r"\bPORT=(\d{2,5})\b"),
    re.compile(r"--listen[=\s]+[^\s]*:(\d{2,5})\b", re.I),
    re.compile(r"\blisten[=\s]+[^\s]*:(\d{2,5})\b", re.I),
    re.compile(r"\bhttp\.server\s+(\d{2,5})\b", re.I),
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


def _pids_from_ss_listeners(port: int) -> list[int]:
    """Parse ``ss -tlnp`` output when ``lsof`` is unavailable."""
    pids: list[int] = []
    seen: set[int] = set()
    needle = f":{port}"
    try:
        result = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode != 0:
            return []
        for line in result.stdout.splitlines():
            if needle not in line or "LISTEN" not in line:
                continue
            for match in re.finditer(r"pid=(\d+)", line):
                pid = int(match.group(1))
                if pid > 0 and pid not in seen:
                    seen.add(pid)
                    pids.append(pid)
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    return pids


def _pids_from_proc_cmdline_port(port: int) -> list[int]:
    """Find listener PIDs by scanning ``/proc/*/cmdline`` when ``lsof`` is blocked."""
    if port < 1 or port > 65535:
        return []
    if port not in ports_in_use([port]):
        return []
    pattern = re.compile(
        rf"(?:--port[=\s]+{port}\b|-p\s+{port}\b|:{port}\b|\.{port}\b)",
        re.I,
    )
    pids: list[int] = []
    seen: set[int] = set()
    try:
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            if pid in seen:
                continue
            try:
                raw = (entry / "cmdline").read_bytes()
            except OSError:
                continue
            text = raw.replace(b"\x00", b" ").decode("utf-8", errors="replace")
            if pattern.search(text):
                seen.add(pid)
                pids.append(pid)
    except OSError:
        return []
    return pids


def _pids_from_fuser(port: int) -> list[int]:
    """Resolve listener PIDs via ``fuser`` when ``lsof``/``ss -p`` are restricted (e.g. ``sg docker``)."""
    pids: list[int] = []
    seen: set[int] = set()
    try:
        result = subprocess.run(
            ["fuser", f"{port}/tcp"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        text = f"{result.stdout or ''} {result.stderr or ''}"
        for token in text.replace("/tcp", " ").split():
            if not token.isdigit():
                continue
            pid = int(token)
            if pid == port or pid <= 0 or pid in seen:
                continue
            seen.add(pid)
            pids.append(pid)
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    return pids


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
            if not pids:
                pids = _pids_from_ss_listeners(port)
            if not pids:
                pids = _pids_from_fuser(port)
            if not pids:
                pids = _pids_from_proc_cmdline_port(port)
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return pids


def extract_listen_ports_from_log(log_text: str) -> list[int]:
    """Infer *listen* ports from typical dev-server bind lines.

    Only match lines that mean the process is accepting connections. Client-side
    URLs (e.g. ``API: http://localhost:8000/users`` in a watcher log) must not
    be treated as owned listen ports — that steals preview targets from the real
    server and hides the worker process.
    """
    if not (log_text or "").strip():
        return []
    patterns = (
        # Next.js / Vite style: "- Local: http://localhost:3001"
        re.compile(r"\bLocal:\s+https?://[^\s]*:(\d{2,5})\b", re.I),
        # "listening on 0.0.0.0:8000" / "running on http://127.0.0.1:5173"
        re.compile(
            r"\b(?:listening|ready|running)\s+(?:on\s+)?(?:https?://)?(?:127\.0\.0\.1|localhost|0\.0\.0\.0|\[::\]|\*):(\d{2,5})\b",
            re.I,
        ),
        re.compile(r"\bUvicorn running on[^\n]*:(\d{2,5})\b", re.I),
        re.compile(r"\bstarted server on[^\n]*:(\d{2,5})\b", re.I),
        re.compile(r"\bServing HTTP on [^\s]+ port (\d{2,5})\b", re.I),
        # Explicit bind host:port without "http" client path noise
        re.compile(
            r"\b(?:bound to|bind(?:ing)? to|listen(?:ing)? at)\s+(?:https?://)?(?:127\.0\.0\.1|localhost|0\.0\.0\.0|\[::\]|\*):(\d{2,5})\b",
            re.I,
        ),
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