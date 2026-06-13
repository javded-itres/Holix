"""Global encryption policy (off vs Linux production only)."""

from __future__ import annotations

import os
import sys
from enum import StrEnum

from core.crypto.profile_crypto import ProfileCryptoError, load_crypto_meta
from core.platform_compat import IS_LINUX


class EncryptionMode(StrEnum):
    OFF = "off"
    LINUX_PRODUCTION = "linux-production"
    ON = "on"


_MODE_ALIASES: dict[str, EncryptionMode] = {
    "off": EncryptionMode.OFF,
    "disabled": EncryptionMode.OFF,
    "false": EncryptionMode.OFF,
    "0": EncryptionMode.OFF,
    "linux-production": EncryptionMode.LINUX_PRODUCTION,
    "linux_production": EncryptionMode.LINUX_PRODUCTION,
    "production-linux": EncryptionMode.LINUX_PRODUCTION,
    "on": EncryptionMode.ON,
    "enabled": EncryptionMode.ON,
    "true": EncryptionMode.ON,
    "1": EncryptionMode.ON,
}


def parse_encryption_mode(raw: str | None) -> EncryptionMode:
    key = (raw or "").strip().lower()
    if not key:
        return EncryptionMode.LINUX_PRODUCTION
    try:
        return _MODE_ALIASES[key]
    except KeyError as exc:
        allowed = ", ".join(sorted({mode.value for mode in EncryptionMode}))
        raise ProfileCryptoError(
            f"Invalid HOLIX_ENCRYPTION_MODE '{raw}'. Allowed: {allowed}"
        ) from exc


def resolve_encryption_mode() -> EncryptionMode:
    raw = os.getenv("HOLIX_ENCRYPTION_MODE", "").strip()
    if not raw:
        raw = os.getenv("HOLIX_ENCRYPTION_POLICY", "").strip()
    if not raw:
        try:
            from config import settings

            raw = getattr(settings, "encryption_mode", "") or ""
        except Exception:
            raw = ""
    return parse_encryption_mode(raw or EncryptionMode.LINUX_PRODUCTION.value)


def is_linux_encryption_host() -> bool:
    """Linux server/desktop host (encryption is not used on macOS/Windows)."""
    return IS_LINUX or sys.platform.startswith("linux")


def is_linux_production_host() -> bool:
    """Backward-compatible alias for :func:`is_linux_encryption_host`."""
    return is_linux_encryption_host()


def is_encryption_runtime_active() -> bool:
    """True when Holix should transparently encrypt/decrypt at runtime."""
    mode = resolve_encryption_mode()
    if mode is EncryptionMode.OFF:
        return False
    if mode is EncryptionMode.ON:
        return True
    return is_linux_encryption_host()


def profile_has_crypto_metadata(profile: str) -> bool:
    return load_crypto_meta(profile) is not None


def is_profile_encryption_enabled(profile: str) -> bool:
    """Profile encryption is active for runtime I/O (policy + crypto.json)."""
    if not is_encryption_runtime_active():
        return False
    return profile_has_crypto_metadata(profile)


def encryption_policy_label() -> str:
    mode = resolve_encryption_mode()
    active = is_encryption_runtime_active()
    state = "active" if active else "inactive"
    host = "linux" if is_linux_encryption_host() else "other"
    return f"{mode.value} ({state}, host={host})"


def require_encryption_enable_allowed() -> None:
    """Raise when profile encryption cannot be enabled on this host."""
    mode = resolve_encryption_mode()
    if mode is EncryptionMode.OFF:
        raise ProfileCryptoError(
            "Profile encryption is disabled (HOLIX_ENCRYPTION_MODE=off)."
        )
    if mode is EncryptionMode.LINUX_PRODUCTION and not is_linux_encryption_host():
        raise ProfileCryptoError(
            "Profile encryption is limited to Linux hosts "
            "(HOLIX_ENCRYPTION_MODE=linux-production). "
            f"Current platform: {sys.platform}. "
            "Use HOLIX_ENCRYPTION_MODE=on to force enable on this machine."
        )


def encryption_policy_status() -> dict[str, object]:
    mode = resolve_encryption_mode()
    return {
        "mode": mode.value,
        "runtime_active": is_encryption_runtime_active(),
        "linux_host": is_linux_encryption_host(),
        "platform": sys.platform,
        "holix_env": os.getenv("HOLIX_ENV", "development"),
    }