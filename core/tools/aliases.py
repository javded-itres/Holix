"""Canonical Holix tool names and aliases used by other agents / models.

Models are trained on Claude Code, Grok, Cline, Cursor, Codex, OpenHands,
Hermes/Qwen, etc. They often call ``Bash`` / ``execute_terminal_command``
instead of ``run_terminal_command``. Resolve those names here so the turn
does not die with ``Tool not found``.

Only names that can actually run against an existing Holix tool are mapped.
"""

from __future__ import annotations

import copy
import inspect
from collections.abc import Callable
from typing import Any

# ---------------------------------------------------------------------------
# Name aliases: foreign / invented name → Holix tool
# Keys are matched case-insensitively.
# ---------------------------------------------------------------------------

TOOL_ALIASES: dict[str, str] = {
    # Already registered historically
    "web_fetch": "fetch_url",
    "run_project": "start_background_process",
    "terminal": "run_terminal_command",
    "code_executor": "execute_python",
    "math_calculator": "calculate",
    # Claude Code / Anthropic
    "bash": "run_terminal_command",
    "shell": "run_terminal_command",
    "read": "read_file",
    "write": "write_file",
    "edit": "patch_file",
    "multiedit": "patch_file",
    "ls": "list_directory",
    "listdir": "list_directory",
    "webfetch": "fetch_url",
    "websearch": "web_search",
    "task": "delegate_to_subagent",
    "todowrite": "todo_write",
    "todo": "todo_write",
    # Grok / Cursor-adjacent
    "run_terminal_cmd": "run_terminal_command",
    "run_terminal": "run_terminal_command",
    "list_dir": "list_directory",
    "search_replace": "patch_file",
    "str_replace": "patch_file",
    "strreplace": "patch_file",
    "spawn_subagent": "delegate_to_subagent",
    # Cline / Roo / Continue
    "execute_command": "run_terminal_command",
    "execute_terminal_command": "run_terminal_command",
    "exec_terminal_command": "run_terminal_command",
    "run_command": "run_terminal_command",
    "run_shell": "run_terminal_command",
    "shell_command": "run_terminal_command",
    "write_to_file": "write_file",
    "create_file": "write_file",
    "replace_in_file": "patch_file",
    "apply_diff": "patch_file",
    "list_files": "list_directory",
    "list_folder": "list_directory",
    # Codex / OpenAI agents
    "apply_patch": "patch_file",
    # OpenHands / SWE-agent / Qwen-coder
    "execute_bash": "run_terminal_command",
    "run_bash": "run_terminal_command",
    "cmd_run": "run_terminal_command",
    "ipython": "execute_python",
    "run_python": "execute_python",
    "python": "execute_python",
    "execute_code": "execute_python",
    "browse": "fetch_url",
    "browser": "browser_open",
    "open_url": "fetch_url",
    "fetch": "fetch_url",
    "search": "web_search",
    "search_web": "web_search",
    "google": "web_search",
    # Background processes (models invent these after seeing Holix names)
    "list_processes": "list_background_processes",
    "list_background_process": "list_background_processes",
    "ps": "list_background_processes",
    "start_process": "start_background_process",
    "start_server": "start_background_process",
    "run_server": "start_background_process",
    "stop_process": "stop_background_process",
    "kill_process": "stop_background_process",
    "restart_process": "restart_background_process",
    "check_process": "check_background_process",
    # Files
    "cat": "read_file",
    "open_file": "read_file",
    "get_file": "read_file",
    "view_file": "read_file",
    "read_files": "read_file",
    "save_file": "write_file",
    "put_file": "write_file",
    "ls_dir": "list_directory",
    "dir": "list_directory",
    # Search / glob / delete (Claude Code, Cline, Grok)
    "search_files": "grep",
    "codebase_search": "grep",
    "rg": "grep",
    "find_files": "glob",
    "file_search": "glob",
    "remove_file": "delete_file",
    "rm_file": "delete_file",
    "unlink": "delete_file",
    "delete": "delete_file",
    # Sub-agents
    "delegate": "delegate_to_subagent",
    "spawn_agent": "delegate_to_subagent",
    "ask": "ask_user",
    "ask_human": "ask_user",
}

