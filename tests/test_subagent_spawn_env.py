"""Sub-agent process spawn must not pass API keys in Process args."""

from __future__ import annotations

import inspect
import os

import pytest
from core.subagents.process import (
    _SUBAGENT_API_KEY_ENV,
    _SUBAGENT_BASE_URL_ENV,
    _SUBAGENT_PRESET_ENV,
    _start_subagent_process,
    run_sub_agent_in_process,
)


def test_start_subagent_process_sets_child_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_SUBAGENT_API_KEY_ENV, raising=False)
    monkeypatch.delenv(_SUBAGENT_BASE_URL_ENV, raising=False)
    monkeypatch.delenv(_SUBAGENT_PRESET_ENV, raising=False)

    seen: dict[str, str] = {}

    class FakeProcess:
        def start(self) -> None:
            seen["api_key"] = os.environ.get(_SUBAGENT_API_KEY_ENV, "")
            seen["base_url"] = os.environ.get(_SUBAGENT_BASE_URL_ENV, "")
            seen["preset_id"] = os.environ.get(_SUBAGENT_PRESET_ENV, "")

    proc = FakeProcess()
    _start_subagent_process(
        proc,
        api_key="secret-key",
        base_url="https://llm.example/v1",
        preset_id="litellm",
    )

    assert seen == {
        "api_key": "secret-key",
        "base_url": "https://llm.example/v1",
        "preset_id": "litellm",
    }
    assert _SUBAGENT_API_KEY_ENV not in os.environ
    assert _SUBAGENT_BASE_URL_ENV not in os.environ
    assert _SUBAGENT_PRESET_ENV not in os.environ


def test_run_sub_agent_process_does_not_accept_api_key_args() -> None:
    params = inspect.signature(run_sub_agent_in_process).parameters
    assert "parent_api_key" not in params
    assert "parent_base_url" not in params