"""Dispatch apply plan tasks to subagents (or main)."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from pathlib import Path
from typing import Any

from core.sdd.store import SpecStore
from core.sdd.task_completion import load_task_jobs_file, write_task_job


async def dispatch_change_tasks(
    store: SpecStore,
    change_id: str,
    *,
    parent_agent: Any,
    only_subagents: bool = True,
) -> dict[str, Any]:
    """Spawn subagents for non-main plan items.

    Multiple tasks with the same assignee type are started in parallel with
    instance names ``type-1``, ``type-2``, … so they can run concurrently.

    Returns job mapping task_id → job_id. Main tasks are listed but not spawned.
    On successful subagent completion, tasks are auto-checked in tasks.md.
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
            "message": (
                "Apply mode is self — no subagents spawned. "
                "Main agent should execute all tasks from the plan."
            ),
            "plan": plan_result["plan"],
        }

    mgr = getattr(parent_agent, "subagents", None)
    if mgr is None:
        return {
            "ok": False,
            "error": "subagent manager not available on parent agent",
            "plan": plan_result["plan"],
        }

    from core.config_utils import is_subagents_enabled

    cfg = getattr(parent_agent, "config", None)
    if not is_subagents_enabled(cfg):
        return {
            "ok": False,
            "error": "sub-agents disabled (enable_subagents / HOLIX_ENABLE_SUBAGENTS)",
            "plan": plan_result["plan"],
        }

    project_rel = _project_rel(store, parent_agent)
    project_attr = f" project={project_rel}" if project_rel else ""

    main_tasks: list[dict[str, Any]] = []
    sub_items: list[dict[str, Any]] = []
    for item in plan_result["plan"]:
        executor = (item.get("executor") or "main").strip()
        if executor == "main":
            main_tasks.append(item)
            continue
        if only_subagents and executor == "main":
            continue
        sub_items.append(item)

    # Group by agent type → numbered instances type-1, type-2, …
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in sub_items:
        by_type[(item.get("executor") or "").strip()].append(item)

    spawn_jobs: list[tuple[dict[str, Any], str, str]] = []
    for agent_type, items in by_type.items():
        if not agent_type:
            continue
        if len(items) == 1:
            # Single task: bare type name (or -1 if busy via allocate_name)
            spawn_jobs.append((items[0], agent_type, ""))
        else:
            for idx, item in enumerate(items, start=1):
                spawn_jobs.append((item, agent_type, f"{agent_type}-{idx}"))

    async def _spawn_one(
        item: dict[str, Any], agent_type: str, instance_name: str
    ) -> dict[str, Any]:
        task_id = item.get("id")
        task_text = (
            f"[SDD change={change_id} task={task_id}{project_attr}]\n"
            f"{item.get('text')}\n\n"
            "Implement this task only. Respect openspec delta specs for this change. "
            "Do not modify unrelated files. "
            "When finished, the parent will mark the SDD checkbox automatically on success."
        )
        try:
            kwargs: dict[str, Any] = {}
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
                "process_mode": getattr(
                    getattr(h, "config", None), "process_mode", None
                ),
            }
            if job["process_mode"] is not None and hasattr(job["process_mode"], "value"):
                job["process_mode"] = job["process_mode"].value
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

    # Parallel spawn (respect manager concurrency limits inside spawn)
    results = await asyncio.gather(
        *[_spawn_one(item, atype, iname) for item, atype, iname in spawn_jobs]
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

    return {
        "ok": True,
        "change_id": change_id,
        "apply_mode": mode,
        "spawned": spawned,
        "main_tasks": main_tasks,
        "errors": errors,
        "message": (
            f"Spawned {len(spawned)} subagent(s) (parallel when same type uses "
            f"-1/-2/… suffixes); {len(main_tasks)} task(s) for main. "
            "Successful subagent jobs auto-mark tasks.md; "
            "use wait_subagent_result / list_subagents; main tasks still need sdd_check_task "
            "(checking a task done cancels its still-running subagent)."
        ),
        "plan": plan_result["plan"],
    }


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
