"""Voice message handler: download → transcribe → text."""

from __future__ import annotations

import asyncio
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp
from core.platform_compat import resolve_holix_home

from integrations.telegram.markdown import escape_html

_LOCAL_MODEL_CACHE: dict[tuple[str, str, str, str], Any] = {}

_MIME_SUFFIX: dict[str, str] = {
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/wav": ".wav",
    "audio/webm": ".webm",
}

_PLACEHOLDER_KEYS = frozenset({"", "ollama", "EMPTY", "none", "null"})


@dataclass(frozen=True, slots=True)
class WhisperConfig:
    api_key: str
    base_url: str
    model: str
    language: str | None = None
    backend: str = "openai"
    local_device: str = "cpu"
    local_compute_type: str = "int8"


def local_whisper_download_root() -> str:
    """Return the directory where faster-whisper stores downloaded weights."""
    from config import settings

    raw = (settings.whisper_local_download_root or "").strip()
    if raw:
        root = Path(raw).expanduser()
    else:
        root = resolve_holix_home() / "models" / "whisper"
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


def faster_whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False


def _local_whisper_config(language: str | None, model: str) -> WhisperConfig:
    from config import settings

    return WhisperConfig(
        api_key="",
        base_url="",
        model=model,
        language=language,
        backend="local",
        local_device=settings.whisper_local_device or "cpu",
        local_compute_type=settings.whisper_local_compute_type or "int8",
    )


def _normalize_base_url(url: str) -> str:
    base = url.strip().rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return base


def _profile_litellm_credentials(profile: str) -> tuple[str, str] | None:
    try:
        from cli.core import get_profile_manager

        config = get_profile_manager().load_profile(profile)
    except Exception:
        return None

    providers = getattr(config, "providers", None) or {}
    pdata = providers.get("litellm")
    if not isinstance(pdata, dict):
        return None

    api_key = str(pdata.get("api_key") or "").strip()
    base_url = str(pdata.get("base_url") or "").strip()
    if not api_key or api_key in _PLACEHOLDER_KEYS or not base_url:
        return None
    return api_key, _normalize_base_url(base_url)


def resolve_whisper_config(*, profile: str | None = None) -> WhisperConfig:
    """Resolve Whisper transcription backend and credentials.

    Backends:
    - ``local`` — faster-whisper on the same machine (``uv sync --extra voice``)
    - ``api`` / ``litellm`` / ``openai`` — HTTP ``/v1/audio/transcriptions``

    Priority (when backend is ``api`` or ``auto``):
    1. HOLIX_WHISPER_API_KEY + HOLIX_WHISPER_BASE_URL
    2. OPENAI_API_KEY + OPENAI_BASE_URL
    3. LITELLM_API_KEY + LITELLM_API_BASE
    4. Profile ``litellm`` provider (when HOLIX_WHISPER_USE_PROFILE_LITELLM=true)
    5. Local faster-whisper (``auto`` only, if installed)
    """
    from config import settings

    language = (settings.telegram_voice_language or "").strip() or None
    model = (settings.whisper_model or "whisper-1").strip()
    backend_mode = (settings.whisper_backend or "api").strip().lower()

    if backend_mode == "local":
        if not faster_whisper_available():
            raise RuntimeError(
                "Local Whisper requires faster-whisper. Install: uv sync --extra voice"
            )
        local_model = (settings.whisper_local_model or "base").strip()
        return _local_whisper_config(language, local_model)

    # 1. Explicit whisper override (recommended for LiteLLM)
    w_key = (settings.whisper_api_key or os.environ.get("HOLIX_WHISPER_API_KEY", "")).strip()
    w_base = (settings.whisper_base_url or os.environ.get("HOLIX_WHISPER_BASE_URL", "")).strip()
    if w_key and w_base:
        return WhisperConfig(
            api_key=w_key,
            base_url=_normalize_base_url(w_base),
            model=model,
            language=language,
            backend="litellm",
        )

    # 2. OpenAI (direct or LiteLLM via OPENAI_BASE_URL)
    api_key = (settings.openai_api_key or os.environ.get("OPENAI_API_KEY", "")).strip()
    if api_key:
        base_url = (
            settings.openai_base_url
            or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        ).strip()
        backend = "litellm" if "litellm" in base_url.lower() or ":4000" in base_url else "openai"
        return WhisperConfig(
            api_key=api_key,
            base_url=_normalize_base_url(base_url),
            model=model,
            language=language,
            backend=backend,
        )

    # 3. LiteLLM env aliases
    litellm_key = os.environ.get("LITELLM_API_KEY", "").strip()
    litellm_base = os.environ.get("LITELLM_API_BASE", "").strip()
    if litellm_key and litellm_base:
        return WhisperConfig(
            api_key=litellm_key,
            base_url=_normalize_base_url(litellm_base),
            model=model,
            language=language,
            backend="litellm",
        )

    # 4. Profile litellm provider (same key/URL as chat)
    if settings.whisper_use_profile_litellm and profile:
        creds = _profile_litellm_credentials(profile)
        if creds:
            api_key, base_url = creds
            litellm_model = model if model != "whisper-1" else "whisper"
            return WhisperConfig(
                api_key=api_key,
                base_url=base_url,
                model=litellm_model,
                language=language,
                backend="litellm",
            )

    if backend_mode == "auto" and faster_whisper_available():
        local_model = (settings.whisper_local_model or "base").strip()
        return _local_whisper_config(language, local_model)

    raise RuntimeError(
        "Whisper not configured. Options:\n"
        "• Local: HOLIX_WHISPER_BACKEND=local + uv sync --extra voice\n"
        "• LiteLLM: HOLIX_WHISPER_BASE_URL + HOLIX_WHISPER_API_KEY\n"
        "• OpenAI: OPENAI_API_KEY\n"
        "• Auto: HOLIX_WHISPER_BACKEND=auto (local if faster-whisper installed, else API)"
    )


