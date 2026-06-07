"""
ReAct Node — core reasoning node for the Helix LangGraph.

Calls the LLM, processes the response, and either sets tool_calls
or sets is_final + final_response. Emits AgentEvent objects to
the event bus as side effects.
"""

import time
import logging
from typing import Any, Dict, List

from openai import AsyncOpenAI

from core.graph.state import HelixGraphState, get_agent_from_config
from langchain_core.runnables import RunnableConfig
from core.agent_events import (
    ThinkingEvent,
    ToolCallStartEvent,
    AssistantDeltaEvent,
    FinalResponseEvent,
)
from core.prompt_builder import build_system_prompt, format_tools_description

logger = logging.getLogger(__name__)


async def react_node(state: HelixGraphState, config: RunnableConfig) -> dict:
    """ReAct reasoning node: call LLM, decide next action.

    This is a direct translation of the reasoning step from
    run_agent_loop() into a graph node. It:
    1. Increments step_count
    2. Builds the system prompt with memories/skills/strategies
    3. Calls the LLM (streaming or non-streaming)
    4. If tool_calls → returns partial state with tool_calls
    5. If final answer → returns is_final=True + final_response

    Args:
        state: Current graph state.
        config: RunnableConfig with agent at config["configurable"]["_agent"].

    Returns:
        Partial state update.
    """
    agent = get_agent_from_config(config)
    step_count = state.get("step_count", 0) + 1
    conversation_id = state.get("conversation_id", "default")
    stream = state.get("stream", False)

    # Emit thinking event
    if agent and hasattr(agent, "emit"):
        agent.emit(ThinkingEvent(
            message=f"Thinking (step {step_count})...",
            conversation_id=conversation_id,
        ))

    # Build system prompt from state
    system_prompt = _build_system_prompt_from_state(state, agent=agent)

    # Build API messages
    messages = state.get("messages", [])
    if agent and hasattr(agent, "context_manager") and agent.context_manager:
        api_messages = _build_api_messages(system_prompt, messages, agent.context_manager)
    else:
        api_messages = [{"role": "system", "content": system_prompt}] + messages[-20:]

    # Get runtime config
    client: AsyncOpenAI = agent.client if agent else None
    model = getattr(agent, "model", None) if agent else None
    if not model:
        return {
            "step_count": step_count,
            "is_final": True,
            "final_response": "Error: No LLM model configured",
        }
    tools = agent.tools.get_schemas() if agent and hasattr(agent, "tools") else []
    temperature = 0.7
    if agent and hasattr(agent, "config"):
        temperature = getattr(agent.config, "temperature", 0.7)

    if not client:
        return {
            "step_count": step_count,
            "is_final": True,
            "final_response": "Error: No LLM client available",
        }

    try:
        if stream:
            return await _react_streaming(state, agent, api_messages, step_count, client, model, tools, temperature)
        else:
            return await _react_non_streaming(state, agent, api_messages, step_count, client, model, tools, temperature)

    except Exception as e:
        logger.error(f"Error in react_node: {e}")
        return {
            "step_count": step_count,
            "is_final": True,
            "final_response": f"Error during agent step: {str(e)}",
        }


