"""Profile-gated System One calls inside Holix.

Each flag stays off until it is set. A configured Jev or nimble preset does
not change Reflexion, end-of-turn, skill order, or shell confirmation by itself.
"""

from __future__ import annotations

import json
from typing import Any

from core.decision.config import resolve_decision
from core.decision.gates import (
    DEFAULT_CONFIDENCE,
    DEFAULT_NOUL,
    DEFAULT_QUALITY,
    INTERNAL_FLAGS,
    QUALITY_LEVELS,
    choice_label,
    noul_value,
    quality_from_score,
)
from core.decision.systemone import call_systemone, call_systemone_blocking
from core.meta_agent import QualityAssessment
from core.runtime.step_budget import step_limit_hit

_FINAL_NUDGE = (
    "The draft may be incomplete. Continue the same task with the missing part, "
    "or say what is still missing. Do not repeat the same draft."
)


def _raw_from_agent(agent: Any) -> dict[str, Any]:
    if agent is not None:
        raw = getattr(getattr(agent, "config", None), "decision", None)
        return dict(raw) if isinstance(raw, dict) else {}
    try:
        from core.profile.service import ProfileManager
        from core.tools.execution_context import get_profile_name

        name = str(get_profile_name() or "").strip()
        if not name:
            return {}
        loaded = getattr(ProfileManager().load_profile(name), "decision", None)
        return dict(loaded) if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _profile_of(agent: Any) -> str:
    name = str(getattr(getattr(agent, "config", None), "profile_name", "") or "").strip()
    if name:
        return name
    try:
        from core.tools.execution_context import get_profile_name

        return str(get_profile_name() or "").strip()
    except Exception:
        return ""


def _resolved_decision(agent: Any, raw: dict[str, Any]):
    from core.decision.config import profile_env_secret

    return resolve_decision(
        raw,
        api_key=profile_env_secret(_profile_of(agent), "DECISION_API_KEY"),
    )


def _threshold(raw: dict[str, Any], name: str, default: float) -> float:
    block = raw.get("thresholds")
    if not isinstance(block, dict) or name not in block:
        return default
    try:
        value = float(block[name])
    except (TypeError, ValueError):
        return default
    return min(1.0, max(0.0, value))


def flag_enabled(raw: dict[str, Any] | None, name: str) -> bool:
    if name not in INTERNAL_FLAGS:
        return False
    data = raw if isinstance(raw, dict) else {}
    if not resolve_decision(data).enabled:
        return False
    internal = data.get("internal")
    return bool(isinstance(internal, dict) and internal.get(name) is True)


def set_internal_flag(block: dict[str, Any] | None, name: str, enabled: bool) -> dict[str, Any]:
    if name not in INTERNAL_FLAGS:
        raise ValueError(f"Unknown internal flag: {name}")
    out = dict(block or {})
    if enabled and not resolve_decision(out).enabled:
        raise ValueError("Turn a decision preset on before enabling an internal gate.")
    internal = dict(out.get("internal") or {})
    internal[name] = bool(enabled)
    out["internal"] = internal
    return out


def set_threshold(block: dict[str, Any] | None, name: str, value: float) -> dict[str, Any]:
    if name not in {"noul", "confidence", "quality"}:
        raise ValueError("Threshold must be noul, confidence, or quality.")
    out = dict(block or {})
    thresholds = dict(out.get("thresholds") or {})
    thresholds[name] = min(1.0, max(0.0, float(value)))
    out["thresholds"] = thresholds
    return out


def _loads(text: str) -> dict[str, Any] | None:
    if text.startswith("System One error:"):
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


