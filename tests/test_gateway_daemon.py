"""Gateway daemon state and process helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from cli.services import gateway_state as gs


def test_gateway_state_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gs, "GATEWAY_DIR", tmp_path)
    monkeypatch.setattr(gs, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(gs, "LOG_PATH", tmp_path / "gateway.log")

    state = gs.new_state(
        pid=4242,
        host="0.0.0.0",
        port=8000,
        profile="default",
        reload=False,
    )
    gs.save_state(state)
    loaded = gs.load_state()
    assert loaded is not None
    assert loaded.pid == 4242
    assert loaded.port == 8000


def test_is_process_alive_current_pid() -> None:
    assert gs.is_process_alive(os.getpid()) is True


def test_is_process_alive_dead_pid() -> None:
    assert gs.is_process_alive(999_999_999) is False


def test_running_state_clears_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gs, "GATEWAY_DIR", tmp_path)
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(gs, "STATE_PATH", state_path)

    stale = gs.new_state(
        pid=999_999_999,
        host="127.0.0.1",
        port=8000,
        profile="default",
        reload=False,
    )
    state_path.write_text(json.dumps(stale.to_dict()), encoding="utf-8")

    from cli.services.gateway_daemon import _running_state

    assert _running_state() is None
    assert not state_path.exists()


def test_gateway_state_docs_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gs, "GATEWAY_DIR", tmp_path)
    monkeypatch.setattr(gs, "STATE_PATH", tmp_path / "state.json")

    state = gs.new_state(
        pid=1,
        host="127.0.0.1",
        port=8000,
        profile="default",
        reload=False,
        docs_pid=5555,
        docs_host="127.0.0.1",
        docs_port=8080,
    )
    gs.save_state(state)
    loaded = gs.load_state()
    assert loaded is not None
    assert loaded.docs_pid == 5555
    assert gs.docs_url(loaded) == "http://127.0.0.1:8080/"


def test_health_url_normalizes_wildcard() -> None:
    state = gs.GatewayState(
        pid=1,
        host="0.0.0.0",
        port=8000,
        profile="default",
        reload=False,
        started_at="now",
        log_file="/tmp/log",
    )
    assert gs.health_url(state) == "http://127.0.0.1:8000/health"