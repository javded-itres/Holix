"""Load Helix environment files from profile dirs (and optional project .env)."""

from __future__ import annotations

import os
from pathlib import Path

from core.platform_compat import resolve_helix_home

_BOOTSTRAPPED = False
_SHELL_ENV_KEYS: set[str] | None = None
_ACTIVE_PROFILE_ENV: str | None = None


def helix_home() -> Path:
    return resolve_helix_home()


def helix_env_path() -> Path:
    """Legacy global env file: ``{HELIX_HOME}/.env`` (fallback for migration)."""
    return helix_home() / ".env"


def project_env_path() -> Path:
    return Path.cwd() / ".env"


def profile_dir_path(profile: str | None = None) -> Path:
    """Return ``{HELIX_HOME}/profiles/<profile>`` (honours HELIX_HOME at call time)."""
    from cli.core import profiles_dir

    name = (profile or active_profile_name()).strip() or "default"
    return (profiles_dir() / name).resolve()


def profile_env_path(profile: str | None = None) -> Path:
    """Primary per-profile env file: ``profiles/<name>/.env``."""
    return profile_dir_path(profile) / ".env"


def _shell_locked_keys() -> set[str]:
    global _SHELL_ENV_KEYS
    if _SHELL_ENV_KEYS is None:
        _SHELL_ENV_KEYS = set(os.environ.keys())
    return _SHELL_ENV_KEYS


def _find_env_example_path() -> Path | None:
    candidates: list[Path] = [
        Path.cwd() / ".env.example",
        Path(__file__).resolve().parents[1] / ".env.example",
    ]
    try:
        import config

        candidates.append(Path(config.__file__).resolve().parent / ".env.example")
    except Exception:
        pass
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _seed_env_files(*, first_run: bool) -> None:
    """Copy bundled ``.env.example`` into ``~/.helix`` on first setup."""
    home = helix_home()
    example_dst = home / ".env.example"
    env_dst = helix_env_path()
    src = _find_env_example_path()

    if src is None:
        if not env_dst.is_file():
            env_dst.write_text("# Helix environment\n", encoding="utf-8")
        return

    content = src.read_text(encoding="utf-8")
    if first_run and not example_dst.is_file():
        example_dst.write_text(content, encoding="utf-8")
    if not env_dst.is_file():
        env_dst.write_text(content, encoding="utf-8")


def _seed_profile_env(profile: str, *, inherit_global: bool = True) -> Path:
    """Ensure ``profiles/<profile>/.env`` exists.

    When *inherit_global* is true (default), create a minimal stub so runtime
    loads shared values from ``global/.env`` / legacy ``~/.helix/.env``.
    When false (--clean profile), write an empty profile env for manual setup.
    """
    target = profile_env_path(profile)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        return target

    if inherit_global:
        target.write_text(
            "# Profile overrides only — unset keys inherit from ~/.helix/global/.env\n",
            encoding="utf-8",
        )
        return target

    target.write_text(
        "# Clean profile — configure API keys and feature flags here\n",
        encoding="utf-8",
    )
    return target


def init_helix_home() -> Path:
    """Create ``HELIX_HOME`` and seed legacy ``.env.example`` / ``.env`` on first run."""
    home = helix_home()
    first_run = not home.exists()
    home.mkdir(parents=True, exist_ok=True)
    _seed_env_files(first_run=first_run)
    try:
        from core.global_config import ensure_global_config, ensure_global_env_template

        ensure_global_config()
        ensure_global_env_template()
    except Exception:
        pass
    return home


def _apply_env_file(path: Path, *, override_file_values: bool = False) -> None:
    if not path.is_file():
        return
    try:
        from dotenv import dotenv_values
    except ImportError:
        return

    locked = _shell_locked_keys()
    for key, value in dotenv_values(path).items():
        if value is None or not str(value).strip():
            continue
        if key in locked:
            continue
        if not override_file_values and key in os.environ:
            continue
        os.environ[key] = str(value)


def bootstrap_env(*, include_project: bool = True, force: bool = False) -> None:
    """Load env files into ``os.environ`` without overriding the shell.

    Priority (lowest → highest among files):
    1. ``./.env`` in the current working directory (dev convenience)
    2. ``~/.helix/global/.env`` (shared global settings)
    3. ``~/.helix/.env`` (legacy global fallback when ``global/.env`` is absent)

    Variables already set in the process environment are never overwritten.
    """
    global _BOOTSTRAPPED, _SHELL_ENV_KEYS
    init_helix_home()
    if _BOOTSTRAPPED and not force:
        return

    if force:
        _SHELL_ENV_KEYS = set(os.environ.keys())
    _shell_locked_keys()

    try:
        from dotenv import dotenv_values
    except ImportError:
        _BOOTSTRAPPED = True
        return

    merged: dict[str, str | None] = {}
    if include_project:
        proj = project_env_path()
        if proj.is_file():
            merged.update(dotenv_values(proj))

    try:
        from core.global_config import global_env_path

        shared_env = global_env_path()
        if shared_env.is_file():
            merged.update(dotenv_values(shared_env))
        else:
            user_env = helix_env_path()
            if user_env.is_file():
                merged.update(dotenv_values(user_env))
    except Exception:
        user_env = helix_env_path()
        if user_env.is_file():
            merged.update(dotenv_values(user_env))

    locked = _shell_locked_keys()
    for key, value in merged.items():
        if value is None or not str(value).strip() or key in locked:
            continue
        os.environ[key] = str(value)

    _BOOTSTRAPPED = True


