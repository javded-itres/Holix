"""TUI session workspace follows the launch directory."""

from __future__ import annotations

import os
from pathlib import Path

from cli.tui.workspace import (
    ENV_LAUNCH_CWD,
    capture_tui_launch_cwd,
    tui_session_workspace_root,
)
from core.di.runtime_config import HolixRuntimeConfig


def test_capture_tui_launch_cwd_sets_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(ENV_LAUNCH_CWD, raising=False)
    root = capture_tui_launch_cwd()
    assert root == tmp_path.resolve()
    assert os.environ[ENV_LAUNCH_CWD] == str(tmp_path.resolve())


def test_tui_session_workspace_prefers_env_over_cwd(tmp_path: Path, monkeypatch) -> None:
    launch = tmp_path / "project"
    launch.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setenv(ENV_LAUNCH_CWD, str(launch))
    monkeypatch.chdir(other)
    assert tui_session_workspace_root() == launch.resolve()


def test_runtime_override_does_not_use_profile_workspace(tmp_path: Path) -> None:
    profile_ws = tmp_path / "profiles" / "default" / "workspace"
    profile_ws.mkdir(parents=True)
    launch = tmp_path / "repo"
    launch.mkdir()
    cfg = HolixRuntimeConfig.from_settings().with_overrides(workspace_root=str(profile_ws))
    session = cfg.with_overrides(workspace_root=str(launch.resolve()))
    assert session.workspace_root == str(launch.resolve())
    assert cfg.workspace_root == str(profile_ws)
