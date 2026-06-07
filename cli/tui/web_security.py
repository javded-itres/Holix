"""Security policy for `helix tui --web` (textual-serve)."""

from __future__ import annotations

import hmac
import os
import secrets
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

from aiohttp import web

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
WILDCARD_BIND_HOSTS = frozenset({"0.0.0.0", "::", "::0", "*"})


@dataclass(frozen=True)
class WebTuiSecurityPolicy:
    host: str
    token: str
    token_generated: bool
    allow_lan: bool
    is_production: bool


class WebTuiSecurityError(RuntimeError):
    """Invalid bind address or missing credentials for web TUI."""


def is_loopback_host(host: str) -> bool:
    h = (host or "").strip().lower()
    if h in LOOPBACK_HOSTS:
        return True
    if h.startswith("127."):
        return True
    return False


def is_wildcard_bind(host: str) -> bool:
    return (host or "").strip() in WILDCARD_BIND_HOSTS


def token_from_request(request: web.Request) -> str | None:
    """Extract bearer or query token from an HTTP/WebSocket request."""
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    q = request.query.get("token")
    return (q.strip() if isinstance(q, str) and q.strip() else None)


def token_valid(request: web.Request, expected: str) -> bool:
    got = token_from_request(request)
    if not got or not expected:
        return False
    return hmac.compare_digest(got, expected)


def append_query_token(url: str, token: str) -> str:
    parts = urlsplit(url)
    query = urlencode({"token": token})
    sep = "&" if parts.query else ""
    new_query = f"{parts.query}{sep}{query}" if parts.query else query
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


def generate_web_token() -> str:
    return secrets.token_urlsafe(32)


def build_web_tui_policy(
    *,
    host: str,
    cli_token: Optional[str] = None,
    allow_lan: bool = False,
    generate_token: bool = True,
    is_production: bool = False,
) -> WebTuiSecurityPolicy:
    """Validate bind + credentials; auto-generate token only on loopback dev."""
    bind = (host or "127.0.0.1").strip()
    if is_wildcard_bind(bind) and not allow_lan:
        raise WebTuiSecurityError(
            f"Refusing to bind web TUI to {bind!r} without --allow-lan. "
            "LAN exposure grants full agent access (shell, files, MCP). "
            "Use: helix tui --web --allow-lan --host 0.0.0.0 --token <secret>"
        )

    loopback = is_loopback_host(bind)
    explicit = (cli_token or "").strip() or os.getenv("HELIX_TUI_WEB_TOKEN", "").strip()

    if explicit:
        token, generated = explicit, False
    elif not loopback or is_production:
        raise WebTuiSecurityError(
            "Web TUI on LAN or in production requires --token <secret> "
            "or HELIX_TUI_WEB_TOKEN in the environment."
        )
    elif generate_token:
        token, generated = generate_web_token(), True
    else:
        raise WebTuiSecurityError(
            "Pass --token <secret>, set HELIX_TUI_WEB_TOKEN, or allow "
            "--generate-token (default on 127.0.0.1)."
        )

    return WebTuiSecurityPolicy(
        host=bind,
        token=token,
        token_generated=generated,
        allow_lan=allow_lan,
        is_production=is_production,
    )


def public_url_with_token(base_url: str, token: str) -> str:
    return append_query_token(base_url.rstrip("/") + "/", token)


def make_auth_middleware(expected_token: str):
    """aiohttp middleware: require token on non-static routes."""

    @web.middleware
    async def auth_middleware(request: web.Request, handler):
        path = request.path or ""
        if path.startswith("/static"):
            return await handler(request)
        if token_valid(request, expected_token):
            return await handler(request)
        raise web.HTTPUnauthorized(
            text=(
                "Helix Web TUI: missing or invalid token. "
                "Open the URL printed at startup (?token=...) or send "
                "Authorization: Bearer <token>."
            ),
            content_type="text/plain",
        )

    return auth_middleware