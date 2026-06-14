"""Persist Telegram credentials per Holix profile."""

from __future__ import annotations

import re
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
from integrations.messenger.platforms import TELEGRAM_PLATFORM

_TOKEN_RE = re.compile(r"^\d+:[A-Za-z0-9_-]{20,}$")
_PLATFORM = TELEGRAM_PLATFORM


def telegram_env_path(profile: str | None = None) -> Path:
    return messenger_env_path(_PLATFORM, profile)


def legacy_telegram_env_path() -> Path:
    return legacy_messenger_env_path(_PLATFORM)


TELEGRAM_ENV_PATH = telegram_env_path("default")


def load_telegram_env_files(profile: str | None = None) -> None:
    load_messenger_env_files(_PLATFORM, profile)


def token_looks_valid(token: str) -> bool:
    return _PLATFORM.token_valid(token)


def mask_token(token: str) -> str:
    return _PLATFORM.token_mask(token)


def format_env_lines(values: dict[str, str]) -> str:
    return _format_env_lines(_PLATFORM, values)


def save_telegram_env(values: dict[str, str], profile: str | None = None) -> Path:
    return save_messenger_env(_PLATFORM, values, profile=profile)


def read_telegram_env_values(profile: str | None = None) -> dict[str, str]:
    return read_messenger_env_values(_PLATFORM, profile)


__all__ = [
    "TELEGRAM_ENV_PATH",
    "apply_to_environ",
    "ensure_holix_home",
    "format_env_lines",
    "legacy_telegram_env_path",
    "load_telegram_env_files",
    "mask_token",
    "merge_project_env",
    "read_telegram_env_values",
    "save_telegram_env",
    "telegram_env_path",
    "token_looks_valid",
]