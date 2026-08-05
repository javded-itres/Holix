"""Agent response pipeline modes: classic (≈1.0.2) vs modern (anti-monologue).

``classic`` (default)
    Behaviour closer to Holix **1.0.2** free-chat path: meta/Reflexion off by
    default, no forced ``tool_choice=required`` on every action turn, no
    truncation-notice-as-final, no status-monologue honesty wall.
    Safety nets kept: think-strip, pathological loop collapse, deferred
    FinalResponse, false-completion honesty for unproven «готово».

``modern``
    Current anti-spam path: tools-first on action requests, monologue nudges,
    truncation notice + honesty retry, optional Reflexion/meta via settings.

Switch via env ``HOLIX_AGENT_PIPELINE``, profile field ``agent_pipeline``,
or messenger menu (Telegram / MAX).
"""

from __future__ import annotations

from typing import Any

PIPELINE_CLASSIC = "classic"
PIPELINE_MODERN = "modern"
PIPELINE_DEFAULT = PIPELINE_CLASSIC

_ALIASES: dict[str, str] = {
    "classic": PIPELINE_CLASSIC,
    "1.0.2": PIPELINE_CLASSIC,
    "v1.0.2": PIPELINE_CLASSIC,
    "legacy": PIPELINE_CLASSIC,
    "old": PIPELINE_CLASSIC,
    "modern": PIPELINE_MODERN,
    "current": PIPELINE_MODERN,
    "anti_monologue": PIPELINE_MODERN,
    "antimonologue": PIPELINE_MODERN,
    "new": PIPELINE_MODERN,
}


def normalize_pipeline(value: str | None) -> str:
    raw = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not raw:
        return PIPELINE_DEFAULT
    return _ALIASES.get(raw, PIPELINE_DEFAULT if raw not in (PIPELINE_CLASSIC, PIPELINE_MODERN) else raw)


def is_classic_pipeline(value: str | None) -> bool:
    return normalize_pipeline(value) == PIPELINE_CLASSIC


def is_modern_pipeline(value: str | None) -> bool:
    return normalize_pipeline(value) == PIPELINE_MODERN


def pipeline_from_config(cfg: Any | None) -> str:
    if cfg is None:
        return PIPELINE_DEFAULT
    return normalize_pipeline(getattr(cfg, "agent_pipeline", None))


def pipeline_from_state(state: dict[str, Any] | None, cfg: Any | None = None) -> str:
    if isinstance(state, dict):
        raw = state.get("agent_pipeline")
        if raw:
            return normalize_pipeline(str(raw))
    return pipeline_from_config(cfg)


def classic_default_meta_enabled() -> bool:
    """1.0.2-style quiet path: meta off unless user enables it."""
    return False


def classic_default_reflexion_enabled() -> bool:
    """Reflexion off in classic (user request + quieter messengers)."""
    return False
