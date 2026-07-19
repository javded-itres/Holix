"""Factory functions registered with Dishka (imports HolixAgent here to avoid cycles)."""

from openai import AsyncOpenAI

from core.agent import HolixAgent
from core.agent_events import AgentEventBus
from core.context import ContextCompressor, ContextManager, TokenCounter
from core.di.runtime_config import HolixRuntimeConfig
from core.memory.facade import MemoryFacade
from core.runtime.background_process import BackgroundProcessRegistry
from core.search.engine import SearchEngine
from core.skills.manager import SkillsManager
from core.tools.registry import ToolRegistry


def create_holix_agent(
    config: HolixRuntimeConfig,
    llm_client: AsyncOpenAI,
    event_bus: AgentEventBus,
    memory: MemoryFacade,
    skills: SkillsManager,
    tools: ToolRegistry,
    token_counter: TokenCounter,
    compressor: ContextCompressor,
    context_manager: ContextManager,
    background_process_registry: BackgroundProcessRegistry,
    search_engine: SearchEngine,
) -> HolixAgent:
    return HolixAgent(
        config=config,
        client=llm_client,
        event_bus=event_bus,
        memory=memory,
        skills=skills,
        tools=tools,
        token_counter=token_counter,
        compressor=compressor,
        context_manager=context_manager,
        background_process_registry=background_process_registry,
        search_engine=search_engine,
        enable_monitoring=False,
        allow_defaults=False,
    )