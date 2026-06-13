"""Read/write Holix global and profile env files."""

from __future__ import annotations

import os
import re
from pathlib import Path

from core.env_loader import ensure_profile_env_template, profile_env_path


def _read_env_map(path: Path, *, profile: str | None = None) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        from core.crypto.profile_files import dotenv_values_for_path
    except ImportError:
        return {}
    return {
        key: str(value)
        for key, value in dotenv_values_for_path(path, profile=profile).items()
        if value is not None and str(value).strip()
    }


def read_global_env_map() -> dict[str, str]:
    from core.global_config import ensure_global_env_template, global_env_path

    ensure_global_env_template()
    return _read_env_map(global_env_path())


def _format_env_value(value: str) -> str:
    if re.search(r'[\r\n#"\\]', value):
        escaped = (
            value.replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace('"', '\\"')
        )
        return f'"{escaped}"'
    return value


def patch_env_file(path: Path, variables: dict[str, str], *, profile: str | None = None) -> None:
    from core.crypto.profile_files import read_profile_file_text, write_profile_file_text

    name = profile or (path.parent.name if path.parent.name != "profiles" else None)
    if path.is_file() and name:
        text = read_profile_file_text(path, profile=name)
        lines = text.splitlines()
    elif path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()
    else:
        lines = []
    existing_keys = {line.split("=", 1)[0] for line in lines if "=" in line}
    for key, value in variables.items():
        prefix = f"{key}="
        lines = [line for line in lines if not line.startswith(prefix)]
        lines.append(f"{prefix}{_format_env_value(value)}")
        os.environ[key] = value
        existing_keys.add(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(lines) + ("\n" if lines else "")
    if name:
        write_profile_file_text(path, payload, profile=name)
    else:
        path.write_text(payload, encoding="utf-8")


def patch_global_env(variables: dict[str, str]) -> Path:
    from core.global_config import ensure_global_env_template

    path = ensure_global_env_template()
    patch_env_file(path, variables)
    from core.profile_admin_seed import maybe_seed_admin_on_env_change

    maybe_seed_admin_on_env_change(variables)
    return path


def patch_profile_env(profile: str, variables: dict[str, str]) -> Path:
    ensure_profile_env_template(profile)
    path = profile_env_path(profile)
    patch_env_file(path, variables, profile=profile)
    return path