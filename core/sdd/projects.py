"""Discover and resolve multi-project openspec roots under a workspace."""

from __future__ import annotations

from pathlib import Path

from core.sdd.paths import CONFIG_FILE, openspec_root

_SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".next",
        ".turbo",
        "target",
        "vendor",
        ".idea",
        ".vscode",
        "openspec",  # never recurse into openspec itself
    }
)


def normalize_project_rel(project: str | None) -> str:
    """Return POSIX-ish relative project path ('' = workspace root)."""
    raw = (project or "").strip().replace("\\", "/").strip("/")
    if not raw or raw == ".":
        return ""
    parts = [p for p in raw.split("/") if p and p != "."]
    if any(p == ".." for p in parts):
        raise ValueError("project path must not contain '..'")
    return "/".join(parts)


def resolve_project_root(workspace: Path | str, project: str | None = None) -> Path:
    """Resolve absolute project root under workspace (folder that owns openspec/)."""
    ws = Path(workspace).expanduser().resolve()
    rel = normalize_project_rel(project)
    if not rel:
        return ws
    root = (ws / rel).resolve()
    try:
        root.relative_to(ws)
    except ValueError as exc:
        raise ValueError(f"project path escapes workspace: {project!r}") from exc
    if root == ws:
        return ws
    # Session already pinned to this project: do not nest ``apps/api/apps/api``.
    if is_sdd_initialized(ws) and not root.is_dir():
        posix = ws.as_posix()
        if posix.endswith("/" + rel) or ws.name == Path(rel).name:
            return ws
    return root


def project_label(rel: str) -> str:
    if not rel:
        return "."
    return rel


def is_sdd_initialized(project_root: Path | str) -> bool:
    root = Path(project_root)
    cfg = openspec_root(root) / CONFIG_FILE
    return openspec_root(root).is_dir() and cfg.is_file()


def discover_sdd_projects(
    workspace: Path | str,
    *,
    max_depth: int = 5,
) -> list[dict]:
    """Find folders containing ``openspec/config.yaml`` under workspace.

    Returns list of dicts: path (rel), label, openspec (rel), initialized.
    Workspace root project uses path ``""``.
    """
    ws = Path(workspace).expanduser().resolve()
    found: list[dict] = []
    seen: set[str] = set()

    try:
        from core.sdd.product_layout import load_product_layout

        layout = load_product_layout(ws)
    except Exception:
        layout = None
    if layout is not None and layout.has_dedicated_spec and layout.spec_root is not None:
        spec = layout.spec_root
        try:
            rel_s = spec.relative_to(ws)
            rel = "" if str(rel_s) == "." else rel_s.as_posix()
        except ValueError:
            try:
                rel_s = spec.relative_to(layout.project_root)
                rel = "" if str(rel_s) == "." else rel_s.as_posix()
            except ValueError:
                rel = spec.name
        op = openspec_root(spec)
        try:
            op_rel = op.relative_to(ws).as_posix()
        except ValueError:
            try:
                op_rel = op.relative_to(layout.project_root).as_posix()
            except ValueError:
                op_rel = str(op)
        return [
            {
                "path": rel,
                "label": project_label(rel),
                "openspec": op_rel,
                "initialized": is_sdd_initialized(spec),
                "role": "spec",
            }
        ]

    def _add(project_root: Path) -> None:
        try:
            rel = project_root.relative_to(ws)
            rel_s = "" if str(rel) == "." else rel.as_posix()
        except ValueError:
            return
        if rel_s in seen:
            return
        seen.add(rel_s)
        op = openspec_root(project_root)
        try:
            op_rel = op.relative_to(ws).as_posix()
        except ValueError:
            op_rel = str(op)
        found.append(
            {
                "path": rel_s,
                "label": project_label(rel_s),
                "openspec": op_rel,
                "initialized": is_sdd_initialized(project_root),
            }
        )

    if is_sdd_initialized(ws):
        _add(ws)

    if max_depth < 1:
        found.sort(key=lambda x: (x["path"] != "", x["path"]))
        return found

    def _walk(current: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            children = sorted(current.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return
        for child in children:
            if not child.is_dir() or child.is_symlink():
                continue
            if child.name in _SKIP_DIR_NAMES or child.name.startswith("."):
                continue
            if is_sdd_initialized(child):
                _add(child)
                # do not recurse into project interiors for nested openspec
                # (still allow sibling packages)
                continue
            _walk(child, depth + 1)

    _walk(ws, 1)
    found.sort(key=lambda x: (x["path"] != "", x["path"]))
    return found
