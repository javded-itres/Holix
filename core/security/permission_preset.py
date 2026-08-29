"""Session permission presets: sandbox mode + approval policy.

Presets (DeepSeek Harness-style):

- workspace-write — OS sandbox writes only in workspace/tmp; confirmations on
- read-only — OS sandbox denies writes; mutating tools refused
- danger-full-access — no OS wrap; auto-allow through HIGH

Pinned per conversation (not written to profile config.yaml). Default:
workspace-write when jail is on, else danger-full-access (current Holix).
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path

from core.profile.names import ProfileNameError, profile_dir_for_name
from core.security.os_sandbox import normalize_sandbox_mode

logger = logging.getLogger(__name__)

PRESETS = ("workspace-write", "read-only", "danger-full-access")

_READ_ONLY_BLOCKED = frozenset(
    {
        "write_file",
        "patch_file",
        "apply_patch",
        "notebook_edit",
        "delete_file",
        "execute_python",
        "code_executor",
        "run_code",
        "start_background_process",
        "restart_background_process",
        "run_project",
    }
)

_lock = threading.Lock()
_cache: dict[tuple[str, str], str] = {}
_loaded: set[str] = set()


def normalize_preset(value: str | None) -> str | None:
    raw = str(value or "").strip().lower().replace("_", "-")
    if raw in PRESETS:
        return raw
    if raw in {"danger", "full", "off"}:
        return "danger-full-access"
    if raw in {"write", "workspace"}:
        return "workspace-write"
    if raw in {"ro", "readonly"}:
        return "read-only"
    return None


def default_preset(*, jail_enabled: bool) -> str:
    env = normalize_preset(os.environ.get("HOLIX_PERMISSION_MODE"))
    if env:
        return env
    return "workspace-write" if jail_enabled else "danger-full-access"


def _path(profile: str) -> Path | None:
    try:
        return profile_dir_for_name(profile) / "data" / "permission_presets.json"
    except ProfileNameError:
        return None


def _ensure_loaded(profile: str) -> None:
    name = (profile or "default").strip() or "default"
    if name in _loaded:
        return
    _loaded.add(name)
    path = _path(name)
    if path is None or not path.is_file():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        logger.debug("permission preset load failed", exc_info=True)
        return
    sessions = payload.get("sessions") if isinstance(payload, dict) else None
    if not isinstance(sessions, dict):
        return
    for cid, raw in sessions.items():
        preset = normalize_preset(raw)
        if preset:
            _cache[(name, str(cid))] = preset


def _persist(profile: str) -> None:
    path = _path(profile)
    if path is None:
        return
    name = (profile or "default").strip() or "default"
    sessions = {cid: preset for (prof, cid), preset in _cache.items() if prof == name}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".perm.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(
                    {"version": 1, "sessions": sessions}, handle, ensure_ascii=False, indent=2
                )
                handle.write("\n")
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError:
        logger.debug("permission preset persist failed", exc_info=True)


def get_preset(
    profile: str,
    conversation_id: str,
    *,
    jail_enabled: bool | None = None,
) -> str:
    name = (profile or "default").strip() or "default"
    cid = (conversation_id or "default").strip() or "default"
    with _lock:
        _ensure_loaded(name)
        pinned = _cache.get((name, cid))
    if pinned:
        return pinned
    jail = bool(jail_enabled)
    if jail_enabled is None:
        try:
            from core.tools.execution_context import is_workspace_jail_enabled

            jail = bool(is_workspace_jail_enabled())
        except Exception:
            jail = False
    return default_preset(jail_enabled=jail)


def set_preset(profile: str, conversation_id: str, preset: str) -> str:
    name = (profile or "default").strip() or "default"
    cid = (conversation_id or "default").strip() or "default"
    wanted = normalize_preset(preset)
    if not wanted:
        raise ValueError(f"unknown permission preset: {preset!r} (use {' | '.join(PRESETS)})")
    with _lock:
        _ensure_loaded(name)
        _cache[(name, cid)] = wanted
        _persist(name)
    return wanted


def sandbox_mode_for_session(
    profile: str,
    conversation_id: str,
    *,
    jail_enabled: bool | None = None,
) -> str:
    preset = get_preset(profile, conversation_id, jail_enabled=jail_enabled)
    return normalize_sandbox_mode(preset)


def is_preset_pinned(profile: str, conversation_id: str) -> bool:
    name = (profile or "default").strip() or "default"
    cid = (conversation_id or "default").strip() or "default"
    with _lock:
        _ensure_loaded(name)
        return (name, cid) in _cache


def auto_allow_high(*, profile: str, conversation_id: str) -> bool:
    """Skip ActionGuard through HIGH only when the session *pinned* danger.

    Implicit default ``danger-full-access`` (jail off / ``HOLIX_PERMISSION_MODE``)
    still leaves confirmations to the profile ActionGuard threshold.
    """
    name = (profile or "default").strip() or "default"
    cid = (conversation_id or "default").strip() or "default"
    with _lock:
        _ensure_loaded(name)
        return _cache.get((name, cid)) == "danger-full-access"


def read_only_block_reason(tool_name: str, *, profile: str, conversation_id: str) -> str | None:
    if get_preset(profile, conversation_id) != "read-only":
        return None
    from core.tools.aliases import resolve_tool_name

    resolved = resolve_tool_name(tool_name)
    if resolved not in _READ_ONLY_BLOCKED and tool_name not in _READ_ONLY_BLOCKED:
        return None
    return (
        f"Error: permission preset is read-only — `{resolved}` is blocked. "
        "Switch with `/permission workspace-write` or `/permission danger-full-access`."
    )


def format_permission_status(
    preset: str,
    *,
    backend: str | None,
    pinned: bool = False,
) -> str:
    sandbox = normalize_sandbox_mode(preset)
    ask = "never" if preset == "danger-full-access" and pinned else "ask"
    backend_txt = backend or "none (fail-closed if restricted)"
    pin = "session" if pinned else "default"
    return (
        f"permission: {preset} ({pin})\nsandbox: {sandbox}\napproval: {ask}\nbackend: {backend_txt}"
    )


def reset_permission_presets() -> None:
    with _lock:
        _cache.clear()
        _loaded.clear()


def current_session_ids() -> tuple[str, str]:
    try:
        from core.tools.execution_context import get_conversation_id, get_profile_name

        return get_profile_name() or "default", get_conversation_id() or "default"
    except Exception:
        return "default", "default"
