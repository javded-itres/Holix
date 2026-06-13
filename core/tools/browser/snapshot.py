"""Build LLM-friendly page snapshots with stable element refs."""

from __future__ import annotations

from typing import Any

_MAX_ELEMENTS = 60
_MAX_TEXT = 120


async def build_page_snapshot(page: Any) -> tuple[str, dict[str, str]]:
    """Tag interactive elements; return (text, ref -> selector map)."""
    refs: dict[str, str] = {}

    await page.evaluate(
        """() => {
            document.querySelectorAll('[data-holix-ref]').forEach(el => {
                el.removeAttribute('data-holix-ref');
            });
        }"""
    )

    elements = await page.locator(
        "a[href], button, input, textarea, select, "
        "[role='button'], [role='link'], [role='textbox'], [role='combobox']"
    ).all()

    lines: list[str] = []
    index = 0

    for el in elements:
        if index >= _MAX_ELEMENTS:
            lines.append(f"... ({len(elements) - _MAX_ELEMENTS} more elements omitted)")
            break

        try:
            if not await el.is_visible():
                continue
        except Exception:
            continue

        index += 1
        ref = f"e{index}"
        selector = f'[data-holix-ref="{ref}"]'

        try:
            await el.evaluate(
                "(el, ref) => el.setAttribute('data-holix-ref', ref)",
                ref,
            )
        except Exception:
            continue

        refs[ref] = selector

        tag = await el.evaluate("el => el.tagName.toLowerCase()")
        role = await el.get_attribute("role") or tag
        name = await el.get_attribute("aria-label") or await el.get_attribute("name") or ""
        text = ""
        try:
            text = (await el.inner_text())[:_MAX_TEXT].replace("\n", " ")
        except Exception:
            pass
        placeholder = await el.get_attribute("placeholder") or ""
        input_type = await el.get_attribute("type") or ""
        href = await el.get_attribute("href") or ""

        label = name or text or placeholder or href or role
        extra = ""
        if input_type and tag == "input":
            extra = f" type={input_type}"
        lines.append(f"[{ref}] {role}{extra} \"{label.strip()[:_MAX_TEXT]}\"")

    title = await page.title()
    header = f"URL: {page.url}\nTitle: {title}\n"
    body = "\n".join(lines) if lines else "(no interactive elements — try browser_wait)"
    return header + body, refs