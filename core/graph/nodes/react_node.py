"""
ReAct Node — core reasoning node for the Holix LangGraph.

Calls the LLM, processes the response, and either sets tool_calls
or sets is_final + final_response. Emits AgentEvent objects to
the event bus as side effects.
"""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.runnables import RunnableConfig
from openai import AsyncOpenAI

from core.agent_events import (
    AssistantDeltaEvent,
    FinalResponseEvent,
    ThinkingEvent,
    ToolCallStartEvent,
)
from core.graph.plan_step import (
    plan_step_active,
    plan_step_complete,
    plan_step_retry_update,
    prefer_non_streaming_for_plan,
)
from core.graph.state import HolixGraphState, get_agent_from_config
from core.i18n.live_ui import live_reasoning_label, live_thinking_step_label
from core.llm.response_text import (
    assistant_message_parts,
    resolve_assistant_text,
    stream_delta_parts,
)
from core.llm.step_timeout import (
    LLMStepTimeoutError,
    llm_step_timeout_message,
    reasoning_only_abort_s,
)
from core.presenters.final_content import MESSENGER_EMPTY_FINAL_RU
from core.profile.soul import profile_name_from_agent
from core.prompt_builder import build_system_prompt, format_tools_description

logger = logging.getLogger(__name__)

_DEFAULT_LLM_STEP_TIMEOUT_S = 300.0


async def _close_async_stream(stream: Any) -> None:
    """Best-effort close of an OpenAI/httpx streaming response."""
    for method_name in ("close", "aclose"):
        method = getattr(stream, method_name, None)
        if not callable(method):
            continue
        try:
            result = method()
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            logger.debug("Failed to close LLM stream via %s", method_name, exc_info=True)
        return


async def _iter_stream_chunks(stream: Any, timeout_s: float) -> AsyncIterator[Any]:
    """Iterate stream chunks with a hard deadline and guaranteed stream cleanup."""
    deadline = time.monotonic() + timeout_s
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            try:
                chunk = await asyncio.wait_for(anext(stream), timeout=remaining)
            except StopAsyncIteration:
                break
            yield chunk
    finally:
        await _close_async_stream(stream)


def _non_empty_final(text: str) -> str:
    """Ensure the user always sees something when a react step ends."""
    return (text or "").strip() or MESSENGER_EMPTY_FINAL_RU


async def _plan_step_result(
    state: HolixGraphState,
    *,
    agent,
    conversation_id: str,
    messages: list[dict[str, Any]],
    step_count: int,
    final_response: str,
    assistant_already_appended: bool,
) -> dict[str, Any]:
    """Return react state for an active plan step (complete or retry)."""
    if plan_step_complete(state, final_response=final_response):
        if agent and hasattr(agent, "memory"):
            await agent.memory.save_message(conversation_id, "assistant", final_response)
        return {
            "messages": messages,
            "step_count": step_count,
            "is_final": False,
            "final_response": final_response,
            "tool_calls": [],
            "is_step_complete": True,
        }
    return plan_step_retry_update(
        messages=messages,
        step_count=step_count,
        final_response=final_response,
        include_assistant=not assistant_already_appended,
    )


def _llm_step_timeout_s(agent) -> float:
    cfg = getattr(agent, "config", None) if agent else None
    raw = getattr(cfg, "llm_step_timeout", None) if cfg else None
    if raw is not None:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            return value
    return _DEFAULT_LLM_STEP_TIMEOUT_S


def _emit_final_response(
    agent,
    *,
    content: str,
    steps_taken: int,
    conversation_id: str,
) -> None:
    if agent and hasattr(agent, "emit"):
        agent._final_response_emitted = True
        agent.emit(
            FinalResponseEvent(
                content=content,
                steps_taken=steps_taken,
                conversation_id=conversation_id,
            )
        )


