"""Scripted OpenAI-compatible LLM responses for user-case tests."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock


@dataclass(frozen=True)
class ToolCall:
    """One function tool call the model should request."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    id: str | None = None


@dataclass(frozen=True)
class Final:
    """Final assistant text with no tool calls."""

    content: str


Turn = ToolCall | Final | list[ToolCall]


def _mock_response(
    *,
    content: str = "",
    tool_calls: list[Any] | None = None,
    finish_reason: str = "stop",
) -> MagicMock:
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls
    message.reasoning_content = None
    choice = MagicMock()
    choice.message = message
    choice.finish_reason = finish_reason
    response = MagicMock()
    response.choices = [choice]
    response.usage = None
    return response


def _tool_call_mock(tc: ToolCall, index: int) -> MagicMock:
    mock = MagicMock()
    mock.id = tc.id or f"call_{index}"
    mock.type = "function"
    mock.function = MagicMock()
    mock.function.name = tc.name
    mock.function.arguments = json.dumps(tc.arguments)
    return mock


def turn_to_response(turn: Turn, *, call_index: int) -> MagicMock:
    """Convert a high-level turn into an OpenAI-shaped chat completion."""
    if isinstance(turn, Final):
        return _mock_response(content=turn.content, tool_calls=None, finish_reason="stop")

    calls = turn if isinstance(turn, list) else [turn]
    mocks = [_tool_call_mock(tc, call_index + i) for i, tc in enumerate(calls)]
    return _mock_response(content="", tool_calls=mocks, finish_reason="tool_calls")


class ScriptedLLM:
    """FIFO script of LLM completions; fails if the graph over/under-consumes.

    Install patches both ``agent.client.chat.completions.create`` and
    ``core.models.fallback.chat_completions_with_fallback`` (react uses the latter
    when ``model_manager`` is present).
    """

    def __init__(self, turns: list[Turn] | None = None) -> None:
        self._script: list[Turn] = list(turns or [])
        self.calls: list[dict[str, Any]] = []
        self._call_index = 0
        self._installed = False

    def script(self, turns: list[Turn]) -> ScriptedLLM:
        self._script = list(turns)
        self.calls.clear()
        self._call_index = 0
        return self

    @property
    def remaining(self) -> int:
        return len(self._script)

    def assert_exhausted(self) -> None:
        if self._script:
            raise AssertionError(
                f"ScriptedLLM has {len(self._script)} unused turn(s): {self._script!r}"
            )

    async def _next_response(self, **kwargs: Any) -> MagicMock:
        self.calls.append(dict(kwargs))
        if not self._script:
            raise AssertionError(
                f"ScriptedLLM exhausted but LLM was called again "
                f"(call #{len(self.calls)}; keys={list(kwargs)})"
            )
        turn = self._script.pop(0)
        response = turn_to_response(turn, call_index=self._call_index)
        if isinstance(turn, Final):
            self._call_index += 1
        else:
            n = len(turn) if isinstance(turn, list) else 1
            self._call_index += n
        return response

    def install(self, agent: Any, monkeypatch: Any) -> ScriptedLLM:
        """Patch agent client so this harness owns LLM responses.

        Force ReAct to use ``agent.client`` (not ModelManager + global fallback) so
        multiple harnesses in one test each keep an independent script queue.
        """
        create = AsyncMock(side_effect=self._next_response)
        agent.client.chat.completions.create = create

        # HolixAgent.model_manager is a property without setter. Leave a falsy
        # non-None sentinel in the cache so the property does not rebuild MM and
        # react_node takes the client.create branch (`if model_manager:`).
        class _NoModelManager:
            def __bool__(self) -> bool:
                return False

        agent._model_manager = _NoModelManager()

        async def _fallback(*_args: Any, **kwargs: Any) -> MagicMock:
            return await self._next_response(**kwargs)

        # Fallback patch still helps single-harness paths that re-create MM.
        monkeypatch.setattr(
            "core.models.fallback.chat_completions_with_fallback",
            _fallback,
        )
        self._installed = True
        return self
