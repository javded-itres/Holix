from openai import AsyncOpenAI

from core.agent_events import AgentEvent, ErrorEvent, FinalResponseEvent
from core.runtime.executor import run_holix


class AgentLoop:
    """Main agent loop for processing user requests.

    Delegates to the unified event-driven engine in agent_execution.py.
    """

    def __init__(self, agent):
        self.agent = agent
        self.client: AsyncOpenAI = agent.client
        self.model: str = agent.model

    def emit(self, event: AgentEvent) -> None:
        if hasattr(self.agent, "emit"):
            self.agent.emit(event)
        elif hasattr(self.agent, "events"):
            self.agent.events.emit(event)

    async def run_conversation(
        self,
        user_input: str,
        conversation_id: str = "default"
    ) -> str:
        """Run a conversation. Uses the unified generator."""
        final_response = ""
        error_msg = None

        async for event in run_holix(
            self.agent,
            user_input,
            conversation_id,
            stream=False,
        ):
            self.emit(event)

            if isinstance(event, FinalResponseEvent):
                final_response = event.content
            elif isinstance(event, ErrorEvent):
                error_msg = event.error

        if error_msg:
            return error_msg
        return final_response or "Agent completed without producing a final response."


# Note:
# The old self_improve method has been moved into the unified engine.
# Streaming logic now lives in StreamingAgentLoop (which also uses run_agent_loop).
