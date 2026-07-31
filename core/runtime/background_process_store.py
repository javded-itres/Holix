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


def record_to_dict(rec: Any) -> dict[str, Any]:
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
    name = (profile or "default").strip() or "default"
    pid = (process_id or "").strip()
    if not pid:
        return
    try:
        items = [i for i in load_index(name) if str(i.get("process_id")) != pid]
        _write_index(name, items)
    except OSError as exc:
        logger.warning("background process index remove failed profile=%s: %s", name, exc)


def prune_dead_records(profile: str, *, is_alive) -> list[dict[str, Any]]:
    """Drop dead PIDs from the index; return surviving rows."""
    name = (profile or "default").strip() or "default"
    items = load_index(name)
    alive: list[dict[str, Any]] = []
    changed = False
    for item in items:
        try:
            pid = int(item.get("pid") or 0)
        except (TypeError, ValueError):
            changed = True
            continue
        if pid > 0 and is_alive(pid):
            alive.append(item)
        else:
            changed = True
    if changed:
        try:
            _write_index(name, alive)
        except OSError as exc:
            logger.warning("background process index prune failed: %s", exc)
    return alive
