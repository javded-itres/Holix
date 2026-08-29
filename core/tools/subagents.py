"""Tools for delegating work to background sub-agents (separate OS processes)."""

from __future__ import annotations

import json
from typing import Any

from core.config_utils import is_subagents_enabled
from core.subagents.registry import list_available_subagents
from core.tools.base import BaseTool


def _profile_name(parent: Any) -> str | None:
    cfg = getattr(parent, "config", None)
    if cfg is None:
        return None
    return str(getattr(cfg, "profile_name", None) or "default")


def _agent(parent: Any):
    return parent


class DelegateToSubAgentTool(BaseTool):
    """Spawn a sub-agent in a background process; returns immediately."""

    def __init__(self, parent_agent: Any):
        super().__init__()
        self._parent = parent_agent
        self.name = "delegate_to_subagent"
        types = list_available_subagents(profile=_profile_name(parent_agent))
        custom = [a["name"] for a in types if not a.get("builtin")]
        builtin = [a["name"] for a in types if a.get("builtin")]
        type_hint = (
            ("Custom (prefer for SDD): " + ", ".join(custom) + ". " if custom else "")
            + "Built-in: "
            + ", ".join(builtin)
        )
        self.description = (
            "Delegate a task to a specialized sub-agent (background). Returns job_id — "
            "use wait_subagent_result. fork=true seeds the child with completed parent "
            "turns (isolated tools/PTY/todos); default is a fresh conversation. "
            "For SDD apply prefer sdd_apply/sdd_dispatch so "
            "assignees from tasks.md are used (do not replace coder-python with coder). "
            + type_hint
        )
        self.risk_level = "low"
        self.parameters = {
            "type": "object",
            "properties": {
                "agent_type": {
                    "type": "string",
                    "description": (
                        "Exact sub-agent type name from list_subagent_types "
                        "(custom names like coder-python, or built-ins). "
                        "For SDD tasks always use the tasks.md assignee string."
                    ),
                },
                "task": {
                    "type": "string",
                    "description": "Clear task description for the sub-agent",
                },
                "fork": {
                    "type": "boolean",
                    "description": (
                        "If true, seed the child with completed parent conversation "
                        "turns (isolated tools, PTY, todos). Default false = fresh spawn."
                    ),
                    "default": False,
                },
            },
            "required": ["agent_type", "task"],
        }

    async def execute(self, agent_type: str, task: str, fork: bool = False) -> str:
        agent = _agent(self._parent)
        cfg = getattr(agent, "config", None)
        if not is_subagents_enabled(cfg):
            return (
                "Error: sub-agents are disabled. Set enable_subagents: true in profile "
                "config.yaml or HOLIX_ENABLE_SUBAGENTS=true in ~/.holix/.env"
            )
        try:
            agent_type = agent_type.strip()
            task = task.strip()
            from core.subagents.resolve import resolve_subagent_type

            agent_type = resolve_subagent_type(agent_type, profile=_profile_name(agent))
            existing = agent.subagents.find_running_duplicate(agent_type, task)
            if existing is not None:
                return json.dumps(
                    {
                        "status": "already_running",
                        "job_id": existing.name,
                        "agent_type": agent_type,
                        "process_mode": existing.config.process_mode.value,
                        "process_id": existing.process_id,
                        "message": (
                            f"Sub-agent '{existing.name}' is already running this task. "
                            f"Call wait_subagent_result(job_id='{existing.name}') "
                            "instead of spawning a duplicate."
                        ),
                    },
                    ensure_ascii=False,
                )
            handle = await agent.subagents.spawn_typed(agent_type, task, fork=bool(fork))
            h, _ = handle
            fallback = (h.spawn_fallback_reason or "").strip()
            payload: dict[str, Any] = {
                "status": "spawned",
                "job_id": h.name,
                "agent_type": agent_type,
                "process_mode": h.config.process_mode.value,
                "process_id": h.process_id,
                "message": (
                    f"Sub-agent '{h.name}' started in {h.config.process_mode.value} mode. "
                    f"Call wait_subagent_result(job_id='{h.name}') when you need the answer."
                ),
            }
            if bool(getattr(h.config, "fork", False)):
                payload["fork"] = True
                payload["seed_turns"] = len(getattr(h.config, "seed_messages", None) or [])
                payload["message"] = (
                    f"Sub-agent '{h.name}' forked from completed parent turns "
                    f"({payload['seed_turns']} messages) in {h.config.process_mode.value} mode. "
                    f"Call wait_subagent_result(job_id='{h.name}') when you need the answer."
                )
            if fallback:
                payload["fallback_from_process"] = True
                payload["fallback_reason"] = fallback
                payload["message"] = (
                    f"Sub-agent '{h.name}' is running in {h.config.process_mode.value} mode "
                    f"(OS-process spawn was unavailable: {fallback}). "
                    f"Call wait_subagent_result(job_id='{h.name}') when you need the answer."
                )
            return json.dumps(payload, ensure_ascii=False)
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
            "job_id may be the bare name (e.g. coder-python) from delegate_to_subagent "
            "or the full id (e.g. studio-123::coder-python) from list_subagents. "
            "Use list_subagents to see running jobs."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": (
                        "Bare job name from delegate_to_subagent (e.g. coder-python) "
                        "or full id from list_subagents (e.g. studio-pid::coder-python)"
                    ),
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
        job_id = (job_id or "").strip()
        try:
            handle = mgr.get_handle(job_id)
            timeout = timeout_seconds
            if handle is not None:
                timeout = timeout_seconds or handle.config.timeout
            elif timeout is None:
                timeout = 3600.0
            # wait_for resolves owner::name and can poll the profile registry.
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
        except KeyError:
            try:
                summary = mgr.get_status_summary()
                known = [
                    str(a.get("id") or a.get("name") or "") for a in (summary.get("agents") or [])
                ]
                known = [k for k in known if k][:12]
            except Exception:
                known = []
            hint = (
                f" Known jobs: {', '.join(known)}."
                if known
                else " Call list_subagents() for current jobs."
            )
            return (
                f"Error: no sub-agent with job_id '{job_id}'.{hint} "
                "Use the bare name (coder-python) or full id (studio-…::coder-python)."
            )
        except TimeoutError as e:
            detail = (str(e) or "").strip() or "wait timed out"
            return (
                f"Error waiting for sub-agent '{job_id}': {detail}. "
                "If it is still running, call wait_subagent_result again "
                "or list_subagents; the job was not cancelled."
            )
        except Exception as e:
            detail = (str(e) or "").strip() or type(e).__name__
            return f"Error waiting for sub-agent '{job_id}': {detail}"


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


