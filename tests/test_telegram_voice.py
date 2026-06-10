"""Telegram voice transcription helpers."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from integrations.telegram.voice_handler import (
    VoiceTranscriber,
    WhisperConfig,
    format_transcription_preview,
    local_whisper_download_root,
    process_voice_message,
    resolve_whisper_config,
    suffix_for_audio,
    warm_local_whisper_model,
)


def test_suffix_for_audio() -> None:
    assert suffix_for_audio(mime_type="audio/ogg") == ".ogg"
    assert suffix_for_audio(mime_type="audio/mpeg") == ".mp3"
    assert suffix_for_audio(file_path="voices/note.M4A") == ".m4a"
    assert suffix_for_audio() == ".ogg"


def test_format_transcription_preview_escapes_html() -> None:
    text = 'Say <b>hello</b> & "test"'
    out = format_transcription_preview(text)
    assert "<b>" not in out
    assert "&amp;" in out


def test_resolve_whisper_config_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    from config import settings

    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "whisper_api_key", "")
    monkeypatch.setattr(settings, "whisper_base_url", "")
    monkeypatch.setattr(settings, "whisper_use_profile_litellm", False)
    monkeypatch.setattr(settings, "whisper_backend", "api")
    monkeypatch.setattr(
        "integrations.telegram.voice_handler.faster_whisper_available",
        lambda: False,
    )
    with pytest.raises(RuntimeError, match="Whisper not configured"):
        resolve_whisper_config()


def test_resolve_whisper_config_local(monkeypatch: pytest.MonkeyPatch) -> None:
    from config import settings

    monkeypatch.setattr(settings, "whisper_backend", "local")
    monkeypatch.setattr(settings, "whisper_local_model", "small")
    monkeypatch.setattr(settings, "whisper_local_device", "cpu")
    monkeypatch.setattr(settings, "whisper_local_compute_type", "int8")
    monkeypatch.setattr(settings, "telegram_voice_language", "ru")
    monkeypatch.setattr(
        "integrations.telegram.voice_handler.faster_whisper_available",
        lambda: True,
    )

    cfg = resolve_whisper_config()
    assert cfg.backend == "local"
    assert cfg.model == "small"
    assert cfg.language == "ru"
    assert cfg.api_key == ""


def test_local_whisper_download_root_default(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from config import settings

    monkeypatch.setattr(settings, "whisper_local_download_root", "")
    monkeypatch.setattr(
        "integrations.telegram.voice_handler.resolve_helix_home",
        lambda: tmp_path / "helix",
    )

    root = local_whisper_download_root()
    assert root == str(tmp_path / "helix" / "models" / "whisper")
    assert (tmp_path / "helix" / "models" / "whisper").is_dir()


def test_warm_local_whisper_model_downloads_when_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config import settings

    monkeypatch.setattr(settings, "whisper_auto_download", True)
    monkeypatch.setattr(settings, "telegram_voice_enabled", True)
    monkeypatch.setattr(settings, "whisper_backend", "local")
    monkeypatch.setattr(settings, "whisper_local_model", "tiny")
    monkeypatch.setattr(
        "integrations.telegram.voice_handler.faster_whisper_available",
        lambda: True,
    )

    called: list[str] = []

    def fake_get_local_model(config: WhisperConfig) -> object:
        called.append(config.model)
        return object()

    monkeypatch.setattr(
        "integrations.telegram.voice_handler._get_local_model",
        fake_get_local_model,
    )

    assert warm_local_whisper_model() is True
    assert called == ["tiny"]


def test_warm_local_whisper_model_skips_api_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    from config import settings

    monkeypatch.setattr(settings, "whisper_auto_download", True)
    monkeypatch.setattr(settings, "telegram_voice_enabled", True)
    monkeypatch.setattr(settings, "whisper_backend", "api")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(
        "integrations.telegram.voice_handler.faster_whisper_available",
        lambda: True,
    )
    def _fail(_config: WhisperConfig) -> object:
        raise AssertionError("should not load local model")

    monkeypatch.setattr("integrations.telegram.voice_handler._get_local_model", _fail)

    assert warm_local_whisper_model() is False


def test_resolve_whisper_config_local_requires_package(monkeypatch: pytest.MonkeyPatch) -> None:
    from config import settings

    monkeypatch.setattr(settings, "whisper_backend", "local")
    monkeypatch.setattr(
        "integrations.telegram.voice_handler.faster_whisper_available",
        lambda: False,
    )
    with pytest.raises(RuntimeError, match="faster-whisper"):
        resolve_whisper_config()


def test_resolve_whisper_config_litellm_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    from config import settings

    monkeypatch.setattr(settings, "whisper_backend", "api")
    monkeypatch.setattr(settings, "whisper_api_key", "sk-litellm")
    monkeypatch.setattr(settings, "whisper_base_url", "http://192.168.1.1:4000/v1")
    monkeypatch.setattr(settings, "whisper_model", "whisper")
    monkeypatch.setattr(settings, "telegram_voice_language", "")

    cfg = resolve_whisper_config()
    assert cfg.api_key == "sk-litellm"
    assert cfg.base_url == "http://192.168.1.1:4000"
    assert cfg.model == "whisper"
    assert cfg.backend == "litellm"


def test_resolve_whisper_config_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from config import settings

    monkeypatch.setattr(settings, "whisper_backend", "api")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "openai_base_url", "https://api.openai.com/v1")
    monkeypatch.setattr(settings, "whisper_model", "whisper-1")
    monkeypatch.setattr(settings, "telegram_voice_language", "ru")

    cfg = resolve_whisper_config()
    assert cfg.api_key == "sk-test"
    assert cfg.base_url == "https://api.openai.com"
    assert cfg.model == "whisper-1"
    assert cfg.language == "ru"


@pytest.mark.asyncio
async def test_voice_transcriber_local_backend(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    audio = tmp_path / "voice.ogg"
    audio.write_bytes(b"fake-audio")

    class FakeSegment:
        def __init__(self, text: str) -> None:
            self.text = text

    def fake_transcribe_sync(path: str, config: WhisperConfig) -> str:
        assert path == str(audio)
        assert config.backend == "local"
        return "локальный текст"

    monkeypatch.setattr(
        "integrations.telegram.voice_handler._transcribe_local_sync",
        fake_transcribe_sync,
    )

    cfg = WhisperConfig(
        api_key="",
        base_url="",
        model="base",
        backend="local",
    )
    transcriber = VoiceTranscriber(cfg)
    result = await transcriber.transcribe(str(audio), suffix=".ogg")
    assert result == "локальный текст"


@pytest.mark.asyncio
async def test_voice_transcriber_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    audio = tmp_path / "voice.ogg"
    audio.write_bytes(b"fake-audio")

    class FakeResponse:
        status = 200

        async def text(self) -> str:
            return json.dumps({"text": "Привет мир"})

    response = FakeResponse()

    class PostCtx:
        async def __aenter__(self):
            return response

        async def __aexit__(self, *args):
            return None

    session = MagicMock()
    session.post.return_value = PostCtx()

    class SessionCtx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr(
        "integrations.telegram.voice_handler.aiohttp.ClientSession",
        lambda *a, **k: SessionCtx(),
    )

    cfg = WhisperConfig(api_key="sk-test", base_url="https://api.openai.com", model="whisper-1")
    transcriber = VoiceTranscriber(cfg)
    result = await transcriber.transcribe(str(audio), suffix=".ogg")
    assert result == "Привет мир"


@pytest.mark.asyncio
async def test_process_voice_message_cleans_temp_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    audio = tmp_path / "voice.ogg"
    audio.write_bytes(b"fake-audio")

    bot = AsyncMock()
    bot.get_file.return_value = MagicMock(file_path="voice/file.ogg")

    async def _download(src, destination: str) -> None:
        with open(destination, "wb") as fh:
            fh.write(b"fake")

    bot.download_file = AsyncMock(side_effect=_download)

    cfg = WhisperConfig(api_key="sk-test", base_url="https://api.openai.com", model="whisper-1")

    async def fake_transcribe(self, audio_path: str, *, suffix: str = ".ogg") -> str:
        assert audio_path.endswith(".ogg")
        return "ok"

    monkeypatch.setattr(VoiceTranscriber, "transcribe", fake_transcribe)

    text = await process_voice_message(bot, "file-id", config=cfg)
    assert text == "ok"