def suffix_for_audio(*, mime_type: str | None = None, file_path: str | None = None) -> str:
    if mime_type:
        normalized = mime_type.split(";")[0].strip().lower()
        if normalized in _MIME_SUFFIX:
            return _MIME_SUFFIX[normalized]
    if file_path:
        ext = Path(file_path).suffix.lower()
        if ext in {".ogg", ".oga", ".mp3", ".m4a", ".wav", ".webm"}:
            return ext
    return ".ogg"


def format_transcription_preview(text: str, *, max_len: int = 300) -> str:
    preview = (text or "").strip()
    if len(preview) > max_len:
        preview = preview[:max_len] + "…"
    return escape_html(preview)


def _get_local_model(config: WhisperConfig) -> Any:
    download_root = local_whisper_download_root()
    key = (config.model, config.local_device, config.local_compute_type, download_root)
    if key not in _LOCAL_MODEL_CACHE:
        from faster_whisper import WhisperModel

        _LOCAL_MODEL_CACHE[key] = WhisperModel(
            config.model,
            device=config.local_device,
            compute_type=config.local_compute_type,
            download_root=download_root,
            local_files_only=False,
        )
    return _LOCAL_MODEL_CACHE[key]


def warm_local_whisper_model(*, profile: str | None = None) -> bool:
    """Download and load local faster-whisper weights when local backend is active."""
    from config import settings

    if not settings.whisper_auto_download or not settings.telegram_voice_enabled:
        return False
    if not faster_whisper_available():
        return False
    try:
        config = resolve_whisper_config(profile=profile)
    except RuntimeError:
        return False
    if config.backend != "local":
        return False
    _get_local_model(config)
    return True


async def warm_local_whisper_model_async(*, profile: str | None = None) -> None:
    """Background-friendly wrapper for :func:`warm_local_whisper_model`."""
    from config import settings

    model = (settings.whisper_local_model or "base").strip()
    root = local_whisper_download_root()
    print(f"Whisper: downloading local model '{model}' to {root} …", flush=True)
    try:
        if await asyncio.to_thread(warm_local_whisper_model, profile=profile):
            print(f"Whisper: local model '{model}' ready", flush=True)
    except Exception as exc:
        print(f"Whisper: model download failed: {exc}", flush=True)


def _transcribe_local_sync(audio_path: str, config: WhisperConfig) -> str:
    model = _get_local_model(config)
    segments, _info = model.transcribe(
        audio_path,
        language=config.language,
        vad_filter=True,
    )
    return " ".join(segment.text.strip() for segment in segments).strip()


class VoiceTranscriber:
    """Transcribes audio via local faster-whisper or OpenAI-compatible HTTP API."""

    def __init__(self, config: WhisperConfig) -> None:
        self._config = config

    async def transcribe(self, audio_path: str, *, suffix: str = ".ogg") -> str:
        if self._config.backend == "local":
            return await asyncio.to_thread(_transcribe_local_sync, audio_path, self._config)

        audio_bytes = Path(audio_path).read_bytes()
        content_type = "audio/ogg" if suffix in {".ogg", ".oga"} else "application/octet-stream"
        filename = f"voice{suffix}"

        url = f"{self._config.base_url}/v1/audio/transcriptions"
        data = aiohttp.FormData()
        data.add_field("file", audio_bytes, filename=filename, content_type=content_type)
        data.add_field("model", self._config.model)
        if self._config.language:
            data.add_field("language", self._config.language)

        headers = {"Authorization": f"Bearer {self._config.api_key}"}

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                data=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                body = await resp.text()
                if resp.status != 200:
                    hint = ""
                    if self._config.backend == "litellm" and "Invalid model name" in body:
                        hint = (
                            " Add a whisper model to LiteLLM config "
                            f"(model_name matching '{self._config.model}', mode: audio_transcription)."
                        )
                    raise RuntimeError(f"Whisper API error {resp.status}: {body[:300]}{hint}")
                import json

                result = json.loads(body)
                return str(result.get("text", "")).strip()


async def download_telegram_file(bot: Any, file_id: str, *, suffix: str) -> str:
    """Download a Telegram file to a temporary path."""
    file_info = await bot.get_file(file_id)
    if not file_info.file_path:
        raise RuntimeError("Could not get file path from Telegram")

    resolved_suffix = suffix_for_audio(file_path=file_info.file_path) if suffix == ".ogg" else suffix
    fd, tmp_path = tempfile.mkstemp(suffix=resolved_suffix)
    os.close(fd)
    await bot.download_file(file_info.file_path, destination=tmp_path)
    return tmp_path


async def process_voice_message(
    bot: Any,
    file_id: str,
    *,
    suffix: str = ".ogg",
    config: WhisperConfig | None = None,
    profile: str | None = None,
) -> str:
    """Download and transcribe a Telegram voice/audio attachment."""
    whisper = config or resolve_whisper_config(profile=profile)
    tmp_path = ""
    try:
        tmp_path = await download_telegram_file(bot, file_id, suffix=suffix)
        transcriber = VoiceTranscriber(whisper)
        return await transcriber.transcribe(tmp_path, suffix=suffix_for_audio(file_path=tmp_path))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass