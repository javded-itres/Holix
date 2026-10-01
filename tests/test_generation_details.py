"""Generation details stay behind a button instead of under the file."""

from __future__ import annotations

import json
from pathlib import Path

from integrations.messenger.generation_details import (
    button_label,
    format_generation_details,
    lookup_generation_details,
    register_generation_details,
    strip_generation_technical_reply,
)


def test_format_details_hides_paths() -> None:
    text = format_generation_details(
        {
            "kind": "image",
            "provider": "mikrollm",
            "model": "image-z-image-turbo",
            "size": "1024x1024",
            "seed": 7,
            "prompt": "a red door",
            "path": "/var/lib/holix/secret.png",
        },
        locale="ru",
    )
    assert "Модель: image-z-image-turbo" in text
    assert "Провайдер: mikrollm" in text
    assert "Seed: 7" in text
    assert "a red door" in text
    assert "/var/lib" not in text
    assert button_label("ru") == "Техническая информация"
    assert button_label("en") == "Generation details"


def test_register_and_lookup_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    image = tmp_path / "pic.png"
    image.write_bytes(b"png")
    meta = {
        "kind": "image",
        "model": "image-z-image-turbo",
        "provider": "mikrollm",
        "prompt": "a red door",
        "seed": 7,
        "size": "1024x1024",
    }
    (tmp_path / "pic.png.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    token = register_generation_details(image, locale="ru")
    assert token
    loaded = lookup_generation_details(token or "")
    assert loaded is not None
    assert "a red door" in loaded
    assert lookup_generation_details("../etc") is None


def test_media_task_label_uses_profile_language(monkeypatch, tmp_path: Path) -> None:
    from core.i18n.locale import LocaleStore
    from integrations.messenger.generation_details import media_task_label

    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    assert media_task_label("image", "admin") == "Генерация изображения"
    assert media_task_label("video", "admin") == "Генерация видео"
    LocaleStore("admin").set("en")
    assert media_task_label("image", "admin") == "Image generation"


def test_strip_drops_the_delivery_note() -> None:
    raw = (
        "Saved image: /tmp/pic.png\n"
        "Delivered to the chat. Do not send another message about the file."
    )
    assert strip_generation_technical_reply(raw) == ""


def test_strip_generation_technical_reply_keeps_a_short_sentence() -> None:
    raw = (
        "Готово.\n"
        "Saved image: /tmp/pic.png\n"
        "provider=mikrollm type=openai_images model=image-z-image-turbo bytes=4\n"
        "seed=7\n"
        "size=1024x1024\n"
        "Open: file:///tmp/pic.png\n"
    )
    assert strip_generation_technical_reply(raw) == "Готово."
