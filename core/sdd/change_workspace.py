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
    # User-picked session pin: sdd_create_change must not steal this conversation.
    locked: bool = False

    def as_dict(self) -> dict[str, Any]:
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
        locked=bool(raw.get("locked")),
    )


def _write_bind(
    profile: str,
    conversation_id: str,
    active: ActiveChange,
    *,
    force: bool = False,
) -> ActiveChange:
    name = (profile or "default").strip() or "default"
    cid = _safe_cid(conversation_id)
    with _LOCK:
        _ensure_loaded(name)
        sessions = _CACHE.setdefault(name, {})
        prev = _parse(sessions.get(cid))
        if prev is not None and prev.locked and not force and not active.locked:
            return prev
        sessions[cid] = active.as_dict()
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
    locked: bool = False,
    force: bool = False,
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
            locked=bool(locked),
        )
    else:
        active = info
        if locked and not active.locked:
            active = ActiveChange(
                change_id=active.change_id,
                branch=active.branch,
                worktree=active.worktree,
                clone=active.clone,
                project=active.project or (project or "").strip(),
                project_root=active.project_root,
                locked=True,
            )
        extra = (project_root or "").strip()
        if extra and not active.project_root:
            active = ActiveChange(
                change_id=active.change_id,
                branch=active.branch,
                worktree=active.worktree,
                clone=active.clone,
                project=active.project or (project or "").strip(),
                project_root=extra,
                locked=active.locked,
            )
    return _write_bind(profile, conversation_id, active, force=force or locked)


def bind_active_project(
    profile: str,
    conversation_id: str,
    project_root: str | Path,
    *,
    project: str = "",
    locked: bool = False,
    replace_worktree: bool = False,
    force: bool = False,
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
    if existing is not None and existing.locked and not force and not locked:
        return existing
    if existing is not None and existing.worktree and not replace_worktree:
        active = ActiveChange(
            change_id=existing.change_id,
            branch=existing.branch,
            worktree=existing.worktree,
            clone=existing.clone,
            project=rel or existing.project,
            project_root=str(root),
            locked=bool(locked or existing.locked),
        )
    else:
        active = ActiveChange(
            change_id="",
            branch="",
            worktree="",
            clone="",
            project=rel,
            project_root=str(root),
            locked=bool(locked),
        )
    return _write_bind(profile, conversation_id, active, force=force or locked)


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
        locked=parsed.locked,
    ).as_dict()


def drop_active_change(profile: str, conversation_id: str) -> None:
    """Remove worktree *and* project pin so the session uses the profile workspace."""
    name = (profile or "default").strip() or "default"
    cid = _safe_cid(conversation_id)
    with _LOCK:
        _ensure_loaded(name)
        sessions = _CACHE.get(name) or {}
        if cid in sessions:
            sessions.pop(cid, None)
            _save(name)


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


def _layout_for_active(active: ActiveChange) -> Any | None:
    try:
        from core.sdd.product_layout import load_product_layout
    except Exception:
        return None
    for raw in (active.project_root, active.worktree, active.clone):
        text = (raw or "").strip()
        if not text:
            continue
        try:
            layout = load_product_layout(Path(text))
        except Exception:
            layout = None
        if layout is not None:
            return layout
    return None


def _is_multi_product(layout: Any | None) -> bool:
    if layout is None:
        return False
    return bool(getattr(layout, "has_dedicated_spec", False) or getattr(layout, "is_multi", False))


def compose_active_change(
    *,
    change_id: str,
    worktree: str,
    clone: str = "",
    project: str = "",
    branch: str = "",
    project_root: str = "",
) -> ActiveChange:
    """Build a pin that keeps the git worktree and the product/project root.

    Multi-repo products (shared ``openspec`` / ``role=spec``) store the spec
    worktree on ``worktree`` but keep ``project_root`` as the product so file
    tools still see every code clone.
    """
    wt = (worktree or "").strip()
    clone_s = (clone or "").strip()
    pr = (project_root or "").strip()
    cid = (change_id or "").strip()
    layout = None
    start = pr or wt or clone_s
    if start:
        try:
            from core.sdd.product_layout import load_product_layout

            layout = load_product_layout(Path(start))
        except Exception:
            layout = None
    if layout is not None and _is_multi_product(layout):
        try:
            pr = str(Path(layout.project_root).expanduser().resolve())
        except (OSError, RuntimeError, ValueError):
            pass
    elif not pr and clone_s:
        try:
            clone_path = Path(clone_s).expanduser()
            if clone_path.is_dir():
                pr = str(clone_path.resolve())
        except (OSError, RuntimeError, ValueError):
            pass
    return ActiveChange(
        change_id=cid,
        branch=(branch or "").strip() or (f"change/{cid}" if cid else ""),
        worktree=wt,
        clone=clone_s,
        project=(project or "").strip(),
        project_root=pr,
    )


def file_workspace_root(active: ActiveChange | None) -> str | None:
    """Directory for file tools / terminal (product root on multi-repo)."""
    if active is None:
        return None
    layout = _layout_for_active(active)
    if _is_multi_product(layout) and layout is not None:
        product = Path(layout.project_root).expanduser()
        if product.is_dir():
            return str(product.resolve())
    if worktrees_enabled() and active.worktree:
        path = Path(active.worktree).expanduser()
        if path.is_dir():
            return str(path.resolve())
    pin = (active.project_root or "").strip()
    if pin:
        path = Path(pin).expanduser()
        if path.is_dir():
            return str(path.resolve())
    return None


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
    return file_workspace_root(get_active_change(prof, cid))


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
    layout = _layout_for_active(active)
    if _is_multi_product(layout) and layout is not None:
        product = str(Path(layout.project_root).expanduser().resolve())
        spec = getattr(layout, "spec_root", None)
        if spec is None:
            infer = getattr(layout, "inferred_openspec_root", None)
            spec = infer() if callable(infer) else None
        lines = [
            "## Active SDD product (multi-repo)\n",
            f"**Workspace (file tools / terminal):** `{product}`",
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
            "Do **not** `cd` into sibling `.holix/worktrees/*` folders. "
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
            "This session is on the **main clone**, not an SDD worktree. "
            "Do **not** write into `.holix/worktrees/` unless the user asked "
            "to switch worktree. Do not list or edit sibling projects."
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
    return file_workspace_root(inherited) or fallback
