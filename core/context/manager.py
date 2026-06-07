"""
Context Manager for Helix.

Monitors token usage relative to the model's context window,
emits warnings as usage increases, and automatically compresses
conversation history when usage approaches the limit.
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any, List, Tuple

from core.context.token_counter import TokenCounter, DEFAULT_CONTEXT_WINDOW
from core.context.compressor import ContextCompressor

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
        token_counter: Optional[TokenCounter] = None,
        compressor: Optional[ContextCompressor] = None,
        event_bus: Optional[Any] = None,
        compression_threshold: float = 0.9,
        warning_threshold: float = 0.7,
    ):
        """Initialize the context manager.

        Args:
            context_window: Maximum context window size in tokens.
            token_counter: TokenCounter instance for counting tokens.
            compressor: ContextCompressor instance for compressing history.
            event_bus: Optional AgentEventBus for emitting events.
            compression_threshold: Fraction (0-1) at which auto-compress triggers.
            warning_threshold: Fraction (0-1) at which warnings are emitted.
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

    def update_context_window(self, context_window: int) -> None:
        """Update the context window size (e.g., when switching models).

        Args:
            context_window: New context window size in tokens.
        """
        self.context_window = context_window

    def get_usage(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get current context usage information.

        Args:
            messages: Current conversation messages.

        Returns:
            Dict with keys: used (int), total (int), percent (float),
            messages_count (int), context_window (int).
        """
        used = self.token_counter.count_message_tokens(messages)
        percent = (used / self.context_window * 100) if self.context_window > 0 else 0

        return {
            "used": used,
            "total": self.context_window,
            "percent": round(percent, 1),
            "messages_count": len(messages),
            "context_window": self.context_window,
        }

    def is_near_limit(
        self,
        messages: List[Dict[str, Any]],
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

    def get_usage_level(self, messages: List[Dict[str, Any]]) -> str:
        """Get usage level for color-coding display.

        Args:
            messages: Current conversation messages.

        Returns:
            "green" if < 70%, "yellow" if 70-89%, "red" if >= 90%.
        """
        usage = self.get_usage(messages)
        percent = usage["percent"]

        if percent >= self.compression_threshold * 100:
            return "red"
        elif percent >= self.warning_threshold * 100:
            return "yellow"
        else:
            return "green"

    def format_usage_display(self, messages: List[Dict[str, Any]]) -> str:
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
        messages: List[Dict[str, Any]],
        keep_recent: int = 10,
    ) -> Tuple[List[Dict[str, Any]], bool]:
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

        compressed, summary = await self.compressor.compress(
            messages, keep_recent=keep_recent
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

        return compressed, True

    async def auto_compress_if_needed(
        self,
        messages: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], bool]:
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

    def _emit_warning_event(self, usage: Dict[str, Any], level: str) -> None:
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