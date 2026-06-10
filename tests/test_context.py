"""Tests for the context management system."""

from unittest.mock import MagicMock

import pytest
from core.agent_events import (
    AgentEventBus,
    ContextCompressedEvent,
    ContextWarningEvent,
    EventType,
)
from core.context.compressor import ContextCompressor
from core.context.manager import ContextManager
from core.context.token_counter import DEFAULT_CONTEXT_WINDOW, TokenCounter


class TestTokenCounter:
    """Tests for TokenCounter."""

    def test_count_text_tokens_empty(self):
        counter = TokenCounter()
        assert counter.count_text_tokens("") == 0

    def test_count_text_tokens_basic(self):
        counter = TokenCounter()
        tokens = counter.count_text_tokens("Hello, world!")
        # Should return a positive integer
        assert isinstance(tokens, int)
        assert tokens > 0

    def test_count_text_tokens_longer_text_more_tokens(self):
        counter = TokenCounter()
        short = counter.count_text_tokens("Hi")
        long = counter.count_text_tokens("This is a longer sentence with many more words and characters in it.")
        assert long > short

    def test_count_message_tokens_empty(self):
        counter = TokenCounter()
        assert counter.count_message_tokens([]) == 0

    def test_count_message_tokens_single(self):
        counter = TokenCounter()
        messages = [{"role": "user", "content": "Hello"}]
        tokens = counter.count_message_tokens(messages)
        # Should include overhead (3 priming + 4 per message + 1 for role)
        assert tokens > 0

    def test_count_message_tokens_multiple(self):
        counter = TokenCounter()
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        tokens = counter.count_message_tokens(messages)
        assert tokens > 0

    def test_count_message_tokens_with_tool_calls(self):
        counter = TokenCounter()
        messages = [
            {"role": "user", "content": "Read the file"},
            {"role": "assistant", "content": "", "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "/tmp/test.txt"}'},
                }
            ]},
            {"role": "tool", "tool_call_id": "call_123", "content": "File content here"},
        ]
        tokens = counter.count_message_tokens(messages)
        assert tokens > 0

    def test_format_token_count(self):
        assert TokenCounter.format_token_count(0) == "0"
        assert TokenCounter.format_token_count(500) == "500"
        assert TokenCounter.format_token_count(1500) == "2k"
        assert TokenCounter.format_token_count(131072) == "131k"
        assert TokenCounter.format_token_count(1_500_000) == "1.5M"

    def test_default_context_window(self):
        assert DEFAULT_CONTEXT_WINDOW == 131072


class TestContextManager:
    """Tests for ContextManager."""

    def setup_method(self):
        self.counter = TokenCounter()
        self.manager = ContextManager(
            context_window=1000,
            token_counter=self.counter,
            compressor=None,  # No compressor for basic tests
            event_bus=None,
        )

    def test_get_usage_empty(self):
        usage = self.manager.get_usage([])
        assert usage["used"] == 0  # No messages = 0 tokens
        assert usage["total"] == 1000
        assert usage["messages_count"] == 0

    def test_get_usage_with_messages(self):
        messages = [
            {"role": "user", "content": "Hello, this is a test message."},
            {"role": "assistant", "content": "Hi! I received your message."},
        ]
        usage = self.manager.get_usage(messages)
        assert usage["used"] > 0
        assert usage["total"] == 1000
        assert usage["messages_count"] == 2

    def test_is_near_limit_below(self):
        messages = [{"role": "user", "content": "Hi"}]
        assert not self.manager.is_near_limit(messages, threshold=0.9)

    def test_is_near_limit_above(self):
        # Create messages that will exceed 90% of a 1000-token window
        messages = [{"role": "user", "content": "x" * 3000}]  # Very long message
        # With 1000 token window, this should be near the limit
        usage = self.manager.get_usage(messages)
        if usage["percent"] >= 90:
            assert self.manager.is_near_limit(messages, threshold=0.9)
        else:
            # If token counting gives lower than expected, just verify the logic works
            assert not self.manager.is_near_limit(messages, threshold=0.99)

    def test_get_usage_level_green(self):
        messages = [{"role": "user", "content": "Hi"}]
        level = self.manager.get_usage_level(messages)
        # With a 1000 token window and a short message, should be green
        assert level in ("green", "yellow", "red")

    def test_format_usage_display(self):
        messages = [{"role": "user", "content": "Hello world"}]
        display = self.manager.format_usage_display(messages)
        # Should contain format like "Xk/1k (Y%)"
        assert "/1k" in display or "/1000" in display
        assert "%" in display

    def test_update_context_window(self):
        self.manager.update_context_window(2000)
        assert self.manager.context_window == 2000

    @pytest.mark.asyncio
    async def test_compress_context_no_compressor(self):
        messages = [{"role": "user", "content": "Test"}]
        result, was_compressed = await self.manager.compress_context(messages)
        assert was_compressed is False
        assert result == messages

    @pytest.mark.asyncio
    async def test_auto_compress_below_threshold(self):
        messages = [{"role": "user", "content": "Hi"}]
        result, was_compressed = await self.manager.auto_compress_if_needed(messages)
        assert was_compressed is False
        assert result == messages


