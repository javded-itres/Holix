"""
Token counting for context management.

Uses tiktoken (required dependency) for accurate token counting
compatible with OpenAI tokenizer formats.
"""

from __future__ import annotations

import tiktoken

DEFAULT_CONTEXT_WINDOW = 131072  # 128k tokens — sensible default for modern models


class TokenCounter:
    """Count tokens in messages and text for context window management.

    Uses tiktoken with cl100k_base encoding (GPT-4 / GPT-4o family).
    Falls back to o200k_base for newer models, or p50k_base for older ones.
    """

    def __init__(self, model: str = ""):
        self._model = model
        self._encoder: tiktoken.Encoding | None = None

    @property
    def encoder(self) -> tiktoken.Encoding:
        """Lazy-initialize the tiktoken encoder."""
        if self._encoder is None:
            try:
                self._encoder = tiktoken.encoding_for_model(self._model)
            except (KeyError, ValueError):
                # Model not in tiktoken's registry — use cl100k_base as default
                # This works well for most OpenAI-compatible models (Qwen, Llama, etc.)
                self._encoder = tiktoken.get_encoding("cl100k_base")
        return self._encoder

    def count_text_tokens(self, text: str) -> int:
        """Count tokens in a plain text string.

        Args:
            text: Text to count tokens in.

        Returns:
            Number of tokens.
        """
        if not text:
            return 0
        try:
            return len(self.encoder.encode(text))
        except Exception:
            # Ultimate fallback: ~4 characters per token
            return len(text) // 4

    def count_message_tokens(self, messages: list[dict]) -> int:
        """Count tokens in a list of OpenAI-format chat messages.

        Uses the OpenAI message format overhead calculation:
        - Each message: ~4 tokens overhead (role, separators)
        - Tool call messages: additional overhead for function name/arguments
        - Total: +3 tokens for message list formatting

        Args:
            messages: List of message dicts with 'role' and 'content' keys.

        Returns:
            Total token count for all messages.
        """
        if not messages:
            return 0

        total = 3  # priming tokens for message list

        for message in messages:
            # Base overhead per message
            total += 4

            # Count tokens in each field
            for key, value in message.items():
                if key == "role":
                    # Role names are very short (1-2 tokens)
                    total += 1
                elif isinstance(value, str):
                    total += self.count_text_tokens(value)
                elif isinstance(value, list):
                    # Tool calls list
                    for item in value:
                        if isinstance(item, dict):
                            # tool_call object: id, type, function.name, function.arguments
                            total += 4  # overhead
                            func = item.get("function", {})
                            if isinstance(func, dict):
                                total += self.count_text_tokens(func.get("name", ""))
                                total += self.count_text_tokens(func.get("arguments", ""))
                            total += self.count_text_tokens(item.get("id", ""))
                elif isinstance(value, dict):
                    # Nested dict (e.g., function call details)
                    for k, v in value.items():
                        if isinstance(v, str):
                            total += self.count_text_tokens(v)

            # If message has 'name' field (named tool responses)
            if "name" in message:
                total += 2

        return total

    @staticmethod
    def format_token_count(tokens: int) -> str:
        """Format a token count for display (e.g., '12k', '128k').

        Args:
            tokens: Number of tokens.

        Returns:
            Human-readable token count string.
        """
        if tokens >= 1_000_000:
            return f"{tokens / 1_000_000:.1f}M"
        elif tokens >= 1000:
            return f"{tokens / 1000:.0f}k"
        else:
            return str(tokens)