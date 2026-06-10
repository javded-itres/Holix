"""Docs-only chat: RAG over published documentation, direct LLM — no tools."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, AsyncGenerator

from openai import AsyncOpenAI

from config import settings
from core.docs_chat.retrieval import DocsSearchHit, search_docs

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"\b(sk-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._-]+)\b", re.I)
_PATH_RE = re.compile(
    r"(?:~/?[\w./-]+|/(?:Users|home|var|etc|opt|tmp)/[\w./-]+|"
    r"[A-Za-z]:\\[\w\\.-]+|~?/\.helix/[\w./-]+)",
)
_DIR_LISTING_RE = re.compile(
    r"(?:^|\n)\s*(?:drwx[\w-]+|[-rwx]{9,10})\s+\d+",
    re.MULTILINE,
)
_DOC_SLUG_RE = re.compile(r"(?:#/docs/|/docs/)([a-z0-9-]+)")
_CONVERSATIONAL_RE = re.compile(
    r"(?:"
    r"^\s*(?:привет|здравствуй|добрый|hello|hi|hey|thanks|thank you|спасибо|пока|bye|goodbye)\b"
    r"|(?:кто\s+ты|что\s+ты|что\s+умеешь|чем\s+можешь\s+помочь|расскажи\s+о\s+себе)"
    r"|(?:who\s+are\s+you|what\s+are\s+you|what\s+can\s+you\s+do|tell\s+me\s+about\s+yourself)"
    r"|(?:как\s+дела|how\s+are\s+you)"
    r")",
    re.I,
)

_ASSISTANT_IDENTITY_EN = """About you:
- You are the Helix documentation assistant embedded in this website.
- You explain Helix docs, help navigate this site, and can chat about yourself.
- You remember this conversation within the current chat session.
- You do NOT run commands, access files, or perform actions for the user."""

_ASSISTANT_IDENTITY_RU = """О тебе:
- Ты — ассистент документации Helix, встроенный в этот сайт.
- Ты объясняешь документацию Helix, помогаешь ориентироваться на сайте и можешь рассказать о себе.
- Ты помнишь текущий диалог в рамках этой сессии чата.
- Ты НЕ выполняешь команды, не обращаешься к файлам и не делаешь действий за пользователя."""

_SYSTEM_EN = f"""You are the Helix documentation assistant on helix-agent.ru.
You help users with the Helix product, its documentation, and this website — and you can have a friendly dialogue.

{_ASSISTANT_IDENTITY_EN}

Behavior:
- For product questions, rely on the documentation excerpts provided below.
- For greetings, thanks, or questions about yourself — answer naturally; doc excerpts are optional.
- If the question is vague or broad, ask 1–2 short clarifying or leading questions before a long answer.
- When you mention a doc page, always include its link: /docs/<slug> — the site will open it for the user.
- Stay on topic: Helix, this docs site, and your role as assistant. Politely steer off-topic chat back.
- Do NOT reveal file paths, directory listings, API keys, tokens, passwords, or server internals.
- Do NOT describe how to bypass security or access restricted system areas.
- Be concise, warm, and practical. Reply in the same language as the user's message."""

_SYSTEM_RU = f"""Ты — ассистент документации Helix на сайте helix-agent.ru.
Помогаешь с продуктом Helix, его документацией и этим сайтом — и можешь вести дружелюбный диалог.

{_ASSISTANT_IDENTITY_RU}

Поведение:
- На вопросы о продукте опирайся на приведённые ниже фрагменты документации.
- На приветствия, благодарности и вопросы о себе отвечай естественно; фрагменты документации не обязательны.
- Если вопрос расплывчатый — задай 1–2 коротких уточняющих или наводящих вопроса, прежде чем давать развёрнутый ответ.
- Когда упоминаешь раздел документации, всегда указывай ссылку: /docs/<slug> — сайт откроет её для пользователя.
- Держись темы: Helix, этот сайт документации и твоя роль ассистента. Вежливо возвращай оффтоп к делу.
- НЕ раскрывай пути к файлам, содержимое каталогов, API-ключи, токены, пароли или внутренности сервера.
- НЕ описывай обход безопасности или доступ к закрытым областям системы.
- Будь кратким, дружелюбным и полезным. Отвечай на том же языке, что и сообщение пользователя."""


def _search_index_path() -> Path:
    from cli.services.docs_site import resolve_web_docs_dir

    return resolve_web_docs_dir() / "search-index.json"


