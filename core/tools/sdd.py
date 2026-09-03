"""Agent tools for Spec-Driven Development (OpenSpec-compatible)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from core.sdd.projects import discover_sdd_projects, resolve_project_root
from core.sdd.store import SpecStore, result_json, workspace_from_context
from core.tools.base import BaseTool

_PROJECT_PROP = {
    "type": "string",
    "description": (
        "Project folder relative to workspace root that owns openspec/ "
        "(empty or omit = workspace root). Use sdd_list_projects."
    ),
    "default": "",
}


def _store(project: str = "") -> SpecStore:
    return SpecStore(resolve_project_root(workspace_from_context(), project))


def _attach_change_worktree(
    store: SpecStore, change_id: str, *, project: str
) -> dict[str, str] | None:
    """Point *store* at a new git worktree when possible. Mutates store.workspace."""
    from core.runtime.git_worktree import (
        WorktreeUnavailable,
        clone_root,
        prepare_change_worktree,
        worktrees_enabled,
    )

    if not worktrees_enabled():
        return None
    start = store.workspace
    try:
        info = prepare_change_worktree(start, change_id)
    except WorktreeUnavailable:
        return None
    if info is None:
        return None
    rel = Path()
    main = clone_root(start) or info.clone
    try:
        rel = start.resolve().relative_to(main.resolve())
    except ValueError:
        rel = Path()
    store.workspace = (info.worktree / rel).resolve()
    src_os = start / "openspec"
    dst_os = store.workspace / "openspec"
    if src_os.is_dir() and not (dst_os / "config.yaml").is_file():
        shutil.copytree(src_os, dst_os, dirs_exist_ok=True)
    return {
        "worktree": str(info.worktree),
        "branch": info.branch,
        "clone": str(info.clone),
        "workspace_now": str(store.workspace),
        "project": project or "",
    }


def _err(exc: BaseException) -> str:
    return result_json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


class SddListProjectsTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "sdd_list_projects"
        self.description = (
            "List projects under the workspace that already have openspec/ "
            "(multi-project SDD). Use path as project= for other sdd_* tools."
        )
        self.risk_level = "no"
        self.parameters = {"type": "object", "properties": {}}

    async def execute(self, **_: Any) -> str:
        try:
            ws = workspace_from_context()
            return result_json(
                {"ok": True, "workspace": str(ws), "projects": discover_sdd_projects(ws)}
            )
        except Exception as exc:
            return _err(exc)


class SddInitTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "sdd_init"
        self.description = (
            "Initialize OpenSpec-style SDD layout for a project folder "
            "(openspec/config.yaml, specs/, changes/). "
            "Pass project= relative path (e.g. apps/api) or empty for workspace root."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROP,
                "example_domain": {
                    "type": "string",
                    "description": "First domain folder under specs/ (default: example)",
                    "default": "example",
                },
                "force": {
                    "type": "boolean",
                    "description": "Overwrite default config/example spec if present",
                    "default": False,
                },
            },
        }

    async def execute(
        self,
        project: str = "",
        example_domain: str = "example",
        force: bool = False,
        **_: Any,
    ) -> str:
        try:
            root = resolve_project_root(workspace_from_context(), project)
            root.mkdir(parents=True, exist_ok=True)
            result = SpecStore(root).init(example_domain=example_domain, force=bool(force))
            result["project"] = project or ""
            return result_json(result)
        except Exception as exc:
            return _err(exc)


class SddListSpecsTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "sdd_list_specs"
        self.description = "List main domain specs under openspec/specs/ (source of truth)."
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {"project": _PROJECT_PROP},
        }

    async def execute(self, project: str = "", **_: Any) -> str:
        try:
            return result_json(
                {
                    "ok": True,
                    "project": project or "",
                    "specs": _store(project).list_specs(),
                }
            )
        except Exception as exc:
            return _err(exc)


class SddReadSpecTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "sdd_read_spec"
        self.description = (
            "Read a main domain spec.md under openspec/specs/<domain>/ "
            "(source of truth, not a change). For a change's proposal / design / "
            "tasks / delta specs use sdd_read_artifact."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROP,
                "domain": {
                    "type": "string",
                    "description": "Domain folder name under openspec/specs/",
                },
            },
            "required": ["domain"],
        }

    async def execute(self, domain: str, project: str = "", **_: Any) -> str:
        try:
            return _store(project).read_spec(domain)
        except Exception as exc:
            return _err(exc)


class SddListChangesTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "sdd_list_changes"
        self.description = "List active (and optionally archived) SDD changes."
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROP,
                "include_archive": {
                    "type": "boolean",
                    "default": False,
                },
            },
        }

    async def execute(self, project: str = "", include_archive: bool = False, **_: Any) -> str:
        try:
            return result_json(
                {
                    "ok": True,
                    "project": project or "",
                    "changes": _store(project).list_changes(include_archive=bool(include_archive)),
                }
            )
        except Exception as exc:
            return _err(exc)


class SddCreateChangeTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "sdd_create_change"
        self.description = (
            "Scaffold a new change under openspec/changes/<id>/ with STUB proposal/"
            "delta specs/tasks only — this does NOT fill the real specification. "
            "In a Studio product project (.holix/project.json) the id is ALWAYS "
            "{task_prefix}-{n} (e.g. litellmkeybot-4). Free-form slugs like "
            "stars-key-for-non-members are rewritten. Prefer "
            "project_create_task_tool when that MCP tool is available. "
            "You MUST then call sdd_write_artifact for proposal, specs, and tasks. "
            "Main openspec/specs/<domain> updates only after sdd_archive. "
            "Pass request= user request text. If understanding gate is enabled: "
            "BEFORE asking the user any questions — (1) read main specs + archived "
            "changes (sdd_list_specs, sdd_read_spec, sdd_list_changes "
            "include_archive=true), (2) if project context is weak run /init-equivalent "
            "analysis and update HOLIX.md, (3) sdd_update_understanding with score/"
            "summary, (4) only then ask residual questions; when score ≥ threshold "
            "sdd_confirm_understanding before filling full proposal. "
            "Chat + all artifacts must use the user's Studio locale only (ru or en)."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROP,
                "change_id": {
                    "type": "string",
                    "description": (
                        "Change id. Studio product projects ignore free-form slugs "
                        "and allocate {task_prefix}-{n} (e.g. litellmkeybot-4). "
                        "Outside Studio a slug like oauth-login is kept."
                    ),
                },
                "domain": {
                    "type": "string",
                    "description": (
                        "Preferred main domain for the delta. If openspec/specs/ already "
                        "has domains, only an existing domain is used (match preferred, "
                        "else project-named domain, else first). If no domains exist, "
                        "delta domain = project folder name. Leave empty to auto-resolve."
                    ),
                    "default": "",
                },
                "request": {
                    "type": "string",
                    "description": "User request / feature description text",
                    "default": "",
                },
            },
            "required": ["change_id"],
        }

    async def execute(
        self,
        change_id: str,
        project: str = "",
        domain: str = "",
        request: str = "",
        **_: Any,
    ) -> str:
        try:
            from core.sdd.prefs import SddPrefsStore
            from core.tools.execution_context import (
                get_conversation_id,
                get_profile_name,
            )

            prefs = SddPrefsStore(get_profile_name()).get()
            store = _store(project)
            from core.sdd.product_change_id import (
                allocate_product_change_id,
                ensure_studio_board_task,
            )

            allocated = allocate_product_change_id(store.workspace, requested=change_id)
            if allocated:
                change_id = str(allocated["change_id"])
            worktree_note = _attach_change_worktree(store, change_id, project=project)
            result = store.create_change(
                change_id,
                domain=domain or "",
                request=request or "",
                understanding_gate_enabled=prefs.understanding_gate_enabled,
                understanding_threshold=prefs.understanding_threshold,
            )
            if worktree_note:
                result.update(worktree_note)
                bind_cid = get_conversation_id()
                bind_profile = get_profile_name()
                try:
                    from core.sdd.change_workspace import ActiveChange, bind_active_change

                    bind_active_change(
                        bind_profile,
                        bind_cid,
                        ActiveChange(
                            change_id=str(result.get("change_id") or change_id),
                            branch=str(worktree_note.get("branch") or ""),
                            worktree=str(worktree_note.get("worktree") or ""),
                            clone=str(worktree_note.get("clone") or ""),
                            project=project or "",
                        ),
                    )
                except Exception:
                    pass
            if allocated:
                result["change_id"] = str(result.get("change_id") or change_id)
                rewritten = allocated.get("rewritten_from")
                if rewritten:
                    result["rewritten_from"] = rewritten
                    result["note"] = (
                        f"Studio product project: allocated {result['change_id']} "
                        f"(ignored slug {rewritten!r}). Use this id for "
                        "sdd_write_artifact and analysis."
                    )
                wt_rel = ""
                if worktree_note:
                    try:
                        wt = Path(str(worktree_note.get("worktree") or "")).resolve()
                        root = Path(workspace_from_context()).resolve()
                        wt_rel = str(wt.relative_to(root))
                    except Exception:
                        wt_rel = str(worktree_note.get("worktree") or "")
                try:
                    board = ensure_studio_board_task(
                        meta_path=allocated["meta_path"],
                        data=allocated["data"],
                        change_id=str(result.get("change_id") or change_id),
                        title=(request or "").strip().split("\n", 1)[0],
                        request=request or "",
                        worktree_rel=wt_rel,
                    )
                    if board:
                        result["task_id"] = board.get("id")
                        result["board_task"] = {
                            "id": board.get("id"),
                            "change_id": board.get("change_id"),
                        }
                except Exception:
                    pass
            # When understanding gate is ON, leave clarifying/score=0 so the agent
            # runs Q&A (sdd_update_understanding). Do NOT auto-confirm to 100%.
            und = result.get("understanding") or {}
            if und.get("enabled") and und.get("status") == "clarifying":
                result["next"] = (
                    "Understanding gate active: research specs + HOLIX, then "
                    "sdd_update_understanding (honest score), ask residual questions "
                    "until score ≥ threshold, sdd_confirm_understanding, then "
                    "sdd_write_artifact. Do not invent score=100 to skip Q&A."
                )
            else:
                result["next"] = (
                    "Fill proposal/specs/tasks via sdd_write_artifact "
                    "(no change-root specs.md — use artifact=specs + domain)."
                )
            result["project"] = project or ""
            result["filled"] = False
            if worktree_note:
                result["warning"] = (
                    "Scaffold only in the git worktree for this change. "
                    "File tools and the terminal now use workspace_now. "
                    "Do not edit the main clone. Stubs until sdd_write_artifact. "
                    "Main domain specs appear only after sdd_archive."
                )
            else:
                result["warning"] = (
                    "Scaffold only: proposal/specs/tasks are stubs until sdd_write_artifact. "
                    "Do not tell the user the specification is complete. "
                    "Paths: openspec/changes/<id>/{proposal,design,tasks}.md and "
                    "specs/<domain>/spec.md — there is NO specs.md at change root. "
                    "Main domain specs (openspec/specs/) appear only after sdd_archive."
                )
            return result_json(result)
        except Exception as exc:
            return _err(exc)


class SddStatusTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "sdd_status"
        self.description = (
            "SDD status for a project: overview, or one change "
            "(artifacts, tasks, apply_mode, understanding gate)."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROP,
                "change_id": {
                    "type": "string",
                    "description": "If set, status for this change only",
                },
            },
        }

    async def execute(self, project: str = "", change_id: str = "", **_: Any) -> str:
        try:
            store = _store(project)
            if change_id:
                from core.sdd.paths import change_dir
                from core.sdd.understanding import load_understanding

                status = store.change_status(change_id)
                data = {
                    "ok": True,
                    "project": project or "",
                    **status.to_dict(),
                }
                und = load_understanding(store.project_root, change_id)
                if und is not None:
                    data["understanding"] = und.to_dict()
                cdir = change_dir(store.workspace, change_id)
                rel = store.tool_relpath(cdir)
                delta_specs = (
                    sorted(store.tool_relpath(p) for p in (cdir / "specs").rglob("spec.md"))
                    if (cdir / "specs").is_dir()
                    else []
                )
                data["artifact_paths"] = {
                    "proposal": f"{rel}/proposal.md",
                    "design": f"{rel}/design.md",
                    "tasks": f"{rel}/tasks.md",
                    "specs": delta_specs,
                }
                data["path_note"] = (
                    "Paths are relative to the Holix workspace (include project/ "
                    "prefix when SDD lives in a subfolder). No specs.md at change "
                    "root — use sdd_write_artifact; delta specs under "
                    "specs/<domain>/spec.md. Prefer sdd_* tools over read_file."
                )
                return result_json(data)
            return result_json({"ok": True, "project": project or "", **store.status_overview()})
        except Exception as exc:
            return _err(exc)


class SddReadArtifactTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "sdd_read_artifact"
        self.description = (
            "Read a change artifact: proposal | design | tasks | specs. "
            "PREFERRED way to inspect a change — do NOT use read_file for "
            "openspec/changes/<id> files. Omit artifact to get all files "
            "(proposal.md, design.md, tasks.md, and delta specs/<domain>/spec.md). "
            "sdd_read_spec is only for main openspec/specs/, not change deltas."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROP,
                "change_id": {"type": "string"},
                "artifact": {
                    "type": "string",
                    "description": ("proposal | design | tasks | specs. Empty = all artifacts."),
                },
                "domain": {
                    "type": "string",
                    "description": "When artifact=specs, delta domain folder name",
                },
            },
            "required": ["change_id"],
        }

    async def execute(
        self,
        change_id: str,
        artifact: str = "",
        domain: str = "",
        project: str = "",
        **_: Any,
    ) -> str:
        try:
            return result_json(
                _store(project).read_artifact(
                    change_id,
                    artifact,
                    domain=domain or None,
                )
            )
        except Exception as exc:
            return _err(exc)


class SddUpdateSpecTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "sdd_update_spec"
        self.description = (
            "Incrementally update a change's delta spec: add, modify, or remove "
            "one requirement without rewriting the whole file. "
            "Use this when requirements change — the spec is patched "
            "(## ADDED / MODIFIED / REMOVED), not replaced. "
            "Main openspec/specs/<domain>/spec.md is updated later by sdd_archive; "
            "the tool returns main_preview. "
            "Pass op+title+body for one requirement, or content= markdown with "
            "## ADDED/MODIFIED/REMOVED Requirements sections to merge. "
            "Do NOT use write_file for specs."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROP,
                "change_id": {"type": "string"},
                "op": {
                    "type": "string",
                    "description": "add | modify | remove (or ADDED/MODIFIED/REMOVED)",
                },
                "title": {
                    "type": "string",
                    "description": "Requirement title (without the 'Requirement:' prefix)",
                },
                "body": {
                    "type": "string",
                    "description": (
                        "Requirement text: SHALL + scenarios. Heading is optional — "
                        "it is added from title when missing."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Optional full delta snippet to merge "
                        "(## ADDED/MODIFIED/REMOVED Requirements)."
                    ),
                },
                "domain": {
                    "type": "string",
                    "description": "Delta domain under the change (omit if only one)",
                },
            },
            "required": ["change_id"],
        }

    async def execute(
        self,
        change_id: str,
        op: str = "",
        title: str = "",
        body: str = "",
        content: str = "",
        domain: str = "",
        project: str = "",
        **_: Any,
    ) -> str:
        try:
            from core.sdd.understanding import gate_blocks_propose

            store = _store(project)
            block = gate_blocks_propose(store.project_root, change_id)
            if block:
                return result_json(
                    {
                        "ok": False,
                        "error": block,
                        "hint": (
                            "Research specs first, sdd_update_understanding until "
                            "score ≥ threshold, then sdd_confirm_understanding "
                            "before updating specs."
                        ),
                    }
                )
            return result_json(
                store.update_spec(
                    change_id,
                    op=op,
                    title=title,
                    body=body,
                    content=content,
                    domain=domain or None,
                )
            )
        except Exception as exc:
            return _err(exc)


class SddWriteArtifactTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "sdd_write_artifact"
        self.description = (
            "Write a change artifact: proposal | design | tasks | specs. "
            "PREFERRED way to fill a change — do NOT use write_file/read_file for "
            "openspec artifacts. Read them with sdd_read_artifact. "
            "To add/change/remove individual spec requirements without rewriting "
            "the whole delta, use sdd_update_spec. "
            "There is NO file openspec/changes/<id>/specs.md; "
            "artifact=specs writes openspec/changes/<id>/specs/<domain>/spec.md "
            "(pass domain= or omit to use the scaffolded domain). "
            "Other paths: proposal.md, design.md, tasks.md under the change folder. "
            "For tasks.md ONLY OpenSpec Holix checklist format is accepted:\n"
            "- [ ] 1.1 Title (one small deliverable)\n"
            "  - **assignee:** `coder`\n"
            "  - **size:** `s`   # xs|s|m required for subagents; l/xl rejected\n"
            "  - **reason:** …\n"
            "  - **depends_on:** `1.0`   # optional; empty or omit if no deps\n"
            "Estimate volume and DECOMPOSE large work: prefer 5–15 XS/S tasks over "
            "1–3 mega-tasks so each sub-agent uses fewer steps. "
            "One subagent task = one deliverable (one endpoint OR one screen OR one "
            "test file — not all). "
            "Build a task **graph**: use depends_on so subagents run in order "
            "(wave 1 = no deps / ready; later waves after prerequisites are done). "
            "Same-section order (1.1 before 1.2) is inferred when depends_on is empty. "
            "Parallel tasks: share the same depends_on (or none). "
            "Do NOT write free-form sections (## 1. … + **Описание**/**Исполнитель**). "
            "Invalid or oversized tasks.md is rejected (or auto-normalized when possible). "
            "Write content in the user's Studio UI language only (ru or en) — "
            "match locale from the user/Studio prompt; do not mix languages."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROP,
                "change_id": {"type": "string"},
                "artifact": {
                    "type": "string",
                    "description": "proposal | design | tasks | specs",
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Full markdown content in the user's Studio locale only "
                        "(ru or en — same language for the whole artifact). "
                        "For artifact=tasks: OpenSpec checklist only "
                        "(`- [ ] 1.1 …` + nested `**assignee:**`, `**size:**` "
                        "xs|s|m, and optional `**depends_on:**`). "
                        "Decompose large work — L/XL subagent tasks are rejected."
                    ),
                },
                "domain": {
                    "type": "string",
                    "description": "Required when artifact=specs (delta domain)",
                },
            },
            "required": ["change_id", "artifact", "content"],
        }

    async def execute(
        self,
        change_id: str,
        artifact: str,
        content: str,
        domain: str = "",
        project: str = "",
        **_: Any,
    ) -> str:
        try:
            from core.sdd.understanding import gate_blocks_propose

            store = _store(project)
            block = gate_blocks_propose(store.project_root, change_id)
            if block:
                return result_json(
                    {
                        "ok": False,
                        "error": block,
                        "hint": (
                            "Research main/archived specs and project context first, "
                            "sdd_update_understanding until score ≥ threshold, "
                            "then sdd_confirm_understanding before writing artifacts."
                        ),
                    }
                )
            return result_json(
                store.write_artifact(
                    change_id,
                    artifact,
                    content,
                    domain=domain or None,
                )
            )
        except Exception as exc:
            return _err(exc)


class SddSetTaskAssigneeTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "sdd_set_task_assignee"
        self.description = "Set assignee (main or subagent type/name) on a tasks.md item."
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROP,
                "change_id": {"type": "string"},
                "assignee": {
                    "type": "string",
                    "description": "main | <subagent-type> | <subagent-name>",
                },
                "task_id": {
                    "type": "string",
                    "description": "Task id prefix e.g. 1.1 (preferred)",
                },
                "index": {
                    "type": "integer",
                    "description": "1-based task index if task_id omitted",
                },
                "reason": {"type": "string"},
            },
            "required": ["change_id", "assignee"],
        }

    async def execute(
        self,
        change_id: str,
        assignee: str,
        task_id: str = "",
        index: int | None = None,
        reason: str = "",
        project: str = "",
        **_: Any,
    ) -> str:
        try:
            return result_json(
                _store(project).set_task_assignee(
                    change_id,
                    assignee,
                    task_id=task_id or None,
                    index=index,
                    reason=reason or None,
                )
            )
        except Exception as exc:
            return _err(exc)


class SddCheckTaskTool(BaseTool):
    def __init__(self, parent_agent: Any = None) -> None:
        super().__init__()
        self._parent = parent_agent
        self.name = "sdd_check_task"
        self.description = (
            "Mark a tasks.md checkbox done or not done. "
            "When done=true, cancels any still-running one-shot subagent bound "
            "to that task (and all SDD subagents for the change if every task "
            "is done). Studio process waiters (followed_process) are not cancelled "
            "— the parent still waits until the process run finishes."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROP,
                "change_id": {"type": "string"},
                "task_id": {"type": "string"},
                "index": {"type": "integer", "description": "1-based index"},
                "done": {"type": "boolean", "default": True},
            },
            "required": ["change_id"],
        }

    async def execute(
        self,
        change_id: str,
        task_id: str = "",
        index: int | None = None,
        done: bool = True,
        project: str = "",
        **_: Any,
    ) -> str:
        try:
            store = _store(project)
            result = store.check_task(
                change_id,
                task_id=task_id or None,
                index=index,
                done=bool(done),
            )
            if bool(done) and self._parent is not None:
                from core.sdd.task_completion import cancel_sdd_subagents_after_check

                cancel = await cancel_sdd_subagents_after_check(
                    self._parent,
                    project_root=store.workspace,
                    change_id=change_id,
                    task_id=task_id or None,
                    done=True,
                    tasks_done=result.get("tasks_done"),
                    tasks_total=result.get("tasks_total"),
                )
                result = {**result, **cancel}
            return result_json(result)
        except Exception as exc:
            return _err(exc)


class SddRequestApplyModeTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "sdd_request_apply_mode"
        self.description = (
            "Before implementation: get the mandatory pre-apply question "
            "(self | subagents | hybrid). Present it to the user; do not code yet."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROP,
                "change_id": {"type": "string"},
            },
            "required": ["change_id"],
        }

    async def execute(self, change_id: str, project: str = "", **_: Any) -> str:
        try:
            return result_json(_store(project).request_apply_mode(change_id))
        except Exception as exc:
            return _err(exc)


class SddSetApplyModeTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "sdd_set_apply_mode"
        self.description = (
            "Record user's apply execution mode: self | subagents | hybrid. "
            "Required before sdd_apply / coding."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROP,
                "change_id": {"type": "string"},
                "mode": {
                    "type": "string",
                    "enum": ["self", "subagents", "hybrid"],
                },
            },
            "required": ["change_id", "mode"],
        }

    async def execute(self, change_id: str, mode: str, project: str = "", **_: Any) -> str:
        try:
            return result_json(_store(project).set_apply_mode(change_id, mode))
        except Exception as exc:
            return _err(exc)


class SddApplyTool(BaseTool):
    def __init__(self, parent_agent: Any | None = None) -> None:
        super().__init__()
        self._parent = parent_agent
        self.name = "sdd_apply"
        self.description = (
            "Start apply for a change only if apply-ready and apply mode is set. "
            "Returns execution plan with task graph (depends_on, waves, ready/blocked). "
            "For mode subagents/hybrid automatically runs sdd_dispatch for **ready** "
            "tasks only (deps satisfied); later waves spawn after prerequisites complete. "
            "Each task uses its **tasks.md assignee**. "
            "Do NOT call delegate_to_subagent(coder) for SDD work."
        )
        self.risk_level = "high"
        self.parameters = {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROP,
                "change_id": {"type": "string"},
                "auto_dispatch": {
                    "type": "boolean",
                    "description": (
                        "If true (default), spawn subagents for non-main assignees when "
                        "mode is subagents/hybrid. Set false to only get the plan."
                    ),
                    "default": True,
                },
            },
            "required": ["change_id"],
        }

    async def execute(
        self,
        change_id: str,
        project: str = "",
        auto_dispatch: bool = True,
        **_: Any,
    ) -> str:
        try:
            store = _store(project)
            plan = store.begin_apply(change_id)
            if not plan.get("ok"):
                return result_json(plan)
            mode = (plan.get("apply_mode") or "").strip().lower()
            if auto_dispatch and mode in ("subagents", "hybrid") and self._parent is not None:
                from core.sdd.dispatch import dispatch_change_tasks

                dispatch = await dispatch_change_tasks(
                    store,
                    change_id,
                    parent_agent=self._parent,
                )
                plan = {**plan, "dispatch": dispatch, "auto_dispatched": True}
                if dispatch.get("ok"):
                    spawned = list(dispatch.get("spawned") or [])
                    proc_n = sum(
                        1 for j in spawned if isinstance(j, dict) and j.get("followed_process")
                    )
                    extra = (
                        " Auto-dispatched subagents by tasks.md assignee "
                        "(use wait_subagent_result on job_id; do not re-spawn with coder)."
                    )
                    if proc_n:
                        extra += (
                            f" {proc_n} job(s) follow a Studio process — "
                            "wait_subagent_result blocks until that process run ends; "
                            "do not mark the SDD task done on the first child step."
                        )
                    plan["message"] = ((plan.get("message") or "") + extra).strip()
            return result_json(plan)
        except Exception as exc:
            return _err(exc)


class SddArchiveTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "sdd_archive"
        self.description = (
            "Merge change delta specs (ADDED/MODIFIED/REMOVED Requirements) into "
            "main openspec/specs/<domain>/spec.md, then move the change folder to "
            "changes/archive/YYYY-MM-DD-<id>/. Nested delta files under "
            "specs/<domain>/… still merge into that domain. Returns warnings if "
            "tasks are still open (merge still proceeds). If the change lives in a "
            "git worktree and the only uncommitted files are under openspec/, "
            "commits them and removes the worktree; extra dirty files keep the tree."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROP,
                "change_id": {"type": "string"},
                "force": {
                    "type": "boolean",
                    "description": "Reserved for stricter gates; archive currently always merges when change exists.",
                    "default": False,
                },
            },
            "required": ["change_id"],
        }

    async def execute(
        self, change_id: str, project: str = "", force: bool = False, **_: Any
    ) -> str:
        try:
            store = _store(project)
            payload = store.archive(change_id, force=bool(force))
            if payload.get("ok"):
                from core.runtime.git_worktree import release_change_worktree
                from core.tools.execution_context import get_profile_name

                payload["worktree"] = release_change_worktree(
                    store.workspace,
                    change_id,
                    profile=get_profile_name() or "default",
                )
            return result_json(payload)
        except Exception as exc:
            return _err(exc)


class SddUpdateUnderstandingTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "sdd_update_understanding"
        self.description = (
            "Update understanding score (0–100) for a change. "
            "First call should follow reading main/archived specs and project context "
            "(/init or HOLIX.md if needed) — put that into summary; only put residual "
            "gaps in questions (do not quiz the user before that research). "
            "Write summary and questions in the user's Studio locale only (ru or en). "
            "After user answers, call again with user_answer and updated score. "
            "If score < threshold → keep open_questions. "
            "If score ≥ threshold → offer proceed or more questions. "
            "If further answers drop score below threshold → clarify again."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROP,
                "change_id": {"type": "string"},
                "score": {
                    "type": "integer",
                    "description": "Your honest understanding of the task 0–100",
                },
                "summary": {
                    "type": "string",
                    "description": "What you currently understand",
                },
                "questions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Open clarifying questions for the user",
                },
                "agent_note": {
                    "type": "string",
                    "description": "What you asked or assessed",
                },
                "user_answer": {
                    "type": "string",
                    "description": "Latest user answer text (if any)",
                },
            },
            "required": ["change_id", "score"],
        }

    async def execute(
        self,
        change_id: str,
        score: int,
        project: str = "",
        summary: str = "",
        questions: list[str] | None = None,
        agent_note: str = "",
        user_answer: str = "",
        **_: Any,
    ) -> str:
        try:
            from core.sdd.understanding import update_understanding

            store = _store(project)
            return result_json(
                update_understanding(
                    store.project_root,
                    change_id,
                    score=int(score),
                    summary=summary or "",
                    questions=questions,
                    agent_note=agent_note or "",
                    user_answer=user_answer or "",
                )
            )
        except Exception as exc:
            return _err(exc)


class SddConfirmUnderstandingTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "sdd_confirm_understanding"
        self.description = (
            "Record that the user confirmed to proceed with SDD propose after "
            "understanding ≥ threshold. Required before filling full artifacts "
            "when understanding gate is enabled."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROP,
                "change_id": {"type": "string"},
            },
            "required": ["change_id"],
        }

    async def execute(self, change_id: str, project: str = "", **_: Any) -> str:
        try:
            from core.sdd.understanding import confirm_understanding

            store = _store(project)
            return result_json(confirm_understanding(store.project_root, change_id))
        except Exception as exc:
            return _err(exc)


class SddDispatchTool(BaseTool):
    """Spawn subagents for apply plan (requires parent agent)."""

    def __init__(self, parent_agent: Any):
        super().__init__()
        self._parent = parent_agent
        self.name = "sdd_dispatch"
        self.description = (
            "Spawn subagents for **graph-ready** non-main tasks (depends_on satisfied; "
            "same-section order inferred). Uses **exact assignee** from tasks.md. "
            "Blocked tasks wait for the next wave after sdd_check_task / auto-complete. "
            "Prefer sdd_apply (auto-dispatches). "
            "Mode self returns main_tasks only. Then wait_subagent_result / sdd_check_task. "
            "If a spawned job has followed_process, wait until the Studio process finishes."
        )
        self.risk_level = "high"
        self.parameters = {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROP,
                "change_id": {"type": "string"},
            },
            "required": ["change_id"],
        }

    async def execute(self, change_id: str, project: str = "", **_: Any) -> str:
        try:
            from core.sdd.dispatch import dispatch_change_tasks

            return result_json(
                await dispatch_change_tasks(
                    _store(project),
                    change_id,
                    parent_agent=self._parent,
                )
            )
        except Exception as exc:
            return _err(exc)


def register_sdd_tools(registry: Any) -> None:
    registry.register(SddListProjectsTool())
    registry.register(SddInitTool())
    registry.register(SddListSpecsTool())
    registry.register(SddReadSpecTool())
    registry.register(SddListChangesTool())
    registry.register(SddCreateChangeTool())
    registry.register(SddStatusTool())
    registry.register(SddReadArtifactTool())
    registry.register(SddUpdateSpecTool())
    registry.register(SddWriteArtifactTool())
    registry.register(SddSetTaskAssigneeTool())
    registry.register(SddCheckTaskTool())
    registry.register(SddRequestApplyModeTool())
    registry.register(SddSetApplyModeTool())
    registry.register(SddApplyTool())  # without parent; upgraded when subagents register
    registry.register(SddArchiveTool())
    registry.register(SddUpdateUnderstandingTool())
    registry.register(SddConfirmUnderstandingTool())


def register_sdd_dispatch_tool(registry: Any, parent_agent: Any) -> None:
    """Register dispatch + apply/check tools bound to the live agent."""
    # Overwrite bare tools so subagents/hybrid auto-spawn and task checks cancel jobs
    registry.register(SddApplyTool(parent_agent))
    registry.register(SddDispatchTool(parent_agent))
    registry.register(SddCheckTaskTool(parent_agent))
