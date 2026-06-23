"""Resolve max_tokens for agent LLM calls (reasoning models need a budget)."""

from __future__ import annotations

DEFAULT_AGENT_MAX_TOKENS = 8192


def resolve_agent_max_tokens(
    *,
    profile_max_tokens: int | None = None,
    default_max_tokens: int | None = None,
) -> int:
    """Pick generation budget: profile override → global default → built-in default."""
    if profile_max_tokens is not None and int(profile_max_tokens) > 0:
        return int(profile_max_tokens)
    if default_max_tokens is not None and int(default_max_tokens) > 0:
        return int(default_max_tokens)
    return DEFAULT_AGENT_MAX_TOKENS


def profile_agent_max_tokens(model_manager: object | None, agent_slot: str) -> int | None:
    """Read ``max_tokens`` from the active agent model config, if any."""
    if model_manager is None:
        return None
    getter = getattr(model_manager, "get_agent_model_config", None)
    if not callable(getter):
        return None
    cfg = getter(agent_slot)
    if cfg is None:
        return None
    raw = getattr(cfg, "max_tokens", None)
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None