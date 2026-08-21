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
from core.models.completion_options import is_ollama_like, model_supports_thinking

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


def _content_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
        return "\n".join(p for p in parts if p)
    return str(content)


def _arguments_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except (TypeError, ValueError, json.JSONDecodeError):
            return {"_raw": value}
    return {}


def _ollama_tool_calls(raw: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        fn = item.get("function") or {}
        out.append(
            {
                "function": {
                    "name": str(fn.get("name") or ""),
                    "arguments": _arguments_object(fn.get("arguments")),
                }
            }
        )
    return out


def _ollama_messages(messages: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "user")
        item: dict[str, Any] = {"role": role, "content": _content_text(msg.get("content"))}
        tool_calls = msg.get("tool_calls")
        if tool_calls:
            converted = _ollama_tool_calls(tool_calls)
            if converted:
                item["tool_calls"] = converted
        images = msg.get("images")
        if images:
            item["images"] = images
        out.append(item)
    return out


def _flatten_schema_types(node: Any) -> Any:
    """Ollama rejects JSON-Schema ``type: ["string", "null"]`` (expects a string)."""
    if isinstance(node, list):
        return [_flatten_schema_types(item) for item in node]
    if not isinstance(node, dict):
        return node
    out = {key: _flatten_schema_types(value) for key, value in node.items()}
    raw_type = out.get("type")
    if isinstance(raw_type, list):
        non_null = [item for item in raw_type if item not in (None, "null")]
        out["type"] = non_null[0] if non_null else "string"
    return out


def _ollama_tools(tools: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        fn = dict(tool.get("function") or {})
        params = _flatten_schema_types(fn.get("parameters") or {"type": "object", "properties": {}})
        out.append(
            {
                "type": "function",
                "function": {
                    "name": str(fn.get("name") or ""),
                    "description": str(fn.get("description") or ""),
                    "parameters": params if isinstance(params, dict) else {"type": "object"},
                },
            }
        )
    return out


def _think_value(kwargs: dict[str, Any], metadata: dict[str, Any]) -> bool | str | None:
    extra = dict(kwargs.get("extra_body") or {})
    raw = extra.get(
        "think",
        extra.get("enable_thinking", metadata.get("think", metadata.get("enable_thinking"))),
    )
    if isinstance(raw, str) and raw.strip().lower() in {"high", "medium", "low", "max"}:
        return raw.strip().lower()
    flag = _flag(raw)
    if flag is True:
        return True
    if flag is False:
        model = str(kwargs.get("model") or "")
        if model_supports_thinking(model):
            return False
        return None
    return None


def build_chat_payload(kwargs: dict[str, Any], metadata: dict[str, Any] | None) -> dict[str, Any]:
    meta = metadata or {}
    extra = dict(kwargs.get("extra_body") or {})
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
        "messages": _ollama_messages(kwargs.get("messages") or []),
        "stream": bool(kwargs.get("stream")),
    }
    think = _think_value(kwargs, meta)
    if think is not None:
        payload["think"] = think
    tools = kwargs.get("tools")
    if tools:
        payload["tools"] = _ollama_tools(tools)
    choice = kwargs.get("tool_choice")
    if isinstance(choice, str) and choice not in {"", "auto", "none"}:
        payload["tool_choice"] = choice
    elif choice == "none":
        payload.pop("tools", None)
    if options:
        payload["options"] = options
    return payload


def _http_error(response: httpx.Response, url: str) -> httpx.HTTPStatusError:
    detail = (response.text or "").strip().replace("\n", " ")[:500]
    message = f"Client error '{response.status_code} {response.reason_phrase}' for url '{url}'"
    if detail:
        message = f"{message} — {detail}"
    return httpx.HTTPStatusError(message, request=response.request, response=response)


class _OllamaCompletions:
    def __init__(
        self,
        http: httpx.AsyncClient,
        origin: str,
        metadata: dict[str, Any],
        openai_client: Any,
    ) -> None:
        self._http = http
        self._origin = origin
        self._metadata = metadata
        self._openai_client = openai_client

    async def create(self, **kwargs: Any) -> Any:
        payload = build_chat_payload(kwargs, self._metadata)
        url = f"{self._origin}/api/chat"
        model = str(payload.get("model") or "")
        if payload.get("stream"):
            return self._stream(url, payload, model, kwargs)
        try:
            return await self._complete_once(url, payload, model)
        except httpx.HTTPStatusError as exc:
            retried = await self._retry_or_fallback(exc, url, payload, model, kwargs)
            if retried is not None:
                return retried
            raise

    async def _complete_once(self, url: str, payload: dict[str, Any], model: str) -> Any:
        response = await self._http.post(url, json=payload)
        if response.status_code >= 400:
            raise _http_error(response, url)
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Ollama /api/chat returned a non-object body")
        return to_openai_response(data, model=model)

    async def _retry_or_fallback(
        self,
        exc: httpx.HTTPStatusError,
        url: str,
        payload: dict[str, Any],
        model: str,
        kwargs: dict[str, Any],
    ) -> Any | None:
        if exc.response is None or exc.response.status_code != 400:
            return None
        body = (exc.response.text or "").lower()
        logger.warning("Ollama /api/chat 400: %s", (exc.response.text or "")[:400])
        if "think" in payload and ("think" in body or "thinking" in body):
            retry = dict(payload)
            retry.pop("think", None)
            try:
                return await self._complete_once(url, retry, model)
            except httpx.HTTPStatusError:
                pass
        if "tool" in body and payload.get("tools"):
            retry = dict(payload)
            retry.pop("tools", None)
            retry.pop("tool_choice", None)
            try:
                return await self._complete_once(url, retry, model)
            except httpx.HTTPStatusError:
                pass
        fallback = getattr(getattr(self._openai_client, "chat", None), "completions", None)
        create = getattr(fallback, "create", None)
        if callable(create):
            logger.warning("Ollama native /api/chat failed; falling back to OpenAI /v1")
            return await create(**kwargs)
        return None

    async def _stream(self, url: str, payload: dict[str, Any], model: str, kwargs: dict[str, Any]):
        try:
            async with self._http.stream("POST", url, json=payload) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise _http_error(response, url)
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
        except httpx.HTTPStatusError as exc:
            retried = await self._retry_or_fallback(exc, url, payload, model, kwargs)
            if retried is not None:
                if hasattr(retried, "__aiter__"):
                    async for chunk in retried:
                        yield chunk
                    return
                # Non-stream fallback: emit a single synthetic chunk.
                msg = getattr(getattr(retried, "choices", [None])[0], "message", None)
                yield to_openai_chunk(
                    {
                        "message": {
                            "role": "assistant",
                            "content": getattr(msg, "content", "") or "",
                            "thinking": getattr(msg, "reasoning", "") or "",
                        },
                        "done": True,
                        "done_reason": "stop",
                    },
                    model=model,
                )
                return
            raise


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
        self.chat = SimpleNamespace(
            completions=_OllamaCompletions(http, origin, metadata, openai_client)
        )


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
