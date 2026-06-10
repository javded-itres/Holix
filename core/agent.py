from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models.manager import ModelConfig

from openai import AsyncOpenAI

from core.agent_events import (
    AgentEvent,
    AgentEventBus,
    EventContext,
    EventHandler,
    ThinkingEvent,
    wire_default_monitoring,
)
from core.context import DEFAULT_CONTEXT_WINDOW, ContextCompressor, ContextManager, TokenCounter
from core.di.runtime_config import HelixRuntimeConfig
from core.loop import AgentLoop
from core.memory.facade import MemoryFacade
from core.models.client_factory import create_openai_client
from core.skills.manager import SkillsManager
from core.tools.registry import ToolRegistry


class HelixAgent:
    """Main Helix Agent - A self-improving AI agent with memory and skills.

    The agent is now event-aware. You can subscribe to rich structured events
    (tool calls, deltas, self-improvement, errors, etc.) instead of relying on
    console output from the core.

    When use_langgraph=True (default), the agent delegates execution to a
    LangGraph StateGraph. Otherwise, it falls back to the legacy AgentLoop.
    """

    def __init__(
        self,
        config: HelixRuntimeConfig | None = None,
        event_bus: AgentEventBus | None = None,
        event_listeners: list[EventHandler] | None = None,
        *,
        client: AsyncOpenAI | None = None,
        # Legacy overrides (merged into config when config is omitted)
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float | None = None,
        max_steps: int | None = None,
        enable_monitoring: bool = True,
    ):
        """Initialize the Helix agent."""
        base_config = config or HelixRuntimeConfig.from_settings()
        self.config = base_config.with_overrides(
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=temperature,
            max_steps=max_steps,
        )

        self.model = self.config.model
        self.client = client or create_openai_client(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            metadata=self.config.provider_metadata or None,
        )

        self.events = event_bus or AgentEventBus(name="HelixAgentAi")
        if event_listeners:
            for listener in event_listeners:
                self.events.subscribe(listener)

        if enable_monitoring:
            wire_default_monitoring(self.events)

        self.memory = MemoryFacade(self.config)
        self.skills = SkillsManager(self.config)
        self.tools = ToolRegistry(
            workspace_root=self.config.workspace_root,
            workspace_jail_enabled=self.config.workspace_jail_enabled,
        )
        self.loop = AgentLoop(self)

        context_window = self._resolve_context_window(self.config.context_window)
        self.token_counter = TokenCounter(model=self.model)
        self.compressor = ContextCompressor(
            client=self.client,
            model=self.model,
            token_counter=self.token_counter,
        )
        self.context_manager = ContextManager(
            context_window=context_window,
            token_counter=self.token_counter,
            compressor=self.compressor,
            event_bus=self.events,
        )

        self._graph = None
        self._use_langgraph = self.config.use_langgraph
        self._execution_mode_last: str | None = None
        self._subagent_manager = None
        self._initialized = False
        self._event_context: EventContext | None = None
        self.agent_slot: str = "main"
        self._model_manager = None

    @property
    def model_manager(self):
        """Lazy ModelManager for provider routing and fallbacks."""
        if self._model_manager is None:
            from cli.core import ProfileManager
            from core.models.manager import ModelManager

            profile_name = getattr(self.config, "profile_name", "default") or "default"
            self._model_manager = ModelManager(ProfileManager().load_profile(profile_name))
        return self._model_manager

    def invalidate_model_manager(self) -> None:
        """Drop cached profile routing (after config reload)."""
        self._model_manager = None

    @property
    def graph(self):
        """Lazy-compiled LangGraph execution graph."""
        if self._graph is None:
            from core.graph.builder import build_helix_graph

            mode = self._execution_mode_last or self.config.execution_mode
            self._graph = build_helix_graph(
                agent=self,
                execution_mode=mode,
            )
            self._execution_mode_last = mode
        return self._graph

    @property
    def subagents(self):
        """Lazy-initialized SubAgentManager for spawning sub-agents."""
        if self._subagent_manager is None:
            from core.subagents.manager import SubAgentManager

            self._subagent_manager = SubAgentManager(self)
        return self._subagent_manager

    def _resolve_context_window(self, explicit: int) -> int:
        if explicit and explicit > 0:
            return explicit
        return DEFAULT_CONTEXT_WINDOW

    def set_active_model_config(
        self,
        model_config: ModelConfig,
        *,
        model_slot_id: str | None = None,
    ) -> None:
        """Switch LLM client/model for subsequent runs (session-level override)."""
        from core.models.manager import ModelConfig
        from core.skills.assignments import normalize_skill_agent_slot

        if not isinstance(model_config, ModelConfig):
            raise TypeError("model_config must be ModelConfig")

        if model_slot_id is not None:
            self.agent_slot = normalize_skill_agent_slot(model_slot_id)

        temperature = model_config.temperature
        context_window = model_config.context_window or self.config.context_window

        self.config = self.config.with_overrides(
            model=model_config.model,
            base_url=model_config.base_url,
            api_key=model_config.api_key,
            temperature=temperature,
            context_window=context_window,
        )
        self.model = self.config.model
        self.client = create_openai_client(
            base_url=model_config.base_url,
            api_key=model_config.api_key,
            metadata=model_config.metadata or None,
        )
        self.loop.client = self.client
        self.loop.model = self.model
        if hasattr(self, "compressor"):
            self.compressor.client = self.client
            self.compressor.model = self.model
        self.token_counter = TokenCounter(model=self.model)
        if hasattr(self, "context_manager"):
            resolved_window = context_window or DEFAULT_CONTEXT_WINDOW
            self.context_manager.update_context_window(resolved_window)
            self.context_manager.token_counter = self.token_counter
        self._graph = None
        self._execution_mode_last = None

    def begin_run(self, conversation_id: str) -> str:
        """Start a correlated run; returns run_id."""
        import uuid

        run_id = uuid.uuid4().hex[:12]
        self._event_context = EventContext(
            conversation_id=conversation_id,
            run_id=run_id,
        )
        return run_id

    def end_run(self) -> None:
        """Clear run correlation context."""
        self._event_context = None

    def set_plan_id(self, plan_id: str) -> None:
        """Attach plan_id to subsequent events in the current run."""
        if self._event_context:
            self._event_context.plan_id = plan_id

    def stamp_event(self, event: AgentEvent) -> AgentEvent:
        """Apply conversation_id / run_id / plan_id from the active run."""
        ctx = self._event_context
        if not ctx:
            return event
        event.conversation_id = ctx.conversation_id
        event.run_id = ctx.run_id
        if ctx.plan_id:
            event.plan_id = ctx.plan_id
        return event

    def emit(self, event: AgentEvent) -> None:
        """Convenience method to emit an event through the agent's bus."""
        self.stamp_event(event)
        self.events.emit(event)

    async def initialize(self):
        """Initialize the agent (async setup)."""
        if self._initialized:
            return

        self.emit(ThinkingEvent(message="Initializing Helix Agent..."))

        await self.memory.initialize_db()

        self.tools.register_all()
        if getattr(self.config, "enable_subagents", False):
            from core.tools.subagents import register_subagent_tools

            register_subagent_tools(self.tools, self)
        # Register MCP tools (if configured in profile/runtime). Non-fatal.
        mcp_count = 0
        if getattr(self.config, "mcp_enabled", True) and getattr(self.config, "mcp_servers", None):
            try:
                mcp_count = await self.tools.register_mcp(
                    self.config.mcp_servers,
                    getattr(self.config, "mcp_assignments", None),
                    slot="main",
                )
            except Exception as e:
                self.emit(ThinkingEvent(message=f"MCP init warning: {e}"))
        self.emit(ThinkingEvent(
            message=f"Registered {len(self.tools.tools)} tools: {', '.join(self.tools.get_tool_names())}"
            + (f" (+{mcp_count} MCP)" if mcp_count else "")
        ))

        self.skills.load_all_skills()
        self.emit(ThinkingEvent(
            message=f"Loaded {len(self.skills.all_skills)} skills"
        ))

        if hasattr(self.memory, "set_skills_manager"):
            self.memory.set_skills_manager(self.skills)

        from core.search.engine import set_search_config

        set_search_config(getattr(self.config, "search", None) or None)
        enabled = []
        try:
            from core.search.engine import get_search_config

            enabled = get_search_config().enabled_providers()
        except Exception:
            pass
        if enabled:
            self.emit(ThinkingEvent(message=f"Search providers: {', '.join(enabled)}"))

        from core.security.confirmation import RiskLevel, init_action_guard

        auto_allow_threshold = RiskLevel(self.config.auto_allow_threshold)
        interactive = not self.config.non_interactive
        guard = init_action_guard(
            event_bus=self.events,
            auto_allow_threshold=auto_allow_threshold,
            interactive=interactive,
            confirmation_timeout=self.config.confirmation_timeout,
            data_dir=self.config.data_dir,
        )
        self.tools.set_action_guard(guard)

        from core.plan_review import init_plan_review_guard

        init_plan_review_guard(
            event_bus=self.events,
            interactive=interactive,
            review_timeout=self.config.plan_review_timeout,
        )

        self._initialized = True
        self.emit(ThinkingEvent(message="Helix Agent ready!"))

    async def close(self) -> None:
        """Cleanup (MCP sessions etc.). Safe to call multiple times."""
        try:
            if hasattr(self.tools, "_mcp_manager") and getattr(self.tools, "_mcp_manager", None):
                await self.tools._mcp_manager.disconnect_all()
        except Exception:
            pass

    async def reload_mcp(
        self,
        mcp_servers: dict[str, Any] | None = None,
        mcp_assignments: dict[str, list[str]] | None = None,
    ) -> int:
        """Hot-reload MCP servers and their tools without full agent restart.

        - Disconnects previous MCP manager
        - Removes all previously registered mcp_* tools
        - Re-registers using provided (or current config) servers/assignments
        - Returns number of MCP tools now registered.
        - Emits ThinkingEvent so UIs can show update.
        """
        if mcp_servers is None:
            mcp_servers = getattr(self.config, "mcp_servers", {}) or {}
        if mcp_assignments is None:
            mcp_assignments = getattr(self.config, "mcp_assignments", {}) or {}

        # Cleanup old MCP
        try:
            if hasattr(self.tools, "_mcp_manager") and getattr(self.tools, "_mcp_manager", None):
                await self.tools._mcp_manager.disconnect_all()
                self.tools._mcp_manager = None  # type: ignore
        except Exception:
            pass

        # Remove old MCP tools from registry (keep other tools)
        to_remove = [n for n in list(self.tools.tools.keys()) if str(n).startswith("mcp_")]
        for n in to_remove:
            self.tools.tools.pop(n, None)

        # Re-register fresh
        count = 0
        if mcp_servers:
            try:
                count = await self.tools.register_mcp(mcp_servers, mcp_assignments, slot="main")
                self.emit(ThinkingEvent(message=f"Hot-reloaded {count} MCP tools"))
            except Exception as e:
                self.emit(ThinkingEvent(message=f"MCP hot-reload warning: {e}"))
        else:
            self.emit(ThinkingEvent(message="MCP tools cleared (no servers configured)"))

        # Keep agent's config in sync for future
        try:
            self.config = self.config.with_overrides(
                mcp_servers=mcp_servers,
                mcp_assignments=mcp_assignments or {},
            )
        except Exception:
            pass

        return count

    async def run(
        self,
        user_input: str,
        conversation_id: str = "default",
        execution_mode: str | None = None,
    ) -> str:
        """Run the agent with user input."""
        if not self._initialized:
            await self.initialize()

        if execution_mode is None:
            execution_mode = self.config.execution_mode

        if self._execution_mode_last != execution_mode:
            self._graph = None
            self._execution_mode_last = execution_mode

        if self._use_langgraph:
            return await self._run_with_graph(user_input, conversation_id, execution_mode)
        else:
            return await self.loop.run_conversation(user_input, conversation_id)

    async def _run_with_graph(
        self,
        user_input: str,
        conversation_id: str = "default",
        execution_mode: str = "react",
    ) -> str:
        """Run the agent using the LangGraph execution graph."""
        from core.agent_events import ErrorEvent, FinalResponseEvent
        from core.runtime.executor import run_helix

        final_response = ""
        async for event in run_helix(
            self,
            user_input,
            conversation_id,
            stream=False,
            execution_mode=execution_mode,
        ):
            self.emit(event)
            if isinstance(event, FinalResponseEvent):
                final_response = event.content
            elif isinstance(event, ErrorEvent):
                final_response = event.error

        return final_response or "Agent completed without producing a final response."

    async def get_conversation_history(
        self,
        conversation_id: str = "default",
        limit: int = 30,
    ) -> list:
        return await self.memory.get_conversation(conversation_id, limit)

    async def search_memory(
        self,
        query: str,
        top_k: int = 5,
        *,
        conversation_id: str | None = None,
    ) -> list:
        return await self.memory.search(query, top_k, conversation_id=conversation_id)

    def format_memory_results(
        self,
        results: list,
        *,
        conversation_id: str | None = None,
        include_current: bool = True,
        content_limit: int = 300,
    ) -> str:
        from core.memory.session_search import format_memory_search_results

        return format_memory_search_results(
            results,
            current_conversation_id=conversation_id,
            include_current=include_current,
            content_limit=content_limit,
        )

    def get_skills(self) -> dict:
        return self.skills.all_skills

    def get_tools(self) -> list:
        return self.tools.get_tool_names()

    async def list_conversations(self, limit: int = 10) -> list[dict]:
        return await self.memory.list_recent_conversations(limit)