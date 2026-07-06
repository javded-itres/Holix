"""Initialize HolixAgent for Studio sessions."""

from __future__ import annotations

from cli.core import init_profile
from core.agent import HolixAgent


async def create_studio_agent(profile: str, *, profile_key: str | None = None) -> HolixAgent:
    config = init_profile(profile, profile_key=profile_key, prompt_key=False)
    from core.paths import ensure_profile_memory_dirs

    ensure_profile_memory_dirs(profile)
    from core.di import resolve_runtime_config

    runtime_config = resolve_runtime_config(config)
    try:
        from core.models.manager import ModelManager

        mc = ModelManager(config).get_default_model_config()
        if mc:
            runtime_config = runtime_config.with_overrides(
                model=mc.model,
                base_url=mc.base_url,
                api_key=mc.api_key,
                temperature=mc.temperature,
            )
    except Exception:
        pass

    agent = HolixAgent(config=runtime_config, enable_monitoring=False)
    await agent.initialize()
    return agent