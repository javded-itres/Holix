"""CLI-facing profile API — implementation lives in ``core.profile.service``.

New core code should import from ``core.profile`` / ``core.profile.service``.
CLI, API, integrations, and tests may keep using ``cli.core``.

Path constants and session globals are forwarded via ``__getattr__`` so a
single source of truth is used. Prefer patching ``core.profile.service`` or
setting ``HOLIX_HOME`` in the environment for path isolation.
"""

from __future__ import annotations

from typing import Any

from core.profile import service as _service
from core.profile_keys import (
    ProfileExistsError,
    ProfileNotFoundError,
    profile_has_access_key,
    require_profile_access_key,
    store_profile_access_key,
    verify_profile_access_key,
)

# Callables / types: same objects as in core (patch either path).
ProfileConfig = _service.ProfileConfig
ProfileManager = _service.ProfileManager
bootstrap_profile_unlock_from_env = _service.bootstrap_profile_unlock_from_env
default_profile_allowed = _service.default_profile_allowed
enable_profile_workspace_isolation = _service.enable_profile_workspace_isolation
get_current_config = _service.get_current_config
get_current_profile = _service.get_current_profile
get_profile_manager = _service.get_profile_manager
init_profile = _service.init_profile
logs_dir = _service.logs_dir
profiles_dir = _service.profiles_dir
resolve_active_profile_name = _service.resolve_active_profile_name
resolve_profile_storage_paths = _service.resolve_profile_storage_paths
switch_profile = _service.switch_profile
unlock_profile = _service.unlock_profile
unlock_profile_encryption = _service.unlock_profile_encryption
validate_profile_name_for_env = _service.validate_profile_name_for_env


def __getattr__(name: str) -> Any:
    """Forward path constants and session globals to ``core.profile.service``."""
    return getattr(_service, name)


def __dir__() -> list[str]:
    names = set(__all__)
    names.update(n for n in dir(_service) if not n.startswith("__"))
    return sorted(names)


__all__ = [
    "HOLIX_HOME",  # noqa: F822 — via __getattr__
    "LOGS_DIR",  # noqa: F822
    "PROFILES_DIR",  # noqa: F822
    "ProfileConfig",
    "ProfileExistsError",
    "ProfileManager",
    "ProfileNotFoundError",
    "bootstrap_profile_unlock_from_env",
    "default_profile_allowed",
    "enable_profile_workspace_isolation",
    "get_current_config",
    "get_current_profile",
    "get_profile_manager",
    "init_profile",
    "logs_dir",
    "profile_has_access_key",
    "profiles_dir",
    "require_profile_access_key",
    "resolve_active_profile_name",
    "resolve_profile_storage_paths",
    "store_profile_access_key",
    "switch_profile",
    "unlock_profile",
    "unlock_profile_encryption",
    "validate_profile_name_for_env",
    "verify_profile_access_key",
]
