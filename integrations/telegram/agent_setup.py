"""Initialize HolixAgent for Telegram sessions."""

from __future__ import annotations

from cli.core import ProfileConfig

from integrations.telegram.profile_auth import (
    init_profile_for_telegram,
    telegram_user_may_access_profile,
)


async def create_agent(
    profile: str,
    config: ProfileConfig | None = None,
    *,
    bot_profile: str | None = None,
    telegram_user_id: int | None = None,
    profile_key: str | None = None,
):
    if bot_profile is not None and telegram_user_id is not None:
        if not telegram_user_may_access_profile(bot_profile, telegram_user_id, profile):
            msg = (
                f"Telegram user {telegram_user_id} is not authorized for profile '{profile}'"
            )
            raise PermissionError(msg)
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
    if config is None:
        from cli.core import init_profile

        if bot_profile is not None and telegram_user_id is not None:
            config = init_profile_for_telegram(
                profile,
                bot_profile=bot_profile,
                telegram_user_id=telegram_user_id,
                profile_key=profile_key,
            )
        else:
            config = init_profile(profile, profile_key=profile_key, prompt_key=False)

    from core.application.profile_runtime import resolve_profile_agent_config
    from core.di import create_agent as di_create_agent

    runtime_config = resolve_profile_agent_config(profile, config)
    agent, _container = await di_create_agent(runtime_config)
    return agent