async def reflexion_assessment(
    agent: Any,
    task: str,
    draft: str,
    trajectory: str = "",
) -> QualityAssessment | None:
    """Score a draft. None means keep the chat-model evaluator."""
    raw = _raw_from_agent(agent)
    if not flag_enabled(raw, "reflexion"):
        return None
    state = f"Task:\n{task[:800]}\n\nDraft:\n{draft[:1500]}"
    if trajectory.strip():
        state += f"\n\nTool results:\n{trajectory[:800]}"
    text = await call_systemone(
        _resolved_decision(agent, raw),
        state,
        {
            "quality": {
                "type": "score",
                "instructions": "How well the draft answers the task.",
                "criteria": list(QUALITY_LEVELS),
            }
        },
    )
    parsed = quality_from_score(
        _loads(text),
        quality_threshold=_threshold(raw, "quality", DEFAULT_QUALITY),
        confidence_threshold=_threshold(raw, "confidence", DEFAULT_CONFIDENCE),
    )
    if parsed is None:
        return None
    quality, needs, level = parsed
    return QualityAssessment(
        quality_score=quality,
        needs_refinement=needs,
        improvement_areas=[level] if needs else [],
        refinement_prompt=level if needs else "",
        reasoning="systemone score",
    )


async def draft_should_continue(agent: Any, task: str, draft: str) -> bool:
    """True only when the end-of-turn flag is on and noul is below the threshold."""
    raw = _raw_from_agent(agent)
    if not flag_enabled(raw, "is_final"):
        return False
    text = await call_systemone(
        _resolved_decision(agent, raw),
        f"Task:\n{task[:800]}\n\nDraft:\n{draft[:1500]}",
        {
            "complete": {
                "type": "noul",
                "instructions": (
                    "The draft fully answers the task and no further tool call is required."
                ),
            }
        },
    )
    value = noul_value(_loads(text), "complete")
    if value is None:
        return False
    return value < _threshold(raw, "noul", DEFAULT_NOUL)


async def hold_incomplete_draft(
    state: dict[str, Any],
    agent: Any,
    messages: list[dict[str, Any]],
    step_count: int,
    final_response: str,
) -> dict[str, Any] | None:
    if int(state.get("decision_final_nudges") or 0) >= 1:
        return None
    if step_limit_hit(step_count, state.get("max_steps")):
        return None
    if not (final_response or "").strip():
        return None
    task = str(state.get("user_input") or "")
    if not await draft_should_continue(agent, task, final_response):
        return None
    updated = list(messages)
    updated.append({"role": "user", "content": _FINAL_NUDGE})
    return {
        "messages": updated,
        "step_count": step_count,
        "is_final": False,
        "final_response": "",
        "tool_calls": [],
        "decision_final_nudges": int(state.get("decision_final_nudges") or 0) + 1,
    }


def promote_skill(
    agent: Any,
    query: str,
    names: list[str],
    descriptions: dict[str, str],
) -> str | None:
    """Pick one suggested skill. None leaves the existing order unchanged."""
    raw = _raw_from_agent(agent)
    if not flag_enabled(raw, "skill_choice"):
        return None
    unique = [name for name in names if name]
    if len(unique) < 2:
        return None
    criteria = {name: (descriptions.get(name) or name)[:240] for name in unique[:8]}
    text = call_systemone_blocking(
        _resolved_decision(agent, raw),
        (query or "")[:800],
        {
            "skill": {
                "type": "choice",
                "instructions": "Which one skill best matches this request.",
                "criteria": criteria,
            }
        },
    )
    return choice_label(
        _loads(text),
        "skill",
        set(criteria),
        confidence_threshold=_threshold(raw, "confidence", DEFAULT_CONFIDENCE),
    )


async def shell_auto_allow(agent: Any, command: str) -> bool:
    """True only for a high noul. Errors and a low score do not allow the command."""
    raw = _raw_from_agent(agent)
    if not flag_enabled(raw, "shell_allow"):
        return False
    text = (command or "").strip()
    if not text:
        return False
    result = await call_systemone(
        _resolved_decision(agent, raw),
        text[:500],
        {
            "allow": {
                "type": "noul",
                "instructions": "This shell command is safe to run without asking the user.",
            }
        },
    )
    value = noul_value(_loads(result), "allow")
    if value is None:
        return False
    return value >= _threshold(raw, "noul", DEFAULT_NOUL)
