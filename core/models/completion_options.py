"""Provider-specific chat.completions extras.

Ollama reasoning models (Kimi K2, Qwen3, …) put tokens into ``message.reasoning``
and leave ``message.content`` empty unless thinking is turned off. Messenger UIs
then report “agent finished without a reply”.
"""

from __future__ import annotations

from typing import Any

from core.url_utils import url_port

_NOT_OLLAMA_PROVIDERS = frozenset(
    {
        "lmstudio",
        "lm-studio",
        "vllm",
        "openai",
        "litellm",
        "litellm_internal",
        "openrouter",
    }
)

# Ollama 400s ``think`` on models that do not support thinking.
_THINKING_MODEL_MARKERS = (
    "kimi",
    "qwen3",
    "qwq",
    "deepseek-r1",
    "gpt-oss",
    "magistral",
    "cogito",
    "thinking",
)


def model_supports_thinking(model: str) -> bool:
    name = (model or "").strip().lower()
    return any(marker in name for marker in _THINKING_MODEL_MARKERS)


def is_ollama_like(cfg: Any) -> bool:
    name = str(getattr(cfg, "provider", "") or "").strip().lower()
    url = str(getattr(cfg, "base_url", "") or "").strip().lower()
    if name in _NOT_OLLAMA_PROVIDERS:
        return False
    if name == "ollama":
        return True
    if "ollama" in url:
        return True
    return url_port(url) == 11434


def _thinking_enabled(metadata: dict[str, Any] | None) -> bool:
    meta = metadata or {}
    raw = meta.get("enable_thinking", meta.get("think", False))
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return bool(raw)


def with_provider_completion_options(cfg: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Merge Ollama think-off extras unless the profile opts into thinking."""
    out = dict(kwargs)
    if not is_ollama_like(cfg):
        return out
    if _thinking_enabled(getattr(cfg, "metadata", None)):
        return out
    if not model_supports_thinking(str(getattr(cfg, "model", "") or "")):
        return out
    extra = dict(out.get("extra_body") or {})
    extra.setdefault("think", False)
    template_kwargs = dict(extra.get("chat_template_kwargs") or {})
    template_kwargs.setdefault("enable_thinking", False)
    extra["chat_template_kwargs"] = template_kwargs
    out["extra_body"] = extra
    return out
