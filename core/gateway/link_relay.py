"""In-process WebSocket hub for Holix Link client sessions."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import WebSocket
from integrations.link.protocol import (
    ErrorMessage,
    PingMessage,
    PongMessage,
    RpcCall,
    RpcResult,
    WsMessageType,
    parse_ws_message,
)


class LinkOfflineError(RuntimeError):
    """Raised when an RPC is sent to a disconnected link client."""


class LinkRelay:
    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}
        self._pending: dict[str, asyncio.Future[RpcResult]] = {}
        self._lock = asyncio.Lock()

    def is_online(self, link_id: str) -> bool:
        return link_id in self._connections

    def online_link_ids(self) -> list[str]:
        return list(self._connections.keys())

    async def register(self, link_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            old = self._connections.get(link_id)
            self._connections[link_id] = websocket
        if old is not None and old is not websocket:
            try:
                await old.close(code=1000, reason="replaced")
            except Exception:
                pass

    async def unregister(self, link_id: str, websocket: WebSocket | None = None) -> None:
        async with self._lock:
            current = self._connections.get(link_id)
            if current is None:
                return
            if websocket is not None and current is not websocket:
                return
            self._connections.pop(link_id, None)

    async def handle_client_message(self, link_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Process an inbound client message; return optional outbound JSON."""
        msg_type = data.get("type")
        if msg_type == WsMessageType.RPC_RESULT:
            result = RpcResult.model_validate(data)
            future = self._pending.get(result.id)
            if future is not None and not future.done():
                future.set_result(result)
            return None

        if msg_type == WsMessageType.PING:
            ping = PingMessage.model_validate(data)
            return PongMessage(ts=ping.ts).model_dump()

        if msg_type == WsMessageType.PONG:
            return None

        try:
            parse_ws_message(data)
        except ValueError as exc:
            err = ErrorMessage(code="invalid_message", message=str(exc))
            return err.model_dump()

        err = ErrorMessage(
            code="unexpected_message",
            message=f"Unexpected client message type: {msg_type!r}",
        )
        return err.model_dump()

    async def call_rpc(
        self,
        link_id: str,
        call: RpcCall,
        *,
        timeout: float = 30.0,
    ) -> RpcResult:
        websocket = self._connections.get(link_id)
        if websocket is None:
            raise LinkOfflineError(f"Link client '{link_id}' is offline")

        loop = asyncio.get_running_loop()
        future: asyncio.Future[RpcResult] = loop.create_future()
        self._pending[call.id] = future
        try:
            await websocket.send_json(call.model_dump())
            return await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError as exc:
            raise TimeoutError(f"RPC {call.op} timed out for link '{link_id}'") from exc
        finally:
            self._pending.pop(call.id, None)

    async def send_ping(self, link_id: str) -> None:
        websocket = self._connections.get(link_id)
        if websocket is None:
            raise LinkOfflineError(f"Link client '{link_id}' is offline")
        await websocket.send_json(PingMessage(ts=time.time()).model_dump())