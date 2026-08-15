"""
ReAct Node — core reasoning node for the Holix LangGraph.

Calls the LLM, processes the response, and either sets tool_calls
or sets is_final + final_response. Emits AgentEvent objects to
the event bus as side effects.
"""

import asyncio
import json
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
from core.graph.action_honesty import (
    MONOLOGUE_HONESTY_REFUSAL,
    has_successful_workspace_listing,
    honesty_refusal_update,
    honesty_retry_update,
    looks_like_status_monologue,
    resolve_tool_choice,
    scrub_false_empty_claim_content,
    should_nudge_false_completion,
    should_refuse_false_empty_workspace,
    should_refuse_status_monologue,
    should_refuse_unproven_sdd_fill,
    workspace_grounding_refusal_text,
)
from core.graph.plan_step import (
    plan_step_active,
    plan_step_complete,
    plan_step_retry_update,
    prefer_non_streaming_for_plan,
)
from core.graph.state import HolixGraphState, get_agent_from_config
from core.i18n.live_ui import live_reasoning_label, live_thinking_step_label
from core.llm.max_tokens import (
    profile_agent_max_tokens,
    purpose_from_graph_state,
    resolve_agent_max_tokens,
)
from core.llm.response_text import (
    assistant_message_parts,
    collapse_repetitive_text,
    is_pathological_repetition,
    reasoning_only_user_message,
    resolve_assistant_text,
    stream_delta_parts,
)
from core.llm.step_timeout import (
    LLMStepTimeoutError,
    llm_step_timeout_message,
    reasoning_only_abort_s,
)
from core.llm.tool_calls import (
    extract_textual_tool_calls,
    looks_like_leaked_tool_markup,
    strip_tool_call_markup,
)
from core.llm.usage import (
    completion_text_from_message,
    emit_llm_call_usage,
    resolve_usage,
    usage_dict_from_response,
    usage_dict_from_stream_chunk,
)
from core.profile.soul import profile_name_from_agent
from core.prompt_builder import build_system_prompt, format_tools_description

logger = logging.getLogger(__name__)

_DEFAULT_LLM_STEP_TIMEOUT_S = 300.0


