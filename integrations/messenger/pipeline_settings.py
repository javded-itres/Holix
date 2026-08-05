"""Read/write profile ``agent_pipeline`` (classic ≈1.0.2 | modern) for messenger UIs."""

from __future__ import annotations

from typing import Any

from core.agent_pipeline import (
    PIPELINE_CLASSIC,
    PIPELINE_MODERN,
    normalize_pipeline,
    pipeline_from_config,
)


def is_pipeline_for_host(host: Any) -> str:
    """Current pipeline mode for this host."""
    agent = getattr(host, "agent", None)
    if agent is not None:
        return pipeline_from_config(getattr(agent, "config", None))

    profile = str(getattr(host, "profile", None) or "").strip()
    if not profile:
        return PIPELINE_CLASSIC
    try:
        from cli.core import get_profile_manager

        cfg = get_profile_manager().load_profile(profile)
        raw = getattr(cfg, "agent_pipeline", None)
        if raw:
            return normalize_pipeline(str(raw))
        # Fall back to env/settings via HolixRuntimeConfig defaults
        from config import Settings

        return normalize_pipeline(getattr(Settings(_env_file=None), "agent_pipeline", None))
    except Exception:
        return PIPELINE_CLASSIC


def set_pipeline_for_host(host: Any, pipeline: str) -> str:
    """Persist ``agent_pipeline`` on the profile and update a live agent.

    Returns normalized pipeline after apply.
    """
    mode = normalize_pipeline(pipeline)
    profile = str(getattr(host, "profile", None) or "").strip()
    if not profile:
        raise ValueError("No active profile to update agent_pipeline")

    from cli.core import get_profile_manager

    manager = get_profile_manager()
    cfg = manager.load_profile(profile)
    cfg.agent_pipeline = mode
    # Classic defaults: keep Reflexion/meta off unless user later enables them.
    if mode == PIPELINE_CLASSIC:
        if getattr(cfg, "enable_self_refinement", None) is None:
            cfg.enable_self_refinement = False
        if getattr(cfg, "enable_meta_agent", None) is None:
            cfg.enable_meta_agent = False
    manager.save_profile(profile, cfg)

    agent = getattr(host, "agent", None)
    if agent is not None and hasattr(agent, "config"):
        overrides: dict[str, Any] = {"agent_pipeline": mode}
        if mode == PIPELINE_CLASSIC:
            # Do not force-disable if user explicitly turned Reflexion on in profile.
            pass
        agent.config = agent.config.with_overrides(**overrides)

    return mode


def pipeline_label(mode: str, *, locale: str = "en") -> str:
    m = normalize_pipeline(mode)
    if m == PIPELINE_MODERN:
        return "modern" if not locale.startswith("ru") else "modern"
    return "classic (1.0.2)" if not locale.startswith("ru") else "classic (1.0.2)"
