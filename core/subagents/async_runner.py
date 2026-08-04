"""
Async Sub-Agent Runner — executes sub-agents as asyncio.Tasks within the main process.

Best for I/O-bound tasks (LLM calls, web searches, file reads).
Zero overhead on startup, shared memory access, fast communication.
"""

import asyncio
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

        # Build client (inherit from parent or use config override)
        model = config.model or self._parent.model
        client = self._parent.client

        # Build tool subset
        tools_schemas = self._get_tool_schemas(config)

        # Build system prompt (include skills scoped to this subagent)
        skills_block = ""
        if hasattr(self._parent, "skills"):
            try:
                relevant = self._parent.skills.get_relevant_skills(
                    task,
                    top_k=3,
                    agent_slot=config.agent_type or config.name,
                )
                skills_block = self._parent.skills.format_skills_for_prompt(relevant)
            except Exception as e:
                logger.debug(f"Skill injection failed for sub-agent: {e}")

        parent_cfg = getattr(self._parent, "config", None)
        profile_name = str(getattr(parent_cfg, "profile_name", None) or "default")
        from pathlib import Path

        from core.subagents.prompt import build_subagent_system_prompt

        try:
            working_directory = str(Path.cwd().resolve())
        except OSError:
            working_directory = str(Path.cwd())

        system_prompt = build_subagent_system_prompt(
            config,
            task,
            skills_block=skills_block,
            profile_name=profile_name,
            workspace_root=getattr(parent_cfg, "workspace_root", None),
            workspace_jail_enabled=getattr(parent_cfg, "workspace_jail_enabled", None),
            working_directory=working_directory,
        )

        # Build messages
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]

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
                    messages.append({
                        "role": "system",
                        "content": "Relevant context from memory:\n" + "\n".join(memory_parts),
                    })
            except Exception as e:
                logger.debug(f"Memory injection failed for sub-agent: {e}")

        # ReAct loop
        tokens_used = 0
        llm_calls = 0
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
                        response = await asyncio.wait_for(
                            client.chat.completions.create(
                                model=model,
                                messages=messages,
                                tools=tools_schemas if tools_schemas else None,
                                tool_choice="auto" if tools_schemas else None,
                                temperature=config.temperature,
                            ),
                            timeout=config.timeout,
                        )
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

                    message = response.choices[0].message
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
                                finish_reason = getattr(
                                    choices[0], "finish_reason", None
                                )
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

                    if message.tool_calls:
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
                                for tc in message.tool_calls
                            ],
                        }
                        messages.append(msg_dict)

                        for tc in message.tool_calls:
                            tool_name = tc.function.name
                            tool_calls_made.append({
                                "name": tool_name,
                                "arguments": tc.function.arguments,
                            })
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
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": result,
                            })
                    else:
                        # Final response
                        final_response = message.content or "No response"
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

        handle.task.cancel()
        handle.status = SubAgentStatus.CANCELLED
        return True

    def get_handle(self, name: str) -> SubAgentHandle | None:
        """Get the handle for a sub-agent."""
        return self._active_handles.get(name)

    def list_active(self) -> list[SubAgentHandle]:
        """List all active (running) sub-agents."""
        return [h for h in self._active_handles.values() if h.is_running]

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
        for tool_name in config.tools:
            tool = get_registered_tool(self._parent.tools, tool_name)
            if tool:
                schemas.append(tool_schema_for_name(tool, tool_name))

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
        conversation_id = str(
            getattr(parent_ctx, "conversation_id", None) or ""
        ).strip() or "default"

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

