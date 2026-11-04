"""Tools brought across from Kilo: snapshots, code search, goals, worktrees."""

from __future__ import annotations

import json
from typing import Any

from core.tools.base import BaseTool
from core.tools.execution_context import get_conversation_id, get_profile_name, get_workspace_root


def _workspace() -> str:
    return get_workspace_root() or ""


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


class WorkspaceSnapshotTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "workspace_snapshot"
        self.description = (
            "Shadow-git snapshots of the workspace, stored outside the project's "
            ".git. action=capture | list | revert | redo. revert restores the "
            "previous snapshot; redo walks forward again."
        )
        self.risk_level = "medium"
        self.parameters = {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["capture", "list", "revert", "redo"],
                },
                "label": {"type": "string"},
            },
            "required": ["action"],
        }

    async def execute(self, action: str, label: str = "") -> str:
        from core.runtime.file_snapshots import capture, list_snapshots, redo, revert

        workspace = _workspace()
        profile = get_profile_name()
        if not workspace:
            return _dump({"ok": False, "error": "no workspace"})
        act = (action or "").strip().lower()
        if act == "capture":
            return _dump(capture(workspace, profile=profile, label=label or "manual"))
        if act == "list":
            return _dump({"ok": True, "snapshots": list_snapshots(workspace, profile=profile)})
        if act == "revert":
            return _dump(revert(workspace, profile=profile))
        if act == "redo":
            return _dump(redo(workspace, profile=profile))
        return _dump({"ok": False, "error": f"unknown action: {action}"})


class SemanticSearchTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "semantic_search"
        self.description = (
            "Search the workspace by meaning across functions and classes. "
            "Opt-in: action=enable for this session, action=reindex to rebuild, "
            "or pass query to search. Disabled until enabled."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "action": {
                    "type": "string",
                    "enum": ["search", "enable", "reindex", "status"],
                },
                "limit": {"type": "integer"},
            },
        }

    async def execute(
        self,
        query: str = "",
        action: str = "search",
        limit: int = 8,
    ) -> str:
        from core.search.code_index import (
            build_index,
            code_index_enabled,
            search,
            set_session_enabled,
        )

        profile = get_profile_name()
        conversation = get_conversation_id()
        workspace = _workspace()
        act = (action or "search").strip().lower()
        if act == "enable":
            set_session_enabled(profile, conversation, True)
            return _dump({"ok": True, "enabled": True})
        if act == "status":
            return _dump(
                {
                    "ok": True,
                    "enabled": code_index_enabled(profile=profile, conversation_id=conversation),
                }
            )
        if not code_index_enabled(profile=profile, conversation_id=conversation):
            return _dump(
                {
                    "ok": False,
                    "error": "code index is off. Call semantic_search with action=enable "
                    "or set code_index_enabled / HOLIX_CODE_INDEX=1.",
                }
            )
        if not workspace:
            return _dump({"ok": False, "error": "no workspace"})
        if act == "reindex":
            return _dump(build_index(workspace, profile=profile))
        if not (query or "").strip():
            return _dump({"ok": False, "error": "query is required"})
        hits = search(workspace, query, profile=profile, limit=int(limit or 8))
        return _dump({"ok": True, "hits": hits})


class SessionGoalTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "session_goal"
        self.description = (
            "Keep one objective active across turns. action=start | status | pause | "
            "resume | clear | report. report uses status=complete or status=blocked. "
            "While the goal is active, ask_user is refused."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["start", "status", "pause", "resume", "clear", "report"],
                },
                "objective": {"type": "string"},
                "status": {"type": "string", "enum": ["complete", "blocked"]},
                "reason": {"type": "string"},
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        objective: str = "",
        status: str = "",
        reason: str = "",
    ) -> str:
        from core.runtime.session_goal import (
            clear_goal,
            get_goal,
            pause_goal,
            report_goal,
            resume_goal,
            start_goal,
        )

        profile = get_profile_name()
        conversation = get_conversation_id()
        act = (action or "").strip().lower()
        if act == "start":
            if not (objective or "").strip():
                return _dump({"ok": False, "error": "objective is required"})
            goal = start_goal(profile, conversation, objective)
            return _dump({"ok": True, **goal.as_dict()})
        if act == "status":
            goal = get_goal(profile, conversation)
            return _dump({"ok": True, "goal": None if goal is None else goal.as_dict()})
        if act == "pause":
            goal = pause_goal(profile, conversation, reason)
            return _dump({"ok": goal is not None, "goal": None if goal is None else goal.as_dict()})
        if act == "resume":
            goal = resume_goal(profile, conversation)
            return _dump({"ok": goal is not None, "goal": None if goal is None else goal.as_dict()})
        if act == "clear":
            clear_goal(profile, conversation)
            return _dump({"ok": True, "goal": None})
        if act == "report":
            goal = report_goal(profile, conversation, status or "complete", reason)
            return _dump({"ok": goal is not None, "goal": None if goal is None else goal.as_dict()})
        return _dump({"ok": False, "error": f"unknown action: {action}"})


class SessionWorktreeTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "session_worktree"
        self.description = (
            "Bind this session to a git worktree (branch session/<id>) so file "
            "tools run there. action=bind | status | diff | leave. bind copies "
            ".env and runs .holix/worktree-setup.sh when those exist. "
            "Independent of SDD changes."
        )
        self.risk_level = "medium"
        self.parameters = {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "status", "diff", "leave"],
                },
                "base": {
                    "type": "string",
                    "description": "Start point for a new branch (branch, tag, or SHA).",
                },
            },
            "required": ["action"],
        }

    async def execute(self, action: str, base: str = "") -> str:
        from core.runtime.session_worktree import (
            bind_session,
            diff_session,
            get_binding,
            leave_session,
        )

        profile = get_profile_name()
        conversation = get_conversation_id()
        act = (action or "").strip().lower()
        if act == "bind":
            return _dump(
                bind_session(
                    _workspace() or ".",
                    profile=profile,
                    conversation_id=conversation,
                    base=base,
                )
            )
        if act == "status":
            binding = get_binding(profile, conversation)
            return _dump({"ok": True, "binding": binding})
        if act == "diff":
            return _dump(diff_session(profile, conversation))
        if act == "leave":
            return _dump(leave_session(profile, conversation))
        return _dump({"ok": False, "error": f"unknown action: {action}"})


def register_kilo_parity_tools(registry: Any) -> None:
    registry.register(WorkspaceSnapshotTool())
    registry.register(SemanticSearchTool())
    registry.register(SessionGoalTool())
    registry.register(SessionWorktreeTool())
