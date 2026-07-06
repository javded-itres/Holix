"""Workspace-scoped file tree and read API for Holix Studio."""

from __future__ import annotations

import mimetypes
import shutil
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
        ".log",
        ".csv",
        ".tsv",
        ".markdown",
        ".rst",
        ".htm",
        ".properties",
    }
)
_TEXT_MIME_TYPES = frozenset(
    {
        "application/json",
        "application/xml",
        "application/yaml",
        "application/x-yaml",
        "application/javascript",
        "application/x-sh",
        "application/sql",
        "application/csv",
        "application/toml",
        "inode/x-empty",
    }
)
_SKIP_DIR_NAMES = frozenset({".git", "__pycache__", ".venv", "node_modules", ".runtime-cache"})
_MAX_WRITE_BYTES = 512_000
_MAX_UPLOAD_BYTES = 5_000_000


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


def _validate_file_name(name: str) -> str:
    text = (name or "").strip()
    if not text or text in {".", ".."}:
        raise WorkspacePathError("Invalid file name")
    if "/" in text or "\\" in text or "\0" in text:
        raise WorkspacePathError("File name cannot contain path separators")
    return text


def _guess_mime(path: Path) -> str | None:
    mime, _ = mimetypes.guess_type(path.name)
    return mime


def _is_allowed_text_path(path: Path) -> bool:
    suffix = path.suffix.lower()
    if not suffix or suffix in _TEXT_SUFFIXES:
        return True
    mime = _guess_mime(path)
    if mime and (mime.startswith("text/") or mime in _TEXT_MIME_TYPES):
        return True
    return False


def _looks_like_utf8_text(path: Path, *, sample_bytes: int = 8192) -> bool:
    try:
        with path.open("rb") as handle:
            chunk = handle.read(sample_bytes)
        if b"\x00" in chunk:
            return False
        chunk.decode("utf-8")
        return True
    except (OSError, UnicodeDecodeError):
        return False


def _reject_unreadable_text_path(path: Path) -> None:
    if _is_allowed_text_path(path) or _looks_like_utf8_text(path):
        return
    mime = _guess_mime(path)
    raise ValueError(f"Binary or unsupported file type: {mime or path.suffix.lower() or path.name}")


