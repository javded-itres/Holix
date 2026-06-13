"""
Context compression module for Holix.

Uses the LLM to intelligently summarize conversation history,
preserving key facts, decisions, artifacts, and goals while
dramatically reducing token usage.
"""

from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from core.context.token_counter import TokenCounter
from core.profile.soul import is_soul_message

# System prompt for the compression LLM call
_COMPRESSION_PROMPT = """You are a conversation summarizer. Your task is to create a concise but complete summary of a conversation history.

Focus on preserving:
1. **Key facts and decisions** — what was established, agreed upon, or decided
2. **Created artifacts** — files created, code written, configurations changed (include file paths and brief descriptions)
3. **Current goal/task** — what the user is trying to accomplish right now
4. **Tool results** — important outputs from tool calls (file contents, command outputs, search results)
5. **Context the user provided** — preferences, constraints, requirements mentioned

Discard:
- Greetings and pleasantries
- Intermediate reasoning that led to a final answer
- Redundant information
- Verbose tool outputs that aren't critical for future context

Format your summary as a structured list of bullet points. Be specific — include file names, paths, values, not vague descriptions.

Example format:
- **Goal**: User wants to create a FastAPI endpoint for user registration
- **Decision**: Using SQLite for storage instead of PostgreSQL
- **Created**: `api/routes/users.py` — POST /register endpoint with validation
- **Created**: `api/models.py` — UserCreate and UserResponse Pydantic models
- **Context**: User prefers async code, project uses uvicorn
- **Key fact**: API key is stored in settings.API_KEY
"""


class ContextCompressor:
    """Compress conversation history using LLM summarization.

    Takes a list of messages, keeps the most recent ones intact,
    and summarizes the rest into a single system message.
    """

    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        token_counter: TokenCounter | None = None,
    ):
        self.client = client
        self.model = model
        self.token_counter = token_counter or TokenCounter(model=model)

    async def compress(
        self,
        messages: list[dict[str, Any]],
        keep_recent: int = 10,
    ) -> tuple[list[dict[str, Any]], str]:
        """Compress conversation history by summarizing older messages.

        Args:
            messages: Full conversation message list.
            keep_recent: Number of recent messages to keep intact (default 10).

        Returns:
            Tuple of (compressed_messages, summary_text).
            compressed_messages format:
                [system_msg_with_summary] + messages[-keep_recent:]
        """
        from core.profile.soul import strip_soul_messages

        soul_safe = strip_soul_messages(messages)
        if len(soul_safe) <= keep_recent:
            return messages, ""

        older_messages = soul_safe[:-keep_recent]
        recent_messages = soul_safe[-keep_recent:]

        # Build text representation of older messages for summarization
        conversation_text = self._format_messages_for_summary(older_messages)

        if not conversation_text.strip():
            return messages, ""

        # Call LLM for summarization
        summary = await self._generate_summary(conversation_text)

        # Build the compressed message list
        summary_message = {
            "role": "system",
            "content": f"Context compressed. Summary of previous conversation:\n\n{summary}",
        }

        compressed = [summary_message] + recent_messages
        return compressed, summary

    async def _generate_summary(self, conversation_text: str) -> str:
        """Use LLM to generate a summary of conversation text.

        Args:
            conversation_text: Formatted conversation text to summarize.

        Returns:
            Summary text.
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": _COMPRESSION_PROMPT},
                    {"role": "user", "content": f"Summarize this conversation:\n\n{conversation_text}"},
                ],
                temperature=0.3,  # Low temperature for consistent summaries
            )
            return response.choices[0].message.content or "Summary unavailable."

        except Exception as e:
            # If LLM summarization fails, create a basic extractive summary
            return self._fallback_summary(conversation_text, str(e))

    def _fallback_summary(self, conversation_text: str, error: str) -> str:
        """Create a basic summary when LLM summarization fails.

        Takes first 2000 characters of conversation as a rough summary.

        Args:
            conversation_text: Formatted conversation text.
            error: Error message from the failed LLM call.

        Returns:
            Fallback summary text.
        """
        truncated = conversation_text[:2000]
        return (
            f"[Auto-extracted summary — LLM summarization failed: {error}]\n\n"
            f"Key conversation excerpts:\n{truncated}..."
        )

    def _format_messages_for_summary(self, messages: list[dict[str, Any]]) -> str:
        """Format messages into a text representation suitable for summarization.

        Args:
            messages: List of message dicts.

        Returns:
            Formatted text representation.
        """
        parts = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            if not content:
                continue

            # Truncate very long individual messages
            max_content_len = 2000
            if len(content) > max_content_len:
                content = content[:max_content_len] + "..."

            if role == "user":
                parts.append(f"USER: {content}")
            elif role == "assistant":
                parts.append(f"ASSISTANT: {content}")
            elif role == "tool":
                tool_name = ""
                metadata = msg.get("metadata", {})
                if isinstance(metadata, dict):
                    tool_name = metadata.get("tool_name", "")
                prefix = f"TOOL ({tool_name}): " if tool_name else "TOOL: "
                # Tool results are often very long — truncate more aggressively
                truncated = content[:500] + "..." if len(content) > 500 else content
                parts.append(f"{prefix}{truncated}")
            elif role == "system":
                if is_soul_message(msg):
                    parts.append(f"AGENT_SOUL (pinned identity): {content[:1500]}")
                else:
                    parts.append(f"SYSTEM: {content}")

        return "\n\n".join(parts)