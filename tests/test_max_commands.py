"""MAX slash-command menu."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from aiohttp import web
from integrations.max.client import MaxClient
from integrations.max.commands import (
    MAX_MENU_HOST_COMMANDS,
    max_bot_commands,
    register_bot_commands,
    sync_bot_menu,
)
from integrations.telegram.commands import command_specs


def test_max_menu_is_short_user_set() -> None:
    names = [item["name"] for item in max_bot_commands("en")]
    assert names == list(MAX_MENU_HOST_COMMANDS)
    assert len(names) < len(command_specs("en"))
    assert "help" in names
    assert "menu" in names
    assert "yes" not in names
    assert "message" not in names
    assert len(names) <= 32


def test_max_menu_uses_command_names_without_slash() -> None:
    for item in max_bot_commands("en"):
        assert not item["name"].startswith("/")


def test_max_menu_includes_tariffs_and_invite_without_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _ext() -> list[SimpleNamespace]:
        return [
            SimpleNamespace(command="billing", description="Тарифы и цены"),
            SimpleNamespace(command="tariffs", description="Тарифы и цены"),
            SimpleNamespace(command="referral", description="Пригласи друга"),
            SimpleNamespace(command="invite", description="Пригласи друга"),
            SimpleNamespace(command="ref", description="Пригласи друга"),
            SimpleNamespace(command="pay", description="Оформить подписку"),
            SimpleNamespace(command="subscribers", description="Список подписчиков (admin)"),
            SimpleNamespace(command="start", description="Старт"),
        ]

    monkeypatch.setattr(
        "integrations.max.plugin_api.extension_bot_commands",
        _ext,
    )
    names = [item["name"] for item in max_bot_commands("en")]
    assert names.count("tariffs") == 1
    assert names.count("invite") == 1
    assert "tariffs" in names
    assert "invite" in names
    assert "pay" in names
    assert "start" in names
    assert "billing" not in names
    assert "referral" not in names
    assert "ref" not in names
    assert "subscribers" not in names
    assert len(names) <= 32


@pytest.mark.asyncio
async def test_register_bot_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, str]] = []

    async def handler(request: web.Request) -> web.Response:
        if request.path == "/me" and request.method == "PATCH":
            body = await request.json()
            seen.extend(body.get("commands", []))
            return web.json_response({"user_id": 1, "is_bot": True, "commands": seen})
        return web.json_response({"error": "not found"}, status=404)

    app = web.Application()
    app.router.add_route("*", "/{path:.*}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    base = f"http://127.0.0.1:{port}"

    try:
        async with MaxClient("tok", base_url=base) as client:
            names = await register_bot_commands(client, locale="en")
        assert "help" in names
        assert any(item["name"] == "help" for item in seen)
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_sync_bot_menu_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.max.config import MaxSettings

    monkeypatch.setattr(
        "integrations.max.config.load_max_settings",
        lambda profile="default": MaxSettings(access_token="", profile=profile),
    )

    with pytest.raises(RuntimeError, match="MAX_ACCESS_TOKEN"):
        await sync_bot_menu("default")
