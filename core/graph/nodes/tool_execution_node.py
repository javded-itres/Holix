"""
Tool Execution Node — executes tool calls from the graph state.
"""

import asyncio
import logging
import time

from langchain_core.runnables import RunnableConfig

from core.agent_events import ToolCallErrorEvent, ToolCallResultEvent
from core.graph.state import HolixGraphState, get_agent_from_config

logger = logging.getLogger(__name__)


def _append_todo_reminder(messages: list, agent: object, conversation_id: str) -> None:
    """Ask the model to refresh an open checklist it has stopped updating."""
    try:
        from core.profile.soul import profile_name_from_agent
        from core.runtime.todo_list import get_todos, todo_reminder_text

        profile = profile_name_from_agent(agent) if agent else "default"
        text = todo_reminder_text(messages, get_todos(profile, str(conversation_id or "default")))
        if text:
            messages.append({"role": "user", "content": text})
    except Exception:
        logger.debug("todo reminder skipped", exc_info=True)


async def tool_execution_node(state: HolixGraphState, config: RunnableConfig) -> dict:
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

    from core.memory.tool_content import (
        truncate_tool_content_for_graph,
        truncate_tool_content_for_memory,
    )

    messages = list(state.get("messages", []))
    tool_results = []

    async def _execute_one(tc_data: dict) -> dict:
        tool_name = tc_data.get("function", {}).get("name", "")
        tool_id = tc_data.get("id", "")

        class _ToolCall:
            def __init__(self, data):
                self.id = data.get("id", "")
                self.type = data.get("type", "function")
                self.function = type(
                    "obj",
                    (object,),
                    {
                        "name": data["function"]["name"],
                        "arguments": data["function"]["arguments"],
                    },
                )()

        from core.runtime.turn_steer import SteerInterrupt
        from core.tools.execution_context import agent_slot_scope, reset_agent_slot_scope

        start = time.time()
        slot_token = None
        cancelled = False
        steered = False
        try:
            slot_token = agent_slot_scope(getattr(agent, "agent_slot", "main") or "main")
            result = await agent.tools.execute(
                _ToolCall(tc_data),
                conversation_id=conversation_id,
                memory=getattr(agent, "memory", None),
            )
            duration = (time.time() - start) * 1000
            if agent and hasattr(agent, "emit"):
                agent.emit(
                    ToolCallResultEvent(
                        tool_name=tool_name,
                        tool_id=tool_id,
                        result=result,
                        duration_ms=duration,
                        conversation_id=conversation_id,
                        truncated=len(result) > 200,
                    )
                )
        except asyncio.CancelledError:
            duration = (time.time() - start) * 1000
            result = "Error: Run cancelled — tool not executed."
            cancelled = True
            if agent and hasattr(agent, "emit"):
                agent.emit(
                    ToolCallErrorEvent(
                        tool_name=tool_name,
                        tool_id=tool_id,
                        error="cancelled",
                        conversation_id=conversation_id,
                    )
                )
        except Exception as tool_err:
            duration = (time.time() - start) * 1000
            if isinstance(tool_err, SteerInterrupt):
                result = "Interrupted: a new instruction arrived before this tool finished."
                steered = True
                if agent and hasattr(agent, "emit"):
                    agent.emit(
                        ToolCallErrorEvent(
                            tool_name=tool_name,
                            tool_id=tool_id,
                            error="interrupted",
                            conversation_id=conversation_id,
                        )
                    )
            else:
                result = f"Error: {tool_err}"
                if agent and hasattr(agent, "emit"):
                    agent.emit(
                        ToolCallErrorEvent(
                            tool_name=tool_name,
                            tool_id=tool_id,
                            error=str(tool_err),
                            conversation_id=conversation_id,
                        )
                    )
        finally:
            if slot_token is not None:
                reset_agent_slot_scope(slot_token)
        return {
            "tool_name": tool_name,
            "tool_id": tool_id,
            "result": result,
            "graph_result": truncate_tool_content_for_graph(result),
            "duration_ms": duration,
            "cancelled": cancelled,
            "steered": steered,
        }

    def _skipped(tc_data: dict, text: str, *, cancelled: bool = False) -> dict:
        return {
            "tool_name": tc_data.get("function", {}).get("name", ""),
            "tool_id": tc_data.get("id", ""),
            "result": text,
            "graph_result": text,
            "duration_ms": 0,
            "cancelled": cancelled,
            "steered": not cancelled,
        }

    async def _drop_remaining(start: int, text: str, *, cancelled: bool) -> None:
        for pending in tool_calls[start:]:
            skipped = _skipped(pending, text, cancelled=cancelled)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": skipped["tool_id"],
                    "content": skipped["graph_result"],
                }
            )
            tool_results.append(skipped)
            if cancelled or not agent or not hasattr(agent, "memory"):
                continue
            await agent.memory.save_message(
                conversation_id,
                "tool",
                truncate_tool_content_for_memory(skipped["result"]),
                metadata={"tool_name": skipped["tool_name"]},
            )

    cancelled_run = False
    guard = getattr(getattr(agent, "tools", None), "_action_guard", None)
    if guard is None:
        from core.graph.nodes.tool_batches import group_tool_calls

        groups = group_tool_calls(agent, tool_calls)
    else:
        groups = [[tc] for tc in tool_calls]

    flat_index = 0
    for group in groups:
        from core.runtime.turn_steer import absorb_steer, steer_requested
        from core.tools.execution_context import is_run_cancelled

        if is_run_cancelled():
            cancelled_run = True
            await _drop_remaining(
                flat_index,
                "Error: Run cancelled — tool not executed.",
                cancelled=True,
            )
            break
        if steer_requested():
            await _drop_remaining(
                flat_index,
                "Interrupted: a new instruction arrived — tool not executed.",
                cancelled=False,
            )
            await absorb_steer(messages, agent, conversation_id)
            break

        if len(group) > 1:
            outcomes = await asyncio.gather(*[_execute_one(tc) for tc in group])
        else:
            outcomes = [await _execute_one(group[0])]

        stop_after = False
        for outcome in outcomes:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": outcome["tool_id"],
                    "content": outcome["graph_result"],
                }
            )
            tool_results.append(outcome)
            if outcome["cancelled"]:
                cancelled_run = True
                stop_after = True
            if not outcome["cancelled"] and agent and hasattr(agent, "memory"):
                await agent.memory.save_message(
                    conversation_id,
                    "tool",
                    truncate_tool_content_for_memory(outcome["result"]),
                    metadata={"tool_name": outcome["tool_name"]},
                )
            if outcome["steered"]:
                stop_after = True
        flat_index += len(group)
        if not (cancelled_run or stop_after or steer_requested()):
            continue
        await _drop_remaining(
            flat_index,
            (
                "Error: Run cancelled — tool not executed."
                if cancelled_run
                else "Interrupted: a new instruction arrived — tool not executed."
            ),
            cancelled=cancelled_run,
        )
        if not cancelled_run:
            await absorb_steer(messages, agent, conversation_id)
        break

    if not cancelled_run:
        _append_todo_reminder(messages, agent, conversation_id)

    if agent and hasattr(agent, "context_manager") and agent.context_manager:
        from core.runtime.context_session import compress_session_if_needed

        messages, _ = await compress_session_if_needed(agent, conversation_id, messages)

    out = {
        "messages": messages,
        "tool_calls": [],  # Clear pending tool calls
        "tool_results": tool_results,
    }
    if cancelled_run:
        stopped = "Stopped."
        if agent and hasattr(agent, "emit"):
            from core.agent_events import FinalResponseEvent

            agent.emit(
                FinalResponseEvent(
                    content=stopped,
                    steps_taken=int(state.get("step_count") or 0),
                    conversation_id=conversation_id,
                )
            )
        out["is_final"] = True
        out["final_response"] = stopped
    return out
