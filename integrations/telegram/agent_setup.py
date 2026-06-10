"""Initialize HelixAgent for Telegram sessions."""

from __future__ import annotations

from cli.core import ProfileConfig, init_profile
from core.agent import HelixAgent


async def create_agent(profile: str, config: ProfileConfig | None = None) -> HelixAgent:
    config = config or init_profile(profile)
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

    agent = HelixAgent(config=runtime_config)
    await agent.initialize()
    return agent