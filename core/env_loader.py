"""Load Helix environment files from ~/.helix (and optional project .env)."""

from __future__ import annotations

import os
from pathlib import Path

from core.platform_compat import resolve_helix_home

_BOOTSTRAPPED = False


def helix_home() -> Path:
    return resolve_helix_home()


def helix_env_path() -> Path:
    """Primary user env file: ``{HELIX_HOME}/.env``."""
    return helix_home() / ".env"


def project_env_path() -> Path:
    return Path.cwd() / ".env"


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


def init_helix_home() -> Path:
    """Create ``HELIX_HOME`` and seed ``.env.example`` / ``.env`` on first run."""
    home = helix_home()
    first_run = not home.exists()
    home.mkdir(parents=True, exist_ok=True)
    _seed_env_files(first_run=first_run)
    return home


def bootstrap_env(*, include_project: bool = True, force: bool = False) -> None:
    """Load ``.env`` into ``os.environ`` without overriding the shell.

    Priority (lowest → highest among files):
    1. ``./.env`` in the current working directory (dev convenience)
    2. ``~/.helix/.env`` (user config)

    Variables already set in the process environment are never overwritten.
    """
    global _BOOTSTRAPPED
    init_helix_home()
    if _BOOTSTRAPPED and not force:
        return

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

    for key, value in merged.items():
        if value is None or not str(value).strip() or key in os.environ:
            continue
        os.environ[key] = str(value)

    _BOOTSTRAPPED = True


def active_profile_name() -> str:
    import os

    return (os.environ.get("HELIX_PROFILE") or "default").strip() or "default"


def _file_tag(path: Path) -> str:
    return "present" if path.is_file() else "missing"


def format_env_context_block(*, profile_name: str | None = None) -> str:
    """Markdown for system prompts: where Helix env vars and profile config live."""
    profile = (profile_name or active_profile_name()).strip() or "default"
    home = helix_home()
    user_env = helix_env_path()
    proj_env = project_env_path()
    tg_env = home / "telegram.env"
    profile_yaml = home / "profiles" / profile / "config.yaml"
    skills_dir = home / "profiles" / profile / "data" / "skills"

    lines = [
        "## Helix configuration paths",
        "",
        "Environment variables load in this order (highest priority wins):",
        "1. Process/shell environment (already exported in the session)",
        f"2. User env file: `{user_env}` ({_file_tag(user_env)})",
    ]
    if proj_env.resolve() != user_env.resolve():
        suffix = "optional" if not proj_env.is_file() else "present"
        lines.append(f"3. Project `.env` overlay: `{proj_env}` ({suffix})")
    lines.extend(
        [
            "",
            "File layers: project `.env` loads first, then `~/.helix/.env` overrides "
            "duplicate keys. Shell variables are never overwritten by files.",
            "",
            f"- **HELIX_HOME**: `{home}`",
            f"- **Active profile** (`HELIX_PROFILE`): `{profile}`",
            f"- **Profile config**: `{profile_yaml}` ({_file_tag(profile_yaml)})",
            f"- **Profile skills**: `{skills_dir}/`",
            f"- **Telegram bot secrets** (optional): `{tg_env}` ({_file_tag(tg_env)})",
            "",
            "To change API keys, provider URLs, Telegram, Whisper, or feature flags, "
            f"edit `{user_env}` and/or the profile YAML — not application source code. "
            "Web search (DuckDuckGo / SearXNG / Firecrawl): `search:` block in profile YAML "
            "or `helix search configure`. Keys: `FIRECRAWL_API_KEY`, `SEARXNG_BASE_URL`. "
            "After env changes with gateway/Telegram running: `helix gateway reload`.",
        ]
    )
    return "\n".join(lines)


def ensure_helix_env_template(example_path: Path | None = None) -> Path:
    """Create ``~/.helix/.env`` from ``.env.example`` when missing."""
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