"""Tests for per-profile env, gateway state, and workspace jail."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from cli.core import ProfileConfig, ProfileManager, init_profile, resolve_profile_storage_paths
from core.env_loader import bootstrap_profile_env, profile_env_path
from core.tools.execution_context import (
    reset_workspace_scope,
    workspace_scope,
)
from core.workspace import WorkspaceJailError, resolve_tool_path


@pytest.fixture
def helix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HELIX_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_profile_env_overrides_global(helix_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HELIX_TEST_VAR", raising=False)
    (helix_home / ".env").write_text("HELIX_TEST_VAR=global\n", encoding="utf-8")

    manager = ProfileManager()
    manager.create_profile("work")
    (profile_env_path("work")).write_text("HELIX_TEST_VAR=profile\n", encoding="utf-8")

    bootstrap_profile_env("work", force=True)
    assert os.environ.get("HELIX_TEST_VAR") == "profile"


def test_profile_env_seeded_on_create(helix_home: Path) -> None:
    manager = ProfileManager()
    manager.create_profile("alice")
    path = profile_env_path("alice")
    assert path.is_file()


def test_per_profile_gateway_state(helix_home: Path) -> None:
    from cli.services import gateway_state as gs

    a = gs.new_state(pid=100, host="127.0.0.1", port=8001, profile="a", reload=False)
    b = gs.new_state(pid=200, host="127.0.0.1", port=8002, profile="b", reload=False)
    gs.save_state(a)
    gs.save_state(b)

    loaded_a = gs.load_state("a")
    loaded_b = gs.load_state("b")
    assert loaded_a is not None and loaded_a.pid == 100
    assert loaded_b is not None and loaded_b.pid == 200
    assert gs.state_path("a") != gs.state_path("b")


def test_workspace_jail_blocks_escape(tmp_path: Path) -> None:
    jail_root = tmp_path / "sandbox"
    jail_root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    tokens = workspace_scope(workspace_root=str(jail_root), workspace_jail_enabled=True)
    try:
        inside = jail_root / "ok.txt"
        inside.write_text("ok", encoding="utf-8")
        assert resolve_tool_path(str(inside)).read_text(encoding="utf-8") == "ok"
        with pytest.raises(WorkspaceJailError):
            resolve_tool_path(str(outside))
    finally:
        reset_workspace_scope(tokens)


def test_workspace_jail_disabled_allows_anywhere(tmp_path: Path) -> None:
    target = tmp_path / "anywhere.txt"
    target.write_text("x", encoding="utf-8")
    tokens = workspace_scope(workspace_root=str(tmp_path / "jail"), workspace_jail_enabled=False)
    try:
        assert resolve_tool_path(str(target)) == target.resolve()
    finally:
        reset_workspace_scope(tokens)


def test_profile_config_workspace_fields(helix_home: Path) -> None:
    manager = ProfileManager()
    cfg = ProfileConfig(
        profile_name="jailed",
        workspace_jail_enabled=True,
        workspace_root="/tmp/data-agent",
    )
    cfg = resolve_profile_storage_paths("jailed", cfg, profile_dir=manager.get_profile_dir("jailed"))
    assert cfg.workspace_jail_enabled is True
    assert cfg.workspace_root.endswith("data-agent")


def test_init_profile_loads_profile_env(helix_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HELIX_TEST_PROFILE_ONLY", raising=False)
    manager = ProfileManager()
    manager.create_profile("gw")
    profile_env_path("gw").write_text("HELIX_TEST_PROFILE_ONLY=from_profile\n", encoding="utf-8")

    init_profile("gw", prompt_key=False)
    assert os.environ.get("HELIX_TEST_PROFILE_ONLY") == "from_profile"