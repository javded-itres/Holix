"""Read/write profile ``max_steps`` (base ReAct/graph budget) for messenger UIs."""

from __future__ import annotations

from typing import Any

DEFAULT_MAX_STEPS = 90
MIN_MAX_STEPS = 10
MAX_MAX_STEPS = 500
MAX_STEPS_PRESETS: tuple[int, ...] = (30, 60, 90, 120, 180, 300)


def normalize_max_steps(value: Any, *, default: int = DEFAULT_MAX_STEPS) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return int(default)
    return max(MIN_MAX_STEPS, min(MAX_MAX_STEPS, n))


def parse_max_steps(value: Any) -> int:
    """Parse user input; raise ValueError if empty, not an int, or out of range."""
    raw = str(value if value is not None else "").strip()
    if not raw:
        raise ValueError("empty")
    try:
        n = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("not an integer") from exc
    if n < MIN_MAX_STEPS or n > MAX_MAX_STEPS:
        raise ValueError("out of range")
    return n


def get_max_steps_for_host(host: Any) -> int:
    """Current effective budget: live agent config, else profile, else default 90."""
    agent = getattr(host, "agent", None)
    if agent is not None:
        return normalize_max_steps(getattr(getattr(agent, "config", None), "max_steps", None))

    profile = str(getattr(host, "profile", None) or "").strip()
    if not profile:
        return DEFAULT_MAX_STEPS
    try:
        from cli.core import get_profile_manager

        cfg = get_profile_manager().load_profile(profile)
        raw = getattr(cfg, "max_steps", None)
        if raw is not None:
            return normalize_max_steps(raw)
        from config import Settings

        return normalize_max_steps(getattr(Settings(_env_file=None), "max_steps", None))
    except Exception:
        return DEFAULT_MAX_STEPS


def set_max_steps_for_host(host: Any, steps: int) -> int:
    """Persist ``max_steps`` on the host profile and update a live agent.

    Returns the clamped value after apply.
    """
    n = normalize_max_steps(steps)
    profile = str(getattr(host, "profile", None) or "").strip()
    if not profile:
        raise ValueError("No active profile to update max_steps")

    from cli.core import get_profile_manager

    manager = get_profile_manager()
    cfg = manager.load_profile(profile)
    cfg.max_steps = n
    manager.save_profile(profile, cfg)

    agent = getattr(host, "agent", None)
    if agent is not None and hasattr(agent, "config"):
        agent.config = agent.config.with_overrides(max_steps=n)

    return n
