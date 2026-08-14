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

# System prompt + tools + HOLIX.md overhead not stored in message history.
DEFAULT_SYSTEM_PROMPT_RESERVE = 4096
_MAX_AUTO_COMPRESS_ROUNDS = 3


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
        compression_threshold: float = 0.85,
        warning_threshold: float = 0.70,
        system_prompt_reserve: int = DEFAULT_SYSTEM_PROMPT_RESERVE,
    ):
        """Initialize the context manager.

        Args:
            context_window: Maximum context window size in tokens.
            token_counter: TokenCounter instance for counting tokens.
            compressor: ContextCompressor instance for compressing history.
            event_bus: Optional AgentEventBus for emitting events.
            compression_threshold: Fraction (0-1) at which auto-compress triggers (default 85%).
            warning_threshold: Fraction (0-1) at which warnings are emitted (default 70%).
            system_prompt_reserve: Estimated tokens for system prompt not in history.
        """
        self.context_window = context_window
        self.token_counter = token_counter or TokenCounter()
        self.compressor = compressor
        self.event_bus = event_bus
        self.compression_threshold = compression_threshold
        self.warning_threshold = warning_threshold
        self.system_prompt_reserve = max(0, int(system_prompt_reserve))

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
        # Count after tool-output caps so a single multi-MB dump cannot report 600%+.
        from core.memory.tool_content import sanitize_messages_tool_content

        messages = sanitize_messages_tool_content(messages)
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
        include_system_reserve: bool = False,
    ) -> dict[str, Any]:
        """Get current context usage information.

        Args:
            messages: Current conversation messages.
            conversation_id: When set, enables incremental token counting cache.
            include_system_reserve: Add estimated system-prompt tokens (for limits).

        Returns:
            Dict with keys: used (int), total (int), percent (float),
            messages_count (int), context_window (int).
        """
        usage = self._build_usage(messages, conversation_id=conversation_id)
        if not include_system_reserve or not self.system_prompt_reserve:
            return usage
        used = int(usage["used"]) + self.system_prompt_reserve
        total = int(usage["total"]) or self.context_window
        percent = (used / total * 100) if total > 0 else 0.0
        return {
            **usage,
            "used": used,
            "percent": round(percent, 1),
            "system_reserve": self.system_prompt_reserve,
        }

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

    def _adaptive_keep_recent(self, messages: list[dict[str, Any]]) -> int:
        """Keep recent messages that fit ~25% of the context window."""
        target = max(512, int(self.context_window * 0.25))
        kept = 0
        tokens = 0
        for msg in reversed(messages):
            msg_tokens = self.token_counter.count_message_tokens([msg])
            if kept >= 2 and tokens + msg_tokens > target:
                break
            tokens += msg_tokens
            kept += 1
        return max(2, min(kept, 10))

    async def compress_context(
        self,
        messages: list[dict[str, Any]],
        keep_recent: int | None = None,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Compress conversation context manually.

        Args:
            messages: Current conversation messages.
            keep_recent: Number of recent messages to keep intact.

        Returns:
            Tuple of (compressed_messages, was_compressed).
        """
        from core.memory.tool_content import sanitize_messages_tool_content
        from core.profile.soul import strip_soul_messages

        # Drop multi-MB tool payloads before keep-recent / summarization.
        original = messages
        messages = sanitize_messages_tool_content(messages)
        sanitized_only = messages is not original

        if not self.compressor:
            logger.warning("ContextCompressor not available — cannot compress")
            return messages, sanitized_only

        keep = keep_recent if keep_recent is not None else self._adaptive_keep_recent(messages)
        if len(messages) <= keep:
            # Short session with a runaway tool dump: capping alone is the fix.
            return messages, sanitized_only

        tokens_before = self.token_counter.count_message_tokens(messages)

        to_compress = strip_soul_messages(messages)
        compressed, summary = await self.compressor.compress(to_compress, keep_recent=keep)

        if not summary.strip():
            return messages, False

        tokens_after = self.token_counter.count_message_tokens(compressed)
        if tokens_after >= tokens_before:
            logger.warning(
                "Context compression did not reduce tokens (%s → %s); skipping",
                tokens_before,
                tokens_after,
            )
            return messages, False

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
        *,
        conversation_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Automatically compress context if usage exceeds threshold.

        Also emits warning events at the warning threshold (70%).

        Args:
            messages: Current conversation messages.
            conversation_id: Cache key for token counting.

        Returns:
            Tuple of (messages, was_compressed).
        """
        from core.memory.tool_content import sanitize_messages_tool_content

        original = messages
        current = sanitize_messages_tool_content(messages)
        any_compressed = current is not original

        for round_idx in range(_MAX_AUTO_COMPRESS_ROUNDS):
            usage = self.get_usage(
                current,
                conversation_id=conversation_id,
                include_system_reserve=True,
            )
            percent = usage["percent"]

            if (
                percent >= self.warning_threshold * 100
                and percent < self.compression_threshold * 100
            ):
                self._emit_warning_event(usage, level="warning")
                break

            if percent < self.compression_threshold * 100:
                break

            self._emit_warning_event(usage, level="critical")
            compressed, was_compressed = await self.compress_context(current)
            if not was_compressed:
                break
            current = compressed
            any_compressed = True
            self.invalidate_usage_cache(conversation_id)

            if round_idx + 1 < _MAX_AUTO_COMPRESS_ROUNDS:
                follow_up = self.get_usage(
                    current,
                    conversation_id=conversation_id,
                    include_system_reserve=True,
                )
                if follow_up["percent"] < self.compression_threshold * 100:
                    break

        return current, any_compressed

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

            self.event_bus.emit(
                ContextCompressedEvent(
                    original_tokens=tokens_before,
                    compressed_tokens=tokens_after,
                    messages_before=messages_before,
                    messages_after=messages_after,
                    summary_preview=summary_preview,
                )
            )
        except Exception as e:
            logger.warning(f"Failed to emit ContextCompressedEvent: {e}")

    def _emit_warning_event(self, usage: dict[str, Any], level: str) -> None:
        """Emit a ContextWarningEvent if an event bus is available."""
        if not self.event_bus:
            return

        try:
            from core.agent_events import ContextWarningEvent

            self.event_bus.emit(
                ContextWarningEvent(
                    usage_percent=usage["percent"],
                    tokens_used=usage["used"],
                    tokens_total=usage["total"],
                    level=level,
                )
            )
        except Exception as e:
            logger.warning(f"Failed to emit ContextWarningEvent: {e}")
