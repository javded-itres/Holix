"""Studio product projects: allocate ``{task_prefix}-{n}`` instead of free slugs."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PREFIX_N = re.compile(r"^([a-z0-9][a-z0-9_-]{0,15})-(\d+)$", re.I)


def normalize_task_prefix(raw: str, *, project_name: str = "") -> str:
    pref = re.sub(r"[^A-Za-z0-9_-]+", "", (raw or "").strip())[:16]
    if not pref:
        pref = re.sub(r"[^A-Za-z0-9]+", "", (project_name or "").strip())[:16]
    if not pref:
        pref = "task"
    pref = pref.lower()
    if not re.match(r"^[a-z0-9]", pref):
        pref = f"t{pref}"[:16]
    return pref


def find_product_project_json(start: Path) -> Path | None:
    """Walk *start* and parents for Studio ``.holix/project.json``."""
    cur = Path(start).expanduser().resolve()
    seen: set[Path] = set()
    for _ in range(8):
        if cur in seen:
            break
        seen.add(cur)
        candidate = cur / ".holix" / "project.json"
        if candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = None
            if isinstance(data, dict) and (
                data.get("id") or data.get("slug") or data.get("tasks") is not None
            ):
                return candidate
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def _max_n_for_prefix(data: dict[str, Any], prefix: str, *, project_root: Path) -> int:
    max_n = 0
    try:
        max_n = max(max_n, int((data.get("settings") or {}).get("task_seq") or 0))
    except (TypeError, ValueError):
        pass
    pat = re.compile(rf"^{re.escape(prefix)}-(\d+)$", re.I)
    for t in data.get("tasks") or []:
        if not isinstance(t, dict):
            continue
        m = pat.match(str(t.get("change_id") or "").strip())
        if m:
            try:
                max_n = max(max_n, int(m.group(1)))
            except (TypeError, ValueError):
                pass
    changes = project_root / "openspec" / "changes"
    if changes.is_dir():
        for d in changes.iterdir():
            if d.is_dir() and not d.name.startswith("."):
                m = pat.match(d.name)
                if m:
                    try:
                        max_n = max(max_n, int(m.group(1)))
                    except (TypeError, ValueError):
                        pass
            if d.name == "archive" and d.is_dir():
                for ad in d.iterdir():
                    if not ad.is_dir():
                        continue
                    m = pat.match(ad.name) or re.search(
                        rf"-{re.escape(prefix)}-(\d+)$", ad.name, re.I
                    )
                    if m:
                        try:
                            max_n = max(max_n, int(m.group(1)))
                        except (TypeError, ValueError):
                            pass
    wt_root = project_root / ".holix" / "worktrees"
    if wt_root.is_dir():
        for d in wt_root.iterdir():
            if d.is_dir():
                m = pat.match(d.name)
                if m:
                    try:
                        max_n = max(max_n, int(m.group(1)))
                    except (TypeError, ValueError):
                        pass
    return max_n


def allocate_product_change_id(
    workspace: Path,
    requested: str = "",
) -> dict[str, Any] | None:
    """If *workspace* is a Studio product project, return allocated ``{prefix}-{n}``.

    Returns None when there is no product ``project.json`` (plain Holix SDD).
    """
    meta_path = find_product_project_json(Path(workspace))
    if meta_path is None:
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    settings = data.get("settings") if isinstance(data.get("settings"), dict) else {}
    prefix = normalize_task_prefix(
        str(settings.get("task_prefix") or ""),
        project_name=str(data.get("name") or data.get("slug") or ""),
    )
    project_root = meta_path.parent.parent
    req = (requested or "").strip().lower()
    m = _PREFIX_N.match(req)
    if m and m.group(1).lower() == prefix:
        cid = f"{prefix}-{int(m.group(2))}"
        dest = project_root / "openspec" / "changes" / cid
        if not dest.exists():
            settings["task_prefix"] = prefix
            try:
                settings["task_seq"] = max(int(settings.get("task_seq") or 0), int(m.group(2)))
            except (TypeError, ValueError):
                settings["task_seq"] = int(m.group(2))
            data["settings"] = settings
            _write_project_json(meta_path, data)
            return {
                "change_id": cid,
                "prefix": prefix,
                "rewritten_from": requested if requested != cid else None,
                "project_json": str(meta_path),
                "data": data,
                "meta_path": meta_path,
            }
    n = _max_n_for_prefix(data, prefix, project_root=project_root) + 1
    cid = f"{prefix}-{n}"
    settings["task_prefix"] = prefix
    settings["task_seq"] = n
    data["settings"] = settings
    _write_project_json(meta_path, data)
    return {
        "change_id": cid,
        "prefix": prefix,
        "rewritten_from": requested if requested and requested != cid else None,
        "project_json": str(meta_path),
        "data": data,
        "meta_path": meta_path,
    }


def ensure_studio_board_task(
    *,
    meta_path: Path,
    data: dict[str, Any],
    change_id: str,
    title: str,
    request: str,
    worktree_rel: str = "",
) -> dict[str, Any] | None:
    """Append a kanban task so analysis UI has a card (idempotent)."""
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        tasks = []
        data["tasks"] = tasks
    cid = (change_id or "").strip()
    for t in tasks:
        if isinstance(t, dict) and str(t.get("change_id") or "").strip() == cid:
            return t
    repos = data.get("repos") if isinstance(data.get("repos"), list) else []
    repo = repos[0] if repos and isinstance(repos[0], dict) else {}
    rel = (
        str(
            data.get("workspace_rel")
            or (f"projects/{data.get('slug')}" if data.get("slug") else "")
        )
        .strip()
        .strip("/")
    )
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    title_s = (title or request or cid).strip().split("\n", 1)[0][:120] or cid
    task = {
        "id": f"task_{uuid.uuid4().hex[:12]}",
        "title": title_s,
        "request": (request or title_s).strip(),
        "kind": "product",
        "change_id": cid,
        "repo_id": repo.get("id"),
        "repo_name": repo.get("name"),
        "repo_path": str(repo.get("path") or rel),
        "worktree_path": worktree_rel or "",
        "column": "draft",
        "created_by_role": "project_manager",
        "spec_status": "draft",
        "comments": [],
        "analysis": None,
        "history": [],
        "created_at": now,
        "updated_at": now,
    }
    tasks.append(task)
    data["updated_at"] = now
    _write_project_json(meta_path, data)
    return task


def _write_project_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
