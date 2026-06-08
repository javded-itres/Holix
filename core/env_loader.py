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
    """Return ``~/.helix/profiles/<profile>``."""
    from cli.core import PROFILES_DIR

    name = (profile or active_profile_name()).strip() or "default"
    return (PROFILES_DIR / name).resolve()


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


def _seed_profile_env(profile: str) -> Path:
    """Ensure ``profiles/<profile>/.env`` exists (copy from global or template)."""
    target = profile_env_path(profile)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        return target

    global_env = helix_env_path()
    if global_env.is_file():
        target.write_text(global_env.read_text(encoding="utf-8"), encoding="utf-8")
        return target

    src = _find_env_example_path()
    if src and src.is_file():
        target.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        target.write_text("# Helix profile environment\n", encoding="utf-8")
    return target


def init_helix_home() -> Path:
    """Create ``HELIX_HOME`` and seed legacy ``.env.example`` / ``.env`` on first run."""
    home = helix_home()
    first_run = not home.exists()
    home.mkdir(parents=True, exist_ok=True)
    _seed_env_files(first_run=first_run)
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
    2. ``~/.helix/.env`` (legacy global fallback)

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
    _seed_profile_env(name)
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

    lines = [
        "## Helix configuration paths",
        "",
        "Environment variables load in this order (highest priority wins):",
        "1. Process/shell environment (already exported in the session)",
        f"2. Profile env file: `{prof_env}` ({_file_tag(prof_env)})",
    ]
    if legacy_env.resolve() != prof_env.resolve():
        lines.append(
            f"3. Legacy global env (fallback): `{legacy_env}` ({_file_tag(legacy_env)})"
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
            f"- **Profile config**: `{profile_yaml}` ({_file_tag(profile_yaml)})",
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


def ensure_profile_env_template(profile: str) -> Path:
    """Create ``profiles/<profile>/.env`` from template or legacy global env."""
    return _seed_profile_env(profile)