async def react_node(state: HolixGraphState, config: RunnableConfig) -> dict:
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
    if prefer_non_streaming_for_plan(state):
        stream = False

    profile_name = profile_name_from_agent(agent) if agent else "default"
    if agent and hasattr(agent, "emit"):
        agent.emit(
            ThinkingEvent(
                message=live_thinking_step_label(profile_name, step_count),
                conversation_id=conversation_id,
            )
        )

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
        err = "Error: No LLM model configured"
        _emit_final_response(
            agent,
            content=err,
            steps_taken=step_count,
            conversation_id=conversation_id,
        )
        return {
            "step_count": step_count,
            "is_final": True,
            "final_response": err,
        }
    tools = agent.tools.get_schemas() if agent and hasattr(agent, "tools") else []
    temperature = 0.7
    if agent and hasattr(agent, "config"):
        temperature = getattr(agent.config, "temperature", 0.7)

    if not client:
        err = "Error: No LLM client available"
        _emit_final_response(
            agent,
            content=err,
            steps_taken=step_count,
            conversation_id=conversation_id,
        )
        return {
            "step_count": step_count,
            "is_final": True,
            "final_response": err,
        }

    agent_slot = getattr(agent, "agent_slot", "main") if agent else "main"
    model_manager = getattr(agent, "model_manager", None) if agent else None
    llm_timeout_s = _llm_step_timeout_s(agent)

    def _on_fallback_switch(cfg) -> None:
        if agent and hasattr(agent, "set_active_model_config"):
            agent.set_active_model_config(cfg)

    try:
        if stream:
            return await _react_streaming(
                state,
                agent,
                api_messages,
                step_count,
                client,
                model,
                tools,
                temperature,
                model_manager=model_manager,
                agent_slot=agent_slot,
                on_switch=_on_fallback_switch,
                llm_timeout_s=llm_timeout_s,
            )
        else:
            return await _react_non_streaming(
                state,
                agent,
                api_messages,
                step_count,
                client,
                model,
                tools,
                temperature,
                model_manager=model_manager,
                agent_slot=agent_slot,
                on_switch=_on_fallback_switch,
                llm_timeout_s=llm_timeout_s,
            )

    except LLMStepTimeoutError as exc:
        err = exc.user_message
        logger.warning(
            "LLM reasoning-only abort (model=%s, step=%s)",
            model,
            step_count,
        )
        _emit_final_response(
            agent,
            content=err,
            steps_taken=step_count,
            conversation_id=conversation_id,
        )
        return {
            "step_count": step_count,
            "is_final": True,
            "final_response": err,
        }
    except TimeoutError:
        timeout_s = llm_timeout_s
        err = llm_step_timeout_message(timeout_s, model=model)
        logger.warning("LLM step timeout (model=%s, step=%s)", model, step_count)
        _emit_final_response(
            agent,
            content=err,
            steps_taken=step_count,
            conversation_id=conversation_id,
        )
        return {
            "step_count": step_count,
            "is_final": True,
            "final_response": err,
        }
    except Exception as e:
        logger.error(f"Error in react_node: {e}")
        err = f"Error during agent step: {str(e)}"
        _emit_final_response(
            agent,
            content=err,
            steps_taken=step_count,
            conversation_id=conversation_id,
        )
        return {
            "step_count": step_count,
            "is_final": True,
            "final_response": err,
        }


