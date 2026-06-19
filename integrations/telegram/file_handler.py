"""Telegram photos and documents: save to profile, extract text, vision."""

from __future__ import annotations

import base64
import mimetypes
import os
import re
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from core.config_utils import resolve_env_refs

from config import settings

_IMAGE_MIMES = frozenset(
    {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
        "image/gif",
        "image/bmp",
        "image/heic",
        "image/heif",
    }
)
_TEXT_SUFFIXES = frozenset(
    {
        ".txt",
        ".md",
        ".markdown",
        ".csv",
        ".tsv",
        ".json",
        ".xml",
        ".html",
        ".htm",
        ".yaml",
        ".yml",
        ".py",
        ".js",
        ".ts",
        ".sql",
        ".log",
        ".rst",
        ".ini",
        ".cfg",
        ".env",
    }
)
_PLACEHOLDER_KEYS = frozenset({"", "ollama", "dummy", "sk-...", "your-api-key"})


@dataclass(slots=True)
class SavedTelegramFile:
    path: Path
    original_name: str
    mime_type: str
    kind: str
    size_bytes: int
    description: str = ""


@dataclass(slots=True)
class VisionConfig:
    model: str
    api_key: str
    base_url: str
    provider_metadata: dict[str, Any] | None = None


def _openai_base_url(url: str) -> str:
    base = (url or "").rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return base


def _valid_api_key(key: str) -> bool:
    return bool(key and key.strip() and key.strip() not in _PLACEHOLDER_KEYS)


def _provider_credentials(pdata: dict[str, Any]) -> tuple[str, str] | None:
    api_key = str(resolve_env_refs(pdata.get("api_key") or "")).strip()
    base_url = str(resolve_env_refs(pdata.get("base_url") or "")).strip()
    if _valid_api_key(api_key) and base_url:
        return api_key, _openai_base_url(base_url)
    return None


def _env_litellm_credentials() -> tuple[str, str] | None:
    api_key = str(os.environ.get("LITELLM_API_KEY") or "").strip()
    base_url = str(
        os.environ.get("LITELLM_API_BASE") or os.environ.get("LITELLM_HOST") or ""
    ).strip()
    if _valid_api_key(api_key) and base_url:
        return api_key, _openai_base_url(base_url)
    return None


def _settings_openai_credentials() -> tuple[str, str] | None:
    api_key = str(settings.openai_api_key or "").strip()
    base_url = str(settings.openai_base_url or "").strip()
    if _valid_api_key(api_key) and base_url:
        return api_key, _openai_base_url(base_url)
    return None


def _pick_model(*candidates: str) -> str:
    for raw in candidates:
        model = str(raw or "").strip()
        if model and model not in _PLACEHOLDER_KEYS:
            return model
    return ""


