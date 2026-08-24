"""ACP client: spawn an agent subprocess and run one prompt turn."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from core.acp.config import acp_argv, acp_permission_policy
from core.acp.transport import encode_message, read_message

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 1


class AcpError(RuntimeError):
    """ACP spawn, protocol, or remote-agent failure."""


@dataclass
class AcpResult:
    text: str
    stop_reason: str = "end_turn"
    session_id: str = ""
    stderr: str = ""
    updates: list[dict[str, Any]] = field(default_factory=list)


def _permission_result(params: dict[str, Any], policy: str) -> dict[str, Any]:
    options = params.get("options") or []
    if policy == "allow":
        for opt in options:
            if not isinstance(opt, dict):
                continue
            kind = str(opt.get("kind") or "").lower()
            if kind in {"allow_once", "allow_always", "allow-once", "allow-always"}:
                oid = opt.get("optionId") or opt.get("option_id")
                if oid:
                    return {"outcome": {"outcome": "selected", "optionId": oid}}
    for opt in options:
        if not isinstance(opt, dict):
            continue
        kind = str(opt.get("kind") or "").lower()
        if "reject" in kind or "deny" in kind:
            oid = opt.get("optionId") or opt.get("option_id")
            if oid:
                return {"outcome": {"outcome": "selected", "optionId": oid}}
    return {"outcome": {"outcome": "cancelled"}}


def _chunk_text(update: dict[str, Any]) -> str:
    kind = str(update.get("sessionUpdate") or update.get("session_update") or "")
    if kind not in {"agent_message_chunk", "agent_message", "message_chunk"}:
        return ""
    content = update.get("content")
    if isinstance(content, dict):
        return str(content.get("text") or "")
    if isinstance(content, str):
        return content
    return ""


class _AcpSession:
    def __init__(self, proc: asyncio.subprocess.Process, policy: str) -> None:
        self.proc = proc
        self.policy = policy
        self._id = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._chunks: list[str] = []
        self._updates: list[dict[str, Any]] = []
        self._reader: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._reader = asyncio.create_task(self._read_loop())

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    async def _read_loop(self) -> None:
        assert self.proc.stdout is not None
        try:
            while True:
                try:
                    msg = await read_message(self.proc.stdout)
                except asyncio.IncompleteReadError:
                    break
                except Exception:
                    logger.debug("ACP read failed", exc_info=True)
                    break
                if msg is None:
                    break
                await self._dispatch(msg)
        finally:
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(AcpError("ACP agent closed the stream"))
            self._pending.clear()

    async def _dispatch(self, msg: dict[str, Any]) -> None:
        if "id" in msg and "method" in msg:
            await self._handle_request(msg)
            return
        if "id" in msg:
            rid = msg["id"]
            fut = self._pending.pop(rid, None)
            if fut is None or fut.done():
                return
            if "error" in msg:
                err = msg["error"]
                text = err.get("message") if isinstance(err, dict) else str(err)
                fut.set_exception(AcpError(text or "ACP error"))
            else:
                fut.set_result(msg.get("result") if isinstance(msg.get("result"), dict) else {})
            return
        method = str(msg.get("method") or "")
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        if method == "session/update":
            update = params.get("update") if isinstance(params.get("update"), dict) else params
            self._updates.append(update)
            text = _chunk_text(update)
            if text:
                self._chunks.append(text)

    async def _handle_request(self, msg: dict[str, Any]) -> None:
        method = str(msg.get("method") or "")
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        req_id = msg["id"]
        if method == "session/request_permission":
            result = _permission_result(params, self.policy)
            await self._send({"jsonrpc": "2.0", "id": req_id, "result": result})
            return
        await self._send(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
        )

    async def _send(self, payload: dict[str, Any]) -> None:
        if self.proc.stdin is None:
            raise AcpError("ACP stdin closed")
        self.proc.stdin.write(encode_message(payload))
        await self.proc.stdin.drain()

    async def request(self, method: str, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        req_id = self._next_id()
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[req_id] = fut
        await self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except TimeoutError as exc:
            self._pending.pop(req_id, None)
            raise AcpError(f"ACP {method} timed out after {int(timeout)}s") from exc

    async def close(self) -> str:
        if self._reader is not None:
            self._reader.cancel()
            try:
                await self._reader
            except (asyncio.CancelledError, Exception):
                pass
        stderr = ""
        if self.proc.stderr is not None:
            try:
                err = await asyncio.wait_for(self.proc.stderr.read(), timeout=1.0)
                stderr = err.decode("utf-8", errors="replace")[-4_000:]
            except Exception:
                pass
        try:
            if self.proc.stdin is not None:
                self.proc.stdin.close()
        except Exception:
            pass
        try:
            if self.proc.returncode is None:
                self.proc.terminate()
                await asyncio.wait_for(self.proc.wait(), timeout=3.0)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        return stderr


async def run_acp_prompt(
    prompt: str,
    *,
    cwd: str | None = None,
    command: str | None = None,
    timeout: float = 300.0,
) -> AcpResult:
    argv = acp_argv(command=command)
    if not argv:
        raise AcpError(
            "No ACP agent configured. Set HOLIX_ACP_COMMAND "
            "(example: `grok --acp` or `claude --acp`)."
        )
    work = (cwd or os.getcwd()).strip() or os.getcwd()
    policy = acp_permission_policy()
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work,
        )
    except FileNotFoundError as exc:
        raise AcpError(f"ACP command not found: {argv[0]}") from exc
    except OSError as exc:
        raise AcpError(f"Failed to start ACP agent: {exc}") from exc

    session = _AcpSession(proc, policy)
    session.start()
    stderr = ""
    try:
        init_timeout = min(30.0, max(5.0, timeout / 4))
        await session.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}},
                "clientInfo": {"name": "holix", "title": "Holix", "version": "1"},
            },
            timeout=init_timeout,
        )
        created = await session.request(
            "session/new",
            {"cwd": work, "mcpServers": []},
            timeout=init_timeout,
        )
        session_id = str(created.get("sessionId") or created.get("session_id") or "")
        if not session_id:
            raise AcpError("ACP session/new did not return sessionId")
        session._chunks.clear()
        prompt_result = await session.request(
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": prompt}],
            },
            timeout=timeout,
        )
        stop = str(
            prompt_result.get("stopReason") or prompt_result.get("stop_reason") or "end_turn"
        )
        text = "".join(session._chunks).strip()
        return AcpResult(
            text=text,
            stop_reason=stop,
            session_id=session_id,
            updates=list(session._updates),
        )
    finally:
        stderr = await session.close()
        if stderr:
            logger.debug("ACP stderr: %s", stderr[:500])
