"""Safety control for agent drop-in extensions (disable / quarantine without core edits).

File::

    ~/.holix/profiles/<profile>/agent_extensions_control.yaml

Example::

    disabled:
      - experimental_thing
    quarantine:
      bad_ext: "register_tools raised TypeError: ..."

Environment (highest priority)::

    HOLIX_AGENT_EXTENSIONS_OFF=1          # disable *all* agent drop-in extensions
    HOLIX_AGENT_EXTENSIONS_DISABLED=a,b   # extra names disabled for this process
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

CONTROL_FILENAME = "agent_extensions_control.yaml"
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,47}$")


def control_path(profile: str) -> Path:
    from core.profile.names import profile_dir_for_name

    return profile_dir_for_name(profile) / CONTROL_FILENAME


def validate_extension_name(name: str) -> str:
    n = (name or "").strip().lower().replace("-", "_")
    if not _NAME_RE.match(n):
        raise ValueError(
            "extension name must match ^[a-z][a-z0-9_]{1,47}$ "
            f"(got {name!r})"
        )
    if n in {"core", "holix", "agent", "test", "main", "con", "prn"}:
        raise ValueError(f"reserved extension name: {n}")
    return n


def _env_disabled_names() -> set[str]:
    raw = (os.environ.get("HOLIX_AGENT_EXTENSIONS_DISABLED") or "").strip()
    if not raw:
        return set()
    out: set[str] = set()
    for part in raw.replace(";", ",").split(","):
        p = part.strip().lower().replace("-", "_")
        if p:
            out.add(p)
    return out


def all_agent_extensions_off() -> bool:
    return (os.environ.get("HOLIX_AGENT_EXTENSIONS_OFF") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def load_control(profile: str) -> dict[str, Any]:
    path = control_path(profile)
    data: dict[str, Any] = {"disabled": [], "quarantine": {}}
    if path.is_file():
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data.update(raw)
        except Exception:
            logger.warning("failed to read %s", path, exc_info=True)
    disabled = data.get("disabled") or []
    if not isinstance(disabled, list):
        disabled = []
    quarantine = data.get("quarantine") or {}
    if not isinstance(quarantine, dict):
        quarantine = {}
    data["disabled"] = [str(x).strip().lower().replace("-", "_") for x in disabled if str(x).strip()]
    data["quarantine"] = {
        str(k).strip().lower().replace("-", "_"): str(v)
        for k, v in quarantine.items()
        if str(k).strip()
    }
    return data


def save_control(profile: str, data: dict[str, Any]) -> Path:
    path = control_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "disabled": sorted(set(data.get("disabled") or [])),
        "quarantine": dict(data.get("quarantine") or {}),
    }
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def is_extension_blocked(profile: str, name: str) -> tuple[bool, str]:
    """Return (blocked, reason)."""
    n = (name or "").strip().lower().replace("-", "_")
    if not n:
        return True, "empty name"
    if all_agent_extensions_off():
        return True, "HOLIX_AGENT_EXTENSIONS_OFF=1"
    if n in _env_disabled_names():
        return True, "HOLIX_AGENT_EXTENSIONS_DISABLED"
    ctrl = load_control(profile)
    if n in (ctrl.get("disabled") or []):
        return True, "disabled in agent_extensions_control.yaml"
    q = ctrl.get("quarantine") or {}
    if n in q:
        return True, f"quarantine: {q[n]}"
    return False, ""


def disable_extension(profile: str, name: str, *, reason: str = "manual") -> dict[str, Any]:
    n = validate_extension_name(name)
    ctrl = load_control(profile)
    disabled = set(ctrl.get("disabled") or [])
    disabled.add(n)
    ctrl["disabled"] = sorted(disabled)
    path = save_control(profile, ctrl)
    # Also flip settings.enabled if settings file exists / can be created
    try:
        from core.extensions.settings import load_extension_settings, save_extension_settings

        settings = load_extension_settings(profile, n, defaults={"enabled": True})
        settings["enabled"] = False
        settings["disabled_reason"] = reason
        save_extension_settings(profile, n, settings)
    except Exception:
        logger.debug("could not update extension settings for %s", n, exc_info=True)
    return {"name": n, "disabled": True, "reason": reason, "control_file": str(path)}


def enable_extension(profile: str, name: str) -> dict[str, Any]:
    n = validate_extension_name(name)
    ctrl = load_control(profile)
    disabled = set(ctrl.get("disabled") or [])
    disabled.discard(n)
    ctrl["disabled"] = sorted(disabled)
    q = dict(ctrl.get("quarantine") or {})
    q.pop(n, None)
    ctrl["quarantine"] = q
    path = save_control(profile, ctrl)
    try:
        from core.extensions.settings import load_extension_settings, save_extension_settings

        settings = load_extension_settings(profile, n, defaults={"enabled": True})
        settings["enabled"] = True
        settings.pop("disabled_reason", None)
        save_extension_settings(profile, n, settings)
    except Exception:
        logger.debug("could not update extension settings for %s", n, exc_info=True)
    return {"name": n, "disabled": False, "control_file": str(path)}


def quarantine_extension(profile: str, name: str, reason: str) -> dict[str, Any]:
    """Block extension after crash/load failure (survives bad code)."""
    n = (name or "").strip().lower().replace("-", "_") or "unnamed"
    ctrl = load_control(profile)
    q = dict(ctrl.get("quarantine") or {})
    q[n] = (reason or "unknown error")[:500]
    ctrl["quarantine"] = q
    # also add to disabled for clarity
    disabled = set(ctrl.get("disabled") or [])
    disabled.add(n)
    ctrl["disabled"] = sorted(disabled)
    path = save_control(profile, ctrl)
    logger.warning("agent extension %s quarantined: %s", n, reason)
    return {"name": n, "quarantined": True, "reason": q[n], "control_file": str(path)}


def clear_quarantine(profile: str, name: str) -> dict[str, Any]:
    n = validate_extension_name(name)
    ctrl = load_control(profile)
    q = dict(ctrl.get("quarantine") or {})
    removed = q.pop(n, None)
    ctrl["quarantine"] = q
    path = save_control(profile, ctrl)
    return {"name": n, "cleared": removed is not None, "control_file": str(path)}


def profile_agent_extensions_dir(profile: str) -> Path:
    from core.profile.names import profile_dir_for_name

    return profile_dir_for_name(profile) / "extensions"


def list_local_agent_extension_folders(profile: str) -> list[dict[str, Any]]:
    """Scan profile + global extension folders for agent.py entries."""
    from core.extensions.local_loader import global_extensions_dir, profile_extensions_dir

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for root, source in (
        (profile_extensions_dir(profile), "profile"),
        (global_extensions_dir(), "global"),
    ):
        if not root.is_dir():
            continue
        try:
            children = sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))
        except OSError:
            continue
        for folder in children:
            agent_py = folder / "agent.py"
            nested = None
            if not agent_py.is_file():
                # nested package holix_*/agent.py
                try:
                    for child in folder.iterdir():
                        if child.is_dir() and (child / "agent.py").is_file():
                            nested = child / "agent.py"
                            break
                except OSError:
                    pass
                if nested is None:
                    continue
                agent_py = nested
            # name from folder or holix.plugin.json
            name = folder.name.lower().replace("-", "_")
            manifest = folder / "holix.plugin.json"
            if not manifest.is_file() and agent_py.parent != folder:
                manifest = agent_py.parent / "holix.plugin.json"
            description = ""
            version = "—"
            if manifest.is_file():
                try:
                    import json

                    data = json.loads(manifest.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        if data.get("id"):
                            name = str(data["id"]).strip().lower().replace("-", "_")
                        description = str(data.get("description") or "")
                        version = str(data.get("version") or "—")
                except Exception:
                    pass
            if name in seen:
                continue
            seen.add(name)
            blocked, reason = is_extension_blocked(profile, name)
            rows.append(
                {
                    "name": name,
                    "path": str(folder.resolve()),
                    "agent_py": str(agent_py.resolve()),
                    "source": source,
                    "version": version,
                    "description": description,
                    "blocked": blocked,
                    "block_reason": reason,
                }
            )
    return rows
