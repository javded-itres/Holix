"""Apply execution mode: self | subagents | hybrid."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from core.sdd.paths import apply_mode_path

ApplyMode = Literal["self", "subagents", "hybrid"]
APPLY_MODES: tuple[str, ...] = ("self", "subagents", "hybrid")

_MODE_PROMPTS = {
    "self": "Main agent executes all tasks (assignees are hints only).",
    "subagents": "Dispatch non-main tasks to subagents by assignee; main keeps main-assigned tasks.",
    "hybrid": "Strictly follow each task assignee (main + subagents).",
}


def normalize_apply_mode(mode: str) -> ApplyMode:
    m = (mode or "").strip().lower()
    if m not in APPLY_MODES:
        raise ValueError(f"apply mode must be one of {APPLY_MODES}, got {mode!r}")
    return m  # type: ignore[return-value]


def load_apply_mode(workspace: Path, change_id: str) -> ApplyMode | None:
    path = apply_mode_path(workspace, change_id)
    if not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8").strip().lower()
    if raw not in APPLY_MODES:
        return None
    return raw  # type: ignore[return-value]


def save_apply_mode(workspace: Path, change_id: str, mode: str) -> ApplyMode:
    normalized = normalize_apply_mode(mode)
    path = apply_mode_path(workspace, change_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(normalized + "\n", encoding="utf-8")
    return normalized


def clear_apply_mode(workspace: Path, change_id: str) -> None:
    path = apply_mode_path(workspace, change_id)
    if path.is_file():
        path.unlink()


def apply_mode_prompt_text(change_id: str, *, assignees: dict[str, int] | None = None) -> str:
    """Human-facing pre-apply question (for chat / ask_user / UI)."""
    lines = [
        f"Change `{change_id}` is ready to apply.",
        "How should tasks be executed?",
        "",
        "1. **self** — main agent does all tasks",
        "2. **subagents** — dispatch by assignee (main keeps `main` tasks)",
        "3. **hybrid** — strictly follow each task's assignee",
        "",
        "Reply with: self | subagents | hybrid",
        "Then call `sdd_set_apply_mode` with that value before coding.",
    ]
    if assignees:
        parts = ", ".join(f"{k}: {v}" for k, v in sorted(assignees.items()))
        lines.insert(1, f"Assignees: {parts}")
    return "\n".join(lines)


def describe_mode(mode: str) -> str:
    return _MODE_PROMPTS.get(normalize_apply_mode(mode), mode)
