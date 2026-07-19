"""Request-scoped run context."""

from dishka import Provider, Scope, from_context

from core.domain.run_context import RunContext


class RunContextProvider(Provider):
    """Per-run scope (conversation, workspace) — set via container(context=...)."""

    scope = Scope.REQUEST
    run_context = from_context(RunContext)