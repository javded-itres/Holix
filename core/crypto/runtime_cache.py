"""Hardened runtime memory cache under HOLIX_HOME/.runtime-cache/."""

from __future__ import annotations

import logging
import shutil
import stat
from pathlib import Path

from core.platform_compat import IS_WINDOWS, resolve_holix_home

logger = logging.getLogger(__name__)

RUNTIME_CACHE_DIRNAME = ".runtime-cache"
LEGACY_DATA_CACHE_DIRNAME = ".holix/memory-cache"
CACHE_DIR_MODE = 0o700
CACHE_FILE_MODE = 0o600


def runtime_cache_root() -> Path:
    return (resolve_holix_home() / RUNTIME_CACHE_DIRNAME).resolve()


def profile_runtime_cache_dir(profile: str) -> Path:
    from core.profile.names import validate_profile_name

    return runtime_cache_root() / validate_profile_name(profile)


def legacy_profile_cache_dir(profile: str) -> Path:
    from core.env_loader import profile_dir_path

    return (profile_dir_path(profile) / "data" / LEGACY_DATA_CACHE_DIRNAME).resolve()


def harden_cache_path(path: Path, *, is_dir: bool | None = None) -> None:
    """Apply owner-only permissions to a cache path."""
    try:
        if is_dir is None:
            is_dir = path.is_dir()
        mode = CACHE_DIR_MODE if is_dir else CACHE_FILE_MODE
        path.chmod(mode)
    except OSError as exc:
        logger.debug("Could not harden cache path %s: %s", path, exc)


def harden_cache_tree(root: Path) -> None:
    """Recursively chmod cache tree to 700/600."""
    if not root.exists():
        return
    harden_cache_path(root, is_dir=True)
    for item in root.rglob("*"):
        harden_cache_path(item, is_dir=item.is_dir())


def wipe_profile_runtime_cache(profile: str) -> bool:
    """Remove a profile runtime cache directory; return True if removed."""
    cache_dir = profile_runtime_cache_dir(profile)
    if not cache_dir.exists():
        return False
    shutil.rmtree(cache_dir, ignore_errors=True)
    return True


def wipe_legacy_profile_cache(profile: str) -> bool:
    """Remove legacy data/.holix/memory-cache for a profile."""
    legacy = legacy_profile_cache_dir(profile)
    if not legacy.exists():
        return False
    shutil.rmtree(legacy, ignore_errors=True)
    return True


def wipe_all_runtime_caches() -> int:
    """Remove every profile cache under .runtime-cache; return count removed."""
    root = runtime_cache_root()
    if not root.is_dir():
        return 0
    count = 0
    for item in root.iterdir():
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
            count += 1
    harden_cache_path(root, is_dir=True)
    return count


def cache_dir_is_private(path: Path) -> bool:
    """Return True when a cache directory is owner-only (mode & 077 == 0)."""
    if not path.is_dir():
        return True
    if IS_WINDOWS:
        # chmod is best-effort on Windows; ACL semantics differ from Unix modes.
        return True
    try:
        mode = path.stat().st_mode
        return (mode & (stat.S_IRWXG | stat.S_IRWXO)) == 0
    except OSError:
        return False


def recover_stale_runtime_caches() -> dict[str, int]:
    """Wipe orphan plaintext caches after crash or legacy layout migration."""
    from cli.core import ProfileManager

    root = runtime_cache_root()
    root.mkdir(parents=True, exist_ok=True)
    harden_cache_tree(root)

    from core.profile.names import ProfileNameError, validate_profile_name

    manager = ProfileManager()
    legacy_removed = 0
    for profile in manager.list_profiles():
        try:
            validate_profile_name(profile)
        except ProfileNameError:
            continue
        if wipe_legacy_profile_cache(profile):
            legacy_removed += 1

    runtime_removed = wipe_all_runtime_caches()
    return {"legacy_removed": legacy_removed, "runtime_removed": runtime_removed}


def iter_world_readable_runtime_caches() -> list[Path]:
    """List profile cache dirs that are readable by group/other."""
    root = runtime_cache_root()
    if not root.is_dir():
        return []
    bad: list[Path] = []
    if not cache_dir_is_private(root):
        bad.append(root)
    for item in root.iterdir():
        if item.is_dir() and not cache_dir_is_private(item):
            bad.append(item)
    return bad