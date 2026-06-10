"""
Tool Execution Node — executes tool calls from the graph state.
"""

import logging
import time

from langchain_core.runnables import RunnableConfig

from core.agent_events import ToolCallErrorEvent, ToolCallResultEvent
from core.graph.state import HelixGraphState, get_agent_from_config

logger = logging.getLogger(__name__)


async def tool_execution_node(state: HelixGraphState, config: RunnableConfig) -> dict:
    """Execute pending tool calls and store results.

    Reads tool_calls from state, executes each via the agent's
    ToolRegistry, emits events, and appends tool results to messages.

    Args:
        state: Current graph state with tool_calls.
        config: RunnableConfig with agent at config["configurable"]["_agent"].

    Returns:
        Partial state update with tool_results and updated messages.
    """
    agent = get_agent_from_config(config)
    tool_calls = state.get("tool_calls", [])
    conversation_id = state.get("conversation_id", "default")

    if not tool_calls or not agent:
        return {"tool_calls": [], "tool_results": []}

    messages = list(state.get("messages", []))
    tool_results = []

    for tc_data in tool_calls:
        tool_name = tc_data.get("function", {}).get("name", "")
        tool_id = tc_data.get("id", "")
        tc_data.get("function", {}).get("arguments", "")

        # Create a minimal tool call object compatible with ToolRegistry.execute()
        class _ToolCall:
            def __init__(self, data):
                self.id = data.get("id", "")
                self.type = data.get("type", "function")
                self.function = type("obj", (object,), {
                    "name": data["function"]["name"],
                    "arguments": data["function"]["arguments"],
                })()

        tool_call_obj = _ToolCall(tc_data)

        start = time.time()
        try:
            result = await agent.tools.execute(
                tool_call_obj,
                conversation_id=conversation_id,
                memory=getattr(agent, "memory", None),
            )
            duration = (time.time() - start) * 1000

            if agent and hasattr(agent, "emit"):
                agent.emit(ToolCallResultEvent(
                    tool_name=tool_name,
                    tool_id=tool_id,
                    result=result,
                    duration_ms=duration,
                    conversation_id=conversation_id,
                    truncated=len(result) > 200,
                ))

        except Exception as tool_err:
            duration = (time.time() - start) * 1000
            result = f"Error: {tool_err}"

            if agent and hasattr(agent, "emit"):
                agent.emit(ToolCallErrorEvent(
                    tool_name=tool_name,
                    tool_id=tool_id,
                    error=str(tool_err),
                    conversation_id=conversation_id,
                ))

        # Append tool result message
        tool_msg = {
            "role": "tool",
            "tool_call_id": tool_id,
            "content": result,
        }
        messages.append(tool_msg)
        tool_results.append({
            "tool_name": tool_name,
            "tool_id": tool_id,
            "result": result,
            "duration_ms": duration,
        })

        # Save to memory (truncate huge outputs — full result stays in graph state)
        if agent and hasattr(agent, "memory"):
            from core.memory.tool_content import truncate_tool_content_for_memory

            await agent.memory.save_message(
                conversation_id,
                "tool",
                truncate_tool_content_for_memory(result),
                metadata={"tool_name": tool_name},
            )

    if agent and hasattr(agent, "context_manager") and agent.context_manager:
        from core.runtime.context_session import compress_session_if_needed

        messages, _ = await compress_session_if_needed(
            agent, conversation_id, messages
        )

    return {
        "messages": messages,
        "tool_calls": [],      # Clear pending tool calls
        "tool_results": tool_results,
    }