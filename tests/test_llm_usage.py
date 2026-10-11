"""LLM token usage extraction and estimation."""

from __future__ import annotations

from types import SimpleNamespace

from core.llm.usage import (
    completion_text_from_message,
    context_occupancy_tokens,
    estimate_chat_tokens,
    resolve_usage,
    usage_dict_from_response,
)


def test_usage_dict_from_response_openai_shape() -> None:
    response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    )
    assert usage_dict_from_response(response) == {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "context_tokens": 100,
    }


def test_context_occupancy_matches_claude_code() -> None:
    # OpenAI prompt_tokens already includes the cache.
    openai = {
        "prompt_tokens": 31126,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }
    assert context_occupancy_tokens(openai) == 31126
    # Anthropic reports uncached input separately from cache read and write.
    anthropic = {
        "prompt_tokens": 1000,
        "cache_read_input_tokens": 20000,
        "cache_creation_input_tokens": 5000,
    }
    assert context_occupancy_tokens(anthropic) == 26000
    assert context_occupancy_tokens({"prompt_tokens": 10, "completion_tokens": 90}) == 10


def test_usage_dict_from_response_sums_when_total_missing() -> None:
    response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=None)
    )
    assert usage_dict_from_response(response)["total_tokens"] == 15


def test_resolve_usage_falls_back_to_estimate() -> None:
    usage = resolve_usage(
        None,
        messages=[{"role": "user", "content": "hello world"}],
        completion_text="hi there",
    )
    assert usage["total_tokens"] > 0
    assert usage["prompt_tokens"] > 0
    assert usage["provider"] is False


def test_estimate_chat_tokens_non_zero() -> None:
    usage = estimate_chat_tokens(
        [{"role": "user", "content": "count these tokens please"}],
        completion_text="ok",
    )
    assert usage["total_tokens"] >= 1


def test_completion_text_includes_tool_calls() -> None:
    message = SimpleNamespace(
        content="",
        tool_calls=[
            SimpleNamespace(function=SimpleNamespace(name="read_file", arguments='{"path":"a.py"}'))
        ],
    )
    text = completion_text_from_message(message)
    assert "read_file" in text
    assert "a.py" in text
