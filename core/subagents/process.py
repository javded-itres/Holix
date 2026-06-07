"""
Sub-Agent Process Runner — executes sub-agents in separate OS processes.

Provides true parallelism (bypasses GIL), crash isolation, and
resource separation. Uses multiprocessing.Process with IPC via
multiprocessing.Queue.

Architecture:
    Parent Process                          Child Process
    ┌──────────────┐    input_queue    ┌──────────────────┐
    │ SubAgentMgr  │─────────────────▶│ run_sub_agent_   │
    │              │                   │ in_process()     │
    │  heartbeat   │◀─────────────────│  output_queue    │
    │  monitor     │    output_queue   │  heartbeat loop  │
    └──────────────┘                   └──────────────────┘
"""

import asyncio
import json
import logging
import multiprocessing
import os
import threading
import time
import uuid
from typing import Any

from openai import AsyncOpenAI

from core.platform_compat import terminate_process
from core.subagents.base import (
    MemoryAccess,
    SubAgentConfig,
    SubAgentHandle,
    SubAgentResult,
    SubAgentStatus,
)
from core.subagents.communication import AgentMessage, ProcessCommunicationBus

logger = logging.getLogger(__name__)

# Heartbeat interval (seconds) — sub-agents send heartbeat messages
# at this interval so the parent can detect hangs.
HEARTBEAT_INTERVAL = 5.0

# Grace period after SIGTERM before SIGKILL (seconds)
GRACE_PERIOD = 5.0

# Child reads credentials from env (not Process args — avoids pickle/log exposure).
_SUBAGENT_API_KEY_ENV = "HELIX_SUBAGENT_API_KEY"
_SUBAGENT_BASE_URL_ENV = "HELIX_SUBAGENT_BASE_URL"
_subagent_spawn_lock = threading.Lock()


