"""Profile terminal whitelist helpers (env-backed)."""

from __future__ import annotations

from core.env_loader import read_profile_env_map, remove_profile_env_vars, upsert_profile_env_var
from core.security.safety import CommandWhitelist

WHITELIST_ENABLED_KEY = "HELIX_TERMINAL_COMMAND_WHITELIST"
WHITELIST_ENABLED_LEGACY_KEY = "TERMINAL_COMMAND_WHITELIST"
WHITELIST_EXTRA_KEY = "HELIX_TERMINAL_WHITELIST_EXTRA"
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
    value = "true" if enabled else "false"
    remove_profile_env_vars(
        profile,
        WHITELIST_ENABLED_KEY,
        WHITELIST_ENABLED_LEGACY_KEY,
    )
    upsert_profile_env_var(profile, WHITELIST_ENABLED_KEY, value)


def add_whitelist_commands(profile: str, commands: str) -> list[str]:
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
    else:
        remove_profile_env_vars(profile, WHITELIST_EXTRA_KEY, WHITELIST_EXTRA_LEGACY_KEY)
        upsert_profile_env_var(profile, WHITELIST_EXTRA_KEY, format_command_list(merged))
    return added


def builtin_whitelist_commands() -> list[str]:
    checker = CommandWhitelist()
    return sorted(checker.safe_commands)


def effective_whitelist_commands(profile: str) -> list[str]:
    checker = CommandWhitelist()
    checker.apply_extra(format_command_list(read_whitelist_extra(profile)))
    return sorted(checker.safe_commands)