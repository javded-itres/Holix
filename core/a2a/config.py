"""A2A configuration from Holix profile / global / env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from core.a2a.mikrollm import MikroLLMLink, parse_mikrollm


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
    # Per-agent peers. A slot present here does not inherit ``remote_agents``.
    agent_remotes: dict[str, list[RemoteA2AAgent]] = field(default_factory=dict)
    agent_enabled: dict[str, bool] = field(default_factory=dict)
    request_timeout_s: float = 300.0
    # Group membership on a MikroLLM gateway. None when this profile is not a member.
    mikrollm: MikroLLMLink | None = None

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


def _parse_agent_map(
    raw: Any,
) -> tuple[dict[str, list[RemoteA2AAgent]], dict[str, bool]]:
    """Per-slot peers. Any ``agents.<slot>`` object is an explicit list."""
    remotes: dict[str, list[RemoteA2AAgent]] = {}
    enabled: dict[str, bool] = {}
    if not isinstance(raw, dict):
        return remotes, enabled
    for key, value in raw.items():
        slot = str(key or "").strip()
        if not slot or not isinstance(value, dict):
            continue
        enabled[slot] = _as_bool(value.get("enabled"), default=True)
        remotes[slot] = _parse_remotes(value.get("remote_agents") or value.get("remotes"))
    return remotes, enabled


def remotes_for_slot(config: A2AConfig, agent_slot: str) -> tuple[bool, list[RemoteA2AAgent]]:
    """Peers this agent may call.

    A slot saved under ``a2a.agents`` uses only its own list. Other agents
    keep the profile-wide ``remote_agents`` list. The profile switch still
    turns the client off for every slot.
    """
    slot = (agent_slot or "main").strip() or "main"
    if slot not in config.agent_remotes:
        return config.client_enabled, list(config.remote_agents)
    own = bool(config.agent_enabled.get(slot, True))
    return bool(config.client_enabled and own), list(config.agent_remotes.get(slot) or [])


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

    agent_remotes, agent_enabled = _parse_agent_map(data.get("agents"))

    return A2AConfig(
        enabled=enabled,
        public_url=public_url,
        card_name=(str(data["name"]).strip() if data.get("name") else None),
        card_description=(str(data["description"]).strip() if data.get("description") else None),
        card_version=str(data.get("version") or "1.0.0"),
        remote_agents=_parse_remotes(data.get("remote_agents") or data.get("remotes")),
        agent_remotes=agent_remotes,
        agent_enabled=agent_enabled,
        request_timeout_s=max(5.0, min(timeout_f, 3600.0)),
        mikrollm=parse_mikrollm(data.get("mikrollm")),
    )
