"""
Unified Agent Execution Engine (Variant B - Phase 0)

This module contains the single source of truth for Holix agent reasoning.

Both classic (AgentLoop) and streaming (StreamingAgentLoop) paths now delegate
to the event-driven generator defined here.

Goals achieved:
- No more massive duplication between loop.py and loop_streaming.py
- All events are emitted from one place
- Easy to add real token streaming
- Clean separation: execution logic vs adapters
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.context import ContextManager

logger = logging.getLogger(__name__)

from openai import AsyncOpenAI

from config import settings
from core.agent_events import (
    AgentEvent,
    AssistantDeltaEvent,
    ErrorEvent,
    FinalResponseEvent,
    MaxStepsReachedEvent,
    SelfImprovementStartedEvent,
    SkillCreatedEvent,
    ThinkingEvent,
    ToolCallErrorEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from core.prompt_builder import build_system_prompt, format_tools_description


async def run_agent_loop(
    agent,
    user_input: str,
    conversation_id: str = "default",
    *,
    stream: bool = False,
) -> AsyncGenerator[AgentEvent, None]:
    """
    Single unified event-driven agent execution loop.

    This is the core of the agent. All reasoning, tool use, and self-improvement
    happens here.

    Args:
        agent: The HolixAgent instance (must have memory, skills, tools, client, etc.)
        user_input: The user's message
        conversation_id: Conversation identifier for memory
        stream: If True, uses LLM streaming and yields AssistantDeltaEvent chunks.
                If False, uses regular non-streaming calls (classic behavior).

    Yields:
        AgentEvent objects (Thinking, ToolCall*, AssistantDelta, FinalResponse, etc.)
    """
    # ------------------------------------------------------------------
    # 1. Common setup (shared with LangGraph via prepare_session)
    # ------------------------------------------------------------------
    from core.runtime.session import prepare_session

    messages, _was_compressed = await prepare_session(
        agent, user_input, conversation_id
    )

    # Retrieve relevant skills
    agent_slot = getattr(agent, "agent_slot", "main")
    relevant_skills = agent.skills.get_relevant_skills(
        user_input, top_k=3, agent_slot=agent_slot
    )
    skills_formatted = agent.skills.format_skills_for_prompt(relevant_skills)

    # Retrieve relevant memories from past conversations
    relevant_memories = ""
    try:
        memories = await agent.memory.search(
            query=user_input,
            top_k=5,
            conversation_id=None,  # Search across ALL conversations
        )
        # Filter: only include memories from OTHER conversations or
        # system messages (context compression summaries) that may not be in current messages
        if memories:
            memory_parts = []
            for mem in memories:
                meta = mem.get("metadata", {})
                mem_conv = meta.get("conversation_id", "")
                mem_type = meta.get("type", "")
                mem_role = meta.get("role", "")
                # Include if from a different conversation, or a context compression summary
                if mem_conv != conversation_id or mem_type == "context_compression":
                    source = f"session {mem_conv[:8]}" if mem_conv else "unknown"
                    if mem_type == "context_compression":
                        source = f"compressed context ({source})"
                    elif mem_role == "system":
                        source = f"system note ({source})"
                    distance = mem.get("distance")
                    relevance = f" (relevance: {1 - distance:.2f})" if distance is not None else ""
                    memory_parts.append(f"[{source}{relevance}]: {mem['content'][:500]}")

            if memory_parts:
                relevant_memories = "\n".join(memory_parts)
    except Exception as e:
        logger.warning(f"Memory search failed: {e}")

    # Build system prompt
    tools_desc = format_tools_description(agent.tools.get_schemas())
    profile_name = getattr(getattr(agent, "config", None), "profile_name", None)
    system_prompt = build_system_prompt(
        tools_description=tools_desc,
        active_skills=relevant_skills,
        skills_formatted=skills_formatted,
        relevant_memories=relevant_memories,
        profile_name=profile_name,
    )

    # ------------------------------------------------------------------
    # 2. Main reasoning loop
    # ------------------------------------------------------------------
    step_count = 0
    agent_config = getattr(agent, "config", None)
    max_steps = getattr(agent_config, "max_steps", settings.max_steps)
    model = getattr(agent, "model", settings.model)
    temperature = getattr(agent_config, "temperature", settings.temperature)
    client: AsyncOpenAI = agent.client
    agent_slot = getattr(agent, "agent_slot", "main")
    model_manager = getattr(agent, "model_manager", None)

    def _on_fallback_switch(cfg) -> None:
        if hasattr(agent, "set_active_model_config"):
            agent.set_active_model_config(cfg)
            nonlocal client, model
            client = agent.client
            model = agent.model

    # Initial thinking signal
    yield ThinkingEvent(
        message="Holix is thinking...",
        conversation_id=conversation_id,
    )

    while step_count < max_steps:
        step_count += 1

        # Build API messages: system prompt + recent messages
        # Use context_manager to determine how many messages fit, or fallback to last 20
        if hasattr(agent, 'context_manager') and agent.context_manager:
            # Context-aware message selection: fit as many messages as possible
            # while staying within the context window (minus system prompt tokens)
            api_messages = _build_api_messages(
                system_prompt, messages, agent.context_manager
            )
        else:
            # Legacy fallback: just last 20 messages
            api_messages = [
                {"role": "system", "content": system_prompt}
            ] + messages[-20:]

        try:
            if stream:
                # ==================== STREAMING PATH ====================
                from core.models.fallback import run_with_provider_fallback

                if model_manager:
                    stream_response = await run_with_provider_fallback(
                        model_manager,
                        agent_name=agent_slot,
                        on_switch=_on_fallback_switch,
                        factory=lambda cfg, llm_client: llm_client.chat.completions.create(
                            model=cfg.model,
                            messages=api_messages,
                            tools=agent.tools.get_schemas(),
                            tool_choice="auto",
                            temperature=temperature,
                            stream=True,
                        ),
                    )
                else:
                    stream_response = await client.chat.completions.create(
                        model=model,
                        messages=api_messages,
                        tools=agent.tools.get_schemas(),
                        tool_choice="auto",
                        temperature=temperature,
                        stream=True,
                    )

                current_content = ""
                tool_calls_dict: dict[int, dict[str, Any]] = {}

                async for chunk in stream_response:
                    delta = chunk.choices[0].delta

                    # --- Content streaming ---
                    if delta.content:
                        current_content += delta.content
                        yield AssistantDeltaEvent(
                            content=delta.content,
                            accumulated=current_content,
                            conversation_id=conversation_id,
                        )

                    # --- Tool call streaming (accumulate deltas) ---
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
                        # Final answer arrived via streaming
                        final_response = current_content or "No response generated"

                        # Save assistant message
                        assistant_msg = {"role": "assistant", "content": final_response}
                        messages.append(assistant_msg)
                        await agent.memory.save_message(
                            conversation_id, "assistant", final_response
                        )

                        yield FinalResponseEvent(
                            content=final_response,
                            steps_taken=step_count,
                            conversation_id=conversation_id,
                        )

                        await _maybe_self_improve(agent, conversation_id, messages, final_response)
                        return

                    elif finish_reason == "tool_calls":
                        # Tool calls arrived via streaming
                        tool_calls = list(tool_calls_dict.values())
                        assistant_msg = {
                            "role": "assistant",
                            "content": current_content,
                            "tool_calls": tool_calls,
                        }
                        messages.append(assistant_msg)

                        # Execute tools
                        for tc_data in tool_calls:
                            tool_name = tc_data["function"]["name"]

                            # Create a minimal tool call object compatible with execute()
                            class _ToolCall:
                                def __init__(self, data):
                                    self.id = data.get("id", "")
                                    self.type = data.get("type", "function")
                                    self.function = type("obj", (object,), {
                                        "name": data["function"]["name"],
                                        "arguments": data["function"]["arguments"],
                                    })()

                            tool_call_obj = _ToolCall(tc_data)

                            yield ToolCallStartEvent(
                                tool_name=tool_name,
                                tool_id=tool_call_obj.id,
                                arguments_raw=tc_data["function"]["arguments"],
                                conversation_id=conversation_id,
                            )

                            start = time.time()
                            try:
                                result = await agent.tools.execute(
                                    tool_call_obj,
                                    conversation_id=conversation_id,
                                    memory=agent.memory,
                                )
                                duration = (time.time() - start) * 1000

                                yield ToolCallResultEvent(
                                    tool_name=tool_name,
                                    tool_id=tool_call_obj.id,
                                    result=result,
                                    duration_ms=duration,
                                    conversation_id=conversation_id,
                                )
                            except Exception as tool_err:
                                yield ToolCallErrorEvent(
                                    tool_name=tool_name,
                                    tool_id=tool_call_obj.id,
                                    error=str(tool_err),
                                    conversation_id=conversation_id,
                                )
                                result = f"Error: {tool_err}"

                            tool_msg = {
                                "role": "tool",
                                "tool_call_id": tool_call_obj.id,
                                "content": result,
                            }
                            messages.append(tool_msg)
                            await agent.memory.save_message(
                                conversation_id, "tool", result,
                                metadata={"tool_name": tool_name}
                            )

                        # Continue to next reasoning step with tool results
                        break  # exit the async for chunk loop

            else:
                # ==================== NON-STREAMING PATH ====================
                from core.models.fallback import chat_completions_with_fallback

                if model_manager:
                    response = await chat_completions_with_fallback(
                        model_manager,
                        agent_name=agent_slot,
                        on_switch=_on_fallback_switch,
                        messages=api_messages,
                        tools=agent.tools.get_schemas(),
                        tool_choice="auto",
                        temperature=temperature,
                    )
                else:
                    response = await client.chat.completions.create(
                        model=model,
                        messages=api_messages,
                        tools=agent.tools.get_schemas(),
                        tool_choice="auto",
                        temperature=temperature,
                    )

                message = response.choices[0].message
                msg_dict = {"role": "assistant", "content": message.content or ""}

                if message.tool_calls:
                    msg_dict["tool_calls"] = [
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
                    messages.append(msg_dict)

                    for tool_call in message.tool_calls:
                        tool_name = tool_call.function.name
                        tool_id = tool_call.id
                        args_raw = tool_call.function.arguments

                        yield ToolCallStartEvent(
                            tool_name=tool_name,
                            tool_id=tool_id,
                            arguments_raw=args_raw,
                            conversation_id=conversation_id,
                        )

                        start = time.time()
                        try:
                            result = await agent.tools.execute(
                                tool_call,
                                conversation_id=conversation_id,
                                memory=agent.memory,
                            )
                            duration = (time.time() - start) * 1000

                            yield ToolCallResultEvent(
                                tool_name=tool_name,
                                tool_id=tool_id,
                                result=result,
                                duration_ms=duration,
                                conversation_id=conversation_id,
                                truncated=len(result) > 200,
                            )
                        except Exception as tool_err:
                            yield ToolCallErrorEvent(
                                tool_name=tool_name,
                                tool_id=tool_id,
                                error=str(tool_err),
                                conversation_id=conversation_id,
                            )
                            result = f"Error: {tool_err}"

                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result,
                        }
                        messages.append(tool_msg)
                        await agent.memory.save_message(
                            conversation_id, "tool", result,
                            metadata={"tool_name": tool_name}
                        )

                    continue  # next reasoning iteration

                else:
                    # Final answer (non-streaming)
                    final_response = message.content or "No response generated"
                    messages.append(msg_dict)

                    await agent.memory.save_message(
                        conversation_id, "assistant", final_response
                    )

                    yield FinalResponseEvent(
                        content=final_response,
                        steps_taken=step_count,
                        conversation_id=conversation_id,
                    )

                    await _maybe_self_improve(agent, conversation_id, messages, final_response)
                    return

        except Exception as e:
            yield ErrorEvent(
                error=f"Error during agent step: {str(e)}",
                error_type="execution",
                recoverable=False,
                conversation_id=conversation_id,
            )
            return

    # Max steps reached
    yield MaxStepsReachedEvent(
        max_steps=max_steps,
        conversation_id=conversation_id,
    )
    timeout_msg = f"Agent reached maximum steps ({max_steps}). Task may be too complex."
    await agent.memory.save_message(conversation_id, "assistant", timeout_msg)


async def _maybe_self_improve(
    agent,
    conversation_id: str,
    messages: list[dict[str, Any]],
    final_response: str,
) -> None:
    """Internal helper for self-improvement (skill creation) and LTM auto-summarization."""
    try:
        should_create = await agent.skills.should_create_skill(messages, final_response)
        if not should_create:
            return

        user_messages = [m for m in messages if m.get("role") == "user"]
        if not user_messages:
            return

        task_description = user_messages[0].get("content", "")

        if hasattr(agent, "emit"):
            agent.emit(
                SelfImprovementStartedEvent(
                    conversation_id=conversation_id,
                    task_description=task_description[:200],
                )
            )

        from core.skills.generator import SkillGenerator

        generator = SkillGenerator(agent.client, model=agent.model)
        skill_data = await generator.create_skill_from_session(messages, task_description)

        if skill_data and skill_data.get("name"):
            agent_slot = getattr(agent, "agent_slot", "main")
            filepath = agent.skills.save_skill(
                name=skill_data["name"],
                description=skill_data.get("description", ""),
                content=skill_data["content"],
                tags=skill_data.get("tags", []),
                examples=skill_data.get("examples", []),
                agent_slot=agent_slot,
            )
            if hasattr(agent, "config"):
                agent.config = agent.config.with_overrides(
                    skill_assignments=agent.skills.skill_assignments
                )

            if hasattr(agent, "emit"):
                agent.emit(
                    SkillCreatedEvent(
                        skill_name=skill_data["name"],
                        description=skill_data.get("description", ""),
                        filepath=str(filepath),
                        tags=skill_data.get("tags", []),
                        conversation_id=conversation_id,
                    )
                )

    except Exception as e:
        if hasattr(agent, "emit"):
            agent.emit(
                ErrorEvent(
                    error=str(e),
                    error_type="self_improvement",
                    recoverable=True,
                    conversation_id=conversation_id,
                )
            )

    # Auto-summarize conversation into episodic memory (LTM)
    if settings.auto_summarize_conversations and hasattr(agent.memory, 'auto_summarize_conversation'):
        try:
            await agent.memory.auto_summarize_conversation(
                conversation_id=conversation_id,
                messages=messages,
                llm_client=agent.client,
                model=agent.model,
            )
        except Exception as e:
            logger.warning(f"Auto-summarization failed for {conversation_id}: {e}")


def _build_api_messages(
    system_prompt: str,
    messages: list[dict[str, Any]],
    context_manager: ContextManager,
) -> list[dict[str, Any]]:
    """Build the API message list, fitting as many recent messages as possible
    within the context window.

    Strategy: start from the most recent messages and work backwards,
    including messages until we'd exceed the context window (minus system prompt overhead).

    Args:
        system_prompt: The system prompt string.
        messages: Full conversation message list.
        context_manager: ContextManager instance for token counting.

    Returns:
        List of messages for the API call, starting with the system prompt.
    """
    system_msg = {"role": "system", "content": system_prompt}
    system_tokens = context_manager.token_counter.count_message_tokens([system_msg])

    # Reserve buffer for model's response and tool overhead
    response_reserve = 2048
    available_tokens = context_manager.context_window - system_tokens - response_reserve

    if available_tokens <= 0:
        # Extremely small context window — just send system prompt
        return [system_msg]

    # Greedily include messages from the end
    selected = []
    running_tokens = 0

    for msg in reversed(messages):
        msg_tokens = context_manager.token_counter.count_message_tokens([msg])
        if running_tokens + msg_tokens > available_tokens:
            break
        selected.append(msg)
        running_tokens += msg_tokens

    # Reverse back to chronological order
    selected.reverse()

    return [system_msg] + selected