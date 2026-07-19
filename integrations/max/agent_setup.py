"""Initialize HolixAgent for MAX sessions."""

from __future__ import annotations

from cli.core import ProfileConfig, init_profile

from integrations.max.profile_auth import authorize_max_profile_access


async def create_agent(
    profile: str,
    config: ProfileConfig | None = None,
    *,
    bot_profile: str | None = None,
    max_user_id: int | None = None,
    profile_key: str | None = None,
):
    if bot_profile is not None and max_user_id is not None:
        authorize_max_profile_access(bot_profile, max_user_id, profile)
        if config is None:
            from cli.core import ProfileManager

            from integrations.max.profile_seed import seed_max_user_profile_from_bot

            seed_max_user_profile_from_bot(
                ProfileManager(),
                bot_profile=bot_profile,
                user_profile=profile,
            )
    from integrations.messenger.locale import ensure_messenger_locale

    ensure_messenger_locale(profile)
    config = config or init_profile(profile, profile_key=profile_key, prompt_key=False)

    import os

    from core.application.profile_runtime import resolve_profile_agent_config
    from core.di import create_agent as di_create_agent

    # Multi-user messenger host: no self-authored extensions into shared agent state.
    os.environ.setdefault("HOLIX_MESSENGER_HOST", "max")

    runtime_config = resolve_profile_agent_config(profile, config)
    runtime_config = runtime_config.with_overrides(self_extensions_enabled=False)
    agent, _container = await di_create_agent(runtime_config)
    return agent