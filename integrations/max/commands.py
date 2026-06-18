"""MAX bot help text and slash-command menu."""

from __future__ import annotations

from integrations.max.client import MaxClient
from integrations.telegram.commands import command_specs

MAX_COMMAND_LIMIT = 32
MAX_COMMAND_DESC_LEN = 256


def max_bot_commands(
    locale: str | None = None,
    *,
    bot_profile: str | None = None,
    user_id: int | None = None,
) -> list[dict[str, str]]:
    """Helix slash commands in MAX BotCommand format (name without /)."""
    if bot_profile is not None and user_id is not None:
        from integrations.max.command_access import commands_for_user

        specs = commands_for_user(bot_profile, int(user_id), locale=locale)
    else:
        specs = command_specs(locale)
    return [
        {
            "name": spec.command,
            "description": spec.description[:MAX_COMMAND_DESC_LEN],
        }
        for spec in specs[:MAX_COMMAND_LIMIT]
    ]


async def register_bot_commands(
    client: MaxClient,
    *,
    locale: str | None = None,
    bot_profile: str | None = None,
    user_id: int | None = None,
) -> list[str]:
    """Register commands in MAX autocomplete menu (when user types /)."""
    commands = max_bot_commands(locale, bot_profile=bot_profile, user_id=user_id)
    await client.set_my_commands(commands)
    return [item["name"] for item in commands]


async def sync_bot_menu(profile: str = "default") -> list[str]:
    """Push command menu to MAX API without starting polling."""
    from integrations.messenger.locale import messenger_locale

    from integrations.max.config import load_max_settings

    settings = load_max_settings(profile)
    token = settings.access_token.strip()
    if not token:
        raise RuntimeError("MAX_ACCESS_TOKEN is not set. Run: holix max setup")

    locale = messenger_locale(profile)
    async with MaxClient(token) as client:
        return await register_bot_commands(client, locale=locale)


def help_message_markdown(
    locale: str | None = None,
    *,
    bot_profile: str | None = None,
    user_id: int | None = None,
) -> str:
    if bot_profile is not None and user_id is not None:
        from integrations.max.command_access import commands_for_user

        specs = commands_for_user(bot_profile, int(user_id), locale=locale)
    else:
        specs = command_specs(locale)
    lines = [
        "**Holix в MAX**",
        "",
        "Пишите задачи обычным текстом — агент использует инструменты, память и навыки.",
        "",
        "**Слэш-команды:**",
    ]
    for spec in specs:
        lines.append(f"• `{spec.slash}` — {spec.description}")
    lines.extend(
        [
            "",
            "`ping` — проверка связи",
            "`/stop` — остановить текущий запуск",
        ]
    )
    return "\n".join(lines)