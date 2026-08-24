"""Host side of Code mode: subprocess worker + JSON-RPC to ToolRegistry."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from core.memory.tool_content import truncate_tool_content_for_graph
from core.tools.code_mode.policy import (
    DEFAULT_PARALLEL_READONLY,
    DEFAULT_WALL_S,
    KILL_GRACE_S,
    MAX_INNER_CALLS,
    clamp_max_inner_calls,
    clamp_wall_timeout_s,
    is_forbidden_in_program,
    is_readonly_inner_tool,
)

WORKER_PATH = Path(__file__).resolve().parent / "worker.py"


class _InnerCall:
    def __init__(self, name: str, arguments: dict[str, Any], call_id: str) -> None:
        self.id = call_id
        self.type = "function"
        self.function = type(
            "obj",
            (object,),
            {
                "name": name,
                "arguments": json.dumps(arguments, ensure_ascii=False),
            },
        )()


def _format_outer(*, logs: list[str], result: Any, error: str | None) -> str:
    parts: list[str] = []
    text_logs = "".join(logs).rstrip()
    if text_logs:
        parts.append(text_logs)
    if error:
        parts.append(f"Error: {error}")
    elif result is not None:
        if isinstance(result, str):
            parts.append(result)
        else:
            try:
                parts.append(json.dumps(result, ensure_ascii=False, indent=2))
            except (TypeError, ValueError):
                parts.append(str(result))
    if not parts:
        return "(run_code completed with no output)"
    return truncate_tool_content_for_graph("\n\n".join(parts))


async def _kill(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    try:
        if os.name == "posix" and proc.pid:
            try:
                os.killpg(proc.pid, 9)
            except (ProcessLookupError, PermissionError, OSError):
                proc.kill()
        else:
            proc.kill()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=KILL_GRACE_S)
    except (TimeoutError, ProcessLookupError):
        pass


async def _readline(proc: asyncio.subprocess.Process, *, timeout: float) -> bytes:
    assert proc.stdout is not None
    return await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)


def _emit(event: Any) -> None:
    from core.tools.execution_context import get_agent_emit

    fn = get_agent_emit()
    if callable(fn):
        try:
            fn(event)
        except Exception:
            pass


def _registry_caps(registry: Any) -> tuple[int, int, bool]:
    wall = clamp_wall_timeout_s(getattr(registry, "_code_mode_wall_s", None), DEFAULT_WALL_S)
    max_inner = clamp_max_inner_calls(
        getattr(registry, "_code_mode_max_inner", None), MAX_INNER_CALLS
    )
    parallel = getattr(registry, "_code_mode_parallel_readonly", DEFAULT_PARALLEL_READONLY)
    return wall, max_inner, bool(parallel)


async def _dispatch_inner(
    registry: Any,
    *,
    name: str,
    args: dict[str, Any],
    inner_id: str,
    parent_tool_id: str,
    conversation_id: str,
    memory: Any,
) -> tuple[str, bool]:
    from core.agent_events import ToolCodeDispatchResultEvent, ToolCodeDispatchStartEvent

    _emit(
        ToolCodeDispatchStartEvent(
            tool_name=name,
            tool_id=inner_id,
            parent_tool_id=parent_tool_id,
            arguments=dict(args),
            conversation_id=conversation_id,
        )
    )
    started = time.time()
    result = await registry.execute(
        _InnerCall(name, args, inner_id),
        conversation_id,
        memory=memory,
        from_code_mode=True,
    )
    duration = (time.time() - started) * 1000
    truncated = truncate_tool_content_for_graph(str(result or ""))
    _emit(
        ToolCodeDispatchResultEvent(
            tool_name=name,
            tool_id=inner_id,
            parent_tool_id=parent_tool_id,
            result=truncated,
            duration_ms=duration,
            conversation_id=conversation_id,
        )
    )
    is_err = truncated.lower().startswith("error")
    return truncated, is_err


async def run_code_program(
    registry: Any,
    *,
    code: str,
    description: str,
    conversation_id: str,
    timeout_s: int | None = None,
    memory: Any = None,
    parent_tool_id: str = "",
) -> str:
    """Run model-written Python; tool calls RPC back into ``registry.execute``."""
    from core.tools.execution_context import is_run_cancelled

    wall_s, max_inner, parallel_ok = _registry_caps(registry)
    timeout_s = clamp_wall_timeout_s(timeout_s if timeout_s is not None else wall_s, wall_s)

    env = os.environ.copy()
    for key in list(env):
        if key.startswith("HOLIX_") and key not in {"HOLIX_HOME", "HOLIX_PROFILE"}:
            if any(s in key.upper() for s in ("KEY", "TOKEN", "SECRET", "PASSWORD", "PEPPER")):
                env.pop(key, None)

    kwargs: dict[str, Any] = {
        "stdin": asyncio.subprocess.PIPE,
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
        "env": env,
        "cwd": str(Path.cwd()),
    }
    if os.name == "posix":
        kwargs["start_new_session"] = True

    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        str(WORKER_PATH),
        **kwargs,
    )
    assert proc.stdin is not None
    proc.stdin.write(
        json.dumps({"code": code, "description": description}, ensure_ascii=False).encode() + b"\n"
    )
    await proc.stdin.drain()

    loop = asyncio.get_running_loop()
    deadline = loop.time() + float(max(1, timeout_s))
    inner_count = 0
    try:
        while True:
            if is_run_cancelled():
                await _kill(proc)
                return "Error: Run cancelled — code execution terminated."
            remaining = deadline - loop.time()
            if remaining <= 0:
                await _kill(proc)
                return f"Error: code run failed (timeout): exceeded {timeout_s}s"
            try:
                raw = await _readline(proc, timeout=min(0.25, remaining))
            except TimeoutError:
                if proc.returncode is not None:
                    err = b""
                    if proc.stderr:
                        err = await proc.stderr.read()
                    msg = err.decode("utf-8", errors="replace").strip()
                    return f"Error: code run failed (worker-exit): {msg or proc.returncode}"
                continue
            if not raw:
                await _kill(proc)
                err = b""
                if proc.stderr:
                    err = await proc.stderr.read()
                msg = err.decode("utf-8", errors="replace").strip()
                return f"Error: code run failed (worker-exit): {msg or 'eof'}"
            try:
                msg = json.loads(raw.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                await _kill(proc)
                return f"Error: code run failed (invalid-output): {raw[:200]!r}"
            if not isinstance(msg, dict):
                await _kill(proc)
                return "Error: code run failed (invalid-output): non-object"
            kind = str(msg.get("t") or "")
            if kind == "call":
                inner_count += 1
                if inner_count > max_inner:
                    await _kill(proc)
                    return (
                        f"Error: code run failed (output-limit): more than {max_inner} tool calls"
                    )
                name = str(msg.get("name") or "")
                args = msg.get("args") if isinstance(msg.get("args"), dict) else {}
                inner_id = f"{parent_tool_id or 'run_code'}:code:{inner_count}"
                tools_map = getattr(registry, "tools", None)
                if is_forbidden_in_program(name, tools=tools_map):
                    reply = {
                        "t": "result",
                        "id": msg.get("id"),
                        "ok": False,
                        "error": (f"tool '{name}' cannot be called from a run_code program"),
                    }
                else:
                    truncated, is_err = await _dispatch_inner(
                        registry,
                        name=name,
                        args=args,
                        inner_id=inner_id,
                        parent_tool_id=parent_tool_id,
                        conversation_id=conversation_id,
                        memory=memory,
                    )
                    reply = {
                        "t": "result",
                        "id": msg.get("id"),
                        "ok": not is_err,
                        "value": truncated if not is_err else None,
                        "error": truncated if is_err else None,
                    }
                proc.stdin.write(json.dumps(reply, ensure_ascii=False).encode() + b"\n")
                await proc.stdin.drain()
                continue
            if kind == "batch":
                raw_calls = msg.get("calls") if isinstance(msg.get("calls"), list) else []
                n_calls = len(raw_calls)
                if n_calls == 0:
                    reply = {
                        "t": "result",
                        "id": msg.get("id"),
                        "ok": False,
                        "error": "parallel() requires at least one call",
                    }
                    proc.stdin.write(json.dumps(reply, ensure_ascii=False).encode() + b"\n")
                    await proc.stdin.drain()
                    continue
                if inner_count + n_calls > max_inner:
                    await _kill(proc)
                    return (
                        f"Error: code run failed (output-limit): more than {max_inner} tool calls"
                    )
                tools_map = getattr(registry, "tools", None)
                parsed: list[tuple[str, dict[str, Any]]] = []
                batch_error = ""
                if not parallel_ok:
                    batch_error = "parallel read-only is disabled for this profile"
                for item in raw_calls:
                    if batch_error:
                        break
                    if not isinstance(item, dict):
                        batch_error = "parallel() items must be objects"
                        break
                    name = str(item.get("name") or "")
                    args = item.get("args") if isinstance(item.get("args"), dict) else {}
                    if is_forbidden_in_program(name, tools=tools_map):
                        batch_error = f"tool '{name}' cannot be called from a run_code program"
                        break
                    if not is_readonly_inner_tool(name, tools=tools_map):
                        batch_error = (
                            f"tools.parallel() only accepts read-only tools "
                            f"(risk_level=no); '{name}' must be called sequentially"
                        )
                        break
                    parsed.append((name, args))
                if batch_error:
                    reply = {
                        "t": "result",
                        "id": msg.get("id"),
                        "ok": False,
                        "error": batch_error,
                    }
                else:

                    async def _one(offset: int, name: str, args: dict[str, Any]):
                        inner_id = f"{parent_tool_id or 'run_code'}:code:{inner_count + offset}"
                        return await _dispatch_inner(
                            registry,
                            name=name,
                            args=args,
                            inner_id=inner_id,
                            parent_tool_id=parent_tool_id,
                            conversation_id=conversation_id,
                            memory=memory,
                        )

                    gathered = await asyncio.gather(
                        *[_one(i + 1, n, a) for i, (n, a) in enumerate(parsed)]
                    )
                    inner_count += n_calls
                    values = []
                    first_err = ""
                    for truncated, is_err in gathered:
                        if is_err and not first_err:
                            first_err = truncated
                        values.append(None if is_err else truncated)
                    reply = {
                        "t": "result",
                        "id": msg.get("id"),
                        "ok": not first_err,
                        "values": values,
                        "error": first_err or None,
                    }
                proc.stdin.write(json.dumps(reply, ensure_ascii=False).encode() + b"\n")
                await proc.stdin.drain()
                continue
            if kind == "done":
                await _kill(proc)
                logs = msg.get("logs") if isinstance(msg.get("logs"), list) else []
                log_lines = [str(x) for x in logs]
                return _format_outer(
                    logs=log_lines,
                    result=msg.get("result"),
                    error=None,
                )
            if kind == "error":
                await _kill(proc)
                logs = msg.get("logs") if isinstance(msg.get("logs"), list) else []
                return _format_outer(
                    logs=[str(x) for x in logs],
                    result=None,
                    error=str(msg.get("error") or "program failed"),
                )
            await _kill(proc)
            return f"Error: code run failed (invalid-output): unknown message {kind!r}"
    finally:
        await _kill(proc)
