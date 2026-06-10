import json
import logging
from collections.abc import AsyncGenerator

from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)

# Import the unified execution engine (Variant B)
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
        conversation_id: str = "default"
    ) -> AsyncGenerator[str, None]:
        """
        Streaming version of the agent loop.

        Now consumes the unified `_run_agent_loop` generator (Variant B).
        This eliminates massive duplication and makes behavior consistent
        between classic and streaming modes.

        For now we translate new AgentEvents back to the legacy SSE format
        so the API Gateway remains backward compatible.
        """
        try:
            async for event in run_helix(
                self.agent,
                user_input,
                conversation_id,
                stream=True,
            ):
                if isinstance(event, AssistantDeltaEvent):
                    # Real token-by-token streaming!
                    yield f"data: {json.dumps({'type': 'content', 'content': event.content})}\n\n"

                elif isinstance(event, ToolCallStartEvent):
                    yield f"data: {json.dumps({'type': 'tool_call', 'tool': event.tool_name})}\n\n"

                elif isinstance(event, ToolCallResultEvent):
                    yield f"data: {json.dumps({'type': 'tool_result', 'tool': event.tool_name, 'result': event.result[:200]})}\n\n"

                elif isinstance(event, FinalResponseEvent):
                    # Final done signal (content was already streamed via deltas)
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    return

                elif isinstance(event, ErrorEvent):
                    yield f"data: {json.dumps({'type': 'error', 'message': event.error})}\n\n"
                    return

                elif isinstance(event, MaxStepsReachedEvent):
                    yield f"data: {json.dumps({'type': 'error', 'message': f'Agent reached maximum steps ({event.max_steps})'})}\n\n"
                    return

        except Exception as e:
            logger.exception("Streaming agent loop failed")
            message = str(e) if settings.log_debug_enabled else "Internal server error"
            yield f"data: {json.dumps({'type': 'error', 'message': message})}\n\n"
