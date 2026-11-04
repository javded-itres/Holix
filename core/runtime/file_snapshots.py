"""Workspace file snapshots outside the project's own git history.

A bare repository under the profile data dir tracks the workspace with
``GIT_WORK_TREE``. ``.gitignore`` is respected. Revert and redo move the
working tree; they do not rewrite the project's ``.git``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MUTATING = frozenset(
    {
        "write_file",
        "patch_file",
        "apply_patch",
        "delete_file",
        "notebook_edit",
    }
)


def snapshots_enabled() -> bool:
    raw = os.environ.get("HOLIX_FILE_SNAPSHOTS", "").strip().lower()
    if raw in {"1", "on", "true", "yes"}:
        return True
    if raw in {"0", "off", "false", "no"}:
        return False
    try:
        from config import settings

        return bool(getattr(settings, "file_snapshots_enabled", False))
    except Exception:
        return False


def is_mutating_tool(name: str) -> bool:
    return (name or "").strip() in _MUTATING


def _profile_data(profile: str) -> Path:
    from core.profile.names import profile_dir_for_name

    return profile_dir_for_name(profile) / "data" / "file_snapshots"


def _store_dir(profile: str, workspace: Path) -> Path:
    digest = hashlib.sha1(str(workspace.resolve()).encode("utf-8")).hexdigest()[:12]
    return _profile_data(profile) / digest


def _git(git_dir: Path, work_tree: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "Holix"
    env["GIT_AUTHOR_EMAIL"] = "holix@localhost"
    env["GIT_COMMITTER_NAME"] = "Holix"
    env["GIT_COMMITTER_EMAIL"] = "holix@localhost"
    env["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        ["git", f"--git-dir={git_dir}", f"--work-tree={work_tree}", *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )


def _ensure_repo(git_dir: Path, work_tree: Path) -> str | None:
    if not (git_dir / "HEAD").exists():
        git_dir.parent.mkdir(parents=True, exist_ok=True)
        init = subprocess.run(
            ["git", "init", "--bare", str(git_dir)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if init.returncode != 0:
            return (init.stderr or init.stdout or "git init failed").strip()
    _git(git_dir, work_tree, "config", "user.email", "holix@localhost")
    _git(git_dir, work_tree, "config", "user.name", "Holix")
    return None


def _state_path(git_dir: Path) -> Path:
    return git_dir.parent / "turns.json"


def _load_state(git_dir: Path) -> dict[str, Any]:
    path = _state_path(git_dir)
    if not path.is_file():
        return {"commits": [], "redo": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"commits": [], "redo": []}
    if not isinstance(payload, dict):
        return {"commits": [], "redo": []}
    payload.setdefault("commits", [])
    payload.setdefault("redo", [])
    return payload


def _save_state(git_dir: Path, state: dict[str, Any]) -> None:
    path = _state_path(git_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _head(git_dir: Path, work_tree: Path) -> str:
    result = _git(git_dir, work_tree, "rev-parse", "HEAD")
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def capture(
    workspace: str | Path,
    *,
    profile: str = "default",
    label: str = "",
) -> dict[str, Any]:
    """Commit the current workspace into the shadow repo."""
    work_tree = Path(workspace).expanduser().resolve()
    if not work_tree.is_dir():
        return {"ok": False, "error": f"workspace is not a directory: {work_tree}"}
    store = _store_dir(profile, work_tree)
    git_dir = store / "repo.git"
    err = _ensure_repo(git_dir, work_tree)
    if err:
        return {"ok": False, "error": err}
    added = _git(git_dir, work_tree, "add", "-A")
    if added.returncode != 0:
        return {"ok": False, "error": (added.stderr or "git add failed").strip()[:400]}
    message = (label or "snapshot").replace("\n", " ")[:200]
    committed = _git(git_dir, work_tree, "commit", "-m", message, "--allow-empty")
    if committed.returncode != 0 and "nothing to commit" not in (
        (committed.stdout or "") + (committed.stderr or "")
    ):
        return {"ok": False, "error": (committed.stderr or "git commit failed").strip()[:400]}
    sha = _head(git_dir, work_tree)
    state = _load_state(git_dir)
    commits = list(state.get("commits") or [])
    if not commits or commits[-1].get("sha") != sha:
        commits.append({"sha": sha, "label": message})
    state["commits"] = commits[-50:]
    state["redo"] = []
    _save_state(git_dir, state)
    return {"ok": True, "sha": sha, "label": message, "count": len(state["commits"])}


def list_snapshots(workspace: str | Path, *, profile: str = "default") -> list[dict[str, Any]]:
    work_tree = Path(workspace).expanduser().resolve()
    store = _store_dir(profile, work_tree)
    git_dir = store / "repo.git"
    if not git_dir.exists():
        return []
    state = _load_state(git_dir)
    rows = []
    for index, item in enumerate(state.get("commits") or []):
        if isinstance(item, dict):
            rows.append({"index": index, "sha": item.get("sha"), "label": item.get("label")})
    return rows


def _checkout(git_dir: Path, work_tree: Path, sha: str) -> str | None:
    result = _git(git_dir, work_tree, "reset", "--hard", sha)
    if result.returncode != 0:
        return (result.stderr or result.stdout or "reset failed").strip()[:400]
    _git(git_dir, work_tree, "clean", "-fd", "-e", ".git")
    return None


def revert(workspace: str | Path, *, profile: str = "default") -> dict[str, Any]:
    """Restore the previous snapshot and keep the current one on the redo stack."""
    work_tree = Path(workspace).expanduser().resolve()
    git_dir = _store_dir(profile, work_tree) / "repo.git"
    if not git_dir.exists():
        return {"ok": False, "error": "no snapshots"}
    state = _load_state(git_dir)
    commits = list(state.get("commits") or [])
    if len(commits) < 2:
        return {"ok": False, "error": "nothing to revert"}
    current = commits.pop()
    target = commits[-1]
    err = _checkout(git_dir, work_tree, str(target.get("sha") or ""))
    if err:
        return {"ok": False, "error": err}
    redo = list(state.get("redo") or [])
    redo.append(current)
    state["commits"] = commits
    state["redo"] = redo
    _save_state(git_dir, state)
    return {"ok": True, "restored": target.get("sha"), "label": target.get("label")}


def redo(workspace: str | Path, *, profile: str = "default") -> dict[str, Any]:
    work_tree = Path(workspace).expanduser().resolve()
    git_dir = _store_dir(profile, work_tree) / "repo.git"
    if not git_dir.exists():
        return {"ok": False, "error": "no snapshots"}
    state = _load_state(git_dir)
    redo_stack = list(state.get("redo") or [])
    if not redo_stack:
        return {"ok": False, "error": "nothing to redo"}
    item = redo_stack.pop()
    err = _checkout(git_dir, work_tree, str(item.get("sha") or ""))
    if err:
        return {"ok": False, "error": err}
    commits = list(state.get("commits") or [])
    commits.append(item)
    state["commits"] = commits
    state["redo"] = redo_stack
    _save_state(git_dir, state)
    return {"ok": True, "restored": item.get("sha"), "label": item.get("label")}


_captured_turn: dict[str, bool] = {}


def capture_before_mutation(
    tool_name: str,
    *,
    workspace: str | None,
    profile: str | None,
    conversation_id: str | None,
) -> None:
    """One shadow commit per conversation turn, before the first mutating tool."""
    if not snapshots_enabled() or not is_mutating_tool(tool_name):
        return
    if not workspace:
        return
    key = f"{profile or 'default'}:{conversation_id or 'default'}"
    if _captured_turn.get(key):
        return
    try:
        result = capture(workspace, profile=profile or "default", label=f"before {tool_name}")
    except Exception:
        logger.debug("file snapshot failed", exc_info=True)
        return
    if result.get("ok"):
        _captured_turn[key] = True


def mark_turn_open(profile: str | None, conversation_id: str | None) -> None:
    """Allow a new auto snapshot on the next user turn."""
    key = f"{profile or 'default'}:{conversation_id or 'default'}"
    _captured_turn.pop(key, None)
