"""Profile presets for System One decisions and optional text embeddings.

The chat model stays the one that writes replies. These blocks only name a
separate endpoint. Both default to off. API keys stay in the profile ``.env``
(``DECISION_API_KEY``, ``EMBEDDINGS_API_KEY``) and are not written into YAML.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

DECISION_PRESETS = ("off", "jev", "nimble", "tev1", "custom")
EMBEDDING_APIS = ("off", "openai", "ollama")

_DECISION_DEFAULTS: dict[str, dict[str, str]] = {
    "off": {"base_url": "", "model": ""},
    "jev": {"base_url": "https://api.typesafe.ai", "model": "jev-latest"},
    "nimble": {"base_url": "http://127.0.0.1:11434", "model": "nimble"},
    "tev1": {"base_url": "http://127.0.0.1:11434", "model": "tev1:4b"},
    "custom": {"base_url": "", "model": ""},
}

_OLLAMA_EMBED_BASE = "http://127.0.0.1:11434"
_MAX_BODY_BYTES = 1_048_576


def max_body_bytes() -> int:
    return _MAX_BODY_BYTES


def is_typesafe_host(base_url: str) -> bool:
    host = (urlparse(str(base_url or "")).hostname or "").lower()
    return host == "api.typesafe.ai" or host.endswith(".typesafe.ai")


def systemone_url(base_url: str) -> str:
    """Build the System One URL for a profile base.

    A base that already ends in ``/api/v1`` or ``/v1`` gets ``/systemone``.
    Any other base gets ``/v1/systemone``.
    """
    base = str(base_url or "").strip().rstrip("/")
    if base.endswith("/api/v1") or base.endswith("/v1"):
        return f"{base}/systemone"
    return f"{base}/v1/systemone"


def embeddings_url(base_url: str, api: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    kind = str(api or "openai").strip().lower()
    if kind == "ollama":
        if base.endswith("/api/embed"):
            return base
        return f"{base}/api/embed"
    if base.endswith("/embeddings"):
        return base
    if base.endswith("/v1"):
        return f"{base}/embeddings"
    return f"{base}/v1/embeddings"


def _timeout(value: Any) -> float:
    try:
        timeout = float(value if value is not None else 30)
    except (TypeError, ValueError):
        timeout = 30.0
    if timeout < 1:
        return 1.0
    if timeout > 120:
        return 120.0
    return timeout


def _as_dict(raw: Any) -> dict[str, Any]:
    return dict(raw) if isinstance(raw, dict) else {}


@dataclass(frozen=True, slots=True)
class ResolvedDecision:
    enabled: bool
    preset: str
    base_url: str
    model: str
    timeout_s: float
    api_key: str


@dataclass(frozen=True, slots=True)
class ResolvedEmbeddings:
    enabled: bool
    api: str
    base_url: str
    model: str
    timeout_s: float
    api_key: str


def resolve_decision(raw: Any, *, api_key: str | None = None) -> ResolvedDecision:
    data = _as_dict(raw)
    preset = str(data.get("preset") or "off").strip().lower()
    if preset not in _DECISION_DEFAULTS:
        preset = "off"
    enabled = bool(data.get("enabled")) and preset != "off"
    base_url = str(data.get("base_url") or "").strip().rstrip("/")
    model = str(data.get("model") or "").strip()
    if enabled:
        defaults = _DECISION_DEFAULTS[preset]
        if not base_url:
            base_url = defaults["base_url"]
        if not model and preset != "custom":
            model = defaults["model"]
        if not model and is_typesafe_host(base_url):
            model = "jev-latest"
    if enabled and (not base_url or not model):
        enabled = False
    if api_key is None:
        api_key = os.environ.get("DECISION_API_KEY", "")
    return ResolvedDecision(
        enabled=enabled,
        preset=preset,
        base_url=base_url,
        model=model,
        timeout_s=_timeout(data.get("timeout_s")),
        api_key=str(api_key or "").strip(),
    )


def configure_decision(
    current: Any,
    preset: str,
    *,
    base_url: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Return the decision block for ``holix decision use``.

    Switching presets replaces that preset's endpoint and model. An explicit
    ``base_url`` or ``model`` wins. Re-applying the same preset keeps a model
    the user already set (for example a pinned ``jev-1.13.0``).
    """
    name = str(preset or "").strip().lower()
    if name not in _DECISION_DEFAULTS:
        raise ValueError(f"Unknown decision preset: {preset}")
    src = _as_dict(current)
    previous = str(src.get("preset") or "off").strip().lower()
    out: dict[str, Any] = {
        "enabled": name != "off",
        "preset": name,
        "base_url": str(src.get("base_url") or "").strip().rstrip("/"),
        "model": str(src.get("model") or "").strip(),
        "timeout_s": _timeout(src.get("timeout_s")),
        "skills": dict(src.get("skills") or {}),
        "internal": dict(src.get("internal") or {}),
        "thresholds": dict(src.get("thresholds") or {}),
    }
    if name == "off":
        return out
    switching = previous != name
    if base_url is not None:
        out["base_url"] = str(base_url).strip().rstrip("/")
    elif (switching or not out["base_url"]) and name != "custom":
        out["base_url"] = _DECISION_DEFAULTS[name]["base_url"]
    if model is not None:
        out["model"] = str(model).strip()
    elif switching or not out["model"]:
        if name == "custom":
            if is_typesafe_host(str(out["base_url"])) and not out["model"]:
                out["model"] = "jev-latest"
        else:
            out["model"] = _DECISION_DEFAULTS[name]["model"]
    if name == "custom" and not out["base_url"]:
        raise ValueError("custom preset needs --base-url")
    if name == "custom" and not out["model"] and is_typesafe_host(str(out["base_url"])):
        out["model"] = "jev-latest"
    return out


