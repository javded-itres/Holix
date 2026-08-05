"""Shared on-disk index of background processes for a Holix profile.

Telegram, Studio, gateway workers, and CLI each have their own Python process and
in-memory registry. This store makes starts from Telegram visible in Studio
Processes / Browser (same profile workspace + index file).
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_INDEX_NAME = "background_processes.json"
_MAX_RECORDS = 200


def _holix_home() -> Path:
    raw = (os.environ.get("HOLIX_HOME") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".holix").resolve()


def profile_process_index_path(profile: str) -> Path:
    name = (profile or "default").strip() or "default"
    return _holix_home() / "profiles" / name / "data" / _INDEX_NAME


def iter_profile_names_with_index() -> list[str]:
    """Profile directory names that have a background process index file."""
    root = _holix_home() / "profiles"
    if not root.is_dir():
        return []
    names: list[str] = []
    try:
        for entry in root.iterdir():
            if entry.is_dir() and (entry / "data" / _INDEX_NAME).is_file():
                names.append(entry.name)
    except OSError:
        return []
    return names


def record_to_dict(rec: Any, *, status: str = "running") -> dict[str, Any]:
    return {
        "process_id": rec.process_id,
        "label": rec.label,
        "command": rec.command,
        "pid": int(rec.pid),
        "conversation_id": rec.conversation_id,
        "profile": rec.profile,
        "chat_id": rec.chat_id,
        "log_path": rec.log_path or "",
        "started_at": float(rec.started_at or time.time()),
        "status": status,
        "stopped_at": None,
    }


def load_index(profile: str) -> list[dict[str, Any]]:
    path = profile_process_index_path(profile)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("background process index read failed %s: %s", path, exc)
        return []
    if not isinstance(raw, dict):
        return []
    items = raw.get("processes")
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict) and item.get("process_id") and item.get("pid"):
            out.append(item)
    return out


def _write_index(profile: str, processes: list[dict[str, Any]]) -> None:
    path = profile_process_index_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Drop dead / oldest beyond cap
    processes = sorted(
        processes,
        key=lambda r: float(r.get("started_at") or 0),
        reverse=True,
    )[:_MAX_RECORDS]
    payload = {
        "version": 1,
        "profile": profile,
        "updated_at": time.time(),
        "processes": processes,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=".bg-proc-",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def upsert_record(rec: Any) -> None:
    """Insert or update a process row for its profile."""
    profile = (getattr(rec, "profile", None) or "default").strip() or "default"
    row = record_to_dict(rec)
    try:
        items = load_index(profile)
        by_id = {str(i.get("process_id")): i for i in items}
        by_id[row["process_id"]] = row
        _write_index(profile, list(by_id.values()))
    except OSError as exc:
        logger.warning("background process index upsert failed profile=%s: %s", profile, exc)


def remove_record(profile: str, process_id: str) -> None:
    """Mark a process as stopped (keep command history for reboot/restart)."""
    name = (profile or "default").strip() or "default"
    pid = (process_id or "").strip()
    if not pid:
        return
    try:
        items = load_index(name)
        now = time.time()
        out: list[dict[str, Any]] = []
        for item in items:
            if str(item.get("process_id")) == pid:
                row = dict(item)
                row["status"] = "stopped"
                row["stopped_at"] = now
                out.append(row)
            else:
                out.append(item)
        _write_index(name, out)
    except OSError as exc:
        logger.warning("background process index remove failed profile=%s: %s", name, exc)


def prune_dead_records(profile: str, *, is_alive) -> list[dict[str, Any]]:
    """Mark dead PIDs as stopped (keep history for reboot/restart), return live rows.

    Stopped entries stay in the index so the agent still knows *what* was
    started (command/label) after reboot and can restart them explicitly.
    """
    name = (profile or "default").strip() or "default"
    items = load_index(name)
    kept: list[dict[str, Any]] = []
    live: list[dict[str, Any]] = []
    changed = False
    now = time.time()
    # Keep stopped history up to 30 days / half of cap.
    max_stopped = max(20, _MAX_RECORDS // 2)
    stopped: list[dict[str, Any]] = []
    for item in items:
        try:
            pid = int(item.get("pid") or 0)
        except (TypeError, ValueError):
            changed = True
            continue
        status = str(item.get("status") or "running")
        if pid > 0 and is_alive(pid):
            if status != "running":
                item = dict(item)
                item["status"] = "running"
                item["stopped_at"] = None
                changed = True
            live.append(item)
            kept.append(item)
        else:
            item = dict(item)
            if status == "running" or not item.get("stopped_at"):
                item["status"] = "stopped"
                item["stopped_at"] = float(item.get("stopped_at") or now)
                changed = True
            # Drop very old stopped rows
            stopped_at = float(item.get("stopped_at") or 0)
            if stopped_at and (now - stopped_at) > 30 * 86400:
                changed = True
                continue
            stopped.append(item)
    # Prefer newest stopped
    stopped.sort(key=lambda r: float(r.get("stopped_at") or 0), reverse=True)
    if len(stopped) > max_stopped:
        changed = True
        stopped = stopped[:max_stopped]
    kept.extend(stopped)
    if changed:
        try:
            _write_index(name, kept)
        except OSError as exc:
            logger.warning("background process index prune failed: %s", exc)
    return live


def list_index_with_status(profile: str, *, is_alive) -> list[dict[str, Any]]:
    """All index rows with live/stopped status (updates index)."""
    name = (profile or "default").strip() or "default"
    prune_dead_records(name, is_alive=is_alive)
    return load_index(name)
