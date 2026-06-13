"""In-process profile DEK unlock state (never persisted)."""

from __future__ import annotations

import os
from contextvars import ContextVar

from core.crypto.profile_crypto import ProfileCryptoLockedError

_profile_dek: ContextVar[bytes | None] = ContextVar("holix_profile_dek", default=None)
_unlocked_profile: ContextVar[str | None] = ContextVar("holix_unlocked_profile", default=None)
_session_deks: dict[str, bytes] = {}


def profile_unlock_scope(*, profile: str, dek: bytes):
    """Return tokens for profile_unlock_scope reset."""
    return [
        ("dek", _profile_dek.set(dek)),
        ("profile", _unlocked_profile.set(profile)),
    ]


def reset_profile_unlock_scope(tokens) -> None:
    for key, token in reversed(tokens):
        if key == "dek":
            _profile_dek.reset(token)
        elif key == "profile":
            _unlocked_profile.reset(token)


def get_profile_dek() -> bytes | None:
    return _profile_dek.get()


def is_profile_unlocked(profile: str) -> bool:
    return _unlocked_profile.get() == profile and _profile_dek.get() is not None


def require_profile_dek(profile: str) -> bytes:
    dek = _profile_dek.get()
    active = _unlocked_profile.get()
    if dek is None or active != profile:
        raise ProfileCryptoLockedError(
            f"Profile '{profile}' is encrypted and locked. "
            "Unlock with: holix -p {name} --unlock-key <key> or holix profile crypto unlock"
        )
    return dek


def set_profile_session_unlock(profile: str, dek: bytes) -> None:
    _session_deks[profile] = dek


def get_profile_session_dek(profile: str) -> bytes | None:
    return _session_deks.get(profile)


def clear_profile_session_unlock(profile: str | None = None) -> None:
    if profile:
        _session_deks.pop(profile, None)
    else:
        _session_deks.clear()


def clear_profile_unlock(profile: str | None = None) -> None:
    if profile:
        release_profile_session_unlock(profile)
        return
    for name in list(_session_deks.keys()):
        release_profile_session_unlock(name)
    _profile_dek.set(None)
    _unlocked_profile.set(None)


def release_profile_session_unlock(profile: str) -> None:
    """Seal memory and clear one profile's session DEK without disturbing others."""
    name = profile.strip()
    dek = _session_deks.get(name)
    if dek is not None:
        try:
            from core.crypto.memory_vault import seal_profile_memory

            seal_profile_memory(name, dek)
        except OSError as exc:
            import logging

            logging.getLogger(__name__).warning(
                "Failed to seal memory for profile '%s': %s", name, exc
            )
    from core.crypto.memory_vault import clear_profile_memory_cache

    clear_profile_memory_cache(name)
    clear_profile_session_unlock(name)
    if _unlocked_profile.get() == name:
        _profile_dek.set(None)
        _unlocked_profile.set(None)


def bootstrap_profile_unlock_from_env(profile: str) -> bool:
    """Unlock encrypted profile using HOLIX_UNLOCK_KEY from the environment."""
    key = os.getenv("HOLIX_UNLOCK_KEY", "").strip()
    if not key:
        return False
    from core.crypto.profile_crypto import (
        ProfileCryptoError,
        is_profile_encryption_enabled,
        unlock_profile_dek,
    )

    if not is_profile_encryption_enabled(profile):
        return False
    try:
        dek = unlock_profile_dek(profile, key)
    except ProfileCryptoError:
        return False
    set_profile_session_unlock(profile, dek)
    return True