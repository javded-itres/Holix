"""Workspace filesystem store for OpenSpec-style SDD layout."""

from __future__ import annotations

import json
import re
import shutil
from datetime import date
from pathlib import Path

from core.sdd.apply_mode import apply_mode_prompt_text, load_apply_mode, save_apply_mode
from core.sdd.merge import merge_delta_into_main
from core.sdd.models import ChangeStatus
from core.sdd.paths import (
    SPEC_FILENAME,
    archive_root,
    change_dir,
    changes_root,
    config_path,
    domain_spec_path,
    openspec_root,
    specs_root,
    validate_change_id,
    validate_domain,
)
from core.sdd.tasks import (
    assignees_summary,
    parse_tasks_markdown,
    set_task_assignee,
    set_task_done,
)

_DEFAULT_CONFIG = """\
schema: holix-spec
context: |
  Holix Spec-Driven Development workspace.
rules:
  proposal: |
    Keep under 500 words; cover Why / What / Impact.
  specs: |
    Scenario-first requirements; no implementation detail.
  tasks: |
    Small checkboxes; group by phase;
    every task MUST have assignee: main | <subagent-type>;
    prefer subagents for independent workstreams.
apply:
  ask_execution_mode: true
  default_mode: ask
"""

_EXAMPLE_SPEC = """\
# Example Domain

### Requirement: System has a documented source of truth
The project SHALL keep durable requirements under `openspec/specs/`.

#### Scenario: New feature work
- **GIVEN** a non-trivial feature request
- **WHEN** work begins
- **THEN** a change proposal is created before implementation
"""

_PROPOSAL_STUB = """\
# Proposal: {change_id}

## Why

<!-- Why this change is needed -->

## What Changes

<!-- User-visible and technical changes -->

## Impact

<!-- Risks, migrations, systems touched -->
"""

_DESIGN_STUB = """\
# Design: {change_id}

## Approach

<!-- High-level design -->

## Task → assignee

| Task | Assignee | Why |
|------|----------|-----|
| | main / <subagent> | |
"""

_TASKS_STUB = """\
# Tasks: {change_id}

## 1. Implementation

- [ ] 1.1 First concrete step
  - **assignee:** `main`
  - **reason:** shared / coordination

- [ ] 1.2 Next step (set assignee to a subagent type for parallel work)
  - **assignee:** `main`
  - **reason:** default to main; change for multi-agent apply
"""

_DELTA_STUB = """\
# Delta: {domain}

## ADDED Requirements

### Requirement: {change_id} capability
The system SHALL …

#### Scenario: Happy path
- **GIVEN** …
- **WHEN** …
- **THEN** …
"""

_REQ_COUNT_RE = re.compile(r"^###\s+Requirement:", re.IGNORECASE | re.MULTILINE)


