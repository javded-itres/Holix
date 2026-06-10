"""Conversation summarization (statistical fallback + episodic persistence)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from openai import AsyncOpenAI

if TYPE_CHECKING:
    from core.memory.conversation import ConversationStore
    from core.memory.ltm import LongTermMemoryStore


class ConversationSummarizer:
    """Summarize conversations and optionally store episodic memories."""

    @staticmethod
    def statistical_summary(messages: list[dict[str, Any]]) -> str:
        if not messages:
            return "No conversation history."

        user_msgs = [m for m in messages if m.get("role") == "user"]
        assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
        tool_msgs = [m for m in messages if m.get("role") == "tool"]

        lines = [
            "Conversation summary:",
            f"- Total messages: {len(messages)}",
            f"- User messages: {len(user_msgs)}",
            f"- Assistant messages: {len(assistant_msgs)}",
        ]
        if tool_msgs:
            lines.append(f"- Tool messages: {len(tool_msgs)}")
        return "\n".join(lines)

    async def summarize_conversation(
        self,
        store: ConversationStore,
        conversation_id: str,
        llm_client: Any = None,
    ) -> str:
        messages = await store.get_conversation(conversation_id, limit=100)
        summary = self.statistical_summary(messages)
        if llm_client:
            # LLM-based summarization can be added here
            pass
        return summary

    async def auto_summarize(
        self,
        ltm: LongTermMemoryStore,
        conversation_id: str,
        messages: list[dict[str, Any]],
        llm_client: AsyncOpenAI | None = None,
        model: str = "",
    ) -> str | None:
        if not llm_client:
            user_msgs = [m for m in messages if m.get("role") == "user"]
            tool_msgs = [m for m in messages if m.get("role") == "tool"]
            summary = (
                f"Conversation with {len(user_msgs)} user messages and "
                f"{len(tool_msgs)} tool calls."
            )
            await ltm.episodic.store_episode(
                conversation_id=conversation_id,
                summary=summary,
                outcome="partial",
                metadata={"auto_generated": True, "fallback": True},
            )
            return summary

        return await ltm.episodic.auto_summarize_conversation(
            conversation_id=conversation_id,
            messages=messages,
            llm_client=llm_client,
            model=model,
        )