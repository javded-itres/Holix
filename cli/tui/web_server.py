"""Holix web TUI server with token auth (subclass of textual-serve Server)."""

from __future__ import annotations

from typing import Any

import aiohttp_jinja2
from aiohttp import web

from cli.tui.web_security import append_query_token, token_from_request


def _textual_serve() -> tuple[type, Any]:
    try:
        from textual_serve.server import Server, to_int
    except ImportError as e:
        raise RuntimeError(
            "Web TUI requires textual-serve. Install with: pip install 'Holix[tui-web]'"
        ) from e
    return Server, to_int


_Server, to_int = _textual_serve()


class HolixWebTuiServer(_Server):
    """textual-serve Server that requires a shared secret on / and /ws."""

    def __init__(self, *args, web_token: str, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._web_token = web_token

    async def _make_app(self) -> web.Application:
        from cli.tui.web_security import make_auth_middleware

        app = await super()._make_app()
        app.middlewares.insert(0, make_auth_middleware(self._web_token))
        return app

    @aiohttp_jinja2.template("app_index.html")
    async def handle_index(self, request: web.Request) -> dict[str, Any]:
        router = request.app.router
        font_size = to_int(request.query.get("fontsize", "16"), 16)
        token = token_from_request(request) or self._web_token

        def get_url(route: str, **args) -> str:
            path = router[route].url_for(**args)
            return f"{self.public_url}{path}"

        def get_websocket_url(route: str, **args) -> str:
            url = get_url(route, **args)
            if self.public_url.startswith("https"):
                ws = "wss:" + url.split(":", 1)[1]
            else:
                ws = "ws:" + url.split(":", 1)[1]
            return append_query_token(ws, token)

        context: dict[str, Any] = {
            "font_size": font_size,
            "app_websocket_url": get_websocket_url("websocket"),
        }
        context["config"] = {
            "static": {
                "url": get_url("static", filename="/").rstrip("/") + "/",
            },
        }
        context["application"] = {
            "name": self.title,
        }
        return context