"""Pick a chat model for one user turn. Off unless global config enables it.

The switch is not stored on the profile. A failed or low-confidence decision
leaves the model that was already selected.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from core.decision.config import profile_env_secret, resolve_decision
from core.decision.gates import DEFAULT_CONFIDENCE, choice_label
from core.decision.internal import _profile_of, _raw_from_agent, _threshold
from core.decision.systemone import call_systemone

logger = logging.getLogger(__name__)

_MAX_CANDIDATES = 12
_STATE_CHARS = 1500
# Decision, embedding, and media aliases are not chat models.
_NON_CHAT = (
    "nimble",
    "tev1",
    "jev",
    "embed",
    "laya",
    "whisper",
    "image",
    "video",
    "hailuo",
    "flux",
    "seedance",
)


@dataclass(frozen=True, slots=True)
class ModelAutoSelect:
    enabled: bool = False
    models: tuple[str, ...] = ()


def read_model_auto_select(raw: dict[str, Any] | None = None) -> ModelAutoSelect:
    """Read ``model_auto_select`` from global config. Missing means off."""
    if raw is None:
        try:
            from core.global_config import load_global_config_raw

            loaded = load_global_config_raw()
            raw = loaded if isinstance(loaded, dict) else {}
        except Exception:
            raw = {}
    block = raw.get("model_auto_select") if isinstance(raw, dict) else None
    if not isinstance(block, dict):
        return ModelAutoSelect()
    names: list[str] = []
    seen: set[str] = set()
    for item in block.get("models") or []:
        name = str(item or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return ModelAutoSelect(enabled=bool(block.get("enabled")), models=tuple(names))


def _non_chat(model_id: str) -> bool:
    low = model_id.lower()
    return any(part in low for part in _NON_CHAT)


def chat_candidates(available: list[str], marked: tuple[str, ...]) -> list[str]:
    """Marked models that are available. An empty mark list means all chat models."""
    live = [
        str(item).strip() for item in available if str(item).strip() and not _non_chat(str(item))
    ]
    live_set = set(live)
    if not marked:
        return live[:_MAX_CANDIDATES]
    chosen: list[str] = []
    for name in marked:
        short = name.split("/")[-1] if "/" in name else name
        if name in live_set and name not in chosen:
            chosen.append(name)
        elif short in live_set and short not in chosen:
            chosen.append(short)
        if len(chosen) >= _MAX_CANDIDATES:
            break
    return chosen


def _provider_models(agent: Any) -> tuple[str, list[str]]:
    config = getattr(agent, "config", None)
    providers = getattr(config, "providers", None) or {}
    if not isinstance(providers, dict):
        return "", []
    active = getattr(agent, "active_model_config", None)
    provider = str(getattr(active, "provider", "") or "").strip()
    if not provider or provider not in providers:
        provider = str(getattr(config, "default_provider", "") or "").strip()
    data = providers.get(provider)
    if not isinstance(data, dict):
        return provider, []
    models = [
        str(item).strip() for item in (data.get("available_models") or []) if str(item).strip()
    ]
    return provider, models


async def choose_chat_model(
    agent: Any, prompt: str, settings: ModelAutoSelect | None = None
) -> str | None:
    """Return a model id, or None to keep the current model."""
    slot = str(getattr(agent, "agent_slot", "main") or "main").strip()
    if slot not in {"", "main"}:
        return None
    text = (prompt or "").strip()
    if not text:
        return None
    selected = settings if settings is not None else read_model_auto_select()
    if not selected.enabled:
        return None
    raw = _raw_from_agent(agent)
    resolved = resolve_decision(
        raw,
        api_key=profile_env_secret(_profile_of(agent), "DECISION_API_KEY"),
    )
    if not resolved.enabled:
        return None
    provider, available = _provider_models(agent)
    candidates = chat_candidates(available, selected.models)
    if len(candidates) < 2 or not provider:
        return None
    try:
        answer = await call_systemone(
            resolved,
            text[:_STATE_CHARS],
            {
                "model": {
                    "type": "choice",
                    "instructions": (
                        "Which one chat model should answer this request? "
                        "Match the difficulty. A short or simple request uses a lighter model. "
                        "A long, ambiguous, or multi-step request uses a stronger model."
                    ),
                    "criteria": {name: name for name in candidates},
                }
            },
        )
    except Exception:
        logger.debug("Model auto-select call failed", exc_info=True)
        return None
    if not isinstance(answer, str) or answer.startswith("System One error:"):
        return None
    try:
        payload = json.loads(answer)
    except json.JSONDecodeError:
        return None
    return choice_label(
        payload,
        "model",
        set(candidates),
        confidence_threshold=_threshold(raw, "confidence", DEFAULT_CONFIDENCE),
    )


async def apply_model_auto_select(
    agent: Any,
    prompt: str,
    *,
    resume: bool = False,
) -> None:
    """Switch the live chat model for this turn. Never raises into the turn."""
    if resume or agent is None:
        return
    try:
        chosen = await choose_chat_model(agent, prompt)
        if not chosen:
            return
        current = str(getattr(agent, "model", "") or "").strip()
        if chosen == current:
            return
        provider, _available = _provider_models(agent)
        manager = getattr(agent, "model_manager", None)
        if manager is None or not provider:
            return
        config = manager.get_provider_model_config(provider, model_id=chosen)
        if config is None:
            return
        agent.set_active_model_config(config)
        logger.info("Model auto-select: %s", chosen)
    except Exception:
        logger.debug("Model auto-select skipped", exc_info=True)
