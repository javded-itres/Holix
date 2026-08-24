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
import queue
import threading
import time
import uuid
from typing import Any

from core.platform_compat import terminate_process
from core.subagents.base import (
    MemoryAccess,
    SubAgentConfig,
    SubAgentHandle,
    SubAgentResult,
    SubAgentStatus,
)
from core.subagents.communication import (
    AgentMessage,
    ProcessCommunicationBus,
    reset_subagent_mp_context,
    subagent_mp_context,
)

logger = logging.getLogger(__name__)

# Heartbeat interval (seconds) — sub-agents send heartbeat messages
# at this interval so the parent can detect hangs.
HEARTBEAT_INTERVAL = 5.0

# Grace period after SIGTERM before SIGKILL (seconds)
GRACE_PERIOD = 5.0

# Child reads credentials from env (not Process args — avoids pickle/log exposure).
_SUBAGENT_API_KEY_ENV = "HOLIX_SUBAGENT_API_KEY"
_SUBAGENT_BASE_URL_ENV = "HOLIX_SUBAGENT_BASE_URL"
_SUBAGENT_PRESET_ENV = "HOLIX_SUBAGENT_PRESET_ID"
_subagent_spawn_lock = threading.Lock()


class SubAgentProcessSpawnError(RuntimeError):
    """Failed to start a sub-agent OS process (IPC / stdio descriptor issue)."""


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
    preset_id: str = "",
) -> None:
    """Start a sub-agent process with credentials in the child environment only."""
    with _subagent_spawn_lock:
        prev = {
            _SUBAGENT_API_KEY_ENV: os.environ.get(_SUBAGENT_API_KEY_ENV),
            _SUBAGENT_BASE_URL_ENV: os.environ.get(_SUBAGENT_BASE_URL_ENV),
            _SUBAGENT_PRESET_ENV: os.environ.get(_SUBAGENT_PRESET_ENV),
        }
        os.environ[_SUBAGENT_API_KEY_ENV] = api_key
        os.environ[_SUBAGENT_BASE_URL_ENV] = base_url
        os.environ[_SUBAGENT_PRESET_ENV] = preset_id
        try:
            try:
                process.start()
            except ValueError as exc:
                if "fds_to_keep" in str(exc):
                    raise SubAgentProcessSpawnError(str(exc)) from exc
                raise
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
    data_dir: str = "",
    mcp_servers: dict[str, Any] | None = None,
    skills_dir: str = "",
    skill_assignments: dict[str, list[str]] | None = None,
    auto_allow_threshold: str = "low",
    confirmation_timeout: float = 0.0,
    interactive: bool = True,
    search_config: dict[str, Any] | None = None,
    profile_name: str = "default",
    workspace_root: str = "",
    workspace_jail_enabled: bool = False,
    working_directory: str = "",
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
        Credentials are read from HOLIX_SUBAGENT_API_KEY / HOLIX_SUBAGENT_BASE_URL in the child env.
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
    parent_api_key = os.environ.get(_SUBAGENT_API_KEY_ENV, "")

    from core.models.client_factory import create_openai_client

    preset_id = (os.environ.get(_SUBAGENT_PRESET_ENV) or "").strip() or None
    client = create_openai_client(
        base_url=parent_base_url,
        api_key=parent_api_key,
        metadata={"preset_id": preset_id} if preset_id else None,
    )

    # Match parent process CWD so relative paths hit the same project tree
    if working_directory and str(working_directory).strip():
        try:
            from pathlib import Path as _Path

            os.chdir(_Path(working_directory).expanduser().resolve())
        except OSError as exc:
            print(f"[sub-process] chdir to working_directory failed: {exc}")

    # Create own tool registry with the same workspace as the main agent
    from core.tools.registry import ToolRegistry

    registry = ToolRegistry(
        workspace_root=(workspace_root or None),
        workspace_jail_enabled=bool(workspace_jail_enabled),
        profile_name=profile_name,
    )
    registry.register_all()

    # MCP for this sub: assigned names + parent defs, filling popular catalogs
    # (Context7 may be assigned on python-coder but missing from parent mcp_servers).
    assigned_mcp = [
        str(s).strip() for s in (getattr(config, "mcp_servers", None) or []) if str(s).strip()
    ]
    if assigned_mcp:
        try:
            from core.mcp.assign import mcp_defs_for_names

            subset = mcp_defs_for_names(mcp_servers, assigned_mcp)
            if subset:
                loop.run_until_complete(
                    registry.register_mcp(subset, {"main": assigned_mcp}, slot="main")
                )
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
            if vector_db_path:
                settings.vector_db_path = vector_db_path
            memory = LongTermMemoryManager()
            loop.run_until_complete(memory.initialize_db())
        except Exception:
            # Memory access is best-effort in subprocess
            pass

    skills_block = ""
    if skills_dir:
        try:
            from core.di.runtime_config import HolixRuntimeConfig
            from core.skills.manager import SkillsManager

            sk_cfg = HolixRuntimeConfig.from_settings().with_overrides(
                skills_dir=skills_dir,
                skill_assignments=skill_assignments or {},
            )
            sk_mgr = SkillsManager(sk_cfg)
            skills_block = sk_mgr.skills_prompt_block(
                task,
                agent_slot=config.agent_type or config.name,
            )
        except Exception:
            pass

    from core.subagents.prompt import build_subagent_system_prompt

    system_prompt = build_subagent_system_prompt(
        config,
        task,
        skills_block=skills_block,
        profile_name=profile_name,
        workspace_root=workspace_root or None,
        workspace_jail_enabled=bool(workspace_jail_enabled),
        working_directory=working_directory or None,
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

    # Inject relevant memories
    if memory and config.memory_access != MemoryAccess.ISOLATED:
        try:
            context = loop.run_until_complete(memory.get_relevant_context(task, top_k=3))
            memory_parts = []
            for ep in context.get("episodic", []):
                memory_parts.append(f"[Past experience]: {ep.get('content', '')[:200]}")
            if memory_parts:
                messages.append(
                    {
                        "role": "system",
                        "content": "Relevant context:\n" + "\n".join(memory_parts),
                    }
                )
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
    tokens_used = 0
    llm_calls = 0
    usage_accounted = True  # flipped False if IPC emit fails
    max_steps = int(config.max_steps or 0)
    base_max_steps = max_steps
    step_budget_extensions = 0
    result = None

    def _usage_fields() -> dict[str, Any]:
        return {
            "tokens_used": tokens_used,
            "llm_calls": llm_calls,
            "usage_accounted": bool(usage_accounted and llm_calls > 0),
            "model": str(model or ""),
        }

    def _send_llm_usage(
        *,
        usage: dict[str, int],
        step: int,
        duration_ms: float,
        finish_reason: str | None = None,
    ) -> None:
        """Notify parent process so Studio can meter model.calls + tokens live."""
        nonlocal usage_accounted
        try:
            msg = AgentMessage(
                from_agent=config.name,
                to_agent="main",
                msg_type="llm_usage",
                content="",
                metadata={
                    "model": str(model or ""),
                    "step": int(step or 0),
                    "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                    "completion_tokens": int(usage.get("completion_tokens") or 0),
                    "total_tokens": int(usage.get("total_tokens") or 0),
                    "duration_ms": float(duration_ms or 0),
                    "finish_reason": finish_reason,
                },
            )
            output_queue.put(msg.serialize(), timeout=0.5)
        except Exception:
            usage_accounted = False

    try:
        from core.runtime.step_budget import StepBudgetPolicy, evaluate_step_budget

        # Process workers may not have full parent Settings; use env-backed defaults.
        try:
            from config import settings as _settings

            step_policy = StepBudgetPolicy.from_config(_settings)
        except Exception:
            step_policy = StepBudgetPolicy()

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

        react_out = _try_process_react_run(
            loop=loop,
            config=config,
            task=task,
            client=client,
            model=str(model or ""),
            registry=registry,
            skills_dir=skills_dir,
            skill_assignments=skill_assignments,
            profile_name=profile_name,
            system_prompt=system_prompt,
            start_time=start_time,
            output_queue=output_queue,
            input_queue=input_queue,
        )
        if react_out is not None:
            heartbeat_stop.set()
            _send_result(output_queue, config.name, react_out)
            return

        force_final = False
        force_native = False
        leak_retries = 0
        empty_final_retries = 0
        while True:
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
                                **_usage_fields(),
                            )
                            _send_result(output_queue, config.name, result)
                            heartbeat_stop.set()
                            return
                except Exception:
                    pass

                steps_taken += 1
                _send_progress(
                    output_queue,
                    config.name,
                    kind="step",
                    message=f"Reasoning step {steps_taken}/{max_steps}",
                    steps_taken=steps_taken,
                )

                # Drain supervisor guidance / cancel from parent
                try:
                    while True:
                        try:
                            data = input_queue.get_nowait()
                        except Exception:
                            break
                        msg = AgentMessage.deserialize(data)
                        if msg.msg_type == "cancel":
                            result = SubAgentResult(
                                name=config.name,
                                success=False,
                                error="Cancelled by parent",
                                duration_ms=(time.monotonic() - start_time) * 1000,
                                steps_taken=steps_taken,
                                tool_calls=tool_calls_made,
                                **_usage_fields(),
                            )
                            _send_result(output_queue, config.name, result)
                            heartbeat_stop.set()
                            return
                        if msg.msg_type in {"guidance", "revise"} and (msg.content or "").strip():
                            messages.append(
                                {
                                    "role": "system",
                                    "content": (
                                        "### Runtime supervisor intervention\n"
                                        "The parent runtime detected a problem and sent guidance. "
                                        "Follow it on this step:\n\n"
                                        f"{msg.content.strip()}"
                                    ),
                                }
                            )
                            _send_progress(
                                output_queue,
                                config.name,
                                kind="status",
                                message="Applied supervisor guidance",
                                steps_taken=steps_taken,
                            )
                except Exception:
                    pass

                # LLM call with timeout
                llm_t0 = time.monotonic()
                try:
                    use_tools = tools_schemas if tools_schemas and not force_final else None
                    if force_final:
                        choice = "none"
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

                    def _llm_once(tool_choice: str | None):
                        return loop.run_until_complete(
                            _asyncio.wait_for(
                                client.chat.completions.create(
                                    model=model,
                                    messages=messages,
                                    tools=use_tools,
                                    tool_choice=tool_choice,
                                    temperature=config.temperature,
                                ),
                                timeout=config.timeout,
                            )
                        )

                    response = None
                    last_choice = choice
                    for attempt in range(3):
                        try:
                            response = _llm_once(last_choice)
                        except Exception:
                            if attempt == 0 and last_choice == "required" and use_tools:
                                last_choice = "auto"
                                response = _llm_once("auto")
                            else:
                                raise
                        if not is_empty_llm_response(response):
                            break
                        _send_progress(
                            output_queue,
                            config.name,
                            kind="status",
                            message=f"Empty LLM response, retry {attempt + 1}/3",
                            steps_taken=steps_taken,
                        )
                        time.sleep(0.4 * (attempt + 1))
                except TimeoutError:
                    result = SubAgentResult(
                        name=config.name,
                        success=False,
                        error=f"Timed out after {config.timeout}s",
                        duration_ms=(time.monotonic() - start_time) * 1000,
                        steps_taken=steps_taken,
                        tool_calls=tool_calls_made,
                        **_usage_fields(),
                    )
                    _send_result(output_queue, config.name, result)
                    heartbeat_stop.set()
                    return

                message = first_choice_message(response)
                if message is None:
                    result = SubAgentResult(
                        name=config.name,
                        success=False,
                        error=EMPTY_LLM_ERROR,
                        duration_ms=(time.monotonic() - start_time) * 1000,
                        steps_taken=steps_taken,
                        tool_calls=tool_calls_made,
                        **_usage_fields(),
                    )
                    _send_result(output_queue, config.name, result)
                    heartbeat_stop.set()
                    return
                llm_duration_ms = (time.monotonic() - llm_t0) * 1000
                try:
                    from core.llm.usage import (
                        completion_text_from_message,
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
                        finish_reason = getattr(response.choices[0], "finish_reason", None)
                    except Exception:
                        finish_reason = None
                    _send_llm_usage(
                        usage=usage,
                        step=steps_taken,
                        duration_ms=llm_duration_ms,
                        finish_reason=finish_reason,
                    )
                except Exception:
                    usage_accounted = False

                native_calls = list(message.tool_calls or [])
                final_override = None
                if not native_calls:
                    from core.llm.tool_calls import resolve_textual_turn, tool_call_objects

                    turn = resolve_textual_turn(
                        message.content,
                        tools=tools_schemas,
                        force_final=force_final,
                    )
                    if turn.kind == "tools":
                        native_calls = tool_call_objects(turn.tool_calls)
                        force_native = False
                        _send_progress(
                            output_queue,
                            config.name,
                            kind="status",
                            message=f"Recovered {len(native_calls)} textual tool call(s)",
                            steps_taken=steps_taken,
                        )
                    elif turn.kind == "retry":
                        leak_retries += 1
                        force_native = True
                        messages.append({"role": "assistant", "content": message.content or ""})
                        messages.append({"role": "system", "content": turn.nudge})
                        _send_progress(
                            output_queue,
                            config.name,
                            kind="status",
                            message="Rejected leaked/broken tool_call as final",
                            steps_taken=steps_taken,
                            details=(message.content or "")[:240],
                        )
                        if leak_retries >= 2:
                            result = SubAgentResult(
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
                            _send_result(output_queue, config.name, result)
                            heartbeat_stop.set()
                            return
                        continue
                    else:
                        final_override = turn.final_text

                if native_calls:
                    force_native = False
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
                        _send_progress(
                            output_queue,
                            config.name,
                            kind="tool_start",
                            message=f"Calling {tool_name}",
                            steps_taken=steps_taken,
                            tool_name=tool_name,
                            details=(tc.function.arguments or "")[:300],
                        )

                        try:
                            tool_result = _execute_tool_guarded(
                                registry,
                                tc,
                                config=config,
                                profile_name=profile_name,
                                output_queue=output_queue,
                                input_queue=input_queue,
                                auto_allow_threshold=auto_allow_threshold,
                                confirmation_timeout=confirmation_timeout,
                                interactive=interactive,
                                data_dir=data_dir,
                                loop=loop,
                            )
                        except Exception as e:
                            tool_result = f"Error: {e}"

                        preview = (tool_result or "").strip()
                        if len(preview) > 240:
                            preview = preview[:239] + "…"
                        tool_calls_made[-1]["result"] = tool_result
                        _send_progress(
                            output_queue,
                            config.name,
                            kind="tool_result",
                            message=f"{tool_name} finished",
                            steps_taken=steps_taken,
                            tool_name=tool_name,
                            details=preview,
                        )

                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "name": tool_name,
                                "content": tool_result,
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
                            force_final = True
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
                            force_final = True
                            messages.append(
                                {
                                    "role": "system",
                                    "content": (
                                        "### Stop repeating the same terminal command\n"
                                        "It already failed the same way. Do not call it again. "
                                        "Write the final answer with NO tool calls."
                                    ),
                                }
                            )
                    except Exception:
                        pass

                else:
                    # Final answer
                    from core.llm.completion import EMPTY_FINAL_CONTINUE, is_blank_final_text

                    final_response = (
                        final_override if final_override is not None else (message.content or "")
                    )
                    if is_blank_final_text(final_response) or is_blank_final_text(
                        getattr(message, "content", None)
                    ):
                        empty_final_retries += 1
                        messages.append(
                            {
                                "role": "assistant",
                                "content": str(getattr(message, "content", "") or "").strip(),
                            }
                        )
                        messages.append({"role": "system", "content": EMPTY_FINAL_CONTINUE})
                        _send_progress(
                            output_queue,
                            config.name,
                            kind="status",
                            message=f"Empty model reply — continue {empty_final_retries}/3",
                            steps_taken=steps_taken,
                        )
                        if empty_final_retries >= 3:
                            result = SubAgentResult(
                                name=config.name,
                                success=False,
                                error="empty LLM reply (no text, no tools)",
                                duration_ms=(time.monotonic() - start_time) * 1000,
                                steps_taken=steps_taken,
                                tool_calls=tool_calls_made,
                                **_usage_fields(),
                            )
                            _send_result(output_queue, config.name, result)
                            heartbeat_stop.set()
                            return
                        continue

                    result = SubAgentResult(
                        name=config.name,
                        success=True,
                        response=final_response,
                        duration_ms=(time.monotonic() - start_time) * 1000,
                        steps_taken=steps_taken,
                        tool_calls=tool_calls_made,
                        **_usage_fields(),
                    )
                    _propose_skill_in_subprocess(
                        loop=loop,
                        skills_dir=skills_dir,
                        skill_assignments=skill_assignments,
                        client=client,
                        model=str(model or ""),
                        messages=messages,
                        final_response=final_response,
                        profile_name=profile_name,
                        config=config,
                    )
                    _send_result(output_queue, config.name, result)
                    heartbeat_stop.set()
                    return

            # Max steps: health-check — extend if still working
            decision = evaluate_step_budget(
                step_count=steps_taken,
                max_steps=max_steps,
                extensions_used=step_budget_extensions,
                messages=messages,
                tool_calls_log=tool_calls_made,
                task=str(task or ""),
                policy=step_policy,
                base_max_steps=base_max_steps,
            )
            if decision.extend:
                prev = max_steps
                max_steps = decision.new_max_steps
                step_budget_extensions = decision.extensions_used
                _send_progress(
                    output_queue,
                    config.name,
                    kind="step_budget_extended",
                    message=(
                        f"Step budget +{decision.extra_steps} "
                        f"({prev} → {max_steps}): {decision.reason}"
                    ),
                    steps_taken=steps_taken,
                )
                continue

            result = SubAgentResult(
                name=config.name,
                success=False,
                error=f"Max steps ({max_steps}) reached: {decision.reason}",
                duration_ms=(time.monotonic() - start_time) * 1000,
                steps_taken=steps_taken,
                tool_calls=tool_calls_made,
                **_usage_fields(),
            )
            _send_result(output_queue, config.name, result)
            heartbeat_stop.set()
            return

    except Exception as e:
        result = SubAgentResult(
            name=config.name,
            success=False,
            error=str(e),
            duration_ms=(time.monotonic() - start_time) * 1000,
            steps_taken=steps_taken,
            tool_calls=tool_calls_made,
            **_usage_fields(),
        )
        _send_result(output_queue, config.name, result)


def _try_process_react_run(
    *,
    loop: Any,
    config: SubAgentConfig,
    task: str,
    client: Any,
    model: str,
    registry: Any,
    skills_dir: str,
    skill_assignments: dict[str, list[str]] | None,
    profile_name: str,
    system_prompt: str,
    start_time: float,
    output_queue: Any,
    input_queue: Any | None = None,
) -> SubAgentResult | None:
    """Best-effort LangGraph ReAct in the worker process."""
    try:
        from types import SimpleNamespace

        from core.agent import HolixAgent
        from core.agent_events import ToolCallResultEvent, ToolCallStartEvent
        from core.di.runtime_config import HolixRuntimeConfig
        from core.skills.manager import SkillsManager
        from core.subagents.react_agent import resolve_subagent_context_window

        base_cfg = HolixRuntimeConfig.from_settings()
        mm = None
        try:
            from core.models.manager import ModelManager
            from core.profile import ProfileManager

            mm = ModelManager(ProfileManager().load_profile(profile_name or "default"))
        except Exception:
            mm = None
        window = resolve_subagent_context_window(
            SimpleNamespace(
                config=base_cfg,
                model=model,
                active_model_config=None,
                model_manager=mm,
            ),
            config,
        )

        overrides: dict[str, Any] = {
            "model": model,
            "max_steps": int(config.max_steps or 150),
            "execution_mode": "react",
            "use_langgraph": True,
            "enable_subagents": False,
            "enable_meta_agent": False,
            "enable_self_refinement": False,
            "enable_evolution": False,
            "plan_review_enabled": False,
            "context_window": window,
            "skill_assignments": skill_assignments or {},
            "profile_name": profile_name or "default",
        }
        if skills_dir:
            overrides["skills_dir"] = skills_dir
        cfg = HolixRuntimeConfig.from_settings().with_overrides(**overrides)
        skills = None
        if skills_dir:
            skills = SkillsManager(cfg)
        child = HolixAgent(
            config=cfg,
            client=client,
            tools=registry,
            skills=skills,
            enable_monitoring=False,
            allow_defaults=True,
        )
        child.model = model
        child.agent_slot = str(config.agent_type or config.name or "main")
        child.subagent_system_prompt = system_prompt
        child._initialized = True
        child._use_langgraph = True
        child._subagent_manager = None
        if getattr(child, "context_manager", None) is not None:
            child.context_manager.context_window = window

        from core.subagents.react_agent import attach_subagent_runtime

        def _on_guidance() -> None:
            _send_progress(
                output_queue,
                config.name,
                kind="status",
                message="Applied supervisor guidance",
            )

        attach_subagent_runtime(
            child,
            name=config.name,
            input_queue=input_queue,
            on_guidance=_on_guidance,
            handle=None,
        )

        def _progress(event: Any) -> None:
            if isinstance(event, ToolCallStartEvent):
                _send_progress(
                    output_queue,
                    config.name,
                    kind="tool_start",
                    message=f"Calling {event.tool_name}",
                    tool_name=event.tool_name,
                    details=str(event.arguments_raw or event.arguments or "")[:300],
                )
            elif isinstance(event, ToolCallResultEvent):
                preview = (event.result or "")[:240]
                _send_progress(
                    output_queue,
                    config.name,
                    kind="tool_result",
                    message=f"{event.tool_name} finished",
                    tool_name=event.tool_name,
                    details=preview,
                )

        child.events.subscribe(_progress)
        conv_id = f"subagent:{config.name}"
        seed = list(getattr(config, "seed_messages", None) or [])
        if seed and getattr(child, "memory", None) is not None:
            try:
                from core.subagents.fork import apply_fork_seed

                loop.run_until_complete(apply_fork_seed(child.memory, conv_id, seed))
            except Exception:
                pass
        text = loop.run_until_complete(
            child.run(task, conversation_id=conv_id, execution_mode="react")
        )
        from core.graph.nodes.react_node import SUBAGENT_CANCELLED_FINAL
        from core.subagents.react_agent import (
            is_failed_react_result,
            recover_empty_react_text,
        )

        recovered = recover_empty_react_text(text)
        if recovered:
            text = recovered
        if (text or "").strip() == SUBAGENT_CANCELLED_FINAL:
            return SubAgentResult(
                name=config.name,
                success=False,
                error="Cancelled by parent",
                duration_ms=(time.monotonic() - start_time) * 1000,
                model=model,
            )
        failed = is_failed_react_result(text)
        if failed:
            return SubAgentResult(
                name=config.name,
                success=False,
                error=failed,
                response=text or "",
                duration_ms=(time.monotonic() - start_time) * 1000,
                model=model,
            )
        return SubAgentResult(
            name=config.name,
            success=True,
            response=text or "",
            duration_ms=(time.monotonic() - start_time) * 1000,
            model=model,
        )
    except Exception:
        logger = logging.getLogger(__name__)
        logger.exception("process-mode Holix ReAct failed; using legacy loop")
        return None


def _propose_skill_in_subprocess(
    *,
    loop: Any,
    skills_dir: str,
    skill_assignments: dict[str, list[str]] | None,
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
    final_response: str,
    profile_name: str,
    config: SubAgentConfig,
) -> None:
    """Best-effort pending skill from a process-mode job (same disk as parent)."""
    if not skills_dir or client is None or not (model or "").strip():
        return
    try:
        from core.di.runtime_config import HolixRuntimeConfig
        from core.skills.manager import SkillsManager
        from core.skills.self_improve import maybe_propose_skill_from_subagent

        sk_cfg = HolixRuntimeConfig.from_settings().with_overrides(
            skills_dir=skills_dir,
            skill_assignments=skill_assignments or {},
            profile_name=profile_name,
        )
        skills = SkillsManager(sk_cfg)
        loop.run_until_complete(
            maybe_propose_skill_from_subagent(
                skills=skills,
                client=client,
                model=model,
                messages=messages,
                final_response=final_response,
                conversation_id=f"subagent:{config.name}",
                profile=profile_name or "default",
                agent_slot=str(config.agent_type or config.name or "main"),
                emit=None,
                run_id=str(config.name or ""),
                config=sk_cfg,
            )
        )
    except Exception:
        pass


def _execute_tool_guarded(
    registry,
    tool_call,
    *,
    config: SubAgentConfig,
    profile_name: str,
    output_queue: multiprocessing.Queue,
    input_queue: multiprocessing.Queue,
    auto_allow_threshold: str,
    confirmation_timeout: float,
    interactive: bool,
    data_dir: str = "",
    loop: asyncio.AbstractEventLoop | None = None,
) -> str:
    """Execute a tool with risk gating and IPC bridge for confirmations / ask_user."""
    from core.tools.aliases import get_registered_tool, resolve_tool_name

    tool_name = tool_call.function.name
    resolved = resolve_tool_name(tool_name, getattr(registry, "tools", None))
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

    from core.tools.base import filter_execute_kwargs
    from core.tools.execution_context import (
        profile_scope,
        reset_profile_scope,
        reset_subagent_scope,
        subagent_scope,
    )

    args = filter_execute_kwargs(tool.execute, args)
    scope_tokens = subagent_scope(config.name, subagent_type=config.agent_type)
    profile_token = profile_scope(profile_name)
    try:
        if risk_order.get(assessment.risk_level, 0) <= risk_order.get(threshold, 1):
            return run_loop.run_until_complete(tool.execute(**args))

        permissions = PermissionManager(data_dir=data_dir or None)
        if permissions.is_allowed(resolved, assessment.risk_level, assessment.pattern_matched):
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
    finally:
        reset_profile_scope(profile_token)
        reset_subagent_scope(scope_tokens)


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


def _send_progress(
    output_queue: multiprocessing.Queue,
    agent_name: str,
    *,
    kind: str,
    message: str,
    steps_taken: int = 0,
    tool_name: str = "",
    details: str = "",
) -> None:
    """Best-effort live progress for the parent process / Studio UI."""
    try:
        msg = AgentMessage(
            from_agent=agent_name,
            to_agent="main",
            msg_type="progress",
            content=message or "",
            metadata={
                "kind": kind,
                "steps_taken": steps_taken,
                "tool_name": tool_name,
                "details": details,
            },
        )
        output_queue.put(msg.serialize(), timeout=0.5)
    except Exception:
        pass


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
            "tokens_used": int(result.tokens_used or 0),
            "llm_calls": int(getattr(result, "llm_calls", 0) or 0),
            "usage_accounted": bool(getattr(result, "usage_accounted", False)),
            "model": str(getattr(result, "model", "") or ""),
        },
    )
    try:
        output_queue.put(msg.serialize(), timeout=5)
    except Exception as exc:
        logger.error("Sub-agent '%s' failed to send result: %s", agent_name, exc)


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
        # Prepare config dict (must be serializable for multiprocessing)
        config_dict = {
            "name": config.name,
            "agent_type": config.agent_type or config.name,
            "system_prompt": config.system_prompt,
            "model": config.model,
            "tools": config.tools,
            "max_steps": config.max_steps,
            "mode": config.mode,
            "process_mode": "process",
            "timeout": config.timeout,
            "memory_access": config.memory_access.value
            if isinstance(config.memory_access, MemoryAccess)
            else config.memory_access,
            "temperature": config.temperature,
            "description": config.description,
            "tags": config.tags,
            "mcp_servers": list(config.mcp_servers or []),
            "fork": bool(getattr(config, "fork", False)),
            "seed_messages": list(getattr(config, "seed_messages", None) or []),
        }

        # Get parent config for subprocess
        parent_cfg = getattr(self._parent, "config", None)
        parent_base_url = getattr(parent_cfg, "base_url", "http://localhost:11434/v1")
        parent_api_key = (getattr(parent_cfg, "api_key", None) or "").strip()
        if not parent_api_key and hasattr(self._parent, "model_manager"):
            try:
                mc = self._parent.model_manager.get_default_model_config()
            except Exception:
                mc = None
            if mc and mc.api_key:
                parent_api_key = mc.api_key
                if mc.base_url:
                    parent_base_url = mc.base_url
        auto_allow_threshold = str(getattr(parent_cfg, "auto_allow_threshold", "low") or "low")
        from core.security.confirmation import normalize_confirmation_timeout

        confirmation_timeout = float(
            normalize_confirmation_timeout(getattr(parent_cfg, "confirmation_timeout", None))
        )
        interactive = not bool(getattr(parent_cfg, "non_interactive", False))
        search_config = dict(getattr(parent_cfg, "search", None) or {})

        # Profile storage paths for shared memory / security in subprocess
        ltm_db_path = ""
        vector_db_path = ""
        data_dir = str(getattr(parent_cfg, "data_dir", "") or "") if parent_cfg else ""
        if (
            config.memory_access != MemoryAccess.ISOLATED
            and hasattr(self._parent, "memory")
            and parent_cfg
        ):
            ltm_db_path = str(getattr(parent_cfg, "ltm_db_path", "") or "")
            vector_db_path = str(getattr(parent_cfg, "vector_db_path", "") or "")

        # Create handle
        handle = SubAgentHandle(
            name=config.name,
            config=config,
            status=SubAgentStatus.RUNNING,
            started_at=time.monotonic(),
            max_steps=int(config.max_steps or 0),
        )

        from core.prompt_builder import resolve_agent_working_directory

        parent_cwd = resolve_agent_working_directory(
            workspace_root=getattr(parent_cfg, "workspace_root", None),
            workspace_jail_enabled=getattr(parent_cfg, "workspace_jail_enabled", None),
        )

        process_args = (
            config_dict,
            task,
            None,  # input_queue — filled per attempt
            None,  # output_queue
            self._parent.model,
            ltm_db_path,
            vector_db_path,
            data_dir,
            getattr(self._parent.config, "mcp_servers", None)
            if hasattr(self._parent, "config")
            else None,
            str(getattr(self._parent.config, "skills_dir", "") or ""),
            dict(getattr(self._parent.config, "skill_assignments", None) or {}),
            auto_allow_threshold,
            confirmation_timeout,
            interactive,
            search_config,
            str(getattr(parent_cfg, "profile_name", None) or "default"),
            str(getattr(parent_cfg, "workspace_root", None) or ""),
            bool(getattr(parent_cfg, "workspace_jail_enabled", False)),
            parent_cwd,
        )
        parent_metadata = dict(getattr(parent_cfg, "provider_metadata", None) or {})
        mp_ctx = subagent_mp_context()
        process: multiprocessing.Process | None = None
        output_queue = None
        last_spawn_error: Exception | None = None

        for attempt in range(2):
            self._comm_bus.register(config.name)
            input_queue = self._comm_bus.get_input_queue(config.name)
            output_queue = self._comm_bus.get_output_queue(config.name)
            if input_queue is None or output_queue is None:
                raise SubAgentProcessSpawnError(
                    f"IPC queues were not created for sub-agent '{config.name}'"
                )
            spawn_args = (
                *process_args[:2],
                input_queue,
                output_queue,
                *process_args[4:],
            )
            process = mp_ctx.Process(
                target=run_sub_agent_in_process,
                args=spawn_args,
                daemon=True,
            )
            try:
                _start_subagent_process(
                    process,
                    api_key=parent_api_key,
                    base_url=parent_base_url,
                    preset_id=str(parent_metadata.get("preset_id") or ""),
                )
                break
            except SubAgentProcessSpawnError as exc:
                last_spawn_error = exc
                logger.warning(
                    "Sub-agent '%s' process spawn failed (attempt %s/2): %s",
                    config.name,
                    attempt + 1,
                    exc,
                )
                self._comm_bus.unregister(config.name)
                reset_subagent_mp_context()
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=1)
        else:
            raise last_spawn_error or SubAgentProcessSpawnError(
                f"Failed to spawn sub-agent '{config.name}'"
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
                data = await asyncio.to_thread(output_queue.get, True, 1.0)
            except queue.Empty:
                if handle.task and not handle.task.is_alive():
                    handle.result = SubAgentResult(
                        name=agent_name,
                        success=False,
                        error="Sub-agent process terminated unexpectedly",
                        duration_ms=(time.monotonic() - (handle.started_at or time.monotonic()))
                        * 1000,
                    )
                    handle.status = SubAgentStatus.FAILED
                    self._notify_parent_done(agent_name)
                    self._cleanup_ipc(agent_name)
                    return
                continue
            except Exception as exc:
                logger.warning("Sub-agent '%s' IPC read failed: %s", agent_name, exc)
                continue

            try:
                msg = AgentMessage.deserialize(data)
            except Exception as exc:
                logger.warning("Sub-agent '%s' IPC deserialize failed: %s", agent_name, exc)
                continue

            if msg.msg_type == "result":
                forced = getattr(handle, "forced_status", None)
                if forced:
                    handle.status = forced
                    if handle.result is None or not getattr(handle.result, "error", None):
                        meta = msg.metadata or {}
                        handle.result = SubAgentResult(
                            name=agent_name,
                            success=False,
                            error=str(getattr(forced, "value", forced)),
                            response=msg.content,
                            duration_ms=meta.get("duration_ms", 0),
                            steps_taken=meta.get("steps_taken", 0),
                            tool_calls=meta.get("tool_calls", []),
                        )
                    self._notify_parent_done(agent_name)
                    self._cleanup_ipc(agent_name)
                    return
                # Final result received
                meta = msg.metadata or {}
                handle.result = SubAgentResult(
                    name=agent_name,
                    success=meta.get("success", False),
                    response=msg.content,
                    error=meta.get("error"),
                    duration_ms=meta.get("duration_ms", 0),
                    steps_taken=meta.get("steps_taken", 0),
                    tool_calls=meta.get("tool_calls", []),
                    tokens_used=int(meta.get("tokens_used") or 0),
                    llm_calls=int(meta.get("llm_calls") or 0),
                    usage_accounted=bool(meta.get("usage_accounted", False)),
                    model=str(meta.get("model") or ""),
                )
                handle.steps_taken = int(meta.get("steps_taken", 0) or 0)
                handle.status = (
                    SubAgentStatus.COMPLETED if handle.result.success else SubAgentStatus.FAILED
                )
                handle.record_activity(
                    "status",
                    "Completed" if handle.result.success else "Failed",
                    steps_taken=handle.steps_taken,
                )
                self._notify_parent_done(agent_name)
                self._cleanup_ipc(agent_name)
                return

            elif msg.msg_type == "llm_usage":
                # Live model usage from OS-process sub-agent → parent event bus
                meta = msg.metadata or {}
                try:
                    from core.llm.usage import emit_llm_call_usage

                    usage = {
                        "prompt_tokens": int(meta.get("prompt_tokens") or 0),
                        "completion_tokens": int(meta.get("completion_tokens") or 0),
                        "total_tokens": int(meta.get("total_tokens") or 0),
                    }
                    emit_llm_call_usage(
                        self._parent,
                        model=str(meta.get("model") or ""),
                        step=int(meta.get("step") or 0),
                        usage=usage,
                        duration_ms=float(meta.get("duration_ms") or 0) or None,
                        finish_reason=meta.get("finish_reason"),
                        operation_name="subagent.chat",
                    )
                except Exception:
                    logger.debug(
                        "Sub-agent '%s' llm_usage emit failed",
                        agent_name,
                        exc_info=True,
                    )

            elif msg.msg_type == "progress":
                meta = msg.metadata or {}
                handle.record_activity(
                    str(meta.get("kind") or "progress"),
                    msg.content or "",
                    tool_name=str(meta.get("tool_name") or ""),
                    details=str(meta.get("details") or ""),
                    steps_taken=int(meta.get("steps_taken") or handle.steps_taken or 0),
                )
                mgr = getattr(self._parent, "subagents", None)
                notify = getattr(mgr, "notify_progress", None)
                if callable(notify):
                    try:
                        notify(agent_name)
                    except Exception:
                        logger.debug("progress notify failed", exc_info=True)

            elif msg.msg_type == "heartbeat":
                # Heartbeats mark liveness for wait-timeout extension without
                # spamming the activity log.
                handle.touch_activity()

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
                handle.record_activity("status", f"Error: {msg.content or 'failed'}")
                self._notify_parent_done(agent_name)
                self._cleanup_ipc(agent_name)
                return

    def _cleanup_ipc(self, agent_name: str) -> None:
        self._comm_bus.unregister(agent_name)

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

        forced = getattr(handle, "forced_status", None)
        if forced:
            handle.status = forced
            if handle.result is None:
                handle.result = SubAgentResult(
                    name=name,
                    success=False,
                    error="loop: stopped by supervisor",
                    duration_ms=(time.monotonic() - (handle.started_at or time.monotonic())) * 1000,
                )
        else:
            handle.status = SubAgentStatus.CANCELLED
            handle.result = SubAgentResult(
                name=name,
                success=False,
                error="Cancelled by parent",
                duration_ms=(time.monotonic() - (handle.started_at or time.monotonic())) * 1000,
            )
        self._notify_parent_done(name)
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