class SpecStore:
    """Read/write SDD artifacts under ``<project_root>/openspec/``.

    ``workspace`` is the project root (folder that owns ``openspec/``).
    When the Holix workspace contains multiple projects, each has its own
    SpecStore pointing at a different project root.
    """

    def __init__(self, workspace: Path | str):
        self.workspace = Path(workspace).expanduser().resolve()

    @property
    def root(self) -> Path:
        return openspec_root(self.workspace)

    @property
    def project_root(self) -> Path:
        return self.workspace

    def is_initialized(self) -> bool:
        return self.root.is_dir() and config_path(self.workspace).is_file()

    def init(self, *, example_domain: str = "example", force: bool = False) -> dict:
        if self.is_initialized() and not force:
            return {
                "ok": True,
                "already_initialized": True,
                "path": str(self.root),
            }
        self.root.mkdir(parents=True, exist_ok=True)
        specs_root(self.workspace).mkdir(parents=True, exist_ok=True)
        changes_root(self.workspace).mkdir(parents=True, exist_ok=True)
        archive_root(self.workspace).mkdir(parents=True, exist_ok=True)
        cfg = config_path(self.workspace)
        if not cfg.is_file() or force:
            cfg.write_text(_DEFAULT_CONFIG, encoding="utf-8")
        domain = validate_domain(example_domain)
        spec_p = domain_spec_path(self.workspace, domain)
        if not spec_p.is_file() or force:
            spec_p.parent.mkdir(parents=True, exist_ok=True)
            spec_p.write_text(_EXAMPLE_SPEC, encoding="utf-8")
        return {
            "ok": True,
            "already_initialized": False,
            "path": str(self.root),
            "example_domain": domain,
        }

    def list_specs(self) -> list[dict]:
        root = specs_root(self.workspace)
        if not root.is_dir():
            return []
        out: list[dict] = []
        for d in sorted(root.iterdir()):
            if not d.is_dir():
                continue
            spec = d / SPEC_FILENAME
            if not spec.is_file():
                continue
            text = spec.read_text(encoding="utf-8")
            out.append(
                {
                    "domain": d.name,
                    "path": str(spec.relative_to(self.workspace)),
                    "requirements": len(_REQ_COUNT_RE.findall(text)),
                    "chars": len(text),
                }
            )
        return out

    def read_spec(self, domain: str) -> str:
        domain = validate_domain(domain)
        path = domain_spec_path(self.workspace, domain)
        if not path.is_file():
            raise FileNotFoundError(f"spec not found for domain {domain!r}")
        return path.read_text(encoding="utf-8")

    def list_changes(self, *, include_archive: bool = False) -> list[dict]:
        root = changes_root(self.workspace)
        if not root.is_dir():
            return []
        active: list[dict] = []
        for d in sorted(root.iterdir()):
            if not d.is_dir() or d.name == "archive":
                continue
            st = self.change_status(d.name)
            active.append(
                {
                    "change_id": st.change_id,
                    "path": st.path,
                    "apply_ready": st.apply_ready,
                    "tasks_done": st.tasks_done,
                    "tasks_total": st.tasks_total,
                    "apply_mode": st.apply_mode,
                    "archived": False,
                }
            )
        if not include_archive:
            return active
        arch = archive_root(self.workspace)
        archived: list[dict] = []
        if arch.is_dir():
            for d in sorted(arch.iterdir()):
                if d.is_dir():
                    archived.append(
                        {
                            "change_id": d.name,
                            "path": str(d.relative_to(self.workspace)),
                            "archived": True,
                        }
                    )
        return active + archived

    def create_change(
        self,
        change_id: str,
        *,
        domain: str = "example",
        request: str = "",
        understanding_gate_enabled: bool = False,
        understanding_threshold: int = 80,
    ) -> dict:
        if not self.is_initialized():
            raise RuntimeError("SDD not initialized — call sdd_init first")
        cid = validate_change_id(change_id)
        domain = validate_domain(domain)
        dest = change_dir(self.workspace, cid)
        if dest.exists():
            raise FileExistsError(f"change already exists: {cid}")
        dest.mkdir(parents=True)
        req = (request or "").strip()
        if req:
            (dest / "request.md").write_text(
                f"# Request: {cid}\n\n{req}\n",
                encoding="utf-8",
            )
            proposal = (
                f"# Proposal: {cid}\n\n"
                f"## Why\n\n{req[:800]}\n\n"
                "## What Changes\n\n<!-- fill after understanding confirmed -->\n\n"
                "## Impact\n\n<!-- risks, migrations -->\n"
            )
            (dest / "proposal.md").write_text(proposal, encoding="utf-8")
        else:
            (dest / "proposal.md").write_text(
                _PROPOSAL_STUB.format(change_id=cid), encoding="utf-8"
            )
        (dest / "design.md").write_text(
            _DESIGN_STUB.format(change_id=cid), encoding="utf-8"
        )
        (dest / "tasks.md").write_text(
            _TASKS_STUB.format(change_id=cid), encoding="utf-8"
        )
        delta_dir = dest / "specs" / domain
        delta_dir.mkdir(parents=True)
        (delta_dir / SPEC_FILENAME).write_text(
            _DELTA_STUB.format(domain=domain, change_id=cid), encoding="utf-8"
        )
        from core.sdd.understanding import init_understanding

        understanding = init_understanding(
            self.workspace,
            cid,
            enabled=bool(understanding_gate_enabled),
            threshold=int(understanding_threshold),
            request=req,
        )
        artifacts = ["proposal.md", "design.md", "tasks.md", f"specs/{domain}/spec.md"]
        if req:
            artifacts.insert(0, "request.md")
        return {
            "ok": True,
            "change_id": cid,
            "path": str(dest.relative_to(self.workspace)),
            "artifacts": artifacts,
            "understanding": understanding.to_dict(),
            "next": (
                "Run understanding clarification (sdd_update_understanding) until "
                f"score ≥ {understanding.threshold}%, then sdd_confirm_understanding, "
                "then fill proposal/specs/tasks."
                if understanding.enabled and understanding.status == "clarifying"
                else "Fill proposal/specs/tasks (with assignees), then apply mode."
            ),
        }

    def change_status(self, change_id: str) -> ChangeStatus:
        cid = validate_change_id(change_id)
        cdir = change_dir(self.workspace, cid)
        if not cdir.is_dir():
            raise FileNotFoundError(f"change not found: {cid}")
        rel = str(cdir.relative_to(self.workspace))
        tasks: list = []
        tasks_path = cdir / "tasks.md"
        if tasks_path.is_file():
            tasks = parse_tasks_markdown(tasks_path.read_text(encoding="utf-8"))
        mode = load_apply_mode(self.workspace, cid)
        tasks_ok = self._tasks_ready_for_apply(tasks, apply_mode=mode)
        artifacts = {
            "proposal": (cdir / "proposal.md").is_file()
            and self._artifact_filled(cdir / "proposal.md"),
            "design": (cdir / "design.md").is_file(),
            "tasks": tasks_path.is_file() and tasks_ok,
            "specs": any(
                p.is_file()
                for p in (cdir / "specs").rglob(SPEC_FILENAME)
            )
            if (cdir / "specs").is_dir()
            else False,
        }
        missing: list[str] = []
        if not artifacts["proposal"]:
            missing.append("proposal (fill Why/What/Impact)")
        if not artifacts["specs"]:
            missing.append("delta specs")
        if not artifacts["tasks"]:
            missing.append(self._tasks_missing_reason(tasks, apply_mode=mode))
        apply_ready = (
            artifacts["proposal"]
            and artifacts["specs"]
            and artifacts["tasks"]
            and len(tasks) > 0
        )
        return ChangeStatus(
            change_id=cid,
            path=rel,
            artifacts=artifacts,
            tasks_total=len(tasks),
            tasks_done=sum(1 for t in tasks if t.done),
            assignees=assignees_summary(tasks),
            apply_mode=mode,
            apply_ready=apply_ready,
            missing=missing,
        )

    def write_artifact(
        self,
        change_id: str,
        artifact: str,
        content: str,
        *,
        domain: str | None = None,
    ) -> dict:
        cid = validate_change_id(change_id)
        cdir = change_dir(self.workspace, cid)
        if not cdir.is_dir():
            raise FileNotFoundError(f"change not found: {cid}")
        art = artifact.strip().lower()
        if art in ("proposal", "proposal.md"):
            path = cdir / "proposal.md"
        elif art in ("design", "design.md"):
            path = cdir / "design.md"
        elif art in ("tasks", "tasks.md"):
            path = cdir / "tasks.md"
        elif art in ("specs", "spec", "delta", "spec.md"):
            dom = validate_domain(domain or "example")
            path = cdir / "specs" / dom / SPEC_FILENAME
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            raise ValueError(
                f"unknown artifact {artifact!r}; use proposal|design|tasks|specs"
            )
        path.write_text(content, encoding="utf-8")
        return {
            "ok": True,
            "path": str(path.relative_to(self.workspace)),
            "chars": len(content),
        }

    def check_task(
        self,
        change_id: str,
        *,
        task_id: str | None = None,
        index: int | None = None,
        done: bool = True,
    ) -> dict:
        cid = validate_change_id(change_id)
        path = change_dir(self.workspace, cid) / "tasks.md"
        if not path.is_file():
            raise FileNotFoundError("tasks.md not found")
        text = path.read_text(encoding="utf-8")
        updated = set_task_done(text, task_id=task_id, index=index, done=done)
        path.write_text(updated, encoding="utf-8")
        tasks = parse_tasks_markdown(updated)
        return {
            "ok": True,
            "tasks_done": sum(1 for t in tasks if t.done),
            "tasks_total": len(tasks),
        }

    def set_task_assignee(
        self,
        change_id: str,
        assignee: str,
        *,
        task_id: str | None = None,
        index: int | None = None,
        reason: str | None = None,
    ) -> dict:
        cid = validate_change_id(change_id)
        path = change_dir(self.workspace, cid) / "tasks.md"
        if not path.is_file():
            raise FileNotFoundError("tasks.md not found")
        text = path.read_text(encoding="utf-8")
        updated = set_task_assignee(
            text, assignee=assignee, task_id=task_id, index=index, reason=reason
        )
        path.write_text(updated, encoding="utf-8")
        return {"ok": True, "assignee": assignee}

    def assign_unassigned_tasks(
        self,
        change_id: str,
        assignee: str = "main",
        *,
        all_tasks: bool = False,
    ) -> dict:
        """Set assignee on unassigned tasks (or every task if all_tasks)."""
        cid = validate_change_id(change_id)
        path = change_dir(self.workspace, cid) / "tasks.md"
        if not path.is_file():
            raise FileNotFoundError("tasks.md not found")
        who = (assignee or "main").strip() or "main"
        text = path.read_text(encoding="utf-8")
        tasks = parse_tasks_markdown(text)
        updated_ids: list[str] = []
        for t in tasks:
            a = (t.assignee or "unassigned").strip().lower()
            if all_tasks or not a or a == "unassigned":
                text = set_task_assignee(text, assignee=who, task_id=t.id)
                updated_ids.append(t.id)
        path.write_text(text, encoding="utf-8")
        return {
            "ok": True,
            "assignee": who,
            "updated": updated_ids,
            "count": len(updated_ids),
        }

    def list_tasks(self, change_id: str) -> list[dict]:
        cid = validate_change_id(change_id)
        path = change_dir(self.workspace, cid) / "tasks.md"
        if not path.is_file():
            return []
        from core.sdd.dispatch import load_task_jobs

        jobs = load_task_jobs(self, cid)
        out: list[dict] = []
        for t in parse_tasks_markdown(path.read_text(encoding="utf-8")):
            out.append(
                {
                    "id": t.id,
                    "text": t.text,
                    "done": t.done,
                    "assignee": t.assignee,
                    "reason": t.reason,
                    "job_id": jobs.get(t.id),
                }
            )
        return out

    def set_apply_mode(self, change_id: str, mode: str) -> dict:
        cid = validate_change_id(change_id)
        if not change_dir(self.workspace, cid).is_dir():
            raise FileNotFoundError(f"change not found: {cid}")
        saved = save_apply_mode(self.workspace, cid, mode)
        return {"ok": True, "change_id": cid, "apply_mode": saved}

    def request_apply_mode(self, change_id: str) -> dict:
        st = self.change_status(change_id)
        if st.apply_mode:
            return {
                "ok": True,
                "already_set": True,
                "apply_mode": st.apply_mode,
                "message": f"Apply mode already set to {st.apply_mode!r}.",
            }
        prompt = apply_mode_prompt_text(st.change_id, assignees=st.assignees)
        return {
            "ok": True,
            "already_set": False,
            "apply_ready": st.apply_ready,
            "missing": st.missing,
            "prompt": prompt,
            "message": (
                "STOP: do not start coding until the user chooses self | subagents | hybrid "
                "and you call sdd_set_apply_mode."
            ),
        }

    def begin_apply(self, change_id: str) -> dict:
        """Validate apply-ready + mode; return dispatch plan (no coding)."""
        st = self.change_status(change_id)
        if not st.apply_ready:
            missing = st.missing or []
            detail = f" ({'; '.join(missing)})" if missing else ""
            return {
                "ok": False,
                "error": f"change is not apply-ready{detail}",
                "missing": missing,
                "status": st.to_dict(),
            }
        if not st.apply_mode:
            req = self.request_apply_mode(change_id)
            return {
                "ok": False,
                "error": "apply mode not set",
                "need_user_choice": True,
                "prompt": req.get("prompt"),
                "message": req.get("message"),
                "status": st.to_dict(),
            }
        path = change_dir(self.workspace, st.change_id) / "tasks.md"
        tasks = parse_tasks_markdown(path.read_text(encoding="utf-8"))
        mode = st.apply_mode
        plan: list[dict] = []
        for t in tasks:
            if t.done:
                continue
            if mode == "self":
                executor = "main"
            elif t.assignee in ("main", "unassigned", ""):
                executor = "main"
            else:
                executor = t.assignee
            plan.append(
                {
                    "id": t.id,
                    "text": t.text,
                    "assignee": t.assignee,
                    "executor": executor,
                }
            )
        return {
            "ok": True,
            "change_id": st.change_id,
            "apply_mode": mode,
            "plan": plan,
            "message": (
                f"Apply mode={mode}. Execute plan in order; mark tasks with sdd_check_task. "
                "For executor!=main use subagent tools when mode is subagents/hybrid."
            ),
        }

    def archive(self, change_id: str) -> dict:
        cid = validate_change_id(change_id)
        cdir = change_dir(self.workspace, cid)
        if not cdir.is_dir():
            raise FileNotFoundError(f"change not found: {cid}")
        merged: list[str] = []
        specs_delta = cdir / "specs"
        if specs_delta.is_dir():
            for delta_spec in sorted(specs_delta.rglob(SPEC_FILENAME)):
                domain = delta_spec.parent.name
                main_path = domain_spec_path(self.workspace, domain)
                delta_text = delta_spec.read_text(encoding="utf-8")
                if main_path.is_file():
                    main_text = main_path.read_text(encoding="utf-8")
                else:
                    main_path.parent.mkdir(parents=True, exist_ok=True)
                    main_text = f"# {domain}\n\n"
                new_main = merge_delta_into_main(main_text, delta_text)
                main_path.write_text(new_main, encoding="utf-8")
                merged.append(str(main_path.relative_to(self.workspace)))

        arch = archive_root(self.workspace)
        arch.mkdir(parents=True, exist_ok=True)
        stamp = date.today().isoformat()
        dest = arch / f"{stamp}-{cid}"
        if dest.exists():
            dest = arch / f"{stamp}-{cid}-{_unique_suffix()}"
        shutil.move(str(cdir), str(dest))
        return {
            "ok": True,
            "change_id": cid,
            "archived_to": str(dest.relative_to(self.workspace)),
            "merged_specs": merged,
        }

    def status_overview(self) -> dict:
        changes = self.list_changes() if self.is_initialized() else []
        # attach understanding snapshot for open changes
        from core.sdd.understanding import load_understanding

        enriched = []
        for ch in changes:
            item = dict(ch)
            und = load_understanding(self.workspace, ch["change_id"])
            if und is not None:
                item["understanding"] = {
                    "score": und.score,
                    "threshold": und.threshold,
                    "status": und.status,
                    "enabled": und.enabled,
                }
            enriched.append(item)
        return {
            "initialized": self.is_initialized(),
            "path": str(self.root.relative_to(self.workspace)) if self.root.exists() else None,
            "project_root": str(self.workspace),
            "specs": self.list_specs() if self.is_initialized() else [],
            "changes": enriched,
        }

    @staticmethod
    def _artifact_filled(path: Path) -> bool:
        text = path.read_text(encoding="utf-8")
        # strip comments and stubs
        cleaned = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
        cleaned = re.sub(r"^#.*$", "", cleaned, flags=re.MULTILINE)
        return len(cleaned.strip()) >= 40

    @staticmethod
    def _unassigned_task_ids(tasks: list) -> list[str]:
        out: list[str] = []
        for t in tasks:
            a = (getattr(t, "assignee", None) or "unassigned").strip().lower()
            if not a or a == "unassigned":
                out.append(getattr(t, "id", "?") or "?")
        return out

    @classmethod
    def _tasks_ready_for_apply(cls, tasks: list, *, apply_mode: str | None) -> bool:
        """Checklist present; strict assignees only for pure subagents mode.

        ``self`` / ``hybrid`` / unset: ``unassigned`` runs on main at dispatch.
        ``subagents`` requires every task to name ``main`` or a subagent type.
        """
        if not tasks:
            return False
        mode = (apply_mode or "self").strip().lower()
        if mode == "subagents":
            return not cls._unassigned_task_ids(tasks)
        return True

    @classmethod
    def _tasks_missing_reason(cls, tasks: list, *, apply_mode: str | None) -> str:
        if not tasks:
            return "tasks (at least one checklist item with - [ ] …)"
        unassigned = cls._unassigned_task_ids(tasks)
        mode = (apply_mode or "self").strip().lower()
        if unassigned and mode == "subagents":
            ids = ", ".join(unassigned)
            return (
                f"tasks with assignees (no unassigned) for mode=subagents: {ids} "
                f"(pick assignee per task, use «All → main», or switch mode to Self)"
            )
        return "tasks (at least one checklist item with - [ ] …)"


def _unique_suffix() -> str:
    import time

    return str(int(time.time()) % 10000)


def workspace_from_context() -> Path:
    """Resolve workspace root for tools."""
    from core.tools.execution_context import get_workspace_root

    raw = get_workspace_root()
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.cwd().resolve()


def result_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
