"""A2A configuration from Holix profile / global / env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RemoteA2AAgent:
    name: str
    url: str
    description: str = ""
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class A2AConfig:
    """Whether Holix exposes/consumes A2A for a profile."""

    enabled: bool = True
    # Server
    public_url: str | None = None  # e.g. https://agent.example.com/a2a
    card_name: str | None = None
    card_description: str | None = None
    card_version: str = "1.0.0"
    # Client
    remote_agents: list[RemoteA2AAgent] = field(default_factory=list)
    request_timeout_s: float = 300.0

    @property
    def server_enabled(self) -> bool:
        return self.enabled

    @property
    def client_enabled(self) -> bool:
        return self.enabled


def _as_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_remotes(raw: Any) -> list[RemoteA2AAgent]:
    if not isinstance(raw, list):
        return []
    out: list[RemoteA2AAgent] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        url = str(item.get("url") or item.get("base_url") or "").strip().rstrip("/")
        if not name or not url:
            continue
        headers: dict[str, str] = {}
        hdr = item.get("headers")
        if isinstance(hdr, dict):
            headers = {str(k): str(v) for k, v in hdr.items() if k and v is not None}
        out.append(
            RemoteA2AAgent(
                name=name,
                url=url,
                description=str(item.get("description") or ""),
                headers=headers,
            )
        )
    return out


def load_a2a_config(profile: str | None = None, *, raw: dict[str, Any] | None = None) -> A2AConfig:
    """Load A2A config: explicit raw → profile yaml → env defaults."""
    data: dict[str, Any] = {}
    if raw and isinstance(raw, dict):
        data = dict(raw.get("a2a") if isinstance(raw.get("a2a"), dict) else raw)
    elif profile:
        try:
            from core.profile import ProfileManager

            cfg = ProfileManager().load_profile(profile)
            a2a = getattr(cfg, "a2a", None)
            if isinstance(a2a, dict):
                data = dict(a2a)
            else:
                dumped = cfg.model_dump() if hasattr(cfg, "model_dump") else {}
                if isinstance(dumped.get("a2a"), dict):
                    data = dict(dumped["a2a"])
            # Extension-style settings can override
            ext = getattr(cfg, "extension_settings", None) or {}
            if isinstance(ext, dict) and isinstance(ext.get("a2a"), dict):
                data = {**data, **ext["a2a"]}
        except Exception:
            pass

    env_enabled = os.getenv("HOLIX_A2A_ENABLED")
    enabled = _as_bool(data.get("enabled"), default=True)
    if env_enabled is not None and str(env_enabled).strip() != "":
        enabled = _as_bool(env_enabled, default=enabled)

    public_url = data.get("public_url") or data.get("url") or os.getenv("HOLIX_A2A_PUBLIC_URL")
    if public_url:
        public_url = str(public_url).strip().rstrip("/") or None

    timeout = data.get("request_timeout_s") or os.getenv("HOLIX_A2A_TIMEOUT_S") or 300
    try:
        timeout_f = float(timeout)
    except (TypeError, ValueError):
        timeout_f = 300.0

    return A2AConfig(
        enabled=enabled,
        public_url=public_url,
        card_name=(str(data["name"]).strip() if data.get("name") else None),
        card_description=(
            str(data["description"]).strip() if data.get("description") else None
        ),
        card_version=str(data.get("version") or "1.0.0"),
        remote_agents=_parse_remotes(data.get("remote_agents") or data.get("remotes")),
        request_timeout_s=max(5.0, min(timeout_f, 3600.0)),
    )
