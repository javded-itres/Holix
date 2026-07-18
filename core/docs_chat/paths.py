"""Locate the Holix documentation web root (pure path resolution)."""

from __future__ import annotations

import os
from pathlib import Path


def _detect_repo_root() -> Path | None:
    """Best-effort repo root without depending on CLI installer."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "core").is_dir():
            return parent
    return None


def resolve_web_docs_dir() -> Path:
    """Locate holix-docs/ (standalone site) or legacy web-docs/ in a checkout."""
    candidates: list[Path] = []

    override = os.getenv("HOLIX_WEB_DOCS_DIR", "").strip()
    if override:
        candidates.append(Path(override).expanduser())

    repo = _detect_repo_root()
    if repo is not None:
        candidates.append(repo.parent / "holix-docs")
        candidates.append(repo / "web-docs")

    candidates.append(Path(__file__).resolve().parents[2] / "web-docs")
    candidates.append(Path.cwd() / "holix-docs")
    candidates.append(Path.cwd() / "web-docs")

    seen: set[Path] = set()
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / "index.html").is_file():
            return resolved

    raise FileNotFoundError(
        "Documentation site not found. Clone holix-docs next to Helix, set "
        "HOLIX_WEB_DOCS_DIR, or run from a checkout that contains web-docs/."
    )
