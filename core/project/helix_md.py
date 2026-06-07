"""Load and inject `.helix/HELIX.md` project knowledge into agent prompts."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from core.config_utils import get_local_helix_dir

HELIX_MD_FILENAME = "HELIX.md"
HELIX_MD_REL_PATH = f".helix/{HELIX_MD_FILENAME}"
DEFAULT_MAX_CHARS = 24_000

TASK_CONTEXT_NOTE = (
    "When `.helix/HELIX.md` exists in the working directory, treat it as the primary "
    "source of truth about this codebase. Read it (or refresh with `read_file`) before "
    "exploring blindly. Prefer facts from HELIX.md over assumptions."
)

PLANNING_CONTEXT_NOTE = (
    "Before planning, check whether `.helix/HELIX.md` exists. If it does, base architecture, "
    "module boundaries, REST/API layout, and conventions on that document. Cite specific "
    "sections when reasoning about the plan."
)


def get_helix_md_path(cwd: Optional[str | Path] = None) -> Path:
    return get_local_helix_dir(cwd) / HELIX_MD_FILENAME


def ensure_helix_dir(cwd: Optional[str | Path] = None) -> Path:
    d = get_local_helix_dir(cwd)
    d.mkdir(parents=True, exist_ok=True)
    return d


def helix_md_exists(cwd: Optional[str | Path] = None) -> bool:
    return get_helix_md_path(cwd).is_file()


def load_helix_md(
    cwd: Optional[str | Path] = None,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str | None:
    """Return HELIX.md text if present, optionally truncated."""
    path = get_helix_md_path(cwd)
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not text:
        return None
    if len(text) > max_chars:
        text = (
            text[:max_chars]
            + f"\n\n… [truncated for context; full file: {HELIX_MD_REL_PATH}]"
        )
    return text


def task_context_note() -> str:
    return TASK_CONTEXT_NOTE


def planning_context_note() -> str:
    return PLANNING_CONTEXT_NOTE


def format_helix_md_block(cwd: Optional[str | Path] = None) -> str:
    """Markdown block with file contents for system prompts, or empty string."""
    body = load_helix_md(cwd)
    if not body:
        return ""
    return (
        f"## Project knowledge ({HELIX_MD_REL_PATH})\n"
        f"{TASK_CONTEXT_NOTE}\n\n"
        f"{body}"
    )


def append_helix_project_context(prompt: str, cwd: Optional[str | Path] = None) -> str:
    """Append HELIX.md block to a system prompt when the file exists."""
    block = format_helix_md_block(cwd)
    if not block:
        return prompt
    return f"{prompt.rstrip()}\n\n{block}\n"