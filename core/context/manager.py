"""
Context Manager for Holix.

Monitors token usage relative to the model's context window,
emits warnings as usage increases, and automatically compresses
conversation history when usage approaches the limit.
"""

from __future__ import annotations

import logging
from typing import Any

from core.context.compressor import ContextCompressor
from core.context.token_counter import DEFAULT_CONTEXT_WINDOW, TokenCounter

logger = logging.getLogger(__name__)


class ContextManager:
    """Manage conversation context window usage and automatic compression.

    Responsibilities:
    - Track token usage vs. context window size
    - Warn when usage exceeds thresholds (70% warning, 90% critical)
    - Automatically compress context when critical threshold is reached
    - Provide formatted usage display for UI
    """

    def __init__(
        self,
        context_window: int = DEFAULT_CONTEXT_WINDOW,
        token_counter: TokenCounter | None = None,
        compressor: ContextCompressor | None = None,
        event_bus: Any | None = None,
        compression_threshold: float = 0.95,
        warning_threshold: float = 0.8,
    ):
        """Initialize the context manager.

        Args:
            context_window: Maximum context window size in tokens.
            token_counter: TokenCounter instance for counting tokens.
            compressor: ContextCompressor instance for compressing history.
            event_bus: Optional AgentEventBus for emitting events.
            compression_threshold: Fraction (0-1) at which auto-compress triggers (default 95%).
            warning_threshold: Fraction (0-1) at which warnings are emitted (default 80%).
        """
        self.context_window = context_window
        self.token_counter = token_counter or TokenCounter()
        self.compressor = compressor
        self.event_bus = event_bus
        self.compression_threshold = compression_threshold
        self.warning_threshold = warning_threshold

        # Track last compression result
        self.last_summary: str = ""
        self._last_compression_tokens_before: int = 0
        self._last_compression_tokens_after: int = 0

        # Per-conversation token usage cache (incremental append, full recount on compress)
        self._usage_cache: dict[str, dict[str, Any]] = {}

    def update_context_window(self, context_window: int) -> None:
        """Update the context window size (e.g., when switching models).

        Args:
            context_window: New context window size in tokens.
        """
        self.context_window = context_window

    def invalidate_usage_cache(self, conversation_id: str | None = None) -> None:
        """Drop cached token counts (e.g. after compression or session switch)."""
        if conversation_id is None:
            self._usage_cache.clear()
        else:
            self._usage_cache.pop(conversation_id, None)

    def _resolve_used_tokens(
        self,
        messages: list[dict[str, Any]],
        *,
        conversation_id: str | None = None,
    ) -> int:
        if not messages:
            return 0
        if not conversation_id:
            return self.token_counter.count_message_tokens(messages)

        cached = self._usage_cache.get(conversation_id)
        count = len(messages)
        if cached and cached.get("count") == count:
            return int(cached["used"])

        if cached and cached.get("count", 0) < count:
            prefix_count = int(cached["count"])
            prefix = messages[:prefix_count]
            prefix_used = self.token_counter.count_message_tokens(prefix)
            if prefix_used == int(cached.get("prefix_used", -1)):
                tail = messages[prefix_count:]
                tail_used = self.token_counter.count_message_tokens(tail)
                # count_message_tokens adds list priming (+3); skip when appending to a prefix.
                if tail:
                    tail_used = max(0, tail_used - 3)
                return prefix_used + tail_used

        return self.token_counter.count_message_tokens(messages)

    def _build_usage(
        self,
        messages: list[dict[str, Any]],
        *,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        used = self._resolve_used_tokens(messages, conversation_id=conversation_id)
        percent = (used / self.context_window * 100) if self.context_window > 0 else 0
        usage = {
            "used": used,
            "total": self.context_window,
            "percent": round(percent, 1),
            "messages_count": len(messages),
            "context_window": self.context_window,
        }
        if conversation_id is not None:
            self._usage_cache[conversation_id] = {
                "count": len(messages),
                "used": used,
                "prefix_used": used,
                "usage": usage,
            }
        return usage

    def get_usage(
        self,
        messages: list[dict[str, Any]],
        *,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        """Get current context usage information.

        Args:
            messages: Current conversation messages.
            conversation_id: When set, enables incremental token counting cache.

        Returns:
            Dict with keys: used (int), total (int), percent (float),
            messages_count (int), context_window (int).
        """
        return self._build_usage(messages, conversation_id=conversation_id)

    def is_near_limit(
        self,
        messages: list[dict[str, Any]],
        threshold: float = 0.9,
    ) -> bool:
        """Check if context usage is near the limit.

        Args:
            messages: Current conversation messages.
            threshold: Fraction (0-1) of context window usage.

        Returns:
            True if usage exceeds the threshold.
        """
        usage = self.get_usage(messages)
        return usage["percent"] >= threshold * 100

    def get_usage_level(
        self,
        messages: list[dict[str, Any]],
        *,
        conversation_id: str | None = None,
        usage: dict[str, Any] | None = None,
    ) -> str:
        """Get usage level for color-coding display.

        Args:
            messages: Current conversation messages.
            conversation_id: Optional cache key (see get_usage).
            usage: Precomputed usage dict to avoid duplicate work.

        Returns:
            "green" if below warning threshold, "yellow" if warning–compress band, "red" if >= compress threshold.
        """
        if usage is None:
            usage = self.get_usage(messages, conversation_id=conversation_id)
        percent = usage["percent"]

        if percent >= self.compression_threshold * 100:
            return "red"
        elif percent >= self.warning_threshold * 100:
            return "yellow"
        else:
            return "green"

    def format_usage_display(self, messages: list[dict[str, Any]]) -> str:
        """Format usage for display in UI (e.g., '12k/128k (9%)').

        Args:
            messages: Current conversation messages.

        Returns:
            Human-readable usage string.
        """
        usage = self.get_usage(messages)
        used_str = TokenCounter.format_token_count(usage["used"])
        total_str = TokenCounter.format_token_count(usage["total"])
        return f"{used_str}/{total_str} ({usage['percent']:.0f}%)"

    async def compress_context(
        self,
        messages: list[dict[str, Any]],
        keep_recent: int = 10,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Compress conversation context manually.

        Args:
            messages: Current conversation messages.
            keep_recent: Number of recent messages to keep intact.

        Returns:
            Tuple of (compressed_messages, was_compressed).
        """
        if not self.compressor:
            logger.warning("ContextCompressor not available — cannot compress")
            return messages, False

        if len(messages) <= keep_recent:
            return messages, False

        tokens_before = self.token_counter.count_message_tokens(messages)

        from core.profile.soul import strip_soul_messages

        to_compress = strip_soul_messages(messages)
        compressed, summary = await self.compressor.compress(
            to_compress, keep_recent=keep_recent
        )

        tokens_after = self.token_counter.count_message_tokens(compressed)

        # Track compression result
        self.last_summary = summary
        self._last_compression_tokens_before = tokens_before
        self._last_compression_tokens_after = tokens_after

        # Emit event
        self._emit_compressed_event(
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            messages_before=len(messages),
            messages_after=len(compressed),
            summary_preview=summary[:200],
        )

        logger.info(
            f"Context compressed: {tokens_before} → {tokens_after} tokens "
            f"({len(messages)} → {len(compressed)} messages)"
        )

        self.invalidate_usage_cache()

        return compressed, True

    async def auto_compress_if_needed(
        self,
        messages: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], bool]:
        """Automatically compress context if usage exceeds threshold.

        Also emits warning events at the warning threshold (70%).

        Args:
            messages: Current conversation messages.

        Returns:
            Tuple of (messages, was_compressed).
        """
        usage = self.get_usage(messages)
        percent = usage["percent"]

        # Emit warning at warning threshold
        if percent >= self.warning_threshold * 100 and percent < self.compression_threshold * 100:
            self._emit_warning_event(usage, level="warning")

        # Auto-compress at compression threshold
        if percent >= self.compression_threshold * 100:
            self._emit_warning_event(usage, level="critical")
            return await self.compress_context(messages)

        return messages, False

    def _emit_compressed_event(
        self,
        tokens_before: int,
        tokens_after: int,
        messages_before: int,
        messages_after: int,
        summary_preview: str = "",
    ) -> None:
        """Emit a ContextCompressedEvent if an event bus is available."""
        if not self.event_bus:
            return

        try:
            from core.agent_events import ContextCompressedEvent

            self.event_bus.emit(ContextCompressedEvent(
                original_tokens=tokens_before,
                compressed_tokens=tokens_after,
                messages_before=messages_before,
                messages_after=messages_after,
                summary_preview=summary_preview,
            ))
        except Exception as e:
            logger.warning(f"Failed to emit ContextCompressedEvent: {e}")

    def _emit_warning_event(self, usage: dict[str, Any], level: str) -> None:
        """Emit a ContextWarningEvent if an event bus is available."""
        if not self.event_bus:
            return

        try:
            from core.agent_events import ContextWarningEvent

            self.event_bus.emit(ContextWarningEvent(
                usage_percent=usage["percent"],
                tokens_used=usage["used"],
                tokens_total=usage["total"],
                level=level,
            ))
        except Exception as e:
            logger.warning(f"Failed to emit ContextWarningEvent: {e}")