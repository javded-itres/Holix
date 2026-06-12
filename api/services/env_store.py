"""Read/write Holix global and profile env files."""

from __future__ import annotations

import os
from pathlib import Path

from core.env_loader import ensure_profile_env_template, profile_env_path


def _read_env_map(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        from dotenv import dotenv_values
    except ImportError:
        return {}
    return {
        key: str(value)
        for key, value in dotenv_values(path).items()
        if value is not None and str(value).strip()
    }


def read_global_env_map() -> dict[str, str]:
    from core.global_config import ensure_global_env_template, global_env_path

    ensure_global_env_template()
    return _read_env_map(global_env_path())


def patch_env_file(path: Path, variables: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    existing_keys = {line.split("=", 1)[0] for line in lines if "=" in line}
    for key, value in variables.items():
        prefix = f"{key}="
        lines = [line for line in lines if not line.startswith(prefix)]
        lines.append(f"{prefix}{value}")
        os.environ[key] = value
        existing_keys.add(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def patch_global_env(variables: dict[str, str]) -> Path:
    from core.global_config import ensure_global_env_template

    path = ensure_global_env_template()
    patch_env_file(path, variables)
    return path


def patch_profile_env(profile: str, variables: dict[str, str]) -> Path:
    ensure_profile_env_template(profile)
    path = profile_env_path(profile)
    patch_env_file(path, variables)
    return path