"""Load and inject `.holix/HOLIX.md` project knowledge into agent prompts."""

from __future__ import annotations

import logging
from pathlib import Path

from core.config_utils import get_local_holix_dir

logger = logging.getLogger(__name__)

HOLIX_MD_FILENAME = "HOLIX.md"
HOLIX_MD_LEGACY_FILENAME = "HELIX.md"
HOLIX_MD_REL_PATH = f".holix/{HOLIX_MD_FILENAME}"
DEFAULT_MAX_CHARS = 24_000
# Studio product projects live at projects/<slug>/<repo> (3 levels from workspace).
HOLIX_MD_SEARCH_DEPTH = 4
_SKIP_SEARCH_DIRS = frozenset(
    {
        ".git",
        ".holix",
        ".helix",
        ".hg",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        # macOS home / volume poison — scandir here blocks the Telegram loop
        "Library",
        "Applications",
        "System",
        "Volumes",
        "Network",
        "Movies",
        "Pictures",
        "Music",
        "CloudStorage",
    }
)

_MINIMAL_HOLIX_TEMPLATE = """# Project handbook

This file (`.holix/HOLIX.md`) is the primary source of truth about this codebase.
Holix loads it on every agent turn. If it was missing, it was created automatically.

When present at the repository root, also follow:
- `AGENTS.md`
- `CLAUDE.md`
- `rules.md` / `RULES.md`

## Overview

## Stack

## Commands
"""

TASK_CONTEXT_NOTE = (
    "`.holix/HOLIX.md` is the primary source of truth about this codebase "
    "(working directory or nested folders up to four levels). Prefer facts from "
    "HOLIX.md over assumptions. If the file is missing, Holix creates a skeleton "
    "at start. Standard agent files are loaded automatically when present: "
    "`AGENTS.md`, `CLAUDE.md`, `rules.md` / `RULES.md`."
)

PLANNING_CONTEXT_NOTE = (
    "Before planning, load `.holix/HOLIX.md` (working directory or nested folders up "
    "to four levels) and **read-only** any existing `openspec/specs/` requirements. "
    "Also follow `AGENTS.md`, `CLAUDE.md`, and `rules.md` / `RULES.md` when present. "
    "Base architecture, modules, APIs, and conventions on the handbook; ground product "
    "work in specs **when they already exist**. "
    "If HOLIX.md is missing, the planner may run `/init` pre-scan only (writes "
    "`.holix/HOLIX.md` skeleton) — that is the **only** project bootstrap allowed in "
    "plan mode. "
    "**Do not** call `sdd_init`, `sdd_apply`, `sdd_propose`, `sdd_write_artifact`, "
    "`sdd_dispatch`, or `sdd_archive` during plan generation. Plan mode does not start "
    "SDD workflows or auto-execute Specs changes. "
    "Also check `.holix/plans/` for previously approved plans and reuse or extend them "
    "when the task matches."
)


def _workspace_root(cwd: str | Path | None = None) -> Path:
    return (Path(cwd) if cwd else Path.cwd()).expanduser().resolve()


def _is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def _is_dot_holix_handbook(path: Path) -> bool:
    return path.name in {HOLIX_MD_FILENAME, HOLIX_MD_LEGACY_FILENAME} and path.parent.name in {
        ".holix",
        ".helix",
    }


def _holix_md_file_in_dir(base: Path) -> Path | None:
    try:
        holix_dir = get_local_holix_dir(base)
        holix_md = holix_dir / HOLIX_MD_FILENAME
        if _is_file(holix_md):
            return holix_md
        legacy = holix_dir / HOLIX_MD_LEGACY_FILENAME
        if _is_file(legacy):
            return legacy
        # Legacy Studio / hand-authored handbook at the repo root.
        root_md = base / HOLIX_MD_FILENAME
        if _is_file(root_md):
            return root_md
    except OSError:
        return None
    return None


