"""Load user-uploaded reference images for image/video generation."""

from __future__ import annotations

import base64
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_MAX_REFS = 6
_MAX_BYTES = 8 * 1024 * 1024
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


class ReferenceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ReferenceImage:
    path: Path
    mime: str
    data: bytes

    @property
    def b64(self) -> str:
        return base64.b64encode(self.data).decode("ascii")

    @property
    def data_url(self) -> str:
        return f"data:{self.mime};base64,{self.b64}"

    def chat_part(self) -> dict[str, Any]:
        return {"type": "image_url", "image_url": {"url": self.data_url}}


def load_references(
    paths: list[str] | None,
    *,
    agent: Any | None = None,
) -> list[ReferenceImage]:
    cleaned = [str(p).strip() for p in (paths or []) if str(p).strip()]
    if not cleaned:
        return []
    if len(cleaned) > _MAX_REFS:
        raise ReferenceError(f"Too many reference images (max {_MAX_REFS})")
    out: list[ReferenceImage] = []
    for raw in cleaned:
        path = _resolve_path(raw, agent=agent)
        if not path.is_file():
            raise ReferenceError(f"Reference image not found: {raw}")
        if not _is_allowed(path, agent=agent):
            raise ReferenceError(f"Reference path is outside workspace/profile: {raw}")
        size = path.stat().st_size
        if size > _MAX_BYTES:
            raise ReferenceError(f"Reference too large ({size // 1024 // 1024} MB): {path.name}")
        mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        if path.suffix.lower() not in _IMAGE_EXT and not mime.startswith("image/"):
            raise ReferenceError(f"Not an image file: {path.name}")
        data = path.read_bytes()
        if mime == "image/jpg":
            mime = "image/jpeg"
        out.append(ReferenceImage(path=path, mime=mime, data=data))
    return out


def user_content(
    prompt: str, refs: list[ReferenceImage], *, size: str = ""
) -> list[dict[str, Any]]:
    text = (prompt or "").strip()
    if size:
        text = f"{text}\nImage size: {size}".strip()
    parts: list[dict[str, Any]] = [{"type": "text", "text": text or "Edit the attached image(s)."}]
    parts.extend(r.chat_part() for r in refs)
    return parts


def _workspace(agent: Any | None) -> Path | None:
    cfg = getattr(agent, "config", None) if agent is not None else None
    root = getattr(cfg, "workspace_root", None) if cfg is not None else None
    if root:
        return Path(str(root)).expanduser().resolve()
    try:
        from holix_media.store import workspace_root

        return workspace_root(agent).resolve()
    except Exception:
        return None


def _resolve_path(raw: str, *, agent: Any | None) -> Path:
    text = raw.strip().strip("`").strip()
    p = Path(text).expanduser()
    if p.is_file():
        return p.resolve()
    ws = _workspace(agent)
    if ws is not None:
        cand = (ws / text).resolve()
        if cand.is_file():
            return cand
    cwd = (Path.cwd() / text).resolve()
    if cwd.is_file():
        return cwd
    return p


def _is_allowed(path: Path, *, agent: Any | None) -> bool:
    resolved = path.resolve()
    jail = False
    try:
        from core.tools.execution_context import is_workspace_jail_enabled

        jail = bool(is_workspace_jail_enabled())
    except Exception:
        jail = False
    if not jail:
        return True
    roots: list[Path] = []
    ws = _workspace(agent)
    if ws is not None:
        roots.append(ws)
    try:
        from core.env_loader import holix_home

        roots.append(Path(holix_home()).expanduser().resolve())
    except Exception:
        pass
    roots.append(Path.cwd().resolve())
    for root in roots:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False
