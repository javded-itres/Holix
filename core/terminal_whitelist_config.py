"""Profile terminal whitelist helpers (env-backed)."""

from __future__ import annotations

from core.env_loader import read_profile_env_map, remove_profile_env_vars, upsert_profile_env_var
from core.security.safety import CommandWhitelist

WHITELIST_ENABLED_KEY = "HOLIX_TERMINAL_COMMAND_WHITELIST"
WHITELIST_ENABLED_LEGACY_KEY = "TERMINAL_COMMAND_WHITELIST"
WHITELIST_EXTRA_KEY = "HOLIX_TERMINAL_WHITELIST_EXTRA"
WHITELIST_EXTRA_LEGACY_KEY = "TERMINAL_WHITELIST_EXTRA"


def parse_command_list(raw: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for part in (raw or "").split(","):
        cmd = part.strip().lower()
        if cmd and cmd not in seen:
            seen.add(cmd)
            out.append(cmd)
    return out


def format_command_list(commands: list[str]) -> str:
    return ",".join(commands)


def _env_bool(raw: str | None, *, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def read_whitelist_enabled(profile: str) -> bool:
    env = read_profile_env_map(profile)
    for key in (WHITELIST_ENABLED_KEY, WHITELIST_ENABLED_LEGACY_KEY):
        if key in env:
            return _env_bool(env[key], default=True)
    return True


def read_whitelist_extra(profile: str) -> list[str]:
    env = read_profile_env_map(profile)
    for key in (WHITELIST_EXTRA_KEY, WHITELIST_EXTRA_LEGACY_KEY):
        if key in env:
            return parse_command_list(env[key])
    return []


def set_whitelist_enabled(profile: str, enabled: bool) -> None:
    import os

    value = "true" if enabled else "false"
    remove_profile_env_vars(
        profile,
        WHITELIST_ENABLED_KEY,
        WHITELIST_ENABLED_LEGACY_KEY,
    )
    upsert_profile_env_var(profile, WHITELIST_ENABLED_KEY, value)
    # Studio runs as a long-lived process: update os.environ so the next
    # terminal call sees the toggle without requiring a full service restart
    # (systemd EnvironmentFile would otherwise keep a stale true until restart).
    os.environ[WHITELIST_ENABLED_KEY] = value
    os.environ[WHITELIST_ENABLED_LEGACY_KEY] = value


def add_whitelist_commands(profile: str, commands: str) -> list[str]:
    import os

    merged = read_whitelist_extra(profile)
    seen = set(merged)
    added: list[str] = []
    for cmd in parse_command_list(commands):
        if cmd in seen:
            continue
        seen.add(cmd)
        merged.append(cmd)
        added.append(cmd)
    if not merged:
        remove_profile_env_vars(profile, WHITELIST_EXTRA_KEY, WHITELIST_EXTRA_LEGACY_KEY)
        os.environ.pop(WHITELIST_EXTRA_KEY, None)
        os.environ.pop(WHITELIST_EXTRA_LEGACY_KEY, None)
    else:
        remove_profile_env_vars(profile, WHITELIST_EXTRA_KEY, WHITELIST_EXTRA_LEGACY_KEY)
        formatted = format_command_list(merged)
        upsert_profile_env_var(profile, WHITELIST_EXTRA_KEY, formatted)
        os.environ[WHITELIST_EXTRA_KEY] = formatted
        os.environ[WHITELIST_EXTRA_LEGACY_KEY] = formatted
    return added


def remove_whitelist_commands(profile: str, commands: str) -> list[str]:
    """Remove commands from profile extras (builtin defaults are never removed)."""
    import os

    current = read_whitelist_extra(profile)
    to_remove = set(parse_command_list(commands))
    if not to_remove:
        return []
    removed: list[str] = []
    kept: list[str] = []
    for cmd in current:
        if cmd in to_remove:
            removed.append(cmd)
        else:
            kept.append(cmd)
    if not removed:
        return []
    if not kept:
        remove_profile_env_vars(profile, WHITELIST_EXTRA_KEY, WHITELIST_EXTRA_LEGACY_KEY)
        os.environ.pop(WHITELIST_EXTRA_KEY, None)
        os.environ.pop(WHITELIST_EXTRA_LEGACY_KEY, None)
    else:
        remove_profile_env_vars(profile, WHITELIST_EXTRA_KEY, WHITELIST_EXTRA_LEGACY_KEY)
        formatted = format_command_list(kept)
        upsert_profile_env_var(profile, WHITELIST_EXTRA_KEY, formatted)
        os.environ[WHITELIST_EXTRA_KEY] = formatted
        os.environ[WHITELIST_EXTRA_LEGACY_KEY] = formatted
    return removed


def builtin_whitelist_commands() -> list[str]:
    checker = CommandWhitelist()
    return sorted(checker.safe_commands)


def effective_whitelist_commands(profile: str) -> list[str]:
    checker = CommandWhitelist()
    checker.apply_extra(format_command_list(read_whitelist_extra(profile)))
    return sorted(checker.safe_commands)