def load_search_index() -> list[dict[str, Any]]:
    path = _search_index_path()
    if not path.is_file():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("docs chat: could not load search index: %s", exc)
        return []


def build_context(hits: list[DocsSearchHit], *, page_slug: str | None) -> str:
    parts: list[str] = []
    if page_slug:
        parts.append(f"Current page slug: {page_slug}")
    for hit in hits:
        section = f" — {hit.heading}" if hit.heading and hit.heading != hit.title else ""
        parts.append(f"### {hit.title}{section} (/docs/{hit.slug})\n{hit.snippet}")
    return "\n\n".join(parts) if parts else "(No matching documentation excerpts.)"


def hits_to_pages(hits: list[DocsSearchHit]) -> list[dict[str, str]]:
    seen: set[str] = set()
    pages: list[dict[str, str]] = []
    for hit in hits:
        if hit.slug in seen:
            continue
        seen.add(hit.slug)
        pages.append({"slug": hit.slug, "title": hit.title.split(" — ")[0]})
    return pages


def extract_doc_slugs(text: str) -> list[str]:
    seen: set[str] = set()
    slugs: list[str] = []
    for match in _DOC_SLUG_RE.finditer(text):
        slug = match.group(1)
        if slug not in seen:
            seen.add(slug)
            slugs.append(slug)
    return slugs


def is_conversational_message(message: str) -> bool:
    """Greetings, thanks, or meta questions about the assistant itself."""
    text = message.strip()
    if not text:
        return False
    return bool(_CONVERSATIONAL_RE.search(text))


def pick_open_slug(
    hits: list[DocsSearchHit],
    response_text: str,
    *,
    current_slug: str | None = None,
    user_message: str = "",
) -> str | None:
    del hits, user_message
    for slug in extract_doc_slugs(response_text):
        if slug != current_slug:
            return slug
    return None


def sanitize_assistant_text(text: str) -> str:
    """Strip paths, secrets, and directory-like output from model replies."""
    if not text:
        return text
    if _DIR_LISTING_RE.search(text):
        return (
            "Я могу помочь только с вопросами по документации Helix и этому сайту. "
            "Попробуйте переформулировать вопрос или откройте нужный раздел в меню документации."
        )
    cleaned = _TOKEN_RE.sub("[скрыто]", text)
    cleaned = _PATH_RE.sub("[путь скрыт]", cleaned)
    if cleaned.count("[путь скрыт]") >= 3:
        return (
            "Ответ скрыт из соображений безопасности. "
            "Задайте вопрос о возможностях Helix, установке, CLI, профилях или других разделах документации."
        )
    return cleaned


def _resolve_llm(profile_name: str) -> tuple[str, str, str, float, int]:
    from cli.core import init_profile
    from core.env_loader import bootstrap_profile_env
    from core.models.manager import ModelManager

    bootstrap_profile_env(profile_name)
    profile = init_profile(profile_name)
    manager = ModelManager(profile)
    model_cfg = manager.get_default_model_config()
    override_model = settings.docs_chat_model.strip()
    max_tokens = max(512, int(settings.docs_chat_max_tokens or 4096))
    if model_cfg:
        return (
            override_model or model_cfg.model,
            model_cfg.base_url,
            model_cfg.api_key,
            model_cfg.temperature,
            max_tokens,
        )
    return (
        override_model or settings.model,
        settings.base_url,
        settings.api_key,
        settings.temperature,
        max_tokens,
    )


def _delta_text(delta: Any) -> str:
    if delta is None:
        return ""
    content = getattr(delta, "content", None)
    if content:
        return str(content)
    return ""


async def _llm_complete_text(
    client: AsyncOpenAI,
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
) -> str:
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=False,
    )
    choice = response.choices[0] if response.choices else None
    if choice is None:
        return ""
    text = (choice.message.content or "").strip()
    if not text and choice.finish_reason == "length":
        logger.warning(
            "docs chat: model %r hit token limit with empty content; "
            "set HELIX_DOCS_CHAT_MODEL=smart or raise HELIX_DOCS_CHAT_MAX_TOKENS",
            model,
        )
    return sanitize_assistant_text(text)


