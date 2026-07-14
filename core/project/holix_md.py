"""Load and inject `.holix/HOLIX.md` project knowledge into agent prompts."""

from __future__ import annotations

from pathlib import Path

from core.config_utils import get_local_holix_dir

HOLIX_MD_FILENAME = "HOLIX.md"
HOLIX_MD_LEGACY_FILENAME = "HELIX.md"
HOLIX_MD_REL_PATH = f".holix/{HOLIX_MD_FILENAME}"
DEFAULT_MAX_CHARS = 24_000
HOLIX_MD_SEARCH_DEPTH = 2
_SKIP_SEARCH_DIRS = frozenset({
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
})

TASK_CONTEXT_NOTE = (
    "When `.holix/HOLIX.md` exists in the working directory or nested subfolders "
    "(up to two levels), treat it as the primary source of truth about this codebase. "
    "Read it (or refresh with `read_file`) before exploring blindly. Prefer facts from "
    "HOLIX.md over assumptions."
)

PLANNING_CONTEXT_NOTE = (
    "Before planning, check whether `.holix/HOLIX.md` exists in the working directory "
    "or nested subfolders (up to two levels). If it does, base architecture, module "
    "boundaries, REST/API layout, and conventions on that document. Cite specific "
    "sections when reasoning about the plan. Also check `.holix/plans/` for previously "
    "approved plans (JSON + Markdown) and reuse or extend them when the task matches."
)


def _workspace_root(cwd: str | Path | None = None) -> Path:
    return (Path(cwd) if cwd else Path.cwd()).expanduser().resolve()


def _holix_md_file_in_dir(base: Path) -> Path | None:
    holix_dir = get_local_holix_dir(base)
    holix_md = holix_dir / HOLIX_MD_FILENAME
    if holix_md.is_file():
        return holix_md
    legacy = holix_dir / HOLIX_MD_LEGACY_FILENAME
    if legacy.is_file():
        return legacy
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
        hit = _holix_md_file_in_dir(directory)
        if hit is not None:
            rel = str(directory.relative_to(root)).replace("\\", "/")
            found.append((depth, rel, hit))

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
            if not child.is_dir():
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
        text = (
            text[:max_chars]
            + f"\n\n… [truncated for context; full file: {rel_path}]"
        )
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
    return (
        f"## Project knowledge ({rel_path})\n"
        f"{TASK_CONTEXT_NOTE}\n\n"
        f"{body}"
    )


def append_holix_project_context(prompt: str, cwd: str | Path | None = None) -> str:
    """Append HOLIX.md block to a system prompt when the file exists."""
    block = format_holix_md_block(cwd)
    if not block:
        return prompt
    return f"{prompt.rstrip()}\n\n{block}\n"