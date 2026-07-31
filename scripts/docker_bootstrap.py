"""First-run bootstrap for the Holix Docker image.

Creates the named profile, writes LLM / messenger env, enables workspace jail
for multi-user production, and ensures extension drop-in directories exist.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _truthy(name: str, default: str = "") -> bool:
    raw = os.getenv(name, default).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _upsert_profile_env(profile: str, values: dict[str, str]) -> None:
    from core.env_loader import upsert_profile_env_var

    for key, value in values.items():
        if value:
            upsert_profile_env_var(profile, key, value)


def _default_profile_name() -> str:
    """Production-safe host profile (``default`` is forbidden when HOLIX_ENV=production)."""
    env_name = (os.getenv("HOLIX_ENV") or "production").strip().lower()
    configured = (os.getenv("HOLIX_PROFILE") or "").strip()
    if configured:
        if env_name == "production" and configured == "default":
            print(
                "[holix] WARN: HOLIX_PROFILE=default is invalid in production; using 'shared'",
                flush=True,
            )
            return "shared"
        return configured
    return "default" if env_name != "production" else "shared"


def _bootstrap_extensions_dirs(home: Path, profile: str) -> None:
    global_ext = home / "extensions"
    global_ext.mkdir(parents=True, exist_ok=True)
    try:
        from core.profile.names import profile_dir_for_name

        prof_ext = profile_dir_for_name(profile) / "extensions"
        prof_ext.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        print(f"[holix] WARN: profile extensions dir: {exc}", flush=True)
    files = Path(os.getenv("HOLIX_FILES_DIR") or "/data/files")
    try:
        files.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def _enable_workspace_jail(manager: object, profile: str) -> None:
    if not _truthy("HOLIX_WORKSPACE_JAIL", "true"):
        return
    try:
        from core.profile.service import enable_profile_workspace_isolation

        path = enable_profile_workspace_isolation(manager, profile)  # type: ignore[arg-type]
        print(f"[holix] Workspace jail enabled: {path}", flush=True)
    except Exception as exc:
        print(f"[holix] WARN: workspace jail: {exc}", flush=True)


def _bootstrap_max(profile: str) -> None:
    token = (
        os.getenv("MAX_ACCESS_TOKEN", "").strip()
        or os.getenv("HOLIX_MAX_ACCESS_TOKEN", "").strip()
    )
    if not token:
        return
    try:
        from core.env_loader import upsert_profile_env_var

        upsert_profile_env_var(profile, "MAX_ACCESS_TOKEN", token)
        upsert_profile_env_var(profile, "HOLIX_MAX_ACCESS_TOKEN", token)
        print("[holix] MAX messenger token configured", flush=True)
    except Exception as exc:
        print(f"[holix] WARN: MAX bootstrap: {exc}", flush=True)


def bootstrap() -> None:
    from cli.core import ProfileManager
    from core.env_loader import bootstrap_profile_env, holix_home, init_holix_home
    from integrations.telegram.env_store import read_telegram_env_values, save_telegram_env

    profile = _default_profile_name()
    # Ensure process env matches resolved name (entrypoint / holix -p)
    os.environ["HOLIX_PROFILE"] = profile

    init_holix_home()
    home = Path(holix_home())
    _bootstrap_extensions_dirs(home, profile)

    manager = ProfileManager()
    if not manager.profile_exists(profile):
        manager.create_profile(profile)
        print(f"[holix] Created profile '{profile}'", flush=True)

    bootstrap_profile_env(profile, force=True)
    _enable_workspace_jail(manager, profile)

    profile_env: dict[str, str] = {
        "HOLIX_ENV": os.getenv("HOLIX_ENV", "production"),
        "HOLIX_GATEWAY_HOST": os.getenv("HOLIX_GATEWAY_HOST", "0.0.0.0"),
        "HOLIX_GATEWAY_PORT": os.getenv("HOLIX_GATEWAY_PORT", "8000"),
        "HOLIX_REQUIRE_AUTH": os.getenv("HOLIX_REQUIRE_AUTH", "true"),
    }
    for key in (
        "MODEL",
        "BASE_URL",
        "API_KEY",
        "TEMPERATURE",
        "HOLIX_API_KEY_PEPPER",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "DEEPSEEK_API_KEY",
        "MOONSHOT_API_KEY",
        "XAI_API_KEY",
        "GROQ_API_KEY",
        "GOOGLE_API_KEY",
        "MISTRAL_API_KEY",
        "LITELLM_API_BASE",
        "LITELLM_API_KEY",
        "OLLAMA_HOST",
        "VLLM_HOST",
        "HOLIX_ENABLE_TERMINAL_TOOL",
        "HOLIX_ENABLE_CODE_EXECUTOR",
        "HOLIX_TERMINAL_COMMAND_WHITELIST",
        "HOLIX_TELEGRAM_VOICE_ENABLED",
        "HOLIX_TELEGRAM_FILES_ENABLED",
        "ENABLE_BROWSER_TOOLS",
        "BROWSER_HEADLESS",
        "HOLIX_CORS_ORIGINS",
        "HOLIX_UNLOCK_KEY",
        "MAX_STEPS",
        "HOLIX_ENABLE_META_AGENT",
        "HOLIX_ENABLE_SELF_REFINEMENT",
        "HOLIX_SUBAGENT_SUPERVISOR_ENABLED",
    ):
        val = os.getenv(key, "").strip()
        if val:
            profile_env[key] = val
    _upsert_profile_env(profile, profile_env)

    token = os.getenv("TELEGRAM_BOT_TOKEN", os.getenv("HOLIX_TELEGRAM_BOT_TOKEN", "")).strip()
    if token:
        existing = read_telegram_env_values(profile)
        tg_values = {
            "TELEGRAM_BOT_TOKEN": token,
            "HOLIX_TELEGRAM_ACCESS_REQUESTS": os.getenv(
                "HOLIX_TELEGRAM_ACCESS_REQUESTS",
                "true",
            ),
        }
        allowed = os.getenv("HOLIX_TELEGRAM_ALLOWED_USERS", "").strip()
        if allowed:
            tg_values["HOLIX_TELEGRAM_ALLOWED_USERS"] = allowed.replace(" ", "")
        elif existing.get("HOLIX_TELEGRAM_ALLOWED_USERS"):
            tg_values["HOLIX_TELEGRAM_ALLOWED_USERS"] = existing["HOLIX_TELEGRAM_ALLOWED_USERS"]

        admin_id = os.getenv("HOLIX_TELEGRAM_ADMIN_USER_ID", "").strip()
        if admin_id:
            tg_values["HOLIX_TELEGRAM_ADMIN_USER_ID"] = admin_id
        allow_all = os.getenv("HOLIX_TELEGRAM_ALLOW_ALL", "").strip()
        if allow_all:
            tg_values["HOLIX_TELEGRAM_ALLOW_ALL"] = allow_all

        path = save_telegram_env(tg_values, profile=profile)
        print(f"[holix] Telegram configured: {path}", flush=True)
    else:
        print("[holix] TELEGRAM_BOT_TOKEN not set — Telegram bot disabled", flush=True)

    _bootstrap_max(profile)

    # Hint for multi-user
    if _truthy("HOLIX_TELEGRAM_ACCESS_REQUESTS", "true") and token:
        print(
            "[holix] Multi-user: users send /start, then "
            f"docker compose exec holix holix -p {profile} telegram requests approve USER_ID "
            "--create-profile <name>",
            flush=True,
        )

    print(f"[holix] Bootstrap complete (profile={profile}, home={home})", flush=True)


if __name__ == "__main__":
    try:
        bootstrap()
    except Exception as exc:
        print(f"[holix] bootstrap failed: {exc}", file=sys.stderr, flush=True)
        raise
