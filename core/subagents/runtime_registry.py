"""Profile-scoped cross-process sub-agent job registry.

Hosts that share a Holix profile (Studio, Telegram, MAX, CLI) publish job
snapshots under ``{profile}/subagents/runtime/`` so any process can list
running and recently finished sub-agents for that profile.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from core.profile.names import profile_dir_for_name, validate_profile_name

logger = logging.getLogger(__name__)

_OWNER_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,64}$")
_NAME_RE = re.compile(r"^[a-zA-Z0-9_.@+-]{1,96}$")

# Keep finished jobs visible for a while so Studio can show results.
_DONE_RETENTION_S = 6 * 3600.0
# Drop running snapshots whose owner process is gone after this idle window.
_STALE_RUNNING_S = 120.0
# Cap activity log size on disk.
_ACTIVITY_MAX = 80


def runtime_root(profile: str) -> Path:
    name = validate_profile_name(profile)
    path = (profile_dir_for_name(name) / "subagents" / "runtime").resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def owner_key(*, source: str | None = None, pid: int | None = None) -> str:
    """Stable id for the host process writing job files."""
    src = (source or detect_source() or "host").strip().lower()
    src = re.sub(r"[^a-z0-9_.-]+", "-", src)[:32] or "host"
    proc = int(pid if pid is not None else os.getpid())
    return f"{src}-{proc}"


def detect_source() -> str:
    """Best-effort channel label for the current process."""
    env = (os.environ.get("HOLIX_MESSENGER_HOST") or "").strip().lower()
    if env:
        return env
    if (os.environ.get("HOLIX_STUDIO") or "").strip().lower() in {"1", "true", "yes"}:
        return "studio"
    if (os.environ.get("HOLIX_GATEWAY") or "").strip().lower() in {"1", "true", "yes"}:
        return "gateway"
    return "host"


def job_id(owner: str, name: str) -> str:
    return f"{owner}::{name}"


def parse_job_id(value: str) -> tuple[str | None, str]:
    """Return (owner, name). Owner is None when *value* is a bare job name."""
    text = (value or "").strip()
    if "::" in text:
        owner, _, name = text.partition("::")
        owner = owner.strip()
        name = name.strip()
        if owner and name:
            return owner, name
    return None, text


def _safe_owner(owner: str) -> str:
    text = (owner or "").strip()
    if not _OWNER_RE.match(text):
        raise ValueError(f"invalid runtime owner: {owner!r}")
    return text


def _safe_name(name: str) -> str:
    text = (name or "").strip()
    if not _NAME_RE.match(text):
        raise ValueError(f"invalid job name: {name!r}")
    return text


def _job_path(profile: str, owner: str, name: str) -> Path:
    return runtime_root(profile) / _safe_owner(owner) / f"{_safe_name(name)}.json"


def _cancel_path(profile: str, owner: str, name: str) -> Path:
    return runtime_root(profile) / _safe_owner(owner) / f"{_safe_name(name)}.cancel"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    try:
        tmp.write_text(raw, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def _pid_alive(pid: int | None) -> bool | None:
    """True if process exists, False if gone, None if unknown/invalid."""
    if pid is None:
        return None
    try:
        p = int(pid)
    except (TypeError, ValueError):
        return None
    if p <= 0:
        return None
    try:
        os.kill(p, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None


def snapshot_from_handle(
    handle: Any,
    *,
    owner: str,
    source: str = "",
    profile: str = "",
    include_activity: bool = True,
    include_result: bool = True,
) -> dict[str, Any]:
    """Serialize a live handle into a registry payload."""
    if hasattr(handle, "to_status_dict"):
        base = handle.to_status_dict(
            include_activity=include_activity,
            include_result=include_result,
        )
    else:
        status = getattr(handle, "status", None)
        status_val = status.value if hasattr(status, "value") else str(status or "")
        base = {
            "name": getattr(handle, "name", "") or "",
            "status": status_val,
            "agent_type": getattr(handle, "agent_type", "") or "",
            "task_preview": getattr(handle, "task_preview", "") or "",
            "process_mode": "",
            "process_id": getattr(handle, "process_id", None),
            "elapsed_ms": float(getattr(handle, "elapsed_ms", 0) or 0),
            "steps_taken": int(getattr(handle, "steps_taken", 0) or 0),
            "max_steps": int(getattr(handle, "max_steps", 0) or 0),
            "current_activity": getattr(handle, "current_activity", "") or "",
            "last_tool": getattr(handle, "last_tool", "") or "",
            "running": bool(getattr(handle, "is_running", False)),
            "done": bool(getattr(handle, "is_done", False)),
            "spawn_fallback_reason": "",
        }

    name = str(base.get("name") or getattr(handle, "name", "") or "").strip()
    src = (source or detect_source() or "host").strip().lower()
    now = time.time()
    started_wall = getattr(handle, "started_at_wall", None)
    if started_wall is None:
        elapsed = float(base.get("elapsed_ms") or 0) / 1000.0
        started_wall = now - max(0.0, elapsed)
    try:
        started_wall = float(started_wall)
    except (TypeError, ValueError):
        started_wall = now

    if include_activity and "activity_log" in base:
        log = list(base.get("activity_log") or [])
        if len(log) > _ACTIVITY_MAX:
            base["activity_log"] = log[-_ACTIVITY_MAX:]

    payload = {
        **base,
        "name": name,
        "id": job_id(owner, name),
        "owner": owner,
        "source": src,
        "profile": profile,
        "owner_pid": os.getpid(),
        "started_at_wall": started_wall,
        "updated_at": now,
        "local": False,
    }
    # Prefer wall-clock elapsed so remote readers stay accurate.
    if not payload.get("done"):
        payload["elapsed_ms"] = round(max(0.0, (now - started_wall) * 1000.0), 1)
    return payload


def publish_handle(
    profile: str,
    handle: Any,
    *,
    owner: str | None = None,
    source: str | None = None,
    include_activity: bool = True,
    include_result: bool = True,
) -> dict[str, Any] | None:
    """Write/update a job snapshot for *handle* under *profile*."""
    try:
        prof = validate_profile_name(profile)
        own = owner or owner_key(source=source)
        if getattr(handle, "started_at_wall", None) is None:
            try:
                handle.started_at_wall = time.time()
            except Exception:
                pass
        payload = snapshot_from_handle(
            handle,
            owner=own,
            source=source or detect_source(),
            profile=prof,
            include_activity=include_activity,
            include_result=include_result,
        )
        name = str(payload.get("name") or "").strip()
        if not name:
            return None
        _atomic_write_json(_job_path(prof, own, name), payload)
        return payload
    except Exception:
        logger.debug("Failed to publish sub-agent runtime snapshot", exc_info=True)
        return None


def request_cancel(profile: str, job_ref: str) -> bool:
    """Ask the owning host to terminate a job (cross-process stop)."""
    try:
        prof = validate_profile_name(profile)
        owner, name = parse_job_id(job_ref)
        if not name:
            return False
        if owner:
            path = _cancel_path(prof, owner, name)
            _atomic_write_json(
                path,
                {"name": name, "owner": owner, "requested_at": time.time()},
            )
            return True
        # Bare name: flag every matching running job.
        flagged = False
        for job in list_jobs(prof, include_done=False):
            if str(job.get("name") or "") != name:
                continue
            job_owner = str(job.get("owner") or "")
            if not job_owner:
                continue
            _atomic_write_json(
                _cancel_path(prof, job_owner, name),
                {
                    "name": name,
                    "owner": job_owner,
                    "requested_at": time.time(),
                },
            )
            flagged = True
        return flagged
    except Exception:
        logger.debug("Failed to request sub-agent cancel", exc_info=True)
        return False


def take_cancel_requests(profile: str, owner: str) -> list[str]:
    """Return job names with pending cancel flags for *owner* and clear them."""
    try:
        prof = validate_profile_name(profile)
        own = _safe_owner(owner)
    except ValueError:
        return []
    root = runtime_root(prof) / own
    if not root.is_dir():
        return []
    names: list[str] = []
    for path in root.glob("*.cancel"):
        name = path.stem
        try:
            path.unlink(missing_ok=True)
        except OSError:
            continue
        if name:
            names.append(name)
    return names


def get_job(
    profile: str,
    job_ref: str,
    *,
    include_activity: bool = True,
    include_result: bool = True,
) -> dict[str, Any] | None:
    """Load one job by id (``owner::name``) or bare name (first match)."""
    jobs = list_jobs(
        profile,
        include_done=True,
        include_activity=include_activity,
        include_result=include_result,
    )
    owner, name = parse_job_id(job_ref)
    if owner:
        want = job_id(owner, name)
        for job in jobs:
            if str(job.get("id") or "") == want:
                return job
        return None
    for job in jobs:
        if str(job.get("name") or "") == name or str(job.get("id") or "") == job_ref:
            return job
    return None


def list_jobs(
    profile: str,
    *,
    include_done: bool = True,
    include_activity: bool = False,
    include_result: bool = False,
    max_done_age_s: float = _DONE_RETENTION_S,
) -> list[dict[str, Any]]:
    """List all published jobs for *profile* (all host processes)."""
    try:
        prof = validate_profile_name(profile)
    except Exception:
        return []
    root = runtime_root(prof)
    now = time.time()
    out: list[dict[str, Any]] = []
    try:
        owner_dirs = [p for p in root.iterdir() if p.is_dir()]
    except OSError:
        return []

    for owner_dir in owner_dirs:
        for path in owner_dir.glob("*.json"):
            if path.name.endswith(".tmp") or ".tmp." in path.name:
                continue
            raw = _read_json(path)
            if not raw:
                continue
            job = _normalize_job(
                raw,
                owner=owner_dir.name,
                path=path,
                now=now,
                max_done_age_s=max_done_age_s,
            )
            if job is None:
                continue
            if not include_done and job.get("done"):
                continue
            if not include_activity:
                job.pop("activity_log", None)
            if not include_result:
                job.pop("result", None)
            out.append(job)

    out.sort(
        key=lambda item: (
            1 if item.get("running") else 0,
            float(item.get("updated_at") or 0),
            str(item.get("id") or item.get("name") or ""),
        ),
        reverse=True,
    )
    return out


def _normalize_job(
    raw: dict[str, Any],
    *,
    owner: str,
    path: Path,
    now: float,
    max_done_age_s: float,
) -> dict[str, Any] | None:
    name = str(raw.get("name") or path.stem or "").strip()
    if not name:
        return None
    status = str(raw.get("status") or "").strip().lower()
    running = bool(raw.get("running")) or status == "running"
    done = bool(raw.get("done")) or status in {
        "completed",
        "failed",
        "cancelled",
        "timed_out",
    }
    if running and done:
        done = False

    updated = float(raw.get("updated_at") or 0) or now
    started = float(raw.get("started_at_wall") or 0) or updated
    owner_pid = raw.get("owner_pid")
    try:
        owner_pid_i = int(owner_pid) if owner_pid is not None else None
    except (TypeError, ValueError):
        owner_pid_i = None

    if running:
        alive = _pid_alive(owner_pid_i)
        stale = (now - updated) > _STALE_RUNNING_S
        if alive is False or (alive is None and stale and (now - updated) > 600):
            # Owner process gone — drop as cancelled so Studio does not show ghosts.
            running = False
            done = True
            status = "cancelled"
            raw = {
                **raw,
                "status": status,
                "running": False,
                "done": True,
                "current_activity": raw.get("current_activity") or "Host process exited",
            }
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return None

    if done and (now - updated) > max_done_age_s:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None

    elapsed = float(raw.get("elapsed_ms") or 0)
    if running:
        elapsed = max(0.0, (now - started) * 1000.0)

    own = str(raw.get("owner") or owner)
    src = str(raw.get("source") or "host")
    jid = str(raw.get("id") or job_id(own, name))
    return {
        **raw,
        "name": name,
        "id": jid,
        "owner": own,
        "source": src,
        "status": status or ("running" if running else "unknown"),
        "running": running,
        "done": done,
        "elapsed_ms": round(elapsed, 1),
        "started_at_wall": started,
        "updated_at": updated,
        "owner_pid": owner_pid_i,
        "local": False,
    }


def merge_local_and_profile(
    local_agents: list[dict[str, Any]],
    profile_agents: list[dict[str, Any]],
    *,
    local_owner: str | None = None,
) -> list[dict[str, Any]]:
    """Union local session jobs with profile registry; local wins on same id."""
    by_id: dict[str, dict[str, Any]] = {}
    for job in profile_agents:
        jid = str(job.get("id") or "")
        if not jid:
            jid = job_id(str(job.get("owner") or "remote"), str(job.get("name") or ""))
        by_id[jid] = {**job, "local": False}

    for agent in local_agents:
        name = str(agent.get("name") or "").strip()
        if not name:
            continue
        own = local_owner or owner_key()
        jid = str(agent.get("id") or job_id(own, name))
        by_id[jid] = {
            **agent,
            "id": jid,
            "owner": own,
            "source": agent.get("source") or detect_source(),
            "local": True,
        }

    agents = list(by_id.values())
    agents.sort(
        key=lambda item: (
            1 if item.get("running") else 0,
            float(item.get("elapsed_ms") or 0),
            str(item.get("name") or ""),
        ),
        reverse=True,
    )
    return agents
