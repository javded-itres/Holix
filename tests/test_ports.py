"""Port availability helpers."""

from __future__ import annotations

import socket

import pytest
from cli.utils.ports import is_port_available, resolve_listen_port


def test_is_port_available_detects_busy_port() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        _, port = sock.getsockname()
        assert is_port_available("127.0.0.1", port) is False


def test_resolve_listen_port_bumps_when_busy() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        busy_port = sock.getsockname()[1]
        resolved = resolve_listen_port("127.0.0.1", busy_port, max_offset=10)
        assert resolved == busy_port + 1


def test_resolve_listen_port_returns_preferred_when_free() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
    assert resolve_listen_port("127.0.0.1", free_port) == free_port


def test_resolve_listen_port_raises_when_exhausted() -> None:
    holders: list[socket.socket] = []
    try:
        for _ in range(3):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", 0))
            holders.append(s)
        base = holders[0].getsockname()[1]
        for s in holders[1:]:
            assert s.getsockname()[1] != base
        with pytest.raises(OSError, match="no free port"):
            resolve_listen_port("127.0.0.1", base, max_offset=0)
    finally:
        for s in holders:
            s.close()