"""URL hostname helpers for safe host matching."""

from __future__ import annotations

from urllib.parse import urlparse


def host_is(host: str, domain: str) -> bool:
    """True if host equals domain or is a subdomain of domain."""
    host = (host or "").lower().rstrip(".")
    domain = (domain or "").lower()
    if not host or not domain:
        return False
    return host == domain or host.endswith(f".{domain}")


def url_hostname(url: str) -> str:
    """Extract lowercase hostname from a URL or host:port string."""
    raw = url.strip()
    if not raw:
        return ""
    lower = raw.lower()
    if lower.startswith("git@"):
        return lower.split("@", 1)[1].split(":", 1)[0]
    if "://" not in raw:
        raw = f"https://{raw}"
    return (urlparse(raw).hostname or "").lower()


def url_port(url: str) -> int | None:
    """Extract port from a URL or host:port string."""
    raw = url.strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = f"https://{raw}"
    return urlparse(raw).port


def spec_looks_like_github(spec: str) -> bool:
    """Detect GitHub git/HTTP sources without substring false positives."""
    s = spec.strip()
    if not s:
        return False
    lower = s.lower()
    if lower.startswith("git@github.com:"):
        return True
    host = url_hostname(s)
    return bool(host) and host_is(host, "github.com")