"""Manage ``HELIX_TELEGRAM_ALLOWED_USERS`` for a bot profile."""

from __future__ import annotations

from integrations.telegram.env_store import read_telegram_env_values, save_telegram_env


def load_allowed_user_ids(bot_profile: str) -> set[int]:
    """Read allowlist from disk on every call (safe for live approve/reject)."""
    from integrations.telegram.env_store import load_telegram_env_files

    load_telegram_env_files(bot_profile)
    raw = read_telegram_env_values(bot_profile).get(
        "HELIX_TELEGRAM_ALLOWED_USERS",
        "",
    )
    out: set[int] = set()
    for part in raw.replace(" ", "").split(","):
        if part.isdigit():
            out.add(int(part))
    return out


def format_allowed_user_ids(user_ids: set[int]) -> str:
    return ",".join(str(uid) for uid in sorted(user_ids))


def add_allowed_user(bot_profile: str, user_id: int) -> str:
    """Append user id to allowlist and persist. Returns updated allowlist string."""
    values = read_telegram_env_values(bot_profile)
    allowed = load_allowed_user_ids(bot_profile)
    allowed.add(int(user_id))
    text = format_allowed_user_ids(allowed)
    values["HELIX_TELEGRAM_ALLOWED_USERS"] = text
    save_telegram_env(values, profile=bot_profile)
    return text


def remove_allowed_user(bot_profile: str, user_id: int) -> str | None:
    values = read_telegram_env_values(bot_profile)
    allowed = load_allowed_user_ids(bot_profile)
    if int(user_id) not in allowed:
        return None
    allowed.remove(int(user_id))
    text = format_allowed_user_ids(allowed)
    if text:
        values["HELIX_TELEGRAM_ALLOWED_USERS"] = text
    else:
        values.pop("HELIX_TELEGRAM_ALLOWED_USERS", None)
    save_telegram_env(values, profile=bot_profile)
    return text