"""Task dependency graph and execution waves for SDD ``tasks.md``."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from core.sdd.models import SpecTask


@dataclass
class TaskGraph:
    """Directed acyclic graph of SDD tasks with topological waves."""

    tasks: dict[str, SpecTask] = field(default_factory=dict)
    # task_id → list of prerequisite task ids
    depends_on: dict[str, list[str]] = field(default_factory=dict)
    # task_id → tasks that list this id as a dependency
    dependents: dict[str, list[str]] = field(default_factory=dict)
    # wave index (0-based) → task ids ready in that wave (ignoring done)
    waves: list[list[str]] = field(default_factory=list)
    # task_id → wave index (or -1 if in a cycle / unknown)
    wave_of: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    inferred: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "waves": [
                {"wave": i + 1, "tasks": list(ids)} for i, ids in enumerate(self.waves)
            ],
            "depends_on": {k: list(v) for k, v in self.depends_on.items()},
            "dependents": {k: list(v) for k, v in self.dependents.items()},
            "wave_of": dict(self.wave_of),
            "inferred": {k: list(v) for k, v in self.inferred.items()},
            "errors": list(self.errors),
            "total_tasks": len(self.tasks),
        }


def _natural_task_key(task_id: str) -> tuple:
    parts: list[Any] = []
    for bit in str(task_id).split("."):
        if bit.isdigit():
            parts.append((0, int(bit)))
        else:
            parts.append((1, bit))
    return tuple(parts)


def _parent_id(task_id: str) -> str:
    tid = str(task_id)
    if "." not in tid:
        return ""
    return tid.rsplit(".", 1)[0]


def infer_sequential_depends(tasks: list[SpecTask]) -> dict[str, list[str]]:
    """Within the same parent (1.1, 1.2, 1.3), chain previous sibling as dep.

    Only for tasks that have **no** explicit ``depends_on``. Cross-section
    (1.x vs 2.x) stays independent unless declared.
    """
    by_parent: dict[str, list[SpecTask]] = defaultdict(list)
    for t in tasks:
        by_parent[_parent_id(t.id)].append(t)

    inferred: dict[str, list[str]] = {}
    for _parent, group in by_parent.items():
        ordered = sorted(group, key=lambda t: _natural_task_key(t.id))
        prev: str | None = None
        for t in ordered:
            if t.depends_on:
                prev = t.id
                continue
            if prev is not None:
                inferred[t.id] = [prev]
            prev = t.id
    return inferred


def build_task_graph(
    tasks: Iterable[SpecTask],
    *,
    infer_sequential: bool = True,
) -> TaskGraph:
    """Build dependency graph and topological waves.

    Done tasks are kept in the graph (for unblocking) but omitted from waves.
    """
    task_list = list(tasks)
    by_id: dict[str, SpecTask] = {t.id: t for t in task_list}
    graph = TaskGraph(tasks=by_id)

    explicit: dict[str, list[str]] = {}
    for t in task_list:
        deps = [d for d in (t.depends_on or []) if str(d).strip()]
        # Drop self-deps and unknown ids (warn)
        cleaned: list[str] = []
        for d in deps:
            if d == t.id:
                graph.errors.append(f"task {t.id}: depends on itself (ignored)")
                continue
            if d not in by_id:
                graph.errors.append(f"task {t.id}: unknown dependency {d!r}")
                continue
            if d not in cleaned:
                cleaned.append(d)
        explicit[t.id] = cleaned

    inferred: dict[str, list[str]] = {}
    if infer_sequential:
        for tid, deps in infer_sequential_depends(task_list).items():
            if explicit.get(tid):
                continue
            # only keep known ids
            keep = [d for d in deps if d in by_id and d != tid]
            if keep:
                inferred[tid] = keep
                graph.inferred[tid] = list(keep)

    depends: dict[str, list[str]] = {}
    for t in task_list:
        deps = list(explicit.get(t.id) or [])
        if not deps and t.id in inferred:
            deps = list(inferred[t.id])
        depends[t.id] = deps
    graph.depends_on = depends

    dependents: dict[str, list[str]] = defaultdict(list)
    for tid, deps in depends.items():
        for d in deps:
            dependents[d].append(tid)
    graph.dependents = {k: sorted(v, key=_natural_task_key) for k, v in dependents.items()}

    # Kahn topological levels (waves), skipping already-done tasks as satisfied
    remaining = {t.id for t in task_list if not t.done}
    satisfied = {t.id for t in task_list if t.done}
    in_degree: dict[str, int] = {}
    for tid in remaining:
        in_degree[tid] = sum(1 for d in depends.get(tid, []) if d not in satisfied)

    waves: list[list[str]] = []
    while remaining:
        ready = sorted(
            [tid for tid in remaining if in_degree.get(tid, 0) == 0],
            key=_natural_task_key,
        )
        if not ready:
            # Cycle among remaining
            cycle_ids = sorted(remaining, key=_natural_task_key)
            graph.errors.append(
                "dependency cycle among tasks: " + ", ".join(cycle_ids)
            )
            for tid in cycle_ids:
                graph.wave_of[tid] = -1
            break
        waves.append(ready)
        wave_idx = len(waves) - 1
        for tid in ready:
            graph.wave_of[tid] = wave_idx
            remaining.discard(tid)
            satisfied.add(tid)
            for child in dependents.get(tid, []):
                if child in in_degree:
                    in_degree[child] = max(0, in_degree[child] - 1)

    graph.waves = waves
    # Done tasks: wave -1 (complete)
    for t in task_list:
        if t.done and t.id not in graph.wave_of:
            graph.wave_of[t.id] = -1
    return graph


def blocked_by(task_id: str, graph: TaskGraph, *, done_ids: set[str] | None = None) -> list[str]:
    """Unsatisfied prerequisites for *task_id*."""
    done = done_ids if done_ids is not None else {
        tid for tid, t in graph.tasks.items() if t.done
    }
    return [d for d in graph.depends_on.get(task_id, []) if d not in done]


def ready_task_ids(
    graph: TaskGraph,
    *,
    done_ids: set[str] | None = None,
    exclude: set[str] | None = None,
) -> list[str]:
    """Task ids with all dependencies satisfied and not done."""
    done = done_ids if done_ids is not None else {
        tid for tid, t in graph.tasks.items() if t.done
    }
    skip = exclude or set()
    ready: list[str] = []
    for tid, task in graph.tasks.items():
        if task.done or tid in done or tid in skip:
            continue
        if blocked_by(tid, graph, done_ids=done):
            continue
        ready.append(tid)
    return sorted(ready, key=_natural_task_key)


def plan_rows_from_graph(
    graph: TaskGraph,
    *,
    executor_for: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Serialize open tasks with wave / dependency metadata for apply/dispatch."""
    executors = executor_for or {}
    done = {tid for tid, t in graph.tasks.items() if t.done}
    rows: list[dict[str, Any]] = []
    for tid, task in sorted(graph.tasks.items(), key=lambda kv: _natural_task_key(kv[0])):
        if task.done:
            continue
        deps = list(graph.depends_on.get(tid, []))
        blocked = blocked_by(tid, graph, done_ids=done)
        wave = graph.wave_of.get(tid)
        wave_num = (wave + 1) if isinstance(wave, int) and wave >= 0 else None
        unblocks = list(graph.dependents.get(tid, []))
        from core.sdd.task_sizing import max_steps_for_size, resolve_task_size

        size = resolve_task_size(task)
        rows.append(
            {
                "id": tid,
                "text": task.text,
                "assignee": task.assignee,
                "executor": executors.get(tid, task.assignee or "main"),
                "size": size,
                "max_steps": max_steps_for_size(size),
                "depends_on": deps,
                "blocked_by": blocked,
                "ready": not blocked,
                "wave": wave_num,
                "unblocks": unblocks,
                "depends_inferred": tid in graph.inferred,
            }
        )
    # Sort by wave then id
    rows.sort(
        key=lambda r: (
            r["wave"] if r["wave"] is not None else 10_000,
            _natural_task_key(str(r["id"])),
        )
    )
    return rows


def format_graph_summary(graph: TaskGraph) -> str:
    """Short human-readable waves for Telegram / agent messages."""
    if graph.errors:
        err = "; ".join(graph.errors[:5])
        head = f"Graph warnings: {err}\n"
    else:
        head = ""
    if not graph.waves:
        return head + "No open tasks in graph."
    lines = [head + f"Task graph: {len(graph.waves)} wave(s)"]
    for i, ids in enumerate(graph.waves, start=1):
        parts = []
        for tid in ids:
            t = graph.tasks.get(tid)
            who = (t.assignee if t else "?") or "?"
            parts.append(f"{tid}→{who}")
        lines.append(f"  wave {i}: " + ", ".join(parts))
    return "\n".join(lines).strip()
