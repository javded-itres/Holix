"""Load and inject `.holix/HOLIX.md` project knowledge into agent prompts."""

from __future__ import annotations

from pathlib import Path

from core.config_utils import get_local_holix_dir

HOLIX_MD_FILENAME = "HOLIX.md"
HOLIX_MD_LEGACY_FILENAME = "HELIX.md"
HOLIX_MD_REL_PATH = f".holix/{HOLIX_MD_FILENAME}"
DEFAULT_MAX_CHARS = 24_000

TASK_CONTEXT_NOTE = (
    "When `.holix/HOLIX.md` exists in the working directory, treat it as the primary "
    "source of truth about this codebase. Read it (or refresh with `read_file`) before "
    "exploring blindly. Prefer facts from HOLIX.md over assumptions."
)

PLANNING_CONTEXT_NOTE = (
    "Before planning, check whether `.holix/HOLIX.md` exists. If it does, base architecture, "
    "module boundaries, REST/API layout, and conventions on that document. Cite specific "
    "sections when reasoning about the plan. Also check `.holix/plans/` for previously "
    "approved plans (JSON + Markdown) and reuse or extend them when the task matches."
)


def get_holix_md_path(cwd: str | Path | None = None) -> Path:
    base = get_local_holix_dir(cwd)
    holix_md = base / HOLIX_MD_FILENAME
    if holix_md.is_file():
        return holix_md
    legacy = base / HOLIX_MD_LEGACY_FILENAME
    return legacy if legacy.is_file() else holix_md


def ensure_holix_dir(cwd: str | Path | None = None) -> Path:
    d = get_local_holix_dir(cwd)
    d.mkdir(parents=True, exist_ok=True)
    return d


def holix_md_exists(cwd: str | Path | None = None) -> bool:
    return get_holix_md_path(cwd).is_file()


def load_holix_md(
    cwd: str | Path | None = None,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str | None:
    """Return HOLIX.md text if present, optionally truncated."""
    path = get_holix_md_path(cwd)
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
            + f"\n\n… [truncated for context; full file: {HOLIX_MD_REL_PATH}]"
        )
    return text


def task_context_note() -> str:
    return TASK_CONTEXT_NOTE


def planning_context_note() -> str:
    return PLANNING_CONTEXT_NOTE


def format_holix_md_block(cwd: str | Path | None = None) -> str:
    """Markdown block with file contents for system prompts, or empty string."""
    body = load_holix_md(cwd)
    if not body:
        return ""
    return (
        f"## Project knowledge ({HOLIX_MD_REL_PATH})\n"
        f"{TASK_CONTEXT_NOTE}\n\n"
        f"{body}"
    )


def append_holix_project_context(prompt: str, cwd: str | Path | None = None) -> str:
    """Append HOLIX.md block to a system prompt when the file exists."""
    block = format_holix_md_block(cwd)
    if not block:
        return prompt
    return f"{prompt.rstrip()}\n\n{block}\n"