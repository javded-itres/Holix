"""Resolve max_tokens for agent LLM calls (reasoning models need a budget)."""

from __future__ import annotations

# Plan / coding headroom (long patches, multi-file reasoning).
DEFAULT_AGENT_MAX_TOKENS = 8192
# Free-chat / messenger steps. Same headroom as plan/coding by default so
# multi-tool turns are not cut mid-call; monologue is blocked by honesty /
# tool_choice, not by starving the budget.
DEFAULT_CHAT_MAX_TOKENS = 8192


def resolve_agent_max_tokens(
    *,
    profile_max_tokens: int | None = None,
    default_max_tokens: int | None = None,
    chat_max_tokens: int | None = None,
    purpose: str = "agent",
) -> int:
    """Pick generation budget.

    Priority:
    1. Per-model profile ``max_tokens`` (always wins when set)
    2. Purpose-specific default (``chat`` vs plan/agent)
    3. Built-in defaults
    """
    if profile_max_tokens is not None and int(profile_max_tokens) > 0:
        return int(profile_max_tokens)

    purpose_key = (purpose or "agent").strip().lower()
    if purpose_key in {"chat", "messenger", "react_chat"}:
        if chat_max_tokens is not None and int(chat_max_tokens) > 0:
            return int(chat_max_tokens)
        return DEFAULT_CHAT_MAX_TOKENS

    if default_max_tokens is not None and int(default_max_tokens) > 0:
        return int(default_max_tokens)
    return DEFAULT_AGENT_MAX_TOKENS


def purpose_from_graph_state(state: object | None) -> str:
    """``chat`` for free ReAct; ``plan`` when executing plan steps / plan modes."""
    if state is None or not isinstance(state, dict):
        return "chat"
    plan_steps = state.get("plan_steps") or []
    try:
        current = int(state.get("current_plan_step") or 0)
    except (TypeError, ValueError):
        current = 0
    if plan_steps and current < len(plan_steps):
        return "plan"
    mode = str(state.get("execution_mode") or "").strip().lower()
    if mode in {"plan_and_execute", "hybrid"}:
        # Hybrid free-chat between plan waves still benefits from chat budget
        # unless a plan step is active (handled above).
        if plan_steps:
            return "plan"
    return "chat"


def _positive_max_tokens(raw: object) -> int | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def profile_agent_max_tokens(model_manager: object | None, agent_slot: str) -> int | None:
    """Read ``max_tokens`` for this agent slot.

    A full ``agent_models`` entry (provider + model) wins through
    ``ModelManager``. A window-only entry — output budget while the agent
    still inherits the parent model — has no provider, so
    ``get_agent_model_config`` returns nothing. That budget still lives on
    ``agent_models.<slot>.max_tokens``.
    """
    if model_manager is None:
        return None
    getter = getattr(model_manager, "get_agent_model_config", None)
    if callable(getter):
        try:
            cfg = getter(agent_slot)
        except Exception:
            cfg = None
        found = _positive_max_tokens(getattr(cfg, "max_tokens", None) if cfg is not None else None)
        if found:
            return found
    profile = getattr(model_manager, "profile_config", None)
    agent_models = getattr(profile, "agent_models", None) or {}
    if isinstance(agent_models, dict):
        entry = agent_models.get(agent_slot)
        if isinstance(entry, dict):
            return _positive_max_tokens(entry.get("max_tokens"))
    return None
