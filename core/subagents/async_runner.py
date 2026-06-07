"""
Async Sub-Agent Runner — executes sub-agents as asyncio.Tasks within the main process.

Best for I/O-bound tasks (LLM calls, web searches, file reads).
Zero overhead on startup, shared memory access, fast communication.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from core.subagents.base import (
    SubAgentConfig,
    SubAgentResult,
    SubAgentHandle,
    SubAgentStatus,
    ProcessMode,
    MemoryAccess,
)
from core.subagents.communication import AgentMessage, AsyncCommunicationBus
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
        comm_bus: Optional[AsyncCommunicationBus] = None,
    ):
        self._parent = parent_agent
        self._comm_bus = comm_bus
        self._active_handles: Dict[str, SubAgentHandle] = {}

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
        tool_calls_made: List[Dict[str, Any]] = []
        steps_taken = 0
        max_steps = config.max_steps

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
                    task, top_k=3, agent_slot=config.name
                )
                skills_block = self._parent.skills.format_skills_for_prompt(relevant)
            except Exception as e:
                logger.debug(f"Skill injection failed for sub-agent: {e}")

        system_prompt = self._build_system_prompt(config, task, skills_block=skills_block)

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
                        "content": f"Relevant context from memory:\n" + "\n".join(memory_parts),
                    })
            except Exception as e:
                logger.debug(f"Memory injection failed for sub-agent: {e}")

        # ReAct loop
        try:
            while steps_taken < max_steps:
                steps_taken += 1

                # Set up timeout
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
                except asyncio.TimeoutError:
                    handle.status = SubAgentStatus.TIMED_OUT
                    handle.result = SubAgentResult(
                        name=config.name,
                        success=False,
                        error=f"Sub-agent timed out after {config.timeout}s",
                        duration_ms=(time.monotonic() - start_time) * 1000,
                        steps_taken=steps_taken,
                        tool_calls=tool_calls_made,
                    )
                    return handle.result

                message = response.choices[0].message

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
                        tool_calls_made.append({
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        })
                        result = await self._execute_tool(tc, config.name)
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
                    handle.result = SubAgentResult(
                        name=config.name,
                        success=True,
                        response=final_response,
                        duration_ms=duration_ms,
                        steps_taken=steps_taken,
                        tool_calls=tool_calls_made,
                    )
                    return handle.result

            # Max steps reached
            duration_ms = (time.monotonic() - start_time) * 1000
            handle.status = SubAgentStatus.FAILED
            handle.result = SubAgentResult(
                name=config.name,
                success=False,
                response="Sub-agent reached maximum steps",
                error=f"Max steps ({max_steps}) reached",
                duration_ms=duration_ms,
                steps_taken=steps_taken,
                tool_calls=tool_calls_made,
            )
            return handle.result

        except asyncio.CancelledError:
            handle.status = SubAgentStatus.CANCELLED
            handle.result = SubAgentResult(
                name=config.name,
                success=False,
                error="Sub-agent was cancelled",
                duration_ms=(time.monotonic() - start_time) * 1000,
                steps_taken=steps_taken,
                tool_calls=tool_calls_made,
            )
            return handle.result

        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            handle.status = SubAgentStatus.FAILED
            handle.result = SubAgentResult(
                name=config.name,
                success=False,
                error=str(e),
                duration_ms=duration_ms,
                steps_taken=steps_taken,
                tool_calls=tool_calls_made,
            )
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

    def get_handle(self, name: str) -> Optional[SubAgentHandle]:
        """Get the handle for a sub-agent."""
        return self._active_handles.get(name)

    def list_active(self) -> List[SubAgentHandle]:
        """List all active (running) sub-agents."""
        return [h for h in self._active_handles.values() if h.is_running]

    def _get_tool_schemas(self, config: SubAgentConfig) -> List[Dict[str, Any]]:
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

    async def _execute_tool(self, tool_call, subagent_name: str) -> str:
        """Execute a tool call using the parent's ToolRegistry.

        Args:
            tool_call: OpenAI tool call object.
            subagent_name: Running sub-agent job id (for confirmations / ask_user).

        Returns:
            Tool execution result string.
        """
        if not hasattr(self._parent, "tools"):
            return f"Error: No tools available for sub-agent"

        bridge = None
        if hasattr(self._parent, "subagents"):
            bridge = getattr(self._parent.subagents, "interactions", None)

        tokens = subagent_scope(subagent_name, interaction_bridge=bridge)
        try:
            return await self._parent.tools.execute(tool_call)
        except Exception as e:
            return f"Error: {e}"
        finally:
            reset_subagent_scope(tokens)

    def _build_system_prompt(
        self,
        config: SubAgentConfig,
        task: str,
        *,
        skills_block: str = "",
    ) -> str:
        """Build the system prompt for the sub-agent.

        Args:
            config: Sub-agent configuration.
            task: The task description.

        Returns:
            System prompt string.
        """
        base = config.system_prompt or f"You are {config.name}, a specialized AI assistant."

        prompt = f"""{base}

## Your Task
{task}

## Available Tools
{', '.join(config.tools) if config.tools else 'No tools available'}

## Instructions
1. Focus on your specific task
2. Use tools when needed to gather information or take action
3. Provide a clear, concise final answer
4. If you cannot complete the task, explain why

Remember: You are {config.name}. Stay focused on your specialized role.
"""
        if skills_block:
            prompt += f"\n\n{skills_block}"
        from core.project.helix_md import append_helix_project_context

        return append_helix_project_context(prompt)