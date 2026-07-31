"""Parse and rewrite ``tasks.md`` checklists with assignees (OpenSpec Holix format)."""

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
_DEPENDS_RE = re.compile(
    r"^\s*-\s*\*\*(?:depends_on|depends|dependencies|зависит_от|зависимости):\*\*\s*(.*)$",
    re.IGNORECASE,
)
_SIZE_RE = re.compile(
    r"^\s*-\s*\*\*(?:size|volume|estimate|объ[её]м|размер):\*\*\s*`?([^`\n]+?)`?\s*$",
    re.IGNORECASE,
)
_ID_PREFIX_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+")

# Free-form section tasks (not OpenSpec checklist) — common LLM mistake
_SECTION_HEADING_RE = re.compile(
    r"^##\s+(\d+(?:\.\d+)*)\s*[.:)\-–—]?\s*(.+?)\s*$"
)
_FIELD_BULLET_RE = re.compile(
    r"^\s*-\s*\*\*("
    r"Описание|Description|Desc|"
    r"Исполнитель|Assignee|Owner|Agent|"
    r"Результат|Result|Deliverable|Outcome|"
    r"Причина|Reason|"
    r"Задача|Task"
    r"):\*\*\s*(.*)$",
    re.IGNORECASE,
)
_PLAIN_ASSIGNEE_RE = re.compile(
    r"^\s*-\s*(?:Исполнитель|Assignee|Owner)\s*:\s*`?([^`\n]+?)`?\s*$",
    re.IGNORECASE,
)

TASKS_FORMAT_EXAMPLE = """\
# Tasks: <change-id>

## 1. Implementation

- [ ] 1.1 Short task title (one deliverable)
  - **assignee:** `coder`
  - **size:** `s`
  - **reason:** why this agent
  - **depends_on:**

- [ ] 1.2 Another small task (runs after 1.1)
  - **assignee:** `coder`
  - **size:** `s`
  - **reason:** needs API from 1.1
  - **depends_on:** `1.1`

- [ ] 1.3 Parallel with 1.2 if both only need 1.1
  - **assignee:** `reviewer`
  - **size:** `xs`
  - **reason:** review contracts
  - **depends_on:** `1.1`
"""

_WRONG_FORMAT_HINTS = (
    (
        re.compile(r"\*\*(Описание|Description|Исполнитель|Assignee)\s*:\*\*", re.I),
        "free-form sections with **Описание**/**Исполнитель** (or Description/Assignee)",
    ),
    (
        re.compile(r"(?m)^##\s+\d+"),
        "numbered ## headings used as tasks without `- [ ]` checklist lines",
    ),
)


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
        size = ""
        depends_on: list[str] = []
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
            sm = _SIZE_RE.match(lines[j])
            if sm:
                size = sm.group(1).strip().strip("`").strip()
                j += 1
                continue
            dm = _DEPENDS_RE.match(lines[j])
            if dm:
                depends_on = parse_depends_on_value(dm.group(1))
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
                depends_on=depends_on,
                size=size,
                line_index=task_line,
            )
        )
        i = j
    return tasks


def parse_depends_on_value(raw: str | None) -> list[str]:
    """Parse ``1.1, 1.2`` / ``1.1 1.2`` / empty into ordered unique task ids."""
    text = (raw or "").strip().strip("`").strip()
    if not text or text in {"—", "-", "–", "none", "None", "нет", "n/a", "N/A"}:
        return []
    parts = re.split(r"[,;|/]+|\s+", text)
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        tid = part.strip().strip("`").strip()
        if not tid or tid in seen:
            continue
        seen.add(tid)
        out.append(tid)
    return out


