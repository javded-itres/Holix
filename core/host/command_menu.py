"""Host command menu specs — shared by Telegram, MAX, Studio."""

from __future__ import annotations

from dataclasses import dataclass

from core.i18n import t

HOST_DEFAULT_LOCALE = "en"

_HOST_COMMAND_KEYS: list[tuple[str, str]] = [
    ("help", "tg.cmd.help"),
    ("status", "tg.cmd.status"),
    ("models", "tg.cmd.models"),
    ("menu", "tg.cmd.menu"),
    ("mode", "tg.cmd.mode"),
    ("profile", "tg.cmd.profile"),
    ("stream", "tg.cmd.stream"),
    ("sessions", "tg.cmd.sessions"),
    ("switch", "tg.cmd.switch"),
    ("clear", "tg.cmd.clear"),
    ("stop", "tg.cmd.stop"),
    ("mcp", "tg.cmd.mcp"),
    ("new", "tg.cmd.new"),
    ("memory", "tg.cmd.memory"),
    ("skills", "tg.cmd.skills"),
    ("subagents", "tg.cmd.subagents"),
    ("tools", "tg.cmd.tools"),
    ("last", "tg.cmd.last"),
    ("metrics", "tg.cmd.metrics"),
    ("compress", "tg.cmd.compress"),
    ("forget", "tg.cmd.forget"),
    ("init", "tg.cmd.init"),
    ("cron", "tg.cmd.cron"),
    ("message", "tg.cmd.message"),
    ("lang", "tg.cmd.lang"),
    ("yes", "tg.cmd.yes"),
    ("no", "tg.cmd.no"),
]


@dataclass(frozen=True, slots=True)
class HostCommandSpec:
    command: str
    description: str
    slash: str

    @classmethod
    def from_pair(cls, command: str, description: str) -> HostCommandSpec:
        return cls(command=command, description=description, slash=f"/{command}")


def host_menu_commands(locale: str | None = None) -> list[tuple[str, str]]:
    loc = locale or HOST_DEFAULT_LOCALE
    return [(cmd, t(key, loc)) for cmd, key in _HOST_COMMAND_KEYS]


def command_specs(locale: str | None = None) -> list[HostCommandSpec]:
    return [
        HostCommandSpec.from_pair(cmd, desc)
        for cmd, desc in host_menu_commands(locale)
    ]