"""Gateway management HTTP client helpers."""

from __future__ import annotations

import pytest
from cli.services.gateway_client import (
    GatewayClientError,
    gateway_base_url,
    resolve_management_headers,
)
from cli.services.gateway_state import new_state


def test_gateway_base_url_normalizes_wildcard() -> None:
    state = new_state(
        pid=1,
        host="0.0.0.0",
        port=8000,
        profile="default",
        reload=False,
    )
    assert gateway_base_url(state) == "http://127.0.0.1:8000"


def test_resolve_management_headers_prefers_gateway_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOLIX_GATEWAY_API_KEY", "hx_admin")
    monkeypatch.setenv("HOLIX_PROFILE_KEY", "hp_user")
    headers = resolve_management_headers("default")
    assert headers["Authorization"] == "Bearer hx_admin"


def test_resolve_management_headers_uses_profile_key_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HOLIX_GATEWAY_API_KEY", raising=False)
    monkeypatch.delenv("HOLIX_API_KEY", raising=False)
    monkeypatch.setenv("HOLIX_PROFILE_KEY", "hp_user")
    headers = resolve_management_headers("work")
    assert headers["X-Holix-Profile-Key"] == "hp_user"
    assert headers["X-Holix-Profile"] == "work"


def test_post_profile_reload_requires_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cli.services.gateway_client import post_profile_reload

    monkeypatch.delenv("HOLIX_GATEWAY_API_KEY", raising=False)
    monkeypatch.delenv("HOLIX_API_KEY", raising=False)
    monkeypatch.delenv("HOLIX_PROFILE_KEY", raising=False)

    state = new_state(
        pid=1,
        host="127.0.0.1",
        port=8000,
        profile="default",
        reload=False,
    )
    with pytest.raises(GatewayClientError, match="HOLIX_GATEWAY_API_KEY"):
        post_profile_reload(state, "default")