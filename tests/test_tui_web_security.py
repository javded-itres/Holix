"""Web TUI security policy and token helpers."""

from __future__ import annotations

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request
from cli.tui.web_security import (
    WebTuiSecurityError,
    append_query_token,
    build_web_tui_policy,
    is_loopback_host,
    is_wildcard_bind,
    make_auth_middleware,
    token_from_request,
    token_valid,
)


def test_wildcard_bind_blocked_without_allow_lan() -> None:
    with pytest.raises(WebTuiSecurityError, match="--allow-lan"):
        build_web_tui_policy(host="0.0.0.0", cli_token="secret", allow_lan=False)


def test_wildcard_bind_requires_explicit_token() -> None:
    with pytest.raises(WebTuiSecurityError, match="requires --token"):
        build_web_tui_policy(host="0.0.0.0", allow_lan=True, generate_token=True)


def test_wildcard_bind_with_token() -> None:
    policy = build_web_tui_policy(
        host="0.0.0.0", cli_token="abc", allow_lan=True, generate_token=False
    )
    assert policy.token == "abc"
    assert policy.host == "0.0.0.0"


def test_loopback_auto_generates_token() -> None:
    policy = build_web_tui_policy(host="127.0.0.1", generate_token=True)
    assert policy.token_generated
    assert len(policy.token) >= 16


def test_loopback_respects_explicit_token() -> None:
    policy = build_web_tui_policy(host="127.0.0.1", cli_token="fixed", generate_token=True)
    assert policy.token == "fixed"
    assert not policy.token_generated


def test_production_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    policy = build_web_tui_policy(
        host="127.0.0.1", cli_token="prod", is_production=True, generate_token=True
    )
    assert policy.token == "prod"
    with pytest.raises(WebTuiSecurityError):
        build_web_tui_policy(host="127.0.0.1", is_production=True, generate_token=False)


def test_token_from_query_and_bearer() -> None:
    req = make_mocked_request("GET", "/?token=querytok")
    assert token_from_request(req) == "querytok"
    req2 = make_mocked_request("GET", "/", headers={"Authorization": "Bearer bearertok"})
    assert token_from_request(req2) == "bearertok"


def test_token_valid_compare_digest() -> None:
    req = make_mocked_request("GET", "/ws?token=sekrit")
    assert token_valid(req, "sekrit")
    assert not token_valid(req, "wrong")


def test_append_query_token() -> None:
    assert "token=abc" in append_query_token("ws://127.0.0.1:8787/ws", "abc")


@pytest.mark.asyncio
async def test_auth_middleware_blocks_without_token() -> None:
    app = web.Application(middlewares=[make_auth_middleware("secret")])

    async def ok_handler(request: web.Request) -> web.Response:
        return web.Response(text="ok")

    app.router.add_get("/", ok_handler)
    req = make_mocked_request("GET", "/")
    with pytest.raises(web.HTTPUnauthorized):
        await app.middlewares[0](req, ok_handler)


@pytest.mark.asyncio
async def test_auth_middleware_allows_static() -> None:
    seen = False

    async def static_handler(request: web.Request) -> web.Response:
        nonlocal seen
        seen = True
        return web.Response(text="ok")

    app = web.Application(middlewares=[make_auth_middleware("secret")])
    app.router.add_get("/static/x.js", static_handler)
    req = make_mocked_request("GET", "/static/x.js")
    await app.middlewares[0](req, static_handler)
    assert seen


def test_host_classifiers() -> None:
    assert is_loopback_host("127.0.0.1")
    assert is_loopback_host("localhost")
    assert not is_loopback_host("0.0.0.0")
    assert is_wildcard_bind("0.0.0.0")