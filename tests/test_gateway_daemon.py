"""Gateway daemon state and process helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from cli.services import gateway_state as gs


def test_gateway_state_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HELIX_HOME", str(tmp_path))
    profile = "default"

    state = gs.new_state(
        pid=4242,
        host="0.0.0.0",
        port=8000,
        profile=profile,
        reload=False,
    )
    gs.save_state(state)
    loaded = gs.load_state(profile)
    assert loaded is not None
    assert loaded.pid == 4242
    assert loaded.port == 8000


def test_is_process_alive_current_pid() -> None:
    assert gs.is_process_alive(os.getpid()) is True


def test_is_process_alive_dead_pid() -> None:
    assert gs.is_process_alive(999_999_999) is False


def test_running_state_clears_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HELIX_HOME", str(tmp_path))
    profile = "default"
    state_path = gs.state_path(profile)

    stale = gs.new_state(
        pid=999_999_999,
        host="127.0.0.1",
        port=8000,
        profile=profile,
        reload=False,
    )
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(stale.to_dict()), encoding="utf-8")

    from cli.services.gateway_daemon import _running_state

    assert _running_state(profile) is None
    assert not state_path.exists()


def test_gateway_state_docs_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HELIX_HOME", str(tmp_path))
    profile = "default"

    state = gs.new_state(
        pid=1,
        host="127.0.0.1",
        port=8000,
        profile=profile,
        reload=False,
        docs_pid=5555,
        docs_host="127.0.0.1",
        docs_port=8080,
    )
    gs.save_state(state)
    loaded = gs.load_state(profile)
    assert loaded is not None
    assert loaded.docs_pid == 5555
    assert gs.docs_url(loaded) == "http://127.0.0.1:8080/"


def test_load_state_prefers_alive_legacy_over_stale_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HELIX_HOME", str(tmp_path))
    profile = "default"

    stale = gs.new_state(
        pid=999_999_998,
        host="127.0.0.1",
        port=8000,
        profile=profile,
        reload=False,
    )
    gs.save_state(stale)

    legacy_dir = tmp_path / "gateway"
    legacy_dir.mkdir(parents=True)
    alive = gs.GatewayState(
        pid=os.getpid(),
        host="127.0.0.1",
        port=8000,
        profile=profile,
        reload=False,
        started_at="2026-06-09T00:00:00+00:00",
        log_file=str(legacy_dir / "gateway.log"),
    )
    (legacy_dir / "state.json").write_text(json.dumps(alive.to_dict()), encoding="utf-8")

    loaded = gs.load_state(profile)
    assert loaded is not None
    assert loaded.pid == os.getpid()
    assert gs.state_path(profile).is_file()
    assert not (legacy_dir / "state.json").exists()


def test_clear_state_removes_legacy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HELIX_HOME", str(tmp_path))
    profile = "default"

    state = gs.new_state(pid=42, host="127.0.0.1", port=8000, profile=profile, reload=False)
    (tmp_path / "gateway").mkdir(parents=True)
    (tmp_path / "gateway" / "state.json").write_text(json.dumps(state.to_dict()), encoding="utf-8")
    gs.save_state(state)

    gs.clear_state(profile)
    assert not gs.state_path(profile).exists()
    assert not (tmp_path / "gateway" / "state.json").exists()


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