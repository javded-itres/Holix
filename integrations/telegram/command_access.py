"""Per-user Telegram command and menu visibility in isolated multi-tenant mode."""

from __future__ import annotations

from integrations.telegram.access_approval import is_telegram_admin
from integrations.telegram.commands import TelegramCommandSpec, command_specs
from integrations.telegram.profile_visibility import is_profile_list_hidden

# Hidden from slash menu for non-admins; invocation returns tg.menu_unavailable.
ADMIN_ONLY_COMMANDS: frozenset[str] = frozenset({
    "message",
    "init",
})

# Hidden from inline status panel for non-admins.
ADMIN_ONLY_MENU_ACTIONS: frozenset[str] = frozenset({
    "profile",
})


def commands_restricted_for_user(bot_profile: str, user_id: int) -> bool:
    return is_profile_list_hidden(bot_profile, user_id)


def is_command_allowed(command: str, bot_profile: str, user_id: int) -> bool:
    token = (command or "").strip().lstrip("/").split()[0].lower()
    if not token:
        return True
    if not commands_restricted_for_user(bot_profile, user_id):
        return True
    if token not in ADMIN_ONLY_COMMANDS:
        return True
    return is_telegram_admin(bot_profile, user_id)


def is_menu_action_allowed(action: str, bot_profile: str, user_id: int) -> bool:
    if not commands_restricted_for_user(bot_profile, user_id):
        return True
    if action not in ADMIN_ONLY_MENU_ACTIONS:
        return True
    return is_telegram_admin(bot_profile, user_id)


def is_mcp_management_allowed(bot_profile: str, user_id: int) -> bool:
    """Install, assign, remove, test MCP — admin only in isolated multi-tenant mode."""
    if not commands_restricted_for_user(bot_profile, user_id):
        return True
    return is_telegram_admin(bot_profile, user_id)


def commands_for_user(
    bot_profile: str,
    user_id: int,
    *,
    locale: str | None = None,
) -> list[TelegramCommandSpec]:
    specs = command_specs(locale)
    if not commands_restricted_for_user(bot_profile, user_id):
        return specs
    if is_telegram_admin(bot_profile, user_id):
        return specs
    return [spec for spec in specs if spec.command not in ADMIN_ONLY_COMMANDS]