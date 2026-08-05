"""Read/write profile ``enable_self_refinement`` (Reflexion) for messenger UIs.

Default is **off** when unset — multi-user bots should not run post-draft critique
unless the user explicitly enables it in the menu.
"""

from __future__ import annotations

from typing import Any


def is_reflexion_enabled_for_host(host: Any) -> bool:
    """Current effective flag: live agent config, else profile, else default off."""
    from core.config_utils import is_self_refinement_enabled

    agent = getattr(host, "agent", None)
    if agent is not None:
        return is_self_refinement_enabled(getattr(agent, "config", None), default=False)

    profile = str(getattr(host, "profile", None) or "").strip()
    if not profile:
        return False
    try:
        from cli.core import get_profile_manager

        cfg = get_profile_manager().load_profile(profile)
        return is_self_refinement_enabled(cfg, default=False)
    except Exception:
        return False


def set_reflexion_enabled_for_host(host: Any, enabled: bool) -> bool:
    """Persist ``enable_self_refinement`` on the host profile and update a live agent.

    Returns the effective flag after apply.
    """
    enabled = bool(enabled)
    profile = str(getattr(host, "profile", None) or "").strip()
    if not profile:
        raise ValueError("No active profile to update enable_self_refinement")

    from cli.core import get_profile_manager

    manager = get_profile_manager()
    cfg = manager.load_profile(profile)
    cfg.enable_self_refinement = enabled
    manager.save_profile(profile, cfg)

    agent = getattr(host, "agent", None)
    if agent is not None and hasattr(agent, "config"):
        agent.config = agent.config.with_overrides(enable_self_refinement=enabled)

    return enabled
