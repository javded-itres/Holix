"""MAX bot help text and slash-command menu."""

from __future__ import annotations

from integrations.max.client import MaxClient
from integrations.telegram.commands import command_specs

MAX_COMMAND_LIMIT = 32
MAX_COMMAND_DESC_LEN = 256

# MAX Bot API allows 32 slash commands. Keep a short user-facing set (no
# TUI/admin extras, no yes/no). Billing aliases are collapsed below.
MAX_MENU_HOST_COMMANDS: tuple[str, ...] = (
    "help",
    "menu",
    "status",
    "models",
    "sessions",
    "new",
    "clear",
    "stop",
    "skills",
    "lang",
)

# Shown first among extension commands. tariffs + invite must stay visible.
MAX_MENU_EXTENSION_PRIORITY: tuple[str, ...] = (
    "start",
    "tariffs",
    "pay",
    "subscription",
    "topup",
    "invite",
    "promo",
    "settings",
)

# Alias → canonical menu name (handlers still accept the alias).
MAX_MENU_EXTENSION_ALIASES: dict[str, str] = {
    "billing": "tariffs",
    "requests": "topup",
    "packs": "topup",
    "cancel": "unsubscribe",
    "unsub": "unsubscribe",
    "auto_renew": "autorenew",
    "promocode": "promo",
    "referral": "invite",
    "ref": "invite",
    "subs": "subscribers",
}

# Not for the user slash menu (admin / nested in another command).
MAX_MENU_EXTENSION_SKIP: frozenset[str] = frozenset(
    {
        "subscribers",
        "unsubscribe",
        "autorenew",
    }
)


def _host_menu_specs(
    locale: str | None = None,
    *,
    bot_profile: str | None = None,
    user_id: int | None = None,
):
    if bot_profile is not None and user_id is not None:
        from integrations.max.command_access import commands_for_user

        specs = commands_for_user(bot_profile, int(user_id), locale=locale)
    else:
        specs = command_specs(locale)
    by_name = {spec.command: spec for spec in specs}
    return [by_name[name] for name in MAX_MENU_HOST_COMMANDS if name in by_name]


def _extension_menu_items() -> list[dict[str, str]]:
    try:
        from integrations.max.plugin_api import extension_bot_commands

        raw = list(extension_bot_commands())
    except Exception:
        return []
    by_name: dict[str, str] = {}
    for ext in raw:
        name = (ext.command or "").strip().lstrip("/").lower()
        if not name:
            continue
        name = MAX_MENU_EXTENSION_ALIASES.get(name, name)
        if name in MAX_MENU_EXTENSION_SKIP:
            continue
        desc = (ext.description or name)[:MAX_COMMAND_DESC_LEN]
        by_name.setdefault(name, desc)
    ordered: list[dict[str, str]] = []
    for name in MAX_MENU_EXTENSION_PRIORITY:
        if name in by_name:
            ordered.append({"name": name, "description": by_name.pop(name)})
    for name, desc in by_name.items():
        ordered.append({"name": name, "description": desc})
    return ordered


def max_bot_commands(
    locale: str | None = None,
    *,
    bot_profile: str | None = None,
    user_id: int | None = None,
) -> list[dict[str, str]]:
    """Helix slash commands in MAX BotCommand format (name without /)."""
    items = [
        {
            "name": spec.command,
            "description": spec.description[:MAX_COMMAND_DESC_LEN],
        }
        for spec in _host_menu_specs(locale, bot_profile=bot_profile, user_id=user_id)
    ]
    seen = {i["name"] for i in items}
    for ext in _extension_menu_items():
        if ext["name"] in seen:
            continue
        items.append(ext)
        seen.add(ext["name"])
        if len(items) >= MAX_COMMAND_LIMIT:
            break
    return items[:MAX_COMMAND_LIMIT]


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
    from integrations.max.config import load_max_settings
    from integrations.messenger.locale import messenger_locale

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
    specs = _host_menu_specs(locale, bot_profile=bot_profile, user_id=user_id)
    lines = [
        "**Holix в MAX**",
        "",
        "Пишите задачи обычным текстом — агент использует инструменты, память и навыки.",
        "",
        "**Слэш-команды:**",
    ]
    for spec in specs:
        lines.append(f"• `{spec.slash}` — {spec.description}")
    for ext in _extension_menu_items():
        lines.append(f"• `/{ext['name']}` — {ext['description']}")
    try:
        from core.commands.help import list_custom_commands

        custom = list_custom_commands()
    except Exception:
        custom = []
    if custom:
        lines.append("")
        lines.append("**Custom commands:**")
        for command in custom:
            desc = command.description or "custom"
            lines.append(f"• `/{command.name}` — {desc} [{command.source}]")
    lines.extend(
        [
            "",
            "`ping` — проверка связи",
            "`/stop` — остановить текущий запуск",
        ]
    )
    return "\n".join(lines)
