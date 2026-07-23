"""TCP listen port helpers."""

from __future__ import annotations

import socket
import time


def _connect_host(host: str) -> str:
    """Map wildcard bind hosts to a loopback address for probe connects."""
    h = (host or "").strip()
    if not h or h == "0.0.0.0":
        return "127.0.0.1"
    if h in {"::", "[::]"}:
        return "::1"
    return h


def is_port_available(host: str, port: int) -> bool:
    """Return True if ``host:port`` can be bound for listening.

    1. If something already accepts TCP connections, treat as busy (cross-platform;
       Windows ``SO_REUSEADDR`` alone can still bind over an active listener).
    2. Otherwise try to bind: on Windows use ``SO_EXCLUSIVEADDRUSE``; on Unix use
       ``SO_REUSEADDR`` so a just-killed listener in TIME_WAIT is not treated as
       busy (uvicorn binds the same way). Without that, Studio often bumps
       8788→8789 after restart while nginx still proxies to 8788.
    """
    port_i = int(port)
    family = socket.AF_INET6 if ":" in host else socket.AF_INET

    # Active listener → busy (works on Linux/macOS/Windows).
    try:
        with socket.socket(family, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.25)
            if probe.connect_ex((_connect_host(host), port_i)) == 0:
                return False
    except OSError:
        pass

    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            # Windows: exclusive bind fails when another process owns the port.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if family == socket.AF_INET6:
                try:
                    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
                except OSError:
                    pass
        sock.bind((host, port_i))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def wait_for_port_available(
    host: str,
    port: int,
    *,
    timeout: float = 10.0,
    poll_interval: float = 0.1,
) -> bool:
    """Wait until ``host:port`` can be bound, or until ``timeout`` elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_port_available(host, port):
            return True
        time.sleep(poll_interval)
    return is_port_available(host, port)


def resolve_listen_port(
    host: str,
    preferred: int,
    *,
    max_offset: int = 100,
    wait_timeout: float = 0,
) -> int:
    """First free port in ``[preferred, preferred + max_offset]``.

    When ``wait_timeout`` > 0, wait for ``preferred`` to free up before
    scanning alternate ports (used after gateway reload stops docs).
    """
    if preferred < 1 or preferred > 65535:
        raise ValueError(f"invalid port: {preferred}")

    if wait_timeout > 0 and not is_port_available(host, preferred):
        wait_for_port_available(host, preferred, timeout=wait_timeout)

    for offset in range(max_offset + 1):
        port = preferred + offset
        if port > 65535:
            break
        if is_port_available(host, port):
            return port

    raise OSError(
        f"no free port in range {preferred}–{min(preferred + max_offset, 65535)} "
        f"on {host}"
    )
