"""Per-profile extension settings loaded at agent initialization."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def extension_settings_dir(profile: str) -> Path:
    """``~/.holix/profiles/<profile>/extension_settings/``."""
    from core.profile.names import profile_dir_for_name

    return profile_dir_for_name(profile) / "extension_settings"


def extension_settings_path(profile: str, extension_name: str) -> Path:
    name = (extension_name or "").strip() or "unnamed"
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
    return extension_settings_dir(profile) / f"{safe}.yaml"


def load_extension_settings(
    profile: str,
    extension_name: str,
    *,
    defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge defaults ← profile config.extension_settings ← settings file."""
    merged: dict[str, Any] = dict(defaults or {})

    # Profile config.yaml: extension_settings: { name: {...} }
    try:
        from core.profile import ProfileManager

        cfg = ProfileManager().load_profile(profile)
        block = getattr(cfg, "extension_settings", None) or {}
        if isinstance(block, dict):
            ext_block = block.get(extension_name)
            if isinstance(ext_block, dict):
                merged.update(ext_block)
    except Exception:
        logger.debug("profile extension_settings unavailable for %s", extension_name, exc_info=True)

    path = extension_settings_path(profile, extension_name)
    if path.is_file():
        try:
            text = path.read_text(encoding="utf-8")
            data = yaml.safe_load(text) if path.suffix in {".yaml", ".yml"} else json.loads(text)
            if isinstance(data, dict):
                merged.update(data)
        except Exception:
            logger.warning("failed to load extension settings %s", path, exc_info=True)

    return merged


def save_extension_settings(
    profile: str,
    extension_name: str,
    settings: dict[str, Any],
) -> Path:
    path = extension_settings_path(profile, extension_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(settings, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def ensure_default_settings_file(
    profile: str,
    extension_name: str,
    defaults: dict[str, Any],
) -> Path | None:
    """Write defaults once if no settings file exists yet."""
    if not defaults:
        return None
    path = extension_settings_path(profile, extension_name)
    if path.is_file():
        return path
    return save_extension_settings(profile, extension_name, defaults)