def resolve_vision_config(*, profile: str) -> VisionConfig:
    """Resolve vision model + API credentials (profile, env, OpenAI fallbacks)."""
    explicit_model = (settings.telegram_vision_model or "").strip()

    try:
        from cli.core import get_profile_manager

        config = get_profile_manager().load_profile(profile)
    except Exception:
        config = None

    api_key = ""
    base_url = ""
    metadata: dict[str, Any] | None = None
    model_candidates: list[str] = [explicit_model]

    if config is not None:
        providers = getattr(config, "providers", None) or {}
        agent_models = getattr(config, "agent_models", None) or {}
        main = agent_models.get("main") if isinstance(agent_models, dict) else {}
        if not isinstance(main, dict):
            main = {}

        provider_name = str(
            main.get("provider")
            or getattr(config, "default_provider", "")
            or ""
        ).strip()
        model_candidates.extend(
            [
                str(main.get("model") or ""),
                str(getattr(config, "model", "") or ""),
            ]
        )

        provider_blocks: list[tuple[str, dict[str, Any]]] = []
        if provider_name and isinstance(providers, dict):
            raw = providers.get(provider_name)
            if isinstance(raw, dict):
                provider_blocks.append((provider_name, raw))
        if isinstance(providers, dict):
            litellm = providers.get("litellm")
            if isinstance(litellm, dict) and ("litellm", litellm) not in provider_blocks:
                provider_blocks.append(("litellm", litellm))
            for name, raw in providers.items():
                if isinstance(raw, dict) and (name, raw) not in provider_blocks:
                    provider_blocks.append((name, raw))

        for _name, pdata in provider_blocks:
            creds = _provider_credentials(pdata)
            if creds and not api_key:
                api_key, base_url = creds
                metadata = pdata.get("metadata") if isinstance(pdata.get("metadata"), dict) else None
            model_candidates.append(str(pdata.get("default_model") or ""))

        if not api_key:
            top_key = str(resolve_env_refs(getattr(config, "api_key", ""))).strip()
            top_url = str(resolve_env_refs(getattr(config, "base_url", ""))).strip()
            if _valid_api_key(top_key) and top_url:
                api_key, base_url = top_key, _openai_base_url(top_url)

    if not api_key:
        env_creds = _env_litellm_credentials()
        if env_creds:
            api_key, base_url = env_creds

    if not api_key:
        openai_creds = _settings_openai_credentials()
        if openai_creds:
            api_key, base_url = openai_creds

    model = _pick_model(*model_candidates)
    if not model:
        raise RuntimeError(
            "Vision: не задана модель. Укажите HOLIX_TELEGRAM_VISION_MODEL "
            "или назначьте модель для main в holix models setup."
        )
    if not api_key or not base_url:
        raise RuntimeError(
            "Vision: не настроен API (ключ/URL). Проверьте ~/.holix/.env "
            "(LITELLM_API_KEY, LITELLM_API_BASE), holix models setup, "
            "или OPENAI_API_KEY."
        )

    return VisionConfig(
        model=model,
        api_key=api_key,
        base_url=base_url,
        provider_metadata=metadata,
    )


def profile_files_dir(
    profile: str,
    chat_id: int,
    *,
    bot_profile: str | None = None,
    telegram_user_id: int | None = None,
) -> Path:
    from core.env_loader import profile_dir_path

    from integrations.telegram.profile_auth import init_profile_for_telegram

    if bot_profile is not None and telegram_user_id is not None:
        init_profile_for_telegram(
            profile,
            bot_profile=bot_profile,
            telegram_user_id=telegram_user_id,
        )
    else:
        from cli.core import init_profile

        init_profile(profile, prompt_key=False)
    # Always store Telegram attachments under the named profile dir (never a shared data_dir).
    dest = profile_dir_path(profile) / "data" / "files" / "telegram" / str(chat_id)
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def _safe_filename(name: str) -> str:
    base = Path(name or "file").name
    base = re.sub(r"[^\w.\-()+ ]", "_", base, flags=re.UNICODE).strip("._ ")
    return base or "file"


def _unique_dest(dest_dir: Path, filename: str) -> Path:
    safe = _safe_filename(filename)
    candidate = dest_dir / safe
    if not candidate.exists():
        return candidate
    stem = Path(safe).stem
    suffix = Path(safe).suffix
    stamp = int(time.time())
    return dest_dir / f"{stem}_{stamp}{suffix}"


def _is_image(mime_type: str, filename: str) -> bool:
    mime = (mime_type or "").split(";")[0].strip().lower()
    if mime in _IMAGE_MIMES or mime.startswith("image/"):
        return True
    guessed, _ = mimetypes.guess_type(filename)
    return bool(guessed and guessed.startswith("image/"))


async def download_telegram_file_to_path(bot: Any, file_id: str, dest: Path) -> int:
    file_info = await bot.get_file(file_id)
    if not file_info.file_path:
        raise RuntimeError("Could not get file path from Telegram")
    dest.parent.mkdir(parents=True, exist_ok=True)
    await bot.download_file(file_info.file_path, destination=str(dest))
    return int(dest.stat().st_size)


def _read_text_file(path: Path, *, max_chars: int = 12000) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1251", "latin-1"):
        try:
            text = path.read_text(encoding=encoding)
            if len(text) > max_chars:
                return text[:max_chars] + f"\n\n... (обрезано, всего {len(text)} символов)"
            return text
        except UnicodeDecodeError:
            continue
    return ""


