"""Resolve max_tokens for agent LLM calls (reasoning models need a budget)."""

from __future__ import annotations

# Plan / coding headroom (long patches, multi-file reasoning).
DEFAULT_AGENT_MAX_TOKENS = 8192
# Free-chat / messenger steps: shorter budget reduces degeneration loops.
DEFAULT_CHAT_MAX_TOKENS = 2048


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