async def _compress_messages_if_needed(
    agent: Any,
    conversation_id: str,
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Compress in-graph history before an LLM step (not only after tools)."""
    if not agent or not getattr(agent, "context_manager", None):
        return messages, {}
    from core.runtime.context_session import compress_session_if_needed

    compressed, was_compressed = await compress_session_if_needed(
        agent,
        conversation_id,
        list(messages),
    )
    if was_compressed:
        return compressed, {"messages": compressed}
    return messages, {}


def _merge_state_patch(update: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    if not patch:
        return update
    return {**patch, **update}


async def _close_async_stream(stream: Any) -> None:
    """Best-effort close of an OpenAI/httpx streaming response."""
    for method_name in ("aclose", "close"):
        method = getattr(stream, method_name, None)
        if not callable(method):
            continue
        try:
            result = method()
            if asyncio.iscoroutine(result):
                await result
            else:
                # Sync close() can block on hung TCP streams and freeze the event loop.
                await asyncio.to_thread(method)
        except Exception:
            logger.debug("Failed to close LLM stream via %s", method_name, exc_info=True)
        return


async def _await_next_stream_chunk(stream: Any, timeout: float) -> Any:
    """Read one chunk without injecting exceptions into ``stream`` on timeout."""
    task = asyncio.create_task(anext(stream))
    try:
        return await asyncio.wait_for(task, timeout=timeout)
    except TimeoutError:
        await _close_async_stream(stream)
        task.cancel()
        try:
            await task
        except BaseException:
            pass
        raise
    except asyncio.CancelledError:
        task.cancel()
        try:
            await task
        except BaseException:
            pass
        await _close_async_stream(stream)
        raise
    except StopAsyncIteration:
        task.cancel()
        raise


async def _iter_stream_chunks(stream: Any, timeout_s: float) -> AsyncIterator[Any]:
    """Iterate stream chunks with a hard deadline and guaranteed stream cleanup."""
    deadline = time.monotonic() + timeout_s
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"LLM stream exceeded {timeout_s:.0f}s deadline")
            try:
                chunk = await _await_next_stream_chunk(stream, remaining)
            except StopAsyncIteration:
                break
            yield chunk
    except asyncio.CancelledError:
        await _close_async_stream(stream)
        raise
    finally:
        await _close_async_stream(stream)


def _non_empty_final(text: str, *, profile_name: str | None = None) -> str:
    """Ensure the user always sees something when a react step *truly* ends.

    Empty intermediate results should not become a fake final answer — callers
    must only use this when they are about to emit FinalResponseEvent.
    """
    cleaned = (text or "").strip()
    if cleaned:
        return cleaned
    return reasoning_only_user_message(profile_name=profile_name)


def _is_reasoning_only_placeholder(text: str) -> bool:
    """True for empty or i18n 'reasoning without visible answer' placeholders."""
    lowered = (text or "").strip().lower()
    if not lowered:
        return True
    markers = (
        "без видимого ответа",
        "without a visible answer",
        "finished reasoning without",
        "reasoning_only",
        "без текстового ответа",
    )
    return any(m in lowered for m in markers)


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
    # Reasoning-only model reply must never complete a plan step.
    if _is_reasoning_only_placeholder(final_response):
        if agent and hasattr(agent, "emit"):
            from core.agent_events import ThinkingEvent

            agent.emit(
                ThinkingEvent(
                    message=(
                        "Model returned reasoning without tools/text — "
                        "retrying current plan step with a stronger tool nudge"
                    ),
                    conversation_id=conversation_id,
                )
            )
        return plan_step_retry_update(
            messages=messages,
            step_count=step_count,
            final_response="",
            include_assistant=False,
        )
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


def _maybe_honesty_retry(
    state: HolixGraphState,
    *,
    messages: list[dict[str, Any]],
    step_count: int,
    final_response: str,
    assistant_already_appended: bool,
) -> dict[str, Any] | None:
    """Block final answers that claim success without tool evidence.

    SDD fill: after max nudges without sdd_write_artifact, replace the lie with
    an honest refusal instead of accepting the claim as final.
    """
    if should_nudge_false_completion(
        state,
        final_response=final_response,
        messages=messages,
    ):
        logger.warning(
            "Action honesty nudge: blocking unproven/empty-tools claim (conversation_id=%s)",
            state.get("conversation_id", ""),
        )
        return honesty_retry_update(
            messages=messages,
            step_count=step_count,
            final_response=final_response,
            honesty_nudge_count=int(state.get("honesty_nudge_count") or 0),
            include_assistant=not assistant_already_appended,
            user_input=state.get("user_input"),
        )
    if should_refuse_false_empty_workspace(
        state,
        final_response=final_response,
        messages=messages,
    ):
        logger.warning(
            "Action honesty refusal: model denied visible tool listings (conversation_id=%s)",
            state.get("conversation_id", ""),
        )
        return honesty_refusal_update(
            messages=messages,
            step_count=step_count,
            honesty_nudge_count=int(state.get("honesty_nudge_count") or 0),
            include_assistant=not assistant_already_appended,
            final_response=final_response,
            refusal=workspace_grounding_refusal_text(
                messages,
                tool_results=state.get("tool_results"),
            ),
        )
    if should_refuse_unproven_sdd_fill(
        state,
        final_response=final_response,
        messages=messages,
    ):
        logger.warning(
            "Action honesty refusal: SDD fill without sdd_write_artifact (conversation_id=%s)",
            state.get("conversation_id", ""),
        )
        return honesty_refusal_update(
            messages=messages,
            step_count=step_count,
            honesty_nudge_count=int(state.get("honesty_nudge_count") or 0),
            include_assistant=not assistant_already_appended,
            final_response=final_response,
        )
    if should_refuse_status_monologue(
        state,
        final_response=final_response,
        messages=messages,
    ):
        logger.warning(
            "Action honesty refusal: status monologue without tools (conversation_id=%s)",
            state.get("conversation_id", ""),
        )
        return honesty_refusal_update(
            messages=messages,
            step_count=step_count,
            honesty_nudge_count=int(state.get("honesty_nudge_count") or 0),
            include_assistant=not assistant_already_appended,
            final_response=final_response,
            refusal=MONOLOGUE_HONESTY_REFUSAL,
        )
    return None


def _llm_max_tokens(
    agent,
    model_manager,
    agent_slot: str,
    state: dict | None = None,
) -> int:
    from config import settings

    return resolve_agent_max_tokens(
        profile_max_tokens=profile_agent_max_tokens(model_manager, agent_slot),
        default_max_tokens=getattr(settings, "agent_max_tokens", None),
        chat_max_tokens=getattr(settings, "agent_chat_max_tokens", None),
        purpose=purpose_from_graph_state(state),
    )


def _agent_pipeline(state: dict | None, agent: Any | None = None) -> str:
    from core.agent_pipeline import pipeline_from_state

    cfg = getattr(agent, "config", None) if agent else None
    return pipeline_from_state(state if isinstance(state, dict) else None, cfg)


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
    """Emit a *terminal* final answer (hard errors only).

    Successful ReAct drafts must NOT call this. They set ``is_final`` /
    ``final_response`` and leave emission to ``run_graph_loop`` after Reflexion
    finishes. Emitting drafts early spammed messengers with monologue text
    ("Что сделаю… Начинаю") before tools ran.
    """
    if agent and hasattr(agent, "emit"):
        agent._final_response_emitted = True
        agent.emit(
            FinalResponseEvent(
                content=content,
                steps_taken=steps_taken,
                conversation_id=conversation_id,
            )
        )


def _emit_llm_usage(
    agent,
    *,
    model: str,
    step: int,
    conversation_id: str,
    usage: dict[str, int],
    duration_ms: float | None = None,
    finish_reason: str | None = None,
    estimated: bool = False,
) -> None:
    """Publish token usage for Studio dashboards (all agent tabs)."""
    emit_llm_call_usage(
        agent,
        model=model,
        step=step,
        conversation_id=conversation_id,
        usage=usage,
        duration_ms=duration_ms,
        finish_reason=finish_reason,
        estimated=estimated,
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

    # Auto-compress before each LLM step (tool-heavy runs can skip compress between react hops)
    messages = list(state.get("messages", []))
    messages, messages_patch = await _compress_messages_if_needed(agent, conversation_id, messages)

    # Build API messages
    if agent and hasattr(agent, "context_manager") and agent.context_manager:
        api_messages = _build_api_messages(system_prompt, messages, agent.context_manager)
    else:
        from core.llm.api_messages import prepare_conversation_for_llm

        api_messages = [
            {"role": "system", "content": system_prompt}
        ] + prepare_conversation_for_llm(messages[-20:])

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
        return _merge_state_patch(
            {
                "step_count": step_count,
                "is_final": True,
                "final_response": err,
            },
            messages_patch,
        )
    tools = agent.tools.get_schemas() if agent and hasattr(agent, "tools") else []
    tool_choice = resolve_tool_choice(state, messages, tools=tools)
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
        return _merge_state_patch(
            {
                "step_count": step_count,
                "is_final": True,
                "final_response": err,
            },
            messages_patch,
        )

    agent_slot = getattr(agent, "agent_slot", "main") if agent else "main"
    model_manager = getattr(agent, "model_manager", None) if agent else None
    primary_override = getattr(agent, "active_model_config", None) if agent else None
    llm_timeout_s = _llm_step_timeout_s(agent)
    max_tokens = _llm_max_tokens(agent, model_manager, agent_slot, state)

    def _on_fallback_switch(cfg) -> None:
        if agent and hasattr(agent, "set_active_model_config"):
            agent.set_active_model_config(cfg)

    try:
        if stream:
            result = await _react_streaming(
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
                primary_override=primary_override,
                on_switch=_on_fallback_switch,
                llm_timeout_s=llm_timeout_s,
                max_tokens=max_tokens,
                tool_choice=tool_choice,
            )
        else:
            result = await _react_non_streaming(
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
                primary_override=primary_override,
                on_switch=_on_fallback_switch,
                llm_timeout_s=llm_timeout_s,
                max_tokens=max_tokens,
                tool_choice=tool_choice,
            )
        from core.runtime.step_budget import maybe_extend_for_graph_result

        result = maybe_extend_for_graph_result(
            state,
            result,
            agent=agent,
            task=str(state.get("user_input") or ""),
        )
        return _merge_state_patch(result, messages_patch)

    except LLMStepTimeoutError as exc:
        err = exc.user_message
        logger.warning(
            "LLM reasoning-only abort (model=%s, step=%s)",
            model,
            step_count,
        )
        # During an active plan step: do not end the whole run with a scary chat
        # message — nudge tools and continue (GPU/tools may still be productive).
        if plan_step_active(state):
            if agent and hasattr(agent, "emit"):
                agent.emit(
                    ThinkingEvent(
                        message=("Model stuck in reasoning — retrying plan step with tool nudge"),
                        conversation_id=conversation_id,
                    )
                )
            messages = list(state.get("messages", []))
            retry = plan_step_retry_update(
                messages=messages,
                step_count=step_count,
                final_response="",
                include_assistant=False,
            )
            return _merge_state_patch(retry, messages_patch)
        _emit_final_response(
            agent,
            content=err,
            steps_taken=step_count,
            conversation_id=conversation_id,
        )
        return _merge_state_patch(
            {
                "step_count": step_count,
                "is_final": True,
                "final_response": err,
            },
            messages_patch,
        )
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
        return _merge_state_patch(
            {
                "step_count": step_count,
                "is_final": True,
                "final_response": err,
            },
            messages_patch,
        )
    except RuntimeError as e:
        if "generator didn't stop after athrow" in str(e):
            raise asyncio.CancelledError() from e
        raise
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Error in react_node: {e}")
        err = f"Error during agent step: {str(e)}"
        _emit_final_response(
            agent,
            content=err,
            steps_taken=step_count,
            conversation_id=conversation_id,
        )
        return _merge_state_patch(
            {
                "step_count": step_count,
                "is_final": True,
                "final_response": err,
            },
            messages_patch,
        )


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
    primary_override=None,
    on_switch=None,
    llm_timeout_s: float = _DEFAULT_LLM_STEP_TIMEOUT_S,
    max_tokens: int | None = None,
    tool_choice: str | dict[str, Any] = "auto",
) -> dict:
    """Non-streaming ReAct step."""
    conversation_id = state.get("conversation_id", "default")
    choice: str | dict[str, Any] = tool_choice or "auto"

    async def _call_llm(active_choice: str | dict[str, Any]):
        if model_manager:
            from core.models.fallback import chat_completions_with_fallback

            return await chat_completions_with_fallback(
                model_manager,
                agent_name=agent_slot,
                primary_override=primary_override,
                on_switch=on_switch,
                messages=api_messages,
                tools=tools,
                tool_choice=active_choice,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        return await client.chat.completions.create(
            model=model,
            messages=api_messages,
            tools=tools,
            tool_choice=active_choice,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    t0 = time.monotonic()
    async with asyncio.timeout(llm_timeout_s):
        try:
            response = await _call_llm(choice)
        except Exception as exc:
            if not _is_unsupported_tool_choice_error(exc, choice):
                raise
            logger.warning(
                "Backend rejected tool_choice=%r (model=%s); retrying with auto",
                choice,
                model,
            )
            choice = "auto"
            response = await _call_llm(choice)
        if (response is None or not getattr(response, "choices", None)) and _is_forced_tool_choice(
            choice
        ):
            logger.warning(
                "Empty LLM response for tool_choice=%r (model=%s); retrying with auto",
                choice,
                model,
            )
            choice = "auto"
            response = await _call_llm(choice)
    if response is None or not getattr(response, "choices", None):
        raise RuntimeError("LLM returned empty response")
    duration_ms = (time.monotonic() - t0) * 1000.0

    message = response.choices[0].message
    finish_reason = response.choices[0].finish_reason if response.choices else None
    provider_usage = usage_dict_from_response(response)
    usage = resolve_usage(
        response,
        messages=api_messages,
        completion_text=completion_text_from_message(message),
        model=model,
    )
    _emit_llm_usage(
        agent,
        model=model,
        step=step_count,
        conversation_id=conversation_id,
        usage=usage,
        duration_ms=duration_ms,
        finish_reason=finish_reason,
        estimated=provider_usage is None,
    )
    messages = list(state.get("messages", []))

    raw_assistant = message.content or ""
    scrubbed = scrub_false_empty_claim_content(
        raw_assistant,
        state.get("messages"),
        tool_results=state.get("tool_results"),
    )
    if scrubbed != raw_assistant and (raw_assistant or "").strip():
        logger.warning(
            "Scrubbed false empty-workspace claim from assistant+tools content "
            "(conversation_id=%s)",
            conversation_id,
        )
    msg_dict = {"role": "assistant", "content": scrubbed}

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
                agent.emit(
                    ToolCallStartEvent(
                        tool_name=tc.function.name,
                        tool_id=tc.id,
                        arguments_raw=tc.function.arguments,
                        conversation_id=conversation_id,
                    )
                )

        return {
            "messages": messages,
            "tool_calls": tool_calls,
            "step_count": step_count,
            "is_final": False,
        }

    recovered = _textual_tool_step_result(
        state=state,
        agent=agent,
        conversation_id=conversation_id,
        step_count=step_count,
        content=raw_assistant,
        tools=tools,
    )
    if recovered is not None:
        return recovered

    else:
        # Final answer
        msg_content, msg_reasoning = assistant_message_parts(message)
        finish_reason = response.choices[0].finish_reason if response.choices else None
        profile_name = profile_name_from_agent(agent) if agent else None
        final_response = resolve_assistant_text(
            content=msg_content,
            reasoning_content=msg_reasoning,
            finish_reason=finish_reason,
            model=model,
            profile_name=profile_name,
            agent_pipeline=_agent_pipeline(state, agent),
        )
        # Reasoning-only / empty: keep plan steps open; for free chat still finish
        # with a clear message only after we have nothing else to try.
        if plan_step_active(state) and not (final_response or "").strip():
            if agent and hasattr(agent, "emit"):
                agent.emit(
                    ThinkingEvent(
                        message="Model returned empty/reasoning-only — retrying plan step",
                        conversation_id=conversation_id,
                    )
                )
            return await _plan_step_result(
                state,
                agent=agent,
                conversation_id=conversation_id,
                messages=messages,
                step_count=step_count,
                final_response="",
                assistant_already_appended=False,
            )

        final_response = _non_empty_final(final_response, profile_name=profile_name)
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

        honesty = _maybe_honesty_retry(
            state,
            messages=messages,
            step_count=step_count,
            final_response=final_response,
            assistant_already_appended=True,
        )
        if honesty is not None:
            return honesty

        if agent and hasattr(agent, "memory"):
            await agent.memory.save_message(conversation_id, "assistant", final_response)

        # Do not emit FinalResponseEvent here — Reflexion may retry; the graph
        # loop emits a single final after the run completes.
        return {
            "messages": messages,
            "step_count": step_count,
            "is_final": True,
            "final_response": final_response,
            "tool_calls": [],
        }


def _has_streaming_tool_calls(tool_calls_dict: dict[int, dict[str, Any]]) -> bool:
    return any(
        (tc.get("function") or {}).get("name", "").strip() for tc in tool_calls_dict.values()
    )


def _is_forced_tool_choice(choice: str | dict[str, Any] | None) -> bool:
    if isinstance(choice, dict):
        return True
    return str(choice or "").strip().lower() not in {"", "auto", "none"}


def _is_unsupported_tool_choice_error(
    exc: BaseException,
    choice: str | dict[str, Any] | None,
) -> bool:
    """True when the backend rejected tool_choice=required / a forced function."""
    if not _is_forced_tool_choice(choice):
        return False
    status = getattr(exc, "status_code", None)
    if status in (400, 422):
        return True
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "tool_choice",
            "synthesised arguments",
            "schema-invalid tool call",
            "does not support",
            "invalid parameter",
        )
    )


def _textual_tool_step_result(
    *,
    state,
    agent,
    conversation_id: str,
    step_count: int,
    content: str,
    tools: list[Any] | None,
) -> dict[str, Any] | None:
    """Recover tool calls leaked as assistant text (Qwen/Hermes XML)."""
    calls = extract_textual_tool_calls(content, tools=tools)
    if not calls:
        return None
    visible = strip_tool_call_markup(content)
    logger.info(
        "Recovered %s textual tool call(s) from assistant content (conversation_id=%s)",
        len(calls),
        conversation_id,
    )
    return _streaming_tool_calls_step_result(
        state=state,
        agent=agent,
        conversation_id=conversation_id,
        step_count=step_count,
        current_content=visible,
        tool_calls_dict={idx: call for idx, call in enumerate(calls)},
    )


def _streaming_tool_calls_error(tool_calls_dict: dict[int, dict[str, Any]]) -> str | None:
    """Detect incomplete streamed tool JSON (common when finish_reason=length)."""
    if not _has_streaming_tool_calls(tool_calls_dict):
        return None
    for tc in tool_calls_dict.values():
        fn = tc.get("function") or {}
        name = (fn.get("name") or "").strip()
        args_raw = fn.get("arguments") or ""
        if not name:
            return (
                "Tool call incomplete (token limit). "
                "Use update_holix_section — one heading, under 30 lines."
            )
        try:
            json.loads(args_raw)
        except json.JSONDecodeError:
            return (
                f"`{name}` arguments truncated by token limit. "
                "Use update_holix_section with a short section body instead."
            )
    return None


def _tool_limit_nudge_result(
    state,
    *,
    step_count: int,
    error: str,
) -> dict[str, Any]:
    messages = list(state.get("messages", []))
    messages.append({"role": "user", "content": f"[System] {error}"})
    return {
        "messages": messages,
        "step_count": step_count,
        "is_final": False,
        "tool_calls": [],
    }


def _streaming_tool_step_or_nudge(
    *,
    state,
    agent,
    conversation_id: str,
    step_count: int,
    current_content: str,
    tool_calls_dict: dict[int, dict[str, Any]],
    finish_reason: str | None = None,
) -> dict[str, Any]:
    tool_err = _streaming_tool_calls_error(tool_calls_dict)
    if tool_err and finish_reason in ("length", "stop", "tool_calls", None):
        return _tool_limit_nudge_result(state, step_count=step_count, error=tool_err)
    return _streaming_tool_calls_step_result(
        state=state,
        agent=agent,
        conversation_id=conversation_id,
        step_count=step_count,
        current_content=current_content,
        tool_calls_dict=tool_calls_dict,
    )


def _streaming_tool_calls_step_result(
    *,
    state,
    agent,
    conversation_id: str,
    step_count: int,
    current_content: str,
    tool_calls_dict: dict[int, dict[str, Any]],
) -> dict:
    """Return a ReAct step that executes accumulated streaming tool calls."""
    tool_calls = list(tool_calls_dict.values())
    messages = list(state.get("messages", []))
    scrubbed = scrub_false_empty_claim_content(
        current_content,
        state.get("messages"),
        tool_results=state.get("tool_results"),
    )
    if scrubbed != (current_content or "") and (current_content or "").strip():
        logger.warning(
            "Scrubbed false empty-workspace claim from streaming assistant+tools "
            "(conversation_id=%s)",
            conversation_id,
        )
    messages.append(
        {
            "role": "assistant",
            "content": scrubbed,
            "tool_calls": tool_calls,
        }
    )

    for tc_data in tool_calls:
        if agent and hasattr(agent, "emit"):
            agent.emit(
                ToolCallStartEvent(
                    tool_name=tc_data["function"]["name"],
                    tool_id=tc_data["id"],
                    arguments_raw=tc_data["function"]["arguments"],
                    conversation_id=conversation_id,
                )
            )

    return {
        "messages": messages,
        "tool_calls": tool_calls,
        "step_count": step_count,
        "is_final": False,
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
    primary_override=None,
    on_switch=None,
    llm_timeout_s: float = _DEFAULT_LLM_STEP_TIMEOUT_S,
    max_tokens: int | None = None,
    tool_choice: str | dict[str, Any] = "auto",
) -> dict:
    """Streaming ReAct step."""
    conversation_id = state.get("conversation_id", "default")
    choice: str | dict[str, Any] = tool_choice or "auto"

    async def _open_stream():
        nonlocal choice
        kwargs: dict[str, Any] = {
            "messages": api_messages,
            "tools": tools,
            "tool_choice": choice,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        async def _create(llm_client, model_name: str):
            nonlocal choice
            try:
                return await llm_client.chat.completions.create(model=model_name, **kwargs)
            except TypeError:
                # Older/local clients may not accept stream_options
                kwargs.pop("stream_options", None)
                return await llm_client.chat.completions.create(model=model_name, **kwargs)
            except Exception as exc:
                # Some OpenAI-compatible servers reject stream_options
                if "stream_options" in kwargs and "stream_options" in str(exc).lower():
                    kwargs.pop("stream_options", None)
                    return await llm_client.chat.completions.create(model=model_name, **kwargs)
                if _is_unsupported_tool_choice_error(exc, kwargs.get("tool_choice")):
                    logger.warning(
                        "Backend rejected streaming tool_choice=%r (model=%s); retrying with auto",
                        kwargs.get("tool_choice"),
                        model_name,
                    )
                    kwargs["tool_choice"] = "auto"
                    choice = "auto"
                    return await llm_client.chat.completions.create(model=model_name, **kwargs)
                raise

        if model_manager:
            from core.models.fallback import run_with_provider_fallback

            return await run_with_provider_fallback(
                model_manager,
                agent_name=agent_slot,
                primary_override=primary_override,
                on_switch=on_switch,
                factory=lambda cfg, llm_client: _create(llm_client, cfg.model),
            )
        return await _create(client, model)

    current_content = ""
    current_reasoning = ""
    tool_calls_dict: dict[int, dict[str, Any]] = {}
    last_finish_reason: str | None = None
    reasoning_status_emitted = False
    reasoning_only_deadline: float | None = None
    stream_usage: dict[str, int] | None = None
    stream_t0 = time.monotonic()
    stream_usage_emitted = False

    def _emit_stream_usage_once(*, completion_text: str = "") -> None:
        nonlocal stream_usage_emitted
        if stream_usage_emitted:
            return
        stream_usage_emitted = True
        # Prefer provider usage; otherwise estimate from prompt + streamed text/tools.
        tool_blob = ""
        if tool_calls_dict:
            parts: list[str] = []
            for item in tool_calls_dict.values():
                fn = (item or {}).get("function") or {}
                parts.append(str(fn.get("name") or ""))
                parts.append(str(fn.get("arguments") or ""))
            tool_blob = "\n".join(parts)
        text = (completion_text or current_content or current_reasoning or tool_blob or "").strip()
        usage = resolve_usage(
            messages=api_messages,
            completion_text=text,
            model=model,
            stream_usage=stream_usage,
        )
        _emit_llm_usage(
            agent,
            model=model,
            step=step_count,
            conversation_id=conversation_id,
            usage=usage,
            duration_ms=(time.monotonic() - stream_t0) * 1000.0,
            finish_reason=last_finish_reason,
            estimated=stream_usage is None,
        )

    stream_response = await _open_stream()
    async for chunk in _iter_stream_chunks(stream_response, llm_timeout_s):
        chunk_usage = usage_dict_from_stream_chunk(chunk)
        if chunk_usage:
            stream_usage = chunk_usage
        if not getattr(chunk, "choices", None):
            continue
        delta = chunk.choices[0].delta
        content_delta, reasoning_delta = stream_delta_parts(delta)

        # Content / reasoning streaming (reasoning models may only fill reasoning_*)
        if content_delta:
            current_content += content_delta
            # Abort runaway model loops early (ABAB monologue, glued «…Поняла»).
            if len(current_content) >= 80 and is_pathological_repetition(
                current_content, min_repeats=3
            ):
                before = len(current_content)
                current_content = collapse_repetitive_text(current_content)
                if len(current_content) > 400 and is_pathological_repetition(
                    current_content, min_repeats=3
                ):
                    from core.llm.response_text import _hard_trim_loop

                    current_content = _hard_trim_loop(current_content)
                logger.warning(
                    "Aborted streaming content loop (model=%s, step=%s, %s→%s chars)",
                    model,
                    step_count,
                    before,
                    len(current_content),
                )
                last_finish_reason = last_finish_reason or "stop"
                # Do not emit further monologue deltas — final path sanitizes again.
                break
            # After successful listings, buffer text until the step finishes so
            # «Список пуст…» is not painted into Studio before we can scrub it.
            prior_listing = has_successful_workspace_listing(
                state.get("messages"),
                tool_results=state.get("tool_results"),
            )
            # Buffer pure status monologue («Да. Смотрю…») — do not spam Studio UI.
            # Honesty will force tools or refuse; painting deltas makes loops look worse.
            buffer_status_mono = not tool_calls_dict and looks_like_status_monologue(
                current_content
            )
            # Do not paint ``tool_call`` / ``<tool_call>`` fences into Studio.
            buffer_tool_markup = looks_like_leaked_tool_markup(current_content)
            if (
                agent
                and hasattr(agent, "emit")
                and not prior_listing
                and not buffer_status_mono
                and not buffer_tool_markup
            ):
                agent.emit(
                    AssistantDeltaEvent(
                        content=content_delta,
                        accumulated=current_content,
                        conversation_id=conversation_id,
                    )
                )
        if reasoning_delta:
            # Reasoning is internal; do not stream it to messenger progress UIs.
            current_reasoning += reasoning_delta
            if reasoning_only_deadline is None:
                reasoning_only_deadline = time.monotonic() + reasoning_only_abort_s(llm_timeout_s)
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

        if finish_reason in ("stop", "tool_calls", "length") and _has_streaming_tool_calls(
            tool_calls_dict
        ):
            _emit_stream_usage_once()
            return _streaming_tool_step_or_nudge(
                state=state,
                agent=agent,
                conversation_id=conversation_id,
                step_count=step_count,
                current_content=current_content,
                tool_calls_dict=tool_calls_dict,
                finish_reason=finish_reason,
            )

        if finish_reason in ("stop", "length"):
            recovered = _textual_tool_step_result(
                state=state,
                agent=agent,
                conversation_id=conversation_id,
                step_count=step_count,
                content=current_content,
                tools=tools,
            )
            if recovered is not None:
                _emit_stream_usage_once()
                return recovered
            # finish_reason=length: model hit max_tokens — often mid monologue loop.
            # Resolve + honesty before accepting as final (same path as stop).
            _pipe = _agent_pipeline(state, agent)
            visible_content = strip_tool_call_markup(current_content) or current_content
            final_response = resolve_assistant_text(
                content=visible_content,
                reasoning_content=current_reasoning,
                finish_reason=finish_reason,
                model=model,
                profile_name=profile_name_from_agent(agent) if agent else None,
                agent_pipeline=_pipe,
            )
            if not (final_response or "").strip():
                if finish_reason == "length":
                    # Explicit truncation notice already preferred; if empty, stop.
                    from core.llm.response_text import reasoning_only_user_message

                    final_response = resolve_assistant_text(
                        content="",
                        finish_reason="length",
                        model=model,
                        profile_name=profile_name_from_agent(agent) if agent else None,
                        agent_pipeline=_pipe,
                    ) or reasoning_only_user_message(
                        profile_name=profile_name_from_agent(agent) if agent else None
                    )
                else:
                    logger.warning(
                        "Empty streaming LLM response (model=%s); retrying non-streaming",
                        model,
                    )
                    # Non-streaming retry will emit its own usage event.
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
                        llm_timeout_s=min(45.0, llm_timeout_s),
                        max_tokens=max_tokens,
                    )
            messages = list(state.get("messages", []))
            # If we buffered stream text after listings, scrub before finalizing.
            final_response = (
                scrub_false_empty_claim_content(
                    final_response,
                    state.get("messages"),
                    tool_results=state.get("tool_results"),
                )
                or final_response
            )
            messages.append({"role": "assistant", "content": final_response})

            if agent and hasattr(agent, "memory"):
                await agent.memory.save_message(conversation_id, "assistant", final_response)

            if plan_step_active(state):
                _emit_stream_usage_once(completion_text=final_response)
                return await _plan_step_result(
                    state,
                    agent=agent,
                    conversation_id=conversation_id,
                    messages=messages,
                    step_count=step_count,
                    final_response=final_response,
                    assistant_already_appended=True,
                )

            honesty = _maybe_honesty_retry(
                state,
                messages=messages,
                step_count=step_count,
                final_response=final_response,
                assistant_already_appended=True,
            )
            if honesty is not None:
                _emit_stream_usage_once(completion_text=final_response)
                return honesty

            if agent and hasattr(agent, "memory"):
                await agent.memory.save_message(conversation_id, "assistant", final_response)

            _emit_stream_usage_once(completion_text=final_response)
            # Emit full text now if we suppressed live deltas after tool listings.
            if (
                has_successful_workspace_listing(
                    state.get("messages"),
                    tool_results=state.get("tool_results"),
                )
                and (final_response or "").strip()
            ):
                if agent and hasattr(agent, "emit"):
                    agent.emit(
                        AssistantDeltaEvent(
                            content=final_response,
                            accumulated=final_response,
                            conversation_id=conversation_id,
                        )
                    )
            # Defer FinalResponseEvent to run_graph_loop (after Reflexion).
            return {
                "messages": messages,
                "step_count": step_count,
                "is_final": True,
                "final_response": final_response,
                "tool_calls": [],
            }

        elif finish_reason == "tool_calls":
            _emit_stream_usage_once()
            return _streaming_tool_step_or_nudge(
                state=state,
                agent=agent,
                conversation_id=conversation_id,
                step_count=step_count,
                current_content=current_content,
                tool_calls_dict=tool_calls_dict,
                finish_reason=finish_reason,
            )

    if _has_streaming_tool_calls(tool_calls_dict):
        _emit_stream_usage_once()
        return _streaming_tool_step_or_nudge(
            state=state,
            agent=agent,
            conversation_id=conversation_id,
            step_count=step_count,
            current_content=current_content,
            tool_calls_dict=tool_calls_dict,
            finish_reason=last_finish_reason,
        )

    recovered = _textual_tool_step_result(
        state=state,
        agent=agent,
        conversation_id=conversation_id,
        step_count=step_count,
        content=current_content,
        tools=tools,
    )
    if recovered is not None:
        _emit_stream_usage_once()
        return recovered

    # Stream ended without an explicit finish_reason — treat as final
    visible_content = strip_tool_call_markup(current_content) or current_content
    final_response = resolve_assistant_text(
        content=visible_content,
        reasoning_content=current_reasoning,
        finish_reason=last_finish_reason,
        model=model,
        profile_name=profile_name_from_agent(agent) if agent else None,
        agent_pipeline=_agent_pipeline(state, agent),
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
            llm_timeout_s=min(45.0, llm_timeout_s),
            max_tokens=max_tokens,
        )
    final_response = _non_empty_final(final_response)
    messages = list(state.get("messages", []))
    messages.append({"role": "assistant", "content": final_response})
    _emit_stream_usage_once(completion_text=final_response)

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

    honesty = _maybe_honesty_retry(
        state,
        messages=messages,
        step_count=step_count,
        final_response=final_response,
        assistant_already_appended=True,
    )
    if honesty is not None:
        return honesty

    if agent and hasattr(agent, "memory"):
        await agent.memory.save_message(conversation_id, "assistant", final_response)

    # Defer FinalResponseEvent to run_graph_loop (after Reflexion).
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
        strategies_text = agent.memory.strategic.format_strategies_for_prompt(relevant_strategies)

    # Combine memories
    combined_memories = memories_text
    if strategies_text:
        combined_memories = (
            f"{memories_text}\n\n{strategies_text}" if memories_text else strategies_text
        )

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
                prev_steps.append(f"  Step {s.get('step', i + 1)}: {s.get('description', '')[:80]}")
            plan_context += "\n## Previous Steps Completed\n" + "\n".join(prev_steps) + "\n"

    # Append plan context to combined memories
    if plan_context:
        combined_memories = (
            f"{combined_memories}\n{plan_context}" if combined_memories else plan_context
        )

    # Meta-agent strategic hint (pre-thinking)
    meta = state.get("meta_decision") or {}
    if isinstance(meta, dict):
        hint = str(meta.get("context_hint") or "").strip()
        if hint:
            block = f"\n\n## Meta-agent guidance\n{hint}\n"
            combined_memories = (
                f"{combined_memories}{block}" if combined_memories else block.strip()
            )

    # Prior Reflexion notes this turn (verbal self-reflection memory)
    reflection_log = list(state.get("reflection_log") or [])
    if reflection_log:
        last = reflection_log[-1]
        areas = ", ".join(last.get("improvement_areas") or []) or "quality"
        refl = (
            f"\n\n## Prior self-reflection (this turn)\n"
            f"Last quality≈{last.get('quality_score', '?')}; focus on: {areas}.\n"
            f"{(last.get('refinement_prompt') or last.get('reasoning') or '')[:400]}\n"
        )
        combined_memories = f"{combined_memories}{refl}" if combined_memories else refl.strip()

    profile_name = profile_name_from_agent(agent) if agent else "default"
    agent_config = getattr(agent, "config", None) if agent else None
    persona_name = getattr(agent, "studio_agent_type", None) if agent else None
    persona_prompt = getattr(agent, "studio_persona_prompt", None) if agent else None
    if persona_name in (None, "", "main"):
        persona_name = None
        persona_prompt = None
    return build_system_prompt(
        tools_description=tools_desc,
        active_skills=relevant_skills,
        skills_formatted=skills_formatted,
        relevant_memories=combined_memories,
        profile_name=profile_name,
        workspace_root=getattr(agent_config, "workspace_root", None),
        workspace_jail_enabled=getattr(agent_config, "workspace_jail_enabled", None),
        persona_name=persona_name,
        persona_prompt=persona_prompt,
    )


def _build_api_messages(system_prompt, messages, context_manager) -> list:
    """Build API message list respecting context window limits."""
    from core.llm.api_messages import prepare_conversation_for_llm

    system_msg = {"role": "system", "content": system_prompt}
    history = prepare_conversation_for_llm(messages)
    system_tokens = context_manager.token_counter.count_message_tokens([system_msg])

    response_reserve = 2048
    available_tokens = context_manager.context_window - system_tokens - response_reserve

    if available_tokens <= 0:
        return [system_msg]

    selected = []
    running_tokens = 0

    for msg in reversed(history):
        msg_tokens = context_manager.token_counter.count_message_tokens([msg])
        if running_tokens + msg_tokens > available_tokens:
            break
        selected.append(msg)
        running_tokens += msg_tokens

    selected.reverse()
    from core.llm.api_messages import finalize_api_messages

    return [system_msg] + finalize_api_messages(selected)
