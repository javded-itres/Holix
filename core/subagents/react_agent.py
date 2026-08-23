"""Run a sub-agent on the same LangGraph ReAct engine as main."""

from __future__ import annotations

import logging
from typing import Any

from core.agent_events import (
    AgentEventBus,
    FinalResponseEvent,
    MaxStepsExtendedEvent,
    ThinkingEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from core.subagents.base import SubAgentConfig, SubAgentHandle
from core.subagents.prompt import build_subagent_system_prompt

logger = logging.getLogger(__name__)


class FilteredToolRegistry:
    """Expose only the sub-agent's tool subset; execute still uses the parent guard."""

    def __init__(
        self,
        inner: Any,
        *,
        allowed: set[str],
        inherit_mcp: bool,
        mcp_servers: list[str],
    ) -> None:
        self._inner = inner
        self._allowed = {str(n).strip() for n in allowed if str(n).strip()}
        self._inherit_mcp = bool(inherit_mcp)
        self._mcp_servers = [str(s).strip() for s in mcp_servers if str(s).strip()]
        self._action_guard = getattr(inner, "_action_guard", None)
        self._workspace_root = getattr(inner, "_workspace_root", None)
        self._workspace_jail_enabled = getattr(inner, "_workspace_jail_enabled", False)
        self._profile_name = getattr(inner, "_profile_name", None)

    def _is_allowed(self, name: str) -> bool:
        key = str(name or "").strip()
        if not key:
            return False
        if key in self._allowed:
            return True
        from core.tools.aliases import resolve_tool_name

        resolved = resolve_tool_name(key, getattr(self._inner, "tools", None))
        if resolved in self._allowed:
            return True
        if key.startswith("mcp_"):
            if self._inherit_mcp:
                return True
            return any(key.startswith(f"mcp_{srv}_") for srv in self._mcp_servers)
        return False

    def get_schemas(self, *, for_agent_slot: str = "main") -> list[dict[str, Any]]:
        schemas = self._inner.get_schemas(for_agent_slot=for_agent_slot)
        out: list[dict[str, Any]] = []
        for schema in schemas:
            fn = schema.get("function") if isinstance(schema, dict) else None
            name = ""
            if isinstance(fn, dict):
                name = str(fn.get("name") or "")
            if self._is_allowed(name):
                out.append(schema)
        return out

    async def execute(
        self, tool_call: Any, conversation_id: str = "default", *, memory: Any = None
    ) -> str:
        name = str(getattr(getattr(tool_call, "function", None), "name", "") or "")
        if not self._is_allowed(name):
            return f"Error: Tool '{name}' is not available to this sub-agent"
        return await self._inner.execute(tool_call, conversation_id, memory=memory)

    @property
    def tools(self) -> dict[str, Any]:
        inner_tools = getattr(self._inner, "tools", None) or {}
        return {k: v for k, v in inner_tools.items() if self._is_allowed(str(k))}

    def set_action_guard(self, guard: Any) -> None:
        self._action_guard = guard

    def get_tool_names(self) -> list[str]:
        return list(self.tools.keys())

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def allowed_tool_names(config: SubAgentConfig) -> set[str]:
    return {str(n).strip() for n in (config.tools or []) if str(n).strip()}


def resolve_subagent_context_window(parent: Any, config: SubAgentConfig | None = None) -> int:
    """Use the child model's window so ReAct compression matches main.

    Order: active session model → agent slot / ``model_contexts`` → parent
    runtime config → Holix default (131072). No artificial 28k cap.
    """
    from core.context.token_counter import DEFAULT_CONTEXT_WINDOW

    model = ""
    slot = ""
    if config is not None:
        model = str(config.model or "").strip()
        slot = str(config.agent_type or "").strip()
    if not model:
        model = str(getattr(parent, "model", "") or "").strip()

    def _positive(value: Any) -> int:
        try:
            n = int(value or 0)
        except (TypeError, ValueError):
            return 0
        return n if n > 0 else 0

    active = getattr(parent, "active_model_config", None)
    if active is not None:
        active_model = str(getattr(active, "model", "") or "").strip()
        active_win = _positive(getattr(active, "context_window", 0))
        if active_win and (not model or model == active_model):
            return max(4096, active_win)

    mm = getattr(parent, "model_manager", None)
    profile = getattr(mm, "profile_config", None) if mm is not None else None
    if profile is None:
        profile = getattr(getattr(parent, "config", None), "profile_config", None)
    agent_models = getattr(profile, "agent_models", None) or {}
    if mm is not None and slot and slot in agent_models:
        try:
            mc = mm.get_agent_model_config(slot)
        except Exception:
            mc = None
        win = _positive(getattr(mc, "context_window", 0) if mc else 0)
        if win:
            return max(4096, win)

    providers = getattr(profile, "providers", None) or {}
    if model and isinstance(providers, dict):
        for pdata in providers.values():
            if not isinstance(pdata, dict):
                continue
            ctxs = pdata.get("model_contexts") or {}
            win = _positive(ctxs.get(model) if isinstance(ctxs, dict) else 0)
            if win:
                return max(4096, win)

    parent_cfg = getattr(parent, "config", None)
    parent_win = _positive(getattr(parent_cfg, "context_window", 0))
    if parent_win:
        return max(4096, parent_win)
    return DEFAULT_CONTEXT_WINDOW


def attach_subagent_runtime(
    child: Any,
    *,
    name: str,
    receive: Any | None = None,
    input_queue: Any | None = None,
    on_guidance: Any | None = None,
    handle: Any | None = None,
) -> None:
    """Let react_node drain supervisor guidance for this child."""
    child._subagent_name = str(name or "").strip()
    child._subagent_guidance_receive = receive
    child._subagent_input_queue = input_queue
    child._subagent_on_guidance = on_guidance
    child._subagent_handle = handle


def is_empty_react_result(text: str | None) -> bool:
    """True when LangGraph finished without a usable sub-agent answer."""
    from core.llm.completion import is_blank_final_text

    raw = text or ""
    if is_blank_final_text(raw):
        return True
    lowered = raw.strip().lower()
    markers = (
        "agent completed without producing a final response",
        "без видимого ответа",
        "without a visible answer",
        "finished reasoning without",
        "без текстового ответа",
        "no response generated",
    )
    return any(marker in lowered for marker in markers)


def is_failed_react_result(text: str | None) -> str | None:
    """Error string when the ReAct child did not produce a successful result."""
    from core.presenters.final_content import is_aborted_final_response

    raw = (text or "").strip()
    if is_aborted_final_response(raw):
        return raw[:240] or "aborted"
    if is_empty_react_result(raw):
        return "empty LLM reply (no text, no tools)"
    return None


def recover_empty_react_text(
    text: str | None,
    *,
    messages: list[dict[str, Any]] | None = None,
    handle: Any | None = None,
) -> str | None:
    """If the model ended empty after successful writes, return a completion summary."""
    if not is_empty_react_result(text):
        return None
    from core.graph.action_honesty import summarize_persist_tools

    summary = summarize_persist_tools(messages)
    if summary:
        return summary
    log = getattr(handle, "activity_log", None) or []
    writes: list[str] = []
    persist = {"write_file", "patch_file", "sdd_write_artifact", "sdd_update_spec"}
    for item in log:
        if not isinstance(item, dict):
            continue
        tool = str(item.get("tool_name") or "").strip()
        kind = str(item.get("kind") or item.get("type") or "")
        if tool not in persist:
            continue
        if kind not in {"tool_result", "tool"}:
            continue
        details = str(item.get("details") or item.get("message") or "").strip()
        preview = " ".join(details.split())[:240]
        writes.append(f"- {tool}: {preview}" if preview else f"- {tool}")
    if not writes:
        return None
    return "Work completed via tools (model returned no final text):\n" + "\n".join(writes[-8:])


def build_react_subagent(parent: Any, config: SubAgentConfig, task: str) -> Any:
    """Child HolixAgent on LangGraph ReAct; reuses parent services."""
    from core.agent import HolixAgent
    from core.context.manager import ContextManager

    parent_cfg = getattr(parent, "config", None)
    model = (config.model or getattr(parent, "model", None) or "").strip()
    max_steps = int(config.max_steps or getattr(parent_cfg, "max_steps", 150) or 150)
    window = resolve_subagent_context_window(parent, config)

    child_cfg = parent_cfg.with_overrides(
        model=model or parent_cfg.model,
        max_steps=max_steps,
        execution_mode="react",
        use_langgraph=True,
        enable_subagents=False,
        enable_meta_agent=False,
        enable_self_refinement=False,
        enable_evolution=False,
        plan_review_enabled=False,
        context_window=window,
    )
    filtered = FilteredToolRegistry(
        parent.tools,
        allowed=allowed_tool_names(config),
        inherit_mcp=bool(getattr(config, "mcp_inherit", True)),
        mcp_servers=list(getattr(config, "mcp_servers", None) or []),
    )
    bus = AgentEventBus(name=f"sub:{config.name}")
    child = HolixAgent(
        config=child_cfg,
        client=parent.client,
        event_bus=bus,
        memory=getattr(parent, "memory", None),
        skills=getattr(parent, "skills", None),
        tools=filtered,
        token_counter=getattr(parent, "token_counter", None),
        compressor=getattr(parent, "compressor", None),
        context_manager=ContextManager(
            context_window=window,
            token_counter=getattr(parent, "token_counter", None),
            compressor=getattr(parent, "compressor", None),
            event_bus=bus,
        ),
        background_process_registry=getattr(parent, "background_processes", None),
        search_engine=getattr(parent, "search", None),
        enable_monitoring=False,
        allow_defaults=True,
    )
    child.model = model or child.model
    child.agent_slot = str(config.agent_type or config.name or "main")
    profile_name = str(getattr(parent_cfg, "profile_name", None) or "default")
    working_directory = ""
    try:
        from pathlib import Path

        working_directory = str(Path.cwd().resolve())
    except OSError:
        working_directory = ""
    child.subagent_system_prompt = build_subagent_system_prompt(
        config,
        task,
        skills_block="",
        profile_name=profile_name,
        workspace_root=getattr(parent_cfg, "workspace_root", None),
        workspace_jail_enabled=getattr(parent_cfg, "workspace_jail_enabled", None),
        working_directory=working_directory or None,
    )
    child._initialized = True
    child._use_langgraph = True
    child._subagent_manager = None
    return child


def record_handle_event(handle: SubAgentHandle, event: Any) -> None:
    """Mirror ReAct events onto the sub-agent activity log."""
    if isinstance(event, MaxStepsExtendedEvent):
        handle.max_steps = int(event.max_steps or handle.max_steps or 0)
        handle.record_activity(
            "step_budget_extended",
            (f"Step budget +{event.extra_steps} ({event.previous_max_steps} → {event.max_steps})"),
            steps_taken=handle.steps_taken,
        )
        return
    if isinstance(event, ToolCallStartEvent):
        args = event.arguments_raw or str(event.arguments or "")
        handle.record_activity(
            "tool_start",
            f"Calling {event.tool_name}",
            tool_name=event.tool_name,
            details=args[:300],
            steps_taken=handle.steps_taken,
        )
        return
    if isinstance(event, ToolCallResultEvent):
        preview = (event.result or "").strip()
        if len(preview) > 240:
            preview = preview[:239] + "…"
        handle.record_activity(
            "tool_result",
            f"{event.tool_name} finished",
            tool_name=event.tool_name,
            details=preview,
            steps_taken=handle.steps_taken,
        )
        return
    if isinstance(event, ThinkingEvent):
        handle.steps_taken = int(handle.steps_taken or 0) + 1
        handle.record_activity(
            "step",
            event.message or f"Reasoning step {handle.steps_taken}",
            steps_taken=handle.steps_taken,
        )
        return
    if isinstance(event, FinalResponseEvent):
        handle.record_activity(
            "status",
            "Completed",
            steps_taken=handle.steps_taken,
        )
