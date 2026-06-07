"""URL safety policy for browser tools."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


_BLOCKED_SCHEMES = frozenset({"file", "javascript", "data", "blob", "about"})


def validate_fetch_url(url: str) -> str:
    """Validate URL for fetch_url / web_fetch (blocks SSRF to private networks)."""
    return validate_browser_url(url)


def validate_browser_url(url: str, allowed_hosts: frozenset[str] | None = None) -> str:
    """Return normalized URL or raise ValueError with reason."""
    raw = (url or "").strip()
    if not raw:
        raise ValueError("URL is required")

    probe = urlparse(raw)
    if probe.scheme:
        if probe.scheme in _BLOCKED_SCHEMES:
            raise ValueError(f"Scheme '{probe.scheme}' is not allowed")
        if probe.scheme not in ("http", "https"):
            raise ValueError(f"Only http/https URLs are allowed, got '{probe.scheme}'")
        parsed = probe
    else:
        raw = f"https://{raw}"
        parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("URL must include a host")

    _reject_private_host(host)

    if allowed_hosts:
        allowed = {h.lower().strip() for h in allowed_hosts if h.strip()}
        if allowed and not _host_allowed(host, allowed):
            raise ValueError(f"Host '{host}' is not in browser_allowed_hosts")

    return raw


def _host_allowed(host: str, allowed: set[str]) -> bool:
    if host in allowed:
        return True
    for pattern in allowed:
        if pattern.startswith(".") and host.endswith(pattern):
            return True
        if host.endswith(f".{pattern}"):
            return True
    return False


def _reject_private_host(host: str) -> None:
    if host in ("localhost", "localhost.localdomain"):
        raise ValueError("localhost is not allowed for browser tools")
    if host.endswith(".local"):
        raise ValueError(".local hosts are not allowed")

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return

    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
        raise ValueError(f"Private/reserved IP '{host}' is not allowed")


def parse_allowed_hosts_csv(value: str) -> frozenset[str]:
    if not value or not value.strip():
        return frozenset()
    return frozenset(part.strip().lower() for part in value.split(",") if part.strip())