"""Build custom sub-agent types from a short user brief."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from typing import Any

from core.subagents.store import (
    DEFAULT_CUSTOM_TOOLS,
    SUBAGENT_TOOL_CHOICES,
    CustomSubAgentType,
    validate_custom_type_name,
)

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9]+")
_STOP = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "with",
        "for",
        "that",
        "who",
        "which",
        "you",
        "are",
        "is",
        "agent",
        "агент",
        "ты",
        "который",
        "которая",
        "которые",
        "using",
        "use",
        "и",
        "с",
        "на",
        "для",
        "это",
        "как",
    }
)

_CODE_HINTS = (
    "code",
    "coder",
    "python",
    "java",
    "typescript",
    "javascript",
    "golang",
    "rust",
    "разработ",
    "developer",
    "программ",
    "di",
    "dishka",
    "fastapi",
    "backend",
    "frontend",
    "api",
)
_REVIEW_HINTS = ("review", "ревью", "audit", "security", "qa", "quality")
_RESEARCH_HINTS = ("research", "исслед", "search", "анализ", "analyst", "data")
_WRITE_HINTS = ("writer", "docs", "document", "readme", "техническ", "писат")
_WEB_HINTS = ("web", "http", "scrap", "fetch", "browser")

_CYRILLIC_RE = re.compile(r"[а-яА-ЯёЁ]")

# Role family → name prefix (coder-python, reviewer-security, …)
_TYPE_PREFIX_CODE = "coder"
_TYPE_PREFIX_REVIEW = "reviewer"
_TYPE_PREFIX_RESEARCH = "researcher"
_TYPE_PREFIX_WRITE = "writer"
_TYPE_PREFIX_WEB = "web"
_TYPE_PREFIX_DEFAULT = "agent"

_PREFIX_STOP = frozenset(
    {
        "coder",
        "code",
        "coding",
        "reviewer",
        "review",
        "researcher",
        "research",
        "writer",
        "write",
        "web",
        "agent",
        "senior",
        "junior",
        "middle",
        "lead",
        "developer",
        "engineer",
        "dev",
        "программист",
        "разработчик",
        "сеньор",
        "синьор",
    }
)

# Map common non-latin / aliases to stable latin specialty tokens
_SPECIALTY_ALIASES: dict[str, str] = {
    "питон": "python",
    "пайтон": "python",
    "питоновский": "python",
    "джава": "java",
    "тайпскрипт": "typescript",
    "джаваскрипт": "javascript",
    "голанг": "golang",
    "го": "go",
    "раст": "rust",
    "дишка": "dishka",
    "дишкаа": "dishka",
    "фастапи": "fastapi",
    "джанго": "django",
    "фласк": "flask",
    "реакт": "react",
    "вью": "vue",
    "ангуляр": "angular",
    "кубер": "k8s",
    "кубернетес": "k8s",
    "докер": "docker",
    "постгрес": "postgres",
    "постгре": "postgres",
    "редис": "redis",
    "секьюрити": "security",
    "безопасность": "security",
}


def type_prefix_from_brief(brief: str) -> str:
    """Return name family prefix from role brief (coder / reviewer / …).

    More specific roles (review / research / write / web) win over generic
    code keywords so «security code review» becomes ``reviewer-…``, not ``coder-…``.
    """
    text = (brief or "").lower()
    if any(h in text for h in _REVIEW_HINTS):
        return _TYPE_PREFIX_REVIEW
    if any(h in text for h in _RESEARCH_HINTS):
        return _TYPE_PREFIX_RESEARCH
    if any(h in text for h in _WRITE_HINTS):
        return _TYPE_PREFIX_WRITE
    if any(h in text for h in _WEB_HINTS):
        return _TYPE_PREFIX_WEB
    if any(h in text for h in _CODE_HINTS):
        return _TYPE_PREFIX_CODE
    return _TYPE_PREFIX_DEFAULT


def specialty_tokens_from_brief(brief: str, *, limit: int = 2) -> list[str]:
    """Extract latin specialty tokens for name suffix (python, dishka, …)."""
    seen: set[str] = set()
    out: list[str] = []
    for w in _WORD_RE.findall(brief or ""):
        low = w.lower()
        if low in _STOP or low in _PREFIX_STOP or len(low) < 2:
            continue
        token = _SPECIALTY_ALIASES.get(low)
        if token is None:
            if re.match(r"^[a-z][a-z0-9]*$", low):
                token = low
            else:
                continue
        if token in _PREFIX_STOP or token in seen:
            continue
        seen.add(token)
        out.append(token)
        if len(out) >= limit:
            break
    return out


def slug_from_brief(brief: str, *, preferred: str | None = None) -> str:
    """Derive a valid custom type name from optional preferred name or brief text.

    Auto names follow ``{type}-{specialty}`` (e.g. ``coder-python``, ``reviewer-security``).
    """
    if preferred and preferred.strip():
        raw = preferred.strip().lower()
    else:
        prefix = type_prefix_from_brief(brief)
        specialty = specialty_tokens_from_brief(brief, limit=2)
        if specialty:
            raw = f"{prefix}-{'-'.join(specialty)}"
        else:
            raw = f"{prefix}-custom"
    raw = re.sub(r"[^a-z0-9_-]+", "-", raw.lower())
    raw = re.sub(r"-{2,}", "-", raw).strip("-_")
    if not raw or not raw[0].isalpha():
        raw = f"agent-{raw}" if raw else "custom-agent"
    raw = raw[:48]
    # ensure validate passes length 2+
    if len(raw) < 2:
        raw = "agent"
    try:
        return validate_custom_type_name(raw)
    except ValueError:
        # collision with builtin or invalid — prefix
        alt = f"x-{raw}"[:48]
        if not alt[0].isalpha():
            alt = f"agent-{raw}"[:48]
        return validate_custom_type_name(alt)


def unique_type_name(base: str, existing: Iterable[str]) -> str:
    """Return base or base-2, base-3… not in existing (builtins + customs)."""
    taken = {str(n).strip().lower() for n in existing}
    try:
        name = validate_custom_type_name(base)
    except ValueError:
        name = slug_from_brief(base)
    if name not in taken:
        return name
    n = 2
    while True:
        candidate = f"{name}-{n}"[:48]
        try:
            candidate = validate_custom_type_name(candidate)
        except ValueError:
            candidate = validate_custom_type_name(f"agent{n}")
        if candidate not in taken:
            return candidate
        n += 1


def infer_tools_from_brief(brief: str) -> list[str]:
    text = (brief or "").lower()
    tools: list[str] = list(DEFAULT_CUSTOM_TOOLS)
    if any(h in text for h in _CODE_HINTS):
        tools = [
            "read_file",
            "write_file",
            "list_directory",
            "grep",
            "glob",
            "delete_file",
            "terminal",
            "code_executor",
        ]
    elif any(h in text for h in _REVIEW_HINTS):
        tools = ["read_file", "list_directory", "grep", "glob", "terminal"]
    elif any(h in text for h in _RESEARCH_HINTS):
        tools = ["web_search", "web_fetch", "read_file", "list_directory", "grep", "glob"]
    elif any(h in text for h in _WRITE_HINTS):
        tools = ["read_file", "write_file", "list_directory", "grep", "glob", "delete_file"]
    if any(h in text for h in _WEB_HINTS):
        for t in ("web_search", "web_fetch"):
            if t not in tools:
                tools.append(t)
    allowed = set(SUBAGENT_TOOL_CHOICES)
    return [t for t in tools if t in allowed] or list(DEFAULT_CUSTOM_TOOLS)


def _is_cyrillic(text: str) -> bool:
    return bool(_CYRILLIC_RE.search(text or ""))


def _role_archetype(brief: str) -> str:
    text = (brief or "").lower()
    if any(h in text for h in _CODE_HINTS):
        return "implementation engineer"
    if any(h in text for h in _REVIEW_HINTS):
        return "code reviewer"
    if any(h in text for h in _RESEARCH_HINTS):
        return "research analyst"
    if any(h in text for h in _WRITE_HINTS):
        return "technical writer"
    if any(h in text for h in _WEB_HINTS):
        return "web researcher"
    return "specialized assistant"


def _key_terms(brief: str, *, limit: int = 12) -> list[str]:
    words = [w for w in _WORD_RE.findall(brief or "") if w.lower() not in _STOP and len(w) > 2]
    seen: set[str] = set()
    out: list[str] = []
    for w in words:
        key = w.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(w)
        if len(out) >= limit:
            break
    return out


def short_description(brief: str, *, max_len: int = 160) -> str:
    """One-line human summary (not a raw dump of the full brief)."""
    line = re.sub(r"\s+", " ", (brief or "").strip())
    if not line:
        return "Custom specialized sub-agent"
    # Prefer first sentence-ish chunk
    for sep in (". ", "! ", "? ", "。"):
        if sep in line:
            line = line.split(sep, 1)[0].strip()
            break
    if len(line) <= max_len:
        return line
    return line[: max_len - 1].rstrip() + "…"


def expand_system_prompt(brief: str) -> str:
    """Turn a short user brief into a full LLM system prompt (not a raw paste).

    Deterministic template used when LLM expansion is unavailable.
    """
    body = re.sub(r"\s+", " ", (brief or "").strip())
    if not body:
        body = "a capable specialized assistant for the assigned task"

    # Drop leading second-person fluff so we rewrite into a proper role block
    cleaned = (
        re.sub(
            r"^(ты|you are|you're|you|агент|agent)\s+",
            "",
            body,
            flags=re.IGNORECASE,
        ).strip()
        or body
    )

    archetype = _role_archetype(body)
    terms = _key_terms(body)
    expertise = ", ".join(terms[:8]) if terms else cleaned
    ru = _is_cyrillic(body)

    if ru:
        role_line = (
            f"Ты специализированный субагент Holix ({archetype}). Твоя предметная роль: {cleaned}."
        )
        expertise_h = "## Экспертиза"
        work_h = "## Как ты работаешь"
        constraints_h = "## Ограничения"
        report_h = "## Отчёт родителю"
        rules_h = "## Операционные правила"
        work_bullets = [
            "- Выполняй только назначенную задачу; не расширяй scope без необходимости.",
            "- Следуй соглашениям, архитектуре и библиотекам уже существующего проекта.",
            "- Перед правками читай релевантный код; после изменений проверяй результат.",
            "- Предпочитай ясные, тестируемые решения и принятые паттерны (SOLID, DI и т.п., если уместно).",
        ]
        constraints = [
            "- Не удаляй и не перезаписывай несвязанные файлы.",
            "- Не меняй инфраструктуру/секреты без явной просьбы в задаче.",
            "- Если контекста не хватает — зафиксируй допущения кратко, не блокируйся.",
        ]
        report = [
            "- Верни родителю краткий итог: что сделано, какие файлы затронуты, как проверить.",
            "- Перечисли риски или незакрытые пункты, если они есть.",
        ]
        rules = [
            "- Работай через доступные tools аккуратно и по делу.",
            "- Не выдумывай пути файлов — проверяй list_directory / read_file.",
            "- Язык ответов: русский, если задача на русском; иначе язык задачи.",
        ]
    else:
        role_line = (
            f"You are a specialized Holix sub-agent ({archetype}). Your domain role: {cleaned}."
        )
        expertise_h = "## Expertise"
        work_h = "## How you work"
        constraints_h = "## Constraints"
        report_h = "## Report to parent"
        rules_h = "## Operating rules"
        work_bullets = [
            "- Focus only on the assigned task; do not expand scope without need.",
            "- Follow existing project conventions, libraries, and architecture.",
            "- Read relevant code before editing; verify results after changes.",
            "- Prefer clear, testable solutions and established patterns when appropriate.",
        ]
        constraints = [
            "- Never delete or overwrite unrelated files.",
            "- Do not change infrastructure or secrets unless the task explicitly requires it.",
            "- If context is missing, state brief assumptions and continue productively.",
        ]
        report = [
            "- Reply to the parent with a concise summary: what changed, files touched, how to verify.",
            "- Call out residual risks or unfinished items.",
        ]
        rules = [
            "- Use tools carefully and only as needed.",
            "- Do not invent file paths — verify with list_directory / read_file.",
            "- Match the language of the task in your final summary.",
        ]

    parts = [
        role_line,
        "",
        expertise_h,
        f"- Core focus: {expertise}",
        f"- Source brief (user intent, do not quote blindly): {body}",
        "",
        work_h,
        *work_bullets,
        "",
        constraints_h,
        *constraints,
        "",
        report_h,
        *report,
        "",
        rules_h,
        *rules,
        "",
    ]
    return "\n".join(parts)


_LLM_EXPAND_SYSTEM = """You write system prompts for specialized Holix sub-agents.

