"""Provider fallback when the primary LLM is unavailable."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, RateLimitError

from core.models.manager import ModelConfig, ModelManager

logger = logging.getLogger(__name__)

_RETRIABLE_HTTP = frozenset({408, 429, 500, 502, 503, 504, 529})

def is_llm_unavailable_error(exc: BaseException) -> bool:
    """Return True when switching to a fallback provider may help."""
    if isinstance(exc, (APIConnectionError, APITimeoutError)):
        return True
    if isinstance(exc, RateLimitError):
        return True
    if isinstance(exc, APIStatusError):
        if exc.status_code in _RETRIABLE_HTTP:
            return True
        if exc.status_code == 404:
            return True
    msg = str(exc).lower()
    if "model" in msg and any(
        token in msg for token in ("not found", "does not exist", "unknown model", "invalid model")
    ):
        return True
    if any(token in msg for token in ("connection refused", "connection error", "timed out", "unavailable", "econnrefused")):
        return True
    return False


def _notify_fallback(
    *,
    from_cfg: ModelConfig,
    to_cfg: ModelConfig,
    error: BaseException,
    on_switch: Callable[[ModelConfig], None] | None,
) -> None:
    logger.warning(
        "LLM provider '%s' unavailable (%s) — falling back to '%s' / %s",
        from_cfg.provider,
        error,
        to_cfg.provider,
        to_cfg.model,
    )
    if on_switch:
        on_switch(to_cfg)


async def chat_completions_with_fallback(
    model_manager: ModelManager,
    *,
    agent_name: str | None = "main",
    on_switch: Callable[[ModelConfig], None] | None = None,
    **create_kwargs: Any,
) -> Any:
    """Call ``chat.completions.create`` trying configured fallback providers."""
    configs = model_manager.iter_fallback_configs(agent_name)
    if not configs:
        raise ValueError("No model configuration available")

    last_error: BaseException | None = None
    for index, cfg in enumerate(configs):
        client = model_manager.get_client(cfg)
        try:
            return await client.chat.completions.create(
                model=cfg.model,
                **create_kwargs,
            )
        except Exception as exc:
            last_error = exc
            has_next = index < len(configs) - 1
            if not has_next or not is_llm_unavailable_error(exc):
                raise
            _notify_fallback(
                from_cfg=cfg,
                to_cfg=configs[index + 1],
                error=exc,
                on_switch=on_switch,
            )
    if last_error:
        raise last_error
    raise ValueError("No model configuration available")


async def run_with_provider_fallback[T](
    model_manager: ModelManager,
    *,
    agent_name: str | None = "main",
    on_switch: Callable[[ModelConfig], None] | None = None,
    factory: Callable[[ModelConfig, AsyncOpenAI], Awaitable[T]],
) -> T:
    """Run an async LLM call with the same fallback chain (streaming or custom)."""
    configs = model_manager.iter_fallback_configs(agent_name)
    if not configs:
        raise ValueError("No model configuration available")

    last_error: BaseException | None = None
    for index, cfg in enumerate(configs):
        client = model_manager.get_client(cfg)
        try:
            return await factory(cfg, client)
        except Exception as exc:
            last_error = exc
            has_next = index < len(configs) - 1
            if not has_next or not is_llm_unavailable_error(exc):
                raise
            _notify_fallback(
                from_cfg=cfg,
                to_cfg=configs[index + 1],
                error=exc,
                on_switch=on_switch,
            )
    if last_error:
        raise last_error
    raise ValueError("No model configuration available")