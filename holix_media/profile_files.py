"""Read profile media files without importing Holix core.

Host extensions must not depend on ``core``. This reader uses ``HOLIX_HOME`` /
``HOLIX_PROFILE`` and the same YAML locations core uses.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

_PROFILE_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")
_ENV_REF = re.compile(r"\$\{(?:ENV:)?([A-Za-z_][A-Za-z0-9_]*)\}")


def holix_home() -> Path:
    """Same locations as ``core.platform_compat.resolve_holix_home``."""
    if raw := os.environ.get("HOLIX_HOME", "").strip():
        return Path(raw).expanduser().resolve()
    if raw := os.environ.get("HELIX_HOME", "").strip():
        return Path(raw).expanduser().resolve()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return (Path(base) / "Holix").resolve()
        return (Path.home() / ".holix").resolve()
    if xdg := os.environ.get("XDG_DATA_HOME", "").strip():
        return (Path(xdg) / "holix").resolve()
    return (Path.home() / ".holix").resolve()


def active_profile_name() -> str:
    return (os.environ.get("HOLIX_PROFILE") or "default").strip() or "default"


def profile_dir(profile: str | None = None) -> Path | None:
    name = (profile or active_profile_name()).strip() or "default"
    if ".." in name or "/" in name or "\\" in name or not _PROFILE_RE.fullmatch(name):
        return None
    root = (holix_home() / "profiles").resolve()
    candidate = (root / name).resolve()
    if candidate != root and root not in candidate.parents:
        return None
    return candidate


def media_settings_path(profile: str | None = None) -> Path | None:
    folder = profile_dir(profile)
    if folder is None:
        return None
    return folder / "extension_settings" / "media.yaml"


def load_media_settings(profile: str | None = None) -> dict[str, Any]:
    """Global ``extension_settings.media``, then the profile, then ``media.yaml``."""
    name = (profile or active_profile_name()).strip() or "default"
    merged: dict[str, Any] = {}
    for source in (_global_config(), _profile_config(name)):
        block = source.get("extension_settings")
        if isinstance(block, dict):
            media = block.get("media")
            if isinstance(media, dict):
                merged.update(media)
    path = media_settings_path(name)
    if path is not None:
        merged.update(_load_yaml(path))
    return merged


def litellm_base_url(profile: str | None = None) -> str:
    """Profile ``providers.litellm.base_url``, else the global config."""
    name = (profile or active_profile_name()).strip() or "default"
    for source in (_profile_config(name), _global_config()):
        providers = source.get("providers")
        if not isinstance(providers, dict):
            continue
        slot = providers.get("litellm")
        if not isinstance(slot, dict):
            continue
        base = _expand(str(slot.get("base_url") or ""))
        if base:
            return base
    return ""


def _profile_config(profile: str) -> dict[str, Any]:
    folder = profile_dir(profile)
    if folder is None:
        return {}
    return _load_yaml(folder / "config.yaml")


def _global_config() -> dict[str, Any]:
    return _load_yaml(holix_home() / "global" / "config.yaml")


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _expand(value: str) -> str:
    return _ENV_REF.sub(lambda match: os.environ.get(match.group(1), ""), value).strip()
