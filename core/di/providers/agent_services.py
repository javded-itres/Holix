"""Agent subsystem providers (memory, skills, tools, context)."""

from dishka import Provider, Scope, provide
from openai import AsyncOpenAI

from core.agent_events import AgentEventBus
from core.context import DEFAULT_CONTEXT_WINDOW, ContextCompressor, ContextManager, TokenCounter
from core.di.runtime_config import HolixRuntimeConfig
from core.memory.facade import MemoryFacade
from core.skills.manager import SkillsManager
from core.tools.registry import ToolRegistry


class AgentServicesProvider(Provider):
    """Core agent services assembled by Dishka."""

    scope = Scope.APP

    @provide(scope=Scope.APP)
    def memory(self, config: HolixRuntimeConfig) -> MemoryFacade:
        # MemoryFacade implements MemoryPort (core.domain.ports)
        return MemoryFacade(config)

    @provide(scope=Scope.APP)
    def skills(self, config: HolixRuntimeConfig) -> SkillsManager:
        # SkillsManager implements SkillsPort
        return SkillsManager(config)

    @provide(scope=Scope.APP)
    def tools(self, config: HolixRuntimeConfig) -> ToolRegistry:
        # ToolRegistry implements ToolsPort
        return ToolRegistry(
            workspace_root=config.workspace_root,
            workspace_jail_enabled=config.workspace_jail_enabled,
            profile_name=config.profile_name,
        )

    @provide(scope=Scope.APP)
    def token_counter(self, config: HolixRuntimeConfig) -> TokenCounter:
        return TokenCounter(model=config.model)

    @provide(scope=Scope.APP)
    def compressor(
        self,
        config: HolixRuntimeConfig,
        llm_client: AsyncOpenAI,
        token_counter: TokenCounter,
    ) -> ContextCompressor:
        return ContextCompressor(
            client=llm_client,
            model=config.model,
            token_counter=token_counter,
        )

    @provide(scope=Scope.APP)
    def context_manager(
        self,
        config: HolixRuntimeConfig,
        token_counter: TokenCounter,
        compressor: ContextCompressor,
        event_bus: AgentEventBus,
    ) -> ContextManager:
        window = config.context_window if config.context_window and config.context_window > 0 else DEFAULT_CONTEXT_WINDOW
        return ContextManager(
            context_window=window,
            token_counter=token_counter,
            compressor=compressor,
            event_bus=event_bus,
        )