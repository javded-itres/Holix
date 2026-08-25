"""
Async Sub-Agent Runner — executes sub-agents as asyncio.Tasks within the main process.

Best for I/O-bound tasks (LLM calls, web searches, file reads).
Zero overhead on startup, shared memory access, fast communication.
"""

import asyncio
import inspect
import logging
import time
from typing import Any

from core.subagents.base import (
    MemoryAccess,
    SubAgentConfig,
    SubAgentHandle,
    SubAgentResult,
    SubAgentStatus,
)
from core.subagents.communication import AsyncCommunicationBus
from core.tools.execution_context import reset_subagent_scope, subagent_scope

logger = logging.getLogger(__name__)


class AsyncSubAgentRunner:
    """Runs a sub-agent as an asyncio.Task within the main process.

    The sub-agent gets:
    - Its own OpenAI client (same base_url/api_key as parent)
    - A subset of tools from the parent's ToolRegistry
    - Access to shared or readonly LTM (via parent's LongTermMemoryManager)
    - Communication via the AsyncCommunicationBus
    """

    def __init__(
        self,
        parent_agent: Any,
        comm_bus: AsyncCommunicationBus | None = None,
    ):
        self._parent = parent_agent
        self._comm_bus = comm_bus
        self._active_handles: dict[str, SubAgentHandle] = {}

    async def run(
        self,
        config: SubAgentConfig,
        task: str,
    ) -> SubAgentHandle:
        """Launch a sub-agent as an asyncio.Task.

        Args:
            config: Sub-agent configuration.
            task: The task description to execute.

        Returns:
            SubAgentHandle for tracking.
        """
        handle = SubAgentHandle(
            name=config.name,
            config=config,
            status=SubAgentStatus.RUNNING,
            started_at=time.monotonic(),
            max_steps=int(config.max_steps or 0),
        )

        # Create the asyncio task
        coro = self._run_sub_agent(config, task, handle)
        handle.task = asyncio.create_task(coro)

        self._active_handles[config.name] = handle
        return handle

    async def _run_sub_agent(
        self,
        config: SubAgentConfig,
        task: str,
        handle: SubAgentHandle,
    ) -> SubAgentResult:
        """Internal: run the sub-agent loop.

        This is a simplified ReAct loop specialized for the sub-agent.
        It uses the parent's LLM client but with the sub-agent's
        system prompt and tool subset.

        Args:
            config: Sub-agent configuration.
            task: Task description.
            handle: Handle to update with results.

        Returns:
            SubAgentResult with the sub-agent's output.
        """
        start_time = time.monotonic()
        tool_calls_made: list[dict[str, Any]] = []
        steps_taken = 0
        max_steps = int(config.max_steps or 0)
        base_max_steps = max_steps
        step_budget_extensions = 0

        from core.agent import HolixAgent

        if isinstance(self._parent, HolixAgent):
            try:
                return await self._run_via_react(config, task, handle, start_time)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Holix ReAct sub-agent '%s' failed; falling back to legacy loop",
                    config.name,
                )

        # Build client (inherit from parent or use config override)
        model = config.model or self._parent.model
        client = self._parent.client

        # Build tool subset
        tools_schemas = self._get_tool_schemas(config)

        # Build system prompt (include skills scoped to this subagent)
        skills_block = ""
        if hasattr(self._parent, "skills"):
            try:
                skills_block = self._parent.skills.skills_prompt_block(
                    task,
                    agent_slot=config.agent_type or config.name,
                )
            except Exception as e:
                logger.debug(f"Skill injection failed for sub-agent: {e}")

        parent_cfg = getattr(self._parent, "config", None)
        profile_name = str(getattr(parent_cfg, "profile_name", None) or "default")
        from core.sdd.change_workspace import overlay_workspace_root
        from core.subagents.prompt import build_subagent_system_prompt
        from core.tools.execution_context import get_conversation_id

        child_ws = overlay_workspace_root(profile_name, get_conversation_id()) or getattr(
            parent_cfg, "workspace_root", None
        )
        system_prompt = build_subagent_system_prompt(
            config,
            task,
            skills_block=skills_block,
            profile_name=profile_name,
            workspace_root=child_ws,
            workspace_jail_enabled=getattr(parent_cfg, "workspace_jail_enabled", None),
        )

        # Build messages
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]
        seed = list(getattr(config, "seed_messages", None) or [])
        if seed:
            from core.subagents.fork import insert_seed_messages

            messages = insert_seed_messages(messages, seed)

        # Inject relevant memories if shared access
        if config.memory_access != MemoryAccess.ISOLATED and hasattr(self._parent, "memory"):
            try:
                context = await self._parent.memory.get_relevant_context(task, top_k=3)
                memory_parts = []
                for ep in context.get("episodic", []):
                    memory_parts.append(f"[Past experience]: {ep.get('content', '')[:200]}")
                for fact in context.get("semantic", []):
                    memory_parts.append(f"[Fact]: {fact.get('content', '')[:200]}")
                if memory_parts:
                    messages.append(
                        {
                            "role": "system",
                            "content": "Relevant context from memory:\n" + "\n".join(memory_parts),
                        }
                    )
            except Exception as e:
                logger.debug(f"Memory injection failed for sub-agent: {e}")

        # ReAct loop
        tokens_used = 0
        llm_calls = 0
        leak_retries = 0
        empty_final_retries = 0
        usage_accounted = True  # flipped False if any call fails to emit

        def _usage_fields() -> dict[str, Any]:
            return {
                "tokens_used": tokens_used,
                "llm_calls": llm_calls,
                "usage_accounted": bool(usage_accounted and llm_calls > 0),
                "model": str(model or ""),
            }

        try:
            from core.runtime.step_budget import StepBudgetPolicy, evaluate_step_budget

            step_policy = StepBudgetPolicy.from_config(parent_cfg)

            while True:
                while steps_taken < max_steps:
                    wait_pause = getattr(handle, "wait_while_paused", None)
                    if inspect.iscoroutinefunction(wait_pause):
                        await wait_pause()
                    steps_taken += 1
                    handle.max_steps = max_steps
                    handle.record_activity(
                        "step",
                        f"Reasoning step {steps_taken}/{max_steps}",
                        steps_taken=steps_taken,
                    )
                    self._notify_progress(config.name)

                    # Runtime supervisor guidance (same job course-correction)
                    try:
                        from core.subagents.supervisor import (
                            drain_guidance_messages,
                            format_guidance_system_message,
                        )

                        if self._comm_bus is not None:
                            guidance_texts = await drain_guidance_messages(
                                self._comm_bus.receive,
                                config.name,
                            )
                            gmsg = format_guidance_system_message(guidance_texts)
                            if gmsg:
                                messages.append({"role": "system", "content": gmsg})
                                handle.record_activity(
                                    "status",
                                    "Applied supervisor guidance",
                                    steps_taken=steps_taken,
                                )
                    except Exception:
                        logger.debug(
                            "sub-agent guidance drain failed",
                            exc_info=True,
                        )

                    # Set up timeout
                    llm_t0 = time.monotonic()
                    try:
                        force_final = bool(getattr(handle, "_force_final_answer", False))
                        force_native = bool(getattr(handle, "_force_native_tools", False))
                        use_tools = tools_schemas if tools_schemas and not force_final else None
                        if force_final:
                            choice: str | None = "none"
                        elif force_native and use_tools:
                            choice = "required"
                        elif use_tools:
                            choice = "auto"
                        else:
                            choice = None
                        from core.llm.completion import (
                            EMPTY_LLM_ERROR,
                            first_choice_message,
                            is_empty_llm_response,
                        )

                        async def _llm_once(tool_choice: str | None):
                            return await asyncio.wait_for(
                                client.chat.completions.create(
                                    model=model,
                                    messages=messages,
                                    tools=use_tools,
                                    tool_choice=tool_choice,
                                    temperature=config.temperature,
                                ),
                                timeout=config.timeout,
                            )

                        response = None
                        last_choice = choice
                        for attempt in range(3):
                            try:
                                response = await _llm_once(last_choice)
                            except Exception as exc:
                                if attempt == 0 and last_choice == "required" and use_tools:
                                    logger.debug(
                                        "tool_choice=required rejected, falling back to auto: %s",
                                        exc,
                                    )
                                    last_choice = "auto"
                                    response = await _llm_once("auto")
                                else:
                                    raise
                            if not is_empty_llm_response(response):
                                break
                            handle.record_activity(
                                "status",
                                f"Empty LLM response, retry {attempt + 1}/3",
                                steps_taken=steps_taken,
                            )
                            await asyncio.sleep(0.4 * (attempt + 1))
                    except TimeoutError:
                        handle.status = SubAgentStatus.TIMED_OUT
                        handle.record_activity(
                            "status",
                            f"Timed out after {config.timeout}s",
                            steps_taken=steps_taken,
                        )
                        handle.result = SubAgentResult(
                            name=config.name,
                            success=False,
                            error=f"Sub-agent timed out after {config.timeout}s",
                            duration_ms=(time.monotonic() - start_time) * 1000,
                            steps_taken=steps_taken,
                            tool_calls=tool_calls_made,
                            **_usage_fields(),
                        )
                        return handle.result

                    message = first_choice_message(response)
                    if message is None:
                        handle.status = SubAgentStatus.FAILED
                        handle.record_activity(
                            "status",
                            "Failed: empty LLM response",
                            steps_taken=steps_taken,
                        )
                        handle.result = SubAgentResult(
                            name=config.name,
                            success=False,
                            error=EMPTY_LLM_ERROR,
                            duration_ms=(time.monotonic() - start_time) * 1000,
                            steps_taken=steps_taken,
                            tool_calls=tool_calls_made,
                            **_usage_fields(),
                        )
                        return handle.result
                    llm_duration_ms = (time.monotonic() - llm_t0) * 1000
                    try:
                        from core.llm.usage import (
                            completion_text_from_message,
                            emit_llm_call_usage,
                            resolve_usage,
                        )

                        usage = resolve_usage(
                            response,
                            messages=messages,
                            completion_text=completion_text_from_message(message),
                            model=model,
                        )
                        tokens_used += int(usage.get("total_tokens") or 0)
                        llm_calls += 1
                        finish_reason = None
                        try:
                            choices = getattr(response, "choices", None) or []
                            if choices:
                                finish_reason = getattr(choices[0], "finish_reason", None)
                        except Exception:
                            finish_reason = None
                        # Parent bus → Studio token_usage_handler (model.calls + tokens)
                        emitted = emit_llm_call_usage(
                            self._parent,
                            model=str(model or ""),
                            step=steps_taken,
                            usage=usage,
                            duration_ms=llm_duration_ms,
                            finish_reason=finish_reason,
                            operation_name="subagent.chat",
                        )
                        if emitted <= 0 and int(usage.get("total_tokens") or 0) > 0:
                            usage_accounted = False
                    except Exception:
                        usage_accounted = False
                        logger.debug("Sub-agent token accounting failed", exc_info=True)

                    native_calls = list(message.tool_calls or [])
                    final_override: str | None = None
                    if not native_calls:
                        from core.llm.tool_calls import (
                            resolve_textual_turn,
                            tool_call_objects,
                        )

                        turn = resolve_textual_turn(
                            message.content,
                            tools=tools_schemas,
                            force_final=force_final,
                        )
                        if turn.kind == "tools":
                            native_calls = tool_call_objects(turn.tool_calls)
                            handle._force_native_tools = False
                            handle.record_activity(
                                "status",
                                f"Recovered {len(native_calls)} textual tool call(s)",
                                steps_taken=steps_taken,
                            )
                        elif turn.kind == "retry":
                            leak_retries += 1
                            handle._force_native_tools = True
                            messages.append(
                                {
                                    "role": "assistant",
                                    "content": message.content or "",
                                }
                            )
                            messages.append(
                                {
                                    "role": "system",
                                    "content": turn.nudge,
                                }
                            )
                            handle.record_activity(
                                "status",
                                "Rejected leaked/broken tool_call as final",
                                details=(message.content or "")[:240],
                                steps_taken=steps_taken,
                            )
                            if leak_retries >= 2:
                                handle.status = SubAgentStatus.FAILED
                                handle.result = SubAgentResult(
                                    name=config.name,
                                    success=False,
                                    error=(
                                        "leaked tool_call: model emitted broken "
                                        "<tool_call> text instead of a native tool "
                                        "call or a final answer"
                                    ),
                                    response=str(message.content or ""),
                                    duration_ms=(time.monotonic() - start_time) * 1000,
                                    steps_taken=steps_taken,
                                    tool_calls=tool_calls_made,
                                    **_usage_fields(),
                                )
                                handle.record_activity(
                                    "status",
                                    "Failed: leaked tool_call",
                                    steps_taken=steps_taken,
                                )
                                return handle.result
                            continue
                        else:
                            final_override = turn.final_text

                    if native_calls:
                        handle._force_native_tools = False
                        # Execute tool calls
                        msg_dict = {
                            "role": "assistant",
                            "content": message.content or "",
                            "tool_calls": [
                                {
                                    "id": tc.id,
                                    "type": tc.type,
                                    "function": {
                                        "name": tc.function.name,
                                        "arguments": tc.function.arguments,
                                    },
                                }
                                for tc in native_calls
                            ],
                        }
                        messages.append(msg_dict)

                        for tc in native_calls:
                            tool_name = tc.function.name
                            tool_calls_made.append(
                                {
                                    "name": tool_name,
                                    "arguments": tc.function.arguments,
                                }
                            )
                            handle.record_activity(
                                "tool_start",
                                f"Calling {tool_name}",
                                tool_name=tool_name,
                                details=(tc.function.arguments or "")[:300],
                                steps_taken=steps_taken,
                            )
                            self._notify_progress(config.name)
                            result = await self._execute_tool(tc, config)
                            preview = (result or "").strip()
                            if len(preview) > 240:
                                preview = preview[:239] + "…"
                            tool_calls_made[-1]["result"] = result
                            handle.record_activity(
                                "tool_result",
                                f"{tool_name} finished",
                                tool_name=tool_name,
                                details=preview,
                                steps_taken=steps_taken,
                            )
                            self._notify_progress(config.name)
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc.id,
                                    "name": tool_name,
                                    "content": result,
                                }
                            )
                        try:
                            from core.runtime.test_run_signals import (
                                extract_command,
                                is_green_test_output,
                                is_test_command,
                            )

                            green_n = 0
                            for call in tool_calls_made:
                                name = str(call.get("name") or "").lower()
                                if name not in {"terminal", "run_terminal_command"}:
                                    continue
                                if is_test_command(extract_command(call.get("arguments"))):
                                    if is_green_test_output(str(call.get("result") or "")):
                                        green_n += 1
                            if green_n >= 1:
                                messages.append(
                                    {
                                        "role": "system",
                                        "content": (
                                            "### Tests already passed\n"
                                            "Automated tests succeeded. Do not run pytest "
                                            "or grep tests again. If the task is done, "
                                            "reply with the final answer and NO tool calls "
                                            "so the Studio process can continue."
                                        ),
                                    }
                                )
                            if green_n >= 2:
                                handle._force_final_answer = True
                                handle.record_activity(
                                    "status",
                                    "Tests already green — forcing final answer",
                                    steps_taken=steps_taken,
                                )
                            from core.runtime.write_signals import is_noop_write_result

                            noop_n = 0
                            for call in tool_calls_made[-6:]:
                                name = str(call.get("name") or "").lower()
                                if name in {"write_file", "patch_file"} and is_noop_write_result(
                                    str(call.get("result") or "")
                                ):
                                    noop_n += 1
                            if noop_n >= 2:
                                messages.append(
                                    {
                                        "role": "system",
                                        "content": (
                                            "### Files already match disk\n"
                                            "write_file returned «no content changes». "
                                            "Do not rewrite those files. "
                                            "Run pytest once if needed, then the final "
                                            "answer with NO tool calls."
                                        ),
                                    }
                                )
                            if noop_n >= 3:
                                handle._force_final_answer = True
                                handle.record_activity(
                                    "status",
                                    "No-op write_file loop — forcing final answer",
                                    steps_taken=steps_taken,
                                )
                            # Same terminal command failing over and over (e.g. false
                            # "use start_background_process" reject) — stop the spin.
                            tails = [
                                (
                                    str(c.get("name") or ""),
                                    str(c.get("arguments") or ""),
                                    str(c.get("result") or "")[:80],
                                )
                                for c in tool_calls_made[-3:]
                            ]
                            if (
                                len(tails) >= 3
                                and tails[-1] == tails[-2] == tails[-3]
                                and tails[-1][0].lower() in {"terminal", "run_terminal_command"}
                                and tails[-1][2].lower().startswith("error")
                            ):
                                handle._force_final_answer = True
                                messages.append(
                                    {
                                        "role": "system",
                                        "content": (
                                            "### Stop repeating the same terminal command\n"
                                            "It already failed the same way. Do not call it again. "
                                            "Write the final answer (what is done / what is blocked) "
                                            "with NO tool calls so the process can continue."
                                        ),
                                    }
                                )
                                handle.record_activity(
                                    "status",
                                    "Identical terminal error — forcing final answer",
                                    steps_taken=steps_taken,
                                )
                        except Exception:
                            logger.debug("green-test finish hint failed", exc_info=True)
                    else:
                        # Final response
                        from core.llm.completion import (
                            EMPTY_FINAL_CONTINUE,
                            is_blank_final_text,
                        )

                        final_response = (
                            final_override
                            if final_override is not None
                            else (message.content or "")
                        )
                        if is_blank_final_text(final_response) or is_blank_final_text(
                            message.content
                        ):
                            empty_final_retries += 1
                            messages.append(
                                {
                                    "role": "assistant",
                                    "content": (message.content or "").strip(),
                                }
                            )
                            messages.append(
                                {
                                    "role": "system",
                                    "content": EMPTY_FINAL_CONTINUE,
                                }
                            )
                            handle.record_activity(
                                "status",
                                f"Empty model reply — continue {empty_final_retries}/3",
                                steps_taken=steps_taken,
                            )
                            if empty_final_retries >= 3:
                                handle.status = SubAgentStatus.FAILED
                                handle.result = SubAgentResult(
                                    name=config.name,
                                    success=False,
                                    error="empty LLM reply (no text, no tools)",
                                    duration_ms=(time.monotonic() - start_time) * 1000,
                                    steps_taken=steps_taken,
                                    tool_calls=tool_calls_made,
                                    **_usage_fields(),
                                )
                                handle.record_activity(
                                    "status",
                                    "Failed: empty LLM reply",
                                    steps_taken=steps_taken,
                                )
                                return handle.result
                            continue

                        messages.append({"role": "assistant", "content": final_response})

                        duration_ms = (time.monotonic() - start_time) * 1000
                        handle.status = SubAgentStatus.COMPLETED
                        handle.record_activity(
                            "status",
                            "Completed",
                            steps_taken=steps_taken,
                        )
                        handle.result = SubAgentResult(
                            name=config.name,
                            success=True,
                            response=final_response,
                            duration_ms=duration_ms,
                            steps_taken=steps_taken,
                            tool_calls=tool_calls_made,
                            **_usage_fields(),
                        )
                        await self._propose_skill_after_success(
                            config=config,
                            client=client,
                            model=str(model or ""),
                            messages=messages,
                            final_response=final_response,
                            handle=handle,
                        )
                        logger.info(
                            "Sub-agent '%s' completed (steps=%d, tools=%d, %.0fms)",
                            config.name,
                            steps_taken,
                            len(tool_calls_made),
                            duration_ms,
                        )
                        return handle.result

                # Max steps: health-check — extend if still working with relevant progress
                decision = evaluate_step_budget(
                    step_count=steps_taken,
                    max_steps=max_steps,
                    extensions_used=step_budget_extensions,
                    messages=messages,
                    tool_calls_log=tool_calls_made,
                    task=task,
                    policy=step_policy,
                    base_max_steps=base_max_steps,
                )
                if decision.extend:
                    prev = max_steps
                    max_steps = decision.new_max_steps
                    step_budget_extensions = decision.extensions_used
                    handle.max_steps = max_steps
                    handle.record_activity(
                        "step_budget_extended",
                        (
                            f"Step budget +{decision.extra_steps} "
                            f"({prev} → {max_steps}): {decision.reason}"
                        ),
                        steps_taken=steps_taken,
                    )
                    self._notify_progress(config.name)
                    logger.info(
                        "Sub-agent '%s' step budget extended %s → %s (ext=%s)",
                        config.name,
                        prev,
                        max_steps,
                        step_budget_extensions,
                    )
                    continue

                duration_ms = (time.monotonic() - start_time) * 1000
                handle.status = SubAgentStatus.FAILED
                handle.record_activity(
                    "status",
                    f"Max steps ({max_steps}) reached: {decision.reason}",
                    steps_taken=steps_taken,
                )
                handle.result = SubAgentResult(
                    name=config.name,
                    success=False,
                    response="Sub-agent reached maximum steps",
                    error=f"Max steps ({max_steps}) reached: {decision.reason}",
                    duration_ms=duration_ms,
                    steps_taken=steps_taken,
                    tool_calls=tool_calls_made,
                    **_usage_fields(),
                )
                logger.warning(
                    "Sub-agent '%s' hit max steps (%d): %s",
                    config.name,
                    max_steps,
                    decision.reason,
                )
                return handle.result

        except asyncio.CancelledError:
            forced = getattr(handle, "forced_status", None)
            if forced == SubAgentStatus.LOOP:
                handle.status = SubAgentStatus.LOOP
                if handle.result is None or not handle.result.error:
                    handle.result = SubAgentResult(
                        name=config.name,
                        success=False,
                        error="loop: stopped by supervisor",
                        duration_ms=(time.monotonic() - start_time) * 1000,
                        steps_taken=steps_taken,
                        tool_calls=tool_calls_made,
                        **_usage_fields(),
                    )
                else:
                    handle.result.steps_taken = steps_taken
                    handle.result.tool_calls = tool_calls_made
                    handle.result.duration_ms = (time.monotonic() - start_time) * 1000
                handle.record_activity(
                    "status",
                    "loop",
                    steps_taken=steps_taken,
                )
                logger.warning("Sub-agent '%s' stopped as loop", config.name)
                return handle.result
            handle.status = SubAgentStatus.CANCELLED
            handle.record_activity(
                "status",
                "Cancelled",
                steps_taken=steps_taken,
            )
            handle.result = SubAgentResult(
                name=config.name,
                success=False,
                error="Sub-agent was cancelled",
                duration_ms=(time.monotonic() - start_time) * 1000,
                steps_taken=steps_taken,
                tool_calls=tool_calls_made,
                **_usage_fields(),
            )
            logger.info("Sub-agent '%s' cancelled", config.name)
            return handle.result

        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            handle.status = SubAgentStatus.FAILED
            handle.record_activity(
                "status",
                f"Failed: {e}",
                steps_taken=steps_taken,
            )
            handle.result = SubAgentResult(
                name=config.name,
                success=False,
                error=str(e),
                duration_ms=duration_ms,
                steps_taken=steps_taken,
                tool_calls=tool_calls_made,
                **_usage_fields(),
            )
            logger.exception("Sub-agent '%s' failed: %s", config.name, e)
            return handle.result
        finally:
            mgr = getattr(self._parent, "subagents", None)
            if mgr is not None:
                mgr.notify_handle_finished(config.name)

    async def cancel(self, name: str) -> bool:
        """Cancel a running sub-agent.

        Args:
            name: Sub-agent name.

        Returns:
            True if cancellation was initiated.
        """
        handle = self._active_handles.get(name)
        if not handle or not handle.is_running or not handle.task:
            return False

        child = getattr(handle, "_react_child", None)
        if child is not None:
            stop = getattr(child, "request_stop", None)
            if callable(stop):
                try:
                    stop()
                except Exception:
                    logger.debug("react child request_stop failed", exc_info=True)
        handle.task.cancel()
        forced = getattr(handle, "forced_status", None)
        handle.status = forced if forced else SubAgentStatus.CANCELLED
        return True

    def get_handle(self, name: str) -> SubAgentHandle | None:
        """Get the handle for a sub-agent."""
        return self._active_handles.get(name)

    def list_active(self) -> list[SubAgentHandle]:
        """List all active (running) sub-agents."""
        return [h for h in self._active_handles.values() if h.is_running]

    async def _run_via_react(
        self,
        config: SubAgentConfig,
        task: str,
        handle: SubAgentHandle,
        start_time: float,
    ) -> SubAgentResult:
        """Run the sub-agent on the same LangGraph ReAct engine as main."""
        from core.subagents.react_agent import (
            attach_subagent_runtime,
            build_react_subagent,
            record_handle_event,
        )

        child = build_react_subagent(self._parent, config, task)
        handle._react_child = child
        receive = getattr(self._comm_bus, "receive", None) if self._comm_bus is not None else None

        def _on_guidance() -> None:
            handle.record_activity(
                "status",
                "Applied supervisor guidance",
                steps_taken=handle.steps_taken,
            )
            self._notify_progress(config.name)

        attach_subagent_runtime(
            child,
            name=config.name,
            receive=receive,
            on_guidance=_on_guidance,
            handle=handle,
        )
        conv_id = f"subagent:{config.name}"
        try:
            from core.sdd.change_workspace import inherit_active_change
            from core.tools.execution_context import get_conversation_id, get_profile_name

            inherit_active_change(get_profile_name(), get_conversation_id(), conv_id)
        except Exception:
            logger.debug("inherit SDD worktree failed", exc_info=True)
        seed = list(getattr(config, "seed_messages", None) or [])
        if seed and hasattr(self._parent, "memory"):
            try:
                from core.subagents.fork import apply_fork_seed

                await apply_fork_seed(self._parent.memory, conv_id, seed)
            except Exception:
                logger.debug("fork seed persist failed", exc_info=True)

        def _on_event(event: Any) -> None:
            record_handle_event(handle, event)
            self._notify_progress(config.name)
            emit = getattr(self._parent, "emit", None)
            if callable(emit):
                try:
                    emit(event)
                except Exception:
                    logger.debug("forward sub-agent event failed", exc_info=True)

        child.events.subscribe(_on_event)
        try:
            from core.graph.nodes.react_node import SUBAGENT_CANCELLED_FINAL
            from core.subagents.react_agent import (
                is_failed_react_result,
                recover_empty_react_text,
            )

            text = await child.run(task, conversation_id=conv_id, execution_mode="react")
            duration_ms = (time.monotonic() - start_time) * 1000
            recovered = recover_empty_react_text(text, handle=handle)
            if recovered:
                text = recovered
            if (text or "").strip() == SUBAGENT_CANCELLED_FINAL:
                handle.status = SubAgentStatus.CANCELLED
                handle.result = SubAgentResult(
                    name=config.name,
                    success=False,
                    error="cancelled",
                    duration_ms=duration_ms,
                    steps_taken=int(handle.steps_taken or 0),
                    model=str(child.model or ""),
                )
                handle.record_activity(
                    "status",
                    "Cancelled",
                    steps_taken=handle.steps_taken,
                )
                return handle.result
            failed = is_failed_react_result(text)
            if failed:
                handle.status = SubAgentStatus.FAILED
                handle.result = SubAgentResult(
                    name=config.name,
                    success=False,
                    error=failed,
                    response=text or "",
                    duration_ms=duration_ms,
                    steps_taken=int(handle.steps_taken or 0),
                    model=str(child.model or ""),
                )
                handle.record_activity(
                    "status",
                    f"Failed: {failed}",
                    steps_taken=handle.steps_taken,
                )
                logger.warning(
                    "Sub-agent '%s' ReAct finished unsuccessfully: %s (steps=%d)",
                    config.name,
                    failed,
                    handle.steps_taken,
                )
                return handle.result
            handle.status = SubAgentStatus.COMPLETED
            handle.result = SubAgentResult(
                name=config.name,
                success=True,
                response=text or "",
                duration_ms=duration_ms,
                steps_taken=int(handle.steps_taken or 0),
                model=str(child.model or ""),
            )
            handle.record_activity(
                "status",
                "Completed",
                steps_taken=handle.steps_taken,
            )
            logger.info(
                "Sub-agent '%s' completed via ReAct (steps=%d, %.0fms)",
                config.name,
                handle.steps_taken,
                duration_ms,
            )
            return handle.result
        except asyncio.CancelledError:
            handle.status = SubAgentStatus.CANCELLED
            handle.result = SubAgentResult(
                name=config.name,
                success=False,
                error="cancelled",
                duration_ms=(time.monotonic() - start_time) * 1000,
                steps_taken=int(handle.steps_taken or 0),
            )
            raise
        except Exception as exc:
            handle.status = SubAgentStatus.FAILED
            handle.result = SubAgentResult(
                name=config.name,
                success=False,
                error=str(exc),
                duration_ms=(time.monotonic() - start_time) * 1000,
                steps_taken=int(handle.steps_taken or 0),
            )
            logger.exception("Sub-agent '%s' ReAct run failed: %s", config.name, exc)
            return handle.result
        finally:
            try:
                child.events.unsubscribe(_on_event)
            except Exception:
                pass
            mgr = getattr(self._parent, "subagents", None)
            if mgr is not None:
                try:
                    mgr.notify_handle_finished(config.name)
                except Exception:
                    pass

    async def _propose_skill_after_success(
        self,
        *,
        config: SubAgentConfig,
        client: Any,
        model: str,
        messages: list[dict[str, Any]],
        final_response: str,
        handle: SubAgentHandle,
    ) -> None:
        """Stage a skill from a finished sub-agent job (same pending path as main)."""
        try:
            from core.skills.self_improve import maybe_propose_skill_from_subagent

            parent_cfg = getattr(self._parent, "config", None)
            rec = await maybe_propose_skill_from_subagent(
                skills=getattr(self._parent, "skills", None),
                client=client,
                model=model,
                messages=messages,
                final_response=final_response,
                conversation_id=f"subagent:{config.name}",
                profile=str(getattr(parent_cfg, "profile_name", None) or "default"),
                agent_slot=str(config.agent_type or config.name or "main"),
                emit=getattr(self._parent, "emit", None),
                run_id=str(getattr(self._parent, "run_id", "") or handle.name),
                config=parent_cfg,
            )
            if rec:
                handle.record_activity(
                    "status",
                    f"Skill proposed: {rec.get('name')}",
                    steps_taken=handle.steps_taken,
                )
        except Exception:
            logger.debug("sub-agent skill proposal failed", exc_info=True)

    def _notify_progress(self, name: str) -> None:
        mgr = getattr(self._parent, "subagents", None)
        notify = getattr(mgr, "notify_progress", None)
        if callable(notify):
            try:
                notify(name)
            except Exception:
                logger.debug("Sub-agent progress notify failed", exc_info=True)

    def _get_tool_schemas(self, config: SubAgentConfig) -> list[dict[str, Any]]:
        """Get OpenAI tool schemas for the sub-agent's tool subset.

        Args:
            config: Sub-agent configuration with tool list.

        Returns:
            List of OpenAI function schemas.
        """
        if not config.tools or not hasattr(self._parent, "tools"):
            return []

        from core.tools.aliases import get_registered_tool, tool_schema_for_name

        schemas = []
        seen: set[str] = set()
        for tool_name in config.tools:
            tool = get_registered_tool(self._parent.tools, tool_name)
            if tool:
                schemas.append(tool_schema_for_name(tool, tool_name))
                seen.add(str(tool_name))

        # MCP tools live on the parent as mcp_<server>_<tool>.
        inherit_mcp = bool(getattr(config, "mcp_inherit", True))
        allowed_servers = [str(s).strip() for s in (config.mcp_servers or []) if str(s).strip()]
        parent_tools = getattr(self._parent.tools, "tools", None) or {}
        for name, tool in parent_tools.items():
            key = str(name or "")
            if not key.startswith("mcp_") or key in seen:
                continue
            if not inherit_mcp:
                if not allowed_servers or not any(
                    key.startswith(f"mcp_{srv}_") for srv in allowed_servers
                ):
                    continue
            schemas.append(tool_schema_for_name(tool, key))
            seen.add(key)

        return schemas

    async def _execute_tool(self, tool_call, config: SubAgentConfig) -> str:
        """Execute a tool call using the parent's ToolRegistry.

        Args:
            tool_call: OpenAI tool call object.
            config: Running sub-agent configuration.

        Returns:
            Tool execution result string.
        """
        if not hasattr(self._parent, "tools"):
            return "Error: No tools available for sub-agent"

        bridge = None
        if hasattr(self._parent, "subagents"):
            bridge = getattr(self._parent.subagents, "interactions", None)

        # Inherit parent run conversation so ActionGuard confirmations land on the
        # correct Studio tab (not ContextVar default "default", which hides the UI).
        parent_ctx = getattr(self._parent, "_event_context", None)
        conversation_id = (
            str(getattr(parent_ctx, "conversation_id", None) or "").strip() or "default"
        )

        tokens = subagent_scope(
            config.name,
            subagent_type=config.agent_type,
            interaction_bridge=bridge,
        )
        try:
            return await self._parent.tools.execute(
                tool_call,
                conversation_id=conversation_id,
                memory=getattr(self._parent, "memory", None),
            )
        except Exception as e:
            return f"Error: {e}"
        finally:
            reset_subagent_scope(tokens)