def render_tasks_markdown(tasks: Iterable[SpecTask], *, title: str = "Tasks") -> str:
    """Render a simple tasks.md body from structured tasks."""
    lines = [f"# {title}", ""]
    for t in tasks:
        mark = "x" if t.done else " "
        text = t.text.strip()
        # Ensure leading id for stable Studio ids
        if not _ID_PREFIX_RE.match(text):
            text = f"{t.id} {text}".strip()
        lines.append(f"- [{mark}] {text}")
        lines.append(f"  - **assignee:** `{(t.assignee or 'unassigned').strip() or 'unassigned'}`")
        size = (t.size or "").strip()
        if size:
            lines.append(f"  - **size:** `{size}`")
        if t.reason:
            lines.append(f"  - **reason:** {t.reason}")
        deps = [d for d in (t.depends_on or []) if str(d).strip()]
        if deps:
            lines.append(f"  - **depends_on:** `{', '.join(deps)}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def detect_wrong_tasks_format(content: str) -> list[str]:
    """Human-readable hints when content is not OpenSpec checklist format."""
    hints: list[str] = []
    for pattern, label in _WRONG_FORMAT_HINTS:
        if pattern.search(content or ""):
            hints.append(label)
    return hints


def validate_tasks_markdown(content: str) -> list[str]:
    """Return validation errors for OpenSpec Holix tasks.md (empty = ok)."""
    text = content or ""
    tasks = parse_tasks_markdown(text)
    errors: list[str] = []
    if not tasks:
        errors.append(
            "No OpenSpec checklist tasks found. Each task MUST be a checkbox line "
            "like `- [ ] 1.1 Description` with nested `  - **assignee:** `type``."
        )
        for hint in detect_wrong_tasks_format(text):
            errors.append(f"Detected non-standard layout: {hint}.")
        errors.append("Required format example:\n" + TASKS_FORMAT_EXAMPLE.strip())
        return errors

    missing_assignee_line = 0
    for t in tasks:
        # Formal or loose assignee line is enough; default unassigned is allowed for mode=self
        # but every checklist item should still be a real `- [ ]` task (already true).
        if not (t.assignee or "").strip():
            missing_assignee_line += 1
    if missing_assignee_line:
        errors.append(
            f"{missing_assignee_line} task(s) have empty assignee; "
            "use `main`, a subagent type, or `unassigned`."
        )
    return errors


def normalize_tasks_markdown(content: str, *, title: str | None = None) -> tuple[str, list[str]]:
    """Coerce common non-OpenSpec layouts into checklist + **assignee:** format.

    Returns ``(markdown, notes)``. If content already parses as checklist tasks,
    re-renders a clean canonical form (stable ids + formal assignee lines).
    """
    text = content or ""
    notes: list[str] = []
    existing = parse_tasks_markdown(text)
    if existing:
        # Canonicalize already-valid checklists (formal assignee lines, ids).
        # Prefer in-place formalization of assignees when structure is already checklist.
        cleaned = _canonicalize_checklist(text)
        if cleaned != text:
            notes.append("Normalized checklist assignee lines to OpenSpec form")
        return cleaned, notes

    converted = _convert_section_tasks(text)
    if converted is not None:
        notes.append(
            "Converted free-form ## section tasks "
            "(Описание/Исполнитель or Description/Assignee) into OpenSpec checklist"
        )
        return converted, notes

    return text, notes


def ensure_tasks_openspec_format(
    content: str,
    *,
    title: str | None = None,
    strict_size: bool = True,
) -> tuple[str, list[str]]:
    """Normalize when possible, then validate. Raises ValueError if still invalid.

    Already-valid checklists keep phase headings (``## 1. …``); free-form layouts
    are converted into a clean checklist body.

    When *strict_size* is true, sub-agent tasks estimated as L/XL are rejected so
    propose must decompose them into smaller checklist items.
    """
    normalized, notes = normalize_tasks_markdown(content, title=title)
    # Ensure each task has an explicit **size:** line (estimated when missing).
    sized, size_notes = ensure_task_sizes(normalized)
    if size_notes:
        notes.extend(size_notes)
        normalized = sized
    errors = validate_tasks_markdown(normalized)
    if strict_size:
        from core.sdd.task_sizing import validate_task_sizes

        errors.extend(validate_task_sizes(parse_tasks_markdown(normalized)))
    if errors:
        raise ValueError(
            "Invalid tasks.md (OpenSpec Holix format required):\n- "
            + "\n- ".join(errors)
        )
    if not normalized.endswith("\n"):
        normalized += "\n"
    return normalized, notes


def ensure_task_sizes(content: str) -> tuple[str, list[str]]:
    """Insert or normalize ``**size:**`` for every checklist task.

    Missing sizes are estimated heuristically and written into the markdown so
    Studio/dispatch can budget max_steps per job.
    """
    from core.sdd.task_sizing import estimate_task_size, normalize_size

    lines = (content or "").splitlines()
    tasks = parse_tasks_markdown(content)
    if not tasks:
        return content, []

    notes: list[str] = []
    # Work bottom-up so line indices stay valid.
    for t in reversed(tasks):
        li = t.line_index
        if li < 0 or li >= len(lines):
            continue
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
        estimated = estimate_task_size(
            t.text, reason=t.reason or "", declared=t.size or None
        )
        size_label = normalize_size(t.size) or estimated
        new_block: list[str] = []
        wrote_size = False
        for bl in block:
            if _SIZE_RE.match(bl):
                if not wrote_size:
                    new_block.append(f"  - **size:** `{size_label}`")
                    wrote_size = True
                continue
            new_block.append(bl)
        if not wrote_size:
            insert_at = 0
            for i, bl in enumerate(new_block):
                if _ASSIGNEE_RE.match(bl) or _ASSIGNEE_LOOSE_RE.match(bl):
                    insert_at = i + 1
                    break
            new_block.insert(insert_at, f"  - **size:** `{size_label}`")
            notes.append(f"Task {t.id}: added size={size_label}")
        elif normalize_size(t.size) != size_label and not normalize_size(t.size):
            notes.append(f"Task {t.id}: size={size_label}")
        lines = lines[: li + 1] + new_block + lines[end:]

    out = "\n".join(lines)
    if content.endswith("\n") and not out.endswith("\n"):
        out += "\n"
    return out, notes


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
        if _ASSIGNEE_RE.match(bl) or _ASSIGNEE_LOOSE_RE.match(bl):
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


def _extract_title(content: str) -> str | None:
    for line in (content or "").splitlines():
        s = line.strip()
        if s.startswith("# ") and not s.startswith("##"):
            return s[2:].strip()
    return None


def _canonicalize_checklist(content: str) -> str:
    """Ensure each checklist task has formal **assignee:** (and keep other nested lines)."""
    lines = content.splitlines()
    tasks = parse_tasks_markdown(content)
    if not tasks:
        return content

    # Work from bottom so line indices stay valid
    for t in reversed(tasks):
        li = t.line_index
        if li < 0 or li >= len(lines):
            continue
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
        wrote_reason = False
        wrote_depends = False
        wrote_size = False
        size_val = (t.size or "").strip()
        for bl in block:
            if _ASSIGNEE_RE.match(bl) or _ASSIGNEE_LOOSE_RE.match(bl):
                if not wrote_assignee:
                    new_block.append(
                        f"  - **assignee:** `{(t.assignee or 'unassigned').strip() or 'unassigned'}`"
                    )
                    wrote_assignee = True
                continue
            if _SIZE_RE.match(bl):
                if size_val and not wrote_size:
                    new_block.append(f"  - **size:** `{size_val}`")
                    wrote_size = True
                elif not size_val:
                    continue
                else:
                    new_block.append(bl)
                    wrote_size = True
                continue
            if _REASON_RE.match(bl):
                if t.reason and not wrote_reason:
                    new_block.append(f"  - **reason:** {t.reason}")
                    wrote_reason = True
                elif not t.reason:
                    continue
                else:
                    new_block.append(bl)
                    wrote_reason = True
                continue
            if _DEPENDS_RE.match(bl):
                deps = [d for d in (t.depends_on or []) if str(d).strip()]
                if deps and not wrote_depends:
                    new_block.append(f"  - **depends_on:** `{', '.join(deps)}`")
                    wrote_depends = True
                elif not deps:
                    continue
                else:
                    new_block.append(bl)
                    wrote_depends = True
                continue
            new_block.append(bl)
        if not wrote_assignee:
            new_block.insert(
                0,
                f"  - **assignee:** `{(t.assignee or 'unassigned').strip() or 'unassigned'}`",
            )
        if size_val and not wrote_size:
            insert_at = 0
            for i, bl in enumerate(new_block):
                if _ASSIGNEE_RE.match(bl):
                    insert_at = i + 1
                    break
            new_block.insert(insert_at, f"  - **size:** `{size_val}`")
        if t.reason and not wrote_reason:
            insert_at = 0
            for i, bl in enumerate(new_block):
                if _ASSIGNEE_RE.match(bl) or _SIZE_RE.match(bl):
                    insert_at = i + 1
                    break
            new_block.insert(insert_at, f"  - **reason:** {t.reason}")
        deps = [d for d in (t.depends_on or []) if str(d).strip()]
        if deps and not wrote_depends:
            insert_at = 0
            for i, bl in enumerate(new_block):
                if _ASSIGNEE_RE.match(bl) or _SIZE_RE.match(bl) or _REASON_RE.match(bl):
                    insert_at = i + 1
            new_block.insert(insert_at, f"  - **depends_on:** `{', '.join(deps)}`")
        # Ensure task text has id prefix
        m = _TASK_LINE_RE.match(lines[li])
        if m:
            mark = m.group(2)
            body = m.group(3).strip()
            if not _ID_PREFIX_RE.match(body):
                body = f"{t.id} {body}".strip()
            lines[li] = f"{m.group(1)}- [{mark}] {body}"
        lines = lines[: li + 1] + new_block + lines[end:]

    out = "\n".join(lines)
    if content.endswith("\n") and not out.endswith("\n"):
        out += "\n"
    return out


def _convert_section_tasks(content: str) -> str | None:
    """Convert ## N. Title + field bullets into OpenSpec checklist. None if not applicable."""
    lines = (content or "").splitlines()
    if not any(_SECTION_HEADING_RE.match(ln) for ln in lines):
        return None
    # Only convert when there are no real checklist tasks
    if parse_tasks_markdown(content):
        return None

    title = _extract_title(content) or "Tasks"
    tasks: list[SpecTask] = []
    i = 0
    while i < len(lines):
        hm = _SECTION_HEADING_RE.match(lines[i])
        if not hm:
            i += 1
            continue
        task_id = hm.group(1).strip()
        heading_title = hm.group(2).strip()
        description = ""
        assignee = "unassigned"
        reason = ""
        result = ""
        i += 1
        while i < len(lines):
            if _SECTION_HEADING_RE.match(lines[i]) or (
                lines[i].startswith("#") and not lines[i].startswith("##")
            ):
                break
            if lines[i].startswith("## "):
                # other ## heading without number — stop this task
                if not _SECTION_HEADING_RE.match(lines[i]):
                    break
            fm = _FIELD_BULLET_RE.match(lines[i])
            if fm:
                key = fm.group(1).lower()
                val = (fm.group(2) or "").strip()
                if key in ("описание", "description", "desc", "задача", "task"):
                    description = val
                elif key in ("исполнитель", "assignee", "owner", "agent"):
                    assignee = val.strip("`").strip() or "unassigned"
                elif key in ("результат", "result", "deliverable", "outcome"):
                    result = val
                elif key in ("причина", "reason"):
                    reason = val
                i += 1
                continue
            pm = _PLAIN_ASSIGNEE_RE.match(lines[i])
            if pm:
                assignee = pm.group(1).strip("`").strip() or "unassigned"
                i += 1
                continue
            # skip empty lines inside section
            if not lines[i].strip():
                i += 1
                continue
            # unknown bullet — stop nested scan for this section
            if lines[i].lstrip().startswith("-"):
                i += 1
                continue
            break

        # Prefer dotted ids (1.1) when section is a bare integer — matches OpenSpec style
        display_id = task_id if "." in task_id else f"{task_id}.1"
        text_parts = [heading_title]
        if description and description not in heading_title:
            text_parts.append(description)
        body = " — ".join(p for p in text_parts if p)
        if result:
            reason = (reason + "; " if reason else "") + f"result: {result}"
        if not _ID_PREFIX_RE.match(body):
            body = f"{display_id} {body}".strip()
        tasks.append(
            SpecTask(
                id=display_id,
                text=body,
                done=False,
                assignee=assignee or "unassigned",
                reason=reason.strip(" ;"),
            )
        )

    if not tasks:
        return None
    return render_tasks_markdown(tasks, title=title)
