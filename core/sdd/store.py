"""Workspace filesystem store for OpenSpec-style SDD layout."""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import date
from pathlib import Path

from core.sdd.apply_mode import apply_mode_prompt_text, load_apply_mode, save_apply_mode
from core.sdd.merge import count_delta_requirements, merge_delta_into_main
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


def _openspec_target(workspace: Path, path: Path) -> str:
    """Real path under openspec/, or raise if it would escape."""
    root = os.path.realpath(str(openspec_root(workspace)))
    target = os.path.realpath(os.path.expanduser(str(path)))
    if target != root and not target.startswith(root + os.sep):
        raise ValueError(f"path escapes {root}: {path}")
    return target


def _write_openspec_file(workspace: Path, path: Path, text: str) -> None:
    target = _openspec_target(workspace, path)
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        fh.write(text)


def _read_openspec_file(workspace: Path, path: Path) -> str:
    target = _openspec_target(workspace, path)
    with open(target, encoding="utf-8") as fh:
        return fh.read()


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
    Small checkboxes only (XS/S preferred); group by phase;
    every task MUST have assignee: main | <subagent-type>;
    every task SHOULD have size: xs|s|m (l/xl forbidden for subagents — split first);
    one subagent task = one deliverable (one endpoint OR one screen OR one test file);
    prefer 5–15 small tasks over 1–3 large ones so jobs use fewer steps;
    wire depends_on for order; prefer subagents for independent workstreams.
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

- [ ] 1.1 First small concrete step (one deliverable)
  - **assignee:** `main`
  - **size:** `s`
  - **reason:** shared / coordination
  - **depends_on:**

- [ ] 1.2 Next small step (runs after 1.1; set assignee for parallel multi-agent apply)
  - **assignee:** `main`
  - **size:** `s`
  - **reason:** default to main; change for multi-agent apply
  - **depends_on:** `1.1`
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

    def tool_relpath(self, path: Path | str) -> str:
        """Path relative to Holix workspace for read_file / write_file.

        SpecStore paths are under the *project* root. Nested projects (e.g.
        ``user_catalog/openspec/...``) must be reported with the project
        prefix so file tools resolve them from the profile workspace root.
        """
        p = Path(path).expanduser().resolve()
        try:
            holix = workspace_from_context()
        except Exception:
            holix = None
        if holix is not None:
            try:
                holix = holix.resolve()
                if p.is_relative_to(holix) and self.workspace.is_relative_to(holix):
                    return p.relative_to(holix).as_posix()
            except (ValueError, OSError):
                pass
        try:
            return p.relative_to(self.workspace).as_posix()
        except ValueError:
            return str(p)

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
                    "path": self.tool_relpath(spec),
                    "requirements": len(_REQ_COUNT_RE.findall(text)),
                    "chars": len(text),
                }
            )
        return out

    def project_domain_slug(self) -> str:
        """Default domain name from the project folder (workspace root name)."""
        raw = (self.workspace.name or "project").strip()
        try:
            return validate_domain(raw)
        except ValueError:
            slug = re.sub(r"[^a-z0-9\-_]+", "-", raw.lower()).strip("-_")
            if not slug:
                slug = "project"
            try:
                return validate_domain(slug[:64])
            except ValueError:
                return "project"

    def resolve_delta_domain(self, preferred: str | None = None) -> str:
        """Pick delta domain: existing main specs first, else project folder name.

        - If ``openspec/specs/<domain>/`` already exists → use one of those
          (prefer *preferred* when it matches, else domain equal to project
          name, else the first sorted domain).
        - If there are no main domains yet → use the project directory name
          (not the change id, not a free-typed ``example`` stub).
        """
        existing = [str(s.get("domain") or "") for s in self.list_specs()]
        existing = [d for d in existing if d]
        pref_norm: str | None = None
        raw = (preferred or "").strip()
        if raw:
            try:
                pref_norm = validate_domain(raw)
            except ValueError:
                pref_norm = None
        if existing:
            if pref_norm:
                for d in existing:
                    if d == pref_norm or d.lower() == pref_norm.lower():
                        return d
            project_slug = self.project_domain_slug()
            for d in existing:
                if d == project_slug or d.lower() == project_slug.lower():
                    return d
            return sorted(existing)[0]
        return self.project_domain_slug()

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
                            "path": self.tool_relpath(d),
                            "archived": True,
                        }
                    )
        return active + archived

    def create_change(
        self,
        change_id: str,
        *,
        domain: str = "",
        request: str = "",
        understanding_gate_enabled: bool = False,
        understanding_threshold: int = 80,
    ) -> dict:
        if not self.is_initialized():
            raise RuntimeError("SDD not initialized — call sdd_init first")
        cid = validate_change_id(change_id)
        domain = self.resolve_delta_domain(domain)
        dest = change_dir(self.workspace, cid)
        if dest.exists():
            raise FileExistsError(f"change already exists: {cid}")
        dest.mkdir(parents=True)
        req = (request or "").strip()
        if req:
            _write_openspec_file(
                self.workspace,
                dest / "request.md",
                f"# Request: {cid}\n\n{req}\n",
            )
            proposal = (
                f"# Proposal: {cid}\n\n"
                f"## Why\n\n{req[:800]}\n\n"
                "## What Changes\n\n<!-- fill after understanding confirmed -->\n\n"
                "## Impact\n\n<!-- risks, migrations -->\n"
            )
            _write_openspec_file(self.workspace, dest / "proposal.md", proposal)
        else:
            _write_openspec_file(
                self.workspace,
                dest / "proposal.md",
                _PROPOSAL_STUB.format(change_id=cid),
            )
        _write_openspec_file(
            self.workspace,
            dest / "design.md",
            _DESIGN_STUB.format(change_id=cid),
        )
        _write_openspec_file(
            self.workspace,
            dest / "tasks.md",
            _TASKS_STUB.format(change_id=cid),
        )
        delta_dir = dest / "specs" / domain
        delta_dir.mkdir(parents=True)
        _write_openspec_file(
            self.workspace,
            delta_dir / SPEC_FILENAME,
            _DELTA_STUB.format(domain=domain, change_id=cid),
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
            "domain": domain,
            "path": self.tool_relpath(dest),
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
        rel = self.tool_relpath(cdir)
        tasks: list = []
        tasks_path = cdir / "tasks.md"
        if tasks_path.is_file():
            tasks = parse_tasks_markdown(_read_openspec_file(self.workspace, tasks_path))
        mode = load_apply_mode(self.workspace, cid)
        tasks_ok = self._tasks_ready_for_apply(tasks, apply_mode=mode)
        specs_dir = cdir / "specs"
        delta_specs: list[Path] = []
        if specs_dir.is_dir():
            root = os.path.realpath(str(openspec_root(self.workspace)))
            for p in specs_dir.rglob(SPEC_FILENAME):
                target = os.path.realpath(str(p))
                if target == root or target.startswith(root + os.sep):
                    delta_specs.append(Path(target))
        artifacts = {
            "proposal": (cdir / "proposal.md").is_file()
            and self._artifact_filled(cdir / "proposal.md"),
            "design": (cdir / "design.md").is_file() and self._artifact_filled(cdir / "design.md"),
            "tasks": tasks_path.is_file() and tasks_ok,
            # File existence alone is not enough — create_change writes stubs.
            "specs": bool(delta_specs) and all(self._artifact_filled(p) for p in delta_specs),
        }
        missing: list[str] = []
        if not artifacts["proposal"]:
            missing.append("proposal (fill Why/What/Impact)")
        if not artifacts["design"]:
            missing.append("design (fill approach + assignees, not stubs)")
        if not artifacts["specs"]:
            missing.append("delta specs (fill ADDED/MODIFIED requirements, not stubs)")
        if not artifacts["tasks"]:
            missing.append(self._tasks_missing_reason(tasks, apply_mode=mode))
        # design is reported for honesty/UI but not required to start apply
        apply_ready = (
            artifacts["proposal"] and artifacts["specs"] and artifacts["tasks"] and len(tasks) > 0
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
        from core.tools.file_diff import build_file_diff_payload

        cid = validate_change_id(change_id)
        cdir = change_dir(self.workspace, cid)
        if not cdir.is_dir():
            raise FileNotFoundError(f"change not found: {cid}")
        art = artifact.strip().lower()
        extra: dict = {}
        if art in ("proposal", "proposal.md"):
            path = cdir / "proposal.md"
        elif art in ("design", "design.md"):
            path = cdir / "design.md"
        elif art in ("tasks", "tasks.md"):
            path = cdir / "tasks.md"
            from core.sdd.task_sizing import size_summary
            from core.sdd.tasks import ensure_tasks_openspec_format, parse_tasks_markdown

            content, norm_notes = ensure_tasks_openspec_format(
                content, title=f"Tasks: {cid}", strict_size=True
            )
            tasks_written = parse_tasks_markdown(content)
            sizing = size_summary(tasks_written)
            extra = {
                "tasks_total": len(tasks_written),
                "normalized": bool(norm_notes),
                "normalize_notes": norm_notes,
                "format": "openspec-checklist",
                "size_summary": sizing,
                "hint": (
                    "Sub-agent tasks must be XS/S (occasionally M). "
                    "L/XL are rejected — split into smaller checklist items "
                    "so each job finishes in fewer steps."
                    if not sizing.get("ok")
                    else (
                        "Task sizes look good. Prefer parallel ready tasks "
                        "(shared depends_on) over long sequential mega-tasks."
                    )
                ),
            }
        elif art in ("specs", "spec", "delta", "spec.md"):
            # Prefer an already-scaffolded delta domain under this change, else resolve.
            if domain and str(domain).strip():
                dom = self.resolve_delta_domain(domain)
            else:
                existing_deltas = (
                    sorted(p.name for p in (cdir / "specs").iterdir() if p.is_dir())
                    if (cdir / "specs").is_dir()
                    else []
                )
                if len(existing_deltas) == 1:
                    dom = existing_deltas[0]
                elif existing_deltas:
                    resolved = self.resolve_delta_domain(None)
                    dom = resolved if resolved in existing_deltas else existing_deltas[0]
                else:
                    dom = self.resolve_delta_domain(None)
            path = cdir / "specs" / dom / SPEC_FILENAME
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            raise ValueError(f"unknown artifact {artifact!r}; use proposal|design|tasks|specs")

        before = None
        try:
            before = _read_openspec_file(self.workspace, path)
        except (FileNotFoundError, ValueError):
            before = None
        _write_openspec_file(self.workspace, path, content)
        rel = self.tool_relpath(path)
        out: dict = {
            "ok": True,
            "path": rel,
            "chars": len(content),
            **extra,
        }
        file_diff = build_file_diff_payload(rel, before, content)
        if file_diff:
            out["file_diff"] = file_diff
        return out

    def update_spec(
        self,
        change_id: str,
        *,
        op: str = "",
        title: str = "",
        body: str = "",
        content: str = "",
        domain: str | None = None,
    ) -> dict:
        """Incrementally patch a change delta spec (ADDED / MODIFIED / REMOVED).

        Main ``openspec/specs/<domain>/spec.md`` is not written here — archive
        merges the delta. ``main_preview`` shows the result after archive.
        """
        from core.sdd.merge import merge_delta_into_main, merge_delta_patches, patch_delta_spec
        from core.tools.file_diff import build_file_diff_payload

        cid = validate_change_id(change_id)
        cdir = change_dir(self.workspace, cid)
        if not cdir.is_dir():
            raise FileNotFoundError(f"change not found: {cid}")
        if domain and str(domain).strip():
            dom = self.resolve_delta_domain(domain)
        else:
            existing_deltas = (
                sorted(p.name for p in (cdir / "specs").iterdir() if p.is_dir())
                if (cdir / "specs").is_dir()
                else []
            )
            if len(existing_deltas) == 1:
                dom = existing_deltas[0]
            elif existing_deltas:
                resolved = self.resolve_delta_domain(None)
                dom = resolved if resolved in existing_deltas else existing_deltas[0]
            else:
                dom = self.resolve_delta_domain(None)
        root = os.path.realpath(str(openspec_root(self.workspace)))
        target = os.path.realpath(str(cdir / "specs" / dom / SPEC_FILENAME))
        if target != root and not target.startswith(root + os.sep):
            raise ValueError(f"path escapes {root}")
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            before = _read_openspec_file(self.workspace, path)
        except (FileNotFoundError, ValueError):
            before = ""
        patch = (content or "").strip()
        if patch:
            after = merge_delta_patches(before, patch)
        else:
            if not (op or "").strip() or not (title or "").strip():
                raise ValueError(
                    "pass op+title+body for one requirement, or content= delta markdown"
                )
            after = patch_delta_spec(before, op=op, title=title, body=body)
        _write_openspec_file(self.workspace, path, after)
        rel = self.tool_relpath(path)
        main_target = os.path.realpath(str(domain_spec_path(self.workspace, dom)))
        if main_target != root and not main_target.startswith(root + os.sep):
            raise ValueError(f"path escapes {root}")
        main_path = Path(main_target)
        main = main_path.read_text(encoding="utf-8") if main_path.is_file() else ""
        preview = merge_delta_into_main(main, after)
        out: dict = {
            "ok": True,
            "change_id": cid,
            "domain": dom,
            "path": rel,
            "op": (op or "").strip() or "content",
            "title": (title or "").strip(),
            "chars": len(after),
            "content": after,
            "main_path": self.tool_relpath(main_path),
            "main_preview": preview,
            "hint": (
                "Delta spec updated. Main openspec/specs/ changes only on sdd_archive. "
                "main_preview is the merged source of truth after archive."
            ),
        }
        file_diff = build_file_diff_payload(rel, before or None, after)
        if file_diff:
            out["file_diff"] = file_diff
        return out

    def read_artifact(
        self,
        change_id: str,
        artifact: str = "",
        *,
        domain: str | None = None,
    ) -> dict:
        """Read proposal / design / tasks / delta specs for a change.

        Empty ``artifact`` returns an index of all change artifacts (and
        contents when the file exists).
        """
        cid = validate_change_id(change_id)
        cdir = change_dir(self.workspace, cid)
        if not cdir.is_dir():
            raise FileNotFoundError(f"change not found: {cid}")
        art = (artifact or "").strip().lower()
        if art in ("proposal.md",):
            art = "proposal"
        elif art in ("design.md",):
            art = "design"
        elif art in ("tasks.md",):
            art = "tasks"
        elif art in ("spec", "delta", "spec.md"):
            art = "specs"
        root = os.path.realpath(str(openspec_root(self.workspace)))

        def _file_payload(path: Path, *, kind: str, extra: dict | None = None) -> dict:
            target = os.path.realpath(os.path.expanduser(str(path)))
            if target != root and not target.startswith(root + os.sep):
                raise ValueError(f"path escapes {root}")
            safe = Path(target)
            exists = safe.is_file()
            text = safe.read_text(encoding="utf-8") if exists else ""
            payload = {
                "artifact": kind,
                "path": self.tool_relpath(safe),
                "exists": exists,
                "chars": len(text),
                "filled": bool(exists and self._artifact_filled(safe)),
                "content": text,
            }
            if extra:
                payload.update(extra)
            return payload

        if not art or art in {"all", "*"}:
            specs_dir = cdir / "specs"
            spec_items: list[dict] = []
            if specs_dir.is_dir():
                for d in sorted(p for p in specs_dir.iterdir() if p.is_dir()):
                    spec_path = d / SPEC_FILENAME
                    spec_items.append(
                        _file_payload(spec_path, kind="specs", extra={"domain": d.name})
                    )
            return {
                "ok": True,
                "change_id": cid,
                "path": self.tool_relpath(cdir),
                "artifacts": {
                    "proposal": _file_payload(cdir / "proposal.md", kind="proposal"),
                    "design": _file_payload(cdir / "design.md", kind="design"),
                    "tasks": _file_payload(cdir / "tasks.md", kind="tasks"),
                    "specs": spec_items,
                },
            }

        extra: dict = {}
        if art == "proposal":
            path = cdir / "proposal.md"
        elif art == "design":
            path = cdir / "design.md"
        elif art == "tasks":
            path = cdir / "tasks.md"
        elif art == "specs":
            specs_dir = cdir / "specs"
            existing = (
                sorted(p.name for p in specs_dir.iterdir() if p.is_dir())
                if specs_dir.is_dir()
                else []
            )
            extra["delta_domains"] = existing
            if domain and str(domain).strip():
                dom = self.resolve_delta_domain(domain)
            elif len(existing) == 1:
                dom = existing[0]
            elif existing:
                resolved = self.resolve_delta_domain(None)
                dom = resolved if resolved in existing else existing[0]
            else:
                raise FileNotFoundError(f"no delta specs for change {cid}")
            extra["domain"] = dom
            path = cdir / "specs" / dom / SPEC_FILENAME
        else:
            raise ValueError(f"unknown artifact {artifact!r}; use proposal|design|tasks|specs")
        payload = _file_payload(path, kind=art, extra=extra)
        if not payload["exists"]:
            return {
                "ok": False,
                "error": f"{art} not found",
                "change_id": cid,
                **payload,
            }
        return {"ok": True, "change_id": cid, **payload}

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
        from core.sdd.task_sizing import max_steps_for_size, resolve_task_size

        jobs = load_task_jobs(self, cid)
        out: list[dict] = []
        for t in parse_tasks_markdown(path.read_text(encoding="utf-8")):
            size = resolve_task_size(t)
            out.append(
                {
                    "id": t.id,
                    "text": t.text,
                    "done": t.done,
                    "assignee": t.assignee,
                    "reason": t.reason,
                    "size": size,
                    "max_steps": max_steps_for_size(size),
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
        from core.sdd.task_graph import (
            build_task_graph,
            format_graph_summary,
            plan_rows_from_graph,
        )

        executors: dict[str, str] = {}
        for t in tasks:
            if mode == "self":
                executors[t.id] = "main"
            elif t.assignee in ("main", "unassigned", ""):
                executors[t.id] = "main"
            else:
                executors[t.id] = t.assignee
        graph = build_task_graph(tasks, infer_sequential=True)
        plan = plan_rows_from_graph(graph, executor_for=executors)
        summary = format_graph_summary(graph)
        return {
            "ok": True,
            "change_id": st.change_id,
            "apply_mode": mode,
            "plan": plan,
            "graph": graph.to_dict(),
            "graph_summary": summary,
            "message": (
                f"Apply mode={mode}. Execute by task graph waves "
                f"(depends_on + same-section order); mark done with sdd_check_task. "
                "Only ready tasks (deps satisfied) may run; "
                "for executor!=main use sdd_dispatch / subagent tools when mode is "
                "subagents/hybrid.\n"
                f"{summary}"
            ),
        }

    @staticmethod
    def _delta_domain_for_spec(specs_delta: Path, delta_spec: Path) -> str | None:
        """Map ``changes/<id>/specs/<domain>/…/spec.md`` → top-level domain name.

        OpenSpec layout is ``specs/<domain>/spec.md``. Nested files under a domain
        (e.g. ``specs/auth/notes/spec.md``) still merge into **auth**, not a
        bogus domain named after the nested folder.
        Only files named ``spec.md`` under ``specs/<domain>/`` (any depth) are used;
        the domain is the first path segment relative to ``specs/``.
        """
        try:
            rel = delta_spec.parent.resolve().relative_to(specs_delta.resolve())
        except ValueError:
            return None
        parts = rel.parts
        if not parts:
            return None
        domain = parts[0]
        try:
            validate_domain(domain)
        except ValueError:
            return None
        return domain

    def archive(self, change_id: str, *, force: bool = False) -> dict:
        """Merge delta specs into main library, then move change to archive.

        SDD rule: main ``openspec/specs/<domain>/spec.md`` is updated from
        ``changes/<id>/specs/<domain>/spec.md`` (ADDED/MODIFIED/REMOVED) **before**
        the change directory is moved. Without a successful merge, the change is
        **not** removed unless ``force=True`` (escape hatch).
        """
        cid = validate_change_id(change_id)
        cdir = change_dir(self.workspace, cid)
        if not cdir.is_dir():
            raise FileNotFoundError(f"change not found: {cid}")

        st = self.change_status(cid)
        warnings: list[str] = []
        if not st.apply_ready:
            warnings.append("Change is not apply_ready (proposal/specs/tasks incomplete).")
        open_tasks = [
            t
            for t in parse_tasks_markdown(
                (cdir / "tasks.md").read_text(encoding="utf-8")
                if (cdir / "tasks.md").is_file()
                else ""
            )
            if not t.done
        ]
        if open_tasks:
            warnings.append(
                f"{len(open_tasks)} open task(s) remain; archive will still merge deltas."
            )

        merged: list[str] = []
        merge_errors: list[str] = []
        specs_delta = cdir / "specs"
        # One merge pass per domain (later nested/duplicate delta files merge in sort order)
        domain_deltas: dict[str, list[Path]] = {}
        if specs_delta.is_dir():
            for delta_spec in sorted(specs_delta.rglob(SPEC_FILENAME)):
                domain = self._delta_domain_for_spec(specs_delta, delta_spec)
                if not domain:
                    merge_errors.append(
                        f"skipped non-domain delta path: {self.tool_relpath(delta_spec)}"
                    )
                    continue
                domain_deltas.setdefault(domain, []).append(delta_spec)

        # Hard gate: never delete the change if there is nothing to merge (unless force).
        if not domain_deltas and not force:
            return {
                "ok": False,
                "change_id": cid,
                "error": (
                    "No delta specs found to merge. Expected "
                    f"openspec/changes/{cid}/specs/<domain>/{SPEC_FILENAME} with "
                    "## ADDED|MODIFIED|REMOVED Requirements and "
                    "### Requirement: … blocks. Change was NOT archived."
                ),
                "merge_errors": merge_errors
                or [
                    f"missing changes/{cid}/specs/<domain>/{SPEC_FILENAME}",
                ],
                "warnings": warnings,
                "merged_specs": [],
            }

        requirements_merged = 0
        for domain, paths in sorted(domain_deltas.items()):
            main_path = domain_spec_path(self.workspace, domain)
            if main_path.is_file():
                main_text = main_path.read_text(encoding="utf-8")
            else:
                main_path.parent.mkdir(parents=True, exist_ok=True)
                main_text = f"# {domain}\n\n"
            domain_had_delta = False
            for delta_spec in paths:
                try:
                    delta_text = delta_spec.read_text(encoding="utf-8")
                    n_reqs = count_delta_requirements(delta_text)
                    if n_reqs <= 0:
                        merge_errors.append(
                            f"{self.tool_relpath(delta_spec)}: "
                            "no ### Requirement blocks under "
                            "## ADDED|MODIFIED|REMOVED Requirements"
                        )
                        continue
                    main_text = merge_delta_into_main(main_text, delta_text)
                    requirements_merged += n_reqs
                    domain_had_delta = True
                except Exception as exc:
                    merge_errors.append(f"{self.tool_relpath(delta_spec)}: {exc}")
            if domain_had_delta:
                main_path.write_text(main_text, encoding="utf-8")
                merged.append(self.tool_relpath(main_path))

        if not force:
            if not merged or requirements_merged <= 0:
                return {
                    "ok": False,
                    "change_id": cid,
                    "error": (
                        "Archive refused: delta specs did not merge into main. "
                        "Fill ## ADDED/MODIFIED/REMOVED Requirements with "
                        "### Requirement: titles, then retry. Change was NOT removed."
                    ),
                    "merge_errors": merge_errors or ["no mergeable requirements in delta specs"],
                    "warnings": warnings,
                    "merged_specs": merged,
                    "requirements_merged": requirements_merged,
                }

        arch = archive_root(self.workspace)
        arch.mkdir(parents=True, exist_ok=True)
        stamp = date.today().isoformat()
        dest = arch / f"{stamp}-{cid}"
        if dest.exists():
            dest = arch / f"{stamp}-{cid}-{_unique_suffix()}"
        # Move only after main specs were written successfully
        shutil.move(str(cdir), str(dest))
        result: dict = {
            "ok": True,
            "change_id": cid,
            "archived_to": self.tool_relpath(dest),
            "merged_specs": merged,
            "requirements_merged": requirements_merged,
        }
        if warnings:
            result["warnings"] = warnings
        if merge_errors:
            result["merge_errors"] = merge_errors
        return result

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
            "path": self.tool_relpath(self.root) if self.root.exists() else None,
            "project_root": str(self.workspace),
            "specs": self.list_specs() if self.is_initialized() else [],
            "changes": enriched,
        }

    @staticmethod
    def _artifact_filled(path: Path) -> bool:
        """True when markdown has real content (not create_change placeholders)."""
        text = path.read_text(encoding="utf-8")
        # Explicit scaffold markers from SpecStore stubs
        stub_markers = (
            "<!-- Why this change is needed -->",
            "<!-- User-visible and technical changes -->",
            "<!-- fill after understanding confirmed -->",
            "<!-- High-level design -->",
            "The system SHALL …",
            "The system SHALL ...",
            "- **GIVEN** …",
            "- **GIVEN** ...",
            "First concrete step",
            "Next step (set assignee",
        )
        if any(m in text for m in stub_markers):
            return False
        # strip comments and headings
        cleaned = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
        cleaned = re.sub(r"^#.*$", "", cleaned, flags=re.MULTILINE)
        # Ellipsis-only placeholders left from stubs
        if re.search(r"(?m)^\s*[-*]\s*\*\*[A-Z]+\*\*\s*[.…]+", cleaned):
            return False
        if "SHALL …" in cleaned or "SHALL ..." in cleaned:
            return False
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
