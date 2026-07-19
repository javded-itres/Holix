"""Parse and rewrite ``tasks.md`` checklists with assignees."""

from __future__ import annotations

import re
from collections.abc import Iterable

from core.sdd.models import SpecTask

_TASK_LINE_RE = re.compile(r"^(\s*)- \[([ xX])\]\s+(.*)$")
_ASSIGNEE_RE = re.compile(
    r"^\s*-\s*\*\*assignee:\*\*\s*`?([^`\n]+?)`?\s*$",
    re.IGNORECASE,
)
# Loose form sometimes written by models; only used if no formal assignee yet
_ASSIGNEE_LOOSE_RE = re.compile(
    r"^\s*-\s*assignee:\s*`?([^`\n]+?)`?\s*$",
    re.IGNORECASE,
)
_REASON_RE = re.compile(
    r"^\s*-\s*\*\*reason:\*\*\s*(.*)$",
    re.IGNORECASE,
)
_ID_PREFIX_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+")


def parse_tasks_markdown(content: str) -> list[SpecTask]:
    """Parse checklist tasks and nested assignee/reason lines."""
    lines = content.splitlines()
    tasks: list[SpecTask] = []
    i = 0
    ordinal = 0
    while i < len(lines):
        m = _TASK_LINE_RE.match(lines[i])
        if not m:
            i += 1
            continue
        done = m.group(2).lower() == "x"
        text = m.group(3).strip()
        task_line = i
        assignee = "unassigned"
        reason = ""
        j = i + 1
        while j < len(lines):
            if _TASK_LINE_RE.match(lines[j]):
                break
            # Stop at next markdown heading
            if lines[j].startswith("#"):
                break
            am = _ASSIGNEE_RE.match(lines[j])
            if am:
                # Formal **assignee:** always wins (even if a loose line follows)
                assignee = am.group(1).strip() or "unassigned"
                j += 1
                continue
            loose = _ASSIGNEE_LOOSE_RE.match(lines[j])
            if loose:
                # Ignore loose lines that conflict with a formal assignee already set
                if assignee in ("unassigned", "", None):
                    assignee = loose.group(1).strip() or "unassigned"
                j += 1
                continue
            rm = _REASON_RE.match(lines[j])
            if rm:
                reason = rm.group(1).strip()
                j += 1
                continue
            # blank or other nested bullets under this task
            if lines[j].strip() == "" or lines[j].startswith(" ") or lines[j].startswith("\t"):
                j += 1
                continue
            break
        ordinal += 1
        id_m = _ID_PREFIX_RE.match(text)
        task_id = id_m.group(1) if id_m else str(ordinal)
        tasks.append(
            SpecTask(
                id=task_id,
                text=text,
                done=done,
                assignee=assignee,
                reason=reason,
                line_index=task_line,
            )
        )
        i = j
    return tasks


def render_tasks_markdown(tasks: Iterable[SpecTask], *, title: str = "Tasks") -> str:
    """Render a simple tasks.md body from structured tasks."""
    lines = [f"# {title}", ""]
    for t in tasks:
        mark = "x" if t.done else " "
        lines.append(f"- [{mark}] {t.text}")
        lines.append(f"  - **assignee:** `{t.assignee}`")
        if t.reason:
            lines.append(f"  - **reason:** {t.reason}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def set_task_done(content: str, *, task_id: str | None = None, index: int | None = None, done: bool = True) -> str:
    """Toggle checkbox for a task by id or 1-based index."""
    tasks = parse_tasks_markdown(content)
    target = _resolve_task(tasks, task_id=task_id, index=index)
    lines = content.splitlines()
    li = target.line_index
    m = _TASK_LINE_RE.match(lines[li])
    if not m:
        raise ValueError(f"task line {li} is not a checklist item")
    mark = "x" if done else " "
    lines[li] = f"{m.group(1)}- [{mark}] {m.group(3)}"
    return "\n".join(lines) + ("\n" if content.endswith("\n") else "")


def set_task_assignee(
    content: str,
    *,
    assignee: str,
    task_id: str | None = None,
    index: int | None = None,
    reason: str | None = None,
) -> str:
    """Set or insert assignee (and optional reason) under a task."""
    tasks = parse_tasks_markdown(content)
    target = _resolve_task(tasks, task_id=task_id, index=index)
    lines = content.splitlines()
    li = target.line_index
    # Find end of this task's nested block
    end = li + 1
    while end < len(lines):
        if _TASK_LINE_RE.match(lines[end]) or lines[end].startswith("#"):
            break
        if lines[end].strip() and not (
            lines[end].startswith(" ") or lines[end].startswith("\t")
        ):
            break
        end += 1

    block = lines[li + 1 : end]
    new_block: list[str] = []
    wrote_assignee = False
    wrote_reason = reason is None  # if not updating reason, leave existing
    for bl in block:
        if _ASSIGNEE_RE.match(bl):
            new_block.append(f"  - **assignee:** `{assignee}`")
            wrote_assignee = True
            continue
        if reason is not None and _REASON_RE.match(bl):
            new_block.append(f"  - **reason:** {reason}")
            wrote_reason = True
            continue
        new_block.append(bl)

    if not wrote_assignee:
        new_block.insert(0, f"  - **assignee:** `{assignee}`")
    if reason is not None and not wrote_reason:
        # after assignee line
        insert_at = 0
        for i, bl in enumerate(new_block):
            if _ASSIGNEE_RE.match(bl):
                insert_at = i + 1
                break
        new_block.insert(insert_at, f"  - **reason:** {reason}")

    out = lines[: li + 1] + new_block + lines[end:]
    return "\n".join(out) + ("\n" if content.endswith("\n") else "")


def _resolve_task(
    tasks: list[SpecTask],
    *,
    task_id: str | None,
    index: int | None,
) -> SpecTask:
    if task_id is not None:
        tid = str(task_id).strip()
        for t in tasks:
            if t.id == tid:
                return t
        raise ValueError(f"task id not found: {tid!r}")
    if index is not None:
        # 1-based for agent UX
        i = int(index)
        if i < 1 or i > len(tasks):
            raise ValueError(f"task index out of range: {i} (1..{len(tasks)})")
        return tasks[i - 1]
    raise ValueError("provide task_id or index")


def assignees_summary(tasks: list[SpecTask]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for t in tasks:
        key = t.assignee or "unassigned"
        summary[key] = summary.get(key, 0) + 1
    return summary
