"""MAX bot configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_int_clamped(name: str, default: int, *, min_value: int, max_value: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(min_value, min(max_value, value))


def _env_int_clamped_first(
    *names: str,
    default: int,
    min_value: int,
    max_value: int,
) -> int:
    for name in names:
        raw = os.getenv(name, "").strip()
        if raw:
            try:
                value = int(raw)
            except ValueError:
                continue
            return max(min_value, min(max_value, value))
    return default


@dataclass
class MaxSettings:
    access_token: str
    allowed_user_ids: str = ""
    profile: str = "default"
    mode: str = "polling"
    webhook_url: str = ""
    webhook_secret: str = ""
    allow_all: bool = False
    access_requests: bool = True
    admin_user_id: int | None = None
    poll_timeout_s: int = 5
    edit_interval_ms: int = 1500
    heartbeat_interval_s: int = 45

    def allowed_ids(self) -> set[int]:
        out: set[int] = set()
        for part in self.allowed_user_ids.replace(" ", "").split(","):
            if part.isdigit():
                out.add(int(part))
        return out

    def is_user_allowed(self, user_id: int) -> bool:
        if self.allow_all:
            return True
        allowed = self.allowed_ids()
        return bool(allowed) and user_id in allowed

    def can_start_without_allowlist(self) -> bool:
        return self.allow_all or self.access_requests

    @property
    def is_webhook_mode(self) -> bool:
        return self.mode.strip().lower() == "webhook"


def _env_first(*keys: str, default: str = "") -> str:
    for key in keys:
        val = os.getenv(key, "").strip()
        if val:
            return val
    return default


def max_files_extra_available() -> bool:
    """True when optional PDF extraction (pypdf) from the `max` extra is installed."""
    try:
        import pypdf  # noqa: F401

        return True
    except ImportError:
        return False


def load_max_settings(profile: str = "default") -> MaxSettings:
    from integrations.max.admin import load_admin_user_id
    from integrations.max.env_store import load_max_env_files

    load_max_env_files(profile)
    access_requests_raw = _env_first(
        "HOLIX_MAX_ACCESS_REQUESTS",
        "HELIX_MAX_ACCESS_REQUESTS",
    ).lower()
    if access_requests_raw:
        access_requests = access_requests_raw in {"1", "true", "yes", "on"}
    else:
        access_requests = True

    mode = _env_first("HOLIX_MAX_MODE", "HELIX_MAX_MODE", default="polling").lower()
    if os.getenv("HOLIX_ENV", "").strip().lower() == "production" and mode not in {"webhook"}:
        mode = "webhook"
    return MaxSettings(
        access_token=_env_first("MAX_ACCESS_TOKEN", "HOLIX_MAX_ACCESS_TOKEN"),
        allowed_user_ids=_env_first("HOLIX_MAX_ALLOWED_USERS", "HELIX_MAX_ALLOWED_USERS"),
        profile=_env_first("HOLIX_MAX_PROFILE", "HELIX_MAX_PROFILE", default=profile),
        mode=mode,
        webhook_url=_env_first("HOLIX_MAX_WEBHOOK_URL", "HELIX_MAX_WEBHOOK_URL"),
        webhook_secret=_env_first("HOLIX_MAX_WEBHOOK_SECRET", "HELIX_MAX_WEBHOOK_SECRET"),
        allow_all=_env_bool("HOLIX_MAX_ALLOW_ALL") or _env_bool("HELIX_MAX_ALLOW_ALL"),
        access_requests=access_requests,
        admin_user_id=load_admin_user_id(profile),
        poll_timeout_s=_env_int_clamped(
            "HELIX_MAX_POLL_TIMEOUT",
            5,
            min_value=0,
            max_value=90,
        ),
        edit_interval_ms=_env_int_clamped_first(
            "HOLIX_MAX_EDIT_INTERVAL_MS",
            "HELIX_MAX_EDIT_INTERVAL_MS",
            default=1500,
            min_value=300,
            max_value=10000,
        ),
        heartbeat_interval_s=_env_int_clamped(
            "HELIX_MAX_HEARTBEAT_INTERVAL",
            45,
            min_value=15,
            max_value=300,
        ),
    )