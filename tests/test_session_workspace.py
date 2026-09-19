"""New-session workspace pin (no inherited project)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from cli.shared.session_workspace import (
    list_workspace_picker_options,
    pin_conversation_to_workspace_root,
)
from core.sdd.change_workspace import (
    bind_active_project,
    overlay_workspace_root,
    reset_active_change_store,
)


def test_pin_new_session_drops_inherited_project(tmp_path: Path, monkeypatch) -> None:
    reset_active_change_store()
    ws = tmp_path / "workspace"
    project = ws / "projects" / "demo"
    project.mkdir(parents=True)
    ws.mkdir(exist_ok=True)
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path / "holix"))
    host = SimpleNamespace(
        profile="default",
        conversation_id="tg_new_1",
        agent=SimpleNamespace(config=SimpleNamespace(workspace_root=str(ws))),
        workspace_root=str(ws),
    )
    bind_active_project("default", "tg_new_1", project, project="projects/demo")
    assert overlay_workspace_root("default", "tg_new_1") == str(project.resolve())
    out = pin_conversation_to_workspace_root(host, "tg_new_1")
    assert out["ok"] is True
    assert out["kind"] == "workspace"
    assert overlay_workspace_root("default", "tg_new_1") == str(ws.resolve())


def test_picker_includes_workspace_root(tmp_path: Path) -> None:
    reset_active_change_store()
    ws = tmp_path / "ws"
    ws.mkdir()
    host = SimpleNamespace(
        profile="default",
        agent=SimpleNamespace(config=SimpleNamespace(workspace_root=str(ws))),
        workspace_root=str(ws),
    )
    opts = list_workspace_picker_options(host)
    assert opts
    assert opts[0]["kind"] == "workspace"
    assert opts[0]["id"] == ""
