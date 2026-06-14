"""Copy bot profile settings into a user's Holix profile (MAX multi-tenant)."""

from __future__ import annotations

from cli.core import ProfileManager


def seed_max_user_profile_from_bot(
    manager: ProfileManager,
    *,
    bot_profile: str,
    user_profile: str,
) -> None:
    """Mirror telegram profile_seed: inherit LLM/MCP/skills from bot host profile."""
    from integrations.telegram.profile_seed import seed_telegram_user_profile_from_bot

    seed_telegram_user_profile_from_bot(
        manager,
        bot_profile=bot_profile,
        user_profile=user_profile,
    )