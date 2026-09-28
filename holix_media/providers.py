"""Pluggable media backends: OpenAI-compatible images/videos and generic JSON HTTP."""

from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from holix_media.config import MediaProvider, json_path
from holix_media.http import HttpTransport, HttpxTransport
from holix_media.refs import ReferenceImage, user_content


@dataclass(frozen=True, slots=True)
class MediaBlob:
    data: bytes
    mime: str
    filename: str
    source_url: str | None = None


class MediaProviderError(RuntimeError):
    pass


def _auth_headers(provider: MediaProvider) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    key = provider.api_key
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _join(base: str, path: str) -> str:
    root = (base or "").rstrip("/") + "/"
    rel = (path or "").lstrip("/")
    return urljoin(root, rel)


def _fill_template(value: Any, mapping: dict[str, str]) -> Any:
    if isinstance(value, str):
        out = value
        for key, val in mapping.items():
            out = out.replace("{{" + key + "}}", val)
        return out
    if isinstance(value, dict):
        return {k: _fill_template(v, mapping) for k, v in value.items()}
    if isinstance(value, list):
        return [_fill_template(v, mapping) for v in value]
    return value


async def generate_image(
    provider: MediaProvider,
    prompt: str,
    *,
    http: HttpTransport | None = None,
    size: str | None = None,
    references: list[ReferenceImage] | None = None,
) -> MediaBlob:
    transport = http or HttpxTransport()
    kind = provider.type.strip().lower()
    refs = list(references or [])
    if kind in {"openai_images", "openai", "dalle", "litellm", "litellm_images"}:
        return await _openai_images(provider, prompt, transport, size=size, references=refs)
    if kind in {"http_json", "http"}:
        return await _http_json(provider, prompt, transport, kind="image", references=refs)
    raise MediaProviderError(f"Unknown image provider type: {provider.type}")


async def generate_video(
    provider: MediaProvider,
    prompt: str,
    *,
    http: HttpTransport | None = None,
    duration_s: int | None = None,
    references: list[ReferenceImage] | None = None,
) -> MediaBlob:
    transport = http or HttpxTransport()
    kind = provider.type.strip().lower()
    refs = list(references or [])
    if kind in {"openai_videos", "openai", "sora", "litellm", "litellm_videos"}:
        return await _openai_videos(
            provider, prompt, transport, duration_s=duration_s, references=refs
        )
    if kind in {"http_json", "http"}:
        return await _http_json(provider, prompt, transport, kind="video", references=refs)
    raise MediaProviderError(f"Unknown video provider type: {provider.type}")


async def _openai_images(
    provider: MediaProvider,
    prompt: str,
    http: HttpTransport,
    *,
    size: str | None,
    references: list[ReferenceImage] | None = None,
) -> MediaBlob:
    if not provider.api_key:
        raise MediaProviderError(f"API key missing ({provider.api_key_env or 'api_key'})")
    base = provider.resolved_base_url or provider.base_url
    if not base:
        raise MediaProviderError(
            "base_url is empty (set LITELLM_API_BASE or image provider base_url)"
        )
    url = _join(base, "/images/generations")
    chosen_size = size or provider.size or "1024x1024"
    body: dict[str, Any] = {
        "model": provider.model or "dall-e-3",
        "prompt": prompt,
        "n": 1,
        "size": chosen_size,
    }
    refs = list(references or [])
    if refs:
        _attach_image_refs(body, prompt, refs, size=chosen_size)
    # DALL·E accepts b64; LiteLLM / gpt-image / Grok often reject response_format.
    ptype = provider.type.strip().lower()
    if ptype not in {"litellm", "litellm_images"} and "dall-e" in (provider.model or "").lower():
        body["response_format"] = "b64_json"
    data = await http.post_json(url, headers=_auth_headers(provider), json=body, timeout=180.0)
    items = data.get("data")
    if not isinstance(items, list) or not items:
        raise MediaProviderError(f"No image in response: {json.dumps(data)[:400]}")
    item = items[0] if isinstance(items[0], dict) else {}
    b64 = item.get("b64_json") or item.get("b64")
    if b64:
        raw = base64.b64decode(str(b64))
        return MediaBlob(raw, "image/png", _filename("png"), source_url=None)
    remote = item.get("url")
    if not remote:
        raise MediaProviderError("Image response has neither b64_json nor url")
    raw, mime = await http.get_bytes(str(remote), timeout=180.0)
    ext = "jpg" if "jpeg" in mime else "png" if "png" in mime else "webp"
    return MediaBlob(raw, mime or "image/png", _filename(ext), source_url=str(remote))


