"""MAX HTTP client tests."""

from __future__ import annotations

import pytest
from aiohttp import web
from integrations.max.client import MaxApiError, MaxClient
from integrations.max.models import (
    conversation_id_for_max,
    message_text,
    reply_kwargs_for_session,
    reply_target_from_message,
    sender_user_id,
    update_type,
    user_id_from_update,
)


async def _start_mock_server(handler):
    app = web.Application()
    app.router.add_route("*", "/{path:.*}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    return runner, base


@pytest.mark.asyncio
async def test_send_message_prefers_chat_id_over_user_id() -> None:
    seen: list[str] = []

    async def handler(request: web.Request) -> web.Response:
        seen.append(request.rel_url.query_string)
        return web.json_response({"message": {"body": {"mid": "m1"}}})

    runner, base = await _start_mock_server(handler)
    try:
        async with MaxClient("tok", base_url=base) as client:
            await client.send_message("hi", user_id=3356055, chat_id=201888907)
        assert "chat_id=201888907" in seen[0]
        assert "user_id" not in seen[0]
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_get_me_and_send_message() -> None:
    calls: list[tuple[str, str]] = []

    async def handler(request: web.Request) -> web.Response:
        calls.append((request.method, request.path))
        auth = request.headers.get("Authorization", "")
        assert auth == "test-token"
        if request.path == "/me":
            return web.json_response({"user_id": 1, "username": "helix_bot", "is_bot": True})
        if request.path == "/messages":
            assert request.rel_url.query.get("user_id") == "42"
            body = await request.json()
            assert body["text"] == "pong"
            return web.json_response({"message": {"body": {"text": "pong"}}})
        return web.json_response({"error": "not found"}, status=404)

    runner, base = await _start_mock_server(handler)
    try:
        async with MaxClient("test-token", base_url=base) as client:
            me = await client.get_me()
            assert me["username"] == "helix_bot"
            await client.send_message("pong", user_id=42)
        assert ("GET", "/me") in calls
        assert ("POST", "/messages") in calls
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_get_updates_passes_marker() -> None:
    seen: list[str] = []

    async def handler(request: web.Request) -> web.Response:
        seen.append(request.rel_url.query_string)
        return web.json_response({"updates": [], "marker": 7})

    runner, base = await _start_mock_server(handler)
    try:
        async with MaxClient("tok", base_url=base) as client:
            payload = await client.get_updates(marker=5, types=["message_created"])
            assert payload["marker"] == 7
        assert "marker=5" in seen[0]
        assert "types=message_created" in seen[0]
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_api_retries_on_429() -> None:
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            return web.json_response({"message": "rate limit"}, status=429)
        return web.json_response({"user_id": 1, "username": "bot", "is_bot": True})

    runner, base = await _start_mock_server(handler)
    try:
        async with MaxClient("tok", base_url=base) as client:
            me = await client.get_me()
            assert me["username"] == "bot"
        assert calls == 3
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_set_my_commands_patches_me() -> None:
    seen_body: dict | None = None

    async def handler(request: web.Request) -> web.Response:
        nonlocal seen_body
        if request.path == "/me" and request.method == "PATCH":
            seen_body = await request.json()
            return web.json_response(
                {
                    "user_id": 1,
                    "username": "helix_bot",
                    "is_bot": True,
                    "commands": seen_body.get("commands", []),
                }
            )
        return web.json_response({"error": "not found"}, status=404)

    runner, base = await _start_mock_server(handler)
    try:
        async with MaxClient("tok", base_url=base) as client:
            result = await client.set_my_commands(
                [{"name": "help", "description": "Справка"}]
            )
            assert result["username"] == "helix_bot"
        assert seen_body == {"commands": [{"name": "help", "description": "Справка"}]}
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_api_error_on_401() -> None:
    async def handler(request: web.Request) -> web.Response:
        return web.json_response({"message": "unauthorized"}, status=401)

    runner, base = await _start_mock_server(handler)
    try:
        async with MaxClient("bad", base_url=base) as client:
            with pytest.raises(MaxApiError) as exc:
                await client.get_me()
            assert exc.value.status == 401
    finally:
        await runner.cleanup()


def test_update_helpers() -> None:
    update = {
        "update_type": "message_created",
        "message": {
            "sender": {"user_id": 99},
            "body": {"text": " ping "},
            "recipient": {"user_id": 99},
        },
    }
    assert update_type(update) == "message_created"
    assert user_id_from_update(update) == 99
    assert message_text(update["message"]) == "ping"
    assert sender_user_id(update["message"]) == 99


def test_conversation_id_dialog_uses_user_id_not_chat_id() -> None:
    assert (
        conversation_id_for_max("default", 3356055, chat_id=201888907, chat_type="dialog")
        == "max_default_3356055"
    )
    assert (
        conversation_id_for_max("default", 3356055, chat_id=201888907, chat_type="group")
        == "max_default_chat_201888907"
    )


def test_reply_target_dialog_uses_sender_not_bot_recipient() -> None:
    message = {
        "sender": {"user_id": 3356055, "is_bot": False},
        "recipient": {
            "chat_id": 201888907,
            "chat_type": "dialog",
            "user_id": 205234460,
        },
        "body": {"text": "hello"},
    }
    assert reply_target_from_message(message) == (None, 201888907)


def test_reply_kwargs_dialog_prefers_chat_id() -> None:
    assert reply_kwargs_for_session(
        user_id=3356055,
        reply_user_id=3356055,
        reply_chat_id=201888907,
        chat_type="dialog",
    ) == {"chat_id": 201888907}


def test_reply_kwargs_group_prefers_chat_id() -> None:
    assert reply_kwargs_for_session(
        user_id=3356055,
        reply_user_id=None,
        reply_chat_id=201888907,
        chat_type="group",
    ) == {"chat_id": 201888907}