"""Load standard agent instruction files from the project tree.

Holix always injects ``.holix/HOLIX.md``. When these files exist at a
repository root (workspace or nested packages), they are appended too:

- ``AGENTS.md`` — portable agent contract
- ``CLAUDE.md`` — Claude Code / compatible agents
- ``rules.md`` / ``RULES.md`` — coding standards
"""

from __future__ import annotations

from pathlib import Path

from core.project.holix_md import HOLIX_MD_SEARCH_DEPTH

INSTRUCTION_FILE_NAMES = (
    "AGENTS.md",
    "CLAUDE.md",
    "rules.md",
    "RULES.md",
)
INSTRUCTION_FILE_MAX_CHARS = 8_000
INSTRUCTION_FILES_TOTAL_MAX = 16_000
INSTRUCTION_FILE_SEARCH_DEPTH = HOLIX_MD_SEARCH_DEPTH
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
        ".next",
        ".turbo",
        "coverage",
        "target",
        "vendor",
    }
)

INSTRUCTION_FILES_NOTE = (
    "Standard agent files at the repository root are loaded automatically when "
    "present: `AGENTS.md`, `CLAUDE.md`, `rules.md` / `RULES.md`. Treat them as "
    "mandatory project instructions, same priority as `.holix/HOLIX.md`."
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


def _rel_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root)).replace("\\", "/")
    except ValueError:
        return path.name


def discover_instruction_files(
    cwd: str | Path | None = None,
    *,
    max_depth: int = INSTRUCTION_FILE_SEARCH_DEPTH,
) -> list[Path]:
    """Return AGENTS.md / CLAUDE.md / rules.md paths, shallowest first.

    Deduplicates case-insensitive paths so macOS ``rules.md`` == ``RULES.md``
    is injected once. ``rules.md`` is preferred over ``RULES.md`` when both
    exist as distinct files.
    """
    root = _workspace_root(cwd)
    depth_limit = max(0, int(max_depth))
    found: list[tuple[int, str, Path]] = []
    seen: set[str] = set()

    def consider(directory: Path, depth: int) -> None:
        for name in INSTRUCTION_FILE_NAMES:
            path = directory / name
            if not _is_file(path):
                continue
            try:
                key = str(path.resolve()).casefold()
            except OSError:
                key = str(path).casefold()
            if key in seen:
                continue
            seen.add(key)
            rel = _rel_path(path, root)
            found.append((depth, rel, path))

    consider(root, 0)
    if depth_limit == 0:
        found.sort(key=lambda item: (item[0], item[1]))
        return [path for _, _, path in found]

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


def load_instruction_file(path: Path, *, max_chars: int = INSTRUCTION_FILE_MAX_CHARS) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not text:
        return None
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n… [truncated for context; full file: {path.name}]"
    return text


def format_instruction_files_block(
    cwd: str | Path | None = None,
    *,
    max_chars_each: int = INSTRUCTION_FILE_MAX_CHARS,
    max_chars_total: int = INSTRUCTION_FILES_TOTAL_MAX,
) -> str:
    """Markdown blocks for discovered instruction files, or empty string."""
    root = _workspace_root(cwd)
    paths = discover_instruction_files(cwd)
    if not paths:
        return ""
    has_agents = any(p.name.casefold() == "agents.md" for p in paths)
    if has_agents:
        # AGENTS.md and CLAUDE.md are the same role; keep one.
        paths = [p for p in paths if p.name.casefold() != "claude.md"]
    chunks: list[str] = [f"## Agent instruction files\n{INSTRUCTION_FILES_NOTE}"]
    used = 0
    for path in paths:
        remaining = max_chars_total - used
        if remaining < 200:
            chunks.append("… [further instruction files truncated]")
            break
        body = load_instruction_file(path, max_chars=min(max_chars_each, remaining))
        if not body:
            continue
        rel = _rel_path(path, root)
        piece = f"### `{rel}`\n\n{body}"
        chunks.append(piece)
        used += len(body)
    if len(chunks) == 1:
        return ""
    return "\n\n".join(chunks)
