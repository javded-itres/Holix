"""Load media provider settings (extension YAML + env)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Any


def _env(key: str, default: str = "") -> str:
    return (os.environ.get(key) or default).strip()


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _dig(data: Any, path: str) -> Any:
    cur = data
    for part in (path or "").split("."):
        if not part:
            continue
        if isinstance(cur, list) and part.isdigit():
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


@dataclass(frozen=True, slots=True)
class MediaProvider:
    id: str
    kind: str  # image | video
    type: str  # openai_images | openai_videos | http_json
    base_url: str
    api_key_env: str
    model: str
    size: str = "1024x1024"
    note: str = ""
    accepts_reference: bool | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def api_key(self) -> str:
        if self.api_key_env:
            val = _env(self.api_key_env)
            if val:
                return val
        extra_key = str(self.extra.get("api_key") or "").strip()
        if extra_key:
            return extra_key
        if self.type.strip().lower() in {"litellm", "litellm_images", "litellm_videos"}:
            return _env("LITELLM_API_KEY") or _env("MIKROLLM_API_KEY") or _env("OPENAI_API_KEY")
        return ""

    @property
    def is_usable(self) -> bool:
        return bool(self.resolved_base_url and self.api_key)

    @property
    def resolved_base_url(self) -> str:
        base = (self.base_url or "").strip()
        if not base and self.type.strip().lower() in {
            "litellm",
            "litellm_images",
            "litellm_videos",
        }:
            base = _env("LITELLM_API_BASE") or _profile_litellm_base()
        return _norm_v1(base)


@dataclass(frozen=True, slots=True)
class MediaConfig:
    enabled: bool
    auto_send: bool
    output_subdir: str
    image_providers: tuple[MediaProvider, ...]
    video_providers: tuple[MediaProvider, ...]

    @property
    def ready(self) -> bool:
        """True only when generation is enabled and a provider can actually be called."""
        if not self.enabled:
            return False
        return any(p.is_usable for p in (*self.image_providers, *self.video_providers))

    def provider(self, kind: str, provider_id: str | None = None) -> MediaProvider | None:
        pool = self.image_providers if kind == "image" else self.video_providers
        if not pool:
            return None
        if provider_id:
            wanted = provider_id.strip().lower()
            for item in pool:
                if item.id.lower() == wanted:
                    return item
            return None
        return pool[0]


def _norm_v1(base: str) -> str:
    url = (base or "").strip().rstrip("/")
    if not url:
        return ""
    if url.endswith("/v1"):
        return url
    return url + "/v1"


def _profile_litellm_base() -> str:
    try:
        from holix_media.profile_files import litellm_base_url

        return litellm_base_url()
    except Exception:
        return ""


def _as_list(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    return []


def _parse_provider(raw: dict[str, Any], *, kind: str) -> MediaProvider | None:
    pid = str(raw.get("id") or "").strip()
    ptype = str(raw.get("type") or "").strip()
    if not pid or not ptype:
        return None
    extra = dict(raw.get("extra") or {})
    for key in ("path", "method", "json_body", "url_json_path", "b64_json_path", "poll_path"):
        if key in raw and key not in extra:
            extra[key] = raw[key]
    return MediaProvider(
        id=pid,
        kind=kind,
        type=ptype,
        base_url=str(raw.get("base_url") or "").rstrip("/"),
        api_key_env=str(raw.get("api_key_env") or "").strip(),
        model=str(raw.get("model") or "").strip(),
        size=str(raw.get("size") or "1024x1024"),
        note=str(raw.get("note") or raw.get("description") or "").strip(),
        accepts_reference=_parse_accepts_reference(raw),
        extra=extra,
    )


def _parse_accepts_reference(raw: dict[str, Any]) -> bool | None:
    if "accepts_reference" not in raw:
        return None
    flag = raw.get("accepts_reference")
    if flag is None or (isinstance(flag, str) and not flag.strip()):
        return None
    if isinstance(flag, str):
        return flag.strip().lower() in {"1", "true", "yes", "on", "reference"}
    return bool(flag)


def _env_image_provider() -> MediaProvider | None:
    ptype = _env("HOLIX_MEDIA_IMAGE_TYPE")
    model = _env("HOLIX_MEDIA_IMAGE_MODEL")
    base = _env("HOLIX_MEDIA_IMAGE_BASE_URL")
    key_env = _env("HOLIX_MEDIA_IMAGE_API_KEY_ENV") or "OPENAI_API_KEY"
    if not ptype and not model and not base:
        return None
    return MediaProvider(
        id=_env("HOLIX_MEDIA_IMAGE_PROVIDER") or "env_image",
        kind="image",
        type=ptype or "openai_images",
        base_url=(base or "https://api.openai.com/v1").rstrip("/"),
        api_key_env=key_env,
        model=model or "dall-e-3",
        size=_env("HOLIX_MEDIA_IMAGE_SIZE") or "1024x1024",
    )


def _env_video_provider() -> MediaProvider | None:
    ptype = _env("HOLIX_MEDIA_VIDEO_TYPE")
    model = _env("HOLIX_MEDIA_VIDEO_MODEL")
    base = _env("HOLIX_MEDIA_VIDEO_BASE_URL")
    key_env = _env("HOLIX_MEDIA_VIDEO_API_KEY_ENV") or "OPENAI_API_KEY"
    if not ptype and not model and not base:
        return None
    return MediaProvider(
        id=_env("HOLIX_MEDIA_VIDEO_PROVIDER") or "env_video",
        kind="video",
        type=ptype or "openai_videos",
        base_url=(base or "https://api.openai.com/v1").rstrip("/"),
        api_key_env=key_env,
        model=model or "sora-2",
    )


def load_media_config(settings: dict[str, Any] | None = None) -> MediaConfig:
    raw = dict(settings or {})
    images = [_parse_provider(x, kind="image") for x in _as_list(raw.get("image_providers"))]
    videos = [_parse_provider(x, kind="video") for x in _as_list(raw.get("video_providers"))]
    env_img = _env_image_provider()
    env_vid = _env_video_provider()
    if env_img:
        images = [env_img, *[p for p in images if p and p.id != env_img.id]]
    if env_vid:
        videos = [env_vid, *[p for p in videos if p and p.id != env_vid.id]]
    images = [_with_resolved_proxy(p) for p in images if p]
    videos = [_with_resolved_proxy(p) for p in videos if p]
    return MediaConfig(
        enabled=_env_bool("HOLIX_MEDIA_ENABLED", bool(raw.get("enabled", True))),
        auto_send=_env_bool("HOLIX_MEDIA_AUTO_SEND", bool(raw.get("auto_send", True))),
        output_subdir=str(raw.get("output_subdir") or "media").strip() or "media",
        image_providers=tuple(p for p in images if p is not None),
        video_providers=tuple(p for p in videos if p is not None),
    )


def _with_resolved_proxy(p: MediaProvider) -> MediaProvider:
    if p.type.strip().lower() not in {"litellm", "litellm_images", "litellm_videos"}:
        return p
    base = p.resolved_base_url
    key_env = p.api_key_env or "LITELLM_API_KEY"
    model = p.model
    if not model:
        model = "sora-2" if p.kind == "video" else "dall-e-3"
    return replace(p, base_url=base, api_key_env=key_env, model=model)


# used by http_json provider
json_path = _dig
