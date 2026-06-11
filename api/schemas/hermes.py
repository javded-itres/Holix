"""Hermes-compatible API request/response models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ResponsesCreateRequest(BaseModel):
    model: str = "helix"
    input: str | list[dict[str, Any]] = ""
    instructions: str | None = None
    store: bool = True
    previous_response_id: str | None = None
    conversation: str | None = None


class RunsCreateRequest(BaseModel):
    model: str = "helix"
    input: str = ""
    session_id: str | None = None
    instructions: str | None = None
    conversation_history: list[dict[str, Any]] | None = None
    previous_response_id: str | None = None


class RunApprovalRequest(BaseModel):
    decision: str = "approve"
    comment: str | None = None


class JobCreateRequest(BaseModel):
    task: str
    cron_expression: str
    name: str = ""
    enabled: bool = True
    notify_chat_id: int | None = None
    session_id: str | None = None


class JobPatchRequest(BaseModel):
    task: str | None = None
    cron_expression: str | None = None
    name: str | None = None
    enabled: bool | None = None
    notify_chat_id: int | None = None
    session_id: str | None = None


class SessionCreateRequest(BaseModel):
    title: str = ""
    profile: str | None = None


class SessionPatchRequest(BaseModel):
    title: str | None = None
    end_reason: str | None = None


class SessionChatRequest(BaseModel):
    input: str = ""
    model: str | None = None


class CapabilitiesResponse(BaseModel):
    object: str = "helix.api_server.capabilities"
    platform: str = "helix"
    model: str = "helix"
    auth: dict[str, Any] = Field(default_factory=lambda: {"type": "bearer", "required": True})
    features: dict[str, bool] = Field(default_factory=dict)
    session_id_header: str = "X-Helix-Session-Id"
    session_key_header: str = "X-Helix-Session-Key"
    endpoints: dict[str, str] = Field(default_factory=dict)