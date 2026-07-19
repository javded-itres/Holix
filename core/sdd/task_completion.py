"""Auto-mark SDD tasks when dispatched subagents finish successfully."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# [SDD change=feat-x task=1.1] or with project=
_SDD_MARKER_RE = re.compile(
    r"\[SDD\s+change=(?P<change>[a-z0-9][a-z0-9\-_]{0,63})"
    r"\s+task=(?P<task>[^\s\]]+)"
    r"(?:\s+project=(?P<project>[^\]]+))?\]",
    re.IGNORECASE,
)


def parse_sdd_task_marker(text: str | None) -> dict[str, str] | None:
    """Extract change_id / task_id / optional project from subagent task text."""
    if not text:
        return None
    m = _SDD_MARKER_RE.search(text)
    if not m:
        return None
    project = (m.group("project") or "").strip().replace("\\", "/").strip("/")
    if project in (".", ""):
        project = ""
    return {
        "change_id": m.group("change").strip().lower(),
        "task_id": m.group("task").strip(),
        "project": project,
    }


def _normalize_jobs_payload(raw: Any) -> dict[str, str]:
    """Return task_id → job_id from legacy flat or structured file."""
    if not isinstance(raw, dict):
        return {}
    if isinstance(raw.get("by_task"), dict):
        out: dict[str, str] = {}
        for k, v in raw["by_task"].items():
            if isinstance(v, str) and v.strip():
                out[str(k)] = v.strip()
            elif isinstance(v, dict) and v.get("job_id"):
                out[str(k)] = str(v["job_id"]).strip()
        return out
    out = {}
    for k, v in raw.items():
        if k in ("by_job", "meta"):
            continue
        if isinstance(v, str) and v.strip():
            out[str(k)] = v.strip()
        elif isinstance(v, dict) and v.get("job_id"):
            out[str(k)] = str(v["job_id"]).strip()
    return out


def load_task_jobs_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        return _normalize_jobs_payload(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return {}


def write_task_job(
    project_root: Path,
    change_id: str,
    task_id: str,
    job_id: str,
    *,
    project_rel: str = "",
) -> None:
    """Persist task↔job mapping (flat by_task + reverse by_job)."""
    from core.sdd.paths import change_dir, validate_change_id

    if not task_id or not job_id:
        return
    cid = validate_change_id(change_id)
    path = change_dir(project_root, cid) / ".task-jobs.json"
    by_task = load_task_jobs_file(path)
    by_task[str(task_id)] = job_id
    by_job: dict[str, dict[str, str]] = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("by_job"), dict):
                by_job = {
                    str(k): dict(v) if isinstance(v, dict) else {"task_id": str(v)}
                    for k, v in raw["by_job"].items()
                }
        except Exception:
            by_job = {}
    by_job[job_id] = {
        "task_id": str(task_id),
        "change_id": cid,
        "project": (project_rel or "").strip().replace("\\", "/").strip("/"),
    }
    payload = {"by_task": by_task, "by_job": by_job}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def find_job_binding(
    workspace: Path,
    job_id: str,
) -> dict[str, str] | None:
    """Find change/task for a job_id by scanning openspec changes under workspace."""
    if not job_id or not workspace:
        return None
    from core.sdd.projects import discover_sdd_projects, resolve_project_root

    roots: list[tuple[str, Path]] = []
    try:
        for p in discover_sdd_projects(workspace):
            rel = str(p.get("path") or "")
            roots.append((rel, resolve_project_root(workspace, rel)))
    except Exception:
        roots = [("", Path(workspace))]
    if not roots:
        roots = [("", Path(workspace))]

    from core.sdd.paths import changes_root

    for project_rel, root in roots:
        changes = changes_root(root)
        if not changes.is_dir():
            continue
        for change_dir_path in changes.iterdir():
            if not change_dir_path.is_dir() or change_dir_path.name == "archive":
                continue
            jobs_path = change_dir_path / ".task-jobs.json"
            if not jobs_path.is_file():
                continue
            try:
                raw = json.loads(jobs_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(raw, dict) and isinstance(raw.get("by_job"), dict):
                entry = raw["by_job"].get(job_id)
                if isinstance(entry, dict) and entry.get("task_id"):
                    return {
                        "change_id": str(
                            entry.get("change_id") or change_dir_path.name
                        ),
                        "task_id": str(entry["task_id"]),
                        "project": str(entry.get("project") or project_rel or ""),
                        "project_root": str(root),
                    }
            # legacy flat / by_task only
            by_task = _normalize_jobs_payload(raw)
            for tid, jid in by_task.items():
                if jid == job_id:
                    return {
                        "change_id": change_dir_path.name,
                        "task_id": tid,
                        "project": project_rel,
                        "project_root": str(root),
                    }
    return None


def mark_sdd_task_done(
    *,
    project_root: Path | str,
    change_id: str,
    task_id: str,
) -> dict[str, Any]:
    from core.sdd.store import SpecStore

    store = SpecStore(project_root)
    return store.check_task(change_id, task_id=task_id, done=True)


def job_ids_for_change(project_root: Path | str, change_id: str) -> dict[str, str]:
    """task_id → job_id for a change (from .task-jobs.json)."""
    from core.sdd.paths import change_dir, validate_change_id

    try:
        cid = validate_change_id(change_id)
    except Exception:
        return {}
    path = change_dir(Path(project_root), cid) / ".task-jobs.json"
    return load_task_jobs_file(path)


def _running_sdd_handles(parent_agent: Any) -> list[Any]:
    mgr = getattr(parent_agent, "subagents", None)
    if mgr is None:
        return []
    try:
        return list(mgr.list_active())
    except Exception:
        handles = getattr(mgr, "_handles", None) or {}
        out = []
        for h in handles.values():
            if getattr(h, "is_running", False):
                out.append(h)
        return out


async def cancel_sdd_subagents_after_check(
    parent_agent: Any | None,
    *,
    project_root: Path | str,
    change_id: str,
    task_id: str | None = None,
    done: bool = True,
    tasks_done: int | None = None,
    tasks_total: int | None = None,
) -> dict[str, Any]:
    """Stop subagents still working on SDD tasks that are now checked done.

    Why: ``sdd_check_task`` / Studio UI only update tasks.md. Without this,
    marking a task (or the whole change) complete leaves dispatched subagents
    running until max_steps / timeout.

    - When a specific task is marked done → cancel its bound job (by
      ``.task-jobs.json`` and/or ``[SDD change=… task=…]`` marker).
    - When every task is done → cancel all remaining SDD jobs for the change.
    """
    if not done or parent_agent is None:
        return {"cancelled_jobs": []}

    mgr = getattr(parent_agent, "subagents", None)
    if mgr is None or not hasattr(mgr, "terminate"):
        return {"cancelled_jobs": []}

    cid = (change_id or "").strip().lower()
    if not cid:
        return {"cancelled_jobs": []}

    want_jobs: set[str] = set()
    jobs_map = job_ids_for_change(project_root, cid)

    if task_id:
        jid = jobs_map.get(str(task_id))
        if jid:
            want_jobs.add(jid)

    all_done = (
        tasks_done is not None
        and tasks_total is not None
        and tasks_total > 0
        and tasks_done >= tasks_total
    )
    if all_done:
        want_jobs.update(j for j in jobs_map.values() if j)

    # Also match live handles by SDD marker (covers missing/stale job index)
    for handle in _running_sdd_handles(parent_agent):
        marker = parse_sdd_task_marker(getattr(handle, "task_preview", None) or "")
        if not marker or marker.get("change_id") != cid:
            continue
        name = getattr(handle, "name", None)
        if not name:
            continue
        if all_done:
            want_jobs.add(str(name))
        elif task_id and marker.get("task_id") == str(task_id):
            want_jobs.add(str(name))

    cancelled: list[str] = []
    for job_id in sorted(want_jobs):
        try:
            ok = await mgr.terminate(job_id)
        except Exception as exc:
            logger.warning(
                "SDD: failed to cancel subagent %s after task check: %s",
                job_id,
                exc,
            )
            continue
        if ok:
            cancelled.append(job_id)
            logger.info(
                "SDD: cancelled subagent %s (change=%s task=%s done)",
                job_id,
                cid,
                task_id or "*",
            )

    return {
        "cancelled_jobs": cancelled,
        "cancel_requested": sorted(want_jobs),
    }


def try_complete_sdd_task_for_subagent(
    *,
    job_id: str,
    task_preview: str | None,
    success: bool,
    workspace: Path | str | None,
) -> dict[str, Any] | None:
    """If this job was an SDD-dispatched task and finished OK, mark checkbox done.

    Returns result dict when a task was marked, else None.
    """
    if not success or not job_id:
        return None
    ws = Path(workspace).expanduser().resolve() if workspace else None
    if ws is None or not ws.is_dir():
        return None

    binding = parse_sdd_task_marker(task_preview)
    project_root: Path | None = None
    change_id = ""
    task_id = ""

    if binding:
        change_id = binding["change_id"]
        task_id = binding["task_id"]
        from core.sdd.projects import resolve_project_root

        try:
            project_root = resolve_project_root(ws, binding.get("project") or "")
        except Exception:
            project_root = ws
    else:
        found = find_job_binding(ws, job_id)
        if not found:
            return None
        change_id = found["change_id"]
        task_id = found["task_id"]
        project_root = Path(found["project_root"])

    if not change_id or not task_id or project_root is None:
        return None

    try:
        result = mark_sdd_task_done(
            project_root=project_root,
            change_id=change_id,
            task_id=task_id,
        )
        logger.info(
            "SDD auto-check task %s in %s (job=%s) → done",
            task_id,
            change_id,
            job_id,
        )
        return {
            "ok": True,
            "change_id": change_id,
            "task_id": task_id,
            "job_id": job_id,
            "project_root": str(project_root),
            **result,
        }
    except Exception as exc:
        logger.warning(
            "SDD auto-check failed for job=%s task=%s: %s",
            job_id,
            task_id,
            exc,
        )
        return {"ok": False, "error": str(exc), "job_id": job_id, "task_id": task_id}
