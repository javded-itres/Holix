"""Holix management API request/response models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProfileCreateRequest(BaseModel):
    name: str
    inherit_global: bool = True
    with_access_key: bool = False
    workspace_jail: bool = False


class ProfileKeyRotateRequest(BaseModel):
    current_key: str


class JailEnableRequest(BaseModel):
    path: str | None = None


class ProviderAddRequest(BaseModel):
    preset_id: str
    name: str | None = None
    api_key: str | None = None
    host: str | None = None
    port: int | None = None
    skip_test: bool = True
    no_verify_ssl: bool = False


class AgentModelsPatchRequest(BaseModel):
    agent_models: dict[str, dict[str, Any]]


class FallbacksPatchRequest(BaseModel):
    providers: list[str]


class SkillAssignRequest(BaseModel):
    skill_name: str
    agents: list[str]


class SkillAssignmentsPatchRequest(BaseModel):
    assignments: dict[str, list[str]]


class McpServerCreateRequest(BaseModel):
    name: str
    transport: str = "stdio"
    command: str = ""
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    risk_level: str = "medium"


class McpAssignmentsPatchRequest(BaseModel):
    assignments: dict[str, list[str]]


class McpInstallRequest(BaseModel):
    popular_key: str | None = None
    git_url: str | None = None
    params: dict[str, str] = Field(default_factory=dict)


class ConfigPatchRequest(BaseModel):
    updates: dict[str, Any]


class EnvPatchRequest(BaseModel):
    variables: dict[str, str]


class ReloadResponse(BaseModel):
    profile: str
    status: str
    agent: str
    companions: dict[str, Any]
    os_companions: dict[str, Any] = Field(default_factory=dict)
    reload_required: bool = False


class TelegramSetupRequest(BaseModel):
    bot_token: str
    also_project_env: bool = False


class TelegramApproveRequest(BaseModel):
    profile: str | None = None
    create_profile: str | None = None
    set_admin: bool = False


class TelegramMapSetRequest(BaseModel):
    user_id: int
    profile: str


class MaxSetupRequest(BaseModel):
    access_token: str
    also_project_env: bool = False


class MaxApproveRequest(BaseModel):
    profile: str | None = None
    create_profile: str | None = None
    set_admin: bool = False


class MaxMapSetRequest(BaseModel):
    user_id: int
    profile: str