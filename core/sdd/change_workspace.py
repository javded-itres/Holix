"""Per-conversation SDD pin: git worktree and/or project root."""

from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.profile.names import ProfileNameError, profile_dir_for_name
from core.runtime.git_worktree import WorktreeInfo, worktrees_enabled

logger = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,120}$")
_LOCK = threading.Lock()
_CACHE: dict[str, dict[str, dict[str, Any]]] = {}
_LOADED: set[str] = set()


@dataclass(frozen=True, slots=True)
class ActiveChange:
    change_id: str
    branch: str
    worktree: str
    clone: str
    project: str = ""
    # Absolute directory that owns openspec/ (product clone or nested project).
    # Used as workspace overlay when no live git worktree is bound.
    project_root: str = ""

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def _safe_cid(raw: str) -> str:
    text = (raw or "default").strip() or "default"
    if not _ID_RE.fullmatch(text):
        return "default"
    return text


def _path(profile: str) -> Path | None:
    try:
        return profile_dir_for_name(profile) / "data" / "sdd_active.json"
    except ProfileNameError:
        return None


def _ensure_loaded(profile: str) -> None:
    name = (profile or "default").strip() or "default"
    if name in _LOADED:
        return
    _LOADED.add(name)
    path = _path(name)
    sessions: dict[str, dict[str, Any]] = {}
    if path is not None and path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            raw = payload.get("sessions") if isinstance(payload, dict) else None
            if isinstance(raw, dict):
                sessions = {str(k): v for k, v in raw.items() if isinstance(v, dict)}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            logger.debug("sdd active load failed for %s", name, exc_info=True)
    _CACHE[name] = sessions


def _save(profile: str) -> None:
    name = (profile or "default").strip() or "default"
    path = _path(name)
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"sessions": _CACHE.get(name) or {}}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        logger.debug("sdd active save failed for %s", name, exc_info=True)


def _parse(raw: dict[str, Any] | None) -> ActiveChange | None:
    if not raw:
        return None
    change_id = str(raw.get("change_id") or "").strip()
    worktree = str(raw.get("worktree") or "").strip()
    project_root = str(raw.get("project_root") or "").strip()
    if not worktree and not project_root:
        return None
    return ActiveChange(
        change_id=change_id,
        branch=str(raw.get("branch") or "").strip(),
        worktree=worktree,
        clone=str(raw.get("clone") or "").strip(),
        project=str(raw.get("project") or "").strip(),
        project_root=project_root,
    )


def _write_bind(profile: str, conversation_id: str, active: ActiveChange) -> ActiveChange:
    name = (profile or "default").strip() or "default"
    cid = _safe_cid(conversation_id)
    with _LOCK:
        _ensure_loaded(name)
        _CACHE.setdefault(name, {})[cid] = active.as_dict()
        _save(name)
    return active


def get_active_change(profile: str, conversation_id: str) -> ActiveChange | None:
    name = (profile or "default").strip() or "default"
    cid = _safe_cid(conversation_id)
    with _LOCK:
        _ensure_loaded(name)
        return _parse((_CACHE.get(name) or {}).get(cid))


def bind_active_change(
    profile: str,
    conversation_id: str,
    info: WorktreeInfo | ActiveChange,
    *,
    project: str = "",
    project_root: str = "",
) -> ActiveChange:
    if isinstance(info, WorktreeInfo):
        pr = (project_root or "").strip() or str(info.clone)
        active = ActiveChange(
            change_id=info.change_id,
            branch=info.branch,
            worktree=str(info.worktree),
            clone=str(info.clone),
            project=(project or "").strip(),
            project_root=pr,
        )
    else:
        active = info
        extra = (project_root or "").strip()
        if extra and not active.project_root:
            active = ActiveChange(
                change_id=active.change_id,
                branch=active.branch,
                worktree=active.worktree,
                clone=active.clone,
                project=active.project or (project or "").strip(),
                project_root=extra,
            )
    return _write_bind(profile, conversation_id, active)


def bind_active_project(
    profile: str,
    conversation_id: str,
    project_root: str | Path,
    *,
    project: str = "",
) -> ActiveChange | None:
    """Pin the conversation to the directory that owns ``openspec/``."""
    try:
        root = Path(project_root).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if not root.is_dir():
        return None
    existing = get_active_change(profile, conversation_id)
    rel = (project or "").strip()
    if existing is not None and existing.worktree:
        active = ActiveChange(
            change_id=existing.change_id,
            branch=existing.branch,
            worktree=existing.worktree,
            clone=existing.clone,
            project=rel or existing.project,
            project_root=str(root),
        )
    else:
        active = ActiveChange(
            change_id="",
            branch="",
            worktree="",
            clone="",
            project=rel,
            project_root=str(root),
        )
    return _write_bind(profile, conversation_id, active)


def _demote_to_project_pin(raw: dict[str, Any] | None) -> dict[str, str] | None:
    parsed = _parse(raw)
    if parsed is None:
        return None
    root = (parsed.project_root or "").strip()
    if not root:
        return None
    return ActiveChange(
        change_id="",
        branch="",
        worktree="",
        clone="",
        project=parsed.project,
        project_root=root,
    ).as_dict()


def clear_active_change(profile: str, conversation_id: str) -> None:
    """Drop the git worktree bind; keep the SDD project pin when present."""
    name = (profile or "default").strip() or "default"
    cid = _safe_cid(conversation_id)
    with _LOCK:
        _ensure_loaded(name)
        sessions = _CACHE.get(name) or {}
        kept = _demote_to_project_pin(sessions.get(cid))
        if kept is None:
            sessions.pop(cid, None)
        else:
            sessions[cid] = kept
        _save(name)


