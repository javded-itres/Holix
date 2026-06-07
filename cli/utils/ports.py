"""TCP listen port helpers."""

from __future__ import annotations

import socket


def is_port_available(host: str, port: int) -> bool:
    """Return True if ``host:port`` can be bound for listening."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def resolve_listen_port(
    host: str,
    preferred: int,
    *,
    max_offset: int = 100,
) -> int:
    """First free port in ``[preferred, preferred + max_offset]``."""
    if preferred < 1 or preferred > 65535:
        raise ValueError(f"invalid port: {preferred}")

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