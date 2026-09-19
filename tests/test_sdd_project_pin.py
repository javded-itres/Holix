"""Conversation workspace pin to the SDD project directory."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from core.sdd.change_workspace import (
    bind_active_change,
    bind_active_project,
    clear_active_change,
    drop_active_change,
    format_active_change_prompt_block,
    get_active_change,
    inherit_active_change,
    overlay_workspace_root,
    reset_active_change_store,
)
from core.sdd.projects import resolve_project_root
from core.tools.execution_context import (
    conversation_scope,
    get_workspace_root,
    profile_scope,
    reset_conversation_scope,
    reset_profile_scope,
    reset_workspace_scope,
    workspace_scope,
)


@pytest.fixture(autouse=True)
def _reset_pins() -> None:
    reset_active_change_store()
    yield
    reset_active_change_store()


def test_bind_active_project_overlays_workspace(tmp_path: Path) -> None:
    profile_ws = tmp_path / "workspace"
    project = profile_ws / "apps" / "api"
    project.mkdir(parents=True)
    (project / "openspec").mkdir()
    (project / "openspec" / "config.yaml").write_text("schema: holix-spec\n", encoding="utf-8")

    bind_active_project("default", "c1", project, project="apps/api")
    tokens = workspace_scope(workspace_root=str(profile_ws), workspace_jail_enabled=True)
    ptok = profile_scope("default")
    ctok = conversation_scope("c1")
    try:
        assert overlay_workspace_root("default", "c1") == str(project.resolve())
        assert get_workspace_root() == str(project.resolve())
        active = get_active_change("default", "c1")
        assert active is not None
        assert active.worktree == ""
        assert "SDD project" in format_active_change_prompt_block(active)
    finally:
        reset_conversation_scope(ctok)
        reset_profile_scope(ptok)
        reset_workspace_scope(tokens)


def test_locked_pin_not_stolen_by_sdd_bind(tmp_path: Path) -> None:
    project = tmp_path / "apps" / "api"
    project.mkdir(parents=True)
    bind_active_project(
        "default",
        "c-lock",
        project,
        project="apps/api",
        locked=True,
        replace_worktree=True,
        force=True,
    )
    other = tmp_path / "wt"
    other.mkdir()
    from core.sdd.change_workspace import ActiveChange, bind_active_change

    bind_active_change(
        "default",
        "c-lock",
        ActiveChange(
            change_id="stolen",
            branch="change/stolen",
            worktree=str(other),
            clone=str(project),
            project="apps/api",
            project_root=str(project),
        ),
    )
    kept = get_active_change("default", "c-lock")
    assert kept is not None
    assert kept.change_id != "stolen"
    assert kept.worktree == ""
    assert overlay_workspace_root("default", "c-lock") == str(project.resolve())


def test_drop_active_change_clears_project_pin(tmp_path: Path) -> None:
    project = tmp_path / "apps" / "api"
    project.mkdir(parents=True)
    bind_active_project("default", "c1", project, project="apps/api")
    assert overlay_workspace_root("default", "c1") == str(project.resolve())
    drop_active_change("default", "c1")
    assert overlay_workspace_root("default", "c1") is None
    assert get_active_change("default", "c1") is None


def test_worktree_overlay_wins_over_project_pin(tmp_path: Path) -> None:
    clone = tmp_path / "clone"
    wt = tmp_path / "worktree"
    clone.mkdir()
    wt.mkdir()
    from core.runtime.git_worktree import WorktreeInfo

    bind_active_change(
        "default",
        "c1",
        WorktreeInfo(
            change_id="feat-1",
            branch="change/feat-1",
            worktree=wt,
            clone=clone,
            git_common_dir=clone / ".git",
        ),
        project_root=str(clone),
    )
    tokens = workspace_scope(workspace_root=str(clone), workspace_jail_enabled=False)
    ptok = profile_scope("default")
    ctok = conversation_scope("c1")
    try:
        assert overlay_workspace_root("default", "c1") == str(wt.resolve())
        clear_active_change("default", "c1")
        leftover = get_active_change("default", "c1")
        assert leftover is not None
        assert leftover.worktree == ""
        assert leftover.project_root == str(clone.resolve())
        assert overlay_workspace_root("default", "c1") == str(clone.resolve())
    finally:
        reset_conversation_scope(ctok)
        reset_profile_scope(ptok)
        reset_workspace_scope(tokens)


def test_inherit_project_pin(tmp_path: Path) -> None:
    project = tmp_path / "app"
    project.mkdir()
    bind_active_project("default", "parent", project)
    child = inherit_active_change("default", "parent", "child")
    assert child is not None
    assert Path(child.project_root) == project.resolve()
    assert overlay_workspace_root("default", "child") == str(project.resolve())


def test_resolve_project_root_does_not_nest_when_already_pinned(tmp_path: Path) -> None:
    api = tmp_path / "apps" / "api"
    api.mkdir(parents=True)
    (api / "openspec").mkdir()
    (api / "openspec" / "config.yaml").write_text("schema: holix-spec\n", encoding="utf-8")
    assert resolve_project_root(api, "apps/api") == api.resolve()
    assert resolve_project_root(tmp_path, "apps/api") == api.resolve()


@pytest.mark.asyncio
async def test_sdd_init_pins_nested_project(tmp_path: Path) -> None:
    from core.tools.registry import ToolRegistry

    ws = tmp_path / "workspace"
    ws.mkdir()
    tokens = workspace_scope(workspace_root=str(ws), workspace_jail_enabled=True)
    ptok = profile_scope("default")
    ctok = conversation_scope("studio-1")
    try:
        reg = ToolRegistry(workspace_root=str(ws), profile_name="default")
        reg.register_all()
        raw = await reg.tools["sdd_init"].execute(project="apps/api")
        data = json.loads(raw)
        assert data.get("ok") is True
        pin = Path(data["workspace_pin"])
        assert pin == (ws / "apps" / "api").resolve()
        assert (pin / "openspec" / "config.yaml").is_file()
        assert get_workspace_root() == str(pin)
        sibling = ws / "other.txt"
        sibling.write_text("nope\n", encoding="utf-8")
        listed = await reg.tools["list_directory"].execute(path=".")
        assert "config.yaml" in listed or "openspec" in listed
        assert "other.txt" not in listed
    finally:
        reset_conversation_scope(ctok)
        reset_profile_scope(ptok)
        reset_workspace_scope(tokens)


@pytest.mark.asyncio
async def test_sdd_init_pins_when_worktrees_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOLIX_WORKTREE", "0")
    from core.tools.registry import ToolRegistry

    tokens = workspace_scope(workspace_root=str(tmp_path), workspace_jail_enabled=False)
    ptok = profile_scope("default")
    ctok = conversation_scope("c-off")
    try:
        reg = ToolRegistry(workspace_root=str(tmp_path), profile_name="default")
        reg.register_all()
        raw = await reg.tools["sdd_init"].execute()
        data = json.loads(raw)
        assert data.get("ok") is True
        assert get_workspace_root() == str(tmp_path.resolve())
        created = await reg.tools["sdd_create_change"].execute(change_id="no-wt", request="pin me")
        payload = json.loads(created)
        assert payload.get("ok") is True
        assert payload.get("worktree") in (None, "")
        active = get_active_change("default", "c-off")
        assert active is not None
        assert active.worktree == ""
        assert Path(active.project_root) == tmp_path.resolve()
    finally:
        reset_conversation_scope(ctok)
        reset_profile_scope(ptok)
        reset_workspace_scope(tokens)
