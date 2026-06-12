"""
Sub-Agent Manager — central orchestrator for sub-agent execution.

Provides a unified interface for spawning, tracking, and collecting
results from sub-agents, whether they run in-process (async) or
in separate OS processes.
"""

import asyncio
import logging
from typing import Any

from core.logging.events import log_subagent_event
from core.platform_compat import process_subagents_supported
from core.subagents.async_runner import AsyncSubAgentRunner
from core.subagents.base import (
    ProcessMode,
    SubAgentConfig,
    SubAgentHandle,
    SubAgentResult,
    SubAgentStatus,
)
from core.subagents.communication import AgentCommunicationBus
from core.subagents.interaction import SubAgentInteractionBridge
from core.subagents.process import SubAgentProcessManager

logger = logging.getLogger(__name__)


class SubAgentManager:
    """Central manager for sub-agent execution.

    Provides a unified interface regardless of process mode:
    - spawn_sub_agent(): Create and start a sub-agent
    - get_result(): Get the result of a completed sub-agent
    - list_active(): List running sub-agents
    - terminate(): Cancel a specific sub-agent
    - terminate_all(): Cancel all running sub-agents
    - wait_all(): Wait for all sub-agents to complete
    """

    def __init__(self, parent_agent: Any):
        self._parent = parent_agent
        self._comm_bus = AgentCommunicationBus()
        cfg = getattr(parent_agent, "config", None)
        from core.security.confirmation import normalize_confirmation_timeout

        timeout = normalize_confirmation_timeout(getattr(cfg, "confirmation_timeout", None))
        self.interactions = SubAgentInteractionBridge(
            parent_agent,
            confirmation_timeout=timeout,
        )
        self._async_runner = AsyncSubAgentRunner(parent_agent, self._comm_bus.async_bus)
        self._process_manager = SubAgentProcessManager(parent_agent, self._comm_bus.process_bus)
        self._handles: dict[str, SubAgentHandle] = {}

    def _max_concurrent(self) -> int:
        cfg = getattr(self._parent, "config", None)
        return int(getattr(cfg, "subagent_max_concurrent", 4) or 4)

    def allocate_name(self, base: str) -> str:
        """Return ``base`` or ``base-N`` when a run with that name is still active."""
        if base not in self._handles or self._handles[base].is_done:
            return base
        n = 2
        while True:
            candidate = f"{base}-{n}"
            existing = self._handles.get(candidate)
            if existing is None or existing.is_done:
                return candidate
            n += 1

    def _ensure_done_event(self, handle: SubAgentHandle) -> asyncio.Event:
        if handle.done_event is None:
            handle.done_event = asyncio.Event()
        return handle.done_event

    def _mark_done(self, handle: SubAgentHandle) -> None:
        if handle.done_event is not None:
            handle.done_event.set()

    async def spawn_sub_agent(
        self,
        config: SubAgentConfig,
        task: str,
        *,
        agent_type: str = "",
    ) -> SubAgentHandle:
        """Spawn a sub-agent with the given configuration and task.

        Automatically selects the runner based on config.process_mode:
        - ASYNC → AsyncSubAgentRunner (in-process asyncio.Task)
        - PROCESS → SubAgentProcessManager (separate OS process)

        Args:
            config: Sub-agent configuration.
            task: Task description for the sub-agent.

        Returns:
            SubAgentHandle for tracking the sub-agent.
        """
        running = self.list_active()
        if len(running) >= self._max_concurrent():
            raise RuntimeError(
                f"Sub-agent limit reached ({self._max_concurrent()}). "
                "Wait for or terminate a running sub-agent first."
            )

        if config.name in self._handles and not self._handles[config.name].is_done:
            raise ValueError(
                f"Sub-agent '{config.name}' is already running. "
                "Wait for it to complete or terminate it first."
            )

        logger.info(
            f"Spawning sub-agent '{config.name}' "
            f"(mode={config.process_mode.value}, tools={config.tools})"
        )
        log_subagent_event(
            "INFO",
            f"spawn mode={config.process_mode.value}",
            subagent=config.name,
            tools=config.tools,
            task_preview=task[:200],
        )

        mode = config.process_mode
        if mode == ProcessMode.PROCESS and not process_subagents_supported():
            logger.warning(
                "Sub-agent '%s': OS process mode is not supported on Windows; using async",
                config.name,
            )
            mode = ProcessMode.ASYNC

        if mode == ProcessMode.PROCESS:
            handle = await self._process_manager.run(config, task)
        else:
            # Register with async bus first
            await self._comm_bus.register_async(config.name)
            handle = await self._async_runner.run(config, task)

        handle.task_preview = (task or "")[:240]
        handle.agent_type = agent_type or config.name
        self._ensure_done_event(handle)
        self._handles[config.name] = handle
        return handle

    async def spawn_typed(
        self,
        agent_type: str,
        task: str,
        *,
        wait: bool = False,
        timeout: float | None = None,
    ) -> tuple[SubAgentHandle, SubAgentResult | None]:
        """Spawn a registry sub-agent in a separate process when supported."""
        from core.subagents.spawn import prepare_subagent_config

        parent_cfg = getattr(self._parent, "config", None)
        instance = self.allocate_name(agent_type)
        sub_cfg = prepare_subagent_config(agent_type, parent_cfg, instance_name=instance)
        handle = await self.spawn_sub_agent(sub_cfg, task, agent_type=agent_type)
        if not wait:
            return handle, None
        result = await self.wait_for(handle.name, timeout=timeout or sub_cfg.timeout)
        return handle, result

    async def spawn_sub_agent_process(
        self,
        config: SubAgentConfig,
        task: str,
    ) -> SubAgentHandle:
        """Explicitly spawn a sub-agent in a separate OS process.

        Forces process_mode=PROCESS regardless of config.

        Args:
            config: Sub-agent configuration.
            task: Task description.

        Returns:
            SubAgentHandle.
        """
        config.process_mode = ProcessMode.PROCESS
        return await self.spawn_sub_agent(config, task)

    async def get_result(self, name: str) -> SubAgentResult | None:
        """Get the result of a completed sub-agent.

        Args:
            name: Sub-agent name.

        Returns:
            SubAgentResult if completed, None if still running or not found.
        """
        handle = self._handles.get(name)
        if not handle:
            return None

        if not handle.is_done:
            # Still running — wait briefly
            try:
                await asyncio.wait_for(self._wait_for_handle(handle), timeout=1.0)
            except TimeoutError:
                return None

        return handle.result

    async def wait_for(self, name: str, timeout: float | None = None) -> SubAgentResult:
        """Wait for a specific sub-agent to complete.

        Args:
            name: Sub-agent name.
            timeout: Max wait time in seconds. None = wait indefinitely.

        Returns:
            SubAgentResult.

        Raises:
            asyncio.TimeoutError: If timeout exceeded.
            KeyError: If sub-agent not found.
        """
        handle = self._handles.get(name)
        if not handle:
            raise KeyError(f"No sub-agent with name '{name}'")

        if handle.is_done:
            return handle.result

        await asyncio.wait_for(self._wait_for_handle(handle), timeout=timeout or 300)

        return handle.result

    async def wait_all(
        self,
        timeout: float | None = None,
    ) -> dict[str, SubAgentResult]:
        """Wait for all running sub-agents to complete.

        Args:
            timeout: Max wait time per sub-agent. None = wait indefinitely.

        Returns:
            Dict mapping sub-agent names to their results.
        """
        running = [h for h in self._handles.values() if not h.is_done]
        if not running:
            return {name: h.result for name, h in self._handles.items() if h.result}

        # Wait for each running handle
        tasks = [self._wait_for_handle(h) for h in running]
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout or 300,
            )
        except TimeoutError:
            logger.warning("wait_all timed out — some sub-agents may still be running")

        return {
            name: h.result
            for name, h in self._handles.items()
            if h.result is not None
        }

    def list_active(self) -> list[SubAgentHandle]:
        """List all currently running sub-agents.

        Returns:
            List of active SubAgentHandles.
        """
        return [h for h in self._handles.values() if h.is_running]

    def list_all(self) -> list[SubAgentHandle]:
        """List all sub-agents (running and completed).

        Returns:
            List of all SubAgentHandles.
        """
        return list(self._handles.values())

    async def terminate(self, name: str) -> bool:
        """Terminate a specific sub-agent.

        For async sub-agents: cancels the asyncio.Task.
        For process sub-agents: sends SIGTERM, then SIGKILL after grace period.

        Args:
            name: Sub-agent name.

        Returns:
            True if termination was initiated.
        """
        handle = self._handles.get(name)
        if not handle:
            return False

        if not handle.is_running:
            return False

        log_subagent_event("WARNING", "terminate requested", subagent=name)
        if handle.config.process_mode == ProcessMode.PROCESS:
            ok = await self._process_manager.cancel(name)
        else:
            ok = await self._async_runner.cancel(name)
        if ok:
            log_subagent_event("INFO", "terminated", subagent=name)
        return ok

    async def terminate_all(self) -> None:
        """Terminate all running sub-agents."""
        # Terminate process-mode agents first (they take longer)
        await self._process_manager.terminate_all()

        # Then cancel async agents
        for name, handle in self._handles.items():
            if handle.is_running and handle.config.process_mode != ProcessMode.PROCESS:
                await self._async_runner.cancel(name)

    def get_handle(self, name: str) -> SubAgentHandle | None:
        """Get the handle for a sub-agent by name.

        Args:
            name: Sub-agent name.

        Returns:
            SubAgentHandle or None.
        """
        return self._handles.get(name)

    async def _wait_for_handle(self, handle: SubAgentHandle) -> None:
        """Wait for a sub-agent handle to complete."""
        if handle.is_done:
            return
        event = self._ensure_done_event(handle)
        if handle.config.process_mode == ProcessMode.ASYNC and handle.task is not None:
            try:
                await handle.task
            except asyncio.CancelledError:
                pass
            return
        await event.wait()

    def format_status_text(self, *, html: bool = False) -> str:
        """Human-readable list of sub-agents for UI / slash commands."""
        handles = self.list_all()
        if not handles:
            empty = "No sub-agents."
            return f"<i>{empty}</i>" if html else empty

        lines: list[str] = []
        if html:
            lines.append("<b>Sub-agents</b>")
        else:
            lines.append("Sub-agents")

        for h in handles:
            preview = (h.task_preview or "")[:60]
            pid = f" pid={h.process_id}" if h.process_id else ""
            mode = h.config.process_mode.value
            elapsed = int(h.elapsed_ms)
            if html:
                lines.append(
                    f"• <code>{h.name}</code> [{h.status.value}] {mode}{pid} {elapsed}ms"
                )
                if preview:
                    lines.append(f"  <i>{preview}</i>")
            else:
                lines.append(
                    f"  {h.name} [{h.status.value}] {mode}{pid} {elapsed}ms — {preview}"
                )
        return "\n".join(lines)

    def get_status_summary(self) -> dict[str, Any]:
        """Get a summary of all sub-agents' status.

        Returns:
            Dict with counts and details.
        """
        handles = list(self._handles.values())
        return {
            "total": len(handles),
            "running": sum(1 for h in handles if h.is_running),
            "completed": sum(1 for h in handles if h.status == SubAgentStatus.COMPLETED),
            "failed": sum(1 for h in handles if h.status == SubAgentStatus.FAILED),
            "cancelled": sum(1 for h in handles if h.status == SubAgentStatus.CANCELLED),
            "timed_out": sum(1 for h in handles if h.status == SubAgentStatus.TIMED_OUT),
            "agents": [
                {
                    "name": h.name,
                    "status": h.status.value,
                    "elapsed_ms": h.elapsed_ms,
                    "process_mode": h.config.process_mode.value,
                    "process_id": h.process_id,
                    "agent_type": h.agent_type,
                    "task_preview": h.task_preview,
                }
                for h in handles
            ],
        }

    def notify_handle_finished(self, name: str) -> None:
        """Called by runners when a sub-agent completes."""
        handle = self._handles.get(name)
        if handle:
            self._mark_done(handle)