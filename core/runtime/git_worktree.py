"""Git worktrees for SDD changes (linked checkouts, shared ``.git``)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_DIRNAME = ".holix/worktrees"
DEFAULT_MAX = 8
_GITIGNORE_LINE = ".holix/worktrees/"
_CHANGE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-_]{0,63}$")
_LOCK = threading.Lock()
_CLONE_LOCKS: dict[str, threading.Lock] = {}


class WorktreeUnavailable(RuntimeError):
    """Host cannot create or use a Holix git worktree."""


class WorktreeLimitError(WorktreeUnavailable):
    """Too many Holix worktrees under the clone."""


class WorktreeConflictError(WorktreeUnavailable):
    """Branch or path already used by another worktree of this clone."""


class WorktreeDirtyError(WorktreeUnavailable):
    """``git worktree remove`` refused because the tree has local changes."""

    def __init__(self, message: str, *, porcelain: str = "") -> None:
        super().__init__(message)
        self.porcelain = porcelain


@dataclass(frozen=True, slots=True)
class WorktreeInfo:
    change_id: str
    branch: str
    worktree: Path
    clone: Path
    git_common_dir: Path


def git_available() -> bool:
    return shutil.which("git") is not None


def worktrees_enabled() -> bool:
    raw = os.environ.get("HOLIX_WORKTREE", "").strip().lower()
    if raw in {"0", "off", "false", "no"}:
        return False
    if raw in {"1", "on", "true", "yes"}:
        return True
    try:
        from config import settings

        return bool(getattr(settings, "git_worktrees_enabled", True))
    except Exception:
        return True


def worktrees_dirname() -> str:
    try:
        from config import settings

        raw = str(getattr(settings, "git_worktrees_dirname", "") or "").strip()
        if raw:
            return raw.strip("/") or DEFAULT_DIRNAME
    except Exception:
        pass
    return DEFAULT_DIRNAME


def max_worktrees() -> int:
    try:
        from config import settings

        n = int(getattr(settings, "git_worktrees_max", DEFAULT_MAX) or DEFAULT_MAX)
        return max(1, n)
    except Exception:
        return DEFAULT_MAX


def sanitize_change_id(change_id: str) -> str:
    cid = (change_id or "").strip().lower().replace(" ", "-")
    if not _CHANGE_ID_RE.fullmatch(cid):
        raise WorktreeUnavailable(
            "change_id must be 1–64 chars: lowercase letters, digits, hyphen, underscore "
            f"(got {change_id!r})"
        )
    return cid


def branch_for_change(change_id: str) -> str:
    return f"change/{sanitize_change_id(change_id)}"


def run_git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    if not git_available():
        raise WorktreeUnavailable("git is not installed")
    env = os.environ.copy()
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    env.setdefault("GIT_OPTIONAL_LOCKS", "0")
    try:
        result = subprocess.run(
            ["git", "-c", "safe.directory=*", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorktreeUnavailable(str(exc)) from exc
    if check and result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip().replace("\n", " ")[:400]
        raise WorktreeUnavailable(err or f"git {' '.join(args)} failed")
    return result


def git_common_dir(path: Path | str) -> Path | None:
    root = Path(path).expanduser()
    if not root.exists():
        return None
    try:
        result = run_git(root, "rev-parse", "--git-common-dir", check=False)
    except WorktreeUnavailable:
        return None
    if result.returncode != 0:
        return None
    raw = (result.stdout or "").strip()
    if not raw:
        return None
    common = Path(raw)
    if not common.is_absolute():
        common = (root / common).resolve()
    else:
        common = common.resolve()
    return common if common.exists() else None


def clone_root(path: Path | str) -> Path | None:
    common = git_common_dir(path)
    if common is None:
        return None
    if common.name == ".git":
        return common.parent
    return None


def show_toplevel(path: Path | str) -> Path | None:
    root = Path(path).expanduser()
    if not root.exists():
        return None
    try:
        result = run_git(root, "rev-parse", "--show-toplevel", check=False)
    except WorktreeUnavailable:
        return None
    if result.returncode != 0:
        return None
    raw = (result.stdout or "").strip()
    if not raw:
        return None
    return Path(raw).resolve()


def is_linked_worktree(path: Path | str) -> bool:
    top = show_toplevel(path)
    main = clone_root(path)
    if top is None or main is None:
        return False
    return top != main


def worktree_path_for(clone: Path, change_id: str) -> Path:
    cid = sanitize_change_id(change_id)
    return (clone / worktrees_dirname() / cid).resolve()


def _clone_lock(clone: Path) -> threading.Lock:
    key = str(clone.resolve())
    with _LOCK:
        lock = _CLONE_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _CLONE_LOCKS[key] = lock
        return lock


def ensure_gitignore(clone: Path) -> None:
    path = clone / ".gitignore"
    try:
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError:
        return
    if _GITIGNORE_LINE in text.splitlines() or f"{_GITIGNORE_LINE}\n" in text:
        return
    try:
        prefix = "" if not text or text.endswith("\n") else "\n"
        path.write_text(text + f"{prefix}{_GITIGNORE_LINE}\n", encoding="utf-8")
    except OSError:
        pass


def list_holix_worktrees(clone: Path) -> list[WorktreeInfo]:
    main = clone_root(clone) or clone.resolve()
    common = git_common_dir(main)
    if common is None:
        return []
    result = run_git(main, "worktree", "list", "--porcelain", check=False)
    if result.returncode != 0:
        return []
    prefix = (main / worktrees_dirname()).resolve()
    out: list[WorktreeInfo] = []
    current: dict[str, str] = {}

    def flush() -> None:
        raw = (current.get("worktree") or "").strip()
        if not raw:
            current.clear()
            return
        wt = Path(raw).resolve()
        try:
            wt.relative_to(prefix)
        except ValueError:
            current.clear()
            return
        branch = (current.get("branch") or "").strip()
        if branch.startswith("refs/heads/"):
            branch = branch[len("refs/heads/") :]
        cid = wt.name
        out.append(
            WorktreeInfo(
                change_id=cid,
                branch=branch or branch_for_change(cid) if _CHANGE_ID_RE.fullmatch(cid) else branch,
                worktree=wt,
                clone=main,
                git_common_dir=common,
            )
        )
        current.clear()

    for line in (result.stdout or "").splitlines():
        if not line.strip():
            flush()
            continue
        key, _, value = line.partition(" ")
        current[key] = value
    flush()
    return out


def _ref_exists(clone: Path, ref: str) -> bool:
    result = run_git(clone, "rev-parse", "--verify", "--quiet", ref, check=False)
    return result.returncode == 0


def add_change_worktree(
    clone: Path,
    change_id: str,
    *,
    start_point: str = "",
) -> WorktreeInfo:
    if not worktrees_enabled():
        raise WorktreeUnavailable("HOLIX_WORKTREE=0")
    if not git_available():
        raise WorktreeUnavailable("git is not installed")
    cid = sanitize_change_id(change_id)
    main = clone_root(clone) or Path(clone).expanduser().resolve()
    if git_common_dir(main) is None:
        raise WorktreeUnavailable(f"not a git repository: {main}")
    dest = worktree_path_for(main, cid)
    branch = branch_for_change(cid)
    lock = _clone_lock(main)
    with lock:
        existing = [w for w in list_holix_worktrees(main) if w.change_id == cid]
        if existing:
            info = existing[0]
            if info.worktree == dest:
                return info
            raise WorktreeConflictError(f"change {cid} already has a worktree at {info.worktree}")
        if dest.exists():
            top = show_toplevel(dest)
            if top == dest:
                common = git_common_dir(dest)
                if common is None:
                    raise WorktreeConflictError(f"path exists and is not a worktree: {dest}")
                return WorktreeInfo(
                    change_id=cid,
                    branch=branch,
                    worktree=dest,
                    clone=main,
                    git_common_dir=common,
                )
            raise WorktreeConflictError(f"worktree path already exists: {dest}")
        live = list_holix_worktrees(main)
        if len(live) >= max_worktrees():
            raise WorktreeLimitError(
                f"at most {max_worktrees()} Holix worktrees under {main / worktrees_dirname()}"
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        ensure_gitignore(main)
        start = (start_point or "").strip()
        if _ref_exists(main, branch):
            run_git(main, "worktree", "add", str(dest), branch)
        elif start:
            run_git(main, "worktree", "add", "-b", branch, str(dest), start)
        else:
            run_git(main, "worktree", "add", "-b", branch, str(dest))
        common = git_common_dir(dest)
        if common is None:
            raise WorktreeUnavailable(f"worktree add produced no git dir: {dest}")
        return WorktreeInfo(
            change_id=cid,
            branch=branch,
            worktree=dest,
            clone=main,
            git_common_dir=common,
        )


def worktree_porcelain(path: Path | str) -> str:
    """``git status --porcelain`` in *path*, or empty if git fails."""
    root = Path(path).expanduser()
    if not root.exists():
        return ""
    try:
        result = run_git(root, "status", "--porcelain", check=False)
    except WorktreeUnavailable:
        return ""
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def dirty_paths(path: Path | str) -> list[str]:
    """Working-tree paths from porcelain status (renames → destination)."""
    out: list[str] = []
    for line in worktree_porcelain(path).splitlines():
        if len(line) < 2:
            continue
        rest = line[2:]
        if rest.startswith(" "):
            rest = rest[1:]
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        out.append(rest.strip().strip('"'))
    return out


def _only_openspec_dirty(paths: list[str]) -> bool:
    for raw in paths:
        norm = raw.replace("\\", "/").removeprefix("./")
        if norm == ".gitignore" or norm == "openspec" or norm.startswith("openspec/"):
            continue
        return False
    return True


def change_is_archived_on_disk(worktree: Path | str, change_id: str) -> bool:
    """True when ``openspec/changes/<id>`` is gone and an archive folder exists."""
    cid = sanitize_change_id(change_id)
    root = Path(worktree)
    if (root / "openspec" / "changes" / cid).is_dir():
        return False
    arch = root / "openspec" / "changes" / "archive"
    if not arch.is_dir():
        return False
    try:
        children = list(arch.iterdir())
    except OSError:
        return False
    suffix = f"-{cid}"
    return any(
        child.is_dir() and (child.name == cid or child.name.endswith(suffix)) for child in children
    )


def remove_change_worktree(clone: Path, change_id: str, *, force: bool = False) -> bool:
    """Unregister and delete a Holix worktree.

    Without *force*, a dirty tree raises ``WorktreeDirtyError`` and is left intact.
    """
    cid = sanitize_change_id(change_id)
    main = clone_root(clone) or Path(clone).expanduser().resolve()
    dest = worktree_path_for(main, cid)
    live = [w for w in list_holix_worktrees(main) if w.change_id == cid]
    if live and live[0].worktree != dest:
        dest = live[0].worktree
    if not dest.exists() and not live:
        with _clone_lock(main):
            run_git(main, "worktree", "prune", check=False)
        return False
    args = ["worktree", "remove"]
    if force:
        args.append("--force")
    args.append(str(dest))
    with _clone_lock(main):
        result = run_git(main, *args, check=False)
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip().replace("\n", " ")[:400]
            if dest.exists() and not force:
                raise WorktreeDirtyError(
                    err or f"worktree is dirty: {dest}",
                    porcelain=worktree_porcelain(dest),
                )
            if force and dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            elif dest.exists():
                raise WorktreeUnavailable(err or f"git worktree remove failed: {dest}")
        elif dest.exists():
            if force:
                shutil.rmtree(dest, ignore_errors=True)
            else:
                raise WorktreeDirtyError(
                    f"git worktree remove left files: {dest}",
                    porcelain=worktree_porcelain(dest),
                )
        run_git(main, "worktree", "prune", check=False)
    return True


def _commit_openspec(worktree: Path, change_id: str) -> bool:
    """Stage openspec (+ .gitignore) and commit. True if a commit was created."""
    to_add = ["openspec"]
    if (worktree / ".gitignore").is_file():
        to_add.append(".gitignore")
    run_git(worktree, "add", "-A", "--", *to_add, check=False)
    cached = run_git(worktree, "diff", "--cached", "--quiet", check=False)
    if cached.returncode == 0:
        return False
    run_git(
        worktree,
        "commit",
        "--no-gpg-sign",
        "-m",
        f"sdd_archive {change_id}",
    )
    return True


def release_change_worktree(
    start: Path | str,
    change_id: str,
    *,
    profile: str | None = None,
    commit_openspec: bool = True,
) -> dict[str, Any]:
    """After ``sdd_archive``: commit openspec-only dirt, then remove if clean.

    Extra uncommitted files (implementation WIP) keep the tree and return
    ``reason=dirty`` plus porcelain status. Not a worktree → no-op.
    """
    if not worktrees_enabled():
        return {"ok": True, "removed": False, "reason": "disabled"}
    cid = sanitize_change_id(change_id)
    root = Path(start).expanduser().resolve()
    top = show_toplevel(root)
    main = clone_root(root)
    if top is None or main is None:
        return {"ok": True, "removed": False, "reason": "not_git"}
    dest = worktree_path_for(main, cid)
    if top == main:
        if dest.is_dir() and show_toplevel(dest) == dest:
            top = dest
        else:
            return {"ok": True, "removed": False, "reason": "not_a_worktree"}

    porcelain = worktree_porcelain(top)
    paths = dirty_paths(top)
    committed = False
    if paths and commit_openspec and _only_openspec_dirty(paths):
        try:
            committed = _commit_openspec(top, cid)
            porcelain = worktree_porcelain(top)
            paths = dirty_paths(top)
        except WorktreeUnavailable as exc:
            return {
                "ok": True,
                "removed": False,
                "reason": "commit_failed",
                "error": str(exc),
                "status": porcelain,
                "worktree": str(top),
            }
    if paths:
        return {
            "ok": True,
            "removed": False,
            "reason": "dirty",
            "committed": committed,
            "status": porcelain[:800],
            "worktree": str(top),
            "message": (
                "Worktree has uncommitted files besides the SDD archive. "
                "Commit or stash them; Holix will not delete a dirty tree."
            ),
        }
    try:
        remove_change_worktree(main, cid, force=False)
    except WorktreeUnavailable as exc:
        return {
            "ok": True,
            "removed": False,
            "reason": "remove_failed",
            "error": str(exc),
            "status": getattr(exc, "porcelain", "") or porcelain,
            "worktree": str(top),
        }
    if profile:
        try:
            from core.sdd.change_workspace import clear_binds_for_change

            clear_binds_for_change(profile, cid)
        except Exception:
            pass
    return {
        "ok": True,
        "removed": True,
        "committed": committed,
        "worktree": str(top),
        "clone": str(main),
        "branch": branch_for_change(cid),
    }


def prune_clone_worktrees(
    clone: Path | str,
    *,
    max_keep: int | None = None,
) -> dict[str, Any]:
    """``git worktree prune``, then drop archived+clean trees when over cap."""
    main = clone_root(clone) or Path(clone).expanduser().resolve()
    if git_common_dir(main) is None:
        return {"ok": True, "removed": [], "skipped": [], "reason": "not_git"}
    with _clone_lock(main):
        run_git(main, "worktree", "prune", check=False)
    cap = max_keep if max_keep is not None else max_worktrees()
    live = list_holix_worktrees(main)
    removed: list[str] = []
    skipped: list[dict[str, str]] = []
    overflow = max(0, len(live) - cap)
    if overflow:
        candidates: list[WorktreeInfo] = []
        for item in live:
            if not change_is_archived_on_disk(item.worktree, item.change_id):
                continue
            if dirty_paths(item.worktree):
                skipped.append({"change_id": item.change_id, "reason": "dirty"})
                continue
            candidates.append(item)
        candidates.sort(key=lambda w: w.worktree.stat().st_mtime if w.worktree.exists() else 0.0)
        for item in candidates:
            if len(list_holix_worktrees(main)) <= cap:
                break
            try:
                remove_change_worktree(main, item.change_id, force=False)
                removed.append(item.change_id)
            except WorktreeUnavailable as exc:
                skipped.append({"change_id": item.change_id, "reason": str(exc)[:200]})
    return {
        "ok": True,
        "clone": str(main),
        "removed": removed,
        "skipped": skipped,
        "remaining": [w.change_id for w in list_holix_worktrees(main)],
        "max": cap,
    }


def prune_workspace_worktrees(
    start: Path | str | None = None,
    *,
    profile: str | None = None,
) -> dict[str, Any]:
    """Prune Holix worktrees for a profile workspace or *start* path."""
    root: Path | None = None
    if profile:
        try:
            from core.project.workspace_root import profile_workspace_cwd

            cwd = profile_workspace_cwd(profile)
            if cwd:
                root = Path(cwd)
        except Exception:
            root = None
    if root is None and start is not None:
        root = Path(start).expanduser()
    if root is None:
        root = Path.cwd()
    if not root.exists():
        return {"ok": True, "removed": [], "reason": "missing"}
    return prune_clone_worktrees(root)


def extra_sandbox_write_roots(workspace_root: str | None) -> list[str]:
    """``.git`` common dir so commit/index work from a linked worktree."""
    if not workspace_root:
        return []
    common = git_common_dir(workspace_root)
    if common is None:
        return []
    return [str(common)]


def prepare_change_worktree(
    start: Path | str,
    change_id: str,
    *,
    project_rel: str = "",
) -> WorktreeInfo | None:
    """Add a worktree when git+flag allow; otherwise ``None`` (caller scaffolds in place)."""
    if not worktrees_enabled() or not git_available():
        return None
    root = Path(start).expanduser().resolve()
    main = clone_root(root)
    if main is None:
        return None
    top = show_toplevel(root)
    cid = sanitize_change_id(change_id)
    dest = worktree_path_for(main, cid)
    if top is not None and top == dest:
        common = git_common_dir(dest)
        if common is None:
            return None
        return WorktreeInfo(
            change_id=cid,
            branch=branch_for_change(cid),
            worktree=dest,
            clone=main,
            git_common_dir=common,
        )
    return add_change_worktree(main, cid)