def discover_holix_md_paths(
    cwd: str | Path | None = None,
    *,
    max_depth: int = HOLIX_MD_SEARCH_DEPTH,
) -> list[Path]:
    """Return existing HOLIX.md paths under *cwd*, shallowest directories first."""
    root = _workspace_root(cwd)
    depth_limit = max(0, int(max_depth))
    found: list[tuple[int, str, Path]] = []

    def consider(directory: Path, depth: int) -> None:
        try:
            hit = _holix_md_file_in_dir(directory)
            if hit is not None:
                rel = str(directory.relative_to(root)).replace("\\", "/")
                found.append((depth, rel, hit))
        except OSError:
            # Unreadable dirs (docker volumes, root-owned mounts) must not abort the agent.
            return

    consider(root, 0)
    if depth_limit == 0:
        return [path for _, _, path in sorted(found)]

    queue: list[tuple[Path, int]] = [(root, 0)]
    while queue:
        current, depth = queue.pop(0)
        if depth >= depth_limit:
            continue
        try:
            children = sorted(current.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            continue
        for child in children:
            if not _is_dir(child):
                continue
            name = child.name
            if name in _SKIP_SEARCH_DIRS or name.startswith("."):
                continue
            next_depth = depth + 1
            consider(child, next_depth)
            if next_depth < depth_limit:
                queue.append((child, next_depth))

    found.sort(key=lambda item: (item[0], item[1]))
    return [path for _, _, path in found]


def resolve_holix_md_read_path(cwd: str | Path | None = None) -> Path | None:
    """Best HOLIX.md for reading: cwd root first, then nested (up to two levels)."""
    hits = discover_holix_md_paths(cwd)
    return hits[0] if hits else None


def holix_md_relative_path(path: Path, cwd: str | Path | None = None) -> str:
    root = _workspace_root(cwd)
    try:
        return str(path.resolve().relative_to(root)).replace("\\", "/")
    except ValueError:
        return HOLIX_MD_REL_PATH


def get_holix_md_path(cwd: str | Path | None = None) -> Path:
    """Canonical HOLIX.md path at *cwd* (write target for `/init`)."""
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
    return resolve_holix_md_read_path(cwd) is not None


def load_holix_md(
    cwd: str | Path | None = None,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str | None:
    """Return HOLIX.md text if present, optionally truncated."""
    path = resolve_holix_md_read_path(cwd)
    if path is None:
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not text:
        return None
    rel_path = holix_md_relative_path(path, cwd)
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n… [truncated for context; full file: {rel_path}]"
    return text


def task_context_note() -> str:
    return TASK_CONTEXT_NOTE


def planning_context_note() -> str:
    return PLANNING_CONTEXT_NOTE


def format_holix_md_block(cwd: str | Path | None = None) -> str:
    """Markdown block with file contents for system prompts, or empty string."""
    path = resolve_holix_md_read_path(cwd)
    body = load_holix_md(cwd)
    if not body or path is None:
        return ""
    rel_path = holix_md_relative_path(path, cwd)
    return f"## Project knowledge ({rel_path})\n{TASK_CONTEXT_NOTE}\n\n{body}"


def _migrate_root_handbook(path: Path) -> Path:
    """Copy a repo-root HOLIX.md into ``.holix/HOLIX.md`` (canonical location)."""
    dest = path.parent / ".holix" / HOLIX_MD_FILENAME
    if _is_file(dest):
        return dest
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        logger.info("migrated root HOLIX.md → %s", dest)
    except OSError:
        logger.warning("could not migrate root HOLIX.md to %s", dest, exc_info=True)
        return path
    return dest if _is_file(dest) else path


def _write_init_skeleton_at(cwd: Path, *, locale: str = "en") -> Path | None:
    from core.project.init_scan import scan_project_for_init, write_init_skeleton

    try:
        from core.i18n.messages import t

        loc = locale if locale in ("en", "ru") else "en"
        template = t("init.holix_template", loc)
    except Exception:
        loc = "en"
        template = _MINIMAL_HOLIX_TEMPLATE
    try:
        scan = scan_project_for_init(cwd=cwd)
        return write_init_skeleton(
            scan,
            holix_rel_path=HOLIX_MD_REL_PATH,
            template=template,
            locale=loc,
        )
    except Exception:
        logger.warning("HOLIX.md /init skeleton failed under %s", cwd, exc_info=True)
        return None


def ensure_holix_md_exists(
    cwd: str | Path | None = None,
    *,
    locale: str = "en",
) -> Path | None:
    """Return handbook path, creating ``.holix/HOLIX.md`` when none exists.

    Migrates a legacy repo-root ``HOLIX.md`` into ``.holix/`` instead of writing
    an empty skeleton over it.
    """
    existing = resolve_holix_md_read_path(cwd)
    if existing is not None:
        if not _is_dot_holix_handbook(existing):
            return _migrate_root_handbook(existing)
        return existing

    root = _workspace_root(cwd)
    written = _write_init_skeleton_at(root, locale=locale)
    if written is not None and _is_file(written):
        return written
    dest = get_holix_md_path(root)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not _is_file(dest):
            dest.write_text(_MINIMAL_HOLIX_TEMPLATE, encoding="utf-8")
            logger.info("created HOLIX.md skeleton at %s", dest)
        return dest if _is_file(dest) else None
    except OSError:
        logger.warning("could not create %s", dest, exc_info=True)
        return None


def format_project_context_block(cwd: str | Path | None = None) -> str:
    """HOLIX.md plus AGENTS.md / CLAUDE.md / rules.md when present."""
    from core.project.instruction_files import format_instruction_files_block

    parts: list[str] = []
    holix_block = format_holix_md_block(cwd)
    if holix_block:
        parts.append(holix_block)
    extra = format_instruction_files_block(cwd)
    if extra:
        parts.append(extra)
    return "\n\n".join(parts)


def append_holix_project_context(prompt: str, cwd: str | Path | None = None) -> str:
    """Append project handbook + standard agent files to a system prompt.

    Creates ``.holix/HOLIX.md`` when missing so every turn has a handbook.
    """
    try:
        ensure_holix_md_exists(cwd)
    except OSError:
        logger.warning("ensure_holix_md_exists failed", exc_info=True)
    block = format_project_context_block(cwd)
    if not block:
        return prompt
    return f"{prompt.rstrip()}\n\n{block}\n"
