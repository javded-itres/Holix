"""Unit tests for Hermes multimodal content parsing."""

from __future__ import annotations

import pytest
from api.services.content_parts import (
    UnsupportedContentTypeError,
    minimal_png_data_url,
    parse_content_parts,
    parse_responses_input,
)


def test_parse_text_content() -> None:
    parsed = parse_content_parts("hello")
    assert parsed.text == "hello"
    assert parsed.image_urls == []


def test_parse_multimodal_content() -> None:
    parsed = parse_content_parts(
        [
            {"type": "text", "text": "What is this?"},
            {"type": "image_url", "image_url": {"url": minimal_png_data_url()}},
        ]
    )
    assert parsed.text == "What is this?"
    assert len(parsed.image_urls) == 1


def test_reject_file_upload() -> None:
    with pytest.raises(UnsupportedContentTypeError):
        parse_content_parts([{"type": "file", "file_id": "file-1"}])


@pytest.mark.asyncio
async def test_enrich_vision_uses_registered_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    from api.services.content_parts import ParsedUserInput, enrich_with_vision_descriptions
    from core.plugins.hooks import vision_hooks

    async def fake(url: str, *, profile: str) -> str:
        return f"{profile} saw {url[-4:]}"

    monkeypatch.setattr(vision_hooks, "describe_image_from_url", fake)
    text = await enrich_with_vision_descriptions(
        ParsedUserInput(text="look", image_urls=[minimal_png_data_url()]),
        profile="default",
    )
    assert text.startswith("look")
    assert "[Image 1]" in text
    assert "default saw" in text


@pytest.mark.asyncio
async def test_enrich_vision_without_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    from api.services.content_parts import ParsedUserInput, enrich_with_vision_descriptions
    from core.plugins.hooks import vision_hooks

    monkeypatch.setattr(vision_hooks, "describe_image_from_url", None)
    text = await enrich_with_vision_descriptions(
        ParsedUserInput(text="", image_urls=[minimal_png_data_url()]),
        profile="default",
    )
    assert "vision unavailable" in text


def test_parse_responses_input_image() -> None:
    parsed = parse_responses_input(
        [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Describe"},
                    {"type": "input_image", "image_url": minimal_png_data_url()},
                ],
            }
        ]
    )
    assert parsed.text == "Describe"
    assert len(parsed.image_urls) == 1
