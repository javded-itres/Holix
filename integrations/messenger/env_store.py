"""Per-profile messenger env files (encrypted when profile crypto is enabled)."""

from __future__ import annotations

import os
from pathlib import Path

from core.env_loader import active_profile_name, profile_dir_path
from core.profile.names import validate_profile_name

from integrations.messenger.platform import MessengerPlatform


def messenger_env_path(platform: MessengerPlatform, profile: str | None = None) -> Path:
    name = validate_profile_name(profile if profile is not None else active_profile_name())
    return profile_dir_path(name) / platform.env_filename


def legacy_messenger_env_path(platform: MessengerPlatform) -> Path:
    from core.env_loader import holix_home

    return holix_home() / platform.env_filename


def ensure_holix_home() -> Path:
    from core.env_loader import init_holix_home

    return init_holix_home()


def _env_value_missing(key: str) -> bool:
    if key not in os.environ:
        return True
    return not str(os.environ.get(key, "")).strip()


def _first_env_value(platform: MessengerPlatform, canonical_key: str) -> str:
    for key in platform.env_key_aliases(canonical_key):
        val = os.getenv(key, "").strip()
        if val:
            return val
    return ""


def load_messenger_env_files(platform: MessengerPlatform, profile: str | None = None) -> None:
    """Load profile env, then profile messenger env (legacy global as fallback)."""
    from core.env_loader import bootstrap_profile_env

    name = (profile or active_profile_name()).strip() or "default"
    try:
        from core.crypto.unlock_context import bootstrap_profile_unlock_from_env

        bootstrap_profile_unlock_from_env(name)
    except Exception:
        pass
    bootstrap_profile_env(name)

    try:
        from core.crypto.profile_files import dotenv_values_for_path
    except ImportError:
        return

    path = messenger_env_path(platform, name)
    if path.is_file():
        for key, value in dotenv_values_for_path(path, profile=name).items():
            if value is not None and str(value).strip() and _env_value_missing(key):
                os.environ[key] = str(value)
        return

    legacy = legacy_messenger_env_path(platform)
    if legacy.is_file():
        for key, value in dotenv_values_for_path(legacy).items():
            if value is not None and str(value).strip() and _env_value_missing(key):
                os.environ[key] = str(value)


def format_env_lines(platform: MessengerPlatform, values: dict[str, str]) -> str:
    lines: list[str] = []
    if platform.env_header:
        lines.extend([platform.env_header, ""])
    written: set[str] = set()
    for key in platform.env_key_order:
        if key in values and values[key]:
            lines.append(f"{key}={values[key]}")
            written.add(key)
    for key, val in sorted(values.items()):
        if key not in written and val:
            lines.append(f"{key}={val}")
    return "\n".join(lines) + "\n"


def save_messenger_env(
    platform: MessengerPlatform,
    values: dict[str, str],
    profile: str | None = None,
) -> Path:
    raw = profile or values.get(platform.profile_key) or active_profile_name()
    name = validate_profile_name(raw)
    ensure_holix_home()
    path = messenger_env_path(platform, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    from core.crypto.profile_files import write_profile_file_text

    write_profile_file_text(path, format_env_lines(platform, values), profile=name)
    apply_to_environ(values)
    return path


def apply_to_environ(values: dict[str, str]) -> None:
    for key, value in values.items():
        if value:
            os.environ[key] = value


def read_messenger_env_values(
    platform: MessengerPlatform,
    profile: str | None = None,
) -> dict[str, str]:
    name = validate_profile_name(profile or active_profile_name())
    path = messenger_env_path(platform, name)
    legacy = False
    if not path.is_file():
        path = legacy_messenger_env_path(platform)
        legacy = True
    if not path.is_file():
        return {}
    try:
        from core.crypto.profile_files import dotenv_values_for_path
    except ImportError:
        return {}
    return {
        key: str(value).strip()
        for key, value in dotenv_values_for_path(
            path,
            profile=None if legacy else name,
        ).items()
        if value is not None and str(value).strip()
    }


def merge_project_env(project_env: Path, values: dict[str, str]) -> None:
    keys = set(values)
    existing: list[str] = []
    if project_env.is_file():
        existing = project_env.read_text(encoding="utf-8").splitlines()

    out: list[str] = []
    seen: set[str] = set()
    for line in existing:
        if not line.strip() or line.strip().startswith("#"):
            out.append(line)
            continue
        key, _, _ = line.partition("=")
        key = key.strip()
        if key in keys:
            out.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            out.append(line)

    for key, val in values.items():
        if key not in seen and val:
            if out and out[-1].strip():
                out.append("")
            out.append(f"{key}={val}")

    project_env.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")