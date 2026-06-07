"""Curated LLM provider presets (URLs, auth, popular models)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.url_utils import host_is, url_hostname, url_port


@dataclass(frozen=True, slots=True)
class ProviderPreset:
    """Built-in provider template for ``helix models setup`` / ``models add``."""

    id: str
    display_name: str
    base_url: str
    api_key_env: str
    api_key_placeholder: str
    auth_type: str = "bearer"
    default_model: str | None = None
    popular_models: tuple[str, ...] = ()
    model_contexts: dict[str, int] = field(default_factory=dict)
    docs_url: str = ""
    notes: str = ""
    extra_env: tuple[str, ...] = ()
    configurable_host: bool = False
    default_host: str = "127.0.0.1"
    default_port: int = 0
    api_path: str = "/v1"
    host_env: str = ""
    host_placeholder: str = ""

    def default_metadata(self) -> dict[str, Any]:
        """Provider ``metadata`` block stored in profile YAML."""
        meta: dict[str, Any] = {"auth_type": self.auth_type, "preset_id": self.id}
        if self.auth_type == "openrouter":
            meta["http_referer"] = "${OPENROUTER_HTTP_REFERER}"
            meta["x_title"] = "Helix"
        if self.extra_env:
            meta["extra_env"] = list(self.extra_env)
        if self.configurable_host:
            meta["configurable_host"] = True
            if self.host_env:
                meta["host_env"] = self.host_env
            if self.default_port:
                meta["default_port"] = self.default_port
        return meta

    def to_provider_dict(self, *, api_key: str | None = None) -> dict[str, Any]:
        """Build a profile ``providers.<name>`` entry."""
        key = api_key if api_key is not None else self.api_key_placeholder
        models = list(self.popular_models)
        return {
            "name": self.id,
            "base_url": self.base_url,
            "api_key": key,
            "default_model": self.default_model or (models[0] if models else None),
            "available_models": models,
            "model_contexts": dict(self.model_contexts),
            "metadata": self.default_metadata(),
        }


# Context windows for common models (tokens); discovery may override.
_CTX = {
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "o3-mini": 200_000,
    "claude-sonnet-4-20250514": 200_000,
    "claude-3-5-sonnet-20241022": 200_000,
    "deepseek-chat": 64_000,
    "deepseek-reasoner": 64_000,
    "moonshot-v1-128k": 128_000,
    "grok-3": 131_072,
    "grok-3-mini": 131_072,
}


def _preset(
    id: str,
    display_name: str,
    base_url: str,
    api_key_env: str,
    *,
    auth_type: str = "bearer",
    default_model: str | None = None,
    popular_models: tuple[str, ...] = (),
    model_contexts: dict[str, int] | None = None,
    docs_url: str = "",
    notes: str = "",
    extra_env: tuple[str, ...] = (),
    configurable_host: bool = False,
    default_host: str = "127.0.0.1",
    default_port: int = 0,
    api_path: str = "/v1",
    host_env: str = "",
    host_placeholder: str = "",
) -> ProviderPreset:
    ctx = dict(model_contexts or {})
    for m in popular_models:
        if m in _CTX and m not in ctx:
            ctx[m] = _CTX[m]
    return ProviderPreset(
        id=id,
        display_name=display_name,
        base_url=base_url,
        api_key_env=api_key_env,
        api_key_placeholder=f"${{{api_key_env}}}",
        auth_type=auth_type,
        default_model=default_model,
        popular_models=popular_models,
        model_contexts=ctx,
        docs_url=docs_url,
        notes=notes,
        extra_env=extra_env,
        configurable_host=configurable_host,
        default_host=default_host,
        default_port=default_port,
        api_path=api_path,
        host_env=host_env,
        host_placeholder=host_placeholder or (f"${{{host_env}}}" if host_env else ""),
    )


def build_base_url_from_host(
    host: str,
    port: int,
    *,
    api_path: str = "/v1",
    scheme: str = "http",
) -> str:
    """Build OpenAI-compatible base URL from host and port."""
    path = api_path if api_path.startswith("/") else f"/{api_path}"
    if not path.endswith("/v1"):
        path = path.rstrip("/") + "/v1"
    host = host.strip()
    if host.startswith("http://") or host.startswith("https://"):
        base = host.rstrip("/")
        return base if base.endswith("/v1") else f"{base}/v1"
    if ":" in host and not host.startswith("["):
        return f"{scheme}://{host}{path}"
    return f"{scheme}://{host}:{port}{path}"


def parse_host_value(
    value: str,
    *,
    default_port: int,
    api_path: str = "/v1",
) -> str:
    """Parse host input: URL, host:port, or hostname → base_url."""
    raw = (value or "").strip()
    if not raw:
        return build_base_url_from_host("127.0.0.1", default_port, api_path=api_path)
    if raw.startswith("http://") or raw.startswith("https://"):
        base = raw.rstrip("/")
        return base if base.endswith("/v1") else f"{base}/v1"
    if "/" in raw:
        base = raw if "://" in raw else f"http://{raw}"
        base = base.rstrip("/")
        return base if base.endswith("/v1") else f"{base}/v1"
    return build_base_url_from_host(raw, default_port, api_path=api_path)


def resolve_preset_base_url(
    preset: ProviderPreset,
    *,
    host: str | None = None,
    port: int | None = None,
) -> str:
    """Resolve base_url for host-capable presets (env → args → catalog default)."""
    if not preset.configurable_host:
        return preset.base_url

    effective_port = port or preset.default_port or 11434

    if host:
        return parse_host_value(host, default_port=effective_port, api_path=preset.api_path)

    if preset.host_env:
        import os

        from core.config_utils import resolve_env_refs

        env_val = os.environ.get(preset.host_env, "").strip()
        if not env_val and preset.host_placeholder:
            resolved = resolve_env_refs(preset.host_placeholder.strip())
            if resolved and resolved != preset.host_placeholder and "${" not in str(resolved):
                env_val = str(resolved).strip()
        if env_val:
            return parse_host_value(env_val, default_port=effective_port, api_path=preset.api_path)

    return preset.base_url


HOST_CAPABLE_PRESET_IDS: frozenset[str] = frozenset({"ollama", "litellm", "vllm"})


PROVIDER_PRESETS: tuple[ProviderPreset, ...] = (
    _preset(
        "ollama",
        "Ollama",
        "http://127.0.0.1:11434/v1",
        "OLLAMA_API_KEY",
        auth_type="none",
        default_model="qwen2.5-coder:32b",
        popular_models=(
            "qwen2.5-coder:32b",
            "llama3.3",
            "deepseek-r1",
            "mistral",
        ),
        docs_url="https://ollama.com",
        notes="Set host (default 127.0.0.1:11434) or OLLAMA_HOST=http://host:11434 in .env",
        configurable_host=True,
        default_host="127.0.0.1",
        default_port=11434,
        host_env="OLLAMA_HOST",
        host_placeholder="${OLLAMA_HOST}",
    ),
    _preset(
        "openai",
        "OpenAI",
        "https://api.openai.com/v1",
        "OPENAI_API_KEY",
        default_model="gpt-4o-mini",
        popular_models=("gpt-4o", "gpt-4o-mini", "o3-mini", "gpt-4.1"),
        docs_url="https://platform.openai.com/docs",
    ),
    _preset(
        "anthropic",
        "Anthropic (via OpenRouter)",
        "https://openrouter.ai/api/v1",
        "OPENROUTER_API_KEY",
        auth_type="openrouter",
        default_model="anthropic/claude-sonnet-4",
        popular_models=(
            "anthropic/claude-sonnet-4",
            "anthropic/claude-3.5-sonnet",
            "anthropic/claude-3-haiku",
        ),
        docs_url="https://docs.anthropic.com",
        notes=(
            "Native Anthropic API is not OpenAI-compatible. "
            "This preset uses OpenRouter with your OPENROUTER_API_KEY. "
            "For a direct Anthropic key, run a LiteLLM/Ollama-compatible proxy."
        ),
        extra_env=("OPENROUTER_HTTP_REFERER",),
    ),
    _preset(
        "openrouter",
        "OpenRouter",
        "https://openrouter.ai/api/v1",
        "OPENROUTER_API_KEY",
        auth_type="openrouter",
        default_model="anthropic/claude-sonnet-4",
        popular_models=(
            "anthropic/claude-sonnet-4",
            "openai/gpt-4o",
            "google/gemini-2.5-pro-preview",
            "deepseek/deepseek-chat",
            "x-ai/grok-3",
            "meta-llama/llama-3.3-70b-instruct",
        ),
        docs_url="https://openrouter.ai/docs",
        notes="One API key for many vendors; optional OPENROUTER_HTTP_REFERER for rankings.",
        extra_env=("OPENROUTER_HTTP_REFERER",),
    ),
    _preset(
        "deepseek",
        "DeepSeek",
        "https://api.deepseek.com/v1",
        "DEEPSEEK_API_KEY",
        default_model="deepseek-chat",
        popular_models=("deepseek-chat", "deepseek-reasoner"),
        docs_url="https://platform.deepseek.com/api-docs",
    ),
    _preset(
        "moonshot",
        "Moonshot / Kimi",
        "https://api.moonshot.cn/v1",
        "MOONSHOT_API_KEY",
        default_model="moonshot-v1-128k",
        popular_models=("moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"),
        docs_url="https://platform.moonshot.cn/docs",
        notes="Also known as Kimi; international endpoints may differ.",
    ),
    _preset(
        "xai",
        "xAI (Grok)",
        "https://api.x.ai/v1",
        "XAI_API_KEY",
        default_model="grok-3-mini",
        popular_models=("grok-3", "grok-3-mini", "grok-2-1212"),
        docs_url="https://docs.x.ai",
    ),
    _preset(
        "groq",
        "Groq",
        "https://api.groq.com/openai/v1",
        "GROQ_API_KEY",
        default_model="llama-3.3-70b-versatile",
        popular_models=(
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
        ),
        docs_url="https://console.groq.com/docs",
    ),
    _preset(
        "google",
        "Google Gemini (OpenAI-compatible)",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "GOOGLE_API_KEY",
        default_model="gemini-2.0-flash",
        popular_models=("gemini-2.0-flash", "gemini-2.5-pro-preview-03-25"),
        docs_url="https://ai.google.dev/gemini-api/docs/openai",
    ),
    _preset(
        "mistral",
        "Mistral AI",
        "https://api.mistral.ai/v1",
        "MISTRAL_API_KEY",
        default_model="mistral-small-latest",
        popular_models=("mistral-large-latest", "mistral-small-latest", "codestral-latest"),
        docs_url="https://docs.mistral.ai",
    ),
    _preset(
        "together",
        "Together AI",
        "https://api.together.xyz/v1",
        "TOGETHER_API_KEY",
        default_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        popular_models=(
            "meta-llama/Llama-3.3-70B-Instruct-Turbo",
            "deepseek-ai/DeepSeek-R1",
        ),
        docs_url="https://docs.together.ai",
    ),
    _preset(
        "fireworks",
        "Fireworks AI",
        "https://api.fireworks.ai/inference/v1",
        "FIREWORKS_API_KEY",
        default_model="accounts/fireworks/models/llama-v3p3-70b-instruct",
        docs_url="https://docs.fireworks.ai",
    ),
    _preset(
        "cerebras",
        "Cerebras",
        "https://api.cerebras.ai/v1",
        "CEREBRAS_API_KEY",
        default_model="llama-3.3-70b",
        popular_models=("llama-3.3-70b", "qwen-3-32b"),
        docs_url="https://inference-docs.cerebras.ai",
    ),
    _preset(
        "litellm",
        "LiteLLM proxy",
        "http://127.0.0.1:4000/v1",
        "LITELLM_API_KEY",
        default_model="smart",
        popular_models=("smart", "fast", "heavy"),
        docs_url="https://docs.litellm.ai",
        notes="Unified proxy; host/port via prompt or LITELLM_API_BASE in .env",
        configurable_host=True,
        default_host="127.0.0.1",
        default_port=4000,
        host_env="LITELLM_API_BASE",
        host_placeholder="${LITELLM_API_BASE}",
        extra_env=("LITELLM_API_KEY",),
    ),
    _preset(
        "vllm",
        "vLLM (OpenAI-compatible)",
        "http://127.0.0.1:8000/v1",
        "VLLM_API_KEY",
        auth_type="none",
        default_model="",
        popular_models=(),
        docs_url="https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html",
        notes="vLLM OpenAI server; host/port via prompt or VLLM_HOST in .env (API key often 'EMPTY')",
        configurable_host=True,
        default_host="127.0.0.1",
        default_port=8000,
        host_env="VLLM_HOST",
        host_placeholder="${VLLM_HOST}",
    ),
)


_PRESET_BY_ID: dict[str, ProviderPreset] = {p.id: p for p in PROVIDER_PRESETS}


def get_provider_preset(preset_id: str) -> ProviderPreset | None:
    return _PRESET_BY_ID.get(preset_id.strip().lower())


def list_provider_presets() -> list[ProviderPreset]:
    return list(PROVIDER_PRESETS)


def detect_preset_from_url(base_url: str) -> str | None:
    """Match configured base_url to a known preset id."""
    host = url_hostname(base_url)
    port = url_port(base_url)

    for preset in PROVIDER_PRESETS:
        preset_host = url_hostname(preset.base_url)
        if preset_host and host_is(host, preset_host):
            return preset.id

    if host_is(host, "openrouter.ai"):
        return "openrouter"
    if host_is(host, "api.openai.com"):
        return "openai"
    if host_is(host, "deepseek.com"):
        return "deepseek"
    if host_is(host, "api.moonshot.cn") or host_is(host, "moonshot.cn"):
        return "moonshot"
    if host_is(host, "api.x.ai"):
        return "xai"
    if host_is(host, "groq.com"):
        return "groq"
    if host_is(host, "generativelanguage.googleapis.com"):
        return "google"
    if host_is(host, "mistral.ai"):
        return "mistral"
    if host_is(host, "together.xyz"):
        return "together"
    if host_is(host, "fireworks.ai"):
        return "fireworks"
    if host_is(host, "cerebras.ai"):
        return "cerebras"
    if port == 11434:
        return "ollama"
    if port == 4000:
        return "litellm"
    if port == 8000:
        return "vllm"
    return None