async def _openai_videos(
    provider: MediaProvider,
    prompt: str,
    http: HttpTransport,
    *,
    duration_s: int | None,
    references: list[ReferenceImage] | None = None,
) -> MediaBlob:
    if not provider.api_key:
        raise MediaProviderError(f"API key missing ({provider.api_key_env or 'api_key'})")
    base = provider.resolved_base_url or provider.base_url
    if not base:
        raise MediaProviderError(
            "base_url is empty (set LITELLM_API_BASE or video provider base_url)"
        )
    url = _join(base, str(provider.extra.get("path") or "/videos"))
    body: dict[str, Any] = {
        "model": provider.model or "sora-2",
        "prompt": prompt,
    }
    if duration_s:
        # OpenAI Videos and OpenComfy expect a string ("6"), not a JSON number.
        body["seconds"] = str(int(duration_s))
    refs = list(references or [])
    if refs:
        _attach_video_refs(body, prompt, refs)
    headers = _auth_headers(provider)
    data = await http.post_json(url, headers=headers, json=body, timeout=180.0)
    blob = await _blob_from_payload(data, http, headers=headers, kind="video")
    if blob is not None:
        return blob
    job_id = str(data.get("id") or data.get("generation_id") or "").strip()
    if not job_id:
        raise MediaProviderError(f"Video job id missing: {json.dumps(data)[:400]}")
    _raise_if_video_failed(data)
    status_url = _video_poll_url(
        base,
        job_id=job_id,
        model=provider.model,
        polling_url=str(data.get("polling_url") or ""),
        poll_path=str(provider.extra.get("poll_path") or "/videos/{id}"),
    )
    last: dict[str, Any] = data
    # OpenRouter / Seedance jobs often take 4–10 minutes.
    for _ in range(120):
        await asyncio.sleep(5.0)
        status = await http.get_json(status_url, headers=headers, timeout=60.0)
        last = status if isinstance(status, dict) else {"raw": status}
        _raise_if_video_failed(last)
        blob = await _blob_from_payload(last, http, headers=headers, kind="video")
        if blob is not None:
            return blob
        state = str(last.get("status") or "").lower()
        if state in {"completed", "succeeded", "success"}:
            content_url = _join(base, f"/videos/{job_id}/content")
            try:
                raw, mime = await http.get_bytes(content_url, headers=headers, timeout=180.0)
            except Exception:
                raw, mime = b"", ""
            if raw and "json" not in (mime or "") and len(raw) > 64:
                return MediaBlob(raw, mime or "video/mp4", _filename("mp4"), source_url=content_url)
            raise MediaProviderError(
                f"Video job completed but no file URL: {json.dumps(last)[:400]}"
            )
    raise MediaProviderError(f"Video generation timed out: {json.dumps(last)[:400]}")


async def _http_json(
    provider: MediaProvider,
    prompt: str,
    http: HttpTransport,
    *,
    kind: str,
    references: list[ReferenceImage] | None = None,
) -> MediaBlob:
    if provider.api_key_env and not provider.api_key:
        raise MediaProviderError(f"API key missing ({provider.api_key_env})")
    refs = list(references or [])
    mapping = {
        "prompt": prompt,
        "model": provider.model,
        "size": provider.size,
        "kind": kind,
        "image_b64": refs[0].b64 if refs else "",
        "image_data_url": refs[0].data_url if refs else "",
    }
    path = str(provider.extra.get("path") or "/")
    url = _join(provider.resolved_base_url or provider.base_url, path)
    body = _fill_template(provider.extra.get("json_body") or {"prompt": "{{prompt}}"}, mapping)
    if not isinstance(body, dict):
        raise MediaProviderError("http_json json_body must be an object")
    data = await http.post_json(url, headers=_auth_headers(provider), json=body, timeout=180.0)
    b64_path = str(provider.extra.get("b64_json_path") or "")
    url_path = str(provider.extra.get("url_json_path") or "")
    if b64_path:
        b64 = json_path(data, b64_path)
        if b64:
            raw = base64.b64decode(str(b64))
            ext = "mp4" if kind == "video" else "png"
            mime = "video/mp4" if kind == "video" else "image/png"
            return MediaBlob(raw, mime, _filename(ext), source_url=None)
    if url_path:
        remote = json_path(data, url_path)
        if remote:
            raw, mime = await http.get_bytes(str(remote), timeout=180.0)
            ext = "mp4" if kind == "video" else "png"
            return MediaBlob(
                raw,
                mime or ("video/mp4" if kind == "video" else "image/png"),
                _filename(ext),
                source_url=str(remote),
            )
    blob = await _blob_from_payload(data, http, headers=_auth_headers(provider), kind=kind)
    if blob is None:
        raise MediaProviderError(f"Could not parse media from JSON: {json.dumps(data)[:400]}")
    return blob


