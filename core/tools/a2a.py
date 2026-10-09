"""Tools so Holix can call remote A2A agents (client role)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from core.a2a.client import A2AClient, A2AClientError, extract_task_text
from core.a2a.config import A2AConfig, load_a2a_config, remotes_for_slot
from core.a2a.mikrollm import MikroLLMError, fetch_directory, neighbor_rows, post_group_message
from core.tools.base import BaseTool


def _profile(agent: Any) -> str:
    cfg = getattr(agent, "config", None)
    return str(getattr(cfg, "profile_name", None) or "default")


def _agent_slot(agent: Any) -> str:
    slot = str(getattr(agent, "agent_slot", None) or "main").strip()
    return slot or "main"


def _slot_client(agent: Any):
    """Enabled flag, this agent's peers, and the request timeout."""
    cfg = load_a2a_config(_profile(agent))
    enabled, remotes = remotes_for_slot(cfg, _agent_slot(agent))
    return enabled, remotes, cfg.request_timeout_s, cfg


async def _neighbors(cfg: A2AConfig) -> tuple[list[dict[str, Any]], str | None]:
    """Members of this agent's MikroLLM groups. Error text is empty when the link is off."""
    link = cfg.mikrollm
    if link is None or not link.url:
        return [], None
    try:
        directory = await fetch_directory(link)
    except (MikroLLMError, httpx.HTTPError, ValueError, OSError) as exc:
        return [], str(exc)
    return neighbor_rows(directory), None


def _resolve_remote(agent: Any, name_or_url: str) -> tuple[str, dict[str, str], float]:
    """Return (url, headers, timeout) for a configured remote or raw URL."""
    raw = (name_or_url or "").strip()
    if not raw:
        raise ValueError("agent name or url is required")
    enabled, remotes, timeout_s, _cfg = _slot_client(agent)
    if not enabled:
        raise RuntimeError(
            "A2A is disabled for this agent. Turn it on in the agent settings "
            "for this profile, or set a2a.enabled: true in profile config.yaml."
        )
    # URL form
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw.rstrip("/"), {}, timeout_s
    # Named remote for this agent only
    for remote in remotes:
        if remote.name == raw or remote.name.lower() == raw.lower():
            return remote.url, dict(remote.headers), timeout_s
    known = ", ".join(r.name for r in remotes) or "(none configured)"
    raise ValueError(
        f"Unknown A2A agent '{raw}'. Use a full URL or configure this agent's A2A peers: {known}"
    )


class A2AListAgentsTool(BaseTool):
    def __init__(self, parent_agent: Any):
        super().__init__()
        self._parent = parent_agent
        self.name = "a2a_list_agents"
        self.description = (
            "List A2A agents this profile can call: configured remotes and neighbors "
            "from its MikroLLM groups. Use before a2a_send_message when you need the name."
        )
        self.risk_level = "no"
        self.parameters = {"type": "object", "properties": {}, "required": []}

    async def execute(self) -> str:
        enabled, remotes, _timeout, cfg = _slot_client(self._parent)
        if not enabled:
            return json.dumps({"enabled": False, "agents": []})
        by_name: dict[str, dict[str, Any]] = {}
        for remote in remotes:
            by_name[remote.name] = {
                "name": remote.name,
                "url": remote.url,
                "description": remote.description,
                "source": "config",
            }
        neighbors, err = await _neighbors(cfg)
        for neighbor in neighbors:
            current = by_name.get(neighbor["name"])
            if current is None:
                by_name[neighbor["name"]] = neighbor
                continue
            current["source"] = "both"
            current["groups"] = neighbor["groups"]
            current["display_name"] = neighbor["display_name"]
            current["company"] = neighbor["company"]
            if not current.get("description"):
                current["description"] = neighbor["description"]
            current["skills"] = neighbor["skills"]
        return json.dumps(
            {
                "enabled": True,
                "agents": list(by_name.values()),
                "mikrollm_error": err,
                "hint": (
                    "Pass the name to a2a_send_message. "
                    "A neighbor with source mikrollm is reached through the shared group."
                ),
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
            "Send a task to a remote A2A agent, or post into a MikroLLM group neighbor. "
            "Configured remotes return the remote reply. Group neighbors are delivered by the gateway. "
            "Prefer a2a_list_agents first."
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
                "group": {
                    "type": "string",
                    "description": "MikroLLM group name when the neighbor shares more than one",
                },
            },
            "required": ["agent", "message"],
        }

    async def execute(
        self,
        agent: str,
        message: str,
        context_id: str | None = None,
        group: str | None = None,
    ) -> str:
        text = (message or "").strip()
        if not text:
            return json.dumps({"ok": False, "error": "message is empty"})
        posted = await self._post_neighbor(agent, text, group)
        if posted is not None:
            return posted
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

    async def _post_neighbor(self, agent: str, text: str, group: str | None) -> str | None:
        """Post to a group neighbor that has no configured URL. None means use the URL path."""
        raw = (agent or "").strip()
        if raw.startswith("http://") or raw.startswith("https://"):
            return None
        _enabled, remotes, _timeout, cfg = _slot_client(self._parent)
        if any(remote.name.lower() == raw.lower() for remote in remotes):
            return None
        neighbors, err = await _neighbors(cfg)
        match = next((item for item in neighbors if item["name"].lower() == raw.lower()), None)
        if match is None:
            if err and cfg.mikrollm is not None:
                return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
            return None
        groups = match.get("groups") or []
        chosen = (group or "").strip() or (groups[0] if groups else "")
        if not chosen:
            return json.dumps(
                {"ok": False, "error": "neighbor has no shared group"}, ensure_ascii=False
            )
        link = cfg.mikrollm
        if link is None:
            return None
        try:
            body = await post_group_message(link, group=chosen, to=match["name"], text=text)
        except (MikroLLMError, httpx.HTTPError, ValueError, OSError) as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
        return json.dumps(
            {
                "ok": True,
                "via": "mikrollm",
                "group": chosen,
                "to": match["name"],
                "message": body.get("message"),
                "note": "Posted to the shared group. The neighbor receives it; this reply is not their answer.",
            },
            ensure_ascii=False,
            indent=2,
        )


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
    """Register A2A client tools when this agent slot may call peers."""
    try:
        enabled, _remotes, _timeout, _cfg = _slot_client(parent_agent)
        if not enabled:
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