def bootstrap_profile_env(profile: str, *, force: bool = False) -> None:
    """Load profile-specific ``.env`` on top of global bootstrap.

    Profile values override global file values but never shell exports.
    """
    global _ACTIVE_PROFILE_ENV, _SHELL_ENV_KEYS
    if force:
        _SHELL_ENV_KEYS = set(os.environ.keys())
    bootstrap_env(force=force)
    name = (profile or "default").strip() or "default"
    os.environ["HELIX_PROFILE"] = name
    _seed_profile_env(name, inherit_global=True)
    _apply_env_file(profile_env_path(name), override_file_values=True)
    _ACTIVE_PROFILE_ENV = name


def active_profile_name() -> str:
    return (os.environ.get("HELIX_PROFILE") or "default").strip() or "default"


def _file_tag(path: Path) -> str:
    return "present" if path.is_file() else "missing"


def format_env_context_block(*, profile_name: str | None = None) -> str:
    """Markdown for system prompts: where Helix env vars and profile config live."""
    profile = (profile_name or active_profile_name()).strip() or "default"
    home = helix_home()
    prof_env = profile_env_path(profile)
    legacy_env = helix_env_path()
    proj_env = project_env_path()
    tg_env = profile_dir_path(profile) / "telegram.env"
    profile_yaml = profile_dir_path(profile) / "config.yaml"
    skills_dir = profile_dir_path(profile) / "data" / "skills"
    gateway_dir = profile_dir_path(profile) / "gateway"

    try:
        from core.global_config import global_config_path, global_env_path

        g_env = global_env_path()
        g_cfg = global_config_path()
    except Exception:
        g_env = home / "global" / ".env"
        g_cfg = home / "global" / "config.yaml"

    lines = [
        "## Helix configuration paths",
        "",
        "Environment variables load in this order (highest priority wins):",
        "1. Process/shell environment (already exported in the session)",
        f"2. Profile env file: `{prof_env}` ({_file_tag(prof_env)})",
        f"3. Global env file: `{g_env}` ({_file_tag(g_env)})",
    ]
    if legacy_env.resolve() != prof_env.resolve() and not g_env.is_file():
        lines.append(
            f"4. Legacy global env (fallback): `{legacy_env}` ({_file_tag(legacy_env)})"
        )
    if proj_env.resolve() != prof_env.resolve():
        suffix = "optional" if not proj_env.is_file() else "present"
        lines.append(f"4. Project `.env` overlay: `{proj_env}` ({suffix})")
    lines.extend(
        [
            "",
            "Each profile is isolated: own `.env`, Telegram secrets, gateway state, "
            "memory, and skills under `profiles/<name>/`.",
            "",
            f"- **HELIX_HOME**: `{home}`",
            f"- **Active profile** (`HELIX_PROFILE`): `{profile}`",
            f"- **Global config**: `{g_cfg}` ({_file_tag(g_cfg)})",
            f"- **Profile config** (overrides): `{profile_yaml}` ({_file_tag(profile_yaml)})",
            f"- **Profile skills**: `{skills_dir}/`",
            f"- **Telegram bot secrets**: `{tg_env}` ({_file_tag(tg_env)})",
            f"- **Gateway state/logs**: `{gateway_dir}/`",
            "",
            "To change API keys, gateway bind, Telegram, or feature flags, edit the "
            f"profile env file `{prof_env}` and/or profile YAML — not application source. "
            "Web search: `search:` block in profile YAML or `helix search configure`. "
            "After env changes with gateway/Telegram running: `helix gateway reload`.",
        ]
    )
    return "\n".join(lines)


def ensure_helix_env_template(example_path: Path | None = None) -> Path:
    """Create legacy ``~/.helix/.env`` from ``.env.example`` when missing."""
    home = init_helix_home()
    target = helix_env_path()
    if target.is_file():
        return target

    src = example_path if example_path and example_path.is_file() else _find_env_example_path()
    if src and src.is_file():
        content = src.read_text(encoding="utf-8")
        target.write_text(content, encoding="utf-8")
        example_dst = home / ".env.example"
        if not example_dst.is_file():
            example_dst.write_text(content, encoding="utf-8")
    else:
        target.write_text("# Helix environment\n", encoding="utf-8")

    return target


def ensure_profile_env_template(profile: str, *, inherit_global: bool = True) -> Path:
    """Create ``profiles/<profile>/.env`` (minimal stub or clean template)."""
    return _seed_profile_env(profile, inherit_global=inherit_global)


def read_profile_env_map(profile: str) -> dict[str, str]:
    """Return key/value pairs from a profile ``.env`` file."""
    path = ensure_profile_env_template(profile)
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


def upsert_profile_env_var(profile: str, key: str, value: str) -> Path:
    """Set or replace a single variable in the profile ``.env`` file."""
    path = ensure_profile_env_template(profile)
    prefix = f"{key}="
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    lines = [line for line in lines if not line.startswith(prefix)]
    lines.append(f"{prefix}{value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[key] = value
    return path


def remove_profile_env_vars(profile: str, *keys: str) -> Path:
    """Remove variables from the profile ``.env`` file when present."""
    path = ensure_profile_env_template(profile)
    if not path.is_file():
        return path
    prefixes = {f"{key}=" for key in keys}
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not any(line.startswith(prefix) for prefix in prefixes)
    ]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    for key in keys:
        os.environ.pop(key, None)
    return path