async def _react_non_streaming(
    state,
    agent,
    api_messages,
    step_count,
    client,
    model,
    tools,
    temperature,
    *,
    model_manager=None,
    agent_slot: str = "main",
    on_switch=None,
    llm_timeout_s: float = _DEFAULT_LLM_STEP_TIMEOUT_S,
) -> dict:
    """Non-streaming ReAct step."""
    conversation_id = state.get("conversation_id", "default")

    async def _call_llm():
        if model_manager:
            from core.models.fallback import chat_completions_with_fallback

            return await chat_completions_with_fallback(
                model_manager,
                agent_name=agent_slot,
                on_switch=on_switch,
                messages=api_messages,
                tools=tools,
                tool_choice="auto",
                temperature=temperature,
            )
        return await client.chat.completions.create(
            model=model,
            messages=api_messages,
            tools=tools,
            tool_choice="auto",
            temperature=temperature,
        )

    async with asyncio.timeout(llm_timeout_s):
        response = await _call_llm()

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
        msg_content, msg_reasoning = assistant_message_parts(message)
        finish_reason = response.choices[0].finish_reason if response.choices else None
        final_response = _non_empty_final(
            resolve_assistant_text(
                content=msg_content,
                reasoning_content=msg_reasoning,
                finish_reason=finish_reason,
                model=model,
                profile_name=profile_name_from_agent(agent) if agent else None,
            )
        )
        msg_dict["content"] = final_response
        messages.append(msg_dict)

        if plan_step_active(state):
            return await _plan_step_result(
                state,
                agent=agent,
                conversation_id=conversation_id,
                messages=messages,
                step_count=step_count,
                final_response=final_response,
                assistant_already_appended=True,
            )

        if agent and hasattr(agent, "memory"):
            await agent.memory.save_message(conversation_id, "assistant", final_response)

        _emit_final_response(
            agent,
            content=final_response,
            steps_taken=step_count,
            conversation_id=conversation_id,
        )

        return {
            "messages": messages,
            "step_count": step_count,
            "is_final": True,
            "final_response": final_response,
            "tool_calls": [],
        }


