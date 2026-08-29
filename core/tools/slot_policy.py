"""Per-slot tool allowlists and plan-mode schema filters."""

from __future__ import annotations

from typing import Any

# Tools not listed here are unrestricted (existing Holix tools).
SLOT_RESTRICTED: dict[str, frozenset[str]] = {
    "apply_patch": frozenset({"main", "coder"}),
    "job_monitor": frozenset({"main", "coder"}),
    "notebook_edit": frozenset({"main", "coder"}),
    "subagent_control": frozenset({"main", "supervisor"}),
    "plan_mode": frozenset({"main", "supervisor"}),
}

# Read-only set while plan_mode is on (canonical names).
PLAN_MODE_ALLOWED: frozenset[str] = frozenset(
    {
        "read_file",
        "grep",
        "glob",
        "list_directory",
        "web_search",
        "web_fetch",
        "fetch_url",
        "session_search",
        "search_sessions",
        "read_session",
        "tool_search",
        "ask_user",
        "lsp",
        "plan_mode",
        "todo_write",
        "skill_view",
    }
)

PLAN_MODE_BLOCKED: frozenset[str] = frozenset(
    {
        "write_file",
        "patch_file",
        "apply_patch",
        "delete_file",
        "notebook_edit",
        "run_terminal_command",
        "terminal",
        "delegate_to_subagent",
        "start_background_process",
        "stop_background_process",
        "restart_background_process",
        "execute_python",
        "code_executor",
        "run_code",
        "sdd_write_artifact",
        "sdd_update_spec",
        "sdd_apply",
        "sdd_dispatch",
    }
)


def normalize_slot(slot: str | None) -> str:
    key = str(slot or "main").strip().lower() or "main"
    if key in {"supervisor", "main"}:
        return key
    if key.startswith("coder"):
        return "coder"
    return key


def tool_allowed_for_slot(name: str, slot: str | None) -> bool:
    key = str(name or "").strip()
    if not key:
        return False
    allowed = SLOT_RESTRICTED.get(key)
    if allowed is None:
        return True
    return normalize_slot(slot) in allowed


def filter_schemas_for_slot(
    schemas: list[dict[str, Any]], slot: str | None
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for schema in schemas:
        fn = schema.get("function") if isinstance(schema, dict) else None
        name = str((fn or {}).get("name") or "") if isinstance(fn, dict) else ""
        if tool_allowed_for_slot(name, slot):
            out.append(schema)
    return out


def is_plan_mode_blocked(name: str) -> bool:
    key = str(name or "").strip()
    if key in PLAN_MODE_BLOCKED:
        return True
    if key in PLAN_MODE_ALLOWED:
        return False
    # Unknown writes stay blocked; unknown reads (MCP, skills) stay allowed.
    return False


def filter_schemas_for_plan_mode(schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for schema in schemas:
        fn = schema.get("function") if isinstance(schema, dict) else None
        name = str((fn or {}).get("name") or "") if isinstance(fn, dict) else ""
        if name in PLAN_MODE_ALLOWED:
            out.append(schema)
    return out
