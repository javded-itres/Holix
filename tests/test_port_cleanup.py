"""Tests for aggressive port cleanup on background process stop/start."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from core.runtime.background_process import BackgroundProcessRegistry
from core.runtime.port_utils import extract_listen_ports_from_log, force_free_ports


def test_extract_listen_ports_from_log() -> None:
    log = "VITE v5.0.0  ready in 120 ms\n  ➜  Local:   http://localhost:5173/"
    assert 5173 in extract_listen_ports_from_log(log)


@pytest.mark.asyncio
async def test_cleanup_before_start_leaves_other_sessions(tmp_path) -> None:
    """Different conversations without port overlap should keep both processes."""
    registry = BackgroundProcessRegistry()
    popen = MagicMock()
    popen.pid = 100

    with (
        patch("core.runtime.background_process.popen_background", return_value=popen),
        patch("core.runtime.background_process.terminate_process") as terminate,
        patch("core.runtime.background_process.is_process_alive", return_value=True),
        patch("core.runtime.port_utils.find_busy_ports", return_value=[]),
        patch("core.workspace.get_effective_workspace_root", return_value=tmp_path),
        patch("core.runtime.port_utils.force_free_ports", return_value=[]) as free_ports,
    ):
        await registry.start(
            command="uvicorn --port 8000",
            label="a",
            conversation_id="c1",
            profile="p1",
        )
        await registry.start(
            command="uvicorn --port 8001",
            label="b",
            conversation_id="c2",
            profile="p1",
        )
        stopped = await registry.cleanup_before_start(
            profile="p1",
            command="uvicorn --port 8002",
            conversation_id="c3",
        )

    assert stopped == []
    terminate.assert_not_called()
    assert free_ports.call_args_list[-1] == (([8002],),)


@pytest.mark.asyncio
async def test_cleanup_before_start_stops_same_session_only(tmp_path) -> None:
    registry = BackgroundProcessRegistry()
    first = MagicMock()
    first.pid = 100
    second = MagicMock()
    second.pid = 200

    with (
        patch(
            "core.runtime.background_process.popen_background",
            side_effect=[first, second],
        ),
        patch("core.runtime.background_process.terminate_process") as terminate,
        patch("core.runtime.background_process.is_process_alive", return_value=True),
        patch("core.runtime.port_utils.find_busy_ports", return_value=[]),
        patch("core.workspace.get_effective_workspace_root", return_value=tmp_path),
        patch("core.runtime.port_utils.force_free_ports", return_value=[]),
    ):
        rec1 = await registry.start(
            command="uvicorn --port 8000",
            label="a",
            conversation_id="c1",
            profile="p1",
        )
        await registry.start(
            command="uvicorn --port 8001",
            label="b",
            conversation_id="c2",
            profile="p1",
        )
        stopped = await registry.cleanup_before_start(
            profile="p1",
            command="sleep 60",
            conversation_id="c1",
        )

    assert len(stopped) == 1
    assert stopped[0].process_id == rec1.process_id
    terminate.assert_called_once_with(100, grace=2.0)


@pytest.mark.asyncio
async def test_cleanup_before_start_stops_port_conflicts(tmp_path) -> None:
    registry = BackgroundProcessRegistry()
    popen = MagicMock()
    popen.pid = 100

    with (
        patch("core.runtime.background_process.popen_background", return_value=popen),
        patch("core.runtime.background_process.terminate_process") as terminate,
        patch("core.runtime.background_process.is_process_alive", return_value=True),
        patch("core.runtime.port_utils.find_busy_ports", return_value=[]),
        patch("core.workspace.get_effective_workspace_root", return_value=tmp_path),
        patch("core.runtime.port_utils.force_free_ports", return_value=[]),
    ):
        rec = await registry.start(
            command="uvicorn --port 8000",
            label="api",
            conversation_id="c1",
            profile="p1",
        )
        stopped = await registry.cleanup_before_start(
            profile="p1",
            command="uvicorn --port 8000",
            conversation_id="c2",
        )

    assert len(stopped) == 1
    assert stopped[0].process_id == rec.process_id
    terminate.assert_called_once_with(100, grace=2.0)


def test_force_free_ports_retries(monkeypatch) -> None:
    calls: list[int] = []

    def fake_pids(port: int) -> list[int]:
        calls.append(port)
        return [5555] if len(calls) <= 2 else []

    monkeypatch.setattr("core.runtime.port_utils.pids_listening_on_port", fake_pids)
    monkeypatch.setattr("core.runtime.port_utils.terminate_process", lambda *a, **k: None)
    monkeypatch.setattr("core.runtime.port_utils.ports_in_use", lambda ports, **k: [] if len(calls) > 2 else ports)
    killed = force_free_ports([8000], wait_s=0)
    assert 5555 in killed