def _ensure_event_loop() -> asyncio.AbstractEventLoop:
    """Create an event loop for a fresh multiprocessing child (Py 3.10+)."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    else:
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    return loop


def _start_subagent_process(
    process: multiprocessing.Process,
    *,
    api_key: str,
    base_url: str,
) -> None:
    """Start a sub-agent process with credentials in the child environment only."""
    with _subagent_spawn_lock:
        prev = {
            _SUBAGENT_API_KEY_ENV: os.environ.get(_SUBAGENT_API_KEY_ENV),
            _SUBAGENT_BASE_URL_ENV: os.environ.get(_SUBAGENT_BASE_URL_ENV),
        }
        os.environ[_SUBAGENT_API_KEY_ENV] = api_key
        os.environ[_SUBAGENT_BASE_URL_ENV] = base_url
        try:
            process.start()
        finally:
            for name, value in prev.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


def run_sub_agent_in_process(
    config_dict: dict[str, Any],
    task: str,
    input_queue: multiprocessing.Queue,
    output_queue: multiprocessing.Queue,
    parent_model: str,
    ltm_db_path: str = "",
    vector_db_path: str = "",
    mcp_servers: dict[str, Any] | None = None,
    skills_dir: str = "",
    skill_assignments: dict[str, list[str]] | None = None,
    auto_allow_threshold: str = "low",
    confirmation_timeout: float = 300.0,
    interactive: bool = True,
    search_config: dict[str, Any] | None = None,
) -> None:
    """Entry point for a sub-agent running in a separate process.

    This function is the target of multiprocessing.Process(). It:
    1. Sets up its own LLM client, tools, and memory
    2. Runs a ReAct loop
    3. Sends results back via output_queue
    4. Sends heartbeat messages for monitoring
    5. Listens for cancel signals on input_queue

    Args:
        config_dict: SubAgentConfig as dict (must be serializable).
        task: Task description.
        input_queue: Queue for parent → child messages.
        output_queue: Queue for child → parent messages.
        parent_model: Default model name.
        Credentials are read from HELIX_SUBAGENT_API_KEY / HELIX_SUBAGENT_BASE_URL in the child env.
        ltm_db_path: Path to LTM SQLite database (empty = no memory).
        vector_db_path: Path to ChromaDB vector database.
        mcp_servers: dict | None = None  # MCP server defs filtered for sub
    """
    import asyncio as _asyncio

    loop = _ensure_event_loop()

    from core.search.engine import set_search_config

    if search_config:
        set_search_config(search_config)

    # Reconstruct config
    config = SubAgentConfig(**config_dict)
    model = config.model or parent_model

    parent_base_url = os.environ.get(_SUBAGENT_BASE_URL_ENV, "http://localhost:11434/v1")
    parent_api_key = os.environ.get(_SUBAGENT_API_KEY_ENV, "ollama")

    # Create own LLM client
    client = AsyncOpenAI(base_url=parent_base_url, api_key=parent_api_key)

    # Create own tool registry (subset)
    from core.tools.registry import ToolRegistry
    registry = ToolRegistry()
    registry.register_all()

    # MCP for this sub (if any servers listed in its config and defs passed)
    if mcp_servers and getattr(config, "mcp_servers", None):
        try:
            from core.mcp.manager import MCPManager
            mcp_mgr = MCPManager({k: v for k, v in mcp_servers.items() if k in config.mcp_servers})
            loop.run_until_complete(mcp_mgr.connect_all())
            loop.run_until_complete(
                registry.register_mcp(
                    {k: v for k, v in mcp_servers.items() if k in config.mcp_servers},
                    {"main": list(config.mcp_servers)},
                    slot="main",
                )
            )
            # stash for cleanup if needed
            registry._mcp_manager = mcp_mgr  # type: ignore
        except Exception as e:
            print(f"[sub-process] MCP init skipped: {e}")

    # Optionally connect to parent's LTM (shared access)
    memory = None
    if ltm_db_path and config.memory_access != MemoryAccess.ISOLATED:
        try:
            # Override settings paths before creating manager
            from config import settings
            from core.memory.manager import LongTermMemoryManager
            settings.ltm_db_path = ltm_db_path
            settings.vector_db_path = vector_db_path or "data/memory/vector_db"
            memory = LongTermMemoryManager()
            loop.run_until_complete(memory.initialize_db())
        except Exception:
            # Memory access is best-effort in subprocess
            pass

    skills_block = ""
    if skills_dir:
        try:
            from core.di.runtime_config import HelixRuntimeConfig
            from core.skills.manager import SkillsManager

            sk_cfg = HelixRuntimeConfig.from_settings().with_overrides(
                skills_dir=skills_dir,
                skill_assignments=skill_assignments or {},
            )
            sk_mgr = SkillsManager(sk_cfg)
            relevant = sk_mgr.get_relevant_skills(
                task, top_k=3, agent_slot=config.name
            )
            skills_block = sk_mgr.format_skills_for_prompt(relevant)
        except Exception:
            pass

    system_prompt = _build_process_system_prompt(config, task, skills_block=skills_block)

    # Build messages
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]

    # Inject relevant memories
    if memory and config.memory_access != MemoryAccess.ISOLATED:
        try:
            context = loop.run_until_complete(memory.get_relevant_context(task, top_k=3))
            memory_parts = []
            for ep in context.get("episodic", []):
                memory_parts.append(f"[Past experience]: {ep.get('content', '')[:200]}")
            if memory_parts:
                messages.append({
                    "role": "system",
                    "content": "Relevant context:\n" + "\n".join(memory_parts),
                })
        except Exception:
            pass

    # Build tool schemas (subset)
    from core.tools.aliases import get_registered_tool, tool_schema_for_name

    tools_schemas = []
    if config.tools:
        for tool_name in config.tools:
            tool = get_registered_tool(registry, tool_name)
            if tool:
                tools_schemas.append(tool_schema_for_name(tool, tool_name))

    # Run the ReAct loop
    start_time = time.monotonic()
    tool_calls_made: list[dict[str, Any]] = []
    steps_taken = 0
    max_steps = config.max_steps
    result = None

    try:
        # Start heartbeat in background
        heartbeat_stop = multiprocessing.Event()

        def heartbeat_worker():
            while not heartbeat_stop.is_set():
                try:
                    hb = AgentMessage(
                        from_agent=config.name,
                        to_agent="main",
                        msg_type="heartbeat",
                        content="alive",
                    )
                    output_queue.put(hb.serialize(), timeout=1)
                except Exception:
                    pass
                heartbeat_stop.wait(HEARTBEAT_INTERVAL)

        import threading
        hb_thread = threading.Thread(target=heartbeat_worker, daemon=True)
        hb_thread.start()

        while steps_taken < max_steps:
            # Check for cancel signal
            try:
                while not input_queue.empty():
                    data = input_queue.get_nowait()
                    msg = AgentMessage.deserialize(data)
                    if msg.msg_type == "cancel":
                        result = SubAgentResult(
                            name=config.name,
                            success=False,
                            error="Cancelled by parent",
                            duration_ms=(time.monotonic() - start_time) * 1000,
                            steps_taken=steps_taken,
                            tool_calls=tool_calls_made,
                        )
                        _send_result(output_queue, config.name, result)
                        heartbeat_stop.set()
                        return
            except Exception:
                pass

            steps_taken += 1

            # LLM call with timeout
            try:
                response = loop.run_until_complete(
                    _asyncio.wait_for(
                        client.chat.completions.create(
                            model=model,
                            messages=messages,
                            tools=tools_schemas if tools_schemas else None,
                            tool_choice="auto" if tools_schemas else None,
                            temperature=config.temperature,
                        ),
                        timeout=config.timeout,
                    )
                )
            except TimeoutError:
                result = SubAgentResult(
                    name=config.name,
                    success=False,
                    error=f"Timed out after {config.timeout}s",
                    duration_ms=(time.monotonic() - start_time) * 1000,
                    steps_taken=steps_taken,
                    tool_calls=tool_calls_made,
                )
                _send_result(output_queue, config.name, result)
                heartbeat_stop.set()
                return

            message = response.choices[0].message

            if message.tool_calls:
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

                    try:
                        tool_result = _execute_tool_guarded(
                            registry,
                            tc,
                            config=config,
                            output_queue=output_queue,
                            input_queue=input_queue,
                            auto_allow_threshold=auto_allow_threshold,
                            confirmation_timeout=confirmation_timeout,
                            interactive=interactive,
                            loop=loop,
                        )
                    except Exception as e:
                        tool_result = f"Error: {e}"

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_result,
                    })
            else:
                # Final answer
                final_response = message.content or "No response"
                result = SubAgentResult(
                    name=config.name,
                    success=True,
                    response=final_response,
                    duration_ms=(time.monotonic() - start_time) * 1000,
                    steps_taken=steps_taken,
                    tool_calls=tool_calls_made,
                )
                _send_result(output_queue, config.name, result)
                heartbeat_stop.set()
                return

        # Max steps
        result = SubAgentResult(
            name=config.name,
            success=False,
            error=f"Max steps ({max_steps}) reached",
            duration_ms=(time.monotonic() - start_time) * 1000,
            steps_taken=steps_taken,
            tool_calls=tool_calls_made,
        )
        _send_result(output_queue, config.name, result)
        heartbeat_stop.set()

    except Exception as e:
        result = SubAgentResult(
            name=config.name,
            success=False,
            error=str(e),
            duration_ms=(time.monotonic() - start_time) * 1000,
            steps_taken=steps_taken,
            tool_calls=tool_calls_made,
        )
        _send_result(output_queue, config.name, result)


def _execute_tool_guarded(
    registry,
    tool_call,
    *,
    config: SubAgentConfig,
    output_queue: multiprocessing.Queue,
    input_queue: multiprocessing.Queue,
    auto_allow_threshold: str,
    confirmation_timeout: float,
    interactive: bool,
    loop: asyncio.AbstractEventLoop | None = None,
) -> str:
    """Execute a tool with risk gating and IPC bridge for confirmations / ask_user."""
    from core.tools.aliases import get_registered_tool, resolve_tool_name

    tool_name = tool_call.function.name
    resolved = resolve_tool_name(tool_name)
    tool = get_registered_tool(registry, tool_name)
    if tool is None:
        return f"Error: Tool '{tool_name}' not found"

    try:
        args = json.loads(tool_call.function.arguments)
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON arguments - {e}"

    if resolved == "ask_user":
        return _ipc_ask_user(
            config.name,
            args,
            output_queue,
            input_queue,
            confirmation_timeout,
        )

    from core.security.confirmation import (
        ConfirmationChoice,
        PermissionManager,
        RiskClassifier,
        RiskLevel,
    )

    classifier = RiskClassifier()
    assessment = classifier.classify(resolved, tool, args)
    risk_order = {RiskLevel.NO: 0, RiskLevel.LOW: 1, RiskLevel.MEDIUM: 2, RiskLevel.HIGH: 3}
    try:
        threshold = RiskLevel(auto_allow_threshold)
    except ValueError:
        threshold = RiskLevel.LOW

    run_loop = loop or _ensure_event_loop()

    if risk_order.get(assessment.risk_level, 0) <= risk_order.get(threshold, 1):
        return run_loop.run_until_complete(tool.execute(**args))

    permissions = PermissionManager()
    if permissions.is_allowed(
        resolved, assessment.risk_level, assessment.pattern_matched
    ):
        return run_loop.run_until_complete(tool.execute(**args))

    if not interactive:
        return (
            f"Error: Tool '{tool_name}' requires confirmation but sub-agent is non-interactive. "
            f"Reason: {assessment.reason}"
        )

    choice_value = _ipc_request_confirmation(
        config.name,
        assessment,
        output_queue,
        input_queue,
        confirmation_timeout,
    )
    if choice_value == ConfirmationChoice.DENY.value:
        return f"Error: Tool call '{tool_name}' denied by user. Reason: {assessment.reason}"

    if choice_value == ConfirmationChoice.ALLOW_SESSION.value:
        from core.security.confirmation import PermissionScope

        permissions.grant(
            tool_name,
            PermissionScope.SESSION,
            assessment.risk_level,
            assessment.pattern_matched,
        )
    elif choice_value == ConfirmationChoice.ALLOW_ALWAYS.value:
        from core.security.confirmation import PermissionScope

        permissions.grant(
            tool_name,
            PermissionScope.ALWAYS,
            assessment.risk_level,
            assessment.pattern_matched,
        )

    return run_loop.run_until_complete(tool.execute(**args))


def _ipc_request_confirmation(
    subagent_name: str,
    assessment,
    output_queue: multiprocessing.Queue,
    input_queue: multiprocessing.Queue,
    timeout: float,
) -> str:
    request_id = f"subcfm_{uuid.uuid4().hex[:10]}"
    msg = AgentMessage(
        from_agent=subagent_name,
        to_agent="main",
        msg_type="confirmation_request",
        content=assessment.reason,
        message_id=request_id,
        metadata={
            "request_id": request_id,
            "tool_name": assessment.tool_name,
            "arguments": assessment.arguments,
            "risk_level": assessment.risk_level.value,
            "reason": assessment.reason,
            "pattern_matched": assessment.pattern_matched,
        },
    )
    output_queue.put(msg.serialize(), timeout=5)
    return _wait_ipc_response(
        input_queue,
        request_id,
        expected_type="confirmation_response",
        timeout=timeout,
        default="deny",
    )


def _ipc_ask_user(
    subagent_name: str,
    args: dict[str, Any],
    output_queue: multiprocessing.Queue,
    input_queue: multiprocessing.Queue,
    timeout: float,
) -> str:
    request_id = f"subq_{uuid.uuid4().hex[:10]}"
    question = str(args.get("question", "") or "").strip()
    if not question:
        return "Error: ask_user requires a non-empty question"
    msg = AgentMessage(
        from_agent=subagent_name,
        to_agent="main",
        msg_type="question",
        content=question,
        message_id=request_id,
        metadata={
            "request_id": request_id,
            "question": question,
            "context": str(args.get("context", "") or ""),
        },
    )
    output_queue.put(msg.serialize(), timeout=5)
    return _wait_ipc_response(
        input_queue,
        request_id,
        expected_type="question_response",
        timeout=timeout,
        default="Error: question timed out — no answer from user",
    )


def _wait_ipc_response(
    input_queue: multiprocessing.Queue,
    request_id: str,
    *,
    expected_type: str,
    timeout: float,
    default: str,
) -> str:
    deadline = time.monotonic() + (timeout if timeout > 0 else 300.0)
    while time.monotonic() < deadline:
        remaining = max(0.1, deadline - time.monotonic())
        try:
            data = input_queue.get(timeout=min(1.0, remaining))
        except Exception:
            continue
        try:
            msg = AgentMessage.deserialize(data)
        except Exception:
            continue
        if msg.msg_type == "cancel":
            return default
        if msg.msg_type == expected_type and msg.message_id == request_id:
            return msg.content or default
    return default


def _send_result(
    output_queue: multiprocessing.Queue,
    agent_name: str,
    result: SubAgentResult,
) -> None:
    """Send a result message back to the parent process."""
    msg = AgentMessage(
        from_agent=agent_name,
        to_agent="main",
        msg_type="result",
        content=result.response,
        metadata={
            "success": result.success,
            "error": result.error,
            "duration_ms": result.duration_ms,
            "steps_taken": result.steps_taken,
            "tool_calls": result.tool_calls,
        },
    )
    try:
        output_queue.put(msg.serialize(), timeout=5)
    except Exception:
        pass


def _build_process_system_prompt(
    config: SubAgentConfig,
    task: str,
    *,
    skills_block: str = "",
) -> str:
    """Build system prompt for a process-mode sub-agent."""
    base = config.system_prompt or f"You are {config.name}, a specialized AI assistant."
    prompt = f"""{base}

