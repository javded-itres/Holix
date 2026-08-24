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
