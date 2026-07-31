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
from core.subagents.process import SubAgentProcessManager, SubAgentProcessSpawnError

logger = logging.getLogger(__name__)

_PROCESS_SPAWN_FALLBACK_MARKERS = (
    "fds_to_keep",
    "bad file descriptor",
    "no such file or directory",
)

# When wait budget is about to expire, re-check activity and optionally extend.
WAIT_GRACE_S = 30.0
# Sub-agent is "active" if progress/heartbeat was seen within this window.
WAIT_ACTIVE_IDLE_S = 90.0
# Safety cap so a runaway job cannot extend forever.
WAIT_MAX_EXTENSIONS = 20
_DEFAULT_WAIT_TIMEOUT_S = 900.0


def _process_spawn_should_fallback(exc: BaseException) -> bool:
    """Return True when OS-process spawn failed and async mode is a safe fallback."""
    if isinstance(exc, SubAgentProcessSpawnError):
        return True
    text = str(exc).lower()
    return any(marker in text for marker in _PROCESS_SPAWN_FALLBACK_MARKERS)


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
        self._pending_done: set[str] = set()
        self._finished_emitted: set[str] = set()
        self._progress_emit_at: dict[str, float] = {}
        self._process_spawn_unreliable = False
        self._progress_min_interval = 1.25
        self._runtime_owner: str | None = None
        self._runtime_source: str | None = None
        self._supervisor: Any = None

    def _max_concurrent(self) -> int:
        cfg = getattr(self._parent, "config", None)
        return int(getattr(cfg, "subagent_max_concurrent", 4) or 4)

    def _profile_name(self) -> str:
        cfg = getattr(self._parent, "config", None)
        return str(getattr(cfg, "profile_name", None) or "default")

    def _runtime_meta(self) -> tuple[str, str]:
        """Return (owner_key, source) for the profile job registry."""
        if self._runtime_owner and self._runtime_source:
            return self._runtime_owner, self._runtime_source
        from core.subagents.runtime_registry import detect_source, owner_key

        source = detect_source()
        owner = owner_key(source=source)
        self._runtime_owner = owner
        self._runtime_source = source
        return owner, source

    def _publish_runtime(self, handle: SubAgentHandle) -> None:
        """Mirror handle state so Studio/other hosts on this profile can see it."""
        try:
            from core.subagents.runtime_registry import publish_handle, take_cancel_requests

            owner, source = self._runtime_meta()
            publish_handle(
                self._profile_name(),
                handle,
                owner=owner,
                source=source,
                include_activity=True,
                include_result=handle.is_done,
            )
            # Honour cross-process stop requests (e.g. Studio Stop on Telegram job).
            for cancel_name in take_cancel_requests(self._profile_name(), owner):
                if cancel_name not in self._handles:
                    continue
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self.terminate(cancel_name))
                except RuntimeError:
                    pass
        except Exception:
            logger.debug("Sub-agent runtime registry publish failed", exc_info=True)

    def allocate_name(self, base: str) -> str:
        """Return ``base`` or ``base-1``, ``base-2``, … when that name is still active."""
        if base not in self._handles or self._handles[base].is_done:
            return base
        n = 1
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
        fallback_reason = ""
        if mode == ProcessMode.PROCESS and not process_subagents_supported():
            fallback_reason = "OS process mode is not supported on this platform"
            logger.warning(
                "Sub-agent '%s': %s; using async",
                config.name,
                fallback_reason,
            )
            mode = ProcessMode.ASYNC
            config.process_mode = ProcessMode.ASYNC

        if mode == ProcessMode.PROCESS and self._process_spawn_unreliable:
            logger.info(
                "Sub-agent '%s': skipping OS process mode (spawn unreliable in this session)",
                config.name,
            )
            mode = ProcessMode.ASYNC

        if mode == ProcessMode.PROCESS:
            try:
                handle = await self._process_manager.run(config, task)
            except Exception as exc:
                if not _process_spawn_should_fallback(exc):
                    raise
                fallback_reason = str(exc).strip()
                self._process_spawn_unreliable = True
                self._comm_bus.process_bus.reset()
                self._process_manager = SubAgentProcessManager(
                    self._parent,
                    self._comm_bus.process_bus,
                )
                logger.warning(
                    "Sub-agent '%s': OS process spawn failed (%s); using async mode",
                    config.name,
                    exc,
                )
                log_subagent_event(
                    "WARNING",
                    f"process spawn failed; async fallback: {exc}",
                    subagent=config.name,
                )
                config.process_mode = ProcessMode.ASYNC
                await self._comm_bus.register_async(config.name)
                handle = await self._async_runner.run(config, task)
        else:
            # Register with async bus first
            await self._comm_bus.register_async(config.name)
            handle = await self._async_runner.run(config, task)

        handle.task_preview = (task or "")[:240]
        handle.agent_type = agent_type or config.name
        handle.spawn_fallback_reason = fallback_reason
        handle.max_steps = int(getattr(config, "max_steps", 0) or 0)
        if not handle.current_activity:
            handle.record_activity(
                "status",
                f"Started ({handle.config.process_mode.value})",
                steps_taken=0,
            )
        self._register_handle(config.name, handle)
        self._emit_started(handle)
        self._publish_runtime(handle)
        self._ensure_supervisor().ensure_running()
        if self._supervisor is not None:
            try:
                self._supervisor.reset_job(config.name)
            except Exception:
                pass
        return handle

    def _ensure_supervisor(self) -> Any:
        """Lazy-create the runtime supervisor (watches jobs, injects guidance)."""
        if self._supervisor is not None:
            return self._supervisor
        from core.subagents.supervisor import SubagentSupervisor, SupervisorPolicy

        cfg = getattr(self._parent, "config", None)
        self._supervisor = SubagentSupervisor(
            self,
            policy=SupervisorPolicy.from_config(cfg),
        )
        return self._supervisor

    def _register_handle(self, name: str, handle: SubAgentHandle) -> None:
        """Track a handle and reconcile completion notifications."""
        import time

        self._ensure_done_event(handle)
        # Job ids are reused (coder-1 after a prior run finished). Clear the
        # once-flag so SubAgentFinishedEvent + SDD auto-check run again.
        if not handle.is_done:
            self._finished_emitted.discard(name)
            self._progress_emit_at.pop(name, None)
        if getattr(handle, "started_at_wall", None) is None:
            try:
                handle.started_at_wall = time.time()
            except Exception:
                pass
        self._handles[name] = handle
        if name in self._pending_done or handle.is_done:
            self._pending_done.discard(name)
            self._mark_done(handle)
            self._emit_finished_once(handle)

    def _emit_agent_event(self, event: Any) -> None:
        emit = getattr(self._parent, "emit", None)
        if not callable(emit):
            return
        try:
            emit(event)
        except Exception:
            logger.debug("Failed to emit sub-agent lifecycle event", exc_info=True)

    def _emit_started(self, handle: SubAgentHandle) -> None:
        from core.agent_events import SubAgentStartedEvent

        mode = handle.config.process_mode
        self._emit_agent_event(
            SubAgentStartedEvent(
                name=handle.name,
                agent_type=handle.agent_type or handle.config.agent_type or "",
                task_preview=handle.task_preview or "",
                process_mode=mode.value if hasattr(mode, "value") else str(mode),
                process_id=handle.process_id,
            )
        )
        self._publish_runtime(handle)

    def _emit_progress(self, handle: SubAgentHandle) -> None:
        from core.agent_events import SubAgentProgressEvent

        self._emit_agent_event(
            SubAgentProgressEvent(
                name=handle.name,
                agent_type=handle.agent_type or handle.config.agent_type or "",
                status=handle.status.value if hasattr(handle.status, "value") else str(handle.status),
                steps_taken=int(handle.steps_taken or 0),
                max_steps=int(handle.max_steps or handle.config.max_steps or 0),
                current_activity=handle.current_activity or "",
                last_tool=handle.last_tool or "",
                elapsed_ms=float(handle.elapsed_ms or 0),
            )
        )
        self._publish_runtime(handle)

    def _emit_finished_once(self, handle: SubAgentHandle) -> None:
        from core.agent_events import SubAgentFinishedEvent

        if handle.name in self._finished_emitted:
            return
        self._finished_emitted.add(handle.name)
        result = handle.result
        success = bool(result.success) if result else False
        response = (result.response if result else "") or ""
        error = (result.error if result else "") or ""
        if len(response) > 400:
            response = response[:399] + "…"
        if len(error) > 400:
            error = error[:399] + "…"
        tokens_used = int((result.tokens_used if result else 0) or 0)
        self._emit_agent_event(
            SubAgentFinishedEvent(
                name=handle.name,
                agent_type=handle.agent_type or handle.config.agent_type or "",
                status=handle.status.value if hasattr(handle.status, "value") else str(handle.status),
                task_preview=handle.task_preview or "",
                success=success,
                error=error,
                response_preview=response,
                steps_taken=int(
                    (result.steps_taken if result else 0) or handle.steps_taken or 0
                ),
                elapsed_ms=float(handle.elapsed_ms or 0),
                tokens_used=tokens_used,
            )
        )
        # SDD apply/dispatch: mark tasks.md checkbox when job succeeds
        self._maybe_complete_sdd_task(handle, success=success)
        self._publish_runtime(handle)

    def _maybe_complete_sdd_task(
        self, handle: SubAgentHandle, *, success: bool
    ) -> None:
        try:
            from core.sdd.task_completion import try_complete_sdd_task_for_subagent

            cfg = getattr(self._parent, "config", None)
            workspace = getattr(cfg, "workspace_root", None)
            # task_preview starts with [SDD change=… task=…] for dispatched jobs
            result = try_complete_sdd_task_for_subagent(
                job_id=handle.name,
                task_preview=handle.task_preview or "",
                success=success,
                workspace=workspace,
            )
            if result and result.get("ok") and success:
                self._schedule_sdd_next_wave(result)
        except Exception:
            logger.debug("SDD task auto-complete skipped", exc_info=True)

    def _schedule_sdd_next_wave(self, complete_result: dict) -> None:
        """After a graph task is marked done, dispatch the next ready wave."""
        try:
            import asyncio

            project_root = complete_result.get("project_root")
            change_id = complete_result.get("change_id")
            if not project_root or not change_id:
                return

            async def _run() -> None:
                try:
                    from core.sdd.dispatch import dispatch_change_tasks
                    from core.sdd.store import SpecStore

                    store = SpecStore(project_root)
                    await dispatch_change_tasks(
                        store, str(change_id), parent_agent=self._parent
                    )
                except Exception:
                    logger.debug("SDD next-wave dispatch skipped", exc_info=True)

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
            loop.create_task(_run())
        except Exception:
            logger.debug("SDD next-wave schedule failed", exc_info=True)

    def notify_progress(self, name: str, *, force: bool = False) -> None:
        """Optional progress fan-out for Studio (throttled)."""
        import time

        handle = self._handles.get(name)
        if not handle or not handle.is_running:
            return
        now = time.monotonic()
        last = self._progress_emit_at.get(name, 0.0)
        if not force and (now - last) < self._progress_min_interval:
            return
        self._progress_emit_at[name] = now
        self._emit_progress(handle)

    async def spawn_typed(
        self,
        agent_type: str,
        task: str,
        *,
        wait: bool = False,
        timeout: float | None = None,
        instance_name: str | None = None,
    ) -> tuple[SubAgentHandle, SubAgentResult | None]:
        """Spawn a registry sub-agent in a separate process when supported.

        ``instance_name`` forces a job id (e.g. ``coder-1``); if that slot is
        busy, falls back to :meth:`allocate_name`.
        """
        from core.subagents.resolve import resolve_subagent_type
        from core.subagents.spawn import prepare_subagent_config

        parent_cfg = getattr(self._parent, "config", None)
        profile = str(getattr(parent_cfg, "profile_name", None) or "default")
        agent_type = resolve_subagent_type(agent_type, profile=profile)
        wanted = (instance_name or "").strip()
        if wanted:
            existing = self._handles.get(wanted)
            instance = (
                wanted
                if existing is None or existing.is_done
                else self.allocate_name(agent_type)
            )
        else:
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
            name: Sub-agent name or full job id (``owner::name``).

        Returns:
            SubAgentResult if completed, None if still running or not found.
        """
        handle = self.get_handle(name)
        if not handle:
            return None

        if not handle.is_done:
            # Still running — wait briefly
            try:
                await asyncio.wait_for(self._wait_for_handle(handle), timeout=1.0)
            except TimeoutError:
                return None

        return handle.result

    def _default_wait_timeout(self, handle: SubAgentHandle) -> float:
        cfg_timeout = float(getattr(handle.config, "timeout", 0) or 0)
        if cfg_timeout > 0:
            return cfg_timeout
        parent_cfg = getattr(self._parent, "config", None)
        parent_timeout = float(
            getattr(parent_cfg, "subagent_process_timeout", 0) or 0
        )
        if parent_timeout > 0:
            return parent_timeout
        return _DEFAULT_WAIT_TIMEOUT_S

    def _emit_timeout_extended(
        self,
        handle: SubAgentHandle,
        *,
        added_s: float,
        total_budget_s: float,
        extensions: int,
    ) -> None:
        from core.agent_events import SubAgentTimeoutExtendedEvent, ThinkingEvent

        name = handle.name
        added = max(1, int(round(added_s)))
        total = max(added, int(round(total_budget_s)))
        activity = (handle.current_activity or handle.last_tool or "working").strip()
        activity_suffix = f"; {activity}" if activity else ""
        msg = (
            f"Timeout for sub-agent `{name}` extended by {added}s "
            f"(still working; total wait budget ~{total}s{activity_suffix})"
        )
        handle.record_activity(
            "timeout_extended",
            msg,
            steps_taken=handle.steps_taken,
        )
        self._emit_agent_event(
            SubAgentTimeoutExtendedEvent(
                name=name,
                agent_type=handle.agent_type or handle.config.agent_type or "",
                added_timeout_s=float(added_s),
                total_budget_s=float(total_budget_s),
                extensions=int(extensions),
                current_activity=activity,
                steps_taken=int(handle.steps_taken or 0),
                message=msg,
            )
        )
        # Also surface in live UIs that only render ThinkingEvent.
        self._emit_agent_event(ThinkingEvent(message=msg))
        log_subagent_event(
            "INFO",
            "wait timeout extended",
            subagent=name,
            added_s=added_s,
            total_budget_s=total_budget_s,
            extensions=extensions,
        )
        self.notify_progress(name, force=True)

    async def wait_for(self, name: str, timeout: float | None = None) -> SubAgentResult:
        """Wait for a specific sub-agent to complete.

        Near the end of the wait budget (last ``WAIT_GRACE_S`` seconds), if the
        sub-agent is still actively working, the budget is extended and the user
        is notified instead of failing immediately.

        Args:
            name: Sub-agent name or full job id (``owner::name`` from list_subagents).
            timeout: Max wait time in seconds for the initial budget.
                ``None`` uses the sub-agent / profile default.

        Returns:
            SubAgentResult.

        Raises:
            asyncio.TimeoutError: If timeout exceeded (and no further extension).
            KeyError: If sub-agent not found.
        """
        resolved = self.resolve_handle_name(name)
        if resolved is None:
            # Job may only exist in the profile registry (other host / full id).
            remote = await self._wait_for_registry_job(name, timeout=timeout)
            if remote is not None:
                return remote
            raise KeyError(f"No sub-agent with name '{name}'")
        name = resolved
        handle = self._handles.get(name)
        if not handle:
            raise KeyError(f"No sub-agent with name '{name}'")

        if handle.is_done:
            if handle.result is None:
                raise TimeoutError(
                    f"sub-agent '{name}' finished without a result"
                )
            return handle.result

        chunk = float(timeout) if timeout is not None else self._default_wait_timeout(handle)
        if chunk <= 0:
            chunk = _DEFAULT_WAIT_TIMEOUT_S

        grace = max(0.0, float(WAIT_GRACE_S))
        max_idle = max(0.0, float(WAIT_ACTIVE_IDLE_S))
        max_ext = max(0, int(WAIT_MAX_EXTENSIONS))
        extensions = 0
        total_budget = chunk
        waited = 0.0

        def _result_or_raise() -> SubAgentResult:
            if handle.result is None:
                raise TimeoutError(
                    f"sub-agent '{name}' finished without a result"
                )
            return handle.result

        while True:
            if handle.is_done:
                return _result_or_raise()

            # Wait until ~grace seconds remain, then decide: extend or drain tail.
            primary = chunk - grace if chunk > grace else 0.0
            if primary > 0:
                try:
                    await asyncio.wait_for(
                        self._wait_for_handle(handle), timeout=primary
                    )
                except TimeoutError:
                    pass
                waited += primary
                if handle.is_done:
                    return _result_or_raise()

            # ~grace seconds left (or whole chunk was ≤ grace): still active?
            if (
                handle.is_running
                and handle.is_actively_working(max_idle_s=max_idle)
                and extensions < max_ext
            ):
                extensions += 1
                total_budget += chunk
                self._emit_timeout_extended(
                    handle,
                    added_s=chunk,
                    total_budget_s=total_budget,
                    extensions=extensions,
                )
                # Fresh chunk starts immediately — do not burn the grace tail.
                continue

            # Not active (or extension cap): wait out remaining grace, then fail.
            tail = min(grace, chunk) if primary > 0 else chunk
            if tail > 0:
                try:
                    await asyncio.wait_for(
                        self._wait_for_handle(handle), timeout=tail
                    )
                except TimeoutError:
                    pass
                waited += tail
                if handle.is_done:
                    return _result_or_raise()

            # One last chance if activity resumed during the grace tail.
            if (
                handle.is_running
                and handle.is_actively_working(max_idle_s=max_idle)
                and extensions < max_ext
            ):
                extensions += 1
                total_budget += chunk
                self._emit_timeout_extended(
                    handle,
                    added_s=chunk,
                    total_budget_s=total_budget,
                    extensions=extensions,
                )
                continue

            idle_note = ""
            if handle.is_running and not handle.is_actively_working(max_idle_s=max_idle):
                idle_note = f"; no activity for >{max_idle:.0f}s (appears idle/hung)"
            raise TimeoutError(
                f"timed out waiting for sub-agent '{name}' after {waited:.0f}s "
                f"(budget={total_budget:.0f}s, extensions={extensions}){idle_note}"
            )

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

    def find_running_duplicate(
        self,
        agent_type: str,
        task: str,
    ) -> SubAgentHandle | None:
        """Return an active handle with the same type and task, if any."""
        want_type = (agent_type or "").strip()
        want_task = (task or "").strip()
        if not want_type or not want_task:
            return None
        for handle in self.list_active():
            if (handle.agent_type or "").strip() != want_type:
                continue
            preview = (handle.task_preview or "").strip()
            if preview == want_task or want_task in preview or preview in want_task:
                return handle
        return None

    def list_all(self) -> list[SubAgentHandle]:
        """List all sub-agents (running and completed).

        Returns:
            List of all SubAgentHandles.
        """
        return list(self._handles.values())

    async def _wait_for_registry_job(
        self, job_ref: str, *, timeout: float | None = None
    ) -> SubAgentResult | None:
        """Poll profile runtime registry when the job is not in local handles.

        Used when the agent passes a full id (``studio-pid::name``) or the job
        was started on another host of the same profile.
        """
        from core.subagents.base import SubAgentResult, SubAgentStatus
        from core.subagents.runtime_registry import get_job, parse_job_id

        text = (job_ref or "").strip()
        if not text:
            return None
        profile = self._profile_name()
        # If the job never existed in the registry, do not wait.
        probe = get_job(profile, text, include_activity=False, include_result=True)
        if probe is None:
            owner, bare = parse_job_id(text)
            if bare and bare != text:
                probe = get_job(
                    profile, bare, include_activity=False, include_result=True
                )
            if probe is None:
                return None

        budget = float(timeout) if timeout is not None and timeout > 0 else 900.0
        deadline = asyncio.get_running_loop().time() + budget
        last = probe
        while True:
            if last is not None:
                done = bool(last.get("done"))
                status = str(last.get("status") or "").lower()
                if done or status in {
                    SubAgentStatus.COMPLETED.value,
                    SubAgentStatus.FAILED.value,
                    SubAgentStatus.CANCELLED.value,
                    SubAgentStatus.TIMED_OUT.value,
                }:
                    res = last.get("result") if isinstance(last.get("result"), dict) else {}
                    success = bool(res.get("success")) if res else status == (
                        SubAgentStatus.COMPLETED.value
                    )
                    if status in {
                        SubAgentStatus.FAILED.value,
                        SubAgentStatus.CANCELLED.value,
                        SubAgentStatus.TIMED_OUT.value,
                    }:
                        success = False
                    return SubAgentResult(
                        name=str(last.get("name") or parse_job_id(text)[1] or text),
                        success=success,
                        response=str(res.get("response") or last.get("response") or ""),
                        error=str(res.get("error") or last.get("error") or ""),
                        duration_ms=float(
                            res.get("duration_ms") or last.get("elapsed_ms") or 0
                        ),
                        steps_taken=int(
                            res.get("steps_taken") or last.get("steps_taken") or 0
                        ),
                    )
            now = asyncio.get_running_loop().time()
            if now >= deadline:
                raise TimeoutError(
                    f"timed out waiting for sub-agent '{text}' "
                    f"(registry job still running)"
                )
            await asyncio.sleep(0.5)
            last = get_job(profile, text, include_activity=False, include_result=True)
            if last is None:
                owner, bare = parse_job_id(text)
                if bare:
                    last = get_job(
                        profile, bare, include_activity=False, include_result=True
                    )

    async def terminate(self, name: str) -> bool:
        """Terminate a specific sub-agent.

        For async sub-agents: cancels the asyncio.Task.
        For process sub-agents: sends SIGTERM, then SIGKILL after grace period.

        Args:
            name: Sub-agent name or full job id (``owner::name``).

        Returns:
            True if termination was initiated.
        """
        resolved = self.resolve_handle_name(name)
        handle = self._handles.get(resolved) if resolved else None
        if not handle:
            # Cross-process: ask the owning host (e.g. Telegram) to stop.
            try:
                from core.subagents.runtime_registry import request_cancel

                return request_cancel(self._profile_name(), name)
            except Exception:
                return False

        if not handle.is_running:
            return False

        log_subagent_event("WARNING", "terminate requested", subagent=handle.name)
        if handle.config.process_mode == ProcessMode.PROCESS:
            ok = await self._process_manager.cancel(handle.name)
        else:
            ok = await self._async_runner.cancel(handle.name)
        if ok:
            log_subagent_event("INFO", "terminated", subagent=handle.name)
            self._publish_runtime(handle)
        return ok

    async def terminate_all(self) -> None:
        """Terminate all running sub-agents."""
        # Terminate process-mode agents first (they take longer)
        await self._process_manager.terminate_all()

        # Then cancel async agents
        for name, handle in self._handles.items():
            if handle.is_running and handle.config.process_mode != ProcessMode.PROCESS:
                await self._async_runner.cancel(name)

    def resolve_handle_name(self, job_ref: str) -> str | None:
        """Map bare name or ``owner::name`` (from list_subagents) to a local handle key.

        ``list_subagents`` / Studio expose full ids like ``studio-123::coder-python``;
        local handles are keyed only by ``coder-python``. Accept both forms.
        """
        text = (job_ref or "").strip()
        if not text:
            return None
        if text in self._handles:
            return text
        from core.subagents.runtime_registry import parse_job_id

        owner, name = parse_job_id(text)
        if name and name in self._handles:
            return name
        # Full id may use a different owner label; still match bare name uniquely.
        if owner and name:
            matches = [n for n in self._handles if n == name]
            if len(matches) == 1:
                return matches[0]
        return None

    def get_handle(self, name: str) -> SubAgentHandle | None:
        """Get the handle for a sub-agent by name or full job id (``owner::name``).

        Args:
            name: Sub-agent name or full job id from list_subagents.

        Returns:
            SubAgentHandle or None.
        """
        key = self.resolve_handle_name(name)
        if key is None:
            return None
        return self._handles.get(key)

    async def _wait_for_handle(self, handle: SubAgentHandle) -> None:
        """Wait for a sub-agent handle to complete."""
        if handle.is_done:
            return
        event = self._ensure_done_event(handle)
        # Always wait on done_event — never `await handle.task` here. Outer
        # asyncio.wait_for(..., timeout=T) would cancel this waiter and, when
        # it was tied to handle.task, kill the sub-agent prematurely.
        while not handle.is_done:
            try:
                await asyncio.wait_for(event.wait(), timeout=0.25)
            except TimeoutError:
                if handle.is_done:
                    break

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

        pending = self.interactions.list_pending_questions()
        if pending:
            if html:
                lines.append("")
                lines.append("<b>Pending questions</b>")
                for item in pending:
                    q = (item.get("question") or "")[:120]
                    name = item.get("subagent_name") or "sub-agent"
                    lines.append(f"• <code>{name}</code>: {q}")
            else:
                lines.append("")
                lines.append("Pending questions")
                for item in pending:
                    q = (item.get("question") or "")[:120]
                    name = item.get("subagent_name") or "sub-agent"
                    lines.append(f"  ? {name}: {q}")

        return "\n".join(lines)

    def get_status_summary(self) -> dict[str, Any]:
        """Get a summary of all sub-agents' status.

        Includes jobs published by other hosts on the same profile
        (Studio / Telegram / MAX) so status is profile-scoped.

        Returns:
            Dict with counts and details.
        """
        from core.subagents.runtime_registry import (
            detect_source,
            job_id,
            list_jobs,
            merge_local_and_profile,
            owner_key,
        )

        owner, source = self._runtime_meta()
        local_agents = []
        for h in self._handles.values():
            row = h.to_status_dict(include_activity=False, include_result=False)
            row["id"] = job_id(owner, h.name)
            row["owner"] = owner
            row["source"] = source
            row["local"] = True
            local_agents.append(row)

        try:
            profile_agents = list_jobs(
                self._profile_name(),
                include_done=True,
                include_activity=False,
                include_result=False,
            )
        except Exception:
            profile_agents = []

        agents = merge_local_and_profile(
            local_agents, profile_agents, local_owner=owner
        )
        # Ensure source label is present for local-only fallback.
        for row in agents:
            if row.get("local") and not row.get("source"):
                row["source"] = source or detect_source()
            if not row.get("owner"):
                row["owner"] = owner or owner_key(source=source)

        def _count(status: str) -> int:
            return sum(1 for a in agents if str(a.get("status") or "") == status)

        return {
            "total": len(agents),
            "running": sum(1 for a in agents if a.get("running")),
            "completed": _count(SubAgentStatus.COMPLETED.value),
            "failed": _count(SubAgentStatus.FAILED.value),
            "cancelled": _count(SubAgentStatus.CANCELLED.value),
            "timed_out": _count(SubAgentStatus.TIMED_OUT.value),
            "agents": agents,
            "profile": self._profile_name(),
        }

    def notify_handle_finished(self, name: str) -> None:
        """Called by runners when a sub-agent completes."""
        handle = self._handles.get(name)
        if handle:
            if handle.is_done and not handle.current_activity:
                status = handle.status.value if hasattr(handle.status, "value") else str(handle.status)
                handle.record_activity("status", f"Finished ({status})")
            self._mark_done(handle)
            self._emit_finished_once(handle)
        else:
            self._pending_done.add(name)