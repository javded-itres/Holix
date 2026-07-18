"""Infrastructure providers (LLM, events, background processes, search)."""

from dishka import Provider, Scope, provide
from openai import AsyncOpenAI

from core.agent_events import AgentEventBus
from core.di.runtime_config import HolixRuntimeConfig
from core.models.client_factory import create_openai_client
from core.runtime.background_process import BackgroundProcessRegistry
from core.search.config import SearchConfig, default_search_config
from core.search.engine import SearchEngine


class InfrastructureProvider(Provider):
    """LLM client and shared infrastructure."""

    scope = Scope.APP

    @provide(scope=Scope.APP)
    def llm_client(self, config: HolixRuntimeConfig) -> AsyncOpenAI:
        return create_openai_client(
            base_url=config.base_url,
            api_key=config.api_key,
            metadata=config.provider_metadata or None,
        )

    @provide(scope=Scope.APP)
    def event_bus(self) -> AgentEventBus:
        return AgentEventBus(name="Holix")

    @provide(scope=Scope.APP)
    def background_process_registry(self) -> BackgroundProcessRegistry:
        return BackgroundProcessRegistry()

    @provide(scope=Scope.APP)
    def search_engine(self, config: HolixRuntimeConfig) -> SearchEngine:
        raw = getattr(config, "search", None) or None
        if isinstance(raw, SearchConfig):
            search_cfg = raw
        elif raw:
            search_cfg = SearchConfig.from_dict(raw)
        else:
            search_cfg = SearchConfig.from_dict(default_search_config())
        return SearchEngine(search_cfg)