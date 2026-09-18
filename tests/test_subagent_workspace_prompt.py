"""Sub-agents share the main agent working directory in prompts and tools."""

from __future__ import annotations

from pathlib import Path

from core.prompt_builder import (
    format_working_directory_block,
    resolve_agent_working_directory,
)
from core.subagents.base import SubAgentConfig
from core.subagents.prompt import build_subagent_system_prompt
from core.tools.aliases import get_registered_tool, resolve_tool_name
from core.tools.registry import ToolRegistry


def test_resolve_working_directory_prefers_jail_root(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    assert resolve_agent_working_directory(
        workspace_root=str(root),
        workspace_jail_enabled=True,
    ) == str(root.resolve())


def test_resolve_working_directory_uses_workspace_even_if_jail_off(
    tmp_path: Path,
) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    assert resolve_agent_working_directory(
        workspace_root=str(root),
        workspace_jail_enabled=False,
    ) == str(root.resolve())


def test_resolve_working_directory_uses_explicit_cwd(tmp_path: Path) -> None:
    cwd = tmp_path / "project"
    cwd.mkdir()
    assert resolve_agent_working_directory(
        workspace_root=str(tmp_path / "profile_ws"),
        workspace_jail_enabled=False,
        working_directory=str(cwd),
    ) == str(cwd.resolve())


def test_subagent_prompt_includes_sdd_worktree_pin(tmp_path: Path) -> None:
    from core.sdd.change_workspace import (
        bind_active_change,
        compose_active_change,
        reset_active_change_store,
    )

    reset_active_change_store()
    clone = tmp_path / "app"
    wt = clone / ".holix" / "worktrees" / "feat-1"
    wt.mkdir(parents=True)
    bind_active_change(
        "default",
        "studio_tab",
        compose_active_change(
            change_id="feat-1",
            worktree=str(wt),
            clone=str(clone),
        ),
    )
    cfg = SubAgentConfig(
        name="coder",
        system_prompt="You code.",
        parent_conversation_id="studio_tab",
        conversation_id="subagent:studio_tab:coder",
    )
    bind_active_change(
        "default",
        cfg.conversation_id,
        compose_active_change(
            change_id="feat-1",
            worktree=str(wt),
            clone=str(clone),
        ),
    )
    text = build_subagent_system_prompt(
        cfg,
        "Implement the task",
        profile_name="default",
        workspace_root=str(wt),
        workspace_jail_enabled=True,
    )
    assert "Active SDD change" in text
    assert "feat-1" in text
    assert str(wt.resolve()) in text or str(wt) in text
    reset_active_change_store()


def test_subagent_prompt_includes_shared_cwd(tmp_path: Path) -> None:
    project = tmp_path / "app"
    project.mkdir()
    cfg = SubAgentConfig(name="coder", system_prompt="You code.", tools=["read_file"])
    prompt = build_subagent_system_prompt(
        cfg,
        "Fix models",
        profile_name="default",
        workspace_root=str(tmp_path / "ws"),
        workspace_jail_enabled=False,
        working_directory=str(project),
    )
    assert "Working directory" in prompt
    assert str(project.resolve()) in prompt
    assert "same" in prompt.lower() or "shared" in prompt.lower()


def test_subagent_prompt_jail_mode_uses_workspace_root(tmp_path: Path) -> None:
    ws = tmp_path / "profile_workspace"
    ws.mkdir()
    cfg = SubAgentConfig(name="coder", system_prompt="You code.")
    prompt = build_subagent_system_prompt(
        cfg,
        "task",
        workspace_root=str(ws),
        workspace_jail_enabled=True,
        working_directory=str(tmp_path / "other"),
    )
    # explicit working_directory wins
    assert str((tmp_path / "other").resolve()) in prompt or str(ws.resolve()) in prompt


def test_subagent_prompt_uses_workspace_root_not_process_cwd(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    home.mkdir()
    ws.mkdir()
    (ws / ".holix").mkdir()
    (ws / ".holix" / "HOLIX.md").write_text("# Workspace handbook\n", encoding="utf-8")
    (home / ".holix").mkdir()
    (home / ".holix" / "HOLIX.md").write_text("# HOME handbook\n", encoding="utf-8")
    monkeypatch.chdir(home)
    cfg = SubAgentConfig(name="coder", system_prompt="You code.")
    prompt = build_subagent_system_prompt(
        cfg,
        "task",
        workspace_root=str(ws),
        workspace_jail_enabled=False,
    )
    assert "Workspace handbook" in prompt
    assert "HOME handbook" not in prompt
    assert str(ws.resolve()) in prompt


def test_format_working_directory_block_nonempty() -> None:
    block = format_working_directory_block(workspace_jail_enabled=False)
    assert "Working directory" in block
    assert "`" in block


def test_list_directory_and_subagent_tool_aliases_registered() -> None:
    registry = ToolRegistry()
    registry.register_all()
    assert "list_directory" in registry.tools
    assert resolve_tool_name("terminal") == "run_terminal_command"
    assert resolve_tool_name("code_executor") == "execute_python"
    assert get_registered_tool(registry, "terminal") is not None
    assert get_registered_tool(registry, "code_executor") is not None
    assert get_registered_tool(registry, "list_directory") is not None
