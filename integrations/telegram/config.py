"""Telegram bot configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass
class TelegramSettings:
    bot_token: str
    allowed_user_ids: str = ""
    profile: str = "default"
    edit_interval_ms: int = 500
    allow_all: bool = False
    access_requests: bool = True
    admin_user_id: int | None = None

    def allowed_ids(self) -> set[int]:
        out: set[int] = set()
        for part in self.allowed_user_ids.replace(" ", "").split(","):
            if part.isdigit():
                out.add(int(part))
        return out

    def is_user_allowed(self, user_id: int) -> bool:
        """Default-deny unless allowlist is set or HELIX_TELEGRAM_ALLOW_ALL=true."""
        if self.allow_all:
            return True
        allowed = self.allowed_ids()
        return bool(allowed) and user_id in allowed

    def can_start_without_allowlist(self) -> bool:
        """Bot may run with an empty allowlist when access-request mode is enabled."""
        return self.allow_all or self.access_requests


def telegram_aiogram_available() -> bool:
    """True when the optional Telegram extra (aiogram) is installed."""
    try:
        import aiogram  # noqa: F401

        return True
    except ImportError:
        return False


def load_telegram_settings(profile: str = "default") -> TelegramSettings:
    from integrations.telegram.env_store import load_telegram_env_files

    load_telegram_env_files(profile)
    access_requests_raw = os.getenv("HELIX_TELEGRAM_ACCESS_REQUESTS", "").strip().lower()
    if access_requests_raw:
        access_requests = access_requests_raw in {"1", "true", "yes", "on"}
    else:
        access_requests = True

    from integrations.telegram.admin import load_admin_user_id

    return TelegramSettings(
        bot_token=os.getenv("TELEGRAM_BOT_TOKEN", os.getenv("HELIX_TELEGRAM_BOT_TOKEN", "")),
        allowed_user_ids=os.getenv("HELIX_TELEGRAM_ALLOWED_USERS", ""),
        profile=profile,
        edit_interval_ms=int(os.getenv("HELIX_TELEGRAM_EDIT_MS", "500")),
        allow_all=_env_bool("HELIX_TELEGRAM_ALLOW_ALL"),
        access_requests=access_requests,
        admin_user_id=load_admin_user_id(profile),
    )