class ListSubAgentTypesTool(BaseTool):
    """List built-in and custom sub-agent types available for SDD assignees / spawn."""

    def __init__(self, parent_agent: Any):
        super().__init__()
        self._parent = parent_agent
        self.name = "list_subagent_types"
        self.description = (
            "List available sub-agent types (built-in + custom for this profile). "
            "Use when assigning SDD tasks (mode subagents/hybrid) or choosing agent_type "
            "for delegate_to_subagent. Prefer custom types when they match the work; "
            "if none exist, use built-ins (coder, reviewer, …). Mode self does not need assignees."
        )
        self.risk_level = "no"
        self.parameters = {"type": "object", "properties": {}, "required": []}

    async def execute(self) -> str:
        profile = _profile_name(self._parent)
        types = list_available_subagents(profile=profile)
        custom = [t for t in types if not t.get("builtin")]
        return json.dumps(
            {
                "profile": profile,
                "types": types,
                "custom_count": len(custom),
                "hint": (
                    "For SDD propose: if custom_count>0 assign tasks to matching custom "
                    "types; else use built-ins. For apply mode self, assignees are ignored."
                ),
            },
            ensure_ascii=False,
        )


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
    registry.register(ListSubAgentTypesTool(parent_agent))
    registry.register(TerminateSubAgentTool(parent_agent))
    from core.tools.subagent_control import SubagentControlTool

    registry.register(SubagentControlTool(parent_agent))
    from core.tools.sdd import register_sdd_dispatch_tool

    register_sdd_dispatch_tool(registry, parent_agent)
