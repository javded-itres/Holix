"""Global Holix settings shared across profiles (~/.holix/global/)."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from core.env_loader import holix_env_path, holix_home
from core.platform_compat import resolve_holix_home

# Keys stored per profile only (never inherited from global config.yaml).
PROFILE_ONLY_KEYS: frozenset[str] = frozenset({
    "profile_name",
    "data_dir",
    "memory_db_path",
    "vector_db_path",
    "ltm_db_path",
    "langgraph_checkpoint_db_path",
    "skills_dir",
    "workspace_jail_enabled",
    "workspace_root",
    "encryption_enabled",
})


def global_dir() -> Path:
    return resolve_holix_home() / "global"


def global_config_path() -> Path:
    return global_dir() / "config.yaml"


def global_env_path() -> Path:
    return global_dir() / ".env"


def ensure_global_dir() -> Path:
    path = global_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def strip_profile_only_keys(data: dict[str, Any]) -> dict[str, Any]:
    """Remove per-profile path fields before storing or comparing global config."""
    return {k: v for k, v in data.items() if k not in PROFILE_ONLY_KEYS}


def _strip_profile_only(data: dict[str, Any]) -> dict[str, Any]:
    return strip_profile_only_keys(data)


def default_global_config_data() -> dict[str, Any]:
    """Baseline global YAML (models, MCP, behavior — no per-profile paths)."""
    from cli.core import ProfileConfig

    return _strip_profile_only(ProfileConfig(profile_name="_global").model_dump())


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    import yaml

    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _migrate_legacy_global_env() -> None:
    """Copy legacy ``~/.holix/.env`` into ``global/.env`` once when global is missing."""
    target = global_env_path()
    if target.is_file():
        return
    legacy = holix_env_path()
    if legacy.is_file():
        ensure_global_dir()
        target.write_text(legacy.read_text(encoding="utf-8"), encoding="utf-8")


def ensure_global_config(*, seed_from_profile: str | None = "default") -> Path:
    """Create ``global/config.yaml`` when absent (optionally seed from an existing profile)."""
    ensure_global_dir()
    _migrate_legacy_global_env()
    path = global_config_path()
    if path.is_file():
        return path

    data: dict[str, Any] | None = None
    if seed_from_profile:
        from cli.core import profiles_dir

        candidate = profiles_dir() / seed_from_profile / "config.yaml"
        if candidate.is_file():
            raw = _load_yaml(candidate)
            data = _strip_profile_only(raw)

    if not data:
        data = default_global_config_data()

    import yaml

    with open(path, "w", encoding="utf-8") as handle:
        yaml.dump(data, handle, default_flow_style=False, allow_unicode=True)
    return path


def ensure_global_env_template() -> Path:
    """Create ``global/.env`` from legacy global env or ``.env.example`` when missing."""
    ensure_global_dir()
    path = global_env_path()
    if path.is_file():
        return path

    _migrate_legacy_global_env()
    if path.is_file():
        return path

    legacy = holix_env_path()
    if legacy.is_file():
        path.write_text(legacy.read_text(encoding="utf-8"), encoding="utf-8")
        return path

    from core.env_loader import _find_env_example_path

    src = _find_env_example_path()
    if src and src.is_file():
        path.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        path.write_text(
            "# Holix global environment (inherited by profiles unless overridden)\n",
            encoding="utf-8",
        )
    return path


def load_global_config_raw() -> dict[str, Any]:
    """Load global config.yaml without env resolution."""
    ensure_global_config()
    return _load_yaml(global_config_path())


def load_global_config_resolved() -> dict[str, Any]:
    from core.config_utils import resolve_env_refs

    return resolve_env_refs(load_global_config_raw())


def deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *override* onto *base* (override wins)."""
    merged = deepcopy(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = deep_merge_dict(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def merge_global_with_profile(
    global_data: dict[str, Any],
    profile_data: dict[str, Any],
) -> dict[str, Any]:
    """Global settings with per-profile overrides (profile wins)."""
    base = _strip_profile_only(global_data)
    overrides = dict(profile_data)
    merged = deep_merge_dict(base, overrides)
    merged["profile_name"] = profile_data.get("profile_name") or merged.get("profile_name", "default")
    return merged


def _values_equal(a: Any, b: Any) -> bool:
    return a == b


def extract_profile_overrides(
    resolved: dict[str, Any],
    global_data: dict[str, Any],
) -> dict[str, Any]:
    """Persist only profile-specific differences from global defaults."""
    global_stripped = _strip_profile_only(global_data)
    out: dict[str, Any] = {
        "profile_name": resolved.get("profile_name", "default"),
    }

    for key, value in resolved.items():
        if key == "profile_name":
            continue
        if key in PROFILE_ONLY_KEYS:
            out[key] = value
            continue
        global_val = global_stripped.get(key)
        if isinstance(value, dict) and isinstance(global_val, dict):
            diff = _extract_dict_diff(value, global_val)
            if diff:
                out[key] = diff
        elif not _values_equal(value, global_val):
            out[key] = value

    return out


def _extract_dict_diff(profile: dict[str, Any], global_map: dict[str, Any]) -> dict[str, Any]:
    diff: dict[str, Any] = {}
    for key, value in profile.items():
        gval = global_map.get(key)
        if isinstance(value, dict) and isinstance(gval, dict):
            nested = _extract_dict_diff(value, gval)
            if nested:
                diff[key] = nested
        elif not _values_equal(value, gval):
            diff[key] = value
    return diff


def format_global_paths_block() -> str:
    home = holix_home()
    cfg = global_config_path()
    env = global_env_path()
    return (
        f"- **Global config**: `{cfg}`\n"
        f"- **Global env**: `{env}`\n"
        f"- **HOLIX_HOME**: `{home}`"
    )