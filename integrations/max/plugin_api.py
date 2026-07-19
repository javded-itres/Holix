"""Plugin surface for third-party MAX extensions (billing, CRM, …).

Core stays free of product logic. Extensions call ``register_max(api)``
(host extension) or register via entry point ``holix.max.extensions``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

MAX_ENTRYPOINT_GROUP = "holix.max.extensions"

MessageGate = Callable[..., Any]
CallbackHandler = Callable[..., Any]
HandlerRegistrar = Callable[["MaxPluginAPI"], None]
AccessCheck = Callable[[int], "bool | None"]


@dataclass(frozen=True, slots=True)
class MaxBotCommand:
    command: str
    description: str

    def normalized(self) -> MaxBotCommand:
        cmd = (self.command or "").strip().lstrip("/").lower()
        desc = (self.description or cmd).strip() or cmd
        return MaxBotCommand(command=cmd, description=desc[:256])


@dataclass(slots=True)
class MessageGateResult:
    allow: bool = True
    reply_text: str | None = None
    reply_markdown: str | None = None
    reply_attachments: list[Any] | None = None
    stop_gates: bool = False


@dataclass
class MaxPluginAPI:
    """Mutable registry filled by extensions during MAX bot construction."""

    bot_profile: str
    settings: Any
    client: Any | None = None  # MaxClient when handling updates
    commands: list[MaxBotCommand] = field(default_factory=list)
    message_gates: list[MessageGate] = field(default_factory=list)
    callback_handlers: list[CallbackHandler] = field(default_factory=list)
    handler_registrars: list[HandlerRegistrar] = field(default_factory=list)
    access_checks: list[AccessCheck] = field(default_factory=list)
    _command_handlers: dict[str, Callable[..., Any]] = field(default_factory=dict)
    _extensions_loaded: list[str] = field(default_factory=list)

    def add_command(self, command: str, description: str) -> None:
        spec = MaxBotCommand(command=command, description=description).normalized()
        if not spec.command:
            return
        self.commands = [c for c in self.commands if c.command != spec.command]
        self.commands.append(spec)

    def add_command_handler(self, command: str, handler: Callable[..., Any]) -> None:
        """Register slash command body (async/sync)."""
        name = (command or "").strip().lstrip("/").lower()
        if name:
            self._command_handlers[name] = handler

    def add_message_gate(self, gate: MessageGate) -> None:
        self.message_gates.append(gate)

    def add_callback_handler(self, handler: CallbackHandler) -> None:
        """``handler(api, *, user_id, chat_id, payload, client, ...)`` → handled bool."""
        self.callback_handlers.append(handler)

    def add_handlers(self, registrar: HandlerRegistrar) -> None:
        self.handler_registrars.append(registrar)

    def add_access_check(self, check: AccessCheck) -> None:
        """Return False to deny, True to allow, None to abstain."""
        self.access_checks.append(check)


def extension_access_allows(api: MaxPluginAPI | None, user_id: int) -> bool | None:
    """None = no extension opinion; False = deny; True = allow."""
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
            logger.exception("max access check failed")
    return True if saw_allow else None


_active_api: MaxPluginAPI | None = None


def get_active_max_plugin_api() -> MaxPluginAPI | None:
    return _active_api


def set_active_max_plugin_api(api: MaxPluginAPI | None) -> None:
    global _active_api
    _active_api = api


def extension_bot_commands() -> list[MaxBotCommand]:
    api = _active_api
    if api is None:
        return []
    return list(api.commands)


def _load_from_host_extensions(api: MaxPluginAPI) -> None:
    try:
        from core.extensions.registry import discover_extensions, startup_extensions

        startup_extensions(profile=api.bot_profile)
        for ext in discover_extensions():
            reg = getattr(ext, "register_max", None)
            if not callable(reg):
                continue
            try:
                reg(api)
                api._extensions_loaded.append(str(getattr(ext, "name", type(ext).__name__)))
            except Exception:
                logger.exception(
                    "max plugin register_max failed for %s",
                    getattr(ext, "name", "?"),
                )
    except Exception:
        logger.exception("failed loading host extensions for max plugins")


def _load_from_max_entrypoints(api: MaxPluginAPI) -> None:
    try:
        from core.extensions.registry import _entry_points_for_group
    except Exception:
        return
    for ep in sorted(_entry_points_for_group(MAX_ENTRYPOINT_GROUP), key=lambda e: e.name):
        try:
            obj = ep.load()
            if isinstance(obj, type):
                plug = obj()
            elif callable(obj):
                plug = obj()
            else:
                plug = obj
            reg = getattr(plug, "register_max", None)
            if not callable(reg):
                logger.warning("max entry point %s has no register_max", ep.name)
                continue
            reg(api)
            name = str(getattr(plug, "name", None) or ep.name)
            if name not in api._extensions_loaded:
                api._extensions_loaded.append(name)
        except Exception:
            logger.exception("failed to load max entry point %s", ep.name)


def load_max_plugins(api: MaxPluginAPI) -> list[str]:
    _load_from_host_extensions(api)
    _load_from_max_entrypoints(api)
    set_active_max_plugin_api(api)
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
            "MAX plugins for profile %s: %s",
            api.bot_profile,
            ", ".join(api._extensions_loaded),
        )
    for reg in api.handler_registrars:
        try:
            reg(api)
        except Exception:
            logger.exception("max handler registrar failed")
    return list(api._extensions_loaded)


async def run_message_gates(
    api: MaxPluginAPI | None,
    *,
    user_id: int,
    chat_id: int,
    text: str,
    is_command: bool = False,
    client: Any = None,
    session: Any = None,
    host: Any = None,
) -> MessageGateResult:
    if api is None or not api.message_gates:
        return MessageGateResult(allow=True)
    for gate in api.message_gates:
        try:
            result = gate(
                user_id=user_id,
                chat_id=chat_id,
                text=text,
                is_command=is_command,
                client=client or api.client,
                session=session,
                host=host,
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
            logger.exception("max message gate failed")
    return MessageGateResult(allow=True)


async def run_callback_handlers(
    api: MaxPluginAPI | None,
    *,
    user_id: int,
    chat_id: int | None,
    payload: str,
    client: Any,
    callback_id: str | None = None,
    reply_user_id: int | None = None,
    reply_chat_id: int | None = None,
) -> bool:
    """Return True if an extension handled the callback."""
    if api is None or not api.callback_handlers:
        return False
    api.client = client
    for handler in api.callback_handlers:
        try:
            result = handler(
                api,
                user_id=user_id,
                chat_id=chat_id,
                payload=payload,
                client=client,
                callback_id=callback_id,
                reply_user_id=reply_user_id,
                reply_chat_id=reply_chat_id,
            )
            if hasattr(result, "__await__"):
                result = await result
            if result:
                return True
        except Exception:
            logger.exception("max callback handler failed")
    return False
