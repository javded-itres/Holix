"""Resolve the project/workspace root for HOLIX.md, /init, and planning.

Studio sets ``agent.config.workspace_root`` to the user's open project. Process
CWD is often the Studio install tree (``--cwd holix-studio``) or the Helix
repo — never use bare ``Path.cwd()`` when a workspace is known.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


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
    if cwd is not None and str(cwd).strip():
        return Path(str(cwd)).expanduser().resolve()

    cfg = config
    if cfg is None and agent is not None:
        cfg = getattr(agent, "config", None)
    root = getattr(cfg, "workspace_root", None) if cfg is not None else None
    if root and str(root).strip():
        return Path(str(root)).expanduser().resolve()

    if host is not None:
        for attr in ("workspace_root", "workspace", "serve_cwd"):
            val = getattr(host, attr, None)
            if val is None:
                continue
            # EffectiveWorkspace may expose .root / .path
            if hasattr(val, "root") and getattr(val, "root", None):
                return Path(str(val.root)).expanduser().resolve()
            if hasattr(val, "path") and getattr(val, "path", None):
                return Path(str(val.path)).expanduser().resolve()
            text = str(val).strip()
            if text and text not in {".", "./"}:
                try:
                    return Path(text).expanduser().resolve()
                except OSError:
                    pass

    try:
        from core.tools.execution_context import get_workspace_root

        ctx = get_workspace_root()
        if ctx and str(ctx).strip():
            return Path(str(ctx)).expanduser().resolve()
    except Exception:
        pass

    return Path.cwd().resolve()
