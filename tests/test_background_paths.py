"""Tests for background process cwd and log path resolution."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from core.platform_compat import IS_WINDOWS
from core.runtime.background_paths import (
    background_log_dir,
    build_background_spawn_env,
    command_needs_shell,
    resolve_argv_executable,
    resolve_background_process_root,
)


def test_resolve_background_process_root_prefers_working_directory(tmp_path) -> None:
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    with (
        patch("core.tools.execution_context.get_workspace_root", return_value="/other"),
        patch("core.workspace.get_effective_workspace_root", return_value=None),
    ):
        root = resolve_background_process_root(working_directory=str(explicit))
    assert root == explicit.resolve()


def test_resolve_background_process_root_uses_jail_root(tmp_path) -> None:
    jail = tmp_path / "jail"
    jail.mkdir()
    with (
        patch("core.workspace.get_effective_workspace_root", return_value=jail),
        patch("core.tools.execution_context.get_workspace_root", return_value="/ignored"),
    ):
        root = resolve_background_process_root()
    assert root == jail.resolve()


def test_resolve_background_process_root_uses_workspace_root(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with (
        patch("core.workspace.get_effective_workspace_root", return_value=None),
        patch(
            "core.tools.execution_context.get_workspace_root",
            return_value=str(workspace),
        ),
        patch("core.tools.execution_context.is_workspace_jail_enabled", return_value=False),
    ):
        root = resolve_background_process_root()
    assert root == workspace.resolve()


def test_resolve_background_process_root_raises_when_jail_enabled_without_root() -> None:
    with (
        patch("core.workspace.get_effective_workspace_root", return_value=None),
        patch("core.tools.execution_context.get_workspace_root", return_value=None),
        patch("core.tools.execution_context.is_workspace_jail_enabled", return_value=True),
    ):
        with pytest.raises(ValueError, match="Workspace jail is enabled"):
            resolve_background_process_root()


def test_background_log_dir(tmp_path) -> None:
    root = background_log_dir(tmp_path / "project")
    assert root == tmp_path / "project" / ".holix" / "process-logs"


def _project_venv_dir(project: Path) -> Path:
    rel = ".venv/Scripts" if IS_WINDOWS else ".venv/bin"
    return project / rel


def test_build_background_spawn_env_prefers_venv(tmp_path) -> None:
    project = tmp_path / "project"
    venv_bin = _project_venv_dir(project)
    venv_bin.mkdir(parents=True)
    (venv_bin / "uvicorn").write_text("", encoding="utf-8")

    env = build_background_spawn_env(project)
    assert env["PYTHONUNBUFFERED"] == "1"
    assert str(venv_bin) in env["PATH"].split(os.pathsep)
    assert str(project) in env["PYTHONPATH"].split(os.pathsep)


def test_resolve_argv_executable_uses_venv(tmp_path) -> None:
    project = tmp_path / "project"
    venv_bin = _project_venv_dir(project)
    venv_bin.mkdir(parents=True)
    tool = venv_bin / "uvicorn"
    tool.write_text("", encoding="utf-8")

    resolved = resolve_argv_executable(["uvicorn", "app.main:app"], project)
    assert resolved[0] == str(tool)


def test_command_needs_shell() -> None:
    assert command_needs_shell("source .venv/bin/activate && uvicorn app:app")
    assert command_needs_shell("export FOO=1 && npm run dev")
    assert not command_needs_shell("uvicorn app.main:app --port 8000")


def _change_worktree(tmp_path: Path) -> tuple[Path, Path, Path]:
    workspace = tmp_path / "workspace"
    clone = workspace / "projects" / "ai_bot_project"
    worktree = clone / ".holix" / "worktrees" / "aibotproject-8"
    (worktree / "backend").mkdir(parents=True)
    (worktree / "widget" / "src").mkdir(parents=True)
    (clone / ".git").mkdir(parents=True)
    return workspace, clone, worktree


def test_worktree_launch_rewrites_workspace_cd(tmp_path: Path) -> None:
    from core.runtime.background_paths import prepare_worktree_project_launch

    _workspace, clone, worktree = _change_worktree(tmp_path)
    command, wd = prepare_worktree_project_launch(
        "cd projects/ai_bot_project && uv run uvicorn app:app --port 9000",
        "",
        worktree,
    )
    assert command == "cd . && uv run uvicorn app:app --port 9000"
    assert wd == ""
    assert "projects/ai_bot_project" not in command

    nested, _wd = prepare_worktree_project_launch(
        "cd projects/ai_bot_project/backend && uv run uvicorn app:app",
        "",
        worktree,
    )
    assert nested == "cd backend && uv run uvicorn app:app"

    widget, _wd = prepare_worktree_project_launch(
        "cd projects/widget && npm run dev",
        "",
        worktree,
    )
    assert widget == "cd widget && npm run dev"

    nested_widget, _wd = prepare_worktree_project_launch(
        "cd projects/widget/src && npm run dev",
        "",
        worktree,
    )
    assert nested_widget == "cd widget/src && npm run dev"

    absolute, _wd = prepare_worktree_project_launch(
        f"cd {clone} && uv run uvicorn app:app",
        "",
        worktree,
    )
    assert absolute.startswith("cd . &&")
    assert str(clone) not in absolute


def test_worktree_launch_maps_working_directory(tmp_path: Path) -> None:
    from core.runtime.background_paths import prepare_worktree_project_launch

    _workspace, _clone, worktree = _change_worktree(tmp_path)
    command, wd = prepare_worktree_project_launch(
        "uv run uvicorn app:app --port 9000",
        "projects/ai_bot_project/backend",
        worktree,
    )
    assert command == "uv run uvicorn app:app --port 9000"
    assert Path(wd) == (worktree / "backend").resolve()


def test_worktree_launch_rejects_unknown_directory(tmp_path: Path) -> None:
    from core.runtime.background_paths import prepare_worktree_project_launch

    _workspace, _clone, worktree = _change_worktree(tmp_path)
    with pytest.raises(ValueError, match="backend") as exc:
        prepare_worktree_project_launch(
            "cd projects/missing && npm run dev",
            "",
            worktree,
        )
    assert "widget" in str(exc.value)
    assert "main clone" in str(exc.value)


def test_project_root_launch_uses_change_worktree(tmp_path: Path) -> None:
    from core.runtime.background_paths import prepare_worktree_project_launch

    product = tmp_path / "app"
    api = product / "api"
    worktree = api / ".holix" / "worktrees" / "chg-1"
    (worktree / "src").mkdir(parents=True)
    (api / "src").mkdir(parents=True)
    (product / "frontend" / ".holix" / "worktrees" / "chg-1").mkdir(parents=True)

    command, wd = prepare_worktree_project_launch(
        "cd api && npm run dev",
        "",
        product,
        change_id="chg-1",
    )
    assert "api/.holix/worktrees/chg-1" in command.replace("\\", "/")
    assert wd == ""

    nested, _wd = prepare_worktree_project_launch(
        "cd api/src && npm run dev",
        "",
        product,
        change_id="chg-1",
    )
    assert nested.replace("\\", "/").endswith("api/.holix/worktrees/chg-1/src && npm run dev")

    _same, pointed = prepare_worktree_project_launch(
        "npm run dev",
        "api",
        product,
        change_id="chg-1",
    )
    assert Path(pointed) == worktree.resolve()


def test_single_change_worktree_becomes_default_cwd(tmp_path: Path) -> None:
    from core.runtime.background_paths import prepare_worktree_project_launch

    product = tmp_path / "app"
    worktree = product / "api" / ".holix" / "worktrees" / "chg-1"
    worktree.mkdir(parents=True)
    command, wd = prepare_worktree_project_launch(
        "npm run dev",
        "",
        product,
        change_id="chg-1",
    )
    assert command == "npm run dev"
    assert Path(wd) == worktree.resolve()


def test_worktree_launch_skipped_when_disabled(tmp_path: Path, monkeypatch) -> None:
    from core.runtime.background_paths import prepare_worktree_project_launch

    _workspace, _clone, worktree = _change_worktree(tmp_path)
    monkeypatch.setattr(
        "core.runtime.git_worktree.worktrees_enabled",
        lambda profile=None: False,
    )
    command = "cd projects/ai_bot_project && uv run uvicorn app:app"
    rewritten, wd = prepare_worktree_project_launch(command, "backend", worktree)
    assert rewritten == command
    assert wd == "backend"


def test_launch_outside_a_worktree_is_unchanged(tmp_path: Path) -> None:
    from core.runtime.background_paths import prepare_worktree_project_launch

    workspace = tmp_path / "workspace"
    (workspace / "projects" / "app").mkdir(parents=True)
    command = "cd projects/app && npm run dev"
    rewritten, wd = prepare_worktree_project_launch(command, "projects/app", workspace)
    assert rewritten == command
    assert wd == "projects/app"
