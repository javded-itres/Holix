"""Tests for TUI performance optimizations (stream batching, deferred init helpers)."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

import pytest
from cli.tui.code.handlers.events import CodeEventHandler
from core.agent_events import (
    AssistantDeltaEvent,
    BackgroundProcessErrorEvent,
    BackgroundProcessStartedEvent,
    BackgroundProcessStoppedEvent,
    FinalResponseEvent,
)


class FakeTranscriptStore:
    def __init__(self) -> None:
        self._stream_plain = ""

    def append_stream_delta(self, text: str) -> None:
        self._stream_plain += text

    def has_stream_buffer(self) -> bool:
        return bool(self._stream_plain.strip())

    def stream_plain(self) -> str:
        return self._stream_plain

    def last_tool(self) -> str | None:
        return None

    def flush_stream_to_assistant(self, *, markdown: str | None = None) -> None:
        self._stream_plain = ""

    def append(self, *args, **kwargs) -> None:
        pass

    def clear_stream(self) -> None:
        self._stream_plain = ""


class FakeApp:
    def __init__(self) -> None:
        self._stream_buffer = ""
        self._is_streaming = False
        self._transcript_store = FakeTranscriptStore()
        self.writes: list = []
        self.status_lines: list[str] = []
        self.scroll_hint_scheduled = 0
        self.stream_deltas: list[str] = []
        self.stream_cleared = 0
        self.background_process: str | None = None
        self.background_process_id: str | None = None
        self.background_process_healthy = True

    def set_background_process(
        self,
        *,
        label: str,
        process_id: str = "",
        healthy: bool = True,
    ) -> None:
        self.background_process = label
        self.background_process_id = process_id or None
        self.background_process_healthy = healthy

    def clear_background_process(self) -> None:
        self.background_process = None
        self.background_process_id = None
        self.background_process_healthy = True

    def transcript_write(self, content, **kwargs) -> None:
        self.writes.append(content)

    def append_stream_delta(self, text: str) -> None:
        self.stream_deltas.append(text)
        self._stream_buffer += text
        self._transcript_store.append_stream_delta(text)
        self._is_streaming = True

    def clear_stream_display(self) -> None:
        self.stream_cleared += 1
        self._stream_buffer = ""

    def flush_partial_stream_to_transcript(self) -> None:
        if self._stream_buffer:
            self.writes.append(self._stream_buffer)
        self._stream_buffer = ""

    def set_thinking(self, message) -> None:
        pass

    def set_status_line(self, text: str) -> None:
        self.status_lines.append(text)

    def _schedule_scroll_hint_update(self, **kwargs) -> None:
        self.scroll_hint_scheduled += 1

    def _restore_prompt_focus(self, **kwargs) -> None:
        pass

    def run_worker(self, *args, **kwargs) -> None:
        pass

    async def _update_context_display_async(self) -> None:
        pass


class TestStreamHandler:
    def test_delta_does_not_write_transcript_during_stream(self):
        app = FakeApp()
        handler = CodeEventHandler(app)
        handler.handle(AssistantDeltaEvent(content="hello "))
        handler.handle(AssistantDeltaEvent(content="world"))
        assert app.writes == []
        assert app._stream_buffer == "hello world"
        assert app.stream_deltas == ["hello ", "world"]

    def test_final_response_renders_markdown_when_streamed(self):
        from rich.markdown import Markdown

        app = FakeApp()
        handler = CodeEventHandler(app)
        app._is_streaming = True
        app._transcript_store._stream_plain = "**Hello** world"
        handler.handle(FinalResponseEvent(content="**Hello** world"))
        assert any(isinstance(w, Markdown) for w in app.writes)
        assert len(app.writes) == 2
        assert app.stream_cleared >= 1
        assert app.scroll_hint_scheduled == 1

    def test_final_response_renders_markdown_without_stream(self):
        from rich.markdown import Markdown

        app = FakeApp()
        handler = CodeEventHandler(app)
        handler.handle(FinalResponseEvent(content="**bold**"))
        assert any(isinstance(w, Markdown) for w in app.writes)

    def test_final_response_uses_stream_buffer_when_final_empty(self):
        from rich.markdown import Markdown

        app = FakeApp()
        handler = CodeEventHandler(app)
        app._is_streaming = True
        app._transcript_store._stream_plain = "Итоговый ответ из стрима"
        handler.handle(FinalResponseEvent(content="No response generated"))
        assert any(isinstance(w, Markdown) for w in app.writes)
        rendered = [w for w in app.writes if isinstance(w, Markdown)][0]
        assert "Итоговый ответ из стрима" in rendered.markup


class TestBackgroundProcessEvents:
    def test_started_sets_process_bar_and_writes_hint(self):
        app = FakeApp()
        handler = CodeEventHandler(app)
        handler.handle(
            BackgroundProcessStartedEvent(
                process_id="proc_abc",
                label="uvicorn",
                command="uvicorn main:app",
                pid=8000,
                log_path="/tmp/proc.log",
            )
        )
        assert app.background_process == "uvicorn · pid 8000"
        assert app.background_process_id == "proc_abc"
        joined = " ".join(str(w) for w in app.writes)
        assert "/process-stop" in joined
        assert "/tmp/proc.log" in joined

    def test_error_marks_unhealthy(self):
        app = FakeApp()
        handler = CodeEventHandler(app)
        handler.handle(
            BackgroundProcessErrorEvent(
                process_id="proc_bad",
                label="api",
                pid=9,
                status="crashed",
                error_summary="ModuleNotFoundError: x",
            )
        )
        assert app.background_process_healthy is False
        assert "error" in " ".join(str(w) for w in app.writes).lower()

    def test_stopped_clears_process_bar(self):
        app = FakeApp()
        app.set_background_process(label="srv · pid 1", process_id="proc_x")
        handler = CodeEventHandler(app)
        handler.handle(
            BackgroundProcessStoppedEvent(
                process_id="proc_x",
                label="srv",
                pid=1,
            )
        )
        assert app.background_process is None
        assert any("stopped" in str(w).lower() for w in app.writes)


@pytest.mark.asyncio
async def test_finish_mcp_registration_adds_late_tools():
    from core.tools.registry import ToolRegistry

    async def _wait_ready(*args, **kwargs):
        return {"srv": True}

    registry = ToolRegistry()
    mgr = MagicMock()
    mgr.available_servers = ["srv"]
    late_tool = MagicMock()
    late_tool.name = "mcp_srv_toolB"
    mgr.get_tool_adapters.return_value = [late_tool]
    mgr.wait_ready = _wait_ready

    registry._mcp_manager = mgr  # type: ignore[attr-defined]
    registry._mcp_enabled_servers = ["srv"]  # type: ignore[attr-defined]

    added = await registry.finish_mcp_registration(timeout=1.0)
    assert added == 1
    assert "mcp_srv_toolB" in registry.tools


@pytest.mark.asyncio
async def test_mcp_wait_ready_parallel():
    from core.mcp.manager import MCPManager

    mgr = MCPManager({})
    mgr._configs = {"a": MagicMock(), "b": MagicMock(), "c": MagicMock()}

    async def _slow_ready(name: str, delay: float) -> None:
        await asyncio.sleep(delay)
        mgr._ready_events[name].set()

    for name in ("a", "b", "c"):
        mgr._ready_events[name] = asyncio.Event()

    for name, delay in (("a", 0.12), ("b", 0.12), ("c", 0.12)):
        asyncio.create_task(_slow_ready(name, delay))

    started = time.monotonic()
    results = await mgr.wait_ready(["a", "b", "c"], timeout=1.0)
    elapsed = time.monotonic() - started

    assert results == {"a": True, "b": True, "c": True}
    assert elapsed < 0.35


def test_usage_cache_hits_on_same_messages():
    from core.context.manager import ContextManager
    from core.context.token_counter import TokenCounter

    counter = TokenCounter()
    manager = ContextManager(context_window=10_000, token_counter=counter)
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]
    usage1 = manager.get_usage(messages, conversation_id="conv1")
    counter.count_message_tokens = lambda msgs: 99999  # type: ignore[method-assign]
    usage2 = manager.get_usage(messages, conversation_id="conv1")
    assert usage2["used"] == usage1["used"]


def test_usage_cache_incremental_append():
    from core.context.manager import ContextManager
    from core.context.token_counter import TokenCounter

    counter = TokenCounter()
    manager = ContextManager(context_window=10_000, token_counter=counter)
    base = [{"role": "user", "content": "one two three four five"}]
    extended = base + [{"role": "assistant", "content": "six"}]

    full = manager.get_usage(extended, conversation_id="conv2")["used"]
    manager.invalidate_usage_cache("conv2")
    manager.get_usage(base, conversation_id="conv2")
    incremental = manager.get_usage(extended, conversation_id="conv2")["used"]
    assert incremental == full


def test_skills_index_skips_unchanged(tmp_path):
    from core.di.runtime_config import HolixRuntimeConfig
    from core.skills.manager import SkillsManager

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill_file = skills_dir / "demo.md"
    skill_file.write_text(
        "---\nname: demo\ndescription: test\n---\nbody\n",
        encoding="utf-8",
    )
    vector_dir = tmp_path / "vector"
    vector_dir.mkdir()

    base = HolixRuntimeConfig.from_settings()
    cfg = base.with_overrides(
        skills_dir=str(skills_dir),
        vector_db_path=str(vector_dir / "memory"),
    )

    mgr = SkillsManager(cfg)
    mgr.skills_collection = MagicMock()
    mgr.load_all_skills(defer_index=True)
    assert mgr.skills_collection.upsert.call_count == 0

    first = mgr.index_all_skills()
    assert first == 1
    second = mgr.index_all_skills()
    assert second == 0