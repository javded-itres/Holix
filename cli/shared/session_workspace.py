"""Pin a messenger / TUI conversation to workspace root or an org project."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def profile_workspace_root(host: Any) -> Path | None:
    cfg = getattr(getattr(host, "agent", None), "config", None)
    raw = getattr(cfg, "workspace_root", None) if cfg is not None else None
    if not raw:
        raw = getattr(host, "workspace_root", None)
    if not raw:
        return None
    try:
        path = Path(raw).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    return path if path.is_dir() else None


def pin_conversation_to_workspace_root(host: Any, conversation_id: str) -> dict[str, Any]:
    """New session default: profile workspace, no inherited project pin."""
    from core.sdd.change_workspace import bind_active_project, drop_active_change

    profile = str(getattr(host, "profile", None) or "default").strip() or "default"
    cid = (conversation_id or "").strip()
    root = profile_workspace_root(host)
    drop_active_change(profile, cid)
    from core.plugins.hooks import host_bridge_hooks

    pin = host_bridge_hooks.pin_conversation_workspace
    if pin is not None:
        try:
            out = pin(
                profile=profile,
                conversation_id=cid,
                project_id="",
                workspace_root=root or Path.cwd(),
                projects_svc=None,
            )
            if isinstance(out, dict) and out.get("ok"):
                return out
        except Exception:
            pass
    if root is not None:
        bind_active_project(profile, cid, root, project=".")
    return {
        "ok": True,
        "kind": "workspace",
        "project_id": "",
        "path": str(root) if root else "",
        "conversation_id": cid,
    }


def list_workspace_picker_options(host: Any) -> list[dict[str, Any]]:
    """Workspace root plus org projects (when Studio is available)."""
    root = profile_workspace_root(host)
    options: list[dict[str, Any]] = [
        {
            "id": "",
            "kind": "workspace",
            "name": "Workspace",
            "workspace_rel": ".",
            "path": str(root) if root else "",
        }
    ]
    from core.plugins.hooks import host_bridge_hooks

    raw: list[Any] = []
    options_fn = host_bridge_hooks.workspace_options
    if options_fn is not None:
        try:
            payload = options_fn()
            raw = list((payload or {}).get("options") or [])
        except Exception:
            raw = []
    seen = {""}
    for row in raw:
        if not isinstance(row, dict):
            continue
        pid = str(row.get("id") or "").strip()
        kind = str(row.get("kind") or "").strip() or ("workspace" if not pid else "project")
        if kind == "workspace" or not pid:
            continue
        if pid in seen:
            continue
        seen.add(pid)
        pname = str(row.get("name") or row.get("slug") or pid)
        rel = str(row.get("workspace_rel") or "")
        options.append(
            {
                "id": pid,
                "kind": "main",
                "project_id": pid,
                "change_id": "",
                "name": f"{pname} · main",
                "workspace_rel": rel,
                "path": str(row.get("path") or ""),
            }
        )
        for wt in row.get("worktrees") or []:
            if not isinstance(wt, dict):
                continue
            wid = str(wt.get("id") or wt.get("change_id") or "").strip()
            if not wid:
                continue
            options.append(
                {
                    "id": f"{pid}::{wid}",
                    "kind": "worktree",
                    "project_id": pid,
                    "change_id": wid,
                    "name": f"{pname} · {wid}",
                    "workspace_rel": f"{rel}/.holix/worktrees/{wid}",
                    "path": str(wt.get("path") or ""),
                }
            )
    return options


def apply_workspace_picker_choice(host: Any, option: dict[str, Any]) -> dict[str, Any]:
    cid = str(getattr(host, "conversation_id", "") or "").strip()
    kind = str(option.get("kind") or "")
    pid = str(option.get("project_id") or option.get("id") or "").strip()
    change = str(option.get("change_id") or "").strip()
    if kind in {"", "workspace"} or not pid:
        return pin_conversation_to_workspace_root(host, cid)
    from core.plugins.hooks import host_bridge_hooks

    pin = host_bridge_hooks.pin_conversation_workspace
    if pin is None:
        return {"ok": False, "error": "project workspace is only available in Studio"}
    root = profile_workspace_root(host) or Path.cwd()
    profile = str(getattr(host, "profile", None) or "default")
    project_id = pid.split("::", 1)[0]
    try:
        return pin(
            profile=profile,
            conversation_id=cid,
            project_id=project_id,
            workspace_root=root,
            change_id=change,
        )
    except TypeError:
        try:
            return pin(
                profile=profile,
                conversation_id=cid,
                project_id=project_id,
                workspace_root=root,
            )
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
