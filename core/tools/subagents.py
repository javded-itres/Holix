"""Tools for delegating work to background sub-agents (separate OS processes)."""

from __future__ import annotations

import json
from typing import Any

from core.subagents.registry import list_available_subagents
from core.tools.base import BaseTool


def _agent(parent: Any):
    return parent


class DelegateToSubAgentTool(BaseTool):
    """Spawn a sub-agent in a background process; returns immediately."""

    def __init__(self, parent_agent: Any):
        super().__init__()
        self._parent = parent_agent
        self.name = "delegate_to_subagent"
        self.description = (
            "Delegate a task to a specialized sub-agent that runs in a separate process "
            "without blocking the main model. Returns a job id — use wait_subagent_result "
            "to collect the answer. Available types: "
            + ", ".join(a["name"] for a in list_available_subagents())
        )
        self.risk_level = "low"
        self.parameters = {
            "type": "object",
            "properties": {
                "agent_type": {
                    "type": "string",
                    "description": "Sub-agent type: researcher, coder, analyst, reviewer, writer, web_researcher",
                },
                "task": {
                    "type": "string",
                    "description": "Clear task description for the sub-agent",
                },
            },
            "required": ["agent_type", "task"],
        }

    async def execute(self, agent_type: str, task: str) -> str:
        agent = _agent(self._parent)
        cfg = getattr(agent, "config", None)
        if not cfg or not getattr(cfg, "enable_subagents", False):
            return (
                "Error: sub-agents are disabled. Set enable_subagents: true in profile "
                "config.yaml or HOLIX_ENABLE_SUBAGENTS=true in ~/.holix/.env"
            )
        try:
            handle = await agent.subagents.spawn_typed(agent_type.strip(), task.strip())
            h, _ = handle
            return json.dumps(
                {
                    "status": "spawned",
                    "job_id": h.name,
                    "agent_type": agent_type,
                    "process_mode": h.config.process_mode.value,
                    "process_id": h.process_id,
                    "message": (
                        f"Sub-agent '{h.name}' started in {h.config.process_mode.value} mode. "
                        f"Call wait_subagent_result(job_id='{h.name}') when you need the answer."
                    ),
                },
                ensure_ascii=False,
            )
        except Exception as e:
            return f"Error spawning sub-agent: {e}"


class WaitSubAgentResultTool(BaseTool):
    """Block until a delegated sub-agent finishes and return its response."""

    def __init__(self, parent_agent: Any):
        super().__init__()
        self._parent = parent_agent
        self.name = "wait_subagent_result"
        self.description = (
            "Wait for a sub-agent started via delegate_to_subagent and return its result. "
            "Use list_subagents to see running jobs."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "Sub-agent job id returned by delegate_to_subagent",
                },
                "timeout_seconds": {
                    "type": "number",
                    "description": "Max seconds to wait (default: sub-agent timeout)",
                },
            },
            "required": ["job_id"],
        }

    async def execute(self, job_id: str, timeout_seconds: float | None = None) -> str:
        agent = _agent(self._parent)
        mgr = agent.subagents
        try:
            handle = mgr.get_handle(job_id)
            if not handle:
                return f"Error: no sub-agent with job_id '{job_id}'. Use list_subagents."
            timeout = timeout_seconds or handle.config.timeout
            result = await mgr.wait_for(job_id, timeout=timeout)
            return json.dumps(
                {
                    "job_id": job_id,
                    "success": result.success,
                    "response": result.response,
                    "error": result.error,
                    "duration_ms": result.duration_ms,
                    "steps_taken": result.steps_taken,
                },
                ensure_ascii=False,
            )
        except Exception as e:
            return f"Error waiting for sub-agent '{job_id}': {e}"


class ListSubAgentsTool(BaseTool):
    """List running and completed sub-agents for this session."""

    def __init__(self, parent_agent: Any):
        super().__init__()
        self._parent = parent_agent
        self.name = "list_subagents"
        self.description = "List sub-agents spawned in this session (status, mode, task preview)."
        self.risk_level = "no"
        self.parameters = {"type": "object", "properties": {}, "required": []}

    async def execute(self) -> str:
        summary = _agent(self._parent).subagents.get_status_summary()
        return json.dumps(summary, ensure_ascii=False)


class TerminateSubAgentTool(BaseTool):
    """Cancel a running sub-agent."""

    def __init__(self, parent_agent: Any):
        super().__init__()
        self._parent = parent_agent
        self.name = "terminate_subagent"
        self.description = "Terminate a running sub-agent by job_id."
        self.risk_level = "medium"
        self.parameters = {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Sub-agent job id"},
            },
            "required": ["job_id"],
        }

    async def execute(self, job_id: str) -> str:
        ok = await _agent(self._parent).subagents.terminate(job_id.strip())
        return "terminated" if ok else f"could not terminate '{job_id}' (not running?)"


def register_subagent_tools(registry: Any, parent_agent: Any) -> None:
    """Attach sub-agent tools to the main agent registry."""
    registry.register(DelegateToSubAgentTool(parent_agent))
    registry.register(WaitSubAgentResultTool(parent_agent))
    registry.register(ListSubAgentsTool(parent_agent))
    registry.register(TerminateSubAgentTool(parent_agent))