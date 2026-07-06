"""Security policy for Holix Studio (local serve and gateway mount)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from cli.tui.web_security import (
    WebTuiSecurityError,
    WebTuiSecurityPolicy,
    append_query_token,
    build_web_tui_policy,
    generate_web_token,
    is_loopback_host,
    token_valid,
)

__all__ = [
    "StudioSecurityError",
    "StudioSecurityPolicy",
    "append_query_token",
    "build_studio_policy",
    "generate_studio_token",
    "is_loopback_host",
    "studio_token_valid",
    "token_valid",
]


class StudioSecurityError(WebTuiSecurityError):
    """Invalid bind address or missing credentials for Studio."""


@dataclass(frozen=True)
class StudioSecurityPolicy(WebTuiSecurityPolicy):
    """Studio auth/bind policy (alias of web TUI policy semantics)."""


def generate_studio_token() -> str:
    return generate_web_token()


def build_studio_policy(
    *,
    host: str,
    cli_token: str | None = None,
    allow_lan: bool = False,
    generate_token: bool = True,
    is_production: bool = False,
) -> StudioSecurityPolicy:
    """Validate bind + credentials for ``holix studio serve``."""
    policy = build_web_tui_policy(
        host=host,
        cli_token=cli_token or os.getenv("HOLIX_STUDIO_TOKEN", "").strip() or None,
        allow_lan=allow_lan,
        generate_token=generate_token,
        is_production=is_production,
    )
    return StudioSecurityPolicy(
        host=policy.host,
        token=policy.token,
        token_generated=policy.token_generated,
        allow_lan=policy.allow_lan,
        is_production=policy.is_production,
    )


def studio_token_valid(authorization: str | None, query_token: str | None, expected: str) -> bool:
    """Check Bearer header or ?token= against expected secret."""
    if not expected:
        return False
    auth = (authorization or "").strip()
    if auth.lower().startswith("bearer "):
        got = auth[7:].strip()
    else:
        got = (query_token or "").strip()
    if not got:
        return False
    import hmac

    return hmac.compare_digest(got, expected)