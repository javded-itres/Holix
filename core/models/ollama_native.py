"""Ollama native ``/api/chat`` client (same path LiteLLM ``ollama_chat/`` uses).

The OpenAI-compat ``/v1/chat/completions`` layer on Ollama often leaves
``message.content`` empty for reasoning models. Native chat returns ``content``
plus ``thinking`` and maps tools the way LiteLLM does.
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

import httpx

from core.models.client_factory import resolve_verify_ssl
from core.models.completion_options import is_ollama_like

logger = logging.getLogger(__name__)


def ollama_origin(base_url: str) -> str:
    """``http://host:11434/v1`` → ``http://host:11434``."""
    raw = (base_url or "").strip().rstrip("/")
    if raw.lower().endswith("/v1"):
        raw = raw[:-3].rstrip("/")
    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    if not parsed.scheme or not parsed.netloc:
        return "http://127.0.0.1:11434"
    return f"{parsed.scheme}://{parsed.netloc}"


def _flag(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
        return None
    return bool(value)


def native_chat_enabled(
    *,
    provider: str = "",
    base_url: str = "",
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Default on for Ollama. Disable with ``metadata.native_chat: false``."""
    meta = metadata or {}
    raw = meta.get("native_chat", meta.get("ollama_native"))
    parsed = _flag(raw)
    if parsed is not None:
        return parsed
    return is_ollama_like(SimpleNamespace(provider=provider, base_url=base_url, metadata=meta))


def _ns(**kwargs: Any) -> SimpleNamespace:
    return SimpleNamespace(**kwargs)


def _stringify_args(value: Any) -> str:
    if value is None:
        return "{}"
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _openai_tool_calls(raw: Any) -> list[Any] | None:
    if not raw:
        return None
    out: list[Any] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        fn = item.get("function") or {}
        out.append(
            _ns(
                id=str(item.get("id") or f"call_{i}"),
                type=str(item.get("type") or "function"),
                function=_ns(
                    name=str(fn.get("name") or ""),
                    arguments=_stringify_args(fn.get("arguments")),
                ),
            )
        )
    return out or None


def to_openai_response(data: dict[str, Any], *, model: str) -> SimpleNamespace:
    msg = data.get("message") if isinstance(data.get("message"), dict) else {}
    thinking = str(msg.get("thinking") or msg.get("reasoning") or "")
    tool_calls = _openai_tool_calls(msg.get("tool_calls"))
    finish = str(data.get("done_reason") or "") or ("stop" if data.get("done") else None)
    if tool_calls:
        finish = "tool_calls"
    prompt = int(data.get("prompt_eval_count") or 0)
    completion = int(data.get("eval_count") or 0)
    return _ns(
        id="chatcmpl-ollama-native",
        model=model,
        choices=[
            _ns(
                index=0,
                finish_reason=finish,
                message=_ns(
                    role="assistant",
                    content=str(msg.get("content") or ""),
                    reasoning=thinking,
                    reasoning_content=thinking,
                    tool_calls=tool_calls,
                ),
            )
        ],
        usage=_ns(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
        ),
    )


def to_openai_chunk(data: dict[str, Any], *, model: str) -> SimpleNamespace:
    msg = data.get("message") if isinstance(data.get("message"), dict) else {}
    thinking = str(msg.get("thinking") or "")
    tool_calls = _openai_tool_calls(msg.get("tool_calls"))
    finish = None
    if data.get("done"):
        finish = "tool_calls" if tool_calls else str(data.get("done_reason") or "stop")
    return _ns(
        id="chatcmpl-ollama-native",
        model=model,
        choices=[
            _ns(
                index=0,
                finish_reason=finish,
                delta=_ns(
                    content=msg.get("content") or "",
                    reasoning=thinking,
                    reasoning_content=thinking,
                    tool_calls=tool_calls,
                ),
            )
        ],
        usage=None,
    )


def build_chat_payload(kwargs: dict[str, Any], metadata: dict[str, Any] | None) -> dict[str, Any]:
    meta = metadata or {}
    extra = dict(kwargs.get("extra_body") or {})
    think = extra.get("think", meta.get("think", meta.get("enable_thinking")))
    think_flag = _flag(think)
    if think_flag is None:
        think_flag = False
    options: dict[str, Any] = {}
    temperature = kwargs.get("temperature")
    if temperature is not None:
        options["temperature"] = temperature
    max_tokens = kwargs.get("max_tokens")
    if max_tokens:
        options["num_predict"] = int(max_tokens)
    num_ctx = extra.get("num_ctx", meta.get("num_ctx"))
    if num_ctx:
        options["num_ctx"] = int(num_ctx)
    payload: dict[str, Any] = {
        "model": kwargs.get("model"),
        "messages": kwargs.get("messages") or [],
        "stream": bool(kwargs.get("stream")),
        "think": think_flag,
    }
    tools = kwargs.get("tools")
    if tools:
        payload["tools"] = tools
    choice = kwargs.get("tool_choice")
    if isinstance(choice, str) and choice not in {"", "auto", "none"}:
        payload["tool_choice"] = choice
    elif choice == "none":
        payload.pop("tools", None)
    if options:
        payload["options"] = options
    return payload


class _OllamaCompletions:
    def __init__(self, http: httpx.AsyncClient, origin: str, metadata: dict[str, Any]) -> None:
        self._http = http
        self._origin = origin
        self._metadata = metadata

    async def create(self, **kwargs: Any) -> Any:
        payload = build_chat_payload(kwargs, self._metadata)
        url = f"{self._origin}/api/chat"
        model = str(payload.get("model") or "")
        if payload.get("stream"):
            return self._stream(url, payload, model)
        response = await self._http.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Ollama /api/chat returned a non-object body")
        return to_openai_response(data, model=model)

    async def _stream(self, url: str, payload: dict[str, Any], model: str):
        async with self._http.stream("POST", url, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                text = (line or "").strip()
                if not text:
                    continue
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    logger.debug("skip malformed Ollama stream line")
                    continue
                if not isinstance(data, dict):
                    continue
                yield to_openai_chunk(data, model=model)


class OllamaNativeClient:
    """Duck-typed AsyncOpenAI: ``chat.completions.create`` → ``/api/chat``."""

    def __init__(
        self,
        *,
        origin: str,
        metadata: dict[str, Any],
        openai_client: Any,
        http: httpx.AsyncClient,
    ) -> None:
        self._origin = origin
        self.models = getattr(openai_client, "models", None)
        self.chat = SimpleNamespace(completions=_OllamaCompletions(http, origin, metadata))


def wrap_ollama_native_client(
    openai_client: Any,
    *,
    provider: str,
    base_url: str,
    metadata: dict[str, Any] | None,
) -> Any:
    meta = dict(metadata or {})
    if not native_chat_enabled(provider=provider, base_url=base_url, metadata=meta):
        return openai_client
    origin = ollama_origin(base_url)
    http = httpx.AsyncClient(
        verify=resolve_verify_ssl(meta),
        follow_redirects=True,
        timeout=httpx.Timeout(600.0, connect=30.0),
    )
    logger.info("Ollama provider using native /api/chat at %s", origin)
    return OllamaNativeClient(
        origin=origin,
        metadata=meta,
        openai_client=openai_client,
        http=http,
    )
