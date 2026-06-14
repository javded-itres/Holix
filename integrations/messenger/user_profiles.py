"""Messenger user id → Holix profile bindings (shared bot)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from core.env_loader import profile_dir_path
from core.profile.names import ProfileNameError, validate_profile_name

from integrations.messenger.env_store import (
    messenger_env_path,
    read_messenger_env_values,
    save_messenger_env,
)
from integrations.messenger.platform import MessengerPlatform

_PAIR_RE = re.compile(r"^\d+:[\w.-]+$")


def users_mapping_path(platform: MessengerPlatform, bot_profile: str) -> Path:
    return profile_dir_path(validate_profile_name(bot_profile)) / platform.users_filename


def parse_user_profiles_text(raw: str) -> dict[int, str]:
    out: dict[int, str] = {}
    for part in raw.replace(" ", "").split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        uid_s, _, profile = part.partition(":")
        profile = profile.strip()
        if not uid_s.isdigit() or not profile:
            continue
        try:
            out[int(uid_s)] = validate_profile_name(profile)
        except ProfileNameError:
            continue
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
        if not uid_s.isdigit() or not profile:
            continue
        try:
            out[int(uid_s)] = validate_profile_name(profile)
        except ProfileNameError:
            continue
    return out


def load_user_profiles(platform: MessengerPlatform, bot_profile: str) -> dict[int, str]:
    name = validate_profile_name(bot_profile)
    merged = _load_json_mapping(users_mapping_path(platform, name))
    env_raw = _profile_env_user_profiles(platform, name)
    if env_raw:
        for uid, profile in parse_user_profiles_text(env_raw).items():
            merged[uid] = profile
    if not merged and name != "default":
        fallback = _load_json_mapping(users_mapping_path(platform, "default"))
        if fallback:
            merged.update(fallback)
    return merged


def _profile_env_user_profiles(platform: MessengerPlatform, bot_profile: str) -> str:
    return read_messenger_env_values(platform, bot_profile).get(
        platform.user_profiles_key,
        "",
    ).strip()


def save_user_profiles(
    platform: MessengerPlatform,
    bot_profile: str,
    mapping: dict[int, str],
) -> Path:
    name = validate_profile_name(bot_profile)
    safe_mapping = {uid: validate_profile_name(profile) for uid, profile in mapping.items()}
    path = users_mapping_path(platform, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = {str(uid): profile for uid, profile in sorted(safe_mapping.items())}
    path.write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _sync_env_user_profiles(platform, name, safe_mapping)
    return path


def _sync_env_user_profiles(
    platform: MessengerPlatform,
    bot_profile: str,
    mapping: dict[int, str],
) -> None:
    values = read_messenger_env_values(platform, bot_profile)
    text = format_user_profiles_text(mapping)
    if text:
        values[platform.user_profiles_key] = text
    else:
        values.pop(platform.user_profiles_key, None)
    token_key = platform.token_key
    if (
        values.get(token_key)
        or values.get(platform.user_profiles_key)
        or messenger_env_path(platform, bot_profile).is_file()
    ):
        save_messenger_env(platform, values, profile=bot_profile)
    elif platform.user_profiles_key in os.environ:
        os.environ.pop(platform.user_profiles_key, None)


def resolve_user_profile(
    platform: MessengerPlatform,
    bot_profile: str,
    user_id: int,
) -> str | None:
    return load_user_profiles(platform, bot_profile).get(int(user_id))


def set_user_profile(
    platform: MessengerPlatform,
    bot_profile: str,
    user_id: int,
    profile: str,
) -> Path:
    mapping = load_user_profiles(platform, bot_profile)
    mapping[int(user_id)] = validate_profile_name(profile)
    return save_user_profiles(platform, bot_profile, mapping)


def remove_user_profile(
    platform: MessengerPlatform,
    bot_profile: str,
    user_id: int,
) -> Path | None:
    mapping = load_user_profiles(platform, bot_profile)
    if int(user_id) not in mapping:
        return None
    del mapping[int(user_id)]
    return save_user_profiles(platform, bot_profile, mapping)


def validate_user_profiles_text(raw: str) -> str | None:
    raw = raw.strip()
    if not raw:
        return None
    for part in raw.replace(" ", "").split(","):
        if not part:
            continue
        if not _PAIR_RE.match(part):
            return f"invalid entry {part!r}; expected USER_ID:profile_name"
    return None