def _ensure_writable_text_path(path: Path) -> None:
    _reject_unreadable_text_path(path)


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
    return {
        "path": _normalize_rel(rel_path) or path.name,
        "kind": "directory" if path.is_dir() else "file",
        "size": st.st_size,
        "readable_text": path.is_file() and (
            _is_allowed_text_path(path) or _looks_like_utf8_text(path)
        ),
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
    _reject_unreadable_text_path(path)

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


def _path_within(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def delete_path(
    profile: str,
    rel_path: str,
    *,
    workspace_root: Path | None = None,
    serve_cwd: Path | str | None = None,
) -> dict[str, Any]:
    """Delete a file or directory (recursive) inside the workspace."""
    rel = _normalize_rel(rel_path)
    if not rel:
        raise WorkspacePathError("Cannot delete workspace root")
    root = workspace_root or resolve_studio_workspace_root(profile, serve_cwd=serve_cwd)
    path = resolve_workspace_path(profile, rel, workspace_root=root)
    if not path.exists():
        raise FileNotFoundError(rel)
    if path.resolve() == root.resolve():
        raise WorkspacePathError("Cannot delete workspace root")
    kind = "directory" if path.is_dir() else "file"
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return {"path": rel, "kind": kind, "deleted": True}


def move_path(
    profile: str,
    source: str,
    destination: str,
    *,
    into: bool = False,
    workspace_root: Path | None = None,
    serve_cwd: Path | str | None = None,
) -> dict[str, Any]:
    """Move or rename a workspace file or directory."""
    source_rel = _normalize_rel(source)
    if not source_rel:
        raise WorkspacePathError("Source path is required")
    dest_input = _normalize_rel(destination)
    if not dest_input and not into:
        raise WorkspacePathError("Destination path is required")

    root = workspace_root or resolve_studio_workspace_root(profile, serve_cwd=serve_cwd)
    src = resolve_workspace_path(profile, source_rel, workspace_root=root)
    if not src.exists():
        raise FileNotFoundError(source_rel)

    if into:
        dest_dir = resolve_workspace_path(profile, dest_input, workspace_root=root)
        if not dest_dir.exists() or not dest_dir.is_dir():
            raise NotADirectoryError(dest_input or ".")
        dst = dest_dir / src.name
        dest_rel = f"{dest_input}/{src.name}" if dest_input else src.name
    else:
        dst = resolve_workspace_path(profile, dest_input, workspace_root=root)
        dest_rel = dest_input

    if src.resolve() == dst.resolve():
        raise ValueError("Cannot move path onto itself")
    if src.is_dir() and _path_within(src, dst):
        raise ValueError("Cannot move directory into itself or its subdirectory")

    if dst.exists():
        raise FileExistsError(dest_rel)

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return {
        "source": source_rel,
        "path": dest_rel,
        "kind": "directory" if dst.is_dir() else "file",
    }


def create_directory(
    profile: str,
    rel_path: str,
    *,
    workspace_root: Path | None = None,
    serve_cwd: Path | str | None = None,
) -> dict[str, Any]:
    """Create a directory inside the workspace."""
    rel = _normalize_rel(rel_path)
    if not rel:
        raise WorkspacePathError("Directory path is required")
    path = resolve_workspace_path(
        profile,
        rel,
        workspace_root=workspace_root,
        serve_cwd=serve_cwd,
    )
    if path.exists():
        raise FileExistsError(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir(parents=False, exist_ok=False)
    return {"path": rel, "kind": "directory"}


def write_file(
    profile: str,
    rel_path: str,
    content: str,
    *,
    create_only: bool = False,
    max_bytes: int = _MAX_WRITE_BYTES,
    workspace_root: Path | None = None,
    serve_cwd: Path | str | None = None,
) -> dict[str, Any]:
    """Create or overwrite a UTF-8 text file inside the workspace."""
    rel = _normalize_rel(rel_path)
    if not rel:
        raise WorkspacePathError("File path is required")
    path = resolve_workspace_path(
        profile,
        rel,
        workspace_root=workspace_root,
        serve_cwd=serve_cwd,
    )
    _ensure_writable_text_path(path)
    existed = path.exists()
    if existed:
        if create_only:
            raise FileExistsError(rel)
        if path.is_dir():
            raise IsADirectoryError(rel)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)

    encoded = content.encode("utf-8")
    if len(encoded) > max_bytes:
        raise ValueError(f"File too large ({len(encoded)} bytes; max {max_bytes})")
    path.write_text(content, encoding="utf-8")
    return {
        "path": rel,
        "size": len(encoded),
        "language": _language_for_path(path),
        "created": not existed,
    }


def upload_file(
    profile: str,
    directory: str,
    filename: str,
    data: bytes,
    *,
    overwrite: bool = False,
    max_bytes: int = _MAX_UPLOAD_BYTES,
    workspace_root: Path | None = None,
    serve_cwd: Path | str | None = None,
) -> dict[str, Any]:
    """Upload one file into a workspace directory (binary-safe)."""
    safe_name = _validate_file_name(filename)
    parent_rel = _normalize_rel(directory)
    rel = f"{parent_rel}/{safe_name}" if parent_rel else safe_name
    path = resolve_workspace_path(
        profile,
        rel,
        workspace_root=workspace_root,
        serve_cwd=serve_cwd,
    )
    if path.exists() and not overwrite:
        raise FileExistsError(rel)
    if path.is_dir():
        raise IsADirectoryError(rel)
    if len(data) > max_bytes:
        raise ValueError(f"File too large ({len(data)} bytes; max {max_bytes})")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"path": rel, "size": len(data)}


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