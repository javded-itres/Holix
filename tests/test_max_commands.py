"""MAX slash-command menu."""

from __future__ import annotations

import pytest
from aiohttp import web
from integrations.max.client import MaxClient
from integrations.max.commands import max_bot_commands, register_bot_commands, sync_bot_menu
from integrations.telegram.commands import command_specs, telegram_menu_commands


def test_max_menu_matches_telegram_specs() -> None:
    assert len(max_bot_commands("en")) == len(command_specs("en"))
    names = {item["name"] for item in max_bot_commands("en")}
    assert "help" in names
    assert "models" in names
    assert len(max_bot_commands("en")) <= 32


def test_max_menu_uses_command_names_without_slash() -> None:
    for cmd, _desc in telegram_menu_commands("en"):
        payload = next(item for item in max_bot_commands("en") if item["name"] == cmd)
        assert not payload["name"].startswith("/")


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