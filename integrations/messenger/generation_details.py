"""Details button for a generated image or video in Telegram and MAX.

The file message stays free of model, seed, and prompt. Those stay behind
the button. The token is random and stored under HOLIX_HOME, not in the
callback payload.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

_TOKEN_RE = re.compile(r"^[0-9a-f]{16}$")
_TECH_LINE = re.compile(
    r"^(?:"
    r"Saved (?:image|video):.*"
    r"|Open:.*"
    r"|\[Open (?:image|video)\].*"
    r"|provider=.*"
    r"|seed=.*"
    r"|size=.*"
    r"|bytes=.*"
    r"|file://.*"
    r"|In TUI the link is already.*"
    r")$",
    re.IGNORECASE,
)


def details_dir() -> Path:
    home = os.environ.get("HOLIX_HOME", "").strip()
    if home:
        root = Path(home).expanduser()
    else:
        from core.platform_compat import resolve_holix_home

        root = resolve_holix_home()
    path = root / "media-details"
    path.mkdir(parents=True, exist_ok=True)
    return path


def button_label(locale: str | None) -> str:
    if (locale or "").lower().startswith("en"):
        return "Generation details"
    return "Техническая информация"


def format_generation_details(meta: dict[str, Any], *, locale: str | None) -> str:
    """User-facing generation card. No filesystem paths."""
    en = (locale or "").lower().startswith("en")
    labels = {
        "kind": ("Тип", "Kind"),
        "provider": ("Провайдер", "Provider"),
        "model": ("Модель", "Model"),
        "size": ("Размер", "Size"),
        "seed": ("Seed", "Seed"),
        "prompt": ("Промпт", "Prompt"),
    }

    def label(key: str) -> str:
        pair = labels[key]
        return pair[1] if en else pair[0]

    lines: list[str] = []
    kind = str(meta.get("kind") or "").strip()
    if kind:
        shown = {
            "image": "изображение" if not en else "image",
            "video": "видео" if not en else "video",
        }
        lines.append(f"{label('kind')}: {shown.get(kind, kind)}")
    provider = str(meta.get("provider") or "").strip()
    if provider:
        lines.append(f"{label('provider')}: {provider}")
    model = str(meta.get("model") or "").strip()
    if model:
        lines.append(f"{label('model')}: {model}")
    size = str(meta.get("size") or "").strip()
    if size:
        lines.append(f"{label('size')}: {size}")
    if meta.get("seed") is not None and str(meta.get("seed")).strip() != "":
        lines.append(f"{label('seed')}: {meta.get('seed')}")
    prompt = str(meta.get("prompt") or "").strip()
    if prompt:
        lines.append(f"{label('prompt')}:\n{prompt}")
    return "\n".join(lines).strip()


def register_generation_details(media_path: Path, *, locale: str | None) -> str | None:
    """Persist a details card for this file. Returns the callback token."""
    from holix_media.params import load_generation_meta

    meta = load_generation_meta(media_path)
    if not meta:
        return None
    text = format_generation_details(meta, locale=locale)
    if not text:
        return None
    token = uuid.uuid4().hex[:16]
    payload = {"text": text}
    (details_dir() / f"{token}.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    return token


def lookup_generation_details(token: str) -> str | None:
    if not _TOKEN_RE.fullmatch(token or ""):
        return None
    path = details_dir() / f"{token}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    text = str(data.get("text") or "").strip()
    return text or None


def _chat_locale() -> str:
    try:
        from core.tools.execution_context import get_profile_name

        from integrations.messenger.locale import messenger_locale

        profile = (get_profile_name() or "").strip()
        if profile:
            return messenger_locale(profile)
    except Exception:
        pass
    return "ru"


def generation_reply_markup(media_path: Path | None, *, platform: str) -> tuple[str | None, Any]:
    """Return (caption override, markup). Caption override None keeps the caller's caption."""
    if media_path is None:
        return None, None
    token = register_generation_details(media_path, locale=_chat_locale())
    if not token:
        return None, None
    label = button_label(_chat_locale())
    payload = f"mg:{token}"
    if platform == "max":
        keyboard = {
            "type": "inline_keyboard",
            "payload": {"buttons": [[{"type": "callback", "text": label, "payload": payload}]]},
        }
        return "", keyboard
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=payload)]]
    )
    return "", keyboard


def strip_generation_technical_reply(text: str) -> str:
    """Drop provider/seed/path lines the model copies after a generated file."""
    kept: list[str] = []
    for line in (text or "").splitlines():
        if _TECH_LINE.match(line.strip()):
            continue
        kept.append(line)
    return "\n".join(kept).strip()
