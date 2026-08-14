"""Detect and probe a live OpenAI-compatible LLM for live_llm tests."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LiveProvider:
    model: str
    base_url: str
    api_key: str
    source: str


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def resolve_live_provider() -> LiveProvider | None:
    """Pick model/base_url/api_key from env, then Holix settings."""
    model = _env("HOLIX_LIVE_MODEL")
    base_url = _env("HOLIX_LIVE_BASE_URL")
    api_key = _env("HOLIX_LIVE_API_KEY")
    source = "env"

    if not (model and base_url):
        try:
            from config import settings

            model = model or (getattr(settings, "model", None) or "").strip()
            base_url = base_url or (getattr(settings, "base_url", None) or "").strip()
            if not api_key:
                api_key = (getattr(settings, "api_key", None) or "").strip()
            source = "settings"
        except Exception:
            pass

    if not (model and base_url):
        # Common local default
        if _env("HOLIX_LIVE_LLM") in {"1", "true", "yes", "on"}:
            model = model or "llama3.2"
            base_url = base_url or "http://localhost:11434/v1"
            api_key = api_key or "ollama"
            source = "live_default"
        else:
            return None

    if not api_key:
        # OpenAI-compatible local servers often accept a dummy key
        api_key = _env("OPENAI_API_KEY") or "ollama"

    return LiveProvider(model=model, base_url=base_url, api_key=api_key, source=source)


async def probe_provider(provider: LiveProvider, *, timeout_s: float = 120.0) -> str | None:
    """Return None if OK, else error message."""
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            base_url=provider.base_url,
            api_key=provider.api_key,
            timeout=timeout_s,
        )
        resp = await client.chat.completions.create(
            model=provider.model,
            messages=[
                {
                    "role": "user",
                    "content": "Reply with exactly the word PONG and nothing else.",
                }
            ],
            max_tokens=128,
            temperature=0,
        )
        msg = resp.choices[0].message
        text = (msg.content or "").strip()
        # Some models put text only in reasoning_content on short probes.
        if not text:
            text = (getattr(msg, "reasoning_content", None) or "").strip()
        if not text and resp.choices:
            # Accept non-error completion even if body is empty once (proxy glitch).
            finish = getattr(resp.choices[0], "finish_reason", None)
            if finish in (None, "stop", "length"):
                return None
            return f"empty completion (finish_reason={finish!r})"
        return None
    except Exception as exc:  # noqa: BLE001 — surface any provider failure as skip reason
        return f"{type(exc).__name__}: {exc}"


def live_llm_forced_off() -> bool:
    return _env("HOLIX_LIVE_LLM").lower() in {"0", "false", "no", "off"}


def live_llm_forced_on() -> bool:
    return _env("HOLIX_LIVE_LLM").lower() in {"1", "true", "yes", "on"}


def soft_contains(text: str, *needles: str, min_hits: int = 1) -> bool:
    """Case-insensitive multi-needle check for flaky live answers."""
    low = (text or "").lower()
    hits = sum(1 for n in needles if n.lower() in low)
    return hits >= min_hits


def extract_final(events: list[Any], return_value: str = "") -> str:
    from core.agent_events import FinalResponseEvent

    for e in reversed(events):
        if isinstance(e, FinalResponseEvent) and (e.content or "").strip():
            return e.content
    return return_value or ""
