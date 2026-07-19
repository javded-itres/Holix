"""Tests for background process port parsing and availability checks."""

from __future__ import annotations

import socket
from unittest.mock import patch

from core.runtime.port_utils import (
    extract_listen_ports_from_log,
    find_busy_ports,
    format_port_conflict_message,
    kill_listeners_on_ports,
    parse_listen_ports,
)


def test_parse_listen_ports_variants() -> None:
    assert parse_listen_ports("uvicorn app:app --host 0.0.0.0 --port 8000") == [8000]
    assert parse_listen_ports("npm run dev -- -p 3000") == [3000]
    assert parse_listen_ports("PORT=5173 npm run dev") == [5173]
    assert parse_listen_ports("python -m http.server") == []
    assert parse_listen_ports("python3 -m http.server 3000") == [3000]


def test_extract_listen_ports_from_log_http_server() -> None:
    log = "Serving HTTP on 0.0.0.0 port 3000 (http://0.0.0.0:3000/) ...\n"
    # Port comes from the "Serving HTTP on … port N" bind line, not the client URL.
    assert extract_listen_ports_from_log(log) == [3000]


def test_format_port_conflict_message_includes_hint() -> None:
    msg = format_port_conflict_message([8000])
    assert "8000" in msg
    assert "stop_background_process" in msg


def test_kill_listeners_on_ports_invokes_terminate(monkeypatch) -> None:
    killed: list[int] = []

    monkeypatch.setattr(
        "core.runtime.port_utils.pids_listening_on_port",
        lambda port: [9999] if port == 8000 else [],
    )

    def fake_terminate(pid: int, *, grace: float = 10.0) -> None:
        killed.append(pid)

    monkeypatch.setattr("core.runtime.port_utils.terminate_process", fake_terminate)
    result = kill_listeners_on_ports([8000])
    assert result == [9999]
    assert killed == [9999]


def test_extract_listen_ports_from_log_nextjs_local_line() -> None:
    log = (
        "▲ Next.js 13.5.6\n"
        "- Local:        http://localhost:3001\n"
        "- ready started server on 0.0.0.0:3001\n"
    )
    assert extract_listen_ports_from_log(log) == [3001]


def test_extract_listen_ports_ignores_client_api_urls() -> None:
    """Worker logs that *call* an API must not claim the API listen port."""
    log = (
        "2026-07-17 09:02:06 [INFO] User watcher started. "
        "Interval: 300s, API: http://localhost:8000/users\n"
        "2026-07-17 09:02:07 [INFO] Baseline saved: 0 users\n"
    )
    assert extract_listen_ports_from_log(log) == []


def test_extract_listen_ports_uvicorn_bind_line() -> None:
    log = "INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)\n"
    assert extract_listen_ports_from_log(log) == [8000]


def test_find_busy_ports_detects_occupied_port() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    try:
        with patch("core.runtime.port_utils.is_port_available", return_value=False):
            assert find_busy_ports(f"uvicorn --port {port}") == [port]
    finally:
        sock.close()