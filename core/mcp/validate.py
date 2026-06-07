"""MCP install / connect validation helpers."""

from __future__ import annotations

from pathlib import Path


def normalize_allowed_paths(raw: str) -> tuple[list[str], list[str]]:
    """Expand and validate filesystem MCP root directories.

    Returns (absolute_paths, error_messages).
    """
    if not (raw or "").strip():
        return [], ["At least one allowed directory is required"]

    paths: list[str] = []
    errors: list[str] = []
    for part in raw.replace(",", " ").split():
        token = part.strip()
        if not token:
            continue
        p = Path(token).expanduser()
        try:
            if not p.is_absolute():
                p = (Path.cwd() / p).resolve()
            else:
                p = p.resolve()
        except OSError as e:
            errors.append(f"Invalid path {token!r}: {e}")
            continue
        if not p.exists():
            errors.append(f"Directory does not exist: {token}")
            continue
        if not p.is_dir():
            errors.append(f"Not a directory: {token}")
            continue
        paths.append(str(p))

    if not paths and not errors:
        errors.append("At least one allowed directory is required")
    return paths, errors


def format_mcp_error(exc: BaseException) -> str:
    """Flatten ExceptionGroup / TaskGroup into a readable message."""
    if isinstance(exc, BaseExceptionGroup):
        parts = [format_mcp_error(e) for e in exc.exceptions]
        return "; ".join(p for p in parts if p) or str(exc)
    cause = exc.__cause__
    if cause and str(cause) not in str(exc):
        return f"{exc} — {format_mcp_error(cause)}"
    return str(exc)