## Your Task
{task}

## Available Tools
{', '.join(config.tools) if config.tools else 'No tools available'}

## Instructions
1. Focus on your specific task
2. Use tools when needed
3. Provide a clear, concise final answer
4. If you cannot complete the task, explain why

Remember: You are {config.name}. Stay focused on your specialized role.
"""
    if skills_block:
        prompt += f"\n\n{skills_block}"
    from core.project.helix_md import append_helix_project_context

    return append_helix_project_context(prompt)


class SubAgentProcessManager:
    """Manages sub-agents running in separate OS processes.

    Provides:
    - Process spawning via multiprocessing.Process
    - Heartbeat monitoring (detect hangs)
    - Graceful shutdown (SIGTERM → grace period → SIGKILL)
    - Result collection from output_queue
    """

    def __init__(
        self,
        parent_agent: Any,
        comm_bus: ProcessCommunicationBus | None = None,
    ):
        self._parent = parent_agent
        self._comm_bus = comm_bus or ProcessCommunicationBus()
        self._active_handles: dict[str, SubAgentHandle] = {}
        self._heartbeat_task: asyncio.Task | None = None

    async def run(
        self,
        config: SubAgentConfig,
        task: str,
    ) -> SubAgentHandle:
        """Launch a sub-agent in a separate OS process.

        Args:
            config: Sub-agent configuration.
            task: Task description.

        Returns:
            SubAgentHandle for tracking.
        """
        # Register communication queues
        self._comm_bus.register(config.name)

        # Get queues for this sub-agent
        input_queue = self._comm_bus.get_input_queue(config.name)
        output_queue = self._comm_bus.get_output_queue(config.name)

        # Prepare config dict (must be serializable for multiprocessing)
        config_dict = {
            "name": config.name,
            "system_prompt": config.system_prompt,
            "model": config.model,
            "tools": config.tools,
            "max_steps": config.max_steps,
            "mode": config.mode,
            "process_mode": "process",
            "timeout": config.timeout,
            "memory_access": config.memory_access.value if isinstance(config.memory_access, MemoryAccess) else config.memory_access,
            "temperature": config.temperature,
            "description": config.description,
            "tags": config.tags,
        }

        # Get parent config for subprocess
        parent_cfg = getattr(self._parent, "config", None)
        parent_base_url = getattr(parent_cfg, "base_url", "http://localhost:11434/v1")
        parent_api_key = getattr(parent_cfg, "api_key", "ollama")
        auto_allow_threshold = str(
            getattr(parent_cfg, "auto_allow_threshold", "low") or "low"
        )
        confirmation_timeout = float(
            getattr(parent_cfg, "confirmation_timeout", 300) or 300
        )
        interactive = not bool(getattr(parent_cfg, "non_interactive", False))
        search_config = dict(getattr(parent_cfg, "search", None) or {})

        # LTM paths for shared memory access
        ltm_db_path = ""
        vector_db_path = ""
        if config.memory_access != MemoryAccess.ISOLATED and hasattr(self._parent, "memory"):
            from config import settings
            ltm_db_path = str(settings.ltm_db_path)
            vector_db_path = str(settings.vector_db_path)

        # Create handle
        handle = SubAgentHandle(
            name=config.name,
            config=config,
            status=SubAgentStatus.RUNNING,
            started_at=time.monotonic(),
        )

        # Spawn the process
        process = multiprocessing.Process(
            target=run_sub_agent_in_process,
            args=(
                config_dict,
                task,
                input_queue,
                output_queue,
                self._parent.model,
                ltm_db_path,
                vector_db_path,
                getattr(self._parent.config, "mcp_servers", None) if hasattr(self._parent, "config") else None,
                str(getattr(self._parent.config, "skills_dir", "") or ""),
                dict(getattr(self._parent.config, "skill_assignments", None) or {}),
                auto_allow_threshold,
                confirmation_timeout,
                interactive,
                search_config,
            ),
            daemon=True,  # Die with parent
        )
        _start_subagent_process(
            process,
            api_key=parent_api_key,
            base_url=parent_base_url,
        )

        handle.task = process
        handle.process_id = process.pid

        self._active_handles[config.name] = handle

        # Start result collector task
        asyncio.create_task(self._collect_result(config.name, output_queue, handle))

        return handle

    async def _collect_result(
        self,
        agent_name: str,
        output_queue: multiprocessing.Queue,
        handle: SubAgentHandle,
    ) -> None:
        """Background task that monitors the output queue for results.

        Args:
            agent_name: Sub-agent name.
            output_queue: Queue to monitor.
            handle: Handle to update when result arrives.
        """
        while not handle.is_done:
            try:
                # Non-blocking check with timeout
                data = output_queue.get(timeout=1.0)
                msg = AgentMessage.deserialize(data)

                if msg.msg_type == "result":
                    # Final result received
                    meta = msg.metadata
                    handle.result = SubAgentResult(
                        name=agent_name,
                        success=meta.get("success", False),
                        response=msg.content,
                        error=meta.get("error"),
                        duration_ms=meta.get("duration_ms", 0),
                        steps_taken=meta.get("steps_taken", 0),
                        tool_calls=meta.get("tool_calls", []),
                    )
                    handle.status = SubAgentStatus.COMPLETED if handle.result.success else SubAgentStatus.FAILED
                    self._notify_parent_done(agent_name)
                    return

                elif msg.msg_type == "heartbeat":
                    pass

                elif msg.msg_type == "confirmation_request":
                    await self._handle_ipc_confirmation(agent_name, msg)

                elif msg.msg_type == "question":
                    await self._handle_ipc_question(agent_name, msg)

                elif msg.msg_type == "error":
                    handle.result = SubAgentResult(
                        name=agent_name,
                        success=False,
                        error=msg.content,
                        duration_ms=(time.monotonic() - (handle.started_at or time.monotonic())) * 1000,
                    )
                    handle.status = SubAgentStatus.FAILED
                    self._notify_parent_done(agent_name)
                    return

            except Exception:
                # Queue.get timeout — check if process is still alive
                if handle.task and not handle.task.is_alive():
                    # Process died without sending result
                    handle.result = SubAgentResult(
                        name=agent_name,
                        success=False,
                        error="Sub-agent process terminated unexpectedly",
                        duration_ms=(time.monotonic() - (handle.started_at or time.monotonic())) * 1000,
                    )
                    handle.status = SubAgentStatus.FAILED
                    self._notify_parent_done(agent_name)
                    return

    async def _handle_ipc_confirmation(self, agent_name: str, msg: AgentMessage) -> None:
        bridge = getattr(getattr(self._parent, "subagents", None), "interactions", None)
        if bridge is None:
            return
        choice_value = await bridge.handle_ipc_confirmation(
            agent_name,
            msg.metadata or {},
        )
        response = AgentMessage(
            from_agent="main",
            to_agent=agent_name,
            msg_type="confirmation_response",
            content=choice_value,
            message_id=msg.message_id or msg.metadata.get("request_id", ""),
        )
        input_queue = self._comm_bus.get_input_queue(agent_name)
        if input_queue:
            input_queue.put(response.serialize())

    async def _handle_ipc_question(self, agent_name: str, msg: AgentMessage) -> None:
        bridge = getattr(getattr(self._parent, "subagents", None), "interactions", None)
        if bridge is None:
            return
        answer = await bridge.handle_ipc_question(agent_name, msg.metadata or {})
        response = AgentMessage(
            from_agent="main",
            to_agent=agent_name,
            msg_type="question_response",
            content=answer,
            message_id=msg.message_id or msg.metadata.get("request_id", ""),
        )
        input_queue = self._comm_bus.get_input_queue(agent_name)
        if input_queue:
            input_queue.put(response.serialize())

    def _notify_parent_done(self, name: str) -> None:
        mgr = getattr(self._parent, "subagents", None)
        if mgr is not None:
            mgr.notify_handle_finished(name)

    async def cancel(self, name: str) -> bool:
        """Cancel a running sub-agent process.

        Graceful shutdown: SIGTERM → 5s grace period → SIGKILL

        Args:
            name: Sub-agent name.

        Returns:
            True if cancellation was initiated.
        """
        handle = self._active_handles.get(name)
        if not handle or not handle.is_running:
            return False

        process = handle.task
        if not process or not process.is_alive():
            return False

        # Send cancel message
        cancel_msg = AgentMessage(
            from_agent="main",
            to_agent=name,
            msg_type="cancel",
            content="Cancellation requested",
        )
        input_queue = self._comm_bus.get_input_queue(name)
        if input_queue:
            input_queue.put(cancel_msg.serialize())

        # Wait for graceful exit
        process.join(timeout=GRACE_PERIOD)

        if process.is_alive():
            logger.warning(f"Force-killing sub-agent '{name}' (PID {process.pid})")
            if process.pid:
                terminate_process(process.pid, grace=1.0)
            process.join(timeout=1)

        handle.status = SubAgentStatus.CANCELLED
        return True

    async def terminate_all(self) -> None:
        """Terminate all running sub-agent processes."""
        for name in list(self._active_handles.keys()):
            await self.cancel(name)

    def get_handle(self, name: str) -> SubAgentHandle | None:
        """Get handle for a sub-agent."""
        return self._active_handles.get(name)

    def list_active(self) -> list[SubAgentHandle]:
        """List all running sub-agent processes."""
        return [h for h in self._active_handles.values() if h.is_running]