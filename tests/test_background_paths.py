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