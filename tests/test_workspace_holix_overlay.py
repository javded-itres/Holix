"""Workspace `.holix` adds and overrides profile skills and MCP."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from core.config_utils import load_local_overlay, merge_profile_with_local, project_holix_dir
from core.security.workspace_command_guard import (
    command_escapes_workspace,
    references_holix_profiles,
)
from core.tools.file_ops import _iter_workspace_files


def test_merge_adds_and_overrides_mcp_without_touching_model() -> None:
    merged = merge_profile_with_local(
        {
            "model": "profile-model",
            "mcp_servers": {"fs": {"command": "profile"}},
            "mcp_assignments": {"main": ["fs"]},
        },
        {
            "model": "local-model",
            "mcp_servers": {
                "fs": {"command": "workspace"},
                "context7": {"command": "npx"},
            },
        },
    )
    assert merged["model"] == "profile-model"
    assert merged["mcp_servers"]["fs"]["command"] == "workspace"
    assert merged["mcp_servers"]["context7"]["command"] == "npx"
    assert merged["mcp_assignments"]["main"] == ["fs", "context7"]


def test_local_assignment_replaces_slot() -> None:
    merged = merge_profile_with_local(
        {"mcp_assignments": {"main": ["fs"], "coder": ["fs"]}},
        {"mcp_servers": {"docs": {"command": "npx"}}, "mcp_assignments": {"main": ["docs"]}},
    )
    assert merged["mcp_assignments"]["main"] == ["docs"]
    assert merged["mcp_assignments"]["coder"] == ["fs"]


def test_overlay_reads_workspace_not_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    workspace = tmp_path / "ws"
    holix = workspace / ".holix"
    holix.mkdir(parents=True)
    (holix / "config.yaml").write_text(
        "mcp_servers:\n  docs:\n    command: npx\n", encoding="utf-8"
    )
    (cwd / ".holix").mkdir()
    (cwd / ".holix" / "config.yaml").write_text(
        "mcp_servers:\n  other:\n    command: cwd\n",
        encoding="utf-8",
    )
    loaded = load_local_overlay(workspace_root=workspace)
    assert "docs" in loaded["mcp_servers"]
    assert "other" not in loaded["mcp_servers"]
    assert project_holix_dir(workspace_root=workspace) == holix


def test_load_profile_uses_default_workspace_holix(tmp_path: Path) -> None:
    del tmp_path
    from core.profile import ProfileManager

    manager = ProfileManager()
    manager.create_profile("default")
    loaded = manager.load_profile("default")
    holix = Path(loaded.workspace_root) / ".holix"
    holix.mkdir(parents=True, exist_ok=True)
    (holix / "config.yaml").write_text(
        "mcp_servers:\n  docs:\n    command: npx\n",
        encoding="utf-8",
    )
    again = manager.load_profile("default")
    assert again.mcp_servers["docs"]["command"] == "npx"
    on_disk = yaml.safe_load(
        (manager.get_profile_dir("default") / "config.yaml").read_text(encoding="utf-8")
    )
    assert "docs" not in (on_disk.get("mcp_servers") or {})


def test_session_workspace_wins_over_profile_root(tmp_path: Path) -> None:
    from core.tools.execution_context import reset_workspace_scope, workspace_scope

    session = tmp_path / "session"
    profile = tmp_path / "profile"
    (session / ".holix").mkdir(parents=True)
    (profile / ".holix").mkdir(parents=True)
    (session / ".holix" / "config.yaml").write_text("mcp_enabled: true\n", encoding="utf-8")
    (profile / ".holix" / "config.yaml").write_text("mcp_enabled: false\n", encoding="utf-8")
    tokens = workspace_scope(workspace_root=str(session), workspace_jail_enabled=True)
    try:
        loaded = load_local_overlay(workspace_root=profile)
    finally:
        reset_workspace_scope(tokens)
    assert loaded["mcp_enabled"] is True


def test_workspace_skill_overrides_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    from core.di.runtime_config import HolixRuntimeConfig
    from core.skills.manager import SkillsManager

    profile_skills = tmp_path / "profile_skills"
    profile_skills.mkdir()
    (profile_skills / "demo.md").write_text(
        "---\nname: demo\ndescription: profile\n---\n\nprofile body\n",
        encoding="utf-8",
    )
    workspace = tmp_path / "ws"
    bundle = workspace / ".holix" / "skills" / "demo"
    bundle.mkdir(parents=True)
    (bundle / "SKILL.md").write_text(
        "---\nname: demo\ndescription: workspace\n---\n\nworkspace body\n",
        encoding="utf-8",
    )
    extra = workspace / ".holix" / "skills" / "only-here"
    extra.mkdir()
    (extra / "SKILL.md").write_text(
        "---\nname: only-here\ndescription: local only\n---\n\nlocal\n",
        encoding="utf-8",
    )
    cfg = HolixRuntimeConfig.from_settings().with_overrides(
        skills_dir=str(profile_skills),
        workspace_root=str(workspace),
    )
    manager = SkillsManager(cfg)
    manager.load_all_skills(defer_index=True)
    assert manager.all_skills["demo"]["description"] == "workspace"
    assert manager.all_skills["demo"]["_source"] == "local"
    assert "only-here" in manager.all_skills


def test_grep_sees_workspace_holix_skills_not_worktrees(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    skill = root / ".holix" / "skills" / "demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("workspace skill marker\n", encoding="utf-8")
    tree = root / ".holix" / "worktrees" / "change"
    tree.mkdir(parents=True)
    (tree / "secret.txt").write_text("worktree marker\n", encoding="utf-8")
    texts = [path.read_text(encoding="utf-8") for path in _iter_workspace_files(root)]
    assert any("workspace skill marker" in text for text in texts)
    assert all("worktree marker" not in text for text in texts)


def test_shell_allows_workspace_holix_and_blocks_profile(tmp_path: Path) -> None:
    workspace = tmp_path / "profiles" / "default" / "workspace"
    workspace.mkdir(parents=True)
    target = workspace / ".holix" / "config.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("mcp_servers: {}\n", encoding="utf-8")
    blocked, _reason = command_escapes_workspace(
        "cat .holix/config.yaml",
        workspace,
        jail_enabled=True,
    )
    assert not blocked
    blocked, _reason = command_escapes_workspace(
        f"cat {target}",
        workspace,
        jail_enabled=True,
    )
    assert not blocked
    profile_config = workspace.parent / "config.yaml"
    profile_config.write_text("model: hidden\n", encoding="utf-8")
    assert references_holix_profiles(f"cat {profile_config}", allow_under=workspace)


def test_tilde_holix_inside_workspace_is_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    workspace = home / ".holix" / "profiles" / "default" / "workspace"
    workspace.mkdir(parents=True)
    config = workspace / ".holix" / "config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("mcp_servers: {}\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    inside = "cat ~/.holix/profiles/default/workspace/.holix/config.yaml"
    assert not references_holix_profiles(inside, allow_under=workspace)
    outside = "cat ~/.holix/profiles/default/config.yaml"
    assert references_holix_profiles(outside, allow_under=workspace)
    assert references_holix_profiles(outside)


@pytest.mark.asyncio
async def test_tool_writes_skill_and_mcp_without_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    from core.tools.workspace_holix import WorkspaceHolixTool

    class Config:
        workspace_root = str(workspace)
        mcp_enabled = True
        mcp_servers: dict = {}
        mcp_assignments: dict = {"main": ["fs"]}

        def with_overrides(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)
            return self

    class Skills:
        loaded = 0

        def load_all_skills(self, *, defer_index: bool = False) -> None:
            del defer_index
            self.loaded += 1

    class Agent:
        def __init__(self) -> None:
            self.config = Config()
            self.skills = Skills()
            self.tools = self

        async def connect_workspace_mcp(self, name: str, data: dict) -> str:
            self.connected = (name, data)
            return "started"

    agent = Agent()
    tool = WorkspaceHolixTool()
    tool.bind_agent(agent)
    written = await tool.execute(
        action="write_skill",
        name="Deploy Notes",
        description="How to ship",
        content="When to Use\n\nProcedure\n",
    )
    assert "deploy-notes" in written
    skill = workspace / ".holix" / "skills" / "deploy-notes" / "SKILL.md"
    assert skill.is_file()
    assert "How to ship" in skill.read_text(encoding="utf-8")
    assert agent.skills.loaded == 1

    saved = await tool.execute(
        action="upsert_mcp",
        name="context7",
        command="npx",
        args=["-y", "@upstash/context7-mcp"],
        env={"CONTEXT7_API_KEY": "secret-value"},
    )
    assert "context7" in saved
    assert "secret-value" not in saved
    raw = yaml.safe_load((workspace / ".holix" / "config.yaml").read_text(encoding="utf-8"))
    assert raw["mcp_servers"]["context7"]["command"] == "npx"
    assert raw["mcp_servers"]["context7"]["env"]["CONTEXT7_API_KEY"] == "secret-value"
    assert agent.config.mcp_servers["context7"]["command"] == "npx"
    assert agent.config.mcp_assignments["main"] == ["fs", "context7"]
    assert agent.connected[0] == "context7"

    shown = await tool.execute(action="show")
    assert "deploy-notes" in shown
    assert "context7" in shown
    assert "secret-value" not in shown
