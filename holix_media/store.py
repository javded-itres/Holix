"""Save generated blobs into the profile workspace."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from holix_media.providers import MediaBlob


def workspace_root(agent: Any | None) -> Path:
    cfg = getattr(agent, "config", None) if agent is not None else None
    root = getattr(cfg, "workspace_root", None) if cfg is not None else None
    if root:
        return Path(str(root)).expanduser()
    return Path.cwd()


def save_blob(blob: MediaBlob, *, agent: Any | None, subdir: str = "media") -> Path:
    dest_dir = workspace_root(agent) / (subdir or "media")
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = _safe_name(blob.filename)
    path = dest_dir / name
    n = 1
    while path.exists():
        stem = Path(name).stem
        path = dest_dir / f"{stem}-{n}{Path(name).suffix}"
        n += 1
    path.write_bytes(blob.data)
    return path.resolve()


def _safe_name(name: str) -> str:
    base = Path(name or "media.bin").name
    base = re.sub(r"[^\w.\-]+", "_", base, flags=re.UNICODE).strip("._")
    return base or "media.bin"
