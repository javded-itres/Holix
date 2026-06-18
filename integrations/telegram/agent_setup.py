"""Initialize HolixAgent for Telegram sessions."""

from __future__ import annotations

from cli.core import ProfileConfig, init_profile
from core.agent import HolixAgent

from integrations.telegram.profile_auth import authorize_telegram_profile_access


async def create_agent(
    profile: str,
    config: ProfileConfig | None = None,
    *,
    bot_profile: str | None = None,
    telegram_user_id: int | None = None,
    profile_key: str | None = None,
) -> HolixAgent:
    if bot_profile is not None and telegram_user_id is not None:
        authorize_telegram_profile_access(bot_profile, telegram_user_id, profile)
        if config is None:
            from cli.core import ProfileManager

            from integrations.telegram.profile_seed import seed_telegram_user_profile_from_bot

            seed_telegram_user_profile_from_bot(
                ProfileManager(),
                bot_profile=bot_profile,
                user_profile=profile,
            )
    from integrations.messenger.locale import ensure_messenger_locale

    ensure_messenger_locale(profile)
    config = config or init_profile(profile, profile_key=profile_key, prompt_key=False)
    from core.paths import ensure_profile_memory_dirs

    ensure_profile_memory_dirs(profile)
    from core.di import resolve_runtime_config

    runtime_config = resolve_runtime_config(config)
    try:
        from core.models.manager import ModelManager

        mc = ModelManager(config).get_default_model_config()
        if mc:
            runtime_config = runtime_config.with_overrides(
                model=mc.model,
                base_url=mc.base_url,
                api_key=mc.api_key,
                temperature=mc.temperature,
            )
    except Exception:
        pass

    agent = HolixAgent(config=runtime_config)
    await agent.initialize()
    return agent