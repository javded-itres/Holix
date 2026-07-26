"""Plugin surface for third-party Telegram extensions (billing, CRM, …).

Core stays free of product logic. Extensions call ``register_telegram(api)``
(host extension) or register via entry point ``holix.telegram.extensions``.

Collected hooks are applied when the Telegram bot is built / starts.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

TELEGRAM_ENTRYPOINT_GROUP = "holix.telegram.extensions"

MessageGate = Callable[..., Any]
HandlerRegistrar = Callable[["TelegramPluginAPI"], None]
AccessCheck = Callable[[int], "bool | None"]


@dataclass(frozen=True, slots=True)
class TelegramBotCommand:
    """Slash command contributed to the Telegram bot menu."""

    command: str
    description: str

    def normalized(self) -> TelegramBotCommand:
        cmd = (self.command or "").strip().lstrip("/").lower()
        desc = (self.description or cmd).strip() or cmd
        return TelegramBotCommand(command=cmd, description=desc[:256])


@dataclass(slots=True)
class MessageGateResult:
    """Result of a pre-agent message gate.

    * ``allow=True`` — continue to agent (or next gates).
    * ``allow=False`` — stop; optionally send ``reply_*`` to the user.
    """

    allow: bool = True
    reply_text: str | None = None
    reply_html: str | None = None
    reply_markup: Any = None
    # If True, do not run remaining gates when allow=True
    stop_gates: bool = False


@dataclass
class TelegramPluginAPI:
    """Mutable registry filled by extensions during bot construction."""

    bot_profile: str
    settings: Any
    bot: Any | None = None
    dispatcher: Any | None = None
    get_session: Any | None = None  # async (chat_id, user_id, bot=) -> session
    make_host: Any | None = None  # (bot, session) -> TelegramHost
    commands: list[TelegramBotCommand] = field(default_factory=list)
    message_gates: list[MessageGate] = field(default_factory=list)
    handler_registrars: list[HandlerRegistrar] = field(default_factory=list)
    access_checks: list[AccessCheck] = field(default_factory=list)
    _extensions_loaded: list[str] = field(default_factory=list)

    def add_command(self, command: str, description: str) -> None:
        spec = TelegramBotCommand(command=command, description=description).normalized()
        if not spec.command:
            return
        # Replace same command name
        self.commands = [c for c in self.commands if c.command != spec.command]
        self.commands.append(spec)

    def add_message_gate(self, gate: MessageGate) -> None:
        """Register an async/sync gate run before free-text agent runs."""
        self.message_gates.append(gate)

    def add_handlers(self, registrar: HandlerRegistrar) -> None:
        """``registrar(api)`` attaches aiogram handlers to ``api.dispatcher``."""
        self.handler_registrars.append(registrar)

    def add_access_check(self, check: AccessCheck) -> None:
        """Optional: return False to deny bot access, True to allow, None to abstain."""
        self.access_checks.append(check)


# Last API built for the active bot process (used by command menu merge).
_active_api: TelegramPluginAPI | None = None


def get_active_telegram_plugin_api() -> TelegramPluginAPI | None:
    return _active_api


def set_active_telegram_plugin_api(api: TelegramPluginAPI | None) -> None:
    global _active_api
    _active_api = api


def extension_bot_commands() -> list[TelegramBotCommand]:
    api = _active_api
    if api is None:
        return []
    return list(api.commands)


def _load_from_host_extensions(api: TelegramPluginAPI) -> None:
    try:
        from core.extensions.registry import discover_extensions, startup_extensions

        startup_extensions(profile=api.bot_profile)
        for ext in discover_extensions():
            reg = getattr(ext, "register_telegram", None)
            if not callable(reg):
                continue
            try:
                reg(api)
                api._extensions_loaded.append(str(getattr(ext, "name", type(ext).__name__)))
            except Exception:
                logger.exception(
                    "telegram plugin register_telegram failed for %s",
                    getattr(ext, "name", "?"),
                )
    except Exception:
        logger.exception("failed loading host extensions for telegram plugins")


def _load_from_telegram_entrypoints(api: TelegramPluginAPI) -> None:
    try:
        from core.extensions.registry import _entry_points_for_group
    except Exception:
        return
    already = set(api._extensions_loaded)
    for ep in sorted(_entry_points_for_group(TELEGRAM_ENTRYPOINT_GROUP), key=lambda e: e.name):
        try:
            obj = ep.load()
            if isinstance(obj, type):
                plug = obj()
            elif callable(obj):
                plug = obj()
            else:
                plug = obj
            name = str(getattr(plug, "name", None) or ep.name)
            # Skip if host entry already registered the same extension
            if name in already:
                continue
            reg = getattr(plug, "register_telegram", None)
            if not callable(reg):
                logger.warning("telegram entry point %s has no register_telegram", ep.name)
                continue
            reg(api)
            if name not in api._extensions_loaded:
                api._extensions_loaded.append(name)
                already.add(name)
        except Exception:
            logger.exception("failed to load telegram entry point %s", ep.name)


def load_telegram_plugins(api: TelegramPluginAPI) -> list[str]:
    """Discover and invoke all Telegram plugins. Returns loaded names.

    Host discovery already includes drop-in folders under ``~/.holix/extensions``.
    Telegram-only entry points are loaded only if the same name was not already
    registered (avoids double-register of packages that declare both groups).
    """
    _load_from_host_extensions(api)
    _load_from_telegram_entrypoints(api)
    set_active_telegram_plugin_api(api)
    # Deduplicate load list (order preserved)
    seen: set[str] = set()
    unique: list[str] = []
    for name in api._extensions_loaded:
        if name in seen:
            continue
        seen.add(name)
        unique.append(name)
    api._extensions_loaded = unique
    if api._extensions_loaded:
        logger.info(
            "Telegram plugins for profile %s: %s",
            api.bot_profile,
            ", ".join(api._extensions_loaded),
        )
    return list(api._extensions_loaded)


def apply_telegram_handlers(api: TelegramPluginAPI) -> None:
    """Run handler registrars (requires api.dispatcher and api.bot set)."""
    for reg in api.handler_registrars:
        try:
            reg(api)
        except Exception:
            logger.exception("telegram handler registrar failed")


async def run_message_gates(
    api: TelegramPluginAPI | None,
    *,
    user_id: int,
    chat_id: int,
    text: str,
    message: Any = None,
    session: Any = None,
    host: Any = None,
    is_command: bool = False,
) -> MessageGateResult:
    """Run gates in order. First ``allow=False`` wins."""
    if api is None or not api.message_gates:
        return MessageGateResult(allow=True)
    for gate in api.message_gates:
        try:
            result = gate(
                user_id=user_id,
                chat_id=chat_id,
                text=text,
                message=message,
                session=session,
                host=host,
                is_command=is_command,
                bot_profile=api.bot_profile,
                api=api,
            )
            if hasattr(result, "__await__"):
                result = await result
            if not isinstance(result, MessageGateResult):
                continue
            if not result.allow:
                return result
            if result.stop_gates:
                return result
        except Exception:
            logger.exception("telegram message gate failed")
    return MessageGateResult(allow=True)


def extension_access_allows(api: TelegramPluginAPI | None, user_id: int) -> bool | None:
    """None = no extension opinion; False = deny; True = allow (skip further deny)."""
    if api is None or not api.access_checks:
        return None
    saw_allow = False
    for check in api.access_checks:
        try:
            verdict = check(int(user_id))
            if verdict is False:
                return False
            if verdict is True:
                saw_allow = True
        except Exception:
            logger.exception("telegram access check failed")
    return True if saw_allow else None
