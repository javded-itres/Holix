"""Enter per-run scope: RunContext + ContextVar sync.

**Canonical runtime context for tools is ContextVars** (``core.tools.execution_context``).
Dishka REQUEST scope is optional and only used when a container is passed; tools
must not depend on Dishka REQUEST being active.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator

from core.domain.run_context import RunContext
from core.tools import execution_context as ec

if TYPE_CHECKING:
    from dishka import AsyncContainer


@asynccontextmanager
async def enter_run_scope(
    agent: Any,
    ctx: RunContext,
    *,
    container: AsyncContainer | None = None,
) -> AsyncIterator[RunContext]:
    """Bind run context for tools and graph nodes for the duration of one run.

    Always sets ContextVars. Optionally opens a Dishka REQUEST scope with
    ``RunContext`` in context when *container* is provided (for future
    request-scoped providers).
    """
    conv_token = ec.conversation_scope(ctx.conversation_id)
    prof_token = ec.profile_scope(ctx.profile_name)
    paths_token = ec.paths_visibility_scope(full_paths_visible=ctx.full_paths_visible)
    ws_tokens = ec.workspace_scope(
        workspace_root=ctx.workspace_root,
        workspace_jail_enabled=ctx.workspace_jail_enabled,
    )
    sub_tokens = (
        ec.subagent_scope(
            ctx.subagent_name,
            subagent_type=ctx.subagent_type,
            interaction_bridge=ctx.interaction_bridge,
        )
        if ctx.subagent_name
        else []
    )
    mem_token = (
        ec.memory_facade_scope(ctx.memory_facade)
        if ctx.memory_facade is not None
        else None
    )
    chat_token = (
        ec.chat_delivery_scope(ctx.chat_delivery_bridge)
        if ctx.chat_delivery_bridge is not None
        else None
    )
    emit_token = ec.agent_emit_scope(ctx.emit_fn) if ctx.emit_fn is not None else None

    di_cm = None
    if container is not None:
        di_cm = container(context={RunContext: ctx})

    try:
        if di_cm is not None:
            async with di_cm:
                yield ctx
        else:
            yield ctx
    finally:
        if emit_token is not None:
            ec.reset_agent_emit_scope(emit_token)
        if chat_token is not None:
            ec.reset_chat_delivery_scope(chat_token)
        if mem_token is not None:
            ec.reset_memory_facade_scope(mem_token)
        if sub_tokens:
            ec.reset_subagent_scope(sub_tokens)
        ec.reset_workspace_scope(ws_tokens)
        ec.reset_paths_visibility_scope(paths_token)
        ec.reset_profile_scope(prof_token)
        ec.reset_conversation_scope(conv_token)


def run_context_from_agent(agent: Any, conversation_id: str) -> RunContext:
    """Build RunContext from a HolixAgent instance."""
    cfg = getattr(agent, "config", None)
    return RunContext(
        conversation_id=conversation_id,
        profile_name=getattr(cfg, "profile_name", "default") if cfg else "default",
        workspace_root=getattr(cfg, "workspace_root", None) if cfg else None,
        workspace_jail_enabled=bool(getattr(cfg, "workspace_jail_enabled", False))
        if cfg
        else False,
        memory_facade=getattr(agent, "memory", None),
        emit_fn=getattr(agent, "emit", None),
    )