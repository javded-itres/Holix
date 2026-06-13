"""Persist MAX credentials per Holix profile."""

from __future__ import annotations

import os
from pathlib import Path

from integrations.messenger.env_store import (
    apply_to_environ,
    ensure_holix_home,
    legacy_messenger_env_path,
    load_messenger_env_files,
    merge_project_env,
    messenger_env_path,
    read_messenger_env_values,
    save_messenger_env,
)
from integrations.messenger.env_store import (
    format_env_lines as _format_env_lines,
)
from integrations.messenger.platforms import MAX_PLATFORM

_PLATFORM = MAX_PLATFORM


def max_env_path(profile: str | None = None) -> Path:
    return messenger_env_path(_PLATFORM, profile)


def legacy_max_env_path() -> Path:
    return legacy_messenger_env_path(_PLATFORM)


MAX_ENV_PATH = max_env_path("default")


def load_max_env_files(profile: str | None = None) -> None:
    load_messenger_env_files(_PLATFORM, profile)
    _sync_legacy_env_aliases()


def _sync_legacy_env_aliases() -> None:
    """Mirror HOLIX_MAX_* values into legacy HELIX_MAX_* keys when unset."""
    pairs = (
        ("HOLIX_MAX_ALLOWED_USERS", "HELIX_MAX_ALLOWED_USERS"),
        ("HOLIX_MAX_ALLOW_ALL", "HELIX_MAX_ALLOW_ALL"),
        ("HOLIX_MAX_ACCESS_REQUESTS", "HELIX_MAX_ACCESS_REQUESTS"),
        ("HOLIX_MAX_PROFILE", "HELIX_MAX_PROFILE"),
        ("HOLIX_MAX_MODE", "HELIX_MAX_MODE"),
        ("HOLIX_MAX_WEBHOOK_URL", "HELIX_MAX_WEBHOOK_URL"),
        ("HOLIX_MAX_WEBHOOK_SECRET", "HELIX_MAX_WEBHOOK_SECRET"),
        ("MAX_ACCESS_TOKEN", "HOLIX_MAX_ACCESS_TOKEN"),
    )
    for canonical, legacy in pairs:
        val = os.getenv(canonical, "").strip()
        if val and not os.getenv(legacy, "").strip():
            os.environ[legacy] = val


def token_looks_valid(token: str) -> bool:
    return _PLATFORM.token_valid(token)


def mask_token(token: str) -> str:
    return _PLATFORM.token_mask(token)


def format_env_lines(values: dict[str, str]) -> str:
    normalized = _normalize_values(values)
    return _format_env_lines(_PLATFORM, normalized)


def save_max_env(values: dict[str, str], profile: str | None = None) -> Path:
    normalized = _normalize_values(values)
    return save_messenger_env(_PLATFORM, normalized, profile=profile)


def read_max_env_values(profile: str | None = None) -> dict[str, str]:
    return read_messenger_env_values(_PLATFORM, profile)


def _normalize_values(values: dict[str, str]) -> dict[str, str]:
    """Map legacy HELIX_MAX_* keys to canonical HOLIX_MAX_* on save."""
    out = dict(values)
    legacy_map = {
        "HELIX_MAX_ALLOWED_USERS": "HOLIX_MAX_ALLOWED_USERS",
        "HELIX_MAX_ALLOW_ALL": "HOLIX_MAX_ALLOW_ALL",
        "HELIX_MAX_ACCESS_REQUESTS": "HOLIX_MAX_ACCESS_REQUESTS",
        "HELIX_MAX_PROFILE": "HOLIX_MAX_PROFILE",
        "HELIX_MAX_MODE": "HOLIX_MAX_MODE",
        "HELIX_MAX_WEBHOOK_URL": "HOLIX_MAX_WEBHOOK_URL",
        "HELIX_MAX_WEBHOOK_SECRET": "HOLIX_MAX_WEBHOOK_SECRET",
        "HOLIX_MAX_ACCESS_TOKEN": "MAX_ACCESS_TOKEN",
    }
    for legacy, canonical in legacy_map.items():
        if legacy in out and canonical not in out:
            out[canonical] = out.pop(legacy)
        elif legacy in out and canonical in out:
            out.pop(legacy, None)
    return out


__all__ = [
    "MAX_ENV_PATH",
    "apply_to_environ",
    "ensure_holix_home",
    "format_env_lines",
    "legacy_max_env_path",
    "load_max_env_files",
    "mask_token",
    "max_env_path",
    "merge_project_env",
    "read_max_env_values",
    "save_max_env",
    "token_looks_valid",
]