def resolve_embeddings(raw: Any, *, api_key: str | None = None) -> ResolvedEmbeddings:
    data = _as_dict(raw)
    api = str(data.get("api") or "openai").strip().lower()
    if api not in {"openai", "ollama"}:
        api = "openai"
    enabled = bool(data.get("enabled"))
    base_url = str(data.get("base_url") or "").strip().rstrip("/")
    model = str(data.get("model") or "").strip()
    if enabled and (not base_url or not model):
        enabled = False
    if api_key is None:
        api_key = os.environ.get("EMBEDDINGS_API_KEY", "")
    return ResolvedEmbeddings(
        enabled=enabled,
        api=api,
        base_url=base_url,
        model=model,
        timeout_s=_timeout(data.get("timeout_s")),
        api_key=str(api_key or "").strip(),
    )


def configure_embeddings(
    current: Any,
    api: str,
    *,
    base_url: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    name = str(api or "").strip().lower()
    if name not in EMBEDDING_APIS:
        raise ValueError(f"Unknown embeddings api: {api}")
    src = _as_dict(current)
    out: dict[str, Any] = {
        "enabled": name != "off",
        "api": "ollama" if name == "ollama" else str(src.get("api") or "openai"),
        "base_url": str(src.get("base_url") or "").strip().rstrip("/"),
        "model": str(src.get("model") or "").strip(),
        "timeout_s": _timeout(src.get("timeout_s")),
        "skills": dict(src.get("skills") or {}),
    }
    if name == "off":
        out["enabled"] = False
        return out
    out["api"] = "ollama" if name == "ollama" else "openai"
    if base_url is not None:
        out["base_url"] = str(base_url).strip().rstrip("/")
    elif name == "ollama" and not out["base_url"]:
        out["base_url"] = _OLLAMA_EMBED_BASE
    if model is not None:
        out["model"] = str(model).strip()
    if not out["base_url"] or not out["model"]:
        raise ValueError("embeddings need --base-url and --model")
    return out
