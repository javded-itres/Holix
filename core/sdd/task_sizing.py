"""Estimate SDD task volume and map size → sub-agent step budget.

Goal: keep each sub-agent job small (few files / one deliverable) so runs finish
in fewer reasoning steps instead of burning 150–240 steps on a mega-task.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from core.sdd.models import SpecTask

TaskSize = Literal["xs", "s", "m", "l", "xl"]

# Soft budgets for SDD-dispatched sub-agents (extensions may still apply).
_MAX_STEPS_BY_SIZE: dict[TaskSize, int] = {
    "xs": 40,
    "s": 60,
    "m": 90,
    "l": 120,
    "xl": 150,
}

_SIZE_ORDER: dict[TaskSize, int] = {"xs": 0, "s": 1, "m": 2, "l": 3, "xl": 4}

_SIZE_ALIASES: dict[str, TaskSize] = {
    "xs": "xs",
    "x-small": "xs",
    "xsmall": "xs",
    "tiny": "xs",
    "s": "s",
    "small": "s",
    "m": "m",
    "med": "m",
    "medium": "m",
    "l": "l",
    "large": "l",
    "xl": "xl",
    "x-large": "xl",
    "xlarge": "xl",
    "huge": "xl",
    "epic": "xl",
}

# Multi-area / epic phrasing → push size up.
_EPIC_RE = re.compile(
    r"(?i)\b("
    r"entire|whole|full\s+stack|end[- ]to[- ]end|e2e|"
    r"all\s+(modules|services|pages|endpoints|components)|"
    r"complete\s+(feature|module|app|system)|"
    r"весь|вся|все\s+(модули|сервисы|страницы|эндпоинты)|"
    r"целиком|полностью|полноценн\w*|"
    r"frontend\s*\+\s*backend|backend\s*\+\s*frontend|"
    r"фронт\w*\s+и\s+бэк\w*|бэк\w*\s+и\s+фронт\w*"
    r")\b"
)

_MULTI_AND_RE = re.compile(
    r"(?i)\b("
    r"and\s+(also\s+)?(add|create|implement|build|wire|fix|update|write|test)|"
    r"и\s+(также\s+)?(добавить|создать|реализовать|сделать|написать|обновить|починить|протестировать)"
    r")\b"
)

_MULTI_SCOPE_RE = re.compile(
    r"(?i)("
    r"\bapi\b.*\b(ui|frontend|page|component)\b|"
    r"\b(ui|frontend|page|component)\b.*\bapi\b|"
    r"\bdb\b.*\b(api|ui)\b|"
    r"\b(api|ui)\b.*\bdb\b|"
    r"миграци\w*.*эндпоинт|эндпоинт\w*.*миграци|"
    r"тест\w*.*и\s+документац|docs?\s+and\s+tests"
    r")"
)

_MANY_FILES_RE = re.compile(
    r"(?i)\b("
    r"\d+\+?\s*files?|"
    r"many\s+files|multiple\s+files|across\s+the\s+codebase|"
    r"несколько\s+файл|много\s+файл|по\s+всему\s+проекту|весь\s+модуль"
    r")\b"
)

_SMALL_HINT_RE = re.compile(
    r"(?i)\b("
    r"single\s+file|one\s+file|one\s+function|one\s+endpoint|"
    r"unit\s+test|stub|skeleton|scaffold\s+only|"
    r"один\s+файл|одна\s+функци|один\s+эндпоинт|заглушк\w*"
    r")\b"
)

_ID_PREFIX_RE = re.compile(r"^\d+(?:\.\d+)*\s+")


def normalize_size(raw: str | None) -> TaskSize | None:
    """Parse a declared size label; None if empty/unknown."""
    text = (raw or "").strip().lower().strip("`").strip()
    if not text:
        return None
    return _SIZE_ALIASES.get(text)


def strip_task_id(text: str) -> str:
    body = (text or "").strip()
    return _ID_PREFIX_RE.sub("", body).strip()


def estimate_task_size(
    text: str,
    *,
    reason: str = "",
    declared: str | None = None,
) -> TaskSize:
    """Heuristic size from task title/body (+ optional declared label).

    Declared size is respected when present; otherwise estimate from wording.
    """
    declared_size = normalize_size(declared)
    body = strip_task_id(text)
    blob = f"{body} {reason or ''}".strip()
    length = len(body)

    if declared_size:
        # Still bump declared S/M up when wording is clearly epic.
        if declared_size in ("xs", "s", "m") and (
            _EPIC_RE.search(blob) or length > 180
        ):
            return "l" if declared_size != "m" or length > 220 else "m"
        return declared_size

    score = 0
    if length <= 40:
        score += 0
    elif length <= 80:
        score += 1
    elif length <= 140:
        score += 2
    elif length <= 220:
        score += 3
    else:
        score += 4

    if _SMALL_HINT_RE.search(blob):
        score = max(0, score - 2)
    if _MULTI_AND_RE.search(blob):
        score += 1
    if _MULTI_SCOPE_RE.search(blob):
        score += 2
    if _MANY_FILES_RE.search(blob):
        score += 2
    if _EPIC_RE.search(blob):
        score += 3
    # Count commas / "и" / "and" as multi-deliverable signal.
    joiner_hits = len(re.findall(r"(?i)\b(?:and|и|plus|\+)\b", body))
    if joiner_hits >= 2:
        score += 1
    if joiner_hits >= 4:
        score += 1

    if score <= 0:
        return "xs"
    if score == 1:
        return "s"
    if score == 2:
        return "m"
    if score == 3:
        return "l"
    return "xl"


def resolve_task_size(task: SpecTask | dict[str, Any]) -> TaskSize:
    if isinstance(task, SpecTask):
        return estimate_task_size(
            task.text,
            reason=task.reason or "",
            declared=task.size,
        )
    return estimate_task_size(
        str(task.get("text") or ""),
        reason=str(task.get("reason") or ""),
        declared=str(task.get("size") or "") or None,
    )


def max_steps_for_size(size: TaskSize | str | None) -> int:
    key = normalize_size(str(size) if size else "") or "m"
    return int(_MAX_STEPS_BY_SIZE.get(key, 90))


def size_rank(size: TaskSize | str | None) -> int:
    key = normalize_size(str(size) if size else "") or "m"
    return int(_SIZE_ORDER.get(key, 2))


def assess_tasks(tasks: list[SpecTask]) -> list[dict[str, Any]]:
    """Per-task size assessment for UI / write_artifact feedback."""
    out: list[dict[str, Any]] = []
    for t in tasks:
        size = resolve_task_size(t)
        out.append(
            {
                "id": t.id,
                "text": strip_task_id(t.text)[:160],
                "assignee": t.assignee,
                "declared_size": normalize_size(t.size),
                "size": size,
                "max_steps": max_steps_for_size(size),
                "needs_split": size_rank(size) >= size_rank("l")
                and (t.assignee or "").strip().lower()
                not in ("main", "unassigned", ""),
            }
        )
    return out


def validate_task_sizes(
    tasks: list[SpecTask],
    *,
    strict_subagents: bool = True,
) -> list[str]:
    """Return errors when subagent tasks are too large and must be split.

    ``main`` / ``unassigned`` tasks may stay larger (main agent coordinates).
    """
    errors: list[str] = []
    if not tasks:
        return errors

    assessed = assess_tasks(tasks)
    oversized = [a for a in assessed if a["needs_split"]]
    if not oversized:
        # Still flag epic single-task plans even for main (weak signal).
        if len(tasks) == 1 and size_rank(assessed[0]["size"]) >= size_rank("xl"):
            errors.append(
                "Single task is XL (epic). Decompose into multiple small checklist "
                "items (XS/S), each one deliverable / few files, with depends_on."
            )
        return errors

    if not strict_subagents:
        return errors

    for a in oversized:
        errors.append(
            f"Task {a['id']} is too large for a sub-agent (size={a['size']}, "
            f"assignee={a['assignee']!r}): {a['text']!r}. "
            "Split into XS/S tasks (one module/file/endpoint each), set "
            "`**size:** \\`s\\`` / `xs`, and wire `depends_on` for order."
        )

    errors.append(
        "Decomposition rules: one sub-agent task = one deliverable "
        "(e.g. one endpoint OR one UI screen OR one test file — not all three). "
        "Prefer 5–15 small tasks over 1–3 large ones so each job uses fewer steps."
    )
    return errors


def size_summary(tasks: list[SpecTask]) -> dict[str, Any]:
    assessed = assess_tasks(tasks)
    counts: dict[str, int] = {}
    for a in assessed:
        counts[a["size"]] = counts.get(a["size"], 0) + 1
    needs_split = [a for a in assessed if a["needs_split"]]
    return {
        "counts": counts,
        "tasks": assessed,
        "needs_split": needs_split,
        "ok": not needs_split,
    }


DECOMPOSITION_GUIDE = """\
# Task sizing (required for subagents)

Each checklist item for a **sub-agent** must be **small**:

| size | Meaning | Typical max_steps |
|------|---------|-------------------|
| xs   | One file / one function / stub | 40 |
| s    | One slice: 1–3 files, one deliverable | 60 |
| m    | One module feature (still focused) | 90 |
| l/xl | **Too big** — split before apply | — |

Rules:
- Prefer **XS/S**. Avoid packing API + UI + tests + docs into one task.
- Use `depends_on` so waves stay parallel where possible (e.g. 1.1 API, 1.2 tests after 1.1).
- Write nested `  - **size:** \\`s\\`` on every task (or let Holix estimate; still split if L/XL).
- Bad: "Implement full OAuth (backend, frontend, tests, docs)"
- Good: 1.1 endpoints, 1.2 session store, 1.3 login UI, 1.4 unit tests, 1.5 docs
"""