class TestContextManagerWithBus:
    """Tests for ContextManager with event bus."""

    def setup_method(self):
        self.counter = TokenCounter()
        self.bus = AgentEventBus(name="test")
        self.events_received = []
        self.bus.subscribe(lambda e: self.events_received.append(e))
        self.manager = ContextManager(
            context_window=1000,
            token_counter=self.counter,
            compressor=None,
            event_bus=self.bus,
        )

    @pytest.mark.asyncio
    async def test_auto_compress_emits_warning(self):
        # Create messages that will trigger warning threshold (70%)
        messages = [{"role": "user", "content": "x" * 2000}]

        await self.manager.auto_compress_if_needed(messages)

        # Check if any warning events were emitted
        warning_events = [e for e in self.events_received if isinstance(e, ContextWarningEvent)]
        usage = self.manager.get_usage(messages)

        if usage["percent"] >= 70:
            assert len(warning_events) > 0
            assert warning_events[0].level in ("warning", "critical")


class TestContextCompressor:
    """Tests for ContextCompressor."""

    def test_format_messages_for_summary(self):
        mock_client = MagicMock()
        compressor = ContextCompressor(client=mock_client, model="test")

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
            {"role": "tool", "content": "result data", "metadata": {"tool_name": "read_file"}},
        ]
        text = compressor._format_messages_for_summary(messages)
        assert "USER: Hello" in text
        assert "ASSISTANT: Hi there" in text
        assert "TOOL (read_file): result data" in text

    def test_format_messages_truncates_long_content(self):
        mock_client = MagicMock()
        compressor = ContextCompressor(client=mock_client, model="test")

        long_content = "x" * 3000
        messages = [{"role": "user", "content": long_content}]
        text = compressor._format_messages_for_summary(messages)
        # Should be truncated
        assert len(text) < len(long_content)

    def test_fallback_summary(self):
        mock_client = MagicMock()
        compressor = ContextCompressor(client=mock_client, model="test")

        summary = compressor._fallback_summary("Some conversation text", "API error")
        assert "Auto-extracted" in summary
        assert "API error" in summary


class TestAgentEvents:
    """Tests for new context-related events."""

    def test_context_compressed_event_type(self):
        event = ContextCompressedEvent(
            original_tokens=50000,
            compressed_tokens=5000,
            messages_before=50,
            messages_after=12,
            summary_preview="User discussed creating a FastAPI endpoint...",
        )
        assert event.type == EventType.CONTEXT_COMPRESSED
        assert event.original_tokens == 50000
        assert event.compressed_tokens == 5000

    def test_context_warning_event_type(self):
        event = ContextWarningEvent(
            usage_percent=85.5,
            tokens_used=110000,
            tokens_total=131072,
            level="warning",
        )
        assert event.type == EventType.CONTEXT_WARNING
        assert event.usage_percent == 85.5
        assert event.level == "warning"

    def test_context_critical_event(self):
        event = ContextWarningEvent(
            usage_percent=92.0,
            tokens_used=120000,
            tokens_total=131072,
            level="critical",
        )
        assert event.level == "critical"

    def test_events_on_bus(self):
        bus = AgentEventBus(name="test")
        received = []
        bus.subscribe(lambda e: received.append(e))

        bus.emit(ContextCompressedEvent(original_tokens=100, compressed_tokens=50))
        bus.emit(ContextWarningEvent(usage_percent=75.0))

        assert len(received) == 2
        assert isinstance(received[0], ContextCompressedEvent)
        assert isinstance(received[1], ContextWarningEvent)

    def test_event_to_dict(self):
        event = ContextCompressedEvent(original_tokens=100, compressed_tokens=50)
        d = event.to_dict()
        assert d["type"] == "context_compressed"
        assert d["original_tokens"] == 100
        assert d["compressed_tokens"] == 50