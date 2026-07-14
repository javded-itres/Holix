"""Deterministic project scan for `/init` — keeps large repos within LLM budget."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.project.holix_md import HOLIX_MD_FILENAME

_SKIP_DIRS = frozenset({
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
    ".idea",
    ".vscode",
    "target",
    "vendor",
})

_MANIFEST_NAMES = frozenset({
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "requirements.txt",
    "Pipfile",
    "setup.py",
    "Makefile",
    "CMakeLists.txt",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
})

_README_NAMES = frozenset({
    "readme.md",
    "readme.rst",
    "readme.txt",
    "readme",
    "contributing.md",
    "changelog.md",
})

_DOC_DIR_NAMES = frozenset({"docs", "doc", "documentation"})

_LARGE_FILE_COUNT = 400
_LARGE_TOP_DIRS = 25
_TREE_MAX_DEPTH = 3
_TREE_MAX_LINES = 180
_MAX_MANIFESTS_LISTED = 40
_MAX_READMES_LISTED = 20


@dataclass
class InitProjectScan:
    scope_rel: str
    scope_root: Path
    workspace_root: Path
    is_large: bool
    file_count: int
    top_level_dirs: list[str] = field(default_factory=list)
    directory_tree: str = ""
    manifest_paths: list[str] = field(default_factory=list)
    readme_paths: list[str] = field(default_factory=list)
    doc_dirs: list[str] = field(default_factory=list)
    subprojects: list[str] = field(default_factory=list)
    compose_paths: list[str] = field(default_factory=list)
    extension_counts: dict[str, int] = field(default_factory=dict)


def _workspace_root(cwd: str | Path | None = None) -> Path:
    return (Path(cwd) if cwd else Path.cwd()).expanduser().resolve()


def _rel_path(path: Path, *, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


def _should_skip_dir(name: str) -> bool:
    return name in _SKIP_DIRS or name.startswith(".")


def _count_files(root: Path, *, limit: int = 5000) -> tuple[int, dict[str, int]]:
    total = 0
    ext_counts: dict[str, int] = {}
    try:
        for path in root.rglob("*"):
            if total >= limit:
                break
            if not path.is_file():
                continue
            parts = path.relative_to(root).parts
            if any(_should_skip_dir(part) for part in parts[:-1]):
                continue
            total += 1
            ext = path.suffix.lower() or "(no ext)"
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
    except OSError:
        pass
    return total, ext_counts


def _format_tree(root: Path, *, workspace_root: Path) -> str:
    lines: list[str] = []
    root_label = _rel_path(root, root=workspace_root) or "."

    def walk(directory: Path, prefix: str, depth: int) -> None:
        if len(lines) >= _TREE_MAX_LINES or depth > _TREE_MAX_DEPTH:
            return
        try:
            children = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return
        dirs = [c for c in children if c.is_dir() and not _should_skip_dir(c.name)]
        files = [c for c in children if c.is_file()]
        entries = dirs + files[:12]
        for index, child in enumerate(entries):
            if len(lines) >= _TREE_MAX_LINES:
                lines.append(f"{prefix}…")
                return
            connector = "└── " if index == len(entries) - 1 else "├── "
            name = child.name + ("/" if child.is_dir() else "")
            lines.append(f"{prefix}{connector}{name}")
            if child.is_dir():
                extension = "    " if index == len(entries) - 1 else "│   "
                walk(child, prefix + extension, depth + 1)

    lines.append(f"{root_label}/")
    walk(root, "", 0)
    if len(lines) >= _TREE_MAX_LINES:
        lines.append("… (tree truncated)")
    return "\n".join(lines)


def _collect_paths(root: Path, *, workspace_root: Path) -> tuple[list[str], list[str], list[str], list[str]]:
    manifests: list[str] = []
    readmes: list[str] = []
    docs: list[str] = []
    compose: list[str] = []
    try:
        for path in sorted(root.rglob("*")):
            rel = _rel_path(path, root=workspace_root)
            parts = Path(rel).parts
            if any(_should_skip_dir(part) for part in parts[:-1]):
                continue
            if not path.is_file() and not (path.is_dir() and path.name in _DOC_DIR_NAMES):
                continue
            name = path.name
            lower = name.lower()
            if name in _MANIFEST_NAMES:
                manifests.append(rel)
                if lower.startswith("docker-compose") or lower.startswith("compose."):
                    compose.append(rel)
            elif lower in _README_NAMES:
                readmes.append(rel)
            elif path.is_dir() and path.name in _DOC_DIR_NAMES:
                docs.append(rel)
    except OSError:
        pass
    return (
        manifests[:_MAX_MANIFESTS_LISTED],
        readmes[:_MAX_READMES_LISTED],
        docs[:12],
        compose[:12],
    )


def _normalize_scope_rel(scope_rel: str) -> str:
    rel = scope_rel.strip().strip("/").replace("\\", "/")
    return "" if rel in ("", ".") else rel


def _detect_subprojects(root: Path, *, workspace_root: Path, manifests: list[str]) -> list[str]:
    found: set[str] = set()
    root_rel = _normalize_scope_rel(_rel_path(root, root=workspace_root))
    for rel in manifests:
        parent = _normalize_scope_rel(str(Path(rel).parent).replace("\\", "/"))
        if not parent:
            continue
        if root_rel:
            if parent != root_rel and not parent.startswith(f"{root_rel}/"):
                continue
            if parent == root_rel:
                continue
        found.add(parent)
    return sorted(found)[:30]


def scan_project_for_init(
    *,
    cwd: str | Path | None = None,
    target_dir: str | None = None,
) -> InitProjectScan:
    """Scan workspace (optionally scoped to *target_dir*) for `/init`."""
    workspace_root = _workspace_root(cwd)
    scope_rel = (target_dir or "").strip().strip("/").replace("\\", "/")
    scope_root = workspace_root / scope_rel if scope_rel else workspace_root
    scope_root = scope_root.resolve()

    try:
        top_dirs = sorted(
            [
                child.name
                for child in scope_root.iterdir()
                if child.is_dir() and not _should_skip_dir(child.name)
            ],
            key=str.lower,
        )
    except OSError:
        top_dirs = []

    file_count, ext_counts = _count_files(scope_root)
    manifests, readmes, doc_dirs, compose_paths = _collect_paths(scope_root, workspace_root=workspace_root)
    subprojects = _detect_subprojects(scope_root, workspace_root=workspace_root, manifests=manifests)
    is_large = (
        file_count >= _LARGE_FILE_COUNT
        or len(top_dirs) >= _LARGE_TOP_DIRS
        or len(subprojects) >= 4
    )

    return InitProjectScan(
        scope_rel=scope_rel,
        scope_root=scope_root,
        workspace_root=workspace_root,
        is_large=is_large,
        file_count=file_count,
        top_level_dirs=top_dirs,
        directory_tree=_format_tree(scope_root, workspace_root=workspace_root),
        manifest_paths=manifests,
        readme_paths=readmes,
        doc_dirs=doc_dirs,
        subprojects=subprojects,
        compose_paths=compose_paths,
        extension_counts=dict(sorted(ext_counts.items(), key=lambda item: (-item[1], item[0]))[:12]),
    )


def format_init_scan_report(scan: InitProjectScan, *, locale: str = "en") -> str:
    """Human-readable pre-scan block injected into the `/init` agent prompt."""
    from core.i18n.messages import t

    loc = locale if locale in ("en", "ru") else "en"
    lines = [t("init.scan.header", loc), ""]
    scope = scan.scope_rel or "."
    lines.append(t("init.scan.scope", loc, dir=scope, files=scan.file_count))
    if scan.is_large:
        lines.append(t("init.scan.large_flag", loc))
    lines.append("")

    if scan.top_level_dirs:
        lines.append(t("init.scan.top_dirs", loc, dirs=", ".join(scan.top_level_dirs[:30])))
        lines.append("")

    if scan.subprojects:
        lines.append(t("init.scan.subprojects", loc, items="\n".join(f"- `{p}`" for p in scan.subprojects)))
        lines.append("")

    if scan.manifest_paths:
        lines.append(t("init.scan.manifests", loc))
        lines.extend(f"- `{p}`" for p in scan.manifest_paths)
        lines.append("")

    if scan.readme_paths:
        lines.append(t("init.scan.readmes", loc))
        lines.extend(f"- `{p}`" for p in scan.readme_paths)
        lines.append("")

    if scan.doc_dirs:
        lines.append(t("init.scan.doc_dirs", loc, dirs=", ".join(f"`{d}`" for d in scan.doc_dirs)))
        lines.append("")

    if scan.extension_counts:
        ext_line = ", ".join(f"{ext}: {count}" for ext, count in scan.extension_counts.items())
        lines.append(t("init.scan.extensions", loc, summary=ext_line))
        lines.append("")

    lines.append(t("init.scan.tree", loc))
    lines.append("```")
    lines.append(scan.directory_tree or "(empty)")
    lines.append("```")
    return "\n".join(lines)


def write_init_skeleton(
    scan: InitProjectScan,
    *,
    holix_rel_path: str,
    template: str,
    locale: str = "en",
) -> Path:
    """Seed HOLIX.md with scan data so the agent fills gaps instead of re-discovering."""
    from core.i18n.messages import t
    from core.project.holix_md import ensure_holix_dir

    scope = scan.scope_rel or None
    ensure_holix_dir(scope)
    out = scan.scope_root / ".holix" / HOLIX_MD_FILENAME
    loc = locale if locale in ("en", "ru") else "en"

    subprojects_block = ""
    if scan.subprojects:
        rows = "\n".join(f"| `{p}` | (fill during /init) |" for p in scan.subprojects)
        subprojects_block = f"\n\n## {t('init.scan.subprojects_heading', loc)}\n| Path | Notes |\n|------|-------|\n{rows}\n"

    body = (
        f"{template.strip()}\n\n"
        f"<!-- {t('init.scan.skeleton_note', loc)} -->\n\n"
        f"## {t('init.scan.prefill_heading', loc)}\n"
        f"- {t('init.scan.prefill_files', loc, count=scan.file_count)}\n"
        f"- {t('init.scan.prefill_scope', loc, dir=scan.scope_rel or '.')}\n\n"
        f"### {t('init.scan.tree_heading', loc)}\n"
        f"```\n{scan.directory_tree}\n```\n"
        f"{subprojects_block}"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    return out