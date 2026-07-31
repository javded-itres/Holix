"""Tools so Holix can call remote A2A agents (client role)."""

from __future__ import annotations

import json
from typing import Any

from core.a2a.client import A2AClient, A2AClientError, extract_task_text
from core.a2a.config import load_a2a_config
from core.tools.base import BaseTool


def _profile(agent: Any) -> str:
    cfg = getattr(agent, "config", None)
    return str(getattr(cfg, "profile_name", None) or "default")


def _resolve_remote(agent: Any, name_or_url: str) -> tuple[str, dict[str, str], float]:
    """Return (url, headers, timeout) for a configured remote or raw URL."""
    raw = (name_or_url or "").strip()
    if not raw:
        raise ValueError("agent name or url is required")
    cfg = load_a2a_config(_profile(agent))
    if not cfg.client_enabled:
        raise RuntimeError(
            "A2A is disabled. Set a2a.enabled: true in profile config.yaml "
            "or HOLIX_A2A_ENABLED=true"
        )
    # URL form
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw.rstrip("/"), {}, cfg.request_timeout_s
    # Named remote
    for remote in cfg.remote_agents:
        if remote.name == raw or remote.name.lower() == raw.lower():
            return remote.url, dict(remote.headers), cfg.request_timeout_s
    known = ", ".join(r.name for r in cfg.remote_agents) or "(none configured)"
    raise ValueError(
        f"Unknown A2A agent '{raw}'. Use a full URL or configure remote_agents: {known}"
    )


class A2AListAgentsTool(BaseTool):
    def __init__(self, parent_agent: Any):
        super().__init__()
        self._parent = parent_agent
        self.name = "a2a_list_agents"
        self.description = (
            "List configured remote A2A (Agent2Agent) agents this Holix profile can call. "
            "Use before a2a_send_message when you need the agent name."
        )
        self.risk_level = "no"
        self.parameters = {"type": "object", "properties": {}, "required": []}

    async def execute(self) -> str:
        cfg = load_a2a_config(_profile(self._parent))
        if not cfg.client_enabled:
            return json.dumps({"enabled": False, "agents": []})
        agents = [
            {
                "name": r.name,
                "url": r.url,
                "description": r.description,
            }
            for r in cfg.remote_agents
        ]
        return json.dumps(
            {
                "enabled": True,
                "agents": agents,
                "hint": "Pass name or full URL to a2a_discover / a2a_send_message",
            },
            ensure_ascii=False,
            indent=2,
        )


class A2ADiscoverTool(BaseTool):
    def __init__(self, parent_agent: Any):
        super().__init__()
        self._parent = parent_agent
        self.name = "a2a_discover"
        self.description = (
            "Fetch an A2A Agent Card from a remote agent (by configured name or base URL). "
            "Returns name, skills, capabilities, and service URL."
        )
        self.risk_level = "low"
        self.parameters = {
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "description": "Configured remote name or https://… base URL",
                },
            },
            "required": ["agent"],
        }

    async def execute(self, agent: str) -> str:
        try:
            url, headers, timeout = _resolve_remote(self._parent, agent)
            client = A2AClient(url, headers=headers, timeout_s=timeout)
            card = await client.fetch_agent_card()
            return json.dumps(
                {
                    "ok": True,
                    "url": client.base_url,
                    "card": {
                        "name": card.get("name"),
                        "description": card.get("description"),
                        "version": card.get("version"),
                        "protocolVersion": card.get("protocolVersion"),
                        "url": card.get("url"),
                        "capabilities": card.get("capabilities"),
                        "skills": card.get("skills"),
                        "defaultInputModes": card.get("defaultInputModes"),
                        "defaultOutputModes": card.get("defaultOutputModes"),
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        except (A2AClientError, ValueError, RuntimeError) as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


class A2ASendMessageTool(BaseTool):
    def __init__(self, parent_agent: Any):
        super().__init__()
        self._parent = parent_agent
        self.name = "a2a_send_message"
        self.description = (
            "Send a task/message to a remote A2A agent and wait for the result (blocking). "
            "Use for cross-agent collaboration when another system exposes Agent2Agent. "
            "Prefer a2a_list_agents / a2a_discover first."
        )
        self.risk_level = "medium"
        self.parameters = {
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "description": "Configured remote name or https://… A2A endpoint",
                },
                "message": {
                    "type": "string",
                    "description": "User message / task for the remote agent",
                },
                "context_id": {
                    "type": "string",
                    "description": "Optional multi-turn contextId to continue a dialogue",
                },
            },
            "required": ["agent", "message"],
        }

    async def execute(
        self,
        agent: str,
        message: str,
        context_id: str | None = None,
    ) -> str:
        text = (message or "").strip()
        if not text:
            return json.dumps({"ok": False, "error": "message is empty"})
        try:
            url, headers, timeout = _resolve_remote(self._parent, agent)
            client = A2AClient(url, headers=headers, timeout_s=timeout)
            task = await client.send_message(
                text,
                context_id=(context_id or "").strip() or None,
                configuration={"returnImmediately": False},
            )
            reply = extract_task_text(task)
            return json.dumps(
                {
                    "ok": True,
                    "task_id": task.get("id"),
                    "context_id": task.get("contextId"),
                    "state": (task.get("status") or {}).get("state")
                    if isinstance(task.get("status"), dict)
                    else None,
                    "text": reply,
                    "task": task,
                },
                ensure_ascii=False,
                indent=2,
            )
        except (A2AClientError, ValueError, RuntimeError) as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


class A2AGetTaskTool(BaseTool):
    def __init__(self, parent_agent: Any):
        super().__init__()
        self._parent = parent_agent
        self.name = "a2a_get_task"
        self.description = (
            "Fetch status/result of a remote A2A task by id (after a2a_send_message)."
        )
        self.risk_level = "low"
        self.parameters = {
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "description": "Configured remote name or https://… endpoint",
                },
                "task_id": {"type": "string", "description": "A2A task id"},
            },
            "required": ["agent", "task_id"],
        }

    async def execute(self, agent: str, task_id: str) -> str:
        tid = (task_id or "").strip()
        if not tid:
            return json.dumps({"ok": False, "error": "task_id is required"})
        try:
            url, headers, timeout = _resolve_remote(self._parent, agent)
            client = A2AClient(url, headers=headers, timeout_s=timeout)
            task = await client.get_task(tid)
            return json.dumps(
                {
                    "ok": True,
                    "text": extract_task_text(task),
                    "task": task,
                },
                ensure_ascii=False,
                indent=2,
            )
        except (A2AClientError, ValueError, RuntimeError) as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


def register_a2a_tools(registry: Any, parent_agent: Any) -> None:
    """Register A2A client tools when enabled for the profile."""
    try:
        cfg = load_a2a_config(_profile(parent_agent))
        if not cfg.client_enabled:
            return
    except Exception:
        return
    for tool in (
        A2AListAgentsTool(parent_agent),
        A2ADiscoverTool(parent_agent),
        A2ASendMessageTool(parent_agent),
        A2AGetTaskTool(parent_agent),
    ):
        registry.register(tool)
