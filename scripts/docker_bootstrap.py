"""First-run bootstrap for the Helix Docker image."""

from __future__ import annotations

import os
import sys


def _upsert_profile_env(profile: str, values: dict[str, str]) -> None:
    from core.env_loader import upsert_profile_env_var

    for key, value in values.items():
        if value:
            upsert_profile_env_var(profile, key, value)


def bootstrap() -> None:
    from cli.core import ProfileManager
    from core.env_loader import bootstrap_profile_env, init_helix_home
    from integrations.telegram.env_store import read_telegram_env_values, save_telegram_env

    profile = (os.getenv("HELIX_PROFILE") or "default").strip() or "default"
    init_helix_home()
    manager = ProfileManager()
    if not manager.profile_exists(profile):
        manager.create_profile(profile)
        print(f"[helix] Created profile '{profile}'", flush=True)

    bootstrap_profile_env(profile, force=True)

    profile_env: dict[str, str] = {
        "HELIX_ENV": os.getenv("HELIX_ENV", "production"),
        "HELIX_GATEWAY_HOST": os.getenv("HELIX_GATEWAY_HOST", "0.0.0.0"),
        "HELIX_GATEWAY_PORT": os.getenv("HELIX_GATEWAY_PORT", "8000"),
        "HELIX_REQUIRE_AUTH": os.getenv("HELIX_REQUIRE_AUTH", "true"),
    }
    for key in (
        "MODEL",
        "BASE_URL",
        "API_KEY",
        "TEMPERATURE",
        "HELIX_API_KEY_PEPPER",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "LITELLM_API_BASE",
        "LITELLM_API_KEY",
        "OLLAMA_HOST",
        "HELIX_ENABLE_TERMINAL_TOOL",
        "HELIX_ENABLE_CODE_EXECUTOR",
        "HELIX_TELEGRAM_VOICE_ENABLED",
        "HELIX_TELEGRAM_FILES_ENABLED",
        "ENABLE_BROWSER_TOOLS",
    ):
        val = os.getenv(key, "").strip()
        if val:
            profile_env[key] = val
    _upsert_profile_env(profile, profile_env)

    token = os.getenv("TELEGRAM_BOT_TOKEN", os.getenv("HELIX_TELEGRAM_BOT_TOKEN", "")).strip()
    if token:
        existing = read_telegram_env_values(profile)
        tg_values = {
            "TELEGRAM_BOT_TOKEN": token,
            "HELIX_TELEGRAM_ACCESS_REQUESTS": os.getenv(
                "HELIX_TELEGRAM_ACCESS_REQUESTS",
                "true",
            ),
        }
        allowed = os.getenv("HELIX_TELEGRAM_ALLOWED_USERS", "").strip()
        if allowed:
            tg_values["HELIX_TELEGRAM_ALLOWED_USERS"] = allowed.replace(" ", "")
        elif existing.get("HELIX_TELEGRAM_ALLOWED_USERS"):
            tg_values["HELIX_TELEGRAM_ALLOWED_USERS"] = existing["HELIX_TELEGRAM_ALLOWED_USERS"]
        path = save_telegram_env(tg_values, profile=profile)
        print(f"[helix] Telegram configured: {path}", flush=True)
    else:
        print("[helix] TELEGRAM_BOT_TOKEN not set — Telegram bot disabled", flush=True)


if __name__ == "__main__":
    try:
        bootstrap()
    except Exception as exc:
        print(f"[helix] bootstrap failed: {exc}", file=sys.stderr, flush=True)
        raise