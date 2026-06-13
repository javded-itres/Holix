"""HTTP client helpers for local gateway management."""

from __future__ import annotations

import os
from typing import Any

import httpx

from cli.services.gateway_state import GatewayState


class GatewayClientError(Exception):
    """Failed to call the local gateway management API."""


def gateway_base_url(state: GatewayState) -> str:
    bind = "127.0.0.1" if state.host in ("0.0.0.0", "::") else state.host
    return f"http://{bind}:{state.port}"


def resolve_management_headers(profile: str) -> dict[str, str]:
    """Build auth headers for ``/api/holix/*`` from profile env."""
    headers: dict[str, str] = {}
    api_key = (
        os.getenv("HOLIX_GATEWAY_API_KEY", "").strip()
        or os.getenv("HOLIX_API_KEY", "").strip()
        or os.getenv("HOLIX_ADMIN_API_KEY", "").strip()
    )
    profile_key = os.getenv("HOLIX_PROFILE_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    elif profile_key:
        headers["X-Holix-Profile-Key"] = profile_key
        headers["X-Holix-Profile"] = profile
    return headers


def post_profile_reload(
    state: GatewayState,
    profile: str,
    *,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Reload agent + companions for ``profile`` via management API."""
    headers = resolve_management_headers(profile)
    if not headers:
        raise GatewayClientError(
            "Set HOLIX_GATEWAY_API_KEY (admin hx_ key) or HOLIX_PROFILE_KEY "
            f"in profiles/{profile}/.env to reload a running gateway"
        )

    url = f"{gateway_base_url(state)}/api/holix/profiles/{profile}/reload"
    try:
        response = httpx.post(url, headers=headers, timeout=timeout)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text.strip() or str(exc)
        raise GatewayClientError(
            f"Gateway reload failed (HTTP {exc.response.status_code}): {detail}"
        ) from exc
    except httpx.RequestError as exc:
        raise GatewayClientError(f"Gateway reload request failed: {exc}") from exc

    body = response.json()
    if not isinstance(body, dict):
        raise GatewayClientError("Gateway reload returned unexpected response")
    return body