async def _blob_from_payload(
    data: dict[str, Any],
    http: HttpTransport,
    *,
    headers: dict[str, str],
    kind: str,
) -> MediaBlob | None:
    b64 = json_path(data, "b64_json") or json_path(data, "data.0.b64_json")
    if b64:
        raw = base64.b64decode(str(b64))
        ext = "mp4" if kind == "video" else "png"
        mime = "video/mp4" if kind == "video" else "image/png"
        return MediaBlob(raw, mime, _filename(ext), source_url=None)
    remote = (
        json_path(data, "url")
        or json_path(data, "data.0.url")
        or json_path(data, "output.url")
        or json_path(data, "output.video_url")
        or json_path(data, "video_url")
        or json_path(data, "image_url")
        or json_path(data, "assets.video")
        or json_path(data, "result.url")
    )
    if remote:
        raw, mime = await http.get_bytes(str(remote), headers=headers, timeout=180.0)
        ext = "mp4" if kind == "video" else "png"
        return MediaBlob(
            raw,
            mime or ("video/mp4" if kind == "video" else "image/png"),
            _filename(ext),
            source_url=str(remote),
        )
    return None


def _raise_if_video_failed(status: dict[str, Any]) -> None:
    state = str(status.get("status") or "").lower()
    if state not in {"failed", "error", "cancelled"}:
        return
    err = status.get("error") or json.dumps(status, ensure_ascii=False)[:400]
    raise MediaProviderError(f"Video job failed: {err}")


def _video_poll_url(
    base: str,
    *,
    job_id: str,
    model: str,
    polling_url: str,
    poll_path: str,
) -> str:
    """Prefer gateway /videos/{id}?model=… even if OpenRouter returned polling_url."""
    path = (poll_path or "/videos/{id}").replace("{id}", job_id)
    raw = (polling_url or "").strip()
    if raw:
        parsed = urlparse(raw)
        if parsed.path:
            path = parsed.path
            if path.startswith("/api/v1/"):
                path = path[len("/api") :]
    url = _join(base, path)
    query = dict(parse_qsl(urlparse(url).query))
    if model and "model" not in query:
        query["model"] = model
    if not query:
        return url
    parts = urlparse(url)
    return urlunparse(parts._replace(query=urlencode(query)))


def _attach_image_refs(
    body: dict[str, Any],
    prompt: str,
    refs: list[ReferenceImage],
    *,
    size: str,
) -> None:
    """MikroLLM/OpenRouter: messages + image_url. OpenAI-style: image / images."""
    body["messages"] = [
        {"role": "user", "content": user_content(prompt, refs, size=size)},
    ]
    body["image"] = refs[0].data_url
    if len(refs) > 1:
        body["images"] = [r.data_url for r in refs]


def _attach_video_refs(body: dict[str, Any], prompt: str, refs: list[ReferenceImage]) -> None:
    """Sora input_reference, OpenRouter image / images, plus chat messages."""
    urls = [r.data_url for r in refs]
    body["input_reference"] = urls[0]
    body["image"] = urls[0]
    if len(urls) > 1:
        body["images"] = urls
    body["messages"] = [
        {"role": "user", "content": user_content(prompt, refs)},
    ]


def _filename(ext: str) -> str:
    import time

    stamp = time.strftime("%Y%m%d-%H%M%S")
    return f"{stamp}.{ext}"
