"""Ensure the Telegram admin Holix profile exists in production and mirrors ``default``."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cli.core import ProfileManager


def is_production_env() -> bool:
    return os.getenv("HOLIX_ENV", "development").strip().lower() == "production"


def _copy_profile_env_from_source(source_profile: str, target_profile: str) -> None:
    from core.env_loader import holix_env_path, profile_env_path

    try:
        from dotenv import dotenv_values

        from core.crypto.profile_files import dotenv_values_for_path
    except ImportError:
        return

    source_env = profile_env_path(source_profile)
    if not source_env.is_file():
        return

    source_values = {
        key: value
        for key, value in dotenv_values_for_path(source_env, profile=source_profile).items()
        if value is not None and str(value).strip()
    }
    if not source_values:
        return

    global_values: dict[str, str | None] = {}
    try:
        from core.global_config import global_env_path

        gpath = global_env_path()
        if gpath.is_file():
            global_values.update(dotenv_values(gpath))
    except Exception:
        pass
    legacy = holix_env_path()
    if legacy.is_file():
        global_values.update(dotenv_values(legacy))

    to_copy = {
        key: value
        for key, value in source_values.items()
        if key not in global_values or global_values.get(key) != value
    }
    if not to_copy:
        return

    target_env = profile_env_path(target_profile)
    target_env.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if target_env.is_file():
        lines.append(target_env.read_text(encoding="utf-8").rstrip())
        lines.append("")
    else:
        lines.append(
            f"# Copied from profile '{source_profile}' for production admin",
        )
    for key in sorted(to_copy):
        lines.append(f"{key}={to_copy[key]}")
    target_env.write_text("\n".join(lines) + "\n", encoding="utf-8")


def copy_profile_settings_from_source(
    manager: ProfileManager,
    *,
    source_profile: str,
    target_profile: str,
) -> bool:
    """Copy resolved config and env overrides from *source_profile* into *target_profile*."""
    source_profile = (source_profile or "").strip()
    target_profile = (target_profile or "").strip()
    if not source_profile or not target_profile or source_profile == target_profile:
        return False
    if not manager.profile_exists(source_profile):
        return False

    from cli.core import ProfileConfig, resolve_profile_storage_paths

    from core.global_config import extract_profile_overrides, load_global_config_resolved

    source_cfg = manager.load_profile(source_profile)
    payload = source_cfg.model_dump()
    payload["profile_name"] = target_profile
    target_cfg = ProfileConfig(**payload)
    target_cfg = resolve_profile_storage_paths(
        target_profile,
        target_cfg,
        profile_dir=manager.get_profile_dir(target_profile),
    )
    storage = extract_profile_overrides(
        target_cfg.model_dump(),
        load_global_config_resolved(),
    )
    manager._write_profile_yaml(target_profile, storage)
    _copy_profile_env_from_source(source_profile, target_profile)
    return True


def ensure_admin_profile_from_default(
    *,
    admin_profile: str | None = None,
    source_profile: str = "default",
    manager: ProfileManager | None = None,
) -> str | None:
    """In production, create *admin_profile* and copy all settings from *source_profile*."""
    if not is_production_env():
        return None

    from cli.core import ProfileManager as PM
    from integrations.telegram.admin import DEFAULT_ADMIN_PROFILE

    mgr = manager or PM()
    target = (admin_profile or DEFAULT_ADMIN_PROFILE).strip() or DEFAULT_ADMIN_PROFILE
    source = (source_profile or "default").strip() or "default"

    if not mgr.profile_exists(source):
        return target if mgr.profile_exists(target) else None

    if not mgr.profile_exists(target):
        mgr.create_profile(target, inherit_global=True)

    copy_profile_settings_from_source(
        mgr,
        source_profile=source,
        target_profile=target,
    )
    return target


def maybe_seed_admin_on_env_change(variables: dict[str, Any]) -> None:
    """After global env patch, seed admin profile when switching to production."""
    raw = variables.get("HOLIX_ENV")
    if raw is None:
        return
    if str(raw).strip().lower() != "production":
        return
    ensure_admin_profile_from_default()