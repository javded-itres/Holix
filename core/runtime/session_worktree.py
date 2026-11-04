"""Bind a chat session to its own git worktree.

This is independent of SDD. The worktree lives under ``.holix/worktrees/``,
on branch ``session/<id>``. A setup script and a copied ``.env`` run once
when the worktree is created. File tools use that checkout while it is bound.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from core.runtime.git_worktree import (
    WorktreeUnavailable,
    add_change_worktree,
    clone_root,
    run_git,
    show_toplevel,
    worktree_porcelain,
)


def _path(profile: str) -> Path | None:
    try:
        from core.profile.names import profile_dir_for_name

        return profile_dir_for_name(profile) / "data" / "session_worktrees.json"
    except Exception:
        return None


def _load(profile: str) -> dict[str, Any]:
    path = _path(profile)
    if path is None or not path.is_file():
        return {"sessions": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"sessions": {}}
    if not isinstance(payload, dict):
        return {"sessions": {}}
    payload.setdefault("sessions", {})
    return payload


def _save(profile: str, payload: dict[str, Any]) -> None:
    path = _path(profile)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_binding(profile: str, conversation_id: str) -> dict[str, Any] | None:
    raw = (_load(profile).get("sessions") or {}).get(conversation_id or "default")
    return raw if isinstance(raw, dict) else None


def overlay_workspace(profile: str | None, conversation_id: str | None) -> str | None:
    binding = get_binding(profile or "default", conversation_id or "default")
    if not binding:
        return None
    path = str(binding.get("worktree") or "").strip()
    if path and Path(path).is_dir():
        return path
    return None


def _session_id(conversation_id: str) -> str:
    raw = (conversation_id or "session").strip().lower().replace("_", "-")
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in raw)
    cleaned = cleaned.strip("-")[:48] or "session"
    if not cleaned[0].isalnum():
        cleaned = f"s{cleaned}"
    return cleaned


def _bootstrap(clone: Path, worktree: Path) -> list[str]:
    notes: list[str] = []
    env_src = clone / ".env"
    env_dst = worktree / ".env"
    if env_src.is_file() and not env_dst.exists():
        try:
            shutil.copy2(env_src, env_dst)
            notes.append("copied .env")
        except OSError:
            notes.append("env copy failed")
    script = clone / ".holix" / "worktree-setup.sh"
    if script.is_file():
        try:
            subprocess.run(
                ["bash", str(script)],
                cwd=str(worktree),
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
                env={**os.environ, "HOLIX_WORKTREE": str(worktree)},
            )
            notes.append("ran worktree-setup.sh")
        except (OSError, subprocess.TimeoutExpired):
            notes.append("setup script failed")
    return notes


def bind_session(
    workspace: str | Path,
    *,
    profile: str,
    conversation_id: str,
    base: str = "",
) -> dict[str, Any]:
    root = Path(workspace).expanduser().resolve()
    clone = clone_root(root) or show_toplevel(root)
    if clone is None:
        return {"ok": False, "error": "workspace is not a git repository"}
    session_id = _session_id(conversation_id)
    try:
        info = add_change_worktree(
            clone,
            session_id,
            start_point=base,
            profile=profile,
            force=True,
            branch_prefix="session",
        )
    except WorktreeUnavailable as exc:
        return {"ok": False, "error": str(exc)}
    notes = _bootstrap(clone, info.worktree)
    payload = _load(profile)
    payload.setdefault("sessions", {})[conversation_id or "default"] = {
        "session_id": session_id,
        "branch": info.branch,
        "worktree": str(info.worktree),
        "clone": str(info.clone),
        "base": base or "HEAD",
    }
    _save(profile, payload)
    return {
        "ok": True,
        "session_id": session_id,
        "branch": info.branch,
        "worktree": str(info.worktree),
        "notes": notes,
    }


def leave_session(profile: str, conversation_id: str) -> dict[str, Any]:
    payload = _load(profile)
    sessions = payload.setdefault("sessions", {})
    removed = sessions.pop(conversation_id or "default", None)
    _save(profile, payload)
    return {"ok": True, "removed": bool(removed)}


def diff_session(profile: str, conversation_id: str) -> dict[str, Any]:
    binding = get_binding(profile, conversation_id)
    if not binding:
        return {"ok": False, "error": "no session worktree"}
    worktree = Path(str(binding.get("worktree") or ""))
    base = str(binding.get("base") or "HEAD")
    try:
        result = run_git(worktree, "diff", "--stat", base, check=False)
    except WorktreeUnavailable as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "branch": binding.get("branch"),
        "worktree": str(worktree),
        "stat": (result.stdout or "").strip(),
        "porcelain": worktree_porcelain(worktree),
    }
