"""Dispatch apply plan tasks to subagents (or main) honouring the task graph."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from pathlib import Path
from typing import Any

from core.sdd.store import SpecStore
from core.sdd.task_completion import (
    clear_task_job,
    load_task_jobs_file,
    write_task_job,
)
from core.sdd.task_graph import (
    build_task_graph,
    format_graph_summary,
    ready_task_ids,
)


async def dispatch_change_tasks(
    store: SpecStore,
    change_id: str,
    *,
    parent_agent: Any,
    only_subagents: bool = True,
    ready_only: bool = True,
) -> dict[str, Any]:
    """Spawn subagents for non-main plan items that are graph-ready.

    Only tasks whose ``depends_on`` (and inferred same-section order) are
    satisfied are spawned. Tasks in later waves wait until prerequisites are
    marked done (auto-check on subagent success re-dispatches the next wave).

    Multiple ready tasks with the same assignee type run in parallel with
    instance names ``type-1``, ``type-2``, ….

    Returns job mapping task_id → job_id. Main tasks are listed but not spawned.
    """
    plan_result = store.begin_apply(change_id)
    if not plan_result.get("ok"):
        return plan_result

    mode = plan_result["apply_mode"]
    if mode == "self":
        return {
            "ok": True,
            "change_id": change_id,
            "apply_mode": mode,
            "spawned": [],
            "main_tasks": plan_result["plan"],
            "blocked": [],
            "graph": plan_result.get("graph"),
            "graph_summary": plan_result.get("graph_summary"),
            "message": (
                "Apply mode is self — no subagents spawned. "
                "Main agent should execute ready tasks from the graph plan "
                "(see waves / depends_on), then later waves."
            ),
            "plan": plan_result["plan"],
        }

    mgr = getattr(parent_agent, "subagents", None)
    if mgr is None:
        return {
            "ok": False,
            "error": "subagent manager not available on parent agent",
            "plan": plan_result["plan"],
            "graph": plan_result.get("graph"),
        }

    from core.config_utils import is_subagents_enabled

    cfg = getattr(parent_agent, "config", None)
    if not is_subagents_enabled(cfg):
        return {
            "ok": False,
            "error": "sub-agents disabled (enable_subagents / HOLIX_ENABLE_SUBAGENTS)",
            "plan": plan_result["plan"],
            "graph": plan_result.get("graph"),
        }

    project_rel = _project_rel(store, parent_agent)
    project_attr = f" project={project_rel}" if project_rel else ""

    plan_by_id = {
        str(item.get("id")): item
        for item in (plan_result.get("plan") or [])
        if item.get("id") is not None
    }

    # Rebuild graph from live tasks.md for accurate done/ready state
    from core.sdd.paths import change_dir, validate_change_id
    from core.sdd.tasks import parse_tasks_markdown

    cid = validate_change_id(change_id)
    tasks_path = change_dir(store.workspace, cid) / "tasks.md"
    tasks = parse_tasks_markdown(tasks_path.read_text(encoding="utf-8"))
    graph = build_task_graph(tasks, infer_sequential=True)
    graph_summary = format_graph_summary(graph)

    existing_jobs = load_task_jobs(store, change_id)

    ready_ids = set(ready_task_ids(graph))
    if not ready_only:
        ready_ids = {t.id for t in tasks if not t.done}

    main_tasks: list[dict[str, Any]] = []
    blocked_tasks: list[dict[str, Any]] = []
    sub_items: list[dict[str, Any]] = []
    stale_cleared: list[dict[str, str]] = []

    for t in tasks:
        if t.done:
            continue
        if t.id in plan_by_id:
            item = dict(plan_by_id[t.id])
        else:
            from core.sdd.task_sizing import max_steps_for_size, resolve_task_size

            size = resolve_task_size(t)
            item = {
                "id": t.id,
                "text": t.text,
                "assignee": t.assignee,
                "executor": t.assignee if t.assignee not in ("main", "unassigned", "") else "main",
                "size": size,
                "max_steps": max_steps_for_size(size),
                "depends_on": list(graph.depends_on.get(t.id, [])),
                "blocked_by": [
                    d for d in graph.depends_on.get(t.id, []) if not _task_done(tasks, d)
                ],
                "ready": t.id in ready_ids,
                "wave": (graph.wave_of.get(t.id, -1) + 1)
                if graph.wave_of.get(t.id, -1) >= 0
                else None,
                "unblocks": list(graph.dependents.get(t.id, [])),
            }
        # Always re-resolve size from live task text/size field.
        if not item.get("size"):
            from core.sdd.task_sizing import max_steps_for_size, resolve_task_size

            size = resolve_task_size(t)
            item["size"] = size
            item["max_steps"] = max_steps_for_size(size)
        executor = (item.get("executor") or "main").strip()
        if t.id not in ready_ids:
            blocked_tasks.append(item)
            continue
        if executor == "main":
            main_tasks.append(item)
            continue
        if only_subagents and executor == "main":
            continue
        prev_job = existing_jobs.get(t.id)
        if prev_job:
            if _job_is_active(parent_agent, prev_job):
                # Live job still running — do not double-spawn
                item = {**item, "already_dispatched": prev_job}
                sub_items.append(item)
                continue
            # Stale mapping (cancelled / completed / missing): clear so re-apply
            # can spawn a fresh subagent for the unfinished task.
            try:
                clear_task_job(
                    Path(store.workspace),
                    change_id,
                    str(t.id),
                    job_id=str(prev_job),
                )
                stale_cleared.append({"task_id": str(t.id), "job_id": str(prev_job)})
            except Exception:
                pass
        sub_items.append(item)

    # Only spawn those without an existing job mapping
    to_spawn = [i for i in sub_items if not i.get("already_dispatched")]

    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in to_spawn:
        by_type[(item.get("executor") or "").strip()].append(item)

    spawn_jobs: list[tuple[dict[str, Any], str, str]] = []
    for agent_type, items in by_type.items():
        if not agent_type:
            continue
        if len(items) == 1:
            spawn_jobs.append((items[0], agent_type, ""))
        else:
            for idx, item in enumerate(items, start=1):
                spawn_jobs.append((item, agent_type, f"{agent_type}-{idx}"))

    async def _spawn_one(
        item: dict[str, Any], agent_type: str, instance_name: str
    ) -> dict[str, Any]:
        from core.sdd.task_sizing import max_steps_for_size, resolve_task_size

        task_id = item.get("id")
        deps = item.get("depends_on") or []
        blocked = item.get("blocked_by") or []
        unblocks = item.get("unblocks") or []
        wave = item.get("wave")
        wave_label = f"wave={wave}" if wave else "wave=?"
        deps_label = ",".join(str(d) for d in deps) if deps else "none"
        # Prefer size from plan/item; fall back to heuristic on text.
        size = item.get("size") or resolve_task_size(item)
        budget = int(item.get("max_steps") or max_steps_for_size(size))
        task_text = (
            f"[SDD change={change_id} task={task_id}{project_attr}]\n"
            f"Task graph: {wave_label}; depends_on={deps_label}; "
            f"unblocks={','.join(str(u) for u in unblocks) if unblocks else 'none'}\n"
            f"Size: {size} (budget ≈ {budget} steps — stay focused).\n"
            f"{item.get('text')}\n\n"
            "Implement THIS task only, in graph order.\n"
            f"- Prerequisites (must already be done): {deps_label}\n"
            f"- Still blocked if any of these incomplete: "
            f"{', '.join(str(b) for b in blocked) if blocked else 'none'}\n"
            f"- Downstream tasks waiting on you: "
            f"{', '.join(str(u) for u in unblocks) if unblocks else 'none'}\n"
            "Scope discipline: do not expand into neighboring tasks. "
            "Prefer the minimal file set for this deliverable. "
            "Do not start work that belongs to other task ids. "
            "Respect openspec delta specs for this change. "
            "Do not modify unrelated files. "
            "When finished, the parent will mark the SDD checkbox automatically on success "
            "and may dispatch the next wave."
        )
        try:
            kwargs: dict[str, Any] = {"max_steps": budget}
            if instance_name:
                kwargs["instance_name"] = instance_name
            handle = await mgr.spawn_typed(agent_type, task_text, **kwargs)
            h, _ = handle if isinstance(handle, tuple) else (handle, None)
            job = {
                "task_id": task_id,
                "text": item.get("text"),
                "assignee": item.get("assignee"),
                "executor": agent_type,
                "job_id": getattr(h, "name", None),
                "wave": wave,
                "size": size,
                "max_steps": budget,
                "depends_on": list(deps),
                "process_mode": getattr(getattr(h, "config", None), "process_mode", None),
            }
            if job["process_mode"] is not None and hasattr(job["process_mode"], "value"):
                job["process_mode"] = job["process_mode"].value
            if getattr(h, "followed_process", False) is True:
                job["followed_process"] = True
                job["studio_process_id"] = str(getattr(h, "studio_process_id", "") or "")
                sdd = getattr(h, "studio_sdd", None)
                if isinstance(sdd, dict) and sdd:
                    job["sdd"] = sdd
                wt = str(getattr(h, "studio_worktree", "") or "").strip()
                if not wt and isinstance(sdd, dict):
                    wt = str(sdd.get("worktree") or "").strip()
                if wt:
                    job["worktree"] = wt
                job["wait_hint"] = (
                    "wait_subagent_result(job_id) blocks until the Studio "
                    "process run finishes — not the first child step. "
                    "Do not treat this SDD task as done until that wait returns."
                )
            _record_task_job(
                store,
                change_id,
                str(task_id or ""),
                job["job_id"] or "",
                project_rel=project_rel,
            )
            return {"ok": True, "job": job}
        except Exception as exc:
            return {
                "ok": False,
                "item": item,
                "error": str(exc),
            }

    results = (
        await asyncio.gather(*[_spawn_one(item, atype, iname) for item, atype, iname in spawn_jobs])
        if spawn_jobs
        else []
    )

    spawned: list[dict[str, Any]] = []
    errors: list[str] = []
    for res in results:
        if res.get("ok"):
            spawned.append(res["job"])
        else:
            item = res.get("item") or {}
            err = res.get("error") or "unknown"
            errors.append(f"task {item.get('id')}: {err}")
            main_tasks.append({**item, "dispatch_error": err})

    already = [
        {
            "task_id": i.get("id"),
            "job_id": i.get("already_dispatched"),
            "wave": i.get("wave"),
        }
        for i in sub_items
        if i.get("already_dispatched")
    ]

    return {
        "ok": True,
        "change_id": change_id,
        "apply_mode": mode,
        "spawned": spawned,
        "already_running": already,
        "stale_cleared": stale_cleared,
        "main_tasks": main_tasks,
        "blocked": blocked_tasks,
        "errors": errors,
        "graph": graph.to_dict(),
        "graph_summary": graph_summary,
        "message": (
            f"Wave dispatch: spawned {len(spawned)} subagent(s); "
            f"{len(already)} already dispatched; "
            f"{len(stale_cleared)} stale job map(s) cleared; "
            f"{len(main_tasks)} ready main task(s); "
            f"{len(blocked_tasks)} blocked by dependencies. "
            "Successful jobs auto-mark tasks.md and re-dispatch the next ready wave. "
            "Main ready tasks still need sdd_check_task. "
            "Jobs with followed_process=true are Studio processes: "
            "wait_subagent_result(job_id) until the process finishes; "
            "do not treat that SDD task as done on the first child step.\n"
            f"{graph_summary}"
        ),
        "plan": plan_result["plan"],
    }


def _job_is_active(parent_agent: Any, job_id: str) -> bool:
    """True when the mapped job is still a live/running subagent."""
    jid = str(job_id or "").strip()
    if not jid:
        return False
    mgr = getattr(parent_agent, "subagents", None)
    if mgr is None:
        return False

    handle = None
    get_handle = getattr(mgr, "get_handle", None)
    if callable(get_handle):
        try:
            handle = get_handle(jid)
        except Exception:
            handle = None
    if handle is None:
        # Also match bare name against active list (owner::name vs name)
        bare = jid.split("::")[-1] if "::" in jid else jid
        try:
            for h in list(mgr.list_active() or []):
                name = str(getattr(h, "name", "") or "")
                if name == jid or name == bare or name.endswith(f"::{bare}"):
                    handle = h
                    break
        except Exception:
            handle = None
    if handle is None:
        return False
    if bool(getattr(handle, "is_running", False)):
        return True
    status = getattr(handle, "status", None)
    status_val = (status.value if hasattr(status, "value") else str(status or "")).strip().lower()
    return status_val in {"running", "pending", "starting"}


def _task_done(tasks: list[Any], task_id: str) -> bool:
    for t in tasks:
        if getattr(t, "id", None) == task_id:
            return bool(getattr(t, "done", False))
    return False


def _project_rel(store: SpecStore, parent_agent: Any) -> str:
    """Relative project path under agent workspace ('' = workspace root)."""
    try:
        cfg = getattr(parent_agent, "config", None)
        parent_ws = getattr(cfg, "workspace_root", None)
        if not parent_ws:
            return ""
        parent = Path(parent_ws).expanduser().resolve()
        proj = Path(store.workspace).expanduser().resolve()
        rel = proj.relative_to(parent)
        s = str(rel).replace("\\", "/").strip("/")
        return "" if s in (".", "") else s
    except Exception:
        return ""


def _record_task_job(
    store: SpecStore,
    change_id: str,
    task_id: str,
    job_id: str,
    *,
    project_rel: str = "",
) -> None:
    write_task_job(
        Path(store.workspace),
        change_id,
        task_id,
        job_id,
        project_rel=project_rel,
    )


def load_task_jobs(store: SpecStore, change_id: str) -> dict[str, str]:
    from core.sdd.paths import change_dir, validate_change_id

    path = change_dir(store.workspace, validate_change_id(change_id)) / ".task-jobs.json"
    return load_task_jobs_file(path)
