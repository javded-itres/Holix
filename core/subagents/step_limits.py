"""Profile policy for sub-agent ReAct step caps.

``subagent_max_steps_enabled`` (default True) keeps type budgets.
When False, children run with ``max_steps=0`` (unlimited, same as the
interactive main agent). When True, ``subagent_max_steps > 0`` overrides
the type default unless the spawn call passed an explicit cap.
"""

from __future__ import annotations

from typing import Any


def subagent_step_limits_enabled(config: Any) -> bool:
    if config is None:
        return True
    raw = getattr(config, "subagent_max_steps_enabled", None)
    if raw is None:
        return True
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in {"0", "false", "no", "off", "n"}:
        return False
    return True


def profile_subagent_max_steps(config: Any) -> int:
    if config is None:
        return 0
    try:
        return max(0, int(getattr(config, "subagent_max_steps", 0) or 0))
    except (TypeError, ValueError):
        return 0


def apply_subagent_step_policy(
    parent_cfg: Any,
    sub_cfg: Any,
    *,
    requested: int | None = None,
) -> int:
    """Mutate ``sub_cfg.max_steps`` from profile policy. Returns the cap (0 = unlimited)."""
    if not subagent_step_limits_enabled(parent_cfg):
        sub_cfg.max_steps = 0
        return 0
    if requested is not None:
        try:
            steps = int(requested)
        except (TypeError, ValueError):
            steps = -1
        if steps >= 0:
            sub_cfg.max_steps = steps
            return steps
    cap = profile_subagent_max_steps(parent_cfg)
    if cap > 0:
        sub_cfg.max_steps = cap
        return cap
    return int(getattr(sub_cfg, "max_steps", 0) or 0)
