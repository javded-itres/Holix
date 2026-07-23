"""Single-gateway process guard."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture()
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "holix"
    home.mkdir()
    monkeypatch.setenv("HOLIX_HOME", str(home))
    return home


def test_assert_can_start_when_empty(holix_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from cli.services import gateway_singleton as gs

    monkeypatch.setattr(gs, "list_running_states", lambda: [])
    monkeypatch.setattr(gs, "find_all_gateway_worker_entries", lambda: [])
    gs.assert_can_start_gateway("default")


def test_assert_can_start_blocks_other(holix_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from cli.services import gateway_singleton as gs

    monkeypatch.setattr(
        gs,
        "list_running_states",
        lambda: [
            SimpleNamespace(
                profile="saas",
                pid=4242,
                host="127.0.0.1",
                port=8011,
            )
        ],
    )
    monkeypatch.setattr(gs, "is_process_alive", lambda pid: True)
    monkeypatch.setattr(gs, "find_all_gateway_worker_entries", lambda: [])

    with pytest.raises(RuntimeError, match="Only one Holix gateway"):
        gs.assert_can_start_gateway("default")


def test_assert_excludes_self_pid(holix_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from cli.services import gateway_singleton as gs

    monkeypatch.setattr(gs, "list_running_states", lambda: [])
    monkeypatch.setattr(gs, "find_all_gateway_worker_entries", lambda: [(99, "default")])
    monkeypatch.setattr(gs, "is_process_alive", lambda pid: True)
    gs.assert_can_start_gateway("default", exclude_pid=99)