Given a short user role brief, produce a complete system prompt suitable for an LLM agent that will receive tools and a single task.

Requirements:
- Do NOT paste the brief as the whole prompt. Rewrite and expand it professionally.
- Structure with clear markdown sections: Role, Expertise, How you work, Constraints, Report to parent.
- Capture domain skills, libraries, patterns, and quality bar from the brief.
- Keep length roughly 400–900 words maximum; be concrete, not fluffy.
- Match the language of the brief (Russian brief → Russian prompt; English → English).
- Output ONLY the system prompt text, no preamble or quotes.
"""


async def expand_system_prompt_via_llm(
    brief: str,
    *,
    profile: str | None = None,
    client: Any | None = None,
    model: str | None = None,
) -> str | None:
    """Ask the main-model LLM to expand a brief into a system prompt.

    Returns None if expansion fails (caller should use :func:`expand_system_prompt`).
    """
    text = (brief or "").strip()
    if len(text) < 8:
        return None

    resolved_client = client
    resolved_model = (model or "").strip() or None
    if resolved_client is None or not resolved_model:
        try:
            from core.models.manager import ModelManager
            from core.profile import init_profile

            prof = init_profile(profile or "default")
            mm = ModelManager(prof)
            mc = mm.get_default_model_config()
            if not mc:
                return None
            if resolved_client is None:
                resolved_client = mm.get_client(mc)
            resolved_model = resolved_model or mc.model
        except Exception as exc:
            logger.debug("LLM expand: no model client: %s", exc)
            return None

    if resolved_client is None or not resolved_model:
        return None

    try:
        response = await resolved_client.chat.completions.create(
            model=resolved_model,
            messages=[
                {"role": "system", "content": _LLM_EXPAND_SYSTEM},
                {
                    "role": "user",
                    "content": f"User brief:\n{text}\n\nWrite the system prompt now.",
                },
            ],
            temperature=0.4,
            max_tokens=1800,
            stream=False,
        )
        choice = response.choices[0] if response.choices else None
        if choice is None:
            return None
        out = (choice.message.content or "").strip()
        if len(out) < 80:
            return None
        # Strip accidental fences
        if out.startswith("```"):
            out = re.sub(r"^```(?:\w+)?\s*", "", out)
            out = re.sub(r"\s*```$", "", out).strip()
        return out
    except Exception as exc:
        logger.info("LLM system-prompt expand failed: %s", exc)
        return None


def normalize_model_slot(model_slot: str | None) -> str:
    """Empty / main / inherit → '' (use parent main agent model)."""
    slot = (model_slot or "").strip()
    if slot.lower() in ("", "main", "default", "inherit", "parent"):
        return ""
    return slot


def build_custom_type_from_brief(
    brief: str,
    *,
    name: str | None = None,
    existing_names: Iterable[str] | None = None,
    tools: list[str] | None = None,
    max_steps: int = 150,
    temperature: float = 0.3,
    model_slot: str | None = None,
    system_prompt: str | None = None,
) -> CustomSubAgentType:
    """Expand a short role brief into a full custom sub-agent type definition.

    ``system_prompt`` may be pre-generated (e.g. via LLM); otherwise a structured
    deterministic expansion is used — never a raw paste of the brief alone.
    """
    text = (brief or "").strip()
    if len(text) < 8:
        raise ValueError("Description is too short — write at least a short role sentence")
    existing = list(existing_names or [])
    base = slug_from_brief(text, preferred=name)
    type_name = unique_type_name(base, existing)
    prompt = (system_prompt or "").strip() or expand_system_prompt(text)
    return CustomSubAgentType(
        name=type_name,
        description=short_description(text),
        system_prompt=prompt,
        tools=tools or infer_tools_from_brief(text),
        max_steps=max_steps,
        temperature=temperature,
        model_slot=normalize_model_slot(model_slot),
    )


async def build_custom_type_from_brief_async(
    brief: str,
    *,
    name: str | None = None,
    existing_names: Iterable[str] | None = None,
    tools: list[str] | None = None,
    max_steps: int = 150,
    temperature: float = 0.3,
    model_slot: str | None = None,
    profile: str | None = None,
    client: Any | None = None,
    model: str | None = None,
) -> CustomSubAgentType:
    """Like :func:`build_custom_type_from_brief` but prefers LLM-expanded prompts."""
    llm_prompt = await expand_system_prompt_via_llm(
        brief, profile=profile, client=client, model=model
    )
    return build_custom_type_from_brief(
        brief,
        name=name,
        existing_names=existing_names,
        tools=tools,
        max_steps=max_steps,
        temperature=temperature,
        model_slot=model_slot,
        system_prompt=llm_prompt,
    )
