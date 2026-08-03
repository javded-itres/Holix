"""Resolve the project/workspace root for HOLIX.md, /init, and planning.

Studio sets ``agent.config.workspace_root`` to the user's open project. Process
CWD is often the Studio install tree (``--cwd holix-studio``) or the Helix
repo — never use bare ``Path.cwd()`` when a workspace is known.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _as_filesystem_path(value: Any) -> Path | None:
    """Coerce *value* to a Path only for real str/Path values.

    Do **not** treat arbitrary ``os.PathLike`` as valid: ``unittest.mock.MagicMock``
    implements ``__fspath__`` via auto-attrs, and ``str(MagicMock())`` is truthy —
    both would create junk directories like ``MagicMock/mock.config…``.
    """
    if value is None:
        return None
    if isinstance(value, Path):
        return value.expanduser().resolve()
    if isinstance(value, bytes):
        try:
            text = value.decode(errors="replace").strip()
        except Exception:
            return None
    elif isinstance(value, str):
        text = value.strip()
    else:
        return None
    if not text or text in {".", "./"}:
        return None
    # Reject mock reprs that slipped in as strings
    if text.startswith("<MagicMock") or text.startswith("<Mock"):
        return None
    try:
        return Path(text).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return None


def resolve_project_root(
    *,
    agent: Any = None,
    config: Any = None,
    cwd: str | Path | None = None,
    host: Any = None,
) -> Path:
    """Best project root for file scans and ``.holix/`` writes.

    Priority:
    1. Explicit ``cwd``
    2. ``config.workspace_root`` / ``agent.config.workspace_root``
    3. ``host.workspace_root`` / ``host.workspace``
    4. Execution context ``get_workspace_root()``
    5. ``Path.cwd()`` (last resort)
    """
    explicit = _as_filesystem_path(cwd)
    if explicit is not None:
        return explicit

    cfg = config
    if cfg is None and agent is not None:
        cfg = getattr(agent, "config", None)
    if cfg is not None:
        root = _as_filesystem_path(getattr(cfg, "workspace_root", None))
        if root is not None:
            return root

    if host is not None:
        for attr in ("workspace_root", "workspace", "serve_cwd"):
            val = getattr(host, attr, None)
            if val is None:
                continue
            # EffectiveWorkspace may expose .root / .path
            nested = getattr(val, "root", None) or getattr(val, "path", None)
            if nested is not None:
                root = _as_filesystem_path(nested)
                if root is not None:
                    return root
            root = _as_filesystem_path(val)
            if root is not None:
                return root

    try:
        from core.tools.execution_context import get_workspace_root

        ctx = get_workspace_root()
        root = _as_filesystem_path(ctx)
        if root is not None:
            return root
    except Exception:
        pass

    return Path.cwd().resolve()
