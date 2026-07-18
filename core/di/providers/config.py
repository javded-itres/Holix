"""Configuration provider."""

from dishka import Provider, Scope, from_context, provide

from core.di.runtime_config import HolixRuntimeConfig


class ConfigProvider(Provider):
    """Provides HolixRuntimeConfig (APP scope, overridable via context)."""

    scope = Scope.APP
    config = from_context(HolixRuntimeConfig)

    @provide(scope=Scope.APP)
    def default_config(self) -> HolixRuntimeConfig:
        return HolixRuntimeConfig.from_settings()