# Holix execute() parameter ← names models actually send
ARG_ALIASES: dict[str, tuple[str, ...]] = {
    "path": (
        "file_path",
        "filepath",
        "filename",
        "target_file",
        "target_directory",
        "dir_path",
        "directory",
        "dir",
        "cwd",
        "folder",
    ),
    "command": ("cmd", "shell_command", "bash", "script"),
    "content": ("contents", "text", "body", "file_text", "new_string"),
    "query": ("q", "search", "search_term", "question"),
    "url": ("uri", "link", "href"),
    "timeout": ("timeout_seconds", "timeout_s"),
    "max_results": ("num_results", "limit"),
    "task": ("prompt", "instruction", "goal"),
    "todos": ("items", "tasks"),
    "replacements": ("edits", "changes", "patches"),
    "old_string": ("old_str", "search", "find_text"),
    "new_string": ("new_str", "replace_text"),
    "agent_type": ("agent", "subagent", "persona", "type"),
    "label": ("process_name",),
    "process_id": ("processid",),
    "include_stopped": ("stopped", "history"),
    "pattern": ("regex", "regexp", "glob_pattern"),
    "glob": ("include", "file_pattern", "file_glob"),
}


def resolve_tool_name(name: str, tools: dict[str, Any] | None = None) -> str:
    """Map a model-invented tool name onto a Holix tool.

    If ``tools`` is given, an exact registered name wins over an alias so an
    MCP/extension tool named ``search`` is not stolen by ``web_search``.
    """
    key = (name or "").strip()
    if not key:
        return name
    folded = key.lower().replace("-", "_")
    if tools:
        if key in tools:
            return key
        if folded in tools:
            return folded
    return TOOL_ALIASES.get(key) or TOOL_ALIASES.get(folded) or folded


def _accepted_param_names(execute_fn: Callable[..., Any]) -> set[str] | None:
    try:
        signature = inspect.signature(execute_fn)
    except (TypeError, ValueError):
        return None
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
        return None
    return {
        name
        for name, param in signature.parameters.items()
        if name != "self"
        and param.kind
        in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
    }


def remap_tool_arguments(
    execute_fn: Callable[..., Any],
    arguments: dict[str, Any] | None,
) -> dict[str, Any]:
    """Copy well-known foreign argument names onto Holix parameters.

    Example: Claude ``Read(file_path=…)`` → Holix ``read_file(path=…)``.
    """
    args = dict(arguments or {})
    accepted = _accepted_param_names(execute_fn)
    if accepted is None:
        dests = set(ARG_ALIASES)
    else:
        dests = accepted
    for dest, sources in ARG_ALIASES.items():
        if dest not in dests or dest in args:
            continue
        for src in sources:
            if src in args:
                args[dest] = args[src]
                break
    return args


def get_registered_tool(registry: Any, name: str) -> Any | None:
    tools = getattr(registry, "tools", None)
    if not isinstance(tools, dict):
        return None
    return tools.get(resolve_tool_name(name, tools)) or tools.get(name)


def tool_schema_for_name(tool: Any, exposed_name: str) -> dict[str, Any]:
    """Return an OpenAI tool schema, optionally under an alias name."""
    schema = tool.to_openai_schema()
    canonical = getattr(tool, "name", exposed_name)
    if exposed_name != canonical:
        schema = copy.deepcopy(schema)
        schema["function"]["name"] = exposed_name
    return schema


def apply_aliases_to_registry(registry: Any) -> int:
    """Register every alias whose target tool is already present.

    Does not overwrite a different tool that already owns the alias name
    (MCP / extensions win).
    """
    tools = getattr(registry, "tools", None)
    if not isinstance(tools, dict):
        return 0
    # Short / generic names stay resolve-only so MCP can still own them.
    skip_register = frozenset(
        {
            "bash",
            "shell",
            "read",
            "write",
            "edit",
            "ls",
            "dir",
            "ps",
            "ask",
            "task",
            "search",
            "python",
            "fetch",
            "browse",
            "cat",
            "google",
            "browser",
            "delete",
        }
    )
    added = 0
    register_alias = getattr(registry, "register_alias", None)
    for alias, canonical in TOOL_ALIASES.items():
        if alias in skip_register:
            continue
        target = tools.get(canonical)
        if target is None:
            continue
        existing = tools.get(alias)
        if existing is not None and existing is not target:
            continue
        if register_alias is not None:
            register_alias(alias, target)
        else:
            tools[alias] = target
        added += 1
    return added
