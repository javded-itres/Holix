"""Parse OpenAI/Hermes multimodal message content for gateway routes."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

_UNSUPPORTED_PART_TYPES = frozenset({"file", "input_file", "file_id"})
_IMAGE_URL_RE = re.compile(r"^data:(image/[^;]+);base64,", re.I)


@dataclass(slots=True)
class ParsedUserInput:
    text: str = ""
    image_urls: list[str] = field(default_factory=list)


class UnsupportedContentTypeError(ValueError):
    """Raised when the client sends unsupported file upload parts."""


def _is_http_image_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_data_image_url(url: str) -> bool:
    return bool(_IMAGE_URL_RE.match(url or ""))


def _extract_image_url(part: dict[str, Any]) -> str | None:
    if part.get("type") in {"image_url", "input_image"}:
        raw = part.get("image_url")
        if isinstance(raw, dict):
            url = str(raw.get("url", "")).strip()
        else:
            url = str(raw or "").strip()
        if url and (_is_http_image_url(url) or _is_data_image_url(url)):
            return url
        if url.startswith("data:"):
            raise UnsupportedContentTypeError(
                "unsupported_content_type: only image data URLs are supported"
            )
    return None


def _extract_text_part(part: dict[str, Any]) -> str:
    ptype = part.get("type")
    if ptype in {"text", "input_text"}:
        return str(part.get("text", ""))
    if ptype is None and "text" in part:
        return str(part.get("text", ""))
    return ""


def parse_content_parts(content: Any) -> ParsedUserInput:
    """Parse string or multipart user content into text and image URLs."""
    if content is None:
        return ParsedUserInput()
    if isinstance(content, str):
        return ParsedUserInput(text=content.strip())

    if not isinstance(content, list):
        raise UnsupportedContentTypeError("unsupported_content_type: invalid content")

    texts: list[str] = []
    images: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        ptype = str(part.get("type", ""))
        if ptype in _UNSUPPORTED_PART_TYPES:
            raise UnsupportedContentTypeError(
                f"unsupported_content_type: {ptype} uploads are not supported"
            )
        text = _extract_text_part(part)
        if text:
            texts.append(text)
        image = _extract_image_url(part)
        if image:
            images.append(image)
        elif ptype == "image_url" and not image:
            url = ""
            raw = part.get("image_url")
            if isinstance(raw, dict):
                url = str(raw.get("url", ""))
            if url.startswith("data:") and not _is_data_image_url(url):
                raise UnsupportedContentTypeError(
                    "unsupported_content_type: only image data URLs are supported"
                )

    return ParsedUserInput(text="\n".join(t for t in texts if t).strip(), image_urls=images)


def parse_responses_input(payload_input: str | list[dict[str, Any]]) -> ParsedUserInput:
    """Parse Responses API input (string or structured list)."""
    if isinstance(payload_input, str):
        return ParsedUserInput(text=payload_input.strip())

    texts: list[str] = []
    images: list[str] = []
    for item in payload_input:
        if not isinstance(item, dict):
            continue
        if item.get("type") in {"input_text", "text"}:
            texts.append(str(item.get("text", "")))
            continue
        if item.get("role") == "user":
            parsed = parse_content_parts(item.get("content", ""))
            texts.append(parsed.text)
            images.extend(parsed.image_urls)
            continue
        if item.get("type") in {"input_image", "image_url"}:
            image = _extract_image_url(item)
            if image:
                images.append(image)
    return ParsedUserInput(text="\n".join(t for t in texts if t).strip(), image_urls=images)


async def enrich_with_vision_descriptions(
    parsed: ParsedUserInput,
    *,
    profile: str,
) -> str:
    """Append vision descriptions for inline images (Hermes multimodal parity)."""
    if not parsed.image_urls:
        return parsed.text

    from integrations.telegram.file_handler import describe_image_from_url

    blocks = [parsed.text] if parsed.text else []
    for idx, url in enumerate(parsed.image_urls, start=1):
        try:
            description = await describe_image_from_url(url, profile=profile)
        except Exception as exc:
            description = f"(image {idx}: vision unavailable: {exc})"
        blocks.append(f"[Image {idx}]\n{description}")
    return "\n\n".join(blocks).strip()


def minimal_png_data_url() -> str:
    """1x1 PNG for tests."""
    b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    return f"data:image/png;base64,{b64}"


def decode_data_url_image(url: str) -> tuple[str, bytes]:
    match = _IMAGE_URL_RE.match(url)
    if not match:
        raise ValueError("Not an image data URL")
    mime = match.group(1)
    payload = url.split(",", 1)[1]
    return mime, base64.standard_b64decode(payload)