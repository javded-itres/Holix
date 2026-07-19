"""LLM middleware chain for Holix agent extensions.

Extensions register middleware during agent init. Every
``client.chat.completions.create`` call on the agent client runs through the
chain. Removing the extension package/folder clears rediscovery on next agent
start — no middleware remains.

Example::

    class StatsMiddleware:
        name = "request_stats"

        async def process(self, ctx, call_next):
            result = await call_next()
            # record tokens / model / latency from ctx + result
            return result

    class StatsExtension(AgentExtensionBase):
        def register_middleware(self, chain, agent):
            chain.add(StatsMiddleware())
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

CallNext = Callable[[], Awaitable[Any]]


@dataclass
class LLMRequestContext:
    """Mutable context for one LLM chat.completions.create invocation."""

    kwargs: dict[str, Any]
    agent: Any = None
    profile: str = "default"
    extension_name: str = ""
    settings: dict[str, Any] = field(default_factory=dict)
    # Filled by the chain around the call
    started_at: float = 0.0
    duration_ms: float = 0.0
    error: BaseException | None = None
    response: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def model(self) -> str:
        return str(self.kwargs.get("model") or "")

    @property
    def messages(self) -> list[Any]:
        return list(self.kwargs.get("messages") or [])

    @property
    def stream(self) -> bool:
        return bool(self.kwargs.get("stream"))


@runtime_checkable
class LLMMiddleware(Protocol):
    """Async onion middleware around LLM requests."""

    name: str

    async def process(self, ctx: LLMRequestContext, call_next: CallNext) -> Any:
        """Call ``await call_next()`` to continue the chain (or short-circuit)."""
        ...


class MiddlewareChain:
    """Ordered list of LLM middleware (outermost first)."""

    def __init__(self) -> None:
        self._items: list[LLMMiddleware] = []

    def __len__(self) -> int:
        return len(self._items)

    def clear(self) -> None:
        self._items.clear()

    def add(self, middleware: LLMMiddleware, *, name: str | None = None) -> None:
        if name and not getattr(middleware, "name", None):
            try:
                object.__setattr__(middleware, "name", name)
            except Exception:
                middleware.name = name  # type: ignore[attr-defined]
        mid_name = getattr(middleware, "name", None) or type(middleware).__name__
        # Replace same name (extension re-register)
        self._items = [m for m in self._items if getattr(m, "name", None) != mid_name]
        if not getattr(middleware, "name", None):
            middleware.name = mid_name  # type: ignore[attr-defined]
        self._items.append(middleware)
        logger.debug("LLM middleware registered: %s", mid_name)

    def names(self) -> list[str]:
        return [str(getattr(m, "name", type(m).__name__)) for m in self._items]

    async def run(self, ctx: LLMRequestContext, terminal: CallNext) -> Any:
        """Execute the onion: middleware[0] → … → middleware[n] → terminal."""

        async def _build(index: int) -> CallNext:
            if index >= len(self._items):
                return terminal

            mw = self._items[index]

            async def _next() -> Any:
                nxt = await _build(index + 1)
                return await nxt()

            async def _layer() -> Any:
                return await mw.process(ctx, _next)

            return _layer

        ctx.started_at = time.perf_counter()
        try:
            entry = await _build(0)
            result = await entry()
            ctx.response = result
            return result
        except BaseException as exc:
            ctx.error = exc
            raise
        finally:
            ctx.duration_ms = (time.perf_counter() - ctx.started_at) * 1000.0


class _CompletionsProxy:
    """Proxy ``chat.completions`` so ``create`` runs the middleware chain."""

    def __init__(self, inner: Any, chain: MiddlewareChain, agent: Any) -> None:
        self._inner = inner
        self._chain = chain
        self._agent = agent

    async def create(self, *args: Any, **kwargs: Any) -> Any:
        # OpenAI SDK uses keyword args only for create()
        if args:
            raise TypeError("chat.completions.create expects keyword arguments only")

        profile = "default"
        if self._agent is not None:
            cfg = getattr(self._agent, "config", None)
            profile = str(getattr(cfg, "profile_name", None) or "default")

        ctx = LLMRequestContext(
            kwargs=kwargs,
            agent=self._agent,
            profile=profile,
            settings=dict(getattr(self._agent, "extension_settings", None) or {}),
        )

        async def _terminal() -> Any:
            return await self._inner.create(**ctx.kwargs)

        if len(self._chain) == 0:
            return await _terminal()
        return await self._chain.run(ctx, _terminal)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _ChatProxy:
    def __init__(self, chat: Any, chain: MiddlewareChain, agent: Any) -> None:
        self._chat = chat
        self.completions = _CompletionsProxy(chat.completions, chain, agent)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._chat, name)


def install_llm_middleware(client: Any, chain: MiddlewareChain, agent: Any) -> Any:
    """Install middleware proxy on ``client.chat`` (in-place when possible).

    Safe to call on every hot-reload: reuses the original ``chat`` object so
    proxies are not nested. Uses ``object.__getattribute__`` so MagicMock
    clients do not auto-fabricate ``_holix_chat_original``.
    """
    if client is None or chain is None:
        return client
    try:
        try:
            base_chat = object.__getattribute__(client, "_holix_chat_original")
        except AttributeError:
            base_chat = None
        if base_chat is None:
            chat = client.chat
            while isinstance(chat, _ChatProxy):
                chat = chat._chat
            base_chat = chat
            try:
                object.__setattr__(client, "_holix_chat_original", base_chat)
            except Exception:
                try:
                    client._holix_chat_original = base_chat
                except Exception:
                    pass
        client.chat = _ChatProxy(base_chat, chain, agent)
    except Exception:
        logger.exception("failed to install LLM middleware proxy on client")
    return client


def get_or_create_chain(agent: Any) -> MiddlewareChain:
    chain = getattr(agent, "llm_middleware", None)
    if isinstance(chain, MiddlewareChain):
        return chain
    chain = MiddlewareChain()
    try:
        agent.llm_middleware = chain
    except Exception:
        pass
    return chain
