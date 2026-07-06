"""Workspace-scoped file tree and read API for Holix Studio."""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_TEXT_SUFFIXES = frozenset(
    {
        ".py",
        ".pyi",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".json",
        ".yaml",
        ".yml",
        ".md",
        ".txt",
        ".html",
        ".css",
        ".scss",
        ".sh",
        ".bash",
        ".zsh",
        ".toml",
        ".ini",
        ".cfg",
        ".xml",
        ".sql",
        ".rs",
        ".go",
        ".java",
        ".kt",
        ".c",
        ".h",
        ".cpp",
        ".hpp",
        ".rb",
        ".php",
        ".swift",
        ".vue",
        ".env",
        ".gitignore",
        ".dockerfile",
    }
)
_SKIP_DIR_NAMES = frozenset({".git", "__pycache__", ".venv", "node_modules", ".runtime-cache"})


class WorkspacePathError(ValueError):
    """Relative path escapes workspace or is invalid."""


@dataclass(frozen=True)
class FileNode:
    name: str
    path: str
    kind: str  # "file" | "directory"
    size: int | None = None
    children: list[FileNode] | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"name": self.name, "path": self.path, "kind": self.kind}
        if self.size is not None:
            data["size"] = self.size
        if self.children is not None:
            data["children"] = [c.to_dict() for c in self.children]
        return data


def resolve_studio_workspace_root(
    profile: str,
    *,
    serve_cwd: Path | str | None = None,
) -> Path:
    """Return the directory Studio should list (aligned with agent file tools).

    When workspace jail is disabled, Holix tools resolve relative paths against
    process CWD — Studio uses ``serve_cwd`` (directory where ``holix studio serve``
    was started). When jail is enabled, the profile ``workspace_root`` is used.
    """
    from cli.core import ProfileManager

    config = ProfileManager().load_profile(profile)
    if getattr(config, "workspace_jail_enabled", False) and config.workspace_root:
        return Path(config.workspace_root).expanduser().resolve()
    base = Path(serve_cwd or Path.cwd()).expanduser().resolve()
    return base


def _normalize_rel(rel: str) -> str:
    text = (rel or "").strip().replace("\\", "/").lstrip("/")
    if not text or text == ".":
        return ""
    parts = [p for p in text.split("/") if p and p != "."]
    if any(p == ".." for p in parts):
        raise WorkspacePathError("Path must stay inside workspace")
    return "/".join(parts)


def resolve_workspace_path(
    profile: str,
    rel_path: str,
    *,
    workspace_root: Path | None = None,
    serve_cwd: Path | str | None = None,
) -> Path:
    """Resolve a workspace-relative path; raise if outside workspace."""
    root = workspace_root or resolve_studio_workspace_root(profile, serve_cwd=serve_cwd)
    rel = _normalize_rel(rel_path)
    target = (root / rel) if rel else root
    resolved = target.resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise WorkspacePathError("Path escapes workspace")
    return resolved


def list_tree(
    profile: str,
    *,
    depth: int = 4,
    root: str = "workspace",
    workspace_root: Path | None = None,
    serve_cwd: Path | str | None = None,
) -> dict[str, Any]:
    """Return nested file tree under the Studio workspace root."""
    if root != "workspace":
        raise WorkspacePathError("Only workspace root is supported")
    ws = workspace_root or resolve_studio_workspace_root(profile, serve_cwd=serve_cwd)
    ws.mkdir(parents=True, exist_ok=True)
    max_depth = max(1, min(int(depth), 8))

    def walk(directory: Path, current_depth: int) -> list[FileNode]:
        if current_depth > max_depth:
            return []
        nodes: list[FileNode] = []
        try:
            entries = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return nodes
        for entry in entries:
            if entry.name.startswith(".") and entry.name not in {".env", ".gitignore"}:
                continue
            if entry.is_dir() and entry.name in _SKIP_DIR_NAMES:
                continue
            rel = entry.relative_to(ws).as_posix()
            if entry.is_dir():
                children = walk(entry, current_depth + 1) if current_depth < max_depth else []
                nodes.append(FileNode(name=entry.name, path=rel, kind="directory", children=children))
            else:
                try:
                    size = entry.stat().st_size
                except OSError:
                    size = None
                nodes.append(FileNode(name=entry.name, path=rel, kind="file", size=size))
        return nodes

    children = walk(ws, 1)
    return {
        "root": "workspace",
        "path": ".",
        "workspace_root": str(ws),
        "children": [n.to_dict() for n in children],
    }


def stat_file(
    profile: str,
    rel_path: str,
    *,
    workspace_root: Path | None = None,
    serve_cwd: Path | str | None = None,
) -> dict[str, Any]:
    path = resolve_workspace_path(
        profile,
        rel_path,
        workspace_root=workspace_root,
        serve_cwd=serve_cwd,
    )
    if not path.exists():
        raise FileNotFoundError(rel_path)
    st = path.stat()
    suffix = path.suffix.lower()
    return {
        "path": _normalize_rel(rel_path) or path.name,
        "kind": "directory" if path.is_dir() else "file",
        "size": st.st_size,
        "readable_text": path.is_file() and (suffix in _TEXT_SUFFIXES or not suffix),
        "language": _language_for_path(path),
    }


def read_file(
    profile: str,
    rel_path: str,
    *,
    max_bytes: int = 512_000,
    workspace_root: Path | None = None,
    serve_cwd: Path | str | None = None,
) -> dict[str, Any]:
    path = resolve_workspace_path(
        profile,
        rel_path,
        workspace_root=workspace_root,
        serve_cwd=serve_cwd,
    )
    if not path.is_file():
        raise FileNotFoundError(rel_path)
    size = path.stat().st_size
    if size > max_bytes:
        raise ValueError(f"File too large ({size} bytes; max {max_bytes})")
    suffix = path.suffix.lower()
    if suffix not in _TEXT_SUFFIXES and suffix:
        mime, _ = mimetypes.guess_type(path.name)
        raise ValueError(f"Binary or unsupported file type: {mime or suffix}")

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise ValueError("File is not valid UTF-8 text") from e

    return {
        "path": _normalize_rel(rel_path),
        "content": content,
        "size": size,
        "language": _language_for_path(path),
    }


def _language_for_path(path: Path) -> str:
    name = path.name.lower()
    if name == "dockerfile":
        return "dockerfile"
    ext = path.suffix.lower().lstrip(".")
    mapping = {
        "py": "python",
        "pyi": "python",
        "js": "javascript",
        "jsx": "javascript",
        "ts": "typescript",
        "tsx": "typescript",
        "json": "json",
        "md": "markdown",
        "yaml": "yaml",
        "yml": "yaml",
        "html": "html",
        "css": "css",
        "scss": "scss",
        "sh": "shell",
        "bash": "shell",
        "zsh": "shell",
        "toml": "ini",
        "xml": "xml",
        "sql": "sql",
        "rs": "rust",
        "go": "go",
        "java": "java",
        "rb": "ruby",
        "php": "php",
        "swift": "swift",
        "vue": "html",
    }
    return mapping.get(ext, "plaintext")