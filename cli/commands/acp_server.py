"""ACP agent: ``holix acp`` speaks Agent Client Protocol on stdio.

The process edits the current working directory. stdout is only JSON-RPC.
Logs stay on stderr. A client drives initialize, session/new, session/prompt.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import threading
from typing import Any

from core.acp.transport import encode_message, read_message

logger = logging.getLogger(__name__)

_PERMISSIONS = (
    {"optionId": "allow_once", "name": "Разрешить", "kind": "allow_once"},
    {"optionId": "allow_session", "name": "На этот чат", "kind": "allow_always"},
    {"optionId": "allow_always", "name": "Всегда", "kind": "allow_always"},
    {"optionId": "deny", "name": "Отклонить", "kind": "reject_once"},
)


class AcpAgent:
    """One Holix agent behind one ACP session."""

    def __init__(self, profile: str, config: Any, model: str, out: Any) -> None:
        self.profile = profile
        self.config = config
        self.model = (model or "").strip()
        self._out = out
        self._write_lock = threading.Lock()
        self._next_id = 0
        self._loop: asyncio.AbstractEventLoop | None = None
        self.sessions: dict[str, str] = {}
        self.agent: Any = None
        self.container: Any = None
        self._saw_delta = False
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def send(self, payload: dict[str, Any]) -> None:
        raw = encode_message(payload)
        with self._write_lock:
            self._out.write(raw)
            self._out.flush()

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self.send({"jsonrpc": "2.0", "method": method, "params": params})

    def reply(self, req_id: Any, result: dict[str, Any]) -> None:
        self.send({"jsonrpc": "2.0", "id": req_id, "result": result})

    def fail(self, req_id: Any, message: str, code: int = -32603) -> None:
        self.send({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._loop is None:
            raise RuntimeError("ACP loop is not running")
        self._next_id += 1
        req_id = self._next_id
        future: asyncio.Future[dict[str, Any]] = self._loop.create_future()
        self._pending[req_id] = future
        self.send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        return await future

    def resolve_response(self, req_id: Any, result: dict[str, Any] | None, error: str) -> None:
        try:
            key = int(req_id)
        except (TypeError, ValueError):
            return
        future = self._pending.pop(key, None)
        if future is None or future.done():
            return
        if error:
            future.set_exception(RuntimeError(error))
        else:
            future.set_result(result or {})

    async def open_session(self, params: dict[str, Any]) -> str:
        import os
        import uuid

        from core.di import create_agent, resolve_runtime_config

        cwd = str(params.get("cwd") or os.getcwd())
        if cwd:
            os.chdir(cwd)
        conversation = str(
            params.get("conversationId") or params.get("conversation_id") or ""
        ).strip()
        if not conversation:
            conversation = "acp_" + uuid.uuid4().hex
        session_id = "ses_" + uuid.uuid4().hex[:16]
        self.sessions[session_id] = conversation
        if self.agent is None:
            runtime = resolve_runtime_config(self.config)
            runtime = _in_workspace(runtime, cwd or os.getcwd())
            self.agent, self.container = await create_agent(
                runtime, event_listeners=[self._on_event]
            )
            _arm(self.agent, self.profile)
            _apply_model(self.agent, self.config, self.model)
        return session_id

    async def prompt(self, params: dict[str, Any]) -> dict[str, Any]:
        session_id = str(params.get("sessionId") or params.get("session_id") or "")
        conversation = self.sessions.get(session_id)
        if not conversation or self.agent is None:
            raise RuntimeError("session not found")
        text = prompt_text(params)
        if not text:
            raise RuntimeError("empty prompt")
        self._saw_delta = False
        answer = await self.agent.run(user_input=text, conversation_id=conversation)
        body = str(answer or "").strip()
        if body and not self._saw_delta:
            self._chunk(session_id, body)
        return {"stopReason": "end_turn"}

    async def cancel(self, params: dict[str, Any]) -> None:
        del params
        task = asyncio.current_task()
        if task is not None:
            task.cancel()

    async def close(self) -> None:
        if self.container is not None:
            await self.container.close()
            self.container = None

    def _on_event(self, event: Any) -> None:
        payload = event.to_dict() if hasattr(event, "to_dict") else None
        if not isinstance(payload, dict):
            return
        kind = str(payload.get("type") or "")
        session_id = next(iter(self.sessions), "")
        if kind == "assistant_delta":
            text = str(payload.get("content") or payload.get("text") or "")
            if text:
                self._saw_delta = True
                self._chunk(session_id, text)
            return
        if kind in {"tool_call_start", "tool_code_dispatch_start"}:
            self._tool(session_id, payload, "in_progress")
            return
        if kind in {"tool_call_result", "tool_code_dispatch_result"}:
            self._tool(session_id, payload, "completed")
            return
        if kind == "tool_call_error":
            self._tool(session_id, payload, "failed")
            return
        if kind == "confirmation_request":
            self._ask_permission(session_id, payload)
            return
        if kind == "subagent_question":
            self._schedule(self._ask_question(payload))
            return
        if kind == "step_budget_choice":
            self._schedule(self._ask_budget(payload))

    def _schedule(self, coro: Any) -> None:
        if self._loop is None:
            coro.close()
            return

        def start() -> None:
            if self._loop is not None:
                self._loop.create_task(coro)

        self._loop.call_soon_threadsafe(start)

    def _chunk(self, session_id: str, text: str) -> None:
        self.notify(
            "session/update",
            {
                "sessionId": session_id,
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": text},
                },
            },
        )

    def _tool(self, session_id: str, payload: dict[str, Any], status: str) -> None:
        self.notify(
            "session/update",
            {
                "sessionId": session_id,
                "update": {
                    "sessionUpdate": "tool_call",
                    "toolCallId": str(payload.get("tool_id") or payload.get("tool_name") or "tool"),
                    "title": str(payload.get("tool_name") or "инструмент"),
                    "status": status,
                    "rawOutput": str(payload.get("result") or payload.get("message") or "")[:500],
                },
            },
        )

    def _ask_permission(self, session_id: str, payload: dict[str, Any]) -> None:
        confirmation_id = str(payload.get("confirmation_id") or "")
        self._schedule(self._permission(session_id, confirmation_id, payload))

    async def _permission(
        self, session_id: str, confirmation_id: str, payload: dict[str, Any]
    ) -> None:
        arguments = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
        result = await self.request(
            "session/request_permission",
            {
                "sessionId": session_id,
                "confirmationId": confirmation_id,
                "toolCall": {
                    "toolCallId": confirmation_id,
                    "title": str(payload.get("tool_name") or ""),
                    "rawInput": arguments,
                },
                "options": list(_PERMISSIONS),
            },
        )
        choice = _selected_option(result) or "deny"
        _resolve_permission(self.profile, self.agent, confirmation_id, choice)

    async def _ask_question(self, payload: dict[str, Any]) -> None:
        result = await self.request(
            "holix/question",
            {
                "requestId": str(payload.get("request_id") or ""),
                "subagentName": str(payload.get("subagent_name") or ""),
                "text": str(payload.get("question") or payload.get("message") or ""),
            },
        )
        answer = str(result.get("answer") or "").strip()
        if not answer:
            return
        from core.subagents.interaction import get_interaction_bridge

        bridge = get_interaction_bridge(self.agent)
        if bridge is None:
            return
        request_id = str(payload.get("request_id") or "")
        if request_id:
            bridge.resolve_question(request_id, answer)
        else:
            bridge.resolve_single_pending_question(answer)

    async def _ask_budget(self, payload: dict[str, Any]) -> None:
        result = await self.request(
            "holix/budget",
            {
                "requestId": str(payload.get("request_id") or ""),
                "text": str(payload.get("message") or payload.get("reason") or ""),
            },
        )
        from core.runtime.step_budget_pause import resolve_step_budget

        resolve_step_budget(
            str(payload.get("request_id") or ""), str(result.get("choice") or "abort")
        )


def prompt_text(params: dict[str, Any] | None) -> str:
    raw = (params or {}).get("prompt")
    if isinstance(raw, str):
        return raw.strip()
    if not isinstance(raw, list):
        return ""
    parts: list[str] = []
    for block in raw:
        if isinstance(block, str):
            text = block.strip()
        elif isinstance(block, dict) and str(block.get("type") or "text") == "text":
            text = str(block.get("text") or "").strip()
        else:
            text = ""
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _selected_option(result: dict[str, Any]) -> str:
    outcome = result.get("outcome")
    if isinstance(outcome, dict):
        inner = outcome.get("outcome")
        if isinstance(inner, dict):
            return str(inner.get("optionId") or inner.get("option_id") or "")
        return str(outcome.get("optionId") or outcome.get("option_id") or "")
    return str(result.get("optionId") or "")


def _resolve_permission(profile: str, agent: Any, confirmation_id: str, choice: str) -> None:
    from core.security.confirmation import ConfirmationChoice, get_action_guard

    guard = getattr(agent, "_action_guard", None) or get_action_guard(profile)
    if guard is None or not confirmation_id:
        return
    try:
        guard.resolve_confirmation(confirmation_id, ConfirmationChoice(choice))
    except ValueError:
        guard.resolve_confirmation(confirmation_id, ConfirmationChoice.DENY)


def _arm(agent: Any, profile: str) -> None:
    from core.security.confirmation import get_action_guard

    guard = getattr(agent, "_action_guard", None) or get_action_guard(profile)
    if guard is not None and hasattr(guard, "_interactive"):
        guard._interactive = True


def _apply_model(agent: Any, config: Any, selected: str) -> None:
    slot = (selected or "").strip()
    if not slot:
        return
    setter = getattr(agent, "set_active_model_config", None)
    if not callable(setter):
        return
    try:
        from core.models.manager import ModelManager

        manager = ModelManager(config)
        model_config = None
        agent_models = getattr(config, "agent_models", None) or {}
        if slot in agent_models:
            model_config = manager.get_agent_model_config(slot)
        if model_config is None:
            providers = getattr(config, "providers", None) or {}
            for provider_name, row in providers.items():
                if not isinstance(row, dict):
                    continue
                known = {str(item) for item in (row.get("available_models") or [])}
                default_model = str(row.get("default_model") or "")
                if default_model:
                    known.add(default_model)
                model_id = slot
                if slot.startswith("prov:"):
                    parts = slot.split(":", 2)
                    if len(parts) == 3 and parts[1] == provider_name:
                        model_id = parts[2]
                if model_id in known or slot == provider_name:
                    model_config = manager.get_provider_model_config(
                        provider_name,
                        model_id=model_id if model_id in known else None,
                    )
                    break
        if model_config is not None:
            try:
                setter(model_config, model_slot_id=slot)
            except TypeError:
                setter(model_config)
    except (AttributeError, ImportError, TypeError, ValueError):
        logger.debug("ACP model slot was not applied", exc_info=True)


def _in_workspace(runtime: Any, cwd: str) -> Any:
    try:
        return runtime.with_overrides(workspace_root=cwd)
    except (AttributeError, TypeError):
        return runtime


async def serve(
    profile: str,
    config: Any,
    model: str,
    out: Any,
    stdin: Any | None = None,
) -> int:
    """Read ACP from stdin until the client disconnects."""
    loop = asyncio.get_running_loop()
    agent = AcpAgent(profile, config, model, out)
    agent.bind(loop)
    stream = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(stream)
    source = sys.stdin.buffer if stdin is None else stdin
    await loop.connect_read_pipe(lambda: protocol, source)
    prompt_task: asyncio.Task[Any] | None = None
    try:
        while True:
            try:
                message = await read_message(stream)
            except (json.JSONDecodeError, ValueError, UnicodeError) as exc:
                agent.send(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": str(exc)[:200]},
                    }
                )
                continue
            if message is None:
                break
            if "id" in message and "method" not in message:
                error = ""
                if isinstance(message.get("error"), dict):
                    error = str(message["error"].get("message") or "ACP error")
                agent.resolve_response(
                    message.get("id"),
                    message.get("result") if isinstance(message.get("result"), dict) else {},
                    error,
                )
                continue
            method = str(message.get("method") or "")
            params = message.get("params") if isinstance(message.get("params"), dict) else {}
            req_id = message.get("id")
            if method == "initialize":
                agent.reply(
                    req_id,
                    {
                        "protocolVersion": 1,
                        "agentCapabilities": {"loadSession": False},
                        "agentInfo": {"name": "holix", "title": "Holix", "version": "1"},
                    },
                )
                continue
            if method == "session/new":
                try:
                    session_id = await agent.open_session(params)
                except Exception as exc:  # noqa: BLE001 - show the agent failure to the client
                    agent.fail(req_id, str(exc)[:300])
                    continue
                agent.reply(req_id, {"sessionId": session_id})
                continue
            if method == "session/prompt":
                prompt_task = asyncio.create_task(_finish_prompt(agent, req_id, params))
                continue
            if method == "session/cancel":
                if prompt_task is not None:
                    prompt_task.cancel()
                if req_id is not None:
                    agent.reply(req_id, {})
                continue
            if req_id is not None:
                agent.fail(req_id, f"Method not found: {method}", -32601)
    finally:
        if prompt_task is not None:
            prompt_task.cancel()
        await agent.close()
    return 0


async def _finish_prompt(agent: AcpAgent, req_id: Any, params: dict[str, Any]) -> None:
    try:
        result = await agent.prompt(params)
    except asyncio.CancelledError:
        agent.reply(req_id, {"stopReason": "cancelled"})
        return
    except Exception as exc:  # noqa: BLE001 - the client must see why the turn stopped
        agent.fail(req_id, str(exc)[:300])
        return
    agent.reply(req_id, result)
