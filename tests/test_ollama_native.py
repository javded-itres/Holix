"""Ollama native /api/chat adapter."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from cli.core import ProfileConfig
from core.models.manager import ModelManager
from core.models.ollama_native import (
    build_chat_payload,
    native_chat_enabled,
    ollama_origin,
    to_openai_response,
    wrap_ollama_native_client,
)


def test_ollama_origin_strips_v1() -> None:
    assert ollama_origin("http://127.0.0.1:11434/v1") == "http://127.0.0.1:11434"
    assert ollama_origin("http://127.0.0.1:11434") == "http://127.0.0.1:11434"


def test_native_chat_defaults_on_for_ollama() -> None:
    assert native_chat_enabled(provider="ollama", base_url="http://127.0.0.1:11434/v1")
    assert not native_chat_enabled(
        provider="ollama",
        base_url="http://127.0.0.1:11434/v1",
        metadata={"native_chat": False},
    )
    assert not native_chat_enabled(provider="openai", base_url="https://api.openai.com/v1")


def test_payload_think_false_and_num_predict() -> None:
    payload = build_chat_payload(
        {
            "model": "kimi-k2.7-code:cloud",
            "messages": [{"role": "user", "content": "hi"}],
            "temperature": 0.2,
            "max_tokens": 4096,
            "tools": [{"type": "function"}],
            "extra_body": {"think": False, "num_ctx": 131072},
        },
        {"think": False},
    )
    assert payload["think"] is False
    assert payload["options"]["num_predict"] == 4096
    assert payload["options"]["num_ctx"] == 131072
    assert payload["tools"]


def test_to_openai_response_maps_thinking_and_tool_args() -> None:
    data = {
        "message": {
            "role": "assistant",
            "content": "PONG",
            "thinking": "say pong",
            "tool_calls": [{"function": {"name": "glob", "arguments": {"pattern": "*.py"}}}],
        },
        "done": True,
        "done_reason": "stop",
        "prompt_eval_count": 10,
        "eval_count": 4,
    }
    resp = to_openai_response(data, model="kimi")
    msg = resp.choices[0].message
    assert msg.content == "PONG"
    assert msg.reasoning == "say pong"
    assert resp.choices[0].finish_reason == "tool_calls"
    args = json.loads(msg.tool_calls[0].function.arguments)
    assert args["pattern"] == "*.py"


def test_wrap_skipped_when_native_chat_false() -> None:
    sentinel = object()
    out = wrap_ollama_native_client(
        sentinel,
        provider="ollama",
        base_url="http://127.0.0.1:11434/v1",
        metadata={"native_chat": False},
    )
    assert out is sentinel


@pytest.mark.asyncio
async def test_native_create_posts_api_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = ProfileConfig(
        profile_name="ollama",
        default_provider="ollama",
        providers={
            "ollama": {
                "base_url": "http://127.0.0.1:11434/v1",
                "api_key": "ollama",
                "default_model": "kimi-k2.7-code:cloud",
                "metadata": {"preset_id": "ollama", "native_chat": True, "think": False},
            }
        },
    )
    mm = ModelManager(cfg)
    posted: dict[str, Any] = {}

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "message": {"role": "assistant", "content": "PONG", "thinking": "ok"},
                "done": True,
                "done_reason": "stop",
            }

    async def fake_post(url, json=None):
        posted["url"] = url
        posted["json"] = json
        return _Resp()

    openai_client = SimpleNamespace(models=object())
    monkeypatch.setattr("core.models.manager.create_openai_client", lambda **_k: openai_client)
    client = mm.get_client(mm.get_provider_model_config("ollama"))
    client.chat.completions._http.post = fake_post  # type: ignore[attr-defined]
    result = await client.chat.completions.create(
        model="kimi-k2.7-code:cloud",
        messages=[{"role": "user", "content": "hi"}],
        extra_body={"think": False},
    )
    assert posted["url"] == "http://127.0.0.1:11434/api/chat"
    assert posted["json"]["think"] is False
    assert result.choices[0].message.content == "PONG"
    assert result.choices[0].message.reasoning == "ok"
