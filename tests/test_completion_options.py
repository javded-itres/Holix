"""Ollama think-off extras so reasoning models return visible content."""

from __future__ import annotations

from types import SimpleNamespace

from core.models.completion_options import (
    is_ollama_like,
    with_provider_completion_options,
)
from core.models.manager import ModelConfig


def test_is_ollama_like_by_provider_and_port() -> None:
    assert is_ollama_like(SimpleNamespace(provider="ollama", base_url="http://x/v1"))
    assert is_ollama_like(SimpleNamespace(provider="local", base_url="http://127.0.0.1:11434/v1"))
    assert not is_ollama_like(
        SimpleNamespace(provider="openai", base_url="https://api.openai.com/v1")
    )


def test_ollama_gets_think_false_extra_body() -> None:
    cfg = ModelConfig(
        provider="ollama",
        model="kimi-k2.7-code:cloud",
        base_url="http://127.0.0.1:11434/v1",
        api_key="ollama",
    )
    out = with_provider_completion_options(cfg, {"messages": [], "temperature": 0.2})
    extra = out["extra_body"]
    assert extra["think"] is False
    assert extra["chat_template_kwargs"]["enable_thinking"] is False
    assert out["temperature"] == 0.2


def test_thinking_opt_in_skips_think_off() -> None:
    cfg = ModelConfig(
        provider="ollama",
        model="kimi-k2.7-code:cloud",
        base_url="http://127.0.0.1:11434/v1",
        api_key="ollama",
        metadata={"enable_thinking": True},
    )
    out = with_provider_completion_options(cfg, {"messages": []})
    assert "extra_body" not in out


def test_openai_provider_untouched() -> None:
    cfg = ModelConfig(
        provider="openai",
        model="gpt-4o",
        base_url="https://api.openai.com/v1",
        api_key="sk",
    )
    kwargs = {"messages": [{"role": "user", "content": "hi"}]}
    assert with_provider_completion_options(cfg, kwargs) == kwargs
