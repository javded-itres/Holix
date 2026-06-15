"""LLM step timeout configuration."""

from __future__ import annotations

from types import SimpleNamespace

from core.graph.nodes.react_node import _DEFAULT_LLM_STEP_TIMEOUT_S, _llm_step_timeout_s
from core.llm.step_timeout import llm_step_timeout_message, reasoning_only_abort_s


def test_llm_step_timeout_default_is_independent_of_subagent_timeout() -> None:
    agent = SimpleNamespace(
        config=SimpleNamespace(
            llm_step_timeout=None,
            subagent_process_timeout=120.0,
        )
    )
    assert _llm_step_timeout_s(agent) == _DEFAULT_LLM_STEP_TIMEOUT_S


def test_llm_step_timeout_reads_dedicated_setting() -> None:
    agent = SimpleNamespace(config=SimpleNamespace(llm_step_timeout=45.0))
    assert _llm_step_timeout_s(agent) == 45.0


def test_reasoning_only_message_mentions_smart() -> None:
    msg = llm_step_timeout_message(90, model="coder", reasoning_only=True)
    assert "smart" in msg
    assert "coder" in msg


def test_reasoning_only_abort_window() -> None:
    assert reasoning_only_abort_s(300.0) == 90.0
    assert reasoning_only_abort_s(120.0) == 90.0