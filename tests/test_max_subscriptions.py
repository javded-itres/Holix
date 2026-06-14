"""MAX webhook subscription client tests."""

from __future__ import annotations

import json

import pytest
from aiohttp import web
from integrations.max.client import MaxClient
from integrations.max.config import MaxSettings
from integrations.max.subscriptions import register_webhook, unregister_webhook, webhook_ready

from tests.test_max_client import _start_mock_server


def test_webhook_ready_requires_url() -> None:
    settings = MaxSettings(
        access_token="tok",
        mode="webhook",
        webhook_url="",
    )
    assert webhook_ready(settings) is False

    settings.webhook_url = "https://example.com/hook"
    assert webhook_ready(settings) is True


@pytest.mark.asyncio
async def test_subscribe_and_delete_webhook() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    async def handler(request: web.Request) -> web.Response:
        body = None
        if request.can_read_body:
            raw = await request.read()
            if raw:
                body = json.loads(raw)
        calls.append((request.method, request.path, body))
        if request.method == "POST" and request.path == "/subscriptions":
            return web.json_response({"success": True})
        if request.method == "DELETE" and request.path == "/subscriptions":
            assert request.rel_url.query.get("url") == "https://ex.com/h"
            return web.json_response({"success": True})
        return web.json_response({}, status=404)

    runner, base = await _start_mock_server(handler)
    try:
        settings = MaxSettings(
            access_token="tok",
            mode="webhook",
            webhook_url="https://ex.com/h",
            webhook_secret="abc12",
        )
        async with MaxClient("tok", base_url=base) as client:
            ok = await register_webhook(settings, client=client)
            assert ok is True
            await unregister_webhook(settings, client=client)

        post = next(c for c in calls if c[0] == "POST")
        assert post[2] == {
            "url": "https://ex.com/h",
            "update_types": ["bot_started", "message_created", "message_callback"],
            "secret": "abc12",
        }
    finally:
        await runner.cleanup()