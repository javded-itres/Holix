"""Mask secrets in profile/global env maps for API responses."""

from __future__ import annotations

_SENSITIVE_PARTS = ("key", "token", "secret", "password", "pepper", "credential")


def _is_sensitive(name: str) -> bool:
    lower = name.lower()
    return any(part in lower for part in _SENSITIVE_PARTS)


def mask_env_map(values: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in values.items():
        if not value:
            out[key] = value
        elif _is_sensitive(key):
            out[key] = "***" if len(value) <= 8 else f"{value[:3]}…{value[-2:]}"
        else:
            out[key] = value
    return out