async def _react_streaming(
    state,
    agent,
    api_messages,
    step_count,
    client,
    model,
    tools,
    temperature,
    *,
    model_manager=None,
    agent_slot: str = "main",
    on_switch=None,
    llm_timeout_s: float = _DEFAULT_LLM_STEP_TIMEOUT_S,
) -> dict:
    """Streaming ReAct step."""
    conversation_id = state.get("conversation_id", "default")

    async def _open_stream():
        if model_manager:
            from core.models.fallback import run_with_provider_fallback

            return await run_with_provider_fallback(
                model_manager,
                agent_name=agent_slot,
                on_switch=on_switch,
                factory=lambda cfg, llm_client: llm_client.chat.completions.create(
                    model=cfg.model,
                    messages=api_messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=temperature,
                    stream=True,
                ),
            )
        return await client.chat.completions.create(
            model=model,
            messages=api_messages,
            tools=tools,
            tool_choice="auto",
            temperature=temperature,
            stream=True,
        )

    current_content = ""
    current_reasoning = ""
    tool_calls_dict: dict[int, dict[str, Any]] = {}
    last_finish_reason: str | None = None
    reasoning_status_emitted = False
    reasoning_only_deadline: float | None = None

    stream_response = await _open_stream()
    async for chunk in _iter_stream_chunks(stream_response, llm_timeout_s):
            delta = chunk.choices[0].delta
            content_delta, reasoning_delta = stream_delta_parts(delta)

            # Content / reasoning streaming (reasoning models may only fill reasoning_*)
            if content_delta:
                current_content += content_delta
                if agent and hasattr(agent, "emit"):
                    agent.emit(AssistantDeltaEvent(
                        content=content_delta,
                        accumulated=current_content,
                        conversation_id=conversation_id,
                    ))
            if reasoning_delta:
                # Reasoning is internal; do not stream it to messenger progress UIs.
                current_reasoning += reasoning_delta
                if reasoning_only_deadline is None:
                    reasoning_only_deadline = (
                        time.monotonic() + reasoning_only_abort_s(llm_timeout_s)
                    )
                if (
                    not current_content.strip()
                    and not tool_calls_dict
                    and reasoning_only_deadline is not None
                    and time.monotonic() > reasoning_only_deadline
                ):
                    raise LLMStepTimeoutError(
                        llm_step_timeout_message(
                            reasoning_only_abort_s(llm_timeout_s),
                            model=model,
                            reasoning_only=True,
                        )
                    )
                if (
                    not current_content.strip()
                    and agent
                    and hasattr(agent, "emit")
                    and not reasoning_status_emitted
                ):
                    agent.emit(
                        ThinkingEvent(
                            message=live_reasoning_label(profile_name_from_agent(agent)),
                            conversation_id=conversation_id,
                        )
                    )
                    reasoning_status_emitted = True

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
            if finish_reason:
                last_finish_reason = finish_reason

            if finish_reason == "stop":
                final_response = resolve_assistant_text(
                    content=current_content,
                    reasoning_content=current_reasoning,
                    finish_reason=finish_reason,
                    model=model,
                    profile_name=profile_name_from_agent(agent) if agent else None,
                )
                if not (final_response or "").strip():
                    logger.warning(
                        "Empty streaming LLM response (model=%s); retrying non-streaming",
                        model,
                    )
                    return await _react_non_streaming(
                        state,
                        agent,
                        api_messages,
                        step_count,
                        client,
                        model,
                        tools,
                        temperature,
                        model_manager=model_manager,
                        agent_slot=agent_slot,
                        on_switch=on_switch,
                        llm_timeout_s=llm_timeout_s,
                    )
                messages = list(state.get("messages", []))
                messages.append({"role": "assistant", "content": final_response})

                if agent and hasattr(agent, "memory"):
                    await agent.memory.save_message(conversation_id, "assistant", final_response)

                if plan_step_active(state):
                    return await _plan_step_result(
                        state,
                        agent=agent,
                        conversation_id=conversation_id,
                        messages=messages,
                        step_count=step_count,
                        final_response=final_response,
                        assistant_already_appended=True,
                    )

                if agent and hasattr(agent, "memory"):
                    await agent.memory.save_message(conversation_id, "assistant", final_response)

                _emit_final_response(
                    agent,
                    content=final_response,
                    steps_taken=step_count,
                    conversation_id=conversation_id,
                )

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

    # Stream ended without an explicit finish_reason — treat as final
    final_response = resolve_assistant_text(
        content=current_content,
        reasoning_content=current_reasoning,
        finish_reason=last_finish_reason,
        model=model,
        profile_name=profile_name_from_agent(agent) if agent else None,
    )
    if not (final_response or "").strip():
        logger.warning(
            "Stream ended without assistant text (model=%s, finish_reason=%s); "
            "retrying non-streaming",
            model,
            last_finish_reason,
        )
        return await _react_non_streaming(
            state,
            agent,
            api_messages,
            step_count,
            client,
            model,
            tools,
            temperature,
            model_manager=model_manager,
            agent_slot=agent_slot,
            on_switch=on_switch,
            llm_timeout_s=llm_timeout_s,
        )
    final_response = _non_empty_final(final_response)
    messages = list(state.get("messages", []))
    messages.append({"role": "assistant", "content": final_response})

    if plan_step_active(state):
        return await _plan_step_result(
            state,
            agent=agent,
            conversation_id=conversation_id,
            messages=messages,
            step_count=step_count,
            final_response=final_response,
            assistant_already_appended=True,
        )

    if agent and hasattr(agent, "memory"):
        await agent.memory.save_message(conversation_id, "assistant", final_response)

    _emit_final_response(
        agent,
        content=final_response,
        steps_taken=step_count,
        conversation_id=conversation_id,
    )

    return {
        "messages": messages,
        "step_count": step_count,
        "is_final": True,
        "final_response": final_response,
        "tool_calls": [],
    }


def _build_system_prompt_from_state(state: HolixGraphState, agent=None) -> str:
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
            plan_context += "\n## Previous Steps Completed\n" + "\n".join(prev_steps) + "\n"

    # Append plan context to combined memories
    if plan_context:
        combined_memories = f"{combined_memories}\n{plan_context}" if combined_memories else plan_context

    profile_name = profile_name_from_agent(agent) if agent else "default"
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