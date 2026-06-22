"""Image overview classification and specialist routing."""

from __future__ import annotations

from integrations.telegram.image_router import (
    classify_image_overview,
    format_routed_description,
)


def test_classify_medicine_xray() -> None:
    route = classify_image_overview(
        "Chest X-ray showing ribs, lungs and heart silhouette. Medical radiograph."
    )
    assert route.category == "medicine"
    assert route.specialist_model == "medgemma:27b"
    assert route.use_image is True


def test_classify_code_screenshot() -> None:
    route = classify_image_overview(
        "Screenshot of Python code in VS Code with a function definition and import statement."
    )
    assert route.category == "code"
    assert route.specialist_model == "coder"
    assert route.use_image is False


def test_classify_food_plate() -> None:
    route = classify_image_overview("A plate with pasta dish, vegetables and sauce in a restaurant.")
    assert route.category == "food"
    assert route.specialist_model == "balanced"


def test_classify_document_chart() -> None:
    route = classify_image_overview("Bar chart and table with quarterly revenue figures in a report.")
    assert route.category == "document"
    assert route.specialist_model == "research"


def test_classify_general_when_ambiguous() -> None:
    route = classify_image_overview("A person standing near a tree on a sunny day.")
    assert route.category == "general"
    assert route.specialist_model == ""


def test_format_routed_description_includes_sections() -> None:
    from integrations.telegram.image_router import ImageRouteResult

    route = ImageRouteResult(
        category="medicine",
        label_ru="медицина",
        specialist_model="medgemma:27b",
        score=4,
        use_image=True,
        specialist_prompt="analyze",
    )
    text = format_routed_description(
        overview="X-ray of shoulder joint.",
        overview_model="gemini-flash",
        route=route,
        specialist_text="Possible joint space narrowing.",
        specialist_model="medgemma:27b",
    )
    assert "Категория: медицина" in text
    assert "## Обзор (gemini-flash)" in text
    assert "## Специализированный анализ" in text
    assert "medgemma:27b" in text