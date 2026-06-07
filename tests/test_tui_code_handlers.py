"""Unit tests for strict TUI formatters and slash routing."""

from __future__ import annotations

import pytest

from cli.tui.shared.formatters import (
    format_tool_args,
    format_tool_header,
    format_tool_result_preview,
    format_write_file_result_preview,
    split_write_file_result,
    truncate_text,
)
from core.tools.file_diff import DIFF_SEPARATOR, format_write_file_result


class TestFormatters:
    def test_truncate(self):
        assert truncate_text("hello", 10) == "hello"
        assert truncate_text("x" * 20, 10).endswith("…")

    def test_tool_header_running(self):
        assert "…" in format_tool_header("read_file", running=True)

    def test_tool_header_success(self):
        h = format_tool_header("terminal", duration_s=1.2, error=False)
        assert "✓" in h and "1.2" in h

    def test_tool_header_error(self):
        assert "✗" in format_tool_header("write_file", error=True)

    def test_tool_args_json(self):
        text = format_tool_args({"path": "/tmp/a"})
        assert "path" in text

    def test_result_preview(self):
        long = "a\n" * 200
        assert len(format_tool_result_preview(long, max_len=50)) <= 51

    def test_write_file_diff_split(self):
        body = format_write_file_result("f.py", "a\n", "b\n")
        summary, diff = split_write_file_result(body)
        assert "Updated f.py" in summary
        assert diff and "+b" in diff
        preview = format_write_file_result_preview(body, max_len=80)
        assert DIFF_SEPARATOR not in preview


@pytest.mark.asyncio
async def test_slash_clear_calls_action():
    from cli.shared.commands.agent_commands import AgentCommands

    class FakeApp:
        def __init__(self):
            self.cleared = False
            self._execution_modes = ["react"]
            self._execution_mode_index = 0
            self.streaming_enabled = False
            self.profile = "default"
            self.transcript_writes: list[str] = []

        def action_clear_chat(self):
            self.cleared = True

        def transcript_write(self, t):
            self.transcript_writes.append(str(t))

        def _refresh_status_bar(self):
            pass

        def run_worker(self, *a, **k):
            pass

        def _resolve_confirmation(self, *a, **k):
            pass

        def _resolve_plan_review(self, *a, **k):
            pass

        def _show_full_tool_result(self, *a, **k):
            pass

        def _list_recent_tools(self):
            pass

        async def _profile(self, cmd):
            pass

    app = FakeApp()
    await AgentCommands(app).handle("/clear")
    assert app.cleared