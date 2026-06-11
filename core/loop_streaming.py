import logging
from collections.abc import AsyncGenerator

from api.services.hermes_sse import (
    assistant_delta,
    hermes_tool_progress,
    run_completed,
    sse_data,
    tool_completed,
    tool_started,
)
from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)

from core.agent_events import (
    AssistantDeltaEvent,
    ErrorEvent,
    FinalResponseEvent,
    MaxStepsReachedEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from core.runtime.executor import run_helix


class StreamingAgentLoop:
    """Streaming version of agent loop for real-time responses."""

    def __init__(self, agent):
        """Initialize the streaming agent loop.

        Args:
            agent: Parent agent instance
        """
        self.agent = agent
        self.client: AsyncOpenAI = agent.client
        self.model: str = agent.model

    async def run_conversation_stream(
        self,
        user_input: str,
        conversation_id: str = "default",
    ) -> AsyncGenerator[str, None]:
        """
        Streaming version of the agent loop.

        Emits legacy Helix chunks plus Hermes-compatible SSE events.
        """
        try:
            async for event in run_helix(
                self.agent,
                user_input,
                conversation_id,
                stream=True,
            ):
                if isinstance(event, AssistantDeltaEvent):
                    yield sse_data({"type": "content", "content": event.content})
                    yield assistant_delta(event.content)

                elif isinstance(event, ToolCallStartEvent):
                    yield sse_data({"type": "tool_call", "tool": event.tool_name})
                    yield tool_started(event.tool_name)
                    yield hermes_tool_progress(event.tool_name)

                elif isinstance(event, ToolCallResultEvent):
                    preview = event.result[:200]
                    yield sse_data({
                        "type": "tool_result",
                        "tool": event.tool_name,
                        "result": preview,
                    })
                    yield tool_completed(event.tool_name, result_preview=preview)

                elif isinstance(event, FinalResponseEvent):
                    yield sse_data({"type": "done"})
                    yield run_completed()
                    return

                elif isinstance(event, ErrorEvent):
                    yield sse_data({"type": "error", "message": event.error})
                    return

                elif isinstance(event, MaxStepsReachedEvent):
                    yield sse_data({
                        "type": "error",
                        "message": f"Agent reached maximum steps ({event.max_steps})",
                    })
                    return

        except Exception as e:
            logger.exception("Streaming agent loop failed")
            message = str(e) if settings.log_debug_enabled else "Internal server error"
            yield sse_data({"type": "error", "message": message})