async def _react_non_streaming(
    state, agent, api_messages, step_count, client, model, tools, temperature
) -> dict:
    """Non-streaming ReAct step."""
    conversation_id = state.get("conversation_id", "default")

    response = await client.chat.completions.create(
        model=model,
        messages=api_messages,
        tools=tools,
        tool_choice="auto",
        temperature=temperature,
    )

    message = response.choices[0].message
    messages = list(state.get("messages", []))

    msg_dict = {"role": "assistant", "content": message.content or ""}

    if message.tool_calls:
        # Tool calls requested
        tool_calls = [
            {
                "id": tc.id,
                "type": tc.type,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in message.tool_calls
        ]
        msg_dict["tool_calls"] = tool_calls
        messages.append(msg_dict)

        # Emit tool call start events
        for tc in message.tool_calls:
            if agent and hasattr(agent, "emit"):
                agent.emit(ToolCallStartEvent(
                    tool_name=tc.function.name,
                    tool_id=tc.id,
                    arguments_raw=tc.function.arguments,
                    conversation_id=conversation_id,
                ))

        return {
            "messages": messages,
            "tool_calls": tool_calls,
            "step_count": step_count,
            "is_final": False,
        }
    else:
        # Final answer
        final_response = message.content or "No response generated"
        messages.append(msg_dict)

        # Save to memory
        if agent and hasattr(agent, "memory"):
            await agent.memory.save_message(conversation_id, "assistant", final_response)

        # Check if we're in plan_and_execute mode with active steps
        plan_steps = state.get("plan_steps", [])
        current_plan_step = state.get("current_plan_step", 0)
        has_active_plan = bool(plan_steps) and current_plan_step < len(plan_steps)

        if has_active_plan:
            # In plan mode: the step is complete, not the entire conversation
            return {
                "messages": messages,
                "step_count": step_count,
                "is_final": False,
                "final_response": final_response,
                "tool_calls": [],
                "is_step_complete": True,
            }

        # Emit final response event
        if agent and hasattr(agent, "emit"):
            agent.emit(FinalResponseEvent(
                content=final_response,
                steps_taken=step_count,
                conversation_id=conversation_id,
            ))

        return {
            "messages": messages,
            "step_count": step_count,
            "is_final": True,
            "final_response": final_response,
            "tool_calls": [],
        }


async def _react_streaming(
    state, agent, api_messages, step_count, client, model, tools, temperature
) -> dict:
    """Streaming ReAct step."""
    conversation_id = state.get("conversation_id", "default")

    stream_response = await client.chat.completions.create(
        model=model,
        messages=api_messages,
        tools=tools,
        tool_choice="auto",
        temperature=temperature,
        stream=True,
    )

    current_content = ""
    tool_calls_dict: Dict[int, Dict[str, Any]] = {}

    async for chunk in stream_response:
        delta = chunk.choices[0].delta

        # Content streaming
        if delta.content:
            current_content += delta.content
            if agent and hasattr(agent, "emit"):
                agent.emit(AssistantDeltaEvent(
                    content=delta.content,
                    accumulated=current_content,
                    conversation_id=conversation_id,
                ))

        # Tool call streaming (accumulate deltas)
        if delta.tool_calls:
            for tc_delta in delta.tool_calls:
                idx = tc_delta.index
                if idx not in tool_calls_dict:
                    tool_calls_dict[idx] = {
                        "id": "",
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    }
                if tc_delta.id:
                    tool_calls_dict[idx]["id"] = tc_delta.id
                if tc_delta.function:
                    if tc_delta.function.name:
                        tool_calls_dict[idx]["function"]["name"] = tc_delta.function.name
                    if tc_delta.function.arguments:
                        tool_calls_dict[idx]["function"]["arguments"] += tc_delta.function.arguments

        finish_reason = chunk.choices[0].finish_reason

        if finish_reason == "stop":
            # Final answer via streaming
            final_response = current_content or "No response generated"
            messages = list(state.get("messages", []))
            messages.append({"role": "assistant", "content": final_response})

            if agent and hasattr(agent, "memory"):
                await agent.memory.save_message(conversation_id, "assistant", final_response)

            # Check if we're in plan_and_execute mode with active steps
            plan_steps = state.get("plan_steps", [])
            current_plan_step = state.get("current_plan_step", 0)
            has_active_plan = bool(plan_steps) and current_plan_step < len(plan_steps)

            if has_active_plan:
                # In plan mode: the step is complete, not the entire conversation
                return {
                    "messages": messages,
                    "step_count": step_count,
                    "is_final": False,
                    "final_response": final_response,
                    "tool_calls": [],
                    "is_step_complete": True,
                }

            if agent and hasattr(agent, "emit"):
                agent.emit(FinalResponseEvent(
                    content=final_response,
                    steps_taken=step_count,
                    conversation_id=conversation_id,
                ))

            return {
                "messages": messages,
                "step_count": step_count,
                "is_final": True,
                "final_response": final_response,
                "tool_calls": [],
            }

        elif finish_reason == "tool_calls":
            # Tool calls via streaming
            tool_calls = list(tool_calls_dict.values())
            messages = list(state.get("messages", []))
            messages.append({
                "role": "assistant",
                "content": current_content,
                "tool_calls": tool_calls,
            })

            for tc_data in tool_calls:
                if agent and hasattr(agent, "emit"):
                    agent.emit(ToolCallStartEvent(
                        tool_name=tc_data["function"]["name"],
                        tool_id=tc_data["id"],
                        arguments_raw=tc_data["function"]["arguments"],
                        conversation_id=conversation_id,
                    ))

            return {
                "messages": messages,
                "tool_calls": tool_calls,
                "step_count": step_count,
                "is_final": False,
            }

    # If we got here without a finish_reason, treat as final
    final_response = current_content or "No response generated"
    messages = list(state.get("messages", []))
    messages.append({"role": "assistant", "content": final_response})

    return {
        "messages": messages,
        "step_count": step_count,
        "is_final": True,
        "final_response": final_response,
        "tool_calls": [],
    }


def _build_system_prompt_from_state(state: HelixGraphState, agent=None) -> str:
    """Build the system prompt using state's memory/skills/strategies."""
    # Format tools
    tools_desc = ""
    if agent and hasattr(agent, "tools"):
        tools_desc = format_tools_description(agent.tools.get_schemas())

    # Format skills
    skills_formatted = ""
    relevant_skills = state.get("relevant_skills", [])
    if relevant_skills and agent and hasattr(agent, "skills"):
        skills_formatted = agent.skills.format_skills_for_prompt(relevant_skills)

    # Format memories
    relevant_memories = state.get("relevant_memories", [])
    memories_text = ""
    if relevant_memories:
        memory_parts = []
        for mem in relevant_memories:
            source = mem.get("source", "unknown")
            relevance = mem.get("relevance", "")
            content = mem.get("content", "")
            memory_parts.append(f"[{source}{relevance}]: {content}")
        memories_text = "\n".join(memory_parts)

    # Format strategies
    relevant_strategies = state.get("relevant_strategies", [])
    strategies_text = ""
    if relevant_strategies and agent and hasattr(agent, "memory"):
        strategies_text = agent.memory.strategic.format_strategies_for_prompt(
            relevant_strategies
        )

    # Combine memories
    combined_memories = memories_text
    if strategies_text:
        combined_memories = f"{memories_text}\n\n{strategies_text}" if memories_text else strategies_text

    # Inject plan step context if in plan_and_execute/hybrid mode
    plan_context = ""
    plan_steps = state.get("plan_steps", [])
    current_step_idx = state.get("current_plan_step", 0)
    if plan_steps and current_step_idx < len(plan_steps):
        step = plan_steps[current_step_idx]
        plan_context = (
            f"\n\n## Current Plan Step ({current_step_idx + 1}/{len(plan_steps)})\n"
            f"**Task**: {step.get('description', '')}\n"
            f"**Tools needed**: {', '.join(step.get('tools_needed', [])) or 'all available'}\n"
            f"**Expected output**: {step.get('expected_output', '')}\n"
            f"**Success criteria**: {step.get('success_criteria', '')}\n\n"
            f"Focus on completing ONLY this step. When you have achieved the success criteria "
            f"and produced the expected output, provide your final answer WITHOUT calling any more tools.\n"
        )
        # Add previous steps context
        if current_step_idx > 0:
            prev_steps = []
            for i in range(current_step_idx):
                s = plan_steps[i]
                prev_steps.append(f"  Step {s.get('step', i+1)}: {s.get('description', '')[:80]}")
            plan_context += f"\n## Previous Steps Completed\n" + "\n".join(prev_steps) + "\n"

    # Append plan context to combined memories
    if plan_context:
        combined_memories = f"{combined_memories}\n{plan_context}" if combined_memories else plan_context

    profile_name = getattr(getattr(agent, "config", None), "profile_name", None)
    return build_system_prompt(
        tools_description=tools_desc,
        active_skills=relevant_skills,
        skills_formatted=skills_formatted,
        relevant_memories=combined_memories,
        profile_name=profile_name,
    )


def _build_api_messages(system_prompt, messages, context_manager) -> list:
    """Build API message list respecting context window limits."""
    system_msg = {"role": "system", "content": system_prompt}
    system_tokens = context_manager.token_counter.count_message_tokens([system_msg])

    response_reserve = 2048
    available_tokens = context_manager.context_window - system_tokens - response_reserve

    if available_tokens <= 0:
        return [system_msg]

    selected = []
    running_tokens = 0

    for msg in reversed(messages):
        msg_tokens = context_manager.token_counter.count_message_tokens([msg])
        if running_tokens + msg_tokens > available_tokens:
            break
        selected.append(msg)
        running_tokens += msg_tokens

    selected.reverse()
    return [system_msg] + selected