def clear_binds_for_change(profile: str, change_id: str) -> int:
    """Drop worktree binds for *change_id*; keep project pins. Returns count."""
    wanted = (change_id or "").strip().lower()
    if not wanted:
        return 0
    name = (profile or "default").strip() or "default"
    cleared = 0
    with _LOCK:
        _ensure_loaded(name)
        sessions = _CACHE.get(name) or {}
        drop = [
            key
            for key, raw in sessions.items()
            if str((raw or {}).get("change_id") or "").strip().lower() == wanted
        ]
        for key in drop:
            kept = _demote_to_project_pin(sessions.get(key))
            if kept is None:
                sessions.pop(key, None)
            else:
                sessions[key] = kept
            cleared += 1
        if drop:
            _save(name)
    return cleared


def reset_active_change_store() -> None:
    with _LOCK:
        _CACHE.clear()
        _LOADED.clear()


def inherit_active_change(
    profile: str, parent_conversation_id: str, child_conversation_id: str
) -> ActiveChange | None:
    parent = get_active_change(profile, parent_conversation_id)
    if parent is None:
        return None
    return bind_active_change(profile, child_conversation_id, parent)


def overlay_workspace_root(
    profile: str | None = None,
    conversation_id: str | None = None,
) -> str | None:
    """Pinned workspace: live git worktree, else SDD project root."""
    try:
        from core.tools.execution_context import get_conversation_id, get_profile_name

        prof = (profile or get_profile_name() or "default").strip() or "default"
        cid = (conversation_id or get_conversation_id() or "default").strip() or "default"
    except Exception:
        if not profile:
            return None
        prof = profile
        cid = (conversation_id or "default").strip() or "default"
    active = get_active_change(prof, cid)
    if active is None:
        return None
    pin = (active.project_root or "").strip()
    if pin:
        try:
            from core.sdd.product_layout import load_product_layout

            layout = load_product_layout(Path(pin))
        except Exception:
            layout = None
        if layout is not None and layout.has_dedicated_spec:
            product = Path(layout.project_root).expanduser()
            if product.is_dir():
                return str(product.resolve())
    if worktrees_enabled() and active.worktree:
        path = Path(active.worktree).expanduser()
        if path.is_dir():
            return str(path.resolve())
    if pin:
        path = Path(pin).expanduser()
        if path.is_dir():
            return str(path.resolve())
    return None


def format_active_change_line(active: ActiveChange | None) -> str:
    if active is None:
        return ""
    if active.worktree and active.change_id:
        branch = active.branch or f"change/{active.change_id}"
        return f"SDD {active.change_id} · {branch} · worktree"
    if active.project_root:
        rel = active.project or active.project_root
        return f"SDD project pin · {rel}"
    return ""


def format_active_change_prompt_block(active: ActiveChange | None) -> str:
    if active is None:
        return ""
    layout = None
    if active.project_root:
        try:
            from core.sdd.product_layout import load_product_layout

            layout = load_product_layout(Path(active.project_root))
        except Exception:
            layout = None
    dedicated = bool(layout is not None and layout.has_dedicated_spec)
    if dedicated and layout is not None and active.project_root:
        spec = layout.spec_root
        lines = [
            "## Active SDD product (multi-repo)\n",
            f"**Workspace (file tools / terminal):** `{active.project_root}`",
            "All member clones of this product are in scope. "
            "Do not list or edit sibling Studio products.",
        ]
        if spec is not None:
            lines.append(f"**Specs (`sdd_*` only):** `{spec}`")
            lines.append(
                "Do not create `openspec/` inside code clones. Implement in repos with `role=code`."
            )
        if active.worktree and active.change_id:
            lines.append(
                f"SDD change `{active.change_id}` uses spec worktree `{active.worktree}` "
                "(artifacts only, not the file-tool jail)."
            )
        return "\n".join(lines)
    if active.worktree and active.change_id:
        return (
            "## Active SDD change (git worktree)\n\n"
            f"You are working on SDD change `{active.change_id}` "
            f"(branch `{active.branch or 'change/' + active.change_id}`).\n"
            f"**Workspace is the git worktree:** `{active.worktree}`\n"
            "File tools, terminal, and SDD artifacts use this directory. "
            "Do not edit the main clone working tree. "
            "Merge the default branch with `git merge main` (or `master`) "
            "**from this worktree**. Do not `cd` to the clone and do not set "
            "GIT_DIR. Local `main` is already in this repo — do not "
            "`git fetch origin` unless a remote exists. "
            f"Main clone (git objects / default branch checkout): `{active.clone}`."
        )
    if active.project_root:
        return (
            "## Active SDD project (workspace pin)\n\n"
            f"**Workspace is this SDD project directory:** `{active.project_root}`\n"
            "File tools, terminal, and SDD artifacts stay inside it. "
            "Do not list or edit sibling projects or the profile workspace root."
        )
    return ""


def resolve_subagent_workspace(
    *,
    profile: str,
    parent_conversation_id: str,
    child_conversation_id: str,
    fallback: str | None,
) -> str | None:
    inherited = inherit_active_change(profile, parent_conversation_id, child_conversation_id)
    if inherited is None:
        return fallback
    pin = (inherited.project_root or "").strip()
    if pin:
        try:
            from core.sdd.product_layout import load_product_layout

            layout = load_product_layout(Path(pin))
        except Exception:
            layout = None
        if layout is not None and layout.has_dedicated_spec:
            product = Path(layout.project_root).expanduser()
            if product.is_dir():
                return str(product.resolve())
    if inherited.worktree:
        wt = Path(inherited.worktree).expanduser()
        if wt.is_dir():
            return str(wt.resolve())
    if pin:
        root = Path(pin).expanduser()
        if root.is_dir():
            return str(root.resolve())
    return fallback
