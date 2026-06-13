"""Gateway multi-profile crypto unlock helpers."""

from __future__ import annotations

import logging

from core.crypto.profile_crypto import ProfileCryptoLockedError, is_profile_encryption_enabled
from core.crypto.unlock_context import (
    bootstrap_profile_unlock_from_env,
    get_profile_session_dek,
    release_profile_session_unlock,
)

logger = logging.getLogger(__name__)


class GatewayProfileLockedError(ProfileCryptoLockedError):
    """Encrypted profile cannot be loaded without HOLIX_UNLOCK_KEY."""


def ensure_gateway_profile_unlock(profile: str) -> bool:
    """Ensure an encrypted profile has a session DEK (via HOLIX_UNLOCK_KEY)."""
    name = profile.strip()
    if not is_profile_encryption_enabled(name):
        return True
    if get_profile_session_dek(name) is not None:
        return True
    return bootstrap_profile_unlock_from_env(name)


def require_gateway_profile_unlock(profile: str) -> None:
    """Raise when the profile is encrypted but no unlock key is available."""
    if ensure_gateway_profile_unlock(profile):
        return
    raise GatewayProfileLockedError(
        f"Profile '{profile}' is encrypted and locked. "
        "Set HOLIX_UNLOCK_KEY in the gateway environment."
    )


def release_gateway_profile_unlock(profile: str) -> None:
    """Seal memory and drop session DEK when a profile agent is unloaded."""
    release_profile_session_unlock(profile)