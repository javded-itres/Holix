"""Telegram user id → Helix profile bindings (shared bot)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from core.env_loader import profile_dir_path

TELEGRAM_USERS_FILE = "telegram-users.json"
ENV_KEY = "HELIX_TELEGRAM_USER_PROFILES"
_PAIR_RE = re.compile(r"^\d+:[\w.-]+$")


def telegram_users_path(bot_profile: str) -> Path:
    name = (bot_profile or "default").strip() or "default"
    return profile_dir_path(name) / TELEGRAM_USERS_FILE


def parse_user_profiles_text(raw: str) -> dict[int, str]:
    """Parse ``123:alice,456:bob`` into a mapping."""
    out: dict[int, str] = {}
    for part in raw.replace(" ", "").split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        uid_s, _, profile = part.partition(":")
        profile = profile.strip()
        if uid_s.isdigit() and profile:
            out[int(uid_s)] = profile
    return out


def format_user_profiles_text(mapping: dict[int, str]) -> str:
    return ",".join(f"{uid}:{name}" for uid, name in sorted(mapping.items()))


def _load_json_mapping(path: Path) -> dict[int, str]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[int, str] = {}
    for key, val in data.items():
        uid_s = str(key).strip()
        profile = str(val).strip()
        if uid_s.isdigit() and profile:
            out[int(uid_s)] = profile
    return out


def load_user_profiles(bot_profile: str) -> dict[int, str]:
    """Load bindings from ``telegram-users.json`` and ``HELIX_TELEGRAM_USER_PROFILES`` env."""
    name = (bot_profile or "default").strip() or "default"
    merged = _load_json_mapping(telegram_users_path(name))
    env_raw = os.getenv(ENV_KEY, "").strip()
    if env_raw:
        for uid, profile in parse_user_profiles_text(env_raw).items():
            merged[uid] = profile
    return merged


def save_user_profiles(bot_profile: str, mapping: dict[int, str]) -> Path:
    """Persist bindings to ``telegram-users.json`` and sync env key in ``telegram.env``."""
    name = (bot_profile or "default").strip() or "default"
    path = telegram_users_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = {str(uid): profile for uid, profile in sorted(mapping.items())}
    path.write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _sync_env_user_profiles(name, mapping)
    return path


def _sync_env_user_profiles(bot_profile: str, mapping: dict[int, str]) -> None:
    from integrations.telegram.env_store import read_telegram_env_values, save_telegram_env

    values = read_telegram_env_values(bot_profile)
    text = format_user_profiles_text(mapping)
    if text:
        values[ENV_KEY] = text
    else:
        values.pop(ENV_KEY, None)
    if values.get("TELEGRAM_BOT_TOKEN") or values.get(ENV_KEY):
        save_telegram_env(values, profile=bot_profile)
    elif ENV_KEY in os.environ:
        os.environ.pop(ENV_KEY, None)


def resolve_user_profile(bot_profile: str, user_id: int) -> str | None:
    return load_user_profiles(bot_profile).get(int(user_id))


def set_user_profile(bot_profile: str, user_id: int, profile: str) -> Path:
    mapping = load_user_profiles(bot_profile)
    mapping[int(user_id)] = profile.strip()
    return save_user_profiles(bot_profile, mapping)


def remove_user_profile(bot_profile: str, user_id: int) -> Path | None:
    mapping = load_user_profiles(bot_profile)
    if int(user_id) not in mapping:
        return None
    del mapping[int(user_id)]
    return save_user_profiles(bot_profile, mapping)


def validate_user_profiles_text(raw: str) -> str | None:
    """Return error message or None if valid."""
    raw = raw.strip()
    if not raw:
        return None
    for part in raw.replace(" ", "").split(","):
        if not part:
            continue
        if not _PAIR_RE.match(part):
            return f"invalid entry {part!r}; expected USER_ID:profile_name"
    return None