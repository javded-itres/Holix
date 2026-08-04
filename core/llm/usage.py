"""Extract or estimate LLM token usage from OpenAI-compatible responses."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _int_field(obj: Any, *names: str) -> int:
    if obj is None:
        return 0
    for name in names:
        if isinstance(obj, dict):
            val = obj.get(name)
        else:
            val = getattr(obj, name, None)
        if val is None:
            continue
        try:
            return max(0, int(val))
        except (TypeError, ValueError):
            continue
    return 0


def usage_dict_from_response(response: Any) -> dict[str, int] | None:
    """Return prompt/completion/total from a chat completion response, if present."""
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if usage is None:
        return None
    prompt = _int_field(usage, "prompt_tokens", "input_tokens")
    completion = _int_field(usage, "completion_tokens", "output_tokens")
    total = _int_field(usage, "total_tokens")
    if total <= 0:
        total = prompt + completion
    if total <= 0 and prompt <= 0 and completion <= 0:
        return None
    return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": total}


def usage_dict_from_stream_chunk(chunk: Any) -> dict[str, int] | None:
    """Some providers attach usage on the final stream chunk when include_usage is set."""
    return usage_dict_from_response(chunk)


def _count_text(text: str, *, model: str = "") -> int:
    if not text:
        return 0
    try:
        import tiktoken

        try:
            enc = tiktoken.encoding_for_model(model) if model else tiktoken.get_encoding(
                "cl100k_base"
            )
        except Exception:
            enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)


def estimate_chat_tokens(
    messages: list[dict[str, Any]] | None = None,
    *,
    completion_text: str = "",
    model: str = "",
) -> dict[str, int]:
    """Estimate tokens with tiktoken when the provider omits usage.

    Uses tiktoken directly (not TokenCounter) to avoid heavy import side-effects.
    """
    prompt = 3  # message list priming
    for message in list(messages or []):
        prompt += 4
        if not isinstance(message, dict):
            continue
        for key, value in message.items():
            if key == "role":
                prompt += 1
            elif isinstance(value, str):
                prompt += _count_text(value, model=model)
            elif isinstance(value, list):
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    prompt += 4
                    func = item.get("function") or {}
                    if isinstance(func, dict):
                        prompt += _count_text(str(func.get("name") or ""), model=model)
                        prompt += _count_text(
                            str(func.get("arguments") or ""), model=model
                        )
    completion = _count_text(completion_text or "", model=model)
    total = max(1, prompt + completion) if (prompt or completion) else 0
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }


def resolve_usage(
    response: Any = None,
    *,
    messages: list[dict[str, Any]] | None = None,
    completion_text: str = "",
    model: str = "",
    stream_usage: dict[str, int] | None = None,
) -> dict[str, int]:
    """Prefer provider usage, then stream usage, then local estimate."""
    for candidate in (usage_dict_from_response(response), stream_usage):
        if candidate and int(candidate.get("total_tokens") or 0) > 0:
            return {
                "prompt_tokens": int(candidate.get("prompt_tokens") or 0),
                "completion_tokens": int(candidate.get("completion_tokens") or 0),
                "total_tokens": int(candidate.get("total_tokens") or 0),
            }
    return estimate_chat_tokens(
        messages,
        completion_text=completion_text,
        model=model,
    )


def completion_text_from_message(message: Any) -> str:
    """Best-effort assistant text (and tool-call payload) for estimation."""
    if message is None:
        return ""
    parts: list[str] = []
    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content")
    if isinstance(content, str) and content:
        parts.append(content)
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls is None and isinstance(message, dict):
        tool_calls = message.get("tool_calls")
    if tool_calls:
        for tc in tool_calls:
            fn = getattr(tc, "function", None)
            if fn is None and isinstance(tc, dict):
                fn = tc.get("function") or {}
            if isinstance(fn, dict):
                parts.append(str(fn.get("name") or ""))
                parts.append(str(fn.get("arguments") or ""))
            else:
                parts.append(str(getattr(fn, "name", "") or ""))
                parts.append(str(getattr(fn, "arguments", "") or ""))
    return "\n".join(p for p in parts if p)


def emit_llm_call_usage(
    agent: Any,
    *,
    model: str = "",
    step: int = 0,
    conversation_id: str = "",
    usage: dict[str, int] | None = None,
    duration_ms: float | None = None,
    finish_reason: str | None = None,
    estimated: bool = False,
    operation_name: str = "chat",
    provider_name: str = "",
) -> int:
    """Emit LLMCallCompletedEvent so Studio can record tokens for all tabs.

    Also records OpenTelemetry GenAI semantic-convention spans/metrics when OTEL
    is configured (see ``core.monitoring.genai_otel``).

    Returns total tokens emitted (0 if skipped for agent events; OTEL still tried).
    """
    usage = usage or {}
    total = int(usage.get("total_tokens") or 0)
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)

    # OpenTelemetry GenAI (no-op when SDK not installed / disabled)
    try:
        from core.monitoring.genai_otel import record_llm_call

        base_url = ""
        if agent is not None:
            cfg = getattr(agent, "config", None)
            base_url = str(getattr(cfg, "base_url", "") or "") if cfg else ""
            if not base_url:
                try:
                    from config import settings as app_settings

                    base_url = str(getattr(app_settings, "base_url", "") or "")
                except Exception:
                    base_url = ""
        record_llm_call(
            model=model or "",
            usage=usage,
            duration_ms=duration_ms,
            finish_reason=finish_reason,
            conversation_id=conversation_id or "",
            provider_name=provider_name,
            operation_name=operation_name or "chat",
            agent_name="holix",
            estimated=estimated,
            base_url=base_url,
        )
    except Exception:
        logger.debug("GenAI OTEL record failed", exc_info=True)

    if total <= 0 or agent is None or not hasattr(agent, "emit"):
        return 0
    try:
        from core.agent_events import LLMCallCompletedEvent

        agent.emit(
            LLMCallCompletedEvent(
                model=model or "",
                step=step,
                duration_ms=duration_ms,
                finish_reason=finish_reason,
                prompt_tokens=prompt,
                completion_tokens=completion,
                total_tokens=total,
                estimated=estimated,
                conversation_id=conversation_id or "",
            )
        )
        return total
    except Exception:
        logger.debug("Failed to emit LLM usage event", exc_info=True)
        return 0
