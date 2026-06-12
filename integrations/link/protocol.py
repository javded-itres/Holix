"""Holix Link RPC and control-plane message types.

Shared contract between Holix-Link client and Holix gateway relay.
Keep in sync with holix_link/protocol.py in the Holix-Link repository.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class RpcOp(StrEnum):
    LIST_DIR = "list_dir"
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    STAT = "stat"
    MKDIR = "mkdir"
    DELETE = "delete"


class LinkPermissions(BaseModel):
    read: bool = True
    write: bool = True
    mkdir: bool = True
    delete: bool = False


class WsMessageType(StrEnum):
    RPC_CALL = "rpc_call"
    RPC_RESULT = "rpc_result"
    PING = "ping"
    PONG = "pong"
    AUTH = "auth"
    AUTH_OK = "auth_ok"
    ERROR = "error"
    NOTIFICATION = "notification"


class RpcCall(BaseModel):
    type: Literal[WsMessageType.RPC_CALL] = WsMessageType.RPC_CALL
    id: str
    op: RpcOp
    path: str = ""
    limit: int | None = Field(default=200, ge=1, le=10_000)
    offset: int | None = Field(default=None, ge=0)
    content_b64: str | None = None
    encoding: Literal["utf-8", "base64"] = "utf-8"

    @field_validator("id")
    @classmethod
    def id_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("id must not be empty")
        return value


class DirEntry(BaseModel):
    name: str
    path: str
    is_dir: bool
    size: int | None = None


class FileStat(BaseModel):
    path: str
    is_dir: bool
    size: int
    mtime: float | None = None


class RpcResultPayload(BaseModel):
    entries: list[DirEntry] | None = None
    content: str | None = None
    content_b64: str | None = None
    stat: FileStat | None = None
    bytes_written: int | None = None


class RpcResult(BaseModel):
    type: Literal[WsMessageType.RPC_RESULT] = WsMessageType.RPC_RESULT
    id: str
    ok: bool
    payload: RpcResultPayload | None = None
    error: str | None = None


class PingMessage(BaseModel):
    type: Literal[WsMessageType.PING] = WsMessageType.PING
    ts: float


class PongMessage(BaseModel):
    type: Literal[WsMessageType.PONG] = WsMessageType.PONG
    ts: float


class AuthMessage(BaseModel):
    type: Literal[WsMessageType.AUTH] = WsMessageType.AUTH
    link_id: str
    device_public_key_b64: str
    nonce: str


class AuthOkMessage(BaseModel):
    type: Literal[WsMessageType.AUTH_OK] = WsMessageType.AUTH_OK
    link_id: str
    session_key_b64: str | None = None
    permissions: LinkPermissions = Field(default_factory=LinkPermissions)


class ErrorMessage(BaseModel):
    type: Literal[WsMessageType.ERROR] = WsMessageType.ERROR
    code: str
    message: str
    request_id: str | None = None


class NotificationMessage(BaseModel):
    type: Literal[WsMessageType.NOTIFICATION] = WsMessageType.NOTIFICATION
    event: Literal["agent_read", "agent_write", "agent_delete", "agent_list"]
    path: str
    ts: float


WsMessage = (
    RpcCall
    | RpcResult
    | PingMessage
    | PongMessage
    | AuthMessage
    | AuthOkMessage
    | ErrorMessage
)


def parse_ws_message(data: dict[str, Any]) -> WsMessage:
    """Parse inbound WebSocket JSON into a typed message."""
    msg_type = data.get("type")
    if msg_type == WsMessageType.RPC_CALL:
        return RpcCall.model_validate(data)
    if msg_type == WsMessageType.RPC_RESULT:
        return RpcResult.model_validate(data)
    if msg_type == WsMessageType.PING:
        return PingMessage.model_validate(data)
    if msg_type == WsMessageType.PONG:
        return PongMessage.model_validate(data)
    if msg_type == WsMessageType.AUTH:
        return AuthMessage.model_validate(data)
    if msg_type == WsMessageType.AUTH_OK:
        return AuthOkMessage.model_validate(data)
    if msg_type == WsMessageType.ERROR:
        return ErrorMessage.model_validate(data)
    raise ValueError(f"Unknown WebSocket message type: {msg_type!r}")


class PairCreateRequest(BaseModel):
    profile: str
    ttl_seconds: int = Field(default=600, ge=60, le=3600)


class PairCreateResponse(BaseModel):
    code: str
    expires_at: str
    profile: str


class PairExchangeRequest(BaseModel):
    code: str
    folder: str
    device_public_key_b64: str
    client_fingerprint: str | None = None


class PairExchangeResponse(BaseModel):
    link_id: str
    gateway_ws_url: str
    server_fingerprint: str
    permissions: LinkPermissions = Field(default_factory=LinkPermissions)


class LinkStatusResponse(BaseModel):
    link_id: str
    profile: str
    folder_portable: str
    online: bool
    connected_at: str | None = None
    status: str = "active"


def new_request_id() -> str:
    return str(UUID.uuid4())