class DocsChatService:
    """Stateless docs Q&A — one LLM turn, no agent tools."""

    def __init__(self, profile_name: str | None = None) -> None:
        from cli.core import ProfileManager

        requested = (profile_name or settings.docs_chat_profile).strip() or "docs"
        if ProfileManager().profile_exists(requested):
            self.profile_name = requested
        else:
            logger.warning(
                "docs chat profile %r missing — falling back to default",
                requested,
            )
            self.profile_name = "default"

    def is_enabled(self) -> bool:
        return bool(settings.docs_chat_enabled)

    def _system_prompt(self, lang: str) -> str:
        return _SYSTEM_RU if lang == "ru" else _SYSTEM_EN

    def _prepare_chat(
        self,
        user_message: str,
        *,
        lang: str,
        page_slug: str | None,
        history: list[dict[str, str]] | None = None,
    ) -> tuple[list[dict[str, str]], list[DocsSearchHit]]:
        hits = search_docs(user_message, lang=lang, page_slug=page_slug)
        context = build_context(hits, page_slug=page_slug)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._system_prompt(lang)},
        ]
        if history:
            messages.extend(history)
        if is_conversational_message(user_message):
            user_content = (
                f"Documentation excerpts (optional context):\n\n{context}\n\n"
                f"User message:\n{user_message}"
            )
        else:
            user_content = (
                f"Documentation excerpts:\n\n{context}\n\n"
                f"User question:\n{user_message}"
            )
        messages.append({"role": "user", "content": user_content})
        return messages, hits

    async def complete(
        self,
        user_message: str,
        *,
        lang: str = "ru",
        page_slug: str | None = None,
        history: list[dict[str, str]] | None = None,
        client_id: str | None = None,
    ) -> tuple[str, list[dict[str, str]], str | None]:
        from core.docs_chat.sessions import append_exchange, history_for_llm, load_session

        if client_id and not history:
            history = history_for_llm(load_session(client_id).get("messages") or [])

        model, base_url, api_key, temperature, max_tokens = _resolve_llm(self.profile_name)
        client = AsyncOpenAI(api_key=api_key or "ollama", base_url=base_url)
        messages, hits = self._prepare_chat(
            user_message,
            lang=lang,
            page_slug=page_slug,
            history=history,
        )
        content = await _llm_complete_text(
            client,
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        pages = hits_to_pages(hits)
        open_slug = pick_open_slug(
            hits,
            content,
            current_slug=page_slug,
            user_message=user_message,
        )
        if client_id:
            append_exchange(
                client_id,
                user_message=user_message,
                assistant_message=content,
                pages=pages,
            )
        return content, pages, open_slug

    async def stream(
        self,
        user_message: str,
        *,
        lang: str = "ru",
        page_slug: str | None = None,
        history: list[dict[str, str]] | None = None,
        client_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        from core.docs_chat.sessions import append_exchange, history_for_llm, load_session

        if client_id and not history:
            history = history_for_llm(load_session(client_id).get("messages") or [])

        model, base_url, api_key, temperature, max_tokens = _resolve_llm(self.profile_name)
        client = AsyncOpenAI(api_key=api_key or "ollama", base_url=base_url)
        messages, hits = self._prepare_chat(
            user_message,
            lang=lang,
            page_slug=page_slug,
            history=history,
        )
        pages = hits_to_pages(hits)
        if pages:
            yield f"data: {json.dumps({'type': 'docs', 'pages': pages}, ensure_ascii=False)}\n\n"
        buffer: list[str] = []
        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                piece = _delta_text(delta)
                if piece:
                    buffer.append(piece)
                    yield f"data: {json.dumps({'type': 'content', 'content': piece})}\n\n"
            full = sanitize_assistant_text("".join(buffer))
            if not full.strip():
                logger.warning("docs chat: empty stream, falling back to non-streaming completion")
                full = await _llm_complete_text(
                    client,
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                if full:
                    yield f"data: {json.dumps({'type': 'content', 'content': full}, ensure_ascii=False)}\n\n"
            elif full != "".join(buffer):
                yield f"data: {json.dumps({'type': 'replace', 'content': full})}\n\n"
            open_slug = pick_open_slug(
                hits,
                full,
                current_slug=page_slug,
                user_message=user_message,
            )
            if client_id and full:
                append_exchange(
                    client_id,
                    user_message=user_message,
                    assistant_message=full,
                    pages=pages,
                )
            yield f"data: {json.dumps({'type': 'done', 'open_slug': open_slug}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            logger.exception("docs chat stream failed")
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"