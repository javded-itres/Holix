"""Profile-level Holix Link settings from config.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from integrations.link.protocol import LinkPermissions


class LinkProfileSettings(BaseModel):
    max_connections: int = Field(default=5, ge=1, le=100)
    permissions: LinkPermissions = Field(default_factory=LinkPermissions)


def _profile_config_path(profile: str) -> Path | None:
    from cli.core import ProfileManager

    manager = ProfileManager()
    if not manager.profile_exists(profile):
        return None
    return manager.get_profile_dir(profile) / "config.yaml"


def load_link_profile_settings(profile: str) -> LinkProfileSettings:
    """Read ``link:`` block from profile config.yaml (raw, before global merge)."""
    path = _profile_config_path(profile)
    if path is None or not path.is_file():
        return LinkProfileSettings()

    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    link_data = data.get("link") or {}
    perms_raw = link_data.get("permissions") or {}
    permissions = LinkPermissions.model_validate(perms_raw) if perms_raw else LinkPermissions()
    max_conn = int(link_data.get("max_connections", 5))
    return LinkProfileSettings(max_connections=max_conn, permissions=permissions)