"""Classify Telegram image overviews and route to specialist models."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Minimum keyword score to pick a specialist route (else general-only overview).
_ROUTE_SCORE_THRESHOLD = 2


@dataclass(frozen=True, slots=True)
class ImageRouteSpec:
    category: str
    label_ru: str
    specialist_model: str
    use_image: bool
    keywords: tuple[str, ...]
    specialist_prompt: str


@dataclass(slots=True)
class ImageRouteResult:
    category: str
    label_ru: str
    specialist_model: str
    score: int
    use_image: bool
    specialist_prompt: str


_IMAGE_ROUTES: tuple[ImageRouteSpec, ...] = (
    ImageRouteSpec(
        category="medicine",
        label_ru="медицина",
        specialist_model="medgemma:27b",
        use_image=True,
        keywords=(
            "x-ray",
            "xray",
            "mri",
            "ct scan",
            "ultrasound",
            "medical",
            "clinical",
            "patient",
            "diagnosis",
            "anatomy",
            "fracture",
            "tumor",
            "lesion",
            "radiograph",
            "медицин",
            "рентген",
            "снимок",
            "диагноз",
            "пациент",
            "мрт",
            "кт",
            "узи",
            "перелом",
            "анатом",
        ),
        specialist_prompt=(
            "You are a medical imaging assistant. Analyze this clinical image in detail. "
            "Describe visible structures, findings, and regions of interest. "
            "Transcribe labels and measurements. "
            "End with a short disclaimer that this is not a medical diagnosis."
        ),
    ),
    ImageRouteSpec(
        category="code",
        label_ru="код",
        specialist_model="coder",
        use_image=False,
        keywords=(
            "code",
            "python",
            "javascript",
            "typescript",
            "function",
            "class ",
            "def ",
            "import ",
            "syntax",
            "ide",
            "vscode",
            "terminal",
            "stack trace",
            "error message",
            "github",
            "repository",
            "sql",
            "api",
            "код",
            "функци",
            "ошибк",
            "терминал",
            "репозитор",
            "программ",
        ),
        specialist_prompt=(
            "You are a senior software engineer. Based on the image overview and OCR below, "
            "analyze the code or technical screenshot: structure, intent, bugs, and improvements. "
            "If code is present, quote the important fragments."
        ),
    ),
    ImageRouteSpec(
        category="food",
        label_ru="еда",
        specialist_model="balanced",
        use_image=True,
        keywords=(
            "food",
            "meal",
            "dish",
            "plate",
            "nutrition",
            "calorie",
            "recipe",
            "ingredient",
            "fruit",
            "vegetable",
            "restaurant",
            "breakfast",
            "lunch",
            "dinner",
            "еда",
            "блюдо",
            "тарелк",
            "калори",
            "нутриент",
            "рецепт",
            "ингредиент",
            "завтрак",
            "обед",
            "ужин",
        ),
        specialist_prompt=(
            "You are a nutrition assistant. Analyze this food image: identify dishes and "
            "ingredients, estimate portions, and give approximate calories and macros. "
            "Note uncertainty where visibility is limited."
        ),
    ),
    ImageRouteSpec(
        category="document",
        label_ru="документ",
        specialist_model="research",
        use_image=False,
        keywords=(
            "chart",
            "graph",
            "table",
            "diagram",
            "spreadsheet",
            "invoice",
            "receipt",
            "form",
            "document",
            "report",
            "slide",
            "presentation",
            "диаграм",
            "график",
            "таблиц",
            "документ",
            "отчёт",
            "отчет",
            "счёт",
            "счет",
            "презентац",
        ),
        specialist_prompt=(
            "You are a document analyst. Based on the overview and OCR, extract structured facts, "
            "summarize tables/charts, and list key figures and conclusions."
        ),
    ),
)

_GENERAL_ROUTE = ImageRouteResult(
    category="general",
    label_ru="общее",
    specialist_model="",
    score=0,
    use_image=False,
    specialist_prompt="",
)


def _normalize_overview(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _score_route(spec: ImageRouteSpec, overview: str) -> int:
    score = 0
    for keyword in spec.keywords:
        if keyword in overview:
            score += 2 if " " in keyword else 1
    return score


def classify_image_overview(overview: str) -> ImageRouteResult:
    """Pick a specialist route from a high-level vision overview."""
    normalized = _normalize_overview(overview)
    if not normalized:
        return _GENERAL_ROUTE

    best: ImageRouteResult | None = None
    for spec in _IMAGE_ROUTES:
        score = _score_route(spec, normalized)
        if score < _ROUTE_SCORE_THRESHOLD:
            continue
        candidate = ImageRouteResult(
            category=spec.category,
            label_ru=spec.label_ru,
            specialist_model=spec.specialist_model,
            score=score,
            use_image=spec.use_image,
            specialist_prompt=spec.specialist_prompt,
        )
        if best is None or candidate.score > best.score:
            best = candidate

    return best or _GENERAL_ROUTE


def _route_spec_for(category: str) -> ImageRouteSpec | None:
    for spec in _IMAGE_ROUTES:
        if spec.category == category:
            return spec
    return None


def format_routed_description(
    *,
    overview: str,
    overview_model: str,
    route: ImageRouteResult,
    specialist_text: str = "",
    specialist_model: str = "",
) -> str:
    """Merge overview and optional specialist analysis for agent prompts."""
    parts = [
        f"Категория: {route.label_ru} ({route.category})",
        "",
        f"## Обзор ({overview_model})",
        overview.strip(),
    ]
    if specialist_text.strip():
        model_label = specialist_model or route.specialist_model or "specialist"
        parts.extend(
            [
                "",
                f"## Специализированный анализ — {route.label_ru} ({model_label})",
                specialist_text.strip(),
            ]
        )
    return "\n".join(parts).strip()


async def analyze_with_specialist(
    *,
    overview: str,
    overview_model: str,
    image_bytes: bytes,
    mime: str,
    profile: str,
    route: ImageRouteResult,
    vision_describe_fn: Any,
    text_analyze_fn: Any,
) -> str:
    """Run a second pass with the routed specialist model."""
    if not route.specialist_model or route.category == "general":
        return format_routed_description(overview=overview, overview_model=overview_model, route=route)

    spec = _route_spec_for(route.category)
    if spec is None:
        return format_routed_description(overview=overview, overview_model=overview_model, route=route)

    specialist_text = ""
    specialist_model = route.specialist_model
    context = f"Image overview:\n{overview.strip()}"

    try:
        if route.use_image:
            specialist_text = await vision_describe_fn(
                image_bytes,
                profile=profile,
                mime=mime,
                model=specialist_model,
                prompt=spec.specialist_prompt,
            )
        else:
            specialist_text = await text_analyze_fn(
                profile=profile,
                model=specialist_model,
                system_prompt=spec.specialist_prompt,
                user_text=context,
            )
    except Exception as exc:
        fallback_model = "fast" if specialist_model != "fast" else "balanced"
        try:
            if route.use_image:
                specialist_text = await vision_describe_fn(
                    image_bytes,
                    profile=profile,
                    mime=mime,
                    model=fallback_model,
                    prompt=spec.specialist_prompt,
                )
            else:
                specialist_text = await text_analyze_fn(
                    profile=profile,
                    model=fallback_model,
                    system_prompt=spec.specialist_prompt,
                    user_text=context,
                )
            specialist_model = fallback_model
        except Exception:
            specialist_text = f"(Специализированный анализ недоступен: {exc})"

    return format_routed_description(
        overview=overview,
        overview_model=overview_model,
        route=route,
        specialist_text=specialist_text,
        specialist_model=specialist_model,
    )