def _extract_pdf_text(path: Path, *, max_chars: int = 12000) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""

    try:
        reader = PdfReader(str(path))
        parts: list[str] = []
        for page in reader.pages[:40]:
            parts.append(page.extract_text() or "")
            if sum(len(p) for p in parts) >= max_chars:
                break
        text = "\n".join(parts).strip()
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n... (обрезано, всего символов больше {max_chars})"
        return text
    except Exception:
        return ""


def _extract_docx_text(path: Path, *, max_chars: int = 12000) -> str:
    try:
        with zipfile.ZipFile(path) as zf:
            xml_bytes = zf.read("word/document.xml")
        root = ElementTree.fromstring(xml_bytes)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        texts = [node.text for node in root.iterfind(".//w:t", ns) if node.text]
        text = " ".join(texts).strip()
        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n... (обрезано)"
        return text
    except Exception:
        return ""


async def _vision_describe_bytes(
    image_bytes: bytes,
    *,
    profile: str,
    mime: str = "image/jpeg",
) -> str:
    image_b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    from core.models.client_factory import create_openai_client

    vision = resolve_vision_config(profile=profile)
    client = create_openai_client(
        base_url=vision.base_url,
        api_key=vision.api_key,
        metadata=vision.provider_metadata,
    )
    response = await client.chat.completions.create(
        model=vision.model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Describe this image in detail. Transcribe visible text (OCR), "
                            "objects, tables, and diagrams."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{image_b64}"},
                    },
                ],
            }
        ],
        max_tokens=2000,
        temperature=0.2,
    )
    return (response.choices[0].message.content or "").strip()


async def describe_image_from_url(url: str, *, profile: str) -> str:
    """Describe an inline or remote image URL (Hermes multimodal gateway path)."""
    raw = (url or "").strip()
    if raw.startswith("data:"):
        header, _, payload = raw.partition(",")
        mime = "image/jpeg"
        if header.startswith("data:") and ";" in header:
            mime = header[5:].split(";", 1)[0] or mime
        image_bytes = base64.standard_b64decode(payload)
        return await _vision_describe_bytes(image_bytes, profile=profile, mime=mime)

    if raw.startswith(("http://", "https://")):
        import httpx

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(raw)
            response.raise_for_status()
            mime = response.headers.get("content-type", "image/jpeg").split(";", 1)[0]
            return await _vision_describe_bytes(response.content, profile=profile, mime=mime)

    raise ValueError(f"Unsupported image URL: {raw[:80]}")


async def describe_image(path: Path, *, profile: str) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    mime = mime or "image/jpeg"
    return await _vision_describe_bytes(path.read_bytes(), profile=profile, mime=mime)


async def enrich_saved_file(saved: SavedTelegramFile, *, profile: str) -> SavedTelegramFile:
    path = saved.path
    suffix = path.suffix.lower()

    if saved.kind == "image" or _is_image(saved.mime_type, saved.original_name):
        try:
            saved.description = await describe_image(path, profile=profile)
            saved.kind = "image"
        except Exception as exc:
            saved.description = f"(Не удалось распознать изображение: {exc})"
        return saved

    if suffix in _TEXT_SUFFIXES:
        saved.description = _read_text_file(path)
        return saved

    if suffix == ".pdf":
        text = _extract_pdf_text(path)
        saved.description = text or "(PDF сохранён; текст не извлечён — возможно скан без текстового слоя)"
        return saved

    if suffix == ".docx":
        text = _extract_docx_text(path)
        saved.description = text or "(DOCX сохранён; текст не извлечён)"
        return saved

    saved.description = f"(Файл сохранён: {saved.mime_type or 'unknown'})"
    return saved


