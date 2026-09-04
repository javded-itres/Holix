"""Per-conversation active SDD change → git worktree binding."""

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
    if not change_id or not worktree:
        return None
    return ActiveChange(
        change_id=change_id,
        branch=str(raw.get("branch") or "").strip(),
        worktree=worktree,
        clone=str(raw.get("clone") or "").strip(),
        project=str(raw.get("project") or "").strip(),
    )


def get_active_change(profile: str, conversation_id: str) -> ActiveChange | None:
    if not worktrees_enabled():
        return None
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
) -> ActiveChange:
    if isinstance(info, WorktreeInfo):
        active = ActiveChange(
            change_id=info.change_id,
            branch=info.branch,
            worktree=str(info.worktree),
            clone=str(info.clone),
            project=(project or "").strip(),
        )
    else:
        active = info
    name = (profile or "default").strip() or "default"
    cid = _safe_cid(conversation_id)
    with _LOCK:
        _ensure_loaded(name)
        _CACHE.setdefault(name, {})[cid] = active.as_dict()
        _save(name)
    return active


def clear_active_change(profile: str, conversation_id: str) -> None:
    name = (profile or "default").strip() or "default"
    cid = _safe_cid(conversation_id)
    with _LOCK:
        _ensure_loaded(name)
        sessions = _CACHE.get(name) or {}
        sessions.pop(cid, None)
        _save(name)


def clear_binds_for_change(profile: str, change_id: str) -> int:
    """Drop every session bind for *change_id* in this profile. Returns count."""
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
            sessions.pop(key, None)
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
    """Worktree path for the active SDD change, if bound."""
    if not worktrees_enabled():
        return None
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
    path = Path(active.worktree).expanduser()
    if not path.is_dir():
        return None
    return str(path.resolve())


def format_active_change_line(active: ActiveChange | None) -> str:
    if active is None:
        return ""
    branch = active.branch or f"change/{active.change_id}"
    return f"SDD {active.change_id} · {branch} · worktree"


def format_active_change_prompt_block(active: ActiveChange | None) -> str:
    if active is None:
        return ""
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


def resolve_subagent_workspace(
    *,
    profile: str,
    parent_conversation_id: str,
    child_conversation_id: str,
    fallback: str | None,
) -> str | None:
    inherited = inherit_active_change(profile, parent_conversation_id, child_conversation_id)
    if inherited is not None:
        return inherited.worktree
    return fallback
