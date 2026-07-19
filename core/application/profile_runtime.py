"""Shared profile → HolixRuntimeConfig resolution for all hosts."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.profile import ProfileConfig

from core.di.runtime_config import HolixRuntimeConfig


def resolve_profile_agent_config(
    profile: str,
    config: ProfileConfig | None = None,
    *,
    profile_key: str | None = None,
    prompt_key: bool = False,
    workspace_jail_enabled: bool | None = None,
    workspace_root: str | None = None,
) -> HolixRuntimeConfig:
    """Build runtime config from a CLI profile with optional workspace overrides."""
    from core.di import resolve_runtime_config
    from core.paths import ensure_profile_memory_dirs
    from core.profile import init_profile

    prof = config or init_profile(
        profile,
        profile_key=profile_key,
        prompt_key=prompt_key,
    )
    if workspace_jail_enabled is not None:
        prof.workspace_jail_enabled = workspace_jail_enabled
    if workspace_root is not None:
        prof.workspace_root = workspace_root

    ensure_profile_memory_dirs(profile)
    runtime_config = resolve_runtime_config(prof)
    try:
        from core.models.manager import ModelManager

        mc = ModelManager(prof).get_default_model_config()
        if mc:
            runtime_config = runtime_config.with_overrides(
                model=mc.model,
                base_url=mc.base_url,
                api_key=mc.api_key,
                temperature=mc.temperature,
            )
    except Exception:
        pass
    return runtime_config