async def save_telegram_attachment(
    bot: Any,
    file_id: str,
    *,
    profile: str,
    chat_id: int,
    file_name: str,
    mime_type: str = "",
    file_size: int = 0,
    bot_profile: str | None = None,
    telegram_user_id: int | None = None,
) -> SavedTelegramFile:
    max_bytes = int(settings.telegram_max_file_mb or 20) * 1024 * 1024
    if file_size and file_size > max_bytes:
        raise RuntimeError(
            f"Файл слишком большой ({file_size // 1024 // 1024} MB). "
            f"Лимит: {settings.telegram_max_file_mb} MB."
        )

    dest_dir = profile_files_dir(
        profile,
        chat_id,
        bot_profile=bot_profile,
        telegram_user_id=telegram_user_id,
    )
    dest = _unique_dest(dest_dir, file_name)
    size = await download_telegram_file_to_path(bot, file_id, dest)

    if size > max_bytes:
        dest.unlink(missing_ok=True)
        raise RuntimeError(
            f"Файл слишком большой ({size // 1024 // 1024} MB). "
            f"Лимит: {settings.telegram_max_file_mb} MB."
        )

    mime = (mime_type or mimetypes.guess_type(file_name)[0] or "").strip()
    kind = "image" if _is_image(mime, file_name) else "document"
    saved = SavedTelegramFile(
        path=dest,
        original_name=file_name,
        mime_type=mime,
        kind=kind,
        size_bytes=size,
    )
    return await enrich_saved_file(saved, profile=profile)


def format_files_preview(
    files: list[SavedTelegramFile],
    *,
    errors: list[str] | None = None,
    max_desc_chars: int = 280,
) -> str:
    from integrations.telegram.markdown import escape_html

    if not files:
        return "📎 <b>Файлы</b>\n\nНичего не сохранено."

    images = sum(1 for f in files if f.kind == "image")
    docs = len(files) - images
    parts = [f"📎 <b>Сохранено {len(files)}</b>"]
    if images:
        parts.append(f"фото: {images}")
    if docs:
        parts.append(f"документов: {docs}")
    lines = [" · ".join(parts), ""]

    for idx, item in enumerate(files, 1):
        label = "Фото" if item.kind == "image" else "Документ"
        lines.append(f"{idx}. <b>{label}</b> {escape_html(item.original_name)}")
        lines.append(f"   <code>{escape_html(str(item.path))}</code>")
        lines.append(f"   {item.size_bytes // 1024} KB")
        if item.description:
            short = item.description[:max_desc_chars]
            if len(item.description) > max_desc_chars:
                short += "…"
            lines.append(f"   <i>{escape_html(short)}</i>")
        lines.append("")

    if errors:
        lines.append(f"⚠️ {escape_html('; '.join(errors))}")

    return "\n".join(lines).strip()


def build_agent_prompt(user_text: str, files: list[SavedTelegramFile]) -> str:
    lines = []
    task = (user_text or "").strip()
    images = [f for f in files if f.kind == "image" or _is_image(f.mime_type, f.original_name)]
    if task:
        lines.append(task)
    elif images:
        lines.append(
            "Проанализируй прикреплённое изображение на основе распознавания ниже "
            "и ответь по запросу пользователя."
        )
    else:
        lines.append("Обработай прикреплённые файлы.")

    lines.append("")
    lines.append("## Вложения из Telegram (уже загружены и сохранены)")
    lines.append(
        "Файлы уже приняты из чата и лежат на диске. "
        "НЕ проси пользователя загрузить их повторно."
    )
    for item in files:
        is_image = item.kind == "image" or _is_image(item.mime_type, item.original_name)
        lines.append(f"- **{item.original_name}** ({item.kind})")
        lines.append(f"  Путь: `{item.path}`")
        lines.append(f"  MIME: {item.mime_type or 'unknown'} · {item.size_bytes} bytes")
        if is_image:
            lines.append(
                "  Тип: изображение — read_file для JPEG/PNG не подходит; "
                "используй блок «Содержимое / распознавание» ниже."
            )
        if item.description:
            lines.append("  Содержимое / распознавание (vision, уже выполнено):")
            lines.append("  ```")
            lines.append(item.description.strip())
            lines.append("  ```")
        elif is_image:
            lines.append("  (Распознавание недоступно — опиши ограничение пользователю.)")
    lines.append("")
    if images:
        lines.append(
            "Для изображений опирайся на vision-описание выше — это основной источник. "
            "Не вызывай read_file для бинарных фото."
        )
        lines.append("")
    lines.append(
        "Для текстовых файлов используй read_file/write_file. "
        "Чтобы отправить сформированные файлы пользователю в Telegram, вызови "
        "send_chat_files с путями (2–10 файлов отправятся альбомом). "
        "Не удаляй оригиналы без явного запроса пользователя."
    )
    return "\n".join(lines)