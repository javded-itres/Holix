"""Tool schema registration must not send duplicate function names to the LLM."""

from __future__ import annotations

from collections import Counter

from core.tools.aliases import get_registered_tool, infer_alias_action, resolve_tool_name
from core.tools.registry import ToolRegistry


def test_get_schemas_has_no_duplicate_function_names() -> None:
    registry = ToolRegistry(profile_name="default")
    registry.register_all()
    names = [s["function"]["name"] for s in registry.get_schemas()]
    dupes = {k: v for k, v in Counter(names).items() if v > 1}
    assert dupes == {}
    assert "start_background_process" in registry.tools
    assert "check_background_process" in registry.tools
    assert "start_background_process" not in names
    assert "grep" in names
    assert "glob" in names
    assert "delete_file" in names
    assert "skill_view" in names
    assert "skill_manage" in names
    assert "todo_write" in names
    assert "apply_patch" in names
    assert "ask_user" in names
    assert "tool_search" in names
    assert "plan_mode" in names
    assert "lsp" in names
    assert "job_monitor" not in names
    assert "session_search" not in names
    assert "notebook_edit" not in names
    assert "subagent_control" not in names
    assert "job_monitor" in registry.tools
    assert "session_search" in registry.tools


def test_run_project_alias_resolves() -> None:
    registry = ToolRegistry(profile_name="default")
    registry.register_all()
    assert resolve_tool_name("run_project") == "start_background_process"
    assert "start_background_process" in registry.tools


def test_execute_terminal_command_alias_resolves() -> None:
    registry = ToolRegistry(profile_name="default")
    registry.register_all()
    assert resolve_tool_name("execute_terminal_command") == "run_terminal_command"
    assert resolve_tool_name("list_dir") == "list_directory"
    assert "execute_terminal_command" in registry.tools
    assert registry.tools["execute_terminal_command"] is registry.tools["run_terminal_command"]


def test_cross_agent_tool_name_aliases() -> None:
    registry = ToolRegistry(profile_name="default")
    registry.register_all()
    expected = {
        "Bash": "run_terminal_command",
        "execute_terminal_command": "run_terminal_command",
        "execute_command": "run_terminal_command",
        "run_terminal_cmd": "run_terminal_command",
        "execute_bash": "run_terminal_command",
        "Read": "read_file",
        "Write": "write_file",
        "write_to_file": "write_file",
        "LS": "list_directory",
        "list_dir": "list_directory",
        "list_files": "list_directory",
        "Grep": "grep",
        "search_files": "grep",
        "Glob": "glob",
        "find_files": "glob",
        "remove_file": "delete_file",
        "WebFetch": "fetch_url",
        "WebSearch": "web_search",
        "run_project": "start_background_process",
        "list_processes": "list_background_processes",
        "Task": "delegate_to_subagent",
        "Agent": "delegate_to_subagent",
        "TodoWrite": "todo_write",
        "ApplyPatch": "apply_patch",
        "AskUserQuestion": "ask_user",
        "EnterPlanMode": "plan_mode",
        "ToolSearch": "tool_search",
        "Monitor": "job_monitor",
        "NotebookEdit": "notebook_edit",
        "SessionSearch": "session_search",
    }
    for foreign, canonical in expected.items():
        assert resolve_tool_name(foreign) == canonical, foreign
        tool = registry.tools.get(canonical)
        if tool is None:
            continue  # registered later on the live agent (sub-agents, …)
        assert get_registered_tool(registry, foreign) is tool, foreign


def test_registered_name_wins_over_alias() -> None:
    """MCP/extension tools keep their own name if it collides with an alias."""

    class _Stub:
        name = "search"

    registry = ToolRegistry(profile_name="default")
    registry.tools["search"] = _Stub()
    assert resolve_tool_name("search", registry.tools) == "search"
    assert resolve_tool_name("search") == "web_search"


def test_multi_action_alias_infers_action() -> None:
    assert resolve_tool_name("Edit") == "patch_file"
    assert resolve_tool_name("ApplyPatch") == "apply_patch"
    assert resolve_tool_name("EnterPlanMode") == "plan_mode"
    assert infer_alias_action("EnterPlanMode", "plan_mode", {})["action"] == "enter"
    assert infer_alias_action("ExitPlanMode", "plan_mode", {})["action"] == "exit"
    assert infer_alias_action("TaskOutput", "job_monitor", {})["action"] == "tail"
    assert infer_alias_action("TaskStop", "job_monitor", {})["action"] == "kill"
    assert infer_alias_action("SendMessage", "subagent_control", {})["action"] == "send"
