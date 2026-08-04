"""Agent max_tokens resolution."""

from __future__ import annotations

from types import SimpleNamespace

from core.llm.max_tokens import (
    DEFAULT_AGENT_MAX_TOKENS,
    DEFAULT_CHAT_MAX_TOKENS,
    profile_agent_max_tokens,
    purpose_from_graph_state,
    resolve_agent_max_tokens,
)


def test_resolve_prefers_profile_override() -> None:
    assert resolve_agent_max_tokens(profile_max_tokens=2048, default_max_tokens=4096) == 2048


def test_resolve_uses_global_default() -> None:
    assert resolve_agent_max_tokens(default_max_tokens=6000) == 6000


def test_resolve_builtin_default() -> None:
    assert resolve_agent_max_tokens() == DEFAULT_AGENT_MAX_TOKENS


def test_resolve_chat_uses_lower_budget() -> None:
    assert resolve_agent_max_tokens(purpose="chat") == DEFAULT_CHAT_MAX_TOKENS
    assert (
        resolve_agent_max_tokens(
            purpose="chat", chat_max_tokens=1500, default_max_tokens=8192
        )
        == 1500
    )


def test_profile_override_beats_chat_budget() -> None:
    assert (
        resolve_agent_max_tokens(
            purpose="chat",
            profile_max_tokens=4096,
            chat_max_tokens=1024,
        )
        == 4096
    )


def test_purpose_from_graph_state() -> None:
    assert purpose_from_graph_state({"execution_mode": "react"}) == "chat"
    assert (
        purpose_from_graph_state(
            {
                "execution_mode": "plan_and_execute",
                "plan_steps": [{"step": 1}],
                "current_plan_step": 0,
            }
        )
        == "plan"
    )


def test_profile_agent_max_tokens_reads_model_manager() -> None:
    manager = SimpleNamespace(
        get_agent_model_config=lambda _slot: SimpleNamespace(max_tokens=3000),
    )
    assert profile_agent_max_tokens(manager, "main") == 3000


def test_profile_agent_max_tokens_ignores_invalid() -> None:
    manager = SimpleNamespace(
        get_agent_model_config=lambda _slot: SimpleNamespace(max_tokens="bad"),
    )
    assert profile_agent_max_tokens(manager, "main") is None
